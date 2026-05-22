# Service API index

Index of all app service modules. All writes to app models must go through the service layer.

**Import pattern:** `from <app>.services import <function>`

| Service module | App | Short description |
|----------------|-----|-------------------|
| [cppa_user_tracker.services](cppa_user_tracker.md) | cppa_user_tracker | Identity, profiles, emails, and staging (TmpIdentity, TempProfileIdentityRelation). |
| [github_activity_tracker.services](github_activity_tracker.md) | github_activity_tracker | Repos, languages, licenses, issues, pull requests, assignees, labels. |
| [boost_collector_runner.services](boost_collector_runner.md) | boost_collector_runner | Collector group run status (last success/failure per YAML schedule group). |
| [boost_library_tracker.services](boost_library_tracker.md) | boost_library_tracker | Boost libraries, versions, dependencies, categories, maintainers/authors. |
| [boost_library_docs_tracker.services](boost_library_docs_tracker.md) | boost_library_docs_tracker | BoostDocContent (per-content metadata and sync state: is_upserted, first/last_version); BoostLibraryDocumentation (join row linking library-version to doc content only). |
| [cppa_pinecone_sync.services](cppa_pinecone_sync.md)           | cppa_pinecone_sync      | Pinecone fail list and sync status (failure tracking, last-sync bookkeeping). |
| [boost_usage_tracker.services](boost_usage_tracker.md)           | boost_usage_tracker     | External repos, Boost usage, missing-header tmp. |
| [discord_activity_tracker.services](discord_activity_tracker.md) | discord_activity_tracker | Servers, channels, messages, reactions (user profiles in cppa_user_tracker). |
| [cppa_youtube_script_tracker.services](cppa_youtube_script_tracker.md) | cppa_youtube_script_tracker | YouTube channels, videos, transcript state, and speaker links for C++ conference talks. |
| [clang_github_tracker.services](clang_github_tracker.md) | clang_github_tracker | Upsert llvm issue/PR/commit rows; DB watermarks for API fetch windows. |
| [boost_mailing_list_tracker.services](boost_mailing_list_tracker.md) | boost_mailing_list_tracker | Mailing list messages and list names. |
| [cppa_slack_tracker.services](cppa_slack_tracker.md) | cppa_slack_tracker | Slack teams, channels, messages, and membership changes. |
| [wg21_paper_tracker.services](wg21_paper_tracker.md) | wg21_paper_tracker | WG21 papers, authors, and mailings. |
| [core.protocols](core_protocols.md) | core | Runtime-checkable DTO protocols (`TrackerResult`, `ActivityRecord`, `IncrementalState`); see also [Core public API](../Core_public_API.md). |

---

## Quick reference

- **cppa_user_tracker** – Create/update Identity, TmpIdentity, BaseProfile–TmpIdentity relations, and Email.
- **github_activity_tracker** – Get-or-create Language/License/Repository; add repo languages/licenses; manage issue and PR assignees and labels.
- **boost_collector_runner** – Record successful or failed group batch runs; read `CollectorGroupRunStatus` by group id.
- **boost_library_tracker** – Get-or-create BoostLibraryRepository, BoostLibrary, BoostVersion, BoostLibraryVersion; add dependencies, categories, and role relationships.
- **boost_library_docs_tracker** – Get-or-create BoostDocContent (by content_hash; holds url, first/last_version, is_upserted); link to BoostLibraryVersion via BoostLibraryDocumentation (join row only); Pinecone sync driven by BoostDocContent.is_upserted.
- **boost_usage_tracker** – Get-or-create BoostExternalRepository, create/update BoostUsage, record missing headers (BoostMissingHeaderTmp).
- **discord_activity_tracker** – Get-or-create DiscordServer, DiscordChannel; create/update DiscordMessage, DiscordReaction. Discord user profiles in cppa_user_tracker.
- **cppa_youtube_script_tracker** – Get-or-create YouTubeChannel, YouTubeVideo; update transcript state; link speakers to videos. Speaker profiles (`YoutubeSpeaker`) in cppa_user_tracker.
- **cppa_pinecone_sync** – Get/clear/record failed IDs in PineconeFailList; get/update PineconeSyncStatus.
- **clang_github_tracker** – Upsert `ClangGithubIssueItem` / `ClangGithubCommit` during sync or backfill; read `Max(github_updated_at)` / `Max(github_committed_at)` for fetch cursors.
- **boost_mailing_list_tracker** – Mailing list message and name helpers.
- **cppa_slack_tracker** – Slack team/channel/message persistence and membership sync.
- **wg21_paper_tracker** – WG21 paper and author persistence.
- **core.protocols** – Structural contracts for sync outcomes and activity payloads (see [core_protocols.md](core_protocols.md)).

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for the rule that all writes go through the service layer, and for **regenerating** these docs from source.
