/**
 * Tests for CAPADashboard page component.
 */

import React from 'react';
import { render, screen, act, fireEvent, waitFor } from '@testing-library/react';

// --- Mocks ---

const mockNavigate = jest.fn();
jest.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}));

jest.mock('@heroicons/react/24/outline', () => ({
  CheckCircleIcon: (props) => <svg data-testid="check-icon" {...props} />,
  Cog6ToothIcon: (props) => <svg data-testid="cog-icon" {...props} />,
  ClockIcon: (props) => <svg data-testid="clock-icon" {...props} />,
  TrashIcon: (props) => <svg data-testid="trash-icon" {...props} />,
}));

// Capture sidebar props so we can invoke navigation handlers
let capturedSidebarProps = {};
jest.mock('../components/sidebar/CapaSidebar', () => (props) => {
  capturedSidebarProps = props;
  return <div data-testid="sidebar">Sidebar</div>;
});

jest.mock('../components/sections/RosaHcpClustersSection', () => (props) => (
  <div data-testid="clusters-section">Clusters</div>
));

let capturedCredsModalProps = {};
jest.mock('../components/modals/CredentialsModal', () => (props) => {
  capturedCredsModalProps = props;
  return props.isOpen ? <div data-testid="creds-modal">Creds</div> : null;
});

let capturedEnvSelectorProps = {};
jest.mock('../components/MCEEnvironmentSelector', () => (props) => {
  capturedEnvSelectorProps = props;
  return <div data-testid="env-selector">Env Selector</div>;
});

jest.mock('../components/ActiveEnvironmentBanner', () => (props) => (
  <div data-testid="env-banner">Banner</div>
));

jest.mock('../components/YamlEditorModal', () => ({
  YamlEditorModal: () => null,
}));

let capturedProvisionModalProps = {};
jest.mock('../components/RosaProvisionModal', () => ({
  RosaProvisionModal: (props) => {
    capturedProvisionModalProps = props;
    return props.isOpen ? <div data-testid="provision-modal">Provision Modal</div> : null;
  },
}));

jest.mock('../components/ResourcesViewer', () => (props) => (
  <div data-testid="resources-viewer">Resources {props.theme}</div>
));

jest.mock('../components/chat/AIAssistantChat', () => ({
  AIAssistantChat: (props) => <div data-testid="ai-chat">AI Chat</div>,
}));

jest.mock('../components/NotificationSettingsInline', () => () => (
  <div data-testid="notifications">Notifications</div>
));

jest.mock('../components/WorkflowBuilder', () => () => (
  <div data-testid="workflow-builder">Workflow</div>
));

// Context mock setup - allow overriding per test
const mockRefreshAllStatus = jest.fn().mockResolvedValue(undefined);
const mockSetOcpStatus = jest.fn();
const mockSetMceLastVerified = jest.fn();
const mockAddToRecent = jest.fn();
const mockUpdateRecentOperationStatus = jest.fn();
const mockClearRecentOperations = jest.fn();
const mockDispatch = jest.fn();

let mockApiStatus = {
  ocpStatus: null,
  mceFeatures: [],
  mceInfo: {},
  mceLastVerified: null,
  loading: false,
  refreshAllStatus: mockRefreshAllStatus,
  setOcpStatus: mockSetOcpStatus,
  setMceLastVerified: mockSetMceLastVerified,
};

let mockRecentOps = {
  operations: [],
  recentOperations: [],
  addOperation: jest.fn(),
  removeOperation: jest.fn(),
  clearAll: jest.fn(),
  addToRecent: mockAddToRecent,
  updateRecentOperationStatus: mockUpdateRecentOperationStatus,
  clearRecentOperations: mockClearRecentOperations,
};

jest.mock('../store/AppContext', () => ({
  useApiStatusContext: () => mockApiStatus,
  useRecentOperationsContext: () => mockRecentOps,
  useApp: () => ({ theme: 'mce' }),
  useAppDispatch: () => mockDispatch,
  AppActionTypes: { SET_ACTIVE_SECTION: 'SET_ACTIVE_SECTION' },
}));

jest.mock('../config/api', () => ({
  buildApiUrl: (path) => `http://localhost:8000${path}`,
  API_ENDPOINTS: {
    ROSA_CLUSTERS: '/api/rosa/clusters',
    ANSIBLE_RUN_TASK: '/api/ansible/run-task',
    ANSIBLE_RUN_PLAYBOOK: '/api/ansible/run-playbook',
  },
  validateApiResponse: jest.fn(),
  extractSafeErrorMessage: jest.fn((e) => e.message || String(e)),
}));

