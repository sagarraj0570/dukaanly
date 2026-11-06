const { chromium } = require('playwright');
const { AxeBuilder } = require('@axe-core/playwright');
const fs = require('fs');
const path = require('path');

const SHOP_ID = '397dd958-810a-4f84-89c8-6a35c082d47a';
const PRODUCT_ID = '493e2c6b-2012-4e77-a45f-f93a36244342';
const ORDER_ID = 'e73d3c6a-f8b5-4f19-aae7-a47da6860582';
const DELIVERY_ID = '7c9564d2-65dc-4f07-a9c0-91895282add2';

async function runAudit() {
  console.log('=== STARTING DUKAANLY A11Y AUDIT (WCAG 2.2 AA) ===\n');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const allViolations = [];

  async function auditPage(page, pageName, url) {
    console.log(`\nAuditing: ${pageName} (${url})...`);
    await page.waitForTimeout(600);
    try {
      const results = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
        .analyze();

      if (results.violations.length > 0) {
        console.log(`  ❌ ${results.violations.length} accessibility violation(s) found:`);
        results.violations.forEach((v) => {
          console.log(`    - [${v.impact?.toUpperCase()}] ${v.id}: ${v.help}`);
          v.nodes.slice(0, 3).forEach((n) => {
            console.log(`      Target: ${n.target.join(' ')}`);
            console.log(`      HTML: ${n.html.substring(0, 100)}`);
            console.log(`      Summary: ${n.failureSummary?.split('\n')[0]}`);
          });
          allViolations.push({
            page: pageName,
            url,
            id: v.id,
            impact: v.impact,
            help: v.help,
            helpUrl: v.helpUrl,
            description: v.description,
            nodes: v.nodes.map((n) => ({
              target: n.target,
              html: n.html,
              failureSummary: n.failureSummary,
            })),
          });
        });
      } else {
        console.log(`  ✓ Passed (0 violations)`);
      }
    } catch (err) {
      console.error(`  Error running axe scan: ${err.message}`);
    }
  }

  // 1. Logged out screens: Login & Register tabs
  const ctxAuth = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const pageAuth = await ctxAuth.newPage();
  await pageAuth.goto('http://localhost:5173/login');
  await auditPage(pageAuth, 'Login Page (Sign In Tab)', 'http://localhost:5173/login');

  const createAccountTab = await pageAuth.$('button:has-text("Create Account")');
  if (createAccountTab) {
    await createAccountTab.click();
    await auditPage(pageAuth, 'Login Page (Create Account Tab)', 'http://localhost:5173/login#register');
  }
  await ctxAuth.close();

  // 2. Customer Portal
  const ctxCust = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const pageCust = await ctxCust.newPage();
  await pageCust.goto('http://localhost:5173/login');
  await pageCust.click('button:has-text("Customer")');
  await pageCust.waitForURL('**/customer**');

  await auditPage(pageCust, 'Customer Dashboard', 'http://localhost:5173/customer');

  await pageCust.goto(`http://localhost:5173/customer/shops/${SHOP_ID}`);
  await auditPage(pageCust, 'Customer Shop Detail', `http://localhost:5173/customer/shops/${SHOP_ID}`);

  await pageCust.goto(`http://localhost:5173/customer/products/${PRODUCT_ID}`);
  await auditPage(pageCust, 'Customer Product Detail', `http://localhost:5173/customer/products/${PRODUCT_ID}`);

  await pageCust.goto('http://localhost:5173/customer/cart');
  await auditPage(pageCust, 'Customer Cart', 'http://localhost:5173/customer/cart');

  await pageCust.goto('http://localhost:5173/customer/checkout');
  await auditPage(pageCust, 'Customer Checkout', 'http://localhost:5173/customer/checkout');

  await pageCust.goto('http://localhost:5173/customer/orders');
  await auditPage(pageCust, 'Customer Order History', 'http://localhost:5173/customer/orders');

  await pageCust.goto(`http://localhost:5173/customer/orders/${ORDER_ID}`);
  await auditPage(pageCust, 'Customer Order Detail & Live Tracking', `http://localhost:5173/customer/orders/${ORDER_ID}`);

  await pageCust.goto(`http://localhost:5173/customer/orders/${ORDER_ID}/confirmation`);
  await auditPage(pageCust, 'Customer Order Confirmation', `http://localhost:5173/customer/orders/${ORDER_ID}/confirmation`);

  await pageCust.goto(`http://localhost:5173/customer/payment/${ORDER_ID}`);
  await auditPage(pageCust, 'Customer Payment Page', `http://localhost:5173/customer/payment/${ORDER_ID}`);
  await ctxCust.close();

  // 3. Shop Owner Portal
  const ctxShop = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const pageShop = await ctxShop.newPage();
  await pageShop.goto('http://localhost:5173/login');
  await pageShop.click('button:has-text("Shop Owner")');
  await pageShop.waitForURL('**/shop**');

  await auditPage(pageShop, 'Shop Owner Dashboard (Incoming Orders)', 'http://localhost:5173/shop#orders');

  await pageShop.click('button:has-text("Catalog & Inventory")');
  await pageShop.waitForTimeout(600);
  await auditPage(pageShop, 'Shop Owner Dashboard (Catalog & Inventory)', 'http://localhost:5173/shop#catalog');

  const addProductBtn = await pageShop.$('button:has-text("Add Product")');
  if (addProductBtn) {
    await addProductBtn.click();
    await pageShop.waitForTimeout(400);
    await auditPage(pageShop, 'Shop Owner Add Product Modal', 'http://localhost:5173/shop#modal');
    const cancelBtn = await pageShop.$('button:has-text("Cancel")');
    if (cancelBtn) await cancelBtn.click();
    else await pageShop.keyboard.press('Escape');
    await pageShop.waitForTimeout(300);
  }

  await pageShop.click('button:has-text("Shop Information")');
  await pageShop.waitForTimeout(400);
  await auditPage(pageShop, 'Shop Owner Dashboard (Shop Settings)', 'http://localhost:5173/shop#settings');
  await ctxShop.close();

  // 4. Rider Portal
  const ctxRider = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const pageRider = await ctxRider.newPage();
  await pageRider.goto('http://localhost:5173/login');
  await pageRider.click('button:has-text("Rider")');
  await pageRider.waitForURL('**/rider**');

  await auditPage(pageRider, 'Rider Dashboard', 'http://localhost:5173/rider');

  await pageRider.goto(`http://localhost:5173/rider/deliveries/${DELIVERY_ID}`);
  await auditPage(pageRider, 'Rider Delivery Detail', `http://localhost:5173/rider/deliveries/${DELIVERY_ID}`);
  await ctxRider.close();

  await browser.close();

  const outPath = 'C:\\Users\\ASUS\\.gemini\\antigravity\\brain\\3d72bcbb-9391-4145-82be-d95f916e894a\\a11y-audit-results.json';
  fs.writeFileSync(outPath, JSON.stringify(allViolations, null, 2), 'utf8');
  console.log(`\n=== AUDIT COMPLETE ===`);
  console.log(`Total Violations Found: ${allViolations.length}`);
  console.log(`Detailed results saved to: ${outPath}`);
}

runAudit().catch((err) => {
  console.error('Fatal audit error:', err);
  process.exit(1);
});
