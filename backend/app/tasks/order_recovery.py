"""
Order and Delivery Lifecycle Recovery Tasks (Stage 6).

Provides reliable, idempotent background jobs for:
1. Reconciling stale pending orders (checkout/payment abandonment timeout).
2. Reconciling stale unaccepted orders (shop confirmation timeout).
3. Reconciling stale delivery assignments with safe reassignment/redispatch.

All state transitions route through the centralized Stage 3 state machine,
preserve inventory OCC integer versions, maintain database invariants
(partial unique indexes), and record OrderEvent audit entries atomically.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, update, and_, exists, func, cast
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import NullPool
from geoalchemy2 import Geography
from geoalchemy2.shape import to_shape

from app.core.celery_app import celery_app
from app.core.config import settings
from app.models.order import Order, OrderStatus, OrderEvent
from app.models.delivery import Delivery, DeliveryStatus
from app.models.payment import Payment, PaymentStatus
from app.models.rider import RiderProfile
from app.models.inventory_reservation import InventoryReservation, ReservationStatus
from app.services.state_machine import transition_order
from app.services.reservation import consume_order_reservations, release_order_reservations
from app.services.payment_provider import get_payment_provider

logger = logging.getLogger(__name__)


def _get_worker_session_maker():
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        future=True,
        poolclass=NullPool,
    )
    session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    return engine, session_maker


def _run_sync(coro):
    """Executes a coroutine synchronously, safely handling environments with or without a running event loop."""
    from celery.exceptions import SoftTimeLimitExceeded
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
        logger.warning("Celery task reached soft time limit. Cleanly terminating execution.")
        return 0



# ---------------------------------------------------------------------------
# Centralized Reservation-Backed Order Reconciliation Helper (Stages 6 & 8)
# ---------------------------------------------------------------------------

async def _reconcile_single_order_reservation_async(
    session: AsyncSession,
    order: Order,
    now: datetime,
) -> Optional[str]:
    """
    Centralized reconciliation of a reservation-backed order.
    Enforces the authoritative 4-way payment outcome decision matrix and delegates
    stock restoration exclusively to the centralized reservation service.
    Returns: 'consumed', 'released', 'expired', 'retained', or None.
    """
    pay_stmt = select(Payment).where(Payment.order_id == order.id).with_for_update()
    payments = (await session.execute(pay_stmt)).scalars().all()
    captured_payment = next((p for p in payments if p.status == PaymentStatus.captured), None)
    provider = get_payment_provider()

    # Fast guard: if another concurrent worker has already reconciled all active reservations,
    # exit idempotently without re-counting or performing duplicate side-effects.
    active_res_stmt = (
        select(func.count(InventoryReservation.id))
        .where(
            InventoryReservation.order_id == order.id,
            InventoryReservation.status == ReservationStatus.active,
        )
    )
    active_res_count = (await session.execute(active_res_stmt)).scalar() or 0
    if active_res_count == 0 and not captured_payment:
        logger.info(f"Order {order.id} has no active reservations remaining. Skipping redundant reconciliation.")
        return None

    if captured_payment:
        logger.info(f"Order {order.id} has captured payment {captured_payment.id}. Consuming reservations.")
        await consume_order_reservations(session, order.id)
        if order.status == OrderStatus.pending:
            await transition_order(
                db=session,
                order_id=order.id,
                to_status=OrderStatus.confirmed,
                actor=None,
                actor_role="system",
                reason="Reconciled captured payment after reservation expiration",
            )
        await session.commit()
        logger.info(f"Reconciliation completed for order {order.id}: reservations consumed")
        return "consumed"

    if not payments:
        # No payment was ever initiated - abandoned checkout.
        await release_order_reservations(
            db=session,
            order_id=order.id,
            release_reason="Reservation expired: checkout abandoned before payment initiation",
            to_status=ReservationStatus.expired,
        )
        if order.status == OrderStatus.pending:
            await transition_order(
                db=session,
                order_id=order.id,
                to_status=OrderStatus.cancelled,
                actor=None,
                actor_role="system",
                reason="Order cancelled: stock reservation expired without payment initiation",
            )
        await session.commit()
        logger.info(f"Reconciliation completed for order {order.id}: abandoned checkout expired")
        return "expired"

    # Inspect pending payments with provider
    has_unknown_outcome = False
    has_in_flight = False
    has_confirmed_success = False

    for p in payments:
        if p.status in [PaymentStatus.created, PaymentStatus.pending, PaymentStatus.authorized]:
            if p.provider_order_id:
                try:
                    provider_order = await provider.fetch_payment_order(p.provider_order_id)
                    p_status = (provider_order.get("status") or "").lower()
                    if p_status in ["paid", "captured"]:
                        p.status = PaymentStatus.captured
                        p.paid_at = datetime.now(timezone.utc)
                        session.add(p)
                        has_confirmed_success = True
                        break
                    elif p_status in ["failed", "cancelled", "expired", "terminated"]:
                        p.status = PaymentStatus.failed
                        p.failure_reason = f"Provider confirmed {p_status}"
                        session.add(p)
                    elif p_status in ["processing", "authorized", "in_progress", "under_review"]:
                        has_in_flight = True
                    elif p_status in ["created", "attempted"]:
                        # Payment order exists at gateway but was never paid/captured
                        pass
                    else:
                        has_unknown_outcome = True
                except Exception as p_err:
                    logger.warning(
                        f"Provider communication error checking order {p.provider_order_id}: {p_err}"
                    )
                    has_unknown_outcome = True
            else:
                pass

    if has_confirmed_success:
        logger.info(f"Order {order.id} confirmed by provider. Consuming reservations.")
        await consume_order_reservations(session, order.id)
        if order.status == OrderStatus.pending:
            await transition_order(
                db=session,
                order_id=order.id,
                to_status=OrderStatus.confirmed,
                actor=None,
                actor_role="system",
                reason="Reconciled captured payment confirmed by provider",
            )
        await session.commit()
        logger.info(f"Reconciliation completed for order {order.id}: confirmed by provider")
        return "consumed"

    if has_unknown_outcome or has_in_flight:
        # Unknown outcome or in-flight processing:
        # RETAIN active reservation and order state while reconciliation is attempted.
        # Do NOT release stock or cancel order.
        logger.warning(
            "inventory.reconciliation_retained_unknown_outcome",
            extra={
                "order_id": str(order.id),
                "in_flight": has_in_flight,
                "unknown_outcome": has_unknown_outcome,
                "action": "retained_active_reservation",
            },
        )
        await session.rollback()
        return "retained"

    # Check if all payments are definitively failed
    all_failed = all(p.status in [PaymentStatus.failed, PaymentStatus.cancelled] for p in payments)
    if all_failed:
        logger.info(f"Order {order.id} has definitively failed payments. Releasing reservations.")
        await release_order_reservations(
            db=session,
            order_id=order.id,
            release_reason="Definitive payment failure confirmed by provider",
            to_status=ReservationStatus.released,
        )
        if order.status == OrderStatus.pending:
            await transition_order(
                db=session,
                order_id=order.id,
                to_status=OrderStatus.cancelled,
                actor=None,
                actor_role="system",
                reason="Order cancelled: payment definitively failed",
            )
        await session.commit()
        logger.info(f"Reconciliation completed for order {order.id}: definitive failure released")
        return "released"

    # Otherwise: payments remain unpaid beyond policy threshold
    # Safe compensating workflow protects against late captures.
    for p in payments:
        if p.status in [PaymentStatus.created, PaymentStatus.pending]:
            p.status = PaymentStatus.cancelled
            p.failure_reason = "Reservation TTL expired before payment completion"
            session.add(p)

    # Exactly-once restoration via centralized reservation service
    await release_order_reservations(
        db=session,
        order_id=order.id,
        release_reason="Reservation expired: payment was not completed within TTL window",
        to_status=ReservationStatus.expired,
    )

    if order.status == OrderStatus.pending:
        await transition_order(
            db=session,
            order_id=order.id,
            to_status=OrderStatus.cancelled,
            actor=None,
            actor_role="system",
            reason="Order cancelled: stock reservation expired",
        )

    await session.commit()
    logger.info(f"Reconciliation completed for order {order.id}: expired pending released")
    return "expired"


# ---------------------------------------------------------------------------
# 1. Stale Pending Orders Reconciliation (Checkout / Payment Timeout)
# ---------------------------------------------------------------------------

async def _reconcile_stale_pending_orders_async(
    cutoff_seconds: Optional[int] = None,
    batch_size: Optional[int] = None,
    db_session: Optional[AsyncSession] = None,
) -> int:
    """
    Cancels orders that have remained in OrderStatus.pending beyond the timeout window
    without a captured payment. Restores reserved inventory stock deterministically.
    """
    effective_timeout = cutoff_seconds if cutoff_seconds is not None else settings.ORDER_PENDING_TIMEOUT_SECONDS
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=effective_timeout)
    effective_batch = batch_size or settings.ORDER_RECOVERY_BATCH_SIZE

    logger.info(
        f"Scanning for stale pending orders created before {cutoff.isoformat()} "
        f"(timeout: {effective_timeout}s, batch: {effective_batch})"
    )

    engine = None
    managed_session = False
    if db_session is None:
        engine, session_maker = _get_worker_session_maker()
        session = session_maker()
        managed_session = True
    else:
        session = db_session

    cancelled_count = 0
    try:
        # Fast indexed lookup for candidate IDs
        cand_stmt = (
            select(Order.id)
            .where(
                Order.status == OrderStatus.pending,
                Order.created_at < cutoff,
            )
            .order_by(Order.created_at.asc())
            .limit(effective_batch)
        )
        result = await session.execute(cand_stmt)
        candidate_ids = result.scalars().all()

        for order_id in candidate_ids:
            try:
                # 1. Fetch Order with row-level lock
                order_stmt = (
                    select(Order)
                    .options(
                        selectinload(Order.items),
                        selectinload(Order.delivery),
                        selectinload(Order.events),
                    )
                    .where(Order.id == order_id)
                    .with_for_update()
                )
                order = (await session.execute(order_stmt)).scalar_one_or_none()
                if not order:
                    continue

                # 2. Re-verify eligibility inside the transaction
                if order.status != OrderStatus.pending or order.created_at >= cutoff:
                    logger.info(f"Order {order_id} no longer eligible for pending timeout. Skipping.")
                    continue

                # Check if order is reservation-backed
                res_count_stmt = select(func.count(InventoryReservation.id)).where(InventoryReservation.order_id == order.id)
                has_reservations = ((await session.execute(res_count_stmt)).scalar() or 0) > 0

                if has_reservations:
                    # All reservation-backed orders must delegate to the centralized reservation recovery workflow.
                    # This prevents dual recovery tasks from independently restoring stock and guarantees
                    # authoritative payment provider outcome checking.
                    outcome = await _reconcile_single_order_reservation_async(session, order, datetime.now(timezone.utc))
                    if outcome in ["consumed", "released", "expired"]:
                        cancelled_count += 1
                    continue

                # 3. Check for any captured payment (legacy fallback for orders without reservation records)
                pay_stmt = select(Payment).where(Payment.order_id == order.id).with_for_update()
                payments = (await session.execute(pay_stmt)).scalars().all()
                if any(p.status == PaymentStatus.captured for p in payments):
                    logger.warning(f"Order {order_id} has a captured payment; skipping auto-cancellation.")
                    continue

                # 4. Cancel uncaptured payment records
                for p in payments:
                    if p.status in [PaymentStatus.created, PaymentStatus.pending]:
                        p.status = PaymentStatus.cancelled
                        session.add(p)

                # 5. Route cancellation through centralized Stage 3 state machine
                await transition_order(
                    db=session,
                    order_id=order.id,
                    to_status=OrderStatus.cancelled,
                    actor=None,
                    actor_role="system",
                    reason="Order auto-cancelled: checkout/payment timeout exceeded",
                )
                cancelled_count += 1
                logger.info(f"Auto-cancelled legacy stale pending order {order_id} and restored inventory.")

            except Exception as exc:
                logger.error(f"Error processing pending timeout for order {order_id}: {exc}", exc_info=True)
                if managed_session:
                    await session.rollback()

    finally:
        if managed_session:
            await session.close()
            if engine:
                await engine.dispose()

    return cancelled_count


@celery_app.task(
    bind=True,
    name="reconcile_stale_pending_orders",
    autoretry_for=(OperationalError, DBAPIError),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
)
def reconcile_stale_pending_orders(self, cutoff_seconds: Optional[int] = None, batch_size: Optional[int] = None) -> int:
    """Celery task entrypoint for pending orders reconciliation."""
    return _run_sync(_reconcile_stale_pending_orders_async(cutoff_seconds, batch_size))


# ---------------------------------------------------------------------------
# 2. Stale Unaccepted Orders Reconciliation (Shop Confirmation Timeout)
# ---------------------------------------------------------------------------

async def _reconcile_stale_unaccepted_orders_async(
    cutoff_seconds: Optional[int] = None,
    batch_size: Optional[int] = None,
    db_session: Optional[AsyncSession] = None,
) -> int:
    """
    Cancels confirmed orders that the shop owner has not accepted/prepared within
    the timeout window. Restores stock, marks payment refunded, and cancels pending delivery.
    """
    effective_timeout = cutoff_seconds if cutoff_seconds is not None else settings.ORDER_CONFIRMED_TIMEOUT_SECONDS
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=effective_timeout)
    effective_batch = batch_size or settings.ORDER_RECOVERY_BATCH_SIZE

    logger.info(
        f"Scanning for stale unaccepted confirmed orders created before {cutoff.isoformat()} "
        f"(timeout: {effective_timeout}s, batch: {effective_batch})"
    )

    engine = None
    managed_session = False
    if db_session is None:
        engine, session_maker = _get_worker_session_maker()
        session = session_maker()
        managed_session = True
    else:
        session = db_session

    cancelled_count = 0
    try:
        # Measure elapsed time from when the order entered confirmed status (updated_at or created_at),
        # ensuring the merchant receives their full configured timeout from confirmation time.
        confirmed_time_expr = func.coalesce(Order.updated_at, Order.created_at)
        cand_stmt = (
            select(Order.id)
            .where(
                Order.status == OrderStatus.confirmed,
                confirmed_time_expr < cutoff,
            )
            .order_by(confirmed_time_expr.asc())
            .limit(effective_batch)
        )
        result = await session.execute(cand_stmt)
        candidate_ids = result.scalars().all()

        for order_id in candidate_ids:
            try:
                order_stmt = (
                    select(Order)
                    .options(
                        selectinload(Order.items),
                        selectinload(Order.delivery),
                        selectinload(Order.events),
                    )
                    .where(Order.id == order_id)
                    .with_for_update()
                )
                order = (await session.execute(order_stmt)).scalar_one_or_none()
                if not order:
                    continue

                # Re-verify eligibility inside the transaction
                effective_confirmed_time = order.updated_at or order.created_at
                if order.status != OrderStatus.confirmed or effective_confirmed_time >= cutoff:
                    logger.info(f"Order {order_id} no longer in confirmed state or within cutoff. Skipping.")
                    continue

                # Protect deliveries that have already been picked up or are out for delivery
                if order.delivery and order.delivery.status in [
                    DeliveryStatus.picked_up,
                    DeliveryStatus.out_for_delivery,
                    DeliveryStatus.delivered,
                ]:
                    logger.info(f"Order {order_id} has delivery in {order.delivery.status.value}; strictly protected.")
                    continue

                # Refund captured payment record (explicitly mark as simulated mock refund)
                pay_stmt = select(Payment).where(Payment.order_id == order.id, Payment.status == PaymentStatus.captured).with_for_update()
                captured_payment = (await session.execute(pay_stmt)).scalar_one_or_none()
                if captured_payment:
                    captured_payment.status = PaymentStatus.refunded
                    captured_payment.failure_reason = "Simulated mock refund: shop acceptance timeout expired"
                    session.add(captured_payment)

                # Cancel order via centralized state machine
                await transition_order(
                    db=session,
                    order_id=order.id,
                    to_status=OrderStatus.cancelled,
                    actor=None,
                    actor_role="system",
                    reason="Order auto-cancelled: shop acceptance timeout exceeded (simulated mock refund recorded)",
                )
                cancelled_count += 1
                logger.info(f"Auto-cancelled stale confirmed order {order_id} (shop timeout) and restored inventory.")

            except Exception as exc:
                logger.error(f"Error processing unaccepted timeout for order {order_id}: {exc}", exc_info=True)
                if managed_session:
                    await session.rollback()

    finally:
        if managed_session:
            await session.close()
            if engine:
                await engine.dispose()

    return cancelled_count


@celery_app.task(
    bind=True,
    name="reconcile_stale_unaccepted_orders",
    autoretry_for=(OperationalError, DBAPIError),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
)
def reconcile_stale_unaccepted_orders(self, cutoff_seconds: Optional[int] = None, batch_size: Optional[int] = None) -> int:
    """Celery task entrypoint for unaccepted orders reconciliation."""
    return _run_sync(_reconcile_stale_unaccepted_orders_async(cutoff_seconds, batch_size))


# ---------------------------------------------------------------------------
# 3. Stale Delivery Assignments Reconciliation & Safe Reassignment
# ---------------------------------------------------------------------------

async def _reconcile_stale_deliveries_async(
    cutoff_seconds: Optional[int] = None,
    batch_size: Optional[int] = None,
    db_session: Optional[AsyncSession] = None,
) -> int:
    """
    Recovers deliveries where a rider was assigned, but the rider has not picked up
    the order within the timeout window. Releases the unresponsive rider, cancels the stale
    delivery (freeing partial unique indexes), creates a fresh replacement delivery, and
    performs PostGIS candidate discovery for safe atomic reassignment.
    """
    effective_timeout = cutoff_seconds if cutoff_seconds is not None else settings.DELIVERY_ASSIGNED_TIMEOUT_SECONDS
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=effective_timeout)
    effective_batch = batch_size or settings.ORDER_RECOVERY_BATCH_SIZE

    logger.info(
        f"Scanning for stale assigned deliveries assigned before {cutoff.isoformat()} "
        f"(timeout: {effective_timeout}s, batch: {effective_batch})"
    )

    engine = None
    managed_session = False
    if db_session is None:
        engine, session_maker = _get_worker_session_maker()
        session = session_maker()
        managed_session = True
    else:
        session = db_session

    reassigned_count = 0
    try:
        cand_stmt = (
            select(Delivery.id)
            .where(
                Delivery.status == DeliveryStatus.assigned,
                Delivery.picked_up_at.is_(None),
                Delivery.assigned_at < cutoff,
            )
            .order_by(Delivery.assigned_at.asc())
            .limit(effective_batch)
        )
        result = await session.execute(cand_stmt)
        candidate_ids = result.scalars().all()

        for delivery_id in candidate_ids:
            try:
                # 1. Fetch Delivery with row-level lock
                delivery_stmt = (
                    select(Delivery)
                    .where(Delivery.id == delivery_id)
                    .with_for_update()
                )
                delivery = (await session.execute(delivery_stmt)).scalar_one_or_none()
                if not delivery:
                    continue

                # 2. Re-verify eligibility inside the transaction
                if (
                    delivery.status != DeliveryStatus.assigned
                    or delivery.picked_up_at is not None
                    or not delivery.assigned_at
                    or delivery.assigned_at >= cutoff
                ):
                    logger.info(f"Delivery {delivery_id} is no longer stale or already picked up. Skipping.")
                    continue

                # 3. Lock parent order to ensure it is not cancelled or delivered
                order_stmt = select(Order).where(Order.id == delivery.order_id).with_for_update()
                order = (await session.execute(order_stmt)).scalar_one_or_none()
                if not order or order.status in [OrderStatus.cancelled, OrderStatus.delivered]:
                    logger.info(f"Parent order {delivery.order_id} is in terminal state. Skipping reassignment.")
                    continue

                stale_rider_id = delivery.rider_id

                # 4. Release unresponsive rider
                if stale_rider_id:
                    rider_stmt = select(RiderProfile).where(RiderProfile.id == stale_rider_id).with_for_update()
                    prev_rider = (await session.execute(rider_stmt)).scalar_one_or_none()
                    if prev_rider:
                        prev_rider.is_available = True
                        session.add(prev_rider)

                # 5. Cancel stale delivery record (frees active-delivery partial unique indexes)
                delivery.status = DeliveryStatus.cancelled
                session.add(delivery)
                await session.flush()

                # 6. Create replacement delivery record
                new_delivery = Delivery(
                    order_id=order.id,
                    status=DeliveryStatus.pending,
                    destination_location=delivery.destination_location,
                )
                session.add(new_delivery)
                await session.flush()

                # 7. PostGIS geospatial candidate rider discovery for atomic reassignment
                candidate_rider = None
                if new_delivery.destination_location is not None:
                    active_deliveries = select(Delivery.id).where(
                        and_(
                            Delivery.rider_id == RiderProfile.id,
                            Delivery.status.in_([
                                DeliveryStatus.assigned,
                                DeliveryStatus.picked_up,
                                DeliveryStatus.out_for_delivery,
                            ])
                        )
                    ).correlate(RiderProfile)

                    radius = settings.RIDER_SEARCH_RADIUS_METERS
                    loc_cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.RIDER_LOCATION_MAX_AGE_SECONDS)
                    dest_query = select(Delivery.destination_location).where(Delivery.id == new_delivery.id).scalar_subquery()

                    cand_query = (
                        select(RiderProfile)
                        .where(
                            RiderProfile.is_available == True,
                            RiderProfile.id != stale_rider_id,  # Exclude timed-out rider
                            RiderProfile.location.is_not(None),
                            RiderProfile.location_updated_at >= loc_cutoff,
                            ~exists(active_deliveries),
                            func.ST_DWithin(
                                cast(RiderProfile.location, Geography()),
                                cast(dest_query, Geography()),
                                radius
                            )
                        )
                        .order_by(
                            func.ST_Distance(
                                cast(RiderProfile.location, Geography()),
                                cast(dest_query, Geography())
                            ),
                            RiderProfile.id
                        )
                        .limit(1)
                        .with_for_update(skip_locked=True)
                    )
                    candidate_rider = (await session.execute(cand_query)).scalar_one_or_none()

                now = datetime.now(timezone.utc)
                if candidate_rider:
                    new_delivery.rider_id = candidate_rider.id
                    new_delivery.status = DeliveryStatus.assigned
                    new_delivery.assigned_at = now
                    candidate_rider.is_available = False
                    session.add(candidate_rider)
                    session.add(new_delivery)
                    assignment_info = f"assigned to rider {candidate_rider.id}"
                else:
                    new_delivery.status = DeliveryStatus.pending
                    new_delivery.awaiting_rider = False
                    new_delivery.dispatch_attempts = 0
                    session.add(new_delivery)
                    await session.flush()
                    if settings.DISPATCH_AUTO_ENABLED:
                        from app.services.dispatch import create_dispatch_batch
                        await create_dispatch_batch(session, new_delivery.id)
                    assignment_info = "set to pending (reset awaiting_rider and re-entered dispatch)"

                # 8. Record OrderEvent audit record in the same atomic transaction
                audit_event = OrderEvent(
                    order_id=order.id,
                    from_state=order.status.value,
                    to_state=order.status.value,
                    actor_role="system",
                    reason=(
                        f"Delivery reassigned: previous rider {stale_rider_id} assignment timed out; "
                        f"created replacement delivery {new_delivery.id} ({assignment_info})"
                    ),
                )
                session.add(audit_event)

                await session.commit()
                reassigned_count += 1
                logger.info(
                    f"Successfully recovered delivery {delivery_id}: cancelled stale delivery, "
                    f"created replacement {new_delivery.id} ({assignment_info})."
                )

                # 9. Post-commit hooks (PubSub & ETA recalculation)
                try:
                    from app.websockets.redis_pubsub import publish_delivery_event
                    await publish_delivery_event(str(new_delivery.id), {
                        "event": "delivery.status_changed",
                        "version": 1,
                        "delivery_id": str(new_delivery.id),
                        "timestamp": now.isoformat(),
                        "data": {
                            "status": new_delivery.status.value,
                            "rider_id": str(new_delivery.rider_id) if new_delivery.rider_id else None,
                        }
                    })
                except Exception as pub_exc:
                    logger.warning(f"PubSub event failed on delivery redispatch {new_delivery.id}: {pub_exc}")

            except Exception as exc:
                logger.error(f"Error recovering stale delivery {delivery_id}: {exc}", exc_info=True)
                if managed_session:
                    await session.rollback()

    finally:
        if managed_session:
            await session.close()
            if engine:
                await engine.dispose()

    return reassigned_count


@celery_app.task(
    bind=True,
    name="reconcile_stale_deliveries",
    autoretry_for=(OperationalError, DBAPIError),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
)
def reconcile_stale_deliveries(self, cutoff_seconds: Optional[int] = None, batch_size: Optional[int] = None) -> int:
    """Celery task entrypoint for stale delivery reassignment reconciliation."""
    return _run_sync(_reconcile_stale_deliveries_async(cutoff_seconds, batch_size))


# ---------------------------------------------------------------------------
# 4. Expired Inventory Reservations Reconciliation (Stage 8)
# ---------------------------------------------------------------------------

async def _reconcile_expired_inventory_reservations_async(
    batch_size: Optional[int] = None,
    db_session: Optional[AsyncSession] = None,
) -> int:
    """
    Finds active inventory reservations whose expiration time has passed.
    Checks payment status:
    - If captured: consumes reservations and confirms order.
    - If pending/failed: releases reservations (to status 'expired'), restores stock exactly once,
      and cancels the order.
    """
    effective_batch = batch_size or settings.ORDER_RECOVERY_BATCH_SIZE
    now = datetime.now(timezone.utc)

    logger.info(
        f"Scanning for expired active inventory reservations (now: {now.isoformat()}, batch: {effective_batch})"
    )

    engine = None
    managed_session = False
    if db_session is None:
        engine, session_maker = _get_worker_session_maker()
        session = session_maker()
        managed_session = True
    else:
        session = db_session

    recovered_orders_count = 0
    try:
        # Fast query for distinct orders with active expired reservations
        cand_stmt = (
            select(InventoryReservation.order_id)
            .where(
                InventoryReservation.status == ReservationStatus.active,
                InventoryReservation.expires_at <= now,
            )
            .distinct()
            .limit(effective_batch)
        )
        result = await session.execute(cand_stmt)
        candidate_order_ids = result.scalars().all()

        for order_id in candidate_order_ids:
            try:
                # Row-level lock on order
                order_stmt = (
                    select(Order)
                    .options(
                        selectinload(Order.items),
                        selectinload(Order.delivery),
                        selectinload(Order.events),
                        selectinload(Order.reservations),
                    )
                    .where(Order.id == order_id)
                    .with_for_update(skip_locked=True)
                )
                order = (await session.execute(order_stmt)).scalar_one_or_none()
                if not order:
                    continue

                outcome = await _reconcile_single_order_reservation_async(session, order, now)
                if outcome in ["consumed", "released", "expired"]:
                    recovered_orders_count += 1

            except Exception as exc:
                logger.error(f"Error reconciling expired reservation for order {order_id}: {exc}", exc_info=True)
                if managed_session:
                    await session.rollback()

    finally:
        if managed_session:
            await session.close()
            if engine:
                await engine.dispose()

    return recovered_orders_count


@celery_app.task(
    bind=True,
    name="reconcile_expired_inventory_reservations",
    autoretry_for=(OperationalError, DBAPIError),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
)
def reconcile_expired_inventory_reservations(self, batch_size: Optional[int] = None) -> int:
    """Celery task entrypoint for reconciling expired active reservations."""
    return _run_sync(_reconcile_expired_inventory_reservations_async(batch_size))


# 5. Automated Proximity Dispatch Offer Escalation
async def _escalate_unassigned_dispatch_offers_async(
    batch_size: Optional[int] = None,
    db_session: Optional[AsyncSession] = None,
) -> int:
    """
    Periodically scans pending deliveries with open or expired automated dispatch offers.
    For each delivery:
    1. Expires any offers where expires_at <= func.now().
    2. If all offers for the current attempt are finished, escalates to the next attempt with wider radius.
    3. If max attempts are reached, marks awaiting_rider=True.
    """
    limit = batch_size or 50
    escalated_count = 0

    engine = None
    managed_session = False
    if db_session is None:
        engine, session_maker = _get_worker_session_maker()
        session = session_maker()
        managed_session = True
    else:
        session = db_session

    try:
        stmt = (
            select(Delivery.id)
            .where(
                Delivery.status == DeliveryStatus.pending,
                Delivery.rider_id.is_(None),
                Delivery.awaiting_rider == False,
                Delivery.dispatch_attempts > 0,
            )
            .limit(limit)
        )
        delivery_ids = (await session.execute(stmt)).scalars().all()

        for deliv_id in delivery_ids:
            try:
                from app.services.dispatch import escalate_dispatch
                escalated = await escalate_dispatch(session, deliv_id)
                if escalated:
                    escalated_count += 1
                await session.commit()
            except Exception as exc:
                logger.error(f"Error escalating dispatch for delivery {deliv_id}: {exc}", exc_info=True)
                await session.rollback()

    finally:
        if managed_session:
            await session.close()
            if engine:
                await engine.dispose()

    return escalated_count


@celery_app.task(
    bind=True,
    name="escalate_unassigned_dispatch_offers",
    autoretry_for=(OperationalError, DBAPIError),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
)
def escalate_unassigned_dispatch_offers(self, batch_size: Optional[int] = None) -> int:
    """Celery task entrypoint for escalating unassigned dispatch offers."""
    return _run_sync(_escalate_unassigned_dispatch_offers_async(batch_size))
