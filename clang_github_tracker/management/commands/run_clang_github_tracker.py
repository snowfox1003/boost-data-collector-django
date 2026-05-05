"""
Management command: run_clang_github_tracker

Fetches GitHub activity for llvm/llvm-project, saves raw JSON and DB rows, optionally
exports Markdown and pushes to the configured Clang markdown GitHub repo. Resume uses DB watermarks (not state.json).
"""

from core.collectors.command_base import BaseCollectorCommand
from clang_github_tracker.collectors import ClangGithubTrackerCollector


class Command(BaseCollectorCommand):
    """Django management command: fetch GitHub activity to raw + DB; optional MD, push, Pinecone."""

    help = (
        "Run Clang GitHub Tracker: fetch llvm/llvm-project activity to "
        "raw/github_activity_tracker and DB. Uses DB cursor for resume (not state.json). "
        "Use --skip-* to skip steps; default runs all."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="No sync, export, push, or Pinecone writes; resolved windows logged at INFO.",
        )
        parser.add_argument(
            "--skip-github-sync",
            action="store_true",
            help="Skip API fetch / sync_clang_github_activity (raw JSON + DB upserts).",
        )
        parser.add_argument(
            "--skip-markdown-export",
            action="store_true",
            help="Skip writing .md files from this run's sync results.",
        )
        parser.add_argument(
            "--skip-remote-push",
            action="store_true",
            help="Skip push to the repo configured via CLANG_GITHUB_CONTEXT_REPO_OWNER / CLANG_GITHUB_CONTEXT_REPO_NAME.",
        )
        parser.add_argument(
            "--skip-pinecone",
            action="store_true",
            help="Skip run_cppa_pinecone_sync for issues and PRs.",
        )
        parser.add_argument(
            "--since",
            "--from-date",
            "--start-time",
            type=str,
            default=None,
            dest="since",
            help="Sync window start: YYYY-MM-DD or ISO-8601. "
            "--from-date / --start-time are aliases for --since.",
        )
        parser.add_argument(
            "--until",
            "--to-date",
            "--end-time",
            type=str,
            default=None,
            dest="until",
            help="Sync window end: same formats as --since. "
            "--to-date / --end-time are aliases for --until.",
        )

    def get_collector(self, **options):
        return ClangGithubTrackerCollector(
            dry_run=options["dry_run"],
            skip_github_sync=options["skip_github_sync"],
            skip_markdown_export=options["skip_markdown_export"],
            skip_remote_push=options["skip_remote_push"],
            skip_pinecone=options["skip_pinecone"],
            since=options.get("since"),
            until=options.get("until"),
        )
