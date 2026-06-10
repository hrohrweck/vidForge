import { test, expect } from '@playwright/test'
import { registerTestUser, injectAuth } from './helpers'
import path from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const TEST_IMAGE = path.join(__dirname, 'fixtures', 'test-image.png')
const CONVERSATION_ID = 'e2e-conv-thinking-test'
const API_BASE = '**/api/chat'

/**
 * Build an SSE response body from a list of {event, data} pairs.
 */
function buildSSEBody(events: Array<{ event: string; data: unknown }>): string {
  return events
    .map((e) => `event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n`)
    .join('\n')
}

/**
 * Common API mocks for chat tests.
 */
async function setupChatMocks(page: import('@playwright/test').Page, options?: {
  messages?: unknown[]
  streamEvents?: Array<{ event: string; data: unknown }>
  uploadResponse?: unknown
}) {
  await page.route(`${API_BASE}/conversations`, async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [] }),
      })
    } else if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: CONVERSATION_ID,
          title: 'Untitled',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }),
      })
    } else {
      await route.fallback()
    }
  })

  await page.route(`${API_BASE}/conversations/${CONVERSATION_ID}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: CONVERSATION_ID,
        title: 'Untitled',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }),
    })
  })

  await page.route(`${API_BASE}/conversations/${CONVERSATION_ID}/messages`, async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: options?.messages ?? [] }),
      })
    } else if (route.request().method() === 'POST') {
      const events = options?.streamEvents ?? [
        { event: 'token', data: { content: 'Hello!' } },
        { event: 'done', data: {} },
      ]
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: buildSSEBody(events),
      })
    } else {
      await route.fallback()
    }
  })

  if (options?.uploadResponse) {
    await page.route(`${API_BASE}/uploads`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(options.uploadResponse),
      })
    })
  }

  await page.route(`${API_BASE}/token-usage`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [] }),
    })
  })
}

/**
 * Helper: navigate to /chat and create a new conversation.
 */
async function createNewChat(page: import('@playwright/test').Page) {
  await page.goto('/chat')
  await page.getByRole('button', { name: /new chat/i }).first().click()
  const messageInput = page.getByPlaceholder(/type a message/i)
  await expect(messageInput).toBeVisible({ timeout: 10_000 })
  return messageInput
}

test.describe('Chat Thinking Filter and Media Display', () => {
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

  test('thinking tags are not visible in chat messages', async ({ page }) => {
    const streamEvents = [
      { event: 'token', data: { content: '<think>Let me analyze this step by step.</think>' } },
      { event: 'token', data: { content: 'Here is my answer to your question.' } },
      { event: 'done', data: {} },
    ]

    await setupChatMocks(page, { streamEvents })
    const messageInput = await createNewChat(page)

    await messageInput.fill('Explain quantum computing')
    await messageInput.press('Enter')

    await expect(page.getByText('Here is my answer to your question.')).toBeVisible({
      timeout: 15_000,
    })

    // CRITICAL: Verify <think> tags are NOT visible in the rendered chat area
    const chatArea = page.locator('.space-y-4.p-4, .h-full.overflow-y-auto').first()
    const bodyText = await chatArea.textContent()

    expect(bodyText).not.toContain('<think>')
    expect(bodyText).not.toContain('</think>')

    // If a thinking section exists, verify thinking content is isolated
    const thinkingButton = page.getByRole('button', { name: /thinking/i })
    if (await thinkingButton.isVisible().catch(() => false)) {
      const answerAreas = page.locator('.px-1')
      if (await answerAreas.count() > 0) {
        const answerText = await answerAreas.first().textContent()
        expect(answerText).not.toContain('Let me analyze this step by step')
      }
    }
  })

  test('uploaded image appears as attachment and in chat', async ({ page }) => {
    const uploadResponse = {
      attachment_id: 'att-123',
      kind: 'image',
      mime_type: 'image/png',
      size: 69,
      url: '/api/chat/uploads/att-123/test-image.png',
    }

    await setupChatMocks(page, {
      uploadResponse,
      streamEvents: [
        { event: 'token', data: { content: 'I can see the image you uploaded.' } },
        { event: 'done', data: {} },
      ],
    })

    const messageInput = await createNewChat(page)

    // Upload an image via the hidden file input
    const fileInput = page.locator('input[type="file"]')
    await fileInput.setInputFiles(TEST_IMAGE)

    // Verify the attachment chip appears (proves upload flow works)
    await expect(page.getByText('test-image.png')).toBeVisible({ timeout: 10_000 })

    // Verify the attachment chip has a remove button (proves it's a valid attachment)
    const removeButton = page.getByRole('button', { name: /remove attachment/i })
    await expect(removeButton).toBeVisible()

    // Type a message and send
    await messageInput.fill('What do you think of this image?')
    await messageInput.press('Enter')

    // Verify the user message text appears
    await expect(page.getByText('What do you think of this image?')).toBeVisible({ timeout: 10_000 })

    // Verify the assistant response appears
    await expect(page.getByText('I can see the image you uploaded.')).toBeVisible({ timeout: 15_000 })
  })

  test('generated media appears after job completion', async ({ page }) => {
    await setupChatMocks(page)
    await createNewChat(page)

    // Use the exposed Zustand store to inject messages with mediaResult
    // This simulates a completed job with generated media
    await page.evaluate((convId) => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const store = (window as any).__chatStore
      if (!store) throw new Error('Chat store not exposed on window')

      // Set the selected conversation
      store.getState().selectConversation(convId)

      // Add messages with mediaResult
      store.getState().setMessages(convId, [
        {
          id: 'msg-user-1',
          role: 'user',
          content: 'Generate an image of a sunset',
          createdAt: new Date().toISOString(),
        },
        {
          id: 'msg-assistant-1',
          role: 'assistant',
          content: 'Here is the generated image:',
          createdAt: new Date().toISOString(),
          mediaResult: {
            kind: 'image',
            url: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==',
            mime_type: 'image/png',
          },
        },
      ])
    }, CONVERSATION_ID)

    // Wait for the React re-render to complete
    await page.waitForTimeout(500)

    // Verify the assistant message content is visible
    await expect(page.getByText('Here is the generated image:')).toBeVisible({ timeout: 10_000 })

    // Verify the generated image is rendered (alt="Generated" from ChatMessageList.tsx)
    const generatedImage = page.locator('img[alt="Generated"]').first()
    await expect(generatedImage).toBeVisible({ timeout: 10_000 })

    // Verify the image src is our data URL
    const imgSrc = await generatedImage.getAttribute('src')
    expect(imgSrc).toContain('data:image/png;base64')
  })
})
