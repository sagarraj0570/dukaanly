import uuid
import logging
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from app.models.payment import Payment, PaymentStatus
from app.models.order import Order, OrderStatus
from app.models.user import User
from app.models.inventory_reservation import InventoryReservation, ReservationStatus
from app.schemas.payment import PaymentInitiationResponse, PaymentVerificationRequest, PaymentResponse
from app.services.payment_provider import get_payment_provider
from app.services.state_machine import transition_order
from app.services.reservation import consume_order_reservations, release_order_reservations
from app.core.config import settings

logger = logging.getLogger(__name__)

async def initiate_payment(db: AsyncSession, order_id: uuid.UUID, customer: User) -> PaymentInitiationResponse:
    # 1. Verify Order Ownership and State with row lock
    stmt = select(Order).where(Order.id == order_id).with_for_update()
    order = (await db.execute(stmt)).scalar_one_or_none()
    
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    if order.customer_id != customer.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to pay for this order")
    if order.status != OrderStatus.pending:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Order is not in a payable state (currently {order.status.value})")

    # 2. Check for existing successful payment
    existing_stmt = select(Payment).where(Payment.order_id == order_id, Payment.status == PaymentStatus.captured)
    existing_payment = (await db.execute(existing_stmt)).scalar_one_or_none()
    if existing_payment:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Order is already paid successfully")

    # 2b. Check reservation status (if reservations exist)
    res_stmt = select(InventoryReservation).where(
        InventoryReservation.order_id == order_id,
        InventoryReservation.status == ReservationStatus.active,
    )
    active_reservations = (await db.execute(res_stmt)).scalars().all()
    if active_reservations:
        now = datetime.now(timezone.utc)
        if any(r.expires_at <= now for r in active_reservations):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Inventory reservation for this order has expired. Please re-order."
            )

    # 3. Create Provider Order using authoritative amount and currency
    provider = get_payment_provider()
    receipt_id = str(order.id)
    
    provider_order = await provider.create_payment_order(
        amount=float(order.total_amount),
        currency=settings.CURRENCY,
        receipt_id=receipt_id
    )

    # 4. Create/Update Local Payment Record
    pending_stmt = select(Payment).where(
        Payment.order_id == order_id,
        Payment.status == PaymentStatus.created
    ).with_for_update()
    payment = (await db.execute(pending_stmt)).scalar_one_or_none()
    
    if payment:
        payment.provider_order_id = provider_order["id"]
        payment.amount = order.total_amount
        payment.currency = settings.CURRENCY
    else:
        payment = Payment(
            order_id=order.id,
            provider=settings.PAYMENT_PROVIDER,
            provider_order_id=provider_order["id"],
            amount=order.total_amount,
            currency=settings.CURRENCY,
            status=PaymentStatus.created
        )
        db.add(payment)
        
    await db.commit()
    await db.refresh(payment)

    mock_payment_id = None
    mock_signature = None
    if getattr(provider, "is_mock", False):
        from app.services.payment_provider.razorpay import compute_mock_razorpay_signature
        mock_payment_id = f"pay_mock_{uuid.uuid4().hex[:10]}"
        mock_signature = compute_mock_razorpay_signature(provider_order["id"], mock_payment_id)

    return PaymentInitiationResponse(
        payment_id=payment.id,
        order_id=order.id,
        provider=settings.PAYMENT_PROVIDER,
        provider_order_id=provider_order["id"],
        amount=order.total_amount,
        currency=settings.CURRENCY,
        key_id=settings.RAZORPAY_KEY_ID,
        mock_payment_id=mock_payment_id,
        mock_signature=mock_signature,
    )

