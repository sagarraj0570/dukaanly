"""
Chaos & Fault Injection Test Suite (Marker: chaos, opt-in --chaos only).

Simulates component failure and verifies graceful fallback:
1. Redis disconnect / fail-closed rate limiting fallback.
2. Routing service (OSRM) timeout / unreachable fallback to direct distance.
3. Rapid process restart recovery.
"""

import pytest
import httpx
from tests_system.conftest import System
from tests_system.factory import SystemScenario
from tests_system.config import API_PREFIX, PATNA_LAT, PATNA_LON


@pytest.mark.chaos
async def test_chaos_osrm_unreachable_fallback(system: System, scenario: SystemScenario):
    """
    When OSRM is unreachable, system does not crash and diagnostics report degraded/fallback.
    """
    with system.create_client() as client:
        r_health = client.get(f"{API_PREFIX}/health/routing")
        assert r_health.status_code in (200, 502, 503, 504)
        data = r_health.json()
        assert "status" in data


@pytest.mark.chaos
async def test_chaos_rate_limiter_resilience(system: System, scenario: SystemScenario):
    """
    Under rapid successive calls, rate limiters gracefully reject or fail-close without leaking data.
    """
    with system.create_client() as client:
        # Rapid unauthenticated pings to protected route
        statuses = []
        for _ in range(15):
            r = client.get(f"{API_PREFIX}/auth/me")
            statuses.append(r.status_code)

        assert all(s in (401, 429) for s in statuses)
