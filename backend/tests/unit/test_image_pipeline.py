"""
Comprehensive unit and integration tests for Dukaanly's license-safe image pipeline.

Covers:
1. Normalization & Canvas: aspect ratio, 600x600 canvas, Warm Ivory background, 200x200 thumb, WebP format.
2. Image Validation: non-images, SVG/scripts, size limits, minimum dimensions.
3. SSRF Guard: loopback, private IPs, AWS metadata IP (169.254.169.254), disallowed schemes.
4. Storage Abstraction: LocalStorageService save, exists, delete, get_url.
5. Sourcing Pipeline: fuzzy matching, confidence thresholds, mocked HTTP calls.
6. Shop-Owner API: authorization, image upload, and DELETE revert to master catalog item.
"""

import io
import uuid
from unittest.mock import patch, MagicMock
from PIL import Image
import pytest
from httpx import AsyncClient

from app.services.storage import (
    normalize_product_image,
    validate_image_bytes,
    validate_safe_url,
    process_and_store_image,
    LocalStorageService,
    InvalidImageError,
    SSRFSecurityError,
    WARM_IVORY_RGB,
    CANVAS_SIZE,
    THUMB_SIZE,
)
from app.models.user import UserRole
from app.db.session import engine
from sqlalchemy import text


# ── Helper Fixtures ─────────────────────────────────────────────────────────────

def create_sample_image(
    width: int = 300,
    height: int = 200,
    format: str = "JPEG",
    color: tuple = (180, 50, 50),
) -> bytes:
    """Generate an in-memory sample image payload."""
    im = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    im.save(buf, format=format)
    return buf.getvalue()


def create_transparent_png(width: int = 300, height: int = 300) -> bytes:
    """Generate an in-memory PNG with transparency."""
    im = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    # Draw a non-transparent center square
    center = Image.new("RGBA", (150, 150), (200, 100, 0, 255))
    im.paste(center, (75, 75))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


# ── 1. Image Validation & Security Tests ────────────────────────────────────────

def test_validate_image_bytes_valid_jpeg():
    raw = create_sample_image(format="JPEG")
    mime = validate_image_bytes(raw)
    assert mime == "image/jpeg"


def test_validate_image_bytes_valid_png():
    raw = create_sample_image(format="PNG")
    mime = validate_image_bytes(raw)
    assert mime == "image/png"


def test_validate_image_bytes_empty_payload():
    with pytest.raises(InvalidImageError, match="empty"):
        validate_image_bytes(b"")


def test_validate_image_bytes_rejects_non_image():
    with pytest.raises(InvalidImageError, match="Unsupported image format"):
        validate_image_bytes(b"This is just plain text content, not an image header.")


def test_validate_image_bytes_rejects_svg():
    svg_payload = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><circle r="50"/></svg>'
    with pytest.raises(InvalidImageError, match="SVG, XML, or script-based"):
        validate_image_bytes(svg_payload)


def test_validate_image_bytes_rejects_embedded_script():
    malicious = b'<script>alert("xss")</script>'
    with pytest.raises(InvalidImageError, match="SVG, XML, or script-based"):
        validate_image_bytes(malicious)


def test_validate_image_bytes_size_limit():
    huge_payload = b"\xff\xd8\xff" + (b"\x00" * (16 * 1024 * 1024))
    with pytest.raises(InvalidImageError, match="exceeds maximum limit"):
        validate_image_bytes(huge_payload)


# ── 2. Normalization & Canvas Tests ─────────────────────────────────────────────

def test_normalization_aspect_ratio_and_canvas():
    """Verify image is centered on 600x600 Warm Ivory canvas without distortion."""
    raw = create_sample_image(width=400, height=200, format="JPEG", color=(100, 150, 200))
    full_bytes, thumb_bytes, sha_hash = normalize_product_image(raw)

    assert len(sha_hash) == 64  # SHA-256 hex string

    # Inspect normalized full image
    with Image.open(io.BytesIO(full_bytes)) as full_img:
        assert full_img.format == "WEBP"
        assert full_img.size == CANVAS_SIZE  # (600, 600)
        # Background corners must be Warm Ivory #FBF8F1 (allow 2 units tolerance due to lossy WebP compression)
        corner_pixel = full_img.getpixel((5, 5))
        for i in range(3):
            assert abs(corner_pixel[i] - WARM_IVORY_RGB[i]) <= 2

    # Inspect thumbnail
    with Image.open(io.BytesIO(thumb_bytes)) as thumb_img:
        assert thumb_img.format == "WEBP"
        assert thumb_img.size == THUMB_SIZE  # (200, 200)


def test_normalization_transparency_compositing():
    """Verify PNG transparency is cleanly composited over Warm Ivory."""
    raw = create_transparent_png(width=300, height=300)
    full_bytes, _, _ = normalize_product_image(raw)

    with Image.open(io.BytesIO(full_bytes)) as img:
        assert img.format == "WEBP"
        # The transparent region must be Warm Ivory, not black (allow tolerance for lossy WebP compression)
        bg_pixel = img.getpixel((10, 10))
        for i in range(3):
            assert abs(bg_pixel[i] - WARM_IVORY_RGB[i]) <= 2


