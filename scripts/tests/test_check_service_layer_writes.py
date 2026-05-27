"""Unit tests for scripts/check_service_layer_writes.py (no Django DB)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import scripts.check_service_layer_writes as slw


def _first_call(tree: ast.AST, attr: str) -> ast.Call:
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            if n.func.attr == attr:
                return n
    raise AssertionError(f"no Call with .{attr}")


def test_model_from_objects_expression_bulk_update() -> None:
    tree = ast.parse(
        "GitHubRepository.objects.bulk_update([], ['stars'])",
        mode="exec",
    )
    call = _first_call(tree, "bulk_update")
    assert slw._model_from_objects_expression(call) == "GitHubRepository"


def test_model_from_objects_expression_filter_delete() -> None:
    tree = ast.parse(
        "GitCommitFileChange.objects.filter(commit=c).delete()",
        mode="exec",
    )
    delete = _first_call(tree, "delete")
    recv = delete.func.value
    assert slw._model_from_objects_expression(recv) == "GitCommitFileChange"


def test_check_allowlist_flags_stale_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "allow.json"
    p.write_text(
        json.dumps(
            {
                "violations": [
                    {
                        "file": "missing.py",
                        "line": 1,
                        "model": "X",
                        "eval": "Test 7 / B2",
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(slw, "ALLOWLIST_PATH", p)
    errs, _ = slw.check_allowlist([], slw.load_allowlist())
    assert any("Stale allowlist" in e for e in errs)


def test_check_allowlist_matches_violation_with_todo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    src = tmp_path / "fake_app" / "cmd.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "# TODO(service-layer): Test 7 / B2\nX.objects.create()\n",
        encoding="utf-8",
    )
    p = tmp_path / "allow.json"
    p.write_text(
        json.dumps(
            {
                "violations": [
                    {
                        "file": str(src.relative_to(tmp_path)).replace("\\", "/"),
                        "line": 2,
                        "model": "X",
                        "eval": "Test 7 / B2",
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(slw, "ALLOWLIST_PATH", p)
    monkeypatch.setattr(slw, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        slw,
        "build_model_owner_map",
        lambda: {"X": "fake_app"},
    )
    v = slw.Violation(
        path="fake_app/cmd.py",
        line=2,
        model="X",
        kind="objects.create",
        owner_app="fake_app",
        file_app="fake_app",
    )
    errs, _ = slw.check_allowlist([v], slw.load_allowlist())
    assert errs == []


_MODELS_PY = """\
from django.db import models

class SharedModel(models.Model):
    pass
"""


def test_build_model_owner_map_detects_duplicate_class_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for app in ("app_a", "app_b"):
        d = tmp_path / app
        d.mkdir()
        (d / "models.py").write_text(_MODELS_PY, encoding="utf-8")
    monkeypatch.setattr(slw, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(slw, "TRACKER_APPS", ["app_a", "app_b"])
    with pytest.raises(SystemExit) as exc:
        slw.build_model_owner_map()
    assert exc.value.code == 2


def test_build_model_owner_map_no_duplicates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "only_app").mkdir()
    (tmp_path / "only_app" / "models.py").write_text(_MODELS_PY, encoding="utf-8")
    monkeypatch.setattr(slw, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(slw, "TRACKER_APPS", ["only_app"])
    owners = slw.build_model_owner_map()
    assert owners == {"SharedModel": "only_app"}


_OWNERS = {"GitHubRepository": "github_activity_tracker"}


def test_scan_detects_queryset_delete_via_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(slw, "REPO_ROOT", tmp_path)
    src = tmp_path / "boost_usage_tracker" / "cmd.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "def f():\n"
        "    qs = GitHubRepository.objects.filter(pk=1)\n"
        "    qs.delete()\n",
        encoding="utf-8",
    )
    violations = slw.scan_file(src, _OWNERS)
    assert len(violations) == 1
    assert violations[0].kind == "queryset.delete"
    assert violations[0].model == "GitHubRepository"
    assert violations[0].owner_app == "github_activity_tracker"
    assert violations[0].file_app == "boost_usage_tracker"


def test_scan_detects_instance_save_via_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(slw, "REPO_ROOT", tmp_path)
    src = tmp_path / "boost_usage_tracker" / "cmd.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "def f():\n"
        "    repo = GitHubRepository.objects.get(pk=1)\n"
        "    repo.save()\n",
        encoding="utf-8",
    )
    violations = slw.scan_file(src, _OWNERS)
    assert len(violations) == 1
    assert violations[0].kind == "instance.save"
    assert violations[0].model == "GitHubRepository"
