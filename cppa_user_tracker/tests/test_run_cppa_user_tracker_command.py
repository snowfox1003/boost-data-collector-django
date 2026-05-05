"""Tests for run_cppa_user_tracker management command."""

from io import StringIO

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_run_cppa_user_tracker_stub_writes_success():
    out = StringIO()
    call_command("run_cppa_user_tracker", stdout=out, verbosity=0)
    assert "completed" in out.getvalue().lower()
