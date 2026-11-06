# Dukaanly — Merchant Import & Candidate Directory Guide

## 1. Overview & Core Philosophy

Dukaanly incorporates public business-listing data to power neighbourhood shop discovery across **Patna, Bihar, India**. 

The governing principle of this integration is:
> **Public listing data enables discovery; it does NOT create verified merchants, imply merchant consent, confirm inventory, or grant delivery eligibility.**

Every business in Dukaanly progresses through explicit lifecycle states:
1. **`discovered`**: Ingested public listing (non-orderable, `is_orderable = False`, `owner_id = NULL`).
2. **`pending_review`**: Claimed or flagged for KYC and store identity review.
3. **`verified`**: Ownership validated by partner onboarding; store profile active.
4. **`rejected`**: Discarded due to invalid coordinates, permanently closed, or duplicate.
5. **`archived`**: Inactive historic listing.

An order can **only** be placed when:
- `shop.is_active == True`
- `shop.is_orderable == True`
- `shop.verification_status == 'verified'`
- Delivery destination is within the shop's 5 km delivery service radius (`ST_DWithin` PostGIS check).

---

## 2. Provider Choice & Licensing / Terms Review

### OpenStreetMap (OSM) via Overpass API / Regional Extracts
- **Licensing**: Open Database License (ODbL) 1.0.
- **Permitted Use**: Public Point-of-Interest (POI) nodes under retail tags (`shop=supermarket`, `shop=convenience`, `shop=grocery`, `shop=chemist`, `shop=bakery`, `shop=dairy`).
- **Attribution Requirement**: Mandatory attribution displayed on all UI surfaces and persisted in database records:
  ```text
  © OpenStreetMap contributors, ODbL
  ```
- **Acceptable Use & Politeness**:
  - Dukaanly **never** uses the public Nominatim search API for bulk harvesting.
  - Live Overpass API queries are bounded strictly to regional envelopes with client rate-limiting, exponential backoff, and caching.
  - A pre-vetted regional extract (`CuratedDatasetProvider`) is provided for 100% deterministic local execution, offline environments, and CI pipelines.

### Prohibited Sources
- **Google Maps Web Scraping**: Strictly prohibited under Google Terms of Service.
- **Google Places API Permanent Coordinate Copying**: Google Places terms prohibit permanently copying or storing place coordinates, names, or metadata in third-party relational databases.

---

## 3. Architecture & Provider Adapter Interface

The importer architecture decouples external data providers from the core shop discovery and checkout engines:

```text
[External Source (OSM / Regional Extract)]
                  │
                  ▼
       [BaseListingProvider]
        ├── OSMOverpassProvider
        └── CuratedDatasetProvider
                  │
                  ▼ (NormalizedListing)
       [MerchantImportService]
        ├── Boundary & Coordinate Check
        ├── Category Allowlist Filter
        ├── Provider ID Deduplication
        └── PostGIS Spatial Dedup (ST_DWithin ≤ 25m)
                  │
                  ▼
          [PostgreSQL + PostGIS]
          (shops table, verification_status='discovered')
```

### Key Modules:
- `backend/app/services/importer/base.py`: Abstract `BaseListingProvider`, `AreaConfig`, `NormalizedListing`, and `ImportSummary`.
- `backend/app/services/importer/osm_provider.py`: Overpass API adapter with retry backoff and error handling.
- `backend/app/services/importer/curated_provider.py`: Permitted regional extract provider.
- `backend/app/services/importer/pipeline.py`: Transactional import engine with spatial deduplication and dry-run simulation.
- `backend/app/cli/import_merchants.py`: Production-conscious CLI script.

---

## 4. Running the Import CLI

All CLI runs must be executed from the `backend/` directory within the Python virtual environment:

```powershell
cd backend
.\venv\Scripts\Activate.ps1
```

### A. Dry-Run Mode (0 Database Writes)
Simulate the import, validate coordinates, test category allowlists, and check duplicate detection without modifying the database:

```powershell
python -m app.cli.import_merchants --provider curated --dry-run
```

