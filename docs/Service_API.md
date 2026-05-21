# Service layer API reference

All writes to app models must go through the service layer. The API is documented **per app** in the [service_api](service_api/) folder.

---

## Index (service name and description)

| Service | Module path | Short description |
|---------|-------------|--------------------|
| **cppa_user_tracker** | `cppa_user_tracker.services` | Identity, profiles, emails, and staging (TmpIdentity, TempProfileIdentityRelation). |
| **cppa_pinecone_sync**      | `cppa_pinecone_sync.services`      | Pinecone fail list and sync status (failure tracking, last-sync bookkeeping).       |
| **github_activity_tracker** | `github_activity_tracker.services` | Repos, languages, licenses, issues, pull requests, assignees, labels. |
| **boost_library_tracker**   | `boost_library_tracker.services`   | Boost libraries, versions, dependencies, categories, maintainers/authors. |
| **boost_library_docs_tracker** | `boost_library_docs_tracker.services` | Globally unique doc content (BoostDocContent) and (library-version, page) relation tracking (BoostLibraryDocumentation). |
| **boost_usage_tracker**    | `boost_usage_tracker.services`    | External repos, Boost usage, missing-header tmp. |
| **discord_activity_tracker** | `discord_activity_tracker.services` | Discord servers, channels, messages, reactions (authors: `cppa_user_tracker.DiscordProfile`). |
| **cppa_youtube_script_tracker** | `cppa_youtube_script_tracker.services` | YouTube channels, videos, tags, transcript state; speaker links. |
| **clang_github_tracker** | `clang_github_tracker.services` | Upsert llvm issue/PR/commit rows; fetch watermarks. |
| **boost_mailing_list_tracker** | `boost_mailing_list_tracker.services` | Mailing list messages and names. |
| **cppa_slack_tracker** | `cppa_slack_tracker.services` | Slack teams, channels, messages, membership. |
| **wg21_paper_tracker** | `wg21_paper_tracker.services` | WG21 papers, authors, mailings. |

---

## Per-app docs

- **[service_api/README.md](service_api/README.md)** – Index of all service modules (name + short description).
- **[service_api/cppa_user_tracker.md](service_api/cppa_user_tracker.md)** – Full API for `cppa_user_tracker.services`.
- **[service_api/github_activity_tracker.md](service_api/github_activity_tracker.md)** – Full API for `github_activity_tracker.services` (includes validation: empty `name` raises `ValueError` for Language/License).
- **[service_api/boost_library_tracker.md](service_api/boost_library_tracker.md)** – API for `boost_library_tracker.services`.
- **[service_api/boost_library_docs_tracker.md](service_api/boost_library_docs_tracker.md)** – API for `boost_library_docs_tracker.services`.
- **[service_api/cppa_pinecone_sync.md](service_api/cppa_pinecone_sync.md)** – API for `cppa_pinecone_sync.services`.
- **[service_api/boost_usage_tracker.md](service_api/boost_usage_tracker.md)** – API for `boost_usage_tracker.services`.
- **[service_api/discord_activity_tracker.md](service_api/discord_activity_tracker.md)** – API for `discord_activity_tracker.services`; management commands, sync modules, and Pinecone notes.
- **[service_api/cppa_youtube_script_tracker.md](service_api/cppa_youtube_script_tracker.md)** – API for `cppa_youtube_script_tracker.services`; preprocessor, fetcher, workspace, and transcript helpers.
- **[service_api/clang_github_tracker.md](service_api/clang_github_tracker.md)** – API for `clang_github_tracker.services`.
- **[service_api/boost_mailing_list_tracker.md](service_api/boost_mailing_list_tracker.md)** – API for `boost_mailing_list_tracker.services`.
- **[service_api/cppa_slack_tracker.md](service_api/cppa_slack_tracker.md)** – API for `cppa_slack_tracker.services`.
- **[service_api/wg21_paper_tracker.md](service_api/wg21_paper_tracker.md)** – API for `wg21_paper_tracker.services`.
- **[service_api/core_protocols.md](service_api/core_protocols.md)** – `core.protocols` DTO protocols (`TrackerResult`, `ActivityRecord`, `IncrementalState`).

Tables in each file are **generated** from source; see [CONTRIBUTING.md](../CONTRIBUTING.md#regenerating-service-api-docs).

---

## Validation (examples)

Some service functions validate arguments and raise before writing:

- **github_activity_tracker.services**
  - `get_or_create_language(name)` – Raises **`ValueError`** if `name` is empty or whitespace-only.
  - `get_or_create_license(name, ...)` – Raises **`ValueError`** if `name` is empty or whitespace-only.
- **boost_library_tracker.services**
  - `get_or_create_boost_library(repo, name)`, `get_or_create_boost_version(version)`, `get_or_create_boost_library_category(name)` – Raise **`ValueError`** if name/version is empty or whitespace-only.
- **boost_library_docs_tracker.services**
  - `get_or_create_doc_content(url, ...)` – Raises **`ValueError`** if `url` is empty or whitespace-only.
- **discord_activity_tracker.services**
  - No intentional **`ValueError`** on invalid inputs; bulk helpers may **skip** rows and log warnings (see [discord_activity_tracker.md](service_api/discord_activity_tracker.md#raises-and-edge-behavior)). **`CollectorFailureCategory`** is not set in this module; see [discord_activity_tracker.md](service_api/discord_activity_tracker.md#collectorfailurecategory).

See each app’s doc in [service_api/](service_api/) for parameter types, return types, and any **Raises** section.

**Sync (orchestration):** For syncing a repo from GitHub, see [github_activity_tracker.md](service_api/github_activity_tracker.md#sync--orchestration-not-a-service): `sync_github(repo)` in `github_activity_tracker.sync`—not a service write, but documented there so others can use it.

---

## Related docs

- [CONTRIBUTING.md](../CONTRIBUTING.md) – Rule that all writes go through the service layer.
- [Schema.md](Schema.md) – Database schema and models.
