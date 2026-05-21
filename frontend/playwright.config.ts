import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright E2E test configuration.
 *
 * Prerequisites:
 *   - Backend running at http://localhost:8001 (or set BASE_URL)
 *   - Frontend dev server running at http://localhost:3000 (or set BASE_URL)
 *   - PostgreSQL and Redis available to the backend
 *
 * Run:
 *   npx playwright install          # first time only
 *   npx playwright test             # headless
 *   npx playwright test --headed    # with browser
 *   npx playwright test --ui        # interactive UI mode
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: process.env.CI ? 'github' : 'html',
  timeout: 30_000,
  expect: { timeout: 10_000 },

  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
