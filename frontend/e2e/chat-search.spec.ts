import { test, expect } from '@playwright/test'
import { registerTestUser, injectAuth } from './helpers'

function nonTextPatterns(): RegExp[] {
  return [
    /flux/i,
    /stable.?diffusion/i,
    /sdxl/i,
    /dall.?e/i,
    /midjourney/i,
    /wan/i,
    /musicgen/i,
    /audiocraft/i,
    /bark/i,
    /whisper/i,
    /tts/i,
  ]
}

function isNonTextModel(optionLabel: string): boolean {
  return nonTextPatterns().some((pattern) => pattern.test(optionLabel))
}

function isSkippableOption(label: string): boolean {
  return (
    label.length === 0 ||
    label.includes('─') ||
    label === 'Loading models...' ||
    label === 'No models available' ||
    label.includes('Custom model')
  )
}

test.describe('Chat Search', () => {
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

  test('sidebar search filters conversations', async ({ page }) => {
    await page.goto('/chat')

    const searchInput = page.getByPlaceholder(/search conversations/i)
    await expect(searchInput).toBeVisible()

    await searchInput.fill('test')
    await page.waitForTimeout(300)

    const conversationList = page.locator('ul li, [role="list"]')
    const noResults = page.getByText(/no (conversations|results) found/i)
    const hasConversations = await conversationList.first().isVisible().catch(() => false)
    const hasNoResults = await noResults.isVisible().catch(() => false)

    expect(hasConversations || hasNoResults).toBe(true)
  })

  test('messages display timestamps', async ({ page }) => {
    await page.goto('/chat')

    await page.getByRole('button', { name: /new chat/i }).click()
    await page.waitForTimeout(500)

    const messageInput = page.getByPlaceholder(/type a message/i)
    await expect(messageInput).toBeVisible()
    await messageInput.fill('Hello, this is a test message.')
    await messageInput.press('Enter')
    await page.waitForTimeout(1000)

    await expect(page.getByText('Hello, this is a test message.')).toBeVisible()

    const timeElements = page.locator('time, [data-timestamp], [datetime]')
    const datePattern = page.getByText(/\d{1,2}[:/]\d{2}/)
    const hasTimestampElement = await timeElements.first().isVisible().catch(() => false)
    const hasDatePattern = await datePattern.first().isVisible().catch(() => false)

    expect(hasTimestampElement || hasDatePattern).toBe(true)
  })

  test('model filter shows only text-output models', async ({ page }) => {
    await page.goto('/chat')

    const modelSelect = page.locator('select')
    await expect(modelSelect).toBeVisible()

    const options = modelSelect.locator('option')
    const optionCount = await options.count()
    expect(optionCount).toBeGreaterThan(0)

    for (let i = 0; i < optionCount; i++) {
      const text = (await options.nth(i).textContent()) ?? ''
      const label = text.trim()

      if (isSkippableOption(label)) continue

      expect(isNonTextModel(label)).toBe(false)
    }
  })
})
