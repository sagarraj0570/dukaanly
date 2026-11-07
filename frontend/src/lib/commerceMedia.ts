/**
 * Deterministic visual media & product metadata helper for Dukaanly.
 * Maps real shop names/descriptions and product names/categories to curated,
 * high-resolution commerce photography with graceful fallback handling.
 */

import { resolveShopType } from './shopTypeClassification'

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
    bgTint: '#E8F3E1',
  },
  {
    id: 'Fruits & Vegetables',
    label: 'Fruits & Vegetables',
    shortLabel: 'Fruits & Veg',
    imageUrl: 'https://images.unsplash.com/photo-1610832958506-aa56368176cf?auto=format&fit=crop&w=400&q=80',
    bgTint: '#FFF1D6',
  },
  {
    id: 'Dairy',
    label: 'Dairy & Bakery',
    shortLabel: 'Dairy',
    imageUrl: 'https://images.unsplash.com/photo-1550583724-b2692b85b150?auto=format&fit=crop&w=400&q=80',
    bgTint: '#FDF3E7',
  },
  {
    id: 'Edible Oils',
    label: 'Oils & Cooking',
    shortLabel: 'Edible Oils',
    imageUrl: 'https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?auto=format&fit=crop&w=400&q=80',
    bgTint: '#F6F0D2',
  },
  {
    id: 'Snacks',
    label: 'Snacks & Instant',
    shortLabel: 'Snacks',
    imageUrl: 'https://images.unsplash.com/photo-1621939514649-280e2ee25f60?auto=format&fit=crop&w=400&q=80',
    bgTint: '#FCE6DF',
  },
  {
    id: 'Household',
    label: 'Daily Essentials',
    shortLabel: 'Essentials',
    imageUrl: 'https://images.unsplash.com/photo-1583947215259-38e31be8751f?auto=format&fit=crop&w=400&q=80',
    bgTint: '#E3F1F6',
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
  const shopType = resolveShopType(name, description)
  if (shopType && shopType.coverImageUrl) {
    return shopType.coverImageUrl
  }

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
 * Always returns `product.image_url` first if present so backend/database URLs are respected.
 */
export function getProductImage(
  name: string,
  category?: string | null,
  imageUrl?: string | null
): string {
  if (imageUrl && imageUrl.trim().length > 0) {
    const trimmed = imageUrl.trim()
    if (trimmed.startsWith('http://') || trimmed.startsWith('https://') || trimmed.startsWith('data:')) {
      return trimmed
    }
    if (trimmed.startsWith('/static/')) {
      const rawApiUrl = import.meta.env.VITE_API_URL
      if (rawApiUrl && typeof window !== 'undefined' && !window.location.hostname.includes('localhost')) {
        try {
          const origin = new URL(rawApiUrl).origin
          return `${origin}${trimmed}`
        } catch {
          // ignore
        }
      }
      return trimmed
    }
    return trimmed
  }

  const lower = name.toLowerCase()
  const cat = (category || '').toLowerCase()

  // 0. High-Priority Dairy & Fresh Bakery Delicacies
  // Must precede personal care & generic matchers to avoid false positive matches on 'cream' / 'oil'
  if (lower.includes('whipped cream') || lower.includes('whipping cream') || lower.includes('fresh cream') || lower.includes('malai')) {
    return 'https://images.unsplash.com/photo-1517427294546-5aa121f68e8a?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('ice cream') || lower.includes('kulfi') || lower.includes('cassata')) {
    return 'https://images.unsplash.com/photo-1497034825429-c343d7c6a68f?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('pastry') || lower.includes('cream pastry')) {
    return 'https://images.unsplash.com/photo-1578985545062-69928b1d9587?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('muffin') || lower.includes('cream muffin')) {
    return 'https://images.unsplash.com/photo-1587668178277-295251f900ce?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('bourbon') || lower.includes('cream biscuit') || lower.includes('oreo')) {
    return 'https://images.unsplash.com/photo-1558961363-fa8fdf82db35?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('milk') || lower.includes('sudha') || lower.includes('amul milk') || lower.includes('full cream milk')) {
    return 'https://images.unsplash.com/photo-1563636619-e9143da7973b?auto=format&fit=crop&w=600&q=80'
  }

  // 1. Medicines & Health
  if (lower.includes('dolo') || lower.includes('paracetamol') || lower.includes('fever')) {
    return 'https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('electral') || lower.includes('ors') || lower.includes('rehydration')) {
    return 'https://images.unsplash.com/photo-1559839734-2b71ea197ec2?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('digene') || lower.includes('antacid') || lower.includes('heartburn') || lower.includes('acidity')) {
    return 'https://images.unsplash.com/photo-1471864190281-a93a3070b6de?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('vicks') || lower.includes('vaporub') || lower.includes('cold relief') || lower.includes('balm')) {
    return 'https://images.unsplash.com/photo-1608571423902-eed4a5ad8108?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('volini') || lower.includes('pain spray')) {
    return 'https://images.unsplash.com/photo-1576765608535-5f04d1e3f289?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('moov') || lower.includes('pain relief') || lower.includes('backache')) {
    return 'https://images.unsplash.com/photo-1587854692152-cbe660dbde88?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('band-aid') || lower.includes('bandage') || lower.includes('plaster') || lower.includes('strips')) {
    return 'https://images.unsplash.com/photo-1616391182219-e080b4d1043a?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('betadine') || lower.includes('povidone') || lower.includes('wound')) {
    return 'https://images.unsplash.com/photo-1631549916768-4119b2e5f926?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('honitus') || lower.includes('cough') || lower.includes('syrup')) {
    return 'https://images.unsplash.com/photo-1512069772995-ec65ed45afd6?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('limcee') || lower.includes('vitamin c') || lower.includes('immunity')) {
    return 'https://images.unsplash.com/photo-1577401239170-897942555fb3?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('strepsils') || lower.includes('lozenge') || lower.includes('sore throat')) {
    return 'https://images.unsplash.com/photo-1607613009820-a29f7bb81c04?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('pudin hara') || lower.includes('mint pearls') || lower.includes('stomach')) {
    return 'https://images.unsplash.com/photo-1584362917165-526a968579e8?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('glucose') || lower.includes('gluco')) {
    return 'https://images.unsplash.com/photo-1556881286-fc6915169721?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('otrivin') || lower.includes('nasal') || lower.includes('decongestant')) {
    return 'https://images.unsplash.com/photo-1585435557343-3b092031a831?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('thermometer')) {
    return 'https://images.unsplash.com/photo-1584017911766-d451b3d0e843?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('mask') || lower.includes('surgical')) {
    return 'https://images.unsplash.com/photo-1586942593568-29361efcd571?auto=format&fit=crop&w=600&q=80'
  }

  // 2. Personal Care & Hygiene
  if (lower.includes('dettol') && lower.includes('liquid') || lower.includes('savlon')) {
    return 'https://images.unsplash.com/photo-1584515979956-d9f6e5d09982?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('dettol') || lower.includes('soap') || lower.includes('sebamed')) {
    return 'https://images.unsplash.com/photo-1585238342024-78d387f4a707?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('body wash') || lower.includes('dove') || lower.includes('shower gel')) {
    return 'https://images.unsplash.com/photo-1556228720-195a672e8a03?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('toothpaste') || lower.includes('colgate') || lower.includes('oral')) {
    return 'https://images.unsplash.com/photo-1571781926291-c477ebfd024b?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('handwash') || lower.includes('lifebuoy')) {
    return 'https://images.unsplash.com/photo-1584744982491-665216d95f8b?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('shampoo') || lower.includes('conditioner') || lower.includes('head & shoulders')) {
    return 'https://images.unsplash.com/photo-1535585209827-a15fcdbc4c2d?auto=format&fit=crop&w=600&q=80'
  }
  if (
    lower.includes('nivea') ||
    lower.includes('moisturizer') ||
    lower.includes('body lotion') ||
    lower.includes('face cream') ||
    lower.includes('skin cream') ||
    lower.includes('cold cream') ||
    lower.includes('vaseline') ||
    (lower.includes('lotion') && !lower.includes('calamine')) ||
    (lower.includes('cream') && (cat.includes('personal') || cat.includes('hygiene') || cat.includes('care') || cat.includes('beauty')))
  ) {
    return 'https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?auto=format&fit=crop&w=600&q=80'
  }

  // 3. Household Essentials
  if (lower.includes('surf excel') || lower.includes('detergent') || lower.includes('washing powder')) {
    return 'https://images.unsplash.com/photo-1610557892470-55d9e80c0bce?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('vim') || lower.includes('dishwash') || lower.includes('dish soap')) {
    return 'https://images.unsplash.com/photo-1585421514284-efb74c2b69ba?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('harpic') || lower.includes('toilet cleaner')) {
    return 'https://images.unsplash.com/photo-1585421514738-01798e348b17?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('lizol') || lower.includes('floor cleaner')) {
    return 'https://images.unsplash.com/photo-1584820927498-cfe5211fd8bf?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('good knight') || lower.includes('mosquito') || lower.includes('all out') || lower.includes('repellent')) {
    return 'https://images.unsplash.com/photo-1563245372-f21724e3856d?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('aer') || lower.includes('freshener') || lower.includes('air freshener')) {
    return 'https://images.unsplash.com/photo-1616949755610-8c9bbc08f138?auto=format&fit=crop&w=600&q=80'
  }

  // 4. Bakery & Confectionery
  if (lower.includes('brown bread') || lower.includes('wheat bread')) {
    return 'https://images.unsplash.com/photo-1589367920969-ab8e050bbb04?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('bread') || lower.includes('white bread') || lower.includes('sandwich bread')) {
    return 'https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('pav') || lower.includes('burger bun') || lower.includes('bun')) {
    return 'https://images.unsplash.com/photo-1586190848861-99aa4a171e90?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('rusk') || lower.includes('toast')) {
    return 'https://images.unsplash.com/photo-1590080875515-8a3a8dc5735e?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('truffle') || lower.includes('chocolate cake')) {
    return 'https://images.unsplash.com/photo-1578985545062-69928b1d9587?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('pound cake') || lower.includes('butterscotch cake') || lower.includes('tea cake')) {
    return 'https://images.unsplash.com/photo-1506459225024-1428097a7e18?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('garlic bread')) {
    return 'https://images.unsplash.com/photo-1619535860434-ba1d8fa12536?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('croissant')) {
    return 'https://images.unsplash.com/photo-1555507036-ab1f4038808a?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('khari') || lower.includes('puff pastry')) {
    return 'https://images.unsplash.com/photo-1549931319-a545dcf3bc73?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('muffin')) {
    return 'https://images.unsplash.com/photo-1587668178277-295251f900ce?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('cupcake')) {
    return 'https://images.unsplash.com/photo-1576618148400-f54bed99fcfd?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('peda')) {
    return 'https://images.unsplash.com/photo-1599785209707-a456fc1337bb?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('kalakand') || lower.includes('mithai') || lower.includes('sweet')) {
    return 'https://images.unsplash.com/photo-1541783245831-57d6fb0926d3?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('patty') || lower.includes('puff')) {
    return 'https://images.unsplash.com/photo-1565557623262-b51c2513a641?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('kathi roll') || lower.includes('wrap') || lower.includes('frankie')) {
    return 'https://images.unsplash.com/photo-1626777552726-4a6b54c97e46?auto=format&fit=crop&w=600&q=80'
  }

  // 5. Groceries & Staples
  if (lower.includes('atta') || lower.includes('wheat') || lower.includes('flour')) {
    return 'https://www.bbassets.com/media/uploads/p/l/126906_8-aashirvaad-atta-whole-wheat.jpg'
  }
  if (lower.includes('rice') || lower.includes('basmati')) {
    return 'https://images.unsplash.com/photo-1586201375761-83865001e31c?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('dal') || lower.includes('toor') || lower.includes('pulses') || lower.includes('lentil')) {
    return 'https://images.unsplash.com/photo-1546833999-b9f581a1996d?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('salt') || lower.includes('namak')) {
    return 'https://www.bbassets.com/media/uploads/p/l/241600_11-tata-salt-iodized.jpg'
  }
  if (lower.includes('sugar') || lower.includes('cheeni')) {
    return 'https://images.unsplash.com/photo-1581441363689-1f3c3c414635?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('mustard oil') || lower.includes('sarson')) {
    return 'https://images.unsplash.com/photo-1620706857370-e1b9770e8bb1?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('sunflower') || lower.includes('cooking oil') || lower.includes('refined oil')) {
    return 'https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('turmeric') || lower.includes('haldi')) {
    return 'https://images.unsplash.com/photo-1615485290382-441e4d049cb5?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('mirch') || lower.includes('chilli') || lower.includes('pepper')) {
    return 'https://images.unsplash.com/photo-1596040033229-a9821ebd058d?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('garam masala') || lower.includes('masala') || lower.includes('spice')) {
    return 'https://images.unsplash.com/photo-1599940824399-b87987ceb72a?auto=format&fit=crop&w=600&q=80'
  }

  // 6. Dairy
  if (lower.includes('paneer') || lower.includes('cottage cheese')) {
    return 'https://images.unsplash.com/photo-1631452180519-c014fe946bc7?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('butter') || lower.includes('makhan')) {
    return 'https://images.unsplash.com/photo-1589985270826-4b7bb135bc9d?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('cheese') || lower.includes('cheddar')) {
    return 'https://images.unsplash.com/photo-1618160702438-9b02ab6515c9?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('dahi') || lower.includes('curd') || lower.includes('yogurt')) {
    return 'https://images.unsplash.com/photo-1488477181946-6428a0291777?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('ghee')) {
    return 'https://images.unsplash.com/photo-1589301760014-d929f3979dbc?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('whipped cream') || lower.includes('whipping cream')) {
    return 'https://images.unsplash.com/photo-1517427294546-5aa121f68e8a?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('milk') || lower.includes('dairy')) {
    return 'https://images.unsplash.com/photo-1563636619-e9143da7973b?auto=format&fit=crop&w=600&q=80'
  }

  // 7. Snacks
  if (lower.includes('maggi') || lower.includes('noodle') || lower.includes('ramen') || lower.includes('pasta')) {
    return 'https://images.unsplash.com/photo-1612929633738-8fe44f7ec841?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('bhujia') || lower.includes('sev') || lower.includes('namkeen')) {
    return 'https://images.unsplash.com/photo-1601050690597-df0568f70950?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('chips') || lower.includes('lays') || lower.includes('crisps') || lower.includes('wafer')) {
    return 'https://images.unsplash.com/photo-1566478989037-eec170784d0b?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('parle') || lower.includes('biscuit') || lower.includes('rusk')) {
    return 'https://images.unsplash.com/photo-1558961363-fa8fdf82db35?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('good day') || lower.includes('cookie') || lower.includes('cookies')) {
    return 'https://images.unsplash.com/photo-1499636136210-6f4ee915583e?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('kurkure') || lower.includes('puff snack')) {
    return 'https://images.unsplash.com/photo-1563805042-7684c019e1cb?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('chocolate') || lower.includes('cadbury') || lower.includes('silk')) {
    return 'https://images.unsplash.com/photo-1549007994-cb92caebd54b?auto=format&fit=crop&w=600&q=80'
  }

  // 8. Beverages
  if (lower.includes('cold brew')) {
    return 'https://images.unsplash.com/photo-1461023058943-07fcbe16d735?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('hot chocolate') || lower.includes('cocoa')) {
    return 'https://images.unsplash.com/photo-1542990253-0d0f5be5f0ed?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('tea') || lower.includes('chai')) {
    return 'https://images.unsplash.com/photo-1576092768241-dec231879fc3?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('coffee') || lower.includes('nescafe') || lower.includes('bru')) {
    return 'https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('rooh afza') || lower.includes('sharbat') || lower.includes('syrup')) {
    return 'https://images.unsplash.com/photo-1513558161293-cdaf765ed2fd?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('mango') || lower.includes('frooti')) {
    return 'https://images.unsplash.com/photo-1546173159-315724a31696?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('juice')) {
    return 'https://images.unsplash.com/photo-1600271886742-f049cd451bba?auto=format&fit=crop&w=600&q=80'
  }

  // Fresh produce / staples
  if (lower.includes('banana')) {
    return 'https://images.unsplash.com/photo-1571771894821-ce9b6c11b08e?auto=format&fit=crop&w=600&q=80'
  }
  if (lower.includes('tomato')) {
    return 'https://images.unsplash.com/photo-1592924357228-91a4daadcfea?auto=format&fit=crop&w=600&q=80'
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

  // Category-level fallbacks
  if (cat.includes('medicine') || cat.includes('pharmacy') || cat.includes('health')) {
    return 'https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?auto=format&fit=crop&w=600&q=80'
  }
  if (cat.includes('personal') || cat.includes('hygiene') || cat.includes('care')) {
    return 'https://images.unsplash.com/photo-1556228720-195a672e8a03?auto=format&fit=crop&w=600&q=80'
  }
  if (cat.includes('household') || cat.includes('cleaning') || cat.includes('essential')) {
    return 'https://images.unsplash.com/photo-1585421514738-01798e348b17?auto=format&fit=crop&w=600&q=80'
  }
  if (cat.includes('bakery') || cat.includes('bread')) {
    return 'https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=600&q=80'
  }
  if (cat.includes('dairy')) {
    return 'https://images.unsplash.com/photo-1550583724-b2692b85b150?auto=format&fit=crop&w=600&q=80'
  }
  if (cat.includes('oil')) {
    return 'https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?auto=format&fit=crop&w=600&q=80'
  }
  if (cat.includes('snack')) {
    return 'https://images.unsplash.com/photo-1621939514649-280e2ee25f60?auto=format&fit=crop&w=600&q=80'
  }
  if (cat.includes('beverage') || cat.includes('drink')) {
    return 'https://images.unsplash.com/photo-1544787219-7f47ccb76574?auto=format&fit=crop&w=600&q=80'
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
