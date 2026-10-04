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
- Docker & Docker Compose
- Node.js 20+
- Python 3.12+

### 1. Clone the repo & configure environment
```bash
git clone <repo-url>
cd Dukaanly
cp .env.example .env
# Fill in required values in .env
```

### 2. Start infrastructure
```bash
docker compose up -d
```

### 3. Run backend
```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

### 4. Run frontend
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
