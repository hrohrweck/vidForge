import { describe, it, expect, beforeEach } from 'vitest'
import { screen, waitFor, prettyDOM } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import ModelManagement from '../../../pages/admin/ModelManagement'
import { renderWithProviders } from '../../../test/utils'
import { server } from '../../../test/mocks/server'

const mockProviders = [
  { id: 'p1', name: 'Local ComfyUI', provider_type: 'comfyui_direct', config: {}, is_active: true, daily_budget_limit: 50, current_daily_spend: 0, priority: 0, created_at: '2024-01-01T00:00:00Z' },
]

describe('Debug', () => {
  beforeEach(() => {
    server.resetHandlers()
    server.use(
      http.get('*/api/providers', () => HttpResponse.json(mockProviders)),
      http.get('*/api/admin/model-configs', () => HttpResponse.json([])),
    )
  })

  it('debug select', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ModelManagement />, { superuser: true })
    await waitFor(() => { expect(screen.getByText('Model Management')).toBeInTheDocument() })
    
    const allCombos = screen.getAllByRole('combobox')
    console.log('Found', allCombos.length, 'comboboxes')
    allCombos.forEach((c, i) => console.log(`Combobox ${i}:`, c.textContent?.substring(0, 50)))
    
    const syncCombo = allCombos.find(el => el.textContent?.includes('Select provider'))
    if (syncCombo) {
      console.log('Clicking sync combo...')
      await user.click(syncCombo)
      await new Promise(r => setTimeout(r, 500))
      
      console.log('DOM after click:')
      console.log(prettyDOM(document.body, 2000))
      
      const allOptions = screen.queryAllByRole('option')
      console.log('Found', allOptions.length, 'options')
    }
  })
})
