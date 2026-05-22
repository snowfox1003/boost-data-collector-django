# Boost Data Collector - Docker image
# Same image runs: web (gunicorn), celery worker, celery beat

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

# System deps: PostgreSQL client, git, curl (HEALTHCHECK), gosu (dev entrypoint only).
# Pinned to Debian 13 (trixie) versions from python:3.13-slim at pin time; refresh with:
#   docker run --rm python:3.13-slim bash -c 'apt-get update -qq && for p in libpq5 git curl gosu; do echo -n "$p="; apt-cache policy "$p" | awk "/Candidate:/{print \$2; exit}"; done'
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5=17.10-0+deb13u1 \
    git=1:2.47.3-0+deb13u1 \
    curl=8.14.1-2+deb13u3 \
    gosu=1.17-3+b4 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY . .

RUN mkdir -p logs staticfiles workspace celerybeat

COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid 10001 --create-home appuser \
    && chown -R appuser:appuser /app
RUN git config --system --add safe.directory '/app/workspace/*'

USER appuser

EXPOSE 8000

# When HEALTH_CHECK_TOKEN is set (runtime env from compose/.env), send Bearer auth.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD sh -c 'if [ -n "${HEALTH_CHECK_TOKEN:-}" ]; then \
    curl -fsS -H "Authorization: Bearer ${HEALTH_CHECK_TOKEN}" http://127.0.0.1:8000/health/; \
  else \
    curl -fsS http://127.0.0.1:8000/health/; \
  fi'

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "-c", "docker/gunicorn.conf.py", "config.wsgi:application"]
