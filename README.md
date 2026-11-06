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
2. **Authoritative PostGIS Geospatial Logic & Distance Calculation**:
   - Spatial queries use native PostGIS functions (`ST_DWithin`, `ST_Distance`) on `geography(Point, 4326)` columns for ellipsoidal distance calculation.
   - **Client vs. Server Distance**: The frontend UI (`ShopCard`, `CustomerDashboard`) prefers the authoritative distance and delivery eligibility returned by the backend PostGIS query (`distance_meters`, `is_delivery_eligible`) for the active user location. Client-side Haversine calculation is used only as an immediate fallback when switching locations or when API distance is loading. Note that client-side spherical Haversine approximations and PostGIS WGS84 ellipsoidal computations can differ slightly (measured at 1.6 m to 2.1 m, or ~0.2%, across the three partner shops). Checkout strictly validates delivery eligibility against the server's PostGIS `ST_Distance <= 5000m` check using the destination coordinates sent from the active location store.
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

## Live Nearby Store Discovery (Geoapify Places API)

Dukaanly integrates with the **Geoapify Places API v2** to allow customers to discover real-world nearby retail stores in their immediate neighbourhood.

### 1. API Endpoint & Query Parameters
`GET /api/v1/discovery/nearby`

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `lat` | Float | **Yes** | — | Customer latitude (`-90.0` to `90.0`) |
| `lon` | Float | **Yes** | — | Customer longitude (`-180.0` to `180.0`) |
| `radius` | Integer | No | `3000` | Search radius in meters (`100` to `10,000`) |
| `category` | String | No | `None` | Retail category filter (e.g. `grocery`, `supermarket`, `chemist`, `bakery`) |
| `limit` | Integer | No | `20` | Max results to return (`1` to `25`) |

