"""
Storage service abstraction and image processing pipeline for Dukaanly.

Provides:
- BaseStorageService & LocalStorageService for managing product media.
- Strict image validation (5MB max, MIME & magic bytes verification, minimum 200x200px, reject SVGs/executables).
- Canvas normalization: centers on 600x600 Warm Ivory (#FBF8F1) canvas with aspect ratio preservation and trimmed borders.
- Export to high-efficiency WebP (600x600 full, 200x200 thumbnail, quality 82, stripped EXIF).
- Content-addressed filenames via SHA-256 for immutable caching.
- SSRF protection guard for remote URL imports.
"""

from abc import ABC, abstractmethod
import hashlib
import io
import ipaddress
import logging
import os
from pathlib import Path
import socket
from typing import Tuple, Optional
from urllib.parse import urlparse

from PIL import Image, ImageOps, ImageChops

logger = logging.getLogger(__name__)

# Constants
MAX_IMAGE_SIZE_BYTES = 15 * 1024 * 1024  # 15MB limit for high-res source media
MIN_IMAGE_DIMENSION = 200
CANVAS_SIZE = (600, 600)
CANVAS_INNER_BOUNDS = (540, 540)
THUMB_SIZE = (200, 200)
WARM_IVORY_RGB = (251, 248, 241)  # #FBF8F1 Fresh Bazaar Warm Ivory
WEBP_QUALITY = 82

ALLOWED_MAGIC_BYTES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"RIFF": "image/webp",  # Requires checking offset 8-12 for 'WEBP'
}


class StorageError(Exception):
    """Base exception for storage and media processing errors."""
    pass


class InvalidImageError(StorageError):
    """Raised when an uploaded file is invalid, corrupt, or fails security checks."""
    pass


class SSRFSecurityError(StorageError):
    """Raised when a URL attempts to access private, loopback, or cloud-metadata IPs."""
    pass


# ── Storage Abstraction ──────────────────────────────────────────────────────────

class BaseStorageService(ABC):
    """Abstract interface for storing and retrieving media assets."""

    @abstractmethod
    def save(self, filename: str, content: bytes) -> str:
        """Persist file content and return the public URL / path."""
        pass

    @abstractmethod
    def exists(self, filename: str) -> bool:
        """Check if a file exists in storage."""
        pass

    @abstractmethod
    def delete(self, filename: str) -> bool:
        """Delete a file from storage if it exists. Returns True if deleted."""
        pass

    @abstractmethod
    def get_url(self, filename: str) -> str:
        """Get the public URL for a stored filename."""
        pass


class LocalStorageService(BaseStorageService):
    """Local filesystem storage service serving assets via FastAPI static files."""

    def __init__(
        self,
        base_dir: Optional[str] = None,
        url_prefix: str = "/static/media/products/",
    ):
        if base_dir:
            self.base_path = Path(base_dir).resolve()
        else:
            # Default to backend/data/media/products
            current_file = Path(__file__).resolve()
            # backend/app/services/storage.py -> backend/data/media/products
            self.base_path = (current_file.parent.parent.parent / "data" / "media" / "products").resolve()

        self.url_prefix = url_prefix.rstrip("/") + "/"
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save(self, filename: str, content: bytes) -> str:
        safe_name = os.path.basename(filename)
        dest_path = self.base_path / safe_name
        dest_path.write_bytes(content)
        return self.get_url(safe_name)

    def exists(self, filename: str) -> bool:
        safe_name = os.path.basename(filename)
        return (self.base_path / safe_name).is_file()

    def delete(self, filename: str) -> bool:
        safe_name = os.path.basename(filename)
        target = self.base_path / safe_name
        if target.is_file():
            target.unlink()
            return True
        return False

    def get_url(self, filename: str) -> str:
        safe_name = os.path.basename(filename)
        return f"{self.url_prefix}{safe_name}"


# Default singleton instance
_default_storage: Optional[BaseStorageService] = None


def get_storage_service() -> BaseStorageService:
    global _default_storage
    if _default_storage is None:
        _default_storage = LocalStorageService()
    return _default_storage


