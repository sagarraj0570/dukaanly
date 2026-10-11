import pytest
import uuid
from httpx import AsyncClient
import json

pytestmark = pytest.mark.asyncio

async def setup_test_data(async_client, engine):
    from sqlalchemy import text
    
    # 1. Setup owner and customer
    owner1_email = f"pay_owner_{uuid.uuid4()}@example.com"
    customer1_email = f"pay_cust1_{uuid.uuid4()}@example.com"
    
    await async_client.post("/api/v1/auth/register", json={"name": "Owner", "email": owner1_email, "password": "PassWord123"})
    await async_client.post("/api/v1/auth/register", json={"name": "Customer 1", "email": customer1_email, "password": "PassWord123"})
    
    async with engine.connect() as conn:
        await conn.execute(text("UPDATE users SET role = 'shop_owner' WHERE email = :e1"), {"e1": owner1_email})
        await conn.commit()
        
    token_owner = (await async_client.post("/api/v1/auth/login", json={"email": owner1_email, "password": "PassWord123"})).json()["access_token"]
    token_cust1 = (await async_client.post("/api/v1/auth/login", json={"email": customer1_email, "password": "PassWord123"})).json()["access_token"]
    
    # 2. Create shop & products
    shop1_id = (await async_client.post("/api/v1/shops", json={"name": "Pay Shop", "address": "1", "location": {"latitude": 1.0, "longitude": 1.0}}, headers={"Authorization": f"Bearer {token_owner}"})).json()["id"]
    p1_id = (await async_client.post(f"/api/v1/shops/{shop1_id}/products", json={"name": "Pay_P1", "price": 100.0}, headers={"Authorization": f"Bearer {token_owner}"})).json()["id"]
    await async_client.patch(f"/api/v1/products/{p1_id}/inventory", json={"stock": 10, "expected_version": 1}, headers={"Authorization": f"Bearer {token_owner}"})
    
    # 3. Create Order
    await async_client.post("/api/v1/cart/items", json={"product_id": p1_id, "quantity": 2}, headers={"Authorization": f"Bearer {token_cust1}"})
    order_id = (await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers={"Authorization": f"Bearer {token_cust1}"})).json()["id"]
    
    return token_cust1, order_id

async def test_payment_initiation_and_verification(async_client: AsyncClient):
    from app.db.session import engine
    token_cust1, order_id = await setup_test_data(async_client, engine)
    headers = {"Authorization": f"Bearer {token_cust1}"}
    
    # 1. Initiate Payment
    init_res = await async_client.post(f"/api/v1/orders/{order_id}/payment", headers=headers)
    assert init_res.status_code == 200
    init_data = init_res.json()
    assert init_data["amount"] == "200.00"
    assert "provider_order_id" in init_data
    
    provider_order_id = init_data["provider_order_id"]
    
    # 2. Verify Payment (Valid Signature)
    verify_req = {
        "razorpay_order_id": provider_order_id,
        "razorpay_payment_id": f"pay_mock_{uuid.uuid4().hex[:6]}",
        "razorpay_signature": "mock_signature_valid" # Valid in mock provider
    }
    verify_res = await async_client.post("/api/v1/payments/verify", json=verify_req, headers=headers)
    assert verify_res.status_code == 200
    assert verify_res.json()["status"] == "captured"
    
    # 3. Check Order state (Should be 'confirmed')
    order_res = await async_client.get(f"/api/v1/orders/{order_id}", headers=headers)
    assert order_res.json()["status"] == "confirmed"
    
    # 4. Check Idempotency (Repeat verify with SAME payload)
    verify_res2 = await async_client.post("/api/v1/payments/verify", json=verify_req, headers=headers)
    assert verify_res2.status_code == 200
    
    # 5. Prevent double initiation
    init_res2 = await async_client.post(f"/api/v1/orders/{order_id}/payment", headers=headers)
    assert init_res2.status_code == 400
    assert "payable state" in init_res2.json()["detail"]

async def test_invalid_signature_and_webhooks(async_client: AsyncClient):
    from app.db.session import engine
    token_cust1, order_id = await setup_test_data(async_client, engine)
    headers = {"Authorization": f"Bearer {token_cust1}"}
    
    # Initiate Payment
    init_data = (await async_client.post(f"/api/v1/orders/{order_id}/payment", headers=headers)).json()
    provider_order_id = init_data["provider_order_id"]
    
    # Test Invalid Signature (Verification)
    verify_req = {
        "razorpay_order_id": provider_order_id,
        "razorpay_payment_id": f"pay_mock_{uuid.uuid4().hex[:6]}",
        "razorpay_signature": "mock_signature_invalid"
    }
    verify_res = await async_client.post("/api/v1/payments/verify", json=verify_req, headers=headers)
    assert verify_res.status_code == 400
    
    # Test Webhook Capture (Valid Signature)
    payment_id = f"pay_mock_{uuid.uuid4().hex[:6]}"
    webhook_payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": provider_order_id
                }
            }
        }
    }
    webhook_res = await async_client.post(
        "/api/v1/payments/webhook", 
        content=json.dumps(webhook_payload).encode(),
        headers={"x-razorpay-signature": "mock_webhook_signature_valid"}
    )
    assert webhook_res.status_code == 200
    
    # Order should now be confirmed because of webhook
    order_res = await async_client.get(f"/api/v1/orders/{order_id}", headers=headers)
    assert order_res.json()["status"] == "confirmed"
    
    # Test Webhook Invalid Signature
    webhook_res_invalid = await async_client.post(
        "/api/v1/payments/webhook", 
        content=json.dumps(webhook_payload).encode(),
        headers={"x-razorpay-signature": "mock_webhook_signature_invalid"}
    )
    assert webhook_res_invalid.status_code == 400

async def test_mock_payment_blocked_in_production_without_flag(async_client: AsyncClient):
    from app.core.config import settings
    orig_env = settings.APP_ENV
    orig_allow = settings.ALLOW_MOCK_PAYMENTS
    try:
        settings.APP_ENV = "production"
        settings.ALLOW_MOCK_PAYMENTS = False
        
        from app.services.payment_provider.razorpay import RazorpayPaymentProvider
        with pytest.raises(Exception) as exc_info:
            RazorpayPaymentProvider()
        assert "disabled in production" in str(exc_info.value.detail)
    finally:
        settings.APP_ENV = orig_env
        settings.ALLOW_MOCK_PAYMENTS = orig_allow

