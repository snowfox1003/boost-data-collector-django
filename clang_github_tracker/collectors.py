"""Clang GitHub tracker collector."""

from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError

from core.collectors.base_collector import AbstractCollector
from core.utils.datetime_parsing import parse_iso_datetime
from clang_github_tracker import state_manager as clang_state
from clang_github_tracker.sync_raw import sync_clang_github_activity
from clang_github_tracker.publisher import publish_clang_markdown
from clang_github_tracker.workspace import OWNER, REPO, get_workspace_root
from core.operations.md_ops.github_export import write_md_files

logger = logging.getLogger(__name__)

DEFAULT_CLANG_REPO_BRANCH = "master"


def _run_pinecone_sync(
    app_type: str, namespace: str, preprocessor_dotted_path: str
) -> None:
    """Trigger run_cppa_pinecone_sync if app_type and namespace are both set."""
    if not app_type:
        logger.warning(
            "Pinecone sync skipped: CLANG_GITHUB_PINECONE_APP_TYPE is empty (settings/env)."
        )
        return
    if not namespace:
        logger.warning(
            "Pinecone sync skipped: CLANG_GITHUB_PINECONE_NAMESPACE is empty (settings/env)."
        )
        return
    try:
        call_command(
            "run_cppa_pinecone_sync",
            app_type=app_type,
            namespace=namespace,
            preprocessor=preprocessor_dotted_path,
        )
        logger.info(
            "run_clang_github_tracker: pinecone sync completed (app_type=%s, namespace=%s)",
            app_type,
            namespace,
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Pinecone sync skipped/failed (run_cppa_pinecone_sync unavailable or errored): %s",
            exc,
        )


