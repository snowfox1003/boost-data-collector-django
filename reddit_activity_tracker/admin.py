from django.contrib import admin

from reddit_activity_tracker.models import RedditComment, RedditSubmission


@admin.register(RedditSubmission)
class RedditSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "reddit_id",
        "subreddit",
        "author",
        "title",
        "score",
        "num_comments",
        "created_utc",
        "fetched_at",
    )
    list_filter = ("subreddit",)
    search_fields = ("reddit_id", "title", "author")
    ordering = ("-created_utc", "reddit_id")


@admin.register(RedditComment)
class RedditCommentAdmin(admin.ModelAdmin):
    list_display = (
        "reddit_id",
        "submission",
        "author",
        "score",
        "created_utc",
        "fetched_at",
    )
    list_filter = ("submission__subreddit",)
    search_fields = ("reddit_id", "author", "body")
    raw_id_fields = ("submission",)
    ordering = ("created_utc", "reddit_id")
