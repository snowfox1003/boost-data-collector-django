"""Application version string (from setuptools-scm-generated core._version)."""

import re

from core import __version__, _version


def test_version_is_semver_like_string():
    assert isinstance(__version__, str)
    assert __version__
    assert re.match(r"^\d+\.\d+\.\d+", __version__)


def test_version_matches_generated_module():
    assert __version__ == _version.version
