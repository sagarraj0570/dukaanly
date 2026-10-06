from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings

# Engine created without full sessionmaker since models aren't needed yet
engine = create_async_engine(settings.database_url, echo=settings.DEBUG)

async def check_db_connection() -> bool:
    """Check if the database is reachable."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
