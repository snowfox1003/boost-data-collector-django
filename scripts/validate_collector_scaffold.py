#!/usr/bin/env python3
"""
Create a throwaway collector app under .test_artifacts/ and verify ruff + pyright pass.

Run from repo root: python scripts/validate_collector_scaffold.py
CI: invoked after dependencies are installed (see .github/workflows/actions.yml).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# Must not collide with any INSTALLED_APPS name.
APP_LABEL = "zzcollectorscaffoldci"
SCRATCH_PARENT = REPO_ROOT / ".test_artifacts" / "collector_scaffold_probe"


def main() -> int:
    SCRATCH_PARENT.mkdir(parents=True, exist_ok=True)
    app_dir = SCRATCH_PARENT / APP_LABEL
    if app_dir.exists():
        shutil.rmtree(app_dir)

    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "manage.py"),
            "startcollector",
            APP_LABEL,
            "--path",
            str(SCRATCH_PARENT),
        ],
        cwd=str(REPO_ROOT),
        check=True,
    )

    subprocess.run(
        ["uv", "run", "--with", "ruff", "ruff", "check", str(app_dir)],
        cwd=str(REPO_ROOT),
        check=True,
    )

    cfg_path = SCRATCH_PARENT / "pyrightconfig.json"
    cfg = {
        "include": [APP_LABEL],
        "exclude": [
            "**/migrations/**",
            "**/tests/**",
            "**/._*",
            "**/.___*",
        ],
        "pythonVersion": "3.11",
        "typeCheckingMode": "basic",
        "reportMissingImports": True,
        "extraPaths": ["../.."],
    }
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

    subprocess.run(
        ["uv", "run", "pyright", "--project", str(SCRATCH_PARENT)],
        cwd=str(SCRATCH_PARENT),
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
