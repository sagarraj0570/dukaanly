import { describe, it, expect } from 'vitest'
import { resolveShopType } from './shopTypeClassification'

describe('shopTypeClassification resolveShopType', () => {
  it('correctly classifies fashion brands and apparel stores', () => {
    const zudio = resolveShopType('Zudio', 'supermarket')
    expect(zudio.id).toBe('fashion')
    expect(zudio.badgeLabel).toBe('Fashion & Apparel')
    expect(zudio.icon).toBe('👕')
    expect(zudio.departments.some((d) => d.title.includes('Men'))).toBe(true)
    expect(zudio.departments.some((d) => d.title.includes('Women'))).toBe(true)
    expect(zudio.departments.some((d) => d.title.includes('Footwear'))).toBe(true)

    const trends = resolveShopType('Trends Fashion', 'clothing')
    expect(trends.id).toBe('fashion')

    const pantaloons = resolveShopType('Pantaloons Store', 'commercial')
    expect(pantaloons.id).toBe('fashion')
  })

  it('correctly classifies health, fitness and sports nutrition stores', () => {
    const nutritionCentre = resolveShopType('Active nutrition centtre', 'supermarket')
    expect(nutritionCentre.id).toBe('nutrition')
    expect(nutritionCentre.badgeLabel).toBe('Health & Sports Nutrition')
    expect(nutritionCentre.icon).toBe('🏋️')
    expect(nutritionCentre.departments.some((d) => d.title.includes('Whey Protein'))).toBe(true)
    expect(nutritionCentre.departments.some((d) => d.title.includes('Pre-Workouts'))).toBe(true)
    expect(nutritionCentre.departments.some((d) => d.title.includes('Creatine'))).toBe(true)

    const gymProtein = resolveShopType('Gold Standard Protein & Supplements', 'general')
    expect(gymProtein.id).toBe('nutrition')
  })

  it('correctly classifies home decor and furniture stores', () => {
    const homeTown = resolveShopType('Home town', 'supermarket')
    expect(homeTown.id).toBe('home_living')
    expect(homeTown.badgeLabel).toBe('Home Living & Furniture')
    expect(homeTown.icon).toBe('🛋️')
    expect(homeTown.departments.some((d) => d.title.includes('Living Room'))).toBe(true)
    expect(homeTown.departments.some((d) => d.title.includes('Bedroom'))).toBe(true)
    expect(homeTown.departments.some((d) => d.title.includes('Dining'))).toBe(true)

    const furnitureStudio = resolveShopType('Royal Furniture & Mattress Gallery')
    expect(furnitureStudio.id).toBe('home_living')
  })

  it('correctly classifies supermarkets and marts', () => {
    const tvsMart = resolveShopType('TVS mart', 'supermarket')
    expect(tvsMart.id).toBe('supermarket')
    expect(tvsMart.badgeLabel).toBe('Supermarket & Provisions')
    expect(tvsMart.icon).toBe('🛒')
    expect(tvsMart.departments.some((d) => d.title.includes('Dairy & Cold Storage'))).toBe(true)
    expect(tvsMart.departments.some((d) => d.title.includes('Staples'))).toBe(true)

    const laxmi = resolveShopType('Laxhmi Supermarket')
    expect(laxmi.id).toBe('supermarket')
  })

  it('correctly classifies pharmacies and chemist shops', () => {
    const apollo = resolveShopType('Apollo Pharmacy', 'chemist')
    expect(apollo.id).toBe('pharmacy')
    expect(apollo.badgeLabel).toBe('Pharmacy & Healthcare')
    expect(apollo.icon).toBe('💊')
    expect(apollo.departments.some((d) => d.title.includes('Prescriptions'))).toBe(true)
    expect(apollo.departments.some((d) => d.title.includes('First Aid'))).toBe(true)

    const medicos = resolveShopType('Sanjeevani Medicos')
    expect(medicos.id).toBe('pharmacy')
  })

  it('correctly classifies bakeries and sweet shops', () => {
    const harilal = resolveShopType("Harilal's Sweets & Bakery")
    expect(harilal.id).toBe('bakery')
    expect(harilal.badgeLabel).toBe('Bakery & Confectionery')
    expect(harilal.icon).toBe('🍞')
    expect(harilal.departments.some((d) => d.title.includes('Breads'))).toBe(true)
    expect(harilal.departments.some((d) => d.title.includes('Cakes'))).toBe(true)
  })

  it('correctly classifies dairy milk parlours', () => {
    const sudha = resolveShopType('Sudha Milk Parlour')
    expect(sudha.id).toBe('dairy')
    expect(sudha.badgeLabel).toBe('Dairy & Milk Parlour')
    expect(sudha.icon).toBe('🥛')
  })

  it('correctly classifies electronics and gadget stores', () => {
    const croma = resolveShopType('Croma Electronics')
    expect(croma.id).toBe('electronics')
    expect(croma.badgeLabel).toBe('Electronics & Mobiles')
    expect(croma.icon).toBe('📱')
    expect(croma.departments.some((d) => d.title.includes('Smartphones'))).toBe(true)
  })

  it('falls back to Kirana & General Store for unclassified neighbourhood stores', () => {
    const jalalPur = resolveShopType('jalal pur')
    expect(jalalPur.id).toBe('general')
    expect(jalalPur.badgeLabel).toBe('Kirana & General Store')
    expect(jalalPur.icon).toBe('🏪')
    expect(jalalPur.departments.length).toBeGreaterThan(0)
  })
})
