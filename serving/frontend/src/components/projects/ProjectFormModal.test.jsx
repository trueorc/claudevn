import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import ProjectFormModal from './ProjectFormModal'

// Mock the API module
vi.mock('../../api/projects', () => ({
  createProject: vi.fn(),
  updateProject: vi.fn(),
  addRepoToProject: vi.fn(),
  createInternalRepo: vi.fn(),
}))

import { createProject, updateProject, addRepoToProject, createInternalRepo } from '../../api/projects'

describe('ProjectFormModal', () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    onSuccess: vi.fn(),
    project: null,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    createProject.mockResolvedValue({ project_id: 'proj_test123' })
    updateProject.mockResolvedValue({})
    addRepoToProject.mockResolvedValue({})
    createInternalRepo.mockResolvedValue({})
  })

  it('renders the new project form', () => {
    render(<ProjectFormModal {...defaultProps} />)

    expect(screen.getByText('New Project')).toBeDefined()
    expect(screen.getByLabelText('Name')).toBeDefined()
    expect(screen.getByLabelText('Description')).toBeDefined()
    expect(screen.getByText('Create Project')).toBeDefined()
  })

  it('renders edit form when project is provided', () => {
    const project = {
      project_id: 'proj_1',
      name: 'My Project',
      description: 'A description',
      icon: null,
      icon_color: null,
      labels: [],
    }

    render(<ProjectFormModal {...defaultProps} project={project} />)

    expect(screen.getByText('Edit Project')).toBeDefined()
    expect(screen.getByText('Save Changes')).toBeDefined()
  })

  it('shows repositories section toggle in create mode', () => {
    render(<ProjectFormModal {...defaultProps} />)

    expect(screen.getByText('Repositories')).toBeDefined()
  })

  it('hides repositories section in edit mode', () => {
    const project = {
      project_id: 'proj_1',
      name: 'My Project',
      description: '',
      icon: null,
      icon_color: null,
      labels: [],
    }

    render(<ProjectFormModal {...defaultProps} project={project} />)

    expect(screen.queryByText('Repositories')).toBeNull()
  })

  it('toggles repo section open/closed', () => {
    render(<ProjectFormModal {...defaultProps} />)

    const toggle = screen.getByText('Repositories')
    fireEvent.click(toggle)

    expect(screen.getByText('Create New')).toBeDefined()
    expect(screen.getByText('Link External')).toBeDefined()
    expect(screen.getByText('Add to list')).toBeDefined()

    // Close it
    fireEvent.click(toggle)
    expect(screen.queryByText('Create New')).toBeNull()
  })

  it('adds an internal repo to pending list', () => {
    render(<ProjectFormModal {...defaultProps} />)

    // Open repo section
    fireEvent.click(screen.getByText('Repositories'))

    // Fill in repo name
    const repoNameInput = screen.getByPlaceholderText('Repository name')
    fireEvent.change(repoNameInput, { target: { value: 'my-repo' } })

    // Add to list
    fireEvent.click(screen.getByText('Add to list'))

    // Should show in pending list
    expect(screen.getByText('my-repo')).toBeDefined()
    expect(screen.getByText(/Internal/)).toBeDefined()
  })

  it('adds an external repo to pending list', () => {
    render(<ProjectFormModal {...defaultProps} />)

    // Open repo section
    fireEvent.click(screen.getByText('Repositories'))

    // Switch to link mode
    fireEvent.click(screen.getByText('Link External'))

    // Fill in repo details
    fireEvent.change(screen.getByPlaceholderText('Repository name'), {
      target: { value: 'external-repo' },
    })
    fireEvent.change(screen.getByPlaceholderText('https://github.com/org/repo.git'), {
      target: { value: 'https://github.com/org/repo.git' },
    })

    // Add to list
    fireEvent.click(screen.getByText('Add to list'))

    expect(screen.getByText('external-repo')).toBeDefined()
    expect(screen.getByText(/External · main/)).toBeDefined()
  })

  it('validates repo name is required', () => {
    render(<ProjectFormModal {...defaultProps} />)

    fireEvent.click(screen.getByText('Repositories'))
    fireEvent.click(screen.getByText('Add to list'))

    expect(screen.getByText('Repository name is required')).toBeDefined()
  })

  it('validates repo URL is required for link mode', () => {
    render(<ProjectFormModal {...defaultProps} />)

    fireEvent.click(screen.getByText('Repositories'))
    fireEvent.click(screen.getByText('Link External'))

    fireEvent.change(screen.getByPlaceholderText('Repository name'), {
      target: { value: 'some-repo' },
    })
    fireEvent.click(screen.getByText('Add to list'))

    expect(screen.getByText('Repository URL is required')).toBeDefined()
  })

  it('removes a pending repo', () => {
    render(<ProjectFormModal {...defaultProps} />)

    fireEvent.click(screen.getByText('Repositories'))

    // Add a repo
    fireEvent.change(screen.getByPlaceholderText('Repository name'), {
      target: { value: 'my-repo' },
    })
    fireEvent.click(screen.getByText('Add to list'))

    expect(screen.getByText('my-repo')).toBeDefined()

    // Remove it
    fireEvent.click(screen.getByTitle('Remove'))

    expect(screen.queryByText('my-repo')).toBeNull()
  })

  it('shows badge count for pending repos', () => {
    render(<ProjectFormModal {...defaultProps} />)

    fireEvent.click(screen.getByText('Repositories'))

    // Add two repos
    fireEvent.change(screen.getByPlaceholderText('Repository name'), {
      target: { value: 'repo-1' },
    })
    fireEvent.click(screen.getByText('Add to list'))

    fireEvent.change(screen.getByPlaceholderText('Repository name'), {
      target: { value: 'repo-2' },
    })
    fireEvent.click(screen.getByText('Add to list'))

    // Badge should show "2"
    expect(screen.getByText('2')).toBeDefined()
  })

  it('creates project without repos when none are added', async () => {
    render(<ProjectFormModal {...defaultProps} />)

    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Test Project' },
    })

    fireEvent.click(screen.getByText('Create Project'))

    await waitFor(() => {
      expect(createProject).toHaveBeenCalledWith({
        name: 'Test Project',
        description: '',
        icon: null,
        icon_color: null,
        labels: [],
      })
    })

    expect(createInternalRepo).not.toHaveBeenCalled()
    expect(addRepoToProject).not.toHaveBeenCalled()
    expect(defaultProps.onSuccess).toHaveBeenCalled()
    expect(defaultProps.onClose).toHaveBeenCalled()
  })

  it('creates project with internal repo', async () => {
    render(<ProjectFormModal {...defaultProps} />)

    // Set project name
    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Test Project' },
    })

    // Open repo section and add a repo
    fireEvent.click(screen.getByText('Repositories'))
    fireEvent.change(screen.getByPlaceholderText('Repository name'), {
      target: { value: 'my-repo' },
    })
    fireEvent.click(screen.getByText('Add to list'))

    // Submit
    fireEvent.click(screen.getByText('Create Project'))

    await waitFor(() => {
      expect(createProject).toHaveBeenCalled()
      expect(createInternalRepo).toHaveBeenCalledWith('proj_test123', {
        name: 'my-repo',
        default_branch: 'main',
      })
    })
  })

  it('creates project with external repo', async () => {
    render(<ProjectFormModal {...defaultProps} />)

    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Test Project' },
    })

    fireEvent.click(screen.getByText('Repositories'))
    fireEvent.click(screen.getByText('Link External'))

    fireEvent.change(screen.getByPlaceholderText('Repository name'), {
      target: { value: 'ext-repo' },
    })
    fireEvent.change(screen.getByPlaceholderText('https://github.com/org/repo.git'), {
      target: { value: 'https://github.com/test/repo.git' },
    })

    fireEvent.click(screen.getByText('Add to list'))
    fireEvent.click(screen.getByText('Create Project'))

    await waitFor(() => {
      expect(createProject).toHaveBeenCalled()
      expect(addRepoToProject).toHaveBeenCalledWith('proj_test123', {
        name: 'ext-repo',
        url: 'https://github.com/test/repo.git',
        default_branch: 'main',
      })
    })
  })

  it('shows error on project creation failure', async () => {
    createProject.mockRejectedValue(new Error('Server error'))

    render(<ProjectFormModal {...defaultProps} />)

    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Test Project' },
    })
    fireEvent.click(screen.getByText('Create Project'))

    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeDefined()
    })
  })

  it('shows error when project name is empty', () => {
    render(<ProjectFormModal {...defaultProps} />)

    fireEvent.click(screen.getByText('Create Project'))

    expect(screen.getByText('Project name is required')).toBeDefined()
  })

  it('resets form when modal reopens', () => {
    const { rerender } = render(<ProjectFormModal {...defaultProps} isOpen={false} />)

    // Open modal
    rerender(<ProjectFormModal {...defaultProps} isOpen={true} />)

    expect(screen.getByLabelText('Name').value).toBe('')
    expect(screen.queryByText('Repositories')).toBeDefined()
  })
})
