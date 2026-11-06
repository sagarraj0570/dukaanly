const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const OUTPUT_DIR = 'C:\\Users\\ASUS\\.gemini\\antigravity\\brain\\3d72bcbb-9391-4145-82be-d95f916e894a\\device-audit';
if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

const VIEWPORTS = [
  { name: 'desktop', width: 1280, height: 800, isMobile: false },
  { name: 'mobile', width: 390, height: 844, isMobile: true, hasTouch: true },
];

async function runDeviceAudit() {
  console.log('--- Starting Real-Device Cross-Screen Audit ---');
  const browser = await chromium.launch({ channel: 'chrome', headless: true });

  for (const vp of VIEWPORTS) {
    console.log(`\nTesting Viewport: ${vp.name.toUpperCase()} (${vp.width}x${vp.height})`);
    const context = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      isMobile: vp.isMobile,
      hasTouch: vp.hasTouch,
    });
    const page = await context.newPage();

    page.on('console', msg => {
      if (msg.type() === 'error') {
        console.log(`[${vp.name} Console Error]:`, msg.text());
      }
    });

    // ==========================================
    // 1. CUSTOMER EXPERIENCE
    // ==========================================
    console.log(`[${vp.name}] 1. Logging in as Customer...`);
    await page.goto('http://localhost:5173/login', { waitUntil: 'networkidle' });
    const custBtn = page.locator('button:has-text("Customer")').first();
    await custBtn.click();
    await page.waitForURL('**/customer**', { timeout: 10000 });

    console.log(`[${vp.name}] Navigating to Customer Order Tracking...`);
    await page.goto('http://localhost:5173/customer/orders/1ffd9db1-68f6-436a-bd90-15df8f7edc85', { waitUntil: 'networkidle' });
    await page.waitForTimeout(3000);

    const custScreenshot = path.join(OUTPUT_DIR, `${vp.name}-01-customer-tracking.png`);
    await page.screenshot({ path: custScreenshot, fullPage: true });
    console.log(`[${vp.name}] Saved Customer tracking screenshot: ${custScreenshot}`);

    // Verify ETA card is visible
    const etaText = await page.locator('text=/Estimated Arrival|arriving|min/i').count();
    console.log(`[${vp.name}] Customer ETA elements detected: ${etaText}`);

    // Clear session for next user
    await page.evaluate(() => localStorage.clear());
    await context.clearCookies();

    // ==========================================
    // 2. SHOP OWNER EXPERIENCE
    // ==========================================
    console.log(`[${vp.name}] 2. Logging in as Shop Owner...`);
    await page.goto('http://localhost:5173/login', { waitUntil: 'networkidle' });
    const shopBtn = page.locator('button:has-text("Shop Owner")').first();
    await shopBtn.click();
    await page.waitForURL('**/shop**', { timeout: 10000 });
    await page.waitForTimeout(2500);

    const shopScreenshot = path.join(OUTPUT_DIR, `${vp.name}-02-shop-owner-dashboard.png`);
    await page.screenshot({ path: shopScreenshot, fullPage: true });
    console.log(`[${vp.name}] Saved Shop Owner screenshot: ${shopScreenshot}`);

    // Clear session for next user
    await page.evaluate(() => localStorage.clear());
    await context.clearCookies();

    // ==========================================
    // 3. RIDER EXPERIENCE
    // ==========================================
    console.log(`[${vp.name}] 3. Logging in as Rider...`);
    await page.goto('http://localhost:5173/login', { waitUntil: 'networkidle' });
    const riderBtn = page.locator('button:has-text("Rider")').first();
    await riderBtn.click();
    await page.waitForURL('**/rider**', { timeout: 10000 });

    console.log(`[${vp.name}] Navigating to Rider Delivery Detail...`);
    await page.goto('http://localhost:5173/rider/deliveries/9a1b3031-3cc0-4478-879d-ae451b588012', { waitUntil: 'networkidle' });
    await page.waitForTimeout(3000);

    const riderScreenshot = path.join(OUTPUT_DIR, `${vp.name}-03-rider-delivery-map.png`);
    await page.screenshot({ path: riderScreenshot, fullPage: true });
    console.log(`[${vp.name}] Saved Rider delivery screenshot: ${riderScreenshot}`);

    await context.close();
  }

  await browser.close();
  console.log('\n--- Real-Device Cross-Screen Audit Completed Successfully! ---');
}

runDeviceAudit().catch(err => {
  console.error('Real-device audit failed:', err);
  process.exit(1);
});
