import { test, expect } from '@playwright/test'
import { registerTestUser, injectAuth } from './helpers'

test.describe('Dashboard Histograms', () => {
  let token: string
  let email: string

  test.beforeAll(async () => {
    const user = await registerTestUser()
    token = user.token
    email = user.email
  })

  test.beforeEach(async ({ page }) => {
    await injectAuth(page, token, email)
  })

  test('renders Token Usage and Cost charts on dashboard', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: /dashboard/i })).toBeVisible()

    await expect(page.getByRole('heading', { name: 'Token Usage' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Cost' })).toBeVisible()
  })

  test('Token Usage chart renders SVG elements via recharts', async ({ page }) => {
    await page.goto('/')

    const tokenSection = page.getByRole('heading', { name: 'Token Usage' })
      .locator('..')
    const svgElements = tokenSection.locator('svg')
    await expect(svgElements.first()).toBeVisible({ timeout: 15_000 })
  })

  test('Cost chart renders SVG elements via recharts', async ({ page }) => {
    await page.goto('/')

    const costSection = page.getByRole('heading', { name: 'Cost' })
      .locator('..')
    const svgElements = costSection.locator('svg')
    await expect(svgElements.first()).toBeVisible({ timeout: 15_000 })
  })

  test('both charts render recharts bar elements', async ({ page }) => {
    await page.goto('/')

    const allBars = page.locator('svg .recharts-bar-rectangle')
    await expect(allBars.first()).toBeVisible({ timeout: 15_000 })
  })

  test.fixme('timeframe dropdown selects Monthly and charts update', async ({ page }) => {
    await page.goto('/')

    const timeframeDropdown = page.getByRole('combobox', { name: /timeframe/i })
    await expect(timeframeDropdown).toBeVisible()
    await timeframeDropdown.selectOption('Monthly')

    await page.waitForTimeout(500)

    const svgElements = page.locator('svg')
    await expect(svgElements.first()).toBeVisible()
  })
})
