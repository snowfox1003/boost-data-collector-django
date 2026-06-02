#!/usr/bin/env python3
"""
Generate markdown service API reference from ``*/services.py`` and ``core/protocols.py``.

Usage:
    python scripts/generate_service_docs.py           # write docs
    python scripts/generate_service_docs.py --check   # exit 1 if docs drift
    python scripts/generate_service_docs.py --app NAME

Markers in each ``docs/service_api/<app>.md`` (and ``core_protocols.md``) delimit the
machine-owned region; narrative content must live outside that region (below END).

    <!-- SERVICE_API:GENERATED:START -->
    ... generated tables ...
    <!-- SERVICE_API:GENERATED:END -->
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_SERVICE_API = REPO_ROOT / "docs" / "service_api"

MARKER_START = "<!-- SERVICE_API:GENERATED:START -->"
MARKER_END = "<!-- SERVICE_API:GENERATED:END -->"

RETURN_TYPE_FALLBACK = "None"
SUMMARY_FALLBACK = "—"

SKIP_TOPLEVEL_DIRS = frozenset(
    {
        ".git",
        ".github",
        ".venv",
        "venv",
        "node_modules",
        "htmlcov",
        "staticfiles",
        "build",
        ".pytest_cache",
        ".tox",
        "site-packages",
        "__pycache__",
        "docs",
        "scripts",
        "code_cleaner",
        "woring_report",
    }
)


def _cell(text: str) -> str:
    t = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    t = t.replace("|", "\\|")
    t = " ".join(t.split())
    return t


def _display_return_type(annotation: str) -> str:
    return annotation.strip() or RETURN_TYPE_FALLBACK


def _display_summary(summary: str) -> str:
    return summary.strip() or SUMMARY_FALLBACK


def _first_paragraph_docstring(
    node: ast.AsyncFunctionDef | ast.FunctionDef | ast.ClassDef,
) -> str:
    raw = ast.get_docstring(node, clean=True)
    if not raw:
        return ""
    return raw.split("\n\n", 1)[0].strip()


def _unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if hasattr(ast, "unparse"):
        return ast.unparse(node).strip()
    raise RuntimeError("Python 3.9+ required (ast.unparse)")


def _format_args(func: ast.AsyncFunctionDef | ast.FunctionDef) -> str:
    parts: list[str] = []
    args = func.args
    n_args = len(args.args)
    n_defaults = len(args.defaults)
    first_default = n_args - n_defaults

    def arg_str(a: ast.arg, default: ast.expr | None) -> str:
        ann = _unparse(a.annotation) if a.annotation else ""
        base = f"{a.arg}: {ann}" if ann else a.arg
        if default is not None:
            base += f" = {_unparse(default)}"
        return base

    for a in args.posonlyargs:
        parts.append(arg_str(a, None))
    if args.posonlyargs:
        parts.append("/")
    for i, a in enumerate(args.args):
        default: ast.expr | None = None
        if i >= first_default:
            default = args.defaults[i - first_default]
        parts.append(arg_str(a, default))
    if args.vararg:
        va = args.vararg
        ann = _unparse(va.annotation) if va.annotation else ""
        parts.append(f"*{va.arg}" + (f": {ann}" if ann else ""))
    elif args.kwonlyargs:
        parts.append("*")
    for a, d in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        default = d
        ann = _unparse(a.annotation) if a.annotation else ""
        base = f"{a.arg}: {ann}" if ann else a.arg
        if default is not None:
            base += f" = {_unparse(default)}"
        parts.append(base)
    if args.kwarg:
        ka = args.kwarg
        ann = _unparse(ka.annotation) if ka.annotation else ""
        parts.append(f"**{ka.arg}" + (f": {ann}" if ann else ""))
    return ", ".join(parts)


@dataclass(frozen=True)
class ServiceFuncRow:
    name: str
    parameters: str
    return_type: str
    summary: str


def _extract_public_functions(source: str) -> list[ServiceFuncRow]:
    tree = ast.parse(source)
    rows: list[ServiceFuncRow] = []
    for node in tree.body:
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        if node.name.startswith("_"):
            continue
        ret = ""
        if node.returns:
            ret = _unparse(node.returns)
        rows.append(
            ServiceFuncRow(
                name=node.name,
                parameters=_format_args(node),
                return_type=ret,
                summary=_first_paragraph_docstring(node),
            )
        )
    rows.sort(key=lambda r: r.name)
    return rows


def _render_service_table(
    rows: Iterable[ServiceFuncRow],
    *,
    section_title: str = "## Public API (generated)",
) -> str:
    lines = [
        section_title,
        "",
        "| Function | Parameters | Return type | Summary |",
        "| --- | --- | --- | --- |",
    ]
    for r in rows:
        fn = f"`{r.name}`"
        lines.append(
            "| "
            + " | ".join(
                _cell(x)
                for x in (
                    fn,
                    r.parameters,
                    _display_return_type(r.return_type),
                    _display_summary(r.summary),
                )
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class ProtocolProperty:
    name: str
    type_ann: str


@dataclass(frozen=True)
class ProtocolRow:
    name: str
    summary: str
    properties: tuple[ProtocolProperty, ...]


def _extract_protocols(
    source: str,
) -> tuple[list[ProtocolRow], list[ServiceFuncRow]]:
    tree = ast.parse(source)
    protocols: list[ProtocolRow] = []
    helpers: list[ServiceFuncRow] = []

    for node in tree.body:
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            if not node.name.startswith("_"):
                ret = _unparse(node.returns) if node.returns else ""
                helpers.append(
                    ServiceFuncRow(
                        name=node.name,
                        parameters=_format_args(node),
                        return_type=ret,
                        summary=_first_paragraph_docstring(node),
                    )
                )
        elif isinstance(node, ast.ClassDef):
            if not _class_has_runtime_checkable(node):
                continue
            if not _bases_protocol(node):
                continue
            props: list[ProtocolProperty] = []
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(
                    item.target, ast.Name
                ):
                    # rare
                    continue
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name == "__init__":
                        continue
                    if _is_property_method(item):
                        ann = ""
                        if item.returns:
                            ann = _unparse(item.returns)
                        props.append(ProtocolProperty(name=item.name, type_ann=ann))
            protocols.append(
                ProtocolRow(
                    name=node.name,
                    summary=_first_paragraph_docstring(node),
                    properties=tuple(props),
                )
            )

    protocols.sort(key=lambda p: p.name)
    helpers.sort(key=lambda r: r.name)
    return protocols, helpers


def _class_has_runtime_checkable(node: ast.ClassDef) -> bool:
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == "runtime_checkable":
            return True
        if isinstance(dec, ast.Attribute) and dec.attr == "runtime_checkable":
            return True
        if isinstance(dec, ast.Call):
            if isinstance(dec.func, ast.Name) and dec.func.id == "runtime_checkable":
                return True
            if (
                isinstance(dec.func, ast.Attribute)
                and dec.func.attr == "runtime_checkable"
            ):
                return True
    return False


def _bases_protocol(node: ast.ClassDef) -> bool:
    for b in node.bases:
        if isinstance(b, ast.Name) and b.id == "Protocol":
            return True
        if isinstance(b, ast.Attribute) and b.attr == "Protocol":
            return True
        if isinstance(b, ast.Subscript):
            if isinstance(b.value, ast.Name) and b.value.id == "Protocol":
                return True
    return False


def _is_property_method(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == "property":
            return True
        if isinstance(dec, ast.Attribute) and dec.attr == "property":
            return True
    return False


def _render_protocols_page(
    protocols: list[ProtocolRow], helpers: list[ServiceFuncRow]
) -> str:
    chunks: list[str] = ["## Protocol types (generated)", ""]
    for p in protocols:
        chunks.append(f"### `{p.name}`")
        if p.summary:
            chunks.append("")
            chunks.append(p.summary)
        chunks.append("")
        chunks.append("| Property | Type |")
        chunks.append("| --- | --- |")
        for pr in p.properties:
            chunks.append(f"| `{pr.name}` | {_cell(pr.type_ann)} |")
        chunks.append("")
    if helpers:
        chunks.append(
            _render_service_table(
                helpers, section_title="## Module functions (generated)"
            )
        )
    return "\n".join(chunks).rstrip() + "\n"


def _discover_apps_with_services() -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    for child in sorted(REPO_ROOT.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        if child.name in SKIP_TOPLEVEL_DIRS:
            continue
        svc = child / "services.py"
        if svc.is_file():
            content = _read_text(svc)
            if "This service should be skipped for docs generation" in content:
                continue
            found.append((child.name, svc))
    return found


def _splice_generated(existing: str, generated: str) -> str:
    if MARKER_START not in existing:
        raise ValueError(
            f"missing {MARKER_START!r}; add markers or see CONTRIBUTING.md"
        )
    head, mid_and_tail = existing.split(MARKER_START, 1)

    if MARKER_END not in mid_and_tail:
        raise ValueError(f"missing {MARKER_END!r}")

    _, tail = mid_and_tail.split(MARKER_END, 1)
    gen_block = f"{MARKER_START}\n\n{generated.rstrip()}\n\n{MARKER_END}"
    return f"{head.rstrip()}\n{gen_block}{tail}"


def _normalize_eol(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_normalize_eol(content), encoding="utf-8", newline="\n")


def _build_generated_for_services_py(path: Path) -> str:
    source = _read_text(path)
    rows = _extract_public_functions(source)
    return _render_service_table(rows)


def _build_generated_for_protocols(path: Path) -> str:
    source = _read_text(path)
    protos, helpers = _extract_protocols(source)
    return _render_protocols_page(protos, helpers)


def _doc_path_for_app(app: str) -> Path:
    return DOCS_SERVICE_API / f"{app}.md"


def _generate_one_app(app: str, services_path: Path, check: bool) -> bool:
    doc_path = _doc_path_for_app(app)
    generated = _build_generated_for_services_py(services_path)
    if not doc_path.is_file():
        raise FileNotFoundError(
            f"expected {doc_path.relative_to(REPO_ROOT)}; "
            "create it with header, markers, and optional manual tail"
        )
    old = _read_text(doc_path)
    new = _normalize_eol(_splice_generated(old, generated))
    if check:
        return _normalize_eol(old) == new
    _write_text(doc_path, new)
    return True


def _generate_protocols(check: bool) -> bool:
    proto_path = REPO_ROOT / "core" / "protocols.py"
    doc_path = _doc_path_for_app("core_protocols")
    generated = _build_generated_for_protocols(proto_path)
    if not doc_path.is_file():
        raise FileNotFoundError(f"expected {doc_path.relative_to(REPO_ROOT)}")
    old = _read_text(doc_path)
    new = _normalize_eol(_splice_generated(old, generated))
    if check:
        return _normalize_eol(old) == new
    _write_text(doc_path, new)
    return True


def _run_all(check: bool, only_app: str | None) -> int:
    ok = True
    if only_app:
        if only_app == "core_protocols":
            if not _generate_protocols(check):
                ok = False
            return 0 if ok else 1
        for app, p in _discover_apps_with_services():
            if app == only_app:
                if not _generate_one_app(app, p, check):
                    ok = False
                return 0 if ok else 1
        print(f"unknown app: {only_app}", file=sys.stderr)
        return 2

    for app, p in _discover_apps_with_services():
        if not _generate_one_app(app, p, check):
            ok = False
    if not _generate_protocols(check):
        ok = False
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit with status 1 if generated content differs from committed files",
    )
    parser.add_argument(
        "--app", type=str, default=None, help="only regenerate one app module"
    )
    args = parser.parse_args()

    try:
        code = _run_all(args.check, args.app)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    if args.check and code != 0:
        print(
            "Service API docs are out of date. Run: python scripts/generate_service_docs.py",
            file=sys.stderr,
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
