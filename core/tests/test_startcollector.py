"""Tests for startcollector management command."""

from __future__ import annotations

import ast
import shutil
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.apps import apps as django_apps
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError

from core.management.collector_registry import (
    append_cross_app_inventory_row,
    append_importlinter_root_package,
    append_schedule_entry,
    insert_installed_app,
    register_collector_project_files,
)


_SETTINGS_FIXTURE = """\
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "core",
    "boost_collector_runner",
    "github_activity_tracker",
    "wg21_paper_tracker",
]
"""

_IMPORTLINTER_FIXTURE = """\
[importlinter]
root_packages =
    github_activity_tracker
    wg21_paper_tracker

[importlinter:contract:example]
name = example
"""

_CROSS_APP_FIXTURE = """\
| App | Role | Has models? |
| --- | --- | --- |
| `github_activity_tracker` | GitHub repos | Yes |
| `wg21_paper_tracker` | WG21 paper tracking | Yes |
"""

_SCHEDULE_FIXTURE = "groups:\n  github:\n    tasks: []\n"


def _write_fake_repo_root(root: Path) -> None:
    (root / "config").mkdir(parents=True)
    (root / "config" / "settings.py").write_text(_SETTINGS_FIXTURE, encoding="utf-8")
    (root / "config" / "boost_collector_schedule.yaml").write_text(
        _SCHEDULE_FIXTURE, encoding="utf-8"
    )
    (root / ".importlinter").write_text(_IMPORTLINTER_FIXTURE, encoding="utf-8")
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "cross-app-dependencies.md").write_text(
        _CROSS_APP_FIXTURE, encoding="utf-8"
    )


def _installed_apps_block(content: str) -> str:
    marker = "INSTALLED_APPS = ["
    start = content.find(marker)
    open_bracket = start + len(marker) - 1
    close_bracket = content.find("]", open_bracket)
    return content[open_bracket : close_bracket + 1]


def _project_app_entries(block: str) -> list[str]:
    return [
        line.strip()
        for line in block.splitlines()
        if line.strip().startswith('"')
        and not line.strip().startswith('"django.contrib')
    ]


def _assert_installed_app_in_settings(
    content: str,
    app_label: str,
    *,
    last_among_project_apps: bool = False,
) -> None:
    ast.parse(content)
    block = _installed_apps_block(content)
    quoted = f'"{app_label}"'
    assert quoted in block
    assert block.index(quoted) < block.rindex("]")
    assert block.rstrip().endswith("]")
    if last_among_project_apps:
        assert _project_app_entries(block)[-1] == f'"{app_label}",'


def test_insert_installed_app_alphabetically() -> None:
    updated = insert_installed_app(_SETTINGS_FIXTURE, "reddit_activity_tracker")
    block = _installed_apps_block(updated)
    assert _project_app_entries(block) == [
        '"core",',
        '"boost_collector_runner",',
        '"github_activity_tracker",',
        '"reddit_activity_tracker",',
        '"wg21_paper_tracker",',
    ]
    _assert_installed_app_in_settings(updated, "reddit_activity_tracker")


def test_insert_installed_app_inserts_before_closing_bracket() -> None:
    """App labels that sort after all project apps must stay inside INSTALLED_APPS."""
    updated = insert_installed_app(_SETTINGS_FIXTURE, "zz_last_app")
    _assert_installed_app_in_settings(
        updated, "zz_last_app", last_among_project_apps=True
    )


def test_insert_installed_app_idempotent() -> None:
    once = insert_installed_app(_SETTINGS_FIXTURE, "reddit_activity_tracker")
    twice = insert_installed_app(once, "reddit_activity_tracker")
    assert once == twice


def test_append_schedule_entry_commented_block() -> None:
    updated = append_schedule_entry(_SCHEDULE_FIXTURE, "my_platform")
    assert "startcollector: my_platform" in updated
    assert "#       - command: run_my_platform" in updated
    assert "#         enabled: false" in updated


