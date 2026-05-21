import { test, expect } from '@playwright/test'
import { registerTestUser } from './helpers'

test.describe('Navigation & Layout', () => {
  test.beforeEach(async ({ page }) => {
    const user = await registerTestUser()
    await injectAuth(page, user.token, user.email)
  })

  test('sidebar shows all standard nav items for regular user', async ({
    page,
  }) => {
    await expect(page.getByRole('link', { name: /dashboard/i })).toBeVisible()
    await expect(page.getByRole('link', { name: /jobs/i })).toBeVisible()
    await expect(page.getByRole('link', { name: /templates/i })).toBeVisible()
    await expect(page.getByRole('link', { name: /media/i })).toBeVisible()
    await expect(page.getByRole('link', { name: /settings/i })).toBeVisible()

    // Regular user should NOT see admin links
    await expect(page.getByRole('link', { name: /^admin$/i })).not.toBeVisible()
  })

  test('navigates between pages', async ({ page }) => {
    // Dashboard -> Jobs
    await page.getByRole('link', { name: /jobs/i }).first().click()
    await expect(page).toHaveURL('/jobs')

    // Jobs -> Templates
    await page.getByRole('link', { name: /templates/i }).first().click()
    await expect(page).toHaveURL('/templates')

    // Templates -> Settings
    await page.getByRole('link', { name: /settings/i }).first().click()
    await expect(page).toHaveURL('/settings')
  })

  test('shows user avatar in header', async ({ page }) => {
    // The avatar button shows the user's email first letter
    // Injected email starts with 'e2e-...' so the button shows 'E'
    const avatarButton = page.locator('header button.rounded-full')
    await expect(avatarButton).toBeVisible()
  })
})

test.describe('Dashboard page', () => {
  test.beforeEach(async ({ page }) => {
    const user = await registerTestUser()
    await injectAuth(page, user.token, user.email)
  })

  test('displays dashboard heading', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /dashboard/i })).toBeVisible()
  })

  test('shows stat cards', async ({ page }) => {
    await expect(page.getByText('Total Jobs')).toBeVisible()
    await expect(page.getByText('Completed')).toBeVisible()
    await expect(page.getByText('Processing')).toBeVisible()
    await expect(page.getByText('Failed')).toBeVisible()
  })
})

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

async function injectAuth(
  page: import('@playwright/test').Page,
  token: string,
  email: string,
) {
  await page.goto('/login')
  await page.evaluate(
    ({ t, e }) => {
      const authState = {
        state: {
          token: t,
          user: {
            id: 'e2e-user',
            email: e,
            is_active: true,
            is_superuser: false,
            groups: [],
            permissions: [],
          },
          isAuthenticated: true,
        },
        version: 0,
      }
      localStorage.setItem('auth-storage', JSON.stringify(authState))
    },
    { t: token, e: email },
  )
  await page.goto('/')
}
