# Dukaanly - API Specification

## 1. RESTful Conventions
- **Base URL**: `/api/v1`
- **Format**: JSON payloads.
- **Authentication**: Bearer Token in `Authorization` header.
- **Pagination**: Query params `?skip=0&limit=20` for list endpoints.

## 2. Core Endpoints

### Auth
- `POST /auth/register` - Register a new user.
- `POST /auth/login` - Login, returns JWT and Refresh Token.
- `POST /auth/refresh` - Refresh access token.

### Shops
- `POST /shops` - Create a new shop (Shop Owner).
- `GET /shops/nearby?lat=X&lng=Y&radius=Z` - Get shops within radius (Customer).
- `GET /shops/{shop_id}` - Get shop details.

### Catalog & Inventory
- `POST /shops/{shop_id}/products` - Add a product to a shop's catalog.
- `GET /shops/{shop_id}/products` - Browse a shop's products.
- `GET /products/{product_id}` - Get product details.
- `PATCH /products/{product_id}` - Update a product's catalog details and price.
- `PATCH /products/{product_id}/inventory` - Update product stock (Future).

### Orders & Checkout
- `POST /orders` - Place a new order (Checkout).
- `GET /orders` - List orders for the current user (Customer/Shop/Rider).
- `GET /orders/{order_id}` - Order details.
- `PATCH /orders/{order_id}/status` - Update order state (Shop/Rider).

### Riders
- `POST /riders` - Register as a rider.
- `PATCH /riders/me/status` - Toggle ONLINE/OFFLINE.
- `PATCH /riders/me/location` - Update live coordinates.
- `GET /orders/assignable` - Internal/Webhook: trigger rider assignment logic.

---

## 3. Example Payloads & Scenarios

### A. Placing an Order (with Race Condition Handling)
**Request**: `POST /orders`
```json
{
  "shop_id": "uuid-1234",
  "delivery_location": {"lat": 12.9716, "lng": 77.5946},
  "items": [
    {
      "product_id": "uuid-abcd",
      "quantity": 2,
      "expected_version": 5
    }
  ],
  "payment_method": "UPI_MOCK"
}
```
**Response (Success - 201 Created)**:
```json
{
  "order_id": "uuid-9876",
  "status": "PENDING",
  "total_amount": 250.00
}
```
**Response (Race Condition / Stock Out - 409 Conflict)**:
```json
{
  "detail": "Inventory mismatch or stock unavailable for product: uuid-abcd. Please refresh cart."
}
```

### B. Rider Assignment (PostGIS Trigger)
While mostly internal, the assignment logic finds riders like so:
**Internal Query Logic**:
Find riders where `status = 'ONLINE'` and `ST_DWithin(current_location, shop_location, 5000)`.
**Notification**: Sent via WebSocket to the chosen Rider's client.

### C. WebSocket Events for Real-Time Tracking
**Connection**: `ws://api.dukaanly.com/ws/tracking/{order_id}`
**Event Payload (Rider Location Update)**:
```json
{
  "type": "LOCATION_UPDATE",
  "data": {
    "lat": 12.9720,
    "lng": 77.5940,
    "timestamp": "2026-10-04T20:55:00Z"
  }
}
```
**Event Payload (Order Status Update)**:
```json
{
  "type": "STATUS_UPDATE",
  "data": {
    "status": "PICKED_UP",
    "note": "Rider is on the way"
  }
}
```
