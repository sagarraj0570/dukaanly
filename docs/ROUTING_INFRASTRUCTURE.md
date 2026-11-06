# Dukaanly: Reliable Production Routing Infrastructure

This guide specifies the architecture, deployment runbook, resource sizing, monitoring, and maintenance procedures for Dukaanly's routing engine in Patna, Bihar.

---

## 1. Architecture Overview

Hyperlocal delivery in Dukaanly depends on accurate driving distances, real road geometry, and traffic-aware candidate ranking.

```
                    +------------------------------------+
                    |        Client Applications         |
                    | (Customer Tracker / Rider Cockpit) |
                    +-----------------+------------------+
                                      |
                                      | HTTPS / WSS
                                      v
                    +-----------------+------------------+
                    |           Caddy Proxy              |
                    +-----------------+------------------+
                                      |
                                      | Internal Docker Network
                                      v
                    +-----------------+------------------+
                    |        FastAPI Backend             |
                    |  - Connection pooling (keep-alive) |
                    |  - Concurrency Semaphore (max 10)  |
                    |  - Redis caching (300s TTL)        |
                    +--------+------------------+--------+
                             |                  |
           PostGIS Distance  |                  | OSRM Road Routing
        & Candidate Discovery|                  | & Table Matrix
                             v                  v
                   +---------+----+      +------+---------+
                   |  PostgreSQL  |      |  OSRM Backend  |
                   |   (PostGIS)  |      | (Bihar MLD 5k) |
                   +--------------+      +----------------+
```

### Key Architectural Invariants
1. **Self-Hosted Isolation**: Dukaanly never uses public routing demo endpoints in production. The public `router.project-osrm.org` endpoint is rate-limited, subject to unannounced downtime, and forbidden by production environment validators.
2. **PostGIS Discovery + OSRM Ranking**: Candidate discovery is performed on true `geometry` columns using PostGIS (`ST_DWithin` & `ST_Distance`). The top candidates (up to `RIDER_MAX_CANDIDATES_TO_ROUTE = 5`) are then ranked via the OSRM Table API.
3. **No Fabricated Road Geometry**: If the routing service is unavailable or a destination is unroutable, the system **never** fabricates straight-line polylines as road routes. Routes return explicit HTTP error codes (`504 Gateway Timeout`, `404 Not Found`), candidate ranking marks status as `"straight_line_fallback"`, and ETA calculation honestly tags the duration source as `"fallback_estimate"`.
4. **Offline Map Preprocessing**: Large OpenStreetMap extracts are **never** downloaded or preprocessed during container boot (`start.sh`). Maps are preprocessed ahead of time using dedicated build scripts.

---

## 2. Configuration & Environment Variables

All routing parameters are configurable via standard environment variables:

| Variable | Default | Production Requirement | Description |
| :--- | :--- | :--- | :--- |
| `ROUTING_PROVIDER` | `osrm` | `osrm` | Active routing engine provider. |
| `OSRM_BASE_URL` | `http://localhost:5000` | `http://osrm:5000` | Base URL of the OSRM HTTP service. Must NOT be `router.project-osrm.org` in production. |
| `OSRM_TIMEOUT_SECONDS` | `4.0` | `4.0` | Upstream HTTP read/write timeout in seconds. |
| `OSRM_CACHE_TTL_SECONDS` | `300` | `300` | Redis route cache TTL (5 minutes). |
| `OSRM_MAX_CONCURRENT_REQUESTS`| `10` | `10` to `20` | Maximum simultaneous in-flight queries to the OSRM service. |

---

## 3. Resource Requirements

### Preprocessing (Build Time)
- **CPU**: 2+ vCPUs
- **RAM**: ~1.5 GB peak during `osrm-extract` and `osrm-partition`
- **Disk Space**: ~500 MB (OSM extract: ~65 MB; preprocessed MLD files: ~280 MB)
- **Time**: ~3 to 4 minutes on modern hardware

### Runtime (Serving Bihar Network)
- **CPU**: 0.2 to 0.5 vCPU baseline (scales with concurrent route queries)
- **RAM**: ~250 MB to 350 MB resident memory
- **Disk Space**: ~300 MB read-only volume mount (`deploy/osrm/data`)
- **Port**: `5000` (internal network only in production; no public exposure)

---

## 4. Bihar OSM Preparation Runbook

Map data must be preprocessed prior to launching the production container. Dukaanly provides reproducible automation scripts for both Unix and Windows environments.

