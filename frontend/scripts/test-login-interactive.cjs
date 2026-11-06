const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const browser = await chromium.launch({ channel: 'msedge' });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    permissions: ['clipboard-read', 'clipboard-write']
  });
  const page = await context.newPage();
  await page.goto('http://localhost:5173/login', { waitUntil: 'networkidle' });

  // 1. Switch tab to Create Account
  await page.click('button[role="tab"]:has-text("Create Account")');
  await page.waitForTimeout(300);

  // 2. Select Shop Owner role
  await page.click('button[role="radio"]:has-text("Shop Owner")');
  await page.waitForTimeout(200);

  // 3. Type a strong password to verify strength meter
  await page.fill('#login-password', 'SecurePass123!');
  await page.waitForTimeout(300);

  const outDir = path.resolve('C:/Users/ASUS/.gemini/antigravity/brain/3d72bcbb-9391-4145-82be-d95f916e894a/login-redesign');
  await page.screenshot({ path: path.join(outDir, 'create-account-mode-1440.png'), fullPage: true });
  console.log('Saved create-account screenshot');

  // 4. Switch back to Sign In
  await page.click('button[role="tab"]:has-text("Sign In")');
  await page.waitForTimeout(200);

  // 5. Check Demo Password Chip copy
  await page.click('button:has-text("Password123!")');
  await page.waitForTimeout(200);
  const copiedVisible = await page.isVisible('text=Copied!');
  console.log('Copied feedback visible:', copiedVisible);

  await page.screenshot({ path: path.join(outDir, 'sign-in-mode-1440.png'), fullPage: true });

  await browser.close();
  console.log('ALL INTERACTIVE TESTS COMPLETED');
})();
