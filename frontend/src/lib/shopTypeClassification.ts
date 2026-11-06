/**
 * Dynamic Retail Shop Classifier & In-Store Department Guide for Dukaanly.
 * Accurately identifies storefront types (Fashion, Sports Nutrition, Home & Living,
 * Electronics, Pharmacy, Bakery, Dairy, Supermarket, etc.) from real-world merchant names
 * and categories, providing tailored departments, photography, badges, and in-store notices.
 */

export type ShopTypeId =
  | 'fashion'
  | 'nutrition'
  | 'home_living'
  | 'electronics'
  | 'pharmacy'
  | 'bakery'
  | 'dairy'
  | 'produce'
  | 'supermarket'
  | 'stationery'
  | 'optician'
  | 'beauty'
  | 'general'

export interface DepartmentGuideItem {
  icon: string
  title: string
  description: string
  popularItems: string[]
}

export interface ShopTypeInfo {
  id: ShopTypeId
  badgeLabel: string
  icon: string
  inStoreNotice: string
  coverImageUrl: string
  departments: DepartmentGuideItem[]
}

export const SHOP_TYPE_REGISTRY: Record<ShopTypeId, ShopTypeInfo> = {
  fashion: {
    id: 'fashion',
    badgeLabel: 'Fashion & Apparel',
    icon: '👕',
    inStoreNotice:
      'Trial rooms, seasonal fashion collections, and size exchanges are available in-store.',
    coverImageUrl:
      'https://images.unsplash.com/photo-1441986300917-64674bd600d8?auto=format&fit=crop&w=1000&q=80',
    departments: [
      {
        icon: '👔',
        title: "Men's Casual & Formal Wear",
        description:
          'Everyday crew tees, polo shirts, formal work shirts, chinos, and stretch denims.',
        popularItems: ['Cotton Crew & Polo Tees', 'Slim Fit Formal Shirts', 'Comfort Stretch Jeans', 'Chinos & Trousers'],
      },
      {
        icon: '👗',
        title: "Women's Ethnic & Western Wear",
        description:
          'Designer kurtas, stylish tops, casual dresses, tunics, and comfortable bottom wear.',
        popularItems: ['Cotton Kurtis & Sets', 'Floral Tops & Tunics', 'A-Line Casual Dresses', 'Leggings & Palazzos'],
      },
      {
        icon: '👟',
        title: 'Footwear & Casual Shoes',
        description:
          'Comfortable everyday sneakers, formal leather shoes, sliders, and running shoes.',
        popularItems: ['Casual Canvas Sneakers', 'Formal Derby Shoes', 'Everyday Cushioned Sliders', 'Athletic Trainers'],
      },
      {
        icon: '🧸',
        title: 'Kids & Teens Fashion',
        description:
          'Breathable cotton outfits, playful graphic tees, shorts, and celebratory dresses.',
        popularItems: ['Graphic Cotton Tees', 'Denim Dungarees & Shorts', 'Festive Frocks & Sets', 'Kids Sleepwear Sets'],
      },
      {
        icon: '👜',
        title: 'Bags, Belts & Accessories',
        description:
          'Crossbody slings, genuine leather belts, wallets, backpacks, and everyday socks.',
        popularItems: ['Crossbody Bags & Slings', 'Leather Belts & Wallets', 'Cotton Ankle Socks', 'Caps & Sunhats'],
      },
    ],
  },

  nutrition: {
    id: 'nutrition',
    badgeLabel: 'Health & Sports Nutrition',
    icon: '🏋️',
    inStoreNotice:
      '100% authentic sealed supplements, batch lab verification & fitness guidance available in-store.',
    coverImageUrl:
      'https://images.unsplash.com/photo-1517838277536-f5f99be501cd?auto=format&fit=crop&w=1000&q=80',
    departments: [
      {
        icon: '🥤',
        title: 'Whey Protein & Isolates',
        description:
          'Rapid absorption whey protein, pure isolates, plant blends, and nighttime casein.',
        popularItems: ['100% Whey Gold Standard', 'Hydrolyzed Whey Isolate', 'Organic Plant Protein', 'Micellar Casein'],
      },
      {
        icon: '⚡',
        title: 'Pre-Workouts & Amino Acids',
        description:
          'Focus boosters, pump enhancers, intra-workout BCAAs, and electrolyte stamina fuels.',
        popularItems: ['High-Stim Pre-Workouts', 'BCAA 2:1:1 Intra-Fuel', 'Citrulline Malate 200g', 'Beta-Alanine Powder'],
      },
      {
        icon: '💪',
        title: 'Creatine & Muscle Builders',
        description:
          'Micronized creatine monohydrate, high-calorie mass gainers, and clean recovery aids.',
        popularItems: ['Creapure Monohydrate 250g', 'Clean Mass Gainer 3kg', 'HMB Capsules', 'Glutamine Recovery'],
      },
      {
        icon: '🥜',
        title: 'High-Protein Foods & Shakers',
        description:
          'All-natural peanut butter, chewy protein bars, leak-proof shakers, and wrist wraps.',
        popularItems: ['Dark Chocolate Peanut Butter', '20g Protein Energy Bars', 'BPA-Free Shaker Bottles', 'Lifting Wrist Straps'],
      },
      {
        icon: '💊',
        title: 'Vitamins & Joint Health',
        description:
          'High-potency athlete multivitamins, triple-strength fish oil, and joint mobility tablets.',
        popularItems: ['Daily Athlete Multivitamins', 'Triple Strength Omega-3', 'Glucosamine & Chondroitin', 'Zinc & Magnesium (ZMA)'],
      },
    ],
  },

  home_living: {
    id: 'home_living',
    badgeLabel: 'Home Living & Furniture',
    icon: '🛋️',
    inStoreNotice:
      'Showroom floor display, fabric swatches, and interior styling assistance available in-store.',
    coverImageUrl:
      'https://images.unsplash.com/photo-1555041469-a586c61ea9bc?auto=format&fit=crop&w=1000&q=80',
    departments: [
      {
        icon: '🛋️',
        title: 'Living Room & Sofas',
        description:
          'Fabric and leatherette 3-seater sofas, manual recliners, coffee tables, and TV consoles.',
        popularItems: ['L-Shaped Sectional Sofas', 'Motorized Recliner Chairs', 'Sheesham Coffee Tables', 'Minimalist TV Units'],
      },
      {
        icon: '🛏️',
        title: 'Bedroom & Mattresses',
        description:
          'King & queen solid wood beds, orthopaedic memory foam mattresses, and spacious wardrobes.',
        popularItems: ['Storage Queen Beds', 'Orthopaedic Foam Mattresses', '3-Door Sliding Wardrobes', 'Engineered Bedside Tables'],
      },
      {
        icon: '🍽️',
        title: 'Dining & Kitchen Furniture',
        description:
          'Solid wood 6-seater dining sets, compact bistro tables, bar stools, and crockery cabinets.',
        popularItems: ['6-Seater Sheesham Dining Sets', 'Cushioned Dining Chairs', 'Glass Door Crockery Units', 'Solid Wood Bar Stools'],
      },
      {
        icon: '🖼️',
        title: 'Home Decor & Lighting',
        description:
          'Modern wall clocks, framed canvas prints, ambient floor lamps, and ceramic flower vases.',
        popularItems: ['Designer Silent Wall Clocks', 'Nordic Ceramic Vases', 'Tripod Floor Lamps', 'Textured Accent Mirrors'],
      },
      {
        icon: '🪟',
        title: 'Curtains & Soft Furnishings',
        description:
          'Thermal blackout window curtains, 300 TC cotton bedsheets, cushions, and fluffy rugs.',
        popularItems: ['Blackout Eyelet Curtains', '300 TC Satin Bed Linen', 'Boho Cushion Covers', 'Anti-Skid Living Room Rugs'],
      },
    ],
  },

  electronics: {
    id: 'electronics',
    badgeLabel: 'Electronics & Mobiles',
    icon: '📱',
    inStoreNotice:
      'Live product experience, brand warranty support, and genuine accessories available in-store.',
    coverImageUrl:
      'https://images.unsplash.com/photo-1550009158-9ebf69173e03?auto=format&fit=crop&w=1000&q=80',
    departments: [
      {
        icon: '📱',
        title: 'Smartphones & Smartwatches',
        description:
          'Latest 5G Android & iOS devices, fitness bands, smartwatches, and tempered protectors.',
        popularItems: ['5G Flagship Smartphones', 'AMOLED Calling Smartwatches', '9H Tempered Glass', 'MagSafe Protective Cases'],
      },
      {
        icon: '🎧',
        title: 'Audio, Earbuds & Speakers',
        description:
          'Active noise-cancelling headphones, true wireless earbuds, and portable Bluetooth speakers.',
        popularItems: ['Active Noise Cancelling TWS', 'Over-Ear Studio Headphones', 'IPX7 Waterproof Speakers', 'Magnetic Neckbands'],
      },
      {
        icon: '💻',
        title: 'Laptops, PCs & Accessories',
        description:
          'Lightweight ultrabooks, mechanical keyboards, ergonomic mice, and high-speed SSDs.',
        popularItems: ['Slim Core i5 / M-Series Laptops', 'RGB Mechanical Keyboards', 'Wireless Ergonomic Mice', '1TB High-Speed External SSD'],
      },
      {
        icon: '🔌',
        title: 'Fast Chargers & Cables',
        description:
          '65W GaN multi-port chargers, heavy-duty braided cables, and 20000mAh power banks.',
        popularItems: ['65W GaN Type-C Chargers', 'Braided 100W PD Cables', '20000mAh Fast Power Banks', 'Multi-Port USB-C Hubs'],
      },
      {
        icon: '📺',
        title: 'Smart TVs & Entertainment',
        description:
          '4K Ultra HD Smart LED TVs, Dolby Atmos soundbars, streaming sticks, and wall mounts.',
        popularItems: ['43" & 55" 4K Smart TVs', 'Dolby Atmos Soundbars', '4K TV Streaming Sticks', 'Heavy-Duty Wall Mounts'],
      },
    ],
  },

  pharmacy: {
    id: 'pharmacy',
    badgeLabel: 'Pharmacy & Healthcare',
    icon: '💊',
    inStoreNotice:
      'Prescription verification and licensed pharmacist consultation available in-store.',
    coverImageUrl:
      'https://images.unsplash.com/photo-1586015555751-63bb77f4322a?auto=format&fit=crop&w=1000&q=80',
    departments: [
      {
        icon: '💊',
        title: 'Prescriptions & OTC Medicines',
        description:
          'Everyday pain relief, fever, cold & cough remedies, antacids, and chronic prescription care.',
        popularItems: ['Paracetamol 650mg & Pain Tablets', 'Cough & Bronchial Syrups', 'Antacid Chewables & ORS', 'Prescription Cardiac / Diabetic'],
      },
      {
        icon: '🩹',
        title: 'First Aid & Wound Care',
        description:
          'Essential emergency dressings, medicated antiseptics, bandages, and pain relief sprays.',
        popularItems: ['Antiseptic Wash (Dettol/Savlon)', 'Adhesive Medicated Strips', 'Sterile Cotton & Rolled Gauze', 'Fast Action Pain Sprays'],
      },
      {
        icon: '👶',
        title: 'Baby Care & Infant Nutrition',
        description:
          'Dermatologist-tested baby powders, gentle washes, diapers, wipes, and infant formulas.',
        popularItems: ['Soft Tape Diaper Pants', 'Aloe Vera Gentle Wipes', 'Tear-Free Baby Shampoo', 'Stage 1-3 Formula Nutrition'],
      },
      {
        icon: '🌿',
        title: 'Daily Vitamins & Immunity',
        description:
          'Multivitamins, chewable vitamin C, calcium with D3, and ayurvedic wellness tonics.',
        popularItems: ['Daily Complete Multivitamins', 'Effervescent Vitamin C 1000mg', 'Calcium & Vitamin D3 Tablets', 'Chyawanprash & Herbal Kadha'],
      },
      {
        icon: '🧼',
        title: 'Personal Hygiene & Protection',
        description:
          'Antibacterial hand washes, alcohol sanitizers, 3-ply surgical masks, and oral hygiene.',
        popularItems: ['Alcohol Hand Sanitizers', 'Antibacterial Hand Wash', '3-Ply Medical Masks', 'Medicated Mouthwash'],
      },
    ],
  },

  bakery: {
    id: 'bakery',
    badgeLabel: 'Bakery & Confectionery',
    icon: '🍞',
    inStoreNotice:
      'Fresh daily oven batches, customised celebration cakes, and warm tea-time savouries.',
    coverImageUrl:
      'https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=1000&q=80',
    departments: [
      {
        icon: '🍞',
        title: 'Fresh Breads & Buns',
        description:
          'Daily oven-fresh white, brown, whole wheat multigrain loaves, and soft dinner pavs.',
        popularItems: ['Sliced Sandwich Bread', '100% Whole Wheat Multigrain', 'Soft Ladi Pav & Burger Buns', 'Herb & Garlic Baguettes'],
      },
      {
        icon: '🎂',
        title: 'Celebration Cakes & Pastries',
        description:
          'Fresh cream birthday cakes, Dutch dark chocolate truffles, and delicate pastry slices.',
        popularItems: ['Dutch Dark Truffle Cake', 'Fresh Fruit Gateau', 'Red Velvet Pastry Slices', 'Chocolate Lava Cakes'],
      },
      {
        icon: '🍪',
        title: 'Artisan Cookies & Rusks',
        description:
          'Golden crispy tea rusks, butter jeera cookies, pistachio biscotti, and puff kharis.',
        popularItems: ['Crisp Milk & Elaichi Rusks', 'Salted Butter Jeera Biscuits', 'Cashew Butter Cookies', 'Flaky Baked Khari Puffs'],
      },
      {
        icon: '🥟',
        title: 'Hot Oven Savouries & Snacks',
        description:
          'Warm flaky vegetable puffs, paneer rolls, baked samosas, and cheesy calzones.',
        popularItems: ['Crispy Veg Aloo Puff', 'Spiced Paneer Tikka Roll', 'Baked Cocktail Samosas', 'Sweet Corn Cheese Pockets'],
      },
      {
        icon: '🍬',
        title: 'Traditional Sweets & Desserts',
        description:
          'Pure desi ghee Indian sweets, dry fruit gift boxes, and seasonal traditional desserts.',
        popularItems: ['Silver Leaf Kaju Katli', 'Spongy Kolkata Rasgullas', 'Pure Ghee Motichoor Laddoos', 'Roasted Dry Fruit Bites'],
      },
    ],
  },

  dairy: {
    id: 'dairy',
    badgeLabel: 'Dairy & Milk Parlour',
    icon: '🥛',
    inStoreNotice:
      'Chilled fresh dairy arrivals twice daily with authentic regional milk & ghee products.',
    coverImageUrl:
      'https://images.unsplash.com/photo-1528750997573-59b89d56f4f7?auto=format&fit=crop&w=1000&q=80',
    departments: [
      {
        icon: '🥛',
        title: 'Fresh Pouched Milk',
        description:
          'Daily fresh standardized toned, full cream, cow milk pouches, and homogenized skim milk.',
        popularItems: ['Toned Fresh Milk 500ml', 'Full Cream Gold Milk 1L', 'Pure Cow Milk 500ml', 'Chilled Skimmed Milk'],
      },
      {
        icon: '🥣',
        title: 'Curd, Paneer & Chaas',
        description:
          'Thick traditional set curd, fresh soft malai paneer blocks, and refreshing spiced chaas.',
        popularItems: ['Thick Set Dahi 400g', 'Fresh Malai Paneer 200g', 'Spiced Masala Chaas 200ml', 'Sweetened Mango Lassi'],
      },
      {
        icon: '🧈',
        title: 'Butter, Pure Ghee & Cream',
        description:
          'Creamery salted table butter, pure Danedar cow ghee, fresh cream, and white makkhan.',
        popularItems: ['Salted Butter 100g / 500g', 'Pure Danedar Desi Ghee 1L', 'Fresh Dairy Cooking Cream', 'Unsalted White Butter'],
      },
      {
        icon: '🍨',
        title: 'Ice Creams & Traditional Dairy',
        description:
          'Rich dairy ice cream tubs, rabri, kulfi sticks, sweetened shrikhand, and pedas.',
        popularItems: ['Real Alphonso Ice Cream 700ml', 'Malai Kulfi on Sticks', 'Elaichi Shrikhand 200g', 'Mathura Milk Peda Box'],
      },
      {
        icon: '🧃',
        title: 'Flavoured Dairy Drinks',
        description:
          'Nutrient-rich badam milk, rich chocolate cold shakes, cold coffee, and fruity yogurts.',
        popularItems: ['Kesar Badam Milk Can', 'Thick Belgian Chocolate Shake', 'Iced Cold Coffee Brew', 'Strawberry Probiotic Yogurt'],
      },
    ],
  },

  produce: {
    id: 'produce',
    badgeLabel: 'Fresh Fruits & Vegetables',
    icon: '🥬',
    inStoreNotice:
      'Farm-fresh produce sorted and weighed daily every morning for in-person shoppers.',
    coverImageUrl:
      'https://images.unsplash.com/photo-1488459716781-31db52582fe9?auto=format&fit=crop&w=1000&q=80',
    departments: [
      {
        icon: '🥔',
        title: 'Daily Cooking Staples',
        description:
          'Fresh soil potatoes, red onions, ripe vine tomatoes, peeled garlic, and spicy chillies.',
        popularItems: ['Fresh New Crop Potatoes 1kg', 'Nashik Red Onions 1kg', 'Hybrid Salad Tomatoes 500g', 'Fresh Ginger & Green Chillies'],
      },
      {
        icon: '🥬',
        title: 'Green Leafy Vegetables',
        description:
          'Tender spinach (palak), fresh methi, crisp coriander, mint, and farm cabbage.',
        popularItems: ['Farm Fresh Palak 250g', 'Aromatic Fresh Coriander', 'Crisp Green Cabbage', 'Tender Cauliflower Florets'],
      },
      {
        icon: '🍎',
        title: 'Seasonal & Local Fruits',
        description:
          'Crisp Himachal apples, sweet Robusta bananas, ripe papayas, and seasonal oranges.',
        popularItems: ['Kinnow / Nagpur Oranges', 'Crisp Red Royal Apples 500g', 'Fresh Golden Bananas 1 Dozen', 'Sweet Table Papaya'],
      },
      {
        icon: '🥦',
        title: 'Exotic & Salad Specials',
        description:
          'Green broccoli florets, coloured bell peppers, English cucumbers, and fresh lemons.',
        popularItems: ['Green Broccoli 250g', 'Coloured Bell Peppers 250g', 'Seedless English Cucumbers', 'Juicy Fresh Lemons (4 pcs)'],
      },
    ],
  },

  stationery: {
    id: 'stationery',
    badgeLabel: 'Books & Stationery',
    icon: '📚',
    inStoreNotice:
      'School, college, and office supplies with instant photostat and document binding services.',
    coverImageUrl:
      'https://images.unsplash.com/photo-1524995997946-a1c2e315a42f?auto=format&fit=crop&w=1000&q=80',
    departments: [
      {
        icon: '📓',
        title: 'Notebooks & Registers',
        description:
          'Long ruled college registers, spiral binding diaries, drawing pads, and sticky notes.',
        popularItems: ['Long Ruled Register 200 Pgs', 'A5 Spiral College Notebooks', 'A4 Cartridge Drawing Book', 'Assorted Neon Sticky Notes'],
      },
      {
        icon: '🖊️',
        title: 'Pens, Pencils & Art Media',
        description:
          'Smooth gel pens, fine ballpoints, graphite pencils, highlighters, and sketch colours.',
        popularItems: ['0.5mm Waterproof Gel Pens', 'Pastel Highlighter Set', '2B/4B Sketching Pencils', 'Water Colour Tube Palette'],
      },
      {
        icon: '📁',
        title: 'Office & Desk Organization',
        description:
          'Clear document folders, desktop staplers, paper punchers, scissors, and adhesive tapes.',
        popularItems: ['Clear Document Button Folders', 'Heavy-Duty Desk Staplers', 'Transparent Packaging Tape', 'Scientific Calculators'],
      },
    ],
  },

  optician: {
    id: 'optician',
    badgeLabel: 'Opticians & Eyewear',
    icon: '👓',
    inStoreNotice:
      'Computerized eye testing, power lenses, and designer frames available in-store.',
    coverImageUrl:
      'https://images.unsplash.com/photo-1574258495973-f010dfbb5371?auto=format&fit=crop&w=1000&q=80',
    departments: [
      {
        icon: '👓',
        title: 'Prescription Eyeglasses & Frames',
        description:
          'Full-rim acetate frames, lightweight titanium glasses, blue-light computer lenses, and progressives.',
        popularItems: ['Anti-Glare Computer Glasses', 'Classic Acetate Wayfarer Frames', 'Lightweight Rimless Frames', 'Progressive Power Lenses'],
      },
      {
        icon: '🕶️',
        title: 'Sunglasses & UV Eyewear',
        description:
          '100% UV400 protection sunglasses, polarized aviators, retro round shades, and sports frames.',
        popularItems: ['Polarized Pilot Aviators', 'UV400 Wayfarer Sunglasses', 'Wraparound Sports Sunglasses', 'Gradient Oversized Frames'],
      },
      {
        icon: '👁️',
        title: 'Contact Lenses & Care',
        description:
          'Monthly and daily disposable contact lenses, natural colour shades, and multi-purpose cleaning solutions.',
        popularItems: ['Monthly Disposable Soft Lenses', 'Multi-Purpose Disinfecting Solution', 'Natural Hazel Colour Lenses', 'Lens Storage Travel Cases'],
      },
    ],
  },

  beauty: {
    id: 'beauty',
    badgeLabel: 'Cosmetics & Beauty',
    icon: '💄',
    inStoreNotice:
      'Authentic cosmetics, skincare trials, and beauty consultations available in-store.',
    coverImageUrl:
      'https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?auto=format&fit=crop&w=1000&q=80',
    departments: [
      {
        icon: '💄',
        title: 'Makeup & Cosmetics',
        description:
          'Matte lipsticks, long-stay liquid foundations, waterproof kajal, eyeliners, and nail polishes.',
        popularItems: ['Liquid Matte Longwear Lipstick', 'Matte Poreless Foundation', 'Smudge-Proof Black Kajal', 'Volumizing Waterproof Mascara'],
      },
      {
        icon: '✨',
        title: 'Skincare, Serums & Sunscreens',
        description:
          'Hydrating face washes, Vitamin C brightening serums, SPF 50 gel sunscreens, and night moisturizers.',
        popularItems: ['Ultra-Light Gel Sunscreen SPF 50', '10% Vitamin C Facial Serum', 'Hyaluronic Acid Face Cream', 'Foaming Tea Tree Face Wash'],
      },
      {
        icon: '🌸',
        title: 'Fragrances & Body Care',
        description:
          'Long-lasting eau de parfum, refreshing body mists, nourishing body lotions, and roll-ons.',
        popularItems: ['Luxury Eau De Parfum 50ml', 'Floral Shimmer Body Mist', 'Deep Moisture Cocoa Butter Lotion', 'All-Day Floral Deodorant'],
      },
    ],
  },

  supermarket: {
    id: 'supermarket',
    badgeLabel: 'Supermarket & Provisions',
    icon: '🛒',
    inStoreNotice:
      'Multi-aisle departmental store equipped with shopping carts and express checkout counters.',
    coverImageUrl:
      'https://images.unsplash.com/photo-1578916171728-46686eac8d58?auto=format&fit=crop&w=1000&q=80',
    departments: [
      {
        icon: '🥛',
        title: 'Dairy & Cold Storage',
        description:
          'Chilled milk pouches, yogurts, salted table butter, fresh paneer, and cheese slices.',
        popularItems: ['Fresh Toned Milk 500ml', 'Set Curd & Chaas', 'Salted Table Butter 100g', 'Fresh Malai Paneer & Cheese Slices'],
      },
      {
        icon: '🌾',
        title: 'Staples, Flours & Grains',
        description:
          'Chakki fresh wheat atta, basmati rice, toor & moong daal, refined sugar, and iodised salt.',
        popularItems: ['Shudh Chakki Atta 5kg', 'Aged Basmati Biryani Rice 1kg', 'Unpolished Toor Daal 1kg', 'Iodised Pure Crystal Salt 1kg'],
      },
      {
        icon: '🍳',
        title: 'Cooking Oils & Masalas',
        description:
          'Cold-pressed mustard oil, refined sunflower oil, desi cow ghee, and blended spices.',
        popularItems: ['Kachi Ghani Mustard Oil 1L', 'Refined Sunflower Oil 1L', 'Desi Cow Ghee 500ml', 'Haldi, Mirch & Garam Masala Packs'],
      },
      {
        icon: '🍪',
        title: 'Snacks, Biscuits & Beverages',
        description:
          'Premium Assam tea, instant coffee, roasted namkeens, potato chips, and refreshing fruit drinks.',
        popularItems: ['CTC Gold Tea 500g', 'Instant Coffee Granules 50g', 'Spicy Bhujia & Namkeen 400g', 'Assorted Cream & Marie Biscuits'],
      },
      {
        icon: '🧼',
        title: 'Cleaning & Household Needs',
        description:
          'Front/top load detergent powders, dishwash bars, floor disinfectants, and pooja supplies.',
        popularItems: ['Stain Removal Detergent Powder 1kg', 'Lemon Dishwash Liquid 500ml', 'Pine Floor Disinfectant 1L', 'Camphor & Pooja Agarbatti'],
      },
      {
        icon: '🧴',
        title: 'Personal Care & Toiletries',
        description:
          'Moisturizing bath soaps, anti-dandruff shampoos, cavity protection toothpastes, and lotions.',
        popularItems: ['Herbal Bathing Soaps (Pack of 3)', 'Pro-V Shampoo 340ml', 'Total Cavity Protection Toothpaste', 'Deep Conditioning Hair Oil'],
      },
    ],
  },

  general: {
    id: 'general',
    badgeLabel: 'Kirana & General Store',
    icon: '🏪',
    inStoreNotice:
      'Friendly neighbourhood shop providing daily grocery essentials and household items.',
    coverImageUrl:
      'https://images.unsplash.com/photo-1604719312566-8912e9227c6a?auto=format&fit=crop&w=1000&q=80',
    departments: [
      {
        icon: '🥛',
        title: 'Dairy & Chilled Staples',
        description:
          'Fresh milk pouches, fresh dahi, table butter, and brown eggs.',
        popularItems: ['Fresh Milk 500ml', 'Curd & Chaas', 'Amul / Mother Dairy Butter', 'Farm Fresh White/Brown Eggs'],
      },
      {
        icon: '🌾',
        title: 'Daily Atta, Rice & Daal',
        description:
          'Everyday kitchen foundation grains, packaged pulses, and pure sugar.',
        popularItems: ['Chakki Fresh Atta 5kg', 'Daily Sona Masoori Rice', 'Moong & Toor Daal 1kg', 'Clean White Sugar 1kg'],
      },
      {
        icon: '🍳',
        title: 'Cooking Oils & Basic Spices',
        description:
          'Pure mustard oil, cooking sunflower oil, desi ghee, turmeric, and chilli powder.',
        popularItems: ['Mustard Oil Pouch 1L', 'Sunflower Cooking Oil 1L', 'Desi Ghee 200ml / 500ml', 'Ground Haldi & Mirch 100g'],
      },
      {
        icon: '☕',
        title: 'Tea, Biscuits & Snacks',
        description:
          'Daily CTC tea, Marie biscuits, crunchy namkeens, chips, and noodles.',
        popularItems: ['Assam Leaf Tea 250g', 'Glucose & Marie Biscuits', 'Sev Bhujia & Mixture', 'Instant Masala Noodles'],
      },
      {
        icon: '🧼',
        title: 'Soaps & Washing Essentials',
        description:
          'Laundry washing bars, dishwashing cakes, floor cleaners, and matches.',
        popularItems: ['Washing Detergent Cake', 'Dishwash Bar 250g', 'Floor Cleaning Disinfectant', 'Safety Matches (Pack of 10)'],
      },
      {
        icon: '🧴',
        title: 'Everyday Personal Care',
        description:
          'Glycerine bath soap, cooling hair oils, toothpastes, and toothbrushes.',
        popularItems: ['Bathing Soap 100g', 'Amla / Coconut Hair Oil', 'Toothpaste 100g', 'Soft Bristle Toothbrush'],
      },
    ],
  },
}

