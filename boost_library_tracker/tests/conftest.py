"""Fixtures for boost_library_tracker tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _patch_github_token_validation_for_github_activity_command():
    """test_settings leaves GitHub tokens empty; avoid real GET /user during commands."""
    cmd = "boost_library_tracker.management.commands.run_boost_github_activity_tracker"
    with patch(f"{cmd}.validate_github_token_for_use"):
        yield
