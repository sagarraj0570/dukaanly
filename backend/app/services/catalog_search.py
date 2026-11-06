"""
Catalog Search Service for Dukaanly AI Shopping Assistant.
Authoritative retrieval strictly scoped to verified, orderable partner shops
within the customer's 5 km delivery serviceability radius.
"""

from decimal import Decimal
import logging
import re
from typing import Any, Dict, List, Optional
import uuid

from geoalchemy2 import Geography
from geoalchemy2.shape import to_shape
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import cast, func, or_, select, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inventory import Inventory
from app.models.product import Product
from app.models.shop import Shop, ShopVerificationStatus

logger = logging.getLogger(__name__)

DEFAULT_DELIVERY_RADIUS_METERS = 5000  # 5 km standard delivery serviceability limit
MAX_SEARCH_RADIUS_METERS = 10000       # Allow up to 10 km for metro-wide urban search

COMMON_STOP_WORDS = {
    "for", "in", "at", "to", "of", "and", "the", "a", "an", "is", "with", "from",
    "hai", "ke", "ka", "ki", "ko", "se", "aur", "chahiye", "bhejo", "kar", "do",
    "bhaiya", "ek", "kya", "toh", "ye", "woh", "ho", "dusra", "ya",
    "nearby", "near", "shop", "shops", "store", "stores", "dukaan", "dukan", "pass", "paas",
    "item", "items", "kuch", "some", "any", "please", "plz", "bhejiye", "order", "delivery",
    "और", "का", "की", "के", "को", "में", "से", "है", "हैं", "चाहिए", "दो", "कर", "एक", "क्या", "तो"
}

# Common Indian grocery synonyms and Hinglish mappings
# Common Indian grocery synonyms, Hinglish, Devanagari Hindi, and typo mappings
GROCERY_SYNONYMS: Dict[str, List[str]] = {
    # Hinglish & English Synonyms
    "snack": ["snack", "snacks", "namkeen", "chips", "biscuit", "cookies", "bhujia"],
    "snacks": ["snack", "snacks", "namkeen", "chips", "biscuit", "cookies", "bhujia"],
    "biscuit": ["biscuit", "biscuits", "cookie", "cookies", "parle", "britannia"],
    "biscuits": ["biscuit", "biscuits", "cookie", "cookies", "parle", "britannia"],
    "cookie": ["cookie", "cookies", "biscuit", "biscuits"],
    "cookies": ["cookie", "cookies", "biscuit", "biscuits"],
    "namkeen": ["namkeen", "bhujia", "mixture", "snack"],
    "chips": ["chips", "lays", "kurkure", "snack"],
    "bhujia": ["bhujia", "namkeen", "sev", "haldiram"],
    "doodh": ["milk", "doodh"],
    "atta": ["flour", "wheat", "aata", "atta", "aashirvaad"],
    "aata": ["flour", "wheat", "atta", "aata", "aashirvaad"],
    "tel": ["oil", "mustard", "sunflower", "fortune"],
    "cheeni": ["sugar"],
    "chini": ["sugar"],
    "chawal": ["rice", "basmati", "india gate"],
    "anda": ["egg"],
    "ande": ["egg", "eggs"],
    "makkhan": ["butter", "makkhan"],
    "dahi": ["curd", "yogurt"],
    "chai": ["tea", "patti"],
    "patti": ["tea"],
    "namak": ["salt"],
    "masala": ["spice", "mdh", "haldi"],
    "haldi": ["turmeric", "haldi", "spice"],
    "sabzi": ["vegetable"],
    "sabji": ["vegetable"],
    "aloo": ["potato"],
    "aaloo": ["potato"],
    "pyaaz": ["onion"],
    "pyaz": ["onion"],
    "tamatar": ["tomato"],
    "paneer": ["paneer", "cheese"],
    "dal": ["dal", "lentil", "pulse", "arhar", "toor"],
    "daal": ["dal", "lentil", "pulse", "arhar", "toor"],
    "biskut": ["biscuit", "cookie", "parle"],
    "biscuit": ["biscuit", "cookie", "parle"],
    "maggi": ["noodles", "instant", "maggi"],
    "dawa": ["medicine"],
    "pani": ["water"],
    "sattu": ["sattu", "gram", "flour"],
    "makhana": ["makhana", "fox nut", "snack"],
    "litti": ["sattu", "atta", "flour"],
    "bread": ["bread", "bakery"],
    "butter": ["butter", "makkhan"],
    "oil": ["oil", "sunflower", "mustard", "fortune"],
    "rice": ["rice", "basmati", "chawal"],
    "flour": ["atta", "flour", "wheat"],
    "soap": ["soap", "dettol", "bath"],
    "shampoo": ["shampoo", "hair"],

    # Devanagari Hindi Script
    "दूध": ["milk", "doodh", "taaza"],
    "आटा": ["atta", "flour", "wheat", "aashirvaad"],
    "आशीर्वाद": ["aashirvaad", "atta", "flour"],
    "चावल": ["rice", "basmati", "chawal"],
    "बासमती": ["basmati", "rice", "chawal"],
    "दाल": ["dal", "lentil", "pulse", "arhar"],
    "चीनी": ["sugar", "chini"],
    "तेल": ["oil", "mustard", "sunflower", "fortune"],
    "फॉर्च्यून": ["fortune", "oil", "sunflower"],
    "चाय": ["tea", "chai", "patti"],
    "पत्ती": ["tea", "chai", "patti"],
    "नमक": ["salt"],
    "टाटा": ["tata"],
    "मक्खन": ["butter", "makkhan"],
    "दही": ["curd", "yogurt"],
    "अंडा": ["egg", "anda"],
    "अंडे": ["egg", "eggs", "ande"],
    "ताजा": ["fresh", "taaza"],
    "अमूल": ["amul"],
    "बिस्कुट": ["biscuit", "cookie", "parle"],
    "पारले": ["parle", "biscuit"],
    "मैगी": ["maggi", "noodles", "instant"],
    "नूडल्स": ["noodles", "maggi", "instant"],
    "पनीर": ["paneer", "cheese"],
    "मसाला": ["spice", "masala", "mdh"],
    "हल्दी": ["turmeric", "haldi", "spice"],
    "आलू": ["potato", "aloo"],
    "प्याज": ["onion", "pyaaz"],
    "टमाटर": ["tomato", "tamatar"],
    "सत्तू": ["sattu", "gram", "flour"],
    "साबुन": ["soap", "dettol"],
    "ब्रेड": ["bread", "bakery"],
    "नाश्ता": ["snack", "biscuit", "noodles", "bread"],

    # Common Phonetic / Transposition Typos
    "ashirwad": ["aashirvaad", "atta", "flour"],
    "aashirvad": ["aashirvaad", "atta", "flour"],
    "ata": ["atta", "flour", "wheat"],
    "nodles": ["noodles", "maggi"],
    "noddles": ["noodles", "maggi"],
    "magi": ["maggi", "noodles"],
    "biscut": ["biscuit", "cookie"],
    "buter": ["butter"],
    "chawl": ["chawal", "rice"],
    "oyl": ["oil", "fortune"],
    "tazza": ["taaza", "milk"],
    "slatt": ["salt", "tata"],
    "shuger": ["sugar"],
    "milkk": ["milk"],
    "amull": ["amul"],
    "fortuen": ["fortune", "oil"],
    "basmti": ["basmati", "rice"],
    "indya": ["india", "gate", "rice"],
    "detol": ["dettol", "soap"],

    # Substitutions / Category Alternatives
    "substitute": ["alternative", "similar"],
    "alternative": ["similar", "other"],
}


