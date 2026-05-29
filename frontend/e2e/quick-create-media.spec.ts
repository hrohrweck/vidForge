import { test, expect } from '@playwright/test'
import { registerTestUser, injectAuth } from './helpers'
import path from 'path'

const TEST_IMAGE = path.join(__dirname, 'fixtures', 'test-image.png')

test.describe('Quick Create Media', () => {
  let token: string

  test.beforeAll(async () => {
    const user = await registerTestUser()
    token = user.token
  })

  test.beforeEach(async ({ page }) => {
    await injectAuth(page, token)
  })

  test('opens and closes the create media modal', async ({ page }) => {
    await page.goto('/media')

    await page.getByRole('button', { name: /create media/i }).click()

    await expect(page.getByRole('heading', { name: /create media/i })).toBeVisible()
    await expect(page.getByRole('tab', { name: /image models/i })).toBeVisible()
    await expect(page.getByRole('tab', { name: /video models/i })).toBeVisible()

    await page.keyboard.press('Escape')
    await expect(page.getByRole('heading', { name: /create media/i })).not.toBeVisible()
  })

  test('selects image model and shows settings panel', async ({ page }) => {
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
    await expect(page.getByText(/prompt/i)).toBeVisible()
    await expect(page.getByText('← Back to model selection')).toBeVisible()
  })

  test('fills prompt, sets aspect ratio, and submits', async ({ page }) => {
    await page.goto('/media')

    await page.getByRole('button', { name: /create media/i }).click()

    await page.getByRole('tab', { name: /image models/i }).click()

    const modelButtons = page.locator('[role="tabpanel"] button')
    const firstModel = modelButtons.first()
    await firstModel.waitFor({ state: 'visible', timeout: 10000 })

    const modelName = await firstModel.textContent()
    test.skip(!modelName || modelName.includes('No image models'), 'No image models available')

    await firstModel.click()

    await expect(page.getByText(/aspect ratio/i)).toBeVisible()

    await page.getByPlaceholder(/describe what you want to generate/i).fill('a sunset over mountains')

    await page.getByRole('combobox', { name: /aspect ratio/i }).click()
    await page.getByRole('option', { name: '16:9' }).click()

    const generateBtn = page.getByRole('button', { name: /^generate$/i })
    await expect(generateBtn).toBeEnabled()

    await generateBtn.click()
    await expect(page.getByRole('heading', { name: /create media/i })).not.toBeVisible({ timeout: 15000 })
    await expect(page).toHaveURL(/\/media/)
  })

  test('create media flow with input image', async ({ page }) => {
    await page.goto('/media')
    await page.getByRole('button', { name: /create media/i }).click()
    await expect(page.getByRole('heading', { name: /create media/i })).toBeVisible()

    await page.getByRole('tab', { name: /image models/i }).click()

    const modelButtons = page.locator('[role="tabpanel"] button')
    const count = await modelButtons.count()

    let foundImageModel = false

    for (let i = 0; i < count; i++) {
      const btn = modelButtons.nth(i)
      const name = await btn.textContent()
      if (!name || name.includes('No image models')) continue

      await btn.click()

      const sourceImageLabel = page.getByText(/source image/i)
      const hasSourceImage = await sourceImageLabel.isVisible({ timeout: 3000 }).catch(() => false)

      if (hasSourceImage) {
        foundImageModel = true

        const fileInput = page.locator('input[type="file"]')
        await expect(fileInput).toBeVisible()
        await fileInput.setInputFiles(TEST_IMAGE)

        const preview = page.locator('img[alt="Preview"]')
        await expect(preview).toBeVisible({ timeout: 5000 })

        const promptField = page.getByPlaceholder(/describe what you want to generate/i)
        if (await promptField.isVisible({ timeout: 1000 }).catch(() => false)) {
          await promptField.fill('a beautiful landscape at sunset')
        }

        await page.getByRole('combobox', { name: /aspect ratio/i }).click()
        await page.getByRole('option', { name: '16:9' }).click()

        const generateBtn = page.getByRole('button', { name: /^generate$/i })
        await expect(generateBtn).toBeEnabled()
        await generateBtn.click()

        await expect(page.getByRole('heading', { name: /create media/i })).not.toBeVisible({ timeout: 15000 })
        break
      }

      await page.getByText(/back to model selection/i).click()
    }

    if (!foundImageModel) {
      // No image-to-image models available — skip gracefully
      test.skip(true, 'No image-to-image capable models available in the test environment')
    }
  })
})
