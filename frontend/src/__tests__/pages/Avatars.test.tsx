import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, within, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Avatars from '../../pages/Avatars'
import { renderWithProviders } from '../../test/utils'
import { avatarsApi, type Avatar } from '../../api/avatars'
import { objectsApi, type ObjectRef } from '../../api/objects'

// ─── Mock avatarsApi module ──────────────────────────────────────────

vi.mock('../../api/avatars', () => ({
  avatarsApi: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    uploadImage: vi.fn(),
    setPrimaryImage: vi.fn(),
    deleteImage: vi.fn(),
    generatePoses: vi.fn(),
    trainLora: vi.fn(),
  },
}))

// ─── Mock objectsApi module ───────────────────────────────────────────

vi.mock('../../api/objects', () => ({
  objectsApi: {
    list: vi.fn(),
    get: vi.fn(),
    delete: vi.fn(),
  },
}))

// ─── Helpers ─────────────────────────────────────────────────────────

function mockAvatar(overrides: Partial<Avatar> = {}): Avatar {
  return {
    id: 'avatar-1',
    userId: 'user-1',
    name: 'Test Avatar',
    gender: 'Female',
    bio: 'A test character',
    consistencyStrategy: 'ip_adapter',
    primaryImageId: 'img-1',
    images: [
      {
        id: 'img-1',
        storagePath: '/avatars/img-1.png',
        isPrimary: true,
        sortOrder: 0,
        width: 512,
        height: 512,
        thumbnailUrl: '/thumbnails/img-1.jpg',
      },
    ],
    jobCount: 3,
    loraTrainingStatus: 'not_trained',
    createdAt: '2024-01-01T00:00:00Z',
    updatedAt: '2024-01-01T00:00:00Z',
    ...overrides,
  }
}

function mockObject(overrides: Partial<ObjectRef> = {}): ObjectRef {
  return {
    id: 'obj-1',
    user_id: 'user-1',
    name: 'Red Car',
    description: 'A fast red sports car',
    category: 'vehicle',
    visual_properties: { color: 'red' },
    images: [
      {
        id: 'objimg-1',
        storage_path: '/objects/car/front.png',
        is_primary: true,
        sort_order: 0,
        width: 1024,
        height: 768,
      },
    ],
    job_count: 2,
    created_at: '2024-05-01T00:00:00Z',
    updated_at: '2024-05-01T00:00:00Z',
    ...overrides,
  }
}

// ─── Tests ───────────────────────────────────────────────────────────

