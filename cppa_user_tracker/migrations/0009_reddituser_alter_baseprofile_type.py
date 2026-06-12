from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("cppa_user_tracker", "0008_wg21paperauthorprofile_author_alias"),
    ]

    operations = [
        migrations.CreateModel(
            name="RedditUser",
            fields=[
                (
                    "baseprofile_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="cppa_user_tracker.baseprofile",
                    ),
                ),
                (
                    "reddit_user_id",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        max_length=64,
                        null=True,
                        unique=True,
                    ),
                ),
                (
                    "username",
                    models.CharField(db_index=True, max_length=255, unique=True),
                ),
                (
                    "display_name",
                    models.CharField(blank=True, db_index=True, max_length=255),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            bases=("cppa_user_tracker.baseprofile",),
        ),
        migrations.AlterField(
            model_name="baseprofile",
            name="type",
            field=models.CharField(
                choices=[
                    ("github", "GitHub"),
                    ("slack", "Slack"),
                    ("mailing_list", "Mailing list"),
                    ("wg21", "WG21"),
                    ("discord", "Discord"),
                    ("youtube", "YouTube"),
                    ("reddit", "Reddit"),
                ],
                db_index=True,
                max_length=20,
            ),
        ),
    ]
