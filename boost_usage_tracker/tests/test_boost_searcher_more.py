"""Extended unit tests for boost_usage_tracker.boost_searcher (mocked GitHub client)."""

from unittest.mock import MagicMock, patch


from boost_usage_tracker.boost_searcher import (
    FileSearchResult,
    _build_boost_include_query,
    _chunked,
    _fetch_repo_files_task,
    _get_file_info_graphql,
    _get_file_info_rest,
    _get_files_info_graphql_batch,
    _search_boost_include_by_query,
    check_repo_has_vendored_boost,
    detect_boost_version_in_repo,
    extract_boost_version_from_content,
    get_file_content_with_commit_date,
    search_boost_include_files,
    search_boost_include_files_batch,
)


def test_chunked_and_build_query():
    assert _chunked(["a", "b", "c"], 2) == [["a", "b"], ["c"]]
    q, rem = _build_boost_include_query([])
    assert "boost/" in q
    assert rem == []
    long_repos = [f"org{i}/repo{i}" for i in range(50)]
    q2, rem2 = _build_boost_include_query(long_repos)
    assert rem2 or len(q2) <= 255


def test_graphql_file_info_success():
    client = MagicMock()
    client.graphql_request.return_value = {
        "data": {
            "repository": {
                "object": {"text": "hello"},
                "defaultBranchRef": {
                    "target": {
                        "history": {
                            "edges": [
                                {"node": {"committedDate": "2024-01-01T00:00:00Z"}}
                            ]
                        }
                    }
                },
            }
        }
    }
    out = _get_file_info_graphql(client, "o", "r", "p.txt")
    assert out["content"] == "hello"
    assert out["commit_date"] is not None


def test_graphql_file_info_failure_returns_none():
    client = MagicMock()
    client.graphql_request.side_effect = RuntimeError("net")
    assert _get_file_info_graphql(client, "o", "r", "f") is None


def test_rest_file_info_base64():
    client = MagicMock()
    import base64

    raw = base64.b64encode(b"cpp").decode("ascii")
    client.rest_request.side_effect = [
        {"encoding": "base64", "content": raw},
        [
            {
                "commit": {
                    "committer": {"date": "2024-06-01T12:00:00Z"},
                }
            }
        ],
    ]
    out = _get_file_info_rest(client, "o/r", "f.hpp")
    assert "cpp" in out["content"]


def test_rest_file_info_plain_content():
    client = MagicMock()
    client.rest_request.side_effect = [
        {"encoding": "utf-8", "content": "plain"},
        [],
    ]
    out = _get_file_info_rest(client, "o/r", "x")
    assert out["content"] == "plain"


def test_rest_file_info_list_returns_none():
    client = MagicMock()
    client.rest_request.return_value = [{"type": "dir"}]
    assert _get_file_info_rest(client, "o/r", "p") is None


def test_batch_graphql_empty_paths():
    client = MagicMock()
    assert _get_files_info_graphql_batch(client, "o", "r", []) == {}


def test_batch_graphql_maps_paths():
    client = MagicMock()
    client.graphql_request.return_value = {
        "data": {
            "repository": {
                "f0": {"text": "a"},
                "h0": {
                    "target": {
                        "history": {
                            "edges": [
                                {"node": {"committedDate": "2024-01-01T00:00:00Z"}}
                            ]
                        }
                    }
                },
            }
        }
    }
    out = _get_files_info_graphql_batch(client, "o", "r", ["f1.txt"])
    assert "f1.txt" in out


def test_get_file_content_with_commit_date_splits_repo():
    client = MagicMock()
    with patch(
        "boost_usage_tracker.boost_searcher._get_file_info_graphql",
        return_value={"content": "z"},
    ) as m:
        r = get_file_content_with_commit_date(client, "a/b", "p")
    m.assert_called_once_with(client, "a", "b", "p")
    assert r["content"] == "z"


@patch("boost_usage_tracker.boost_searcher.time.sleep", return_value=None)
@patch("boost_usage_tracker.boost_searcher._get_files_info_graphql_batch")
def test_fetch_repo_files_task_uses_rest_fallback(mock_batch, _sleep):
    mock_batch.return_value = {}
    client = MagicMock()
    client.rest_request.side_effect = [
        {"encoding": "utf-8", "content": "x"},
        [{"commit": {"committer": {"date": "2024-01-01T00:00:00Z"}}}],
    ]
    out = _fetch_repo_files_task(client, "o/r", ["a.cpp"])
    assert len(out) == 1
    assert isinstance(out[0], FileSearchResult)