describe('Avatars Page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(avatarsApi.list).mockResolvedValue({ avatars: [], total: 0 })
    vi.mocked(avatarsApi.create).mockResolvedValue(mockAvatar({ id: 'new-avatar', name: 'New Avatar' }))
    vi.mocked(avatarsApi.delete).mockResolvedValue(undefined)
    vi.mocked(avatarsApi.update).mockResolvedValue(mockAvatar())
  })

  // 1. test_renders_empty_state
  it('renders empty state when no avatars exist', async () => {
    renderWithProviders(<Avatars />)

    await waitFor(() => {
      expect(screen.getByText('No avatars yet')).toBeInTheDocument()
    })
    expect(screen.getByText(/Create your first avatar/)).toBeInTheDocument()
  })

  // 2. test_renders_avatar_cards
  it('renders avatar cards when avatars are returned from API', async () => {
    vi.mocked(avatarsApi.list).mockResolvedValue({
      avatars: [
        mockAvatar({ name: 'Alice' }),
        mockAvatar({ id: 'avatar-2', name: 'Bob', gender: 'Male' }),
      ],
      total: 2,
    })

    renderWithProviders(<Avatars />)

    await waitFor(() => {
      expect(screen.getByText('Alice')).toBeInTheDocument()
    })
    expect(screen.getByText('Bob')).toBeInTheDocument()
    // Gender badges
    expect(screen.getByText('Female')).toBeInTheDocument()
    expect(screen.getByText('Male')).toBeInTheDocument()
  })

  // 3. test_create_modal_opens
  it('opens create modal when Create Avatar button is clicked', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Avatars />)

    await waitFor(() => {
      expect(screen.getByText('No avatars yet')).toBeInTheDocument()
    })

    const createButtons = screen.getAllByRole('button', { name: /create avatar/i })
    await user.click(createButtons[0])

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: 'Create Avatar' })).toBeInTheDocument()
  })

  // 4. test_create_modal_validates_name
  it('disables submit when name is empty in create form', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Avatars />)

    await waitFor(() => {
      expect(screen.getByText('No avatars yet')).toBeInTheDocument()
    })

    // Open create modal
    const createButtons = screen.getAllByRole('button', { name: /create avatar/i })
    await user.click(createButtons[0])

    const dialog = await screen.findByRole('dialog')
    // Submit should be disabled when name is empty
    const submitButton = within(dialog).getByRole('button', { name: /create avatar/i })
    expect(submitButton).toBeDisabled()

    // Type a name, then clear it
    const nameInput = screen.getByLabelText('Name *')
    await user.type(nameInput, 'Test')
    expect(submitButton).not.toBeDisabled()
    await user.clear(nameInput)
    expect(submitButton).toBeDisabled()
  })

  // 5. test_create_modal_submits
  it('calls avatarsApi.create when form is filled and submitted', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Avatars />)

    await waitFor(() => {
      expect(screen.getByText('No avatars yet')).toBeInTheDocument()
    })

    const createButtons = screen.getAllByRole('button', { name: /create avatar/i })
    await user.click(createButtons[0])

    const dialog = await screen.findByRole('dialog')
    const nameInput = screen.getByLabelText('Name *')
    await user.type(nameInput, 'My Character')

    const submitButton = within(dialog).getByRole('button', { name: /create avatar/i })
    expect(submitButton).not.toBeDisabled()
    await user.click(submitButton)

    await waitFor(() => {
      expect(avatarsApi.create).toHaveBeenCalledWith({
        name: 'My Character',
        gender: 'Male',
        bio: undefined,
        consistencyStrategy: 'ip_adapter',
      })
    })
  })

  // 6. test_edit_modal_opens_with_data
  it('opens edit modal with pre-filled data when clicking an avatar card', async () => {
    vi.mocked(avatarsApi.list).mockResolvedValue({
      avatars: [mockAvatar({ name: 'Charlie', gender: 'Non-binary', bio: 'Bio text' })],
      total: 1,
    })

    const user = userEvent.setup()
    renderWithProviders(<Avatars />)

    await waitFor(() => {
      expect(screen.getByText('Charlie')).toBeInTheDocument()
    })

    // Click the card (it has role="button")
    const card = screen.getByRole('button', { name: /charlie/i })
    await user.click(card)

    await waitFor(() => {
      expect(screen.getByText('Edit Avatar')).toBeInTheDocument()
    })

    // Pre-filled name in input
    expect(screen.getByDisplayValue('Charlie')).toBeInTheDocument()
  })

  // 7. test_delete_shows_confirmation
  it('shows delete confirmation dialog when delete is clicked in edit modal', async () => {
    vi.mocked(avatarsApi.list).mockResolvedValue({
      avatars: [mockAvatar({ name: 'DeleteMe' })],
      total: 1,
    })

    const user = userEvent.setup()
    renderWithProviders(<Avatars />)

    await waitFor(() => {
      expect(screen.getByText('DeleteMe')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /deleteme/i }))

    await waitFor(() => {
      expect(screen.getByText('Edit Avatar')).toBeInTheDocument()
    })

    const deleteButton = screen.getByRole('button', { name: /delete avatar/i })
    deleteButton.click()

    await waitFor(() => {
      expect(screen.getByText(/Are you sure you want to delete/)).toBeInTheDocument()
    })
    expect(screen.getByRole('checkbox', { hidden: true })).toBeInTheDocument()
  })

  // 8. test_delete_confirms
  it('calls avatarsApi.delete when deletion is confirmed', async () => {
    vi.mocked(avatarsApi.list).mockResolvedValue({
      avatars: [mockAvatar({ name: 'ToDelete' })],
      total: 1,
    })

    const user = userEvent.setup()
    renderWithProviders(<Avatars />)

    await waitFor(() => {
      expect(screen.getByText('ToDelete')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /todelete/i }))

    await waitFor(() => {
      expect(screen.getByText('Edit Avatar')).toBeInTheDocument()
    })

    screen.getByRole('button', { name: /delete avatar/i }).click()

    await waitFor(() => {
      expect(screen.getByText(/Are you sure/)).toBeInTheDocument()
    })

    const checkbox = screen.getByLabelText('I understand this action is irreversible')
    fireEvent.click(checkbox)

    const deleteConfirmBtn = screen.getByRole('button', { name: 'Delete', hidden: true })
    deleteConfirmBtn.click()

    await waitFor(() => {
      expect(avatarsApi.delete).toHaveBeenCalledWith('avatar-1')
    })
  })

  // ── Objects Tab Tests ─────────────────────────────────────────

  describe('Objects Tab', () => {
    beforeEach(() => {
      vi.mocked(avatarsApi.list).mockResolvedValue({ avatars: [], total: 0 })
      vi.mocked(objectsApi.list).mockResolvedValue({ objects: [], total: 0 })
      vi.mocked(objectsApi.delete).mockResolvedValue(undefined)
    })

    it('switches to Objects tab when tab button is clicked', async () => {
      const user = userEvent.setup()
      renderWithProviders(<Avatars />)

      await waitFor(() => {
        expect(screen.getByText('No avatars yet')).toBeInTheDocument()
      })

      const objectsTab = screen.getByRole('button', { name: /objects/i })
      await user.click(objectsTab)

      await waitFor(() => {
        expect(screen.getByText('No objects yet')).toBeInTheDocument()
      })
      expect(screen.getByText('Objects auto-detected from your scenes')).toBeInTheDocument()
    })

    it('renders object cards when objects are returned from API', async () => {
      vi.mocked(objectsApi.list).mockResolvedValue({
        objects: [
          mockObject({ name: 'Red Car', category: 'vehicle' }),
          mockObject({
            id: 'obj-2',
            name: 'Blue Vase',
            description: 'A ceramic vase',
            category: 'decor',
            images: [],
            job_count: 0,
          }),
        ],
        total: 2,
      })

      const user = userEvent.setup()
      renderWithProviders(<Avatars />)

      const objectsTab = screen.getByRole('button', { name: /objects/i })
      await user.click(objectsTab)

      await waitFor(() => {
        expect(screen.getByText('Red Car')).toBeInTheDocument()
      })
      expect(screen.getByText('Blue Vase')).toBeInTheDocument()

      // Category badges
      expect(screen.getByText('vehicle')).toBeInTheDocument()
      expect(screen.getByText('decor')).toBeInTheDocument()

      // Description
      expect(screen.getByText('A ceramic vase')).toBeInTheDocument()

      // Object without image shows "Pending" badge
      expect(screen.getByText('Pending')).toBeInTheDocument()

      // Job count
      expect(screen.getByText('Used in 2 jobs')).toBeInTheDocument()
    })

    it('shows empty state in objects tab when no objects exist', async () => {
      vi.mocked(objectsApi.list).mockResolvedValue({ objects: [], total: 0 })
      const user = userEvent.setup()
      renderWithProviders(<Avatars />)

      const objectsTab = screen.getByRole('button', { name: /objects/i })
      await user.click(objectsTab)

      await waitFor(() => {
        expect(screen.getByText('No objects yet')).toBeInTheDocument()
      })
      expect(
        screen.getByText(/Objects are automatically detected/)
      ).toBeInTheDocument()
    })

    it('switches back to avatars tab correctly', async () => {
      vi.mocked(avatarsApi.list).mockResolvedValue({
        avatars: [mockAvatar({ name: 'My Char' })],
        total: 1,
      })
      const user = userEvent.setup()
      renderWithProviders(<Avatars />)

      const objectsTab = screen.getByRole('button', { name: /objects/i })
      await user.click(objectsTab)

      await waitFor(() => {
        expect(screen.getByText('No objects yet')).toBeInTheDocument()
      })

      const avatarsTab = screen.getByRole('button', { name: /avatars/i })
      await user.click(avatarsTab)

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'Avatars' })).toBeInTheDocument()
        expect(screen.getByText('My Char')).toBeInTheDocument()
      })
    })

    it('shows delete confirmation and calls objectsApi.delete when confirm clicked', async () => {
      vi.mocked(objectsApi.list).mockResolvedValue({
        objects: [mockObject({ name: 'ToDeleteObj' })],
        total: 1,
      })
      renderWithProviders(<Avatars />)

      const objectsTab = screen.getByRole('button', { name: /objects/i })
      fireEvent.click(objectsTab)

      await waitFor(() => {
        expect(screen.getByText('ToDeleteObj')).toBeInTheDocument()
      })

      const card = screen.getByText('ToDeleteObj').closest('.group') as HTMLElement
      fireEvent.mouseOver(card)

      const deleteBtn = within(card).getByRole('button', { name: /delete/i })
      fireEvent.click(deleteBtn)

      await waitFor(() => {
        expect(screen.getByText('Delete Object')).toBeInTheDocument()
      })

      const modalContainer = screen.getByText('Delete Object').closest('.fixed') as HTMLElement
      const checkbox = within(modalContainer).getByRole('checkbox')
      fireEvent.click(checkbox)

      const confirmDeleteBtn = within(modalContainer).getByRole('button', { name: /^delete$/i })
      fireEvent.click(confirmDeleteBtn)

      await waitFor(() => {
        expect(objectsApi.delete).toHaveBeenCalledWith('obj-1')
      })
    })
  })
})
