"""Publish Boost library usage dashboard artifacts to a GitHub repository."""

from __future__ import annotations

import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import CommandError

from core.operations.github_ops.git_ops import (
    clone_repo,
    prepare_repo_for_pull,
    pull,
    push,
)

logger = logging.getLogger(__name__)

# GitHub owner/login and repository name: single path segment, no traversal.
_GITHUB_OWNER_REPO_SLUG = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")


def _validate_github_slug(label: str, value: str) -> str:
    """Return stripped owner or repo name, or raise CommandError if unsafe or invalid."""
    v = (value or "").strip()
    if not v:
        raise CommandError(f"Invalid GitHub {label}: empty")
    if v in (".", ".."):
        raise CommandError(f"Invalid GitHub {label}: {v!r}")
    if "/" in v or "\\" in v:
        raise CommandError(f"Invalid GitHub {label}: {v!r}")
    if Path(v).is_absolute():
        raise CommandError(f"Invalid GitHub {label}: {v!r}")
    if not _GITHUB_OWNER_REPO_SLUG.fullmatch(v):
        raise CommandError(f"Invalid GitHub {label}: {v!r}")
    return v


def publish_dashboard(
    output_dir: Path,
    owner: str,
    repo: str,
    branch: str,
) -> None:
    """
    Publish using a persistent clone at raw/boost_library_usage_dashboard/<owner>/<repo>.
    Clone if missing, then fetch/clean/reset the clone, pull, sync ``develop/`` from
    output_dir, commit, push.

    Uses ``settings.GITHUB_TOKEN_WRITE`` for clone/pull/push and
    ``settings.GIT_AUTHOR_NAME`` / ``settings.GIT_AUTHOR_EMAIL`` for the commit
    identity (via env vars on ``git commit`` only).
    """
    owner = _validate_github_slug("owner", owner)
    repo = _validate_github_slug("repo", repo)

    publish_root = (Path(settings.RAW_DIR) / "boost_library_usage_dashboard").resolve()
    clone_dir = (publish_root / owner / repo).resolve()
    try:
        clone_dir.relative_to(publish_root)
    except ValueError:
        raise CommandError(
            f"Publish clone path escapes dashboard publish root: {clone_dir}"
        ) from None

    output_dir = output_dir.resolve()
    if (
        clone_dir == output_dir
        or clone_dir in output_dir.parents
        or output_dir in clone_dir.parents
    ):
        raise CommandError(
            "Workspace output directory must not overlap with the publish clone path: "
            f"{clone_dir}"
        )

    clone_dir.parent.mkdir(parents=True, exist_ok=True)
    token = (getattr(settings, "GITHUB_TOKEN_WRITE", None) or "").strip() or None
    git_user_name = (getattr(settings, "GIT_AUTHOR_NAME", None) or "unknown").strip()
    git_user_email = (
        getattr(settings, "GIT_AUTHOR_EMAIL", None) or "unknown@noreply.github.com"
    ).strip()

    repo_slug = f"{owner}/{repo}"
    logger.info("Publishing dashboard artifacts to %s (%s)...", repo_slug, branch)

    if not clone_dir.exists() or not (clone_dir / ".git").is_dir():
        if clone_dir.exists():
            shutil.rmtree(clone_dir)
        logger.info("Cloning %s to %s", repo_slug, clone_dir)
        clone_repo(repo_slug, clone_dir, token=token)

    logger.info("Bootstrapping clone before pull: fetch, clean, reset (%s)", clone_dir)
    prepare_repo_for_pull(clone_dir, remote="origin", token=token)

    logger.info("Pulling latest for %s", clone_dir)
    pull(clone_dir, branch=branch, token=token)

    for child in clone_dir.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir() and child.name == "develop":
            shutil.rmtree(child)

    publish_subdir = clone_dir / "develop"
    publish_subdir.mkdir(parents=True, exist_ok=True)

    for child in output_dir.iterdir():
        dest = publish_subdir / child.name
        if child.is_dir():
            shutil.copytree(child, dest)
        else:
            if child.suffix != ".html":
                continue
            shutil.copy2(child, dest)

    commit_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    commit_message = f"Update Boost library usage dashboard artifacts ({commit_time})"
    push(
        clone_dir,
        remote="origin",
        branch=branch,
        commit_message=commit_message,
        token=token,
        git_user_name=git_user_name,
        git_user_email=git_user_email,
    )
    logger.info("Dashboard artifacts published successfully to %s.", repo_slug)
