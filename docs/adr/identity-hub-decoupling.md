# ADR: Identity hub data-layer decoupling

**Status:** Accepted (pilot implemented for `boost_mailing_list_tracker`)
**Context:** Week 22 import-linter contracts enforce Python import boundaries; ORM `ForeignKey` into `cppa_user_tracker` still forces every consumer app to depend on the full identity schema for migrations and pytest table creation.

## Decision

1. **Replace cross-app `ForeignKey` to profile models** with a **`BigIntegerField`** storing the profile primary key, keeping the existing **`db_column`** (e.g. `sender_id`) so production data needs no value rewrite.
2. **Drop the PostgreSQL FK constraint** in migrations (`RunSQL` / dynamic constraint discovery); do not rely on `db_constraint=False` as the end state.
3. **Resolve identity at boundaries:**
   - **Writes:** consumer collectors call `cppa_user_tracker.services.get_or_create_*` and pass `profile.pk` into the consumer `services.py`.
   - **Reads:** consumer code calls `cppa_user_tracker.services.get_*_profile_by_id` (and optional bulk helpers), not `cppa_user_tracker.models` from consumer packages (enforced by import-linter for decoupled apps).
4. **Subset-schema tests:** per-app `config/test_settings_subset_<app>.py` with minimal `INSTALLED_APPS` so pytest can create only that app’s tables when the hub FK is removed.

## Consequences

- Deleting a profile row **no longer CASCADE-deletes** dependent messages in decoupled apps; ops should treat orphan `sender_id` values via periodic SQL checks.
- Consumer `admin.py` loses `raw_id_fields` / `select_related` on profile FKs; use profile id columns and service lookups where needed.
- Rollout order: mailing list (pilot) → YouTube / WG21 paper → Discord / Slack → GitHub cluster.

## References

- [cross-app-dependencies.md §1](../cross-app-dependencies.md) — FK inventory
- [cppa_user_tracker/services.py](../../cppa_user_tracker/services.py) — identity write/read API
- [config/test_settings_subset_boost_mailing_list.py](../../config/test_settings_subset_boost_mailing_list.py) — subset pytest settings (pilot)
