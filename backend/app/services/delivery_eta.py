"""
Smart Delivery ETA Domain & Calculation Service for Dukaanly.
Features:
- Deterministic, phase-aware calculations deducting elapsed preparation time.
- Dynamic component breakdowns: prep remaining, assignment wait, pickup travel, pickup buffer, dropoff travel, handoff buffer.
- Phase-tightening arrival windows: [now + earliest, now + latest].
- Clear source attribution: 'osrm' (verified road network), 'fallback_estimate', or 'unavailable'.
- Meaningful delay explanations without presenting estimates as guarantees.
- PostgreSQL persistence and Redis/WebSocket publication.
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from fastapi import HTTPException, status
from geoalchemy2.shape import to_shape

from app.core.config import settings
from app.models.delivery import Delivery, DeliveryStatus
from app.models.order import Order, OrderStatus
from app.models.user import User, UserRole
from app.models.rider import RiderProfile
from app.models.shop import Shop
from app.schemas.delivery import (
    DeliveryEtaResponse,
    DeliveryEtaDetail,
    DeliveryEtaBreakdown,
)
from app.services.osrm import (
    osrm_service,
    OSRMError,
    haversine_distance,
    estimate_fallback_duration,
)
from app.websockets.redis_pubsub import publish_delivery_event

logger = logging.getLogger(__name__)


def calculate_eta_components(
    delivery_status: DeliveryStatus,
    prep_expected_seconds: int,
    prep_elapsed_seconds: int,
    pickup_travel_seconds: int,
    dropoff_travel_seconds: int,
    source: str = "osrm",
    now: Optional[datetime] = None,
    delay_reason_override: Optional[str] = None,
    created_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Pure, deterministic ETA calculation based on delivery phase and elapsed progress.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # 1. Terminal / Completed States
    if delivery_status in [DeliveryStatus.delivered, DeliveryStatus.cancelled]:
        return {
            "remaining_seconds": 0,
            "earliest_at": now,
            "latest_at": now,
            "source": source,
            "is_estimated": False,
            "calculated_at": now,
            "breakdown": {
                "preparation_remaining_seconds": 0,
                "assignment_wait_seconds": 0,
                "pickup_travel_remaining_seconds": 0,
                "pickup_buffer_seconds": 0,
                "dropoff_travel_seconds": 0,
                "handoff_buffer_seconds": 0,
            },
            "delay_explanation": None,
        }

    # 2. Remaining preparation time
    prep_remaining_seconds = max(0, prep_expected_seconds - prep_elapsed_seconds)

    # 3. Phase-specific component resolution
    if delivery_status == DeliveryStatus.pending:
        # Order confirmed, no rider assigned yet
        assignment_wait = settings.ETA_ASSIGNMENT_WAIT_BUFFER_SECONDS
        pickup_travel = 0
        pickup_buffer = settings.ETA_PICKUP_BUFFER_SECONDS
        dropoff_travel = dropoff_travel_seconds
        handoff_buffer = settings.ETA_DROPOFF_BUFFER_SECONDS
        prep_remaining = prep_remaining_seconds
        uncertainty_buffer = 360  # 6 min uncertainty

    elif delivery_status == DeliveryStatus.assigned:
        # Rider assigned, heading to shop
        assignment_wait = 0
        pickup_travel = pickup_travel_seconds
        pickup_buffer = settings.ETA_PICKUP_BUFFER_SECONDS
        dropoff_travel = dropoff_travel_seconds
        handoff_buffer = settings.ETA_DROPOFF_BUFFER_SECONDS
        prep_remaining = prep_remaining_seconds
        uncertainty_buffer = settings.ETA_UNCERTAINTY_BUFFER_SECONDS  # 5 min uncertainty

    elif delivery_status in [DeliveryStatus.picked_up, DeliveryStatus.out_for_delivery]:
        # Order picked up, on the road to customer
        assignment_wait = 0
        prep_remaining = 0  # Food already cooked!
        pickup_travel = 0   # Already at shop / picked up!
        pickup_buffer = 0   # Pickup completed!
        dropoff_travel = dropoff_travel_seconds
        handoff_buffer = settings.ETA_DROPOFF_BUFFER_SECONDS
        uncertainty_buffer = 180  # 3 min uncertainty (food on the road)

    else:
        # Fallback for unexpected status
        assignment_wait = 0
        pickup_travel = pickup_travel_seconds
        pickup_buffer = 0
        dropoff_travel = dropoff_travel_seconds
        handoff_buffer = settings.ETA_DROPOFF_BUFFER_SECONDS
        prep_remaining = prep_remaining_seconds
        uncertainty_buffer = settings.ETA_UNCERTAINTY_BUFFER_SECONDS

    total_remaining = (
        prep_remaining
        + assignment_wait
        + pickup_travel
        + pickup_buffer
        + dropoff_travel
        + handoff_buffer
    )

    earliest_seconds = max(0, total_remaining - uncertainty_buffer)
    latest_seconds = total_remaining + uncertainty_buffer

    earliest_at = now + timedelta(seconds=earliest_seconds)
    latest_at = now + timedelta(seconds=latest_seconds)

    # 4. Contextual delay explanation
    delay_explanation = delay_reason_override
    if not delay_explanation:
        if delivery_status in [DeliveryStatus.pending, DeliveryStatus.assigned] and prep_elapsed_seconds > prep_expected_seconds:
            delay_explanation = "Your shop is taking a little extra time to prepare your order fresh."
        elif delivery_status == DeliveryStatus.pending and created_at and (now - created_at).total_seconds() > 300:
            delay_explanation = "Looking for an available delivery partner nearby."

    return {
        "remaining_seconds": int(total_remaining),
        "earliest_at": earliest_at,
        "latest_at": latest_at,
        "source": source,
        "is_estimated": True,
        "calculated_at": now,
        "breakdown": {
            "preparation_remaining_seconds": int(prep_remaining),
            "assignment_wait_seconds": int(assignment_wait),
            "pickup_travel_remaining_seconds": int(pickup_travel),
            "pickup_buffer_seconds": int(pickup_buffer),
            "dropoff_travel_seconds": int(dropoff_travel),
            "handoff_buffer_seconds": int(handoff_buffer),
        },
        "delay_explanation": delay_explanation,
    }


class DeliveryEtaService:
    """
    Manages ETA calculation, road route fetching, persistence, and event distribution.
    """

    async def calculate_delivery_eta(
        self,
        delivery: Delivery,
        shop: Optional[Shop] = None,
        rider: Optional[RiderProfile] = None,
        now: Optional[datetime] = None,
        travel_override: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Calculate phase-aware ETA for a delivery model instance.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        # 1. Terminal delivery check
        if delivery.status in [DeliveryStatus.delivered, DeliveryStatus.cancelled]:
            return calculate_eta_components(
                delivery_status=delivery.status,
                prep_expected_seconds=0,
                prep_elapsed_seconds=0,
                pickup_travel_seconds=0,
                dropoff_travel_seconds=0,
                source="osrm",
                now=now,
            )

        # 2. Preparation parameters
        prep_minutes = (
            delivery.preparation_estimated_minutes
            if delivery.preparation_estimated_minutes is not None
            else settings.ETA_DEFAULT_PREPARATION_MINUTES
        )
        prep_expected_seconds = prep_minutes * 60

        prep_elapsed_seconds = 0
        if delivery.preparation_started_at:
            prep_elapsed_seconds = max(
                0, int((now - delivery.preparation_started_at).total_seconds())
            )

        # 3. Resolve Coordinates
        shop_lat, shop_lon = None, None
        if shop and shop.location:
            pt = to_shape(shop.location)
            shop_lat, shop_lon = float(pt.y), float(pt.x)

        dest_lat, dest_lon = None, None
        if delivery.destination_location:
            pt = to_shape(delivery.destination_location)
            dest_lat, dest_lon = float(pt.y), float(pt.x)

        rider_lat, rider_lon = None, None
        active_rider = rider or delivery.rider
        if active_rider and active_rider.location:
            pt = to_shape(active_rider.location)
            rider_lat, rider_lon = float(pt.y), float(pt.x)

        # 4. Resolve Road Travel Durations (OSRM or Fallback)
        pickup_travel_seconds = 0
        dropoff_travel_seconds = 0
        source = "osrm"

        if travel_override is not None:
            pickup_travel_seconds = travel_override.get("pickup_travel_seconds", 0)
            dropoff_travel_seconds = travel_override.get("dropoff_travel_seconds", 0)
            source = travel_override.get("source", "osrm")

        elif dest_lat is not None and dest_lon is not None and shop_lat is not None and shop_lon is not None:
            try:
                # Pickup Travel: only relevant if rider assigned and not yet picked up
                if delivery.status == DeliveryStatus.assigned and rider_lat is not None and rider_lon is not None:
                    pickup_route = await osrm_service.get_two_point_route(
                        start_lat=rider_lat,
                        start_lon=rider_lon,
                        end_lat=shop_lat,
                        end_lon=shop_lon,
                        from_name="Rider",
                        to_name="Shop",
                    )
                    pickup_travel_seconds = int(pickup_route.get("duration_seconds", 0))

                # Dropoff Travel:
                # If order picked up/out for delivery, route from Rider's current location -> Customer
                # If still at shop, route from Shop -> Customer
                start_dropoff_lat = rider_lat if (delivery.status in [DeliveryStatus.picked_up, DeliveryStatus.out_for_delivery] and rider_lat is not None) else shop_lat
                start_dropoff_lon = rider_lon if (delivery.status in [DeliveryStatus.picked_up, DeliveryStatus.out_for_delivery] and rider_lon is not None) else shop_lon

                dropoff_route = await osrm_service.get_two_point_route(
                    start_lat=start_dropoff_lat,
                    start_lon=start_dropoff_lon,
                    end_lat=dest_lat,
                    end_lon=dest_lon,
                    from_name="Origin",
                    to_name="Customer",
                )
                dropoff_travel_seconds = int(dropoff_route.get("duration_seconds", 0))

            except OSRMError as e:
                logger.warning(f"OSRM unavailable for ETA calculation ({e}). Using labelled fallback estimate.")
                source = "fallback_estimate"
                # Conservative fallback road duration based on 22 km/h urban speed
                dist_meters = haversine_distance(shop_lat, shop_lon, dest_lat, dest_lon) * 1.3
                dropoff_travel_seconds = int(estimate_fallback_duration(dist_meters))
                if delivery.status == DeliveryStatus.assigned and rider_lat is not None and rider_lon is not None:
                    pickup_dist = haversine_distance(rider_lat, rider_lon, shop_lat, shop_lon) * 1.3
                    pickup_travel_seconds = int(estimate_fallback_duration(pickup_dist))

        else:
            source = "unavailable"
            dropoff_travel_seconds = 0
            pickup_travel_seconds = 0

        # 5. Compute full breakdown
        calc_result = calculate_eta_components(
            delivery_status=delivery.status,
            prep_expected_seconds=prep_expected_seconds,
            prep_elapsed_seconds=prep_elapsed_seconds,
            pickup_travel_seconds=pickup_travel_seconds,
            dropoff_travel_seconds=dropoff_travel_seconds,
            source=source,
            now=now,
            delay_reason_override=delivery.eta_delay_reason,
            created_at=delivery.created_at,
        )

        return calc_result

    async def update_and_persist_delivery_eta(
        self,
        db: AsyncSession,
        delivery_id: uuid.UUID,
        update_reason: Optional[str] = None,
        force: bool = False,
    ) -> DeliveryEtaResponse:
        """
        Calculates and persists the authoritative ETA snapshot to PostgreSQL,
        then broadcasts the update over Redis Pub/Sub for connected WebSockets.
        """
        stmt = (
            select(Delivery)
            .options(
                joinedload(Delivery.order).joinedload(Order.shop),
                joinedload(Delivery.rider),
            )
            .where(Delivery.id == delivery_id)
        )
        delivery = (await db.execute(stmt)).scalar_one_or_none()
        if not delivery:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery not found")

        now = datetime.now(timezone.utc)

        # Throttling check: avoid thrashing calculations if recently calculated unless forced or status changed
        if not force and delivery.eta_calculated_at:
            elapsed_since_calc = (now - delivery.eta_calculated_at).total_seconds()
            if elapsed_since_calc < settings.ETA_MIN_RECALC_INTERVAL_SECONDS:
                logger.debug(f"ETA calculation throttled for delivery {delivery_id} (elapsed: {elapsed_since_calc}s)")
                await db.rollback()
                return self._build_response(delivery)

        shop = delivery.order.shop if delivery.order else None
        rider = delivery.rider

        calc_data = await self.calculate_delivery_eta(
            delivery=delivery,
            shop=shop,
            rider=rider,
            now=now,
        )

        # Persist to database
        delivery.eta_earliest_at = calc_data["earliest_at"]
        delivery.eta_latest_at = calc_data["latest_at"]
        delivery.eta_remaining_seconds = calc_data["remaining_seconds"]
        delivery.eta_source = calc_data["source"]
        delivery.eta_calculated_at = now
        delivery.eta_version = (delivery.eta_version or 0) + 1
        if update_reason:
            delivery.eta_update_reason = update_reason

        db.add(delivery)
        await db.commit()
        await db.refresh(delivery)

        response = self._build_response(delivery, calc_data=calc_data)

        # Distribute via WebSocket after successful commit
        try:
            await publish_delivery_event(str(delivery.id), {
                "event": "delivery.eta_updated",
                "version": delivery.eta_version,
                "delivery_id": str(delivery.id),
                "timestamp": now.isoformat(),
                "data": response.model_dump(mode="json"),
            })
        except Exception as e:
            logger.warning(f"Failed to publish delivery.eta_updated event: {e}")

        return response

    def _build_response(
        self,
        delivery: Delivery,
        calc_data: Optional[Dict[str, Any]] = None,
    ) -> DeliveryEtaResponse:
        """
        Builds a normalized DeliveryEtaResponse from delivery snapshot or calculation data.
        """
        if calc_data:
            breakdown_dict = calc_data["breakdown"]
            source = calc_data["source"]
            is_estimated = calc_data["is_estimated"]
            delay_explanation = calc_data["delay_explanation"]
            remaining_seconds = calc_data["remaining_seconds"]
            earliest_at = calc_data["earliest_at"]
            latest_at = calc_data["latest_at"]
            calculated_at = calc_data["calculated_at"]
        else:
            remaining_seconds = delivery.eta_remaining_seconds or 0
            earliest_at = delivery.eta_earliest_at
            latest_at = delivery.eta_latest_at
            calculated_at = delivery.eta_calculated_at
            source = delivery.eta_source or "unavailable"
            is_estimated = delivery.status not in [DeliveryStatus.delivered, DeliveryStatus.cancelled]
            delay_explanation = delivery.eta_delay_reason
            # Estimate breakdown approximation from snapshot
            breakdown_dict = {
                "preparation_remaining_seconds": 0,
                "assignment_wait_seconds": 0,
                "pickup_travel_remaining_seconds": 0,
                "pickup_buffer_seconds": 0,
                "dropoff_travel_seconds": remaining_seconds,
                "handoff_buffer_seconds": settings.ETA_DROPOFF_BUFFER_SECONDS if remaining_seconds > 0 else 0,
            }

        return DeliveryEtaResponse(
            delivery_id=delivery.id,
            status=delivery.status,
            eta=DeliveryEtaDetail(
                earliest_at=earliest_at,
                latest_at=latest_at,
                remaining_seconds=remaining_seconds,
                source=source,
                is_estimated=is_estimated,
                calculated_at=calculated_at,
            ),
            breakdown=DeliveryEtaBreakdown(**breakdown_dict),
            update_reason=delivery.eta_update_reason,
            delay_explanation=delay_explanation,
        )


eta_service = DeliveryEtaService()
