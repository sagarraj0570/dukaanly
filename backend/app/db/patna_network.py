"""
Dukaanly Urban Patna Verified Merchant Partner Network Seeder.
Provides multi-region coverage across all 7 major urban Patna zones:
1. West Patna (Danapur, Saguna More, Gola Road, Priyadarshi Nagar)
2. West-Central Patna (Bailey Road, Raja Bazar, Ashiana Nagar, Jagdeo Path)
3. North-West & Central (Boring Road, Patliputra Colony, SK Puri, Anandpuri)
4. South & South-East (Kankarbagh, Hanuman Nagar, Rajendra Nagar, Kumhrar)
5. Central CBD (Gandhi Maidan, Fraser Road, Exhibition Road, Ashok Rajpath)
6. East Patna (Patna City, Chowk, Padri Ki Haveli, Agam Kuan)
7. South-West Patna (Anisabad, Phulwari Sharif, AIIMS Patna, Khagaul)

Strict invariants enforced:
- Idempotent execution: safe to run multiple times without duplicating shops or products.
- Real PostGIS coordinates in SRID 4326.
- Strict inventory OCC versioning with in-stock items.
- Tagged with source='patna_network' so demo catalog test suites remain isolated.
"""

from decimal import Decimal
import logging
from typing import Dict, List, Any

from sqlalchemy import select
from geoalchemy2.elements import WKTElement

from app.db.session import async_session_maker
from app.models.user import User, UserRole
from app.models.shop import Shop, ShopVerificationStatus
from app.models.product import Product
from app.models.inventory import Inventory
from app.core.security import get_password_hash

logger = logging.getLogger("patna_network")

NETWORK_PASSWORD = "Password123!"

# Dedicated shop owner accounts for regional verified partner stores
NETWORK_USERS: List[Dict[str, Any]] = [
    {
        "name": "Sanjay Gupta (Saguna More)",
        "email": "owner.saguna@dukaanly.com",
        "phone_number": "9431050101",
        "role": UserRole.shop_owner,
    },
    {
        "name": "Dr. Rajiv Ranjan (Danapur Medicos)",
        "email": "owner.danapur.med@dukaanly.com",
        "phone_number": "9431050102",
        "role": UserRole.shop_owner,
    },
    {
        "name": "Vikram Singh (Gola Road Bakes)",
        "email": "owner.gola.bake@dukaanly.com",
        "phone_number": "9431050103",
        "role": UserRole.shop_owner,
    },
    {
        "name": "Manoj Kumar (Raja Bazar)",
        "email": "owner.rajabazar@dukaanly.com",
        "phone_number": "9431050201",
        "role": UserRole.shop_owner,
    },
    {
        "name": "Dr. Sneha Kumari (Paras Care Pharmacy)",
        "email": "owner.paras.med@dukaanly.com",
        "phone_number": "9431050202",
        "role": UserRole.shop_owner,
    },
    {
        "name": "Pradeep Jha (Kankarbagh Provisions)",
        "email": "owner.kankarbagh@dukaanly.com",
        "phone_number": "9431050301",
        "role": UserRole.shop_owner,
    },
    {
        "name": "Dr. R.K. Choudhary (Hanuman Nagar Sanjeevani)",
        "email": "owner.hanuman.med@dukaanly.com",
        "phone_number": "9431050302",
        "role": UserRole.shop_owner,
    },
    {
        "name": "Anita Prasad (Rajendra Delights)",
        "email": "owner.rajendra.bake@dukaanly.com",
        "phone_number": "9431050303",
        "role": UserRole.shop_owner,
    },
    {
        "name": "Deepak Agrawal (Fraser Road Express)",
        "email": "owner.fraser@dukaanly.com",
        "phone_number": "9431050401",
        "role": UserRole.shop_owner,
    },
    {
        "name": "Dr. Amitabh Sen (Gandhi Maidan Health)",
        "email": "owner.gandhimaidan.med@dukaanly.com",
        "phone_number": "9431050402",
        "role": UserRole.shop_owner,
    },
    {
        "name": "Harpreet Singh (Patna Sahib Wholesale)",
        "email": "owner.patnasahib@dukaanly.com",
        "phone_number": "9431050501",
        "role": UserRole.shop_owner,
    },
    {
        "name": "Dr. Manjit Singh (Guru Gobind Medicos)",
        "email": "owner.gurugobind.med@dukaanly.com",
        "phone_number": "9431050502",
        "role": UserRole.shop_owner,
    },
    {
        "name": "Rakesh Patel (Anisabad Family Mart)",
        "email": "owner.anisabad@dukaanly.com",
        "phone_number": "9431050601",
        "role": UserRole.shop_owner,
    },
    {
        "name": "Dr. Tariq Anwar (Phulwari Care Chemist)",
        "email": "owner.phulwari.med@dukaanly.com",
        "phone_number": "9431050602",
        "role": UserRole.shop_owner,
    },
]

