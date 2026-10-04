# Dukaanly - Agent Instructions

## Project Context
Dukaanly is a hyperlocal marketplace built as a solo portfolio project. It connects Customers, Shop Owners, and Delivery Riders.

## STRICT SCOPE CONSTRAINTS (Section 0)
1. **Never implement**: Reviews & Ratings, Admin Dashboards, Analytics, or Push/SMS Notifications.
2. **Mocked Services**: Payment gateway (mock UPI/COD), SMS/OTP.
3. **Core Engineering Requirements (Non-Negotiable)**:
   - **Inventory Concurrency**: Stock updates MUST use optimistic locking (a `version` column) to prevent race conditions and overselling.
   - **Geospatial Logic**: Rider assignment and shop discovery MUST use actual PostGIS queries (`ST_DWithin`, `ST_Distance`) on real `geometry` columns, not math approximations in Python.

## Approved Tech Stack
- **Frontend**: React, Vite, TypeScript, Tailwind CSS, shadcn/ui, React Router, Zustand, TanStack Query, Leaflet.
- **Backend**: Python, FastAPI, SQLAlchemy 2.0, Pydantic, WebSockets.
- **Database**: PostgreSQL with PostGIS, Redis (Cache/PubSub).
- **Testing**: Pytest, Vitest, Playwright.

## Architectural Principles
- **Modular Monolith**: No microservices. (Best approach for solo maintainability).
- **Server-Side Security**: Never trust the client. Verify resource ownership (`user_id == resource.owner_id`) on every state-changing endpoint.
- **DB Migrations**: Always use Alembic for schema changes.

## Coding Standards
- Use type hints everywhere in Python.
- Use environment variables for all secrets.
- Handle errors consistently with standard HTTP status codes.
- Do not use mock data arrays as production DB fallbacks.
- Write tests for core logic, especially the inventory race-condition.

## Making Changes
- Check this file and the `docs/` folder before suggesting structural changes.
- Stay within the defined MVP scope. If a request pushes boundaries, explicitly warn the user.
