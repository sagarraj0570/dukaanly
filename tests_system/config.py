"""
System Test Harness Configuration.
Namespaces all generated entities under a distinct RUN_ID to isolate from demo data.
"""

import os
import uuid
from typing import Optional


# ── Unique Run Namespace ───────────────────────────────────────────────────────
# Default to an 8-character hex string; can be overridden via environment
RUN_ID = os.environ.get("SYSTEST_RUN_ID", uuid.uuid4().hex[:8])

# ── Service Endpoints ──────────────────────────────────────────────────────────
TARGET_URL = os.environ.get("TARGET_URL", "http://127.0.0.1:8000").rstrip("/")
API_PREFIX = "/api/v1"

# Database Configuration (Separate direct connection for harness assertions)
DEFAULT_ASYNC_DB = "postgresql+asyncpg://dukaanly_user:dukaanly_dev_pass@127.0.0.1:5433/dukaanly"
DEFAULT_SYNC_DB = "postgresql://dukaanly_user:dukaanly_dev_pass@127.0.0.1:5433/dukaanly"

DB_URL = os.environ.get("DATABASE_URL", os.environ.get("DB_URL", DEFAULT_ASYNC_DB))
# Normalize asyncpg dialect for SQLAlchemy async engine
if DB_URL.startswith("postgresql://"):
    ASYNC_DB_URL = DB_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    SYNC_DB_URL = DB_URL
else:
    ASYNC_DB_URL = DB_URL
    SYNC_DB_URL = DB_URL.replace("postgresql+asyncpg://", "postgresql://", 1)

# Redis Configuration
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")

# WebSocket Endpoint Base
WS_URL = os.environ.get(
    "WS_URL",
    TARGET_URL.replace("http://", "ws://").replace("https://", "wss://") + f"{API_PREFIX}/ws/deliveries"
)

# OSRM Endpoint Base
OSRM_BASE_URL = os.environ.get("OSRM_BASE_URL", "http://127.0.0.1:5000")


# ── Namespaced Entity Helpers ──────────────────────────────────────────────────
SYSTEST_TAG_PREFIX = "systest-"
SYSTEST_SHOP_PREFIX = "SYSTEST "


def make_email(role: str, run_id: Optional[str] = None) -> str:
    rid = run_id or RUN_ID
    return f"systest-{rid}-{role}@dukaanly.com"


def make_shop_name(suffix: str = "Bazaar", run_id: Optional[str] = None) -> str:
    rid = run_id or RUN_ID
    return f"SYSTEST {rid} {suffix}"


def make_phone(offset: int = 1, run_id: Optional[str] = None) -> str:
    # 10 digit Indian number with distinct test prefix 9999
    rid = run_id or RUN_ID
    numeric_rid = abs(hash(rid)) % 10000
    return f"9999{numeric_rid:04d}{offset % 100:02d}"


# Standard demo coordinates (Patna Boring Road)
PATNA_LAT = 25.6144
PATNA_LON = 85.1158
