"""
Base abstractions, domain models, and interfaces for merchant listing providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

@dataclass
class AreaConfig:
    name: str = "Patna Commercial Envelope"
    city: str = "Patna"
    state: str = "Bihar"
    country: str = "India"
    min_lat: float = 25.5500
    max_lat: float = 25.6500
    min_lon: float = 85.0500
    max_lon: float = 85.2500

    def contains(self, lat: float, lon: float) -> bool:
        """Check if coordinates fall within the defined bounding envelope."""
        return self.min_lat <= lat <= self.max_lat and self.min_lon <= lon <= self.max_lon

@dataclass
class NormalizedListing:
    name: str
    category: str
    address: str
    latitude: float
    longitude: float
    source: str
    source_id: str
    source_attribution: str
    phone: Optional[str] = None
    opening_hours: Optional[str] = None
    original_url: Optional[str] = None
    imported_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw_data: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ImportSummary:
    provider: str
    area: str
    dry_run: bool = False
    batch_id: Optional[str] = None
    total_fetched: int = 0
    accepted: int = 0
    rejected_bounds: int = 0
    rejected_category: int = 0
    duplicates_source: int = 0
    duplicates_spatial: int = 0
    errors: List[str] = field(default_factory=list)
    records: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "provider": self.provider,
            "area": self.area,
            "dry_run": self.dry_run,
            "total_fetched": self.total_fetched,
            "accepted": self.accepted,
            "rejected_bounds": self.rejected_bounds,
            "rejected_category": self.rejected_category,
            "duplicates_source": self.duplicates_source,
            "duplicates_spatial": self.duplicates_spatial,
            "error_count": len(self.errors),
            "errors": self.errors,
            "record_count": len(self.records),
        }

class BaseListingProvider(ABC):
    """
    Abstract interface for public merchant listing providers.
    Allows swappable sources without altering shop discovery or checkout services.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique identifier for the listing provider (e.g., 'osm', 'curated')."""
        pass

    @property
    @abstractmethod
    def attribution(self) -> str:
        """Attribution notice required by source terms and licensing."""
        pass

    @abstractmethod
    async def fetch_candidate_listings(
        self,
        area: AreaConfig,
        categories: List[str],
        max_records: int = 100
    ) -> List[NormalizedListing]:
        """Fetch raw listings from the source and return normalized records."""
        pass

    @abstractmethod
    def validate_and_normalize(
        self,
        raw_item: Dict[str, Any],
        area: AreaConfig
    ) -> Optional[NormalizedListing]:
        """Validate single raw record and convert into NormalizedListing."""
        pass