/**
 * Accurately determines the retail shop classification from its store name and raw category metadata.
 */
export function resolveShopType(
  name: string = '',
  rawCategory?: string | null
): ShopTypeInfo {
  const n = (name || '').toLowerCase()
  const c = (rawCategory || '').toLowerCase()
  const combined = `${n} ${c}`

  // 1. Pharmacy & Chemist
  if (
    combined.includes('chemist') ||
    combined.includes('pharmacy') ||
    combined.includes('medical') ||
    combined.includes('medicos') ||
    combined.includes('druggist') ||
    combined.includes('apollo') ||
    combined.includes('medplus') ||
    combined.includes('sanjeevani') ||
    combined.includes('dawa') ||
    combined.includes('healthcare')
  ) {
    return SHOP_TYPE_REGISTRY.pharmacy
  }

  // 2. Health, Fitness & Sports Nutrition (e.g. "Active nutrition centtre")
  if (
    combined.includes('nutrition') ||
    combined.includes('protein') ||
    combined.includes('supplement') ||
    combined.includes('nutra') ||
    combined.includes('bodybuilding') ||
    combined.includes('fitness') ||
    combined.includes('muscle') ||
    combined.includes('whey') ||
    combined.includes('creatine')
  ) {
    return SHOP_TYPE_REGISTRY.nutrition
  }

  // 3. Fashion & Clothing (e.g. "Zudio", "Trends", "Pantaloons", "Fabindia", "Raymond")
  if (
    combined.includes('zudio') ||
    combined.includes('v-mart') ||
    combined.includes('vmart') ||
    combined.includes('vishal mega mart') ||
    combined.includes('trends') ||
    combined.includes('max fashion') ||
    combined.includes('pantaloons') ||
    combined.includes('fabindia') ||
    combined.includes('raymond') ||
    combined.includes('mufti') ||
    combined.includes('zara') ||
    combined.includes('h&m') ||
    combined.includes('shoppers stop') ||
    combined.includes('westside') ||
    combined.includes('peter england') ||
    combined.includes('manyavar') ||
    combined.includes('allen solly') ||
    combined.includes('louis philippe') ||
    combined.includes('clothing') ||
    combined.includes('apparel') ||
    combined.includes('garment') ||
    combined.includes('fashion') ||
    combined.includes('boutique') ||
    combined.includes('textile') ||
    combined.includes('dresses') ||
    combined.includes('menswear') ||
    combined.includes('womenswear') ||
    combined.includes('kidswear') ||
    combined.includes('footwear') ||
    combined.includes('shoe') ||
    combined.includes('sneakers') ||
    combined.includes('sandals')
  ) {
    return SHOP_TYPE_REGISTRY.fashion
  }

  // 4. Home Decor, Furniture & Mattresses (e.g. "Home town")
  if (
    combined.includes('home town') ||
    combined.includes('hometown') ||
    combined.includes('furniture') ||
    combined.includes('home decor') ||
    combined.includes('furnishing') ||
    combined.includes('interiors') ||
    combined.includes('mattress') ||
    combined.includes('sleepwell') ||
    combined.includes('kurlon') ||
    combined.includes('woodcraft') ||
    combined.includes('curtains') ||
    combined.includes('sofa')
  ) {
    return SHOP_TYPE_REGISTRY.home_living
  }

  // 5. Electronics & Mobiles (e.g. Croma, Reliance Digital, Vijay Sales)
  if (
    combined.includes('electronic') ||
    combined.includes('mobile') ||
    combined.includes('computer') ||
    combined.includes('laptop') ||
    combined.includes('croma') ||
    combined.includes('reliance digital') ||
    combined.includes('vijay sales') ||
    combined.includes('sangeetha') ||
    combined.includes('poorvika') ||
    combined.includes('gadget') ||
    combined.includes('appliances')
  ) {
    return SHOP_TYPE_REGISTRY.electronics
  }

  // 6. Bakery & Confectionery (e.g. Harilal's, cakes, sweets)
  if (
    combined.includes('bakery') ||
    combined.includes('cake') ||
    combined.includes('pastry') ||
    combined.includes('sweets') ||
    combined.includes('confectionery') ||
    combined.includes('mithai') ||
    combined.includes('harilal') ||
    combined.includes('haldiram') ||
    combined.includes('bikanervala') ||
    combined.includes('monginis') ||
    combined.includes('bake')
  ) {
    return SHOP_TYPE_REGISTRY.bakery
  }

  // 7. Dairy & Milk Parlour (e.g. Sudha, Amul, Mother Dairy)
  if (
    combined.includes('sudha') ||
    combined.includes('amul') ||
    combined.includes('mother dairy') ||
    combined.includes('dairy') ||
    combined.includes('milk parlour') ||
    combined.includes('milk booth') ||
    combined.includes('creamery')
  ) {
    return SHOP_TYPE_REGISTRY.dairy
  }

  // 8. Fresh Produce & Vegetables (e.g. Sabzi, Mandi)
  if (
    combined.includes('sabzi') ||
    combined.includes('mandi') ||
    combined.includes('vegetable') ||
    combined.includes('fruit') ||
    combined.includes('produce')
  ) {
    return SHOP_TYPE_REGISTRY.produce
  }

  // 9. Books & Stationery
  if (
    combined.includes('book') ||
    combined.includes('stationery') ||
    combined.includes('stationers') ||
    combined.includes('paper')
  ) {
    return SHOP_TYPE_REGISTRY.stationery
  }

  // 10. Opticians & Eyewear
  if (
    combined.includes('optical') ||
    combined.includes('optician') ||
    combined.includes('lenskart') ||
    combined.includes('eyewear') ||
    combined.includes('spectacles') ||
    combined.includes('glasses')
  ) {
    return SHOP_TYPE_REGISTRY.optician
  }

  // 11. Cosmetics & Beauty
  if (
    combined.includes('cosmetics') ||
    combined.includes('beauty') ||
    combined.includes('salon') ||
    combined.includes('parlour') ||
    combined.includes('parlor') ||
    combined.includes('makeup') ||
    combined.includes('skincare')
  ) {
    return SHOP_TYPE_REGISTRY.beauty
  }

  // 12. Supermarket & Departmental Store (e.g. TVS mart, Laxhmi Supermarket, City Supermarket)
  if (
    combined.includes('supermarket') ||
    combined.includes('hypermarket') ||
    combined.includes('mart') ||
    combined.includes('bazaar') ||
    combined.includes('departmental') ||
    combined.includes('super market')
  ) {
    return SHOP_TYPE_REGISTRY.supermarket
  }

  // 13. Default to Kirana / General Store
  return SHOP_TYPE_REGISTRY.general
}
