# Dukaanly - Development Roadmap

This plan is structured for a **solo** build focused on a robust core MVP. With no strict timeline, we will prioritize building each milestone securely and correctly, utilizing a modular monolith approach which remains the best choice for this scale.

## Milestone 1: Environment Setup & Core Auth
- **Objective**: Scaffold the project, configure DB, and implement secure authentication.
- **Tasks**:
  - Init Git repository.
  - Setup Docker Compose (Postgres+PostGIS, Redis, FastAPI, React/Vite).
  - Implement Alembic migrations.
  - Build User models, JWT Auth, and RBAC (Customer, Shop, Rider).
- **Deliverables**: Working login/register APIs, protected routes.
- **Definition of Done (DoD)**: Unit tests for Auth pass; users can successfully authenticate.

## Milestone 2: Shops & Catalog
- **Objective**: Allow shops to register and manage inventory.
- **Tasks**:
  - Implement Shop model with PostGIS geography.
  - Implement Product (Master) and ShopListing models.
  - Create Shop CRUD APIs.
  - Create Inventory management APIs.
- **Deliverables**: Endpoints to create shops and add stock.
- **DoD**: Shop owner can create a shop and populate a menu/catalog.

## Milestone 3: Discovery, Cart & Inventory Concurrency
- **Objective**: Customers can find shops and safely add items to a cart.
- **Tasks**:
  - Customer API to find nearby shops using PostGIS (`ST_DWithin`).
  - Cart state management (Frontend + Backend).
  - **Critical**: Implement Optimistic Locking (`version` column) for inventory stock deduction.
- **Deliverables**: Nearby shops API, Cart APIs, strict concurrency tests.
- **DoD**: A dedicated unit test proves that concurrent purchase requests to the same listing correctly reject the one that causes negative stock or version mismatch.

## Milestone 4: Checkout & Order State Machine
- **Objective**: Complete the checkout flow and establish order lifecycle.
- **Tasks**:
  - Mock Payment gateway logic.
  - Convert Cart to Order securely.
  - Implement Order and OrderStatusEvents state machine.
  - APIs for Shops to Accept/Prepare/Ready orders.
- **Deliverables**: End-to-end ordering API flow.
- **DoD**: Customer can place an order; Shop can transition it to `READY_FOR_PICKUP`.

## Milestone 5: Rider Assignment & PostGIS
- **Objective**: Match orders to riders geographically.
- **Tasks**:
  - Rider registration and location updates.
  - Implement Nearest-Rider matching algorithm (PostGIS).
  - Rider accept/reject logic.
- **Deliverables**: Automated assignment system.
- **DoD**: When order is ready, the system successfully finds the nearest online rider and assigns the order.

## Milestone 6: WebSockets & Real-Time Tracking
- **Objective**: Live updates for the customer.
- **Tasks**:
  - Setup FastAPI WebSockets connected to Redis Pub/Sub.
  - Broadcast Order status changes.
  - Broadcast Rider location changes.
- **Deliverables**: Live tracking connection.
- **DoD**: A mock script moving a rider's coordinates updates the frontend map in real time.

## Milestone 7: Frontend Integration & UI Refinement
- **Objective**: Connect the React app to all backend APIs.
- **Tasks**:
  - Build Customer App, Shop Dashboard, and Rider Interface.
  - Implement React Query for data fetching.
  - UI/UX polish (Tailwind, shadcn).
- **Deliverables**: Fully functional web interfaces.
- **DoD**: All three user roles have working UIs mapped to real endpoints.

## Milestone 8: Testing, Polish & Deployment
- **Objective**: Final QA and deployment readiness.
- **Tasks**:
  - Write Playwright E2E tests for the critical path (Auth -> Order -> Deliver).
  - Final bug fixes.
  - Document deployment steps.
- **Deliverables**: Portfolio-ready repository.
- **DoD**: CI pipeline passes, system works end-to-end locally, README is complete.

## Recommended First Implementation Milestone
**Milestone 1**: Environment Setup & Core Auth. We must establish the Docker containers (especially Postgres with PostGIS) and the JWT authentication foundation before any domain logic can be built.

