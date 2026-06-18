# scripts/

Repository **maintenance** scripts (not Django app code).

| Script | Purpose |
| --- | --- |
| [`backup_database.sh`](backup_database.sh) | Production VM: `pg_dump` PostgreSQL, upload to GCS (`bdc-YYYYMMDD.dump`), prune objects older than 7 days. See [docs/Deployment.md](../docs/Deployment.md#automated-database-backups). |
| [`check_service_layer_writes.py`](check_service_layer_writes.py) | CI/pre-commit: fail on Django ORM writes outside the owning app’s `services.py` (see [docs/cross-app-dependencies.md](../docs/cross-app-dependencies.md) §6). Run: `uv run python scripts/check_service_layer_writes.py` or `--report`. |
| [`generate_service_docs.py`](generate_service_docs.py) | Regenerate `docs/service_api/` from `services.py` (see CONTRIBUTING). |
| [`list_cross_app_imports.py`](list_cross_app_imports.py) | Emit cross-app import tables for [docs/cross-app-dependencies.md](../docs/cross-app-dependencies.md). |
| [`validate_collector_scaffold.py`](validate_collector_scaffold.py) | CI: validate `startcollector` scaffold (ruff + scoped pyright). |
