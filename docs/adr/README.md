# Architecture Decision Records (ADR)

ADRs capture significant architectural choices, context, and consequences. They complement [Architecture overview](../Architecture_overview.md) and [Architecture data flow](../Architecture_data_flow.md), which describe the system as it is today.

## Index

| ADR | Summary | Status |
|-----|---------|--------|
| [identity-hub-decoupling.md](identity-hub-decoupling.md) | Identity hub data-layer decoupling (soft profile IDs) | Accepted (pilot: `boost_mailing_list_tracker`) |
| [paradigm-unification.md](paradigm-unification.md) | Batch (YAML/Celery) vs event-driven (Slack Socket Mode) paradigms, target swim-lane deployables, app mapping, migration path | See document |

## Format

This repo does not ship a separate ADR template file. New ADRs follow a lightweight [MADR](https://adr.github.io/madr/)-style outline: context, decision drivers, options, decision, consequences, and references.

When adding an ADR, link it here and reference [cross-app-dependencies.md](../cross-app-dependencies.md) for coupling detail.
