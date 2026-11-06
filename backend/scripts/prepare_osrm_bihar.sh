#!/usr/bin/env bash
# ==============================================================================
# Dukaanly: Bihar OpenStreetMap (OSRM) Data Preparation Script
#
# Downloads the Bihar OSM road extract from Geofabrik and preprocesses it
# for the Multi-Level Dijkstra (MLD) routing engine using the pinned OSRM
# backend container.
#
# Prerequisites:
#   - Docker running
#   - curl or wget
#   - ~1.5 GB available RAM
#   - ~500 MB free disk space in deploy/osrm/data
#
# Usage:
#   bash backend/scripts/prepare_osrm_bihar.sh
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DATA_DIR="${REPO_ROOT}/deploy/osrm/data"
OSRM_IMAGE="ghcr.io/project-osrm/osrm-backend:v5.27.1"
PBF_URL="https://download.geofabrik.de/asia/india/bihar-latest.osm.pbf"
PBF_FILE="${DATA_DIR}/bihar-latest.osm.pbf"
OSRM_BASE="${DATA_DIR}/bihar-latest.osrm"

echo "=================================================================="
echo "Dukaanly: Preparing Bihar Road Network for OSRM"
echo "Target Directory: ${DATA_DIR}"
echo "=================================================================="

mkdir -p "${DATA_DIR}"

# 1. Download PBF if not already present
if [ -f "${PBF_FILE}" ]; then
    echo "==> Found existing OSM extract: ${PBF_FILE} ($(du -h "${PBF_FILE}" | cut -f1))"
else
    echo "==> Downloading Bihar extract from Geofabrik (~65MB)..."
    if command -v curl >/dev/null 2>&1; then
        curl -L --fail --show-error -C - -o "${PBF_FILE}" "${PBF_URL}"
    elif command -v wget >/dev/null 2>&1; then
        wget -c -O "${PBF_FILE}" "${PBF_URL}"
    else
        echo "Error: Neither curl nor wget found. Please download ${PBF_URL} to ${PBF_FILE} manually." >&2
        exit 1
    fi
    echo "==> Download complete."
fi

# 2. Check Docker availability
if ! command -v docker >/dev/null 2>&1; then
    echo "Error: Docker CLI not found. Preprocessing requires Docker." >&2
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    echo "Error: Docker daemon is not running or accessible." >&2
    exit 1
fi

# 3. Pull OSRM backend container
echo "==> Verifying OSRM container image (${OSRM_IMAGE})..."
docker pull "${OSRM_IMAGE}"

# 4. Extract road network graph using car profile
echo "==> Step 1/3: Extracting road network (osrm-extract)..."
docker run --rm -t \
    -v "${DATA_DIR}:/data" \
    "${OSRM_IMAGE}" \
    osrm-extract -p /opt/car.lua /data/bihar-latest.osm.pbf

# 5. Partition the road graph for Multi-Level Dijkstra (MLD)
echo "==> Step 2/3: Partitioning road graph (osrm-partition)..."
docker run --rm -t \
    -v "${DATA_DIR}:/data" \
    "${OSRM_IMAGE}" \
    osrm-partition /data/bihar-latest.osrm

# 6. Customize cell weights and routing metrics
echo "==> Step 3/3: Customizing routing metrics (osrm-customize)..."
docker run --rm -t \
    -v "${DATA_DIR}:/data" \
    "${OSRM_IMAGE}" \
    osrm-customize /data/bihar-latest.osrm

# 7. Verify generated artifacts
echo "==> Verifying generated routing artifacts..."
REQUIRED_FILES=(
    "${OSRM_BASE}"
    "${OSRM_BASE}.cells"
    "${OSRM_BASE}.partition"
    "${OSRM_BASE}.mldgr"
    "${OSRM_BASE}.ebg"
    "${OSRM_BASE}.names"
)

ALL_PRESENT=true
for f in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "${f}" ]; then
        echo "Warning: Expected artifact missing: ${f}"
        ALL_PRESENT=false
    fi
done

if [ "$ALL_PRESENT" = true ]; then
    echo "=================================================================="
    echo "SUCCESS: Bihar OSRM routing data prepared successfully!"
    echo "Total data size: $(du -sh "${DATA_DIR}" | cut -f1)"
    echo "To launch the local OSRM routing container:"
    echo "    docker compose up -d osrm"
    echo "Healthcheck test:"
    echo "    curl http://127.0.0.1:5000/nearest/v1/driving/85.1158,25.6144"
    echo "=================================================================="
else
    echo "Error: One or more routing artifacts failed to build." >&2
    exit 1
fi
