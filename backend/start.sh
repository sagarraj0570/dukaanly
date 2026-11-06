#!/bin/sh
set -e

# Run migrations only if enabled on this instance (prevents concurrency conflicts across multiple replicas)
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "==> Running PostGIS initialization and database migrations..."
    python -m app.db.init_predeploy
    alembic -c alembic.ini upgrade head
else
    echo "==> Skipping migrations (RUN_MIGRATIONS='${RUN_MIGRATIONS}'). Migrations handled by dedicated deployment runner."
fi

# Only seed demo accounts in development mode.
# Staging and production environments must NEVER automatically create or reset accounts with known default credentials.
if [ "$APP_ENV" = "development" ] && [ "${SEED_DEMO_DATA:-true}" = "true" ]; then
    echo "==> Seeding demo accounts and catalog for development (APP_ENV=development)..."
    python -m app.db.seed_demo
else
    echo "==> Skipping demo seeding (APP_ENV='${APP_ENV:-<missing>}'). Demo accounts are only seeded in development."
fi

# Embedded Celery is only started if explicitly requested for single-container standalone environments.
# Multi-container environments (Docker Compose / Production) run dedicated worker and beat services to prevent duplicate Beat schedules.
if [ "${START_CELERY_EMBEDDED:-false}" = "true" ] && [ -n "$REDIS_URL" ]; then
    echo "==> Starting embedded Celery background worker and scheduler (Beat) for standalone mode..."
    celery -A app.core.celery_app worker -B --loglevel=info --concurrency=1 &
fi

echo "==> Starting Uvicorn web server..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-*}"
