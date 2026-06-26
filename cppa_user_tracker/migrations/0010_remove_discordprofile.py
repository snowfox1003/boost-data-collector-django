"""Drop DiscordProfile from cppa_user_tracker Django state (table unchanged).

The physical table ``cppa_user_tracker_discordprofile`` remains for existing rows.
When the Discord collector app is installed, it adopts this model in its own app
label via a separate state-only migration there.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("cppa_user_tracker", "0009_reddituser_alter_baseprofile_type"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(
                    name="DiscordProfile",
                ),
            ],
            database_operations=[],
        ),
    ]
