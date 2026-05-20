# `core.operations.github_ops`

GitHub API and git-remote helpers used by multiple trackers.

## Modules

| Module | Role |
| --- | --- |
| [`client.py`](client.py) | `GitHubAPIClient` — REST/GraphQL, pagination, rate limits. |
| [`tokens.py`](tokens.py) | Token resolution and `get_github_client()`. |
| [`git_ops.py`](git_ops.py) | Clone, push, pull, blob/tree upload, remote file read, commit file changes. |

## Docs

[docs/operations/github.md](../../../docs/operations/github.md)

## Tests

[`../../tests/github_ops/`](../../tests/github_ops/)
