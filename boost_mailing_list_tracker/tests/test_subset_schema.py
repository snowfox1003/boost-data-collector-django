"""Tests that run under subset INSTALLED_APPS (no cppa_user_tracker tables).

Run:
  DJANGO_SETTINGS_MODULE=config.test_settings_subset_boost_mailing_list \\
    uv run pytest boost_mailing_list_tracker/tests/test_subset_schema.py -m subset_schema -v
"""

from datetime import datetime, timezone

import pytest

from boost_mailing_list_tracker import services
from boost_mailing_list_tracker.models import MailingListMessage, MailingListName


@pytest.mark.django_db
@pytest.mark.subset_schema
def test_mailing_list_message_create_with_soft_sender_id():
    """MailingListMessage persists with sender_profile_id only (no identity hub ORM)."""
    sender_id = 42_001
    sent_at = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    msg, created = services.get_or_create_mailing_list_message(
        sender_id,
        msg_id="<subset@example.com>",
        sent_at=sent_at,
        list_name=MailingListName.BOOST_USERS.value,
        subject="Subset test",
        content="Body",
    )
    assert created is True
    assert msg.sender_profile_id == sender_id
    assert MailingListMessage.objects.filter(msg_id="<subset@example.com>").exists()


@pytest.mark.django_db
@pytest.mark.subset_schema
def test_mailing_list_message_rejects_invalid_sender_profile_id():
    """Service validates sender_profile_id without requiring hub models."""
    sent_at = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(
        ValueError, match="sender_profile_id must be a positive integer"
    ):
        services.get_or_create_mailing_list_message(
            0,
            msg_id="<bad-sender@example.com>",
            sent_at=sent_at,
            list_name=MailingListName.BOOST.value,
        )
