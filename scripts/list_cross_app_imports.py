#!/usr/bin/env python3
"""
List every cross-app Python import across the tracker apps in this project.

Usage:
    python scripts/list_cross_app_imports.py [--format md|csv] [--no-tests]

Output (Markdown by default):
    1. Production imports  - files outside tests/ directories.
    2. Test-only imports   - files inside tests/ directories.
    3. ORM read-coupling candidates - production files outside models.py that
       import a model from another tracker app AND contain a .objects usage.

Re-run after large refactors to keep docs/cross-app-dependencies.md current.
"""

import argparse
import ast
import csv as csv_mod
import io
import sys
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent

# All project tracker apps (INSTALLED_APPS minus django.contrib.* and core).
# boost_collector_runner is the orchestration app; included because its lazy
# imports into boost_library_tracker are real coupling edges.
TRACKER_APPS = [
    "boost_collector_runner",
    "cppa_user_tracker",
    "github_activity_tracker",
    "boost_library_tracker",
    "boost_library_docs_tracker",
    "boost_library_usage_dashboard",
    "boost_usage_tracker",
    "boost_mailing_list_tracker",
    "cppa_pinecone_sync",
    "clang_github_tracker",
    "cppa_slack_tracker",
    "wg21_paper_tracker",
    "cppa_youtube_script_tracker",
]

TRACKER_APP_SET = set(TRACKER_APPS)

# Directory names to skip when walking source trees.
SKIP_DIRS = {
    "migrations",
    "__pycache__",
    ".git",
    "staticfiles",
    "htmlcov",
    ".test_artifacts",
}


class CrossAppImport(NamedTuple):
    source_app: str
    source_file: str  # relative to repo root, forward slashes
    target_app: str
    symbols: str  # comma-separated names, or bare module path for plain `import`
    is_test: bool
    line: int


def _root_module(module_name: str) -> str:
    return module_name.split(".")[0]


def _is_test_file(path: Path) -> bool:
    return any(part.startswith("test") for part in path.parts)


def _collect_imports(filepath: Path) -> list[tuple[str, str, int]]:
    """Return list of (root_module, symbols_str, lineno) by AST-parsing *filepath*.

    Using ast.walk captures imports inside functions (lazy / guarded imports)
    which a line-by-line grep would miss.
    """
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return []

    results: list[tuple[str, str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            root = _root_module(node.module)
            if root in TRACKER_APP_SET:
                symbols = ", ".join(alias.name for alias in node.names)
                results.append((root, symbols, node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = _root_module(alias.name)
                if root in TRACKER_APP_SET:
                    results.append((root, alias.name, node.lineno))
    return results


def _has_objects_usage(filepath: Path) -> bool:
    """Return True if the file contains any `.objects` attribute access."""
    try:
        return ".objects" in filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def scan(include_tests: bool = True) -> list[CrossAppImport]:
    """Walk all tracker app directories and collect cross-app import edges."""
    rows: list[CrossAppImport] = []
    for app in TRACKER_APPS:
        app_dir = REPO_ROOT / app
        if not app_dir.is_dir():
            continue
        for filepath in sorted(app_dir.rglob("*.py")):
            if any(part in SKIP_DIRS for part in filepath.parts):
                continue
            relative = filepath.relative_to(REPO_ROOT)
            rel_str = relative.as_posix()
            is_test = _is_test_file(relative)
            if not include_tests and is_test:
                continue
            for target_app, symbols, line in _collect_imports(filepath):
                if target_app == app:
                    continue  # same-app self-import
                if target_app == "core":
                    continue  # core is shared infrastructure, not cross-tracker coupling
                rows.append(
                    CrossAppImport(
                        source_app=app,
                        source_file=rel_str,
                        target_app=target_app,
                        symbols=symbols,
                        is_test=is_test,
                        line=line,
                    )
                )
    return rows


def orm_coupling_candidates(all_rows: list[CrossAppImport]) -> list[CrossAppImport]:
    """Return rows where a production, non-models.py file imports from another
    tracker app AND contains at least one .objects usage.

    These are the files most likely to perform direct cross-app ORM reads, which
    bypass the target app's service layer and violate the read-isolation intent.
    """
    seen: set[str] = set()
    candidates: list[CrossAppImport] = []
    for row in all_rows:
        if row.is_test:
            continue
        if row.source_file.endswith("models.py"):
            continue
        key = row.source_file  # only flag each file once
        if key in seen:
            continue
        filepath = REPO_ROOT / row.source_file
        if _has_objects_usage(filepath):
            candidates.append(row)
            seen.add(key)
    return candidates


def _md_table(rows: list[CrossAppImport]) -> str:
    if not rows:
        return "_None found._"
    lines = [
        "| Source app | Source file | Target app | Symbols | Line |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| `{r.source_app}` | `{r.source_file}` | `{r.target_app}` | `{r.symbols}` | {r.line} |"
        )
    return "\n".join(lines)


def _csv_output(rows: list[CrossAppImport]) -> str:
    buf = io.StringIO()
    # Use LF only: csv's default CRLF + Windows stdout newline translation yields \r\r\n.
    w = csv_mod.writer(buf, lineterminator="\n")
    w.writerow(
        ["source_app", "source_file", "target_app", "symbols", "is_test", "line"]
    )
    for r in rows:
        w.writerow(
            [r.source_app, r.source_file, r.target_app, r.symbols, r.is_test, r.line]
        )
    return buf.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Emit a cross-app import report for the tracker apps."
    )
    parser.add_argument(
        "--format", choices=["md", "csv"], default="md", help="Output format."
    )
    parser.add_argument(
        "--no-tests", action="store_true", help="Exclude test files from the scan."
    )
    args = parser.parse_args()

    all_rows = scan(include_tests=not args.no_tests)
    prod_rows = [r for r in all_rows if not r.is_test]
    test_rows = [r for r in all_rows if r.is_test]
    orm_rows = orm_coupling_candidates(all_rows)

    if args.format == "csv":
        sys.stdout.write(_csv_output(all_rows))
        return

    print("## Cross-App Python Imports - Production Files\n")
    print(_md_table(prod_rows))

    if not args.no_tests:
        print("\n\n## Cross-App Python Imports - Test Files\n")
        print(_md_table(test_rows))

    print("\n\n## ORM Read-Coupling Candidates\n")
    print(
        "> Production files outside `models.py` that import from another tracker app "
        "AND contain a `.objects` usage.  These may query the foreign app's DB table "
        "directly instead of going through that app's service layer.\n"
    )
    print(_md_table(orm_rows))


if __name__ == "__main__":
    main()
