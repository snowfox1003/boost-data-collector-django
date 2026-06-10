# `core.collectors`

Collector orchestration shared by every `run_*` management command.

## Modules

| Module | Role |
| --- | --- |
| [`base_collector.py`](base_collector.py) | `AbstractCollector` (`validate_config`, `collect() -> TrackerResult`), `CollectorRunnable` protocol, lifecycle mixin (`load_incremental_state`, `sync_pinecone`, `handle_error`). |
| [`command_base.py`](command_base.py) | `BaseCollectorCommand` — Django template: `get_collector` → `run` (logs `TrackerResult`) → `sync_pinecone`. |
| [`../tracker_result.py`](../tracker_result.py) | `GenericTrackerResult` — default frozen `TrackerResult` DTO. |
| [`../incremental_state.py`](../incremental_state.py) | `GenericIncrementalState` — default frozen `IncrementalState` DTO. |

## Usage

New collectors should subclass `AbstractCollector` and wire a management command through `BaseCollectorCommand`. See [Tutorial: building a collector](../../docs/Tutorial_building_a_collector.md) (walkthrough), [How to add a collector](../../docs/How_to_add_a_collector.md) (checklist), and the parent [core README](../README.md).

## Tests

[`../tests/test_collectors_base.py`](../tests/test_collectors_base.py)
