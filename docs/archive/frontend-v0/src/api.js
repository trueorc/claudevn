/**
 * API client for Serving Component
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8002/api/v1';

/**
 * Compute Registry API
 */

export const getComputeInstances = async (status = null) => {
  const url = new URL(`${API_BASE_URL}/compute`);
  if (status) {
    url.searchParams.append('status', status);
  }
  
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch instances: ${response.statusText}`);
  }
  return response.json();
};

export const getComputeInstance = async (instanceId) => {
  const response = await fetch(`${API_BASE_URL}/compute/${instanceId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch instance: ${response.statusText}`);
  }
  return response.json();
};

export const registerComputeInstance = async (data) => {
  const response = await fetch(`${API_BASE_URL}/compute/register`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to register instance');
  }
  return response.json();
};

export const deregisterComputeInstance = async (instanceId) => {
  const response = await fetch(`${API_BASE_URL}/compute/${instanceId}`, {
    method: 'DELETE',
  });
  
  if (!response.ok) {
    throw new Error(`Failed to deregister instance: ${response.statusText}`);
  }
  return response.json();
};

export const updateComputeInstance = async (instanceId, data) => {
  const response = await fetch(`${API_BASE_URL}/compute/${instanceId}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });
  
  if (!response.ok) {
    throw new Error(`Failed to update instance: ${response.statusText}`);
  }
  return response.json();
};

export const sendHeartbeat = async (instanceId, metadata = null) => {
  const response = await fetch(`${API_BASE_URL}/compute/${instanceId}/health`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(metadata || {}),
  });
  
  if (!response.ok) {
    throw new Error(`Failed to send heartbeat: ${response.statusText}`);
  }
  return response.json();
};

export const getAggregatedCapabilities = async () => {
  const response = await fetch(`${API_BASE_URL}/compute/capabilities/aggregated`);
  if (!response.ok) {
    throw new Error(`Failed to fetch capabilities: ${response.statusText}`);
  }
  return response.json();
};

export const findInstancesByAgent = async (agentId, onlineOnly = true) => {
  const url = new URL(`${API_BASE_URL}/compute/search/by-agent/${agentId}`);
  url.searchParams.append('online_only', onlineOnly);
  
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to search instances: ${response.statusText}`);
  }
  return response.json();
};

export const findInstancesByTool = async (toolId, onlineOnly = true) => {
  const url = new URL(`${API_BASE_URL}/compute/search/by-tool/${toolId}`);
  url.searchParams.append('online_only', onlineOnly);
  
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to search instances: ${response.statusText}`);
  }
  return response.json();
};

export const getRegistryStats = async () => {
  const response = await fetch(`${API_BASE_URL}/compute/stats/summary`);
  if (!response.ok) {
    throw new Error(`Failed to fetch stats: ${response.statusText}`);
  }
  return response.json();
};

/**
 * Marketplace Registry API
 */

export const getMarketplaces = async (status = null) => {
  const url = new URL(`${API_BASE_URL}/marketplaces`);
  if (status) {
    url.searchParams.append('status', status);
  }
  
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch marketplaces: ${response.statusText}`);
  }
  return response.json();
};

export const getMarketplace = async (marketplaceId) => {
  const response = await fetch(`${API_BASE_URL}/marketplaces/${marketplaceId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch marketplace: ${response.statusText}`);
  }
  return response.json();
};

export const getMarketplaceStats = async () => {
  const response = await fetch(`${API_BASE_URL}/marketplaces/stats/summary`);
  if (!response.ok) {
    throw new Error(`Failed to fetch marketplace stats: ${response.statusText}`);
  }
  return response.json();
};

export const getAggregatedMarketplaceStats = async () => {
  const response = await fetch(`${API_BASE_URL}/marketplaces/stats/aggregated`);
  if (!response.ok) {
    throw new Error(`Failed to fetch aggregated marketplace stats: ${response.statusText}`);
  }
  return response.json();
};

/**
 * Logs API
 */

export const getComputeLogs = async (instanceId, lines = 100) => {
  const response = await fetch(`${API_BASE_URL}/logs/compute/${instanceId}?lines=${lines}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch compute logs: ${response.statusText}`);
  }
  return response.json();
};

export const getMarketplaceLogs = async (marketplaceId, lines = 100) => {
  const response = await fetch(`${API_BASE_URL}/logs/marketplace/${marketplaceId}?lines=${lines}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch marketplace logs: ${response.statusText}`);
  }
  return response.json();
};

/**
 * Sessions API
 */

export const getSessions = async (status = null) => {
  const url = new URL(`${API_BASE_URL}/sessions`);
  if (status) {
    url.searchParams.append('status', status);
  }
  
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch sessions: ${response.statusText}`);
  }
  return response.json();
};

export const getSession = async (sessionId) => {
  const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch session: ${response.statusText}`);
  }
  return response.json();
};

export const createSession = async (data) => {
  const response = await fetch(`${API_BASE_URL}/sessions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });
  
  if (!response.ok) {
    throw new Error(`Failed to create session: ${response.statusText}`);
  }
  return response.json();
};

export const createFacilitatedSession = async (businessGoal, userId = null, context = null) => {
  const response = await fetch(`${API_BASE_URL}/sessions/create-facilitated`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ business_goal: businessGoal, user_id: userId, context }),
  });
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || 'Failed to create facilitated session');
  }
  return response.json();
};

/**
 * Process Maps API
 */

export const createProcessMap = async (sessionId, businessGoal) => {
  const response = await fetch(`${API_BASE_URL}/process-maps/sessions/${sessionId}/map`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ session_id: sessionId, business_goal: businessGoal }),
  });
  
  if (!response.ok) {
    throw new Error(`Failed to create process map: ${response.statusText}`);
  }
  return response.json();
};

