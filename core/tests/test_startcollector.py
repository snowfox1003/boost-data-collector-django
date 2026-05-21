"""Tests for startcollector management command."""

from __future__ import annotations

import shutil
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from django.apps import apps as django_apps
from django.core.management import call_command
from django.core.management.base import CommandError


def test_startcollector_dry_run_does_not_create_app(tmp_path: Path) -> None:
    out = StringIO()
    label = "zzdryruncollect"
    call_command(
        "startcollector",
        label,
        "--path",
        str(tmp_path),
        "--dry-run",
        stdout=out,
    )
    assert not (tmp_path / label).exists()


def test_startcollector_rejects_invalid_label(tmp_path: Path) -> None:
    with pytest.raises(CommandError, match="app_label"):
        call_command("startcollector", "BadName", "--path", str(tmp_path))
    with pytest.raises(CommandError, match="reserved"):
        call_command("startcollector", "django", "--path", str(tmp_path))


def test_startcollector_rejects_installed_app_name(tmp_path: Path) -> None:
    with pytest.raises(CommandError, match="INSTALLED_APPS"):
        call_command(
            "startcollector",
            "github_activity_tracker",
            "--path",
            str(tmp_path),
        )


def test_startcollector_rejects_dotted_installed_app_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_config = MagicMock()
    mock_config.label = "github_activity_tracker"
    monkeypatch.setattr(django_apps, "get_app_configs", lambda: [mock_config])
    with pytest.raises(CommandError, match="INSTALLED_APPS"):
        call_command(
            "startcollector",
            "github_activity_tracker",
            "--path",
            str(tmp_path),
        )


def test_startcollector_creates_expected_layout(tmp_path: Path) -> None:
    label = "zzlayoutcollect"
    call_command("startcollector", label, "--path", str(tmp_path))
    app_dir = tmp_path / label
    assert (app_dir / "models.py").exists()
    assert (app_dir / "services.py").exists()
    assert (app_dir / "schedule_snippet.yaml").exists()
    assert (app_dir / "migrations" / "0001_initial.py").exists()
    cmd_file = app_dir / "management" / "commands" / f"run_{label}.py"
    text = cmd_file.read_text(encoding="utf-8")
    assert "AbstractCollector" in text
    assert "BaseCollectorCommand" in text
    assert "CollectorBase" not in text
    assert (app_dir / "tests" / f"test_run_{label}_command.py").exists()
    assert not (app_dir / "tests.py").exists()
    shutil.rmtree(app_dir)


def test_startcollector_apps_py_default_auto_field(tmp_path: Path) -> None:
    label = "zzappscfgcollect"
    call_command("startcollector", label, "--path", str(tmp_path))
    apps_py = (tmp_path / label / "apps.py").read_text(encoding="utf-8")
    assert 'default_auto_field = "django.db.models.BigAutoField"' in apps_py
    assert f'name = "{label}"' in apps_py
    shutil.rmtree(tmp_path / label)


def test_startcollector_rejects_existing_path(tmp_path: Path) -> None:
    label = "zzexistsblock"
    (tmp_path / label).mkdir()
    with pytest.raises(CommandError, match="already exists|Path already exists"):
        call_command("startcollector", label, "--path", str(tmp_path))
    shutil.rmtree(tmp_path / label)
