#!/usr/bin/env python3
"""Write core/_version.py for environments without a full Git checkout (e.g. Docker)."""

from __future__ import annotations

import tomllib
from pathlib import Path


def _load_scm_config(root: Path) -> tuple[str, str, str]:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    scm = data["tool"]["setuptools_scm"]
    return (
        scm["write_to"],
        scm["write_to_template"],
        scm["fallback_version"],
    )


def resolve_version(root: Path, fallback_version: str) -> str:
    try:
        from setuptools_scm import get_version
    except ImportError:
        return fallback_version

    try:
        return get_version(root=str(root))
    except LookupError:
        return fallback_version


def write_version_file(root: Path | None = None) -> Path:
    root = root or Path(__file__).resolve().parents[1]
    write_to, template, fallback = _load_scm_config(root)
    version = resolve_version(root, fallback)
    target = root / write_to
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(template.format(version=version), encoding="utf-8")
    return target


def main() -> None:
    target = write_version_file()
    for line in target.read_text(encoding="utf-8").splitlines():
        if line.startswith("version = "):
            print(f"Wrote {target} ({line})")
            return
    print(f"Wrote {target}")


if __name__ == "__main__":
    main()