### 2. Environment Variables
Configure in `backend/.env` (or root `.env`):
- `GEOAPIFY_API_KEY`: Upstream API key obtained from [Geoapify](https://myprojects.geoapify.com/).
- `GEOAPIFY_BASE_URL`: Upstream endpoint (default: `https://api.geoapify.com/v2/places`).
- `GEOAPIFY_CACHE_TTL_SECONDS`: Cache expiry duration (default: `300` / 5 minutes).
- `GEOAPIFY_REQUEST_TIMEOUT_SECONDS`: Upstream network timeout (default: `8.0` seconds).

*Security Guarantee*: `GEOAPIFY_API_KEY` is loaded strictly on the backend, never exposed to client applications, never logged in diagnostic logs, and stripped from all error payloads.

### 3. Caching Behavior & Credit Protection
- **Spatial Grid Bucketing**: Coordinates are bucketed into an ~110m spatial resolution grid (`round(coord, 3)`), enabling users in the same neighbourhood block to share cache hits.
- **Two-Tier Cache Strategy**: Redis primary cache with bounded in-memory LRU (`InMemoryDiscoveryCache`) fallback.
- **Response Invalidation**: Separate cache partitions are created for each unique `(lat_grid, lon_grid, radius, category, limit)` tuple, preventing cross-category or cross-radius cache leaks.
- Responses include a `cached: true/false` status and mandatory attribution string.

### 4. Category Mapping
Dukaanly normalizes retail categories to Geoapify Places hierarchy tags:
- `grocery`, `general` $\rightarrow$ `commercial.supermarket,commercial.convenience,commercial.food_and_drink`
- `supermarket` $\rightarrow$ `commercial.supermarket`
- `convenience` $\rightarrow$ `commercial.convenience`
- `chemist`, `pharmacy` $\rightarrow$ `healthcare.pharmacy,commercial.chemist`
- `bakery` $\rightarrow$ `commercial.food_and_drink.bakery`
- `dairy`, `produce`, `fruits` $\rightarrow$ `commercial.food_and_drink`

### 5. Directory-Only Restrictions & Guardrails
- **Zero Database Writes**: Results are transient DTOs (`NearbyDiscoveryResponse`). Results are never written to the PostgreSQL `shops` table.
- **Strict In-Store Only Designation**: Labeled with `📍 Directory Listing · In-store Only`.
- **Checkout Guardrails**: External listings cannot be claimed, ordered, added to cart (`/api/v1/cart/items`), or checked out (`/api/v1/orders/checkout`), returning `HTTP 400` or `HTTP 404`.
- **Frontend Capabilities**:
  - Interactive **Map / List View** toggle.
  - **Distance Sorting** (Closest First, Furthest First, Name A–Z).
  - Direct **Open in Maps** button providing instant Google Maps directions to the physical store coordinates.
  - Mandatory legal attribution: `Powered by Geoapify | © OpenStreetMap contributors`.

---

## Realistic Demo Data & Seed Catalog

Dukaanly provides an idempotent, deterministic demo seeding engine designed for local development, demonstrations, and test suites. It populates authentic multi-category catalogs across 3 dedicated verified partner stores in Patna, while preserving strict separation from discovered directory listings.

### 1. Seeding Commands

#### A. Seed Demo Data (Idempotent)
Populates or updates demo users, dedicated partner shops, realistic product catalogs across 8 core categories, and candidate directory POIs:
```bash
cd backend
# Windows PowerShell:
$env:PYTHONPATH = "backend"; .\venv\Scripts\python.exe -m app.db.seed_demo

# Linux/macOS:
PYTHONPATH=backend ./venv/bin/python -m app.db.seed_demo
```
*Note: Rerunning this command is strictly idempotent — it updates existing records in place and produces zero duplicate users, shops, products, or inventory rows.*

#### B. Safe Stock Reset (`--reset-stock`)
Resets inventory quantities for all demo products back to their initial catalog levels and increments the optimistic locking `version` column without deleting users, historical orders, or delivery records:
```bash
cd backend
# Windows PowerShell:
$env:PYTHONPATH = "backend"; .\venv\Scripts\python.exe -m app.db.seed_demo --reset-stock

# Linux/macOS:
PYTHONPATH=backend ./venv/bin/python -m app.db.seed_demo --reset-stock
```

### 2. Environment Gating & Production Safety
- **Strict Guardrail**: Seeding is guarded by `verify_seed_environment()`, which verifies `APP_ENV == 'development'`.
- Attempting to run the seeding engine in staging, testing, or production environments raises a fatal `RuntimeError` immediately.
- Default passwords (`Password123!`) and demo data are never written to production databases.

### 3. Dedicated Demo Partner Shops (Boring Road, Patna)
All demo shops are located within the active 5 km delivery serviceability zone:

| Store Name | Owner Account | Category Specialization | Initial Products |
|---|---|---|---|
| **Patna Super Kirana (Verified Partner)** | `shop@dukaanly.com` | Groceries, Dairy, Snacks, Beverages, Personal Care, Household Essentials | 43 items (incl. 0-stock and low-stock edge items) |
| **Patna City Medicos (Verified Partner)** | `pharmacy@dukaanly.com` | OTC Medicines, First Aid, Oral Rehydration, Personal Care, Diagnostics | 20 items |
| **Pataliputra Bakery & Confectionery (Verified Partner)** | `bakery@dukaanly.com` | Artisanal Breads, Tea Rusks, Celebration Cakes, Savouries, Coffee | 19 items |

**Demo Rider**: `rider@dukaanly.com` (Amit Kumar, active GPS coordinate in Boring Road).  
**Demo Customer**: `customer@dukaanly.com` (Rahul Sharma).

### 4. Comprehensive Category Coverage
The seeded inventory covers all 8 core marketplace categories:
1. **Groceries**: Aashirvaad Chakki Atta, Daawat Basmati Rice, Tata Toor Dal, Tata Salt, Madhur Sugar, Fortune Sunflower Oil, Engine Mustard Oil, Everest Haldi, MDH Deggi Mirch, Catch Garam Masala.
2. **Dairy**: Sudha Special Toned Milk, Sudha Full Cream Milk, Sudha Dahi, Sudha Paneer, Sudha Desi Ghee, Amul Butter, Amul Cheese Slices.
3. **Snacks**: Maggi Noodles, Haldiram's Bhujia, Lay's Magic Masala, Parle-G Gold, Britannia Good Day, Kurkure, Cadbury Dairy Milk Silk.
4. **Beverages**: Tata Tea Gold, Nescafe Classic, Rooh Afza Sharbat, Frooti, Real Mixed Fruit Juice, Bru Coffee.
5. **Personal Care**: Dettol Bathing Soap, Dove Body Wash, Colgate Total Toothpaste, Lifebuoy Handwash, Head & Shoulders, Sebamed Baby Soap, Nivea Cream.
6. **Household Essentials**: Surf Excel Powder, Vim Dishwash Gel, Harpic Toilet Cleaner, Lizol Surface Cleaner, Good Knight Mosquito Vaporizer, Godrej Aer Pocket, Omron Thermometer, Surgical Face Masks.
7. **Bakery**: Modern White Bread, Britannia Whole Wheat Brown Bread, Bakeway Pav Buns, Milk Rusk Toast, Dark Chocolate Truffle Cake, Butterscotch Pound Cake, Garlic Bread, Croissants, Khari Puffs, Muffins, Cupcakes.
8. **Medicines**: Dolo 650, Electral ORS, Digene Gel, Vicks VapoRub, Volini Spray, Moov Gel, Band-Aid Strips, Betadine Ointment, Honitus Cough Syrup, Limcee Vitamin C, Strepsils, Pudin Hara, Glucose-D, Otrivin Nasal Spray.

### 5. Schema Alignment & Demo Provenance
- Zero new schema migrations: leverages existing `Shop`, `Product`, `Inventory`, and `User` models.
- **Identification as Demo Data**:
  - `Shop.source = "demo"`
  - `Shop.source_id = "demo:shop:..."`
  - `Shop.source_attribution = "Dukaanly Demo Catalog"`
  - `Product.description` tagged with `"[Dukaanly Demo Product]"`
  - Product unit/pack size (e.g., `5kg`, `1L`, `500ml`, `Pack of 6`, `2 pcs`) embedded directly in `Product.name`, extracted by the frontend via `extractProductUnit()`.
  - Image URLs reference curated, high-resolution photography with fallback to `commerceMedia.ts`.

### 6. Separation of Real-World Directory vs Orderable Demo Stores
- Discovered public directory listings (`source in ("gmap", "geoapify", "osm")`):
  - `verification_status = 'discovered'`
  - `is_orderable = False`
  - `owner_id = None`
  - Zero products seeded.
  - Cart addition and checkout return `HTTP 400 Bad Request` ("This business is listed for directory discovery only and is not currently accepting online orders.").
- Only verified partner demo stores are activated for transactional online ordering with optimistic inventory decrement and delivery assignment.


Dukaanly incorporates a real-time, phase-aware Smart Delivery ETA engine combined with the Open Source Routing Machine (OSRM) driving API.

### 1. API Endpoints
- `GET /api/v1/deliveries/{id}/eta`: Current phase-aware arrival estimate, remaining duration, component breakdown, and source attribution.
- `PATCH /api/v1/deliveries/{id}/preparation`: Update shop kitchen prep time and contextual delay explanation.
- `GET /api/v1/deliveries/{id}/route`: Road route polylines and turn-by-turn discrete legs (Rider $\to$ Shop and Shop $\to$ Customer).

### 2. Arrival Time Formulation
- **Elapsed Prep Deduction**: $T_{\text{prep remaining}} = \max(0, T_{\text{prep expected}} - (T_{\text{now}} - T_{\text{prep start}}))$.
- **Phase Component Matrix**:
  - `pending`: Remaining Prep + Assignment Wait ($3\,\text{m}$) + Dropoff Travel + Handoff ($3\,\text{m}$)
  - `assigned`: Remaining Prep + Pickup Road Travel + Pickup Buffer ($3\,\text{m}$) + Dropoff Road Travel + Handoff ($3\,\text{m}$)
  - `picked_up` / `out_for_delivery`: Dropoff Road Travel + Handoff ($3\,\text{m}$)
  - `delivered`: $0\,\text{s}$ (Terminal state)
- **Arrival Window**: $[T_{\text{remaining}} - B_{\text{uncertainty}}, T_{\text{remaining}} + B_{\text{uncertainty}}]$.

### 3. Resilience & Security
- **PostgreSQL Authoritative**: Snapshot persisted before emitting WebSocket updates (`delivery.eta_updated`).
- **OSRM Fallback**: Conservative $1.3 \times$ Haversine factor at $22\,\text{km/h}$ city driving speed when OSRM is unreachable; explicit `source: 'fallback_estimate'`.
- **Strict Server-Side Ownership**: Authorized strictly for order customer, fulfilling merchant, assigned rider, or admin. Private rider coordinates are never leaked in ETA payloads.
