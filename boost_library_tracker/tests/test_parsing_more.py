"""Tests for boost_library_tracker.parsing helpers."""

import json

from boost_library_tracker.parsing import (
    parse_gitmodules_lib_submodules,
    parse_libraries_json_full,
    parse_libraries_json_library_names,
)


def test_parse_gitmodules_lib_submodules():
    text = """
[submodule "alg"]
\tpath = other/path
[submodule "json"]
\tpath = libs/json
"""
    entries = parse_gitmodules_lib_submodules(text)
    assert entries == [("json", "libs/json")]


def test_parse_libraries_json_library_names_variants():
    payload = json.dumps(
        [
            {"key": "json", "name": "JSON"},
            {"key": "child", "name": "ChildLib"},
        ]
    )
    names = parse_libraries_json_library_names(payload, "json")
    assert "json" in names
    assert "ChildLib" in names


def test_parse_libraries_json_handles_invalid_bytes_and_json():
    assert parse_libraries_json_library_names(b"\xff\xfe", "x") == []
    assert parse_libraries_json_library_names("{", "x") == []
    assert parse_libraries_json_library_names(json.dumps({}), "x") == []


def test_parse_libraries_json_full_roundtrip():
    raw = [
        {
            "key": "json",
            "name": "JSON",
            "description": "Desc",
            "documentation": "doc",
            "authors": ["A"],
            "maintainers": ["M"],
            "category": ["Cat"],
            "cxxstd": "17",
        }
    ]
    full = parse_libraries_json_full(json.dumps(raw), "json")
    assert len(full) == 1
    assert full[0]["key"] == "json"
    assert full[0]["authors"] == ["A"]
