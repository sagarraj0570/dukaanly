# Dukaanly — Production Deployment Plan & Environment Readiness

## 1. Hosting Architecture Overview (Cloud PaaS: Render)

Dukaanly is deployed as a modular monolith composed of 4 coordinated services managed through [`render.yaml`](../render.yaml) on Render's 100% Free Tier (requiring zero payment information):

```mermaid
flowchart TD
    Client[End User Browser / Mobile]

    subgraph CDN[Edge / Static Hosting (Free)]
        Frontend["dukaanly-frontend (React SPA on CDN)<br/>Default Hostname: https://dukaanly-frontend.onrender.com"]
    end

    subgraph Compute[Containerized Application Tier (Free)]
        API["dukaanly-api (FastAPI + WebSockets + Background Worker)<br/>Default Hostname: https://dukaanly-api.onrender.com<br/>Runs Uvicorn + concurrent Celery worker via start.sh"]
    end

    subgraph DataTier[Private Managed Data Tier (Free)]
        DB[("Managed PostgreSQL 16 + PostGIS 3.4<br/>(dukaanly-postgres)")]
        Redis[("Managed Key-Value / Redis 7<br/>(dukaanly-redis)")]
    end

    Client -->|HTTPS / WSS| Frontend
    Frontend -->|REST API / WebSockets| API
    API -->|Async SQLAlchemy / PostGIS| DB
    API -->|Pub/Sub & Task Dispatch| Redis
```

---

## 2. Service Definitions & Assigned Hostnames

| Service | Type | Plan | Runtime | Build / Start Command | Assigned Hostname / Ingress | Health Check |
|---|---|---|---|---|---|---|
| **`dukaanly-frontend`** | Static Site | Free | Node.js 20 | `npm ci && npm run build` (publish: `dist`) | `https://dukaanly-frontend.onrender.com` | SPA rewrite `/* -> /index.html` |
| **`dukaanly-api`** | Web Service | Free | Docker (`backend/Dockerfile`) | `/app/start.sh` (Runs migrations, Celery, and Uvicorn) | `https://dukaanly-api.onrender.com` | `GET /api/v1/health/live` |
| **`dukaanly-postgres`**| Managed Database | Free | PostgreSQL 16 | PostGIS extension auto-provisioned on startup | Private network only | Managed DB health |
| **`dukaanly-redis`**   | Managed Key-Value | Free | Redis 7 | Managed Redis cluster | Private network only | Managed Redis ping |

> [!NOTE]
> Render's Blueprint specification for `fromService` supports properties `host`, `port`, `hostport`, `slug`, and `connectionString` (it does not support `property: url`). Therefore, canonical URLs for `ALLOWED_ORIGINS` (`https://dukaanly-frontend.onrender.com`) and `VITE_API_URL` (`https://dukaanly-api.onrender.com/api/v1`) are defined as explicit static values matching the assigned service domains.
> Furthermore, `dukaanly-redis` is declared under `services:` as `type: keyvalue` (Render does not support a root-level `redis:` block). Background task processing runs concurrently inside `dukaanly-api` via `/app/start.sh`, eliminating the need for a separate paid worker service.

---

## 3. Environment Variables & Secret Sharing via `envVarGroups`

To guarantee that both the API and worker receive **the identical JWT secret** without exposing credentials in git or build logs, the Render blueprint defines an environment variable group (`dukaanly-shared-config`) with `generateValue: true`:

### Root-Level Shared Environment Group (`dukaanly-shared-config`)
| Variable | Value / Generation | Purpose |
|---|---|---|
| `APP_ENV` | `production` | Enforces production security validations across all services |
| `DEBUG` | `false` | Disables tracebacks, mock data fallbacks, and interactive docs |
| `ALLOW_MOCK_PAYMENTS` | `false` | Strictly disables mock payment processing in production |
| `JWT_ALGORITHM` | `HS256` | Standard HMAC-SHA256 signing algorithm |
| `JWT_SECRET_KEY` | `generateValue: true` | Render generates a cryptographically random 256-bit secret shared identically across API and worker |

### Service-Specific Injected Variables
- **`dukaanly-api`**:
  - `fromGroup: dukaanly-shared-config`
  - `DATABASE_URL`: `fromDatabase: dukaanly-postgres` (connectionString)
  - `REDIS_URL`: `fromService: dukaanly-redis` (connectionString, type: keyvalue)
  - `ALLOWED_ORIGINS`: `https://dukaanly-frontend.onrender.com`
- **`dukaanly-frontend`**:
  - `VITE_API_URL`: `https://dukaanly-api.onrender.com/api/v1`
  - `VITE_WS_URL`: `""` (dynamically derived by `getDeliveryWsUrl`)

---

## 4. Automated PostGIS & Database Migration Startup Phase

Because Render Free Tier does not support standalone ephemeral `preDeployCommand` containers, migrations and PostGIS verification execute reliably at the beginning of the container startup lifecycle via [`/app/start.sh`](../backend/start.sh) before traffic is accepted:

```bash
#!/bin/sh
set -e

# 1. PostGIS verification and database schema migrations
python -m app.db.init_predeploy
alembic -c alembic.ini upgrade head

# 2. Celery background task worker (concurrent background process)
if [ -n "$REDIS_URL" ]; then
    celery -A app.core.celery_app.celery_app worker --loglevel=info --concurrency=1 &
fi

# 3. FastAPI application server
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Startup Execution Sequence:
1. **Connectivity Check**: Establishes async connection to PostgreSQL via `DATABASE_URL`.
2. **PostGIS Availability Audit**: Queries `pg_available_extensions` to confirm that `postgis` binary is present in the PostgreSQL 16 engine. If missing, execution halts with exit code 1 to protect the database.
3. **Automated Extension Provisioning**: Executes `CREATE EXTENSION IF NOT EXISTS postgis;` idempotently.
4. **Operational Readiness Assert**: Executes `SELECT PostGIS_Version();` and logs the verified PostGIS version (e.g. `>= 3.4`).
5. **Schema Migration**: Executes `alembic -c alembic.ini upgrade head` to apply all pending schema revisions.
6. **Worker Launch**: Starts `celery worker` concurrently in the background with concurrency 1, connecting to `dukaanly-redis`.
7. **Traffic Ingress**: Launches `uvicorn` in the foreground. Render's health check (`/api/v1/health/live`) passes, and user traffic begins flowing.

---

## 5. Domain, TLS, CORS & WebSocket Normalization

1. **Automatic TLS 1.3**:
   - Render automatically provisions and renews Let's Encrypt certificates for all `.onrender.com` and custom domains.
   - Plain HTTP requests are 301 redirected to HTTPS with HSTS enabled.
2. **CORS Alignment**:
   - `ALLOWED_ORIGINS` is injected dynamically from `dukaanly-frontend`'s assigned URL (`https://dukaanly-frontend.onrender.com`).
   - Browser cross-origin requests from the React SPA are authorized with full credential support.
3. **URL & WebSocket Normalization**:
   - The frontend Axios client normalizes `VITE_API_URL` to ensure `/api/v1` is present regardless of whether the injected URL contains a trailing path.
   - `getDeliveryWsUrl` automatically converts `https:` $\to$ `wss:` and appends `/api/v1/ws/deliveries/{id}`, guaranteeing zero WebSocket handshake mismatches behind PaaS TLS edge proxies.

---

## 6. Live Deployment Verification Runbook

Following initial production deployment, run the verification sequence:

### Step 1: Health & Dependency Readiness Probes
Inspect HTTP status and complete JSON response bodies:
```bash
# 1. Liveness Probe (process is running)
curl -s -i https://dukaanly-api.onrender.com/api/v1/health/live
# Expected: HTTP/2 200 OK
# Body: {"status":"alive"}

# 2. Readiness Probe (database & redis connectivity)
curl -s -i https://dukaanly-api.onrender.com/api/v1/health/ready
# Expected: HTTP/2 200 OK
# Body: {"status":"ready","database":"connected","redis":"connected"}
```
> [!IMPORTANT]
> The readiness probe executes `SELECT 1` on PostgreSQL and a `PING` on Redis. Both subsystems must report `"connected"`.

### Step 2: PostGIS Verification via API
Verify spatial queries execute on the database:
```bash
curl -s "https://dukaanly-api.onrender.com/api/v1/shops/nearby?lat=12.9716&lng=77.5946&radius_km=10"
# Expected: HTTP/2 200 OK with shop array (spatial ST_DWithin query succeeded)
```

### Step 3: Production Security Guardrails
Verify mock payments fail closed:
```bash
curl -s -i -X POST https://dukaanly-api.onrender.com/api/v1/payments/mock-process \
  -H "Content-Type: application/json" \
  -d '{"order_id": "00000000-0000-0000-0000-000000000000"}'
# Expected: HTTP/2 403 Forbidden or 401 Unauthorized (never 200 OK in production)
```

### Step 4: Real-Time WebSocket Delivery Stream
Connect to `wss://dukaanly-api.onrender.com/api/v1/ws/deliveries/{delivery_id}?token={jwt_token}` and verify receipt of initial `connection.ready` event.

---

## 7. Decoupled Rollback & Disaster Recovery Procedures

Application code rollback and database recovery are strictly separated operations:

### A. Application Code Rollback (Zero Data Impact)
- If a regression is discovered in the API, worker, or frontend code that **does not involve a schema change**:
  1. Open Render Dashboard $\to$ Service (`dukaanly-api`, `dukaanly-worker`, or `dukaanly-frontend`).
  2. Select **Deploys** $\to$ Locate the previous known-good deployment artifact.
  3. Click **Rollback to this deploy**.
  4. Render immediately shifts traffic back to the previous immutable container image.

### B. Database Schema Migration Rollback (Controlled Schema Reversal)
- If a newly applied migration caused application errors:
  ```bash
  # Target the specific down-revision
  alembic -c alembic.ini downgrade -1
  ```
  > [!WARNING]
  > Never roll back container code while an incompatible schema migration is active. Always align the database schema before or synchronously with container rollback.

### C. Disaster Recovery & Point-In-Time Restoration (Disaster Only)
- In the event of catastrophic data corruption or accidental drop:
  1. Managed daily snapshots are maintained by Render PostgreSQL.
  2. Provision a new target database or restore the backup archive via `pg_restore`:
     ```bash
     pg_restore --clean --if-exists -d dukaanly_recovery_db dukaanly_backup.dump
     ```
  3. Validate PostGIS extensions and data integrity before updating `DATABASE_URL`.