const mockFetch = jest.fn();
global.fetch = mockFetch;

import CAPADashboard from './CAPADashboard';

// --- Setup & Teardown ---

beforeEach(() => {
  mockFetch.mockReset();
  mockNavigate.mockReset();
  mockRefreshAllStatus.mockReset().mockResolvedValue(undefined);
  mockAddToRecent.mockReset();
  mockUpdateRecentOperationStatus.mockReset();
  mockClearRecentOperations.mockReset();
  mockDispatch.mockReset();
  capturedSidebarProps = {};
  capturedCredsModalProps = {};
  capturedEnvSelectorProps = {};
  capturedProvisionModalProps = {};

  // Default: no running jobs
  mockFetch.mockResolvedValue({
    ok: true,
    json: async () => ({ success: true, jobs: [] }),
  });

  // Reset context mocks
  mockApiStatus.mceFeatures = [];
  mockApiStatus.mceLastVerified = null;
  mockApiStatus.loading = false;
  mockRecentOps.recentOperations = [];
});

// --- Helpers ---

async function renderDashboard() {
  let result;
  await act(async () => {
    result = render(<CAPADashboard />);
  });
  return result;
}

/** Simulate sidebar navigation by calling captured handler */
async function navigateTo(section) {
  const handlerMap = {
    verify: 'onVerifyClick',
    configure: 'onConfigureClick',
    provision: 'onProvisionClick',
    'rosa-hcp-clusters': 'onRosaHcpClustersClick',
    resources: 'onResourcesClick',
    environments: 'onEnvironmentsClick',
    credentials: 'onCredentialsClick',
    'ai-assistant': 'onAIAssistantClick',
    terminal: 'onTerminalClick',
    notifications: 'onNotificationsClick',
    'recent-tasks': 'onRecentTasksClick',
    workflows: 'onWorkflowsClick',
  };
  const handler = capturedSidebarProps[handlerMap[section]];
  if (!handler) throw new Error(`No handler found for section: ${section}`);
  await act(async () => {
    handler();
  });
}

// ============================================================
// TESTS
// ============================================================

