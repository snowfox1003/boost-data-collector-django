"""Tests for boost_collector_runner.schedule_config: load_config, validation, get_tasks_for_schedule, get_beat_schedule."""

import calendar
import logging
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from django.core.management import get_commands

from boost_collector_runner.schedule_config import (
    DEFAULT_GROUP_BATCH_SCHEDULE_KIND,
    INTERVAL_MINUTES_MAX,
    ScheduleConfigurationError,
    ensure_schedule_yaml_loaded,
    get_beat_schedule,
    get_groups_and_tasks,
    get_tasks_for_schedule,
    is_schedule_strict,
    iter_beat_schedule_entry_keys,
    load_config,
    resolve_schedule_yaml_path,
    _parse_time,
    _validate_task,
)


# --- resolve_schedule_yaml_path ---


def test_resolve_schedule_yaml_path_default(tmp_path):
    assert (
        resolve_schedule_yaml_path(base_dir=tmp_path)
        == (tmp_path / "config" / "boost_collector_schedule.yaml").resolve()
    )


def test_resolve_schedule_yaml_path_from_env_relative(tmp_path):
    path = resolve_schedule_yaml_path(
        base_dir=tmp_path,
        env_path="custom/schedule.yaml",
    )
    assert path == (tmp_path / "custom" / "schedule.yaml").resolve()


def test_resolve_schedule_yaml_path_from_env_absolute(tmp_path):
    custom = tmp_path / "abs" / "schedule.yaml"
    assert resolve_schedule_yaml_path(base_dir=tmp_path, env_path=str(custom)) == custom


# --- load_config validation ---


def test_load_config_requires_path():
    """load_config(path=None) raises ValueError."""
    with pytest.raises(ValueError, match="load_config requires a path"):
        load_config(None)


def test_load_config_file_not_found(tmp_path):
    """load_config with non-existent path raises FileNotFoundError."""
    missing = tmp_path / "missing.yaml"
    with pytest.raises(FileNotFoundError, match="Schedule YAML not found"):
        load_config(missing)


def test_load_config_data_not_dict(tmp_path):
    """YAML that is not a dict (e.g. list or null) raises ValueError."""
    path = tmp_path / "config.yaml"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="Schedule YAML must be a dict with 'groups'"):
        load_config(path)

    path.write_text("null", encoding="utf-8")
    with pytest.raises(ValueError, match="Schedule YAML must be a dict with 'groups'"):
        load_config(path)


def test_load_config_groups_missing(tmp_path):
    """YAML without 'groups' key or with null groups raises ValueError."""
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump({"other": 1}), encoding="utf-8")
    with pytest.raises(ValueError, match="Schedule YAML must have 'groups' \\(dict\\)"):
        load_config(path)

    path.write_text(yaml.dump({"groups": None}), encoding="utf-8")
    with pytest.raises(ValueError, match="Schedule YAML must have 'groups' \\(dict\\)"):
        load_config(path)