def test_append_importlinter_root_package_alphabetical() -> None:
    updated = append_importlinter_root_package(
        _IMPORTLINTER_FIXTURE, "reddit_activity_tracker"
    )
    packages = [
        line.strip()
        for line in updated.splitlines()
        if line.startswith("    ") and not line.strip().startswith("[")
    ]
    assert packages == [
        "github_activity_tracker",
        "reddit_activity_tracker",
        "wg21_paper_tracker",
    ]


def test_append_cross_app_inventory_row() -> None:
    updated = append_cross_app_inventory_row(
        _CROSS_APP_FIXTURE, "reddit_activity_tracker"
    )
    assert (
        "| `reddit_activity_tracker` | Collector stub (customize role) | Yes |"
        in updated
    )
    idx_github = updated.index("`github_activity_tracker`")
    idx_reddit = updated.index("`reddit_activity_tracker`")
    idx_wg21 = updated.index("`wg21_paper_tracker`")
    assert idx_github < idx_reddit < idx_wg21


def test_register_collector_project_files_dry_run(tmp_path: Path) -> None:
    _write_fake_repo_root(tmp_path)
    lines = register_collector_project_files(tmp_path, "zzregistrydemo", dry_run=True)
    assert any("Would update config/settings.py" in line for line in lines)
    assert '"zzregistrydemo"' not in (tmp_path / "config" / "settings.py").read_text(
        encoding="utf-8"
    )


def test_register_collector_project_files_aborts_before_writes_if_target_missing(
    tmp_path: Path,
) -> None:
    _write_fake_repo_root(tmp_path)
    (tmp_path / "docs" / "cross-app-dependencies.md").unlink()
    settings_before = (tmp_path / "config" / "settings.py").read_text(encoding="utf-8")
    with pytest.raises(CommandError, match="aborted before any edits"):
        register_collector_project_files(tmp_path, "zzregistrydemo", dry_run=False)
    assert (tmp_path / "config" / "settings.py").read_text(
        encoding="utf-8"
    ) == settings_before


def test_register_collector_project_files_apply_error_is_command_error(
    tmp_path: Path,
) -> None:
    _write_fake_repo_root(tmp_path)
    (tmp_path / "config" / "settings.py").write_text(
        "# no INSTALLED_APPS block\n",
        encoding="utf-8",
    )
    with pytest.raises(CommandError, match=r"Failed to update config/settings\.py"):
        register_collector_project_files(tmp_path, "zzregistrydemo", dry_run=False)


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


def test_startcollector_does_not_register_when_path_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    label = "zzisolatedcollect"
    with patch(
        "core.management.commands.startcollector.register_collector_project_files"
    ) as mock_register:
        call_command("startcollector", label, "--path", str(tmp_path))
        mock_register.assert_not_called()
    shutil.rmtree(tmp_path / label)


def test_startcollector_dry_run_previews_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_fake_repo_root(tmp_path)
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)
    label = "zzdryregcollect"
    out = StringIO()
    call_command(
        "startcollector",
        label,
        "--path",
        str(tmp_path),
        "--dry-run",
        stdout=out,
    )
    text = out.getvalue()
    assert "project registration (preview)" in text
    assert "Would update config/settings.py" in text
    assert "migrations/0001_initial.py" in text
    assert not (tmp_path / label).exists()


def test_startcollector_registers_at_repo_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_fake_repo_root(tmp_path)
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)
    label = "zzrootregcollect"
    call_command("startcollector", label, "--path", str(tmp_path))

    settings_text = (tmp_path / "config" / "settings.py").read_text(encoding="utf-8")
    schedule_text = (tmp_path / "config" / "boost_collector_schedule.yaml").read_text(
        encoding="utf-8"
    )
    importlinter_text = (tmp_path / ".importlinter").read_text(encoding="utf-8")
    cross_app_text = (tmp_path / "docs" / "cross-app-dependencies.md").read_text(
        encoding="utf-8"
    )

    # zzrootregcollect sorts after every fixture app — exercises last-slot insertion.
    _assert_installed_app_in_settings(
        settings_text, label, last_among_project_apps=True
    )
    assert f"startcollector: {label}" in schedule_text
    assert label in importlinter_text
    assert f"| `{label}` |" in cross_app_text
    assert (tmp_path / label / "migrations" / "0001_initial.py").is_file()
    shutil.rmtree(tmp_path / label)