Output example:
```text
=================================================================
 DUKAANLY MERCHANT DIRECTORY PIPELINE -- DRY-RUN (Simulated, 0 DB writes)
=================================================================
 Provider:   curated (© OpenStreetMap contributors, ODbL)
 Envelope:   Patna, Bihar [25.55, 85.05] to [25.65, 85.25]
 Categories: grocery, supermarket, convenience, chemist, bakery, dairy
 Max Limit:  50
-----------------------------------------------------------------

=================================================================
 IMPORT SUMMARY (DRY-RUN COMPLETE)
=================================================================
 Total Candidates Evaluated: 23
 Accepted & Validated:       23
 Duplicates (Provider ID):   0
 Duplicates (Spatial <= 25m): 0
 Rejected (Outside Bounds):  0
 Rejected (Category):        0
=================================================================
```

### B. Live Regional Import
Persist candidate listings into PostgreSQL:

```powershell
python -m app.cli.import_merchants --provider curated --max-records 30
```

### C. Live Overpass API Query (Targeted Categories)
Fetch directly from OpenStreetMap servers in dry-run mode:

```powershell
python -m app.cli.import_merchants --provider osm --categories grocery,chemist --dry-run
```

### D. JSON Output (Scripting / Audit)
```powershell
python -m app.cli.import_merchants --provider curated --dry-run --json
```

---

## 5. Geographic Scope & Categories

### Pilot Patna Envelope
- **Latitude Range**: `25.5500° N` to `25.6500° N`
- **Longitude Range**: `85.0500° E` to `85.2500° E`
- **Pilot Commercial Clusters**:
  1. **Boring Road / Boring Canal Rd** (`25.6144, 85.1158`) — High-density daily provisions, groceries, bakeries, pharmacies.
  2. **Kankarbagh Main Road** (`25.5947, 85.1588`) — Independent kirana and supermarket clusters.
  3. **Rajendra Nagar Market** (`25.6022, 85.1633`) — Traditional neighbourhood bazaars.
  4. **Bailey Road / Raja Bazar** (`25.6083, 85.0892`) — Western arterial retail corridor.

### Category Allowlist
Only essential neighbourhood commerce categories supported by Dukaanly are ingested:
- `grocery`: Kirana, provisions, staples, grains.
- `supermarket`: Self-service food and FMCG marts.
- `convenience`: Daily fresh, milk booths, general stores.
- `chemist`: Pharmacies, OTC health essentials.
- `bakery`: Artisan breads, packaged baked goods.
- `dairy`: Milk depots, fresh dairy items.

Non-relevant retail (e.g., auto parts, fashion, electronics, hardware) is discarded at ingestion.

---

## 6. Deduplication & Idempotency Strategy

The pipeline applies two layers of conservative deduplication:

1. **Provider Identity (`source`, `source_id`)**:
   - Backed by PostgreSQL unique index `uq_shops_source_source_id`.
   - Re-running the import on the same source updates `last_seen_at` without duplicating the shop record.
2. **Spatial Deduplication (`ST_DWithin` ≤ 25m)**:
   - Evaluates PostGIS geography ellipsoidal meter distance.
   - If an existing shop exists within 25 meters with a matching or highly similar name, the candidate is classified as a duplicate and skipped.
   - Ambiguous listings with different names at the same complex are preserved separately for human review.

---

## 7. Discovery Radius vs. Delivery Service Zone

Dukaanly maintains a strict distinction between **shop discovery** and **doorstep delivery**:

| Metric | Configured Value | Enforcement |
| :--- | :---: | :--- |
| **Default Discovery Radius** | **5 km** | Applied when customer coordinates are provided. |
| **Customer Selectable Radii** | **3 km, 5 km, 10 km** | Reconciled across frontend and backend. |
| **Max Discovery Radius** | **10 km** (`10,000 m`) | Clamped by backend validation (`le=10000`) and frontend store. |
| **Delivery Service Zone** | **5 km** (`5,000 m`) | Fixed boundary. Customers > 5 km away can view shops but cannot order delivery. |

---

## 8. Database Migrations, Merchant Claiming Security & Rollback Runbook

### A. Migration Chain
- **Base Revision**: `710e16fe5e57` (Add notifications table)
- **Intermediate Migration**: `83f19e42bd31` (`83f19e42bd31_add_shop_verification_and_public_listings.py`):
  - Made `shops.owner_id` nullable (`SET NULL` on FK delete).
  - Created `shop_verification_status` PostgreSQL enum (`discovered`, `claimed`, `verified`).
  - Added `is_orderable`, `source`, `source_id`, `source_attribution`, `phone`, `opening_hours`.
  - Added unique partial index `uq_shops_source_source_id`.
