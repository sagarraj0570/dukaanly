from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from sqlalchemy import select, func, and_, exists
from app.core.config import settings
import uuid

async def get_rider_candidates(db, delivery_id, actor):
    pass
