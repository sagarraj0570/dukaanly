# Dukaanly - Database Design

## 1. Overview
The database is PostgreSQL, utilizing the **PostGIS** extension for geospatial queries. All schema changes will be managed via Alembic.

## 2. Entity-Relationship Diagram

```mermaid
erDiagram
    USERS ||--o{ SHOPS : owns
    USERS ||--o{ ORDERS : places
    USERS ||--o| RIDERS : is
    
    SHOPS ||--o{ SHOP_LISTINGS : has
    SHOPS ||--o{ ORDERS : receives
    
    PRODUCTS ||--o{ SHOP_LISTINGS : templates
    
    ORDERS ||--o{ ORDER_ITEMS : contains
    ORDERS ||--o{ ORDER_STATUS_EVENTS : logs
    RIDERS ||--o{ ORDERS : delivers
    
    SHOP_LISTINGS ||--o{ ORDER_ITEMS : supplies
    
    USERS {
        uuid id PK
        string email UK
        string password_hash
        string role "CUSTOMER, SHOP_OWNER, RIDER"
        string phone
        datetime created_at
    }

    SHOPS {
        uuid id PK
        uuid owner_id FK
        string name
        string description
        geometry location "Point(lon, lat) 4326"
        string address
        boolean is_active
        datetime created_at
    }

    PRODUCTS {
        uuid id PK
        string name
        string category
        string image_url
        string description
    }

    SHOP_LISTINGS {
        uuid id PK
        uuid shop_id FK
        uuid product_id FK "Nullable (if custom product)"
        string custom_name "If no product_id"
        decimal price
        int stock
        int version "Optimistic Locking Column"
        boolean is_available
    }

    ORDERS {
        uuid id PK
        uuid customer_id FK
        uuid shop_id FK
        uuid rider_id FK "Nullable initially"
        string status "PENDING, ACCEPTED, etc"
        decimal total_amount
        string payment_status "MOCKED"
        geometry delivery_location "Point(lon, lat) 4326"
        datetime created_at
    }

    ORDER_ITEMS {
        uuid id PK
        uuid order_id FK
        uuid shop_listing_id FK
        int quantity
        decimal unit_price
    }

    ORDER_STATUS_EVENTS {
        uuid id PK
        uuid order_id FK
        string status
        string note
        datetime created_at
    }

    RIDERS {
        uuid id PK
        uuid user_id FK
        string vehicle_type
        geometry current_location "Point(lon, lat) 4326"
        string status "OFFLINE, ONLINE, BUSY"
    }
```

## 3. Concurrency Control (Optimistic Locking)
To handle concurrent stock updates, the `SHOP_LISTINGS` table includes a `version` column.

When an order is placed, the system attempts to deduct stock like this:
```sql
UPDATE shop_listings 
SET stock = stock - :quantity, 
    version = version + 1 
WHERE id = :listing_id 
  AND stock >= :quantity 
  AND version = :expected_version;
```
If the row count returned is `0`, a race condition occurred (another transaction changed the stock or stock is insufficient). The backend will abort the transaction and return a `409 Conflict`.

## 4. Geospatial Indexing
To support fast nearest-rider and nearby-shop queries, we create **GiST indexes** on the geometry columns.

```sql
CREATE INDEX idx_shops_location ON shops USING GIST (location);
CREATE INDEX idx_riders_current_location ON riders USING GIST (current_location);
```
Using EPSG:4326 (WGS 84) for standard Longitude/Latitude representation. PostGIS functions like `ST_DWithin` will be cast to geography to calculate distances in meters.
