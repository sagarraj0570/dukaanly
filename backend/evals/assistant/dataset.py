"""
Dataset loader and resolver for Dukaanly AI Shopping Assistant evaluations.
Parses cases.jsonl, validates case schema via Pydantic, and authoritatively resolves
product and shop references against live PostgreSQL database records.
"""

from decimal import Decimal
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.product import Product
from app.models.shop import Shop

logger = logging.getLogger(__name__)

DEFAULT_CASES_PATH = Path(__file__).parent / "cases.jsonl"


class ExpectedItem(BaseModel):
    product_ref: str = Field(..., min_length=1, description="Exact product name or stable identifier")
    quantity: int = Field(1, ge=1, le=50, description="Expected item quantity")

    model_config = ConfigDict(extra="forbid")


class AssistantTestCase(BaseModel):
    id: str = Field(..., min_length=1, description="Unique case identifier")
    category: str = Field(..., min_length=1, description="Evaluation category")
    query: str = Field(..., min_length=1, description="Customer shopping query")
    shop_ref: str = Field(..., min_length=1, description="Target shop reference identifier")
    expected_items: List[ExpectedItem] = Field(default_factory=list, description="Expected proposed items")
    forbidden_items: List[str] = Field(default_factory=list, description="Items that must not appear")
    max_total: Optional[float] = Field(None, gt=0, description="Optional maximum allowed budget")
    expect_unavailable: List[str] = Field(default_factory=list, description="Items expected to be unavailable")
    expect_refusal: bool = Field(False, description="Whether assistant must refuse the request")
    reviewed: bool = Field(False, description="Human review verification status")
    notes: str = Field("", description="Annotator notes and rationale")

    model_config = ConfigDict(extra="forbid")

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        valid_categories = {
            "hinglish_basic",
            "hindi_script",
            "english_basic",
            "quantities_units",
            "brand_and_size",
            "budget",
            "misspellings_and_slang",
            "unavailable",
            "out_of_scope",
        }
        if v not in valid_categories:
            raise ValueError(f"Invalid evaluation category '{v}'. Allowed: {sorted(valid_categories)}")
        return v


class ResolvedExpectedItem(BaseModel):
    product_id: uuid.UUID
    product_name: str
    quantity: int
    unit_price: Decimal
    stock: int

    model_config = ConfigDict(from_attributes=True)


class ResolvedTestCase(BaseModel):
    id: str
    category: str
    query: str
    shop_id: uuid.UUID
    shop_name: str
    shop_ref: str
    expected_items: List[ResolvedExpectedItem]
    forbidden_product_ids: List[uuid.UUID]
    max_total: Optional[float]
    expect_unavailable: List[str]
    expect_refusal: bool
    reviewed: bool
    notes: str

    model_config = ConfigDict(from_attributes=True)


def load_raw_cases(filepath: Optional[Union[str, Path]] = None) -> List[AssistantTestCase]:
    """
    Read and parse all cases from cases.jsonl, strictly validating each against
    the AssistantTestCase Pydantic model.
    """
    path = Path(filepath) if filepath else DEFAULT_CASES_PATH
    if not path.exists():
        raise FileNotFoundError(f"Evaluation cases file not found at: {path.resolve()}")

    cases: List[AssistantTestCase] = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line_str = line.strip()
            if not line_str:
                continue
            try:
                case_obj = AssistantTestCase.model_validate_json(line_str)
                cases.append(case_obj)
            except Exception as exc:
                raise ValueError(f"Schema validation error on line {line_no} of {path}: {exc}") from exc

    return cases


async def resolve_test_case(case: AssistantTestCase, db: AsyncSession) -> ResolvedTestCase:
    """
    Authoritatively resolve shop_ref and expected/forbidden product references
    against the database. Raises clear ValueError if any entity cannot be found.
    """
    # 1. Resolve shop
    shop_query = (
        select(Shop)
        .where(
            or_(
                Shop.source_id == case.shop_ref,
                Shop.source_id == f"demo:shop:{case.shop_ref}",
                Shop.name.ilike(case.shop_ref.replace("-", " ")),
            )
        )
    )
    shop_res = await db.execute(shop_query)
    shop = shop_res.scalars().first()

    if not shop:
        raise ValueError(
            f"Evaluation case '{case.id}' specifies shop_ref '{case.shop_ref}', "
            f"but no matching Shop exists in the database."
        )

    # 2. Resolve expected items
    resolved_expected: List[ResolvedExpectedItem] = []
    for item in case.expected_items:
        prod_query = (
            select(Product)
            .options(selectinload(Product.inventory))
            .where(
                Product.shop_id == shop.id,
                Product.name == item.product_ref,
            )
        )
        prod_res = await db.execute(prod_query)
        product = prod_res.scalar_one_or_none()

        if not product:
            raise ValueError(
                f"Evaluation case '{case.id}' references expected product '{item.product_ref}' "
                f"for shop '{shop.name}' (id={shop.id}), but this product DOES NOT EXIST in the database."
            )

        if not product.is_active:
            raise ValueError(
                f"Evaluation case '{case.id}' references product '{item.product_ref}' "
                f"which is marked inactive (is_active=False) in the database."
            )

        available_stock = product.inventory.stock if product.inventory else 0

        resolved_expected.append(
            ResolvedExpectedItem(
                product_id=product.id,
                product_name=product.name,
                quantity=item.quantity,
                unit_price=product.price,
                stock=available_stock,
            )
        )

    # 3. Resolve forbidden items
    resolved_forbidden_ids: List[uuid.UUID] = []
    for forb_ref in case.forbidden_items:
        forb_query = select(Product.id).where(
            Product.shop_id == shop.id,
            Product.name == forb_ref,
        )
        forb_res = await db.execute(forb_query)
        forb_id = forb_res.scalar_one_or_none()
        if forb_id:
            resolved_forbidden_ids.append(forb_id)

    return ResolvedTestCase(
        id=case.id,
        category=case.category,
        query=case.query,
        shop_id=shop.id,
        shop_name=shop.name,
        shop_ref=case.shop_ref,
        expected_items=resolved_expected,
        forbidden_product_ids=resolved_forbidden_ids,
        max_total=case.max_total,
        expect_unavailable=case.expect_unavailable,
        expect_refusal=case.expect_refusal,
        reviewed=case.reviewed,
        notes=case.notes,
    )


async def load_and_resolve_dataset(
    db: AsyncSession,
    filepath: Optional[Union[str, Path]] = None,
) -> List[ResolvedTestCase]:
    """
    Load raw test cases from JSONL and resolve all product references against the database.
    Fails immediately with an informative error if any product or shop is missing.
    """
    raw_cases = load_raw_cases(filepath)
    resolved_cases: List[ResolvedTestCase] = []

    for case in raw_cases:
        resolved = await resolve_test_case(case, db)
        resolved_cases.append(resolved)

    logger.info(
        "Successfully loaded and resolved %d evaluation cases from %s",
        len(resolved_cases),
        filepath or DEFAULT_CASES_PATH,
    )
    return resolved_cases
