# Google API Client Dependency Evaluation

**Date:** 2026-06-23
**Scope:** `google-api-python-client>=2.100,<3` in `requirements.in`
**Evaluator:** Automated analysis per evaluation plan
**Status:** Evaluation complete — **provisional REPLACE** pending one successful keyed live parity run (no `requirements.in` change in this task)

---

## 1. Call inventory

### Production usage (1 file)

| File | Function | Client API | REST endpoint |
|------|----------|------------|---------------|
| [`cppa_youtube_script_tracker/fetcher.py`](../../cppa_youtube_script_tracker/fetcher.py) | `_fetch_search_page` | `youtube.search().list(**params).execute()` | `GET https://www.googleapis.com/youtube/v3/search` |
| [`cppa_youtube_script_tracker/fetcher.py`](../../cppa_youtube_script_tracker/fetcher.py) | `_fetch_video_details` | `youtube.videos().list(...).execute()` | `GET https://www.googleapis.com/youtube/v3/videos` |
| [`cppa_youtube_script_tracker/fetcher.py`](../../cppa_youtube_script_tracker/fetcher.py) | `fetch_videos` | `build("youtube", "v3", developerKey=...)` | Discovery + client construction only |

### Indirect callers (no Google imports)

| File | Role |
|------|------|
| [`cppa_youtube_script_tracker/management/commands/run_cppa_youtube_script_tracker.py`](../../cppa_youtube_script_tracker/management/commands/run_cppa_youtube_script_tracker.py) | Phase 2 calls `fetch_videos()` |
| [`cppa_youtube_script_tracker/services.py`](../../cppa_youtube_script_tracker/services.py) | DB persistence only |

### Test-only usage

| File | Import |
|------|--------|
| [`cppa_youtube_script_tracker/tests/test_fetcher.py`](../../cppa_youtube_script_tracker/tests/test_fetcher.py) | Stubs `googleapiclient.discovery.build` |
| [`cppa_youtube_script_tracker/tests/test_failure_classification.py`](../../cppa_youtube_script_tracker/tests/test_failure_classification.py) | Optional `googleapiclient.errors.HttpError` |

### Ripgrep confirmation

```text
cppa_youtube_script_tracker/fetcher.py          build("youtube", "v3", ...)
cppa_youtube_script_tracker/tests/test_failure_classification.py   HttpError
```

No usage under `wg21_paper_tracker/` despite the stale comment in `requirements.in` line 43.

---

## 2. Distinct API method count: **2**

### Method 1: `search.list`

**Parameters sent** (from `_fetch_search_page`):

| Parameter | Value |
|-----------|-------|
| `q` | Query text |
| `part` | `id,snippet` |
| `type` | `video` |
| `maxResults` | `50` |
| `order` | `date` |
| `publishedAfter` | RFC 3339 UTC |
| `publishedBefore` | RFC 3339 UTC |
| `channelId` | Optional |
| `pageToken` | Optional (pagination) |

**Response fields consumed:**

- `items[].id.kind` (filter `youtube#video`)
- `items[].id.videoId`
- `nextPageToken`

### Method 2: `videos.list`

**Parameters sent** (from `_fetch_video_details`):

| Parameter | Value |
|-----------|-------|
| `part` | `snippet,statistics,contentDetails` |
| `id` | Comma-separated video IDs (≤50 per search page) |

**Response fields consumed** (via `_format_video_data`):

- `id`, `snippet` (title, description, channelId, channelTitle, publishedAt, tags)
- `statistics` (viewCount, likeCount, commentCount)
- `contentDetails.duration` (ISO 8601 → seconds)

### Auth

- **API key only** via `YOUTUBE_API_KEY` / `developerKey`
- No OAuth, service accounts, or token refresh
- `google-auth` stack is unused for this use case

### Error handling today

- Broad `except Exception`
- `QuotaExceededError` when `str(exc)` contains `quotaexceeded` or `youtube.quota`
- `HttpError` type is **not** used in production code

---

## 3. What the client provides vs. what we need

