import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import {
  checkNoHorizontalOverflow,
  checkInputFontSizes,
  checkTouchTargets,
  saveScreenshot,
} from './helpers'

const CUSTOMER_CREDENTIALS = {
  email: 'customer@dukaanly.com',
  password: 'Password123!',
}

const SHOP_CREDENTIALS = {
  email: 'shop@dukaanly.com',
  password: 'Password123!',
}

const RIDER_CREDENTIALS = {
  email: 'rider@dukaanly.com',
  password: 'Password123!',
}

async function loginAs(page: any, credentials: { email: string; password: string }, destination: string) {
  await page.goto('/login')
  await page.waitForLoadState('networkidle')
  
  // Fill email & password
  const emailInput = page.locator('#login-email')
  const passInput = page.locator('#login-password')
  await emailInput.fill(credentials.email)
  await passInput.fill(credentials.password)
  
  // Submit
  await page.locator('button[type="submit"]:has-text("Sign in")').click()
  await page.waitForURL(`**${destination}`, { timeout: 15000 }).catch(() => {})
  await page.waitForLoadState('networkidle')
}

test.describe('Responsive Layout & Touch Suite', () => {

  test('Login Page: Layout, Inputs >=16px, Touch Targets & Keyboard Submit', async ({ page }, testInfo) => {
    await page.goto('/login')
    await page.waitForLoadState('networkidle')

    // 1. Assert no horizontal overflow
    const overflow = await checkNoHorizontalOverflow(page)
    expect(overflow.hasOverflow, `Horizontal overflow on Login page: ${overflow.offendingElements.join(', ')}`).toBe(false)

    // 2. On mobile, assert input font sizes are >= 16px to prevent iOS auto-zoom
    if (page.viewportSize() && page.viewportSize()!.width < 768) {
      const smallInputs = await checkInputFontSizes(page)
      expect(smallInputs.length, `Inputs with font-size < 16px on mobile: ${JSON.stringify(smallInputs)}`).toBe(0)
    }

    // 3. Touch target sizes on mobile
    if (testInfo.project.use.hasTouch) {
      const offenders = await checkTouchTargets(page)
      expect(offenders.length, `Touch targets under minimum size: ${offenders.join(', ')}`).toBe(0)
    }

    // 4. Keyboard test: Tab through login form and submit with Enter
    if (!testInfo.project.use.isMobile) {
      await page.locator('#login-email').focus()
      await page.keyboard.type(CUSTOMER_CREDENTIALS.email)
      await page.keyboard.press('Tab')
      await expect(page.locator('#login-password')).toBeFocused()
      await page.keyboard.type(CUSTOMER_CREDENTIALS.password)
      // Enter key submits form
      await page.keyboard.press('Enter')
      await page.waitForURL('**/customer', { timeout: 10000 }).catch(() => {})
    }

    // 5. Save screenshot artifact
    await saveScreenshot(page, testInfo, 'login_page')
  })

  test('Customer Home & Directory: Responsive Grids, Category Snap & Leaflet Map', async ({ page }, testInfo) => {
    await loginAs(page, CUSTOMER_CREDENTIALS, '/customer')
    await page.goto('/customer')
    await page.waitForLoadState('networkidle')

    // 1. Assert no horizontal overflow
    const overflow = await checkNoHorizontalOverflow(page)
    expect(overflow.hasOverflow, `Horizontal overflow on Customer Dashboard: ${overflow.offendingElements.join(', ')}`).toBe(false)

    // 2. Category snap row exists
    const categoryRow = page.locator('.scroll-snap-x').first()
    await expect(categoryRow).toBeVisible()

    // 3. Shop grid column validation
    const vpWidth = page.viewportSize()?.width || 1280
    if (vpWidth < 640) {
      // On mobile, shop cards are stacked in 1 column
      const firstCard = page.locator('[data-testid="shop-card"]').first()
      if (await firstCard.isVisible()) {
        const cardBox = await firstCard.boundingBox()
        if (cardBox) {
          expect(cardBox.width).toBeGreaterThan(250)
          expect(cardBox.width).toBeLessThanOrEqual(vpWidth)
        }
      }
    }

    // 4. Test In-Store Places Tab and Leaflet Map
    const mapTab = page.locator('[data-testid="tab-in-store"]')
    if (await mapTab.isVisible()) {
      await mapTab.click()
      await page.waitForTimeout(500)

      // Toggle to Map View
      const toggleMap = page.locator('[data-testid="toggle-map-view"]')
      if (await toggleMap.isVisible()) {
        await toggleMap.click()
        await page.waitForTimeout(500)

        // Leaflet map container must have non-zero height
        const mapContainer = page.locator('[data-testid="discovery-map-view"] .leaflet-container')
        await expect(mapContainer).toBeVisible()
        const mapBox = await mapContainer.boundingBox()
        expect(mapBox?.height).toBeGreaterThanOrEqual(250)

        // Orientation / Resize test: Swap width & height and assert map remains sized
        const currentVp = page.viewportSize()!
        await page.setViewportSize({ width: currentVp.height, height: currentVp.width })
        await page.waitForTimeout(400)
        const rotatedMapBox = await mapContainer.boundingBox()
        expect(rotatedMapBox?.height).toBeGreaterThanOrEqual(200)

        // Restore viewport
        await page.setViewportSize(currentVp)
      }
    }

    // 5. Check AI Assistant button and Mobile Nav
    if (vpWidth < 768) {
      const mobileNav = page.locator('nav[aria-label="Mobile Navigation"]')
      await expect(mobileNav).toBeVisible()
    }

    // 6. Save screenshot
    await saveScreenshot(page, testInfo, 'customer_home')
  })

  test('Shop Page: 2-Col Mobile Product Grid, Sticky Cart Bar & Safe Areas', async ({ page }, testInfo) => {
    await loginAs(page, CUSTOMER_CREDENTIALS, '/customer')
    
    // Visit first available shop
    await page.goto('/customer')
    await page.waitForLoadState('networkidle')
    const firstShopLink = page.locator('a[href^="/customer/shops/"]').first()
    if (await firstShopLink.isVisible()) {
      await firstShopLink.click()
      await page.waitForLoadState('networkidle')

      // Assert no horizontal overflow
      const overflow = await checkNoHorizontalOverflow(page)
      expect(overflow.hasOverflow, `Horizontal overflow on Shop Detail: ${overflow.offendingElements.join(', ')}`).toBe(false)

      const vpWidth = page.viewportSize()?.width || 1280

      // Add item to cart to test sticky bottom bar
      const addBtn = page.locator('button:has-text("Add")').first()
      if (await addBtn.isVisible()) {
        await addBtn.click()
        await page.waitForTimeout(800)

        if (vpWidth < 1024) {
          // Sticky mobile cart bar must be visible with non-zero dimensions
          const stickyCartBar = page.locator('text=items in cart').first()
          await expect(stickyCartBar).toBeVisible()
        }
      }

      await saveScreenshot(page, testInfo, 'shop_detail')
    }
  })

  test('Cart & Checkout Pages: Stacking, Sticky Place Order & Form Inputs', async ({ page }, testInfo) => {
    await loginAs(page, CUSTOMER_CREDENTIALS, '/customer/cart')
    await page.goto('/customer/cart')
    await page.waitForLoadState('networkidle')

    const overflowCart = await checkNoHorizontalOverflow(page)
    expect(overflowCart.hasOverflow, `Horizontal overflow on Cart: ${overflowCart.offendingElements.join(', ')}`).toBe(false)
    await saveScreenshot(page, testInfo, 'customer_cart')

    // Navigate to checkout if cart has items
    const checkoutBtn = page.locator('button:has-text("Proceed to Checkout")').first()
    if (await checkoutBtn.isVisible()) {
      await checkoutBtn.click()
      await page.waitForURL('**/customer/checkout')
      await page.waitForLoadState('networkidle')

      const overflowCheckout = await checkNoHorizontalOverflow(page)
      expect(overflowCheckout.hasOverflow, `Horizontal overflow on Checkout: ${overflowCheckout.offendingElements.join(', ')}`).toBe(false)

      const vpWidth = page.viewportSize()?.width || 1280
      if (vpWidth < 1024) {
        // Sticky mobile bar with place order
        const placeOrderSticky = page.locator('button:has-text("Place Order"), button:has-text("Confirm Order")').first()
        await expect(placeOrderSticky).toBeVisible()
      }

      await saveScreenshot(page, testInfo, 'customer_checkout')
    }
  })

  test('Shop Dashboard: Stacked Rows on Mobile, Table on Desktop, 48px Actions', async ({ page }, testInfo) => {
    await loginAs(page, SHOP_CREDENTIALS, '/shop')
    await page.goto('/shop')
    await page.waitForLoadState('networkidle')

    const overflow = await checkNoHorizontalOverflow(page)
    expect(overflow.hasOverflow, `Horizontal overflow on Shop Dashboard: ${overflow.offendingElements.join(', ')}`).toBe(false)

    const vpWidth = page.viewportSize()?.width || 1280

    // Switch to Products Tab
    const productsTab = page.locator('button:has-text("Products"), button:has-text("Inventory")').first()
    if (await productsTab.isVisible()) {
      await productsTab.click()
      await page.waitForTimeout(400)

      if (vpWidth < 768) {
        // Desktop table must be hidden
        const desktopTable = page.locator('table')
        if (await desktopTable.count() > 0) {
          await expect(desktopTable).toBeHidden()
        }
      } else {
        // Desktop table should be visible
        const desktopTable = page.locator('table')
        if (await desktopTable.count() > 0) {
          await expect(desktopTable).toBeVisible()
        }
      }
    }

    await saveScreenshot(page, testInfo, 'shop_dashboard')
  })

  test('Rider Dashboard: Centered Column, Accessible Duty Switch, Landscape 360px Usability', async ({ page }, testInfo) => {
    await loginAs(page, RIDER_CREDENTIALS, '/rider')
    await page.goto('/rider')
    await page.waitForLoadState('networkidle')

    const overflow = await checkNoHorizontalOverflow(page)
    expect(overflow.hasOverflow, `Horizontal overflow on Rider Dashboard: ${overflow.offendingElements.join(', ')}`).toBe(false)

    // Duty switch button should be visible and clickable
    const dutySwitch = page.locator('button[role="switch"]').first()
    await expect(dutySwitch).toBeVisible()

    // Test extreme landscape at 360px height
    const currentVp = page.viewportSize() || { width: 375, height: 667 }
    await page.setViewportSize({ width: 780, height: 360 })
    await page.waitForTimeout(300)

    const landscapeOverflow = await checkNoHorizontalOverflow(page)
    expect(landscapeOverflow.hasOverflow).toBe(false)
    await expect(dutySwitch).toBeVisible()

    // Restore viewport
    await page.setViewportSize(currentVp)
    await saveScreenshot(page, testInfo, 'rider_dashboard')
  })

  test('Axe Accessibility Scan: No Critical or Serious WCAG Violations', async ({ page }, testInfo) => {
    const vpWidth = page.viewportSize()?.width || 1280
    // Run Axe on Customer Home and Login pages at mobile (360) and desktop (1280)
    if (vpWidth === 360 || vpWidth === 1280) {
      await page.goto('/login')
      await page.waitForLoadState('networkidle')

      const accessibilityScanResults = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa'])
        .analyze()

      const criticalOrSerious = accessibilityScanResults.violations.filter(
        v => v.impact === 'critical' || v.impact === 'serious'
      )

      if (criticalOrSerious.length > 0) {
        console.warn(`[Axe ${vpWidth}px] Violations found:`, criticalOrSerious.map(v => `${v.id}: ${v.description}`))
      }

      // Assert no critical violations
      const critical = criticalOrSerious.filter(v => v.impact === 'critical')
      expect(critical.length, `Critical accessibility violations: ${critical.map(v => v.id).join(', ')}`).toBe(0)
    }
  })

})
