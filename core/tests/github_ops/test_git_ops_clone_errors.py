"""Tests for clone_repo error paths (timeout / failure) with redacted exceptions."""

import subprocess
from unittest.mock import patch

import pytest

from core.operations.github_ops import git_ops


@pytest.fixture
def fake_token():
    return "ghp_super_secret_do_not_leak"


@patch("core.operations.github_ops.git_ops.get_github_token", return_value="tok")
@patch("core.operations.github_ops.git_ops.subprocess.run")
def test_clone_repo_timeout_reraises_with_redacted_cmd(
    mock_run, _mock_token, tmp_path, fake_token
):
    dest = tmp_path / "dest"
    mock_run.side_effect = subprocess.TimeoutExpired(
        cmd=[
            "git",
            "clone",
            f"https://x-access-token:{fake_token}@github.com/o/r.git",
            str(dest),
        ],
        timeout=1,
        output="out",
        stderr="err",
    )
    with pytest.raises(subprocess.TimeoutExpired) as ei:
        git_ops.clone_repo("https://github.com/o/r.git", dest, token=fake_token)
    cmd_joined = " ".join(map(str, ei.value.cmd))
    assert fake_token not in cmd_joined
    assert "https://github.com/o/r.git" in ei.value.cmd[2]


@patch("core.operations.github_ops.git_ops.get_github_token", return_value="tok")
@patch("core.operations.github_ops.git_ops.subprocess.run")
def test_clone_repo_called_process_error_reraises_sanitized_stderr(
    mock_run, _mock_token, tmp_path, fake_token
):
    dest = tmp_path / "dest2"
    mock_run.side_effect = subprocess.CalledProcessError(
        1,
        [
            "git",
            "clone",
            f"https://x-access-token:{fake_token}@github.com/o/r.git",
            str(dest),
            "--depth",
            "1",
        ],
        output=None,
        stderr=(
            f"fatal: unable to access "
            f"'https://x-access-token:{fake_token}@github.com/o/r.git/': denied\n"
        ),
    )
    with pytest.raises(subprocess.CalledProcessError) as ei:
        git_ops.clone_repo("o/r", dest, token=fake_token, depth=1)
    cmd_joined = " ".join(map(str, ei.value.cmd))
    assert fake_token not in cmd_joined
    assert fake_token not in (ei.value.stderr or "")
    assert "--depth" in cmd_joined
