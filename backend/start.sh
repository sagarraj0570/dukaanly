#!/bin/sh
set -e

echo "==> Running PostGIS initialization and database migrations..."
python -m app.db.init_predeploy
alembic -c alembic.ini upgrade head

echo "==> Seeding demo accounts and catalog..."
python -m app.db.seed_demo

if [ -n "$REDIS_URL" ]; then
    echo "==> Starting Celery background worker..."
    celery -A app.core.celery_app.celery_app worker --loglevel=info --concurrency=1 &
fi

echo "==> Starting Uvicorn web server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
