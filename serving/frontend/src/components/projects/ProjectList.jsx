import { FolderGit2 } from 'lucide-react'
import useProjects from '../../hooks/useProjects'
import ProjectCard from './ProjectCard'
import Spinner from '../common/Spinner'
import EmptyState from '../common/EmptyState'
import './Projects.css'

function ProjectList({ onSelect, onEdit, onDelete, onSelectActive, activeProjectId, filters = {} }) {
  const { projects, loading, error } = useProjects({ filters })

  const hasFilters = filters.search ||
    (filters.status && filters.status !== 'all') ||
    (filters.sort && filters.sort !== 'name_asc')

  if (loading) {
    return (
      <div className="loading-state">
        <Spinner />
      </div>
    )
  }

  if (error) {
    return (
      <EmptyState
        icon={FolderGit2}
        title="Failed to load projects"
        description={error}
      />
    )
  }

  if (projects.length === 0) {
    return (
      <EmptyState
        icon={FolderGit2}
        title={hasFilters ? "No projects match filters" : "No projects"}
        description={hasFilters
          ? "Try adjusting your search or filter criteria"
          : "Create a project to organize your repositories and work"
        }
      />
    )
  }

  return (
    <div className="project-grid">
      {projects.map(project => (
        <ProjectCard
          key={project.project_id}
          project={project}
          onClick={() => onSelect?.(project)}
          onEdit={onEdit}
          onDelete={onDelete}
          onSelectActive={onSelectActive}
          isActive={activeProjectId === project.project_id}
        />
      ))}
    </div>
  )
}

export default ProjectList
