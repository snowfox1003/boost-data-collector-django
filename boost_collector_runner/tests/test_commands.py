"""Tests for boost_collector_runner management commands."""

import logging
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command, get_commands
from django.core.management.base import CommandError

from boost_collector_runner.schedule_config import DEFAULT_GROUP_BATCH_SCHEDULE_KIND
from core import __version__


@pytest.mark.django_db
def test_run_scheduled_collectors_command_exists():
    """run_scheduled_collectors is registered."""
    commands = get_commands()
    assert "run_scheduled_collectors" in commands


@pytest.mark.django_db
def test_run_scheduled_collectors_logs_version_at_startup(caplog, tmp_path, settings):
    """Startup log includes collector_version in message and structured extra."""
    import yaml

    yaml_path = tmp_path / "boost_collector_schedule.yaml"
    yaml_path.write_text(
        yaml.dump(
            {
                "groups": {
                    "github": {
                        "default_time": "04:10",
                        "tasks": [
                            {
                                "command": "run_boost_github_activity_tracker",
                                "schedule": "daily",
                            },
                        ],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    settings.BOOST_COLLECTOR_SCHEDULE_YAML = str(yaml_path)

    caplog.set_level(logging.INFO)
    out = StringIO()
    err = StringIO()
    with (
        patch(
            "boost_collector_runner.schedule_config._get_yaml_path",
            return_value=yaml_path,
        ),
        patch(
            "boost_collector_runner.management.commands.run_scheduled_collectors.call_command",
            return_value=None,
        ),
    ):
        call_command(
            "run_scheduled_collectors",
            "--schedule",
            "daily",
            stdout=out,
            stderr=err,
        )

    startup = [
        r
        for r in caplog.records
        if "run_scheduled_collectors: starting collector_version=" in r.getMessage()
    ]
    assert startup, "expected startup version log line"
    assert startup[0].collector_version == __version__
    assert __version__ in startup[0].getMessage()


@pytest.mark.django_db
def test_run_scheduled_collectors_daily_runs_tasks_from_yaml(tmp_path, settings):
    """run_scheduled_collectors --schedule daily runs tasks returned by get_tasks_for_schedule."""
    import yaml

    yaml_path = tmp_path / "boost_collector_schedule.yaml"
    yaml_path.write_text(
        yaml.dump(
            {
                "groups": {
                    "github": {
                        "default_time": "04:10",
                        "tasks": [
                            {
                                "command": "run_boost_github_activity_tracker",
                                "schedule": "daily",
                            },
                        ],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    settings.BOOST_COLLECTOR_SCHEDULE_YAML = str(yaml_path)

    out = StringIO()
    err = StringIO()
    with (
        patch(
            "boost_collector_runner.schedule_config._get_yaml_path",
            return_value=yaml_path,
        ),
        patch(
            "boost_collector_runner.management.commands.run_scheduled_collectors.call_command",
            return_value=None,
        ) as mock_call,
    ):
        call_command(
            "run_scheduled_collectors",
            "--schedule",
            "daily",
            stdout=out,
            stderr=err,
        )
    # Command uses logger, not stdout; verify it ran the task from YAML
    assert mock_call.call_count == 1
    mock_call.assert_called_once_with("run_boost_github_activity_tracker")


@pytest.mark.django_db
def test_run_scheduled_collectors_default_group_batch(tmp_path, settings):
    """run_scheduled_collectors --schedule default --group X runs group batch (daily + weekly + monthly + on_release) for that group."""
    import yaml

    yaml_path = tmp_path / "boost_collector_schedule.yaml"
    yaml_path.write_text(
        yaml.dump(
            {
                "groups": {
                    "github": {
                        "default_time": "04:10",
                        "tasks": [
                            {"command": "run_foo", "schedule": "daily"},
                            {
                                "command": "run_bar",
                                "schedule": "weekly",
                                "on": "monday",
                            },
                        ],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    settings.BOOST_COLLECTOR_SCHEDULE_YAML = str(yaml_path)

    out = StringIO()
    err = StringIO()
    with (
        patch(
            "boost_collector_runner.schedule_config._get_yaml_path",
            return_value=yaml_path,
        ),
        patch(
            "boost_collector_runner.management.commands.run_scheduled_collectors.call_command",
            return_value=None,
        ) as mock_call,
    ):
        call_command(
            "run_scheduled_collectors",
            "--schedule",
            DEFAULT_GROUP_BATCH_SCHEDULE_KIND,
            "--group",
            "github",
            stdout=out,
            stderr=err,
        )
    # Command uses logger, not stdout; verify it ran the group batch tasks
    assert mock_call.call_count >= 1
    call_names = [c[0][0] for c in mock_call.call_args_list]
    assert "run_foo" in call_names or "run_bar" in call_names


@pytest.mark.django_db
def test_run_scheduled_collectors_requires_schedule():
    """run_scheduled_collectors without --schedule raises CommandError."""
    out = StringIO()
    err = StringIO()
    with pytest.raises(CommandError) as exc_info:
        call_command("run_scheduled_collectors", stdout=out, stderr=err)
    assert "schedule" in str(exc_info.value).lower()


@pytest.mark.django_db
def test_run_scheduled_collectors_default_requires_group():
    with pytest.raises(CommandError, match="default requires --group"):
        call_command(
            "run_scheduled_collectors",
            "--schedule",
            "default",
        )


@pytest.mark.django_db
def test_run_scheduled_collectors_weekly_requires_day_of_week():
    with pytest.raises(CommandError, match="weekly requires --day-of-week"):
        call_command(
            "run_scheduled_collectors",
            "--schedule",
            "weekly",
        )


@pytest.mark.django_db
def test_run_scheduled_collectors_monthly_requires_day_of_month():
    with pytest.raises(CommandError, match="monthly requires --day-of-month"):
        call_command(
            "run_scheduled_collectors",
            "--schedule",
            "monthly",
        )


@pytest.mark.django_db
def test_run_scheduled_collectors_interval_requires_minutes():
    with pytest.raises(CommandError, match="interval requires --interval-minutes"):
        call_command(
            "run_scheduled_collectors",
            "--schedule",
            "interval",
        )


@pytest.mark.django_db
def test_run_scheduled_collectors_wraps_schedule_resolution_error(tmp_path, settings):
    yaml_path = tmp_path / "boost_collector_schedule.yaml"
    yaml_path.write_text("groups: {}\n", encoding="utf-8")
    settings.BOOST_COLLECTOR_SCHEDULE_YAML = str(yaml_path)
    with patch(
        "boost_collector_runner.management.commands.run_scheduled_collectors.get_tasks_for_schedule",
        side_effect=ValueError("bad yaml"),
    ):
        with pytest.raises(CommandError, match="bad yaml"):
            call_command(
                "run_scheduled_collectors",
                "--schedule",
                "daily",
            )


@pytest.mark.django_db
def test_run_scheduled_collectors_no_tasks_returns_zero(tmp_path, settings):
    import yaml

    yaml_path = tmp_path / "boost_collector_schedule.yaml"
    yaml_path.write_text(
        yaml.dump({"groups": {"empty": {"tasks": []}}}),
        encoding="utf-8",
    )
    settings.BOOST_COLLECTOR_SCHEDULE_YAML = str(yaml_path)
    with (
        patch(
            "boost_collector_runner.schedule_config._get_yaml_path",
            return_value=yaml_path,
        ),
        patch(
            "boost_collector_runner.management.commands.run_scheduled_collectors.get_tasks_for_schedule",
            return_value=[],
        ),
    ):
        call_command(
            "run_scheduled_collectors",
            "--schedule",
            "daily",
            "--group",
            "empty",
        )


@pytest.mark.django_db
def test_run_scheduled_collectors_child_system_exit_nonzero(tmp_path, settings):
    yaml_path = tmp_path / "boost_collector_schedule.yaml"
    yaml_path.write_text("groups: {}\n", encoding="utf-8")
    settings.BOOST_COLLECTOR_SCHEDULE_YAML = str(yaml_path)
    fake_tasks = [
        ("g", {"command": "run_foo", "schedule": "daily"}),
    ]
    with (
        patch(
            "boost_collector_runner.schedule_config._get_yaml_path",
            return_value=yaml_path,
        ),
        patch(
            "boost_collector_runner.management.commands.run_scheduled_collectors.get_tasks_for_schedule",
            return_value=fake_tasks,
        ),
        patch(
            "boost_collector_runner.management.commands.run_scheduled_collectors.call_command",
            side_effect=SystemExit(5),
        ),
    ):
        with pytest.raises(SystemExit) as ei:
            call_command(
                "run_scheduled_collectors",
                "--schedule",
                "daily",
                "--group",
                "g",
            )
        assert ei.value.code == 5


@pytest.mark.django_db
def test_run_scheduled_collectors_stop_on_failure_short_circuits(
    tmp_path, settings, caplog
):
    yaml_path = tmp_path / "boost_collector_schedule.yaml"
    yaml_path.write_text("groups: {}\n", encoding="utf-8")
    settings.BOOST_COLLECTOR_SCHEDULE_YAML = str(yaml_path)
    fake_tasks = [
        ("g", {"command": "run_a", "schedule": "daily"}),
        ("g", {"command": "run_b", "schedule": "daily"}),
    ]

    def fail_first(name, *args, **kwargs):
        if name == "run_a":
            raise SystemExit(1)
        return None

    caplog.set_level(logging.WARNING)
    with (
        patch(
            "boost_collector_runner.schedule_config._get_yaml_path",
            return_value=yaml_path,
        ),
        patch(
            "boost_collector_runner.management.commands.run_scheduled_collectors.get_tasks_for_schedule",
            return_value=fake_tasks,
        ),
        patch(
            "boost_collector_runner.management.commands.run_scheduled_collectors.call_command",
            side_effect=fail_first,
        ) as mock_inner,
    ):
        with pytest.raises(SystemExit) as ei:
            call_command(
                "run_scheduled_collectors",
                "--schedule",
                "daily",
                "--group",
                "g",
                "--stop-on-failure",
            )
        assert ei.value.code == 1
    assert mock_inner.call_count == 1
    skip_msgs = [r for r in caplog.records if "Skipping collector" in r.getMessage()]
    assert (
        skip_msgs
    ), "expected skip warning for collectors not run after stop-on-failure"
    assert any("run_b" in r.getMessage() for r in skip_msgs)
    assert any("run_a" in r.getMessage() for r in skip_msgs)


@pytest.mark.django_db
def test_run_scheduled_collectors_skipped_on_release_does_not_record_success(
    tmp_path, settings
):
    """When all tasks are skipped (e.g. on_release with no new release), do not record group success."""

    yaml_path = tmp_path / "boost_collector_schedule.yaml"
    yaml_path.write_text("groups: {}\n", encoding="utf-8")
    settings.BOOST_COLLECTOR_SCHEDULE_YAML = str(yaml_path)
    fake_tasks = [
        ("boost", {"command": "run_boost_release", "schedule": "on_release"}),
    ]
    with (
        patch(
            "boost_collector_runner.schedule_config._get_yaml_path",
            return_value=yaml_path,
        ),
        patch(
            "boost_collector_runner.management.commands.run_scheduled_collectors.get_tasks_for_schedule",
            return_value=fake_tasks,
        ),
        patch(
            "boost_library_tracker.release_check.has_new_boost_release",
            return_value=False,
        ),
        patch(
            "boost_collector_runner.management.commands.run_scheduled_collectors.call_command",
        ) as mock_call,
        patch(
            "boost_collector_runner.management.commands.run_scheduled_collectors.collector_services.record_group_success",
        ) as mock_success,
        patch(
            "boost_collector_runner.management.commands.run_scheduled_collectors.collector_services.record_group_failure",
        ) as mock_failure,
    ):
        call_command(
            "run_scheduled_collectors",
            "--schedule",
            "on_release",
            "--group",
            "boost",
        )
    mock_call.assert_not_called()
    mock_success.assert_not_called()
    mock_failure.assert_not_called()


@pytest.mark.django_db
def test_run_scheduled_collectors_strict_missing_yaml_raises(tmp_path, settings):
    missing = tmp_path / "missing.yaml"
    settings.BOOST_COLLECTOR_SCHEDULE_YAML = str(missing)
    with patch(
        "boost_collector_runner.schedule_config._get_yaml_path", return_value=missing
    ):
        with pytest.raises(CommandError, match="Schedule YAML"):
            call_command(
                "run_scheduled_collectors",
                "--schedule",
                "daily",
                "--strict",
            )
