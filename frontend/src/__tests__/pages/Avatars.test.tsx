import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, within, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Avatars from '../../pages/Avatars'
import { renderWithProviders } from '../../test/utils'
import { avatarsApi, type Avatar } from '../../api/avatars'

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
})
