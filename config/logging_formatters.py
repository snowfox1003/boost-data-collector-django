"""Logging formatters for GCP Cloud Logging ingestion."""

from __future__ import annotations

from pythonjsonlogger import jsonlogger


class CloudLoggingJsonFormatter(jsonlogger.JsonFormatter):
    """JSON lines with severity field for Cloud Logging / Stackdriver."""

    def __init__(self, *args, **kwargs):
        fmt = kwargs.pop(
            "fmt",
            "%(asctime)s %(levelname)s %(name)s %(module)s %(message)s",
        )
        kwargs.setdefault("rename_fields", {"levelname": "severity"})
        kwargs.setdefault("timestamp", True)
        super().__init__(fmt, *args, **kwargs)
