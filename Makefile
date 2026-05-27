# =============================================================================
# Boost Data Collector – Developer Makefile
# Wraps docker compose + common Django management commands.
#
# Usage:  make <target>
#         make help     → list all targets
# =============================================================================

SHELL := /bin/bash
COMPOSE   := docker compose
APP       := web
BEAT      := celery_beat
MANAGE    := $(COMPOSE) run --rm $(APP) python manage.py

.DEFAULT_GOAL := help

# ── Help ─────────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@echo "  Stack"
	@echo "    build          Build (or rebuild) all images"
	@echo "    up             Clean macOS files, then start all services (detached)"
	@echo "    down           Stop and remove containers (volumes kept)"
	@echo "    stop           Pause all containers (fast restart)"
	@echo "    start          Resume paused containers"
	@echo "    restart        Stop then start all containers"
	@echo "    reset          !! Remove containers AND volumes (wipes DB + data)"
	@echo ""
	@echo "  Logs & status"
	@echo "    ps             Show running containers"
	@echo "    health         Verify DB, Redis, Celery Beat schedule, and containers"
	@echo "    notify         Send Slack/Discord startup notification (celery_beat; optional DEPLOY_BRANCH)"
	@echo "    logs           Follow logs for all services"
	@echo "    logs-web       Follow logs for the web service"
	@echo "    logs-worker    Follow logs for the Celery worker"
	@echo "    logs-beat      Follow logs for the Celery beat"
	@echo ""
	@echo "  Django"
	@echo "    migrate        Apply database migrations"
	@echo "    makemigrations Create new migration files"
	@echo "    superuser      Create a Django superuser"
	@echo "    shell          Open Django shell inside the web container"
	@echo "    bash           Open a bash shell inside the web container"
	@echo "    collectstatic  Collect static files"
	@echo ""
	@echo "  Testing (runs locally, not inside Docker)"
	@echo "    test           Run full pytest suite"
	@echo "    test-fast      Run tests, stop on first failure"
	@echo "    test-cov       Run tests with coverage report"
	@echo ""
	@echo "  Slack session (xoxc/xoxd token extraction)"
	@echo "    slack-login            Start slack-chromium (noVNC http://127.0.0.1:7900)"
	@echo "    slack-wait-profile     Wait until Slack login wrote Cookies + LevelDB"
	@echo "    slack-login-stop       Stop slack-chromium before extract"
	@echo "    extract-slack-tokens   Extract tokens to workspace JSON (one-shot)"
	@echo "    slack-tokens-reextract Stop chromium → extract JSON"
	@echo "    slack-tokens-refresh   Login (noVNC) → wait → extract JSON"
	@echo ""
	@echo "  Utilities"
	@echo "    clean-mac      Remove macOS ._* resource-fork files"
	@echo "    clean-pyc      Remove compiled Python files"
	@echo "    clean          Run clean-mac + clean-pyc"
	@echo ""

# ── Stack ─────────────────────────────────────────────────────────────────────

.PHONY: build
build: clean-mac
	$(COMPOSE) build

.PHONY: up
up: clean-mac
	$(COMPOSE) up -d

.PHONY: down
down:
	$(COMPOSE) down

.PHONY: stop
stop:
	$(COMPOSE) stop

.PHONY: start
start:
	$(COMPOSE) start

.PHONY: restart
restart: stop start

.PHONY: reset
reset:
	@echo "WARNING: This will delete all containers AND volumes (database, workspace, logs)."
	@read -r -p "Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ] || (echo "Aborted."; exit 1)
	$(COMPOSE) down -v

# ── Logs & status ─────────────────────────────────────────────────────────────

.PHONY: ps
ps:
	$(COMPOSE) ps

.PHONY: health
# HEALTH_CHECK_TOKEN comes from the web container env (env_file: .env). When set, /health/ requires Bearer auth.
health:
	$(COMPOSE) exec -T $(APP) sh -c '\
	  if [ -n "$${HEALTH_CHECK_TOKEN:-}" ]; then \
	    curl -fsS -H "Authorization: Bearer $${HEALTH_CHECK_TOKEN}" http://127.0.0.1:8000/health/; \
	  else \
	    curl -fsS http://127.0.0.1:8000/health/; \
	  fi | python -c "import sys,json; d=json.load(sys.stdin); print(d.get(\"status\")); sys.exit(0 if d.get(\"status\")==\"healthy\" else 1)"'
	$(COMPOSE) exec -T redis redis-cli ping | grep -q PONG
	$(COMPOSE) ps --status running celery_worker | grep -q celery_worker
	$(COMPOSE) ps --status running celery_beat | grep -q celery_beat

.PHONY: notify
notify:
	$(COMPOSE) exec -T -e DEPLOY_BRANCH="$(DEPLOY_BRANCH)" $(BEAT) python manage.py send_startup_notification

.PHONY: logs
logs:
	$(COMPOSE) logs -f

.PHONY: logs-web
logs-web:
	$(COMPOSE) logs -f web

.PHONY: logs-worker
logs-worker:
	$(COMPOSE) logs -f celery_worker

.PHONY: logs-beat
logs-beat:
	$(COMPOSE) logs -f celery_beat

# ── Django ────────────────────────────────────────────────────────────────────

.PHONY: migrate
migrate:
	$(MANAGE) migrate

.PHONY: makemigrations
makemigrations:
	$(MANAGE) makemigrations

.PHONY: superuser
superuser:
	$(MANAGE) createsuperuser

.PHONY: shell
shell:
	$(MANAGE) shell

.PHONY: bash
bash:
	$(COMPOSE) exec $(APP) bash

.PHONY: collectstatic
collectstatic:
	$(MANAGE) collectstatic --noinput

# ── Testing (runs locally, not inside the production image) ───────────────────

.PHONY: test
test:
	python -m pytest

.PHONY: test-fast
test-fast:
	python -m pytest -x --tb=short

.PHONY: test-cov
test-cov:
	python -m pytest --tb=short --cov=. --cov-report=term-missing

# ── Slack session ─────────────────────────────────────────────────────────────

.PHONY: slack-login slack-wait-profile slack-login-stop extract-slack-tokens \
	slack-tokens-reextract slack-tokens-refresh

slack-login:
	@mkdir -p workspace/slack_event_handler/chrome_profile
	$(COMPOSE) --profile slack-session up -d --force-recreate slack-chromium
	@echo "Open http://127.0.0.1:7900 and sign in at https://app.slack.com (wait until Slack is fully loaded)"
	@command -v open >/dev/null 2>&1 && open "http://127.0.0.1:7900" || true

slack-wait-profile:
	@chmod +x scripts/wait_slack_chrome_profile.sh
	@./scripts/wait_slack_chrome_profile.sh

slack-login-stop:
	$(COMPOSE) --profile slack-session stop slack-chromium

extract-slack-tokens: slack-login-stop
	$(MANAGE) extract_slack_tokens

# Profile already exists (re-extract without opening noVNC again).
slack-tokens-reextract: extract-slack-tokens

# Login in noVNC, wait for profile files, then extract JSON.
slack-tokens-refresh: slack-login slack-wait-profile extract-slack-tokens

# ── Utilities ─────────────────────────────────────────────────────────────────

.PHONY: clean-mac
clean-mac:
	@find . -name '._*' -not -path './.git/*' -delete 2>/dev/null && \
		echo "Removed macOS ._* files." || true

.PHONY: clean-pyc
clean-pyc:
	@find . -type f -name '*.pyc' -delete && \
	 find . -type d -name '__pycache__' -delete && \
	 echo "Removed .pyc and __pycache__."

.PHONY: clean
clean: clean-mac clean-pyc
