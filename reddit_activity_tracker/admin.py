from django.contrib import admin

from reddit_activity_tracker.models import RedditComment, RedditSubmission


@admin.register(RedditSubmission)
class RedditSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "reddit_submission_id",
        "subreddit",
        "user",
        "title",
        "score",
        "num_comments",
        "created_utc",
        "fetched_at",
    )
    list_filter = ("subreddit",)
    search_fields = ("reddit_submission_id", "title", "user__username")
    raw_id_fields = ("user",)
    ordering = ("-created_utc", "reddit_submission_id")


@admin.register(RedditComment)
class RedditCommentAdmin(admin.ModelAdmin):
    list_display = (
        "reddit_comment_id",
        "submission",
        "user",
        "score",
        "created_utc",
        "fetched_at",
    )
    list_filter = ("submission__subreddit",)
    search_fields = ("reddit_comment_id", "user__username", "body")
    raw_id_fields = ("submission", "user")
    ordering = ("created_utc", "reddit_comment_id")
