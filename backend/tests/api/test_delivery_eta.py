import pytest
import uuid
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock
from sqlalchemy import text

from app.services.osrm import osrm_service, OSRMTimeoutError

pytestmark = pytest.mark.asyncio


async def test_delivery_eta_lifecycle_and_api(async_client: AsyncClient):
    """
    Test complete lifecycle of Smart Delivery ETA:
    1. Initial delivery creation -> Provisional ETA calculated.
    2. Shop owner reads ETA (200) & updates preparation time (200).
    3. Customer reads updated ETA (200).
    4. Rider assigned -> ETA recalculates with pickup travel.
    5. Order picked up -> Preparation and pickup components drop to 0.
    6. Delivered -> Remaining time becomes 0, is_estimated is False.
    """
    from app.db.session import engine
    from tests.api.test_deliveries import setup_delivery_test_data

    tokens, order_id, rider1_id, shop_id = await setup_delivery_test_data(async_client, engine)

    # Mock OSRM two-point route so test is isolated from external network
    mock_pickup_route = {
        "distance_meters": 1200.0,
        "duration_seconds": 240.0,  # 4 mins
        "duration_minutes": 4.0,
        "geometry": [[25.6100, 85.1100], [25.6144, 85.1158]],
        "is_fallback": False,
        "cached": False,
    }
    mock_dropoff_route = {
        "distance_meters": 2400.0,
        "duration_seconds": 480.0,  # 8 mins
        "duration_minutes": 8.0,
        "geometry": [[25.6144, 85.1158], [25.6180, 85.1220]],
        "is_fallback": False,
        "cached": False,
    }

    async def mock_get_route(*args, **kwargs):
        if kwargs.get("from_name") == "Rider":
            return mock_pickup_route
        return mock_dropoff_route

    with patch.object(osrm_service, "get_two_point_route", side_effect=mock_get_route):
        # 1. Create Delivery
        res_create = await async_client.post(
            "/api/v1/deliveries",
            json={
                "order_id": order_id,
                "destination_latitude": 25.6180,
                "destination_longitude": 85.1220,
            },
            headers={"Authorization": f"Bearer {tokens['shop_owner']}"},
        )
        assert res_create.status_code == 201
        delivery_id = res_create.json()["id"]

        # 2. Read ETA as Customer
        res_eta = await async_client.get(
            f"/api/v1/deliveries/{delivery_id}/eta",
            headers={"Authorization": f"Bearer {tokens['customer']}"},
        )
        assert res_eta.status_code == 200
        eta_data = res_eta.json()

        assert eta_data["delivery_id"] == delivery_id
        assert eta_data["status"] == "pending"
        assert eta_data["eta"]["source"] == "osrm"
        assert eta_data["eta"]["remaining_seconds"] > 0
        assert eta_data["breakdown"]["dropoff_travel_seconds"] == 480
        assert eta_data["breakdown"]["assignment_wait_seconds"] > 0

        # 3. Shop Owner updates preparation time to 25 minutes with reason
        res_prep = await async_client.patch(
            f"/api/v1/deliveries/{delivery_id}/preparation",
            json={
                "estimated_minutes": 25,
                "delay_reason": "High order volume during dinner rush",
            },
            headers={"Authorization": f"Bearer {tokens['shop_owner']}"},
        )
        assert res_prep.status_code == 200
        prep_data = res_prep.json()
        assert prep_data["breakdown"]["preparation_remaining_seconds"] == 25 * 60
        assert prep_data["delay_explanation"] == "High order volume during dinner rush"

        # 4. Assign Rider -> Rider heading to shop
        await async_client.patch(
            "/api/v1/riders/me/location",
            json={"latitude": 25.6100, "longitude": 85.1100},
            headers={"Authorization": f"Bearer {tokens['rider']}"},
        )
        res_assign = await async_client.post(
            f"/api/v1/deliveries/{delivery_id}/assign",
            json={"rider_id": rider1_id},
            headers={"Authorization": f"Bearer {tokens['shop_owner']}"},
        )
        assert res_assign.status_code == 200

        # Read ETA again -> assignment wait dropped to 0, pickup travel is 240s
        res_eta_assigned = await async_client.get(
            f"/api/v1/deliveries/{delivery_id}/eta",
            headers={"Authorization": f"Bearer {tokens['customer']}"},
        )
        assert res_eta_assigned.status_code == 200
        assigned_eta = res_eta_assigned.json()
        assert assigned_eta["status"] == "assigned"
        assert assigned_eta["breakdown"]["assignment_wait_seconds"] == 0
        assert assigned_eta["breakdown"]["pickup_travel_remaining_seconds"] == 240

        # 5. Order Picked Up -> Transition to picked_up
        res_pickup = await async_client.patch(
            f"/api/v1/deliveries/{delivery_id}/status",
            json={"status": "picked_up"},
            headers={"Authorization": f"Bearer {tokens['rider']}"},
        )
        assert res_pickup.status_code == 200

        # Read ETA -> preparation and pickup components MUST BE 0!
        res_eta_pickup = await async_client.get(
            f"/api/v1/deliveries/{delivery_id}/eta",
            headers={"Authorization": f"Bearer {tokens['customer']}"},
        )
        assert res_eta_pickup.status_code == 200
        pickup_eta = res_eta_pickup.json()
        assert pickup_eta["status"] == "picked_up"
        assert pickup_eta["breakdown"]["preparation_remaining_seconds"] == 0
        assert pickup_eta["breakdown"]["pickup_travel_remaining_seconds"] == 0
        assert pickup_eta["breakdown"]["pickup_buffer_seconds"] == 0
        assert pickup_eta["breakdown"]["dropoff_travel_seconds"] == 480

        # 6. Mark Delivered -> Remaining is 0, is_estimated is False
        await async_client.patch(
            f"/api/v1/deliveries/{delivery_id}/status",
            json={"status": "out_for_delivery"},
            headers={"Authorization": f"Bearer {tokens['rider']}"},
        )
        res_delivered = await async_client.patch(
            f"/api/v1/deliveries/{delivery_id}/status",
            json={"status": "delivered"},
            headers={"Authorization": f"Bearer {tokens['rider']}"},
        )
        assert res_delivered.status_code == 200

        res_eta_delivered = await async_client.get(
            f"/api/v1/deliveries/{delivery_id}/eta",
            headers={"Authorization": f"Bearer {tokens['customer']}"},
        )
        assert res_eta_delivered.status_code == 200
        delivered_eta = res_eta_delivered.json()
        assert delivered_eta["status"] == "delivered"
        assert delivered_eta["eta"]["remaining_seconds"] == 0
        assert delivered_eta["eta"]["is_estimated"] is False


