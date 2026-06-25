"""
Models per docs/Schema.md section 7: WG21 Papers Tracker.
References cppa_user_tracker.WG21PaperAuthorProfile (section 1) as author.
"""

from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from django.db.models.manager import Manager


class WG21Mailing(models.Model):
    """WG21 mailing release (mailing_date, title)."""

    mailing_date = models.CharField(max_length=7, unique=True, db_index=True)
    title = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    if TYPE_CHECKING:
        id: int

    class Meta:
        ordering = ["-mailing_date"]
        verbose_name = "WG21 Mailing"
        verbose_name_plural = "WG21 Mailings"

    def __str__(self):
        return f"{self.mailing_date} ({self.title})"


class WG21Paper(models.Model):
    """WG21 paper (paper_id, url, title, document_date, year, mailing, subgroup, is_downloaded)."""

    paper_id = models.CharField(max_length=255, db_index=True)
    url = models.URLField(max_length=1024)
    title = models.CharField(max_length=1024, db_index=True)
    document_date = models.DateField(db_index=True, null=True, blank=True)
    year = models.IntegerField(default=0, db_index=True)
    mailing = models.ForeignKey(
        WG21Mailing,
        on_delete=models.CASCADE,
        related_name="papers",
    )
    subgroup = models.CharField(max_length=255, blank=True, db_index=True)
    is_downloaded = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    if TYPE_CHECKING:
        mailing_id: int
        authors: Manager["WG21PaperAuthor"]

    class Meta:
        unique_together = [["paper_id", "year"]]
        ordering = ["-document_date", "-paper_id", "-year"]
        verbose_name = "WG21 Paper"
        verbose_name_plural = "WG21 Papers"

    def __str__(self):
        return f"{self.paper_id}: {self.title[:60]}"


class WG21PaperAuthor(models.Model):
    """Paper-author link (paper_id, profile_id->WG21PaperAuthorProfile)."""

    paper = models.ForeignKey(
        WG21Paper,
        on_delete=models.CASCADE,
        related_name="authors",
        db_column="paper_id",
    )
    profile = models.ForeignKey(
        "cppa_user_tracker.WG21PaperAuthorProfile",
        on_delete=models.CASCADE,
        related_name="papers",
        db_column="profile_id",
    )
    author_order = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (("paper", "profile"),)
        ordering = ["id"]
        verbose_name = "WG21 Paper Author"
        verbose_name_plural = "WG21 Paper Authors"

    def __str__(self):
        return f"{self.paper.paper_id} - {self.profile.display_name}"