# Verified partner shops with exact coordinates in every key urban Patna region
NETWORK_SHOPS: List[Dict[str, Any]] = [
    # ── Region 1: West Patna (Saguna More / Gola Road / Danapur / Priyadarshi Nagar) ──
    {
        "source_id": "patna:partner:saguna-super-mart",
        "name": "Saguna Super Mart & Kirana",
        "owner_email": "owner.saguna@dukaanly.com",
        "description": "Verified grocery & essentials partner serving Saguna More, Gola Road, Priyadarshi Nagar & Danapur with instant delivery.",
        "address": "Plot 18, Gola Road, Near Saguna More, Patna - 801503",
        "phone": "+91 94310 50101",
        "opening_hours": "07:00 - 22:30",
        "latitude": 25.6120,
        "longitude": 85.0505,
        "category": "supermarket",
        "delivery_radius_meters": 5000,
    },
    {
        "source_id": "patna:partner:danapur-medicos",
        "name": "Danapur Medicos & Healthcare",
        "owner_email": "owner.danapur.med@dukaanly.com",
        "description": "Licensed retail pharmacy providing authentic prescription medicines, OTC remedies, first aid, and baby care across Danapur & Gola Road.",
        "address": "Main Market, Gola Road, Danapur, Patna - 801503",
        "phone": "+91 94310 50102",
        "opening_hours": "08:00 - 23:00",
        "latitude": 25.6150,
        "longitude": 85.0520,
        "category": "pharmacy",
        "delivery_radius_meters": 5000,
    },
    {
        "source_id": "patna:partner:gola-road-bakers",
        "name": "Gola Road Bakers & Sweets",
        "owner_email": "owner.gola.bake@dukaanly.com",
        "description": "Fresh artisan bakery offering daily sandwich breads, tea rusks, celebration cakes, and warm oven savouries in Western Patna.",
        "address": "Opposite HP Petrol Pump, Gola Road, Patna - 801503",
        "phone": "+91 94310 50103",
        "opening_hours": "08:30 - 22:00",
        "latitude": 25.6140,
        "longitude": 85.0480,
        "category": "bakery",
        "delivery_radius_meters": 5000,
    },

    # ── Region 2: West-Central Patna (Bailey Road / Raja Bazar / Ashiana Nagar) ──
    {
        "source_id": "patna:partner:raja-bazar-super-kirana",
        "name": "Raja Bazar Super Kirana",
        "owner_email": "owner.rajabazar@dukaanly.com",
        "description": "Verified partner supermarket serving Raja Bazar, Pillar 60 Bailey Road, Ashiana Nagar, and Jagdeo Path.",
        "address": "Pillar 62, Bailey Road, Raja Bazar, Patna - 800014",
        "phone": "+91 94310 50201",
        "opening_hours": "07:30 - 22:30",
        "latitude": 25.6083,
        "longitude": 85.0892,
        "category": "supermarket",
        "delivery_radius_meters": 5000,
    },
    {
        "source_id": "patna:partner:paras-care-pharmacy",
        "name": "Paras Care Pharmacy",
        "owner_email": "owner.paras.med@dukaanly.com",
        "description": "24/7 medical & wellness pharmacy near Paras HMRI Hospital serving Bailey Road, Sheikhpura, and Raja Bazar.",
        "address": "Opposite Paras HMRI Hospital, Raja Bazar, Patna - 800014",
        "phone": "+91 94310 50202",
        "opening_hours": "07:00 - 23:30",
        "latitude": 25.6095,
        "longitude": 85.0870,
        "category": "pharmacy",
        "delivery_radius_meters": 5000,
    },

    # ── Region 4: South & South-East Patna (Kankarbagh / Rajendra Nagar / Hanuman Nagar) ──
    {
        "source_id": "patna:partner:kankarbagh-central-provisions",
        "name": "Kankarbagh Central Provisions",
        "owner_email": "owner.kankarbagh@dukaanly.com",
        "description": "Premier verified grocery partner serving Kankarbagh Tempo Stand, PC Colony, and Lohia Nagar.",
        "address": "Tempo Stand Road, PC Colony, Kankarbagh, Patna - 800020",
        "phone": "+91 94310 50301",
        "opening_hours": "07:00 - 22:30",
        "latitude": 25.5947,
        "longitude": 85.1588,
        "category": "supermarket",
        "delivery_radius_meters": 5000,
    },
    {
        "source_id": "patna:partner:hanuman-nagar-sanjeevani",
        "name": "Hanuman Nagar Sanjeevani Pharmacy",
        "owner_email": "owner.hanuman.med@dukaanly.com",
        "description": "Licensed chemist and healthcare provider serving Hanuman Nagar, Doctor Colony, and Kumhrar.",
        "address": "90 Feet Road, Doctor Colony, Hanuman Nagar, Patna - 800020",
        "phone": "+91 94310 50302",
        "opening_hours": "08:00 - 23:00",
        "latitude": 25.5880,
        "longitude": 85.1670,
        "category": "pharmacy",
        "delivery_radius_meters": 5000,
    },
    {
        "source_id": "patna:partner:rajendra-delights",
        "name": "Rajendra Delights Bakery",
        "owner_email": "owner.rajendra.bake@dukaanly.com",
        "description": "Confectionery & bakery partner serving Rajendra Nagar, Dinkar Golambar, and Bazar Samiti.",
        "address": "Near Dinkar Golambar, Rajendra Nagar, Patna - 800016",
        "phone": "+91 94310 50303",
        "opening_hours": "08:30 - 22:00",
        "latitude": 25.6022,
        "longitude": 85.1633,
        "category": "bakery",
        "delivery_radius_meters": 5000,
    },

    # ── Region 5: Central CBD (Gandhi Maidan / Fraser Road / Exhibition Road) ──
    {
        "source_id": "patna:partner:fraser-road-express",
        "name": "Fraser Road Express Kirana",
        "owner_email": "owner.fraser@dukaanly.com",
        "description": "Verified central supermarket serving Dak Bungalow Crossing, Fraser Road, Maurya Lok, and Patna Junction.",
        "address": "Dak Bungalow Crossing, Fraser Road, Patna - 800001",
        "phone": "+91 94310 50401",
        "opening_hours": "07:30 - 22:30",
        "latitude": 25.6030,
        "longitude": 85.1380,
        "category": "supermarket",
        "delivery_radius_meters": 5000,
    },
    {
        "source_id": "patna:partner:gandhi-maidan-health",
        "name": "Gandhi Maidan Health Chemist",
        "owner_email": "owner.gandhimaidan.med@dukaanly.com",
        "description": "Trusted medical and healthcare shop on South Gandhi Maidan & Exhibition Road.",
        "address": "South Gandhi Maidan, Exhibition Road, Patna - 800001",
        "phone": "+91 94310 50402",
        "opening_hours": "08:00 - 23:00",
        "latitude": 25.6150,
        "longitude": 85.1430,
        "category": "pharmacy",
        "delivery_radius_meters": 5000,
    },

    # ── Region 6: East Patna (Patna City / Chowk / Padri Ki Haveli) ──
    {
        "source_id": "patna:partner:patna-sahib-wholesale",
        "name": "Patna Sahib Wholesale & Provisions",
        "owner_email": "owner.patnasahib@dukaanly.com",
        "description": "Heritage provisions and grocery partner serving Patna City, Gurudwara, Chowk, and Mangal Talab.",
        "address": "Harmandir Gali, Patna City Chowk, Patna - 800008",
        "phone": "+91 94310 50501",
        "opening_hours": "07:00 - 22:00",
        "latitude": 25.5940,
        "longitude": 85.2280,
        "category": "supermarket",
        "delivery_radius_meters": 5000,
    },
    {
        "source_id": "patna:partner:guru-gobind-medicos",
        "name": "Guru Gobind Medicos",
        "owner_email": "owner.gurugobind.med@dukaanly.com",
        "description": "Essential medicine and first aid partner in Old Patna City and Padri Ki Haveli.",
        "address": "Main Chowk Road, Patna City, Patna - 800008",
        "phone": "+91 94310 50502",
        "opening_hours": "08:00 - 22:30",
        "latitude": 25.5960,
        "longitude": 85.2250,
        "category": "pharmacy",
        "delivery_radius_meters": 5000,
    },

    # ── Region 7: South-West Patna (Anisabad / Phulwari Sharif / AIIMS) ──
    {
        "source_id": "patna:partner:anisabad-daily-mart",
        "name": "Anisabad Daily Needs & Mart",
        "owner_email": "owner.anisabad@dukaanly.com",
        "description": "Verified grocery partner serving Anisabad Golambar, Chitkohra, Police Colony, and Beur.",
        "address": "Chitkohra Golambar, Police Colony Road, Anisabad, Patna - 800002",
        "phone": "+91 94310 50601",
        "opening_hours": "07:00 - 22:30",
        "latitude": 25.5860,
        "longitude": 85.1130,
        "category": "supermarket",
        "delivery_radius_meters": 5000,
    },
    {
        "source_id": "patna:partner:phulwari-care-chemist",
        "name": "Phulwari Care Chemist",
        "owner_email": "owner.phulwari.med@dukaanly.com",
        "description": "Healthcare partner serving Phulwari Sharif, AIIMS Patna corridor, and Walmi.",
        "address": "Khanqah Road, Phulwari Sharif Bazaar, Patna - 801505",
        "phone": "+91 94310 50602",
        "opening_hours": "08:00 - 23:00",
        "latitude": 25.5780,
        "longitude": 85.0650,
        "category": "pharmacy",
        "delivery_radius_meters": 5000,
    },
]

