"""
Workspace paths: one root folder, subfolders per app for raw/processed files.
Use for clone repos, downloaded PDFs, converted output, etc.
"""

from pathlib import Path

from django.conf import settings

# Operational failures from Path(settings.WORKSPACE_DIR) and mkdir(..., exist_ok=True).
# Does not include AttributeError (missing WORKSPACE_DIR): that indicates misconfigured
# settings and should propagate. Callers that log-and-continue on workspace setup (e.g.
# optional diagnostics) should catch this tuple only.
WORKSPACE_PATH_SETUP_ERRORS = (OSError, ValueError, TypeError)


def get_workspace_path(app_slug: str) -> Path:
    """
    Return the workspace subfolder for an app. Creates it if missing.

    app_slug: e.g. "github_activity_tracker", "boost_library_tracker", "shared"

    Raises:
        TypeError: WORKSPACE_DIR is not valid for Path().
        ValueError: Rare pathlib edge cases for invalid path components (OS-dependent).
        OSError: mkdir failed (permissions, disk, etc.).
    """
    path = Path(settings.WORKSPACE_DIR) / app_slug
    path.mkdir(parents=True, exist_ok=True)
    return path
