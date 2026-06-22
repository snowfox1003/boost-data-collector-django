#!/bin/sh
set -e
# Dev compose sets ALLOW_ROOT_ENTRYPOINT=1 so root can chown bind-mounted volumes.
if [ "$(id -u)" = 0 ] && [ "${ALLOW_ROOT_ENTRYPOINT:-0}" = 1 ]; then
  chown -R appuser:appuser /app/logs 2>/dev/null || true
  [ -d /app/celerybeat ] && chown -R appuser:appuser /app/celerybeat 2>/dev/null || true
  # Workspace bind mounts can be huge; recursive chown blocks startup for minutes.
  # Fix only the mount root; existing tree keeps host ownership (typical on macOS/Linux dev).
  chown appuser:appuser /app/workspace 2>/dev/null || true
fi
if [ ! -f /app/core/_version.py ]; then
  python /app/scripts/generate_version_file.py
fi
if [ "$(id -u)" = 0 ] && [ "${ALLOW_ROOT_ENTRYPOINT:-0}" = 1 ]; then
  exec gosu appuser "$@"
fi
exec "$@"
