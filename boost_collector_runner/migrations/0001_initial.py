# Generated manually for production health tracking

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="CollectorGroupRunStatus",
            fields=[
                (
                    "group_id",
                    models.CharField(max_length=64, primary_key=True, serialize=False),
                ),
                ("last_success_at", models.DateTimeField(blank=True, null=True)),
                ("last_failure_at", models.DateTimeField(blank=True, null=True)),
                ("last_run_at", models.DateTimeField(blank=True, null=True)),
                ("last_exit_code", models.IntegerField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Collector group run status",
                "verbose_name_plural": "Collector group run statuses",
                "db_table": "boost_collector_runner_collectorgrouprunstatus",
            },
        ),
    ]