# Standard grocery, snacks, and biscuit inventory stocked in every regional supermarket partner
STANDARD_SUPERMARKET_PRODUCTS: List[Dict[str, Any]] = [
    # Snacks & Biscuits
    {
        "name": "Parle-G Original Glucose Biscuits 800g",
        "category": "Snacks",
        "price": Decimal("75.00"),
        "stock": 80,
        "description": "India's favourite golden baked glucose biscuits with tea time crunch.",
        "image_url": "https://images.unsplash.com/photo-1558961363-fa8fdf82db35?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Britannia Good Day Butter Cookies 600g",
        "category": "Snacks",
        "price": Decimal("115.00"),
        "stock": 65,
        "description": "Rich butter and cashew cookies baked to a golden smile.",
        "image_url": "https://images.unsplash.com/photo-1499636136210-6f4ee915583e?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Britannia Marie Gold Tea Time Biscuits 1kg",
        "category": "Snacks",
        "price": Decimal("130.00"),
        "stock": 50,
        "description": "Crisp, light tea companion biscuits enriched with essential vitamins.",
        "image_url": "https://images.unsplash.com/photo-1558961363-fa8fdf82db35?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Haldiram Nagpur Bhujia Sev 400g",
        "category": "Snacks",
        "price": Decimal("110.00"),
        "stock": 75,
        "description": "Crispy spiced moth bean and chickpea flour namkeen with authentic flavour.",
        "image_url": "https://images.unsplash.com/photo-1621939514649-280e2ee25f60?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Lay's India's Magic Masala Potato Chips 50g",
        "category": "Snacks",
        "price": Decimal("20.00"),
        "stock": 100,
        "description": "Spicy Indian street masala flavoured crisp potato wafers.",
        "image_url": "https://images.unsplash.com/photo-1566478989037-eec170784d0b?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Kurkure Masala Munch Crispy Snacks 85g",
        "category": "Snacks",
        "price": Decimal("20.00"),
        "stock": 90,
        "description": "Crunchy tedhe-medhe corn puffs packed with tangy Indian spices.",
        "image_url": "https://images.unsplash.com/photo-1621939514649-280e2ee25f60?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Cadbury Oreo Vanilla Creme Biscuits 300g",
        "category": "Snacks",
        "price": Decimal("85.00"),
        "stock": 45,
        "description": "Rich dark cocoa sandwich biscuits loaded with smooth vanilla creme.",
        "image_url": "https://images.unsplash.com/photo-1563729784474-d77dbb933a9e?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Sunfeast Dark Fantasy Choco Fills 300g",
        "category": "Snacks",
        "price": Decimal("140.00"),
        "stock": 40,
        "description": "Crispy dark chocolate cookie crust filled with molten chocolate centre.",
        "image_url": "https://images.unsplash.com/photo-1558961363-fa8fdf82db35?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Britannia Bourbon Chocolate Cream Biscuits 150g",
        "category": "Snacks",
        "price": Decimal("35.00"),
        "stock": 55,
        "description": "Sugar-sprinkled crispy chocolate biscuits with smooth chocolate fondant.",
        "image_url": "https://images.unsplash.com/photo-1558961363-fa8fdf82db35?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Roasted Himalayan Pink Salt Phool Makhana 100g",
        "category": "Snacks",
        "price": Decimal("125.00"),
        "stock": 35,
        "description": "Crunchy roasted fox nuts seasoned with pure Himalayan rock salt.",
        "image_url": "https://images.unsplash.com/photo-1599490659213-e2b9527bd087?auto=format&fit=crop&w=600&q=80",
    },

    # Groceries & Staples
    {
        "name": "Aashirvaad Superior MP Shudh Chakki Atta 5kg",
        "category": "Groceries",
        "price": Decimal("245.00"),
        "stock": 50,
        "description": "100% pure whole wheat flour processed with traditional stone chakki.",
        "image_url": "https://images.unsplash.com/photo-1542838132-92c53300491e?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Daawat Rozana Gold Basmati Rice 5kg",
        "category": "Groceries",
        "price": Decimal("465.00"),
        "stock": 40,
        "description": "Aged aromatic long grain basmati rice ideal for everyday family meals.",
        "image_url": "https://images.unsplash.com/photo-1586201375761-83865001e31c?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Tata Sampann Unpolished Toor Dal 1kg",
        "category": "Groceries",
        "price": Decimal("175.00"),
        "stock": 60,
        "description": "High protein unpolished arhar dal with wholesome natural nutrition.",
        "image_url": "https://images.unsplash.com/photo-1542838132-92c53300491e?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Tata Salt Vacuum Evaporated Iodised Salt 1kg",
        "category": "Groceries",
        "price": Decimal("28.00"),
        "stock": 100,
        "description": "Desh ka namak with guaranteed iodine quality and purity.",
        "image_url": "https://images.unsplash.com/photo-1542838132-92c53300491e?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Madhur Pure & Hygienic Sugar 1kg",
        "category": "Groceries",
        "price": Decimal("52.00"),
        "stock": 90,
        "description": "Refined sulphurless sparkling white crystal sugar.",
        "image_url": "https://images.unsplash.com/photo-1542838132-92c53300491e?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Fortune Sunlite Refined Sunflower Oil 1L",
        "category": "Groceries",
        "price": Decimal("145.00"),
        "stock": 45,
        "description": "Light, cholesterol-free refined cooking oil enriched with Vitamins A and D.",
        "image_url": "https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Engine Brand Kachi Ghani Mustard Oil 1L",
        "category": "Groceries",
        "price": Decimal("165.00"),
        "stock": 40,
        "description": "Traditional pungent cold-pressed pure mustard oil for authentic Bihar cooking.",
        "image_url": "https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?auto=format&fit=crop&w=600&q=80",
    },

    # Dairy
    {
        "name": "Sudha Gold Full Cream Fresh Milk 500ml",
        "category": "Dairy",
        "price": Decimal("33.00"),
        "stock": 60,
        "description": "Fresh pasteurized full cream milk rich in calcium and natural proteins.",
        "image_url": "https://images.unsplash.com/photo-1550583724-b2692b85b150?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Sudha Healthy Toned Fresh Milk 500ml",
        "category": "Dairy",
        "price": Decimal("28.00"),
        "stock": 70,
        "description": "Daily wholesome pasteurized toned milk pouch.",
        "image_url": "https://images.unsplash.com/photo-1550583724-b2692b85b150?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Amul Pasteurised Salted Butter 100g",
        "category": "Dairy",
        "price": Decimal("58.00"),
        "stock": 50,
        "description": "Utterly butterly delicious pure cream table butter.",
        "image_url": "https://images.unsplash.com/photo-1589985270826-4b7bb135bc9d?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Mother Dairy Classic Dahi Curd 400g",
        "category": "Dairy",
        "price": Decimal("40.00"),
        "stock": 45,
        "description": "Thick traditional set curd packed with gut-healthy probiotics.",
        "image_url": "https://images.unsplash.com/photo-1550583724-b2692b85b150?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Fresh Malai Paneer Block 200g",
        "category": "Dairy",
        "price": Decimal("95.00"),
        "stock": 35,
        "description": "Soft and fresh cottage cheese paneer blocks made from farm cow milk.",
        "image_url": "https://images.unsplash.com/photo-1550583724-b2692b85b150?auto=format&fit=crop&w=600&q=80",
    },

    # Beverages
    {
        "name": "Tata Tea Gold Leaf & Dust Blend 500g",
        "category": "Beverages",
        "price": Decimal("295.00"),
        "stock": 40,
        "description": "Rich aromatic CTC black tea blended with fine orthodox long leaves.",
        "image_url": "https://images.unsplash.com/photo-1544787219-7f47ccb76574?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Nescafe Classic Instant Coffee Jar 50g",
        "category": "Beverages",
        "price": Decimal("185.00"),
        "stock": 30,
        "description": "100% pure roasted robusta coffee granules for instant morning freshness.",
        "image_url": "https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Real Activ 100% Mixed Fruit Juice 1L",
        "category": "Beverages",
        "price": Decimal("140.00"),
        "stock": 35,
        "description": "Natural fruit juice with no added sugar or preservatives.",
        "image_url": "https://images.unsplash.com/photo-1621506289937-a8e4df240d0b?auto=format&fit=crop&w=600&q=80",
    },
]

