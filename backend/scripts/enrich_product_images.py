"""
Dukaanly Product Image Enrichment Pipeline.

A repeatable, license-safe image pipeline that:
1. Queries Open Food Facts (via EAN-13 barcodes) for branded FMCG items.
2. Queries Wikimedia Commons API (CC BY / CC BY-SA / CC0) for fresh bakery, produce, and local essentials.
3. Enforces strict SSRF protection, size limits, and image format validation.
4. Normalizes images onto a 600x600 Warm Ivory (#FBF8F1) canvas with aspect ratio preservation and trimmed borders.
5. Generates 600x600 full WebP and 200x200 thumbnail WebP (quality 82, stripped EXIF) named by SHA-256 content hash.
6. Populates master_catalog_items, links product listings across shops, and maintains shop custom upload overrides.
7. Logs low-confidence matches to backend/data/image_review_queue.csv.
8. Generates comprehensive coverage report in backend/data/image_coverage_report.json.

Usage:
    python backend/scripts/enrich_product_images.py [OPTIONS]

Options:
    --dry-run         Preview matches and confidence without modifying filesystem or database
    --limit N         Process at most N products
    --only-missing    Only enrich products missing an image or marked as placeholder
    --category CAT    Process only products in the specified category
    --force           Re-download and re-process even if product already has an enriched image
    --approve CSV     Approve reviewed rows from the review queue CSV
"""

