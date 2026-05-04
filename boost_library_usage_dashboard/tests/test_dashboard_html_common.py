"""Tests for boost_library_usage_dashboard.dashboard_html_common."""

from boost_library_usage_dashboard import dashboard_html_common as common


def test_e_escapes_html():
    assert common.e("<script>") == "&lt;script&gt;"
    assert "&amp;" in common.e("&")


def test_json_for_script_escapes_line_separators_and_script_close():
    payload = {"text": "a\u2028b\u2029c", "tag": "</script><evil>"}
    raw = common.json_for_script(payload)
    assert r"\u003c/" in raw
    assert "\u2028" not in raw or "\\u2028" in raw


def test_version_key_sorts_semantically():
    assert common.version_key("1.85.0") == common.version_key("1.85.0")
    assert common.version_key("1.10.0") > common.version_key("1.9.0")


def test_base_css_and_table_helpers_return_non_empty():
    assert "box-sizing" in common.base_css()
    html = common.table_container(
        title="T",
        table_id="tbl",
        search_id="s",
        info_id="i",
        prev_id="p",
        next_id="n",
        headers=[("Col", "c")],
    )
    assert "tbl" in html and "sortable" in html
    assert "initDataTable" in common.table_js()
