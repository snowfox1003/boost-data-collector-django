import logging

import yaml
from django.apps import AppConfig
from django.conf import settings

logger = logging.getLogger(__name__)

_schedule_startup_logged = False


class BoostCollectorRunnerConfig(AppConfig):
    """Django app config for boost_collector_runner (YAML-driven collector schedule)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "boost_collector_runner"
    verbose_name = "Boost Collector Runner"

    def ready(self):
        global _schedule_startup_logged
        if _schedule_startup_logged:
            return
        _schedule_startup_logged = True

        from boost_collector_runner import schedule_config as sc

        path = sc._get_yaml_path()
        try:
            data = sc.load_config(path)
        except FileNotFoundError:
            logger.error(
                "Boost collector schedule startup check failed: YAML not found at %s",
                path,
            )
            sc.SCHEDULE_STARTUP_OK = False
        except (ValueError, yaml.YAMLError, OSError) as e:
            logger.error(
                "Boost collector schedule startup check failed: invalid YAML at %s: %s",
                path,
                e,
            )
            sc.SCHEDULE_STARTUP_OK = False
        else:
            sc.SCHEDULE_STARTUP_OK = True
            beat_keys = sorted(sc.iter_beat_schedule_entry_keys(data))
            groups = sc.get_groups_and_tasks(data=data)
            n_groups = len(groups)
            n_tasks = sum(len(ts) for _, _, ts in groups)
            logger.info(
                "Boost collector schedule: path=%s groups_with_tasks=%s "
                "enabled_tasks=%s beat_entry_count=%s beat_entry_keys=%s",
                path,
                n_groups,
                n_tasks,
                len(beat_keys),
                beat_keys,
            )

        settings.BOOST_COLLECTOR_SCHEDULE_STARTUP_OK = sc.SCHEDULE_STARTUP_OK
