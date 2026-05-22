"""Tests for JSON logging formatter."""

import json
import logging

from config.logging_formatters import CloudLoggingJsonFormatter


def test_cloud_logging_json_formatter_emits_severity():
    formatter = CloudLoggingJsonFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="something failed",
        args=(),
        exc_info=None,
    )
    line = formatter.format(record)
    data = json.loads(line)
    assert data["severity"] == "ERROR"
    assert "something failed" in data["message"]
