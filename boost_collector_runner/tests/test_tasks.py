"""Tests for Celery tasks in boost_collector_runner."""

from unittest.mock import patch

import pytest

from boost_collector_runner.tasks import run_scheduled_collectors_task


@patch("boost_collector_runner.tasks.call_command")
def test_run_scheduled_collectors_task_invokes_management_command(mock_call):
    run_scheduled_collectors_task.run("daily")
    mock_call.assert_called_once_with("run_scheduled_collectors", "--schedule", "daily")


@patch("boost_collector_runner.tasks.call_command")
def test_run_scheduled_collectors_task_passes_strict(mock_call):
    run_scheduled_collectors_task.run("daily", strict=True)
    mock_call.assert_called_once_with(
        "run_scheduled_collectors",
        "--schedule",
        "daily",
        "--strict",
    )


@patch("boost_collector_runner.tasks.call_command")
def test_run_scheduled_collectors_task_passes_all_cli_flags(mock_call):
    run_scheduled_collectors_task.run(
        "weekly",
        day_of_week="monday",
        day_of_month=None,
        interval_minutes=None,
        group_id="github",
        stop_on_failure=True,
    )
    mock_call.assert_called_once_with(
        "run_scheduled_collectors",
        "--schedule",
        "weekly",
        "--group",
        "github",
        "--day-of-week",
        "monday",
        "--stop-on-failure",
    )


@patch("boost_collector_runner.tasks.call_command")
def test_run_scheduled_collectors_task_monthly_and_interval(mock_call):
    run_scheduled_collectors_task.run(
        "monthly",
        day_of_month=15,
        group_id=None,
    )
    mock_call.assert_called_once_with(
        "run_scheduled_collectors",
        "--schedule",
        "monthly",
        "--day-of-month",
        "15",
    )
    mock_call.reset_mock()
    run_scheduled_collectors_task.run("interval", interval_minutes=30)
    mock_call.assert_called_once_with(
        "run_scheduled_collectors",
        "--schedule",
        "interval",
        "--interval-minutes",
        "30",
    )


@patch("boost_collector_runner.tasks.call_command", side_effect=SystemExit(0))
def test_run_scheduled_collectors_task_system_exit_zero_success(mock_call):
    run_scheduled_collectors_task.run("daily")


@patch("boost_collector_runner.tasks.call_command", side_effect=SystemExit(None))
def test_run_scheduled_collectors_task_system_exit_none_is_success(mock_call):
    run_scheduled_collectors_task.run("daily")


@patch("boost_collector_runner.tasks.call_command", side_effect=SystemExit(2))
def test_run_scheduled_collectors_task_system_exit_nonzero_raises(mock_call):
    with pytest.raises(RuntimeError, match="exited with code 2"):
        run_scheduled_collectors_task.run("daily")


@patch(
    "boost_collector_runner.tasks.call_command",
    side_effect=SystemExit([2]),
)
def test_run_scheduled_collectors_task_system_exit_non_int_code(mock_call):
    with pytest.raises(RuntimeError, match="exited with code 1"):
        run_scheduled_collectors_task.run("daily")


@patch("boost_collector_runner.tasks.call_command", side_effect=ValueError("boom"))
def test_run_scheduled_collectors_task_propagates_exceptions(mock_call):
    with pytest.raises(ValueError, match="boom"):
        run_scheduled_collectors_task.run("daily")