def validate_coordinates(latitude: float, longitude: float) -> bool:
    """
    Validate that coordinates are strictly within valid geographic bounds
    and not Null Island (0.0, 0.0).
    """
    if latitude == 0.0 and longitude == 0.0:
        return False
    if not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
        return False
    return True


class CatalogProductItem(BaseModel):
    product_id: uuid.UUID
    product_name: str
    product_description: Optional[str] = None
    category: Optional[str] = None
    price: Decimal
    stock: int
    image_url: Optional[str] = None
    thumb_url: Optional[str] = None
    shop_id: uuid.UUID
    shop_name: str
    shop_address: str
    distance_meters: float
    is_delivery_eligible: bool = True

    model_config = ConfigDict(from_attributes=True)


async def search_partner_catalog(
    db: AsyncSession,
    latitude: float,
    longitude: float,
    query: Optional[str] = None,
    category: Optional[str] = None,
    shop_id: Optional[uuid.UUID] = None,
    max_results: int = 15,
    max_radius_meters: int = DEFAULT_DELIVERY_RADIUS_METERS,
) -> List[CatalogProductItem]:
    """
    Search for active, in-stock products strictly belonging to verified, orderable partner shops
    within the 5 km delivery serviceability boundary.
    
    Invariants enforced:
    1. Valid geographic coordinates (non-zero, within [-90, 90] & [-180, 180])
    2. Shop.is_active is True
    3. Shop.is_orderable is True (excludes directory-only OSM/Geoapify listings)
    4. Shop.verification_status == ShopVerificationStatus.verified
    5. Shop.owner_id is NOT None (registered merchant on Dukaanly)
    6. Product.is_active is True
    7. Inventory.stock > 0 (excludes out-of-stock items)
    8. PostGIS ST_DWithin ellipsoidal distance <= 5,000 meters
    9. Synonym and Hinglish expansion for common Indian grocery queries
    """
    # Reject invalid coordinates (Null Island or out of bounds)
    if not validate_coordinates(latitude, longitude):
        logger.warning("Invalid or zero coordinates provided to search_partner_catalog: (%.4f, %.4f)", latitude, longitude)
        return []

    # Clamp search radius to 5 km delivery limit
    clamped_radius = max(100, min(max_radius_meters, MAX_SEARCH_RADIUS_METERS))

    # Construct user geography point (SRID 4326)
    user_point = func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)
    user_geog = cast(user_point, Geography())
    shop_geog = cast(Shop.location, Geography())

    dist_expr = func.ST_Distance(shop_geog, user_geog).label("distance_meters")

    # Base join query: Product -> Shop & Product -> Inventory
    stmt = (
        select(Product, Shop, Inventory, dist_expr)
        .join(Shop, Product.shop_id == Shop.id)
        .join(Inventory, Product.id == Inventory.product_id)
        .where(
            # Shop invariants
            Shop.is_active == True,
            Shop.is_orderable == True,
            Shop.verification_status == ShopVerificationStatus.verified,
            Shop.owner_id.is_not(None),
            Shop.location.is_not(None),
            # Delivery serviceability boundary
            func.ST_DWithin(shop_geog, user_geog, clamped_radius),
            # Product invariants
            Product.is_active == True,
            # Inventory invariants (positive in-stock only)
            Inventory.stock > 0,
        )
    )

    # Optional specific shop filter
    if shop_id:
        stmt = stmt.where(Shop.id == shop_id)

    # Optional category filter
    if category and category.strip():
        stmt = stmt.where(Product.category.ilike(f"%{category.strip()}%"))

    # Natural-language query filter across product name, description, and category
    if query and query.strip():
        raw_query = query.strip().lower()
        all_tokens = [t for t in re.sub(r"[^\w\s\u0900-\u097F]", " ", raw_query).split() if len(t) >= 2]
        content_tokens = [t for t in all_tokens if t not in COMMON_STOP_WORDS or t in GROCERY_SYNONYMS]
        base_tokens = content_tokens if content_tokens else all_tokens
        
        # Expand tokens with Hindi/Hinglish grocery synonyms
        expanded_tokens: List[str] = []
        for token in base_tokens:
            expanded_tokens.append(token)
            if token in GROCERY_SYNONYMS:
                expanded_tokens.extend(GROCERY_SYNONYMS[token])

        # Deduplicate while preserving order, limit to top 20 tokens for search efficiency
        seen = set()
        unique_tokens: List[str] = []
        for t in expanded_tokens:
            if t not in seen:
                seen.add(t)
                unique_tokens.append(t)
            if len(unique_tokens) >= 20:
                break

        if unique_tokens:
            clauses = []
            for token in unique_tokens:
                clauses.append(Product.name.ilike(f"%{token}%"))
                clauses.append(Product.description.ilike(f"%{token}%"))
                clauses.append(Product.category.ilike(f"%{token}%"))
                clauses.append(Shop.name.ilike(f"%{token}%"))
            stmt = stmt.where(or_(*clauses))

            # Prioritize matches in product name over generic description matches
            name_match_cases = [Product.name.ilike(f"%{token}%") for token in unique_tokens]
            name_match_score = case((or_(*name_match_cases), 0), else_=1)
            stmt = stmt.order_by(dist_expr.asc(), name_match_score.asc(), Product.name.asc()).limit(max_results)
        else:
            stmt = stmt.order_by(dist_expr.asc(), Product.name.asc()).limit(max_results)
    else:
        # Order by proximity to customer first, then alphabetically by product name
        stmt = stmt.order_by(dist_expr.asc(), Product.name.asc()).limit(max_results)

    result = await db.execute(stmt)
    rows = result.all()

    items: List[CatalogProductItem] = []
    for product_obj, shop_obj, inventory_obj, dist in rows:
        dist_float = round(float(dist), 1)
        items.append(
            CatalogProductItem(
                product_id=product_obj.id,
                product_name=product_obj.name,
                product_description=product_obj.description,
                category=product_obj.category,
                price=product_obj.price,
                stock=inventory_obj.stock,
                image_url=product_obj.image_url,
                thumb_url=product_obj.thumb_url,
                shop_id=shop_obj.id,
                shop_name=shop_obj.name,
                shop_address=shop_obj.address,
                distance_meters=dist_float,
                is_delivery_eligible=True,
            )
        )

    logger.info(
        "Partner catalog search executed [lat=%.4f, lon=%.4f, query='%s', results=%d]",
        latitude,
        longitude,
        query or "",
        len(items),
    )
    return items
