"""Tests for slack_event_handler.utils.huddle_markdown."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from slack_event_handler.utils.huddle_markdown import generate_huddle_markdown


def test_generate_huddle_markdown_missing_html_returns_none(tmp_path):
    missing_html = tmp_path / "nope.html"
    json_path = tmp_path / "t.json"
    json_path.write_text("{}", encoding="utf-8")
    assert (
        generate_huddle_markdown(str(missing_html), str(json_path), str(tmp_path))
        is None
    )


def test_generate_huddle_markdown_invalid_json_returns_none(tmp_path):
    html = tmp_path / "s.html"
    html.write_text("<html><body>x</body></html>", encoding="utf-8")
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not json", encoding="utf-8")
    assert generate_huddle_markdown(str(html), str(bad_json), str(tmp_path)) is None


@patch("slack_event_handler.utils.huddle_markdown.write_huddle_transcript_md")
@patch("slack_event_handler.utils.huddle_markdown.replace_channel_ids_with_names")
@patch("slack_event_handler.utils.huddle_markdown.replace_user_ids_with_usernames")
@patch("slack_event_handler.utils.huddle_markdown.html_to_markdown")
@patch("slack_event_handler.utils.huddle_markdown.generate_transcript_from_json")
@patch("slack_event_handler.utils.huddle_markdown.SlackFetcher")
@patch("slack_event_handler.utils.huddle_markdown.parse_html_summary")
def test_generate_huddle_markdown_success_path(
    mock_parse,
    mock_fetcher_cls,
    mock_gen_tx,
    mock_html_md,
    mock_replace_u,
    mock_replace_c,
    mock_write,
    tmp_path,
):
    html = tmp_path / "p.html"
    html.write_text("<html>@UZZZTOP</html>", encoding="utf-8")
    js = tmp_path / "p.json"
    js.write_text('{"messages": []}', encoding="utf-8")

    mock_parse.return_value = {"channel_id": "C9", "attendee_ids": ["UA"]}
    fetcher = MagicMock()
    fetcher.get_channel_info.return_value = "general"
    fetcher.get_user_info.return_value = {"display_name": "Someone"}
    mock_fetcher_cls.return_value = fetcher
    mock_gen_tx.return_value = [{"user_id": "UB", "text": "hi"}]
    mock_html_md.return_value = "## Hi\n# Title\n"
    # replace_* must return str; default MagicMock breaks re.sub below.
    mock_replace_u.return_value = "## Hi\n# Title\n"
    mock_replace_c.return_value = "## Hi\n# Title\n"
    mock_write.return_value = Path(tmp_path / "out.md")

    out = generate_huddle_markdown(str(html), str(js), str(tmp_path), bot_token="x")

    assert out is not None
    assert Path(out).resolve() == (tmp_path / "out.md").resolve()
    mock_replace_u.assert_called_once()
    mock_replace_c.assert_called_once()


@patch(
    "slack_event_handler.utils.huddle_markdown.SlackFetcher",
    side_effect=ValueError("bad"),
)
def test_generate_huddle_markdown_fetcher_init_fails(_mock_sf, tmp_path):
    html = tmp_path / "a.html"
    html.write_text("<html/>", encoding="utf-8")
    js = tmp_path / "a.json"
    js.write_text("{}", encoding="utf-8")
    assert generate_huddle_markdown(str(html), str(js), str(tmp_path)) is None


@patch("slack_event_handler.utils.huddle_markdown.open", side_effect=OSError("no"))
def test_generate_huddle_markdown_html_read_error(_mock_open, tmp_path):
    assert (
        generate_huddle_markdown(
            str(tmp_path / "missing.html"),
            str(tmp_path / "x.json"),
            str(tmp_path),
        )
        is None
    )