async def verify_payment(db: AsyncSession, verification_data: PaymentVerificationRequest, customer: User) -> PaymentResponse:
    provider_order_id = verification_data.razorpay_order_id
    
    # 1. Non-locking lookup of order_id to enforce canonical lock hierarchy:
    #    Order -> Payment -> InventoryReservation -> Inventory
    order_id_stmt = select(Payment.order_id).where(Payment.provider_order_id == provider_order_id)
    order_id = (await db.execute(order_id_stmt)).scalar_one_or_none()
    
    if not order_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment record not found")
        
    # 2. Acquire Order row lock FIRST
    order_stmt = select(Order).where(Order.id == order_id).with_for_update()
    order = (await db.execute(order_stmt)).scalar_one_or_none()
    
    if not order or order.customer_id != customer.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to verify this payment")

    # 3. Acquire Payment row lock SECOND
    stmt = select(Payment).where(Payment.provider_order_id == provider_order_id).with_for_update()
    payment = (await db.execute(stmt)).scalar_one_or_none()
    
    if not payment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment record not found")
        
    # 3. Idempotent check: if already captured, return cleanly or detect conflicting payment ID
    if payment.status == PaymentStatus.captured:
        if payment.provider_payment_id == verification_data.razorpay_payment_id:
            logger.info(f"Payment {payment.id} already captured with provider reference {verification_data.razorpay_payment_id}. Idempotent return.")
            return payment
        else:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Payment is already captured with a different transaction ID."
            )

    # 4. Validate order state, amount, and currency
    if order.status == OrderStatus.cancelled:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Cannot pay for an order in status '{order.status.value}'"
        )
        
    if Decimal(str(payment.amount)) != Decimal(str(order.total_amount)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment amount mismatch with order total")
        
    if payment.currency != settings.CURRENCY:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment currency mismatch")

    # 5. Check if provider_payment_id is already claimed by another payment record (409 Conflict)
    colliding_stmt = select(Payment).where(
        Payment.provider_payment_id == verification_data.razorpay_payment_id,
        Payment.id != payment.id
    )
    colliding_payment = (await db.execute(colliding_stmt)).scalar_one_or_none()
    if colliding_payment:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payment provider reference has already been used by another transaction."
        )

    # 6. Cryptographic verification
    provider = get_payment_provider()
    is_valid = await provider.verify_payment(verification_data.model_dump())
    
    if not is_valid:
        payment.status = PaymentStatus.failed
        payment.failure_reason = "Signature verification failed"
        await db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment signature verification failed")
        
    # 6b. Consume active inventory reservations (Stage 8)
    await consume_order_reservations(db, order.id)

    # 7. Mark payment as captured
    payment.status = PaymentStatus.captured
    payment.provider_payment_id = verification_data.razorpay_payment_id
    payment.paid_at = datetime.now(timezone.utc)
    
    # 8. Synchronize order transition via Stage 3 centralized state machine
    if order.status == OrderStatus.pending:
        await transition_order(
            db=db,
            order_id=order.id,
            to_status=OrderStatus.confirmed,
            actor=customer,
            actor_role="system",
            reason=f"Payment confirmed via provider verification ({verification_data.razorpay_payment_id})"
        )
    
    try:
        await db.commit()
        await db.refresh(payment)
    except IntegrityError as exc:
        await db.rollback()
        logger.warning(f"IntegrityError during payment capture commit: {exc}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payment provider reference has already been used."
        )

    return payment

