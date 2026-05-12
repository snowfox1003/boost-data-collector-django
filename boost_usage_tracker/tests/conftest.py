"""Fixtures for boost_usage_tracker tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _patch_github_token_validation_for_usage_command():
    """test_settings leaves GitHub tokens empty; avoid real GET /user during commands."""
    cmd = "boost_usage_tracker.management.commands.run_boost_usage_tracker"
    with patch(f"{cmd}.validate_github_token_for_use"):
        yield
