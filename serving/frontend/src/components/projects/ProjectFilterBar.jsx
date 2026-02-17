import { Search, X } from 'lucide-react'
import './ProjectFilterBar.css'

const STATUS_OPTIONS = [
  { value: 'all', label: 'All statuses' },
  { value: 'active', label: 'Active' },
  { value: 'archived', label: 'Archived' },
  { value: 'suspended', label: 'Suspended' }
]

const SORT_OPTIONS = [
  { value: 'name_asc', label: 'Name (A-Z)' },
  { value: 'name_desc', label: 'Name (Z-A)' },
  { value: 'created_desc', label: 'Created (newest)' },
  { value: 'created_asc', label: 'Created (oldest)' },
  { value: 'updated_desc', label: 'Last activity' }
]

function ProjectFilterBar({ filters, onChange }) {
  const handleSearchChange = (e) => {
    onChange({ ...filters, search: e.target.value })
  }

  const handleStatusChange = (e) => {
    onChange({ ...filters, status: e.target.value })
  }

  const handleSortChange = (e) => {
    onChange({ ...filters, sort: e.target.value })
  }

  const handleClearFilters = () => {
    onChange({ search: '', status: 'all', sort: 'name_asc' })
  }

  const hasActiveFilters = filters.search ||
    (filters.status && filters.status !== 'all') ||
    (filters.sort && filters.sort !== 'name_asc')

  return (
    <div className="project-filter-bar">
      <div className="filter-search">
        <Search size={14} className="search-icon" />
        <input
          type="text"
          placeholder="Search projects..."
          value={filters.search || ''}
          onChange={handleSearchChange}
          className="filter-search-input"
        />
      </div>

      <select
        value={filters.status || 'all'}
        onChange={handleStatusChange}
        className="filter-select"
      >
        {STATUS_OPTIONS.map(opt => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>

      <select
        value={filters.sort || 'name_asc'}
        onChange={handleSortChange}
        className="filter-select"
      >
        {SORT_OPTIONS.map(opt => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>

      {hasActiveFilters && (
        <button
          onClick={handleClearFilters}
          className="filter-clear-btn"
          title="Clear filters"
        >
          <X size={14} />
          Clear
        </button>
      )}
    </div>
  )
}

export default ProjectFilterBar
