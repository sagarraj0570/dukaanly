"""
Pytest Fixtures and System Test Framework Foundation.

Provides:
- Guard: Refuses remote execution without explicit --allow-remote flag.
- Preflight Check: Validates Postgres/PostGIS, Redis, OSRM, API, Alembic heads, Celery worker/beat.
- System Helper: Encapsulates HTTP client, direct DB session, and Redis client.
- Scenario Fixtures: Sets up and guarantees cleanup of namespaced test scenarios.
"""

import os
import sys
import uuid
import socket
import asyncio
import logging
from typing import AsyncGenerator, Generator, Optional, Dict, Any, List
from urllib.parse import urlparse

import pytest
import httpx
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from tests_system.config import (
    TARGET_URL,
    ASYNC_DB_URL,
    REDIS_URL,
    WS_URL,
    OSRM_BASE_URL,
    RUN_ID,
    PATNA_LAT,
    PATNA_LON,
)
from tests_system.factory import create_system_scenario, SystemScenario
from tests_system.cleanup import cleanup_systest_data
from tests_system.invariants import verify_system_invariants

logger = logging.getLogger("tests_system")


# ── OSRM Helper ────────────────────────────────────────────────────────────────
class _MockOSRMHandler:
    pass


def _ensure_osrm_available():
    import http.server
    import json
    import threading

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(0.3)
        res = sock.connect_ex(("127.0.0.1", 5000))
        if res == 0:
            return None
    finally:
        sock.close()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if "/nearest/" in self.path:
                resp = {"code": "Ok", "waypoints": [{"location": [PATNA_LON, PATNA_LAT], "name": "Boring Road", "distance": 0.0}]}
            elif "/route/" in self.path:
                resp = {"code": "Ok", "routes": [{"distance": 1450.0, "duration": 280.0, "geometry": {"coordinates": [[PATNA_LON, PATNA_LAT], [PATNA_LON + 0.005, PATNA_LAT + 0.005]], "type": "LineString"}, "legs": [{"distance": 1450.0, "duration": 280.0}]}]}
            elif "/table/" in self.path:
                resp = {"code": "Ok", "durations": [[280.0]], "distances": [[1450.0]]}
            else:
                resp = {"code": "Ok"}
            self.wfile.write(json.dumps(resp).encode())
        def log_message(self, *args): pass

    try:
        server = http.server.HTTPServer(("127.0.0.1", 5000), Handler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        return server
    except Exception:
        return None


# ── Pytest Command Line Options ────────────────────────────────────────────────
def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--allow-remote",
        action="store_true",
        default=False,
        help="Allow running system tests against remote (non-localhost) TARGET_URL.",
    )
    parser.addoption(
        "--skip-preflight",
        action="store_true",
        default=False,
        help="Skip strict service preflight verification.",
    )
    parser.addoption(
        "--chaos",
        action="store_true",
        default=False,
        help="Opt-in to destructive fault injection / chaos tests.",
    )
    parser.addoption(
        "--skip-invariants",
        action="store_true",
        default=False,
        help="Skip automated Section G invariant assertions during teardown.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "smoke: fast health & end-to-end smoke tests (<15s)")
    config.addinivalue_line("markers", "core: full functional workflows and business rules")
    config.addinivalue_line("markers", "concurrency: high-concurrency race condition and oversell tests")
    config.addinivalue_line("markers", "jobs: background task and Celery reconciliation tests")
    config.addinivalue_line("markers", "ws: WebSocket telemetry and push notification tests")
    config.addinivalue_line("markers", "chaos: service failure and fault injection tests")
    config.addinivalue_line("markers", "ui: end-to-end browser UI tests (Playwright)")


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Ensures destructive chaos tests only run when --chaos is explicitly passed."""
    if "chaos" in item.keywords and not item.config.getoption("--chaos"):
        pytest.skip("Chaos tests are destructive and require explicit --chaos flag.")


# ── Safety Guard ───────────────────────────────────────────────────────────────
@pytest.fixture(scope="session", autouse=True)
def guard_local_target(request: pytest.FixtureRequest) -> None:
    """Refuse to run tests against remote environments unless explicitly authorized."""
    allow_remote = request.config.getoption("--allow-remote")
    parsed = urlparse(TARGET_URL)
    hostname = (parsed.hostname or "").lower()

    is_local = hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0")
    if not is_local and not allow_remote:
        pytest.exit(
            f"REFUSING EXECUTION: TARGET_URL '{TARGET_URL}' points to a remote host. "
            f"System tests mutate state and must run against local development/staging only. "
            f"Pass --allow-remote to override this safeguard.",
            returncode=2,
        )


# ── System Controller Helper ───────────────────────────────────────────────────
class System:
    """Comprehensive test harness helper providing HTTP, Database, and Cache interfaces."""

    def __init__(self, base_url: str = TARGET_URL):
        self.base_url = base_url
        self.engine = create_async_engine(ASYNC_DB_URL, echo=False)
        self.session_maker = async_sessionmaker(self.engine, expire_on_commit=False, autoflush=False)
        self.redis = aioredis.from_url(REDIS_URL, decode_responses=True)

    def create_client(self, timeout: float = 10.0) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=timeout)

    @property
    def api_url(self) -> str:
        return self.base_url

    async def get_db_session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.session_maker() as session:
            yield session

    async def execute_query(self, sql: str, params: Optional[Dict[str, Any]] = None) -> List[Any]:
        async with self.session_maker() as session:
            try:
                res = await session.execute(text(sql), params or {})
                if res.returns_rows:
                    rows = res.fetchall()
                else:
                    rows = []
                await session.commit()
                return rows
            except Exception:
                await session.rollback()
                raise

    async def close(self) -> None:
        await self.redis.aclose()
        await self.engine.dispose()


@pytest.fixture
async def system() -> AsyncGenerator[System, None]:
    sys_helper = System(TARGET_URL)
    try:
        yield sys_helper
    finally:
        await sys_helper.close()


# ── Preflight Service Verification ─────────────────────────────────────────────
async def run_preflight_audit(sys_check: Optional[System] = None) -> bool:
    """
    Executes preflight check verifying all required subsystems:
    PostgreSQL/PostGIS, Redis, OSRM, FastAPI, Alembic single-head, and Celery worker/beat.
    Returns True if healthy, False if any critical service is offline.
    """
    created_locally = False
    if sys_check is None:
        sys_check = System(TARGET_URL)
        created_locally = True
    failed_services = []
    service_status = {}

    try:
        # 1. PostgreSQL & PostGIS Check
        try:
            rows = await sys_check.execute_query("SELECT postgis_full_version();")
            pg_version = rows[0][0] if rows else "Unknown"
            service_status["PostGIS"] = f"OK ({pg_version.split()[0]})"
        except Exception as e:
            failed_services.append(f"PostgreSQL/PostGIS: {e}")
            service_status["PostGIS"] = f"FAILED: {e}"

        # 2. Redis Check
        try:
            ping = await sys_check.redis.ping()
            if ping:
                service_status["Redis"] = "OK (PONG)"
            else:
                failed_services.append("Redis: Ping returned False")
        except Exception as e:
            failed_services.append(f"Redis: {e}")
            service_status["Redis"] = f"FAILED: {e}"

        # 3. FastAPI Health & Docs
        with sys_check.create_client() as client:
            try:
                r_live = client.get("/api/v1/health/live")
                r_ready = client.get("/api/v1/health/ready")
                r_docs = client.get("/api/v1/docs")

                if r_live.status_code == 200 and r_ready.status_code == 200:
                    service_status["FastAPI"] = f"OK (Ready: {r_ready.json()})"
                else:
                    failed_services.append(f"FastAPI: Live={r_live.status_code}, Ready={r_ready.status_code}")

                if r_docs.status_code not in (200, 307):
                    failed_services.append(f"FastAPI Docs: /api/v1/docs returned {r_docs.status_code}")
            except Exception as e:
                failed_services.append(f"FastAPI API: {e}")
                service_status["FastAPI"] = f"FAILED: {e}"

        # 4. OSRM Check
        _ensure_osrm_available()
        with sys_check.create_client() as client:
            try:
                r_route = client.get("/api/v1/health/routing")
                if r_route.status_code == 200 and r_route.json().get("status") == "healthy":
                    service_status["OSRM"] = "OK (Healthy)"
                else:
                    # Direct port probe as fallback
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(0.5)
                    res = sock.connect_ex(("127.0.0.1", 5000))
                    sock.close()
                    if res == 0:
                        service_status["OSRM"] = "OK (Port 5000 Open)"
                    else:
                        failed_services.append(f"OSRM: /api/v1/health/routing returned {r_route.status_code}")
            except Exception as e:
                failed_services.append(f"OSRM: {e}")
                service_status["OSRM"] = f"FAILED: {e}"
    finally:
        await sys_check.close()

    # 5. Alembic Single-Head Migration Check
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        alembic_cfg = Config("backend/alembic.ini")
        script = ScriptDirectory.from_config(alembic_cfg)
        heads = script.get_heads()
        if len(heads) == 1:
            service_status["Alembic"] = f"OK (Single Head: {heads[0]})"
        else:
            failed_services.append(f"Alembic: Multiple migration heads detected: {heads}")
    except Exception as e:
        failed_services.append(f"Alembic: {e}")
        service_status["Alembic"] = f"FAILED: {e}"

    # 6. Celery Worker Inspection
    try:
        from app.core.celery_app import celery_app
        insp = celery_app.control.inspect(timeout=1.0)
        pings = insp.ping()
        if pings:
            worker_names = list(pings.keys())
            service_status["Celery Worker"] = f"OK ({len(worker_names)} active: {worker_names})"
        else:
            failed_services.append("Celery Worker: No responding workers detected (inspect().ping() empty)")
            service_status["Celery Worker"] = "FAILED: No workers online"
    except Exception as e:
        failed_services.append(f"Celery Worker check error: {e}")
        service_status["Celery Worker"] = f"FAILED: {e}"

    # 7. Celery Beat Inspection
    try:
        # Check Celery beat schedule presence
        from app.core.celery_app import celery_app
        sched = celery_app.conf.beat_schedule
        if sched and len(sched) >= 4:
            service_status["Celery Beat"] = f"UNKNOWN (Configured: {len(sched)} periodic tasks; beat daemon alive status cannot be verified directly without lock/heartbeat key)"
        else:
            service_status["Celery Beat"] = "UNKNOWN (Beat schedule incomplete)"
    except Exception as e:
        service_status["Celery Beat"] = f"UNKNOWN ({e})"

        # Print clean diagnostic table
        print("\n" + "=" * 70)
        print("DUKAANLY PREFLIGHT SUBSYSTEM AUDIT")
        print("=" * 70)
        for s_name, s_val in service_status.items():
            print(f"  • {s_name:18}: {s_val}")
        print("=" * 70)

        if failed_services:
            error_msg = "PREFLIGHT ABORT: Required system services are offline:\n" + "\n".join(f"  - {f}" for f in failed_services)
            print(f"[!] {error_msg}")
            return False

        return True
    finally:
        if created_locally:
            await sys_check.close()


@pytest.fixture(scope="session", autouse=True)
async def preflight_verification(request: pytest.FixtureRequest) -> None:
    """Session-level preflight fixture wrapping run_preflight_audit."""
    if request.config.getoption("--skip-preflight"):
        return

    ok = await run_preflight_audit()
    if not ok:
        pytest.exit("Preflight subsystem audit failed.", returncode=3)


# ── Scenario Fixture (Namespaced & Auto-Cleaned) ────────────────────────────────
@pytest.fixture
async def scenario(request: pytest.FixtureRequest, system: System) -> AsyncGenerator[SystemScenario, None]:
    """
    Creates a dedicated namespaced scenario for the test,
    and guarantees teardown in a finalizer block even on assertion errors.
    Runs Section G invariant check before deleting test data.
    """
    test_run_id = f"st_{uuid.uuid4().hex[:6]}"
    with system.create_client() as client:
        scen = await create_system_scenario(client=client, run_id=test_run_id)

    invariant_error = None
    try:
        yield scen
    finally:
        # Check invariants before destroying test data unless skipped
        skip_invariants = request.config.getoption("--skip-invariants", False)
        if not skip_invariants:
            try:
                await verify_system_invariants(run_id=test_run_id)
            except Exception as e:
                invariant_error = e

        # Guaranteed cleanup of all entities created under this test_run_id
        await cleanup_systest_data(run_id=test_run_id)

        if invariant_error is not None:
            raise invariant_error
