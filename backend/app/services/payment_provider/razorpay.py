import hmac
import hashlib
import json
import httpx
import uuid
from typing import Dict, Any, Optional
from app.core.config import settings
from app.services.payment_provider.base import PaymentProvider
from fastapi import HTTPException, status

DEFAULT_MOCK_KEY_SECRET = "mock_secret_key_for_testing"
DEFAULT_MOCK_WEBHOOK_SECRET = "mock_webhook_secret_for_testing"

def compute_mock_razorpay_signature(order_id: str, payment_id: str, secret: Optional[str] = None) -> str:
    """Compute deterministic HMAC-SHA256 signature for mock payment verification."""
    key_secret = secret or settings.RAZORPAY_KEY_SECRET or DEFAULT_MOCK_KEY_SECRET
    msg = f"{order_id}|{payment_id}"
    return hmac.new(
        key_secret.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

def compute_mock_webhook_signature(payload: bytes | str, secret: Optional[str] = None) -> str:
    """Compute deterministic HMAC-SHA256 signature for mock webhook verification."""
    wh_secret = secret or settings.RAZORPAY_WEBHOOK_SECRET or DEFAULT_MOCK_WEBHOOK_SECRET
    payload_bytes = payload.encode("utf-8") if isinstance(payload, str) else payload
    return hmac.new(
        wh_secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()

class RazorpayPaymentProvider(PaymentProvider):
    _mock_orders: Dict[str, Dict[str, Any]] = {}
    _mock_exceptions: Dict[str, Exception] = {}

    @classmethod
    def set_mock_order_status(cls, order_id: str, status_str: str) -> None:
        if order_id in cls._mock_orders:
            cls._mock_orders[order_id]["status"] = status_str
        else:
            cls._mock_orders[order_id] = {
                "id": order_id,
                "entity": "order",
                "amount": 10000,
                "currency": "INR",
                "status": status_str,
                "attempts": 1 if status_str in ["paid", "captured"] else 0,
            }

    @classmethod
    def set_mock_fetch_exception(cls, order_id: str, exc: Optional[Exception]) -> None:
        if exc is None:
            cls._mock_exceptions.pop(order_id, None)
        else:
            cls._mock_exceptions[order_id] = exc

    @classmethod
    def reset_mock_state(cls) -> None:
        cls._mock_orders.clear()
        cls._mock_exceptions.clear()

    def __init__(self):
        self.key_id = settings.RAZORPAY_KEY_ID
        self.key_secret = settings.RAZORPAY_KEY_SECRET
        self.webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
        self.is_mock = self.key_id == "mock_key_id" or not self.key_id
        
        if self.is_mock and settings.APP_ENV == "production" and not settings.ALLOW_MOCK_PAYMENTS:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Mock payment provider is disabled in production without explicit ALLOW_MOCK_PAYMENTS policy."
            )
        
    async def create_payment_order(self, amount: float, currency: str, receipt_id: str) -> Dict[str, Any]:
        amount_paise = int(amount * 100)
        
        if self.is_mock:
            if settings.APP_ENV == "production" and not settings.ALLOW_MOCK_PAYMENTS:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Mock payment order creation is disabled in production."
                )
            # Return mocked provider order
            order_data = {
                "id": f"order_mock_{uuid.uuid4().hex[:10]}",
                "entity": "order",
                "amount": amount_paise,
                "currency": currency,
                "receipt": receipt_id,
                "status": "created",
                "attempts": 0,
            }
            self._mock_orders[order_data["id"]] = order_data
            return order_data
            
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
                raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to communicate with payment provider")
            return res.json()

    async def verify_payment(self, verification_data: Dict[str, Any]) -> bool:
        razorpay_order_id = verification_data.get("razorpay_order_id")
        razorpay_payment_id = verification_data.get("razorpay_payment_id")
        razorpay_signature = verification_data.get("razorpay_signature")
        
        if not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
            return False

        if self.is_mock:
            if settings.APP_ENV == "production" and not settings.ALLOW_MOCK_PAYMENTS:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Mock payment verification is disabled in production."
                )
            effective_secret = self.key_secret or DEFAULT_MOCK_KEY_SECRET
        else:
            effective_secret = self.key_secret

        if not effective_secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Payment secret is not configured."
            )

        # Validate signature format (HMAC-SHA256 hex digest must be 64 valid hex characters)
        if not isinstance(razorpay_signature, str) or len(razorpay_signature) != 64:
            return False
        try:
            int(razorpay_signature, 16)
        except ValueError:
            return False
            
        msg = f"{razorpay_order_id}|{razorpay_payment_id}"
        expected_signature = hmac.new(
            effective_secret.encode("utf-8"),
            msg.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, razorpay_signature)

    async def verify_webhook(self, payload: bytes, signature: str) -> Dict[str, Any]:
        if self.is_mock:
            if settings.APP_ENV == "production" and not settings.ALLOW_MOCK_PAYMENTS:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Mock webhook verification is disabled in production."
                )
            effective_secret = self.webhook_secret or DEFAULT_MOCK_WEBHOOK_SECRET
        else:
            effective_secret = self.webhook_secret

        if not effective_secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Webhook secret not configured."
            )

        if not signature or not isinstance(signature, str) or len(signature) != 64:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid webhook signature format")
        try:
            int(signature, 16)
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid webhook signature format")
            
        expected_signature = hmac.new(
            effective_secret.encode("utf-8"),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(expected_signature, signature):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid webhook signature")
            
        try:
            return json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed JSON payload in webhook")

    async def fetch_payment_order(self, provider_order_id: str) -> Dict[str, Any]:
        """
        Fetch authoritative payment order details and status from provider.
        """
        if self.is_mock:
            if provider_order_id in self._mock_exceptions:
                raise self._mock_exceptions[provider_order_id]
            order = self._mock_orders.get(provider_order_id)
            if order:
                return dict(order)
            return {
                "id": provider_order_id,
                "entity": "order",
                "amount": 0,
                "currency": "INR",
                "status": "created",
                "attempts": 0,
            }

        auth = (self.key_id, self.key_secret)
        async with httpx.AsyncClient() as client:
            res = await client.get(
                f"https://api.razorpay.com/v1/orders/{provider_order_id}",
                auth=auth,
                timeout=10.0,
            )
            if res.status_code != 200:
                raise HTTPException(
                    status.HTTP_502_BAD_GATEWAY,
                    f"Provider error fetching order {provider_order_id}: {res.text}"
                )
            return res.json()

    async def refund_payment(self, provider_payment_id: str, amount: float, reason: str = "") -> Dict[str, Any]:
        """
        Issue refund for a captured transaction (used in safe compensating workflows).
        """
        amount_paise = int(amount * 100)
        if self.is_mock:
            return {
                "id": f"rfnd_mock_{uuid.uuid4().hex[:10]}",
                "entity": "refund",
                "amount": amount_paise,
                "currency": "INR",
                "payment_id": provider_payment_id,
                "status": "processed",
                "notes": {"reason": reason},
            }

        auth = (self.key_id, self.key_secret)
        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"https://api.razorpay.com/v1/payments/{provider_payment_id}/refund",
                auth=auth,
                json={"amount": amount_paise, "notes": {"reason": reason}},
                timeout=10.0,
            )
            if res.status_code not in (200, 201):
                raise HTTPException(
                    status.HTTP_502_BAD_GATEWAY,
                    f"Provider refund failed: {res.text}"
                )
            return res.json()

# Global provider instance
def get_payment_provider() -> PaymentProvider:
    if settings.PAYMENT_PROVIDER == "razorpay":
        return RazorpayPaymentProvider()
    raise NotImplementedError(f"Provider {settings.PAYMENT_PROVIDER} not implemented")
