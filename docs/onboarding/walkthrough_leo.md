# Onboarding walkthrough — Leo

- **Participant:** Leo ([@leostar0412](https://github.com/leostar0412))
- **Facilitator:** Daniel ([@snowfox1003](https://github.com/snowfox1003))
- **Duration:** 90–120 min
- **Prerequisites:** Root [README.md](../../README.md) setup; skim [Architecture_overview.md](../Architecture_overview.md) §3–4

## Goals (by end of session)

- [ ] Run one management command locally (dry-run or scoped test)
- [ ] Trace one write path: command → `services.py` → model
- [ ] Name one upstream and one downstream app for `github_activity_tracker`
- [ ] Know where to open [Schema.md](../Schema.md), [service_api/](../service_api/), [cross-app-dependencies.md](../cross-app-dependencies.md)

## Agenda

1. **Mental model (15m)** — [Onboarding.md](../Onboarding.md) §1 (one DB, collectors, service layer, `core`).
2. **Live trace (45m)** — Identity → GitHub → Boost catalog → scheduler (below).
3. **Tests & PR hygiene (20m)** — pytest subset, [Development_guideline.md § Review process](../Development_guideline.md#review-process), CODEOWNERS paths for Leo’s areas.
4. **Q&A and homework (10m)** — Review a small draft PR touching `github_activity_tracker/` or `cppa_user_tracker/`.

## Focus apps

| App | Why |
|-----|-----|
| `cppa_user_tracker` | Identity hub; downstream trackers FK here |
| `github_activity_tracker` | GitHub mirror; shared Language/License |
| `boost_library_tracker` | Boost catalog on top of GitHub models |
| `boost_collector_runner` | `run_scheduled_collectors` + YAML |

Use app READMEs instead of re-deriving commands: [cppa_user_tracker/README.md](../../cppa_user_tracker/README.md), [github_activity_tracker/README.md](../../github_activity_tracker/README.md), [boost_library_tracker/README.md](../../boost_library_tracker/README.md), [boost_collector_runner/README.md](../../boost_collector_runner/README.md).

## Hands-on exercises

### Exercise A — Locate commands

```bash
python manage.py help | grep -E "run_cppa_user|run_boost_github|run_scheduled"
```

Open `config/boost_collector_schedule.yaml` and find one task that maps to a command above.

### Exercise B — Trace a write path

1. Open `github_activity_tracker/management/commands/run_boost_github_activity_tracker.py` (or the command your schedule uses).
2. Follow one call into `github_activity_tracker/services.py` (e.g. repo or issue upsert).
3. Open the matching model in `github_activity_tracker/models.py`.
4. Confirm **no** `Model.objects.create()` in the command module outside tests.

### Exercise C — Coupling

In [cross-app-dependencies.md](../cross-app-dependencies.md) §1, find one FK from `github_activity_tracker` → `cppa_user_tracker`. Explain why it is intentional.

### Exercise D — Tests

```bash
python -m pytest cppa_user_tracker/tests -q --tb=no -x
# or: python -m pytest github_activity_tracker/tests -q --tb=no -x
```

## Review homework (after session)

- Review a **draft PR** from Daniel that touches `github_activity_tracker/` or `cppa_user_tracker/` (or `boost_library_tracker/`).
- Leave at least **one concrete comment** (question or suggestion).
- If branch protection is on, approve only when comfortable (request review from `@leostar0412` manually if needed).

## Session log

<!-- Facilitator: fill after the live 1:1. -->

| Field | Value |
|-------|--------|
| **Date** | |
| **Attendees** | Leo (@leostar0412), Daniel (@snowfox1003) |
| **Commands run** | e.g. `manage.py help`, `pytest …`, dry-run collector |
| **Questions / answers** | |
| **Follow-up PRs** | Link PR(s) Leo reviewed: |
| **Facilitator sign-off** | Ready to review PRs in `github_activity_tracker/`, `cppa_user_tracker/`, `boost_library_tracker/`, `boost_collector_runner/`? **Y / N** |

### Notes

_Space for additional notes from the session._
