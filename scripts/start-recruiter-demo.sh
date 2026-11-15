#!/usr/bin/env sh
set -eu

mkdir -p /app/storage/uploads /app/storage/processed /app/storage/temp

attempt=0
max_attempts=30

until uv run --no-sync alembic upgrade head; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge "$max_attempts" ]; then
    echo "PostgreSQL migrations did not become ready after $max_attempts attempts." >&2
    exit 1
  fi
  echo "Waiting for PostgreSQL before running migrations ($attempt/$max_attempts)..." >&2
  sleep 2
done

exec /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf
