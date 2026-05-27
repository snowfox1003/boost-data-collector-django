# Documentation (per-topic)

Documentation is organized **by topic**, not by app. Each doc covers one cross-cutting concern (workflow, workspace, service API, schema, etc.). To understand a single app, use the relevant topic docs and the per-app service API file.

## Topic index

| Topic | Doc | Purpose |
|-------|-----|---------|
| **Onboarding** | [Onboarding.md](Onboarding.md) | First-day orientation: mental model, app roles, data dependencies, where patterns differ. |
| **Architecture overview** | [Architecture_overview.md](Architecture_overview.md) | **Start here for system design:** all 15 domain apps + `core`, persistence, coupling, links to app READMEs and service API. |
| **Workflow** | [Workflow.md](Workflow.md) | Main application workflow, execution order, and project details. |
| **Architecture (data flow)** | [Architecture_data_flow.md](Architecture_data_flow.md) | Data flow (sources → collectors → DB / workspace → Pinecone), orchestration diagram, per-app component map. |
| **Tutorial: building a collector** | [Tutorial_building_a_collector.md](Tutorial_building_a_collector.md) | End-to-end walkthrough: `startcollector`, hooks, tests, YAML/Celery, deploy. |
| **Cross-app dependencies** | [cross-app-dependencies.md](cross-app-dependencies.md) | FK/import matrix, import-linter contracts, regeneration via `list_cross_app_imports.py`. |
| **CODEOWNERS / reviews** | [CODEOWNERS_and_branch_protection.md](CODEOWNERS_and_branch_protection.md) | CODEOWNERS behavior, enabling branch protection, verification checklist. |
| **Onboarding walkthroughs** | [onboarding/](onboarding/README.md) | 1:1 session runbooks (Leo, Jonathan) and session logs. |
| **Bus-factor checklist** | [BUS_FACTOR_DELIVERABLES.md](BUS_FACTOR_DELIVERABLES.md) | Ticket acceptance checklist, branch-protection verification, comment template. |
| **Add a collector** | [How_to_add_a_collector.md](How_to_add_a_collector.md) | Checklist: new command, registration, tests, docs. |
| **Core API** | [Core_public_API.md](Core_public_API.md) | Stable `core` imports: collectors, error classification. |
| **Operations** | [operations/](operations/README.md) | **Group:** shared I/O (GitHub, Discord, etc.) used by multiple apps. Index in [operations/README.md](operations/README.md). |
| → GitHub | [operations/github.md](operations/github.md) | Clone, push, fetch file, create PR/issue/comment; token use. |
| → DiscordChatExporter | [operations/discord_chat_exporter.md](operations/discord_chat_exporter.md) | Install CLI, workspace path, `.env` for Tyrrrz exporter used by Discord ingestion. |
| **Workspace** | [Workspace.md](Workspace.md) | Workspace layout and usage for file processing (`workspace/<app>/...`). |
| **Schema** | [Schema.md](Schema.md) | Database schema and table relationships. |
| **Development** | [Development_guideline.md](Development_guideline.md) | Development setup, app requirements, and step-by-step workflow. |
| **Testing / typing** | [README.md](../README.md#running-tests), [Development_guideline.md](Development_guideline.md#testing-workflow) | pytest (Postgres), coverage, when to run tests; **Pyright** (`uv run pyright`) and CI jobs. |
| **Deployment** | [Deployment.md](Deployment.md) | CI/CD pipeline, environment secrets (`SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY`; optional `SSH_PORT`), server setup, and deploy script behavior. |
| **Contributing** | [CONTRIBUTING.md](../CONTRIBUTING.md) | Service layer (single place for writes) and contributor guidelines. |
| **Service API** | [Service_API.md](Service_API.md) | API reference and index for all service layer functions. |
| **Service API (per app)** | [service_api/](service_api/) | Per-app service API docs (name, description, parameters, return types, validation). |

## Operations (shared I/O)

**Operations** = external integrations used by many apps (not the same as **Service API**, which is for DB writes). See **[operations/README.md](operations/README.md)** for the full list and when to add one.

- **GitHub:** [operations/github.md](operations/github.md) — `core.operations.github_ops` (clone, push, PR, issue, comment).
- **Discord (ingestion):** [operations/discord_chat_exporter.md](operations/discord_chat_exporter.md) — DiscordChatExporter CLI; [service_api/discord_activity_tracker.md](service_api/discord_activity_tracker.md) — commands, sync layout, Pinecone. *(Notifications / webhooks: add an operations doc when implemented.)*

## Finding app-specific info

- **Service layer (create/update/delete):** [service_api/](service_api/) → e.g. [github_activity_tracker.md](service_api/github_activity_tracker.md).
- **Operations (GitHub, Discord, …):** [operations/README.md](operations/README.md) and the docs in [operations/](operations/).
- **Workspace (file paths, JSON cache):** [Workspace.md](Workspace.md) — which apps use workspace and the folder layout.
- **Schema (models):** [Schema.md](Schema.md).
- **Workflow (when an app runs):** [Workflow.md](Workflow.md).
