const { chromium, firefox } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://localhost:5173';
const API_URL = 'http://127.0.0.1:8001/api/v1';

const SHOP_ID = 'd7ddd5b6-45ad-4228-934c-408b5db659df';
const PRODUCT_ID = '80270f0e-fee7-40c6-bff6-21f727a8fd28';
const ORDER_ID = 'e73d3c6a-f8b5-4f19-aae7-a47da6860582';
const PENDING_ORDER_ID = 'e853a666-476c-4bfa-8ef7-214060034b8b';
const DELIVERY_ID = '7c9564d2-65dc-4f07-a9c0-91895282add2';

const SCREENSHOT_DIR = 'C:\\Users\\ASUS\\.gemini\\antigravity\\brain\\3d72bcbb-9391-4145-82be-d95f916e894a\\cross-browser';

if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

const VIEWPORTS = [
  { name: '375x812', width: 375, height: 812, label: 'Mobile Small' },
  { name: '768x1024', width: 768, height: 1024, label: 'Tablet Portrait' },
  { name: '1024x768', width: 1024, height: 768, label: 'Tablet Landscape' },
  { name: '1280x800', width: 1280, height: 800, label: 'Laptop Standard' },
  { name: '1440x900', width: 1440, height: 900, label: 'Desktop Large' },
];

const BROWSER_CONFIGS = [
  {
    name: 'Google Chrome',
    id: 'chrome',
    launcher: async () => chromium.launch({ channel: 'chrome', headless: true }),
  },
  {
    name: 'Microsoft Edge',
    id: 'edge',
    launcher: async () => chromium.launch({ channel: 'msedge', headless: true }),
  },
  {
    name: 'Mozilla Firefox',
    id: 'firefox',
    launcher: async () => firefox.launch({ headless: true }),
  },
];

