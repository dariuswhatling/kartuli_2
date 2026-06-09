#!/usr/bin/env bash
set -e

echo "Waiting for database..."
python - <<'PY'
import os, time
import dj_database_url
import psycopg

url = os.environ.get("DATABASE_URL")
if url:
    cfg = dj_database_url.parse(url)
    for attempt in range(30):
        try:
            psycopg.connect(
                host=cfg["HOST"], port=cfg.get("PORT") or 5432,
                dbname=cfg["NAME"], user=cfg["USER"], password=cfg["PASSWORD"],
            ).close()
            print("Database is ready.")
            break
        except Exception as exc:
            print(f"  db not ready ({attempt+1}/30): {exc}")
            time.sleep(2)
    else:
        raise SystemExit("Database never became available.")
PY

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

# Optionally create a superuser from env vars (idempotent).
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "Ensuring superuser exists..."
    python manage.py createsuperuser --noinput || true
fi

echo "Starting Gunicorn..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout 120
