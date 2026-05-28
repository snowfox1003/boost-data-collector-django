# API contract test fixtures

Recorded JSON payloads used by `tests/test_api_contracts.py` to verify that
GitHub and Slack API responses still deserialize through the Pydantic boundary
schemas in `github_activity_tracker.api_schemas` and `cppa_slack_tracker.api_schemas`.

## Filename convention

`<provider>_<resource>_<YYYY-MM-DD>.json`

The date suffix is the **recording date** (when the fixture was captured or last
refreshed), not the API event timestamp inside the JSON.

## When to refresh

- After GitHub or Slack API version or field changes that affect collectors
- After changing boundary parsers or Pydantic models in `api_schemas.py`
- When contract tests fail in CI with validation errors on these fixtures

## How to refresh

1. Capture a representative response from the live API (or from fetcher/sync debug output).
2. Redact secrets and sensitive data (see below).
3. Save under this directory with a **new** recording date in the filename.
4. Remove or keep older dated files; contract tests glob all matching prefixes.
5. Run: `uv run pytest tests/test_api_contracts.py -v`

### Example: GitHub issue (nested bundle shape)

```bash
# Replace TOKEN, owner, repo, and issue number.
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/OWNER/REPO/issues/NUMBER" \
  > /tmp/issue.json
# Wrap as fetcher bundle if needed: {"issue_info": <issue>, "comments": [...]}
```

### Example: Slack channel (`conversations.list` member)

Use a public channel object from Slack Web API responses; ensure `is_channel: true`
and `is_private: false` if testing channel ingestion paths.

## Redaction rules

- Do **not** commit API tokens, bot tokens, or webhook URLs.
- Mask or omit real user emails when possible (`@example.com` placeholders are fine).
- Trim large binary or irrelevant fields; keep fields the collector parsers use.

## Fixture inventory

| File | Parser |
|------|--------|
| `github_issue_bundle_*.json` | `parse_issue_bundle` |
| `github_pr_bundle_*.json` | `parse_pr_bundle` |
| `github_commit_*.json` | `parse_commit` |
| `slack_team_*.json` | `parse_team` |
| `slack_channel_*.json` | `parse_channel` |
| `slack_user_*.json` | `parse_user` |
| `slack_message_*.json` | `parse_message` |
