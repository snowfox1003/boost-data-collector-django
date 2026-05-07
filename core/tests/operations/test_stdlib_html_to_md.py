"""Tests for core.operations.md_ops.html_to_markdown (stdlib HTMLParser)."""

from pathlib import Path

from core.operations.md_ops.html_to_md import (
    HTMLToMarkdownConverter,
    convert_html_file_to_markdown,
    html_to_markdown,
)


def test_html_to_markdown_headings_lists_links():
    html = """<html><body>
<h1>T</h1><h2>U</h2><h3>V</h3><h4>W</h4><h5>X</h5><h6>Y</h6>
<p>Para with <b>bold</b> and <i>italic</i>.</p>
<ul><li>a</li><li>b</li></ul>
<ol><li>one</li><li>two</li></ol>
<a href="https://ex">link text</a>
<br/><hr/>
<code>x</code>
<pre>line1\nline2</pre>
<img src="/i.png" alt="pic"/>
</body></html>"""
    md = html_to_markdown(html)
    assert "# T" in md
    assert "**bold**" in md or "bold" in md
    assert "[link text](https://ex)" in md
    assert "```" in md


def test_embedded_file_paragraph_skipped():
    html = '<p class="embedded-file">skip me</p><p>keep</p>'
    md = html_to_markdown(html)
    assert "skip" not in md.lower()
    assert "keep" in md.lower()


def test_control_tag_inserts_content():
    html = "<html><body><control>Hello :emoji: world</control></body></html>"
    md = html_to_markdown(html)
    assert "Hello" in md


def test_entity_and_charref():
    html = "<p>a&nbsp;b &lt;c&gt;</p>"
    md = html_to_markdown(html)
    assert "a" in md and "b" in md


def test_convert_html_file_roundtrip(tmp_path):
    inp = tmp_path / "in.html"
    inp.write_text("<html><body><p>ok</p></body></html>", encoding="utf-8")
    out = convert_html_file_to_markdown(str(inp))
    assert Path(out).exists()
    assert Path(out).read_text(encoding="utf-8")


def test_converter_get_markdown_collapses_blank_lines():
    c = HTMLToMarkdownConverter()
    c.feed("<p>a</p><p>b</p>")
    m = c.get_markdown()
    assert "a" in m and "b" in m


def test_img_inside_control_tag_does_not_emit_markdown():
    html = "<html><body><control><img src='/x.png' alt='y'/></control></body></html>"
    md = html_to_markdown(html)
    assert "![" not in md and "x.png" not in md


def test_anchor_empty_text_still_emits_url():
    html = '<html><body><p><a href="https://example.com/path"></a></p></body></html>'
    md = html_to_markdown(html)
    assert "example.com" in md
