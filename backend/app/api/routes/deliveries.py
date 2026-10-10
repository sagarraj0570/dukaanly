import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.schemas.delivery import DeliveryResponse, DeliveryCreate, DeliveryAssign, DeliveryStatusUpdate
from app.services import delivery as delivery_service
from app.api.dependencies import get_current_user

router = APIRouter()

@router.post("", response_model=DeliveryResponse, status_code=201)
async def create_delivery(
    request: DeliveryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a delivery for a confirmed order."""
    return await delivery_service.create_delivery(
        db=db, 
        order_id=request.order_id, 
        owner=current_user,
        dest_lat=request.destination_latitude,
        dest_lon=request.destination_longitude
    )

@router.get("/{delivery_id}", response_model=DeliveryResponse)
async def get_delivery(
    delivery_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get delivery details."""
    return await delivery_service.get_delivery(db=db, delivery_id=delivery_id, actor=current_user)

@router.post("/{delivery_id}/assign", response_model=DeliveryResponse)
async def assign_delivery(
    delivery_id: uuid.UUID,
    request: DeliveryAssign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Assign a rider to a delivery."""
    return await delivery_service.assign_rider(db=db, delivery_id=delivery_id, rider_id=request.rider_id, owner=current_user)

@router.patch("/{delivery_id}/status", response_model=DeliveryResponse)
async def update_delivery_status(
    delivery_id: uuid.UUID,
    request: DeliveryStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update delivery operational status."""
    return await delivery_service.update_delivery_status(db=db, delivery_id=delivery_id, new_status=request.status, actor=current_user)

from app.schemas.delivery import RiderCandidateResponse

@router.get("/{delivery_id}/rider-candidates", response_model=list[RiderCandidateResponse])
async def get_rider_candidates(
    delivery_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get eligible riders nearby."""
    return await delivery_service.get_rider_candidates(db=db, delivery_id=delivery_id, actor=current_user)

@router.post("/{delivery_id}/auto-assign", response_model=DeliveryResponse)
async def auto_assign_delivery(
    delivery_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Automatically assign the nearest eligible rider."""
    return await delivery_service.auto_assign_delivery(db=db, delivery_id=delivery_id, actor=current_user)