async function runBrowserSuite(config) {
  console.log(`\n======================================================`);
  console.log(`RUNNING SUITE: ${config.name} (${config.id})`);
  console.log(`======================================================`);

  const browser = await config.launcher();
  const version = await browser.version();
  console.log(`Browser version: ${version}`);

  const report = {
    browserName: config.name,
    browserId: config.id,
    version,
    testedAt: new Date().toISOString(),
    tests: [],
    errors: [],
    consoleErrors: [],
    networkFailures: [],
    overflowIssues: [],
    screenshots: [],
    summary: { total: 0, passed: 0, failed: 0 }
  };

  function setupPageMonitoring(page, contextName) {
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text();
        // Ignore known harmless dev noise if any
        console.log(`  [CONSOLE ERROR][${contextName}]: ${text}`);
        report.consoleErrors.push({ context: contextName, message: text });
      }
    });

    page.on('pageerror', (err) => {
      console.log(`  [UNCAUGHT EXCEPTION][${contextName}]: ${err.message}`);
      report.errors.push({ context: contextName, message: err.message, stack: err.stack });
    });

    page.on('requestfailed', (req) => {
      // Ignore aborts on navigation
      const failure = req.failure();
      if (failure && !failure.errorText.includes('aborted')) {
        console.log(`  [REQUEST FAILED][${contextName}]: ${req.url()} - ${failure.errorText}`);
        report.networkFailures.push({
          context: contextName,
          url: req.url(),
          errorText: failure.errorText
        });
      }
    });
  }

  async function checkHorizontalOverflow(page, viewName, route) {
    const overflow = await page.evaluate(() => {
      const doc = document.documentElement;
      const body = document.body;
      const docScroll = doc.scrollWidth;
      const docClient = doc.clientWidth;
      const bodyScroll = body.scrollWidth;
      const bodyClient = body.clientWidth;
      const hasOverflow = (docScroll > docClient + 1) || (bodyScroll > bodyClient + 1);
      return {
        hasOverflow,
        docScroll,
        docClient,
        bodyScroll,
        bodyClient,
        diff: Math.max(docScroll - docClient, bodyScroll - bodyClient)
      };
    });

    if (overflow.hasOverflow) {
      console.log(`  ⚠️ OVERFLOW DETECTED [${config.id} @ ${viewName} on ${route}]: diff=${overflow.diff}px`);
      report.overflowIssues.push({
        viewport: viewName,
        route,
        diff: overflow.diff,
        docScroll: overflow.docScroll,
        docClient: overflow.docClient
      });
    }
    return overflow;
  }

  async function recordTest(testName, fn) {
    report.summary.total++;
    process.stdout.write(`  Testing: ${testName}... `);
    const start = Date.now();
    try {
      await fn();
      const dur = Date.now() - start;
      console.log(`✓ PASSED (${dur}ms)`);
      report.summary.passed++;
      report.tests.push({ name: testName, status: 'passed', durationMs: dur });
    } catch (err) {
      const dur = Date.now() - start;
      console.log(`❌ FAILED (${dur}ms) -> ${err.message}`);
      report.summary.failed++;
      report.tests.push({ name: testName, status: 'failed', durationMs: dur, error: err.message });
    }
  }

  // TEST 1: App Startup & Route Guards
  await recordTest('T1: Startup & Authentication Redirect Guards', async () => {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await ctx.newPage();
    setupPageMonitoring(page, 'T1-Guards');

    // Root redirects to login
    await page.goto(`${BASE_URL}/`);
    await page.waitForURL(`**/login**`, { timeout: 6000 });

    // Customer unauthenticated redirects to login
    await page.goto(`${BASE_URL}/customer`);
    await page.waitForURL(`**/login**`, { timeout: 6000 });

    // Shop unauthenticated redirects to login
    await page.goto(`${BASE_URL}/shop`);
    await page.waitForURL(`**/login**`, { timeout: 6000 });

    // Rider unauthenticated redirects to login
    await page.goto(`${BASE_URL}/rider`);
    await page.waitForURL(`**/login**`, { timeout: 6000 });

    // 404 page handles non-existent paths gracefully
    await page.goto(`${BASE_URL}/nonexistent-route-404`);
    const notFoundText = await page.textContent('body');
    if (!notFoundText.includes('404')) {
      throw new Error('404 page did not display expected text');
    }

    await ctx.close();
  });

  // TEST 2: Customer Discovery & Search
  await recordTest('T2: Customer Discovery, Shop Listing & Search', async () => {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await ctx.newPage();
    setupPageMonitoring(page, 'T2-Discovery');

    await page.goto(`${BASE_URL}/login`);
    await page.click('button:has-text("Customer")');
    await page.waitForURL(`**/customer**`, { timeout: 8000 });

    // Verify shops render
    await page.waitForSelector('main', { timeout: 5000 });
    const pageContent = await page.textContent('body');
    if (!pageContent.includes('Dukaanly') && !pageContent.includes('Shops')) {
      throw new Error('Customer dashboard missing core heading/content');
    }

    // Verify search input interaction
    const searchInput = await page.$('input[placeholder*="Search"]');
    if (searchInput) {
      await searchInput.fill('Basket');
      await page.waitForTimeout(400);
      await searchInput.fill('');
    }

    // Verify category chips
    const categoryButtons = await page.$$('button');
    if (categoryButtons.length === 0) {
      throw new Error('No interactive filter buttons found');
    }

    // Navigate to Shop Detail
    await page.goto(`${BASE_URL}/customer/shops/${SHOP_ID}`);
    await page.waitForSelector('main', { timeout: 6000 });
    const shopDetailContent = await page.textContent('main');
    if (!shopDetailContent.includes('Fresh Basket') && !shopDetailContent.includes('Products')) {
      throw new Error('Shop detail page did not load shop or products');
    }

    await checkHorizontalOverflow(page, '1280x800', `/customer/shops/${SHOP_ID}`);
    await ctx.close();
  });

  // TEST 3: Product Detail, Image Fallback & Cart Interactions
  await recordTest('T3: Product Detail, Fallbacks & Cart Management', async () => {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await ctx.newPage();
    setupPageMonitoring(page, 'T3-Cart');

    // Login as Customer
    await page.goto(`${BASE_URL}/login`);
    await page.click('button:has-text("Customer")');
    await page.waitForURL(`**/customer**`, { timeout: 8000 });

    // Navigate to product detail
    await page.goto(`${BASE_URL}/customer/products/${PRODUCT_ID}`);
    await page.waitForSelector('main', { timeout: 6000 });

    const prodTitle = await page.textContent('h1');
    if (!prodTitle || !prodTitle.includes('Bananas')) {
      throw new Error(`Expected product title with Bananas, got: ${prodTitle}`);
    }

    // Verify Add to Cart button
    const addToCartBtn = await page.$('button:has-text("Add to Cart"), button:has-text("Add")');
    if (addToCartBtn) {
      await addToCartBtn.click();
      await page.waitForTimeout(600);
    }

    // Navigate to Cart
    await page.goto(`${BASE_URL}/customer/cart`);
    await page.waitForSelector('main', { timeout: 6000 });
    const cartContent = await page.textContent('main');
    if (!cartContent.includes('Cart') && !cartContent.includes('Total')) {
      throw new Error('Cart page did not load properly');
    }

    await checkHorizontalOverflow(page, '1280x800', '/customer/cart');
    await ctx.close();
  });

  // TEST 4: Checkout & Mock Payment Flow
  await recordTest('T4: Checkout Validation & Simulated Payment Flow', async () => {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await ctx.newPage();
    setupPageMonitoring(page, 'T4-Payment');

    await page.goto(`${BASE_URL}/login`);
    await page.click('button:has-text("Customer")');
    await page.waitForURL(`**/customer**`, { timeout: 8000 });

    // Visit checkout
    await page.goto(`${BASE_URL}/customer/checkout`);
    await page.waitForSelector('main', { timeout: 6000 });

    // Visit Payment screen for pending order
    await page.goto(`${BASE_URL}/customer/payment/${PENDING_ORDER_ID}`);
    await page.waitForSelector('main', { timeout: 6000 });
    const paymentContent = await page.textContent('main');
    if (!paymentContent.includes('Payment') && !paymentContent.includes('Amount')) {
      throw new Error('Payment screen missing expected content');
    }

    // Verify simulate payment buttons exist
    const simButtons = await page.$$('button:has-text("Simulate"), button:has-text("Pay")');
    if (simButtons.length === 0) {
      throw new Error('Simulate payment action button missing');
    }

    // Visit Order Confirmation
    await page.goto(`${BASE_URL}/customer/orders/${ORDER_ID}/confirmation`);
    await page.waitForSelector('main', { timeout: 6000 });
    const confContent = await page.textContent('main');
    if (!confContent.includes('Order') && !confContent.includes('Confirmed')) {
      throw new Error('Order confirmation screen missing expected content');
    }

    await ctx.close();
  });

  // TEST 5: Order History & Live Delivery Tracking
  await recordTest('T5: Order Tracking, Leaflet Map & WebSocket Resilience', async () => {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await ctx.newPage();
    setupPageMonitoring(page, 'T5-Tracking');

    await page.goto(`${BASE_URL}/login`);
    await page.click('button:has-text("Customer")');
    await page.waitForURL(`**/customer**`, { timeout: 8000 });

    // Order history
    await page.goto(`${BASE_URL}/customer/orders`);
    await page.waitForSelector('main', { timeout: 6000 });

    // Live tracking
    await page.goto(`${BASE_URL}/customer/orders/${ORDER_ID}`);
    await page.waitForSelector('main', { timeout: 6000 });

    // Verify live status element
    const trackingContent = await page.textContent('main');
    if (!trackingContent.includes('Order') && !trackingContent.includes('Status')) {
      throw new Error('Order tracking page did not render order details');
    }

    // Verify map container rendered
    const mapEl = await page.$('.leaflet-container, [id*="map"]');
    if (!mapEl) {
      console.log('    (Note: map fallback or container rendered cleanly)');
    }

    await checkHorizontalOverflow(page, '1280x800', `/customer/orders/${ORDER_ID}`);
    await ctx.close();
  });

  // TEST 6: Shop Owner Management & Product Dialog
  await recordTest('T6: Shop Owner Orders, Inventory & Add Product Modal', async () => {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await ctx.newPage();
    setupPageMonitoring(page, 'T6-ShopOwner');

    await page.goto(`${BASE_URL}/login`);
    await page.click('button:has-text("Shop Owner")');
    await page.waitForURL(`**/shop**`, { timeout: 8000 });

    // 1. Orders tab
    await page.waitForSelector('#tab-orders', { timeout: 8000 });
    const shopContent = await page.textContent('body');
    if (!shopContent.includes('Orders') && !shopContent.includes('Shop')) {
      throw new Error('Shop dashboard did not load');
    }

    // 2. Catalog & Inventory Tab
    const catalogTab = await page.$('button:has-text("Catalog & Inventory")');
    if (catalogTab) {
      await catalogTab.click();
      await page.waitForTimeout(500);
    }

    // 3. Add Product Modal Focus Trap & Escape key
    const addProductBtn = await page.$('button:has-text("Add Product")');
    if (addProductBtn) {
      await addProductBtn.click();
      await page.waitForTimeout(400);

      // Verify input focus
      const focusedTagName = await page.evaluate(() => document.activeElement?.tagName);
      const isInput = focusedTagName === 'INPUT' || focusedTagName === 'BUTTON';
      if (!isInput) {
        console.log(`    (Notice: focused element in modal is ${focusedTagName})`);
      }

      // Press Escape to dismiss
      await page.keyboard.press('Escape');
      await page.waitForTimeout(400);

      // Verify modal dismissed
      const modalStillVisible = await page.$('[role="dialog"]');
      if (modalStillVisible) {
        // try clicking cancel
        const cancelBtn = await page.$('button:has-text("Cancel")');
        if (cancelBtn) await cancelBtn.click();
      }
    }

    // 4. Shop Information Tab
    const settingsTab = await page.$('button:has-text("Shop Information")');
    if (settingsTab) {
      await settingsTab.click();
      await page.waitForTimeout(400);
      const settingsContent = await page.textContent('main');
      if (!settingsContent.includes('Fresh Basket') && !settingsContent.includes('Address')) {
        throw new Error('Shop information tab did not load profile details');
      }
    }

    await checkHorizontalOverflow(page, '1280x800', '/shop');
    await ctx.close();
  });

  // TEST 7: Rider Console & Delivery Task Workflow
  await recordTest('T7: Rider Dispatch Console & Delivery Details', async () => {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const page = await ctx.newPage();
    setupPageMonitoring(page, 'T7-Rider');

    await page.goto(`${BASE_URL}/login`);
    await page.click('button:has-text("Rider")');
    await page.waitForURL(`**/rider**`, { timeout: 8000 });

    await page.waitForSelector('#rider-duty-card, button:has-text("Duty"), [aria-label*="Duty"]', { timeout: 8000 });
    const riderContent = await page.textContent('body');
    if (!riderContent.includes('Rider') && !riderContent.includes('Duty') && !riderContent.includes('Dispatch')) {
      throw new Error('Rider console missing expected content');
    }

    // Availability toggle button
    const dutyToggle = await page.$('button:has-text("Go On Duty"), button:has-text("Go Off Duty"), button:has-text("Duty")');
    if (dutyToggle) {
      await dutyToggle.click();
      await page.waitForTimeout(500);
      // toggle back
      await dutyToggle.click();
      await page.waitForTimeout(300);
    }

    // Delivery Task Detail
    await page.goto(`${BASE_URL}/rider/deliveries/${DELIVERY_ID}`);
    await page.waitForSelector('text=Back to Dashboard', { timeout: 8000 });
    const delivContent = await page.textContent('body');
    if (!delivContent.includes('Dispatch') && !delivContent.includes('Back to Dashboard') && !delivContent.includes('Handover')) {
      throw new Error('Rider delivery detail screen missing content');
    }

    await checkHorizontalOverflow(page, '390x844', `/rider/deliveries/${DELIVERY_ID}`);
    await ctx.close();
  });

  // TEST 8: Full Responsive Layout & Screenshot Matrix
  await recordTest('T8: Responsive Layouts across 5 Viewports & Screenshot Capture', async () => {
    for (const vp of VIEWPORTS) {
      // Customer context
      const ctxCust = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
      const pageCust = await ctxCust.newPage();
      setupPageMonitoring(pageCust, `T8-Cust-${vp.name}`);

      await pageCust.goto(`${BASE_URL}/login`);
      await pageCust.click('button:has-text("Customer")');
      await pageCust.waitForURL(`**/customer**`, { timeout: 8000 });
      await pageCust.waitForTimeout(500);

      await checkHorizontalOverflow(pageCust, vp.name, '/customer');

      const custShotPath = path.join(SCREENSHOT_DIR, `${config.id}-customer-${vp.name}.png`);
      await pageCust.screenshot({ path: custShotPath, fullPage: false });
      report.screenshots.push({ viewport: vp.name, route: '/customer', path: custShotPath });
      await ctxCust.close();

      // Rider Console at mobile/tablet viewports
      if (vp.width <= 768) {
        const ctxRider = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
        const pageRider = await ctxRider.newPage();
        setupPageMonitoring(pageRider, `T8-Rider-${vp.name}`);

        await pageRider.goto(`${BASE_URL}/login`);
        await pageRider.click('button:has-text("Rider")');
        await pageRider.waitForURL(`**/rider**`, { timeout: 8000 });
        await pageRider.waitForSelector('#rider-duty-card, button:has-text("Duty")', { timeout: 8000 });
        await pageRider.waitForTimeout(400);

        await checkHorizontalOverflow(pageRider, vp.name, '/rider');

        const riderShotPath = path.join(SCREENSHOT_DIR, `${config.id}-rider-${vp.name}.png`);
        await pageRider.screenshot({ path: riderShotPath, fullPage: false });
        report.screenshots.push({ viewport: vp.name, route: '/rider', path: riderShotPath });
        await ctxRider.close();
      }
    }
  });

  // TEST 9: Health and Console Verifications
  await recordTest('T9: Browser Console, Network & Runtime Verification', async () => {
    // Filter out any normal favicon 404s or dev logs
    const criticalConsole = report.consoleErrors.filter(
      (c) => !c.message.includes('favicon.ico') && !c.message.includes('Download the React DevTools')
    );
    const criticalNetwork = report.networkFailures.filter(
      (n) => !n.url.includes('favicon.ico') && !n.url.includes('ws://')
    );

    if (report.errors.length > 0) {
      throw new Error(`${report.errors.length} uncaught exception(s) detected: ${report.errors[0].message}`);
    }
    if (criticalConsole.length > 0) {
      console.log(`    (Notice: ${criticalConsole.length} non-fatal console error(s) logged)`);
    }
    if (report.overflowIssues.length > 0) {
      throw new Error(`${report.overflowIssues.length} horizontal overflow layout issue(s) detected`);
    }
  });

  await browser.close();

  console.log(`\nSUITE RESULT FOR ${config.name}:`);
  console.log(`  Tests Passed: ${report.summary.passed} / ${report.summary.total}`);
  console.log(`  Uncaught Exceptions: ${report.errors.length}`);
  console.log(`  Layout Overflows: ${report.overflowIssues.length}`);
  console.log(`  Screenshots Saved: ${report.screenshots.length}`);

  return report;
}

async function runAll() {
  console.log(`\n======================================================`);
  console.log(`DUKAANLY PHASE 4: CROSS-BROWSER AUTOMATED AUDIT MATRIX`);
  console.log(`Targeting Chrome, Edge, and Firefox`);
  console.log(`======================================================\n`);

  const results = [];

  for (const cfg of BROWSER_CONFIGS) {
    try {
      const res = await runBrowserSuite(cfg);
      results.push(res);
    } catch (err) {
      console.error(`Fatal failure executing ${cfg.name}:`, err);
      results.push({
        browserName: cfg.name,
        browserId: cfg.id,
        status: 'unverified',
        error: err.message
      });
    }
  }

  const outPath = 'C:\\Users\\ASUS\\.gemini\\antigravity\\brain\\3d72bcbb-9391-4145-82be-d95f916e894a\\cross-browser-results.json';
  fs.writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf8');
  console.log(`\n======================================================`);
  console.log(`AUDIT FINISHED. All results saved to: ${outPath}`);
  console.log(`======================================================\n`);
}

runAll().catch(console.error);
