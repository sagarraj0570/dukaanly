/**
 * Deterministic visual media & product metadata helper for Dukaanly.
 * Maps real shop names/descriptions and product names/categories to curated,
 * high-resolution commerce photography with graceful fallback handling.
 */

export interface CategoryMeta {
  id: string
  label: string
  shortLabel: string
  imageUrl: string
  bgTint: string
}

export const COMMERCE_CATEGORIES: CategoryMeta[] = [
  {
    id: 'Groceries',
    label: 'Groceries & Staples',
    shortLabel: 'Groceries',
    imageUrl: 'https://images.unsplash.com/photo-1542838132-92c53300491e?auto=format&fit=crop&w=400&q=80',
    bgTint: '#F3F8F4',
  },
  {
    id: 'Fruits & Vegetables',
    label: 'Fruits & Vegetables',
    shortLabel: 'Fruits & Veg',
    imageUrl: 'https://images.unsplash.com/photo-1610832958506-aa56368176cf?auto=format&fit=crop&w=400&q=80',
    bgTint: '#F4F9F2',
  },
  {
    id: 'Dairy',
    label: 'Dairy & Bakery',
    shortLabel: 'Dairy & Bakery',
    imageUrl: 'https://images.unsplash.com/photo-1550583724-b2692b85b150?auto=format&fit=crop&w=400&q=80',
    bgTint: '#F2F6FA',
  },
  {
    id: 'Edible Oils',
    label: 'Oils & Cooking',
    shortLabel: 'Edible Oils',
    imageUrl: 'https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?auto=format&fit=crop&w=400&q=80',
    bgTint: '#FAF6EE',
  },
  {
    id: 'Snacks',
    label: 'Snacks & Instant',
    shortLabel: 'Snacks',
    imageUrl: 'https://images.unsplash.com/photo-1621939514649-280e2ee25f60?auto=format&fit=crop&w=400&q=80',
    bgTint: '#FDF5F2',
  },
  {
    id: 'Household',
    label: 'Daily Essentials',
    shortLabel: 'Essentials',
    imageUrl: 'https://images.unsplash.com/photo-1583947215259-38e31be8751f?auto=format&fit=crop&w=400&q=80',
    bgTint: '#F4F5F7',
  },
]

export const HERO_GROCERY_IMAGE =
  'https://images.unsplash.com/photo-1542838132-92c53300491e?auto=format&fit=crop&w=1000&q=85'

const SHOP_STOREFRONT_IMAGES = [
  // Traditional & modern neighbourhood grocery / kirana storefronts
  'https://images.unsplash.com/photo-1604719312566-8912e9227c6a?auto=format&fit=crop&w=900&q=80',
  'https://images.unsplash.com/photo-1578916171728-46686eac8d58?auto=format&fit=crop&w=900&q=80',
  'https://images.unsplash.com/photo-1542838132-92c53300491e?auto=format&fit=crop&w=900&q=80',
  'https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=900&q=80',
  'https://images.unsplash.com/photo-1534723452862-4c874018d66d?auto=format&fit=crop&w=900&q=80',
  'https://images.unsplash.com/photo-1488459716781-31db52582fe9?auto=format&fit=crop&w=900&q=80',
]

/**
 * Picks a realistic storefront cover image based on shop name & description.
 */
export function getShopCoverImage(name: string, description?: string | null): string {
  const text = `${name} ${description || ''}`.toLowerCase()
  if (text.includes('kirana') || text.includes('general') || text.includes('sharma')) {
    return SHOP_STOREFRONT_IMAGES[0]
  }
  if (text.includes('fresh') || text.includes('mart') || text.includes('daily')) {
    return SHOP_STOREFRONT_IMAGES[1]
  }
  if (text.includes('organic') || text.includes('green') || text.includes('veg') || text.includes('fruit')) {
    return SHOP_STOREFRONT_IMAGES[5]
  }
  if (text.includes('bakery') || text.includes('bread') || text.includes('sweet')) {
    return SHOP_STOREFRONT_IMAGES[3]
  }

  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) >>> 0
  }
  return SHOP_STOREFRONT_IMAGES[hash % SHOP_STOREFRONT_IMAGES.length]
}

/**
 * Resolves a realistic, appetizing product image when `image_url` is not set on the product.
 * Always returns `product.image_url` first if present so backend/test URLs are respected.
 */
export function getProductImage(
  name: string,
  category?: string | null,
  imageUrl?: string | null
): string {
  if (imageUrl && imageUrl.trim().length > 0) {
    return imageUrl
  }

  const lower = name.toLowerCase()
  const cat = (category || '').toLowerCase()

  if (lower.includes('atta') || lower.includes('wheat') || lower.includes('flour')) {
    return 'https://images.unsplash.com/photo-1574323347407-f5e1ad6d020b?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('milk') || lower.includes('amul') || lower.includes('curd') || lower.includes('paneer')) {
    return 'https://images.unsplash.com/photo-1563636619-e9143da7973b?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('salt') || lower.includes('sugar') || lower.includes('spice')) {
    return 'https://images.unsplash.com/photo-1518843875459-f738682238a6?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('oil') || lower.includes('sunflower') || lower.includes('fortune') || lower.includes('ghee')) {
    return 'https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('maggi') || lower.includes('noodle') || lower.includes('pasta') || lower.includes('instant')) {
    return 'https://images.unsplash.com/photo-1612929633738-8fe44f7ec841?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('banana')) {
    return 'https://images.unsplash.com/photo-1571771894821-ce9b6c11b08e?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('tomato')) {
    return 'https://images.unsplash.com/photo-1592924357228-91a4daadcfea?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('bread') || lower.includes('bakery') || lower.includes('bun')) {
    return 'https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('egg')) {
    return 'https://images.unsplash.com/photo-1582722872445-44dc5f7e3c8f?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('potato')) {
    return 'https://images.unsplash.com/photo-1518977676601-b53f82aba655?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('onion')) {
    return 'https://images.unsplash.com/photo-1618512496248-a07fe83aa8cb?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('rice') || lower.includes('basmati') || lower.includes('dal')) {
    return 'https://images.unsplash.com/photo-1586201375761-83865001e31c?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('tea') || lower.includes('coffee')) {
    return 'https://images.unsplash.com/photo-1544787219-7f47ccb76574?auto=format&fit=crop&w=600&q=80'
  }

  // Category-level fallbacks
  if (cat.includes('dairy')) {
    return 'https://images.unsplash.com/photo-1550583724-b2692b85b150?auto=format&fit=crop&w=600&q=80'
  }
  if (cat.includes('oil')) {
    return 'https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?auto=format&fit=crop&w=600&q=80'
  }
  if (cat.includes('snack')) {
    return 'https://images.unsplash.com/photo-1621939514649-280e2ee25f60?auto=format&fit=crop&w=600&q=80'
  }
  if (cat.includes('fruit') || cat.includes('veg')) {
    return 'https://images.unsplash.com/photo-1610832958506-aa56368176cf?auto=format&fit=crop&w=600&q=80'
  }

  return 'https://images.unsplash.com/photo-1542838132-92c53300491e?auto=format&fit=crop&w=600&q=80'
}

/**
 * Extracts a trailing or embedded pack size / unit from a product title if present
 * (e.g. "Aashirvaad Whole Wheat Atta 5kg" -> "5 kg", "Amul Taaza Milk 1L" -> "1 L").
 */
export function extractProductUnit(name: string): string | null {
  const match = name.match(/\b(\d+(?:\.\d+)?\s*(?:kg|g|gm|ml|l|ltr|pcs|pc|pack))\b/i)
  return match ? match[1] : null
}
