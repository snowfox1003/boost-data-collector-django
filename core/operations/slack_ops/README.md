# `core.operations.slack_ops`

Slack Web API integration shared by `cppa_slack_tracker` and related jobs.

## Modules

| Module | Role |
| --- | --- |
| [`client.py`](client.py) | `SlackAPIClient` wrapper. |
| [`tokens.py`](tokens.py) | Bot/app token lookup per team. |
| [`channels.py`](channels.py) | Channel list, join policy, background join worker. |
| [`messages.py`](messages.py) | Channel history fetch. |
| [`fetcher.py`](fetcher.py) | `SlackFetcher`, file download, huddle transcript helpers. |

## Tests

[`../../tests/operations/`](../../tests/operations/) (`test_slack_*.py`)
