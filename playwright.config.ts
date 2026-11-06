import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/responsive',
  timeout: 30000,
  expect: {
    timeout: 7000,
  },
  fullyParallel: true,
  retries: 0,
  workers: 4,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'tests/responsive/artifacts/report' }]],
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'Mobile Small Android (360x640)',
      use: {
        viewport: { width: 360, height: 640 },
        hasTouch: true,
        isMobile: true,
        userAgent:
          'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
      },
    },
    {
      name: 'Mobile iPhone SE',
      use: {
        viewport: { width: 375, height: 667 },
        hasTouch: true,
        isMobile: true,
        deviceScaleFactor: 2,
      },
    },
    {
      name: 'Mobile iPhone 14',
      use: {
        viewport: { width: 390, height: 844 },
        hasTouch: true,
        isMobile: true,
        deviceScaleFactor: 3,
      },
    },
    {
      name: 'Mobile Pixel 7',
      use: {
        viewport: { width: 412, height: 915 },
        hasTouch: true,
        isMobile: true,
        deviceScaleFactor: 2.625,
      },
    },
    {
      name: 'Tablet iPad Mini',
      use: {
        viewport: { width: 768, height: 1024 },
        hasTouch: true,
        isMobile: true,
        deviceScaleFactor: 2,
      },
    },
    {
      name: 'Tablet iPad Mini landscape',
      use: {
        viewport: { width: 1024, height: 768 },
        hasTouch: true,
        isMobile: true,
        deviceScaleFactor: 2,
      },
    },
    {
      name: 'Tablet iPad Pro 11',
      use: {
        viewport: { width: 834, height: 1194 },
        hasTouch: true,
        isMobile: true,
        deviceScaleFactor: 2,
      },
    },
    {
      name: 'Desktop 1280x800',
      use: {
        viewport: { width: 1280, height: 800 },
        hasTouch: false,
        isMobile: false,
      },
    },
    {
      name: 'Desktop 1920x1080',
      use: {
        viewport: { width: 1920, height: 1080 },
        hasTouch: false,
        isMobile: false,
      },
    },
  ],
  webServer: {
    command: 'cmd /c "npm --prefix frontend run dev -- --port 5173"',
    port: 5173,
    reuseExistingServer: true,
    timeout: 30000,
  },
})