async def process_webhook(db: AsyncSession, payload: bytes, signature: str) -> dict:
    provider = get_payment_provider()
    event_data = await provider.verify_webhook(payload, signature)
    
    event_type = event_data.get("event")
    
    if event_type == "payment.captured":
        entity = event_data.get("payload", {}).get("payment", {}).get("entity", {})
        provider_order_id = entity.get("order_id")
        provider_payment_id = entity.get("id")
        
        if provider_order_id:
            # 1. Non-locking lookup of order_id to enforce canonical lock hierarchy:
            #    Order -> Payment -> InventoryReservation -> Inventory
            order_id_stmt = select(Payment.order_id).where(Payment.provider_order_id == provider_order_id)
            order_id = (await db.execute(order_id_stmt)).scalar_one_or_none()
            if not order_id:
                logger.warning(f"Webhook payment.captured: No payment found for provider_order_id {provider_order_id}")
                return {"status": "ignored", "reason": "payment_record_not_found"}

            # 2. Acquire Order row lock FIRST
            order_stmt = select(Order).where(Order.id == order_id).with_for_update()
            order = (await db.execute(order_stmt)).scalar_one_or_none()

            # 3. Acquire Payment row lock SECOND
            stmt = select(Payment).where(Payment.provider_order_id == provider_order_id).with_for_update()
            payment = (await db.execute(stmt)).scalar_one_or_none()
            
            if payment:
                if payment.status == PaymentStatus.captured:
                    return {"status": "ok", "message": "already_captured"}
                
                # Check for collision on provider_payment_id
                if provider_payment_id:
                    colliding_stmt = select(Payment).where(
                        Payment.provider_payment_id == provider_payment_id,
                        Payment.id != payment.id
                    )
                    colliding = (await db.execute(colliding_stmt)).scalar_one_or_none()
                    if colliding:
                        logger.warning(f"Webhook payment.captured: {provider_payment_id} already claimed by {colliding.id}")
                        return {"status": "ignored", "reason": "duplicate_provider_payment_id"}
                
                if order and order.status == OrderStatus.cancelled:
                    # Safe Compensating Workflow:
                    # Order was cancelled (e.g. reservation expired). A late payment capture cannot
                    # revive the cancelled order or oversell stock. Immediately issue automated refund.
                    payment.status = PaymentStatus.refunded
                    payment.provider_payment_id = provider_payment_id
                    payment.paid_at = datetime.now(timezone.utc)
                    payment.failure_reason = "late_payment_captured_after_order_cancellation: auto-refunded"
                    logger.warning(
                        "payment.compensating_refund_triggered",
                        extra={
                            "order_id": str(order.id),
                            "payment_id": str(payment.id),
                            "provider_payment_id": provider_payment_id,
                            "reason": "Late capture received for already cancelled order",
                        },
                    )
                    try:
                        await provider.refund_payment(
                            provider_payment_id=provider_payment_id,
                            amount=float(payment.amount),
                            reason="Order reservation expired and cancelled before payment confirmation"
                        )
                    except Exception as refund_err:
                        logger.error(
                            f"CRITICAL: Failed to issue automated provider refund for {provider_payment_id} on cancelled order {order.id}: {refund_err}",
                            exc_info=True,
                        )
                elif order and order.status == OrderStatus.pending:
                    payment.status = PaymentStatus.captured
                    payment.provider_payment_id = provider_payment_id
                    payment.paid_at = datetime.now(timezone.utc)
                    # 4. Acquire InventoryReservation lock THIRD and consume
                    await consume_order_reservations(db, payment.order_id)
                    await transition_order(
                        db=db,
                        order_id=order.id,
                        to_status=OrderStatus.confirmed,
                        actor=None,
                        actor_role="system",
                        reason=f"Payment captured via provider webhook ({provider_payment_id})"
                    )
                else:
                    payment.status = PaymentStatus.captured
                    payment.provider_payment_id = provider_payment_id
                    payment.paid_at = datetime.now(timezone.utc)
                    
                try:
                    await db.commit()
                except IntegrityError:
                    await db.rollback()
                    logger.warning(f"Integrity error recording captured payment {provider_payment_id} in webhook")
                    return {"status": "conflict", "reason": "integrity_error"}
                
    elif event_type == "payment.failed":
        entity = event_data.get("payload", {}).get("payment", {}).get("entity", {})
        provider_order_id = entity.get("order_id")
        
        if provider_order_id:
            # 1. Non-locking lookup of order_id to enforce canonical lock hierarchy:
            #    Order -> Payment -> InventoryReservation -> Inventory
            order_id_stmt = select(Payment.order_id).where(Payment.provider_order_id == provider_order_id)
            order_id = (await db.execute(order_id_stmt)).scalar_one_or_none()
            if not order_id:
                logger.warning(f"Webhook payment.failed: No payment found for provider_order_id {provider_order_id}")
                return {"status": "ignored", "reason": "payment_record_not_found"}

            # 2. Acquire Order row lock FIRST
            order_stmt = select(Order).where(Order.id == order_id).with_for_update()
            order = (await db.execute(order_stmt)).scalar_one_or_none()

            # 3. Acquire Payment row lock SECOND
            stmt = select(Payment).where(Payment.provider_order_id == provider_order_id).with_for_update()
            payment = (await db.execute(stmt)).scalar_one_or_none()
            
            if payment and payment.status not in (PaymentStatus.captured, PaymentStatus.failed):
                payment.status = PaymentStatus.failed
                payment.failure_reason = entity.get("error_description", "Webhook reported failure")
                
                # 4. Exactly-once reservation release and stock restoration (Stage 8)
                #    Locks InventoryReservation THIRD and Inventory FOURTH (sorted product_id ASC)
                await release_order_reservations(
                    db=db,
                    order_id=payment.order_id,
                    release_reason=f"webhook_payment_failed: {payment.failure_reason}",
                    to_status=ReservationStatus.released,
                )
                
                if order and order.status == OrderStatus.pending:
                    await transition_order(
                        db=db,
                        order_id=order.id,
                        to_status=OrderStatus.cancelled,
                        actor=None,
                        actor_role="system",
                        reason="Payment failed via provider webhook",
                    )
                await db.commit()

    return {"status": "ok"}