@patch("boost_usage_tracker.boost_searcher.time.sleep", return_value=None)
@patch(
    "boost_usage_tracker.boost_searcher.as_completed",
    lambda futures: iter(futures),
)
@patch("boost_usage_tracker.boost_searcher.wait", return_value=(set(), set()))
@patch("boost_usage_tracker.boost_searcher.ThreadPoolExecutor")
def test_search_boost_include_by_query(mock_exec, _mock_wait, _sleep):
    fut = MagicMock()
    fut.result.return_value = [
        FileSearchResult("o/r", "f.cpp", content="", boost_headers=[]),
    ]
    mock_exec.return_value.__enter__.return_value.submit.return_value = fut

    client = MagicMock()
    client.rest_request.return_value = {
        "items": [
            {
                "path": "src/main.cpp",
                "repository": {"full_name": "user/repo"},
            }
        ]
    }
    results = _search_boost_include_by_query(client, "q")
    assert len(results) >= 1


@patch("boost_usage_tracker.boost_searcher.time.sleep", return_value=None)
@patch("boost_usage_tracker.boost_searcher._search_boost_include_by_query")
def test_search_boost_include_files_delegates(mock_search, _sleep):
    client = MagicMock()
    search_boost_include_files(client, "a/b")
    mock_search.assert_called_once()


@patch("boost_usage_tracker.boost_searcher.time.sleep", return_value=None)
@patch("boost_usage_tracker.boost_searcher._search_boost_include_by_query")
def test_search_boost_include_files_batch_splits_on_large_total(mock_search, _sleep):
    mock_search.return_value = []
    state = {"probe_calls": 0}

    def rest_side_effect(_path, params=None):
        if params and params.get("per_page") == 1:
            state["probe_calls"] += 1
            # Parent probe: huge → split; child probes: small → single query path
            return {"total_count": 1500 if state["probe_calls"] <= 2 else 10}
        return {"items": [], "total_count": 0}

    client = MagicMock()
    client.rest_request.side_effect = rest_side_effect
    search_boost_include_files_batch(client, ["a/x", "b/y"])
    assert mock_search.called


@patch("boost_usage_tracker.boost_searcher.time.sleep", return_value=None)
@patch("boost_usage_tracker.boost_searcher.get_file_content_with_commit_date")
def test_check_repo_has_vendored_boost(mock_gfc, _sleep):
    mock_gfc.return_value = {
        "content": "#define BOOST_VERSION 107900\n",
    }
    client = MagicMock()
    client.rest_request.return_value = {
        "total_count": 1,
        "items": [{"path": "boost/version.hpp"}],
    }
    ok, ver = check_repo_has_vendored_boost(client, "u/r")
    assert ok is True
    assert ver


@patch("boost_usage_tracker.boost_searcher.time.sleep", return_value=None)
def test_detect_boost_version_prefers_vendored(_sleep):
    client = MagicMock()
    with patch(
        "boost_usage_tracker.boost_searcher.check_repo_has_vendored_boost",
        return_value=(True, "1.79.0"),
    ):
        vendored, ver = detect_boost_version_in_repo(client, "u/r")
    assert vendored and ver == "1.79.0"


@patch("boost_usage_tracker.boost_searcher.time.sleep", return_value=None)
@patch("boost_usage_tracker.boost_searcher.get_file_content_with_commit_date")
def test_detect_boost_version_from_cmake(mock_gfc, _sleep):
    mock_gfc.return_value = {"content": "find_package(Boost 1.82 REQUIRED)\n"}
    client = MagicMock()
    with patch(
        "boost_usage_tracker.boost_searcher.check_repo_has_vendored_boost",
        return_value=(False, None),
    ):
        vendored, ver = detect_boost_version_in_repo(client, "u/r")
    assert vendored is False
    assert ver


def test_extract_boost_version_more_patterns():
    assert extract_boost_version_from_content(
        'GIT_TAG "boost-1.70.0"', "CMakeLists.txt"
    )
    assert extract_boost_version_from_content("boost/1.2.3", "conanfile.txt")


def test_extract_boost_version_from_empty_content():
    assert extract_boost_version_from_content("", "boost/version.hpp") is None


def test_graphql_file_info_missing_repository():
    client = MagicMock()
    client.graphql_request.return_value = {"data": {"repository": None}}
    assert _get_file_info_graphql(client, "o", "r", "p.txt") is None


def test_graphql_file_info_blob_without_text():
    client = MagicMock()
    client.graphql_request.return_value = {
        "data": {
            "repository": {
                "object": {"oid": "x"},
                "defaultBranchRef": {"target": {"history": {"edges": []}}},
            }
        }
    }
    assert _get_file_info_graphql(client, "o", "r", "p.txt") is None


def test_batch_graphql_missing_repository():
    client = MagicMock()
    client.graphql_request.return_value = {"data": {"repository": None}}
    assert _get_files_info_graphql_batch(client, "o", "r", ["a.cpp"]) == {}


def test_batch_graphql_request_failure_returns_empty():
    client = MagicMock()
    client.graphql_request.side_effect = RuntimeError("gql")
    assert _get_files_info_graphql_batch(client, "o", "r", ["a.cpp"]) == {}


