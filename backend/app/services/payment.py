import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.models.payment import Payment, PaymentStatus
from app.models.order import Order, OrderStatus
from app.models.user import User
from app.schemas.payment import PaymentInitiationResponse, PaymentVerificationRequest, PaymentResponse
from app.services.payment_provider import get_payment_provider
from app.core.config import settings

async def initiate_payment(db: AsyncSession, order_id: uuid.UUID, customer: User) -> PaymentInitiationResponse:
    # 1. Verify Order Ownership and State
    stmt = select(Order).where(Order.id == order_id)
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

    # 3. Create Provider Order using authoritative amount
    provider = get_payment_provider()
    receipt_id = str(order.id)
    
    provider_order = await provider.create_payment_order(
        amount=float(order.total_amount),
        currency=settings.CURRENCY,
        receipt_id=receipt_id
    )

    # 4. Create/Update Local Payment Record
    # Check if a payment record already exists and is pending
    pending_stmt = select(Payment).where(Payment.order_id == order_id, Payment.status == PaymentStatus.created)
    payment = (await db.execute(pending_stmt)).scalar_one_or_none()
    
    if payment:
        payment.provider_order_id = provider_order["id"]
        payment.amount = order.total_amount
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

    return PaymentInitiationResponse(
        payment_id=payment.id,
        order_id=order.id,
        provider=settings.PAYMENT_PROVIDER,
        provider_order_id=provider_order["id"],
        amount=order.total_amount,
        currency=settings.CURRENCY,
        key_id=settings.RAZORPAY_KEY_ID
    )

async def verify_payment(db: AsyncSession, verification_data: PaymentVerificationRequest, customer: User) -> PaymentResponse:
    provider_order_id = verification_data.razorpay_order_id
    
    # Fetch local payment record
    stmt = select(Payment).where(Payment.provider_order_id == provider_order_id)
    payment = (await db.execute(stmt)).scalar_one_or_none()
    
    if not payment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment record not found")
        
    # Verify ownership of the associated order
    order_stmt = select(Order).where(Order.id == payment.order_id)
    order = (await db.execute(order_stmt)).scalar_one_or_none()
    
    if not order or order.customer_id != customer.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to verify this payment")
        
    if payment.status == PaymentStatus.captured:
        return payment # Idempotent response
        
    # Cryptographic verification
    provider = get_payment_provider()
    is_valid = await provider.verify_payment(verification_data.model_dump())
    
    if not is_valid:
        payment.status = PaymentStatus.failed
        payment.failure_reason = "Signature verification failed"
        await db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment signature verification failed")
        
    # Mark payment as captured
    payment.status = PaymentStatus.captured
    payment.provider_payment_id = verification_data.razorpay_payment_id
    payment.paid_at = datetime.now(timezone.utc)
    
    # We do NOT mark order as delivered. Order remains confirmed.
    order.status = OrderStatus.confirmed
    
    await db.commit()
    await db.refresh(payment)
    return payment

async def process_webhook(db: AsyncSession, payload: bytes, signature: str) -> dict:
    provider = get_payment_provider()
    event_data = await provider.verify_webhook(payload, signature)
    
    event_type = event_data.get("event")
    
    if event_type == "payment.captured":
        # Usually contains the order ID in payload["payload"]["payment"]["entity"]["order_id"]
        entity = event_data.get("payload", {}).get("payment", {}).get("entity", {})
        provider_order_id = entity.get("order_id")
        provider_payment_id = entity.get("id")
        
        if provider_order_id:
            stmt = select(Payment).where(Payment.provider_order_id == provider_order_id)
            payment = (await db.execute(stmt)).scalar_one_or_none()
            
            if payment and payment.status != PaymentStatus.captured:
                payment.status = PaymentStatus.captured
                payment.provider_payment_id = provider_payment_id
                payment.paid_at = datetime.now(timezone.utc)
                
                # Fetch order to update status
                order_stmt = select(Order).where(Order.id == payment.order_id)
                order = (await db.execute(order_stmt)).scalar_one_or_none()
                if order and order.status == OrderStatus.pending:
                    order.status = OrderStatus.confirmed
                    
                await db.commit()
                
    elif event_type == "payment.failed":
        entity = event_data.get("payload", {}).get("payment", {}).get("entity", {})
        provider_order_id = entity.get("order_id")
        
        if provider_order_id:
            stmt = select(Payment).where(Payment.provider_order_id == provider_order_id)
            payment = (await db.execute(stmt)).scalar_one_or_none()
            
            if payment and payment.status not in (PaymentStatus.captured, PaymentStatus.failed):
                payment.status = PaymentStatus.failed
                payment.failure_reason = entity.get("error_description", "Webhook reported failure")
                await db.commit()

    return {"status": "ok"}
