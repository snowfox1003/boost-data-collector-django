"""Additional unit tests for boost_library_docs_tracker.fetcher (zip, paths, walk)."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import zipfile

import pytest

from boost_library_docs_tracker import fetcher


def test_source_zip_url_and_fallback():
    assert "1.90.0" in fetcher.source_zip_url("1.90.0")
    assert "boost_1_90_0" in fetcher.source_zip_url("boost-1.90.0")
    assert "github.com" in fetcher.source_zip_fallback_url("1.90.0")


def test_get_start_path_variants():
    p = fetcher.get_start_path("utility", "doc/html/index.html")
    assert "utility" in str(p)
    assert str(p).replace("\\", "/").endswith("doc/html/index.html")

    p2 = fetcher.get_start_path("numeric/ublas", "/doc/html/foo.html")
    assert str(p2).startswith("doc")

    p3 = fetcher.get_start_path("x", "")
    assert str(p3).endswith("index.html")

    p4 = fetcher.get_start_path("x", "guide/")
    assert str(p4).replace("\\", "/").endswith("guide/index.html")


def test_library_root_for_key():
    assert fetcher._library_root_for_key("") == Path("libs")
    assert fetcher._library_root_for_key("  ") == Path("libs")
    assert fetcher._library_root_for_key("numeric/foo") == Path("libs") / "numeric/foo"
    assert fetcher._library_root_for_key("enable_if") == Path("libs") / "core"
    assert fetcher._library_root_for_key("swap") == Path("libs") / "core"
    assert (
        fetcher._library_root_for_key("algorithm/string") == Path("libs") / "algorithm"
    )


def test_get_session_singleton():
    fetcher._SESSION = None
    s1 = fetcher._get_session()
    s2 = fetcher._get_session()
    assert s1 is s2
    assert "User-Agent" in s1.headers


@patch("boost_library_docs_tracker.fetcher.convert_html_to_markdown", lambda h: "x")
@patch("boost_library_docs_tracker.fetcher.get_extract_dir")
def test_walk_library_html_respects_max_pages(mock_get_extract, tmp_path):
    url_ver = "1_87_0"
    base = tmp_path / f"boost_{url_ver}"
    for name in ("a.html", "b.html"):
        p = base / "libs" / "algo" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("<html><body>x</body></html>", encoding="utf-8")
    mock_get_extract.return_value = tmp_path
    out = fetcher.walk_library_html(
        Path("libs/algo/a.html"), "algo", "1.87.0", max_pages=1
    )
    assert len(out) == 1


@patch(
    "boost_library_docs_tracker.fetcher.convert_html_to_markdown",
    lambda h: f"MD:{h[:20]}",
)
@patch("boost_library_docs_tracker.fetcher.get_extract_dir")
def test_walk_library_html_bfs_and_skips(mock_get_extract, tmp_path):
    url_ver = "1_87_0"
    base = tmp_path / f"boost_{url_ver}"
    lib_html = base / "libs" / "algo" / "a.html"
    lib_html.parent.mkdir(parents=True)
    page_b = base / "libs" / "algo" / "b.html"
    lib_html.write_text(
        '<html><body><a href="b.html">b</a><a href="https://x/y.html">ext</a>'
        '<a href="skip.txt">t</a></body></html>',
        encoding="utf-8",
    )
    page_b.write_text("<html><body>done</body></html>", encoding="utf-8")
    hidden = base / "libs" / "algo" / ".hidden.html"
    hidden.write_text("<html>x</html>", encoding="utf-8")

    mock_get_extract.return_value = tmp_path
    out = fetcher.walk_library_html(
        Path("libs/algo/a.html"), "algo", "1.87.0", max_pages=10
    )
    urls = [u for u, _ in out]
    assert any("a.html" in u for u in urls)
    assert any("b.html" in u for u in urls)


@patch("boost_library_docs_tracker.fetcher.convert_html_to_markdown", lambda h: "x")
@patch("boost_library_docs_tracker.fetcher.get_extract_dir")
def test_walk_library_html_read_error_skipped(mock_get_extract, tmp_path):
    mock_get_extract.return_value = tmp_path
    base = tmp_path / "boost_1_87_0"
    f = base / "libs" / "z" / "c.html"
    f.parent.mkdir(parents=True)
    with patch.object(Path, "read_text", side_effect=OSError("no")):
        out = fetcher.walk_library_html(
            Path("libs/z/c.html"), "z", "1.87.0", max_pages=5
        )
    assert out == []


@patch("boost_library_docs_tracker.fetcher.convert_html_to_markdown", lambda h: h)
@patch("boost_library_docs_tracker.fetcher.time.sleep", return_value=None)
@patch("boost_library_docs_tracker.fetcher._get_session")
def test_crawl_request_failure_continues(mock_sess, _sleep):
    session = MagicMock()
    session.get.side_effect = fetcher.requests.RequestException("timeout")
    mock_sess.return_value = session
    out = fetcher.crawl_library_pages(
        Path("libs/x"), "x", "1.0.0", max_pages=3, delay_secs=0
    )
    assert out == []


@patch("boost_library_docs_tracker.fetcher.convert_html_to_markdown", lambda h: h)
@patch("boost_library_docs_tracker.fetcher.time.sleep", return_value=None)
@patch("boost_library_docs_tracker.fetcher._get_session")
def test_crawl_empty_lib_key_warns(mock_sess, _sleep):
    session = MagicMock()
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.headers = {"Content-Type": "text/html"}
    resp.text = "<html><body>ok</body></html>"
    resp.url = "https://www.boost.org/doc/libs/1_87_0/"
    session.get.return_value = resp
    mock_sess.return_value = session
    out = fetcher.crawl_library_pages(
        Path("libs//"), "", "1.87.0", max_pages=2, delay_secs=0
    )
    assert len(out) >= 1


def test_extract_source_zip_empty_raises(tmp_path):
    zpath = tmp_path / "empty.zip"
    with zipfile.ZipFile(zpath, "w"):
        pass
    with pytest.raises(RuntimeError, match="no entries"):
        fetcher.extract_source_zip(zpath, tmp_path / "out")


def test_extract_and_delete_extract_dir(tmp_path):
    zpath = tmp_path / "src.zip"
    extract_to = tmp_path / "ex"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("boost_root/readme.txt", "hi")
    top = fetcher.extract_source_zip(zpath, extract_to)
    assert top.name == "boost_root"
    fetcher.delete_extract_dir(top)
    assert not top.exists()


def test_download_source_zip_resume_existing(tmp_path):
    fetcher._SESSION = None
    norm = "1.2.3"
    zip_name = f"boost_{norm.replace('.', '_')}.zip"
    zp = tmp_path / zip_name
    zp.write_bytes(b"x")
    out = fetcher.download_source_zip("boost-1.2.3", tmp_path)
    assert out == zp


def _cm_resp(raise_exc=None, chunks=(b"ab",), content_length="2"):
    resp = MagicMock()
    if raise_exc:
        resp.raise_for_status = MagicMock(side_effect=raise_exc)
    else:
        resp.raise_for_status = MagicMock()
    resp.headers = {"Content-Length": content_length}
    resp.iter_content.return_value = list(chunks)
    cm = MagicMock()
    cm.__enter__.return_value = resp
    cm.__exit__.return_value = False
    return cm


@patch("boost_library_docs_tracker.fetcher._get_session")
def test_download_source_zip_primary_then_fallback(mock_gs, tmp_path):
    fetcher._SESSION = None
    session = MagicMock()
    session.get.side_effect = [
        _cm_resp(raise_exc=fetcher.requests.RequestException("fail")),
        _cm_resp(chunks=(b"x",), content_length="1"),
    ]
    mock_gs.return_value = session
    out = fetcher.download_source_zip("1.0.0", tmp_path)
    assert out.exists()
    assert session.get.call_count == 2
