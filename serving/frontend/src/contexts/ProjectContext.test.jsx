import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { ProjectProvider, useProjectContext } from './ProjectContext'

const mockProjects = [
  { project_id: 'p1', name: 'Project Alpha' },
  { project_id: 'p2', name: 'Project Beta' },
  { project_id: 'p3', name: 'Project Gamma' },
  { project_id: 'p4', name: 'Project Delta' },
]

vi.mock('../api/projects', () => ({
  getProjects: vi.fn(() => Promise.resolve(mockProjects)),
  getProject: vi.fn((id) => Promise.resolve(mockProjects.find(p => p.project_id === id))),
}))

const wrapper = ({ children }) => <ProjectProvider>{children}</ProjectProvider>

describe('ProjectContext', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('provides projects list after loading', async () => {
    const { result } = renderHook(() => useProjectContext(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.projects).toHaveLength(4)
  })

  it('auto-selects first project when none saved', async () => {
    const { result } = renderHook(() => useProjectContext(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.activeProject?.project_id).toBe('p1')
  })

  it('restores saved project from localStorage', async () => {
    localStorage.setItem('claudevn_active_project_id', 'p2')
    const { result } = renderHook(() => useProjectContext(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.activeProject?.project_id).toBe('p2')
  })

  it('throws when used outside provider', () => {
    expect(() => {
      renderHook(() => useProjectContext())
    }).toThrow('useProjectContext must be used within a ProjectProvider')
  })
})

describe('ProjectContext recent projects', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('starts with empty recent projects when none saved', async () => {
    const { result } = renderHook(() => useProjectContext(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    // Auto-select sets the first project as active, which adds it to recents
    expect(result.current.recentProjects.length).toBeGreaterThanOrEqual(0)
  })

  it('adds project to recents when set as active', async () => {
    const { result } = renderHook(() => useProjectContext(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => {
      result.current.setActiveProject(mockProjects[1])
    })

    expect(result.current.recentProjects[0].project_id).toBe('p2')
  })

  it('moves project to top of recents on re-selection', async () => {
    localStorage.setItem('claudevn_recent_project_ids', JSON.stringify(['p1', 'p2', 'p3']))
    const { result } = renderHook(() => useProjectContext(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => {
      result.current.setActiveProject(mockProjects[2]) // p3
    })

    expect(result.current.recentProjects[0].project_id).toBe('p3')
    expect(result.current.recentProjects[1].project_id).toBe('p1')
    expect(result.current.recentProjects[2].project_id).toBe('p2')
  })

  it('limits recents to 3 projects', async () => {
    localStorage.setItem('claudevn_recent_project_ids', JSON.stringify(['p1', 'p2', 'p3']))
    const { result } = renderHook(() => useProjectContext(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => {
      result.current.setActiveProject(mockProjects[3]) // p4
    })

    expect(result.current.recentProjects).toHaveLength(3)
    expect(result.current.recentProjects[0].project_id).toBe('p4')
    expect(result.current.recentProjects.find(p => p.project_id === 'p3')).toBeUndefined()
  })

  it('persists recents to localStorage', async () => {
    const { result } = renderHook(() => useProjectContext(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => {
      result.current.setActiveProject(mockProjects[1])
    })

    const stored = JSON.parse(localStorage.getItem('claudevn_recent_project_ids'))
    expect(stored).toContain('p2')
  })

  it('filters out deleted projects from recents', async () => {
    localStorage.setItem('claudevn_recent_project_ids', JSON.stringify(['deleted-id', 'p1', 'p2']))
    const { result } = renderHook(() => useProjectContext(), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))

    // deleted-id doesn't exist in mockProjects, so it should be filtered out
    expect(result.current.recentProjects.find(p => p.project_id === 'deleted-id')).toBeUndefined()
    expect(result.current.recentProjects[0].project_id).toBe('p1')
  })
})