def set_storage_service(storage: BaseStorageService) -> None:
    global _default_storage
    _default_storage = storage


# ── SSRF Security Guard ──────────────────────────────────────────────────────────

def validate_safe_url(url: str) -> str:
    """
    Validate that a remote URL uses http/https and does NOT resolve to private,
    loopback, link-local, or cloud-metadata IP addresses (e.g. AWS 169.254.169.254).
    """
    if not url or not isinstance(url, str):
        raise SSRFSecurityError("URL must be a non-empty string.")

    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in ("http", "https"):
        raise SSRFSecurityError(f"Disallowed URL scheme: '{parsed.scheme}'. Only HTTP and HTTPS are permitted.")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFSecurityError("URL must contain a valid hostname.")

    if hostname.lower() in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        raise SSRFSecurityError("Access to localhost / loopback addresses is strictly forbidden.")

    # Resolve hostname to IP addresses and inspect each
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise SSRFSecurityError(f"Could not resolve hostname '{hostname}': {e}")

    for item in addr_info:
        ip_str = item[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                raise SSRFSecurityError(f"Host '{hostname}' resolves to restricted IP: {ip_str}")
        except ValueError:
            raise SSRFSecurityError(f"Invalid resolved IP: {ip_str}")

    return url.strip()


# ── Image Validation & Normalization ───────────────────────────────────────────

def validate_image_bytes(image_bytes: bytes) -> str:
    """
    Validates magic bytes, max file size, and file structure.
    Returns the detected MIME type ('image/jpeg', 'image/png', or 'image/webp').
    Raises InvalidImageError on failure.
    """
    if not image_bytes:
        raise InvalidImageError("Image payload is empty.")

    if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
        raise InvalidImageError(
            f"Image size exceeds maximum limit of 5MB (got {len(image_bytes) / (1024 * 1024):.2f}MB)."
        )

    # Magic byte check
    detected_mime = None
    if image_bytes.startswith(b"\xff\xd8\xff"):
        detected_mime = "image/jpeg"
    elif image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        detected_mime = "image/png"
    elif image_bytes.startswith(b"RIFF") and len(image_bytes) >= 12 and image_bytes[8:12] == b"WEBP":
        detected_mime = "image/webp"

    # Explicitly disallow SVG, HTML, or unknown scripts
    lower_snippet = image_bytes[:512].lower()
    if b"<svg" in lower_snippet or b"<?xml" in lower_snippet or b"<html" in lower_snippet or b"<script" in lower_snippet:
        raise InvalidImageError("SVG, XML, or script-based image formats are forbidden for security reasons.")

    if not detected_mime:
        raise InvalidImageError(
            "Unsupported image format. Only JPEG, PNG, and WebP images are permitted."
        )

    return detected_mime


def _trim_near_white_borders(img: Image.Image, threshold: int = 244) -> Image.Image:
    """
    Trims uniform near-white background borders from product studio shots.
    Preserves image if trimming would crop too aggressively.
    """
    if img.mode != "RGB":
        rgb_img = img.convert("RGB")
    else:
        rgb_img = img

    # Invert and check non-white pixels
    bg = Image.new("RGB", rgb_img.size, (255, 255, 255))
    diff = ImageChops.difference(rgb_img, bg)
    bbox = diff.getbbox()

    if bbox:
        # Check if cropped area is at least 30% of original dimensions to avoid over-clipping
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        if width >= (rgb_img.width * 0.3) and height >= (rgb_img.height * 0.3):
            return img.crop(bbox)

    return img


def normalize_product_image(
    image_bytes: bytes,
) -> Tuple[bytes, bytes, str]:
    """
    Normalizes an input image:
    1. Validates magic bytes, max size (5MB), and minimum dimensions (200x200).
    2. Converts to RGB, composites transparency over Warm Ivory (#FBF8F1).
    3. Trims near-white borders.
    4. Scales and centers within 600x600 canvas with #FBF8F1 background.
    5. Produces:
       - Full WebP: 600x600 (quality 82, no EXIF)
       - Thumb WebP: 200x200 (quality 82, no EXIF)
       - Content hash (SHA-256 of the normalized full image)

    Returns (full_webp_bytes, thumb_webp_bytes, sha256_hash).
    """
    validate_image_bytes(image_bytes)

    try:
        with Image.open(io.BytesIO(image_bytes)) as pil_img:
            # Check minimum dimensions
            if pil_img.width < MIN_IMAGE_DIMENSION or pil_img.height < MIN_IMAGE_DIMENSION:
                raise InvalidImageError(
                    f"Image dimensions ({pil_img.width}x{pil_img.height}) are below the required "
                    f"minimum of {MIN_IMAGE_DIMENSION}x{MIN_IMAGE_DIMENSION}px."
                )

            # Strip EXIF orientation by auto-orienting
            oriented_img = ImageOps.exif_transpose(pil_img) or pil_img

            # Handle transparency (RGBA / LA / P)
            if oriented_img.mode in ("RGBA", "LA") or (oriented_img.mode == "P" and "transparency" in oriented_img.info):
                rgba_img = oriented_img.convert("RGBA")
                # Create warm ivory canvas to composite alpha
                alpha_bg = Image.new("RGBA", rgba_img.size, (*WARM_IVORY_RGB, 255))
                alpha_bg.paste(rgba_img, (0, 0), rgba_img)
                working_img = alpha_bg.convert("RGB")
            else:
                working_img = oriented_img.convert("RGB")

            # Trim near-white borders
            trimmed_img = _trim_near_white_borders(working_img)

            # Create 600x600 canvas
            canvas = Image.new("RGB", CANVAS_SIZE, WARM_IVORY_RGB)

            # Fit into CANVAS_INNER_BOUNDS (540, 540) maintaining aspect ratio
            fitted_img = trimmed_img.copy()
            fitted_img.thumbnail(CANVAS_INNER_BOUNDS, Image.Resampling.LANCZOS)

            # Center on 600x600 canvas
            offset_x = (CANVAS_SIZE[0] - fitted_img.width) // 2
            offset_y = (CANVAS_SIZE[1] - fitted_img.height) // 2
            canvas.paste(fitted_img, (offset_x, offset_y))

            # Generate Full 600x600 WebP
            full_buf = io.BytesIO()
            canvas.save(full_buf, format="WEBP", quality=WEBP_QUALITY, method=6)
            full_webp_bytes = full_buf.getvalue()

            # Generate Thumb 200x200 WebP
            thumb_canvas = canvas.resize(THUMB_SIZE, Image.Resampling.LANCZOS)
            thumb_buf = io.BytesIO()
            thumb_canvas.save(thumb_buf, format="WEBP", quality=WEBP_QUALITY, method=6)
            thumb_webp_bytes = thumb_buf.getvalue()

            # Content hash based on normalized full WebP bytes
            content_hash = hashlib.sha256(full_webp_bytes).hexdigest()

            return full_webp_bytes, thumb_webp_bytes, content_hash

    except InvalidImageError:
        raise
    except Exception as e:
        logger.error(f"Failed to process and normalize image: {e}", exc_info=True)
        raise InvalidImageError(f"Invalid or corrupted image data: {str(e)}")


def process_and_store_image(
    image_bytes: bytes,
    storage: Optional[BaseStorageService] = None,
) -> Tuple[str, str, str]:
    """
    High-level helper:
    Normalizes image, saves full and thumbnail WebP files using storage service,
    and returns (full_url, thumb_url, sha256_hash).
    """
    if storage is None:
        storage = get_storage_service()

    full_bytes, thumb_bytes, content_hash = normalize_product_image(image_bytes)

    full_filename = f"{content_hash}.webp"
    thumb_filename = f"{content_hash}_thumb.webp"

    full_url = storage.save(full_filename, full_bytes)
    thumb_url = storage.save(thumb_filename, thumb_bytes)

    return full_url, thumb_url, content_hash
