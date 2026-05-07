"""Add category_id/category_name to DiscordChannel; add message_type/is_pinned to DiscordMessage."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discord_activity_tracker", "0004_delete_discorduser"),
    ]

    operations = [
        # DiscordChannel: category fields from DiscordChatExporter
        migrations.AddField(
            model_name="discordchannel",
            name="category_id",
            field=models.BigIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="discordchannel",
            name="category_name",
            field=models.CharField(blank=True, default="", max_length=255),
            preserve_default=False,
        ),
        # DiscordMessage: type and pinned fields from DiscordChatExporter
        migrations.AddField(
            model_name="discordmessage",
            name="message_type",
            field=models.CharField(default="Default", db_index=True, max_length=50),
        ),
        migrations.AddField(
            model_name="discordmessage",
            name="is_pinned",
            field=models.BooleanField(default=False, db_index=True),
        ),
        migrations.AddIndex(
            model_name="discordmessage",
            index=models.Index(
                fields=["message_type"],
                name="discord_act_message_type_idx",
            ),
        ),
    ]
