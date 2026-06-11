# cppa_user_tracker.services

**Module path:** `cppa_user_tracker.services`
**Description:** Identity, profiles (GitHubAccount, SlackUser, MailingListProfile, DiscordProfile, etc.), emails, and staging (TmpIdentity, TempProfileIdentityRelation). Single place for all writes to cppa_user_tracker models.

**Type notation:** Model types refer to `cppa_user_tracker.models` (e.g. `Identity`, `BaseProfile`, `Email`).

---
<!-- SERVICE_API:GENERATED:START -->

## Public API (generated)

| Function | Parameters | Return type | Summary |
| --- | --- | --- | --- |
| `add_email` | base_profile: BaseProfile, email: str, is_primary: bool = False, is_active: bool = True | Email | Add an email to a BaseProfile. Returns the new Email. |
| `add_temp_profile_identity_relation` | base_profile: BaseProfile, target_identity: TmpIdentity | tuple[TempProfileIdentityRelation, bool] | Link a BaseProfile to a TmpIdentity (staging). Returns (relation, created). |
| `create_identity` | display_name: str = '', description: str = '' | Identity | Create an Identity. Returns the new Identity. |
| `create_tmp_identity` | display_name: str = '', description: str = '' | TmpIdentity | Create a TmpIdentity (staging). Returns the new TmpIdentity. |
| `get_github_account_by_username` | username: str | GitHubAccount \| None | Return GitHubAccount for username, or None if not found (read-only lookup). |
| `get_mailing_list_profile_by_id` | profile_id: int | MailingListProfile \| None | Return MailingListProfile for profile_id, or None if not found (read-only lookup). |
| `get_mailing_list_profiles_by_ids` | profile_ids: list[int] | dict[int, MailingListProfile] | Return mailing-list profiles keyed by pk for the given ids (read-only bulk lookup). |
| `get_or_create_discord_profile` | discord_user_id: int, username: str = '', display_name: str = '', avatar_url: str = '', is_bot: bool = False, identity: Identity \| None = None | tuple[DiscordProfile, bool] | Get or create a DiscordProfile by discord_user_id. Returns (profile, created). |
| `get_or_create_github_account` | github_account_id: int, username: str = '', display_name: str = '', avatar_url: str = '', account_type: str = GitHubAccountType.USER, identity: Identity \| None = None | tuple[GitHubAccount, bool] | Get or create a GitHubAccount by github_account_id. Returns (account, created). |
| `get_or_create_identity` | display_name: str = '', description: str = '', defaults: dict[str, Any] \| None = None | tuple[Identity, bool] | Get or create an Identity by display_name. If exists, updates description from defaults. |
| `get_or_create_mailing_list_profile` | display_name: str = '', email: str = '' | tuple[MailingListProfile, bool] | Get or create a MailingListProfile by display_name and email. Returns (profile, created). |
| `get_or_create_owner_account` | client: GitHubClientProtocol, owner: str | GitHubAccount | Get or create a GitHubAccount for an owner (org or user). For use by any app. |
| `get_or_create_slack_user` | user_data: SlackUserPayload \| dict[str, Any] | tuple[SlackUser, bool] | Get or create a SlackUser from Slack API user data. Returns (SlackUser, created). |
| `get_or_create_unknown_github_account` | name: str \| None = None, email: str = '' | tuple[GitHubAccount, bool] | Get or create a GitHubAccount for commits with no API author/committer. |
| `get_or_create_wg21_paper_author_profile` | display_name: str, email: str \| None = None | tuple[WG21PaperAuthorProfile, bool] | Get or create a WG21PaperAuthorProfile by display_name, with optional email disambiguation. |
| `get_or_create_youtube_speaker` | external_id: str, display_name: str = '', identity: Identity \| None = None | tuple[YoutubeSpeaker, bool] | Get or create a YoutubeSpeaker by external_id. Returns (speaker, created). |
| `remove_email` | email_obj: Email | None | Remove an email from a profile. |
| `remove_temp_profile_identity_relation` | base_profile: BaseProfile, target_identity: TmpIdentity | None | Remove the staging relation between base_profile and target_identity. |
| `update_email` | email_obj: Email, **kwargs: Any | Email | Update an Email instance. Allowed keys: email, is_primary, is_active. |

<!-- SERVICE_API:GENERATED:END -->

## Related

- [Service API index](README.md)
- [CONTRIBUTING.md](../../CONTRIBUTING.md)
- [Schema](../Schema.md)
