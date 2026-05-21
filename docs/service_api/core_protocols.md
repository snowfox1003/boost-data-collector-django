# core.protocols

**Module path:** `core.protocols`
**Description:** Portable DTO protocols for tracker sync and collection boundaries (`TrackerResult`, `ActivityRecord`, `IncrementalState`). See also [Core public API](../Core_public_API.md).

---
<!-- SERVICE_API:GENERATED:START -->

## Protocol types (generated)

### `ActivityRecord`

Portable activity event (not a Django model).

| Property | Type |
| --- | --- |
| `source_system` | str |
| `external_id` | str |
| `occurred_at` | str |
| `activity_type` | str |
| `actor_external_id` | str |
| `source_url` | str \| None |
| `summary` | str |

### `IncrementalState`

Serializable checkpoint between runs (opaque token + human marker + extras).

| Property | Type |
| --- | --- |
| `checkpoint_token` | str \| None |
| `human_readable_marker` | str \| None |
| `extras` | Mapping[str, Any] |

### `TrackerResult`

Outcome of one logical collection or sync cycle.

| Property | Type |
| --- | --- |
| `success` | bool |
| `counts` | Mapping[str, int] |

## Module functions (generated)

| Function | Parameters | Return type | Summary |
| --- | --- | --- | --- |
| `require_activity_record` | obj: object | ActivityRecord | Return *obj* if it satisfies :class:`ActivityRecord`; else raise ``TypeError``. |
| `require_tracker_result` | obj: object | TrackerResult | Return *obj* if it satisfies :class:`TrackerResult`; else raise ``TypeError``. |

<!-- SERVICE_API:GENERATED:END -->

## Related

- [Core public API](../Core_public_API.md) — orchestration vs data protocols
- [Service API index](README.md)
- [CONTRIBUTING.md](../../CONTRIBUTING.md)
