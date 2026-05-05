# Collector data flow (architecture)

High-level view of how data moves through Boost Data Collector. For execution order and scheduling, see [Workflow.md](Workflow.md).

```mermaid
flowchart LR
  subgraph sources [External_sources]
    GH[GitHub_API]
    SL[Slack_API]
    DC[Discord]
    ML[Mailing_lists]
    YT[YouTube]
  end

  subgraph collectors [Django_apps_commands]
    CMD[Management_commands]
  end

  subgraph storage [Local_and_DB]
    WS[workspace_raw]
    PG[(PostgreSQL)]
  end

  subgraph vectors [Search]
    PC[cppa_pinecone_sync]
    PIN[Pinecone]
  end

  GH --> CMD
  SL --> CMD
  DC --> CMD
  ML --> CMD
  YT --> CMD
  CMD --> WS
  CMD --> PG
  PG --> PC
  PC --> PIN
```

- **Collectors** are Django apps exposing `management/commands` (scheduled via `boost_collector_runner` YAML + Celery Beat, or run manually with `manage.py`).
- **Workspace** holds clones, exports, and intermediate files under `WORKSPACE_DIR` (see [Workspace.md](Workspace.md)).
- **PostgreSQL** is the system of record for ORM models across apps.
- **cppa_pinecone_sync** (and app-specific upsert paths) push embeddings/metadata to **Pinecone** namespaces.
