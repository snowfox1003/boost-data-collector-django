"""Pure helpers for registering a new collector app in project config files."""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass
from pathlib import Path

from django.core.management.base import CommandError

_CONTRIB_PREFIX = "django.contrib."
_INSTALLED_APPS_MARKER = "INSTALLED_APPS = ["
_SCHEDULE_MARKER = f"startcollector: {{app_label}}"
_IMPORTLINTER_SECTION = "[importlinter]"
_INVENTORY_TABLE_HEADER = "| App | Role | Has models? |"
_INVENTORY_ROW_RE = re.compile(r"^\| `([^`]+)` \|")


def insert_installed_app(content: str, app_label: str) -> str:
    """Insert app_label into INSTALLED_APPS among project apps (alphabetically)."""
    if f'"{app_label}"' in content:
        return content

    start = content.find(_INSTALLED_APPS_MARKER)
    if start == -1:
        raise ValueError("INSTALLED_APPS = [ not found in settings.py")

    open_bracket = start + len(_INSTALLED_APPS_MARKER) - 1
    close_bracket = content.find("]", open_bracket)
    if close_bracket == -1:
        raise ValueError("INSTALLED_APPS closing ] not found in settings.py")

    block = content[open_bracket : close_bracket + 1]
    lines = block.splitlines(keepends=True)

    project_indices: list[int] = []
    project_names: list[str] = []
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith('"'):
            continue
        match = re.match(r'"([^"]+)"', stripped)
        if not match:
            continue
        name = match.group(1)
        if name.startswith(_CONTRIB_PREFIX):
            continue
        project_indices.append(idx)
        project_names.append(name)

    insert_at = len(lines)
    for pos, name in enumerate(project_names):
        if app_label < name:
            insert_at = project_indices[pos]
            break

    entry = f'    "{app_label}",\n'
    lines.insert(insert_at, entry)
    new_block = "".join(lines)
    return content[:open_bracket] + new_block + content[close_bracket + 1 :]


def append_schedule_entry(content: str, app_label: str) -> str:
    """Append a commented schedule scaffold block at EOF."""
    marker = _SCHEDULE_MARKER.format(app_label=app_label)
    if marker in content:
        return content

    cmd = f"run_{app_label}"
    block = textwrap.dedent(
        f"""\
        # --- {marker} (move under the right group; uncomment when ready) ---
        # groups:
        #   github:
        #     tasks:
        #       - command: {cmd}
        #         schedule: daily
        #         enabled: false
        """
    )
    if content and not content.endswith("\n"):
        content += "\n"
    return content + block


def append_importlinter_root_package(content: str, app_label: str) -> str:
    """Insert app_label into root_packages alphabetically."""
    if re.search(rf"^\s*{re.escape(app_label)}\s*$", content, re.MULTILINE):
        return content

    section_start = content.find(_IMPORTLINTER_SECTION)
    if section_start == -1:
        raise ValueError("[importlinter] section not found in .importlinter")

    next_section = content.find("\n[", section_start + 1)
    section_end = next_section if next_section != -1 else len(content)
    section = content[section_start:section_end]

    root_match = re.search(r"^root_packages\s*=\s*$", section, re.MULTILINE)
    if not root_match:
        raise ValueError("root_packages = not found in .importlinter")

    lines = section.splitlines(keepends=True)
    package_lines: list[tuple[int, str]] = []
    in_root = False
    for idx, line in enumerate(lines):
        if line.strip() == "root_packages =":
            in_root = True
            continue
        if in_root:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("["):
                break
            package_lines.append((idx, stripped))

    insert_idx = len(lines)
    for pos, (_, pkg) in enumerate(package_lines):
        if app_label < pkg:
            insert_idx = package_lines[pos][0]
            break
    else:
        if package_lines:
            insert_idx = package_lines[-1][0] + 1

    lines.insert(insert_idx, f"    {app_label}\n")
    new_section = "".join(lines)
    return content[:section_start] + new_section + content[section_end:]


def append_cross_app_inventory_row(content: str, app_label: str) -> str:
    """Insert a stub inventory table row alphabetically by app name."""
    row_prefix = f"| `{app_label}` |"
    if row_prefix in content:
        return content

    header_idx = content.find(_INVENTORY_TABLE_HEADER)
    if header_idx == -1:
        raise ValueError("Tracker App Inventory table header not found")

    table_start = content.find("| --- |", header_idx)
    if table_start == -1:
        raise ValueError("Tracker App Inventory table separator not found")

    separator_end = content.find("\n", table_start)
    line_start = separator_end + 1 if separator_end != -1 else len(content)
    rows: list[tuple[str, int]] = []
    while True:
        next_newline = content.find("\n", line_start)
        if next_newline == -1:
            line_end = len(content)
        else:
            line_end = next_newline
        line = content[line_start:line_end]
        match = _INVENTORY_ROW_RE.match(line)
        if not match:
            break
        rows.append((match.group(1), line_start))
        if next_newline == -1:
            break
        line_start = next_newline + 1

    new_row = (
        f"| `{app_label}` | Collector stub (customize role) | Yes |\n"
    )
    insert_at = rows[-1][1] if rows else table_start
    for name, pos in rows:
        if app_label < name:
            insert_at = pos
            break
    else:
        if rows:
            last_line_end = content.find("\n", rows[-1][1])
            insert_at = last_line_end + 1 if last_line_end != -1 else len(content)

    return content[:insert_at] + new_row + content[insert_at:]


@dataclass(frozen=True)
class ProjectFileTarget:
    relative_path: str
    transform: object  # Callable[[str, str], str]

    def apply(self, content: str, app_label: str) -> str:
        return self.transform(content, app_label)  # type: ignore[operator]


PROJECT_FILE_TARGETS: tuple[ProjectFileTarget, ...] = (
    ProjectFileTarget("config/settings.py", insert_installed_app),
    ProjectFileTarget(
        "config/boost_collector_schedule.yaml", append_schedule_entry
    ),
    ProjectFileTarget(".importlinter", append_importlinter_root_package),
    ProjectFileTarget(
        "docs/cross-app-dependencies.md", append_cross_app_inventory_row
    ),
)


def register_collector_project_files(
    repo_root: Path,
    app_label: str,
    *,
    dry_run: bool = False,
) -> list[str]:
    """Update project config files for a new collector app. Returns log lines."""
    log: list[str] = []
    for target in PROJECT_FILE_TARGETS:
        path = repo_root / target.relative_path
        if not path.is_file():
            raise CommandError(
                f"Expected project file missing: {path}. "
                f"Registration skipped; app scaffold may still exist on disk."
            )
        original = path.read_text(encoding="utf-8")
        updated = target.apply(original, app_label)
        rel = target.relative_path
        if updated == original:
            log.append(f"Skipped {rel} ({app_label} already present)")
            continue
        if dry_run:
            log.append(f"Would update {rel}")
        else:
            try:
                path.write_text(updated, encoding="utf-8")
            except OSError as exc:
                raise CommandError(
                    f"Failed to write {path}: {exc}. "
                    f"App scaffold may exist; finish registration manually."
                ) from exc
            log.append(f"Updated {rel}")
    return log