- **Head Migration**: `94e21a87bf02` (`94e21a87bf02_add_merchant_provenance_and_expanded_lifecycle.py`):
  - Added `imported_at` (`TIMESTAMPTZ`), `last_seen_at` (`TIMESTAMPTZ`), `original_url` (`VARCHAR(500)`).
  - Expanded `shop_verification_status` with `pending_review`, `rejected`, `archived`.
- **Apply Command**:
  ```powershell
  alembic upgrade head
  ```
- **Downgrade Command**:
  ```powershell
  alembic downgrade -1   # Downgrades 94e21a87bf02 to 83f19e42bd31
  alembic downgrade -2   # Downgrades back to 710e16fe5e57
  ```

### B. Merchant Claiming Security Guardrails
Public candidate listings (`owner_id = NULL`, `verification_status = 'discovered'`) are strictly protected against unauthorized claims:
1. **Schema Protection**: `ShopUpdate` excludes `owner_id`, `verification_status`, and `is_orderable`. Clients cannot pass these fields in API payloads.
2. **Endpoint Ownership Isolation**: `PATCH /api/v1/shops/{shop_id}` requires `current_user.id == shop.owner_id`. Because `shop.owner_id` is `None` on candidate listings, any claim attempt by arbitrary users returns `HTTP 403 Forbidden`.
3. **Product Catalog Protection**: `POST /api/v1/shops/{shop_id}/products` enforces `verify_shop_ownership`, preventing unauthorized product creation.
4. **Order Guardrails**: `POST /api/v1/cart/items` and `POST /api/v1/orders/checkout` reject unverified shops with `HTTP 400 Bad Request`.
5. **Future Claim Workflow**: Claiming requires verified identity documentation (e.g. GSTIN/FSSAI, phone OTP verification matching listing) reviewed and approved via an authorized verification service before `owner_id` is assigned and `verification_status` is transitioned to `verified`.

### C. Safe Production Ingestion Rollback Runbook
Never execute blanket SQL deletions against production. Follow this 4-step audited procedure:

1. **Step 1: Backup Database Snapshot**:
   ```bash
   pg_dump -h localhost -p 5432 -U postgres -d dukaanly -F c -f "dukaanly_pre_rollback_$(date +%Y%m%d_%H%M%S).dump"
   ```

2. **Step 2: Preview Affected Rows (Read-Only Audit)**:
   Filter strictly by the specific import batch timestamp window and source:
   ```sql
   SELECT id, name, source, source_id, verification_status, imported_at
   FROM shops
   WHERE source = 'osm'
     AND verification_status = 'discovered'
     AND imported_at >= '2026-10-13 18:00:00+00' -- Specific import batch window!
     AND imported_at <= '2026-10-13 19:00:00+00'
   ORDER BY imported_at DESC;
   ```

3. **Step 3: Execute Scoped Transactional Deletion**:
   Run inside an explicit transaction block so the row count can be verified before committing:
   ```sql
   BEGIN;

   DELETE FROM shops
   WHERE source = 'osm'
     AND verification_status = 'discovered'
     AND owner_id IS NULL
     AND imported_at >= '2026-10-13 18:00:00+00'
     AND imported_at <= '2026-10-13 19:00:00+00';

   -- Inspect rows affected count in output:
   -- If count matches preview from Step 2 exactly:
   COMMIT;
   -- If count does NOT match preview:
   ROLLBACK;
   ```

4. **Step 4: Verify PostGIS Spatial Index Integrity**:
   ```sql
   REINDEX TABLE shops;
   ```

---

## 9. Separation of Bengaluru Demo Data and Patna Records

- Automated backend tests (e.g. `test_shops.py`) dynamically create temporary test shops in Bengaluru (`12.9716, 77.5946`) or Patna (`25.6144, 85.1158`).
- The primary development seed script (`seed_demo.py`) positions the verified partner shop (*"Patna Super Kirana"*) and delivery rider in Boring Road, Patna (`25.6144, 85.1158`).
- Real Patna candidate records maintain `source="osm"`, `is_orderable=False`, and `owner_id=NULL`.