| Client feature | Used? | Needed? |
|----------------|-------|---------|
| Discovery document (`build()`) | Yes | No — fixed REST URLs |
| `google-auth` / OAuth | No | No |
| Protobuf / `proto-plus` | Transitive only | No — JSON responses |
| `httplib2` transport | Transitive only | No |
| Request builders | Yes | Convenience only — 1:1 query params |

`build("youtube", "v3")` import + construction measured **~1.6 s** in a clean venv (mostly import weight of the Google stack).

---

## 4. Transitive dependency analysis

### Packages in the Google-only stack (12)

Versions from [`requirements.lock`](../../requirements.lock):

| Package | Version | Installed size (MB) |
|---------|---------|---------------------|
| google-api-python-client | 2.196.0 | 95.02 |
| google-api-core | 2.30.3 | 1.05 |
| google-auth | 2.52.0 | 1.64 |
| google-auth-httplib2 | 0.4.0 | 0.03 |
| googleapis-common-protos | 1.75.0 | 0.89 |
| proto-plus | 1.28.0 | 0.25 |
| protobuf | 7.34.1 | 2.44 |
| httplib2 | 0.31.2 | 0.29 |
| pyasn1 | 0.6.3 | 0.79 |
| pyasn1-modules | 0.4.2 | 1.74 |
| uritemplate | 4.2.0 | 0.07 |
| pyparsing | 3.3.2 | 0.94 |
| **Total** | | **105.15 MB** |

> **Note:** `google-api-python-client` alone accounts for **~90%** of on-disk footprint (discovery JSON + generated API surface for all YouTube v3 methods).

### Packages retained after removal

Removing `google-api-python-client` from `requirements.in` and recompiling (scratch lockfile via `uv pip compile`) drops **12 packages**:

```text
google-api-core, google-api-python-client, google-auth, google-auth-httplib2,
googleapis-common-protos, httplib2, proto-plus, protobuf, pyasn1,
pyasn1-modules, pyparsing, uritemplate
```

| Metric | Current | Without Google client |
|--------|---------|----------------------|
| Lockfile lines | 189 | 153 (−36) |
| Resolved packages (uv) | 70 | 58 (−12) |

`cryptography` remains (direct pin in `requirements.in`). `requests` remains (already a direct dependency).

---

## 5. pip-audit surface

Scanned [`requirements.lock`](../../requirements.lock) with `pip-audit>=2.10,<3` against installed tree (Python 3.13 venv):

| Scan | Result |
|------|--------|
| Full lockfile | **No known vulnerabilities found** |
| Google-stack packages | **0 advisories** (none matched) |

**Interpretation:** Current pins are clean, but the Google stack still adds **12 packages** to the audit blast radius on every CI run ([`.github/workflows/security-audit.yml`](../../.github/workflows/security-audit.yml)). Removing the stack reduces packages scanned and future advisory exposure without fixing an active CVE today.

---

## 6. Prototype results (`requests` vs `httpx`)

Prototype script: [`scripts/eval_youtube_direct_http.py`](../../scripts/eval_youtube_direct_http.py)

### Fixture validation (no API key required) — **passed**

- Search response shape: all keys required by `_fetch_search_page` / `_process_one_channel_query` present
- Videos response shape: all keys required by `_format_video_data` present
- Quota error JSON (`reason: quotaExceeded`, `domain: youtube.quota`) detected by `_is_quota_exceeded()` logic

### Live API validation

`YOUTUBE_API_KEY` was **not set** in the project `.env` at evaluation time. Live comparison was skipped; re-run:

```bash
export YOUTUBE_API_KEY=...
python scripts/eval_youtube_direct_http.py
```

### Direct HTTP implementation sketch

```python
BASE = "https://www.googleapis.com/youtube/v3"

# search.list
requests.get(f"{BASE}/search", params={**params, "key": api_key}, timeout=30)

# videos.list
requests.get(f"{BASE}/videos", params={
    "key": api_key,
    "part": "snippet,statistics,contentDetails",
    "id": ",".join(video_ids),
}, timeout=30)
```

### Client comparison