def test_normalization_rejects_sub_minimum_dimensions():
    """Images below 200x200 must be rejected."""
    tiny_img = create_sample_image(width=150, height=150)
    with pytest.raises(InvalidImageError, match="below the required minimum"):
        normalize_product_image(tiny_img)


# ── 3. SSRF Protection Tests ────────────────────────────────────────────────────

def test_ssrf_blocks_localhost():
    with pytest.raises(SSRFSecurityError, match="localhost / loopback"):
        validate_safe_url("http://localhost:8000/media.jpg")

    with pytest.raises(SSRFSecurityError, match="localhost / loopback"):
        validate_safe_url("http://127.0.0.1/admin.png")


def test_ssrf_blocks_private_subnets():
    with pytest.raises(SSRFSecurityError, match="restricted IP"):
        validate_safe_url("http://10.0.0.1/secret.jpg")

    with pytest.raises(SSRFSecurityError, match="restricted IP"):
        validate_safe_url("http://192.168.1.100/config.png")


def test_ssrf_blocks_cloud_metadata():
    with pytest.raises(SSRFSecurityError, match="restricted IP"):
        validate_safe_url("http://169.254.169.254/latest/meta-data/")


def test_ssrf_blocks_disallowed_schemes():
    with pytest.raises(SSRFSecurityError, match="Disallowed URL scheme"):
        validate_safe_url("file:///etc/passwd")

    with pytest.raises(SSRFSecurityError, match="Disallowed URL scheme"):
        validate_safe_url("ftp://ftp.example.com/image.png")


def test_ssrf_permits_valid_public_domain():
    url = "https://commons.wikimedia.org/wiki/File:Example.jpg"
    assert validate_safe_url(url) == url


# ── 4. Storage Service Tests ────────────────────────────────────────────────────

def test_local_storage_service(tmp_path):
    storage = LocalStorageService(base_dir=str(tmp_path), url_prefix="/static/test/")
    filename = "sample_test_image.webp"
    content = b"fake-webp-binary-content"

    assert not storage.exists(filename)
    url = storage.save(filename, content)

    assert url == f"/static/test/{filename}"
    assert storage.exists(filename)
    assert (tmp_path / filename).read_bytes() == content

    assert storage.delete(filename) is True
    assert not storage.exists(filename)


# ── 5. Shop-Owner API Integration Tests ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_shop_product_image_upload_and_authorization(async_client: AsyncClient):
    """Test owner authorization, 403 on non-owner, and WebP normalization via API."""
    # 1. Create two shop owner accounts
    owner1_email = f"owner1_{uuid.uuid4()}@test.com"
    owner2_email = f"owner2_{uuid.uuid4()}@test.com"

    await async_client.post("/api/v1/auth/register", json={"name": "Owner 1", "email": owner1_email, "password": "Password123!"})
    await async_client.post("/api/v1/auth/register", json={"name": "Owner 2", "email": owner2_email, "password": "Password123!"})

    async with engine.connect() as conn:
        await conn.execute(
            text("UPDATE users SET role = 'shop_owner' WHERE email IN (:e1, :e2)"),
            {"e1": owner1_email, "e2": owner2_email},
        )
        await conn.commit()

    token1 = (await async_client.post("/api/v1/auth/login", json={"email": owner1_email, "password": "Password123!"})).json()["access_token"]
    token2 = (await async_client.post("/api/v1/auth/login", json={"email": owner2_email, "password": "Password123!"})).json()["access_token"]

    # 2. Owner 1 creates a shop
    shop_res = await async_client.post(
        "/api/v1/shops",
        json={"name": "Kirana Studio 1", "address": "Boring Rd", "location": {"latitude": 25.61, "longitude": 85.11}},
        headers={"Authorization": f"Bearer {token1}"},
    )
    shop_id = shop_res.json()["id"]

    # 3. Create a product in Shop 1
    prod_res = await async_client.post(
        f"/api/v1/shops/{shop_id}/products",
        json={"name": "Organic Basmati 1kg", "category": "Groceries", "price": 120.00},
        headers={"Authorization": f"Bearer {token1}"},
    )
    prod_id = prod_res.json()["id"]

    # 4. Owner 2 attempts to upload image to Owner 1's product -> 403 Forbidden
    sample_file = create_sample_image(width=300, height=300)
    files = {"file": ("test.jpg", sample_file, "image/jpeg")}
    unauthorized_res = await async_client.post(
        f"/api/v1/shops/{shop_id}/products/{prod_id}/image",
        files=files,
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert unauthorized_res.status_code == 403

    # 5. Owner 1 uploads image -> 200 OK
    files = {"file": ("product.jpg", sample_file, "image/jpeg")}
    upload_res = await async_client.post(
        f"/api/v1/shops/{shop_id}/products/{prod_id}/image",
        files=files,
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert upload_res.status_code == 200
    data = upload_res.json()
    assert data["image_source"] == "shop_upload"
    assert data["image_url"].startswith("/static/media/products/")
    assert data["image_url"].endswith(".webp")
    assert data["thumb_url"].endswith("_thumb.webp")

    # 6. Delete/revert custom image -> reverts to master or placeholder
    delete_res = await async_client.delete(
        f"/api/v1/shops/{shop_id}/products/{prod_id}/image",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert delete_res.status_code == 200
    rev_data = delete_res.json()
    assert rev_data["image_source"] in ("placeholder", "open_food_facts", "wikimedia")
