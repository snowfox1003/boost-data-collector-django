#!/usr/bin/env python3
"""
Fail CI when Django ORM writes happen outside the owning app's services.py.

Reads allowlist from .service-layer-write-allowlist.json (repo root). Each
allowlisted violation must have a nearby # TODO(service-layer): line containing
the eval id substring from the allowlist entry.

Usage:
    uv run python scripts/check_service_layer_writes.py          # exit 1 on violations
    uv run python scripts/check_service_layer_writes.py --report # markdown table
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST_PATH = REPO_ROOT / ".service-layer-write-allowlist.json"

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
    "discord_activity_tracker",
    "wg21_paper_tracker",
    "cppa_youtube_script_tracker",
    "slack_event_handler",
]
TRACKER_APP_SET = set(TRACKER_APPS)

SKIP_DIR_PARTS = frozenset(
    {
        "migrations",
        "__pycache__",
        ".git",
        "staticfiles",
        "htmlcov",
        ".test_artifacts",
    }
)

MANAGER_WRITE_METHODS = frozenset(
    {
        "create",
        "bulk_create",
        "bulk_update",
        "update_or_create",
        "get_or_create",
    }
)

QUERYSET_WRITE_METHODS = frozenset({"delete", "update"})


@dataclass(frozen=True)
class Violation:
    path: str  # posix relative
    line: int
    model: str
    kind: str
    owner_app: str
    file_app: str


def _is_test_path(rel: Path) -> bool:
    return any(p == "tests" or p.startswith("test") for p in rel.parts)


def _file_app(rel: Path) -> str | None:
    if not rel.parts:
        return None
    top = rel.parts[0]
    return top if top in TRACKER_APP_SET else None


def _collect_py_files() -> list[Path]:
    out: list[Path] = []
    for app in TRACKER_APPS:
        app_dir = REPO_ROOT / app
        if not app_dir.is_dir():
            continue
        for path in sorted(app_dir.rglob("*.py")):
            if any(p in SKIP_DIR_PARTS for p in path.parts):
                continue
            rel = path.relative_to(REPO_ROOT)
            if _is_test_path(rel):
                continue
            if rel.parts[-1] == "models.py":
                continue
            out.append(path)
    return out


def _looks_like_django_model_class(
    node: ast.ClassDef, local_model_names: set[str]
) -> bool:
    if not node.bases:
        return False
    for base in node.bases:
        if isinstance(base, ast.Attribute):
            if base.attr == "Model" and isinstance(base.value, ast.Name):
                if base.value.id == "models":
                    return True
        elif isinstance(base, ast.Name):
            if base.id == "Model":
                return True
            if base.id in local_model_names:
                return True
    return False


def _model_classes_from_models_py(path: Path) -> set[str]:
    try:
        tree = ast.parse(
            path.read_text(encoding="utf-8", errors="replace"), filename=str(path)
        )
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            names.add(node.name)
    models: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if _looks_like_django_model_class(node, names):
            inner_meta = next(
                (
                    b
                    for b in node.body
                    if isinstance(b, ast.ClassDef) and b.name == "Meta"
                ),
                None,
            )
            if inner_meta:
                is_abstract = False
                for stmt in inner_meta.body:
                    if (
                        isinstance(stmt, ast.Assign)
                        and len(stmt.targets) == 1
                        and isinstance(stmt.targets[0], ast.Name)
                        and stmt.targets[0].id == "abstract"
                    ):
                        if (
                            isinstance(stmt.value, ast.Constant)
                            and stmt.value.value is True
                        ):
                            is_abstract = True
                if not is_abstract:
                    models.add(node.name)
                continue
            models.add(node.name)
    return models


def build_model_owner_map() -> dict[str, str]:
    """Map model class name -> owning Django app package name."""
    owners: dict[str, str] = {}
    duplicates: dict[str, set[str]] = {}
    for app in TRACKER_APPS:
        mp = REPO_ROOT / app / "models.py"
        if not mp.is_file():
            continue
        for cls in _model_classes_from_models_py(mp):
            prev = owners.get(cls)
            if prev is not None and prev != app:
                duplicates.setdefault(cls, {prev}).add(app)
                continue
            owners[cls] = app
    if duplicates:
        details = ", ".join(
            f"{model} -> {sorted(apps)}" for model, apps in sorted(duplicates.items())
        )
        print(
            f"ERROR: duplicate model class names across tracker apps: {details}",
            file=sys.stderr,
        )
        sys.exit(2)
    return owners


def _model_from_objects_expression(expr: ast.AST) -> str | None:
    """Resolve ``Model`` from ``Model.objects....`` (expr may be inner Call e.g. ``.filter()``)."""
    func: ast.AST = expr
    if isinstance(expr, ast.Call):
        func = expr.func
    if not isinstance(func, ast.Attribute):
        return None
    parts: list[str] = []
    cur: ast.AST = func
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if not isinstance(cur, ast.Name):
        return None
    parts.append(cur.id)
    parts.reverse()
    try:
        oi = parts.index("objects")
    except ValueError:
        return None
    if oi == 0:
        return None
    return parts[oi - 1]


def _for_loop_iter_model_name(node: ast.For | ast.AsyncFor) -> str | None:
    if isinstance(node.iter, ast.Call):
        return _model_from_objects_expression(node.iter)
    return None


class _ScopeVisitor(ast.NodeVisitor):
    """Track simple bindings: for x in Model.objects... -> x is Model."""

    def __init__(self, model_owners: dict[str, str], file_app: str | None) -> None:
        self.model_owners = model_owners
        self.file_app = file_app
        self.var_model: dict[str, str] = {}
        self.violations: list[Violation] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        old = dict(self.var_model)
        for a in node.args.args:
            ann = a.annotation
            if isinstance(ann, ast.Name) and ann.id in self.model_owners:
                self.var_model[a.arg] = ann.id
            elif isinstance(ann, ast.Attribute) and isinstance(ann.value, ast.Name):
                if ann.attr in self.model_owners:
                    self.var_model[a.arg] = ann.attr
        self.generic_visit(node)
        self.var_model = old
        return None

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        old = dict(self.var_model)
        for a in node.args.args:
            ann = a.annotation
            if isinstance(ann, ast.Name) and ann.id in self.model_owners:
                self.var_model[a.arg] = ann.id
            elif isinstance(ann, ast.Attribute) and isinstance(ann.value, ast.Name):
                if ann.attr in self.model_owners:
                    self.var_model[a.arg] = ann.attr
        self.generic_visit(node)
        self.var_model = old
        return None

    def visit_For(self, node: ast.For) -> Any:
        self._visit_for_asyncfor(node)
        return None

    def visit_AsyncFor(self, node: ast.AsyncFor) -> Any:
        self._visit_for_asyncfor(node)
        return None

    def _visit_for_asyncfor(self, node: ast.For | ast.AsyncFor) -> None:
        old = dict(self.var_model)
        self.visit(node.iter)
        m = _for_loop_iter_model_name(node)
        if m and isinstance(node.target, ast.Name):
            self.var_model[node.target.id] = m
        for child in node.body:
            self.visit(child)
        for child in node.orelse:
            self.visit(child)
        self.var_model = old

    def visit_Assign(self, node: ast.Assign) -> Any:
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
            if isinstance(node.value, ast.Call):
                m = _model_from_objects_expression(node.value)
                if m and m in self.model_owners:
                    self.var_model[target] = m
        self.generic_visit(node)
        return None

    def _model_for_receiver(self, recv: ast.AST) -> str | None:
        m = _model_from_objects_expression(recv)
        if m is None and isinstance(recv, ast.Name):
            m = self.var_model.get(recv.id)
        return m

    def visit_Call(self, node: ast.Call) -> Any:
        self._check_call(node)
        self.generic_visit(node)
        return None

    def _check_call(self, node: ast.Call) -> None:
        if not self.file_app:
            return
        rel = getattr(self, "_rel_path", "")
        if rel.endswith("/services.py"):
            return

        # Manager writes: Model.objects.create / bulk_update / ...
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in MANAGER_WRITE_METHODS
        ):
            m = _model_from_objects_expression(node)
            if m and m in self.model_owners:
                owner = self.model_owners[m]
                if not _write_allowed(rel, owner):
                    self.violations.append(
                        Violation(
                            path=rel,
                            line=node.lineno,
                            model=m,
                            kind=f"objects.{node.func.attr}",
                            owner_app=owner,
                            file_app=self.file_app,
                        )
                    )
            return

        # .delete() or .update() on queryset from Model.objects...
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in QUERYSET_WRITE_METHODS
        ):
            recv = node.func.value
            m = self._model_for_receiver(recv)
            if m and m in self.model_owners:
                owner = self.model_owners[m]
                if not _write_allowed(rel, owner):
                    self.violations.append(
                        Violation(
                            path=rel,
                            line=node.lineno,
                            model=m,
                            kind=f"queryset.{node.func.attr}",
                            owner_app=owner,
                            file_app=self.file_app,
                        )
                    )
            return

        # instance .save() / .delete()
        if isinstance(node.func, ast.Attribute) and node.func.attr in (
            "save",
            "delete",
        ):
            recv = node.func.value
            model = self._model_for_receiver(recv)
            if model and model in self.model_owners:
                owner = self.model_owners[model]
                if not _write_allowed(rel, owner):
                    self.violations.append(
                        Violation(
                            path=rel,
                            line=node.lineno,
                            model=model,
                            kind=f"instance.{node.func.attr}",
                            owner_app=owner,
                            file_app=self.file_app,
                        )
                    )


def _write_allowed(rel_posix: str, owner_app: str) -> bool:
    if rel_posix.endswith(f"{owner_app}/services.py"):
        return True
    return False


def scan_file(path: Path, model_owners: dict[str, str]) -> list[Violation]:
    rel = path.relative_to(REPO_ROOT).as_posix()
    file_app = _file_app(path.relative_to(REPO_ROOT))
    if rel.endswith("/services.py") and file_app:
        # Only allow writes to models owned by this app; still need to scan for cross-app.
        visitor = _CrossAppServiceVisitor(model_owners, file_app, rel)
    else:
        visitor = _ScopeVisitor(model_owners, file_app)
        visitor._rel_path = rel  # type: ignore[attr-defined]
    try:
        tree = ast.parse(
            path.read_text(encoding="utf-8", errors="replace"), filename=str(path)
        )
    except SyntaxError:
        return []
    visitor.visit(tree)
    return visitor.violations


class _CrossAppServiceVisitor(_ScopeVisitor):
    """Inside services.py: flag writes to models not owned by file_app."""

    def __init__(self, model_owners: dict[str, str], file_app: str, rel: str) -> None:
        super().__init__(model_owners, file_app)
        self._rel_path = rel

    def _check_call(self, node: ast.Call) -> None:
        if not self.file_app:
            return
        rel = self._rel_path

        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in MANAGER_WRITE_METHODS
        ):
            m = _model_from_objects_expression(node)
            if m and m in self.model_owners:
                owner = self.model_owners[m]
                if owner != self.file_app:
                    self.violations.append(
                        Violation(
                            path=rel,
                            line=node.lineno,
                            model=m,
                            kind=f"objects.{node.func.attr}",
                            owner_app=owner,
                            file_app=self.file_app,
                        )
                    )
            return

        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in QUERYSET_WRITE_METHODS
        ):
            recv = node.func.value
            m = self._model_for_receiver(recv)
            if m and m in self.model_owners:
                owner = self.model_owners[m]
                if owner != self.file_app:
                    self.violations.append(
                        Violation(
                            path=rel,
                            line=node.lineno,
                            model=m,
                            kind=f"queryset.{node.func.attr}",
                            owner_app=owner,
                            file_app=self.file_app,
                        )
                    )
            return

        if isinstance(node.func, ast.Attribute) and node.func.attr in (
            "save",
            "delete",
        ):
            recv = node.func.value
            model = self._model_for_receiver(recv)
            if model and model in self.model_owners:
                owner = self.model_owners[model]
                if owner != self.file_app:
                    self.violations.append(
                        Violation(
                            path=rel,
                            line=node.lineno,
                            model=model,
                            kind=f"instance.{node.func.attr}",
                            owner_app=owner,
                            file_app=self.file_app,
                        )
                    )


def load_allowlist() -> list[dict[str, Any]]:
    if not ALLOWLIST_PATH.is_file():
        return []
    raw = ALLOWLIST_PATH.read_text(encoding="utf-8", errors="replace").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"ERROR: Invalid JSON allowlist: {exc}", file=sys.stderr)
        sys.exit(2)
    rows = data.get("violations")
    if rows is None:
        return []
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _todo_matches(lines_above: list[str], eval_substring: str) -> bool:
    pat = re.compile(r"#\s*TODO\s*\(\s*service-layer\s*\)\s*:", re.I)
    for line in lines_above:
        if pat.search(line) and eval_substring in line:
            return True
    return False


def _read_lines_above(path: Path, lineno: int, n: int = 5) -> list[str]:
    try:
        all_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    i = lineno - 1
    start = max(0, i - n)
    return all_lines[start:i]


def check_allowlist(
    violations: list[Violation], allowlist: list[dict[str, Any]]
) -> tuple[list[str], list[str]]:
    """Return (errors, warnings_as_errors)."""
    errors: list[str] = []
    keyed_violations: dict[tuple[str, int, str], Violation] = {
        (v.path, v.line, v.model): v for v in violations
    }
    used_keys: set[tuple[str, int, str]] = set()

    for row in allowlist:
        f = row.get("file")
        line = row.get("line")
        model = row.get("model")
        eval_id = row.get("eval", "")
        if (
            not isinstance(f, str)
            or not isinstance(line, int)
            or not isinstance(model, str)
        ):
            errors.append(f"Invalid allowlist row (bad types): {row!r}")
            continue
        key = (f, line, model)
        if key not in keyed_violations:
            errors.append(
                f"Stale allowlist entry (no matching violation): {f}:{line} {model} ({eval_id})"
            )
            continue
        used_keys.add(key)
        path = REPO_ROOT / f
        if not isinstance(eval_id, str) or not eval_id.strip():
            errors.append(f"Allowlist row missing eval id: {f}:{line}")
            continue
        above = _read_lines_above(path, line)
        if not _todo_matches(above, eval_id.strip()):
            errors.append(
                f"Allowlisted violation at {f}:{line} missing "
                f"# TODO(service-layer): ... containing {eval_id!r}"
            )

    for v in violations:
        key = (v.path, v.line, v.model)
        if key in used_keys:
            continue
        errors.append(
            f"ORM write outside owning services.py: {v.path}:{v.line} "
            f"model={v.model} kind={v.kind} owner={v.owner_app} file_app={v.file_app}"
        )
    return errors, []


def report_markdown(violations: list[Violation]) -> str:
    lines = [
        "| File | Line | Model | Kind | Owner app | File app |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for v in sorted(violations, key=lambda x: (x.path, x.line)):
        lines.append(
            f"| `{v.path}` | {v.line} | `{v.model}` | {v.kind} | `{v.owner_app}` | `{v.file_app}` |"
        )
    if len(lines) == 2:
        return "_No violations detected._\n"
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print markdown table and exit 0.",
    )
    args = parser.parse_args()

    model_owners = build_model_owner_map()
    violations: list[Violation] = []
    for path in _collect_py_files():
        violations.extend(scan_file(path, model_owners))

    if args.report:
        sys.stdout.write(report_markdown(violations))
        return

    allowlist = load_allowlist()
    errors, _ = check_allowlist(violations, allowlist)
    if errors:
        sys.stderr.write("service-layer write check failed:\n\n")
        for e in errors:
            sys.stderr.write(f"  - {e}\n")
        sys.stderr.write("\nSee CONTRIBUTING.md (service layer).\n")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
