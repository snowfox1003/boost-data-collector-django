"""Tests for core.operations.md_ops.pr_to_md helper functions."""

from core.operations.md_ops import pr_to_md as m


def test_format_datetime_none_and_invalid():
    assert m.format_datetime(None) == "N/A"
    assert m.format_datetime("garbage") == "garbage"


def test_parse_diff_hunk_header_and_get_last_n_lines():
    diff = """@@ -10,3 +10,4 @@
 context
-old
+new
 more
"""
    assert "old" in m.get_last_n_lines(diff, n=5)
    assert m._parse_diff_hunk_header("@@ -5 +7 @@")[0] == 5


def test_build_comment_tree():
    comments = [
        {"id": 1, "body": "root"},
        {"id": 2, "in_reply_to_id": 1, "body": "reply"},
    ]
    replies, roots = m.build_comment_tree(comments)
    assert len(roots) == 1
    assert 1 in replies


def test_transform_suggestion_to_diff_with_original_line():
    diff_hunk = """@@ -1,3 +1,3 @@
 line1
-old
+new
"""
    body = "```suggestion\nx\n```"
    out = m._transform_suggestion_to_diff(body, diff_hunk, original_line=2)
    assert "```diff" in out


def test_transform_suggestion_fallback_old_lines():
    diff_hunk = """@@ -1,2 +1,2 @@
 a
-b
+c
"""
    body = "```suggestion\nz\n```"
    out = m._transform_suggestion_to_diff(body, diff_hunk, original_line=None)
    assert "+" in out


def test_format_comment_with_replies_and_suggestion():
    replies = {
        10: [
            {
                "id": 11,
                "user": {"login": "u2"},
                "created_at": "2024-01-01T00:00:00Z",
                "body": "reply",
            }
        ]
    }
    comment = {
        "id": 10,
        "user": {"login": "u1"},
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
        "html_url": "https://ex",
        "body": "top",
        "diff_hunk": "",
    }
    text = m.format_comment_with_replies(comment, replies)
    assert "u1" in text and "reply" in text


def test_format_review_comments_groups_files():
    rc = [
        {
            "path": "f.cpp",
            "diff_hunk": "@@ -1,2 +1,2 @@\n x\n-y\n+z\n",
            "user": {"login": "r"},
            "created_at": "2024-01-01T00:00:00Z",
            "body": "note",
            "resolved": True,
        }
    ]
    out = m.format_review_comments(rc, {})
    assert "f.cpp" in out
    assert "Resolved" in out


def test_convert_pr_to_markdown_includes_review_comments():
    data = {
        "pr_info": {
            "number": 1,
            "title": "t",
            "state": "open",
            "merged": False,
            "user": {"login": "a"},
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "body": "",
        },
        "reviews": [
            {
                "id": 500,
                "user": {"login": "rv"},
                "state": "COMMENTED",
                "submitted_at": "2024-01-01T01:00:00Z",
                "body": "review body",
                "html_url": "https://github.com/o/r/pull/1#pullrequestreview-500",
            }
        ],
        "comments": [
            {
                "path": "a.py",
                "pull_request_review_id": 500,
                "diff_hunk": "@@ -1,1 +1,1 @@\n-old\n+new\n",
                "user": {"login": "rv"},
                "created_at": "2024-01-01T01:00:00Z",
                "body": "lc",
            }
        ],
    }
    md = m.convert_pr_to_markdown(data)
    assert "a.py" in md or "📁" in md
