# boost_library_tracker.services

**Module path:** `boost_library_tracker.services`
**Description:** Boost libraries, versions, dependencies, categories, and maintainer/author roles. Single place for all writes to boost_library_tracker models.

**Type notation:** Model types refer to `boost_library_tracker.models`. Cross-app: `GitHubRepository`, `GitHubFile` are from `github_activity_tracker.models`; `GitHubAccount` is from `cppa_user_tracker.models`.

---
<!-- SERVICE_API:GENERATED:START -->

## Public API (generated)

| Function | Parameters | Return type | Summary |
| --- | --- | --- | --- |
| `add_boost_dependency` | client_library: BoostLibrary, version: BoostVersion, dep_library: BoostLibrary | tuple[BoostDependency, bool] | Add a dependency (idempotent). Returns (dependency, created). |
| `add_dependency_changelog` | client_library: BoostLibrary, dep_library: BoostLibrary, is_add: bool, created_at | tuple[DependencyChangeLog, bool] | Add or update a dependency changelog entry. If exists (same client, dep, created_at), updates is_add. Returns (log, created). |
| `add_library_category` | library: BoostLibrary, category: BoostLibraryCategory | tuple[BoostLibraryCategoryRelationship, bool] | Link library to category (idempotent). Returns (relation, created). |
| `add_library_version_role` | library_version: BoostLibraryVersion, account: GitHubAccount, is_maintainer: bool = False, is_author: bool = False | tuple[BoostLibraryRoleRelationship, bool] | Add or update maintainer/author for a library version. Returns (relation, created). |
| `get_or_create_account_from_name` | name: str | GitHubAccount | Get or create a GitHubAccount for a contributor name string (from libraries.json). |
| `get_or_create_boost_file` | github_file: GitHubFile, library: BoostLibrary | tuple[BoostFile, bool] | Get or create BoostFile linking a GitHubFile to a BoostLibrary. If exists, updates library. |
| `get_or_create_boost_library` | repo: BoostLibraryRepository, name: str | tuple[BoostLibrary, bool] | Get or create a BoostLibrary by repo and name. If exists, no extra fields to update. |
| `get_or_create_boost_library_category` | name: str | tuple[BoostLibraryCategory, bool] | Get or create BoostLibraryCategory by name. |
| `get_or_create_boost_library_repo` | github_repository: GitHubRepository | tuple[BoostLibraryRepository, bool] | Get or create BoostLibraryRepository for a GitHub repository (inherited model). Creates only the child row (no parent save) to avoid NOT NULL errors on corrupt parent rows. |
| `get_or_create_boost_library_version` | library: BoostLibrary, version: BoostVersion, cpp_version: str \| None = None, description: str \| None = None, key: str \| None = None, documentation: str \| None = None | tuple[BoostLibraryVersion, bool] | Get or create BoostLibraryVersion for library + version. If exists, updates only fields that are provided (not None). |
| `get_or_create_boost_version` | version: str, version_created_at = None | tuple[BoostVersion, bool] | Get or create BoostVersion by version string. If exists, updates version_created_at. |
| `has_new_boost_release` |  | bool | Return True when GitHub has a Boost release not yet recorded in BoostVersion. |

<!-- SERVICE_API:GENERATED:END -->

## Related

- [Service API index](README.md)
- [CONTRIBUTING.md](../../CONTRIBUTING.md)
- [Schema](../Schema.md)
