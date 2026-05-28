import { test, expect } from '@playwright/test'
import { registerTestUser, injectAuth } from './helpers'

test.describe('Cost Tracking', () => {
  let token: string

  test.beforeAll(async () => {
    const user = await registerTestUser()
    token = user.token
  })

  test.beforeEach(async ({ page }) => {
    await injectAuth(page, token)
  })

  test('shows cost estimate for image model in QuickCreateMedia', async ({ page }) => {
    await page.goto('/media')

    await page.getByRole('button', { name: /create media/i }).click()
    await expect(page.getByRole('heading', { name: /create media/i })).toBeVisible()

    await page.getByRole('tab', { name: /image models/i }).click()

    const modelButtons = page.locator('[role="tabpanel"] button')
    const firstModel = modelButtons.first()
    await firstModel.waitFor({ state: 'visible', timeout: 10000 })

    const modelName = await firstModel.textContent()
    test.skip(!modelName || modelName.includes('No image models'), 'No image models available')

    await firstModel.click()

    await expect(page.getByText(/aspect ratio/i)).toBeVisible()

    const costLabel = page.getByText(/estimated cost/i)
    await expect(costLabel).toBeVisible({ timeout: 5000 })

    const costText = await costLabel.textContent()
    expect(costText).toBeTruthy()
    expect(costText).not.toMatch(/0\s*credits/i)
    expect(costText).toMatch(/\d/)
  })

  test('cost estimate updates when video duration changes', async ({ page }) => {
    await page.goto('/media')

    await page.getByRole('button', { name: /create media/i }).click()
    await expect(page.getByRole('heading', { name: /create media/i })).toBeVisible()

    await page.getByRole('tab', { name: /video models/i }).click()

    const modelButtons = page.locator('[role="tabpanel"] button')
    const firstModel = modelButtons.first()
    await firstModel.waitFor({ state: 'visible', timeout: 10000 })

    const modelName = await firstModel.textContent()
    test.skip(!modelName || modelName.includes('No video models'), 'No video models available')

    await firstModel.click()

    await expect(page.getByText(/aspect ratio/i)).toBeVisible()

    const durationInput = page.getByLabel(/duration/i)
    await expect(durationInput).toBeVisible({ timeout: 3000 })

    const costLabel = page.getByText(/estimated cost/i)
    await expect(costLabel).toBeVisible({ timeout: 5000 })

    const initialCostText = await costLabel.textContent()
    expect(initialCostText).toBeTruthy()

    await durationInput.clear()
    await durationInput.fill('10')
    await page.waitForTimeout(500)

    const updatedCostText = await costLabel.textContent()
    expect(updatedCostText).toBeTruthy()
    expect(updatedCostText).not.toBe(initialCostText)
  })
})
