# `core.operations.md_ops`

Convert GitHub/Slack payloads and HTML into Markdown files on disk.

## Modules

| Module | Role |
| --- | --- |
| [`issue_to_md.py`](issue_to_md.py) | GitHub issue JSON → Markdown. |
| [`pr_to_md.py`](pr_to_md.py) | Pull request JSON → Markdown (comments, diffs). |
| [`html_to_md.py`](html_to_md.py) | Generic HTML → Markdown (`HTMLToMarkdownConverter`). |
| [`github_export.py`](github_export.py) | Batch export layout for GitHub activity workspace trees. |
| [`_write.py`](_write.py) | Shared `write_markdown()` helper. |

## Tests

[`../../tests/operations/`](../../tests/operations/) (`test_*_md*.py`, `test_github_export*.py`, `test_stdlib_html_to_md.py`)