def test_batch_graphql_skips_blob_without_text():
    client = MagicMock()
    client.graphql_request.return_value = {
        "data": {
            "repository": {
                "f0": {"oid": "only"},
                "h0": {"target": {"history": {"edges": []}}},
            }
        }
    }
    assert _get_files_info_graphql_batch(client, "o", "r", ["z.hpp"]) == {}


@patch("boost_usage_tracker.boost_searcher.time.sleep", return_value=None)
def test_search_boost_include_files_batch_empty(_sleep):
    client = MagicMock()
    assert search_boost_include_files_batch(client, []) == []


@patch("boost_usage_tracker.boost_searcher.time.sleep", return_value=None)
@patch("boost_usage_tracker.boost_searcher.search_boost_include_files")
def test_search_boost_include_files_batch_single_repo(mock_single, _sleep):
    client = MagicMock()
    mock_single.return_value = ["x"]
    assert search_boost_include_files_batch(client, ["only/repo"]) == ["x"]
    mock_single.assert_called_once_with(client, "only/repo")


@patch("boost_usage_tracker.boost_searcher.time.sleep", return_value=None)
def test_search_boost_include_files_batch_probe_failure_returns_empty(_sleep):
    client = MagicMock()
    client.rest_request.side_effect = RuntimeError("probe failed")
    assert search_boost_include_files_batch(client, ["a/z", "b/y"]) == []


@patch("boost_usage_tracker.boost_searcher.time.sleep", return_value=None)
def test_search_boost_include_files_batch_zero_total(_sleep):
    client = MagicMock()
    client.rest_request.return_value = {"total_count": 0}
    assert search_boost_include_files_batch(client, ["a/z", "b/y"]) == []


@patch("boost_usage_tracker.boost_searcher.time.sleep", return_value=None)
@patch("boost_usage_tracker.boost_searcher.ThreadPoolExecutor")
def test_search_boost_include_by_query_code_search_error(mock_exec, _sleep):
    mock_exec.return_value.__enter__.return_value.submit.side_effect = RuntimeError(
        "no worker"
    )
    client = MagicMock()
    client.rest_request.side_effect = RuntimeError("search down")
    assert _search_boost_include_by_query(client, "q") == []


@patch("boost_usage_tracker.boost_searcher.time.sleep", return_value=None)
@patch(
    "boost_usage_tracker.boost_searcher.as_completed",
    lambda futures: iter(futures),
)
@patch("boost_usage_tracker.boost_searcher.wait", return_value=(set(), set()))
@patch("boost_usage_tracker.boost_searcher.ThreadPoolExecutor")
def test_search_boost_include_by_query_skips_boost_paths_and_boostorg(
    mock_exec, _mock_wait, _sleep
):
    bad_fut = MagicMock()
    bad_fut.result.side_effect = RuntimeError("task")
    good_fut = MagicMock()
    good_fut.result.return_value = []
    mock_exec.return_value.__enter__.return_value.submit.side_effect = [
        good_fut,
        bad_fut,
    ]
    client = MagicMock()
    client.rest_request.return_value = {
        "items": [
            {"path": "third_party/boost/foo.hpp", "repository": {"full_name": "u/r"}},
            {"path": "src/x.cpp", "repository": {"full_name": "boostorg/boost"}},
            {
                "path": "app.cpp",
                "repository": {"full_name": "me/proj"},
            },
        ]
    }
    _search_boost_include_by_query(client, "q")
    assert mock_exec.return_value.__enter__.return_value.submit.call_count == 1


@patch("boost_usage_tracker.boost_searcher.time.sleep", return_value=None)
@patch("boost_usage_tracker.boost_searcher.get_file_content_with_commit_date")
def test_check_repo_has_vendored_boost_search_fails(mock_gfc, _sleep):
    client = MagicMock()
    client.rest_request.side_effect = RuntimeError("code search")
    assert check_repo_has_vendored_boost(client, "u/r") == (False, None)


@patch("boost_usage_tracker.boost_searcher.time.sleep", return_value=None)
@patch("boost_usage_tracker.boost_searcher.get_file_content_with_commit_date")
def test_check_repo_has_vendored_boost_zero_hits(_mock_gfc, _sleep):
    client = MagicMock()
    client.rest_request.return_value = {"total_count": 0, "items": []}
    assert check_repo_has_vendored_boost(client, "u/r") == (False, None)
    _mock_gfc.assert_not_called()


@patch("boost_usage_tracker.boost_searcher.time.sleep", return_value=None)
@patch("boost_usage_tracker.boost_searcher.get_file_content_with_commit_date")
def test_detect_boost_version_no_build_file_version(mock_gfc, _sleep):
    mock_gfc.return_value = None
    client = MagicMock()
    with patch(
        "boost_usage_tracker.boost_searcher.check_repo_has_vendored_boost",
        return_value=(False, None),
    ):
        embed, ver = detect_boost_version_in_repo(client, "u/r")
    assert embed is False
    assert ver is None