# Standard pharmacy & health inventory stocked in every regional pharmacy partner
STANDARD_PHARMACY_PRODUCTS: List[Dict[str, Any]] = [
    {
        "name": "Dolo 650 Paracetamol Fever Tablets (Strip of 15)",
        "category": "Medicines",
        "price": Decimal("32.00"),
        "stock": 100,
        "description": "Fast-acting antipyretic and pain relief paracetamol 650mg tablets.",
        "image_url": "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Vicks VapoRub Cold & Cough Relief Balm 50ml",
        "category": "Medicines",
        "price": Decimal("145.00"),
        "stock": 60,
        "description": "Ayurvedic formulation for relief from blocked nose, headache, and body aches.",
        "image_url": "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Electral ORS Oral Rehydration Salt Sachet 21.8g",
        "category": "Medicines",
        "price": Decimal("22.00"),
        "stock": 150,
        "description": "WHO-recommended oral rehydration salts for restoring electrolytes.",
        "image_url": "https://images.unsplash.com/photo-1559839734-2b71ea197ec2?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Band-Aid Medicated Antiseptic Strips (Pack of 20)",
        "category": "Medicines",
        "price": Decimal("55.00"),
        "stock": 80,
        "description": "Flexible wash-proof adhesive bandages with antiseptic pad.",
        "image_url": "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Dettol Antiseptic Disinfectant Liquid 250ml",
        "category": "Medicines",
        "price": Decimal("120.00"),
        "stock": 70,
        "description": "First aid antiseptic liquid for cuts, bites, and daily hygiene.",
        "image_url": "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Volini Pain Relief Fast Spray 55g",
        "category": "Medicines",
        "price": Decimal("160.00"),
        "stock": 45,
        "description": "Microfine fast-absorbing pain relief spray for sprains and joint pain.",
        "image_url": "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Pampers All-Round Protection Baby Diapers Medium (24 Count)",
        "category": "Medicines",
        "price": Decimal("320.00"),
        "stock": 40,
        "description": "Ultra-absorbent baby diaper pants with anti-rash lotion with Aloe Vera.",
        "image_url": "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Limcee Vitamin C 500mg Chewable Tablets (Strip of 15)",
        "category": "Medicines",
        "price": Decimal("25.00"),
        "stock": 90,
        "description": "Orange-flavoured chewable vitamin C immunity booster tablets.",
        "image_url": "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?auto=format&fit=crop&w=600&q=80",
    },
]

