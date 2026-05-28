/**
 * Shared E2E test helpers.
 *
 * All tests go through the real backend API to set up / tear down state,
 * so the tests exercise the full stack end-to-end.
 */

import { request, type APIRequestContext } from '@playwright/test'

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000'
const API_URL = process.env.API_URL || 'http://localhost:8001'

/* ------------------------------------------------------------------ */
/*  Test user pool                                                     */
/* ------------------------------------------------------------------ */

let userCounter = 0

export function uniqueEmail(): string {
  userCounter += 1
  return `e2e-${Date.now()}-${userCounter}@test.vidforge`
}

export function testPassword(): string {
  return 'TestPass123!'
}

/* ------------------------------------------------------------------ */
/*  Auth helpers                                                       */
/* ------------------------------------------------------------------ */

export interface TestUser {
  email: string
  password: string
  token: string
  id: string
}

/**
 * Register a brand-new user via the API and return credentials + token.
 */
export async function registerTestUser(
  api?: APIRequestContext,
): Promise<TestUser> {
  const email = uniqueEmail()
  const password = testPassword()
  const ctx = api || (await request.newContext({ baseURL: API_URL }))

  const reg = await ctx.post('/api/auth/register', {
    data: { email, password },
  })
  if (reg.status() !== 200) {
    throw new Error(`Register failed (${reg.status()}): ${await reg.text()}`)
  }
  const id = (await reg.json()).id

  const login = await ctx.post('/api/auth/login', {
    data: { email, password },
  })
  if (login.status() !== 200) {
    throw new Error(`Login failed (${login.status()}): ${await login.text()}`)
  }
  const token = (await login.json()).access_token

  if (!api) await ctx.dispose()
  return { email, password, token, id }
}

/**
 * Log in an existing user and return credentials + token.
 */
export async function loginTestUser(
  email: string,
  password: string,
  api?: APIRequestContext,
): Promise<TestUser> {
  const ctx = api || (await request.newContext({ baseURL: API_URL }))

  const login = await ctx.post('/api/auth/login', {
    data: { email, password },
  })
  if (login.status() !== 200) {
    throw new Error(`Login failed (${login.status()}): ${await login.text()}`)
  }
  const { access_token: token } = await login.json()

  const me = await ctx.get('/api/auth/me', {
    headers: { Authorization: `Bearer ${token}` },
  })
  const { id } = await me.json()

  if (!api) await ctx.dispose()
  return { email, password, token, id }
}

/* ------------------------------------------------------------------ */
/*  API helpers (with auth)                                            */
/* ------------------------------------------------------------------ */

export async function apiContext(
  token: string,
): Promise<APIRequestContext> {
  return request.newContext({
    baseURL: API_URL,
    extraHTTPHeaders: { Authorization: `Bearer ${token}` },
  })
}

/**
 * Get the first seeded template ID (needed to create jobs).
 */
export async function getFirstTemplateId(
  ctx: APIRequestContext,
): Promise<string | null> {
  const res = await ctx.get('/api/templates')
  if (res.status() !== 200) return null
  const templates = await res.json()
  if (!Array.isArray(templates) || templates.length === 0) return null
  return templates[0].id
}

/**
 * Get the seeded admin credentials. We only call this if we know the
 * default admin exists (first-run seeding).
 */
export const ADMIN_EMAIL = 'e2e-admin@vidforge.dev'
export const ADMIN_PASSWORD = 'E2eAdmin123!'

/* ------------------------------------------------------------------ */
/*  Browser auth injection                                             */
/* ------------------------------------------------------------------ */

/**
 * Inject auth state into the browser's localStorage so the app
 * considers the user authenticated without going through the login form.
 *
 * @param page - Playwright Page
 * @param token - JWT access token
 * @param email - Optional: the user's email (for the Zustand user object)
 */
export async function injectAuth(
  page: import('@playwright/test').Page,
  token: string,
  email?: string,
): Promise<void> {
  await page.goto('/')
  await page.evaluate(
    ({ token, email }) => {
      const state = {
        state: {
          token,
          user: email
            ? { id: '', email, is_active: true, is_superuser: false, groups: [], permissions: [] }
            : null,
          isAuthenticated: true,
        },
        version: 0,
      }
      localStorage.setItem('auth-storage', JSON.stringify(state))
    },
    { token, email },
  )
  await page.reload()
}
