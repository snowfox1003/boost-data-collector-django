# Onboarding walkthrough — Jonathan

- **Participant:** Jonathan ([@jonathanMLDev](https://github.com/jonathanMLDev))
- **Facilitator:** Daniel ([@snowfox1003](https://github.com/snowfox1003))
- **Duration:** 90–120 min
- **Prerequisites:** Root [README.md](../../README.md) setup; skim [Architecture_overview.md](../Architecture_overview.md) §3–5

## Goals (by end of session)

- [ ] Run one management command locally (dry-run or scoped test)
- [ ] Trace one write path: command → `services.py` → model
- [ ] Explain how `cppa_pinecone_sync` fits after a doc or GitHub collector
- [ ] Run or interpret **`lint-imports`** once

## Agenda

1. **Mental model (15m)** — [Onboarding.md](../Onboarding.md) §1; service layer and Pinecone pipeline.
2. **Live trace (45m)** — Docs tracker → usage → Pinecone → `core` contracts (below).
3. **Import boundaries (15m)** — [cross-app-dependencies.md](../cross-app-dependencies.md) §5, `.importlinter`.
4. **Tests & PR hygiene (15m)** — pytest, review checklist, CODEOWNERS on `docs/` and `core/`.
5. **Q&A and homework (10m)** — Review a draft PR touching `boost_library_docs_tracker/` or `cppa_pinecone_sync/`.

## Focus apps

| App | Why |
|-----|-----|
| `boost_library_docs_tracker` | Doc crawl; joins `boost_library_tracker`; Pinecone upstream |
| `boost_usage_tracker` | External repo Boost header usage |
| `cppa_pinecone_sync` | Vector upserts and fail lists |
| `core` | `AbstractCollector`, protocols, shared operations |

READMEs: [boost_library_docs_tracker/README.md](../../boost_library_docs_tracker/README.md), [boost_usage_tracker/README.md](../../boost_usage_tracker/README.md), [cppa_pinecone_sync/README.md](../../cppa_pinecone_sync/README.md), [core/README.md](../../core/README.md).

## Hands-on exercises

### Exercise A — Docs command

```bash
python manage.py help run_boost_library_docs_tracker
# Skim boost_library_docs_tracker/management/commands/run_boost_library_docs_tracker.py
```

Note dependency on **pandoc** (see root README).

### Exercise B — Service layer + generated docs

1. Open `boost_library_docs_tracker/services.py` and one public function.
2. Open [service_api/boost_library_docs_tracker.md](../service_api/boost_library_docs_tracker.md) — generated region between `SERVICE_API:GENERATED` markers.
3. Regenerate check (optional): `python scripts/generate_service_docs.py --check`

### Exercise C — Pinecone path

Read [Architecture_overview.md § Pinecone pipeline](../Architecture_overview.md#pinecone-pipeline) and [Pinecone_preprocess_guideline.md](../Pinecone_preprocess_guideline.md) intro. Open `cppa_pinecone_sync/services.py` for fail-list / sync status writes.

### Exercise D — Import linter

```bash
# From repo root with dev deps installed:
lint-imports
# or: pre-commit run lint-imports --all-files
```

If it fails, read the contract name in the error and find it in [cross-app-dependencies.md §5](../cross-app-dependencies.md#5-import-linting--import-linter-enabled).

### Exercise E — Tests

```bash
python -m pytest boost_library_docs_tracker/tests -q --tb=no -x
# or: python -m pytest cppa_pinecone_sync/tests -q --tb=no -x
```

## Review homework (after session)

- Review a **draft PR** touching `boost_library_docs_tracker/`, `boost_usage_tracker/`, `cppa_pinecone_sync/`, or `core/`.
- Leave at least **one concrete comment**.
- Confirm **`lint-imports`** passes on the PR branch if imports changed.

## Session log

<!-- Facilitator: fill after the live 1:1. -->

| Field | Value |
|-------|--------|
| **Date** | |
| **Attendees** | Jonathan (@jonathanMLDev), Daniel (@snowfox1003) |
| **Commands run** | e.g. `manage.py help`, `pytest …`, `lint-imports` |
| **Questions / answers** | |
| **Follow-up PRs** | Link PR(s) Jonathan reviewed: |
| **Facilitator sign-off** | Ready to review PRs in docs/usage/Pinecone/core paths? **Y / N** |

### Notes

_Space for additional notes from the session._
