import { createContext, useContext, useState, useCallback, useEffect } from 'react'
import { getProjects, getProject } from '../api/projects'

const PROJECT_STORAGE_KEY = 'claudevn_active_project_id'

const ProjectContext = createContext(null)

export function ProjectProvider({ children }) {
  const [activeProject, setActiveProjectState] = useState(null)
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)

  // Fetch all projects on mount
  useEffect(() => {
    async function fetchProjects() {
      try {
        const projectList = await getProjects()
        setProjects(projectList)
        return projectList
      } catch (error) {
        console.error('Failed to fetch projects:', error)
        return []
      }
    }

    async function restoreProject() {
      setLoading(true)
      const projectList = await fetchProjects()

      // Try to restore from localStorage
      const savedProjectId = localStorage.getItem(PROJECT_STORAGE_KEY)
      if (savedProjectId) {
        // Verify the project still exists
        const exists = projectList.find(p => p.project_id === savedProjectId)
        if (exists) {
          setActiveProjectState(exists)
        } else {
          // Project no longer exists, auto-select first available
          localStorage.removeItem(PROJECT_STORAGE_KEY)
          if (projectList.length > 0) {
            setActiveProjectState(projectList[0])
            localStorage.setItem(PROJECT_STORAGE_KEY, projectList[0].project_id)
          }
        }
      } else if (projectList.length > 0) {
        // No saved project, auto-select first available
        setActiveProjectState(projectList[0])
        localStorage.setItem(PROJECT_STORAGE_KEY, projectList[0].project_id)
      }
      setLoading(false)
    }

    restoreProject()
  }, [])

  const setActiveProject = useCallback((project) => {
    setActiveProjectState(project)
    if (project) {
      localStorage.setItem(PROJECT_STORAGE_KEY, project.project_id)
    } else {
      localStorage.removeItem(PROJECT_STORAGE_KEY)
    }
  }, [])

  const clearProject = useCallback(() => {
    setActiveProjectState(null)
    localStorage.removeItem(PROJECT_STORAGE_KEY)
  }, [])

  const refreshProjects = useCallback(async () => {
    try {
      const projectList = await getProjects()
      setProjects(projectList)

      // If active project was deleted, select first available
      if (activeProject && !projectList.find(p => p.project_id === activeProject.project_id)) {
        if (projectList.length > 0) {
          setActiveProject(projectList[0])
        } else {
          clearProject()
        }
      }

      return projectList
    } catch (error) {
      console.error('Failed to refresh projects:', error)
      return projects
    }
  }, [activeProject, setActiveProject, clearProject, projects])

  const value = {
    activeProject,
    activeProjectId: activeProject?.project_id || null,
    setActiveProject,
    clearProject,
    projects,
    refreshProjects,
    loading
  }

  return (
    <ProjectContext.Provider value={value}>
      {children}
    </ProjectContext.Provider>
  )
}

export function useProjectContext() {
  const context = useContext(ProjectContext)
  if (!context) {
    throw new Error('useProjectContext must be used within a ProjectProvider')
  }
  return context
}

export default ProjectContext