export const getProcessMap = async (sessionId) => {
  const response = await fetch(`${API_BASE_URL}/process-maps/sessions/${sessionId}/map`);
  if (!response.ok) {
    throw new Error(`Failed to fetch process map: ${response.statusText}`);
  }
  return response.json();
};

export const getProcessMapHistory = async (sessionId) => {
  const response = await fetch(`${API_BASE_URL}/process-maps/sessions/${sessionId}/map/history`);
  if (!response.ok) {
    throw new Error(`Failed to fetch process map history: ${response.statusText}`);
  }
  return response.json();
};

export const getProcessMapProgress = async (sessionId) => {
  const response = await fetch(`${API_BASE_URL}/process-maps/sessions/${sessionId}/map/progress`);
  if (!response.ok) {
    throw new Error(`Failed to fetch process map progress: ${response.statusText}`);
  }
  return response.json();
};

export const addActivity = async (sessionId, goal, description = null, dependsOn = []) => {
  const response = await fetch(`${API_BASE_URL}/process-maps/sessions/${sessionId}/map/activities`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ goal, description, depends_on: dependsOn }),
  });
  
  if (!response.ok) {
    throw new Error(`Failed to add activity: ${response.statusText}`);
  }
  return response.json();
};

export const getActivity = async (sessionId, activityId) => {
  const response = await fetch(`${API_BASE_URL}/process-maps/sessions/${sessionId}/activities/${activityId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch activity: ${response.statusText}`);
  }
  return response.json();
};

export const updateActivityStatus = async (sessionId, activityId, status) => {
  const response = await fetch(`${API_BASE_URL}/process-maps/sessions/${sessionId}/activities/${activityId}/status`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ status }),
  });
  
  if (!response.ok) {
    throw new Error(`Failed to update activity status: ${response.statusText}`);
  }
  return response.json();
};

export const assignParticipant = async (sessionId, activityId, agentId, agentName, role, capabilities, reason) => {
  const response = await fetch(`${API_BASE_URL}/process-maps/sessions/${sessionId}/activities/${activityId}/participants`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ agent_id: agentId, agent_name: agentName, role, capabilities, reason }),
  });
  
  if (!response.ok) {
    throw new Error(`Failed to assign participant: ${response.statusText}`);
  }
  return response.json();
};

export const selectParticipants = async (sessionId, activityId, capabilities = [], domain = null) => {
  const response = await fetch(`${API_BASE_URL}/process-maps/sessions/${sessionId}/activities/${activityId}/select-participants`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ capabilities, domain }),
  });
  
  if (!response.ok) {
    throw new Error(`Failed to select participants: ${response.statusText}`);
  }
  return response.json();
};

export const startFacilitation = async (sessionId, activityId, initialPrompt = "Let's begin working on this activity") => {
  const response = await fetch(`${API_BASE_URL}/process-maps/sessions/${sessionId}/activities/${activityId}/start-facilitation`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ initial_prompt: initialPrompt }),
  });
  
  if (!response.ok) {
    throw new Error(`Failed to start facilitation: ${response.statusText}`);
  }
  return response.json();
};

export const getActivityExchanges = async (sessionId, activityId) => {
  const response = await fetch(`${API_BASE_URL}/process-maps/sessions/${sessionId}/activities/${activityId}/exchanges`);
  if (!response.ok) {
    throw new Error(`Failed to fetch exchanges: ${response.statusText}`);
  }
  return response.json();
};

export const checkConsistency = async (sessionId) => {
  const response = await fetch(`${API_BASE_URL}/process-maps/sessions/${sessionId}/check-consistency`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(`Failed to check consistency: ${response.statusText}`);
  }
  return response.json();
};

export const generateProgressReport = async (sessionId) => {
  const response = await fetch(`${API_BASE_URL}/process-maps/sessions/${sessionId}/generate-progress-report`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(`Failed to generate progress report: ${response.statusText}`);
  }
  return response.json();
};

export const synthesizeResults = async (sessionId) => {
  const response = await fetch(`${API_BASE_URL}/process-maps/sessions/${sessionId}/synthesize-results`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(`Failed to synthesize results: ${response.statusText}`);
  }
  return response.json();
};

export const getCoordinatingEvents = async (sessionId, eventType = null) => {
  const url = eventType 
    ? `${API_BASE_URL}/process-maps/sessions/${sessionId}/coordinating-events?event_type=${eventType}`
    : `${API_BASE_URL}/process-maps/sessions/${sessionId}/coordinating-events`;
  
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch coordinating events: ${response.statusText}`);
  }
  return response.json();
};

/**
 * Task Submission API
 */

export const submitTask = async (taskRequest) => {
  const response = await fetch(`${API_BASE_URL}/tasks/submit`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(taskRequest),
  });
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || 'Failed to submit task');
  }
  return response.json();
};

export const getTaskStatus = async (taskId, computeInstanceId) => {
  const response = await fetch(`${API_BASE_URL}/tasks/${taskId}?compute_instance_id=${computeInstanceId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch task status: ${response.statusText}`);
  }
  return response.json();
};

export const runDemoBusinessProcess = async () => {
  const response = await fetch(`${API_BASE_URL}/tasks/demo/business-process`, {
    method: 'POST',
  });
  
  if (!response.ok) {
    throw new Error(`Failed to run demo business process: ${response.statusText}`);
  }
  return response.json();
};

/**
 * Health API
 */

export const getSystemHealth = async () => {
  const response = await fetch(`${API_BASE_URL}/health`);
  if (!response.ok) {
    throw new Error(`Failed to fetch health: ${response.statusText}`);
  }
  return response.json();
};

