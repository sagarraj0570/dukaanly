from abc import ABC, abstractmethod
from typing import Dict, Any

class PaymentProvider(ABC):
    
    @abstractmethod
    async def create_payment_order(self, amount: float, currency: str, receipt_id: str) -> Dict[str, Any]:
        """
        Create a payment order on the provider side.
        Returns a dict containing provider-specific order details.
        """
        pass
        
    @abstractmethod
    async def verify_payment(self, verification_data: Dict[str, Any]) -> bool:
        """
        Verify payment cryptographic signature or status server-side.
        """
        pass
        
    @abstractmethod
    async def verify_webhook(self, payload: bytes, signature: str) -> Dict[str, Any]:
        """
        Verify webhook signature and return parsed event data.
        """
        pass

    @abstractmethod
    async def fetch_payment_order(self, provider_order_id: str) -> Dict[str, Any]:
        """
        Fetch authoritative payment order status and details from provider.
        Returns a dict containing entity fields such as 'id', 'status', 'amount', etc.
        """
        pass

    @abstractmethod
    async def refund_payment(self, provider_payment_id: str, amount: float, reason: str = "") -> Dict[str, Any]:
        """
        Trigger a refund for a captured payment as part of a safe compensating workflow.
        """
        pass
