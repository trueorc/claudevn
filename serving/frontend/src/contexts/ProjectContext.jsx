import { createContext, useContext, useState, useCallback, useEffect, useMemo } from 'react'
import { getProjects, getProject } from '../api/projects'

const PROJECT_STORAGE_KEY = 'claudevn_active_project_id'
const RECENT_PROJECTS_KEY = 'claudevn_recent_project_ids'
const MAX_RECENT_PROJECTS = 3

const ProjectContext = createContext(null)

function loadRecentIds() {
  try {
    const raw = localStorage.getItem(RECENT_PROJECTS_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function saveRecentIds(ids) {
  localStorage.setItem(RECENT_PROJECTS_KEY, JSON.stringify(ids))
}

function addToRecents(projectId, currentIds) {
  const filtered = currentIds.filter(id => id !== projectId)
  return [projectId, ...filtered].slice(0, MAX_RECENT_PROJECTS)
}

export function ProjectProvider({ children }) {
  const [activeProject, setActiveProjectState] = useState(null)
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [recentIds, setRecentIds] = useState(loadRecentIds)

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
      setRecentIds(prev => {
        const updated = addToRecents(project.project_id, prev)
        saveRecentIds(updated)
        return updated
      })
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

  // Resolve recent IDs to full project objects, filtered to those that still exist
  const recentProjects = useMemo(() => {
    const projectMap = new Map(projects.map(p => [p.project_id, p]))
    return recentIds
      .map(id => projectMap.get(id))
      .filter(Boolean)
  }, [recentIds, projects])

  const value = {
    activeProject,
    activeProjectId: activeProject?.project_id || null,
    setActiveProject,
    clearProject,
    projects,
    recentProjects,
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