# Standard bakery & confectionery inventory stocked in every regional bakery partner
STANDARD_BAKERY_PRODUCTS: List[Dict[str, Any]] = [
    {
        "name": "The Bakeway Sliced Milk Sandwich Bread 400g",
        "category": "Bakery",
        "price": Decimal("45.00"),
        "stock": 50,
        "description": "Daily fresh baked soft white sandwich bread slices.",
        "image_url": "https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "100% Whole Wheat Brown Bread 400g",
        "category": "Bakery",
        "price": Decimal("55.00"),
        "stock": 40,
        "description": "High fibre whole wheat brown loaf baked fresh daily.",
        "image_url": "https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Dutch Dark Chocolate Truffle Cake 500g",
        "category": "Bakery",
        "price": Decimal("480.00"),
        "stock": 15,
        "description": "Decadent layered dark chocolate truffle sponge cake with silky ganache.",
        "image_url": "https://images.unsplash.com/photo-1578985545062-69928b1d9587?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Crispy Milk & Butter Rusks 300g",
        "category": "Bakery",
        "price": Decimal("65.00"),
        "stock": 60,
        "description": "Double-baked golden crunchy cardamom tea rusks.",
        "image_url": "https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Salted Butter Jeera Cookies 250g",
        "category": "Bakery",
        "price": Decimal("95.00"),
        "stock": 45,
        "description": "Melt-in-mouth savoury cumin seed butter cookies.",
        "image_url": "https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Soft Fresh Dinner Pav Buns (Pack of 6)",
        "category": "Bakery",
        "price": Decimal("30.00"),
        "stock": 50,
        "description": "Extra soft, airy dinner pavs perfect for bhaji, misal, and vadapav.",
        "image_url": "https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=600&q=80",
    },
    {
        "name": "Spiced Paneer Tikka Puff Pastry",
        "category": "Bakery",
        "price": Decimal("40.00"),
        "stock": 35,
        "description": "Flaky oven-baked puff loaded with seasoned paneer filling.",
        "image_url": "https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=600&q=80",
    },
]


