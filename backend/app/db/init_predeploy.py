"""Pre-deploy database initialization and PostGIS validation script.

Executes during the cloud PaaS release phase before Alembic migrations run.
Validates:
1. Database connectivity.
2. Availability of the PostGIS extension in the PostgreSQL distribution.
3. Automatically creates/enables the PostGIS extension if not already active.
4. Verifies PostGIS operational readiness via PostGIS_Version().
"""

import asyncio
import logging
import sys
from sqlalchemy import text
from app.db.session import engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("init_predeploy")


async def init_predeploy() -> None:
    logger.info("Starting Dukaanly pre-deploy database and PostGIS validation...")
    try:
        async with engine.connect() as conn:
            # 1. Verify basic database connectivity
            await conn.execute(text("SELECT 1"))
            logger.info("Database connection established successfully.")

            # 2. Check if PostGIS extension is available in PostgreSQL catalog
            result = await conn.execute(
                text(
                    "SELECT name, default_version, installed_version "
                    "FROM pg_available_extensions WHERE name = 'postgis'"
                )
            )
            row = result.mappings().fetchone()
            if not row:
                logger.error(
                    "FATAL: PostGIS extension binary is not available on this PostgreSQL server. "
                    "Ensure your cloud database plan supports PostGIS (e.g., PostgreSQL 16 on Render)."
                )
                sys.exit(1)

            logger.info(
                "PostGIS extension available in catalog (default_version: %s, installed_version: %s)",
                row.get("default_version"),
                row.get("installed_version"),
            )

            # 3. Create extension if not already present
            logger.info("Ensuring PostGIS extension is active...")
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            await conn.commit()

            # 4. Verify PostGIS operational readiness
            version_result = await conn.execute(text("SELECT PostGIS_Version();"))
            version = version_result.scalar()
            logger.info("PostGIS operational check passed. Active version: %s", version)

        logger.info("Pre-deploy database initialization completed successfully.")
    except Exception as exc:
        logger.exception("Pre-deploy initialization failed: %s", exc)
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_predeploy())