def test_load_config_groups_not_dict(tmp_path):
    """YAML with groups as non-dict raises ValueError."""
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump({"groups": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="Schedule YAML must have 'groups' \\(dict\\)"):
        load_config(path)


def test_load_config_group_id_empty_string(tmp_path):
    """Group id that is empty string raises ValueError."""
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.dump(
            {
                "groups": {
                    "": {
                        "default_time": "04:10",
                        "tasks": [],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Group id must be a non-empty string"):
        load_config(path)


def test_load_config_group_id_whitespace_only(tmp_path):
    """Group id that is only whitespace raises ValueError."""
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.dump(
            {
                "groups": {
                    "   ": {
                        "default_time": "04:10",
                        "tasks": [],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Group id must be a non-empty string"):
        load_config(path)


def test_load_config_group_data_not_dict(tmp_path):
    """Group value that is not a dict raises ValueError."""
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.dump(
            {
                "groups": {
                    "github": "not a dict",
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Group 'github' must be a dict"):
        load_config(path)


def test_load_config_default_time_missing(tmp_path):
    """Group without default_time or with empty default_time raises ValueError."""
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.dump(
            {
                "groups": {
                    "github": {
                        "tasks": [],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must have 'default_time'"):
        load_config(path)

    path.write_text(
        yaml.dump(
            {
                "groups": {
                    "github": {
                        "default_time": "   ",
                        "tasks": [],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must have 'default_time'"):
        load_config(path)


def test_load_config_default_time_invalid(tmp_path):
    """Group with invalid default_time format raises ValueError."""
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.dump(
            {
                "groups": {
                    "github": {
                        "default_time": "25:00",
                        "tasks": [],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Invalid time"):
        load_config(path)

    path.write_text(
        yaml.dump(
            {
                "groups": {
                    "github": {
                        "default_time": "not-time",
                        "tasks": [],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Invalid time"):
        load_config(path)


def test_load_config_tasks_not_list(tmp_path):
    """Group with tasks not a list raises ValueError."""
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.dump(
            {
                "groups": {
                    "github": {
                        "default_time": "04:10",
                        "tasks": "not a list",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must have 'tasks' \\(list\\)"):
        load_config(path)


def test_load_config_valid_minimal(tmp_path):
    """Valid minimal YAML loads and returns data dict."""
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.dump(
            {
                "groups": {
                    "github": {
                        "default_time": "04:10",
                        "tasks": [
                            {"command": "run_foo", "schedule": "daily"},
                        ],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    data = load_config(path)
    assert data is not None
    assert "groups" in data
    assert "github" in data["groups"]
    assert data["groups"]["github"]["default_time"] == "04:10"


def test_load_config_invalid_task_fails(tmp_path):
    """Invalid task in YAML causes load_config to raise ValueError from _validate_task."""
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.dump(
            {
                "groups": {
                    "github": {
                        "default_time": "04:10",
                        "tasks": [
                            {"command": "run_foo", "schedule": "daily"},
                            {"command": "run_bar"},  # missing schedule
                        ],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="'schedule' must be one of"):
        load_config(path)


# --- _validate_task validation ---


def test_validate_task_not_dict():
    """Task that is not a dict raises ValueError."""
    with pytest.raises(ValueError, match="Task in group .* must be a dict"):
        _validate_task([], "g1")
    with pytest.raises(ValueError, match="Task in group .* must be a dict"):
        _validate_task("task", "g1")


def test_validate_task_command_missing():
    """Task without command or with empty command raises ValueError."""
    with pytest.raises(ValueError, match=r"must have 'command' \(non-empty string\)"):
        _validate_task({"schedule": "daily"}, "g1")
    with pytest.raises(ValueError, match=r"must have 'command' \(non-empty string\)"):
        _validate_task({"command": "", "schedule": "daily"}, "g1")
    with pytest.raises(ValueError, match=r"must have 'command' \(non-empty string\)"):
        _validate_task({"command": 123, "schedule": "daily"}, "g1")


def test_validate_task_schedule_invalid():
    """Task with missing or invalid schedule raises ValueError."""
    with pytest.raises(ValueError, match="'schedule' must be one of"):
        _validate_task({"command": "c1", "schedule": "invalid"}, "g1")
    with pytest.raises(ValueError, match="'schedule' must be one of"):
        _validate_task({"command": "c1"}, "g1")


def test_validate_task_weekly_requires_on():
    """Task with schedule weekly but no valid on/day_of_week raises ValueError."""
    with pytest.raises(ValueError, match="'schedule: weekly' requires 'on'"):
        _validate_task({"command": "c1", "schedule": "weekly"}, "g1")
    with pytest.raises(ValueError, match="'schedule: weekly' requires 'on'"):
        _validate_task({"command": "c1", "schedule": "weekly", "on": "notaday"}, "g1")


def test_validate_task_weekly_valid():
    """Task with schedule weekly and valid on passes."""
    _validate_task({"command": "c1", "schedule": "weekly", "on": "monday"}, "g1")
    _validate_task({"command": "c1", "schedule": "weekly", "on": "mon"}, "g1")


def test_validate_task_monthly_requires_on():
    """Task with schedule monthly but no on raises ValueError."""
    with pytest.raises(ValueError, match="'schedule: monthly' requires 'on'"):
        _validate_task({"command": "c1", "schedule": "monthly"}, "g1")


def test_validate_task_monthly_on_non_numeric():
    """Task with schedule monthly and on not convertible to int raises ValueError."""
    with pytest.raises(ValueError, match="'schedule: monthly' requires 'on' \\(1-31"):
        _validate_task({"command": "c1", "schedule": "monthly", "on": "abc"}, "g1")


def test_validate_task_monthly_on_out_of_range():
    """Task with schedule monthly and on outside 1-31 raises ValueError."""
    with pytest.raises(ValueError, match="'schedule: monthly' requires 'on' \\(1-31"):
        _validate_task({"command": "c1", "schedule": "monthly", "on": 0}, "g1")
    with pytest.raises(ValueError, match="'schedule: monthly' requires 'on' \\(1-31"):
        _validate_task({"command": "c1", "schedule": "monthly", "on": 32}, "g1")


def test_validate_task_monthly_valid():
    """Task with schedule monthly and valid on (1-31) passes."""
    _validate_task({"command": "c1", "schedule": "monthly", "on": 1}, "g1")
    _validate_task({"command": "c1", "schedule": "monthly", "on": "15"}, "g1")
    _validate_task({"command": "c1", "schedule": "monthly", "on": 31}, "g1")


def test_validate_task_interval_requires_minutes():
    """Task with schedule interval but no minutes raises ValueError."""
    with pytest.raises(ValueError, match="'schedule: interval' requires 'minutes'"):
        _validate_task({"command": "c1", "schedule": "interval"}, "g1")


def test_validate_task_interval_minutes_not_int():
    """Task with schedule interval and minutes not int raises ValueError."""
    with pytest.raises(ValueError, match="'minutes' must be an integer"):
        _validate_task({"command": "c1", "schedule": "interval", "minutes": "x"}, "g1")


def test_validate_task_interval_minutes_out_of_range():
    """Task with schedule interval and minutes outside 1-180 raises ValueError."""
    with pytest.raises(ValueError, match="'minutes' must be 1-180"):
        _validate_task({"command": "c1", "schedule": "interval", "minutes": 0}, "g1")
    with pytest.raises(ValueError, match="'minutes' must be 1-180"):
        _validate_task(
            {
                "command": "c1",
                "schedule": "interval",
                "minutes": INTERVAL_MINUTES_MAX + 1,
            },
            "g1",
        )


def test_validate_task_interval_valid():
    """Task with schedule interval and valid minutes passes."""
    _validate_task({"command": "c1", "schedule": "interval", "minutes": 1}, "g1")
    _validate_task({"command": "c1", "schedule": "interval", "minutes": 60}, "g1")
    _validate_task(
        {
            "command": "c1",
            "schedule": "interval",
            "minutes": INTERVAL_MINUTES_MAX,
        },
        "g1",
    )


def test_validate_task_enabled_not_bool():
    """Task with enabled not boolean raises ValueError."""
    with pytest.raises(ValueError, match="'enabled' must be boolean"):
        _validate_task(
            {"command": "c1", "schedule": "daily", "enabled": "yes"},
            "g1",
        )


def test_validate_task_args_not_list():
    """Task with args not a list raises ValueError."""
    with pytest.raises(ValueError, match="'args' must be a list of strings"):
        _validate_task(
            {"command": "c1", "schedule": "daily", "args": "not-a-list"},
            "g1",
        )


def test_validate_task_args_element_not_string():
    """Task with args containing non-string element raises ValueError."""
    with pytest.raises(ValueError, match=r"'args\[0\]' must be a string"):
        _validate_task(
            {"command": "c1", "schedule": "daily", "args": [123]},
            "g1",
        )
    with pytest.raises(ValueError, match=r"'args\[1\]' must be a string"):
        _validate_task(
            {"command": "c1", "schedule": "daily", "args": ["--ok", None]},
            "g1",
        )


def test_validate_task_args_valid():
    """Task with args as list of strings passes."""
    _validate_task(
        {"command": "c1", "schedule": "daily", "args": ["--a", "b"]},
        "g1",
    )


def test_validate_task_daily_valid():
    """Minimal valid daily task passes."""
    _validate_task({"command": "c1", "schedule": "daily"}, "g1")


def test_validate_task_on_release_valid():
    """Minimal valid on_release task passes."""
    _validate_task({"command": "c1", "schedule": "on_release"}, "g1")


# --- get_tasks_for_schedule runtime ---


def test_get_tasks_for_schedule_monthly_exact_match_with_month_year(tmp_path):
    """get_tasks_for_schedule with month and year returns only tasks matching that day (exact or last-day fallback)."""
    path = tmp_path / "schedule.yaml"
    path.write_text(
        yaml.dump(
            {
                "groups": {
                    "g1": {
                        "default_time": "04:10",
                        "tasks": [
                            {
                                "command": "cmd_mid",
                                "schedule": "monthly",
                                "on": 15,
                            },
                            {
                                "command": "cmd_last",
                                "schedule": "monthly",
                                "on": 31,
                            },
                        ],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    data = load_config(path)
    # March 2024 has 31 days; day 15 is exact match
    tasks_15 = get_tasks_for_schedule(
        "monthly",
        day_of_month=15,
        month=3,
        year=2024,
        data=data,
    )
    assert len(tasks_15) == 1
    assert tasks_15[0][1]["command"] == "cmd_mid"
    # day 31 in March: both task 15 and 31 match (15 not, 31 yes)
    tasks_31 = get_tasks_for_schedule(
        "monthly",
        day_of_month=31,
        month=3,
        year=2024,
        data=data,
    )
    assert len(tasks_31) == 1
    assert tasks_31[0][1]["command"] == "cmd_last"
    # day 10: no monthly task on 10
    tasks_10 = get_tasks_for_schedule(
        "monthly",
        day_of_month=10,
        month=3,
        year=2024,
        data=data,
    )
    assert len(tasks_10) == 0


def test_get_tasks_for_schedule_monthly_last_day_fallback(tmp_path):
    """get_tasks_for_schedule with month/year returns task with day_of_month 31 on last day of February."""
    path = tmp_path / "schedule.yaml"
    path.write_text(
        yaml.dump(
            {
                "groups": {
                    "g1": {
                        "default_time": "04:10",
                        "tasks": [
                            {
                                "command": "month_end",
                                "schedule": "monthly",
                                "on": 31,
                            },
                        ],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    data = load_config(path)
    # Feb 2023 has 28 days; request day 28 with month/year -> effective_day = min(31, 28) = 28, task runs
    _, last_day = calendar.monthrange(2023, 2)
    assert last_day == 28
    tasks = get_tasks_for_schedule(
        "monthly",
        day_of_month=28,
        month=2,
        year=2023,
        data=data,
    )
    assert len(tasks) == 1
    assert tasks[0][1]["command"] == "month_end"
    assert tasks[0][1]["day_of_month"] == 31
    # Feb 2024 has 29 days; request day 29 -> effective_day = min(31, 29) = 29
    _, last_day_2024 = calendar.monthrange(2024, 2)
    assert last_day_2024 == 29
    tasks_leap = get_tasks_for_schedule(
        "monthly",
        day_of_month=29,
        month=2,
        year=2024,
        data=data,
    )
    assert len(tasks_leap) == 1
    assert tasks_leap[0][1]["command"] == "month_end"


@pytest.mark.django_db
def test_get_beat_schedule_missing_yaml_non_strict_returns_empty(
    tmp_path, caplog, settings
):
    """With DEBUG True and no strict env, missing YAML yields empty beat schedule and a warning."""
    settings.DEBUG = True
    settings.BOOST_COLLECTOR_SCHEDULE_STRICT = False
    missing = tmp_path / "missing.yaml"
    settings.BOOST_COLLECTOR_SCHEDULE_YAML = str(missing)
    caplog.set_level(logging.WARNING)
    with patch(
        "boost_collector_runner.schedule_config._get_yaml_path", return_value=missing
    ):
        assert get_beat_schedule() == {}
    assert any("not found" in r.getMessage().lower() for r in caplog.records)


@pytest.mark.django_db
def test_get_beat_schedule_missing_yaml_strict_raises(tmp_path, caplog, settings):
    """With DEBUG False, missing YAML raises ScheduleConfigurationError and logs ERROR."""
    settings.DEBUG = False
    settings.BOOST_COLLECTOR_SCHEDULE_STRICT = False
    missing = tmp_path / "missing.yaml"
    settings.BOOST_COLLECTOR_SCHEDULE_YAML = str(missing)
    caplog.set_level(logging.ERROR)
    with patch(
        "boost_collector_runner.schedule_config._get_yaml_path", return_value=missing
    ):
        with pytest.raises(ScheduleConfigurationError, match="not found"):
            get_beat_schedule()
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


@pytest.mark.django_db
def test_get_beat_schedule_missing_yaml_strict_with_debug_true_via_env(
    tmp_path, caplog, settings
):
    """BOOST_COLLECTOR_SCHEDULE_STRICT forces strict behavior when DEBUG is True."""
    settings.DEBUG = True
    settings.BOOST_COLLECTOR_SCHEDULE_STRICT = True
    missing = tmp_path / "missing.yaml"
    settings.BOOST_COLLECTOR_SCHEDULE_YAML = str(missing)
    caplog.set_level(logging.ERROR)
    with patch(
        "boost_collector_runner.schedule_config._get_yaml_path", return_value=missing
    ):
        with pytest.raises(ScheduleConfigurationError):
            get_beat_schedule()


@pytest.mark.django_db
def test_get_beat_schedule_invalid_yaml_strict_raises(tmp_path, caplog, settings):
    settings.DEBUG = False
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.dump({"groups": []}), encoding="utf-8")
    settings.BOOST_COLLECTOR_SCHEDULE_YAML = str(bad)
    caplog.set_level(logging.ERROR)
    with patch(
        "boost_collector_runner.schedule_config._get_yaml_path", return_value=bad
    ):
        with pytest.raises(ScheduleConfigurationError, match="Invalid schedule YAML"):
            get_beat_schedule()


def test_get_beat_schedule_generates_expected_entries(tmp_path, settings):
    """get_beat_schedule returns Beat entries with expected task name, keys, and interval."""
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
                                "schedule": "interval",
                                "minutes": 15,
                            },
                        ],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    settings.BOOST_COLLECTOR_SCHEDULE_YAML = str(yaml_path)

    schedule = get_beat_schedule()

    assert isinstance(schedule, dict)
    group_key = "boost-collector-group-github-04-10"
    assert group_key in schedule
    assert (
        schedule[group_key]["task"]
        == "boost_collector_runner.tasks.run_scheduled_collectors_task"
    )
    assert "kwargs" in schedule[group_key]
    assert (
        schedule[group_key]["kwargs"]["schedule_kind"]
        == DEFAULT_GROUP_BATCH_SCHEDULE_KIND
    )
    assert schedule[group_key]["kwargs"]["group_id"] == "github"

    interval_key = "boost-collector-interval-15min"
    assert interval_key in schedule
    assert (
        schedule[interval_key]["task"]
        == "boost_collector_runner.tasks.run_scheduled_collectors_task"
    )
    assert schedule[interval_key]["kwargs"]["schedule_kind"] == "interval"
    assert schedule[interval_key]["kwargs"]["interval_minutes"] == 15
    assert "group_id" not in schedule[interval_key]["kwargs"]
    from datetime import timedelta

    assert schedule[interval_key]["schedule"].run_every == timedelta(minutes=15)


def test_get_beat_schedule_with_all_schedule_types(tmp_path, settings):
    """get_beat_schedule with daily, weekly, monthly, on_release, interval yields correct entries per group and one per interval_minutes (no group_id)."""
    from datetime import timedelta

    yaml_path = tmp_path / "boost_collector_schedule.yaml"
    yaml_path.write_text(
        yaml.dump(
            {
                "groups": {
                    "github": {
                        "default_time": "16:10",
                        "tasks": [
                            {"command": "run_daily", "schedule": "daily"},
                            {
                                "command": "run_weekly",
                                "schedule": "weekly",
                                "on": "monday",
                            },
                            {
                                "command": "run_monthly",
                                "schedule": "monthly",
                                "on": 1,
                            },
                            {"command": "run_on_release", "schedule": "on_release"},
                            {
                                "command": "run_interval_15",
                                "schedule": "interval",
                                "minutes": 15,
                            },
                        ],
                    },
                    "slack": {
                        "default_time": "16:30",
                        "tasks": [
                            {"command": "run_slack_daily", "schedule": "daily"},
                            {
                                "command": "run_slack_interval",
                                "schedule": "interval",
                                "minutes": 60,
                            },
                        ],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    settings.BOOST_COLLECTOR_SCHEDULE_YAML = str(yaml_path)

    schedule = get_beat_schedule()

    assert isinstance(schedule, dict)
    # Group batch entries (default schedule kind) — one per group with non-interval tasks
    for group_id, time_str, key_suffix in [
        ("github", "16-10", "16-10"),
        ("slack", "16-30", "16-30"),
    ]:
        group_key = f"boost-collector-group-{group_id}-{key_suffix}"
        assert group_key in schedule, f"missing {group_key}"
        assert (
            schedule[group_key]["kwargs"]["schedule_kind"]
            == DEFAULT_GROUP_BATCH_SCHEDULE_KIND
        )
        assert schedule[group_key]["kwargs"]["group_id"] == group_id

    # Interval entries — one per interval_minutes (no group_id)
    interval_15_key = "boost-collector-interval-15min"
    interval_60_key = "boost-collector-interval-60min"
    assert interval_15_key in schedule
    assert interval_60_key in schedule
    assert schedule[interval_15_key]["kwargs"]["schedule_kind"] == "interval"
    assert schedule[interval_15_key]["kwargs"]["interval_minutes"] == 15
    assert "group_id" not in schedule[interval_15_key]["kwargs"]
    assert schedule[interval_60_key]["kwargs"]["schedule_kind"] == "interval"
    assert schedule[interval_60_key]["kwargs"]["interval_minutes"] == 60
    assert "group_id" not in schedule[interval_60_key]["kwargs"]
    assert schedule[interval_15_key]["schedule"].run_every == timedelta(minutes=15)
    assert schedule[interval_60_key]["schedule"].run_every == timedelta(minutes=60)


def test_get_tasks_for_schedule_interval_scoped_by_group_id(tmp_path):
    """get_tasks_for_schedule(interval, ..., group_id=X) returns only that group's interval tasks; group_id=None returns all."""
    path = tmp_path / "schedule.yaml"
    path.write_text(
        yaml.dump(
            {
                "groups": {
                    "g1": {
                        "default_time": "04:10",
                        "tasks": [
                            {
                                "command": "interval_g1",
                                "schedule": "interval",
                                "minutes": 15,
                            },
                        ],
                    },
                    "g2": {
                        "default_time": "04:20",
                        "tasks": [
                            {
                                "command": "interval_g2",
                                "schedule": "interval",
                                "minutes": 15,
                            },
                        ],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    data = load_config(path)

    tasks_g1 = get_tasks_for_schedule(
        "interval",
        interval_minutes=15,
        group_id="g1",
        data=data,
    )
    assert len(tasks_g1) == 1
    assert tasks_g1[0][0] == "g1"
    assert tasks_g1[0][1]["command"] == "interval_g1"

    tasks_g2 = get_tasks_for_schedule(
        "interval",
        interval_minutes=15,
        group_id="g2",
        data=data,
    )
    assert len(tasks_g2) == 1
    assert tasks_g2[0][0] == "g2"
    assert tasks_g2[0][1]["command"] == "interval_g2"

    tasks_all = get_tasks_for_schedule(
        "interval",
        interval_minutes=15,
        group_id=None,
        data=data,
    )
    assert len(tasks_all) == 2
    commands = {t[1]["command"] for t in tasks_all}
    assert commands == {"interval_g1", "interval_g2"}


@pytest.mark.django_db
def test_committed_schedule_yaml_loads_non_empty_beat_schedule(settings):
    """Repo ships config/boost_collector_schedule.yaml; Beat must not be empty on clone."""
    repo_yaml = Path(settings.BASE_DIR) / "config" / "boost_collector_schedule.yaml"
    assert (
        repo_yaml.is_file()
    ), "committed schedule missing; add config/boost_collector_schedule.yaml"
    settings.BOOST_COLLECTOR_SCHEDULE_YAML = repo_yaml
    data = load_config(repo_yaml)
    registered = get_commands()
    for _group_id, group_data in (data.get("groups") or {}).items():
        if not isinstance(group_data, dict):
            continue
        task_list = group_data.get("tasks") or []
        for task in task_list:
            if not isinstance(task, dict) or task.get("enabled") is False:
                continue
            cmd = task.get("command")
            assert cmd in registered, f"unknown management command in YAML: {cmd!r}"
    schedule = get_beat_schedule()
    assert schedule, "CELERY_BEAT_SCHEDULE must not be empty when committed YAML exists"


# --- is_schedule_strict / ensure_schedule_yaml_loaded ---


def test_is_schedule_strict_explicit_override():
    assert is_schedule_strict(strict=True) is True
    assert is_schedule_strict(strict=False) is False


@pytest.mark.django_db
def test_is_schedule_strict_from_settings(settings):
    settings.DEBUG = True
    settings.BOOST_COLLECTOR_SCHEDULE_STRICT = False
    assert is_schedule_strict() is False

    settings.DEBUG = False
    assert is_schedule_strict() is True

    settings.DEBUG = True
    settings.BOOST_COLLECTOR_SCHEDULE_STRICT = True
    assert is_schedule_strict() is True


def test_ensure_schedule_yaml_loaded_raises_when_missing(tmp_path):
    missing = tmp_path / "missing.yaml"
    with pytest.raises(ScheduleConfigurationError, match="not found"):
        with patch(
            "boost_collector_runner.schedule_config._get_yaml_path",
            return_value=missing,
        ):
            ensure_schedule_yaml_loaded()


# --- iter_beat_schedule_entry_keys / get_groups_and_tasks ---


def test_iter_beat_schedule_entry_keys_matches_get_beat_schedule_keys(
    tmp_path, settings
):
    yaml_path = tmp_path / "schedule.yaml"
    yaml_path.write_text(
        yaml.dump(
            {
                "groups": {
                    "g1": {
                        "default_time": "04:10",
                        "tasks": [
                            {"command": "run_foo", "schedule": "daily"},
                            {
                                "command": "run_interval",
                                "schedule": "interval",
                                "minutes": 30,
                            },
                        ],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    data = load_config(yaml_path)
    keys = list(iter_beat_schedule_entry_keys(data))
    assert keys == [
        "boost-collector-group-g1-04-10",
        "boost-collector-interval-30min",
    ]


def test_get_groups_and_tasks_skips_disabled_tasks(tmp_path):
    path = tmp_path / "schedule.yaml"
    path.write_text(
        yaml.dump(
            {
                "groups": {
                    "g1": {
                        "default_time": "04:10",
                        "tasks": [
                            {"command": "run_on", "schedule": "daily"},
                            {
                                "command": "run_off",
                                "schedule": "daily",
                                "enabled": False,
                            },
                        ],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    data = load_config(path)
    groups = get_groups_and_tasks(data=data)
    assert len(groups) == 1
    assert len(groups[0][2]) == 1
    assert groups[0][2][0]["command"] == "run_on"


def test_get_groups_and_tasks_raises_when_default_time_blank():
    data = {
        "groups": {
            "g2": {
                "default_time": "   ",
                "tasks": [],
            },
        },
    }
    with pytest.raises(ValueError, match="must have 'default_time'"):
        get_groups_and_tasks(data=data)


def test_parse_time_rejects_non_numeric_parts():
    with pytest.raises(ValueError, match="Invalid time"):
        _parse_time("ab:cd")


# --- get_tasks_for_schedule validation ---


def test_get_tasks_for_schedule_rejects_invalid_schedule_kind(tmp_path):
    data = load_config(_minimal_schedule_yaml(tmp_path))
    with pytest.raises(ValueError, match="schedule_kind must be one of"):
        get_tasks_for_schedule("not-a-schedule", data=data)


def test_get_tasks_for_schedule_weekly_requires_day_of_week(tmp_path):
    data = load_config(_minimal_schedule_yaml(tmp_path))
    with pytest.raises(ValueError, match="day_of_week required"):
        get_tasks_for_schedule("weekly", data=data)


def test_get_tasks_for_schedule_weekly_rejects_invalid_day(tmp_path):
    data = load_config(_minimal_schedule_yaml(tmp_path))
    with pytest.raises(ValueError, match="day_of_week must be monday"):
        get_tasks_for_schedule("weekly", day_of_week="notaday", data=data)


def test_get_tasks_for_schedule_monthly_requires_day_of_month(tmp_path):
    data = load_config(_minimal_schedule_yaml(tmp_path))
    with pytest.raises(ValueError, match="day_of_month required"):
        get_tasks_for_schedule("monthly", data=data)


def test_get_tasks_for_schedule_monthly_rejects_non_integer(tmp_path):
    data = load_config(_minimal_schedule_yaml(tmp_path))
    with pytest.raises(ValueError, match="day_of_month must be an integer"):
        get_tasks_for_schedule("monthly", day_of_month="x", data=data)


def test_get_tasks_for_schedule_monthly_rejects_out_of_range(tmp_path):
    data = load_config(_minimal_schedule_yaml(tmp_path))
    with pytest.raises(ValueError, match="day_of_month must be 1-31"):
        get_tasks_for_schedule("monthly", day_of_month=32, data=data)


def test_get_tasks_for_schedule_interval_requires_minutes(tmp_path):
    data = load_config(_minimal_schedule_yaml(tmp_path))
    with pytest.raises(ValueError, match="interval_minutes required"):
        get_tasks_for_schedule("interval", data=data)


def test_get_tasks_for_schedule_interval_rejects_non_integer(tmp_path):
    data = load_config(_minimal_schedule_yaml(tmp_path))
    with pytest.raises(ValueError, match="interval_minutes must be an integer"):
        get_tasks_for_schedule("interval", interval_minutes="x", data=data)


def test_get_tasks_for_schedule_interval_rejects_out_of_range(tmp_path):
    data = load_config(_minimal_schedule_yaml(tmp_path))
    with pytest.raises(
        ValueError, match=f"interval_minutes must be 1-{INTERVAL_MINUTES_MAX}"
    ):
        get_tasks_for_schedule(
            "interval",
            interval_minutes=INTERVAL_MINUTES_MAX + 1,
            data=data,
        )


def test_get_tasks_for_schedule_daily_and_weekly_filters(tmp_path):
    path = tmp_path / "schedule.yaml"
    path.write_text(
        yaml.dump(
            {
                "groups": {
                    "g1": {
                        "default_time": "04:10",
                        "tasks": [
                            {"command": "run_daily", "schedule": "daily"},
                            {
                                "command": "run_weekly",
                                "schedule": "weekly",
                                "on": "tuesday",
                            },
                        ],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    data = load_config(path)
    daily = get_tasks_for_schedule("daily", data=data)
    assert len(daily) == 1
    assert daily[0][1]["command"] == "run_daily"

    weekly = get_tasks_for_schedule("weekly", day_of_week="tuesday", data=data)
    assert len(weekly) == 1
    assert weekly[0][1]["command"] == "run_weekly"


def test_get_tasks_for_schedule_group_batch_excludes_interval(tmp_path):
    path = tmp_path / "schedule.yaml"
    path.write_text(
        yaml.dump(
            {
                "groups": {
                    "g1": {
                        "default_time": "04:10",
                        "tasks": [
                            {"command": "run_daily", "schedule": "daily"},
                            {
                                "command": "run_interval",
                                "schedule": "interval",
                                "minutes": 15,
                            },
                        ],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    data = load_config(path)
    batch = get_tasks_for_schedule(DEFAULT_GROUP_BATCH_SCHEDULE_KIND, data=data)
    commands = {t[1]["command"] for t in batch}
    assert commands == {"run_daily"}


@pytest.mark.django_db
def test_get_beat_schedule_invalid_yaml_non_strict_returns_empty(
    tmp_path, caplog, settings
):
    settings.DEBUG = True
    settings.BOOST_COLLECTOR_SCHEDULE_STRICT = False
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.dump({"groups": []}), encoding="utf-8")
    caplog.set_level(logging.WARNING)
    schedule = get_beat_schedule(strict=False, yaml_path=bad)
    assert schedule == {}
    assert any("Invalid schedule YAML" in r.getMessage() for r in caplog.records)


def _minimal_schedule_yaml(tmp_path: Path) -> Path:
    path = tmp_path / "schedule.yaml"
    path.write_text(
        yaml.dump(
            {
                "groups": {
                    "g1": {
                        "default_time": "04:10",
                        "tasks": [{"command": "run_foo", "schedule": "daily"}],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return path
