import asyncio
import uuid
import logging
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from app.core.celery_app import celery_app
from app.core.config import settings
from app.models.notification import Notification

logger = logging.getLogger(__name__)

async def _create_notification_async(user_id: str, title: str, body: str, notification_type: str, reference_id: Optional[str] = None, data: Optional[dict] = None) -> str:
    """Async actual implementation of notification creation with idempotency check."""
    
    # Create engine inside the coroutine to tie it strictly to the current event loop
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        future=True,
        poolclass=NullPool,  # No connection pooling; safe for transient worker tasks
    )
    AsyncSessionMaker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    
    try:
        async with AsyncSessionMaker() as session:
            # Idempotency check
            if reference_id and notification_type:
                stmt = select(Notification).where(
                    Notification.user_id == uuid.UUID(user_id),
                    Notification.type == notification_type,
                    Notification.reference_id == reference_id
                )
                result = await session.execute(stmt)
                existing = result.scalars().first()
                if existing:
                    logger.info(f"Notification {notification_type} for reference {reference_id} already exists for user {user_id}. Skipping.")
                    return str(existing.id)

            notification = Notification(
                user_id=uuid.UUID(user_id),
                title=title,
                body=body,
                type=notification_type,
                reference_id=reference_id,
                data=data
            )
            session.add(notification)
            await session.commit()
            await session.refresh(notification)
            logger.info(f"Created notification {notification.id} for user {user_id}")
            return str(notification.id)
    finally:
        await engine.dispose()


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=5,
    name="app.tasks.notifications.create_notification"
)
def create_notification(self, user_id: str, title: str, body: str, notification_type: str, reference_id: Optional[str] = None, data: Optional[dict] = None):
    """
    Creates an in-app notification in the database.
    Uses exponential backoff for retries.
    """
    try:
        # Run the async DB logic synchronously in the Celery worker
        # By creating and disposing the engine within the coroutine, we are completely event-loop safe.
        return asyncio.run(
            _create_notification_async(user_id, title, body, notification_type, reference_id, data)
        )
    except Exception as exc:
        logger.error(f"Error creating notification: {exc}")
        raise
