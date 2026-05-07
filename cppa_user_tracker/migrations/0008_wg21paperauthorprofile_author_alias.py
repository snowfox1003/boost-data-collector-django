"""Add author_alias field to Wg21PaperAuthorProfile (sequential after 0007)."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cppa_user_tracker", "0007_youtubespeaker_external_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="wg21paperauthorprofile",
            name="author_alias",
            field=models.CharField(blank=True, db_index=True, default="", max_length=255),
            preserve_default=False,
        ),
    ]
