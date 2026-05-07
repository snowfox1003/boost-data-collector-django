# Merged initial migration: WG21 Mailing, WG21 Paper (year not null), WG21 Paper Author

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("cppa_user_tracker", "0008_wg21paperauthorprofile_author_alias"),
    ]

    operations = [
        migrations.CreateModel(
            name="WG21Mailing",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "mailing_date",
                    models.CharField(db_index=True, max_length=7, unique=True),
                ),
                ("title", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "WG21 Mailing",
                "verbose_name_plural": "WG21 Mailings",
                "db_table": "wg21_paper_tracker_wg21mailing",
                "ordering": ["-mailing_date"],
            },
        ),
        migrations.CreateModel(
            name="WG21Paper",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("paper_id", models.CharField(db_index=True, max_length=255)),
                ("url", models.URLField(max_length=1024)),
                ("title", models.CharField(db_index=True, max_length=1024)),
                (
                    "document_date",
                    models.DateField(blank=True, db_index=True, null=True),
                ),
                ("year", models.IntegerField(db_index=True, default=0)),
                (
                    "subgroup",
                    models.CharField(
                        blank=True, db_index=True, max_length=255
                    ),
                ),
                (
                    "is_downloaded",
                    models.BooleanField(db_index=True, default=False),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "mailing",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="papers",
                        to="wg21_paper_tracker.wg21mailing",
                    ),
                ),
            ],
            options={
                "verbose_name": "WG21 Paper",
                "verbose_name_plural": "WG21 Papers",
                "db_table": "wg21_paper_tracker_wg21paper",
                "ordering": ["-document_date", "-paper_id", "-year"],
                "unique_together": {("paper_id", "year")},
            },
        ),
        migrations.CreateModel(
            name="WG21PaperAuthor",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("author_order", models.PositiveIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "paper",
                    models.ForeignKey(
                        db_column="paper_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="authors",
                        to="wg21_paper_tracker.wg21paper",
                    ),
                ),
                (
                    "profile",
                    models.ForeignKey(
                        db_column="profile_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="papers",
                        to="cppa_user_tracker.wg21paperauthorprofile",
                    ),
                ),
            ],
            options={
                "verbose_name": "WG21 Paper Author",
                "verbose_name_plural": "WG21 Paper Authors",
                "db_table": "wg21_paper_tracker_wg21paperauthor",
                "ordering": ["id"],
                "unique_together": {("paper", "profile")},
            },
        ),
    ]
