# Generated manually for identity-hub decoupling (soft sender_profile_id).

import django.core.validators
from django.db import migrations, models


def drop_sender_foreign_key(apps, schema_editor):
    """Drop PostgreSQL FK on sender_id; column values are unchanged."""
    if schema_editor.connection.vendor != "postgresql":
        return
    table = "boost_mailing_list_tracker_mailinglistmessage"
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT tc.constraint_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.table_schema = CURRENT_SCHEMA()
              AND tc.table_name = %s
              AND tc.constraint_type = 'FOREIGN KEY'
              AND kcu.column_name = 'sender_id'
            """,
            [table],
        )
        for (constraint_name,) in cursor.fetchall():
            cursor.execute(
                f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{constraint_name}"'
            )


def noop_reverse(apps, schema_editor):
    """Re-adding FK requires manual verification of sender_id orphans; not automated."""


class Migration(migrations.Migration):

    dependencies = [
        ("boost_mailing_list_tracker", "0002_list_name_choices"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(drop_sender_foreign_key, noop_reverse),
            ],
            state_operations=[
                migrations.RemoveField(
                    model_name="mailinglistmessage",
                    name="sender",
                ),
                migrations.AddField(
                    model_name="mailinglistmessage",
                    name="sender_profile_id",
                    field=models.BigIntegerField(
                        db_column="sender_id",
                        db_index=True,
                        validators=[django.core.validators.MinValueValidator(1)],
                        help_text="cppa_user_tracker.MailingListProfile primary key (soft reference).",
                    ),
                    preserve_default=False,
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="mailinglistmessage",
            constraint=models.CheckConstraint(
                check=models.Q(("sender_profile_id__gte", 1)),
                name="boost_mailing_list_tracker_sender_profile_id_gte_1",
            ),
        ),
    ]
