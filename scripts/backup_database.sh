#!/usr/bin/env bash
# Dump production PostgreSQL to a timestamped file, upload to GCS, prune old objects.
# See docs/Deployment.md (Automated database backups).
set -euo pipefail

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
error() {
  log "ERROR: $*" >&2
  BACKUP_LAST_ERROR="$*"
}

DEPLOY_DIR="${DEPLOY_DIR:-/opt/boost-data-collector}"
ENV_FILE=""
DRY_RUN=false
LIST_RETENTION_ONLY=false
BACKUP_SHOULD_NOTIFY=false
BACKUP_LAST_ERROR=""
BACKUP_SUCCESS_DETAIL=""

usage() {
  cat <<'EOF'
Usage: backup_database.sh [OPTIONS]

Dump PostgreSQL (pg_dump -Fc), upload to GCS, and optionally delete bucket
objects older than BACKUP_RETENTION_DAYS (default 7; 0 disables pruning).

Options:
  --env-file PATH   Load environment from PATH (default: $DEPLOY_DIR/.env)
  --dry-run         Run dump and upload; list retention deletes without removing
  --list-retention  Only list GCS objects that would be deleted (no dump/upload)
  -h, --help        Show this help

Environment (see docs/Deployment.md):
  DATABASE_URL or DB_*     Database credentials (same as Django)
  BACKUP_DATABASE_URL      Optional override for backup connections
  BACKUP_GCS_BUCKET        Required GCS bucket name
  BACKUP_GCS_PREFIX        Optional; defaults to BACKUP_FILE_PREFIX (bdc/)
  BACKUP_FILE_PREFIX       Default bdc/ → files named bdc-YYYYMMDD.dump
  BACKUP_STAGING_DIR       Default /var/backups/boost-data-collector
  BACKUP_RETENTION_DAYS    Default 7; set 0 to keep all GCS dumps (no pruning)
  BACKUP_DELETE_LOCAL_AFTER_UPLOAD  Default true
  DISCORD_WEBHOOK_URL      Optional; notify on success/failure (same as deploy notify)
  SLACK_WEBHOOK_URL        Optional; notify on success/failure
  BACKUP_NOTIFICATIONS     Default true; set false to skip webhook posts

Exit codes: 0 success; 1 config/prereq; 2 pg_dump; 3 upload; 4 retention delete
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      [[ $# -ge 2 ]] || { error "--env-file requires a path"; exit 1; }
      ENV_FILE="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --list-retention)
      LIST_RETENTION_ONLY=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      error "Unknown option: $1"
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "$ENV_FILE" ]]; then
  ENV_FILE="${DEPLOY_DIR}/.env"
fi

if [[ ! -f "$ENV_FILE" ]]; then
  error ".env not found at ${ENV_FILE}"
  exit 1
fi
if [[ ! -r "$ENV_FILE" ]]; then
  error ".env is not readable: ${ENV_FILE}"
  exit 1
fi

# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a

PG_DUMP="${PG_DUMP:-pg_dump}"
GCLOUD="${GCLOUD:-gcloud}"
PYTHON=""
for _py_candidate in python3 python; do
  if command -v "$_py_candidate" >/dev/null 2>&1 && "$_py_candidate" -c "import sys" >/dev/null 2>&1; then
    PYTHON="$_py_candidate"
    break
  fi
done
BACKUP_FILE_PREFIX="${BACKUP_FILE_PREFIX:-bdc/}"
BACKUP_STAGING_DIR="${BACKUP_STAGING_DIR:-/var/backups/boost-data-collector}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
BACKUP_DELETE_LOCAL_AFTER_UPLOAD="${BACKUP_DELETE_LOCAL_AFTER_UPLOAD:-true}"

PREFIX_STEM="${BACKUP_FILE_PREFIX%/}"
GCS_PREFIX="${BACKUP_GCS_PREFIX:-$BACKUP_FILE_PREFIX}"
DUMP_BASENAME="${PREFIX_STEM}-$(date -u +%Y%m%d).dump"
DUMP_FILE="${BACKUP_STAGING_DIR}/${DUMP_BASENAME}"

send_backup_notification() {
  local status="$1"
  local exit_code="$2"
  local detail="$3"

  [[ -n "$PYTHON" ]] || return 0

  local notifications_enabled="${BACKUP_NOTIFICATIONS:-true}"
  if [[ "$notifications_enabled" == "false" || "$notifications_enabled" == "False" || "$notifications_enabled" == "0" ]]; then
    return 0
  fi

  local discord_url="${DISCORD_WEBHOOK_URL:-}"
  local slack_url="${SLACK_WEBHOOK_URL:-}"
  if [[ -z "$discord_url" && -z "$slack_url" ]]; then
    return 0
  fi

  BACKUP_NOTIFY_STATUS="$status" \
  BACKUP_NOTIFY_EXIT_CODE="$exit_code" \
  BACKUP_NOTIFY_DETAIL="$detail" \
  DISCORD_WEBHOOK_URL="$discord_url" \
  SLACK_WEBHOOK_URL="$slack_url" \
  DUMP_BASENAME="$DUMP_BASENAME" \
  "$PYTHON" - <<'PY' || return 1
import json
import os
import sys
from datetime import datetime, timezone
from urllib import request

status = os.environ["BACKUP_NOTIFY_STATUS"]
exit_code = os.environ["BACKUP_NOTIFY_EXIT_CODE"]
detail = os.environ.get("BACKUP_NOTIFY_DETAIL", "")
dump_name = os.environ.get("DUMP_BASENAME", "")
discord_url = (os.environ.get("DISCORD_WEBHOOK_URL") or "").strip()
slack_url = (os.environ.get("SLACK_WEBHOOK_URL") or "").strip()

if status == "success":
    title = "Database backup succeeded"
    color = 0x2ECC71
    slack_emoji = ":white_check_mark:"
else:
    title = "Database backup failed"
    color = 0xE74C3C
    slack_emoji = ":x:"

lines = [
    f"Status: {status}",
    f"Exit code: {exit_code}",
    f"Time (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}",
]
if dump_name:
    lines.append(f"Dump: {dump_name}")
if detail:
    lines.append("")
    lines.append(detail)
body = "\n".join(lines)

errors = []

if discord_url:
    embed = {
        "title": title,
        "description": body[:4000],
        "color": color,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    payload = {"username": "Boost Data Collector", "embeds": [embed]}
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        discord_url,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=15) as resp:
            if resp.status not in (200, 204):
                errors.append(f"Discord webhook returned status {resp.status}")
    except Exception as exc:
        errors.append(f"Discord webhook failed: {exc}")

if slack_url:
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": title, "emoji": True},
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": f"```{body[:2800]}```"}},
    ]
    payload = {
        "username": "Boost Data Collector",
        "blocks": blocks,
        "icon_emoji": slack_emoji,
    }
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        slack_url,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=15) as resp:
            if resp.status != 200:
                errors.append(f"Slack webhook returned status {resp.status}")
    except Exception as exc:
        errors.append(f"Slack webhook failed: {exc}")

