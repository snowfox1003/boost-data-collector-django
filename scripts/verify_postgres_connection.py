"""Verify Django can connect to PostgreSQL (used by CI on all platforms)."""

import django
from django.db import connection

django.setup()
connection.ensure_connection()
with connection.cursor() as cursor:
    cursor.execute("SELECT 1")
host = connection.settings_dict.get("HOST") or ""
name = connection.settings_dict.get("NAME") or ""
print(f"PostgreSQL OK (host={host!r}, database={name!r})")
