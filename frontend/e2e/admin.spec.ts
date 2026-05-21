import { test, expect } from '@playwright/test'
import { ADMIN_EMAIL, ADMIN_PASSWORD } from './helpers'

test.describe('Admin pages', () => {
  test.beforeEach(async ({ page }) => {
    // Login as admin via the form
    await page.goto('/login')
    await page.getByLabel('Email').fill(ADMIN_EMAIL)
    await page.getByLabel('Password').fill(ADMIN_PASSWORD)
    await page.getByRole('button', { name: /sign in/i }).click()
    await expect(page).toHaveURL('/', { timeout: 15000 })
  })

  test('admin can see admin nav items', async ({ page }) => {
    await expect(page.getByRole('link', { name: /^admin$/i })).toBeVisible()
    await expect(page.getByRole('link', { name: /providers/i })).toBeVisible()
    await expect(page.getByRole('link', { name: /groups/i })).toBeVisible()
  })

  test('admin dashboard shows user management', async ({ page }) => {
    await page.getByRole('link', { name: /^admin$/i }).click()
    await expect(page).toHaveURL('/admin')
    await expect(page.getByRole('heading', { name: /users/i })).toBeVisible()
  })

  test('providers page shows provider management', async ({ page }) => {
    await page.getByRole('link', { name: /providers/i }).click()
    await expect(page).toHaveURL('/admin/providers')
    await expect(
      page.getByRole('heading', { name: /provider management/i }),
    ).toBeVisible()
  })

  test('groups page shows group management', async ({ page }) => {
    await page.getByRole('link', { name: /groups/i }).click()
    await expect(page).toHaveURL('/admin/groups')
    await expect(page.getByRole('heading', { name: /group/i })).toBeVisible()
  })
})

test.describe('Admin access control', () => {
  test('regular user cannot access admin pages', async ({ page }) => {
    // Register a regular user and inject auth
    const email = `e2e-restricted-${Date.now()}@test.com`
    const password = 'TestPass123!'

    const apiCtx = await import('@playwright/test').then((m) =>
      m.request.newContext({ baseURL: 'http://localhost:8001' }),
    )
    await apiCtx.post('/api/auth/register', {
      data: { email, password },
    })
    const loginRes = await apiCtx.post('/api/auth/login', {
      data: { email, password },
    })
    const { access_token: token } = await loginRes.json()
    await apiCtx.dispose()

    // Inject auth
    await page.goto('/login')
    await page.evaluate(
      ({ t, e }) => {
        localStorage.setItem(
          'auth-storage',
          JSON.stringify({
            state: {
              token: t,
              user: {
                id: 'e2e-regular',
                email: e,
                is_active: true,
                is_superuser: false,
                groups: [],
                permissions: [],
              },
              isAuthenticated: true,
            },
            version: 0,
          }),
        )
      },
      { t: token, e: email },
    )

    await page.goto('/admin')

    // Admin user management controls should not appear
    await expect(page.getByText(/delete user/i)).not.toBeVisible()
  })
})
