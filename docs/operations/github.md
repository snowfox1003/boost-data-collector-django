# GitHub operations – shared utilities under `core.operations.github_ops`

The **`core.operations.github_ops`** package is the single layer for all GitHub-related actions (clone, push, fetch file, create PR, create issue, comment). Tokens, rate limits, and errors are handled there. Any app (`github_activity_tracker`, `boost_library_tracker`, `core`, etc.) should use **`core.operations.github_ops`** instead of calling GitHub or git directly.

This is **not** a Django app: it is **not** listed in **`INSTALLED_APPS`**.

---

## Token use (which token for which operation)

| Operation | Token use | Env / setting |
|-----------|-----------|----------------|
| **Read API** (fetch repos, issues, PRs, file content) | `scraping` | `GITHUB_TOKENS_SCRAPING` (round-robin, thread-safe) or `GITHUB_TOKEN` |
| **Git clone** | `scraping` | Same as above |
| **Git push, create PR, create issue, comment on issue** | `push`, `write`, or `create_pr` | `GITHUB_TOKEN_WRITE` or `GITHUB_TOKEN` |

---

## 1. Git operations (clone, push, fetch one file)

**Module:** `core.operations.github_ops.git_ops` (or `from core.operations.github_ops import clone_repo, push, fetch_file_content`)

| Function | Description |
|----------|-------------|
| `clone_repo(url_or_slug, dest_dir, token=None, depth=None)` | Clone a repo. `url_or_slug`: `"owner/repo"` or full URL. Uses scraping token. |
| `push(repo_dir, remote="origin", branch=None, token=None)` | Push to remote. Uses push token. |
| `fetch_file_content(owner, repo, path, ref=None, client=None)` | Get one file content via API (bytes). Uses scraping token. |

**Example (any app):**

```python
from core.operations.github_ops import clone_repo, push, fetch_file_content

# Clone (read-only token)
clone_repo("boostorg/boost", "/tmp/boost", depth=1)

# Fetch one file (e.g. README)
content = fetch_file_content("boostorg", "boost", "README.md")
text = content.decode("utf-8")

# Push (push token)
push("/tmp/boost", remote="origin", branch="my-branch")
```

---

## 2. API client (read + write)

**Module:** `core.operations.github_ops.client.GitHubAPIClient`
**Obtain client:** `get_github_client(use=...)` from `core.operations.github_ops`

| Method | Token use | Description |
|--------|-----------|-------------|
| `rest_request(endpoint)` | (client built with given `use`) | GET request |
| `get_file_content(owner, repo, path, ref=None)` | scraping | One file (bytes + encoding). |
| `create_pull_request(owner, repo, title, head, base, body="")` | write | Create PR. |
| `create_issue(owner, repo, title, body="")` | write | Create issue. |
| `create_issue_comment(owner, repo, issue_number, body)` | write | Comment on issue. |

**Example (any app):**

```python
from core.operations.github_ops import get_github_client

# Create PR, issue, comment (same write token)
client = get_github_client(use="write")
pr = client.create_pull_request(
    "boostorg", "boost", "Title", "my-branch", "develop", "Body"
)
issue = client.create_issue("boostorg", "boost", "Bug", "Description")
client.create_issue_comment("boostorg", "boost", issue["number"], "A comment")
```

---

## 3. Getting a raw token (e.g. for external tools)

**Module:** `core.operations.github_ops.tokens`

```python
from core.operations.github_ops import get_github_token

token = get_github_token(use="push")   # for git over HTTPS
token = get_github_token(use="write")  # for issues/comments
```

---

## Summary

- **One package:** **`core.operations.github_ops`** – git operations (`clone_repo`, `push`, `fetch_file_content`) and API client (`get_github_client(use=...)`, `GitHubAPIClient`).
- **Token per use:** scraping (read/clone), push (git push), write (create PR, issues, comments).
- **All apps** import from **`core.operations.github_ops`**; **`github_activity_tracker`** uses it for sync and does not contain GitHub I/O code.
