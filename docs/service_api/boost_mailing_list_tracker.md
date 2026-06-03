# boost_mailing_list_tracker.services

**Module path:** `boost_mailing_list_tracker.services`
**Description:** Service layer for mailing list messages and names. All creates/updates/deletes for this app's models must go through functions here.

**Type notation:** Model types refer to `boost_mailing_list_tracker.models`.

---
<!-- SERVICE_API:GENERATED:START -->

## Public API (generated)

| Function | Parameters | Return type | Summary |
| --- | --- | --- | --- |
| `delete_mailing_list_message` | message: MailingListMessage | None | Delete a MailingListMessage. |
| `get_or_create_mailing_list_message` | sender_profile_id: int, msg_id: str, sent_at: datetime, parent_id: str = '', thread_id: str = '', subject: str = '', content: str = '', list_name: str = '' | tuple[MailingListMessage, bool] | Get or create a MailingListMessage by msg_id (unique). |

<!-- SERVICE_API:GENERATED:END -->

## Related

- [Service API index](README.md)
- [CONTRIBUTING.md](../../CONTRIBUTING.md)
