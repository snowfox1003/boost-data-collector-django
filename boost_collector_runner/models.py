"""Models for scheduled collector group run tracking."""

from django.db import models


class CollectorGroupRunStatus(models.Model):
    """Last run outcome per YAML schedule group (e.g. github, slack)."""

    group_id = models.CharField(max_length=64, primary_key=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_exit_code = models.IntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "boost_collector_runner_collectorgrouprunstatus"
        verbose_name = "Collector group run status"
        verbose_name_plural = "Collector group run statuses"

    def __str__(self) -> str:
        return f"CollectorGroupRunStatus(group_id={self.group_id})"
