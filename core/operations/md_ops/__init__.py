"""Markdown operations: transcript, issue, PR, html_to_md (and more)."""

from core.operations.md_ops.github_export import (
    detect_renames,
    detect_renames_from_dirs,
    write_md_files,
)
from core.operations.md_ops.html_to_md import (
    HTMLToMarkdownConverter,
    convert_html_file_to_markdown,
    html_to_markdown,
)
from core.operations.md_ops.issue_to_md import issue_json_to_md
from core.operations.md_ops.pr_to_md import pr_json_to_md

__all__ = [
    "HTMLToMarkdownConverter",
    "convert_html_file_to_markdown",
    "detect_renames",
    "detect_renames_from_dirs",
    "html_to_markdown",
    "issue_json_to_md",
    "pr_json_to_md",
    "write_md_files",
]
