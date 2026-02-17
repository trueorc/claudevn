import { request } from './index.js'

/**
 * List all available work profile presets.
 * @returns {Promise<Array>} List of PresetSummary objects
 */
export async function listPresets() {
  return request('/profiles/presets')
}

/**
 * Activate a work profile preset for a project.
 * @param {string} presetName - Preset to activate (build, harden, test, invest)
 * @param {string} projectId - Project to activate for
 * @returns {Promise<Object>} ActivatePresetResponse
 */
export async function activatePreset(presetName, projectId) {
  return request(`/profiles/presets/${presetName}/activate?project_id=${encodeURIComponent(projectId)}`, {
    method: 'POST',
  })
}

/**
 * Get the currently active preset for a project.
 * @param {string} projectId
 * @returns {Promise<Object>} ActivePresetResponse
 */
export async function getActivePreset(projectId) {
  return request(`/profiles/presets/active?project_id=${encodeURIComponent(projectId)}`)
}
