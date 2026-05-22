# boost_collector_runner.services

**Module path:** `boost_collector_runner.services`
**Description:** Persists last run outcome per YAML schedule group (`CollectorGroupRunStatus`). All creates/updates for this app's models must go through functions here.

**Type notation:** Model types refer to `boost_collector_runner.models`.

---
<!-- SERVICE_API:GENERATED:START -->

## Public API (generated)

| Function | Parameters | Return type | Summary |
| --- | --- | --- | --- |
| `get_group_status` | group_id: str | Optional[CollectorGroupRunStatus] | Return status row for a group, or None if never run. |
| `list_group_statuses` |  | dict[str, CollectorGroupRunStatus] | Return all group statuses keyed by group_id. |
| `record_group_failure` | group_id: str, *, exit_code: int = 1, when: Optional[datetime] = None | CollectorGroupRunStatus | Record a failed group batch run. |
| `record_group_success` | group_id: str, *, when: Optional[datetime] = None | CollectorGroupRunStatus | Record a successful group batch run. |

<!-- SERVICE_API:GENERATED:END -->

## Related

- [Service API index](README.md)
- [Contributing](../../CONTRIBUTING.md)
