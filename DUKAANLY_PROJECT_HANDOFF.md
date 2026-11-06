# Dukaanly — Comprehensive Project Technical Handoff & Claude Scaling Guide

**Document Version**: 2.0.0 (Updated Post-Stage 7 Hyperlocal Expansion & Verification)  
**Alembic Head**: `d5a8e2b74c10 (head)`  
**Test Suite State**: 100% Passed (398 Backend Tests, 106 Frontend Tests, 0 Failures, 0 Errors)  
**Repository Location**: `c:\Users\ASUS\Documents\VIT\Dukaanly`  
**Target Systems / LLMs**: Claude (Anthropic), Distributed Systems Engineers, Dev Leads  

---

## 1. Project Overview & Business Logic

**Dukaanly** is a hyperlocal commerce platform engineered specifically around the commercial geography of **Patna, Bihar**. It connects three actors in real time:
- **Customers**: Discover verified neighbourhood shops within 10 km, search 30+ localities by place name, add products to a single-shop cart, chat with an AI assistant that understands Hinglish & Devanagari, and track live deliveries over WebSockets on a real road map with dynamic Smart ETAs.
- **Shop Owners (Dukaandars)**: Manage shop profile, maintain product catalogs (>= 50 active items/shop), manage inventory with Optimistic Concurrency Control (`version` column), accept/reject incoming orders, and dispatch riders.
- **Delivery Riders**: Toggle availability, stream GPS coordinates via WebSockets, accept delivery tasks (maximum 1 active delivery per rider enforced by DB partial unique index), and follow turn-by-turn routes via OSRM.

---

## 2. Strict Non-Negotiable Invariants (`AGENTS.md`)

Claude **MUST** always preserve these core rules:
1. **Never implement**: Reviews & ratings, public admin dashboards, analytics, or push/SMS notification gateways.
2. **Payments remain mocked**: Mock Razorpay provider with cryptographic HMAC-SHA256 signature verification. No real money integration.
3. **Inventory OCC**: Inventory updates **MUST** use optimistic concurrency control via an integer `version` column on products (`UPDATE products SET stock = stock - :qty, version = version + 1 WHERE id = :id AND version = :version`).
4. **Real PostGIS Queries**: Shop discovery and rider assignment **MUST** use PostGIS `ST_DWithin` and `ST_Distance` on `geography(Point, 4326)` columns. No Euclidean/math approximations in Python.
5. **Rider Uniqueness**: Maximum 1 active delivery per rider enforced by the partial unique index:
   ```sql
   CREATE UNIQUE INDEX uq_active_rider_delivery ON deliveries(rider_id) 
   WHERE status IN ('assigned', 'picked_up');
   ```
6. **Alembic**: All schema changes must follow linear Alembic migrations. Current head is `d5a8e2b74c10`.

---

## 3. Technology Stack & Local Services

- **Backend**: Python 3.13, FastAPI, SQLAlchemy 2.0 (Asyncpg), Pydantic v2, Uvicorn (`http://127.0.0.1:8000/api/v1`).
- **Database**: PostgreSQL 16 + PostGIS 3.4 in Docker (`127.0.0.1:5433`).
- **Cache & Real-Time**: Redis 7 Alpine in Docker (`127.0.0.1:6379`).
- **Background Tasks**: Celery 5.3 + Celery Beat (Periodic reconciliation every 60s for stale orders/deliveries).
- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS v4, Zustand, TanStack Query, Leaflet (`http://127.0.0.1:5173`).
- **Routing**: Open Source Routing Machine (OSRM) driving API with polyline geometries & smart ETAs.
- **AI Subsystem**: Groq API (`openai/gpt-oss-120b`) with server-side catalog grounding & fallback mock provider.

---

## 4. Current Database Schema & Models