| Criterion | `requests` | `httpx` | `google-api-python-client` |
|-----------|------------|---------|----------------------------|
| New direct dependency? | **No** (already in `requirements.in`) | Yes | Yes (12 transitive) |
| API parity for 2 endpoints | Yes (fixture + REST docs) | Yes (same URLs) | Current implementation |
| Quota error mapping | Parse `resp.text` / JSON `error.errors[].reason` | Same | String match on exception today |
| Project conventions | Used widely | Not in lockfile | Only YouTube fetcher |
| Import / startup cost | Low | Low | ~1.6 s `build()` measured |

### Invalid-key probe (live)

`GET /youtube/v3/search` with a fake key returned HTTP 400, `reason: badRequest` — confirms structured JSON error bodies are available for direct HTTP error handling (distinct from `quotaExceeded`).

---

## 7. Recommendation: **REPLACE** with direct HTTP (`requests`) — **provisional**

Fixture validation and REST-doc parity passed, but the **keyed live comparison was skipped** (§6 — `YOUTUBE_API_KEY` not set). Treat **REPLACE** as provisional until one successful live run of [`scripts/eval_youtube_direct_http.py`](../../scripts/eval_youtube_direct_http.py) confirms SDK vs direct-HTTP parity on real responses.

**Proceed with migration only after:**

```bash
export YOUTUBE_API_KEY=...
python scripts/eval_youtube_direct_http.py
```

The script must report live parity (search + videos) with no mismatches. Until then, keep the Google API client in `requirements.in`.

### Why replace (pending live confirmation)

1. **Minimal API surface** — only 2 methods, API-key auth, JSON request/response; no OAuth, protobuf, or discovery benefits are exercised.
2. **Large footprint** — **105 MB** installed across 12 packages; **95 MB** is the client library alone. Removing 12 packages shrinks Docker layers and pip-audit scope.
3. **Zero new dependencies** — `requests` is already pinned; no need for `httpx`.
4. **Stale `requirements.in` comment** — `wg21_paper_tracker` does not use this dependency.

### Why you might keep (counterarguments)

- Official SDK if YouTube scope expands soon (playlists, captions API, OAuth).
- Google-maintained retry/backoff (not used today — code uses manual `time.sleep(0.5)`).

### Migration outline (follow-up task — **not done here**)

1. Sync with **Daniel** before editing `requirements.in` / lockfiles (he owns lock-file audit + aiohttp removal this week).
2. Refactor [`fetcher.py`](../../cppa_youtube_script_tracker/fetcher.py): thin `_youtube_get(path, params)` wrapper around `requests.get`.
3. Map HTTP errors to `QuotaExceededError` via JSON body / `resp.text` (preserve `_is_quota_exceeded_error` semantics).
4. Remove `google-api-python-client` from `requirements.in`; recompile locks on Linux/CI.
5. Update [`test_fetcher.py`](../../cppa_youtube_script_tracker/tests/test_fetcher.py) mocks (`requests.get` or wrapper).
6. Update [`docs/service_api/cppa_youtube_script_tracker.md`](../service_api/cppa_youtube_script_tracker.md) line 116 (`ImportError` note).
7. Delete or archive [`scripts/eval_youtube_direct_http.py`](../../scripts/eval_youtube_direct_http.py) after migration.

---

## 8. Coordination

| Item | Status |
|------|--------|
| Keyed live parity run (`eval_youtube_direct_http.py`) | **Pending** — skipped at evaluation time; required before REPLACE is final |
| Discussed with Daniel | **Not yet** — defer `requirements.in` / lock-file change until aligned |
| Code changes in this task | Evaluation only + throwaway prototype script |
| `requirements.in` modified | **No** (per acceptance criteria for evaluation) |

---

## Acceptance criteria checklist

- [x] Analysis lists Google API client calls, distinct method count (2), transitive dep count (12) and size (105.15 MB)
- [x] Prototype demonstrates direct HTTP feasibility (`scripts/eval_youtube_direct_http.py`)
- [x] Recommendation: **provisional REPLACE** with `requests` (not keep) — conditional on one successful keyed live parity run
- [ ] Keyed live parity run passes (`YOUTUBE_API_KEY` set; `python scripts/eval_youtube_direct_http.py` reports search + videos parity)
- [x] No `requirements.in` change (evaluation task only)
