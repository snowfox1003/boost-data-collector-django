"""Models per docs/Schema.md section 12: Reddit Activity Tracker."""

from django.db import models


class RedditSubmission(models.Model):
    """Reddit post (submission) from a subreddit; keyed by reddit_id (t3_* fullname)."""

    reddit_id = models.CharField(max_length=20, unique=True, db_index=True)
    subreddit = models.CharField(max_length=128, db_index=True)
    author = models.CharField(max_length=255, blank=True)
    author_id = models.CharField(max_length=64, blank=True)
    title = models.CharField(max_length=1024)
    selftext = models.TextField(blank=True)
    selftext_html = models.TextField(blank=True)
    url = models.URLField(max_length=1024)
    permalink = models.CharField(max_length=512)
    score = models.IntegerField(default=0)
    num_comments = models.IntegerField(default=0)
    created_utc = models.IntegerField(db_index=True)
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_utc", "reddit_id"]
        verbose_name = "Reddit submission"
        verbose_name_plural = "Reddit submissions"

    def __str__(self) -> str:
        return f"{self.reddit_id}: {self.title[:60]}"


class RedditComment(models.Model):
    """Reddit comment on a submission; keyed by reddit_id (t1_* fullname)."""

    reddit_id = models.CharField(max_length=20, unique=True, db_index=True)
    submission = models.ForeignKey(
        RedditSubmission,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    parent_id = models.CharField(max_length=20, blank=True)
    author = models.CharField(max_length=255, blank=True)
    author_id = models.CharField(max_length=64, blank=True)
    body = models.TextField(blank=True)
    url = models.URLField(max_length=1024)
    score = models.IntegerField(default=0)
    created_utc = models.IntegerField(db_index=True)
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_utc", "reddit_id"]
        verbose_name = "Reddit comment"
        verbose_name_plural = "Reddit comments"

    def __str__(self) -> str:
        return f"{self.reddit_id} on {self.submission.reddit_id}"
