"""
Tests for cppa_slack_tracker.services.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from cppa_user_tracker.services import get_or_create_slack_user
from cppa_slack_tracker.services import (
    get_or_create_slack_channel,
    get_or_create_slack_team,
    add_channel_membership_change,
    save_slack_message,
    sync_channel_memberships,
    _parse_slack_ts_string,
)
from cppa_slack_tracker.models import (
    SlackChannelMembership,
    SlackChannelMembershipChangeLog,
)
from cppa_user_tracker.models import Email, SlackUser


@pytest.mark.django_db
class TestSlackService:
    """Tests for cppa_slack_tracker.services."""

    def test_add_slack_team(self):
        """Test adding a Slack team."""
        team_data = {
            "team_id": "T12345678",
            "team_name": "Test Team",
        }
        team, _ = get_or_create_slack_team(team_data)

        assert team.team_id == "T12345678"
        assert team.team_name == "Test Team"

    def test_update_slack_team(self, sample_slack_team):
        """Test updating an existing Slack team."""
        team_data = {
            "team_id": "T12345678",
            "team_name": "Updated Team Name",
        }

        team, _ = get_or_create_slack_team(team_data)
        assert team.team_id == "T12345678"
        assert team.team_name == "Updated Team Name"

    def test_add_slack_user(self, sample_slack_user_data):
        """Test adding a Slack user."""
        user, _ = get_or_create_slack_user(sample_slack_user_data)
        assert user.slack_user_id == "U87654321"
        assert user.username == "janedoe"
        assert user.display_name == "Jane Doe"
        assert user.avatar_url == "https://example.com/jane.jpg"
        # Email is created when provided in profile; identity is not created here
        emails = Email.objects.filter(base_profile=user)
        assert emails.exists()
        assert emails.first().email == "jane@example.com"

    def test_add_slack_user_without_email(self):
        """Test adding a Slack user without email: no email or identity created."""
        user_data = {
            "id": "U11111111",
            "name": "nomail",
            "real_name": "No Email User",
            "profile": {},
        }
        user, _ = get_or_create_slack_user(user_data)
        assert user.slack_user_id == "U11111111"
        assert user.identity is None
        emails = Email.objects.filter(base_profile=user)
        assert not emails.exists()

    def test_update_slack_user(self, sample_slack_user):
        """Test updating an existing Slack user."""
        user_data = {
            "id": "U12345678",
            "name": "updateduser",
            "real_name": "Updated Name",
            "profile": {
                "image_72": "https://example.com/new-avatar.jpg",
            },
        }

        user, _ = get_or_create_slack_user(user_data)
        assert user.slack_user_id == "U12345678"
        assert user.username == "updateduser"
        assert user.display_name == "Updated Name"

    def test_add_slack_channel(
        self, sample_slack_team, sample_slack_user, sample_slack_channel_data
    ):
        """Test adding a Slack channel."""
        channel, _ = get_or_create_slack_channel(
            sample_slack_channel_data,
            sample_slack_team,
        )

        assert channel.channel_id == "C87654321"
        assert channel.channel_name == "random"
        assert channel.channel_type == "public_channel"
        assert channel.description == "Random discussions"
        assert channel.creator == sample_slack_user

    def test_add_channel_membership_change(
        self, sample_slack_channel, sample_slack_user
    ):
        """Test adding a channel membership change."""
        log = add_channel_membership_change(
            sample_slack_channel,
            "U12345678",
            "1609459200.123456",
            is_joined=True,
        )

        assert log.channel == sample_slack_channel
        assert log.user == sample_slack_user
        assert log.is_joined

        # Check that membership was created
        membership = SlackChannelMembership.objects.get(
            channel=sample_slack_channel, user=sample_slack_user
        )
        assert not membership.is_deleted

    def test_add_channel_leave(
        self, sample_slack_channel, sample_slack_user, sample_slack_membership
    ):
        """Test adding a channel leave event."""
        log = add_channel_membership_change(
            sample_slack_channel,
            "U12345678",
            "1609459200.123456",
            is_joined=False,
        )

        assert not log.is_joined

        # Check that membership was marked as deleted
        membership = SlackChannelMembership.objects.get(
            channel=sample_slack_channel, user=sample_slack_user
        )
        assert membership.is_deleted

    def test_save_slack_message(
        self,
        sample_slack_channel,
        sample_slack_user,
        sample_slack_message_data,
    ):
        """Test saving a Slack message."""
        message = save_slack_message(
            sample_slack_channel,
            sample_slack_message_data,
        )

        assert message is not None
        assert message.channel == sample_slack_channel
        assert message.user == sample_slack_user
        assert message.message == "This is a test message"
        assert message.ts == "1609459200.123456"

    def test_save_slack_message_channel_join(
        self, sample_slack_channel, sample_slack_user
    ):
        """Test that channel_join messages are handled correctly."""
        message_data = {
            "user": "U12345678",
            "text": "joined the channel",
            "ts": "1609459200.123456",
            "subtype": "channel_join",
        }

        message = save_slack_message(
            sample_slack_channel,
            message_data,
        )
        # Should return None (not saved as message)
        assert message is None

        # But should create membership change log
        logs = SlackChannelMembershipChangeLog.objects.filter(
            channel=sample_slack_channel,
            user=sample_slack_user,
            is_joined=True,
        )
        assert logs.exists()

    def test_save_slack_message_with_ignored_subtype(self, sample_slack_channel):
        """Test that ignored subtypes return None."""
        message_data = {
            "text": "Bot message",
            "ts": "1609459200.123456",
            "subtype": "bot_message",
        }

        message = save_slack_message(
            sample_slack_channel,
            message_data,
        )
        assert message is None

    def test_update_slack_message(self, sample_slack_message):
        """Test updating an existing message."""
        message_data = {
            "user": "U12345678",
            "text": "Updated message text",
            "ts": "1234567890.123456",
            "edited": {
                "ts": "1234567891.000000",
            },
        }

        message = save_slack_message(
            sample_slack_message.channel,
            message_data,
        )

        assert message.message == "Updated message text"
        assert message.slack_message_updated_at is not None

    def test_sync_channel_memberships(
        self, sample_slack_channel, sample_slack_user, sample_identity
    ):
        """Test syncing channel memberships."""
        # Create another user (SlackUser from cppa_user_tracker)
        user2 = SlackUser.objects.create(
            identity=sample_identity,
            slack_user_id="U22222222",
            username="user2",
        )

        # Create initial membership
        SlackChannelMembership.objects.create(
            channel=sample_slack_channel,
            user=sample_slack_user,
        )

        # Sync with new member list
        sync_channel_memberships(
            sample_slack_channel,
            ["U22222222"],
        )

        # Check that user1 is marked as deleted
        membership1 = SlackChannelMembership.objects.get(
            channel=sample_slack_channel, user=sample_slack_user
        )
        assert membership1.is_deleted

        # Check that user2 was added
        membership2 = SlackChannelMembership.objects.get(
            channel=sample_slack_channel, user=user2
        )
        assert not membership2.is_deleted

    def test_parse_slack_ts_string(self):
        """Test parsing Slack timestamp strings."""
        ts = "1609459200.123456"
        dt = _parse_slack_ts_string(ts)
        assert dt.year == 2021
        assert dt.month == 1
        assert dt.day == 1

    def test_save_slack_message_me_message_subtype(
        self, sample_slack_channel, sample_slack_user
    ):
        """Test that me_message subtype stores text as <@user_id> text."""
        message_data = {
            "user": "U12345678",
            "text": "waves",
            "ts": "1609459200.123456",
            "subtype": "me_message",
        }
        message = save_slack_message(sample_slack_channel, message_data)
        assert message is not None
        assert message.message == "<@U12345678> waves"

    def test_save_slack_message_unknown_user_fetches_info_and_creates_unknown_without_fetch_for_sentinel(
        self, sample_slack_channel
    ):
        """When user is not in DB, fetch_user_info is called for that id; when API returns nothing, message is saved with unknown user (-1), and -1 is never passed to fetch_user_info."""
        from unittest.mock import patch
        from cppa_user_tracker.models import SlackUser

        message_data = {
            "user": "U99999999",  # not in DB
            "text": "from unknown",
            "ts": "1609459200.999999",
        }
        with patch(
            "cppa_slack_tracker.services.fetch_user_info",
            return_value=None,
        ) as mock_fetch:
            message = save_slack_message(sample_slack_channel, message_data)
        assert message is not None
        assert message.message == "from unknown"
        # Unknown user should be created with slack_user_id -1
        unknown = SlackUser.objects.get(slack_user_id="-1")
        assert unknown.username == "unknown"
        assert message.user == unknown
        # fetch_user_info should have been called for U99999999, not for -1
        mock_fetch.assert_called()
        calls = [c[0][0] for c in mock_fetch.call_args_list]
        assert "U99999999" in calls
        assert "-1" not in calls

    def test_get_or_create_slack_team_requires_team_id(self):
        with pytest.raises(ValueError, match="Slack team ID is required"):
            get_or_create_slack_team({})

    def test_parse_slack_ts_string_invalid_returns_now_utc(self):
        before = datetime.now(timezone.utc)
        dt = _parse_slack_ts_string("not-a-valid-ts")
        after = datetime.now(timezone.utc)
        assert before <= dt <= after

    def test_get_or_create_slack_channel_skips_private(self, sample_slack_team):
        ch, created = get_or_create_slack_channel(
            {
                "id": "Cprivate01",
                "name": "secret",
                "is_channel": True,
                "is_private": True,
            },
            sample_slack_team,
        )
        assert ch is None
        assert created is False

    def test_get_or_create_slack_channel_topic_when_no_purpose(
        self, sample_slack_team, sample_slack_user
    ):
        cid = "Ctopiconly01"
        ch, created = get_or_create_slack_channel(
            {
                "id": cid,
                "name": "announcements",
                "is_channel": True,
                "is_private": False,
                "topic": {"value": "Read this first"},
                "creator": "U12345678",
            },
            sample_slack_team,
        )
        assert created is True
        assert ch.description == "Read this first"
        assert ch.creator == sample_slack_user

    def test_get_or_create_slack_channel_updates_existing(
        self, sample_slack_team, sample_slack_user, sample_slack_channel
    ):
        data = {
            "id": sample_slack_channel.channel_id,
            "name": "renamed",
            "is_channel": True,
            "is_private": False,
            "purpose": {"value": "new purpose"},
            "creator": "U12345678",
        }
        ch, created = get_or_create_slack_channel(data, sample_slack_team)
        assert created is False
        assert ch.channel_name == "renamed"
        assert ch.description == "new purpose"

    def test_save_slack_message_channel_join_without_ts_logs(
        self, sample_slack_channel, caplog
    ):
        import logging

        with caplog.at_level(logging.WARNING):
            msg = save_slack_message(
                sample_slack_channel,
                {"subtype": "channel_join", "user": "U12345678"},
            )
        assert msg is None
        assert "Skipping channel_join without ts" in caplog.text

    def test_save_slack_message_channel_leave_without_ts_logs(
        self, sample_slack_channel, caplog
    ):
        import logging

        with caplog.at_level(logging.WARNING):
            msg = save_slack_message(
                sample_slack_channel,
                {"subtype": "channel_leave", "user": "U12345678"},
            )
        assert msg is None
        assert "Skipping channel_leave without ts" in caplog.text

    def test_save_slack_message_file_comment_with_comment_dict(
        self, sample_slack_channel, sample_slack_user
    ):
        message_data = {
            "user": "U12345678",
            "subtype": "file_comment",
            "text": "Nice file",
            "ts": "1609459200.555555",
            "comment": {"comment": "nested text"},
        }
        msg = save_slack_message(sample_slack_channel, message_data)
        assert msg is not None
        assert "Nice file" in msg.message
        assert "nested text" in msg.message

    def test_save_slack_message_file_placeholder_without_user_returns_none(
        self, sample_slack_channel
    ):
        msg = save_slack_message(
            sample_slack_channel,
            {"text": "A file was commented on", "ts": "1609459200.666666"},
        )
        assert msg is None

    def test_save_slack_message_requires_user_for_normal_message(
        self, sample_slack_channel
    ):
        with pytest.raises(ValueError, match="User not found"):
            save_slack_message(
                sample_slack_channel,
                {"text": "hello", "ts": "1609459200.777777"},
            )

    def test_add_channel_membership_change_updates_existing_log_is_joined(
        self, sample_slack_channel, sample_slack_user
    ):
        ts = "1609459200.888888"
        log1 = add_channel_membership_change(
            sample_slack_channel, "U12345678", ts, is_joined=True
        )
        assert log1.is_joined is True
        log2 = add_channel_membership_change(
            sample_slack_channel, "U12345678", ts, is_joined=False
        )
        assert log2.pk == log1.pk
        log1.refresh_from_db()
        assert log1.is_joined is False

    def test_add_channel_membership_rejoin_restores_deleted_membership(
        self, sample_slack_channel, sample_slack_user, sample_slack_membership
    ):
        sample_slack_membership.is_deleted = True
        sample_slack_membership.save()
        add_channel_membership_change(
            sample_slack_channel,
            "U12345678",
            "1609459200.999999",
            is_joined=True,
        )
        sample_slack_membership.refresh_from_db()
        assert not sample_slack_membership.is_deleted

    def test_sync_channel_memberships_skips_unknown_user_ids(
        self, sample_slack_channel, sample_slack_user
    ):
        SlackChannelMembership.objects.create(
            channel=sample_slack_channel,
            user=sample_slack_user,
        )
        sync_channel_memberships(
            sample_slack_channel,
            ["U12345678", "Unonexistent"],
        )
        m = SlackChannelMembership.objects.get(
            channel=sample_slack_channel, user=sample_slack_user
        )
        assert not m.is_deleted

    def test_sync_channel_memberships_remove_continues_if_user_missing(
        self, sample_slack_channel, sample_slack_user
    ):
        SlackChannelMembership.objects.create(
            channel=sample_slack_channel,
            user=sample_slack_user,
        )
        with patch.object(
            SlackUser.objects,
            "get",
            side_effect=SlackUser.DoesNotExist,
        ):
            sync_channel_memberships(sample_slack_channel, [])
        m = SlackChannelMembership.objects.get(
            channel=sample_slack_channel, user=sample_slack_user
        )
        assert not m.is_deleted
