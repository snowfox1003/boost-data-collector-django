from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("cppa_user_tracker", "0009_reddituser_alter_baseprofile_type"),
        ("reddit_activity_tracker", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="redditsubmission",
            old_name="reddit_id",
            new_name="reddit_submission_id",
        ),
        migrations.RenameField(
            model_name="redditcomment",
            old_name="reddit_id",
            new_name="reddit_comment_id",
        ),
        migrations.AlterModelOptions(
            name="redditsubmission",
            options={
                "ordering": ["-created_utc", "reddit_submission_id"],
                "verbose_name": "Reddit submission",
                "verbose_name_plural": "Reddit submissions",
            },
        ),
        migrations.AlterModelOptions(
            name="redditcomment",
            options={
                "ordering": ["created_utc", "reddit_comment_id"],
                "verbose_name": "Reddit comment",
                "verbose_name_plural": "Reddit comments",
            },
        ),
        migrations.RemoveField(
            model_name="redditsubmission",
            name="author",
        ),
        migrations.RemoveField(
            model_name="redditsubmission",
            name="author_id",
        ),
        migrations.RemoveField(
            model_name="redditcomment",
            name="author",
        ),
        migrations.RemoveField(
            model_name="redditcomment",
            name="author_id",
        ),
        migrations.AddField(
            model_name="redditsubmission",
            name="user",
            field=models.ForeignKey(
                blank=True,
                db_column="reddit_user_id",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="submissions",
                to="cppa_user_tracker.reddituser",
            ),
        ),
        migrations.AddField(
            model_name="redditcomment",
            name="user",
            field=models.ForeignKey(
                blank=True,
                db_column="reddit_user_id",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="comments",
                to="cppa_user_tracker.reddituser",
            ),
        ),
    ]
