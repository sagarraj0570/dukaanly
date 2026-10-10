from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.rider import RiderProfileResponse, RiderAvailabilityUpdate
from app.schemas.delivery import DeliveryResponse
from app.services import rider as rider_service
from app.services import delivery as delivery_service
from app.api.dependencies import require_role

router = APIRouter()

@router.post("/profile", response_model=RiderProfileResponse, status_code=201)
async def create_rider_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.rider))
):
    """Create a rider profile for the current user."""
    return await rider_service.create_rider_profile(db=db, user=current_user)

@router.get("/me", response_model=RiderProfileResponse)
async def get_my_rider_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.rider))
):
    """Get the current rider's profile."""
    return await rider_service.get_rider_profile_by_user(db=db, user_id=current_user.id)

@router.patch("/me/availability", response_model=RiderProfileResponse)
async def update_my_availability(
    request: RiderAvailabilityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.rider))
):
    """Update the current rider's availability."""
    return await rider_service.update_rider_availability(db=db, user=current_user, is_available=request.is_available)

from app.schemas.rider import RiderLocationUpdate

@router.patch("/me/location", response_model=RiderProfileResponse)
async def update_my_location(
    request: RiderLocationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.rider))
):
    """Update the current rider's location."""
    return await rider_service.update_rider_location(db=db, user=current_user, latitude=request.latitude, longitude=request.longitude)


@router.get("/me/deliveries", response_model=list[DeliveryResponse])
async def get_my_deliveries(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.rider))
):
    """Get all deliveries assigned to the current rider."""
    page = (skip // limit) + 1
    return await delivery_service.get_rider_deliveries(db=db, actor=current_user, page=page, size=limit)