### Option A: Linux / macOS / CI
```bash
# 1. Run the preparation script from the repository root
bash backend/scripts/prepare_osrm_bihar.sh

# 2. Verify generated files in deploy/osrm/data/
ls -lh deploy/osrm/data/
# Expected:
#   bihar-latest.osm.pbf (~65MB)
#   bihar-latest.osrm
#   bihar-latest.osrm.cells
#   bihar-latest.osrm.partition
#   bihar-latest.osrm.mldgr
#   bihar-latest.osrm.ebg
#   bihar-latest.osrm.names
```

### Option B: Windows (PowerShell)
```powershell
# 1. Run the PowerShell preparation script
powershell -ExecutionPolicy Bypass -File backend\scripts\prepare_osrm_bihar.ps1

# 2. Verify generated files
Get-ChildItem deploy\osrm\data
```

### Option C: Manual Docker Steps
If executing outside the helper scripts:
```bash
# 1. Download extract
curl -L -o deploy/osrm/data/bihar-latest.osm.pbf https://download.geofabrik.de/asia/india/bihar-latest.osm.pbf

# 2. Extract car profile graph
docker run --rm -v "$(pwd)/deploy/osrm/data:/data" ghcr.io/project-osrm/osrm-backend:v5.27.1 \
    osrm-extract -p /opt/car.lua /data/bihar-latest.osm.pbf

# 3. Partition for Multi-Level Dijkstra (MLD)
docker run --rm -v "$(pwd)/deploy/osrm/data:/data" ghcr.io/project-osrm/osrm-backend:v5.27.1 \
    osrm-partition /data/bihar-latest.osrm

# 4. Customize cell weights
docker run --rm -v "$(pwd)/deploy/osrm/data:/data" ghcr.io/project-osrm/osrm-backend:v5.27.1 \
    osrm-customize /data/bihar-latest.osrm
```

---

## 5. Deployment & Container Management

### Local Development (`docker-compose.yml`)
The development stack maps port 5000 to localhost for inspection:
```bash
docker compose up -d osrm
```

Test the local daemon directly:
```bash
curl "http://127.0.0.1:5000/nearest/v1/driving/85.1158,25.6144"
```

### Production Deployment (`docker-compose.prod.yml`)
In production, OSRM runs on the isolated `dukaanly_private` bridge network without exposing host ports.
```bash
# Launch full stack
docker compose -f docker-compose.prod.yml up -d
```

---

## 6. Health Checks & Monitoring

### 1. HTTP Endpoint Probe
FastAPI provides a dedicated routing probe:
```bash
curl http://localhost:8000/api/v1/health/routing
```
**Healthy Response (200 OK):**
```json
{
  "status": "healthy",
  "provider": "osrm",
  "base_url": "http://osrm:5000",
  "details": "OSRM routing service operational"
}
```
**Unavailable Response (503 Service Unavailable):**
```json
{
  "status": "unreachable",
  "provider": "osrm",
  "base_url": "http://osrm:5000",
  "details": "OSRM service offline"
}
```

### 2. Container Healthcheck
Both `docker-compose.yml` and `docker-compose.prod.yml` define healthchecks:
```yaml
healthcheck:
  test: ["CMD-SHELL", "wget -q -O - http://127.0.0.1:5000/nearest/v1/driving/85.1158,25.6144 | grep -q 'code.*Ok' || exit 1"]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 15s
```

---

## 7. Zero-Downtime Map Updates & Rollback

OpenStreetMap data changes as new roads and bypasses open in Patna. Updates should occur monthly.

### Zero-Downtime Update Procedure
1. Create a staging data directory:
   ```bash
   mkdir -p deploy/osrm/data_new
   ```
2. Download and preprocess the new extract inside `deploy/osrm/data_new`.
3. Verify artifacts in `data_new` with a temporary container.
4. Swap directories atomically:
   ```bash
   mv deploy/osrm/data deploy/osrm/data_backup_$(date +%Y%m%d)
   mv deploy/osrm/data_new deploy/osrm/data
   ```
5. Reload the OSRM container:
   ```bash
   docker compose -f docker-compose.prod.yml restart osrm
   ```
6. Verify routing health:
   ```bash
   curl http://localhost:8000/api/v1/health/routing
   ```

### Rollback Procedure
If the newly built map exhibits issues (e.g., missing road segments or unroutable bridges):
1. Immediately revert to the backup directory:
   ```bash
   mv deploy/osrm/data deploy/osrm/data_failed
   mv deploy/osrm/data_backup_YYYYMMDD deploy/osrm/data
   ```
2. Restart the OSRM service:
   ```bash
   docker compose -f docker-compose.prod.yml restart osrm
   ```
3. Confirm recovery using `/api/v1/health/routing`.
