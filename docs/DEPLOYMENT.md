# Dukaanly — Production Deployment Guide

## 1. Architecture Overview
Dukaanly is structured as a resilient **Modular Monolith** designed for high throughput, predictable latency, and low operational overhead.

### Component Topology
- **Web / Mobile Frontend**: React + Vite + TypeScript (Single Page Application served via Nginx or static CDN).
- **Application Server (API)**: FastAPI running on Uvicorn ASGI workers.
- **Database**: PostgreSQL 16+ with PostGIS spatial extensions.
- **Caching & Real-Time Broker**: Redis 7+ (sliding window rate limiting, caching, WebSocket pub/sub).
- **Asynchronous Task Workers**: Celery workers executing background reconciliations and notifications.
- **Task Scheduler**: Celery Beat triggering scheduled periodic reconciliations.
- **Routing Engine**: OSRM (Open Source Routing Machine) or mock routing provider.

---

## 2. Docker Compose Production Configuration

In multi-container production environments, services should run in isolated containers sharing an internal bridge network:

```yaml
version: '3.8'

services:
  postgres:
    image: postgis/postgis:16-3.4
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-dukaanly}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Database password required}
      POSTGRES_DB: ${POSTGRES_DB:-dukaanly}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-dukaanly} -d ${POSTGRES_DB:-dukaanly}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes", "--requirepass", "${REDIS_PASSWORD:-}"]
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    restart: unless-stopped

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    environment:
      APP_ENV: production
      DEBUG: "false"
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
      JWT_SECRET_KEY: ${JWT_SECRET_KEY:?JWT Secret required}
      RUN_MIGRATIONS: "true"
      START_CELERY_EMBEDDED: "false"
      DB_POOL_SIZE: 10
      DB_MAX_OVERFLOW: 10
      DB_POOL_PRE_PING: "true"
      DB_POOL_RECYCLE: 1800
      LOG_FORMAT: "json"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    ports:
      - "8000:8000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health/live"]
      interval: 10s
      timeout: 3s
      retries: 3
    stop_grace_period: 20s
    restart: unless-stopped

  celery_worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    command: ["celery", "-A", "app.core.celery_app", "worker", "-l", "info", "-c", "2", "-Q", "celery"]
    environment:
      APP_ENV: production
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
      JWT_SECRET_KEY: ${JWT_SECRET_KEY}
      RUN_MIGRATIONS: "false"
      START_CELERY_EMBEDDED: "false"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    stop_grace_period: 30s
    restart: unless-stopped

  celery_beat:
    build:
      context: ./backend
      dockerfile: Dockerfile
    command: ["celery", "-A", "app.core.celery_app", "beat", "-l", "info"]
    environment:
      APP_ENV: production
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
      RUN_MIGRATIONS: "false"
      START_CELERY_EMBEDDED: "false"
    depends_on:
      redis:
        condition: service_healthy
    restart: unless-stopped

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      - backend
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
```

---

## 3. Environment Variable Matrix

| Variable | Required in Prod | Default | Purpose / Security Guardrails |
| :--- | :---: | :---: | :--- |
| `APP_ENV` | Yes | `production` | Set to `production` to disable debug tracebacks and enforce secret validations. |
| `DEBUG` | Yes | `false` | Must be `false` in production. Disables internal exception exposure. |
| `JWT_SECRET_KEY` | Yes | — | Cryptographic secret for signing JWTs. Must be $\ge 32$ chars, high-entropy. |
| `DATABASE_URL` | Yes | — | `postgresql+asyncpg://user:pass@host:5432/dbname`. |
| `REDIS_URL` | Yes | `redis://localhost:6379/0` | Redis broker and cache connection URI. |
| `RUN_MIGRATIONS` | Optional | `true` | When `true`, runs `alembic upgrade head` before booting server. Set `false` on worker/beat replicas. |
| `START_CELERY_EMBEDDED` | Optional | `false` | When `true`, starts embedded Celery worker for local dev. Set `false` in multi-container setups. |
| `DB_POOL_SIZE` | Optional | `10` | Base number of persistent PostgreSQL connections per process. |
| `DB_MAX_OVERFLOW` | Optional | `10` | Maximum surge connections beyond base pool. |
| `DB_POOL_RECYCLE` | Optional | `1800` | Connection max age in seconds (30m) before automatic renewal. |
| `DB_POOL_PRE_PING` | Optional | `true` | Lightweight validation query before connection checkout. |
| `LOG_FORMAT` | Optional | `json` | Structured JSON log formatter for production log aggregators. |
| `GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS` | Optional | `15.0` | Seconds allocated for connection draining before SIGKILL. |

