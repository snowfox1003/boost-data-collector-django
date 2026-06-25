"""
Service layer for boost_mailing_list_tracker.

All creates/updates/deletes for this app's models must go through functions here.
See CONTRIBUTING.md.
"""

from __future__ import annotations

import logging
from datetime import datetime

from .models import MailingListMessage, MailingListName

logger = logging.getLogger(__name__)


# --- MailingListMessage ---
def get_or_create_mailing_list_message(
    sender_profile_id: int,
    msg_id: str,
    sent_at: datetime | None,
    parent_id: str = "",
    thread_id: str = "",
    subject: str = "",
    content: str = "",
    list_name: str = "",
) -> tuple[MailingListMessage, bool]:
    """Get or create a MailingListMessage by msg_id (unique).

      ``sender_profile_id`` is the primary key of a cppa_user_tracker.MailingListProfile
    (resolve or create profiles via cppa_user_tracker.services).

      If the message already exists (same msg_id), no fields are updated.
      Returns (message, created).

      Raises:
          ValueError: If msg_id is empty or whitespace-only, list_name is invalid,
              or sender_profile_id is not a positive integer.
    """
    if (
        not isinstance(sender_profile_id, int)
        or isinstance(sender_profile_id, bool)
        or sender_profile_id < 1
    ):
        raise ValueError("sender_profile_id must be a positive integer.")

    if not (msg_id and msg_id.strip()):
        raise ValueError("msg_id must not be empty.")

    list_value = (list_name or "").strip()
    valid_values = [m.value for m in MailingListName]

    if list_value not in valid_values:
        raise ValueError(
            f"list_name must be one of {valid_values}, got {list_value!r}."
        )

    return MailingListMessage.objects.get_or_create(
        msg_id=msg_id.strip(),
        defaults={
            "sender_profile_id": sender_profile_id,
            "parent_id": parent_id,
            "thread_id": thread_id,
            "subject": subject,
            "content": content,
            "list_name": list_value,
            "sent_at": sent_at,
        },
    )


def delete_mailing_list_message(message: MailingListMessage) -> None:
    """Delete a MailingListMessage."""
    message.delete()
