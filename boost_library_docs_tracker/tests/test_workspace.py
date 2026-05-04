"""Tests for boost_library_docs_tracker.workspace path helpers."""

from __future__ import annotations


import pytest

from boost_library_docs_tracker.workspace import (
    _source_version_dirname,
    _url_version,
    get_converted_root,
    get_extract_dir,
    get_page_path,
    get_zip_dir,
    load_page_by_url,
    resolve_path_from_url,
    save_page,
)


@pytest.fixture
def workspace_root(settings, tmp_path):
    settings.WORKSPACE_DIR = str(tmp_path)
    return tmp_path


def test_url_version_helpers():
    assert _url_version("boost-1.87.0") == "1_87_0"
    assert _url_version("1.90.0") == "1_90_0"
    assert _source_version_dirname("1.90.0") == "boost_1_90_0"


def test_workspace_directories_created(workspace_root):
    z = get_zip_dir()
    assert z.name == "boost_library_docs_tracker"
    assert "raw" in z.parts
    e = get_extract_dir()
    assert e.name == "extracted"
    c = get_converted_root()
    assert c.name == "converted"


def test_resolve_path_from_url_valid(workspace_root):
    url = "https://www.boost.org/doc/libs/1_87_0/libs/algorithm/doc/html/index.html"
    p = resolve_path_from_url(url)
    assert p is not None
    assert p.name == "index.md"
    assert "boost_1_87_0" in p.parts


@pytest.mark.parametrize(
    "url",
    [
        "https://nope.example/doc/libs/1_87_0/libs/x/y.html",
        "https://www.boost.org/other/libs/1_87_0/libs/x/y.html",
        "https://www.boost.org/doc/libs/1_87_0/",
    ],
)
def test_resolve_path_from_url_invalid(workspace_root, url):
    assert resolve_path_from_url(url) is None


def test_resolve_rejects_dot_dot_segment(workspace_root):
    url = "https://www.boost.org/doc/libs/1_81_0/libs/../escape/doc/x.html"
    assert resolve_path_from_url(url) is None


def test_get_page_path_raises_for_unsupported_url(workspace_root):
    with pytest.raises(ValueError, match="Unsupported Boost docs URL"):
        get_page_path("1.0.0", "algorithm", "https://evil.example/doc/libs/1/x/y.html")


def test_save_page_and_load_roundtrip(workspace_root):
    url = "https://www.boost.org/doc/libs/1_81_0/libs/algorithm/doc/html/readme.html"
    body = "# Title\n"
    path = save_page("1.81.0", "algorithm", url, body)
    assert path.exists()
    assert load_page_by_url(url) == body


def test_load_page_by_url_missing_returns_none(workspace_root):
    url = "https://www.boost.org/doc/libs/1_81_0/libs/none/doc/html/missing.html"
    assert load_page_by_url(url) is None
