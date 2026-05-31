import { beforeAll, afterAll, afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'
import { server } from './mocks/server'
import '@testing-library/jest-dom/vitest'

const store: Record<string, string> = {}
const mockStorage = {
  getItem: (key: string) => store[key] ?? null,
  setItem: (key: string, value: string) => { store[key] = value },
  removeItem: (key: string) => { delete store[key] },
  clear: () => { Object.keys(store).forEach(k => delete store[k]) },
  get length() { return Object.keys(store).length },
  key: (index: number) => Object.keys(store)[index] ?? null,
} as Storage

globalThis.localStorage = mockStorage
if (typeof window !== 'undefined') {
  window.localStorage = mockStorage
}

if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false
}

if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {}
}

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }))

afterEach(() => {
  cleanup()
  server.resetHandlers()
})

afterAll(() => server.close())
