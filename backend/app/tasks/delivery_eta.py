import asyncio
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool

from app.core.celery_app import celery_app
from app.core.config import settings
from app.models.delivery import Delivery, DeliveryStatus

logger = logging.getLogger(__name__)


async def _reconcile_active_deliveries_eta_async() -> int:
    """Finds active deliveries with stale ETAs and refreshes their snapshot."""
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        future=True,
        poolclass=NullPool,
    )
    AsyncSessionMaker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )

    refreshed_count = 0
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.ETA_MAX_SNAPSHOT_AGE_SECONDS)

    try:
        async with AsyncSessionMaker() as session:
            stmt = select(Delivery.id).where(
                Delivery.status.in_([
                    DeliveryStatus.pending,
                    DeliveryStatus.assigned,
                    DeliveryStatus.picked_up,
                    DeliveryStatus.out_for_delivery,
                ]),
                (Delivery.eta_calculated_at == None) | (Delivery.eta_calculated_at < cutoff),
            ).limit(20)

            result = await session.execute(stmt)
            delivery_ids = result.scalars().all()

            logger.info(f"Starting ETA reconciliation: found {len(delivery_ids)} stale active deliveries")
            from app.services.delivery_eta import eta_service
            for d_id in delivery_ids:
                try:
                    await eta_service.update_and_persist_delivery_eta(
                        session, d_id, update_reason="periodic_reconciliation", force=True
                    )
                    refreshed_count += 1
                except Exception as e:
                    logger.warning(f"Error during ETA reconciliation for delivery {d_id}: {e}", exc_info=True)
            logger.info(f"Completed ETA reconciliation: {refreshed_count}/{len(delivery_ids)} refreshed successfully")

    finally:
        await engine.dispose()

    return refreshed_count


from sqlalchemy.exc import DBAPIError, OperationalError
from celery.exceptions import SoftTimeLimitExceeded

def _run_sync(coro):
    """Executes a coroutine synchronously, safely handling environments with or without a running event loop."""
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                return executor.submit(asyncio.run, coro).result()
        return asyncio.run(coro)
    except SoftTimeLimitExceeded:
        logger.warning("ETA reconciliation reached soft time limit. Exiting cleanly.")
        return 0


@celery_app.task(
    bind=True,
    name="reconcile_active_deliveries_eta",
    autoretry_for=(OperationalError, DBAPIError),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
)
def reconcile_active_deliveries_eta(self) -> int:
    """Celery task to periodically refresh active delivery ETAs with idempotency and retry backoff."""
    return _run_sync(_reconcile_active_deliveries_eta_async())
