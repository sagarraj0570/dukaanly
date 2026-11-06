"""
Centralized inventory reservation service.
Guarantees durable PostgreSQL reservations, deterministic row locking,
and exactly-once inventory restoration.
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Sequence, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from fastapi import HTTPException, status

from app.models.inventory_reservation import InventoryReservation, ReservationStatus
from app.models.inventory import Inventory
from app.models.order import Order
from app.core.config import settings

logger = logging.getLogger(__name__)


async def create_order_reservations(
    db: AsyncSession,
    order: Order,
    items: Sequence[dict],
    customer_id: uuid.UUID,
    ttl_seconds: Optional[int] = None,
) -> list[InventoryReservation]:
    """
    Creates durable inventory reservations for an order.
    Assumes caller holds locks and decrements Inventory.stock in the same transaction.
    """
    ttl = ttl_seconds if ttl_seconds is not None else settings.INVENTORY_RESERVATION_TTL_SECONDS
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=ttl)

    reservations: list[InventoryReservation] = []
    for item in items:
        product_id = item["product_id"] if isinstance(item, dict) else item.product_id
        quantity = item["quantity"] if isinstance(item, dict) else item.quantity

        ref_id = f"res_{uuid.uuid4().hex[:16]}"
        res = InventoryReservation(
            reservation_reference=ref_id,
            order_id=order.id,
            product_id=product_id,
            customer_id=customer_id,
            quantity=quantity,
            status=ReservationStatus.active,
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
            version=1,
        )
        db.add(res)
        reservations.append(res)

    logger.info(
        "inventory.reservations_created",
        extra={
            "order_id": str(order.id),
            "customer_id": str(customer_id),
            "item_count": len(reservations),
            "expires_at": expires_at.isoformat(),
        },
    )
    return reservations


async def consume_order_reservations(
    db: AsyncSession,
    order_id: uuid.UUID,
) -> list[InventoryReservation]:
    """
    Consumes all active reservations for an order upon successful payment capture.
    Idempotent: if already consumed, returns the consumed reservations.
    Rejects consumption if any reservation is already expired or released.
    """
    stmt = (
        select(InventoryReservation)
        .where(InventoryReservation.order_id == order_id)
        .order_by(InventoryReservation.product_id.asc())
        .with_for_update()
    )
    reservations = (await db.execute(stmt)).scalars().all()

    if not reservations:
        logger.warning(
            "inventory.consume_no_reservations_found",
            extra={"order_id": str(order_id)},
        )
        return []

    # Check if already fully consumed (idempotent path)
    if all(r.status == ReservationStatus.consumed for r in reservations):
        logger.info(
            "inventory.reservations_already_consumed",
            extra={"order_id": str(order_id)},
        )
        return list(reservations)

    # Check for invalid terminal states
    for r in reservations:
        if r.status in (ReservationStatus.expired, ReservationStatus.released):
            logger.error(
                "inventory.consume_rejected_invalid_state",
                extra={
                    "order_id": str(order_id),
                    "reservation_id": str(r.id),
                    "status": r.status.value,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot consume inventory reservation in state '{r.status.value}'.",
            )

    now = datetime.now(timezone.utc)
    for r in reservations:
        if r.status == ReservationStatus.active:
            r.status = ReservationStatus.consumed
            r.consumed_at = now
            r.version = r.version + 1
            db.add(r)

    logger.info(
        "inventory.reservations_consumed",
        extra={"order_id": str(order_id), "count": len(reservations)},
    )
    return list(reservations)


async def release_order_reservations(
    db: AsyncSession,
    order_id: uuid.UUID,
    release_reason: str,
    to_status: ReservationStatus = ReservationStatus.released,
    from_statuses: Optional[Sequence[ReservationStatus]] = None,
) -> int:
    """
    Centralized, exactly-once inventory restoration service.
    Transitions reservations to 'released' or 'expired', restoring stock
    in deterministic product_id order within the active transaction.

    Safety invariants:
    - Never restores stock if reservation is already released or expired.
    - Status change is guarded by WHERE status IN (:allowed_from).
    - Restores stock ONLY if rowcount == 1 on reservation update.
    """
    if to_status not in (ReservationStatus.released, ReservationStatus.expired):
        raise ValueError(f"Invalid target status for release: {to_status}")

    allowed_from = list(from_statuses) if from_statuses is not None else [ReservationStatus.active]

    # Fetch eligible reservations with row-level locks
    stmt = (
        select(InventoryReservation)
        .where(
            InventoryReservation.order_id == order_id,
            InventoryReservation.status.in_(allowed_from),
        )
        .order_by(InventoryReservation.product_id.asc())
        .with_for_update()
    )
    eligible_reservations = (await db.execute(stmt)).scalars().all()

    if not eligible_reservations:
        logger.info(
            "inventory.no_eligible_reservations_to_release",
            extra={"order_id": str(order_id), "reason": release_reason, "allowed_from": [s.value for s in allowed_from]},
        )
        return 0

    now = datetime.now(timezone.utc)
    restoration_plan: dict[uuid.UUID, int] = {}
    released_count = 0

    for res in eligible_reservations:
        # Atomic conditional status update: only transition if still in allowed_from
        upd_stmt = (
            update(InventoryReservation)
            .where(
                InventoryReservation.id == res.id,
                InventoryReservation.status.in_(allowed_from),
            )
            .values(
                status=to_status,
                released_at=now,
                release_reason=release_reason,
                version=InventoryReservation.version + 1,
            )
        )
        res_update = await db.execute(upd_stmt)
        if res_update.rowcount == 1:
            released_count += 1
            restoration_plan[res.product_id] = (
                restoration_plan.get(res.product_id, 0) + res.quantity
            )
        else:
            logger.warning(
                "inventory.reservation_already_transitioned_concurrently",
                extra={"reservation_id": str(res.id), "order_id": str(order_id)},
            )

    # Restore stock in deterministic product_id ascending order to avoid lock inversion
    for product_id in sorted(restoration_plan.keys(), key=lambda p: str(p)):
        qty_to_restore = restoration_plan[product_id]
        inv_upd = (
            update(Inventory)
            .where(Inventory.product_id == product_id)
            .values(
                stock=Inventory.stock + qty_to_restore,
                version=Inventory.version + 1,
            )
        )
        await db.execute(inv_upd)

    logger.info(
        "inventory.reservations_released_stock_restored",
        extra={
            "order_id": str(order_id),
            "released_count": released_count,
            "to_status": to_status.value,
            "reason": release_reason,
            "restored_products": [str(p) for p in sorted(restoration_plan.keys(), key=lambda p: str(p))],
        },
    )
    return released_count


async def get_order_reservations(
    db: AsyncSession,
    order_id: uuid.UUID,
) -> Sequence[InventoryReservation]:
    """Retrieve all reservations for an order."""
    stmt = (
        select(InventoryReservation)
        .where(InventoryReservation.order_id == order_id)
        .order_by(InventoryReservation.created_at.asc())
    )
    return (await db.execute(stmt)).scalars().all()


async def get_order_reservation_summary(
    db: AsyncSession,
    order_id: uuid.UUID,
) -> dict:
    """Retrieve real-time reservation summary with authoritative backend countdown."""
    now = datetime.now(timezone.utc)
    reservations = await get_order_reservations(db, order_id)
    if not reservations:
        return {
            "order_id": order_id,
            "status": "none",
            "expires_at": None,
            "seconds_remaining": 0,
            "server_time": now,
            "is_expired": False,
            "items": [],
        }

    # If any is active, overall state is active
    active_res = [r for r in reservations if r.status == ReservationStatus.active]
    if active_res:
        earliest_expiry = min(r.expires_at for r in active_res)
        seconds_left = max(0, int((earliest_expiry - now).total_seconds()))
        is_expired = seconds_left == 0
        overall_status = "expired" if is_expired else "active"
    elif all(r.status == ReservationStatus.consumed for r in reservations):
        earliest_expiry = None
        seconds_left = 0
        is_expired = False
        overall_status = "consumed"
    elif any(r.status == ReservationStatus.expired for r in reservations):
        earliest_expiry = None
        seconds_left = 0
        is_expired = True
        overall_status = "expired"
    else:
        earliest_expiry = None
        seconds_left = 0
        is_expired = False
        overall_status = "released"

    items_data = [
        {
            "product_id": r.product_id,
            "quantity": r.quantity,
            "status": r.status.value,
            "reservation_reference": r.reservation_reference,
        }
        for r in reservations
    ]

    return {
        "order_id": order_id,
        "status": overall_status,
        "expires_at": earliest_expiry,
        "seconds_remaining": seconds_left,
        "server_time": now,
        "is_expired": is_expired,
        "items": items_data,
    }
