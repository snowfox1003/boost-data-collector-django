#!/usr/bin/env python3
"""
Throwaway evaluation script: YouTube Data API v3 via direct HTTP vs google-api-python-client.

Usage:
  export YOUTUBE_API_KEY=your_key
  # or set YOUTUBE_API_KEY in the repo-root .env (loaded automatically)
  python scripts/eval_youtube_direct_http.py

Not imported by production code. Safe to delete after migration decision.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

BASE_URL = "https://www.googleapis.com/youtube/v3"

SEARCH_PARAMS = {
    "q": "C++",
    "part": "id,snippet",
    "type": "video",
    "maxResults": 5,
    "order": "date",
    "publishedAfter": "2024-01-01T00:00:00Z",
    "publishedBefore": "2025-01-01T00:00:00Z",
    "channelId": "UCMlGfpWw-RUdWX_JbLCukXg",  # CppCon
}


def _get_youtube_api_key() -> str:
    """Return YOUTUBE_API_KEY from the environment or repo-root .env."""
    key = (os.environ.get("YOUTUBE_API_KEY") or "").strip()
    if key:
        return key
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.is_file():
        import environ

        environ.Env.read_env(str(env_file))
        key = (os.environ.get("YOUTUBE_API_KEY") or "").strip()
    return key


def _is_quota_exceeded(text: str) -> bool:
    lowered = text.lower()
    return "quotaexceeded" in lowered or "youtube.quota" in lowered


def _extract_video_ids(search_response: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for item in search_response.get("items", []):
        if item.get("id", {}).get("kind") == "youtube#video":
            vid = item["id"].get("videoId")
            if vid:
                ids.append(vid)
    return ids


def _required_search_keys(data: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if "items" not in data:
        missing.append("items")
        return missing
    for item in data.get("items", [])[:1]:
        id_block = item.get("id", {})
        for key in ("kind", "videoId"):
            if key not in id_block:
                missing.append(f"items[].id.{key}")
        snippet = item.get("snippet", {})
        for key in ("title", "channelId", "channelTitle", "publishedAt"):
            if key not in snippet:
                missing.append(f"items[].snippet.{key}")
    return missing


def _required_video_keys(items: list[dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    if not items:
        return ["items (empty)"]
    item = items[0]
    for key in ("id", "snippet", "statistics", "contentDetails"):
        if key not in item:
            missing.append(key)
    snippet = item.get("snippet", {})
    for key in ("title", "description", "channelId", "channelTitle", "publishedAt"):
        if key not in snippet:
            missing.append(f"snippet.{key}")
    stats = item.get("statistics", {})
    for key in ("viewCount",):
        if key not in stats:
            missing.append(f"statistics.{key}")
    if "duration" not in item.get("contentDetails", {}):
        missing.append("contentDetails.duration")
    return missing


def search_list_requests(api_key: str, params: dict[str, Any]) -> dict[str, Any]:
    import requests

    query = {**params, "key": api_key}
    time.sleep(0.5)
    resp = requests.get(f"{BASE_URL}/search", params=query, timeout=30)
    if not resp.ok:
        body = resp.text
        if _is_quota_exceeded(body):
            raise RuntimeError(f"quota exceeded: HTTP {resp.status_code}")
        resp.raise_for_status()
    return resp.json()


def search_list_httpx(api_key: str, params: dict[str, Any]) -> dict[str, Any]:
    import httpx

    query = {**params, "key": api_key}
    time.sleep(0.5)
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{BASE_URL}/search", params=query)
        if resp.status_code >= 400:
            body = resp.text
            if _is_quota_exceeded(body):
                raise RuntimeError(f"quota exceeded: HTTP {resp.status_code}")
            raise RuntimeError(f"HTTP {resp.status_code}: {body}")
        return resp.json()


def videos_list_requests(api_key: str, video_ids: list[str]) -> dict[str, Any]:
    import requests

    query = {
        "key": api_key,
        "part": "snippet,statistics,contentDetails",
        "id": ",".join(video_ids),
    }
    time.sleep(0.5)
    resp = requests.get(f"{BASE_URL}/videos", params=query, timeout=30)
    if not resp.ok:
        body = resp.text
        if _is_quota_exceeded(body):
            raise RuntimeError(f"quota exceeded: HTTP {resp.status_code}")
        resp.raise_for_status()
    return resp.json()


def search_list_google_client(api_key: str, params: dict[str, Any]) -> dict[str, Any]:
    from googleapiclient.discovery import build

    youtube = build("youtube", "v3", developerKey=api_key)
    time.sleep(0.5)
    try:
        return youtube.search().list(**params).execute()
    except Exception as exc:
        if _is_quota_exceeded(str(exc)):
            raise RuntimeError("quota exceeded: google client") from exc
        raise


def _print_section(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def _run_live_comparison(api_key: str) -> int:
    errors = 0
    _print_section("Live API: requests")
    try:
        req_data = search_list_requests(api_key, SEARCH_PARAMS)
        missing = _required_search_keys(req_data)
        print(f"  items: {len(req_data.get('items', []))}")
        print(f"  nextPageToken: {req_data.get('nextPageToken', '(none)')}")
        print(f"  missing keys: {missing or 'none'}")
        if missing:
            errors += 1
    except Exception as exc:
        print(f"  ERROR: {exc}")
        errors += 1
        req_data = {}

    _print_section("Live API: httpx")
    try:
        import httpx  # noqa: F401

        httpx_data = search_list_httpx(api_key, SEARCH_PARAMS)
        missing = _required_search_keys(httpx_data)
        print(f"  items: {len(httpx_data.get('items', []))}")
        print(f"  nextPageToken: {httpx_data.get('nextPageToken', '(none)')}")
        print(f"  missing keys: {missing or 'none'}")
        if missing:
            errors += 1
    except ImportError:
        print("  SKIP: httpx not installed (pip install 'httpx>=0.27,<1')")
    except Exception as exc:
        print(f"  ERROR: {exc}")
        errors += 1

    _print_section("Live API: google-api-python-client")
    try:
        google_data = search_list_google_client(api_key, SEARCH_PARAMS)
        missing = _required_search_keys(google_data)
        print(f"  items: {len(google_data.get('items', []))}")
        print(f"  nextPageToken: {google_data.get('nextPageToken', '(none)')}")
        print(f"  missing keys: {missing or 'none'}")
        if missing:
            errors += 1
    except Exception as exc:
        print(f"  ERROR: {exc}")
        errors += 1
        google_data = {}

    req_ids = _extract_video_ids(req_data) if req_data else []
    google_ids = _extract_video_ids(google_data) if google_data else []
    if req_data and google_data:
        print(
            f"\n  video ID overlap (requests vs google): {set(req_ids) & set(google_ids)}"
        )

    video_ids = (req_ids or google_ids)[:3]
    if not video_ids:
        print("\n  SKIP videos.list: no video IDs from search")
        return errors

    _print_section("Live API: videos.list via requests")
    try:
        videos_data = videos_list_requests(api_key, video_ids)
        items = videos_data.get("items", [])
        missing = _required_video_keys(items)
        print(f"  items: {len(items)}")
        print(f"  missing keys: {missing or 'none'}")
        if missing:
            errors += 1
    except Exception as exc:
        print(f"  ERROR: {exc}")
        errors += 1

    return errors


def _run_fixture_checks() -> None:
    """Validate parsers against representative JSON (no API key required)."""
    sample_search = {
        "items": [
            {
                "id": {"kind": "youtube#video", "videoId": "abc123"},
                "snippet": {
                    "title": "Modern C++",
                    "channelId": "UCMlGfpWw-RUdWX_JbLCukXg",
                    "channelTitle": "CppCon",
                    "publishedAt": "2024-06-01T12:00:00Z",
                },
            }
        ],
        "nextPageToken": "CAUQAA",
    }
    sample_video = {
        "items": [
            {
                "id": "abc123",
                "snippet": {
                    "title": "Modern C++",
                    "description": "Talk",
                    "channelId": "UCMlGfpWw-RUdWX_JbLCukXg",
                    "channelTitle": "CppCon",
                    "publishedAt": "2024-06-01T12:00:00Z",
                    "tags": ["cpp", "templates"],
                },
                "statistics": {
                    "viewCount": "1000",
                    "likeCount": "50",
                    "commentCount": "10",
                },
                "contentDetails": {"duration": "PT1H2M10S"},
            }
        ]
    }
    sample_quota_error = {
        "error": {
            "code": 403,
            "message": "The request cannot be completed because you have exceeded your quota.",
            "errors": [
                {
                    "message": "The request cannot be completed because you have exceeded your quota.",
                    "domain": "youtube.quota",
                    "reason": "quotaExceeded",
                }
            ],
        }
    }

    _print_section("Fixture: search response shape")
    print(f"  missing keys: {_required_search_keys(sample_search) or 'none'}")
    print(f"  video IDs: {_extract_video_ids(sample_search)}")

    _print_section("Fixture: videos response shape")
    print(f"  missing keys: {_required_video_keys(sample_video['items']) or 'none'}")

    _print_section("Fixture: quota error detection")
    err_text = json.dumps(sample_quota_error)
    print(f"  _is_quota_exceeded: {_is_quota_exceeded(err_text)}")
    print(f"  sample reason: {sample_quota_error['error']['errors'][0]['reason']}")


def main() -> int:
    api_key = _get_youtube_api_key()
    print("YouTube Data API v3 — direct HTTP evaluation")
    print(f"YOUTUBE_API_KEY set: {'yes' if api_key else 'no'}")

    _run_fixture_checks()

    if not api_key:
        print(
            "\nNo YOUTUBE_API_KEY — skipping live calls. "
            "Set YOUTUBE_API_KEY in the environment or repo-root .env."
        )
        return 0

    return _run_live_comparison(api_key)


if __name__ == "__main__":
    sys.exit(main())
