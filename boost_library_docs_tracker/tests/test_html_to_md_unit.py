"""Unit tests for boost_library_docs_tracker.html_to_md (mock pandoc)."""

from unittest.mock import MagicMock, patch

import pytest

from boost_library_docs_tracker import html_to_md as htm


def test_preprocess_removes_script_tag():
    html = "<html><body><script>x</script><p>ok</p></body></html>"
    out = htm._preprocess_html(html)
    assert "script" not in out.lower()
    assert "ok" in out


def test_preprocess_removes_booster_nav_table():
    html = """<html><body><table><tr><td><img src="/boost.png"/></td></tr></table>
<p>Hello</p></body></html>"""
    out = htm._preprocess_html(html)
    assert "boost.png" not in out.lower()
    assert "Hello" in out


def test_preprocess_flattens_code_spans():
    html = """<html><body><code><span class="identifier">boost</span></code></body></html>"""
    out = htm._preprocess_html(html)
    assert "boost" in out


def test_postprocess_strips_nav_and_spans():
    md = """| Home | Libraries |
|--------|-------------|
| x | y |

---

<div class="spirit-nav">x</div>

<span id="a">inner</span>

`code` and <b>bold</b>

``` programlisting
hi
```
"""
    out = htm._postprocess_markdown(md)
    assert "inner" in out
    assert "spirit-nav" not in out


def test_join_wrapped_lines_merges_prose():
    md = "# Title\nwrapped\nline\n\n- item\n"
    out = htm._join_wrapped_lines(md)
    assert "wrapped line" in out


@pytest.mark.parametrize(
    "fmt_exc",
    [
        RuntimeError("bad fmt"),
        OSError("no pandoc"),
    ],
)
def test_pandoc_convert_cli_success(fmt_exc):
    fake_proc = MagicMock()
    fake_proc.returncode = 0
    fake_proc.stdout = "# ok\n"
    with patch.object(htm, "pypandoc", None):
        with patch(
            "boost_library_docs_tracker.html_to_md.subprocess.run",
            return_value=fake_proc,
        ):
            assert htm._pandoc_convert("<p>x</p>") == "# ok\n"


def test_pandoc_convert_raises_when_unavailable():
    fake_proc = MagicMock()
    fake_proc.returncode = 1
    with patch.object(htm, "pypandoc", None):
        with patch(
            "boost_library_docs_tracker.html_to_md.subprocess.run",
            return_value=fake_proc,
        ):
            with pytest.raises(RuntimeError, match="pandoc is not available"):
                htm._pandoc_convert("<p>x</p>")


def test_convert_html_to_markdown_pipeline(monkeypatch):
    monkeypatch.setattr(
        htm,
        "_pandoc_convert",
        lambda html: "# " + html[:10],
    )
    out = htm.convert_html_to_markdown("<html><body><p>Hi</p></body></html>")
    assert isinstance(out, str)
    assert len(out) > 0


def test_pypandoc_path_used_when_available(monkeypatch):
    mock_p = MagicMock()
    mock_p.convert_text.return_value = "via pypandoc"
    monkeypatch.setattr(htm, "pypandoc", mock_p)
    assert htm._pandoc_convert("<p>a</p>") == "via pypandoc"
    mock_p.convert_text.assert_called_once()