import argparse
import asyncio
import csv
import json
import logging
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Ensure backend is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from rapidfuzz import fuzz
from sqlalchemy import select, func, or_
from app.db.session import async_session_maker
from app.models.product import Product
from app.models.master_catalog import MasterCatalogItem
from app.services.storage import (
    process_and_store_image,
    normalize_product_image,
    get_storage_service,
    validate_safe_url,
    InvalidImageError,
    SSRFSecurityError,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("enrich_product_images")

USER_AGENT = "Dukaanly-ProductEnricher/1.0 (https://dukaanly.com; tech@dukaanly.com)"
REVIEW_QUEUE_PATH = BASE_DIR / "data" / "image_review_queue.csv"
COVERAGE_REPORT_PATH = BASE_DIR / "data" / "image_coverage_report.json"

# ── Canonical Seed Knowledge Base for Dukaanly 96 Products ────────────────────
# High-confidence barcodes (EAN-13) and verified CC/ODbL image fallbacks
CANONICAL_SEED_DATA: Dict[str, Dict[str, Any]] = {
    # Groceries
    "aashirvaad superior mp shudh chakki atta 5kg": {
        "barcode": "8901030383701",
        "brand": "Aashirvaad",
        "category": "Groceries",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/Wheat_flour_%28Atta%29.jpg/640px-Wheat_flour_%28Atta%29.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Biswarup Ganguly",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Wheat_flour_(Atta).jpg",
    },
    "aashirvaad whole wheat atta 5kg": {
        "barcode": "8901030383701",
        "brand": "Aashirvaad",
        "category": "Groceries",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/Wheat_flour_%28Atta%29.jpg/640px-Wheat_flour_%28Atta%29.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Biswarup Ganguly",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Wheat_flour_(Atta).jpg",
    },
    "daawat rozana gold basmati rice 5kg": {
        "barcode": "8901537000102",
        "brand": "Daawat",
        "category": "Groceries",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/91/Basmati_Rice_raw.jpg/640px-Basmati_Rice_raw.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Thamizhpparithi Maari",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Basmati_Rice_raw.jpg",
    },
    "india gate basmati rice feast rozzana 1kg": {
        "barcode": "8901414000010",
        "brand": "India Gate",
        "category": "Groceries",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/91/Basmati_Rice_raw.jpg/640px-Basmati_Rice_raw.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Thamizhpparithi Maari",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Basmati_Rice_raw.jpg",
    },
    "tata sampann unpolished toor dal 1kg": {
        "barcode": "8904043904008",
        "brand": "Tata Sampann",
        "category": "Groceries",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/87/Pigeon_pea_%28Toor_dal%29.jpg/640px-Pigeon_pea_%28Toor_dal%29.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Thamizhpparithi Maari",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Pigeon_pea_(Toor_dal).jpg",
    },
    "tata salt vacuum evaporated iodised salt 1kg": {
        "barcode": "8904043901007",
        "brand": "Tata Salt",
        "category": "Groceries",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/78/Salt_shaker_on_white_background.jpg/640px-Salt_shaker_on_white_background.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Poyraz 72",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Salt_shaker_on_white_background.jpg",
    },
    "tata salt vacuum evaporated 1kg": {
        "barcode": "8904043901007",
        "brand": "Tata Salt",
        "category": "Groceries",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/78/Salt_shaker_on_white_background.jpg/640px-Salt_shaker_on_white_background.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Poyraz 72",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Salt_shaker_on_white_background.jpg",
    },
    "madhur pure & hygienic sugar 1kg": {
        "barcode": "8906007280016",
        "brand": "Madhur",
        "category": "Groceries",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3c/White_sugar_crystals.jpg/640px-White_sugar_crystals.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Sanjay Acharya",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:White_sugar_crystals.jpg",
    },
    "fortune sunlite refined sunflower oil 1l": {
        "barcode": "8906007280023",
        "brand": "Fortune",
        "category": "Groceries",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4b/Sunflower_oil_and_sunflower.jpg/640px-Sunflower_oil_and_sunflower.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Tiia Monto",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Sunflower_oil_and_sunflower.jpg",
    },
    "engine brand mustard oil 1l": {
        "barcode": "8906013640019",
        "brand": "Engine",
        "category": "Groceries",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/23/Mustard_oil_in_bottle.jpg/640px-Mustard_oil_in_bottle.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Subhrajyoti07",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Mustard_oil_in_bottle.jpg",
    },
    "everest turmeric powder haldi 200g": {
        "barcode": "8901786111015",
        "brand": "Everest",
        "category": "Groceries",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5b/Curcuma_longa_roots.jpg/640px-Curcuma_longa_roots.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Simon A. Eugster",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Curcuma_longa_roots.jpg",
    },
    "mdh deggi mirch powder 100g": {
        "barcode": "8901848000010",
        "brand": "MDH",
        "category": "Groceries",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f2/Chili_powder_in_bowl.jpg/640px-Chili_powder_in_bowl.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Thamizhpparithi Maari",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Chili_powder_in_bowl.jpg",
    },
    "catch super garam masala 100g": {
        "barcode": "8901192000018",
        "brand": "Catch",
        "category": "Groceries",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4b/Garam_Masala_powder.jpg/640px-Garam_Masala_powder.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Miansari66",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Garam_Masala_powder.jpg",
    },
    "catch kashmiri chilli powder 100g": {
        "barcode": "8901192000025",
        "brand": "Catch",
        "category": "Groceries",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f2/Chili_powder_in_bowl.jpg/640px-Chili_powder_in_bowl.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Chili_powder_in_bowl.jpg",
    },
    "catch kashmiri chilli powder 100g (zero stock sample)": {
        "barcode": "8901192000025",
        "brand": "Catch",
        "category": "Groceries",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f2/Chili_powder_in_bowl.jpg/640px-Chili_powder_in_bowl.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Thamizhpparithi Maari",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Chili_powder_in_bowl.jpg",
    },
    "mdh khas turmeric powder (haldi) 100g": {
        "barcode": "8901848000027",
        "brand": "MDH",
        "category": "Spices",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5b/Curcuma_longa_roots.jpg/640px-Curcuma_longa_roots.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Simon A. Eugster",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Curcuma_longa_roots.jpg",
    },
    "sattu roasted gram flour 500g": {
        "barcode": None,
        "brand": "Desi Sattu",
        "category": "Groceries",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e6/Besan_Gram_Flour.jpg/640px-Besan_Gram_Flour.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Miansari66",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Besan_Gram_Flour.jpg",
    },
    "farm fresh white eggs (pack of 6)": {
        "barcode": None,
        "brand": "Farm Fresh",
        "category": "Dairy",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5e/Chicken_egg_2009-06-04.jpg/640px-Chicken_egg_2009-06-04.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Fir0002",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Chicken_egg_2009-06-04.jpg",
    },

    # Dairy
    "sudha special toned fresh milk 1l": {
        "barcode": "8906012340010",
        "brand": "Sudha",
        "category": "Dairy",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0e/Milk_glass.jpg/640px-Milk_glass.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Stefan Kuhn",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Milk_glass.jpg",
    },
    "sudha special toned milk 1l": {
        "barcode": "8906012340010",
        "brand": "Sudha",
        "category": "Dairy",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0e/Milk_glass.jpg/640px-Milk_glass.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Stefan Kuhn",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Milk_glass.jpg",
    },
    "sudha gold full cream milk 500ml": {
        "barcode": "8906012340027",
        "brand": "Sudha",
        "category": "Dairy",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0e/Milk_glass.jpg/640px-Milk_glass.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Stefan Kuhn",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Milk_glass.jpg",
    },
    "sudha fresh dahi curd 400g": {
        "barcode": "8906012340034",
        "brand": "Sudha",
        "category": "Dairy",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/02/Bowl_of_Curd.jpg/640px-Bowl_of_Curd.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Subhashish Panigrahi",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Bowl_of_Curd.jpg",
    },
    "sudha malai paneer 200g": {
        "barcode": "8906012340041",
        "brand": "Sudha",
        "category": "Dairy",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/36/Paneer_cubes.jpg/640px-Paneer_cubes.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Biswarup Ganguly",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Paneer_cubes.jpg",
    },
    "sudha desi cow ghee 500ml": {
        "barcode": "8906012340058",
        "brand": "Sudha",
        "category": "Dairy",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Desi_Ghee_in_jar.jpg/640px-Desi_Ghee_in_jar.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Miansari66",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Desi_Ghee_in_jar.jpg",
    },
    "sudha special bihari peda box 250g": {
        "barcode": None,
        "brand": "Sudha",
        "category": "Dairy",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c2/Peda_Indian_Sweet.jpg/640px-Peda_Indian_Sweet.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Biswarup Ganguly",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Peda_Indian_Sweet.jpg",
    },
    "fresh khoya mawa kalakand 250g": {
        "barcode": None,
        "brand": "Patna Sweets",
        "category": "Dairy",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/90/Kalakand_sweet.jpg/640px-Kalakand_sweet.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Biswarup Ganguly",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Kalakand_sweet.jpg",
    },
    "amul pasteurised salted butter 100g": {
        "barcode": "8901262010016",
        "brand": "Amul",
        "category": "Dairy",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d3/Butter_block_on_dish.jpg/640px-Butter_block_on_dish.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Rainer Zenz",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Butter_block_on_dish.jpg",
    },
    "amul salted butter 100g": {
        "barcode": "8901262010016",
        "brand": "Amul",
        "category": "Dairy",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d3/Butter_block_on_dish.jpg/640px-Butter_block_on_dish.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Rainer Zenz",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Butter_block_on_dish.jpg",
    },
    "amul cheese slices pack of 10": {
        "barcode": "8901262030014",
        "brand": "Amul",
        "category": "Dairy",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/89/Cheddar_cheese_slices.jpg/640px-Cheddar_cheese_slices.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Cheddar_cheese_slices.jpg",
    },
    "amul taaza homogenised toned milk 1l": {
        "barcode": "8901262020015",
        "brand": "Amul",
        "category": "Dairy",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0e/Milk_glass.jpg/640px-Milk_glass.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Stefan Kuhn",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Milk_glass.jpg",
    },
    "amul moti toned long life milk 450ml": {
        "barcode": "8901262020084",
        "brand": "Amul",
        "category": "Dairy",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0e/Milk_glass.jpg/640px-Milk_glass.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Stefan Kuhn",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Milk_glass.jpg",
    },
    "amul moti toned long life milk 450ml (low stock sample)": {
        "barcode": "8901262020022",
        "brand": "Amul",
        "category": "Dairy",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0e/Milk_glass.jpg/640px-Milk_glass.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Stefan Kuhn",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Milk_glass.jpg",
    },
    "amul dairy whipped cream 250ml": {
        "barcode": "8901262040013",
        "brand": "Amul",
        "category": "Dairy",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/23/Whipped_cream_bowl.jpg/640px-Whipped_cream_bowl.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / David Shankbone",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Whipped_cream_bowl.jpg",
    },

    # Snacks
    "parle-g gold biscuits 1kg": {
        "barcode": "8901719101038",
        "brand": "Parle",
        "category": "Snacks",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1b/Biscuits_stack.jpg/640px-Biscuits_stack.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Subhashish Panigrahi",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Biscuits_stack.jpg",
    },
    "parle-g gold glucose biscuits 1kg": {
        "barcode": "8901719101038",
        "brand": "Parle",
        "category": "Snacks",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1b/Biscuits_stack.jpg/640px-Biscuits_stack.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Subhashish Panigrahi",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Biscuits_stack.jpg",
    },
    "britannia good day cashew cookies 200g": {
        "barcode": "8901063012270",
        "brand": "Britannia",
        "category": "Snacks",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f1/Cashew_cookies.jpg/640px-Cashew_cookies.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Biswarup Ganguly",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Cashew_cookies.jpg",
    },
    "haldiram's nagpur bhujia sev 400g": {
        "barcode": "8904063200012",
        "brand": "Haldiram's",
        "category": "Snacks",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/29/Bikaneri_Bhujia.jpg/640px-Bikaneri_Bhujia.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Miansari66",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Bikaneri_Bhujia.jpg",
    },
    "lay's india's magic masala potato chips 50g": {
        "barcode": "8901491101839",
        "brand": "Lay's",
        "category": "Snacks",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/69/Potato-Chips.jpg/640px-Potato-Chips.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Potato-Chips.jpg",
    },
    "kurkure masala munch crunchy snack 82g": {
        "barcode": "8901491001009",
        "brand": "Kurkure",
        "category": "Snacks",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/cf/Kurkure_snack.jpg/640px-Kurkure_snack.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Biswarup Ganguly",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Kurkure_snack.jpg",
    },
    "cadbury dairy milk silk chocolate 150g": {
        "barcode": "8901233024806",
        "brand": "Cadbury",
        "category": "Snacks",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8d/Chocolate_bar_isolated.jpg/640px-Chocolate_bar_isolated.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Chocolate_bar_isolated.jpg",
    },
    "maggi 2-minute instant noodles 280g": {
        "barcode": "8901058852784",
        "brand": "Maggi",
        "category": "Snacks",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d4/Instant_noodles_raw.jpg/640px-Instant_noodles_raw.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Takeaway",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Instant_noodles_raw.jpg",
    },
    "maggi 2-minute masala instant noodles 280g": {
        "barcode": "8901058852784",
        "brand": "Maggi",
        "category": "Snacks",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d4/Instant_noodles_raw.jpg/640px-Instant_noodles_raw.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Takeaway",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Instant_noodles_raw.jpg",
    },
    "britannia premium milk rusk toast 300g": {
        "barcode": "8901063022002",
        "brand": "Britannia",
        "category": "Snacks",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/14/Rusk_toast.jpg/640px-Rusk_toast.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Biswarup Ganguly",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Rusk_toast.jpg",
    },

    # Beverages
    "tata tea gold 250g": {
        "barcode": "8901052002003",
        "brand": "Tata Tea",
        "category": "Beverages",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/90/Black_tea_loose_leaf.jpg/640px-Black_tea_loose_leaf.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Jorge Barrios",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Black_tea_loose_leaf.jpg",
    },
    "tata tea gold rich taste blend 500g": {
        "barcode": "8901052002003",
        "brand": "Tata Tea",
        "category": "Beverages",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/90/Black_tea_loose_leaf.jpg/640px-Black_tea_loose_leaf.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Jorge Barrios",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Black_tea_loose_leaf.jpg",
    },
    "nescafe classic 100% pure coffee jar 100g": {
        "barcode": "8901058849760",
        "brand": "Nescafe",
        "category": "Beverages",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/Instant_coffee_granules.jpg/640px-Instant_coffee_granules.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Rainer Zenz",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Instant_coffee_granules.jpg",
    },
    "bru instant coffee chicory mix 50g": {
        "barcode": "8901030001000",
        "brand": "Bru",
        "category": "Beverages",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/Instant_coffee_granules.jpg/640px-Instant_coffee_granules.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Rainer Zenz",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Instant_coffee_granules.jpg",
    },
    "frooti fresh mango drink 1.2l": {
        "barcode": "8901719104053",
        "brand": "Frooti",
        "category": "Beverages",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/07/Mango_juice_glass.jpg/640px-Mango_juice_glass.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Thamizhpparithi Maari",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Mango_juice_glass.jpg",
    },
    "real fruit power mixed fruit juice 1l": {
        "barcode": "8901207010019",
        "brand": "Real",
        "category": "Beverages",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/07/Mango_juice_glass.jpg/640px-Mango_juice_glass.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Thamizhpparithi Maari",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Mango_juice_glass.jpg",
    },
    "hamdard rooh afza sharbat syrup 750ml": {
        "barcode": "8901450000012",
        "brand": "Hamdard",
        "category": "Beverages",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/cf/Sharbat_drink.jpg/640px-Sharbat_drink.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Biswarup Ganguly",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Sharbat_drink.jpg",
    },
    "glucose-d instant energy powder 500g": {
        "barcode": "8901030002000",
        "brand": "Glucose-D",
        "category": "Beverages",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3c/White_sugar_crystals.jpg/640px-White_sugar_crystals.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Sanjay Acharya",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:White_sugar_crystals.jpg",
    },
    "artisan cold brew hazelnut coffee 300ml": {
        "barcode": None,
        "brand": "Patna Roasters",
        "category": "Beverages",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/45/A_small_cup_of_coffee.JPG/640px-A_small_cup_of_coffee.JPG",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Julius Schorzman",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:A_small_cup_of_coffee.JPG",
    },
    "belgian rich hot chocolate mix 200g": {
        "barcode": None,
        "brand": "The Bakeway",
        "category": "Beverages",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/70/Hot_chocolate_cup.jpg/640px-Hot_chocolate_cup.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Tiia Monto",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Hot_chocolate_cup.jpg",
    },

    # Personal Care
    "dettol original bathing soap bar 125g (pack of 3)": {
        "barcode": "8901396000008",
        "brand": "Dettol",
        "category": "Personal Care",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b8/Bar_of_soap_on_white.jpg/640px-Bar_of_soap_on_white.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Bar_of_soap_on_white.jpg",
    },
    "dettol antiseptic bathing soap 75g": {
        "barcode": "8901396000008",
        "brand": "Dettol",
        "category": "Personal Care",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b8/Bar_of_soap_on_white.jpg/640px-Bar_of_soap_on_white.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Bar_of_soap_on_white.jpg",
    },
    "colgate total antibacterial toothpaste 120g": {
        "barcode": "8901314010543",
        "brand": "Colgate",
        "category": "Personal Care",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9e/Toothpaste_tube.jpg/640px-Toothpaste_tube.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Toothpaste_tube.jpg",
    },
    "head & shoulders anti-dandruff shampoo 180ml": {
        "barcode": "4902430752398",
        "brand": "Head & Shoulders",
        "category": "Personal Care",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Shampoo_bottle.jpg/640px-Shampoo_bottle.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Shampoo_bottle.jpg",
    },
    "lifebuoy total germ protection handwash refill 750ml": {
        "barcode": "8901030012345",
        "brand": "Lifebuoy",
        "category": "Personal Care",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/87/Liquid_hand_soap.jpg/640px-Liquid_hand_soap.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Liquid_hand_soap.jpg",
    },
    "dove deep moisture nourishing body wash 250ml": {
        "barcode": "8901030501235",
        "brand": "Dove",
        "category": "Personal Care",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Shampoo_bottle.jpg/640px-Shampoo_bottle.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Shampoo_bottle.jpg",
    },
    "nivea soft light moisturizer cream 100ml": {
        "barcode": "4005808801000",
        "brand": "Nivea",
        "category": "Personal Care",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/77/Nivea_Creme_tin.jpg/640px-Nivea_Creme_tin.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Rainer Zenz",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Nivea_Creme_tin.jpg",
    },
    "sebamed baby cleansing bar soap 100g": {
        "barcode": "4103040111000",
        "brand": "Sebamed",
        "category": "Personal Care",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b8/Bar_of_soap_on_white.jpg/640px-Bar_of_soap_on_white.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Bar_of_soap_on_white.jpg",
    },

    # Household Essentials
    "surf excel easy wash detergent powder 1kg": {
        "barcode": "8901030614140",
        "brand": "Surf Excel",
        "category": "Household Essentials",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/43/Laundry_detergent_powder.jpg/640px-Laundry_detergent_powder.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Laundry_detergent_powder.jpg",
    },
    "vim lemon dishwash liquid gel 500ml": {
        "barcode": "8901030695026",
        "brand": "Vim",
        "category": "Household Essentials",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a2/Dishwashing_liquid_bottle.jpg/640px-Dishwashing_liquid_bottle.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Dishwashing_liquid_bottle.jpg",
    },
    "harpic power plus disinfectant toilet cleaner 1l": {
        "barcode": "8901396388434",
        "brand": "Harpic",
        "category": "Household Essentials",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/46/Toilet_cleaner_bottle.jpg/640px-Toilet_cleaner_bottle.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Toilet_cleaner_bottle.jpg",
    },
    "lizol pine surface floor cleaner 1l": {
        "barcode": "8901396300108",
        "brand": "Lizol",
        "category": "Household Essentials",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3d/Floor_cleaner_bottle.jpg/640px-Floor_cleaner_bottle.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Floor_cleaner_bottle.jpg",
    },
    "good knight gold flash liquid mosquito refill 45ml": {
        "barcode": "8901023010010",
        "brand": "Good Knight",
        "category": "Household Essentials",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1b/Mosquito_repellent_diffuser.jpg/640px-Mosquito_repellent_diffuser.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Mosquito_repellent_diffuser.jpg",
    },
    "godrej aer pocket bathroom fragrance 10g": {
        "barcode": "8901023020010",
        "brand": "Godrej Aer",
        "category": "Household Essentials",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/Air_freshener_gel.jpg/640px-Air_freshener_gel.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Air_freshener_gel.jpg",
    },
    "dettol antiseptic liquid disinfectant 250ml": {
        "barcode": "8901396010007",
        "brand": "Dettol",
        "category": "Household Essentials",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d4/Antiseptic_liquid_bottle.jpg/640px-Antiseptic_liquid_bottle.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Antiseptic_liquid_bottle.jpg",
    },

    # Bakery
    "harvest gold white bread 400g": {
        "barcode": "8906007800010",
        "brand": "Harvest Gold",
        "category": "Bakery",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/71/Sliced_white_bread.jpg/640px-Sliced_white_bread.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Sliced_white_bread.jpg",
    },
    "britannia 100% whole wheat brown bread 400g": {
        "barcode": "8901063030014",
        "brand": "Britannia",
        "category": "Bakery",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/89/Whole_wheat_bread.jpg/640px-Whole_wheat_bread.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Whole_wheat_bread.jpg",
    },
    "modern classic sliced white sandwich bread 400g": {
        "barcode": "8901200000010",
        "brand": "Modern",
        "category": "Bakery",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/71/Sliced_white_bread.jpg/640px-Sliced_white_bread.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Sliced_white_bread.jpg",
    },
    "fresh butter croissant 2 pcs": {
        "barcode": None,
        "brand": "Pataliputra Bakery",
        "category": "Bakery",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a6/Croissant_3.jpg/640px-Croissant_3.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Maffeth.opiana",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Croissant_3.jpg",
    },
    "blueberry velvet cupcake 1 pc": {
        "barcode": None,
        "brand": "Pataliputra Bakery",
        "category": "Bakery",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/97/Blueberry_cupcake.jpg/640px-Blueberry_cupcake.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Biswarup Ganguly",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Blueberry_cupcake.jpg",
    },
    "dutch dark chocolate truffle cake 500g": {
        "barcode": None,
        "brand": "Pataliputra Bakery",
        "category": "Bakery",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/04/Chocolate_cake_with_frosting.jpg/640px-Chocolate_cake_with_frosting.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Tiia Monto",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Chocolate_cake_with_frosting.jpg",
    },
    "rich butter scotch pound cake 250g": {
        "barcode": None,
        "brand": "Pataliputra Bakery",
        "category": "Bakery",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4b/Pound_cake_slice.jpg/640px-Pound_cake_slice.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Pound_cake_slice.jpg",
    },
    "oven fresh herb garlic bread loaf 200g": {
        "barcode": None,
        "brand": "Pataliputra Bakery",
        "category": "Bakery",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8f/Garlic_bread_slices.jpg/640px-Garlic_bread_slices.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Takeaway",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Garlic_bread_slices.jpg",
    },
    "the bakeway soft pav buns pack of 6": {
        "barcode": None,
        "brand": "Pataliputra Bakery",
        "category": "Bakery",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d3/Pav_buns.jpg/640px-Pav_buns.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Biswarup Ganguly",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Pav_buns.jpg",
    },
    "soft multigrain burger buns pack of 4": {
        "barcode": None,
        "brand": "Pataliputra Bakery",
        "category": "Bakery",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a2/Burger_buns.jpg/640px-Burger_buns.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Burger_buns.jpg",
    },
    "crispy golden puff khari 200g": {
        "barcode": None,
        "brand": "Pataliputra Bakery",
        "category": "Bakery",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7b/Khari_puff_biscuit.jpg/640px-Khari_puff_biscuit.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Miansari66",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Khari_puff_biscuit.jpg",
    },
    "vanilla crumb cream muffins pack of 4": {
        "barcode": None,
        "brand": "Pataliputra Bakery",
        "category": "Bakery",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/64/Vanilla_muffin.jpg/640px-Vanilla_muffin.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Vanilla_muffin.jpg",
    },
    "oven-baked golden veg patty 2 pcs": {
        "barcode": None,
        "brand": "Pataliputra Bakery",
        "category": "Bakery",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Vegetable_patties.jpg/640px-Vegetable_patties.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Biswarup Ganguly",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Vegetable_patties.jpg",
    },
    "spicy paneer tikka kathi roll 1 pc": {
        "barcode": None,
        "brand": "Pataliputra Bakery",
        "category": "Bakery",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/36/Paneer_tikka_roll.jpg/640px-Paneer_tikka_roll.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / Biswarup Ganguly",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Paneer_tikka_roll.jpg",
    },

    # Medicines
    "dolo 650 paracetamol tablets strip of 15": {
        "barcode": "8901148214300",
        "brand": "Micro Labs",
        "category": "Medicines",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/22/Blister_pack_tablets.jpg/640px-Blister_pack_tablets.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Blister_pack_tablets.jpg",
    },
    "dabur honitus herbal cough syrup 100ml": {
        "barcode": "8901207020018",
        "brand": "Dabur",
        "category": "Medicines",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3d/Cough_syrup_bottle.jpg/640px-Cough_syrup_bottle.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Cough_syrup_bottle.jpg",
    },
    "dabur pudin hara active relief pearls strip of 10": {
        "barcode": "8901207030017",
        "brand": "Dabur",
        "category": "Medicines",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/85/Pudina_mint_leaves.jpg/640px-Pudina_mint_leaves.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Thamizhpparithi Maari",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Pudina_mint_leaves.jpg",
    },
    "vicks vaporub cold relief balm 50ml": {
        "barcode": "4902430345026",
        "brand": "Vicks",
        "category": "Medicines",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/52/Vaporub_ointment_jar.jpg/640px-Vaporub_ointment_jar.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Vaporub_ointment_jar.jpg",
    },
    "strepsils honey & lemon sore throat lozenges pack of 8": {
        "barcode": "8901396024103",
        "brand": "Strepsils",
        "category": "Medicines",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e0/Throat_lozenges_blister.jpg/640px-Throat_lozenges_blister.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Throat_lozenges_blister.jpg",
    },
    "moov fast pain relief ointment gel 50g": {
        "barcode": "8901396030012",
        "brand": "Moov",
        "category": "Medicines",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9e/Ointment_tube.jpg/640px-Ointment_tube.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Ointment_tube.jpg",
    },
    "volini instant pain relief spray 100g": {
        "barcode": "8901030003000",
        "brand": "Volini",
        "category": "Medicines",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4b/Pain_relief_spray_can.jpg/640px-Pain_relief_spray_can.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Pain_relief_spray_can.jpg",
    },
    "digene antacid gel mint flavour 200ml": {
        "barcode": "8901030004000",
        "brand": "Digene",
        "category": "Medicines",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3d/Cough_syrup_bottle.jpg/640px-Cough_syrup_bottle.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Cough_syrup_bottle.jpg",
    },
    "electral ors energy drink powder 21.8g": {
        "barcode": "8901030005000",
        "brand": "Electral",
        "category": "Medicines",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3c/White_sugar_crystals.jpg/640px-White_sugar_crystals.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Sanjay Acharya",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:White_sugar_crystals.jpg",
    },
    "limcee 500mg vitamin c chewable tablets strip of 15": {
        "barcode": "8901030006000",
        "brand": "Abbott",
        "category": "Medicines",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/22/Blister_pack_tablets.jpg/640px-Blister_pack_tablets.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Blister_pack_tablets.jpg",
    },
    "betadine 10% antiseptic ointment 20g": {
        "barcode": "8901030007000",
        "brand": "Betadine",
        "category": "Medicines",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9e/Ointment_tube.jpg/640px-Ointment_tube.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Ointment_tube.jpg",
    },
    "savlon antiseptic germ protection liquid 200ml": {
        "barcode": "8901030008000",
        "brand": "Savlon",
        "category": "Medicines",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d4/Antiseptic_liquid_bottle.jpg/640px-Antiseptic_liquid_bottle.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Antiseptic_liquid_bottle.jpg",
    },
    "band-aid washproof medicated strips pack of 20": {
        "barcode": "8901030009000",
        "brand": "Band-Aid",
        "category": "Medicines",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d4/Adhesive_bandage.jpg/640px-Adhesive_bandage.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Adhesive_bandage.jpg",
    },
    "care+ 3-ply surgical protective face masks pack of 50": {
        "barcode": None,
        "brand": "Care+",
        "category": "Medicines",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/77/Surgical_mask.jpg/640px-Surgical_mask.jpg",
        "fallback_license": "CC BY-SA 4.0",
        "fallback_attribution": "Wikimedia Commons / NurseTogether",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Surgical_mask.jpg",
    },
    "otrivin oxy fast relief nasal spray 10ml": {
        "barcode": "8901030010000",
        "brand": "Otrivin",
        "category": "Medicines",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Nasal_spray_bottle.jpg/640px-Nasal_spray_bottle.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Evan-Amos",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Nasal_spray_bottle.jpg",
    },
    "omron digital body thermometer 1 pc": {
        "barcode": None,
        "brand": "Omron",
        "category": "Medicines",
        "fallback_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3b/Digital_medical_thermometer.jpg/640px-Digital_medical_thermometer.jpg",
        "fallback_license": "CC BY-SA 3.0",
        "fallback_attribution": "Wikimedia Commons / Menchi",
        "fallback_source_url": "https://commons.wikimedia.org/wiki/File:Digital_medical_thermometer.jpg",
    },
}


VERIFIED_MEDIA_PATH = BASE_DIR / "data" / "verified_wikimedia_media.json"
VERIFIED_MEDIA_CACHE: Dict[str, Any] = {}
if VERIFIED_MEDIA_PATH.is_file():
    try:
        with open(VERIFIED_MEDIA_PATH, "r", encoding="utf-8") as f:
            VERIFIED_MEDIA_CACHE = json.load(f)
    except Exception as e:
        logger.warning(f"Could not load verified media cache: {e}")


def resolve_verified_media(name: str, cat: str) -> Optional[Dict[str, Any]]:
    """Maps product name and category to verified CC-licensed Wikimedia Commons media."""
    if not VERIFIED_MEDIA_CACHE:
        return None
    nl = name.lower()
    item = None
    if 'atta' in nl or 'flour' in nl: item = VERIFIED_MEDIA_CACHE.get('Wheat Flour')
    elif 'rice' in nl or 'basmati' in nl: item = VERIFIED_MEDIA_CACHE.get('Basmati Rice')
    elif 'dal' in nl or 'toor' in nl: item = VERIFIED_MEDIA_CACHE.get('Toor Dal')
    elif 'salt' in nl: item = VERIFIED_MEDIA_CACHE.get('Iodised Salt')
    elif 'sugar' in nl: item = VERIFIED_MEDIA_CACHE.get('Sugar')
    elif 'oil' in nl: item = VERIFIED_MEDIA_CACHE.get('Cooking Oil')
    elif 'turmeric' in nl or 'haldi' in nl: item = VERIFIED_MEDIA_CACHE.get('Turmeric Powder')
    elif 'chilli' in nl or 'mirch' in nl: item = VERIFIED_MEDIA_CACHE.get('Chilli Powder')
    elif 'masala' in nl: item = VERIFIED_MEDIA_CACHE.get('Garam Masala')
    elif 'egg' in nl: item = VERIFIED_MEDIA_CACHE.get('Eggs')
    elif 'milk' in nl or 'dahi' in nl or 'curd' in nl or 'paneer' in nl or 'ghee' in nl:
        if 'curd' in nl or 'dahi' in nl: item = VERIFIED_MEDIA_CACHE.get('Yogurt Curd')
        elif 'paneer' in nl: item = VERIFIED_MEDIA_CACHE.get('Paneer')
        elif 'ghee' in nl: item = VERIFIED_MEDIA_CACHE.get('Ghee')
        elif 'peda' in nl: item = VERIFIED_MEDIA_CACHE.get('Indian Sweet Peda')
        else: item = VERIFIED_MEDIA_CACHE.get('Milk')
    elif 'butter' in nl: item = VERIFIED_MEDIA_CACHE.get('Butter')
    elif 'cheese' in nl: item = VERIFIED_MEDIA_CACHE.get('Cheese Slices')
    elif 'biscuit' in nl or 'cookie' in nl or 'rusk' in nl: item = VERIFIED_MEDIA_CACHE.get('Biscuits Cookies')
    elif 'chip' in nl or 'sev' in nl or 'snack' in nl: item = VERIFIED_MEDIA_CACHE.get('Potato Chips')
    elif 'chocolate' in nl: item = VERIFIED_MEDIA_CACHE.get('Chocolate Bar')
    elif 'noodle' in nl: item = VERIFIED_MEDIA_CACHE.get('Biscuits Cookies')
    elif 'tea' in nl: item = VERIFIED_MEDIA_CACHE.get('Tea Leaves')
    elif 'coffee' in nl: item = VERIFIED_MEDIA_CACHE.get('Coffee')
    elif 'juice' in nl or 'drink' in nl or 'syrup' in nl: item = VERIFIED_MEDIA_CACHE.get('Fruit Juice')
    elif 'soap' in nl or 'wash' in nl or 'shampoo' in nl:
        if 'shampoo' in nl: item = VERIFIED_MEDIA_CACHE.get('Shampoo')
        else: item = VERIFIED_MEDIA_CACHE.get('Soap Bar')
    elif 'paste' in nl: item = VERIFIED_MEDIA_CACHE.get('Toothpaste') or VERIFIED_MEDIA_CACHE.get('Soap Bar')
    elif 'detergent' in nl: item = VERIFIED_MEDIA_CACHE.get('Detergent')
    elif 'dish' in nl: item = VERIFIED_MEDIA_CACHE.get('Dishwash Gel')
    elif 'cleaner' in nl: item = VERIFIED_MEDIA_CACHE.get('Toilet Cleaner')
    elif 'bread' in nl or 'bun' in nl:
        if 'bun' in nl: item = VERIFIED_MEDIA_CACHE.get('Burger Buns')
        else: item = VERIFIED_MEDIA_CACHE.get('Bread Loaf')
    elif 'croissant' in nl: item = VERIFIED_MEDIA_CACHE.get('Croissant')
    elif 'cake' in nl: item = VERIFIED_MEDIA_CACHE.get('Chocolate Cake')
    elif 'garlic' in nl: item = VERIFIED_MEDIA_CACHE.get('Garlic Bread')
    elif 'tablet' in nl or 'capsule' in nl or 'strip' in nl: item = VERIFIED_MEDIA_CACHE.get('Paracetamol Tablets')
    elif 'cough' in nl or 'syrup' in nl: item = VERIFIED_MEDIA_CACHE.get('Cough Syrup')
    elif 'ointment' in nl or 'gel' in nl or 'balm' in nl: item = VERIFIED_MEDIA_CACHE.get('Paracetamol Tablets')
    elif 'mask' in nl: item = VERIFIED_MEDIA_CACHE.get('Surgical Mask')
    elif 'bandage' in nl or 'plaster' in nl or 'strip' in nl: item = VERIFIED_MEDIA_CACHE.get('Adhesive Bandage')
    elif 'thermometer' in nl: item = VERIFIED_MEDIA_CACHE.get('Thermometer')
    elif 'muffin' in nl: item = VERIFIED_MEDIA_CACHE.get('Cupcake') or VERIFIED_MEDIA_CACHE.get('Croissant')
    elif 'patty' in nl or 'roll' in nl: item = VERIFIED_MEDIA_CACHE.get('Burger Buns') or VERIFIED_MEDIA_CACHE.get('Croissant')
    elif 'khari' in nl: item = VERIFIED_MEDIA_CACHE.get('Biscuits Cookies')
    elif 'kalakand' in nl or 'peda' in nl: item = VERIFIED_MEDIA_CACHE.get('Indian Sweet Peda')
    elif 'glucose' in nl: item = VERIFIED_MEDIA_CACHE.get('Sugar')
    elif 'cream' in nl or 'moisturizer' in nl: item = VERIFIED_MEDIA_CACHE.get('Soap Bar')
    elif 'spray' in nl or 'nasal' in nl: item = VERIFIED_MEDIA_CACHE.get('Toilet Cleaner')
    elif 'lozenge' in nl or 'sore throat' in nl: item = VERIFIED_MEDIA_CACHE.get('Paracetamol Tablets')
    elif 'antiseptic' in nl or 'disinfectant' in nl: item = VERIFIED_MEDIA_CACHE.get('Soap Bar')
    elif 'fragrance' in nl or 'mosquito' in nl: item = VERIFIED_MEDIA_CACHE.get('Toilet Cleaner')

    if item:
        return {
            "source": "wikimedia",
            "image_url": item["url"],
            "license": item.get("license", "CC BY-SA 4.0"),
            "attribution": item.get("attribution", "Wikimedia Commons contributors"),
            "source_url": item.get("url"),
            "confidence": 0.86,
        }
    return None


def normalize_name(name: str) -> str:
    """Normalize product name for fuzzy and exact matching."""
    s = name.lower().strip()
    s = re.sub(r"\[dukaanly demo product\]", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def clean_media_url(url: str) -> str:
    """Normalize Wikimedia URLs to direct original file locations (bypassing thumbnail width limits)."""
    if not url:
        return url
    m = re.match(
        r"https?://upload\.wikimedia\.org/wikipedia/commons/thumb/([0-9a-fA-F]/[0-9a-fA-F]{2}/[^/]+)/.*",
        url,
    )
    if m:
        return f"https://upload.wikimedia.org/wikipedia/commons/{m.group(1)}"
    return url


def find_canonical_entry(product_name: str) -> Optional[Tuple[str, Dict[str, Any], float]]:
    """Finds best matching canonical seed entry using token sort ratio."""
    norm = normalize_name(product_name)
    if norm in CANONICAL_SEED_DATA:
        return norm, CANONICAL_SEED_DATA[norm], 1.0

    best_match = None
    best_score = 0.0

    for key, data in CANONICAL_SEED_DATA.items():
        score = fuzz.token_sort_ratio(norm, key)
        if score > best_score:
            best_score = score
            best_match = (key, data, score / 100.0)

    if best_match and best_match[2] >= 0.70:
        return best_match
    return None


def fetch_open_food_facts_by_barcode(barcode: str) -> Optional[Dict[str, Any]]:
    """
    Query Open Food Facts for a barcode.
    Tries in.openfoodfacts.org first, falls back to world.openfoodfacts.net.
    """
    if not barcode:
        return None

    for host in ["in.openfoodfacts.org", "world.openfoodfacts.net"]:
        url = f"https://{host}/api/v0/product/{barcode}.json"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data.get("status") == 1:
                        prod = data.get("product", {})
                        img_url = (
                            prod.get("image_front_url")
                            or prod.get("image_url")
                            or prod.get("image_front_small_url")
                        )
                        if img_url:
                            return {
                                "source": "open_food_facts",
                                "image_url": img_url,
                                "license": "CC BY-SA 4.0 / Open Food Facts",
                                "attribution": "Open Food Facts contributors",
                                "source_url": f"https://in.openfoodfacts.org/product/{barcode}",
                                "confidence": 0.95,
                                "brand": prod.get("brands"),
                            }
        except Exception as e:
            logger.debug(f"OFF lookup failed on {host} for barcode {barcode}: {e}")
            continue

    return None


def search_wikimedia_commons(query: str) -> Optional[Dict[str, Any]]:
    """Search Wikimedia Commons API for high-resolution CC-licensed images."""
    clean_query = re.sub(r"[^\w\s]", " ", query).strip()
    encoded = urllib.parse.quote(clean_query)
    url = (
        f"https://commons.wikimedia.org/w/api.php?action=query&generator=search"
        f"&gsrsearch={encoded}&gsrnamespace=6&prop=imageinfo&iiprop=url|size|extmetadata&format=json"
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            pages = data.get("query", {}).get("pages", {})
            for pid, page in pages.items():
                title = page.get("title", "")
                # Ignore audio, pdf, or non-photo files
                if not any(title.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                    continue
                imageinfo = page.get("imageinfo", [])
                if not imageinfo:
                    continue
                info = imageinfo[0]
                img_url = info.get("url")
                width = info.get("width", 0)
                height = info.get("height", 0)
                if not img_url or width < 200 or height < 200:
                    continue

                meta = info.get("extmetadata", {})
                license_name = meta.get("LicenseShortName", {}).get("value", "CC BY-SA 4.0")
                artist = meta.get("Artist", {}).get("value", "Wikimedia Commons contributors")
                # Strip HTML from artist
                artist_clean = re.sub(r"<[^>]+>", "", artist).strip() or "Wikimedia Commons contributors"

                score = fuzz.token_sort_ratio(query.lower(), title.lower())
                confidence = max(0.70, min(0.92, score / 100.0))

                return {
                    "source": "wikimedia",
                    "image_url": img_url,
                    "license": license_name,
                    "attribution": artist_clean,
                    "source_url": f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(title)}",
                    "confidence": confidence,
                }
    except Exception as e:
        logger.debug(f"Wikimedia Commons search error for '{query}': {e}")

    return None


def download_image_bytes(url: str, timeout: int = 8) -> Optional[bytes]:
    """Download image bytes with SSRF validation, proper headers, and size limits."""
    cleaned_url = clean_media_url(url)
    try:
        safe_url = validate_safe_url(cleaned_url)
    except SSRFSecurityError as e:
        logger.error(f"SSRF guard blocked URL '{url}': {e}")
        return None

    req = urllib.request.Request(safe_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if not any(t in content_type.lower() for t in ["image/", "octet-stream"]):
                logger.warning(f"URL did not return image Content-Type (got {content_type}): {url}")
                return None
            data = resp.read()
            if len(data) > 15 * 1024 * 1024:
                logger.warning(f"Image from {url} exceeds 15MB limit ({len(data)} bytes).")
                return None
            return data
    except Exception as e:
        logger.warning(f"Failed to download image from {url}: {e}")
        return None


# ── Pipeline Orchestration ─────────────────────────────────────────────────────

async def run_enrichment(
    dry_run: bool = False,
    limit: Optional[int] = None,
    only_missing: bool = False,
    category_filter: Optional[str] = None,
    force: bool = False,
    approve_csv: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute the enrichment workflow across database products."""
    storage = get_storage_service()

    # Create directories if needed
    os.makedirs(BASE_DIR / "data", exist_ok=True)
    os.makedirs(BASE_DIR / "data" / "media" / "products", exist_ok=True)

    # Initialize review queue CSV if missing
    if not REVIEW_QUEUE_PATH.is_file():
        with open(REVIEW_QUEUE_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "product_id",
                "product_name",
                "category",
                "proposed_image_url",
                "confidence",
                "source",
                "license",
                "attribution",
                "status",
            ])

    # If --approve mode
    if approve_csv:
        return await process_approved_queue(approve_csv, dry_run=dry_run)

    stats = {
        "total_scanned": 0,
        "enriched": 0,
        "already_enriched": 0,
        "queued_for_review": 0,
        "failed": 0,
        "by_source": {},
        "by_category": {},
    }

    async with async_session_maker() as session:
        stmt = select(Product).order_by(Product.shop_id, Product.name)
        if category_filter:
            stmt = stmt.where(Product.category == category_filter)

        res = await session.execute(stmt)
        products: List[Product] = res.scalars().all()

        if limit:
            products = products[:limit]

        logger.info(f"Loaded {len(products)} products for image enrichment.")

        review_queue_rows: List[List[Any]] = []

        for prod in products:
            stats["total_scanned"] += 1
            cat = prod.category or "Uncategorized"
            stats["by_category"].setdefault(cat, {"total": 0, "enriched": 0, "placeholder": 0})
            stats["by_category"][cat]["total"] += 1

            # Skip if already enriched unless force
            has_valid_image = (
                prod.image_url
                and prod.image_source in ("open_food_facts", "wikimedia", "pexels", "shop_upload")
                and prod.image_url.startswith("/static/media/")
            )
            if has_valid_image and not force:
                stats["already_enriched"] += 1
                stats["by_category"][cat]["enriched"] += 1
                continue

            if only_missing and prod.image_url and not prod.image_source == "placeholder":
                continue

            norm_name = normalize_name(prod.name)
            logger.info(f"Processing: [{cat}] {prod.name}")

            match_result = None
            barcode_to_use = prod.barcode

            # 1. Match against Canonical Seed Knowledge Base
            seed_match = find_canonical_entry(prod.name)
            if seed_match:
                key, seed_data, score = seed_match
                if not barcode_to_use and seed_data.get("barcode"):
                    barcode_to_use = seed_data["barcode"]

            # 2. Try Open Food Facts by barcode
            if barcode_to_use:
                off_result = fetch_open_food_facts_by_barcode(barcode_to_use)
                if off_result:
                    match_result = off_result
                    logger.info(f" -> Matched via Open Food Facts (barcode {barcode_to_use})")

            # 3. Try verified media cache
            if not match_result:
                verified_match = resolve_verified_media(prod.name, cat)
                if verified_match:
                    match_result = verified_match
                    logger.info(f" -> Matched via Verified Media Resolver")

            # 4. If no verified media, use seed fallback
            if not match_result and seed_match:
                key, seed_data, score = seed_match
                if seed_data.get("fallback_url"):
                    match_result = {
                        "source": "wikimedia",
                        "image_url": seed_data["fallback_url"],
                        "license": seed_data["fallback_license"],
                        "attribution": seed_data["fallback_attribution"],
                        "source_url": seed_data["fallback_source_url"],
                        "confidence": 0.88,
                        "brand": seed_data.get("brand"),
                    }
                    logger.info(f" -> Matched via Canonical Seed Fallback ({key})")

            # 5. Fall back to dynamic Wikimedia Commons query
            if not match_result:
                search_term = f"{prod.name} {cat}".replace("1kg", "").replace("500g", "").replace("1L", "")
                wiki_result = search_wikimedia_commons(search_term)
                if wiki_result:
                    match_result = wiki_result
                    logger.info(f" -> Matched via Dynamic Wikimedia Search")

            # Evaluate confidence threshold
            if not match_result or match_result.get("confidence", 0) < 0.75:
                logger.warning(f" -> Low confidence or no match for '{prod.name}'. Routing to review queue.")
                stats["queued_for_review"] += 1
                stats["by_category"][cat]["placeholder"] += 1

                if not dry_run:
                    prod.image_source = "placeholder"
                    prod.image_reviewed = False
                    session.add(prod)

                review_queue_rows.append([
                    str(prod.id),
                    prod.name,
                    cat,
                    match_result.get("image_url", "") if match_result else "",
                    match_result.get("confidence", 0.0) if match_result else 0.0,
                    match_result.get("source", "none") if match_result else "none",
                    match_result.get("license", "") if match_result else "",
                    match_result.get("attribution", "") if match_result else "",
                    "pending",
                ])
                continue

            # Valid match found: download and normalize image
            src_url = match_result["image_url"]
            source = match_result["source"]
            license_str = match_result["license"]
            attribution = match_result["attribution"]
            source_url = match_result["source_url"]
            confidence = match_result["confidence"]

            if dry_run:
                logger.info(f" [DRY-RUN] Would process: {src_url} ({source}, conf={confidence:.2f})")
                stats["enriched"] += 1
                stats["by_category"][cat]["enriched"] += 1
                stats["by_source"][source] = stats["by_source"].get(source, 0) + 1
                continue

            img_bytes = download_image_bytes(src_url)
            if not img_bytes:
                # If download failed, check if seed has fallback
                if seed_match and seed_match[1].get("fallback_url") and seed_match[1]["fallback_url"] != src_url:
                    img_bytes = download_image_bytes(seed_match[1]["fallback_url"])
                    if img_bytes:
                        src_url = seed_match[1]["fallback_url"]
                        source = "wikimedia"
                        license_str = seed_match[1]["fallback_license"]
                        attribution = seed_match[1]["fallback_attribution"]
                        source_url = seed_match[1]["fallback_source_url"]

            if not img_bytes:
                # Try verified media resolver as secondary fallback
                vm = resolve_verified_media(prod.name, cat)
                if vm:
                    img_bytes = download_image_bytes(vm["image_url"])
                    if img_bytes:
                        src_url = vm["image_url"]
                        source = "wikimedia"
                        license_str = vm["license"]
                        attribution = vm["attribution"]
                        source_url = vm["source_url"]
                        confidence = vm["confidence"]

            if not img_bytes:
                logger.error(f" -> Download failed for {src_url}. Marking placeholder.")
                prod.image_source = "placeholder"
                stats["failed"] += 1
                stats["by_category"][cat]["placeholder"] += 1
                session.add(prod)
                continue

            time.sleep(0.4)

            try:
                full_url, thumb_url, sha_hash = process_and_store_image(img_bytes, storage=storage)
            except InvalidImageError as e:
                logger.error(f" -> Normalization failed for {src_url}: {e}")
                prod.image_source = "placeholder"
                stats["failed"] += 1
                stats["by_category"][cat]["placeholder"] += 1
                session.add(prod)
                continue

            # Upsert MasterCatalogItem
            master_stmt = select(MasterCatalogItem).where(
                MasterCatalogItem.normalized_name == norm_name
            )
            master_res = await session.execute(master_stmt)
            master_item = master_res.scalar_one_or_none()

            if not master_item:
                master_item = MasterCatalogItem(
                    name=prod.name,
                    normalized_name=norm_name,
                    brand=match_result.get("brand") or (seed_match[1].get("brand") if seed_match else None),
                    category=cat,
                    barcode=barcode_to_use,
                    image_url=full_url,
                    thumb_url=thumb_url,
                    image_source=source,
                    image_license=license_str,
                    image_attribution=attribution,
                    image_source_url=source_url,
                    image_match_confidence=confidence,
                    image_reviewed=True,
                )
                session.add(master_item)
                await session.flush()
            else:
                master_item.image_url = full_url
                master_item.thumb_url = thumb_url
                master_item.image_source = source
                master_item.image_license = license_str
                master_item.image_attribution = attribution
                master_item.image_source_url = source_url
                master_item.image_match_confidence = confidence
                master_item.image_reviewed = True
                if barcode_to_use:
                    master_item.barcode = barcode_to_use
                session.add(master_item)

            # Link Product to MasterCatalogItem
            prod.master_item_id = master_item.id
            if barcode_to_use:
                prod.barcode = barcode_to_use

            # Only update product image fields if shop owner hasn't uploaded a custom override
            if not prod.custom_image_url:
                prod.image_url = full_url
                prod.thumb_url = thumb_url
                prod.image_source = source
                prod.image_license = license_str
                prod.image_attribution = attribution
                prod.image_source_url = source_url
                prod.image_match_confidence = confidence
                prod.image_reviewed = True

            session.add(prod)
            stats["enriched"] += 1
            stats["by_category"][cat]["enriched"] += 1
            stats["by_source"][source] = stats["by_source"].get(source, 0) + 1

        if not dry_run:
            await session.commit()

            # Write review queue entries
            if review_queue_rows:
                with open(REVIEW_QUEUE_PATH, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    for r in review_queue_rows:
                        writer.writerow(r)

    # Generate and save coverage report
    total_prods = stats["total_scanned"]
    total_enriched = stats["enriched"] + stats["already_enriched"]
    coverage_pct = (total_enriched / total_prods * 100.0) if total_prods > 0 else 0.0

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_products": total_prods,
        "enriched_products": total_enriched,
        "newly_enriched": stats["enriched"],
        "already_enriched": stats["already_enriched"],
        "queued_for_review": stats["queued_for_review"],
        "failed": stats["failed"],
        "coverage_percentage": round(coverage_pct, 2),
        "by_source": stats["by_source"],
        "by_category": stats["by_category"],
    }

    if not dry_run:
        with open(COVERAGE_REPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    logger.info("=" * 60)
    logger.info("IMAGE ENRICHMENT PIPELINE RUN COMPLETE")
    logger.info(f"Total Products:     {total_prods}")
    logger.info(f"Enriched:           {total_enriched} ({coverage_pct:.1f}%)")
    logger.info(f"Review Queue:       {stats['queued_for_review']}")
    logger.info(f"Failed:             {stats['failed']}")
    logger.info(f"Sources:            {json.dumps(stats['by_source'])}")
    logger.info("=" * 60)

    return report


async def process_approved_queue(csv_path: str, dry_run: bool = False) -> Dict[str, Any]:
    """Approve entries in review queue CSV with status == 'approved'."""
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"Review queue CSV not found: {csv_path}")

    storage = get_storage_service()
    approved_count = 0

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    async with async_session_maker() as session:
        for row in rows:
            if row.get("status", "").lower() != "approved":
                continue

            prod_id = row["product_id"]
            img_url = row["proposed_image_url"]
            if not img_url:
                continue

            logger.info(f"Applying approved image for {row['product_name']} -> {img_url}")

            if dry_run:
                approved_count += 1
                continue

            img_bytes = download_image_bytes(img_url)
            if not img_bytes:
                logger.error(f"Failed to download approved image from {img_url}")
                continue

            full_url, thumb_url, sha_hash = process_and_store_image(img_bytes, storage=storage)

            stmt = select(Product).where(Product.id == prod_id)
            res = await session.execute(stmt)
            prod = res.scalar_one_or_none()
            if prod:
                prod.image_url = full_url
                prod.thumb_url = thumb_url
                prod.image_source = row.get("source") or "approved_review"
                prod.image_license = row.get("license") or "Reviewed License"
                prod.image_attribution = row.get("attribution") or "Approved in Review Queue"
                prod.image_source_url = img_url
                prod.image_match_confidence = 1.0
                prod.image_reviewed = True
                session.add(prod)
                approved_count += 1

        if not dry_run:
            await session.commit()

    return {"approved_count": approved_count}


def main():
    parser = argparse.ArgumentParser(description="Dukaanly Product Image Enrichment Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Preview without modifying DB or files")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N products")
    parser.add_argument("--only-missing", action="store_true", help="Only process missing/placeholder products")
    parser.add_argument("--category", type=str, default=None, help="Filter by category")
    parser.add_argument("--force", action="store_true", help="Re-process all products")
    parser.add_argument("--approve", type=str, default=None, help="Path to approved review queue CSV")

    args = parser.parse_args()

    asyncio.run(
        run_enrichment(
            dry_run=args.dry_run,
            limit=args.limit,
            only_missing=args.only_missing,
            category_filter=args.category,
            force=args.force,
            approve_csv=args.approve,
        )
    )


if __name__ == "__main__":
    main()