- `users`: ID, email, hashed_password, role (`customer`, `shop_owner`, `rider`), is_active.
- `refresh_tokens`: ID, user_id, token_hash, family_id, is_revoked, expires_at (7 days).
- `shops`: ID, owner_id, name, category, address, location (`geography(Point, 4326)`), is_active, is_orderable, source (`demo`, `geoapify`, `osm`), verification_status (`verified`, `unverified`).
- `products`: ID, shop_id, name, category, price, stock, version (Integer OCC counter), image_url, is_active.
- `orders`: ID, customer_id, shop_id, status (`pending`, `confirmed`, `preparing`, `ready_for_pickup`, `out_for_delivery`, `delivered`, `cancelled`), total_amount, version, created_at.
- `order_items`: ID, order_id, product_id, quantity, unit_price, subtotal.
- `order_events`: ID, order_id, from_status, to_status, actor_type, actor_id, reason, metadata, created_at (State machine audit log).
- `deliveries`: ID, order_id, rider_id, status (`pending`, `assigned`, `picked_up`, `delivered`, `cancelled`), pickup_location, dropoff_location, distance_meters, estimated_duration_seconds, version.
- `payments`: ID, order_id, amount, status (`pending`, `captured`, `failed`, `refunded`), provider (`mock`), transaction_id, signature.

---

## 5. Seeded Demo Catalog Data

- **Patna Super Kirana (Verified Partner)**: 69 active products (82 total) — Groceries, Dairy, Staples, Household.
- **Patna City Medicos (Verified Partner)**: 50 active products — Medicines, First Aid, Personal Care, Baby Care.
- **Pataliputra Bakery & Confectionery (Verified Partner)**: 50 active products — Fresh Breads, Cakes, Pastries, Snacks.
- **External Directory Listings**: 91 real-world physical stores discovered via Geoapify/OSM with `is_orderable = false` and 0 products attached (walk-in informational listings only).

---

## 6. Key Scaling Vectors for Future Stages

1. **Redis Distributed Stock Reservation (Flash Sales)**:
   - *Problem*: High-concurrency checkout bursts cause Postgres OCC serialization retries.
   - *Solution*: Pre-reserve stock in Redis via Lua scripts with a 10-minute hold lease, batch-updating Postgres asynchronously.
2. **PostGIS Spatial Partitioning & Uber H3**:
   - *Problem*: As shops scale across multiple cities/states, table-wide `ST_DWithin` scans degrade.
   - *Solution*: Index shops using Uber H3 spatial hex indexes (resolution 7–8) or PostGIS spatial table partitioning by city/zone.
3. **Horizontal WebSocket Scaling**:
   - *Problem*: WebSocket client registry is currently process-local in memory.
   - *Solution*: Route all client frame broadcasts through Redis Streams / PubSub consumer groups across multiple Uvicorn instances behind NGINX.
4. **Batched Bipartite Dispatch (VRP Solver)**:
   - *Problem*: Single-pass nearest rider assignment causes dispatch sub-optimality during peak hours.
   - *Solution*: Implement a 15–30 second scheduling tick that computes a bipartite matching matrix (rider road ETA to shop vs order urgency) using Google OR-Tools or Hungarian algorithm.
5. **Database Connection Pooling (PgBouncer)**:
   - *Problem*: Asyncpg direct connections will saturate Postgres `max_connections` under high customer concurrency.
   - *Solution*: Introduce PgBouncer in transaction pooling mode + Read/Write replica routing.

---

## 7. Master Hand-Off Prompt for Claude

When starting a session with Claude to scale this project, copy and paste this exact prompt:

```markdown
Hi Claude,

I am handing over the codebase for Dukaanly, a production-hardened hyperlocal marketplace platform built with FastAPI (Python 3.13), PostgreSQL 16 + PostGIS 3.4, Redis 7, Celery, and React 19 + TypeScript.

Before making any changes, please read DUKAANLY_PROJECT_HANDOFF.md and AGENTS.md.
Ensure you strictly observe our core invariants:
1. Never implement reviews/ratings, admin dashboards, analytics, or push/SMS gateways.
2. Keep payments strictly mocked (HMAC-SHA256 signature verification).
3. Preserve inventory Optimistic Concurrency Control (OCC) using the integer `version` column.
4. All geospatial queries must use PostGIS `ST_DWithin` and `ST_Distance` on `geography(Point, 4326)` columns.
5. Max 1 active delivery per rider via the partial unique index `uq_active_rider_delivery`.
6. Alembic migrations must stay linear (current head: `d5a8e2b74c10`).

Current Status:
- Backend: 398 passed, 0 failed.
- Frontend: 106 passed across 26 test files, 0 failed.
- Catalog: 3 verified demo partner shops with >= 50 products each + 91 directory shops.
- Place Search: Live search across 30+ Patna neighbourhoods.

Today's Scaling Task:
[Insert specific scaling objective from Section 6 above]

Please inspect the existing codebase, confirm understanding, and propose an implementation plan that preserves all existing invariants.
```
