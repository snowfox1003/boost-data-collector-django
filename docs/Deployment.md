# Deployment

This project uses a GitHub Actions CI/CD pipeline that deploys to a remote server over SSH after the **CI** workflow succeeds on `push`, or when **Deploy** is run manually.

## Overview

```
Push to main/develop
      ↓
CI workflow ("CI": lint, Pyright, tests)
      ↓ on success (push only)
Deploy workflow (workflow_run)
      ↓
SSH into server → curl deploy.sh → bash on server
      ↓
git pull repo → make down / build / up / health
```

Manual trigger:

```
Actions → Deploy → Run workflow (branch: develop|main)
```

- **`develop`** → GitHub Environment **`staging`** (staging server secrets).
- **`main`** → GitHub Environment **`production`** (production server secrets).

Workflow definition: [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml).

### Deploy workflow behavior

| Trigger | When Deploy runs |
| ------- | ---------------- |
| **`workflow_run`** | After workflow **CI** completes with `conclusion: success` on `main` or `develop`, and the run was triggered by **`push`** (not PR-only CI). |
| **`workflow_dispatch`** | Operator chooses **`develop`** or **`main`** in the Actions UI (`inputs.ref`). |

- **Concurrency:** one deploy per branch (`deploy-${{ branch }}`); in-progress deploys are not cancelled.
- **Job timeout:** 20 minutes.
- **On the runner:** the job selects the environment from the branch, then uses [appleboy/ssh-action](https://github.com/appleboy/ssh-action) with environment secrets (`SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY`, optional `SSH_PORT`, `SSH_KEY_PASSPHRASE`).
- **Deploy script URL:** `DEPLOY_SCRIPT_URL` if set; otherwise the default raw URL for [`.github/workflows/deploy-script/deploy.sh`](../.github/workflows/deploy-script/deploy.sh) at the triggering commit (`workflow_run.head_sha`) or at the dispatched branch ref (`workflow_dispatch` input).
- **Script download:** `curl` with optional `Authorization: token` when `DEPLOY_SCRIPT_TOKEN` is set; then `bash` on the server with `REPO_URL`, `BRANCH`, and `SCRIPT_URL` passed from the workflow.

---

## GitHub Environments and Secrets

The deploy workflow uses **GitHub Environments** so that each branch uses the right server. Required secrets are **environment-scoped** (`SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY`) and optional `SSH_PORT` (defaults to `22`) and `SSH_KEY_PASSPHRASE` — set per environment (production / staging), not as PROD*\* / DEV*\* repository secrets.

### 1. Create the environments

Go to **Settings → Environments** and create two environments:

- **`production`** — used when the deploy is triggered from the `main` branch.
- **`staging`** — used when the deploy is triggered from the `develop` branch.

For **production**, it is recommended to enable **Required reviewers** to add a manual approval gate before each production deploy.

### 2. Add environment secrets

In each environment (**production** and **staging**), add the following **Environment secrets** (same names in both; different values per server):

| Secret               | Description                                                                            |
| -------------------- | -------------------------------------------------------------------------------------- |
| `SSH_HOST`           | IP address or hostname of the server                                                   |
| `SSH_USER`           | SSH username for the deploy account on the server                                      |
| `SSH_PRIVATE_KEY`    | SSH private key (full content, including header/footer)                                |
| `SSH_PORT`           | SSH port (optional, defaults to `22`)                                                  |
| `SSH_KEY_PASSPHRASE` | Passphrase for the SSH private key (optional; only if the key is passphrase-protected) |

GitHub injects the correct set based on the branch: `main` → production environment secrets, `develop` → staging environment secrets.

### 3. Optional repository secrets

These can stay as **Repository secrets** (Settings → Secrets and variables → Actions) if you use them:

| Secret                | Description                                                                                                                   |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `DEPLOY_SCRIPT_TOKEN` | Token to authenticate downloading a custom `deploy.sh`. Required only if `DEPLOY_SCRIPT_URL` is set and needs authentication. |
| `DEPLOY_SCRIPT_URL`   | Override the deploy script URL. If unset, Deploy uses this repo’s [`.github/workflows/deploy-script/deploy.sh`](../.github/workflows/deploy-script/deploy.sh) at `workflow_run.head_sha` or the `workflow_dispatch` branch ref. |

---

## Server Prerequisites

Install these once on each server before the first deploy:

```bash
sudo apt update && sudo apt install -y git make
```

Docker and Docker Compose are also required. Refer to the [official Docker docs](https://docs.docker.com/engine/install/ubuntu/) for installation.

---

## Server SSH key for GitHub

The account that runs `git pull` on the server (same as `SSH_USER` in GitHub Actions) needs a key **on the server** that GitHub accepts for `git@github.com:YOUR_GITHUB_ORG/boost-data-collector.git`. This is separate from the **`SSH_PRIVATE_KEY`** GitHub stores to log _into_ the server.

1. Install the private key under a dedicated name (example: `~/.ssh/id_ed25519_github`) and the matching `.pub` next to it. You can copy it from your workstation with `scp` (path to the key on your machine → `user@server:~/.ssh/...`).
2. `~/.ssh/config`:

```sshconfig
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519_github
    IdentitiesOnly yes
```

3. Restrict permissions: `chmod 700 ~/.ssh`, `chmod 600 ~/.ssh/id_ed25519_github ~/.ssh/config`, `chmod 644 ~/.ssh/id_ed25519_github.pub`.
4. Verify: `ssh -T git@github.com` (expect a GitHub success / username message).

---

## One-Time Server Setup

### 1. Create the `.env` file (two-step process)

The deploy script does **not** manage secrets. It also requires an empty or non-existent deploy directory for the first clone: `git clone` in [deploy.sh](../.github/workflows/deploy-script/deploy.sh) fails if the target directory already exists and is not a git repo. So create `.env` **after** the first clone, not before.

**Step 1 — Trigger the first deploy**

Push to `main` or `develop` (or re-run the Deploy workflow). The script will clone the repo into `/opt/boost-data-collector` and then exit with an error because `.env` is missing.

**Step 2 — Add `.env` on the server**

SSH into the server as the same user GitHub Actions uses (the account named in `SSH_USER`) and create the file inside the cloned directory:

```bash
cd /opt/boost-data-collector
cp .env.example .env
# edit .env
```

The collector schedule ships in the repo as `config/boost_collector_schedule.yaml`. Adjust it via pull request if you need different times or groups; see [Workflow.md](Workflow.md).

Use `.env.example` as a reference for required environment variables.

If you create or edit `.env` with `sudo` (e.g. `sudo nano`), the file is often owned by **root** with mode `600`. **Docker Compose reads `.env` as the user running `make build` / `make up`** (your deploy user), which causes `permission denied`. Fix ownership after saving:

```bash
sudo chown YOUR_DEPLOY_USER:YOUR_DEPLOY_USER /opt/boost-data-collector/.env
sudo chmod 600 /opt/boost-data-collector/.env
```

(Replace `YOUR_DEPLOY_USER` with the same Unix account as `SSH_USER`.)

**Step 3 — Run deploy again**

Re-run the Deploy workflow (or push again). The script will see the existing repo and `.env`, and complete successfully.

### 2. Add the deploy SSH key

On your local machine, generate a dedicated deploy key:

```bash
ssh-keygen -t ed25519 -C "deploy" -f ~/.ssh/deploy_key -N ""
```

Copy the public key to the server:

```bash
ssh-copy-id -i ~/.ssh/deploy_key.pub user@your-server
```

Add the private key content (`~/.ssh/deploy_key`) as the **`SSH_PRIVATE_KEY`** secret in the **production** or **staging** environment, depending on which server you use.

---

## Remote server layout: Docker Compose + host PostgreSQL + nginx

This matches a common production/staging layout for this repo:

- **On the host:** PostgreSQL (package install), **nginx** (TLS + reverse proxy).
- **In Docker Compose:** `web` (Gunicorn), `celery_worker`, `celery_beat`, `redis`. The bundled **`db` service is commented out** in `docker-compose.yml`; the app uses **`DATABASE_URL`** to reach PostgreSQL on the host.

Compose already sets `extra_hosts: host.docker.internal:host-gateway` on app containers so `DATABASE_URL` can use host `host.docker.internal` (see `.env.example`). **`DATABASE_URL` is required** in `.env` for `docker compose` (there is no default to a bundled `db` service while that service stays commented out).

### Google Cloud Storage (optional seed and backups)

Use a private bucket name you control (placeholder: `your-backup-bucket`).

- Prefer **`gcloud storage`** over legacy `gsutil` for copies; it is typically much faster on large objects.
- **Automated database backups** run on the VM via [`scripts/backup_database.sh`](../scripts/backup_database.sh) (see [Automated database backups](#automated-database-backups) below).
- Workspace and one-off seed artifacts can still be copied manually.

Example: copy from bucket to the VM, then unpack (paths are illustrative):

```bash
gcloud storage cp "gs://your-backup-bucket/workspace-2026-03-24.zip" .
gcloud storage cp "gs://your-backup-bucket/boost-data-collector/staging/bdc-20260325.dump" .
unzip workspace-2026-03-24.zip -d /path/to/workspace-parent
```

Sync workspace back to the bucket (first full sync can take a long time; later syncs are incremental):

```bash
gcloud storage rsync /opt/boost-data-collector/workspace gs://your-backup-bucket/workspace --recursive
```

#### Automated database backups

Daily `pg_dump` uploads to GCS are handled by [`scripts/backup_database.sh`](../scripts/backup_database.sh). The script:

1. Reads database credentials from `/opt/boost-data-collector/.env` (or `--env-file`).
2. Writes a custom-format dump (`pg_dump -Fc`) named `bdc-YYYYMMDD.dump` under a local staging directory.
3. Uploads to `gs://BUCKET/boost-data-collector/staging/bdc-YYYYMMDD.dump` when using the example `.env` below (prefix configurable via `BACKUP_GCS_PREFIX`; default `bdc/` → `gs://BUCKET/bdc/bdc-YYYYMMDD.dump`).
4. Deletes GCS objects older than **7 days** (configurable).
5. Exits non-zero with `ERROR:` logs on failure (suitable for cron alerts).

**Host prerequisites (one-time)**

```bash
sudo apt install -y postgresql-client   # pg_dump / pg_restore
# gcloud CLI — install if not already present: https://cloud.google.com/sdk/docs/install
sudo mkdir -p /var/backups/boost-data-collector
sudo chown YOUR_DEPLOY_USER:YOUR_DEPLOY_USER /var/backups/boost-data-collector
chmod 700 /var/backups/boost-data-collector
```

Ensure `pg_hba.conf` allows the backup database user from `127.0.0.1` when the app uses `host.docker.internal` in `DATABASE_URL` (see [Alternative: restore as `bdc` over TCP](#alternative-restore-as-bdc-over-tcp-127001)).

**GCS bucket**

- Create a **private** bucket (uniform bucket-level access, no public access).
- Replace `your-backup-bucket` with your real bucket name in `.env` and examples below.
- Optional: add a GCS lifecycle rule to delete objects under `bdc/` after 8 days (the script enforces 7-day retention).

**IAM for the deploy user**

Grant the VM deploy user (`SSH_USER`, same account as GitHub Actions deploy) permission to create, list, read, and delete objects in the bucket:

| Permission | Purpose |
| ---------- | ------- |
| `storage.objects.create` | Upload dumps |
| `storage.objects.get` | Verify uploads |
| `storage.objects.list` | Retention listing |
| `storage.objects.delete` | Prune old dumps |

Convenient role: **Storage Object Admin** (`roles/storage.objectAdmin`) on the bucket.

The deploy user must already be able to run `gcloud storage` (Application Default Credentials or `gcloud auth login` on the VM).

**Environment variables**

Add to `/opt/boost-data-collector/.env` (see commented examples in [`.env.example`](../.env.example)):

| Variable | Required | Default | Notes |
| -------- | -------- | ------- | ----- |
| `DATABASE_URL` or `DB_*` | yes | — | Same as Django; script rewrites `host.docker.internal` → `127.0.0.1` |
| `BACKUP_GCS_BUCKET` | yes | — | Private GCS bucket name |
| `BACKUP_FILE_PREFIX` | no | `bdc` | Dump basename stem → `bdc-YYYYMMDD.dump` (path segments stripped) |
| `BACKUP_GCS_PREFIX` | no | `bdc/` | GCS object prefix; trailing `/` added if missing |
| `BACKUP_STAGING_DIR` | no | `/var/backups/boost-data-collector` | Local dump directory |
| `BACKUP_RETENTION_DAYS` | no | `7` | GCS objects to keep; `0` disables pruning |
| `BACKUP_DELETE_LOCAL_AFTER_UPLOAD` | no | `true` | Remove local dump after success |
| `DISCORD_WEBHOOK_URL` / `SLACK_WEBHOOK_URL` | no | — | Optional success/failure webhook (same vars as deploy notify) |
| `BACKUP_NOTIFICATIONS` | no | `true` | Set `false` to skip backup webhook posts |
| `BACKUP_DATABASE_URL` | no | — | Optional override (e.g. explicit `127.0.0.1` URL) |

Example `.env` fragment:

```bash
BACKUP_GCS_BUCKET=your-backup-bucket
BACKUP_FILE_PREFIX=bdc
BACKUP_GCS_PREFIX=boost-data-collector/staging/
# Optional if DATABASE_URL uses host.docker.internal for Docker only:
# BACKUP_DATABASE_URL=postgres://bdc:REPLACE_WITH_STRONG_PASSWORD@127.0.0.1:5432/boost_dashboard
```

Restore, smoke-test, and retention examples below use this prefix (`boost-data-collector/staging/`). If you omit `BACKUP_GCS_PREFIX`, substitute `bdc/` in those paths.

**Cron job**

Run as the **deploy user** (not root), daily at an off-peak time on the **VM host**. This is separate from collector scheduling: daily collector runs are driven by **Celery Beat** inside the Docker stack (`celery_beat` service), which reads [`config/boost_collector_schedule.yaml`](../config/boost_collector_schedule.yaml) at Django startup (see [Workflow.md](Workflow.md)). Beat times are **UTC** (`default_time` per group).

A common choice is **23:00 UTC** — after the afternoon Celery Beat batch (last group `reddit` at 17:00 UTC) and before the midnight batch (`github` at 00:05 UTC). Adjust the hour if you edit the YAML or add interval tasks. Cron uses the **system timezone** unless you set `TZ=UTC` in the cron file (see example below).

Create a log directory owned by the deploy user (once per server; replace `YOUR_DEPLOY_USER`):

```bash
mkdir -p /home/YOUR_DEPLOY_USER/log
chmod 700 /home/YOUR_DEPLOY_USER/log
```

```cron
# /etc/cron.d/bdc-db-backup (or deploy user's crontab -e)
TZ=UTC
0 23 * * * YOUR_DEPLOY_USER /opt/boost-data-collector/scripts/backup_database.sh >> /home/YOUR_DEPLOY_USER/log/bdc-db-backup.log 2>&1
```

If you use the deploy user's crontab (`crontab -e`) instead of `/etc/cron.d/`, omit the username column and you may use `~/log/bdc-db-backup.log` for the log path.

The script loads `$DEPLOY_DIR/.env` automatically (`DEPLOY_DIR` defaults to `/opt/boost-data-collector`).

Optional **systemd timer** alternative:

```ini
# /etc/systemd/system/bdc-db-backup.service
[Unit]
Description=Boost Data Collector PostgreSQL backup to GCS

[Service]
Type=oneshot
User=YOUR_DEPLOY_USER
WorkingDirectory=/opt/boost-data-collector
ExecStart=/opt/boost-data-collector/scripts/backup_database.sh
StandardOutput=append:/home/YOUR_DEPLOY_USER/log/bdc-db-backup.log
StandardError=append:/home/YOUR_DEPLOY_USER/log/bdc-db-backup.log

# /etc/systemd/system/bdc-db-backup.timer
[Unit]
Description=Daily PostgreSQL backup to GCS

[Timer]
OnCalendar=*-*-* 23:00:00 UTC
Persistent=true

[Install]
WantedBy=timers.target
```

Enable with `sudo systemctl enable --now bdc-db-backup.timer`.

**Restore from an automated backup**

1. Download the dump (custom format — use `pg_restore`, not `psql -f`):

   ```bash
   gcloud storage cp "gs://your-backup-bucket/boost-data-collector/staging/bdc-20260618.dump" ~/
   chmod 600 ~/bdc-20260618.dump
   ```

2. Restore using the steps in [Restoring from `pg_dump` (custom format)](#restoring-from-pg_dump-custom-format) below (socket superuser or TCP as `bdc`).

3. If you restored as `postgres`, re-run the post-restore `GRANT` block for `bdc`.

**Smoke test checklist**

On staging or production after deploy pulls the script:

1. `scripts/backup_database.sh --help` — confirm usage text.
2. Manual run: `/opt/boost-data-collector/scripts/backup_database.sh` — exit 0; log shows dump size and `gs://…/boost-data-collector/staging/bdc-YYYYMMDD.dump`.
3. `gcloud storage ls "gs://your-backup-bucket/boost-data-collector/staging/bdc-*.dump"` — today's object is present.
4. `scripts/backup_database.sh --list-retention` — lists only objects older than 7 days (none on first run).
5. Optional retention test: upload `gs://your-backup-bucket/boost-data-collector/staging/bdc-20190101.dump`, re-run the script, confirm the old object is removed.
6. Failure test: temporarily set invalid `BACKUP_GCS_BUCKET`; confirm non-zero exit and `ERROR:` on stderr.

Script flags: `--dry-run` (dump + upload, retention deletes logged only), `--list-retention` (retention preview only), `--env-file PATH`.

### Repository checkout and permissions

The deploy user (the same Unix account as `SSH_USER`) should own the app tree under `/opt/boost-data-collector` so `git`, `make`, and Docker Compose can run without sudo.

If you are **not** relying on the first CI deploy to create the directory, prepare the tree manually (after [Server SSH key for GitHub](#server-ssh-key-for-github) is working), for example:

```bash
sudo mkdir -p /opt/boost-data-collector
sudo chown -R "$USER:$USER" /opt/boost-data-collector
cd /opt/boost-data-collector
git clone -b develop git@github.com:YOUR_GITHUB_ORG/boost-data-collector.git .
```

(`develop` matches the staging branch described above; use `main` for a production-only checkout if you prefer.)

If the tree was created as root, normalize ownership:

```bash
sudo chown -R YOUR_DEPLOY_USER:YOUR_DEPLOY_USER /opt/boost-data-collector
```

Docker bind mounts for `staticfiles` (and optionally a host `workspace` directory if you use one) must be readable/writable by the **UID used inside the image** for the app process (commonly `1000`). Example:

```bash
mkdir -p /opt/boost-data-collector/staticfiles
sudo chown -R 1000:1000 /opt/boost-data-collector/staticfiles
# If using a host workspace directory mounted into the container:
sudo chown -R 1000:1000 /opt/boost-data-collector/workspace
sudo chmod -R u+rwX /opt/boost-data-collector/workspace
```

### PostgreSQL on the host (role `bdc`, database `boost_dashboard`)

Install PostgreSQL on the server (version should be compatible with your dumps and Django; this project is tested with recent PostgreSQL releases).

Create the application role and database **once** (use a strong password; the example below uses a placeholder):

```bash
sudo -u postgres psql
```

In the `psql` session (as superuser, e.g. `postgres`):

```sql
CREATE ROLE bdc WITH LOGIN PASSWORD 'REPLACE_WITH_STRONG_PASSWORD';
-- equivalent: CREATE USER bdc WITH PASSWORD 'REPLACE_WITH_STRONG_PASSWORD';
DROP DATABASE IF EXISTS boost_dashboard;
CREATE DATABASE boost_dashboard OWNER bdc;
GRANT ALL PRIVILEGES ON DATABASE boost_dashboard TO bdc;
GRANT CREATE, USAGE ON SCHEMA public TO bdc;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO bdc;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO bdc;
CREATE ROLE app_readonly NOLOGIN;
```

The app role does not need `CREATEDB`; the database is created explicitly above. If you need a separate migration-only user with broader rights, create that role separately.

If your dump replays `GRANT … TO app_readonly`, the `app_readonly` role must exist before restore (as above).

### `pg_hba.conf`: Docker containers → host PostgreSQL

With `host.docker.internal` in `DATABASE_URL` (see `docker-compose.yml` `extra_hosts`), Postgres still sees the client as the **container’s bridge IP** (e.g. `172.20.0.4`), not `127.0.0.1`, so `host … 127.0.0.1/32` rules do not match that traffic. `pg_hba.conf` lines match **database**, **user**, and **client address**; without a matching line you may see:

```text
FATAL:  no pg_hba.conf entry for host "172.20.0.4", user "bdc", database "boost_dashboard", ...
```

Add something like (adjust user/database names and auth to match your install; `scram-sha-256` is typical):

```conf
host  boost_dashboard  bdc  172.16.0.0/12  scram-sha-256
```

**`172.16.0.0/12`** covers `172.16.0.0`–`172.31.255.255`, which includes common Docker bridge subnets. To narrow to one subnet (e.g. only `172.20.*`), use **`172.20.0.0/16`** instead.

Reload Postgres after editing:

```bash
sudo systemctl reload postgresql
```

If the client negotiates SSL but the server does not use TLS for this path, add **`?sslmode=disable`** or **`prefer`** to **`DATABASE_URL`** (see `.env.example`).

### Restoring from `pg_dump` (custom format)

Backups produced with `pg_dump -Fc` are **not** plain SQL. Restore with **`pg_restore`**, not `psql -f`. The file may still be named `*.sql` even though it is custom format—use `pg_restore`, not the extension, to decide the tool.

**Where to put the dump file**

- Whoever runs **`pg_restore`** must be able to read the dump: the **`postgres`** OS user when using `sudo -u postgres …`, or the account you use when restoring as **`bdc`** over **`127.0.0.1`** below. **Do not** make backups world-readable (e.g. **`644`** on a shared host): other local users could read sensitive data. Use least privilege instead: **`chmod 600`** (or tighter) and **`chown`** the file to match the restoring account (`postgres` vs your login). Prefer a **private directory** (your `$HOME`, a root-only path such as `/root/…`, or **`/var/lib/postgresql/…`** when only `postgres` should read it) over **`/tmp/`** unless you keep **`600`** and tight ownership there too.
- To avoid **`postgres`** needing filesystem access to the path, you can stream from an account that already owns a **`600`** dump: **`cat /path/to/dump | sudo -u postgres pg_restore -h /var/run/postgresql -p 5432 -U postgres --verbose --clean --if-exists -d boost_dashboard -`**. Use the same idea without **`sudo`** when you run **`pg_restore`** as **`bdc`**.

**Prefer Unix socket for superuser restore**

`sudo -u postgres pg_restore -h localhost …` often fails because **TCP** to `localhost` uses `pg_hba.conf` **password** rules, not **peer** auth. Connect via the **socket** instead (omit `-h` or use `-h /var/run/postgresql`):

```bash
sudo -u postgres pg_restore -h /var/run/postgresql -p 5432 -U postgres \
  --verbose --clean --if-exists \
  -d boost_dashboard \
  /var/lib/postgresql/boost-data-collector-db-2026-03-25.dump
```

**Alternative: restore as `bdc` over TCP (`127.0.0.1`)**

If `pg_hba.conf` allows `bdc` from **`127.0.0.1/32`** (password / `scram-sha-256`), you can run `pg_restore` as a normal user instead of `sudo -u postgres`:

```bash
pg_restore -h 127.0.0.1 -U bdc -d boost_dashboard --verbose ~/bdc-20260514.dump
```

Adjust the dump path as needed; set ownership and **`chmod 600`** on the file to match whoever runs **`pg_restore`**. You are prompted for `bdc`'s password unless you use **`PGPASSWORD`** or **`~/.pgpass`**. Add **`--clean --if-exists`** if you want the restore to drop existing objects first (match your dump and risk tolerance).

**After restore — privileges for the app user:** If you restored **as `postgres`** (or another superuser), **`public` tables may remain owned by `postgres`**; DB owner `bdc` still has **no table rights** until you `GRANT` (empty `role_table_grants` for `bdc` is expected). Grants to other roles in the dump (e.g. `app_readonly`) do not apply to `bdc`. If you restored **as `bdc`** and objects are already owned by `bdc`, you may not need the grants—verify if the app reports permission errors.

1. As superuser: `\c boost_dashboard`, then run (adjust role name if not `bdc`):

```sql
GRANT USAGE ON SCHEMA public TO bdc;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO bdc;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO bdc;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO bdc;
```

2. **Check:** `pg_tables` / `information_schema` are **per database**—always `\c boost_dashboard` before querying. After grants, `SELECT COUNT(*) FROM information_schema.role_table_grants WHERE grantee = 'bdc' AND table_schema = 'public'` should be large (on the order of hundreds for a full app schema).

Repeat step 1 after any future restore that leaves table ownership on `postgres`.

### `.env` for host PostgreSQL

Set **`DATABASE_URL`** (and any `DB_*` overrides) so containers reach the host database, for example:

```bash
DATABASE_URL=postgres://bdc:REPLACE_WITH_STRONG_PASSWORD@host.docker.internal:5432/boost_dashboard
```

Also set production-safe values for:

- **`ALLOWED_HOSTS`** — your public hostname(s).
- **`CSRF_TRUSTED_ORIGINS`** — `https://your.hostname` entries for HTTPS sites.
- **`USE_X_FORWARDED_HOST=True`** and **`USE_TLS_PROXY_HEADERS=True`** when Django sits behind nginx terminating TLS (see comments in `config/settings.py`).
- **`STATIC_URL`** / **`FORCE_SCRIPT_NAME`** — only if you serve the app under a URL prefix; see the optional nginx subsection below.

### Docker stack

From `/opt/boost-data-collector` as the deploy user:

```bash
make build   # first build is slower; later builds are incremental
make up
make health  # optional smoke checks (see Makefile)
```

CI uses the same targets in a fixed order (`make down` first); see [Deploy Script Behavior](#deploy-script-behavior).

### nginx reverse proxy

`docker-compose.yml` publishes Gunicorn on **`127.0.0.1:8000`** only. Terminate TLS on the host with nginx and proxy to that port.

#### At site root (`/`)

The following example assumes the app is served at the **domain root** (`https://app.example.com/`) and static files at **`/static/`**.

```nginx
upstream boost_collector_app {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    listen 443 ssl http2;
    server_name app.example.com;

    ssl_certificate     /etc/letsencrypt/live/app.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.example.com/privkey.pem;

    client_max_body_size 100M;

    location / {
        proxy_pass         http://boost_collector_app;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_redirect     off;
        proxy_read_timeout 300s;
    }

    location /static/ {
        alias /opt/boost-data-collector/staticfiles/;
    }
}
```

#### Optional: URL prefix (subpath)

If the app must live under a prefix (e.g. `https://app.example.com/boost-data-collector/`), set in `.env`:

- `FORCE_SCRIPT_NAME=/boost-data-collector` (no trailing slash)
- `STATIC_URL=/boost-data-collector/static/` (must end with `/`)

Example nginx (adjust the prefix string to match your `FORCE_SCRIPT_NAME`):

```nginx
upstream boost_collector_app {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    listen 443 ssl http2;
    server_name app.example.com;

    ssl_certificate     /etc/letsencrypt/live/app.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.example.com/privkey.pem;

    client_max_body_size 100M;

    location /boost-data-collector/static/ {
        alias /opt/boost-data-collector/staticfiles/;
    }

    location /boost-data-collector/ {
        proxy_pass         http://boost_collector_app/;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_redirect     off;
        proxy_read_timeout 300s;
    }
}
```

Reload nginx after testing config (`sudo nginx -t && sudo systemctl reload nginx`).

---

## Deploy Script Behavior

The deploy script ([`.github/workflows/deploy-script/deploy.sh`](../.github/workflows/deploy-script/deploy.sh), or the URL from `DEPLOY_SCRIPT_URL`) runs on the remote server after the SSH step downloads it (see [Deploy workflow behavior](#deploy-workflow-behavior)). It does the following:

1. Validates `REPO_URL` and `BRANCH` are set.
2. Checks that `git` and `make` are installed.
3. If the repo already exists — fetches and hard-resets to `origin/<branch>`.
4. If the repo does not exist — clones it fresh.
5. Checks for `.env` in the deploy directory (`$DEPLOY_DIR/.env`). If it is missing, the script exits with an error. Create `.env` after the first clone using the [two-step process](#1-create-the-env-file-two-step-process).
6. Stops existing containers (`make down`).
7. Builds and starts the stack (`make build && make up`).
8. Waits for `make health` to succeed (see `Makefile`).

### Overriding the deploy directory

By default the repo is cloned into `/opt/boost-data-collector`. To use a different path, set `DEPLOY_DIR` as an environment variable on the server. The [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) SSH step does not pass `DEPLOY_DIR`; configure it on the host if needed.

---

## Updating `.env` on the Server

When secrets or config values change, SSH into the server and edit the file directly:

```bash
nano /opt/boost-data-collector/.env
```

If you saved with `sudo`, fix ownership and mode for the deploy user as in [Step 2 — Add `.env` on the server](#1-create-the-env-file-two-step-process).

Then restart the containers to pick up the new values:

```bash
cd /opt/boost-data-collector && make down && make up
```

---

## Production Compose overlay

For VM production, use the prod overlay (resource limits, `LOG_FORMAT=json`):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

See [GCP_Production_Checklist.md](./GCP_Production_Checklist.md) for Cloud SQL, secrets, and handoff notes.

## Health checks (`make health`)

`make health` calls **`GET /health/`** inside the `web` container (database, Celery workers, collector group freshness), then checks Redis and that Celery containers are running.

- **Readiness JSON:** `curl http://127.0.0.1:8000/health/` (or via nginx). If `HEALTH_CHECK_TOKEN` is set in `.env`, `make health` sends `Authorization: Bearer …` using the value from the `web` container environment.
- **Production:** keep `HEALTH_ENFORCE_COLLECTOR_FRESHNESS=true` so stale daily groups return HTTP 503.
- **CI / first boot:** can set `HEALTH_ENFORCE_COLLECTOR_FRESHNESS=false` until collectors have run once.

For more detail see [Docker.md](./Docker.md), [GCP_Production_Checklist.md](./GCP_Production_Checklist.md), and the `health` target in the `Makefile`.