---

## 4. Startup & Migration Sequencing (`start.sh`)

To avoid race conditions when scaling horizontal API containers, Alembic migrations must be gated:
1. One designated initialization job or primary backend container runs `RUN_MIGRATIONS=true`.
2. All subsequent horizontally scaled API replicas, Celery workers, and Beat schedulers run `RUN_MIGRATIONS=false`.
3. The script verifies that demo seeding is gated strictly behind `APP_ENV=development`:
   ```bash
   if [ "$APP_ENV" = "development" ] && [ "${SEED_DEMO_DATA:-true}" = "true" ]; then
       python app/services/importer/seed_catalog.py
   fi
   ```

---

## 5. Reverse Proxy & WebSocket Configuration (Nginx)

When deploying behind Nginx or an AWS ALB, ensure WebSocket headers are forwarded correctly:

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

upstream fastapi_backend {
    server backend:8000;
    keepalive 32;
}

server {
    listen 80;
    server_name dukaanly.example.com;

    # Static frontend assets
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }

    # API endpoints
    location /api/ {
        proxy_pass http://fastapi_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Request-ID $request_id;
    }

    # WebSocket tracking endpoints
    location /api/v1/deliveries/ws/ {
        proxy_pass http://fastapi_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

---

## 6. Graceful Termination & Draining

FastAPI handles `SIGTERM` and `SIGINT` signals through its lifespan lifecycle:
1. Rejects new incoming requests (if managed by load balancer health checks).
2. Closes all active WebSocket tracking connections with RFC 6455 code `1001` (Going Away).
3. Awaits background PubSub subscriber loops and cancels pending location listeners.
4. Closes OSRM and Redis client pools.
5. Disposes SQLAlchemy connection pool, allowing active queries up to `GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS` (15s) to complete.

---

## 7. Database Backup & Disaster Recovery Procedures

All production database backups use PostgreSQL custom binary archive format (`-Fc`), enabling parallel restoration, schema table selection, and bit-for-bit integrity validation.

### A. Creating an Authoritative Backup
Backups should run via a scheduled cron job or before every schema deployment:
```bash
# Execute within the PostgreSQL container
docker exec dukaanly_postgres pg_dump -U dukaanly_user -d dukaanly -Fc -f /tmp/dukaanly_release_backup.dump

# Copy archive out to persistent storage / S3 bucket
docker cp dukaanly_postgres:/tmp/dukaanly_release_backup.dump ./data/backups/dukaanly_$(date +%Y%m%d_%H%M%S).dump
```

### B. Disaster Recovery & Restoration Verification
Restoring into a fresh database instance:
```bash
# 1. Create target database with PostGIS spatial extension
docker exec -i dukaanly_postgres psql -U dukaanly_user -d postgres -c "CREATE DATABASE dukaanly_restore;"
docker exec -i dukaanly_postgres psql -U dukaanly_user -d dukaanly_restore -c "CREATE EXTENSION IF NOT EXISTS postgis;"

# 2. Restore schema, tables, and spatial data
docker exec -i dukaanly_postgres pg_restore -U dukaanly_user -d dukaanly_restore --no-owner /tmp/dukaanly_release_backup.dump

# 3. Verify spatial indexing and row integrity
docker exec -i dukaanly_postgres psql -U dukaanly_user -d dukaanly_restore -c \
  "SELECT COUNT(*) FROM shops; SELECT id, name, ST_AsText(location) FROM shops LIMIT 3;"
```

---

## 8. Migration Rollback & Recovery Procedures

Dukaanly maintains a strict, linear Alembic migration history (single linear head: `2c3278e09b46`).

### A. Deploying Migrations
```bash
alembic -c alembic.ini upgrade head
```

### B. Single-Step Safe Rollback
Every migration includes an explicit, tested `downgrade()` implementation:
```bash
# Downgrade to preceding revision
alembic -c alembic.ini downgrade -1

# Re-verify migration status
alembic -c alembic.ini current
```

### C. Migration Recovery Guardrails
- In multi-container environments, `RUN_MIGRATIONS=true` is set on exactly one container during deployment (`api`).
- Workers and schedulers have `RUN_MIGRATIONS=false` to prevent concurrent DDL locking.
- Spatial PostGIS extensions are initialized idempotently in `app.db.init_predeploy` before any table creation.
