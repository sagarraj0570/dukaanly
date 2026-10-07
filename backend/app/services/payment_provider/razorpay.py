import hmac
import hashlib
import json
import httpx
import uuid
from typing import Dict, Any
from app.core.config import settings
from app.services.payment_provider.base import PaymentProvider
from fastapi import HTTPException

class RazorpayPaymentProvider(PaymentProvider):
    def __init__(self):
        self.key_id = settings.RAZORPAY_KEY_ID
        self.key_secret = settings.RAZORPAY_KEY_SECRET
        self.webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
        self.is_mock = self.key_id == "mock_key_id" or not self.key_id
        
    async def create_payment_order(self, amount: float, currency: str, receipt_id: str) -> Dict[str, Any]:
        amount_paise = int(amount * 100)
        
        if self.is_mock:
            # Return mocked provider order
            return {
                "id": f"order_mock_{uuid.uuid4().hex[:10]}",
                "entity": "order",
                "amount": amount_paise,
                "currency": currency,
                "receipt": receipt_id,
                "status": "created"
            }
            
        auth = (self.key_id, self.key_secret)
        async with httpx.AsyncClient() as client:
            res = await client.post(
                "https://api.razorpay.com/v1/orders",
                auth=auth,
                json={
                    "amount": amount_paise,
                    "currency": currency,
                    "receipt": receipt_id
                }
            )
            if res.status_code != 200:
                raise HTTPException(500, "Failed to communicate with payment provider")
            return res.json()

    async def verify_payment(self, verification_data: Dict[str, Any]) -> bool:
        razorpay_order_id = verification_data.get("razorpay_order_id")
        razorpay_payment_id = verification_data.get("razorpay_payment_id")
        razorpay_signature = verification_data.get("razorpay_signature")
        
        if not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
            return False
            
        if self.is_mock:
            # Mock verification rule: signature must equal 'mock_signature_valid'
            return razorpay_signature == "mock_signature_valid"
            
        msg = f"{razorpay_order_id}|{razorpay_payment_id}"
        expected_signature = hmac.new(
            self.key_secret.encode(),
            msg.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, razorpay_signature)

    async def verify_webhook(self, payload: bytes, signature: str) -> Dict[str, Any]:
        if self.is_mock:
            if signature != "mock_webhook_signature_valid":
                raise HTTPException(400, "Invalid webhook signature")
            return json.loads(payload)
            
        if not self.webhook_secret:
            raise HTTPException(500, "Webhook secret not configured")
            
        expected_signature = hmac.new(
            self.webhook_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(expected_signature, signature):
            raise HTTPException(400, "Invalid webhook signature")
            
        return json.loads(payload)

# Global provider instance
def get_payment_provider() -> PaymentProvider:
    if settings.PAYMENT_PROVIDER == "razorpay":
        return RazorpayPaymentProvider()
    raise NotImplementedError(f"Provider {settings.PAYMENT_PROVIDER} not implemented")
