# `core.utils`

Stateless helpers imported across apps. Prefer adding a focused module here rather than duplicating logic in trackers.

## Modules

| Module | Role |
| --- | --- |
| [`datetime_parsing.py`](datetime_parsing.py) | CLI/API date strings → timezone-aware `datetime`. |
| [`text_processing.py`](text_processing.py) | Slack/Discord message cleaning and filler filtering. |
| [`boost_version_operations.py`](boost_version_operations.py) | Boost version parse, encode, and loose compare for metadata keys. |

## Tests

[`../tests/test_datetime_parsing.py`](../tests/test_datetime_parsing.py), [`../tests/test_text_processing.py`](../tests/test_text_processing.py), [`../tests/test_boost_version_operations.py`](../tests/test_boost_version_operations.py)
