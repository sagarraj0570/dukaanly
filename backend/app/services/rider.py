from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
import uuid

from app.models.rider import RiderProfile
from app.models.user import User, UserRole

async def create_rider_profile(db: AsyncSession, user: User) -> RiderProfile:
    if user.role != UserRole.rider:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only users with rider role can create a rider profile")
        
    profile = RiderProfile(user_id=user.id)
    db.add(profile)
    try:
        await db.commit()
        await db.refresh(profile)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Rider profile already exists")
        
    return profile

async def get_rider_profile_by_user(db: AsyncSession, user_id: uuid.UUID) -> RiderProfile:
    stmt = select(RiderProfile).where(RiderProfile.user_id == user_id)
    profile = (await db.execute(stmt)).scalar_one_or_none()
    
    if not profile:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rider profile not found")
        
    return profile

async def update_rider_availability(db: AsyncSession, user: User, is_available: bool) -> RiderProfile:
    profile = await get_rider_profile_by_user(db, user.id)
    
    profile.is_available = is_available
    await db.commit()
    await db.refresh(profile)
    
    return profile

async def update_rider_location(db: AsyncSession, user: User, latitude: float, longitude: float) -> RiderProfile:
    profile = await get_rider_profile_by_user(db, user.id)
    
    point_wkt = f"SRID=4326;POINT({longitude} {latitude})"
    profile.location = point_wkt
    profile.location_updated_at = func.now()
    
    await db.commit()
    await db.refresh(profile)
    
    return profile
