# GCP / production deployment checklist

Handoff for VM Docker Compose production and future Cloud Run work (@snowfox1003).

## Runtime

- **Python:** 3.13 (`python:3.13-slim` image; CI uses 3.13).
- **Pinecone SDK:** 6.x (`pinecone>=6.0,<7` in `requirements.lock`).
- **Start prod stack:**
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
  docker compose exec -T web python manage.py migrate --noinput
  curl -fsS http://127.0.0.1:8000/health/
  ```

## Database (Cloud SQL)

- Set `DATABASE_URL` in server `.env` (chmod 600), not in the image.
- Examples: Auth Proxy → `127.0.0.1`, public IP with `?sslmode=require`, or Unix socket `host=/cloudsql/PROJECT:REGION:INSTANCE`.
- Prod compose does **not** start a `db` service; Postgres is external.

## Secrets (six platforms)

Mirror [`.env.example`](../.env.example) groups; inject via Secret Manager → env on the host:

| Platform | Key env vars |
|----------|----------------|
| GitHub | `GITHUB_TOKEN`, `GITHUB_TOKENS_SCRAPING`, `GITHUB_TOKEN_WRITE` |
| Slack | `SLACK_TEAM_IDS`, `SLACK_BOT_TOKEN_*`, `SLACK_APP_TOKEN_*` |
| Discord | `DISCORD_TOKEN`, `DISCORD_SERVER_ID`, exporter paths |
| Pinecone | `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`, … |
| YouTube | `YOUTUBE_API_KEY` |
| WG21 | `WG21_GITHUB_DISPATCH_*` (see `config/settings.py`) |

## Health and monitoring

- **Readiness:** `GET /health/` — database, Celery worker `ping`, collector group staleness (daily groups in YAML).
- **Production:** set `HEALTH_ENFORCE_COLLECTOR_FRESHNESS=true` (default). After first deploy, run collectors or expect **503** until groups succeed.
- **Logs:** `LOG_FORMAT=json` on prod compose (stdout → GCP logging agent).
- Optional: `HEALTH_CHECK_TOKEN` + `Authorization: Bearer …` for external probes.

## Collectors in Beat schedule

Configured in [`config/boost_collector_schedule.yaml`](../config/boost_collector_schedule.yaml): `github`, `boost_library_docs`, `slack`, `mailing_list`, `reddit`.

**Not** on Beat yet (manual / future): WG21, YouTube, Clang — `/health/` shows `last_success_at: null` until scheduled or `record_group_success` is updated.

## Services layout

| Service | Prod notes |
|---------|------------|
| `web` | Gunicorn `gthread`; resource limits in `docker-compose.prod.yml` |
| `celery_worker` | `--max-tasks-per-child` (default 50) |
| `celery_beat` | Persistent `celerybeat` volume |

## Ingress

- Expose `/health/` to load balancer; restrict `/admin/`.
- Same image for web/worker/beat; worker/beat disable Docker `HEALTHCHECK` (no HTTP on :8000).
