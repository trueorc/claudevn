import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import ApprovalModal from './ApprovalModal'

// Mock the projects API
vi.mock('../../api/projects', () => ({
  getProjects: vi.fn(),
}))

// Mock lucide-react icons
vi.mock('lucide-react', () => ({
  Check: () => <span data-testid="icon-check" />,
  Globe: () => <span data-testid="icon-globe" />,
  X: () => <span data-testid="icon-x" />,
}))

import { getProjects } from '../../api/projects'

const mockInstance = {
  instance_id: 'compute-001',
  name: 'Test Compute',
}

const mockProjects = [
  { project_id: 'proj-1', name: 'Project Alpha', description: 'First project' },
  { project_id: 'proj-2', name: 'Project Beta', description: 'Second project' },
]

describe('ApprovalModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getProjects.mockResolvedValue(mockProjects)
  })

  it('renders modal with instance name', async () => {
    render(
      <ApprovalModal
        instance={mockInstance}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
        loading={false}
      />
    )

    expect(screen.getByText('Approve Compute Instance')).toBeInTheDocument()
    expect(screen.getByText('Test Compute')).toBeInTheDocument()
  })

  it('fetches and displays projects', async () => {
    render(
      <ApprovalModal
        instance={mockInstance}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
        loading={false}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('Project Alpha')).toBeInTheDocument()
      expect(screen.getByText('Project Beta')).toBeInTheDocument()
    })
  })

  it('shows loading state while fetching projects', () => {
    getProjects.mockReturnValue(new Promise(() => {})) // never resolves
    render(
      <ApprovalModal
        instance={mockInstance}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
        loading={false}
      />
    )

    expect(screen.getByText('Loading projects...')).toBeInTheDocument()
  })

  it('shows error when project fetch fails', async () => {
    getProjects.mockRejectedValue(new Error('Network error'))
    render(
      <ApprovalModal
        instance={mockInstance}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
        loading={false}
      />
    )

    await waitFor(() => {
      expect(screen.getByText(/Network error/)).toBeInTheDocument()
    })
  })

  it('approve button disabled when no selection', async () => {
    render(
      <ApprovalModal
        instance={mockInstance}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
        loading={false}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('Project Alpha')).toBeInTheDocument()
    })

    const approveBtn = screen.getByRole('button', { name: /approve/i })
    expect(approveBtn).toBeDisabled()
  })

  it('sends selected project_ids on confirm', async () => {
    const onConfirm = vi.fn()
    render(
      <ApprovalModal
        instance={mockInstance}
        onConfirm={onConfirm}
        onClose={vi.fn()}
        loading={false}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('Project Alpha')).toBeInTheDocument()
    })

    // Click on Project Alpha checkbox
    const alphaCheckbox = screen.getAllByRole('checkbox')[1] // [0] is "All projects"
    fireEvent.click(alphaCheckbox)

    const approveBtn = screen.getByRole('button', { name: /approve/i })
    expect(approveBtn).not.toBeDisabled()
    fireEvent.click(approveBtn)

    expect(onConfirm).toHaveBeenCalledWith(['proj-1'])
  })

  it('sends ["*"] when all projects selected', async () => {
    const onConfirm = vi.fn()
    render(
      <ApprovalModal
        instance={mockInstance}
        onConfirm={onConfirm}
        onClose={vi.fn()}
        loading={false}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('Project Alpha')).toBeInTheDocument()
    })

    // Click "All projects" checkbox
    const allCheckbox = screen.getAllByRole('checkbox')[0]
    fireEvent.click(allCheckbox)

    const approveBtn = screen.getByRole('button', { name: /approve/i })
    fireEvent.click(approveBtn)

    expect(onConfirm).toHaveBeenCalledWith(['*'])
  })

  it('calls onClose when cancel clicked', async () => {
    const onClose = vi.fn()
    render(
      <ApprovalModal
        instance={mockInstance}
        onConfirm={vi.fn()}
        onClose={onClose}
        loading={false}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onClose).toHaveBeenCalled()
  })

  it('shows approving state when loading', async () => {
    render(
      <ApprovalModal
        instance={mockInstance}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
        loading={true}
      />
    )

    expect(screen.getByText('Approving...')).toBeInTheDocument()
  })

  it('falls back to instance_id when name is missing', async () => {
    render(
      <ApprovalModal
        instance={{ instance_id: 'compute-002' }}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
        loading={false}
      />
    )

    expect(screen.getByText('compute-002')).toBeInTheDocument()
  })
})
