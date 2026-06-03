"""
Subset-schema test settings for boost_mailing_list_tracker.

Uses PostgreSQL (via config.test_settings) but only installs django.contrib,
core, and boost_mailing_list_tracker — no cppa_user_tracker or peer trackers.
Requires DATABASE_URL (see README → Running tests).
"""

from .test_settings import *  # noqa: F401, F403

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "core",
    "boost_mailing_list_tracker",
]