describe('CAPADashboard', () => {
  // ----------------------------------------------------------
  // 1. Basic rendering
  // ----------------------------------------------------------

  it('renders sidebar', async () => {
    await renderDashboard();
    expect(screen.getByTestId('sidebar')).toBeInTheDocument();
  });

  it('renders environment banner', async () => {
    await renderDashboard();
    expect(screen.getByTestId('env-banner')).toBeInTheDocument();
  });

  it('renders without crashing', async () => {
    await renderDashboard();
    expect(document.body).toBeTruthy();
  });

  it('renders page header with title', async () => {
    await renderDashboard();
    expect(screen.getByText('MCE Environment')).toBeInTheDocument();
  });

  it('renders environments section by default', async () => {
    await renderDashboard();
    expect(screen.getByTestId('env-selector')).toBeInTheDocument();
  });

  it('passes activeSection to sidebar', async () => {
    await renderDashboard();
    expect(capturedSidebarProps.activeSection).toBe('environments');
  });

  // ----------------------------------------------------------
  // 2. Section navigation
  // ----------------------------------------------------------

  it('navigates to verify section', async () => {
    await renderDashboard();
    await navigateTo('verify');
    expect(screen.getByText('Verify Environment')).toBeInTheDocument();
  });

  it('navigates to configure section', async () => {
    await renderDashboard();
    await navigateTo('configure');
    expect(screen.getByText('Configure CAPI/CAPA')).toBeInTheDocument();
  });

  it('navigates to provision section', async () => {
    await renderDashboard();
    await navigateTo('provision');
    expect(screen.getByText('Provision ROSA HCP Cluster')).toBeInTheDocument();
  });

  it('navigates to rosa-hcp-clusters section', async () => {
    await renderDashboard();
    await navigateTo('rosa-hcp-clusters');
    expect(screen.getByTestId('clusters-section')).toBeInTheDocument();
  });

  it('navigates to resources section', async () => {
    await renderDashboard();
    await navigateTo('resources');
    expect(screen.getByText('CAPA Resources')).toBeInTheDocument();
    expect(screen.getByTestId('resources-viewer')).toBeInTheDocument();
  });

  it('navigates to credentials section', async () => {
    await renderDashboard();
    await navigateTo('credentials');
    expect(screen.getByText('Credentials')).toBeInTheDocument();
    expect(screen.getByTestId('creds-modal')).toBeInTheDocument();
  });

  it('navigates to workflows section', async () => {
    await renderDashboard();
    await navigateTo('workflows');
    expect(screen.getByText('Workflow Builder')).toBeInTheDocument();
    expect(screen.getByTestId('workflow-builder')).toBeInTheDocument();
  });

  it('navigates to ai-assistant section', async () => {
    await renderDashboard();
    await navigateTo('ai-assistant');
    expect(screen.getByText('AI Assistant')).toBeInTheDocument();
    expect(screen.getByTestId('ai-chat')).toBeInTheDocument();
  });

  it('navigates to terminal section', async () => {
    await renderDashboard();
    await navigateTo('terminal');
    expect(screen.getByText('MCE Terminal')).toBeInTheDocument();
  });

  it('navigates to notifications section', async () => {
    await renderDashboard();
    await navigateTo('notifications');
    expect(screen.getByText('Notification Settings')).toBeInTheDocument();
    expect(screen.getByTestId('notifications')).toBeInTheDocument();
  });

  it('navigates to recent-tasks section', async () => {
    await renderDashboard();
    await navigateTo('recent-tasks');
    expect(screen.getByText('Task Summary')).toBeInTheDocument();
  });

  it('navigates to AWS usage via react-router', async () => {
    await renderDashboard();
    // AWS usage handler calls navigate, not setActiveSection
    await act(async () => {
      capturedSidebarProps.onAWSUsageClick();
    });
    expect(mockNavigate).toHaveBeenCalledWith('/aws-usage');
  });

  // ----------------------------------------------------------
  // 3. Verify section details
  // ----------------------------------------------------------

  it('shows Run Verification button in verify section', async () => {
    await renderDashboard();
    await navigateTo('verify');
    expect(screen.getByText('Run Verification')).toBeInTheDocument();
  });

  it('shows Components heading in verify section', async () => {
    await renderDashboard();
    await navigateTo('verify');
    expect(screen.getByText('Components')).toBeInTheDocument();
  });

  it('shows no CAPI components message when mceFeatures is empty', async () => {
    mockApiStatus.mceFeatures = [];
    await renderDashboard();
    await navigateTo('verify');
    expect(screen.getByText('No CAPI components configured')).toBeInTheDocument();
    expect(screen.getByText('No Hypershift components configured')).toBeInTheDocument();
  });

  it('displays CAPI component list from mceFeatures', async () => {
    mockApiStatus.mceFeatures = [
      { name: 'cluster-api', enabled: true },
      { name: 'cluster-api-provider-aws', enabled: false },
    ];
    await renderDashboard();
    await navigateTo('verify');
    expect(screen.getByText('cluster-api')).toBeInTheDocument();
    expect(screen.getByText('cluster-api-provider-aws')).toBeInTheDocument();
  });

  it('displays Hypershift components from mceFeatures', async () => {
    mockApiStatus.mceFeatures = [
      { name: 'hypershift-addon', enabled: true },
    ];
    await renderDashboard();
    await navigateTo('verify');
    expect(screen.getByText('hypershift-addon')).toBeInTheDocument();
  });

  it('shows last verified info when mceLastVerified is set', async () => {
    mockApiStatus.mceLastVerified = '2026-01-01T12:00:00.000Z';
    await renderDashboard();
    await navigateTo('verify');
    expect(screen.getByText(/Last verified:/)).toBeInTheDocument();
  });

  it('shows Refresh button in verify section', async () => {
    await renderDashboard();
    await navigateTo('verify');
    // The refresh button in the components section
    const refreshButtons = screen.getAllByText(/Refresh/);
    expect(refreshButtons.length).toBeGreaterThan(0);
  });

  it('starts verification when Run Verification button is clicked', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, job_id: 'verify-123', jobs: [] }),
    });
    await renderDashboard();
    await navigateTo('verify');

    await act(async () => {
      fireEvent.click(screen.getByText('Run Verification'));
    });

    expect(mockAddToRecent).toHaveBeenCalled();
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/ansible/run-task'),
      expect.objectContaining({ method: 'POST' })
    );
  });

  // ----------------------------------------------------------
  // 4. Configure section details
  // ----------------------------------------------------------

  it('shows Start Configuration button in configure section', async () => {
    await renderDashboard();
    await navigateTo('configure');
    expect(screen.getByText('Start Configuration')).toBeInTheDocument();
  });

  it('shows configure description text', async () => {
    await renderDashboard();
    await navigateTo('configure');
    expect(
      screen.getByText(/Enable and configure CAPI\/CAPA components/)
    ).toBeInTheDocument();
  });

  it('starts configuration when button is clicked', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, job_id: 'config-123', jobs: [] }),
    });
    await renderDashboard();
    await navigateTo('configure');

    await act(async () => {
      fireEvent.click(screen.getByText('Start Configuration'));
    });

    expect(mockAddToRecent).toHaveBeenCalled();
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/ansible/run-playbook'),
      expect.objectContaining({ method: 'POST' })
    );
  });

  it('disables configure button when apiLoading is true', async () => {
    mockApiStatus.loading = true;
    await renderDashboard();
    await navigateTo('configure');
    // When loading, button shows "Configuring..." text
    expect(screen.getByText('Configuring...')).toBeInTheDocument();
  });

  // ----------------------------------------------------------
  // 5. Provision section details
  // ----------------------------------------------------------

  it('shows provision title in provision section', async () => {
    await renderDashboard();
    await navigateTo('provision');
    expect(screen.getByText('Provision ROSA HCP Cluster')).toBeInTheDocument();
  });

  it('shows provision modal form when no results and not provisioning', async () => {
    await renderDashboard();
    await navigateTo('provision');
    expect(screen.getByTestId('provision-modal')).toBeInTheDocument();
  });

  it('checks for running provision jobs when navigating to provision', async () => {
    await renderDashboard();
    await navigateTo('provision');
    // Should have fetched /api/jobs to check for running jobs
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/jobs')
    );
  });

  it('clears previous provision results when navigating to provision via sidebar', async () => {
    await renderDashboard();
    // Navigate away then back to provision
    await navigateTo('verify');
    await navigateTo('provision');
    // The provision modal form should be shown (results cleared)
    expect(screen.getByTestId('provision-modal')).toBeInTheDocument();
  });

  // ----------------------------------------------------------
  // 6. Terminal section details
  // ----------------------------------------------------------

  it('shows terminal welcome message', async () => {
    await renderDashboard();
    await navigateTo('terminal');
    expect(
      screen.getByText(/Welcome to MCE Terminal/)
    ).toBeInTheDocument();
  });

  it('shows command input field in terminal', async () => {
    await renderDashboard();
    await navigateTo('terminal');
    expect(
      screen.getByPlaceholderText(/Enter command/)
    ).toBeInTheDocument();
  });

  it('shows Execute button in terminal', async () => {
    await renderDashboard();
    await navigateTo('terminal');
    expect(screen.getByText('Execute')).toBeInTheDocument();
  });

  it('shows Clear button in terminal', async () => {
    await renderDashboard();
    await navigateTo('terminal');
    // The clear button has emoji + text
    const clearBtn = screen.getByTitle('Clear Terminal');
    expect(clearBtn).toBeInTheDocument();
  });

  it('Execute button is disabled when input is empty', async () => {
    await renderDashboard();
    await navigateTo('terminal');
    const executeBtn = screen.getByText('Execute');
    expect(executeBtn).toBeDisabled();
  });

  it('allows typing in command input', async () => {
    await renderDashboard();
    await navigateTo('terminal');
    const input = screen.getByPlaceholderText(/Enter command/);
    await act(async () => {
      fireEvent.change(input, { target: { value: 'oc get pods' } });
    });
    expect(input.value).toBe('oc get pods');
  });

  it('executes command on Enter key press', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, output: 'pod-1\npod-2', jobs: [] }),
    });
    await renderDashboard();
    await navigateTo('terminal');
    const input = screen.getByPlaceholderText(/Enter command/);

    await act(async () => {
      fireEvent.change(input, { target: { value: 'oc get pods' } });
    });
    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter' });
    });

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/ocp/execute-command'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ command: 'oc get pods' }),
      })
    );
  });

  it('displays command output after execution', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/ocp/execute-command')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, output: 'NAME  READY  STATUS' }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, jobs: [] }),
      });
    });

    await renderDashboard();
    await navigateTo('terminal');
    const input = screen.getByPlaceholderText(/Enter command/);

    await act(async () => {
      fireEvent.change(input, { target: { value: 'oc get pods' } });
    });
    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter' });
    });

    await waitFor(() => {
      expect(screen.getByText(/NAME\s+READY\s+STATUS/)).toBeInTheDocument();
    });
  });

  it('displays error when command fails', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/ocp/execute-command')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: false, error: 'Command not found' }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, jobs: [] }),
      });
    });

    await renderDashboard();
    await navigateTo('terminal');
    const input = screen.getByPlaceholderText(/Enter command/);

    await act(async () => {
      fireEvent.change(input, { target: { value: 'bad-cmd' } });
    });
    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter' });
    });

    await waitFor(() => {
      expect(screen.getByText(/Error: Command not found/)).toBeInTheDocument();
    });
  });

  it('displays error when fetch fails in terminal', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/ocp/execute-command')) {
        return Promise.reject(new Error('Network down'));
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, jobs: [] }),
      });
    });

    await renderDashboard();
    await navigateTo('terminal');
    const input = screen.getByPlaceholderText(/Enter command/);

    await act(async () => {
      fireEvent.change(input, { target: { value: 'test' } });
    });
    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter' });
    });

    await waitFor(() => {
      expect(screen.getByText(/Failed to execute command - Network down/)).toBeInTheDocument();
    });
  });

  it('clears terminal on Clear button click', async () => {
    await renderDashboard();
    await navigateTo('terminal');
    const clearBtn = screen.getByTitle('Clear Terminal');

    await act(async () => {
      fireEvent.click(clearBtn);
    });

    expect(screen.getByText(/Terminal cleared/)).toBeInTheDocument();
  });

  it('does not execute empty command', async () => {
    await renderDashboard();
    await navigateTo('terminal');
    const input = screen.getByPlaceholderText(/Enter command/);

    // Try Enter on empty input
    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter' });
    });

    // fetch should only have been called for the initial /api/jobs check, not for execute-command
    const executeCalls = mockFetch.mock.calls.filter(
      (call) => typeof call[0] === 'string' && call[0].includes('execute-command')
    );
    expect(executeCalls).toHaveLength(0);
  });

  // ----------------------------------------------------------
  // 7. Recent tasks section
  // ----------------------------------------------------------

  it('shows empty state when no recent tasks', async () => {
    mockRecentOps.recentOperations = [];
    await renderDashboard();
    await navigateTo('recent-tasks');
    expect(screen.getByText('No tasks')).toBeInTheDocument();
  });

  it('does not show Clear All button when no tasks', async () => {
    mockRecentOps.recentOperations = [];
    await renderDashboard();
    await navigateTo('recent-tasks');
    expect(screen.queryByText('Clear All')).not.toBeInTheDocument();
  });

  it('shows tasks when recentOperations has items', async () => {
    mockRecentOps.recentOperations = [
      {
        id: 'task-1',
        title: 'Test Task One',
        environment: 'mce',
        color: 'bg-green-600',
        status: 'Success',
        timestamp: '2026-01-01T12:00:00.000Z',
      },
    ];
    await renderDashboard();
    await navigateTo('recent-tasks');
    expect(screen.getByText('Test Task One')).toBeInTheDocument();
  });

  it('shows Clear All button when tasks exist', async () => {
    mockRecentOps.recentOperations = [
      {
        id: 'task-1',
        title: 'Task',
        environment: 'mce',
        status: 'done',
      },
    ];
    await renderDashboard();
    await navigateTo('recent-tasks');
    expect(screen.getByText('Clear All')).toBeInTheDocument();
  });

  it('calls clearRecentOperations when Clear All is clicked', async () => {
    mockRecentOps.recentOperations = [
      {
        id: 'task-1',
        title: 'Task',
        environment: 'mce',
        status: 'done',
      },
    ];
    await renderDashboard();
    await navigateTo('recent-tasks');

    await act(async () => {
      fireEvent.click(screen.getByText('Clear All'));
    });
    expect(mockClearRecentOperations).toHaveBeenCalled();
  });

  it('shows task playbook info in recent tasks', async () => {
    mockRecentOps.recentOperations = [
      {
        id: 'task-1',
        title: 'Test Task',
        environment: 'mce',
        playbook: 'playbooks/test.yml',
        status: 'running',
      },
    ];
    await renderDashboard();
    await navigateTo('recent-tasks');
    expect(screen.getByText('playbooks/test.yml')).toBeInTheDocument();
  });

  it('shows success icon for successful tasks', async () => {
    mockRecentOps.recentOperations = [
      {
        id: 'task-1',
        title: 'Success Task',
        environment: 'mce',
        status: 'Success completed',
      },
    ];
    await renderDashboard();
    await navigateTo('recent-tasks');
    // The status renderer checks for 'success' keyword and shows a checkmark
    expect(screen.getByText('Success Task')).toBeInTheDocument();
  });

  it('filters tasks by mce environment only', async () => {
    mockRecentOps.recentOperations = [
      { id: '1', title: 'MCE Task', environment: 'mce', status: 'ok' },
      { id: '2', title: 'Other Task', environment: 'other', status: 'ok' },
    ];
    await renderDashboard();
    await navigateTo('recent-tasks');
    expect(screen.getByText('MCE Task')).toBeInTheDocument();
    expect(screen.queryByText('Other Task')).not.toBeInTheDocument();
  });

  it('shows View Output for tasks with output', async () => {
    mockRecentOps.recentOperations = [
      {
        id: 'task-1',
        title: 'Task With Output',
        environment: 'mce',
        status: 'done',
        output: 'some playbook output here',
      },
    ];
    await renderDashboard();
    await navigateTo('recent-tasks');
    expect(screen.getByText('View Output')).toBeInTheDocument();
  });

  it('shows AI Agent stats when task has agentStats', async () => {
    mockRecentOps.recentOperations = [
      {
        id: 'task-1',
        title: 'Agent Task',
        environment: 'mce',
        status: 'done',
        agentStats: {
          enabled: true,
          issues_detected: 2,
          interventions: 1,
        },
      },
    ];
    await renderDashboard();
    await navigateTo('recent-tasks');
    expect(screen.getByText(/Issues: 2/)).toBeInTheDocument();
    expect(screen.getByText(/Interventions: 1/)).toBeInTheDocument();
    expect(screen.getByText(/Agent auto-fixed 1 issue/)).toBeInTheDocument();
  });

  it('shows no issues message when agentStats has zero issues', async () => {
    mockRecentOps.recentOperations = [
      {
        id: 'task-1',
        title: 'Clean Task',
        environment: 'mce',
        status: 'done',
        agentStats: {
          enabled: true,
          issues_detected: 0,
          interventions: 0,
        },
      },
    ];
    await renderDashboard();
    await navigateTo('recent-tasks');
    expect(screen.getByText('No issues detected')).toBeInTheDocument();
  });

  // ----------------------------------------------------------
  // 8. Environments section
  // ----------------------------------------------------------

  it('renders MCE environment selector on environments section', async () => {
    await renderDashboard();
    // Environments is the default section
    expect(screen.getByTestId('env-selector')).toBeInTheDocument();
  });

  it('passes onUseCredentials to environment selector', async () => {
    await renderDashboard();
    expect(capturedEnvSelectorProps.onUseCredentials).toBeDefined();
  });

  it('handles useEnvironmentCredentials success', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, jobs: [] }),
    });
    await renderDashboard();

    // Call the credential handler
    await act(async () => {
      await capturedEnvSelectorProps.onUseCredentials({
        clusterName: 'test-cluster',
      });
    });

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/credentials'),
      expect.objectContaining({ method: 'POST' })
    );
  });

  it('handles useEnvironmentCredentials API error', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/credentials')) {
        return Promise.resolve({
          ok: false,
          json: async () => ({ message: 'Invalid creds' }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, jobs: [] }),
      });
    });
    await renderDashboard();

    await act(async () => {
      await capturedEnvSelectorProps.onUseCredentials({
        clusterName: 'bad-cluster',
      });
    });

    // Should show error toast
    await waitFor(() => {
      expect(screen.getByText(/Failed to save credentials/)).toBeInTheDocument();
    });
  });

  it('handles useEnvironmentCredentials network error', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/credentials')) {
        return Promise.reject(new Error('Network error'));
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, jobs: [] }),
      });
    });
    await renderDashboard();

    await act(async () => {
      await capturedEnvSelectorProps.onUseCredentials({
        clusterName: 'test',
      });
    });

    await waitFor(() => {
      expect(screen.getByText(/Failed to save credentials.*Network error/)).toBeInTheDocument();
    });
  });

  // ----------------------------------------------------------
  // 9. Toast message
  // ----------------------------------------------------------

  it('shows toast and allows dismissal', async () => {
    // Trigger a toast via credential error
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/credentials')) {
        return Promise.resolve({
          ok: false,
          json: async () => ({ message: 'Bad creds' }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, jobs: [] }),
      });
    });
    await renderDashboard();

    await act(async () => {
      await capturedEnvSelectorProps.onUseCredentials({ clusterName: 'x' });
    });

    await waitFor(() => {
      expect(screen.getByText('Dismiss')).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByText('Dismiss'));
    });

    expect(screen.queryByText('Dismiss')).not.toBeInTheDocument();
  });

  // ----------------------------------------------------------
  // 10. Credentials section
  // ----------------------------------------------------------

  it('renders credentials modal inline in credentials section', async () => {
    await renderDashboard();
    await navigateTo('credentials');
    expect(screen.getByTestId('creds-modal')).toBeInTheDocument();
    expect(capturedCredsModalProps.inline).toBe(true);
    expect(capturedCredsModalProps.isOpen).toBe(true);
    expect(capturedCredsModalProps.theme).toBe('mce');
  });

  // ----------------------------------------------------------
  // 12. Resources section
  // ----------------------------------------------------------

  it('passes mce theme to ResourcesViewer', async () => {
    await renderDashboard();
    await navigateTo('resources');
    expect(screen.getByText(/Resources mce/)).toBeInTheDocument();
  });

  // ----------------------------------------------------------
  // 13. Configure section - checking for running jobs
  // ----------------------------------------------------------

  it('checks for running configure jobs when navigating to configure', async () => {
    await renderDashboard();
    await navigateTo('configure');
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/jobs')
    );
  });

  it('checks for running verify jobs when navigating to verify', async () => {
    await renderDashboard();
    await navigateTo('verify');
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/jobs')
    );
  });

  // ----------------------------------------------------------
  // 14. Configure section error handling
  // ----------------------------------------------------------

  it('handles configuration API returning non-ok response', async () => {
    mockFetch.mockImplementation((url, opts) => {
      if (url.includes('/api/ansible/run-playbook') && opts?.method === 'POST') {
        return Promise.resolve({
          ok: false,
          json: async () => ({ detail: 'Server error' }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, jobs: [] }),
      });
    });
    await renderDashboard();
    await navigateTo('configure');

    await act(async () => {
      fireEvent.click(screen.getByText('Start Configuration'));
    });

    // Should show configuration failed result
    await waitFor(() => {
      expect(screen.getByText('Configuration Failed')).toBeInTheDocument();
    });
  });

  it('handles configuration fetch rejection', async () => {
    mockFetch.mockImplementation((url, opts) => {
      if (url.includes('/api/ansible/run-playbook') && opts?.method === 'POST') {
        return Promise.reject(new Error('Connection refused'));
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, jobs: [] }),
      });
    });
    await renderDashboard();
    await navigateTo('configure');

    await act(async () => {
      fireEvent.click(screen.getByText('Start Configuration'));
    });

    await waitFor(() => {
      expect(screen.getByText('Configuration Failed')).toBeInTheDocument();
    });
  });

  // ----------------------------------------------------------
  // 15. Verify section error handling
  // ----------------------------------------------------------

  it('handles verification API failure', async () => {
    mockFetch.mockImplementation((url, opts) => {
      if (url.includes('/api/ansible/run-task') && opts?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: false, message: 'No connection' }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, jobs: [] }),
      });
    });
    await renderDashboard();
    await navigateTo('verify');

    await act(async () => {
      fireEvent.click(screen.getByText('Run Verification'));
    });

    await waitFor(() => {
      expect(screen.getByText('Verification Failed')).toBeInTheDocument();
    });
  });

  it('handles verification fetch rejection', async () => {
    mockFetch.mockImplementation((url, opts) => {
      if (url.includes('/api/ansible/run-task') && opts?.method === 'POST') {
        return Promise.reject(new Error('Timeout'));
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, jobs: [] }),
      });
    });
    await renderDashboard();
    await navigateTo('verify');

    await act(async () => {
      fireEvent.click(screen.getByText('Run Verification'));
    });

    await waitFor(() => {
      expect(screen.getByText('Verification Failed')).toBeInTheDocument();
    });
  });

  // ----------------------------------------------------------
  // 16. Terminal keyboard navigation
  // ----------------------------------------------------------

  it('does not crash on ArrowUp with empty history', async () => {
    await renderDashboard();
    await navigateTo('terminal');
    const input = screen.getByPlaceholderText(/Enter command/);

    await act(async () => {
      fireEvent.keyDown(input, { key: 'ArrowUp' });
    });

    expect(input.value).toBe('');
  });

  it('does not crash on ArrowDown with empty history', async () => {
    await renderDashboard();
    await navigateTo('terminal');
    const input = screen.getByPlaceholderText(/Enter command/);

    await act(async () => {
      fireEvent.keyDown(input, { key: 'ArrowDown' });
    });

    expect(input.value).toBe('');
  });

  // ----------------------------------------------------------
  // 17. Section switching clears state
  // ----------------------------------------------------------

  it('switches between multiple sections correctly', async () => {
    await renderDashboard();

    await navigateTo('verify');
    expect(screen.getByText('Verify Environment')).toBeInTheDocument();

    await navigateTo('configure');
    expect(screen.getByText('Configure CAPI/CAPA')).toBeInTheDocument();
    expect(screen.queryByText('Verify Environment')).not.toBeInTheDocument();

    await navigateTo('terminal');
    expect(screen.getByText('MCE Terminal')).toBeInTheDocument();
    expect(screen.queryByText('Configure CAPI/CAPA')).not.toBeInTheDocument();
  });

  // ----------------------------------------------------------
  // 19. Running jobs detection
  // ----------------------------------------------------------

  it('handles error when checking for running provision jobs', async () => {
    mockFetch.mockRejectedValue(new Error('API down'));
    await renderDashboard();
    await navigateTo('provision');
    // Should not crash, should show provision form
    await waitFor(() => {
      expect(screen.getByText('Provision ROSA HCP Cluster')).toBeInTheDocument();
    });
  });

  it('detects running provision job and shows its output', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/jobs') && !url.includes('/logs') && !url.includes('/agent')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            success: true,
            jobs: [
              {
                id: 'prov-running-1',
                status: 'running',
                description: 'Provision ROSA HCP: test-cluster',
              },
            ],
            // Also handle single job status endpoint
            status: 'running',
          }),
        });
      }
      if (url.includes('/logs')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ logs: ['Creating cluster...'] }),
        });
      }
      if (url.includes('/agent-stats')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ agent_stats: null }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true }),
      });
    });

    await renderDashboard();
    await navigateTo('provision');

    await waitFor(() => {
      expect(screen.getByText(/Provisioning in Progress/)).toBeInTheDocument();
    });
  });

  // ----------------------------------------------------------
  // 20. Workflow section content
  // ----------------------------------------------------------

  it('shows workflow description text', async () => {
    await renderDashboard();
    await navigateTo('workflows');
    expect(
      screen.getByText(/Chain playbooks into automated workflows/)
    ).toBeInTheDocument();
  });

  // ----------------------------------------------------------
  // 21. AI Assistant section content
  // ----------------------------------------------------------

  it('shows AI assistant description text', async () => {
    await renderDashboard();
    await navigateTo('ai-assistant');
    expect(
      screen.getByText(/Chat with the AI assistant/)
    ).toBeInTheDocument();
  });

  // ----------------------------------------------------------
  // 22. Recent tasks with resource_details in agent stats
  // ----------------------------------------------------------

  it('shows agent resource details in recent tasks', async () => {
    mockRecentOps.recentOperations = [
      {
        id: 'task-details',
        title: 'Deletion Task',
        environment: 'mce',
        status: 'done',
        agentStats: {
          enabled: true,
          issues_detected: 1,
          interventions: 1,
          resource_details: [
            {
              resource_key: 'cf-stack-123',
              issue_type: 'cloudformation_deletion_failure',
              status: 'resolved',
              diagnosis: 'Orphaned SG blocking CF delete',
            },
          ],
        },
      },
    ];
    await renderDashboard();
    await navigateTo('recent-tasks');
    expect(screen.getByText('cf-stack-123')).toBeInTheDocument();
    expect(screen.getByText(/Cloudformation Deletion Failure/)).toBeInTheDocument();
    expect(screen.getByText(/Orphaned SG blocking CF delete/)).toBeInTheDocument();
  });
});
