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
