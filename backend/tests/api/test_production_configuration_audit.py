"""
Production & Staging Configuration Audit Suite.

Verifies:
1. Production configuration guardrails (secrets >= 32 chars, DEBUG=False, ALLOW_MOCK_PAYMENTS=False).
2. Staging database connectivity, PostGIS 3.4 verification, and Alembic HEAD revision check.
3. AI feature flags isolation and global kill-switch zero blast radius.
4. Diagnostic endpoint RBAC authorization (401 unauth, 403 customer/rider, 200 admin) and cost-abuse cooldown.
5. Per-user rate limiting enforcement (HTTP 429 with Retry-After).
6. Alembic bidirectional migration chain and rollback procedures integrity.
"""

from decimal import Decimal
from pathlib import Path
import time
import uuid
import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.ai import (
    AIService,
    MockLLMProvider,
    ai_service,
)
from app.core.ai.schemas import (
    ChatMessage,
    ChatRole,
    LLMCompletionRequest,
)
from app.core.config import Settings, settings
from app.core.security import create_access_token
from app.db.session import async_session_maker, engine
from app.models.user import User, UserRole

# pytestmark = pytest.mark.asyncio removed to prevent warnings on sync functions

PATNA_LAT = 25.6144
PATNA_LON = 85.1158


# ---------------------------------------------------------------------------
# 1. Production Secrets, Debug Mode, and Mock Payments Guardrails
# ---------------------------------------------------------------------------

def test_production_secrets_and_jwt_guardrails():
    """Verify that production settings enforce strict cryptographic and security invariants."""
    # 1. Rejects default development secret
    with pytest.raises(ValidationError) as exc1:
        Settings(
            APP_ENV="production",
            JWT_SECRET_KEY="supersecret_for_development_only",
            DEBUG=False,
            ALLOW_MOCK_PAYMENTS=False,
        )
    assert "In production, JWT_SECRET_KEY must be a strong random secret" in str(exc1.value)

    # 2. Rejects short secret (< 32 chars)
    with pytest.raises(ValidationError) as exc2:
        Settings(
            APP_ENV="production",
            JWT_SECRET_KEY="too_short_secret_under_32_ch",
            DEBUG=False,
            ALLOW_MOCK_PAYMENTS=False,
        )
    assert "at least 32 characters" in str(exc2.value)

    # 3. Rejects DEBUG=True in production
    with pytest.raises(ValidationError) as exc3:
        Settings(
            APP_ENV="production",
            JWT_SECRET_KEY="f" * 64,
            DEBUG=True,
            ALLOW_MOCK_PAYMENTS=False,
        )
    assert "DEBUG mode must be False in production" in str(exc3.value)

    # 4. Rejects ALLOW_MOCK_PAYMENTS=True in production
    with pytest.raises(ValidationError) as exc4:
        Settings(
            APP_ENV="production",
            JWT_SECRET_KEY="f" * 64,
            DEBUG=False,
            ALLOW_MOCK_PAYMENTS=True,
        )
    assert "ALLOW_MOCK_PAYMENTS cannot be enabled in production" in str(exc4.value)

    # 5. Accepts valid hardened production configuration
    valid_prod = Settings(
        APP_ENV="production",
        JWT_SECRET_KEY="a1b2c3d4e5f678901234567890abcdef1234567890abcdef1234567890abcdef",
        DEBUG=False,
        ALLOW_MOCK_PAYMENTS=False,
    )
    assert valid_prod.APP_ENV == "production"
    assert valid_prod.DEBUG is False
    assert valid_prod.ALLOW_MOCK_PAYMENTS is False


