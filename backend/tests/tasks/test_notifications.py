import pytest
import uuid
from sqlalchemy import select
from app.tasks.notifications import create_notification
from app.models.notification import Notification
from app.core.celery_app import celery_app
from httpx import AsyncClient

# Make celery run tasks synchronously in tests
celery_app.conf.update(task_always_eager=True)

import nest_asyncio
nest_asyncio.apply()

from app.db.session import get_db

@pytest.mark.asyncio
async def test_create_notification_task(async_client: AsyncClient):
    # Register a user to get a valid user_id
    email = f"user_{uuid.uuid4()}@example.com"
    await async_client.post("/api/v1/auth/register", json={"name": "Test User", "email": email, "password": "PassWord123"})
    
    # Get user_id from DB
    from app.models.user import User
    from sqlalchemy import text
    async for db in get_db():
        stmt = select(User).where(User.email == email)
        user = (await db.execute(stmt)).scalar_one_or_none()
        user_id = str(user.id)
        break

    # Call the task (runs synchronously because task_always_eager=True)
    ref_id = str(uuid.uuid4())
    result = create_notification.delay(
        user_id=user_id,
        title="Test Notification",
        body="This is a test.",
        notification_type="TEST_TYPE",
        reference_id=ref_id
    )
    
    notif_id = result.get()
    assert notif_id is not None
    
    # Verify in DB
    async for db in get_db():
        stmt = select(Notification).where(Notification.id == uuid.UUID(notif_id))
        notif = (await db.execute(stmt)).scalar_one_or_none()
        assert notif is not None
        assert notif.title == "Test Notification"
        assert notif.type == "TEST_TYPE"
        assert notif.reference_id == ref_id
        
        # Call again to test idempotency
        result2 = create_notification.delay(
            user_id=user_id,
            title="Test Notification Diff",
            body="Diff body.",
            notification_type="TEST_TYPE",
            reference_id=ref_id
        )
        notif_id2 = result2.get()
        assert notif_id2 == notif_id  # Should return the same ID
        break
