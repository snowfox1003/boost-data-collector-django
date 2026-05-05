"""Tests for import_boost_dependencies command and module helpers."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from model_bakery import baker

from boost_library_tracker.management.commands import import_boost_dependencies as ibd
from boost_library_tracker.models import BoostDependency, BoostLibrary, BoostVersion


def test_parse_deps_stdout_basic():
    text = "algorithm -> utility core\n\nignore me\nfoo -> bar baz\n"
    out = ibd._parse_deps_stdout(text)
    assert out == [
        ("algorithm", ["utility", "core"]),
        ("foo", ["bar", "baz"]),
    ]


def test_boost_tag_minor_version():
    assert ibd._boost_tag_minor_version("boost-1.84.0") == 84
    assert ibd._boost_tag_minor_version("nope") is None


@pytest.mark.django_db
def test_get_tags_to_process_explicit_and_all(tmp_path):
    clone = tmp_path / "boost"
    clone.mkdir()
    baker.make(BoostVersion, version="boost-1.84.0")
    tags = ibd._get_tags_to_process(clone, "boost-1.84.0")
    assert tags == ["boost-1.84.0"]
    all_tags = ibd._get_tags_to_process(clone, "all")
    assert "boost-1.84.0" in all_tags


@pytest.mark.django_db
def test_get_tags_to_process_new_tags_from_git(tmp_path):
    clone = tmp_path / "boost"
    clone.mkdir()
    baker.make(BoostVersion, version="boost-1.84.0")
    with patch.object(
        ibd, "_get_git_boost_tags", return_value=["boost-1.84.0", "boost-1.99.0"]
    ):
        new_only = ibd._get_tags_to_process(clone, None)
    assert new_only == ["boost-1.99.0"]


@pytest.mark.django_db
def test_library_by_name_mapping_numeric_ublas(boost_library_repository):
    baker.make(BoostLibrary, repo=boost_library_repository, name="uBLAS")
    cache = ibd._build_library_cache()
    hit = ibd._library_by_name("numeric~ublas", cache=cache)
    assert hit is not None
    assert hit.name == "uBLAS"


@pytest.mark.django_db
def test_normalize_boostdep_name_candidates():
    c = ibd._normalize_boostdep_name_to_db_candidates("numeric~conversion")
    assert any("Numeric Conversion" in x for x in c)


@pytest.mark.django_db
def test_import_deps_command_prepare_fails_short_circuits(tmp_path):
    with patch.object(ibd, "_prepare_boost_clone_for_import", return_value=False):
        call_command(
            "import_boost_dependencies",
            "--clone-dir",
            str(tmp_path / "c"),
        )


@pytest.mark.django_db
def test_import_deps_dry_run_logs_tag_count(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    with patch.object(
        ibd, "_prepare_boost_clone_for_import", return_value=True
    ), patch.object(
        ibd,
        "_get_tags_to_process",
        return_value=["boost-1.84.0", "boost-1.85.0"],
    ):
        call_command(
            "import_boost_dependencies",
            "--dry-run",
            "--clone-dir",
            str(tmp_path / "c"),
        )
    assert any("Tags to process: 2" in r.message for r in caplog.records)


@pytest.mark.django_db
def test_import_deps_no_tags_logs_error(tmp_path, caplog):
    caplog.set_level(logging.ERROR)
    with patch.object(
        ibd, "_prepare_boost_clone_for_import", return_value=True
    ), patch.object(
        ibd,
        "_get_tags_to_process",
        return_value=[],
    ):
        call_command("import_boost_dependencies", "--clone-dir", str(tmp_path / "c"))
    assert any("No tags to process" in r.message for r in caplog.records)


@pytest.mark.django_db
def test_import_deps_writes_dependencies(tmp_path, boost_library_repository):
    client = baker.make(
        BoostLibrary,
        repo=boost_library_repository,
        name="AlgorithmClient",
    )
    dep = baker.make(BoostLibrary, repo=boost_library_repository, name="AlgorithmDep")
    ver = baker.make(BoostVersion, version="boost-1.84.0")

    def fake_gen(_clone: Path, tags: list[str]):
        yield tags[0], [("AlgorithmClient", ["AlgorithmDep"])]

    with patch.object(
        ibd, "_prepare_boost_clone_for_import", return_value=True
    ), patch.object(
        ibd,
        "_get_tags_to_process",
        return_value=["boost-1.84.0"],
    ), patch.object(
        ibd, "_generate_deps_output", side_effect=fake_gen
    ):
        call_command("import_boost_dependencies", "--clone-dir", str(tmp_path / "c"))

    assert BoostDependency.objects.filter(
        client_library=client,
        dep_library=dep,
        version=ver,
    ).exists()


@pytest.mark.django_db
def test_import_deps_skips_unknown_library(tmp_path, caplog, boost_library_repository):
    caplog.set_level(logging.INFO)
    baker.make(BoostLibrary, repo=boost_library_repository, name="Known")

    def fake_gen(_clone: Path, tags: list[str]):
        yield tags[0], [("MissingClient", ["Known"])]

    with patch.object(
        ibd, "_prepare_boost_clone_for_import", return_value=True
    ), patch.object(
        ibd,
        "_get_tags_to_process",
        return_value=["boost-1.84.0"],
    ), patch.object(
        ibd, "_generate_deps_output", side_effect=fake_gen
    ):
        call_command("import_boost_dependencies", "--clone-dir", str(tmp_path / "c"))

    assert any("skipped (no library)" in r.message for r in caplog.records)


def test_prepare_boost_clone_fetch_tags_failure(tmp_path):
    d = tmp_path / "boost"
    d.mkdir()
    (d / ".git").mkdir()
    with patch.object(ibd, "_fetch_tags", return_value=False):
        assert ibd._prepare_boost_clone_for_import(d) is False


def test_prepare_boost_clone_submodule_init_failure(tmp_path):
    d = tmp_path / "boost"
    d.mkdir()
    (d / ".git").mkdir()
    with patch.object(ibd, "_fetch_tags", return_value=True), patch.object(
        ibd, "_init_submodules", return_value=(False, "submodule failed")
    ):
        assert ibd._prepare_boost_clone_for_import(d) is False


def test_prepare_boost_clone_build_boostdep_failure(tmp_path):
    d = tmp_path / "boost"
    d.mkdir()
    (d / ".git").mkdir()
    with patch.object(ibd, "_fetch_tags", return_value=True), patch.object(
        ibd, "_init_submodules", return_value=(True, "")
    ), patch.object(ibd, "_build_boostdep", return_value=False):
        assert ibd._prepare_boost_clone_for_import(d) is False


def test_ensure_clone_when_git_present(tmp_path):
    d = tmp_path / "boost"
    d.mkdir()
    (d / ".git").mkdir()
    assert ibd._ensure_clone(d) is True


def test_ensure_clone_invokes_git_clone(tmp_path):
    d = tmp_path / "boost"
    with patch(
        "boost_library_tracker.management.commands.import_boost_dependencies.subprocess.run",
        return_value=MagicMock(returncode=0),
    ) as run_mock:
        ok = ibd._ensure_clone(d)
    assert ok is True
    assert run_mock.called


def test_ensure_clone_git_missing_returns_false(tmp_path):
    with patch(
        "boost_library_tracker.management.commands.import_boost_dependencies.subprocess.run",
        side_effect=FileNotFoundError("git"),
    ):
        assert ibd._ensure_clone(tmp_path / "boost") is False


def test_fetch_tags_failure(tmp_path):
    d = tmp_path / "boost"
    d.mkdir()
    with patch(
        "boost_library_tracker.management.commands.import_boost_dependencies.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, ["git"]),
    ):
        assert ibd._fetch_tags(d) is False


def test_fetch_tags_success(tmp_path):
    d = tmp_path / "boost"
    d.mkdir()
    with patch(
        "boost_library_tracker.management.commands.import_boost_dependencies.subprocess.run",
        return_value=MagicMock(returncode=0),
    ):
        assert ibd._fetch_tags(d) is True


def test_fetch_tags_file_not_found(tmp_path):
    d = tmp_path / "boost"
    d.mkdir()
    with patch(
        "boost_library_tracker.management.commands.import_boost_dependencies.subprocess.run",
        side_effect=FileNotFoundError("git"),
    ):
        assert ibd._fetch_tags(d) is False


def test_init_submodules_nonzero():
    d = Path(".")
    proc = MagicMock(returncode=1, stdout="o", stderr="e")
    with patch(
        "boost_library_tracker.management.commands.import_boost_dependencies.subprocess.run",
        return_value=proc,
    ):
        ok, err = ibd._init_submodules(d)
    assert ok is False
    assert err


def test_init_submodules_success():
    with patch(
        "boost_library_tracker.management.commands.import_boost_dependencies.subprocess.run",
        return_value=MagicMock(returncode=0, stdout="", stderr=""),
    ):
        ok, err = ibd._init_submodules(Path("."))
    assert ok is True
    assert err == ""


def test_init_submodules_filenotfound():
    with patch(
        "boost_library_tracker.management.commands.import_boost_dependencies.subprocess.run",
        side_effect=FileNotFoundError("git"),
    ):
        ok, err = ibd._init_submodules(Path("."))
    assert ok is False


def test_get_git_boost_tags_subprocess_error(tmp_path):
    d = tmp_path / "boost"
    d.mkdir()
    with patch(
        "boost_library_tracker.management.commands.import_boost_dependencies.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, "git"),
    ):
        assert ibd._get_git_boost_tags(d) == []


def test_get_git_boost_tags_filters_non_matching_lines(tmp_path):
    d = tmp_path / "boost"
    d.mkdir()
    out = "refs/heads/main\nnot-a-tag\nboost-1.84.0\n"
    with patch(
        "boost_library_tracker.management.commands.import_boost_dependencies.subprocess.run",
        return_value=MagicMock(returncode=0, stdout=out, stderr=""),
    ):
        tags = ibd._get_git_boost_tags(d)
    assert tags == ["boost-1.84.0"]


def test_build_boostdep_skips_when_binary_exists(tmp_path):
    d = tmp_path / "boost"
    bindir = d / "dist" / "bin"
    bindir.mkdir(parents=True)
    fname = "boostdep.exe" if sys.platform == "win32" else "boostdep"
    (bindir / fname).write_text("", encoding="utf-8")
    assert ibd._build_boostdep(d) is True


def test_generate_deps_output_no_tags():
    assert list(ibd._generate_deps_output(Path("."), [])) == []


def test_generate_deps_output_checkout_failure(tmp_path, caplog):
    caplog.set_level("WARNING")
    clone = tmp_path / "boost"
    bindir = clone / "dist" / "bin"
    bindir.mkdir(parents=True)
    fname = "boostdep.exe" if sys.platform == "win32" else "boostdep"
    (bindir / fname).write_text("", encoding="utf-8")

    def run_side_effect(cmd, **_kw):
        args = list(cmd) if isinstance(cmd, (list, tuple)) else [cmd]
        if len(args) >= 3 and args[:2] == ["git", "checkout"]:
            raise subprocess.CalledProcessError(1, args)
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch(
        "boost_library_tracker.management.commands.import_boost_dependencies.subprocess.run",
        side_effect=run_side_effect,
    ):
        assert list(ibd._generate_deps_output(clone, ["boost-1.84.0"])) == []
    assert any(
        "checkout" in r.message.lower() or "failed" in r.message.lower()
        for r in caplog.records
    )


@pytest.mark.skipif(
    sys.platform != "darwin", reason="AppleDouble cleanup runs only on macOS"
)
def test_remove_macos_appledouble_removes_dot_underscore(tmp_path):
    d = tmp_path / "clone"
    d.mkdir()
    junk = d / "._x"
    junk.write_text("y", encoding="utf-8")
    removed = ibd._remove_macos_appledouble_files(d)
    assert removed >= 1
    assert not junk.exists()


def test_generate_deps_output_boostdep_success(tmp_path):
    clone = tmp_path / "boost"
    bindir = clone / "dist" / "bin"
    bindir.mkdir(parents=True)
    fname = "boostdep.exe" if sys.platform == "win32" else "boostdep"
    (bindir / fname).write_text("", encoding="utf-8")

    def run(cmd, **_kw):
        joined = " ".join(str(x) for x in cmd)
        if "checkout" in joined:
            return MagicMock(returncode=0, stdout="", stderr="")
        if "submodule" in joined and "update" in joined:
            return MagicMock(returncode=0, stdout="", stderr="")
        if "clean" in joined and "-dff" in joined:
            return MagicMock(returncode=0, stdout="", stderr="")
        if "boostdep" in joined.lower():
            return MagicMock(returncode=0, stdout="algo -> utility core\n", stderr="")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch(
        "boost_library_tracker.management.commands.import_boost_dependencies.subprocess.run",
        side_effect=run,
    ):
        pairs = list(ibd._generate_deps_output(clone, ["boost-1.84.0"]))
    assert pairs == [("boost-1.84.0", [("algo", ["utility", "core"])])]


def test_prepare_boost_clone_returns_false_when_ensure_clone_fails(tmp_path):
    with patch.object(ibd, "_ensure_clone", return_value=False):
        assert ibd._prepare_boost_clone_for_import(tmp_path / "missing") is False


def test_prepare_boost_clone_succeeds_when_steps_pass(tmp_path):
    root = tmp_path / "boost"
    root.mkdir()
    (root / ".git").mkdir()
    with patch.object(ibd.sys, "platform", "linux"), patch.object(
        ibd, "_fetch_tags", return_value=True
    ), patch.object(ibd, "_init_submodules", return_value=(True, "")), patch.object(
        ibd, "_build_boostdep", return_value=True
    ), patch.object(
        ibd, "_remove_macos_appledouble_files", return_value=0
    ):
        assert ibd._prepare_boost_clone_for_import(root) is True


def test_ensure_clone_git_clone_process_error(tmp_path):
    with patch(
        "boost_library_tracker.management.commands.import_boost_dependencies.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, ["git"]),
    ):
        assert ibd._ensure_clone(tmp_path / "fresh") is False


def test_enable_git_long_paths_swallows_subprocess_errors(tmp_path):
    clone = tmp_path / "boost"
    clone.mkdir()
    n = {"i": 0}

    def run_side_effect(*_a, **_k):
        n["i"] += 1
        if n["i"] == 1:
            return MagicMock(returncode=0)
        raise subprocess.CalledProcessError(1, ["git"])

    with patch(
        "boost_library_tracker.management.commands.import_boost_dependencies.subprocess.run",
        side_effect=run_side_effect,
    ):
        ibd._enable_git_long_paths(clone)


def test_remove_macos_appledouble_when_platform_is_darwin(tmp_path):
    root = tmp_path / "clone"
    root.mkdir()
    junk = root / "._noise"
    junk.write_text("x", encoding="utf-8")
    with patch.object(ibd.sys, "platform", "darwin"):
        removed = ibd._remove_macos_appledouble_files(root)
    assert removed == 1
    assert not junk.exists()


def test_remove_macos_appledouble_oserror_on_unlink_is_ignored(tmp_path):
    root = tmp_path / "clone"
    root.mkdir()
    junk = root / "._blocked"
    junk.write_text("x", encoding="utf-8")

    orig_unlink = Path.unlink

    def bad_unlink(self, *a, **k):
        if self.name.startswith("._"):
            raise OSError("nope")
        return orig_unlink(self, *a, **k)

    with patch.object(ibd.sys, "platform", "darwin"), patch.object(
        Path, "unlink", bad_unlink
    ):
        assert ibd._remove_macos_appledouble_files(root) == 0


def test_build_boostdep_windows_bootstrap_failure(tmp_path):
    clone = tmp_path / "boost"
    clone.mkdir()
    with patch.object(ibd.sys, "platform", "win32"), patch(
        "boost_library_tracker.management.commands.import_boost_dependencies.subprocess.run",
        return_value=MagicMock(returncode=1, stdout="out", stderr="err"),
    ):
        assert ibd._build_boostdep(clone) is False


def test_build_boostdep_unix_bootstrap_failure(tmp_path):
    clone = tmp_path / "boost"
    clone.mkdir()
    with patch.object(ibd.sys, "platform", "linux"), patch(
        "boost_library_tracker.management.commands.import_boost_dependencies.subprocess.run",
        return_value=MagicMock(returncode=1, stdout="o", stderr="e"),
    ):
        assert ibd._build_boostdep(clone) is False


def test_build_boostdep_b2_missing_after_bootstrap(tmp_path):
    clone = tmp_path / "boost"
    clone.mkdir()
    with patch.object(ibd.sys, "platform", "win32"), patch(
        "boost_library_tracker.management.commands.import_boost_dependencies.subprocess.run",
        return_value=MagicMock(returncode=0, stdout="", stderr=""),
    ):
        assert ibd._build_boostdep(clone) is False


def test_build_boostdep_b2_compile_failure(tmp_path):
    clone = tmp_path / "boost"
    clone.mkdir()
    (clone / "b2.exe").write_text("", encoding="utf-8")

    def run_side_effect(cmd, **_kw):
        if (
            isinstance(cmd, (list, tuple))
            and cmd
            and Path(cmd[0]).name.startswith("b2")
        ):
            return MagicMock(returncode=1, stdout="x", stderr="y")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch.object(ibd.sys, "platform", "win32"), patch(
        "boost_library_tracker.management.commands.import_boost_dependencies.subprocess.run",
        side_effect=run_side_effect,
    ):
        assert ibd._build_boostdep(clone) is False


def test_build_boostdep_darwin_retries_b2_with_clang(tmp_path):
    clone = tmp_path / "boost"
    clone.mkdir()
    (clone / "b2").write_text("", encoding="utf-8")

    def run_side_effect(cmd, **_kw):
        joined = " ".join(str(c) for c in cmd)
        if "bootstrap.sh" in joined:
            return MagicMock(returncode=0, stdout="", stderr="")
        if "toolset=clang" in joined:
            return MagicMock(returncode=0, stdout="", stderr="")
        exe = Path(cmd[0]).name if cmd else ""
        if exe == "b2":
            return MagicMock(returncode=1, stdout="", stderr="first")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch.object(ibd.sys, "platform", "darwin"), patch(
        "boost_library_tracker.management.commands.import_boost_dependencies.subprocess.run",
        side_effect=run_side_effect,
    ):
        assert ibd._build_boostdep(clone) is True


def test_build_boostdep_subprocess_raises_file_not_found(tmp_path):
    clone = tmp_path / "boost"
    clone.mkdir()
    with patch.object(ibd.sys, "platform", "win32"), patch(
        "boost_library_tracker.management.commands.import_boost_dependencies.subprocess.run",
        side_effect=FileNotFoundError("cmd"),
    ):
        assert ibd._build_boostdep(clone) is False


def test_generate_deps_output_win32_retries_submodule_update(tmp_path):
    clone = tmp_path / "boost"
    bindir = clone / "dist" / "bin"
    bindir.mkdir(parents=True)
    (bindir / "boostdep.exe").write_text("", encoding="utf-8")
    sm_calls: list[int] = []

    def run(cmd, **_kw):
        joined = " ".join(str(c) for c in cmd)
        if "checkout" in joined:
            return MagicMock(returncode=0, stdout="", stderr="")
        if "submodule" in joined and "update" in joined:
            sm_calls.append(1)
            if len(sm_calls) == 1:
                return MagicMock(returncode=1, stdout="", stderr="long")
            return MagicMock(returncode=0, stdout="", stderr="")
        if "clean" in joined and "-dff" in joined:
            return MagicMock(returncode=0, stdout="", stderr="")
        if "boostdep" in joined.lower():
            return MagicMock(returncode=0, stdout="x -> y\n", stderr="")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch.object(ibd.sys, "platform", "win32"), patch(
        "boost_library_tracker.management.commands.import_boost_dependencies.subprocess.run",
        side_effect=run,
    ):
        pairs = list(ibd._generate_deps_output(clone, ["boost-1.84.0"]))
    assert len(sm_calls) == 2
    assert pairs == [("boost-1.84.0", [("x", ["y"])])]


def test_generate_deps_output_submodule_fails_after_windows_retry(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    clone = tmp_path / "boost"
    bindir = clone / "dist" / "bin"
    bindir.mkdir(parents=True)
    (bindir / "boostdep.exe").write_text("", encoding="utf-8")

    def run(cmd, **_kw):
        joined = " ".join(str(c) for c in cmd)
        if "checkout" in joined:
            return MagicMock(returncode=0, stdout="", stderr="")
        if "submodule" in joined and "update" in joined:
            return MagicMock(returncode=1, stdout="", stderr="fail")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch.object(ibd.sys, "platform", "win32"), patch(
        "boost_library_tracker.management.commands.import_boost_dependencies.subprocess.run",
        side_effect=run,
    ):
        assert list(ibd._generate_deps_output(clone, ["boost-1.84.0"])) == []
    assert caplog.records


def test_generate_deps_output_boostdep_nonzero_exit(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    clone = tmp_path / "boost"
    bindir = clone / "dist" / "bin"
    bindir.mkdir(parents=True)
    fname = "boostdep.exe" if sys.platform == "win32" else "boostdep"
    (bindir / fname).write_text("", encoding="utf-8")

    def run(cmd, **_kw):
        joined = " ".join(str(c) for c in cmd)
        if "checkout" in joined:
            return MagicMock(returncode=0, stdout="", stderr="")
        if "submodule" in joined and "update" in joined:
            return MagicMock(returncode=0, stdout="", stderr="")
        if "clean" in joined:
            return MagicMock(returncode=0, stdout="", stderr="")
        if "boostdep" in joined.lower():
            return MagicMock(returncode=1, stdout="", stderr="bad")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch(
        "boost_library_tracker.management.commands.import_boost_dependencies.subprocess.run",
        side_effect=run,
    ):
        assert list(ibd._generate_deps_output(clone, ["boost-1.84.0"])) == []
    assert any("boostdep failed" in r.message for r in caplog.records)


def test_generate_deps_output_boostdep_raises_file_not_found(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    clone = tmp_path / "boost"
    bindir = clone / "dist" / "bin"
    bindir.mkdir(parents=True)
    fname = "boostdep.exe" if sys.platform == "win32" else "boostdep"
    (bindir / fname).write_text("", encoding="utf-8")

    def run(cmd, **_kw):
        joined = " ".join(str(c) for c in cmd)
        if "checkout" in joined:
            return MagicMock(returncode=0, stdout="", stderr="")
        if "submodule" in joined and "update" in joined:
            return MagicMock(returncode=0, stdout="", stderr="")
        if "clean" in joined:
            return MagicMock(returncode=0, stdout="", stderr="")
        if "boostdep" in joined.lower():
            raise FileNotFoundError("boostdep")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch(
        "boost_library_tracker.management.commands.import_boost_dependencies.subprocess.run",
        side_effect=run,
    ):
        assert list(ibd._generate_deps_output(clone, ["boost-1.84.0"])) == []
    assert caplog.records


@pytest.mark.django_db
def test_library_by_name_queries_database_when_no_cache(boost_library_repository):
    lib = baker.make(BoostLibrary, repo=boost_library_repository, name="DirectHit")
    assert ibd._library_by_name("DirectHit", cache=None) == lib


@pytest.mark.django_db
def test_library_by_name_matches_underscore_variants(boost_library_repository):
    baker.make(BoostLibrary, repo=boost_library_repository, name="Nice Title")
    hit = ibd._library_by_name("nice_title", cache=None)
    assert hit is not None
    assert hit.name == "Nice Title"


@pytest.mark.django_db
def test_library_by_name_skips_repeated_candidate_entries(boost_library_repository):
    with patch.object(
        ibd,
        "_normalize_boostdep_name_to_db_candidates",
        return_value=["Ghost", "Ghost"],
    ):
        assert ibd._library_by_name("Ghost", cache=None) is None


@pytest.mark.django_db
def test_import_deps_skips_unknown_dependency_library(
    tmp_path, caplog, boost_library_repository
):
    caplog.set_level(logging.INFO)
    client = baker.make(BoostLibrary, repo=boost_library_repository, name="OnlyClient")

    def fake_gen(_clone: Path, tags: list[str]):
        yield tags[0], [(client.name, ["MissingDep"])]

    with patch.object(
        ibd, "_prepare_boost_clone_for_import", return_value=True
    ), patch.object(
        ibd,
        "_get_tags_to_process",
        return_value=["boost-1.84.0"],
    ), patch.object(
        ibd, "_generate_deps_output", side_effect=fake_gen
    ):
        call_command("import_boost_dependencies", "--clone-dir", str(tmp_path / "c"))

    assert any("skipped (no library)" in r.message for r in caplog.records)


@pytest.mark.django_db
def test_import_deps_duplicate_dependency_does_not_increment_added(
    tmp_path, boost_library_repository
):
    client = baker.make(BoostLibrary, repo=boost_library_repository, name="C1")
    dep = baker.make(BoostLibrary, repo=boost_library_repository, name="D1")

    def fake_gen(_clone: Path, tags: list[str]):
        yield tags[0], [(client.name, [dep.name])]

    with patch.object(
        ibd, "_prepare_boost_clone_for_import", return_value=True
    ), patch.object(
        ibd,
        "_get_tags_to_process",
        return_value=["boost-1.84.0"],
    ), patch.object(
        ibd, "_generate_deps_output", side_effect=fake_gen
    ), patch.object(
        ibd, "add_boost_dependency", return_value=(None, False)
    ):
        call_command("import_boost_dependencies", "--clone-dir", str(tmp_path / "c"))

    assert BoostDependency.objects.count() == 0