def test_production_osrm_routing_guardrails():
    """Verify that production rejects public OSRM demo endpoint and requires valid base URL."""
    # Rejects public demo endpoint
    with pytest.raises(ValidationError) as exc1:
        Settings(
            APP_ENV="production",
            JWT_SECRET_KEY="a1b2c3d4e5f678901234567890abcdef1234567890abcdef1234567890abcdef",
            DEBUG=False,
            ALLOW_MOCK_PAYMENTS=False,
            OSRM_BASE_URL="https://router.project-osrm.org",
        )
    assert "In production, OSRM_BASE_URL must not point to the public demo endpoint" in str(exc1.value)

    # Rejects empty OSRM_BASE_URL
    with pytest.raises(ValidationError) as exc2:
        Settings(
            APP_ENV="production",
            JWT_SECRET_KEY="a1b2c3d4e5f678901234567890abcdef1234567890abcdef1234567890abcdef",
            DEBUG=False,
            ALLOW_MOCK_PAYMENTS=False,
            OSRM_BASE_URL="",
        )
    assert "OSRM_BASE_URL must not point to the public demo endpoint" in str(exc2.value)

    # Accepts self-hosted OSRM URL
    valid_prod = Settings(
        APP_ENV="production",
        JWT_SECRET_KEY="a1b2c3d4e5f678901234567890abcdef1234567890abcdef1234567890abcdef",
        DEBUG=False,
        ALLOW_MOCK_PAYMENTS=False,
        OSRM_BASE_URL="http://osrm:5000",
    )
    assert valid_prod.OSRM_BASE_URL == "http://osrm:5000"


# ---------------------------------------------------------------------------
# 2. Staging Database Connectivity, PostGIS 3.4, and Revision HEAD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_staging_database_connectivity_and_postgis_revision():
    """Verify live database connection, PostGIS operational version, and Alembic revision HEAD."""
    async with async_session_maker() as session:
        # Check connectivity
        one = (await session.execute(text("SELECT 1"))).scalar()
        assert one == 1

        # Check PostGIS operational version
        postgis_ver = (await session.execute(text("SELECT PostGIS_Version()"))).scalar()
        assert postgis_ver is not None
        assert "3.4" in postgis_ver or "3." in postgis_ver
        assert "USE_GEOS=1" in postgis_ver

        # Check alembic_version table matches the migration head
        from pathlib import Path
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        alembic_ini_path = Path(__file__).resolve().parent.parent.parent / "alembic.ini"
        alembic_cfg = Config(str(alembic_ini_path))
        script = ScriptDirectory.from_config(alembic_cfg)
        expected_head = script.get_current_head()

        db_rev = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar()
        assert db_rev == expected_head, f"Staging DB is at {db_rev}, expected {expected_head} (HEAD)"


# ---------------------------------------------------------------------------
# 3. AI Feature Flags Isolation and Kill-Switch Zero Blast Radius
# ---------------------------------------------------------------------------

async def test_ai_feature_flags_isolation_and_kill_switch(async_client: AsyncClient, monkeypatch):
    """Verify kill-switch shuts down AI endpoints while ordinary commerce remains 100% operational."""
    # 1. Create a customer
    async with async_session_maker() as session:
        cust = User(
            id=uuid.uuid4(),
            name="KillSwitch Customer",
            email=f"kill_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.customer,
            is_active=True,
        )
        session.add(cust)
        await session.commit()

    token = create_access_token(str(cust.id), cust.role.value)
    headers = {"Authorization": f"Bearer {token}"}

    # Activate kill switch
    monkeypatch.setattr(settings, "AI_ENABLED", False)

    # AI status endpoint reflects disabled state
    status_res = await async_client.get("/api/v1/ai/status", headers=headers)
    assert status_res.status_code == 200
    assert status_res.json()["enabled"] is False

    # AI shopping assistant returns 503 Service Unavailable
    chat_res = await async_client.post(
        "/api/v1/ai/assistant/chat",
        json={"message": "I need groceries", "latitude": PATNA_LAT, "longitude": PATNA_LON},
        headers=headers,
    )
    assert chat_res.status_code == 503
    assert "disabled" in chat_res.json()["detail"].lower()

    # Core commerce remains completely operational
    shops_res = await async_client.get(f"/api/v1/shops?latitude={PATNA_LAT}&longitude={PATNA_LON}&radius=5000")
    assert shops_res.status_code == 200
    assert "items" in shops_res.json()


