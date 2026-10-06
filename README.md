# Dukaanly — Hyperlocal Marketplace

A portfolio-grade hyperlocal marketplace connecting Customers, Shop Owners, and Delivery Riders in real time.

## Tech Stack
| Layer | Technology |
|---|---|
| Frontend | React + Vite + TypeScript, Tailwind CSS, shadcn/ui, Leaflet |
| Backend | Python, FastAPI, SQLAlchemy 2.0, Alembic |
| Database | PostgreSQL + PostGIS |
| Cache / PubSub | Redis |
| Infra | Docker, Docker Compose |
| Testing | Pytest, Vitest, Playwright |

## Getting Started (Local Development)

### Prerequisites
- Docker Desktop (with Linux containers mode)
- Node.js 20+
- Python 3.12+

### 1. Clone the repo & configure environment
```bash
git clone <repo-url>
cd Dukaanly
cp .env.example .env
# Edit .env — set POSTGRES_PASSWORD and JWT_SECRET_KEY at minimum
```

### 2. Start infrastructure
```bash
docker compose up -d
```

This starts:
- **PostgreSQL 16 + PostGIS 3.4** on `localhost:5433` (host port 5433 → container port 5432)
- **Redis 7** on `localhost:6379`

Both services have health checks. Volumes `dukaanly_postgres_data` and `dukaanly_redis_data` persist data across restarts.

### 3. Verify infrastructure is healthy
```bash
docker compose ps                          # both should show (healthy)
docker exec dukaanly_postgres pg_isready -U dukaanly_user -d dukaanly
docker exec dukaanly_redis redis-cli ping  # should respond PONG
docker exec dukaanly_postgres psql -U dukaanly_user -d dukaanly -c "SELECT PostGIS_Version();"
```

### 4. Stop / tear down
```bash
docker compose down        # stop, keep volumes (data preserved)
docker compose down -v     # stop + wipe volumes (clean slate)
```

### 5. Run backend
```bash
cd backend
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Mac/Linux:
# source venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload
```
Once running, the backend provides:
- **API Documentation**: [http://localhost:8000/api/v1/docs](http://localhost:8000/api/v1/docs)
- **Liveness Check**: [http://localhost:8000/api/v1/health/live](http://localhost:8000/api/v1/health/live)
- **Readiness Check**: [http://localhost:8000/api/v1/health/ready](http://localhost:8000/api/v1/health/ready)

### 6. Run backend tests
Make sure the infrastructure is running first (for the readiness check tests).
```bash
cd backend
# With virtual environment activated:
pytest -v
```

## Database Migrations (Alembic)
Dukaanly uses Alembic for database migrations. SQLAlchemy declarative models should not use `create_all()`.

### Creating a new migration
When you change or add models in `backend/app/models/` and have imported them in `backend/alembic/env.py` or `backend/app/db/base.py`:
```bash
alembic revision --autogenerate -m "description_of_change"
```

### Applying migrations
To apply all pending migrations up to the latest:
```bash
alembic upgrade head
```

### Inspecting migration state
```bash
alembic current
alembic history
```

### Rolling back migrations
To rollback the last migration:
```bash
alembic downgrade -1
```

### 7. Run frontend
```bash
cd frontend
npm install
npm run dev
```

## Project Structure
```
Dukaanly/
├── frontend/       # React SPA
├── backend/        # FastAPI application
├── docs/           # Architecture, DB design, API spec, roadmap
├── tests/          # Playwright E2E tests
├── docker-compose.yml
├── .env.example
└── AGENTS.md
```

## Key Engineering Decisions
- **Optimistic Locking** on inventory (`version` column) prevents overselling under concurrency.
- **PostGIS** (`ST_DWithin` / `ST_Distance`) for all geospatial queries — no approximation math in Python.
- **Modular Monolith** — no microservices, maximising solo maintainability without sacrificing structure.
- Payment gateway is **intentionally mocked** (UPI/COD simulation). No real integration.

## Documentation
- [`docs/PRODUCT_REQUIREMENTS.md`](docs/PRODUCT_REQUIREMENTS.md)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/DATABASE_DESIGN.md`](docs/DATABASE_DESIGN.md)
- [`docs/API_SPECIFICATION.md`](docs/API_SPECIFICATION.md)
- [`docs/DEVELOPMENT_ROADMAP.md`](docs/DEVELOPMENT_ROADMAP.md)