class ClangGithubTrackerCollector(AbstractCollector):
    """Fetch llvm/llvm-project activity; optional MD export, push, Pinecone."""

    def __init__(
        self,
        *,
        dry_run: bool,
        skip_github_sync: bool,
        skip_markdown_export: bool,
        skip_remote_push: bool,
        skip_pinecone: bool,
        since,
        until,
    ) -> None:
        self.dry_run = dry_run
        self.skip_github_sync = skip_github_sync
        self.skip_markdown_export = skip_markdown_export
        self.skip_remote_push = skip_remote_push
        self.skip_pinecone = skip_pinecone
        self.since = since
        self.until = until
        self._issue_numbers: list[int] = []
        self._pr_numbers: list[int] = []
        self._md_output_dir: Path | None = None
        self._new_files: dict[str, str] = {}

    @property
    def name(self) -> str:
        return "clang_github_tracker"

    def validate_config(self) -> None:
        try:
            self._since_dt = parse_iso_datetime(self.since)
            self._until_dt = parse_iso_datetime(self.until)
        except ValueError as e:
            raise CommandError(str(e)) from e

    def collect(self) -> None:
        start_commit, start_item, end_date = clang_state.resolve_start_end_dates(
            self._since_dt, self._until_dt
        )
        logger.info(
            "Resolved: start_commit=%r start_item=%r end=%r",
            start_commit,
            start_item,
            end_date,
        )

        if self.dry_run:
            if not self.skip_github_sync:
                logger.info("dry-run: would run GitHub sync for llvm/llvm-project")
            else:
                logger.info("dry-run: skipping GitHub sync (--skip-github-sync)")
            if not self.skip_markdown_export:
                logger.info("dry-run: would export Markdown for issues/PRs from sync")
            if not self.skip_remote_push:
                logger.info("dry-run: would push Markdown to configured Clang repo")
            if not self.skip_pinecone:
                logger.info("dry-run: would run Pinecone upsert for issues and PRs")
            logger.info("dry-run finished")
            return

        issue_numbers: list[int] = []
        pr_numbers: list[int] = []

        if not self.skip_github_sync:
            commits_saved, issue_numbers, pr_numbers = sync_clang_github_activity(
                start_commit=start_commit,
                start_item=start_item,
                end_date=end_date,
            )
            logger.info(
                "run_clang_github_tracker: sync done; commits=%s issues=%s prs=%s",
                commits_saved,
                len(issue_numbers),
                len(pr_numbers),
            )
        else:
            logger.info("skipping GitHub sync (--skip-github-sync)")

        self._issue_numbers = issue_numbers
        self._pr_numbers = pr_numbers

        md_output_dir = get_workspace_root() / "md_export"
        md_output_dir.mkdir(parents=True, exist_ok=True)
        self._md_output_dir = md_output_dir

        new_files: dict[str, str] = {}
        if not self.skip_markdown_export:
            if issue_numbers or pr_numbers:
                logger.info("writing MD to %s", md_output_dir)
                new_files = write_md_files(
                    owner=OWNER,
                    repo=REPO,
                    issue_numbers=issue_numbers,
                    pr_numbers=pr_numbers,
                    output_dir=md_output_dir,
                    folder_prefix="",
                )
                logger.info(
                    "run_clang_github_tracker: generated %s MD file(s).",
                    len(new_files),
                )
            elif self.skip_github_sync:
                logger.info("skipped Markdown export (no sync in this run)")
            else:
                logger.info(
                    "run_clang_github_tracker: no issues/PRs synced; skipping MD export."
                )
        else:
            logger.info("skipping Markdown export (--skip-markdown-export)")

        self._new_files = new_files

        if not self.skip_remote_push:
            logger.info("push Markdown to configured GitHub repo")
            self._push_markdown(md_output_dir, new_files)
        else:
            logger.info("skipping remote push (--skip-remote-push)")

        logger.info("run_clang_github_tracker finished successfully")

    def sync_pinecone(self) -> None:
        if self.dry_run or self.skip_pinecone:
            if self.skip_pinecone and not self.dry_run:
                logger.info("skipping Pinecone (--skip-pinecone)")
            return
        app_type = (settings.CLANG_GITHUB_PINECONE_APP_TYPE or "").strip()
        namespace = (settings.CLANG_GITHUB_PINECONE_NAMESPACE or "").strip()
        if not app_type:
            logger.warning(
                "Pinecone sync skipped: CLANG_GITHUB_PINECONE_APP_TYPE is empty (settings/env)."
            )
            return
        _run_pinecone_sync(
            f"{app_type}-issues",
            namespace,
            "clang_github_tracker.preprocessors.issue_preprocessor.preprocess_for_pinecone",
        )
        _run_pinecone_sync(
            f"{app_type}-prs",
            namespace,
            "clang_github_tracker.preprocessors.pr_preprocessor.preprocess_for_pinecone",
        )

    def _push_markdown(self, md_output_dir: Path, new_files: dict[str, str]) -> None:
        clang_github_context_repo_owner = getattr(
            settings, "CLANG_GITHUB_CONTEXT_REPO_OWNER", ""
        ).strip()
        clang_github_context_repo_name = getattr(
            settings, "CLANG_GITHUB_CONTEXT_REPO_NAME", ""
        ).strip()
        clang_github_context_repo_branch = (
            getattr(settings, "CLANG_GITHUB_CONTEXT_REPO_BRANCH", "") or ""
        ).strip() or DEFAULT_CLANG_REPO_BRANCH
        if not clang_github_context_repo_owner or not clang_github_context_repo_name:
            logger.error(
                "CLANG_GITHUB_CONTEXT_REPO_OWNER / CLANG_GITHUB_CONTEXT_REPO_NAME "
                "not configured; skipping Markdown push."
            )
            return

        publish_clang_markdown(
            md_output_dir,
            clang_github_context_repo_owner,
            clang_github_context_repo_name,
            clang_github_context_repo_branch,
            new_files,
        )
        logger.info("run_clang_github_tracker: MD publish complete.")
        for local_path in new_files.values():
            Path(local_path).unlink(missing_ok=True)
