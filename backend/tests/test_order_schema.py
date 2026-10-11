import uuid
from datetime import datetime, timezone
from decimal import Decimal
from app.models.order import OrderStatus
from app.models.delivery import DeliveryStatus
from app.schemas.order import OrderResponse, OrderDeliverySummary, OrderItemResponse

def test_order_response_without_delivery():
    order_id = uuid.uuid4()
    cust_id = uuid.uuid4()
    shop_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    order = OrderResponse(
        id=order_id,
        customer_id=cust_id,
        shop_id=shop_id,
        status=OrderStatus.pending,
        total_amount=Decimal("150.00"),
        items=[],
        created_at=now,
        updated_at=now,
        delivery=None
    )

    data = order.model_dump()
    assert data["id"] == order_id
    assert data["delivery"] is None

def test_order_response_with_delivery_summary():
    order_id = uuid.uuid4()
    cust_id = uuid.uuid4()
    shop_id = uuid.uuid4()
    delivery_id = uuid.uuid4()
    rider_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    delivery_summary = OrderDeliverySummary(
        id=delivery_id,
        status=DeliveryStatus.assigned,
        rider_id=rider_id,
        assigned_at=now,
        picked_up_at=None,
        delivered_at=None
    )

    order = OrderResponse(
        id=order_id,
        customer_id=cust_id,
        shop_id=shop_id,
        status=OrderStatus.confirmed,
        total_amount=Decimal("250.00"),
        items=[
            OrderItemResponse(
                id=uuid.uuid4(),
                product_id=uuid.uuid4(),
                product_name="Product A",
                unit_price=Decimal("250.00"),
                quantity=1,
                line_total=Decimal("250.00")
            )
        ],
        created_at=now,
        updated_at=now,
        delivery=delivery_summary
    )

    data = order.model_dump()
    assert data["id"] == order_id
    assert data["delivery"] is not None
    assert data["delivery"]["id"] == delivery_id
    assert data["delivery"]["status"] == DeliveryStatus.assigned
    assert data["delivery"]["rider_id"] == rider_id
    assert data["delivery"]["assigned_at"] == now
