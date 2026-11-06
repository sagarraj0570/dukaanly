const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ channel: 'msedge' });
  const ctx = await browser.newContext({ viewport: { width: 375, height: 812 } });
  const page = await ctx.newPage();
  await page.goto('http://localhost:5173/login');
  await page.click('button:has-text("Customer")');
  await page.waitForURL('**/customer**');
  await page.goto('http://localhost:5173/customer/orders/e73d3c6a-f8b5-4f19-aae7-a47da6860582/confirmation');
  await page.waitForLoadState('networkidle');
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(400);
  await page.screenshot({ path: 'C:/Users/ASUS/.gemini/antigravity/brain/3d72bcbb-9391-4145-82be-d95f916e894a/screenshots/confirmation-scrolled-375x812.png' });
  
  const btn = page.locator('button:has-text("Track Order")');
  const btnBox = await btn.boundingBox();
  console.log('Track Order button position after scroll:', btnBox);
  
  // Also check Checkout page scrolled
  await page.goto('http://localhost:5173/customer/checkout');
  await page.waitForLoadState('networkidle');
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(400);
  await page.screenshot({ path: 'C:/Users/ASUS/.gemini/antigravity/brain/3d72bcbb-9391-4145-82be-d95f916e894a/screenshots/checkout-scrolled-375x812.png' });
  
  const confirmBtn = page.locator('button:has-text("Confirm Order")');
  const confirmBox = await confirmBtn.boundingBox();
  console.log('Confirm Order button position after scroll:', confirmBox);

  await browser.close();
})();