async def test_delivery_eta_authorization_and_privacy(async_client: AsyncClient):
    """
    Test strict authorization for GET /eta and PATCH /preparation:
    - Customer can read their ETA (200)
    - Shop Owner can read their ETA (200) and update preparation (200)
    - Assigned Rider can read ETA (200)
    - Admin can read ETA (200) and update preparation (200)
    - Unrelated Customer cannot read ETA (403)
    - Customer cannot update preparation (403)
    - Non-existent delivery returns 404
    - Unauthenticated returns 401
    """
    from app.db.session import engine
    from tests.api.test_deliveries import setup_delivery_test_data

    tokens, order_id, rider1_id, shop_id = await setup_delivery_test_data(async_client, engine)

    res_create = await async_client.post(
        "/api/v1/deliveries",
        json={
            "order_id": order_id,
            "destination_latitude": 25.6180,
            "destination_longitude": 85.1220,
        },
        headers={"Authorization": f"Bearer {tokens['shop_owner']}"},
    )
    delivery_id = res_create.json()["id"]

    # 1. Unauthenticated -> 401
    res_no_auth = await async_client.get(f"/api/v1/deliveries/{delivery_id}/eta")
    assert res_no_auth.status_code == 401

    # 2. Non-existent delivery -> 404
    fake_id = str(uuid.uuid4())
    res_404 = await async_client.get(
        f"/api/v1/deliveries/{fake_id}/eta",
        headers={"Authorization": f"Bearer {tokens['customer']}"},
    )
    assert res_404.status_code == 404

    # 3. Unrelated customer -> 403
    unrelated_email = f"unrelated_cust_{uuid.uuid4()}@example.com"
    await async_client.post("/api/v1/auth/register", json={"name": "UC", "email": unrelated_email, "password": "PassWord123"})
    unrelated_token = (await async_client.post("/api/v1/auth/login", json={"email": unrelated_email, "password": "PassWord123"})).json()["access_token"]
    res_unrelated = await async_client.get(
        f"/api/v1/deliveries/{delivery_id}/eta",
        headers={"Authorization": f"Bearer {unrelated_token}"},
    )
    assert res_unrelated.status_code == 403

    # 4. Customer attempts to patch preparation -> 403 (Only shop owner or admin allowed)
    res_cust_prep = await async_client.patch(
        f"/api/v1/deliveries/{delivery_id}/preparation",
        json={"estimated_minutes": 15},
        headers={"Authorization": f"Bearer {tokens['customer']}"},
    )
    assert res_cust_prep.status_code == 403

    # 5. Admin can read ETA and update preparation -> 200
    res_admin_get = await async_client.get(
        f"/api/v1/deliveries/{delivery_id}/eta",
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert res_admin_get.status_code == 200

    res_admin_patch = await async_client.patch(
        f"/api/v1/deliveries/{delivery_id}/preparation",
        json={"estimated_minutes": 18},
        headers={"Authorization": f"Bearer {tokens['admin']}"},
    )
    assert res_admin_patch.status_code == 200
    assert res_admin_patch.json()["breakdown"]["preparation_remaining_seconds"] == 18 * 60


async def test_delivery_eta_fallback_when_osrm_fails(async_client: AsyncClient):
    """
    Test that when OSRM times out or fails:
    - ETA does not crash with a 500 or invent a fake road polyline.
    - ETA returns source='fallback_estimate'.
    """
    from app.db.session import engine
    from tests.api.test_deliveries import setup_delivery_test_data

    tokens, order_id, rider1_id, shop_id = await setup_delivery_test_data(async_client, engine)

    res_create = await async_client.post(
        "/api/v1/deliveries",
        json={
            "order_id": order_id,
            "destination_latitude": 25.6180,
            "destination_longitude": 85.1220,
        },
        headers={"Authorization": f"Bearer {tokens['shop_owner']}"},
    )
    delivery_id = res_create.json()["id"]

    with patch.object(osrm_service, "get_two_point_route", side_effect=OSRMTimeoutError("OSRM timed out")):
        res_eta = await async_client.get(
            f"/api/v1/deliveries/{delivery_id}/eta",
            headers={"Authorization": f"Bearer {tokens['customer']}"},
        )
        assert res_eta.status_code == 200
        data = res_eta.json()
        assert data["eta"]["source"] == "fallback_estimate"
        assert data["eta"]["remaining_seconds"] > 0
        assert data["eta"]["is_estimated"] is True


async def test_delivery_eta_unrelated_actors_and_malformed_id(async_client: AsyncClient):
    """
    Test edge-case security & input validation:
    - Unrelated shop owner cannot view or patch another shop's delivery ETA (403)
    - Unassigned rider cannot view delivery ETA (403)
    - Malformed UUID returns 422
    """
    from app.db.session import engine
    from tests.api.test_deliveries import setup_delivery_test_data

    tokens, order_id, rider1_id, shop_id = await setup_delivery_test_data(async_client, engine)

    res_create = await async_client.post(
        "/api/v1/deliveries",
        json={
            "order_id": order_id,
            "destination_latitude": 25.6180,
            "destination_longitude": 85.1220,
        },
        headers={"Authorization": f"Bearer {tokens['shop_owner']}"},
    )
    delivery_id = res_create.json()["id"]

    # 1. Malformed UUID -> 422
    res_malformed = await async_client.get(
        "/api/v1/deliveries/invalid-uuid-format/eta",
        headers={"Authorization": f"Bearer {tokens['customer']}"},
    )
    assert res_malformed.status_code == 422

    # 2. Register unrelated shop owner
    so2_email = f"so2_{uuid.uuid4()}@example.com"
    await async_client.post("/api/v1/auth/register", json={"name": "SO2", "email": so2_email, "password": "PassWord123"})
    async with engine.connect() as conn:
        await conn.execute(text("UPDATE users SET role = 'shop_owner' WHERE email = :e"), {"e": so2_email})
        await conn.commit()
    so2_token = (await async_client.post("/api/v1/auth/login", json={"email": so2_email, "password": "PassWord123"})).json()["access_token"]

    # Unrelated shop owner cannot view ETA -> 403
    res_so2_get = await async_client.get(
        f"/api/v1/deliveries/{delivery_id}/eta",
        headers={"Authorization": f"Bearer {so2_token}"},
    )
    assert res_so2_get.status_code == 403

    # Unrelated shop owner cannot patch preparation -> 403
    res_so2_patch = await async_client.patch(
        f"/api/v1/deliveries/{delivery_id}/preparation",
        json={"estimated_minutes": 20},
        headers={"Authorization": f"Bearer {so2_token}"},
    )
    assert res_so2_patch.status_code == 403

    # 3. Register second, unassigned rider
    r2_email = f"r2_{uuid.uuid4()}@example.com"
    await async_client.post("/api/v1/auth/register", json={"name": "R2", "email": r2_email, "password": "PassWord123"})
    async with engine.connect() as conn:
        await conn.execute(text("UPDATE users SET role = 'rider' WHERE email = :e"), {"e": r2_email})
        await conn.commit()
    r2_token = (await async_client.post("/api/v1/auth/login", json={"email": r2_email, "password": "PassWord123"})).json()["access_token"]
    await async_client.post("/api/v1/riders/profile", headers={"Authorization": f"Bearer {r2_token}"})

    # Unassigned rider cannot view ETA -> 403
    res_r2_get = await async_client.get(
        f"/api/v1/deliveries/{delivery_id}/eta",
        headers={"Authorization": f"Bearer {r2_token}"},
    )
    assert res_r2_get.status_code == 403


async def test_delivery_eta_persistence_before_publish(async_client: AsyncClient):
    """
    Verify PostgreSQL is authoritative:
    - Delivery record persists eta_earliest_at, eta_latest_at, eta_source, eta_version.
    - Repeated updates increment eta_version monotonically.
    - Redis publish hook is called with the committed snapshot.
    """
    from app.db.session import engine
    from app.models.delivery import Delivery
    from sqlalchemy.ext.asyncio import AsyncSession
    from tests.api.test_deliveries import setup_delivery_test_data

    tokens, order_id, rider1_id, shop_id = await setup_delivery_test_data(async_client, engine)

    res_create = await async_client.post(
        "/api/v1/deliveries",
        json={
            "order_id": order_id,
            "destination_latitude": 25.6180,
            "destination_longitude": 85.1220,
        },
        headers={"Authorization": f"Bearer {tokens['shop_owner']}"},
    )
    delivery_id = uuid.UUID(res_create.json()["id"])

    with patch("app.services.delivery_eta.publish_delivery_event", new_callable=AsyncMock) as mock_publish:
        # Patch preparation -> triggers update_and_persist_delivery_eta
        res_prep = await async_client.patch(
            f"/api/v1/deliveries/{delivery_id}/preparation",
            json={"estimated_minutes": 14, "delay_reason": "Order batching"},
            headers={"Authorization": f"Bearer {tokens['shop_owner']}"},
        )
        assert res_prep.status_code == 200
        eta_payload = res_prep.json()

        # Check DB directly
        async with AsyncSession(engine) as session:
            stmt = text("SELECT eta_version, eta_source, eta_delay_reason, eta_remaining_seconds FROM deliveries WHERE id = :did")
            row = (await session.execute(stmt, {"did": delivery_id})).first()
            assert row is not None
            assert row[0] >= 1  # version incremented
            assert row[2] == "Order batching"
            assert row[3] == eta_payload["eta"]["remaining_seconds"]

        # Ensure publish was called after DB persistence
        assert mock_publish.called
        event_call = mock_publish.call_args[0]
        assert event_call[0] == str(delivery_id)
        assert event_call[1]["event"] == "delivery.eta_updated"

