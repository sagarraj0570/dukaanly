# Dukaanly - Product Requirements Document (PRD)

## 1. Product Vision and Objectives
Dukaanly is a hyperlocal e-commerce marketplace designed to seamlessly connect local customers with nearby shops and delivery riders. The primary objective is to provide a reliable, real-time platform where customers can order from their neighborhood stores and track deliveries, while shop owners manage their catalog/inventory, and riders receive nearest-match assignments.

## 2. User Roles and Permissions
1. **Customer**: Can browse shops, view products, add to cart, place orders, and track deliveries.
2. **Shop Owner**: Can register a shop, manage a catalog (master + custom listings), manage inventory, and process incoming orders.
3. **Delivery Rider**: Can register, toggle availability, receive delivery assignments, and update delivery status.
4. **Admin (Future Scope)**: Platform oversight, dispute resolution, analytics. *Not included in MVP.*

## 3. Core User Journeys
- **Customer Journey**: Register/Login -> View nearby shops -> Browse inventory -> Add to Cart -> Checkout (Mock Payment) -> Track Order Real-time.
- **Shop Owner Journey**: Register Shop -> Add Products & Stock -> Receive Order -> Accept & Prepare -> Handover to Rider.
- **Rider Journey**: Register -> Go Online -> Receive Assignment Request -> Accept -> Pickup Order -> Deliver -> Complete.

## 4. Functional Requirements (MVP Scope)
- **Authentication & RBAC**: JWT-based auth with refresh tokens. Argon2id hashing. Role-based access control for Customer, Shop Owner, and Rider.
- **Shop Discovery & Geolocation**: Customers can find shops based on their current location using PostGIS spatial queries.
- **Product Catalog**: Support for a master catalog of common items and shop-specific custom listings.
- **Inventory & Stock Management**: Real-time stock management. **Must** handle concurrent purchase race conditions safely (via optimistic locking with a version column).
- **Cart & Checkout**: Cart management and checkout flow. Payment gateway integration will be mocked (simulating UPI/COD).
- **Order Management**: Explicit state machine for orders (e.g., Pending, Accepted, Preparing, Ready, Assigned, Picked Up, Delivered).
- **Rider Registration & Assignment**: Riders register and are matched to orders based on real PostGIS geospatial queries (`ST_DWithin` / `ST_Distance`).
- **Real-Time Order Tracking**: WebSockets to push order status updates and rider live locations to customers.

## 5. Non-Functional Requirements
- **Security**: Server-side authorization verifying resource ownership (not just role). Inputs must be validated and sanitized.
- **Reliability**: No duplicate orders or overselling (negative stock) under high concurrency.
- **Performance**: Efficient geospatial queries using PostGIS GiST indexes. Pagination on all list endpoints.

## 6. Future Enhancements (OUT OF MVP SCOPE)
*These features are explicitly excluded from the current MVP build:*
- **Reviews & Ratings**: Customer feedback for shops and riders.
- **Admin Dashboard**: Comprehensive platform management UI.
- **Analytics & Reporting**: Sales trends, rider performance metrics.
- **Notifications**: Push notifications, SMS, or Email integrations (SMS/OTP for MVP will be skipped/mocked).
- **Background Verification**: Rider KYC and document verification.

## 7. Assumptions, Dependencies, and Risks
- **Assumptions**: Users have devices capable of reporting accurate geolocation.
- **Dependencies**: OpenStreetMap/Leaflet for frontend maps. PostgreSQL with PostGIS extension for backend.
- **Risks**: Race conditions in inventory updates (mitigated by strict DB locking strategies). Geographic sparsity (mitigated by simulated rider locations in dev/testing).
