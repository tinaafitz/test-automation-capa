// API Configuration
// Centralized configuration for API endpoints

const getApiBaseUrl = () => {
  // Check for environment variable first
  if (process.env.REACT_APP_API_BASE_URL) {
    return process.env.REACT_APP_API_BASE_URL;
  }

  // Development default
  if (process.env.NODE_ENV === 'development') {
    return 'http://localhost:8000';
  }

  // Production: use relative URLs (works behind nginx/reverse proxy)
  return '';
};

export const API_BASE_URL = getApiBaseUrl();

// API Endpoints
export const API_ENDPOINTS = {
  // ROSA endpoints
  ROSA_CLUSTERS: '/api/rosa/clusters',

  // Ansible endpoints
  ANSIBLE_RUN_TASK: '/api/ansible/run-task',
  ANSIBLE_RUN_PLAYBOOK: '/api/ansible/run-playbook',

  // MCE endpoints
  MCE_YAML: '/api/mce/yaml',

  // Provisioning endpoints
  PROVISIONING_GENERATE_YAML: '/api/provisioning/generate-yaml',
  PROVISIONING_APPLY_YAML: '/api/provisioning/apply-yaml',
  PROVISIONING_LOG_FORWARDING_CONFIG: '/api/provisioning/log-forwarding-config',

  // Status endpoints
  STATUS_API: '/api/status',
  STATUS_OCP: '/api/status/ocp',
  STATUS_MCE: '/api/status/mce',

  // Job endpoints
  JOBS_HISTORY: '/api/jobs',
  JOBS_STATUS: '/api/jobs/status',

  // Credentials endpoints
  CREDENTIALS_GET: '/api/credentials',

  // CAPI endpoints
  CAPI_COMPONENT_VERSIONS: '/api/capi/component-versions',

  // Version endpoints
  VERSIONS: '/api/versions',

  // Agent Dashboard endpoints
  AGENTS_DASHBOARD: '/api/agents/dashboard',
  AGENTS_REMEDIATION_METRICS: '/api/agents/remediation-metrics',
  AGENTS_CONFIDENCE: '/api/agents/confidence',
  AGENTS_KNOWLEDGE_BASE: '/api/agents/knowledge-base',
  AGENTS_ROI: '/api/agents/roi',

  // Jenkins endpoints
  JENKINS_TEST_RESULTS_TREND: '/api/jenkins/test-results-trend',
};

// Helper function to build full URL
export const buildApiUrl = (endpoint) => {
  return `${API_BASE_URL}${endpoint}`;
};

// Input validation helper
export const validateApiResponse = (response, expectedFields = []) => {
  if (!response || typeof response !== 'object') {
    throw new Error('Invalid API response format');
  }

  for (const field of expectedFields) {
    if (!(field in response)) {
      throw new Error(`Missing required field: ${field}`);
    }
  }

  return response;
};

// Safe error message extraction (prevents info leakage)
export const extractSafeErrorMessage = (error) => {
  if (process.env.NODE_ENV === 'development') {
    // Show full error in development
    return error.message || 'An error occurred';
  }

  // In production, sanitize error messages
  if (error.message && error.message.includes('fetch')) {
    return 'Network connection failed';
  }

  if (error.message && error.message.includes('JSON')) {
    return 'Invalid server response';
  }

  return 'An error occurred. Please try again.';
};
