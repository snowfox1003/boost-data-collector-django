# wg21_paper_tracker.services

**Module path:** `wg21_paper_tracker.services`
**Description:** Database logic for WG21 Paper Tracker. Writes for this app's models go through this module.

**Type notation:** Model types refer to `wg21_paper_tracker.models`.

---
<!-- SERVICE_API:GENERATED:START -->

## Public API (generated)

| Function | Parameters | Return type | Summary |
| --- | --- | --- | --- |
| `get_or_create_mailing` | mailing_date: str, title: str | tuple[WG21Mailing, bool] | — |
| `get_or_create_paper` | paper_id: str, url: str, title: str, document_date: date \| None, mailing: WG21Mailing, subgroup: str = '', author_names: Optional[list[str]] = None, author_emails: Optional[list[str]] = None, year: int \| None = None | tuple[WG21Paper, bool] | — |
| `get_or_create_paper_author` | paper: WG21Paper, profile: WG21PaperAuthorProfile, author_order: int | tuple[WG21PaperAuthor, bool] | Get or create a WG21PaperAuthor link for (paper, profile), with author_order (1-based). Updates author_order on existing link if it differs. |
| `mark_paper_downloaded` | paper_id: str, year: int \| None = None | None | — |

<!-- SERVICE_API:GENERATED:END -->

## Related

- [Service API index](README.md)
- [CONTRIBUTING.md](../../CONTRIBUTING.md)
