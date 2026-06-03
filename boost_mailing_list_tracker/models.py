"""
Models per docs/Schema.md section 5: Boost Mailing List Tracker.

Sender identity is stored as a soft reference to cppa_user_tracker.MailingListProfile.pk
(column sender_id). Resolve profiles via cppa_user_tracker.services.
"""

from django.db import models


class MailingListName(models.TextChoices):
    """Boost mailing list names; values match the list address used in API URLs (fetcher.BOOST_LIST_URLS)."""

    BOOST_ANNOUNCE = "boost-announce@lists.boost.org", "Boost Announce"
    BOOST_USERS = "boost-users@lists.boost.org", "Boost Users"
    BOOST = "boost@lists.boost.org", "Boost"


class MailingListMessage(models.Model):
    """Mailing list message (sender_profile_id, msg_id, subject, content, list_name, sent_at)."""

    sender_profile_id = models.BigIntegerField(
        db_column="sender_id",
        db_index=True,
        help_text="cppa_user_tracker.MailingListProfile primary key (soft reference).",
    )
    msg_id = models.CharField(max_length=255, unique=True, db_index=True)
    parent_id = models.CharField(max_length=255, blank=True, db_index=True)
    thread_id = models.CharField(max_length=255, blank=True, db_index=True)
    subject = models.CharField(max_length=1024, blank=True)
    content = models.TextField(blank=True)
    list_name = models.CharField(
        max_length=255,
        choices=MailingListName.choices,
        db_index=True,
    )
    sent_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "boost_mailing_list_tracker_mailinglistmessage"
        ordering = ["-sent_at"]
        verbose_name = "Mailing list message"
        verbose_name_plural = "Mailing list messages"

    def __str__(self):
        return f"{self.list_name}: {self.subject[:60]}" if self.subject else self.msg_id
