import pytest
import uuid
from unittest.mock import MagicMock
from app.models.user import UserRole
from app.api.routes.ws_deliveries import authorize_delivery_ws

pytestmark = pytest.mark.asyncio

async def test_authorize_delivery_ws_customer():
    cust_id = uuid.uuid4()
    other_cust_id = uuid.uuid4()

    user = MagicMock()
    user.id = cust_id
    user.role = MagicMock()
    user.role.value = "customer"

    delivery = MagicMock()
    delivery.order = MagicMock()
    delivery.order.customer_id = cust_id

    # Authorized customer
    assert await authorize_delivery_ws(user, delivery) is True

    # Unauthorized customer
    other_user = MagicMock()
    other_user.id = other_cust_id
    other_user.role = MagicMock()
    other_user.role.value = "customer"

    assert await authorize_delivery_ws(other_user, delivery) is False

async def test_authorize_delivery_ws_rider():
    rider_user_id = uuid.uuid4()
    other_rider_user_id = uuid.uuid4()

    user = MagicMock()
    user.id = rider_user_id
    user.role = MagicMock()
    user.role.value = "rider"

    delivery = MagicMock()
    delivery.rider = MagicMock()
    delivery.rider.user_id = rider_user_id

    # Assigned rider
    assert await authorize_delivery_ws(user, delivery) is True

    # Other rider
    other_user = MagicMock()
    other_user.id = other_rider_user_id
    other_user.role = MagicMock()
    other_user.role.value = "rider"

    assert await authorize_delivery_ws(other_user, delivery) is False

    # Delivery without assigned rider
    delivery_unassigned = MagicMock()
    delivery_unassigned.rider = None
    assert await authorize_delivery_ws(user, delivery_unassigned) is False

async def test_authorize_delivery_ws_shop_owner_and_admin():
    owner_id = uuid.uuid4()
    other_owner_id = uuid.uuid4()

    user_owner = MagicMock()
    user_owner.id = owner_id
    user_owner.role = MagicMock()
    user_owner.role.value = "shop_owner"

    delivery = MagicMock()
    delivery.order = MagicMock()
    delivery.order.shop = MagicMock()
    delivery.order.shop.owner_id = owner_id

    # Authorized shop owner
    assert await authorize_delivery_ws(user_owner, delivery) is True

    # Unauthorized shop owner
    other_owner = MagicMock()
    other_owner.id = other_owner_id
    other_owner.role = MagicMock()
    other_owner.role.value = "shop_owner"
    assert await authorize_delivery_ws(other_owner, delivery) is False

    # Admin
    admin_user = MagicMock()
    admin_user.role = MagicMock()
    admin_user.role.value = "admin"
    assert await authorize_delivery_ws(admin_user, delivery) is True
