# `core.operations`

Shared **external I/O** (GitHub, Slack, markdown export, filenames). Not a separate Django app — import from tracker apps and commands. Contrast with per-app **service APIs** (database writes only).

## Subpackages

| Package | README | Purpose |
| --- | --- | --- |
| [`github_ops/`](github_ops/) | [github_ops/README.md](github_ops/README.md) | GitHub REST/GraphQL client, tokens, git clone/push/upload. |
| [`slack_ops/`](slack_ops/) | [slack_ops/README.md](slack_ops/README.md) | Slack API client, tokens, channels, messages, file fetch. |
| [`md_ops/`](md_ops/) | [md_ops/README.md](md_ops/README.md) | JSON/HTML → Markdown (issues, PRs, GitHub export). |
| [`file_ops/`](file_ops/) | [file_ops/README.md](file_ops/README.md) | Cross-platform `sanitize_filename`. |

## Docs

Long-form design notes: [docs/operations/](../../docs/operations/README.md) (e.g. [github.md](../../docs/operations/github.md)).

## Tests

[`../tests/operations/`](../tests/operations/) and [`../tests/github_ops/`](../tests/github_ops/)
