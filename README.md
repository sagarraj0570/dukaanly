# Dukaanly — Hyperlocal Marketplace

A portfolio-grade hyperlocal marketplace connecting Customers, Shop Owners, and Delivery Riders in real time.

## Tech Stack
| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, TypeScript, Tailwind CSS, shadcn/ui, Leaflet, Zustand, TanStack Query |
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2.0, Alembic, WebSockets |
| Database | PostgreSQL 16 + PostGIS 3.4 |
| Cache / PubSub / Queue | Redis 7, Celery |
| Infra | Docker, Docker Compose |
| Testing | Pytest, Vitest |

---

## Getting Started (Local Development)

### Prerequisites
- Docker Desktop (with Linux container support)
- Node.js 20+
- Python 3.12+

### 1. Configure Environment Variables
```bash
cp .env.example .env
```
Key environment variables to configure:
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `POSTGRES_PORT` (defaults to host port `5433` for local dev to avoid conflicting with standard local PostgreSQL)
- `REDIS_URL`
- `JWT_SECRET_KEY` (must be at least 32 characters in production)
- `APP_ENV` (`development` | `production`)
- `ALLOWED_ORIGINS` (comma-separated origins, e.g. `http://localhost:5173`)
- `PAYMENT_PROVIDER` (`razorpay`) and `ALLOW_MOCK_PAYMENTS` (`true` for sandbox/mock)

*Note: Never commit secret values or private `.env` files to source control.*

### 2. Start Infrastructure via Docker Compose
```bash
docker compose up -d postgres redis
```
This starts:
- **PostgreSQL 16 + PostGIS 3.4** on `localhost:5433` (container port 5432).
  - Automatically enables PostGIS extensions on initial volume mount via `backend/db/init/01_enable_postgis.sql`.
- **Redis 7** on `localhost:6379`.

Volumes `postgres_data` and `redis_data` provide persistence across container restarts.

### 3. Verify Infrastructure Health
```bash
docker compose ps
docker exec dukaanly_postgres pg_isready -U dukaanly_user -d dukaanly
docker exec dukaanly_redis redis-cli ping
docker exec dukaanly_postgres psql -U dukaanly_user -d dukaanly -c "SELECT PostGIS_Version();"
```

### 4. Apply Database Migrations (Alembic)
Dukaanly uses Alembic for database migrations.
```bash
cd backend
# With virtual environment activated:
alembic upgrade head
```

To verify migration state:
```bash
alembic current
alembic history
```

### 5. Run Backend & Background Worker
```bash
cd backend
python -m venv venv

# Windows:
.\venv\Scripts\activate
# Linux/macOS:
# source venv/bin/activate

pip install -r requirements.txt

# Start FastAPI API server:
uvicorn app.main:app --reload --port 8000

# In a separate terminal, start the Celery notification worker:
celery -A app.core.celery_app worker --loglevel=info
```

Endpoints available:
- **API Documentation**: [http://localhost:8000/api/v1/docs](http://localhost:8000/api/v1/docs) (available when `DEBUG=true`)
- **Liveness Probe**: [http://localhost:8000/api/v1/health/live](http://localhost:8000/api/v1/health/live)
- **Readiness Probe**: [http://localhost:8000/api/v1/health/ready](http://localhost:8000/api/v1/health/ready)

### 6. Run Frontend
```bash
cd frontend
npm install
npm run dev
```
Frontend runs at [http://localhost:5173](http://localhost:5173).

---

## Full Docker Compose Stack
To run the entire stack (PostgreSQL, Redis, FastAPI API, and Celery Worker) via Docker:
```bash
docker compose up -d --build
```
This builds and launches:
- `dukaanly_postgres` (healthy check via `pg_isready`)
- `dukaanly_redis` (healthy check via `redis-cli ping`)
- `dukaanly_api` (healthy check via `/api/v1/health/live`)
- `dukaanly_worker` (depends on healthy postgres & redis)

---

## Verification & Testing Commands

### Backend Test Suite
```bash
cd backend
pytest -v
```
Runs the complete test suite including authentication, catalog, cart, optimistic inventory concurrency, idempotent checkout, payment simulations, PostGIS geospatial assignments, and live WebSockets.

### Frontend Test Suite & Production Build
```bash
cd frontend
npm run lint
npm run test
npm run build
```

---

## Architectural & Security Policies

1. **Inventory Concurrency & Optimistic Locking**:
   - Stock updates require a matching `version` column.
   - Prevents race conditions and overselling during concurrent customer checkout.
2. **Authoritative PostGIS Geospatial Logic**:
   - Spatial queries use native PostGIS functions (`ST_DWithin`, `ST_Distance`) on `geometry(Point, 4326)` columns.
3. **Mock/Sandbox Payment Constraints**:
   - Real payment transactions and live gateway credentials are out of scope.
   - In `development`, the sandbox provider simulates success and failure flows using `mock_signature_valid`.
   - In `production`, mock payments are strictly forbidden (`ALLOW_MOCK_PAYMENTS=true` raises a startup error), and live payment processing is intentionally unavailable until a separately authorized scope change.
4. **WebSocket & Real-Time Tracking**:
   - WebSocket connections authenticate via JWT and authorize against delivery ownership (customer, assigned rider, shop owner).
   - Authoritative state is maintained in PostgreSQL; Redis Pub/Sub distributes events to connected clients.
   - Throttling is enforced on rider coordinate ingestion (`RIDER_LOCATION_MIN_UPDATE_INTERVAL_SECONDS`).
   - Production deployments running behind reverse proxies should set `VITE_WS_URL` or use `wss://` origins.
5. **Role-Based Access Control (RBAC) & Ownership**:
   - Customer registration cannot grant elevated roles (`admin`, `shop_owner`, `rider`).
   - Resource endpoints strictly verify `customer_id == user.id` or `shop.owner_id == user.id`.

---

## Deployment Prerequisites & Limitations
- **External Reverse Proxy**: In a production deployment, terminate TLS (HTTPS/WSS) at the ingress proxy (e.g., Nginx, Caddy, or cloud load balancer) and forward headers (`X-Forwarded-Proto`, `Upgrade`).
- **PostGIS Extension Support**: Managed databases must support the PostGIS extension.
- **Mock Scope**: Payment and SMS/OTP remain mocked/sandbox by design. Admin dashboards, customer reviews/ratings, and push notification gateways are out of scope.
