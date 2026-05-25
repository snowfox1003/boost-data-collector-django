# cppa_pinecone_sync — Service API

Module: `cppa_pinecone_sync.services`

All creates/updates/deletes for `PineconeFailList` and `PineconeSyncStatus` must go through this module. See [CONTRIBUTING.md](../../CONTRIBUTING.md).

---
<!-- SERVICE_API:GENERATED:START -->

## Public API (generated)

| Function | Parameters | Return type | Summary |
| --- | --- | --- | --- |
| `clear_failed_ids` | app_type: str | int | Delete all PineconeFailList records for the given app_type. Returns count deleted. |
| `get_failed_ids` | app_type: str | list[str] | Return all failed_id values for the given app_type. |
| `get_final_sync_at` | app_type: str | Optional[datetime] | Return final_sync_at for the given app_type, or None if no record exists. |
| `record_failed_ids` | app_type: str, failed_ids: list[str] | list[PineconeFailList] | Bulk-create PineconeFailList entries for each failed_id. Returns created objects. |
| `sync_source_to_pinecone` | app_type: str, namespace: str, preprocess_fn: Callable[..., Any], *, instance: Any = None | dict[str, Any] | Public cross-app entry for vector upsert. |
| `update_sync_status` | app_type: str, final_sync_at: Optional[datetime] = None | PineconeSyncStatus | Create or update PineconeSyncStatus for the given app_type. |

<!-- SERVICE_API:GENERATED:END -->

## Related

- [Service API index](README.md)
- [CONTRIBUTING.md](../../CONTRIBUTING.md)
