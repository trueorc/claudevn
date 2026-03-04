import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Sidebar from './Sidebar.jsx'

vi.mock('../../hooks/useSystemHealth', () => ({
  default: vi.fn(() => ({
    health: null,
    overallStatus: 'unknown',
    loading: true,
  })),
}))

vi.mock('../../contexts/ProjectContext', () => ({
  useProjectContext: vi.fn(() => ({
    activeProject: null,
    projects: [],
    setActiveProject: vi.fn(),
    loading: false,
  })),
}))

import useSystemHealth from '../../hooks/useSystemHealth'

function renderSidebar() {
  return render(
    <MemoryRouter>
      <Sidebar />
    </MemoryRouter>
  )
}

describe('Sidebar', () => {
  describe('version display', () => {
    it('shows version when health data includes version', () => {
      useSystemHealth.mockReturnValue({
        health: { version: '0.3.0', status: 'healthy' },
        overallStatus: 'healthy',
        loading: false,
      })

      renderSidebar()
      expect(screen.getByText('v0.3.0')).toBeInTheDocument()
    })

    it('does not show version when health data is null', () => {
      useSystemHealth.mockReturnValue({
        health: null,
        overallStatus: 'unknown',
        loading: true,
      })

      renderSidebar()
      expect(screen.queryByText(/^v\d/)).not.toBeInTheDocument()
    })

    it('does not show version when health has no version field', () => {
      useSystemHealth.mockReturnValue({
        health: { status: 'healthy' },
        overallStatus: 'healthy',
        loading: false,
      })

      renderSidebar()
      expect(screen.queryByText(/^v\d/)).not.toBeInTheDocument()
    })

    it('renders version with correct CSS class', () => {
      useSystemHealth.mockReturnValue({
        health: { version: '1.0.0', status: 'healthy' },
        overallStatus: 'healthy',
        loading: false,
      })

      renderSidebar()
      const versionEl = screen.getByText('v1.0.0')
      expect(versionEl).toHaveClass('sidebar-brand-version')
    })
  })

  describe('brand', () => {
    it('renders the ClaudeVN brand text', () => {
      useSystemHealth.mockReturnValue({
        health: null,
        overallStatus: 'unknown',
        loading: true,
      })

      renderSidebar()
      expect(screen.getByText('ClaudeVN')).toBeInTheDocument()
    })

    it('renders the logo image', () => {
      useSystemHealth.mockReturnValue({
        health: null,
        overallStatus: 'unknown',
        loading: true,
      })

      renderSidebar()
      expect(screen.getByAltText('ClaudeVN')).toBeInTheDocument()
    })
  })
})
