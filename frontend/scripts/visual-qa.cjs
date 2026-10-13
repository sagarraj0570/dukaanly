const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const SCREENSHOT_DIR = path.resolve('C:/Users/ASUS/.gemini/antigravity/brain/3d72bcbb-9391-4145-82be-d95f916e894a/screenshots');
if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

const VIEWPORTS = [
  { name: '375x812', width: 375, height: 812 },
  { name: '390x844', width: 390, height: 844 },
  { name: '768x1024', width: 768, height: 1024 },
  { name: '1024x768', width: 1024, height: 768 },
  { name: '1280x800', width: 1280, height: 800 },
  { name: '1440x900', width: 1440, height: 900 }
];

const SHOP_ID = '397dd958-810a-4f84-89c8-6a35c082d47a';
const PRODUCT_ID = '493e2c6b-2012-4e77-a45f-f93a36244342';
const ORDER_ID = 'e73d3c6a-f8b5-4f19-aae7-a47da6860582';
const DELIVERY_ID = '7c9564d2-65dc-4f07-a9c0-91895282add2';

async function audit() {
  const browser = await chromium.launch({ channel: 'msedge' });
  const issues = [];

  console.log('=== STARTING DUKAANLY VISUAL QA AUDIT ===\n');

  for (const vp of VIEWPORTS) {
    console.log(`\n--- Auditing Viewport: ${vp.name} (${vp.width}x${vp.height}) ---`);

    // Helper to check page overflow and layout defects
    async function checkPage(page, pageName, screenshotFilename, customAction) {
      if (customAction) await customAction(page);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(500);

      const metrics = await page.evaluate(() => {
        const docWidth = document.documentElement.scrollWidth;
        const winWidth = window.innerWidth;
        const hasOverflow = docWidth > winWidth;

        // Find overflowing elements
        const overflowingElements = [];
        const allElements = document.querySelectorAll('*');
        for (const el of allElements) {
          const rect = el.getBoundingClientRect();
          if (rect.right > winWidth + 1) {
            const tag = el.tagName.toLowerCase();
            const cls = (el.className || '').toString().slice(0, 50);
            const id = el.id ? `#${el.id}` : '';
            overflowingElements.push(`${tag}${id}.${cls} (right: ${Math.round(rect.right)}px > win: ${winWidth}px)`);
          }
        }

        // Broken images check
        const brokenImages = [];
        for (const img of document.querySelectorAll('img')) {
          if (img.complete && img.naturalWidth === 0 && img.style.display !== 'none') {
            brokenImages.push(img.src || img.alt);
          }
        }

        return {
          hasOverflow,
          docWidth,
          winWidth,
          overflowingElements: overflowingElements.slice(0, 5),
          brokenImages
        };
      });

      if (metrics.hasOverflow) {
        console.warn(`[OVERFLOW] ${pageName} on ${vp.name}: docWidth=${metrics.docWidth}px > winWidth=${metrics.winWidth}px`);
        if (metrics.overflowingElements.length) {
          console.warn(`  Elements: ${metrics.overflowingElements.join('; ')}`);
        }
        issues.push({
          page: pageName,
          viewport: vp.name,
          type: 'overflow',
          detail: `docWidth=${metrics.docWidth}px > ${metrics.winWidth}px`,
          elements: metrics.overflowingElements
        });
      }

      if (metrics.brokenImages.length > 0) {
        console.warn(`[BROKEN IMAGE] ${pageName} on ${vp.name}: ${metrics.brokenImages.join(', ')}`);
        issues.push({
          page: pageName,
          viewport: vp.name,
          type: 'broken-image',
          detail: metrics.brokenImages.join(', ')
        });
      }

      const shotPath = path.join(SCREENSHOT_DIR, `${screenshotFilename}-${vp.name}.png`);
      await page.screenshot({ path: shotPath, fullPage: false });
    }

    // 1. PUBLIC / AUTH: LOGIN
    const ctxAuth = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
    const pageAuth = await ctxAuth.newPage();
    await pageAuth.goto('http://localhost:5173/login');
    await checkPage(pageAuth, 'Login (Sign In)', '01-login-signin');

    // Switch to Create Account tab
    await pageAuth.click('button:has-text("Create Account")');
    await pageAuth.waitForTimeout(200);
    await checkPage(pageAuth, 'Login (Create Account)', '01-login-register');
    await ctxAuth.close();

    // 2. CUSTOMER PORTAL
    const ctxCust = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
    const pageCust = await ctxCust.newPage();
    await pageCust.goto('http://localhost:5173/login');
    await pageCust.click('button:has-text("Customer")');
    await pageCust.waitForURL('**/customer**');
    await checkPage(pageCust, 'Customer Dashboard', '02-customer-dashboard');

    // Shop Detail
    await pageCust.goto(`http://localhost:5173/customer/shops/${SHOP_ID}`);
    await checkPage(pageCust, 'Customer Shop Detail', '03-customer-shop-detail');

    // Product Detail
    await pageCust.goto(`http://localhost:5173/customer/products/${PRODUCT_ID}`);
    await checkPage(pageCust, 'Customer Product Detail', '04-customer-product-detail');

    // Cart
    await pageCust.goto('http://localhost:5173/customer/cart');
    await checkPage(pageCust, 'Customer Cart', '05-customer-cart');

    // Checkout
    await pageCust.goto('http://localhost:5173/customer/checkout');
    await checkPage(pageCust, 'Customer Checkout', '06-customer-checkout');

    // Orders History
    await pageCust.goto('http://localhost:5173/customer/orders');
    await checkPage(pageCust, 'Customer Orders History', '07-customer-orders');

    // Order Detail & Tracker
    await pageCust.goto(`http://localhost:5173/customer/orders/${ORDER_ID}`);
    await checkPage(pageCust, 'Customer Order Detail Tracker', '08-customer-order-detail');

    // Order Confirmation
    await pageCust.goto(`http://localhost:5173/customer/orders/${ORDER_ID}/confirmation`);
    await checkPage(pageCust, 'Customer Order Confirmation', '09-customer-order-confirmation');

    // Payment Page
    await pageCust.goto(`http://localhost:5173/customer/payment/${ORDER_ID}`);
    await checkPage(pageCust, 'Customer Payment', '10-customer-payment');
    await ctxCust.close();

    // 3. SHOP OWNER PORTAL
    const ctxShop = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
    const pageShop = await ctxShop.newPage();
    await pageShop.goto('http://localhost:5173/login');
    await pageShop.click('button:has-text("Shop Owner")');
    await pageShop.waitForURL('**/shop**');
    await checkPage(pageShop, 'Shop Owner Dashboard (Orders)', '11-shop-orders');

    // Tab 2: Catalog & Inventory
    await pageShop.click('button:has-text("Catalog & Inventory")');
    await pageShop.waitForTimeout(600);
    await checkPage(pageShop, 'Shop Owner Dashboard (Catalog)', '12-shop-catalog');

    // Open Add Product modal
    const addProductBtn = await pageShop.$('button:has-text("Add Product")');
    if (addProductBtn) {
      await addProductBtn.click();
      await pageShop.waitForTimeout(300);
      await checkPage(pageShop, 'Shop Owner Add Product Modal', '13-shop-add-product-modal');
      // Dismiss modal by clicking Cancel
      const cancelBtn = await pageShop.$('button:has-text("Cancel")');
      if (cancelBtn) {
        await cancelBtn.click();
      } else {
        await pageShop.keyboard.press('Escape');
      }
      await pageShop.waitForTimeout(300);
    }

    // Tab 3: Shop Information
    await pageShop.click('button:has-text("Shop Information")');
    await checkPage(pageShop, 'Shop Owner Dashboard (Settings)', '14-shop-settings');
    await ctxShop.close();

    // 4. RIDER PORTAL
    const ctxRider = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
    const pageRider = await ctxRider.newPage();
    await pageRider.goto('http://localhost:5173/login');
    await pageRider.click('button:has-text("Rider")');
    await pageRider.waitForURL('**/rider**');
    await checkPage(pageRider, 'Rider Dashboard', '15-rider-dashboard');

    // Rider Delivery Detail
    await pageRider.goto(`http://localhost:5173/rider/deliveries/${DELIVERY_ID}`);
    await checkPage(pageRider, 'Rider Delivery Detail', '16-rider-delivery-detail');
    await ctxRider.close();

    console.log(`✓ Viewport ${vp.name} audit complete.`);
  }

  await browser.close();

  console.log('\n=== AUDIT FINISHED ===');
  console.log(`Total issues detected: ${issues.length}`);
  fs.writeFileSync(
    path.join(SCREENSHOT_DIR, 'audit-results.json'),
    JSON.stringify(issues, null, 2)
  );
  return issues;
}

audit().catch(err => {
  console.error('Audit failed with error:', err);
  process.exit(1);
});
