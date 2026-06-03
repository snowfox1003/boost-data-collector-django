"""Runtime checks for :mod:`core.protocols` and ``core/pyright_samples`` Pyright snippets."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.activity_types import (
    ActivityType,
    SourceSystem,
    actor_external_id,
    parse_activity_occurred_at,
)
from core.protocols import (
    ActivityRecord,
    IncrementalState,
    TrackerResult,
    require_activity_record,
    require_tracker_result,
)
from discord_activity_tracker.protocol_impl import (
    DiscordActivityRecord,
    DiscordCollectionTrackerResult,
)
from github_activity_tracker.protocol_impl import (
    GitHubActivityRecord,
    GitHubIncrementalState,
    GitHubSyncTrackerResult,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TYPING_DIR = _REPO_ROOT / "core" / "pyright_samples"


def test_tracker_result_isinstance_github_dataclass() -> None:
    r = GitHubSyncTrackerResult(success=True, counts={"issues": 2, "pull_requests": 1})
    assert isinstance(r, TrackerResult)
    assert r.counts["issues"] == 2


def test_activity_record_isinstance_discord_dataclass() -> None:
    rec = DiscordActivityRecord(
        source_system=SourceSystem.DISCORD,
        external_id="1:2:3",
        occurred_at=parse_activity_occurred_at("2024-01-01T00:00:00Z"),
        activity_type=ActivityType.discord_message("Default"),
        actor_external_id=actor_external_id("99"),
        source_url="https://discord.com/channels/1/2/3",
        summary="hi",
    )
    assert isinstance(rec, ActivityRecord)


def test_incremental_state_isinstance_github() -> None:
    st = GitHubIncrementalState.from_repo_watermark(repo_id=42, marker="2024-06")
    assert isinstance(st, IncrementalState)


def test_activity_record_isinstance_github_from_issue() -> None:
    rec = GitHubActivityRecord.from_issue(repo_id=7, issue_number=123, summary="title")
    assert isinstance(rec, ActivityRecord)
    assert "7:issue:123" in rec.external_id


def test_tracker_result_isinstance_discord_dataclass() -> None:
    r = DiscordCollectionTrackerResult(
        success=True, counts={"messages": 5, "channels": 1}
    )
    assert isinstance(r, TrackerResult)


def test_require_tracker_result_raises_type_error_on_bad_object() -> None:
    class NotAResult:
        success = True
        # missing counts

    with pytest.raises(TypeError, match="TrackerResult"):
        require_tracker_result(NotAResult())


def test_require_activity_record_raises_type_error_on_bad_object() -> None:
    class NotARecord:
        source_system = "x"
        # missing fields

    with pytest.raises(TypeError, match="ActivityRecord"):
        require_activity_record(NotARecord())


def test_pyright_positive_protocol_assignment_file() -> None:
    path = _TYPING_DIR / "protocol_assignment_positive.py"
    proc = subprocess.run(
        [sys.executable, "-m", "pyright", str(path)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 and "No module named pyright" in (proc.stderr or ""):
        pytest.skip("pyright not installed (pip install -r requirements-dev.lock)")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_pyright_negative_activity_record_assignment_file(tmp_path: Path) -> None:
    src = _TYPING_DIR / "activity_record_assignment_negative.py"
    dest = tmp_path / "activity_record_assignment_negative.py"
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    cfg_path = tmp_path / "pyrightconfig.json"
    cfg_path.write_text(
        json.dumps(
            {
                "include": ["activity_record_assignment_negative.py"],
                "exclude": [],
                "pythonVersion": "3.13",
                "typeCheckingMode": "basic",
                "reportMissingImports": True,
                "executionEnvironments": [
                    {
                        "root": str(tmp_path.resolve()),
                        "extraPaths": [str(_REPO_ROOT.resolve())],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, "-m", "pyright", "--project", str(tmp_path)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    stderr = proc.stderr or ""
    if "No module named pyright" in stderr:
        pytest.skip("pyright not installed (pip install -r requirements-dev.lock)")
    assert proc.returncode != 0, (
        "expected pyright errors for activity_record_assignment_negative.py; "
        f"stdout={proc.stdout!r} stderr={stderr!r}"
    )


def test_pyright_negative_protocol_assignment_file(tmp_path: Path) -> None:
    """Run Pyright in an isolated project so root ``pyrightconfig`` excludes do not skip the file."""
    src = _TYPING_DIR / "protocol_assignment_negative.py"
    dest = tmp_path / "protocol_assignment_negative.py"
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    cfg_path = tmp_path / "pyrightconfig.json"
    cfg_path.write_text(
        json.dumps(
            {
                "include": ["protocol_assignment_negative.py"],
                "exclude": [],
                "pythonVersion": "3.11",
                "typeCheckingMode": "basic",
                "reportMissingImports": True,
                "stubPath": "",
                "executionEnvironments": [
                    {
                        "root": str(tmp_path.resolve()),
                        "extraPaths": [str(_REPO_ROOT.resolve())],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, "-m", "pyright", "--project", str(tmp_path)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    stderr = proc.stderr or ""
    stdout = proc.stdout or ""
    if "No module named pyright" in stderr:
        pytest.skip("pyright not installed (pip install -r requirements-dev.lock)")
    assert proc.returncode != 0, (
        "expected pyright errors for protocol_assignment_negative.py; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
