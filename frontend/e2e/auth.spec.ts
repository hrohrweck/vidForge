import { test, expect } from '@playwright/test'
import {
  registerTestUser,
  loginTestUser,
  uniqueEmail,
  testPassword,
  ADMIN_EMAIL,
  ADMIN_PASSWORD,
} from './helpers'

test.describe('Authentication', () => {
  test.describe('Login page', () => {
    test('shows login form by default', async ({ page }) => {
      await page.goto('/login')

      await expect(page.getByLabel('Email')).toBeVisible()
      await expect(page.getByLabel('Password')).toBeVisible()
      await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible()
      await expect(page.getByText(/sign up/i)).toBeVisible()
    })

    test('shows validation errors for empty submission', async ({ page }) => {
      await page.goto('/login')

      // Try clicking submit with empty fields — browser validation keeps us on page
      await page.getByRole('button', { name: /sign in/i }).click()
      await expect(page.getByLabel('Email')).toBeVisible()
    })

    test('shows error on wrong credentials', async ({ page }) => {
      await page.goto('/login')

      await page.getByLabel('Email').fill('nonexistent@test.com')
      await page.getByLabel('Password').fill('wrongpassword123')
      await page.getByRole('button', { name: /sign in/i }).click()

      await expect(page.getByText(/invalid/i)).toBeVisible({ timeout: 10000 })
    })

    test('can register a new account', async ({ page }) => {
      const email = uniqueEmail()
      const password = testPassword()

      await page.goto('/login')

      // Switch to register mode
      await page.getByText(/sign up/i).click()
      await expect(page.getByRole('button', { name: /create account/i })).toBeVisible()

      await page.getByLabel('Email').fill(email)
      await page.getByLabel('Password').fill(password)
      await page.getByRole('button', { name: /create account/i }).click()

      // Should redirect to dashboard after successful registration + auto-login
      await expect(page).toHaveURL('/', { timeout: 15000 })
      await expect(page.getByRole('heading', { name: /dashboard/i })).toBeVisible()
    })

    test('can log in with existing credentials', async ({ page }) => {
      // First register via API
      const user = await registerTestUser()

      await page.goto('/login')

      await page.getByLabel('Email').fill(user.email)
      await page.getByLabel('Password').fill(user.password)
      await page.getByRole('button', { name: /sign in/i }).click()

      // Should redirect to dashboard
      await expect(page).toHaveURL('/', { timeout: 15000 })
      await expect(page.getByRole('heading', { name: /dashboard/i })).toBeVisible()
    })

    test('redirects unauthenticated users to login', async ({ page }) => {
      await page.goto('/jobs')
      await expect(page).toHaveURL(/\/login/, { timeout: 5000 })
    })
  })

  test.describe('Logout', () => {
    test('can log out from the avatar menu', async ({ page }) => {
      const user = await registerTestUser()

      // Log in via the page
      await page.goto('/login')
      await page.getByLabel('Email').fill(user.email)
      await page.getByLabel('Password').fill(user.password)
      await page.getByRole('button', { name: /sign in/i }).click()
      await expect(page).toHaveURL('/', { timeout: 15000 })

      // Open avatar dropdown (round button with user initial)
      const avatarButton = page.locator('header button.rounded-full')
      await avatarButton.click()

      // Click logout menu item
      await page.getByRole('menuitem', { name: /log out/i }).click()

      // Should be back on login page
      await expect(page).toHaveURL(/\/login/, { timeout: 5000 })
    })
  })

  test.describe('Default admin', () => {
    test('can log in as the default admin', async ({ page }) => {
      await page.goto('/login')

      await page.getByLabel('Email').fill(ADMIN_EMAIL)
      await page.getByLabel('Password').fill(ADMIN_PASSWORD)
      await page.getByRole('button', { name: /sign in/i }).click()

      // Should redirect to dashboard
      await expect(page).toHaveURL('/', { timeout: 15000 })

      // Admin should see the Admin nav link
      await expect(page.getByRole('link', { name: /^admin$/i })).toBeVisible()
    })
  })
})
