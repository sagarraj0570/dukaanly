const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

(async () => {
  const browser = await chromium.launch({ channel: 'msedge' });
  const viewports = [
    { name: 'mobile-360', width: 360, height: 740 },
    { name: 'tablet-768', width: 768, height: 1024 },
    { name: 'desktop-1280', width: 1280, height: 800 },
    { name: 'desktop-1920', width: 1920, height: 1080 }
  ];

  const outDir = path.resolve('C:/Users/ASUS/.gemini/antigravity/brain/3d72bcbb-9391-4145-82be-d95f916e894a/login-redesign');
  if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });

  for (const vp of viewports) {
    const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
    const page = await context.newPage();
    await page.goto('http://localhost:5173/login', { waitUntil: 'networkidle' });
    
    // Check overflow
    const overflow = await page.evaluate(() => {
      return document.documentElement.scrollWidth > window.innerWidth;
    });

    const screenshotPath = path.join(outDir, vp.name + '.png');
    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log(`Viewport ${vp.name}: width=${vp.width}, overflow=${overflow}`);
    await context.close();
  }

  await browser.close();
  console.log('ALL VIEWPORTS AUDITED SUCCESSFULLY');
})();