if errors:
    for msg in errors:
        print(msg, file=sys.stderr)
    sys.exit(1)
PY
}

on_exit() {
  local exit_code=$?
  if [[ "$BACKUP_SHOULD_NOTIFY" == true ]]; then
    local status="failure"
    local detail="$BACKUP_LAST_ERROR"
    if (( exit_code == 0 )); then
      status="success"
      detail="$BACKUP_SUCCESS_DETAIL"
    elif [[ -z "$detail" ]]; then
      detail="Backup script exited with code ${exit_code}"
    fi
    if ! send_backup_notification "$status" "$exit_code" "$detail"; then
      log "WARNING: backup notification failed (non-fatal)" >&2
    fi
  fi
  exit "$exit_code"
}

if [[ "$LIST_RETENTION_ONLY" != true ]]; then
  BACKUP_SHOULD_NOTIFY=true
fi
trap on_exit EXIT

if [[ -z "${BACKUP_GCS_BUCKET:-}" ]]; then
  error "BACKUP_GCS_BUCKET is not set (configure in ${ENV_FILE})"
  exit 1
fi

if ! [[ "${BACKUP_RETENTION_DAYS}" =~ ^[0-9]+$ ]]; then
  error "BACKUP_RETENTION_DAYS must be a non-negative integer (got: ${BACKUP_RETENTION_DAYS})"
  exit 1
