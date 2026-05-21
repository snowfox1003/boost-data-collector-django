# cppa_slack_tracker.services

**Module path:** `cppa_slack_tracker.services`
**Description:** Service layer for Slack tracker models. All creates/updates/deletes for this app's models must go through functions in this module.

**Type notation:** Model types refer to `cppa_slack_tracker.models` unless noted in docstrings.

---
<!-- SERVICE_API:GENERATED:START -->

## Public API (generated)

| Function | Parameters | Return type | Summary |
| --- | --- | --- | --- |
| `add_channel_membership_change` | channel: SlackChannel, slack_user_id: str, ts: str, is_joined: bool | SlackChannelMembershipChangeLog | Record a channel join/leave and update current membership. Returns the change log entry. Raises ValueError if user not found. |
| `get_or_create_slack_channel` | slack_channel: dict[str, Any], team: SlackTeam | tuple[Optional[SlackChannel], bool] | Get or create a Slack channel. Returns (channel, created); channel is None when skipped. |
| `get_or_create_slack_team` | team_data: dict[str, Any] | tuple[SlackTeam, bool] | Get or create a Slack team (workspace). Requires team_data['team_id']. Returns (SlackTeam, created). |
| `save_slack_message` | channel: SlackChannel, slack_message: dict[str, Any] | Optional[SlackMessage] | Save or update a Slack message from a Slack API payload. |
| `sync_channel_memberships` | channel: SlackChannel, member_ids: list[str] | None | Sync current channel memberships to match member_ids (add new, mark removed as deleted). |

<!-- SERVICE_API:GENERATED:END -->

## Related

- [Service API index](README.md)
- [CONTRIBUTING.md](../../CONTRIBUTING.md)
