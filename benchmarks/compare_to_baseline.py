#!/usr/bin/env python3
"""
Compare pytest-benchmark JSON (--benchmark-json) against benchmarks/baselines.json.

Exits with status 1 if any baseline median exceeds baseline_median * regression_ratio.
Default ratio is 1.10 (10% slower); override with --regression-ratio or
BENCHMARK_REGRESSION_RATIO.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

DEFAULT_REGRESSION_RATIO = 1.10


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare benchmark JSON to checked-in median baselines."
    )
    parser.add_argument(
        "results_json",
        type=Path,
        help="Path written by pytest-benchmark --benchmark-json",
    )
    parser.add_argument(
        "baselines_json",
        type=Path,
        help="Path to benchmarks/baselines.json",
    )
    env_ratio = os.environ.get("BENCHMARK_REGRESSION_RATIO")
    if env_ratio:
        try:
            default_ratio = float(env_ratio)
        except ValueError:
            parser.error("BENCHMARK_REGRESSION_RATIO must be a number (e.g. 1.10)")
        if default_ratio <= 0:
            parser.error("BENCHMARK_REGRESSION_RATIO must be > 0")
    else:
        default_ratio = DEFAULT_REGRESSION_RATIO
    parser.add_argument(
        "--regression-ratio",
        type=float,
        default=default_ratio,
        metavar="R",
        help=(
            f"Fail if median > baseline_median * R "
            f"(default {default_ratio}; env BENCHMARK_REGRESSION_RATIO)"
        ),
    )
    args = parser.parse_args()

    results = json.loads(args.results_json.read_text(encoding="utf-8"))
    baselines_doc = json.loads(args.baselines_json.read_text(encoding="utf-8"))

    bench_by_name = {b["fullname"]: b for b in results.get("benchmarks", [])}
    expected: dict[str, dict] = baselines_doc.get("benchmarks", {})

    failures: list[str] = []
    warnings: list[str] = []

    for fullname, spec in expected.items():
        if spec.get("skip"):
            continue
        ref = spec.get("median_seconds")
        if ref is None:
            warnings.append(f"{fullname}: baseline has no median_seconds; skipping")
            continue

        bench = bench_by_name.get(fullname)
        if bench is None:
            failures.append(f"{fullname}: missing from benchmark results")
            continue

        median = float(bench["stats"]["median"])
        exp_n = spec.get("n")
        if exp_n is not None:
            got_n = bench.get("extra_info", {}).get("n")
            if got_n is not None and int(got_n) != int(exp_n):
                warnings.append(
                    f"{fullname}: baseline n={exp_n} but run reported n={got_n} "
                    "(set BENCHMARK_COMMIT_N to match baselines.json)"
                )

        limit = float(ref) * float(args.regression_ratio)
        if median > limit:
            failures.append(
                f"{fullname}: median {median:.6f}s exceeds limit {limit:.6f}s "
                f"(baseline {float(ref):.6f}s x {args.regression_ratio})"
            )

    for line in warnings:
        print(f"WARNING: {line}", file=sys.stderr)
    for line in failures:
        print(f"FAIL: {line}", file=sys.stderr)

    if failures:
        print(
            f"Benchmark regression check failed ({len(failures)} scenario(s)).",
            file=sys.stderr,
        )
        return 1
    print("Benchmark regression check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
