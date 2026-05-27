#!/usr/bin/env bash
# Wait until slack-chromium has written a usable Chrome profile (Cookies + LevelDB).
set -euo pipefail

PROFILE_ROOT="${1:-workspace/slack_event_handler/chrome_profile}"
COOKIES="${PROFILE_ROOT}/Default/Cookies"
LEVELDB="${PROFILE_ROOT}/Default/Local Storage/leveldb"
TIMEOUT_SEC="${SLACK_PROFILE_WAIT_TIMEOUT:-600}"
INTERVAL_SEC="${SLACK_PROFILE_WAIT_INTERVAL:-5}"

if ! [[ "${TIMEOUT_SEC}" =~ ^[0-9]+$ ]] || ! [[ "${INTERVAL_SEC}" =~ ^[0-9]+$ ]]; then
  echo "SLACK_PROFILE_WAIT_TIMEOUT and SLACK_PROFILE_WAIT_INTERVAL must be non-negative integers." >&2
  exit 1
fi
if (( TIMEOUT_SEC <= 0 || INTERVAL_SEC <= 0 )); then
  echo "SLACK_PROFILE_WAIT_TIMEOUT and SLACK_PROFILE_WAIT_INTERVAL must be > 0." >&2
  exit 1
fi

deadline=$((SECONDS + TIMEOUT_SEC))
echo "Waiting for Slack Chrome profile under ${PROFILE_ROOT}"
echo "  Sign in at http://127.0.0.1:7900 → https://app.slack.com"
echo "  Timeout: ${TIMEOUT_SEC}s (override with SLACK_PROFILE_WAIT_TIMEOUT)"

while (( SECONDS < deadline )); do
  if [[ -f "${COOKIES}" && -s "${COOKIES}" && -d "${LEVELDB}" ]]; then
    if compgen -G "${LEVELDB}/*" > /dev/null; then
      echo "Profile ready (${COOKIES}, ${LEVELDB})."
      exit 0
    fi
  fi
  sleep "${INTERVAL_SEC}"
done

echo "Timed out waiting for Chrome profile. Check noVNC login and slack-chromium logs." >&2
exit 1