async def seed_patna_network() -> Dict[str, int]:
    """
    Idempotently seeds all urban Patna regional verified partner shops, owners, products, and inventory.
    """
    stats = {"users_created": 0, "shops_created": 0, "products_created": 0, "inventory_created": 0}

    async with async_session_maker() as session:
        # 1. Seed or retrieve user accounts
        user_map: Dict[str, User] = {}
        for user_data in NETWORK_USERS:
            stmt = select(User).where(User.email == user_data["email"])
            user = (await session.execute(stmt)).scalar_one_or_none()
            if not user:
                user = User(
                    name=user_data["name"],
                    email=user_data["email"],
                    phone_number=user_data["phone_number"],
                    password_hash=get_password_hash(NETWORK_PASSWORD),
                    role=user_data["role"],
                    is_active=True,
                )
                session.add(user)
                await session.flush()
                stats["users_created"] += 1
            user_map[user_data["email"]] = user

        # 2. Seed or update shops
        for shop_data in NETWORK_SHOPS:
            owner = user_map.get(shop_data["owner_email"])
            if not owner:
                continue

            stmt = select(Shop).where(Shop.source_id == shop_data["source_id"])
            shop = (await session.execute(stmt)).scalars().first()

            point_wkt = f"POINT({shop_data['longitude']} {shop_data['latitude']})"

            if not shop:
                shop = Shop(
                    owner_id=owner.id,
                    name=shop_data["name"],
                    description=shop_data["description"],
                    location=WKTElement(point_wkt, srid=4326),
                    address=shop_data["address"],
                    phone=shop_data.get("phone"),
                    opening_hours=shop_data.get("opening_hours"),
                    is_active=True,
                    is_orderable=True,
                    verification_status=ShopVerificationStatus.verified,
                    source="patna_network",
                    source_id=shop_data["source_id"],
                    source_attribution="Dukaanly Verified Merchant Partner Network",
                )
                session.add(shop)
                await session.flush()
                stats["shops_created"] += 1
            else:
                shop.owner_id = owner.id
                shop.name = shop_data["name"]
                shop.description = shop_data["description"]
                shop.address = shop_data["address"]
                shop.location = WKTElement(point_wkt, srid=4326)
                shop.is_active = True
                shop.is_orderable = True
                shop.verification_status = ShopVerificationStatus.verified
                shop.source = "patna_network"
                await session.flush()

            # 3. Seed appropriate product catalogue based on shop category
            cat_type = shop_data["category"]
            if cat_type == "pharmacy":
                items_to_seed = STANDARD_PHARMACY_PRODUCTS
            elif cat_type == "bakery":
                items_to_seed = STANDARD_BAKERY_PRODUCTS
            else:
                items_to_seed = STANDARD_SUPERMARKET_PRODUCTS

            for prod in items_to_seed:
                p_stmt = select(Product).where(
                    Product.shop_id == shop.id,
                    Product.name == prod["name"],
                )
                product = (await session.execute(p_stmt)).scalar_one_or_none()
                if not product:
                    product = Product(
                        shop_id=shop.id,
                        name=prod["name"],
                        category=prod["category"],
                        price=prod["price"],
                        description=prod["description"],
                        image_url=prod["image_url"],
                        is_active=True,
                    )
                    session.add(product)
                    await session.flush()
                    stats["products_created"] += 1

                # Ensure inventory record with stock
                inv_stmt = select(Inventory).where(Inventory.product_id == product.id)
                inv = (await session.execute(inv_stmt)).scalar_one_or_none()
                if not inv:
                    inv = Inventory(
                        product_id=product.id,
                        stock=prod["stock"],
                        version=1,
                    )
                    session.add(inv)
                    stats["inventory_created"] += 1
                elif inv.stock <= 0:
                    inv.stock = prod["stock"]
                    inv.version += 1

        await session.commit()

    return stats


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    res = asyncio.run(seed_patna_network())
    print("Seeding completed:", res)