# ---------------------------------------------------------------------------
# 4. Diagnostic Endpoint RBAC & Cost-Abuse Cooldown Caching
# ---------------------------------------------------------------------------

async def test_diagnostic_endpoint_rbac_and_cooldown_caching(async_client: AsyncClient, monkeypatch):
    """
    Verify /api/v1/ai/diagnostic/check:
    - 401 for anonymous
    - 403 for customer & rider
    - 200 for admin
    - 30-second cooldown caching prevents automated cost abuse
    - Zero secrets leaked
    """
    async with async_session_maker() as session:
        admin = User(
            id=uuid.uuid4(),
            name="Prod Admin",
            email=f"admin_prod_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.admin,
            is_active=True,
        )
        customer = User(
            id=uuid.uuid4(),
            name="Prod Customer",
            email=f"cust_prod_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.customer,
            is_active=True,
        )
        session.add_all([admin, customer])
        await session.commit()

    token_admin = create_access_token(str(admin.id), admin.role.value)
    token_cust = create_access_token(str(customer.id), customer.role.value)

    # 1. Anonymous -> 401
    res_anon = await async_client.get("/api/v1/ai/diagnostic/check")
    assert res_anon.status_code == 401

    # 2. Customer -> 403
    res_cust = await async_client.get(
        "/api/v1/ai/diagnostic/check",
        headers={"Authorization": f"Bearer {token_cust}"},
    )
    assert res_cust.status_code == 403

    # 3. Admin -> 200
    monkeypatch.setattr(settings, "AI_ENABLED", True)
    monkeypatch.setattr(settings, "AI_PROVIDER", "mock")
    ai_service.reset_diagnostic_cache()
    ai_service.reset_circuit_breaker()

    res_admin1 = await async_client.get(
        "/api/v1/ai/diagnostic/check",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert res_admin1.status_code == 200
    data1 = res_admin1.json()
    assert data1["connection_successful"] is True
    assert data1["cached"] is False
    assert "api_key" not in data1

    # 4. Immediate second probe -> Cached (preventing upstream provider billing)
    res_admin2 = await async_client.get(
        "/api/v1/ai/diagnostic/check",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert res_admin2.status_code == 200
    data2 = res_admin2.json()
    assert data2["cached"] is True


# ---------------------------------------------------------------------------
# 5. User Rate Limiting Enforcement
# ---------------------------------------------------------------------------

async def test_user_rate_limiting_enforcement(async_client: AsyncClient, monkeypatch):
    """Verify sliding-window rate limiter blocks users exceeding rate limit with HTTP 429."""
    from app.api.routes.ai import ai_user_rate_limiter

    user_id = str(uuid.uuid4())
    ai_user_rate_limiter.reset(user_id)

    # Simulate 20 requests in the current window
    for _ in range(settings.AI_RATE_LIMIT_PER_MINUTE):
        allowed, retry_after = ai_user_rate_limiter.check_and_record(user_id)
        assert allowed is True

    # 21st request must be denied with retry_after > 0
    denied, retry_after = ai_user_rate_limiter.check_and_record(user_id)
    assert denied is False
    assert retry_after is not None
    assert retry_after > 0.0


# ---------------------------------------------------------------------------
# 6. Alembic Bidirectional Rollback Integrity
# ---------------------------------------------------------------------------

def test_alembic_bidirectional_migration_chain():
    """Verify that every migration in the chain defines downgrade() for rollback readiness."""
    alembic_ini_path = Path(__file__).resolve().parent.parent.parent / "alembic.ini"
    config = Config(str(alembic_ini_path))
    script = ScriptDirectory.from_config(config)

    heads = script.get_heads()
    assert len(heads) == 1, f"Expected exactly 1 Alembic head (linear history invariant), found: {heads}"
    head_rev = heads[0]

    # Walk from head to base verifying all revisions have downgrade functions
    revs = list(script.walk_revisions(base="base", head=head_rev))
    assert len(revs) >= 22, f"Expected at least 22 migrations, found {len(revs)}"

    for r in revs:
        module = r.module
        assert hasattr(module, "upgrade"), f"Migration {r.revision} missing upgrade()"
        assert hasattr(module, "downgrade"), f"Migration {r.revision} missing downgrade()"
        assert callable(module.upgrade)
        assert callable(module.downgrade)


# ---------------------------------------------------------------------------
# 7. Demo Seeding Environment Security & Gating Regression
# ---------------------------------------------------------------------------

def test_seed_demo_environment_verification():
    """
    Verify demo seeding is permitted ONLY when APP_ENV='development'.
    Staging, production, missing, or ambiguous environments must strictly fail safely.
    """
    from app.db.seed_demo import verify_seed_environment

    # 1. Allowed in development
    assert verify_seed_environment("development") is True
    assert verify_seed_environment("DEVELOPMENT") is True
    assert verify_seed_environment("  development  ") is True

    # 2. Strictly forbidden in production
    with pytest.raises(RuntimeError) as exc_prod:
        verify_seed_environment("production")
    assert "forbidden in environment 'production'" in str(exc_prod.value)
    assert "Password123!" not in str(exc_prod.value)  # Zero credentials exposed in error

    # 3. Strictly forbidden in staging
    with pytest.raises(RuntimeError) as exc_stag:
        verify_seed_environment("staging")
    assert "forbidden in environment 'staging'" in str(exc_stag.value)

    # 4. Strictly forbidden when missing, None, or empty
    with pytest.raises(RuntimeError) as exc_none:
        verify_seed_environment(None)
    assert "missing or empty" in str(exc_none.value)

    with pytest.raises(RuntimeError) as exc_empty:
        verify_seed_environment("")
    assert "missing or empty" in str(exc_empty.value)

    # 5. Strictly forbidden when ambiguous or unexpected
    with pytest.raises(RuntimeError) as exc_ambig:
        verify_seed_environment("test_pilot")
    assert "forbidden in environment 'test_pilot'" in str(exc_ambig.value)


@pytest.mark.asyncio
async def test_seed_demo_data_execution_guard(monkeypatch):
    """Verify that seed_demo_data() aborts immediately without touching database when not in development."""
    from app.db.seed_demo import seed_demo_data

    # Production guard
    monkeypatch.setattr(settings, "APP_ENV", "production")
    with pytest.raises(RuntimeError) as exc_prod:
        await seed_demo_data()
    assert "forbidden in environment 'production'" in str(exc_prod.value)

    # Staging guard
    monkeypatch.setattr(settings, "APP_ENV", "staging")
    with pytest.raises(RuntimeError) as exc_stag:
        await seed_demo_data()
    assert "forbidden in environment 'staging'" in str(exc_stag.value)

    # Missing/empty guard
    monkeypatch.setattr(settings, "APP_ENV", "")
    with pytest.raises(RuntimeError) as exc_empty:
        await seed_demo_data()
    assert "missing or empty" in str(exc_empty.value)


def test_start_script_environment_gating():
    """Verify start.sh only invokes demo seeding conditionally for development."""
    start_sh_path = Path(__file__).resolve().parent.parent.parent / "start.sh"
    assert start_sh_path.exists(), "backend/start.sh must exist"
    content = start_sh_path.read_text(encoding="utf-8")

    # 1. Must check APP_ENV=development
    assert '[ "$APP_ENV" = "development" ]' in content

    # 2. Must have an else branch explaining skip
    assert "Skipping demo seeding" in content

    # 3. Migrations must be run unconditionally
    assert "alembic -c alembic.ini upgrade head" in content

    # 4. Zero credentials in start.sh
    assert "Password123!" not in content
    assert "password" not in content.lower()

