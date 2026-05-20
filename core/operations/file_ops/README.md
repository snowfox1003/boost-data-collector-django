# `core.operations.file_ops`

Small path/filename helpers safe across Windows, Linux, and macOS.

## API

- [`sanitize_filename()`](__init__.py) — strip invalid characters, reserved Windows names, and overlong paths (default max 200).

## Tests

[`../../tests/test_file_ops.py`](../../tests/test_file_ops.py)
