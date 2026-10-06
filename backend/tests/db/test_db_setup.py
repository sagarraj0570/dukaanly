import pytest
from sqlalchemy import text
from app.db.session import engine, get_db

pytestmark = pytest.mark.asyncio

@pytest.fixture(autouse=True)
async def cleanup_engine():
    yield
    await engine.dispose()

async def test_sqlalchemy_engine_connection():
    """Verify that the async engine can connect and execute a simple query."""
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1

async def test_session_dependency():
    """Verify that the FastAPI get_db dependency yields a working session."""
    async for session in get_db():
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1
        break  # We only need to verify the first yield