fi

resolve_database_uri() {
  "$PYTHON" - <<'PY'
import os
import sys
from urllib.parse import quote_plus, urlencode, urlparse, urlunparse

def rewrite_host_docker_internal(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("postgres", "postgresql"):
        sys.stderr.write(f"ERROR: unsupported database URL scheme: {parsed.scheme!r}\n")
        sys.exit(1)
    if parsed.hostname == "host.docker.internal":
        port = parsed.port or 5432
        userinfo = parsed.netloc.split("@", 1)[0] if "@" in parsed.netloc else ""
        new_netloc = f"{userinfo}@127.0.0.1:{port}" if userinfo else f"127.0.0.1:{port}"
        parsed = parsed._replace(netloc=new_netloc)
        return urlunparse(parsed)
    return url

backup_url = (os.environ.get("BACKUP_DATABASE_URL") or "").strip()
if backup_url:
    print(rewrite_host_docker_internal(backup_url))
    sys.exit(0)

db_url = (os.environ.get("DATABASE_URL") or "").strip()
if db_url:
    print(rewrite_host_docker_internal(db_url))
    sys.exit(0)

name = (os.environ.get("DB_NAME") or "boost_dashboard").strip()
user = (os.environ.get("DB_USER") or "").strip()
password = os.environ.get("DB_PASSWORD") or ""
host = (os.environ.get("DB_HOST") or "localhost").strip()
port = (os.environ.get("DB_PORT") or "5432").strip()
sslmode = (os.environ.get("DB_OPTIONS_SSLMODE") or "").strip()

if not user:
    sys.stderr.write("ERROR: set DATABASE_URL, BACKUP_DATABASE_URL, or DB_USER/DB_PASSWORD/...\n")
    sys.exit(1)

if host == "host.docker.internal":
    host = "127.0.0.1"

query = f"sslmode={quote_plus(sslmode)}" if sslmode else ""
netloc = f"{quote_plus(user)}:{quote_plus(password)}@{host}:{port}"
uri = f"postgres://{netloc}/{quote_plus(name)}"
if query:
    uri = f"{uri}?{query}"
print(uri)
PY
}

log_database_target() {
  "$PYTHON" - <<'PY'
import os
import sys
from urllib.parse import parse_qs, urlparse

uri = os.environ["RESOLVED_URI"]
parsed = urlparse(uri)
dbname = (parsed.path or "/").lstrip("/") or "?"
host = parsed.hostname or parse_qs(parsed.query).get("host", ["?"])[0]
port = parsed.port or "default"
user = parsed.username or "?"
print(f"Database target: host={host!r} port={port!r} database={dbname!r} user={user!r}")
PY
}

require_commands() {
  local missing=()
  if [[ -z "$PYTHON" ]]; then
    missing+=("python3 or python")
  fi
  for cmd in "$PYTHON" "$PG_DUMP" "$GCLOUD"; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      missing+=("$cmd")
    fi
  done
  if ((${#missing[@]} > 0)); then
    error "Missing required commands: ${missing[*]}"
    exit 1
  fi
}

ensure_staging_dir() {
  if [[ ! -d "$BACKUP_STAGING_DIR" ]]; then
    mkdir -p "$BACKUP_STAGING_DIR"
  fi
  chmod 700 "$BACKUP_STAGING_DIR" 2>/dev/null || true
}

run_retention() {
  local delete_mode="$1"  # dry-run | list | live

  if (( BACKUP_RETENTION_DAYS == 0 )); then
    log "Retention: disabled (BACKUP_RETENTION_DAYS=0); no GCS objects will be removed"
    return 0
  fi

  local gcs_glob="gs://${BACKUP_GCS_BUCKET}/${GCS_PREFIX}${PREFIX_STEM}-*.dump"

  log "Retention: listing ${gcs_glob} (keep last ${BACKUP_RETENTION_DAYS} day(s))"
  local listing
  if ! listing="$("$GCLOUD" storage ls "$gcs_glob" 2>/dev/null || true)"; then
    error "Failed to list GCS objects at ${gcs_glob}"
    return 4
  fi
  if [[ -z "$listing" ]]; then
    log "Retention: no matching objects in bucket"
    return 0
  fi

  local to_delete
  to_delete="$(GCS_LISTING="$listing" PREFIX_STEM="$PREFIX_STEM" BACKUP_RETENTION_DAYS="$BACKUP_RETENTION_DAYS" DUMP_BASENAME="$DUMP_BASENAME" "$PYTHON" - <<'PY'
import os
import re
from datetime import datetime, timedelta, timezone

prefix_stem = os.environ["PREFIX_STEM"]
retention_days = int(os.environ["BACKUP_RETENTION_DAYS"])
today_dump = os.environ.get("DUMP_BASENAME", "")
cutoff = datetime.now(timezone.utc).date() - timedelta(days=retention_days)
pattern = re.compile(rf"^{re.escape(prefix_stem)}-(\d{{8}})\.dump$")

for line in os.environ.get("GCS_LISTING", "").splitlines():
    line = line.strip()
    if not line:
        continue
    basename = line.rsplit("/", 1)[-1]
    if basename == today_dump:
        continue
    match = pattern.match(basename)
    if not match:
        continue
    try:
        obj_date = datetime.strptime(match.group(1), "%Y%m%d").date()
    except ValueError:
        continue
    if obj_date < cutoff:
        print(line)
PY
)"

  if [[ -z "$to_delete" ]]; then
    log "Retention: no objects older than ${BACKUP_RETENTION_DAYS} day(s) to remove"
    return 0
  fi

  while IFS= read -r object_uri; do
    [[ -n "$object_uri" ]] || continue
    case "$delete_mode" in
      list|dry-run)
        log "Retention: would delete ${object_uri}"
        ;;
      live)
        log "Retention: deleting ${object_uri}"
        if ! "$GCLOUD" storage rm "$object_uri"; then
          error "Failed to delete ${object_uri}"
          return 4
        fi
        ;;
    esac
  done <<< "$to_delete"

  return 0
}

export PREFIX_STEM BACKUP_RETENTION_DAYS DUMP_BASENAME

require_commands

if [[ "$LIST_RETENTION_ONLY" == true ]]; then
  run_retention list
  exit $?
fi

RESOLVED_URI="$(resolve_database_uri)"
export RESOLVED_URI
log_database_target

ensure_staging_dir

log "Starting pg_dump → ${DUMP_FILE}"
if ! "$PG_DUMP" -Fc --no-owner --no-acl -f "$DUMP_FILE" --dbname="$RESOLVED_URI"; then
  error "pg_dump failed"
  exit 2
fi
chmod 600 "$DUMP_FILE"
dump_size="$(wc -c < "$DUMP_FILE" | tr -d ' ')"
log "Dump complete (${dump_size} bytes): ${DUMP_FILE}"

GCS_URI="gs://${BACKUP_GCS_BUCKET}/${GCS_PREFIX}${DUMP_BASENAME}"
log "Uploading to ${GCS_URI}"
if ! "$GCLOUD" storage cp "$DUMP_FILE" "$GCS_URI"; then
  error "GCS upload failed; local dump retained at ${DUMP_FILE}"
  exit 3
fi
log "Upload complete: ${GCS_URI}"

if [[ "$DRY_RUN" == true ]]; then
  run_retention dry-run || exit 4
else
  run_retention live || exit 4
fi

if [[ "${BACKUP_DELETE_LOCAL_AFTER_UPLOAD}" == "true" || "${BACKUP_DELETE_LOCAL_AFTER_UPLOAD}" == "True" || "${BACKUP_DELETE_LOCAL_AFTER_UPLOAD}" == "1" ]]; then
  rm -f "$DUMP_FILE"
  log "Removed local staging file ${DUMP_FILE}"
fi

retention_note="${BACKUP_RETENTION_DAYS} day(s)"
if [[ "$DRY_RUN" == true ]]; then
  retention_note+=" (retention dry-run)"
fi
BACKUP_SUCCESS_DETAIL="Uploaded: ${GCS_URI}
Dump size: ${dump_size} bytes
Retention: ${retention_note}"

log "Backup finished successfully"
