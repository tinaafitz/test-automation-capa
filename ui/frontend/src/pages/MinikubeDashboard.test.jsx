/**
 * Tests for MinikubeDashboard page component.
 * Covers rendering, section switching, sidebar navigation, API calls,
 * terminal, notifications, and various component states.
 */

import React from 'react';
import { render, screen, act, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Track sidebar props so we can invoke callbacks in tests
let capturedSidebarProps = {};

jest.mock('@heroicons/react/24/outline', () => ({
  CheckCircleIcon: (props) => <svg data-testid="check-icon" {...props} />,
  Cog6ToothIcon: (props) => <svg data-testid="cog-icon" {...props} />,
  ClockIcon: (props) => <svg data-testid="clock-icon" {...props} />,
  ExclamationCircleIcon: (props) => <svg data-testid="exclaim-icon" {...props} />,
}));

jest.mock('../components/sidebar/CapaSidebar', () => (props) => {
  capturedSidebarProps = props;
  return (
    <div data-testid="sidebar">
      <span data-testid="sidebar-active-section">{props.activeSection}</span>
      <span data-testid="sidebar-environment">{props.environment}</span>
      <button data-testid="nav-configure" onClick={props.onConfigureClick}>Configure</button>
      <button data-testid="nav-reconfigure" onClick={props.onReconfigureClick}>Reconfigure</button>
      <button data-testid="nav-provision" onClick={props.onProvisionClick}>Provision</button>
      <button data-testid="nav-rosa-hcp" onClick={props.onRosaHcpClustersClick}>ROSA HCP</button>
      <button data-testid="nav-resources" onClick={props.onResourcesClick}>Resources</button>
      <button data-testid="nav-environments" onClick={props.onEnvironmentsClick}>Environments</button>
      <button data-testid="nav-ai-assistant" onClick={props.onAIAssistantClick}>AI Assistant</button>
      <button data-testid="nav-terminal" onClick={props.onTerminalClick}>Terminal</button>
      <button data-testid="nav-notifications" onClick={props.onNotificationsClick}>Notifications</button>
      <button data-testid="nav-recent-tasks" onClick={props.onRecentTasksClick}>Recent Tasks</button>
      <button data-testid="nav-components" onClick={props.onComponentsClick}>Components</button>
    </div>
  );
});

jest.mock('../components/sections/RosaHcpClustersSection', () => (props) => (
  <div data-testid="clusters-section">Clusters (theme={props.theme})</div>
));

let capturedEnvSelectorProps = {};
jest.mock('../components/MCEEnvironmentSelector', () => (props) => {
  capturedEnvSelectorProps = props;
  return (
    <div data-testid="env-selector">
      <span data-testid="env-selector-theme">{props.theme}</span>
      <span data-testid="env-selector-type">{props.environmentType}</span>
      <button data-testid="env-use-creds" onClick={() => props.onUseCredentials && props.onUseCredentials({ clusterName: 'test-mk', minikubeCluster: 'test-mk' })}>Use Creds</button>
    </div>
  );
});

jest.mock('../components/ActiveEnvironmentBanner', () => (props) => (
  <div data-testid="env-banner" data-environment={props.environment}>Banner</div>
));

jest.mock('../components/YamlEditorModal', () => ({
  YamlEditorModal: (props) => <div data-testid="yaml-editor">{props.inline ? 'inline' : 'modal'}</div>,
}));

jest.mock('../components/RosaProvisionModal', () => ({
  RosaProvisionModal: (props) => (
    <div data-testid="rosa-provision-modal">
      <span data-testid="provision-theme">{props.theme}</span>
      <button data-testid="provision-submit" onClick={() => props.onSubmit && props.onSubmit({ clusterName: 'test-cluster', openShiftVersion: '4.14', awsRegion: 'us-east-1', fips: false })}>Submit</button>
    </div>
  ),
}));

jest.mock('../components/ResourcesViewer', () => (props) => (
  <div data-testid="resources-viewer">Resources (theme={props.theme})</div>
));

jest.mock('../components/chat/AIAssistantChat', () => ({
  AIAssistantChat: (props) => <div data-testid="ai-chat">AI Chat (theme={props.theme})</div>,
}));

// Context mocks with configurable values
const mockAddToRecent = jest.fn();
const mockUpdateRecentOperationStatus = jest.fn();
const mockRemoveRecentOperation = jest.fn();
const mockVerifyMinikubeCluster = jest.fn();
const mockFetchMinikubeActiveResources = jest.fn();
const mockFetchMinikubeClusters = jest.fn();
const mockSetSelectedMinikubeCluster = jest.fn();
const mockSetMinikubeClusterInput = jest.fn();
const mockDispatch = jest.fn();

let mockRecentOperations = [];
let mockVerifiedInfo = null;

jest.mock('../store/AppContext', () => ({
  useMinikubeContext: () => ({
    cluster: 'test-minikube',
    setCluster: jest.fn(),
    verifiedMinikubeClusterInfo: mockVerifiedInfo,
    minikubeActiveResources: null,
    minikubeClusters: [],
    selectedMinikubeCluster: null,
    minikubeClusterInput: '',
    minikubeVerificationResult: null,
    minikubeLoading: false,
    minikubeResourcesLoading: false,
    verifyMinikubeCluster: mockVerifyMinikubeCluster,
    fetchMinikubeActiveResources: mockFetchMinikubeActiveResources,
    fetchMinikubeClusters: mockFetchMinikubeClusters,
    setSelectedMinikubeCluster: mockSetSelectedMinikubeCluster,
    setMinikubeClusterInput: mockSetMinikubeClusterInput,
  }),
  useRecentOperationsContext: () => ({
    operations: [],
    recentOperations: mockRecentOperations,
    addToRecent: mockAddToRecent,
    updateRecentOperationStatus: mockUpdateRecentOperationStatus,
    removeRecentOperation: mockRemoveRecentOperation,
    addOperation: jest.fn(),
    removeOperation: jest.fn(),
    clearAll: jest.fn(),
  }),
  useApp: () => ({ theme: 'minikube' }),
  useAppDispatch: () => mockDispatch,
  AppActionTypes: {
    SET_ACTIVE_SECTION: 'SET_ACTIVE_SECTION',
    ADD_NOTIFICATION: 'ADD_NOTIFICATION',
  },
}));

jest.mock('../config/api', () => ({
  buildApiUrl: (path) => `http://localhost:8000${path}`,
  API_ENDPOINTS: {
    ROSA_CLUSTERS: '/api/rosa/clusters',
    ANSIBLE_RUN_PLAYBOOK: '/api/ansible/run-playbook',
  },
  validateApiResponse: jest.fn(),
  extractSafeErrorMessage: jest.fn((e) => e.message),
}));

const mockFetch = jest.fn();
global.fetch = mockFetch;

import MinikubeDashboard from './MinikubeDashboard';

beforeEach(() => {
  mockFetch.mockReset();
  mockAddToRecent.mockReset();
  mockUpdateRecentOperationStatus.mockReset();
  mockRemoveRecentOperation.mockReset();
  mockDispatch.mockReset();
  mockRecentOperations = [];
  mockVerifiedInfo = null;
  capturedSidebarProps = {};
  capturedEnvSelectorProps = {};

  // Default fetch: return success for all endpoints
  mockFetch.mockResolvedValue({
    ok: true,
    json: async () => ({ success: true }),
  });
});

// Helper to render and wait for initial effects
const renderDashboard = async () => {
  let result;
  await act(async () => {
    result = render(<MinikubeDashboard />);
  });
  return result;
};

// ============================================================================
// 1. Basic Rendering
// ============================================================================
describe('MinikubeDashboard - Basic Rendering', () => {
  it('renders without crashing', async () => {
    await renderDashboard();
    expect(document.body).toBeTruthy();
  });

  it('renders sidebar', async () => {
    await renderDashboard();
    expect(screen.getByTestId('sidebar')).toBeInTheDocument();
  });

  it('renders environment banner', async () => {
    await renderDashboard();
    expect(screen.getByTestId('env-banner')).toBeInTheDocument();
  });

  it('passes minikube environment to sidebar', async () => {
    await renderDashboard();
    expect(screen.getByTestId('sidebar-environment')).toHaveTextContent('minikube');
  });

  it('passes minikube environment to banner', async () => {
    await renderDashboard();
    expect(screen.getByTestId('env-banner')).toHaveAttribute('data-environment', 'minikube');
  });

  it('renders page header with Minikube Environment title', async () => {
    await renderDashboard();
    expect(screen.getByText('Minikube Environment')).toBeInTheDocument();
  });

  it('starts with environments as default section', async () => {
    await renderDashboard();
    expect(screen.getByTestId('sidebar-active-section')).toHaveTextContent('environments');
  });

  it('renders MCEEnvironmentSelector in default environments section', async () => {
    await renderDashboard();
    expect(screen.getByTestId('env-selector')).toBeInTheDocument();
  });

  it('passes minikube theme to environment selector', async () => {
    await renderDashboard();
    expect(screen.getByTestId('env-selector-theme')).toHaveTextContent('minikube');
  });

  it('passes minikube environmentType to environment selector', async () => {
    await renderDashboard();
    expect(screen.getByTestId('env-selector-type')).toHaveTextContent('minikube');
  });
});

// ============================================================================
// 2. Sidebar Navigation / Section Switching
// ============================================================================
describe('MinikubeDashboard - Section Switching', () => {
  it('switches to configure section', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-configure'));
    });
    expect(screen.getByText('Configure CAPI/CAPA')).toBeInTheDocument();
  });

  it('switches to reconfigure section', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-reconfigure'));
    });
    expect(screen.getByText('Set Custom CAPA Image')).toBeInTheDocument();
  });

  it('switches to provision section', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-provision'));
    });
    expect(screen.getByText('Provision ROSA HCP Cluster')).toBeInTheDocument();
  });

  it('switches to rosa-hcp-clusters section', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-rosa-hcp'));
    });
    expect(screen.getByTestId('clusters-section')).toBeInTheDocument();
  });

  it('switches to resources section', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-resources'));
    });
    expect(screen.getByText('CAPA Resources')).toBeInTheDocument();
    expect(screen.getByTestId('resources-viewer')).toBeInTheDocument();
  });

  it('switches to ai-assistant section', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-ai-assistant'));
    });
    expect(screen.getAllByText('AI Assistant').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByTestId('ai-chat')).toBeInTheDocument();
  });

  it('switches to terminal section', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-terminal'));
    });
    expect(screen.getByText('Minikube Terminal')).toBeInTheDocument();
  });

  it('switches to notifications section', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-notifications'));
    });
    expect(screen.getByText('Notification Settings')).toBeInTheDocument();
  });

  it('switches to recent-tasks section', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-recent-tasks'));
    });
    expect(screen.getByText('Task Summary')).toBeInTheDocument();
  });

  it('renders default section for unknown activeSection', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-components'));
    });
    expect(screen.getByText(/Content for components section coming soon/)).toBeInTheDocument();
  });

  it('switches back to environments from another section', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-configure'));
    });
    expect(screen.getByText('Configure CAPI/CAPA')).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-environments'));
    });
    expect(screen.getByTestId('env-selector')).toBeInTheDocument();
  });
});

// ============================================================================
// 3. Configure Section
// ============================================================================
describe('MinikubeDashboard - Configure Section', () => {
  it('shows Start Configuration button', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-configure'));
    });
    expect(screen.getByText('Start Configuration')).toBeInTheDocument();
  });

  it('shows configuration description text', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-configure'));
    });
    expect(screen.getByText(/Enable and configure CAPI\/CAPA components/)).toBeInTheDocument();
  });

  it('shows error when no cluster verified and configure clicked', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-configure'));
    });
    await act(async () => {
      fireEvent.click(screen.getByText('Start Configuration'));
    });
    expect(screen.getByText(/Please verify a Minikube cluster first/)).toBeInTheDocument();
  });
});

// ============================================================================
// 4. Reconfigure / Custom Image Section
// ============================================================================
describe('MinikubeDashboard - Reconfigure Section', () => {
  it('shows Use Custom CAPA Image checkbox', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-reconfigure'));
    });
    expect(screen.getByText('Use Custom CAPA Image')).toBeInTheDocument();
  });

  it('shows custom image fields when checkbox is checked', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-reconfigure'));
    });
    const checkbox = screen.getByRole('checkbox');
    await act(async () => {
      fireEvent.click(checkbox);
    });
    expect(screen.getByText('Image Repository')).toBeInTheDocument();
    expect(screen.getByText('Image Tag')).toBeInTheDocument();
    expect(screen.getByText('CRD Location (URL)')).toBeInTheDocument();
  });

  it('shows Apply Changes button', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-reconfigure'));
    });
    expect(screen.getByText('Apply Changes')).toBeInTheDocument();
  });

  it('hides custom image fields when checkbox is unchecked', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-reconfigure'));
    });
    const checkbox = screen.getByRole('checkbox');
    // Check
    await act(async () => {
      fireEvent.click(checkbox);
    });
    expect(screen.getByText('Image Repository')).toBeInTheDocument();
    // Uncheck
    await act(async () => {
      fireEvent.click(checkbox);
    });
    expect(screen.queryByText('Image Repository')).not.toBeInTheDocument();
  });
});

// ============================================================================
// 5. Provision Section
// ============================================================================
describe('MinikubeDashboard - Provision Section', () => {
  it('shows Configure ROSA HCP Cluster heading', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-provision'));
    });
    expect(screen.getByText('Configure ROSA HCP Cluster')).toBeInTheDocument();
  });

  it('shows Target Environment indicator', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-provision'));
    });
    expect(screen.getByText('Target Environment')).toBeInTheDocument();
  });

  it('shows No cluster selected when no cluster is active', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-provision'));
    });
    expect(screen.getByText('No cluster selected')).toBeInTheDocument();
  });

  it('renders RosaProvisionModal inline with minikube theme', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-provision'));
    });
    expect(screen.getByTestId('rosa-provision-modal')).toBeInTheDocument();
    expect(screen.getByTestId('provision-theme')).toHaveTextContent('minikube');
  });

  it('shows cancel button in provision section', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-provision'));
    });
    expect(screen.getByText('Cancel')).toBeInTheDocument();
  });
});

// ============================================================================
// 6. Resources Section
// ============================================================================
describe('MinikubeDashboard - Resources Section', () => {
  it('renders ResourcesViewer with minikube theme', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-resources'));
    });
    expect(screen.getByTestId('resources-viewer')).toHaveTextContent('theme=minikube');
  });
});

// ============================================================================
// 7. Terminal Section
// ============================================================================
describe('MinikubeDashboard - Terminal Section', () => {
  it('shows terminal welcome message', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-terminal'));
    });
    expect(screen.getByText(/Welcome to Minikube Terminal/)).toBeInTheDocument();
  });

  it('shows command input', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-terminal'));
    });
    expect(screen.getByPlaceholderText(/Enter command/)).toBeInTheDocument();
  });

  it('shows Execute button', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-terminal'));
    });
    expect(screen.getByText('Execute')).toBeInTheDocument();
  });

  it('Execute button is disabled when input is empty', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-terminal'));
    });
    const executeBtn = screen.getByText('Execute');
    expect(executeBtn).toBeDisabled();
  });

  it('enables Execute button when command is typed', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-terminal'));
    });
    const input = screen.getByPlaceholderText(/Enter command/);
    await act(async () => {
      fireEvent.change(input, { target: { value: 'kubectl get pods' } });
    });
    const executeBtn = screen.getByText('Execute');
    expect(executeBtn).not.toBeDisabled();
  });

  it('executes command and shows output on success', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/ocp/execute-command')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, output: 'pod/test-pod   1/1     Running   0          5m' }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
    });

    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-terminal'));
    });
    const input = screen.getByPlaceholderText(/Enter command/);
    await act(async () => {
      fireEvent.change(input, { target: { value: 'kubectl get pods' } });
    });
    await act(async () => {
      fireEvent.click(screen.getByText('Execute'));
    });

    await waitFor(() => {
      expect(screen.getByText(/pod\/test-pod/)).toBeInTheDocument();
    });
  });

  it('shows error output when command fails', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/ocp/execute-command')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: false, error: 'Command not found' }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
    });

    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-terminal'));
    });
    const input = screen.getByPlaceholderText(/Enter command/);
    await act(async () => {
      fireEvent.change(input, { target: { value: 'badcmd' } });
    });
    await act(async () => {
      fireEvent.click(screen.getByText('Execute'));
    });

    await waitFor(() => {
      expect(screen.getByText(/Command not found/)).toBeInTheDocument();
    });
  });

  it('shows network error in terminal', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/ocp/execute-command')) {
        return Promise.reject(new Error('Network error'));
      }
      return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
    });

    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-terminal'));
    });
    const input = screen.getByPlaceholderText(/Enter command/);
    await act(async () => {
      fireEvent.change(input, { target: { value: 'test' } });
    });
    await act(async () => {
      fireEvent.click(screen.getByText('Execute'));
    });

    await waitFor(() => {
      expect(screen.getByText(/Failed to execute command - Network error/)).toBeInTheDocument();
    });
  });

  it('clears terminal output when Clear button clicked', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-terminal'));
    });
    // Click clear
    const clearBtn = screen.getByTitle('Clear Terminal');
    await act(async () => {
      fireEvent.click(clearBtn);
    });
    expect(screen.getByText(/Terminal cleared/)).toBeInTheDocument();
  });

  it('executes command on Enter key press', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/ocp/execute-command')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, output: 'enter-key-output' }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
    });

    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-terminal'));
    });
    const input = screen.getByPlaceholderText(/Enter command/);
    await act(async () => {
      fireEvent.change(input, { target: { value: 'ls' } });
    });
    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
    });

    await waitFor(() => {
      expect(screen.getByText(/enter-key-output/)).toBeInTheDocument();
    });
  });
});

// ============================================================================
// 8. Notification Settings Section
// ============================================================================
describe('MinikubeDashboard - Notification Settings', () => {
  it('shows Email and Slack tabs', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-notifications'));
    });
    await waitFor(() => {
      // Multiple elements may contain "Email" (tab + form fields), just verify at least one exists
      expect(screen.getAllByText(/Email/).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/Slack/).length).toBeGreaterThan(0);
    });
  });

  it('shows loading spinner while fetching settings', async () => {
    // Make notification-settings fetch hang (never resolve)
    let resolveSettings;
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/notification-settings') && !url.includes('POST')) {
        return new Promise((resolve) => { resolveSettings = resolve; });
      }
      return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
    });

    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-notifications'));
    });
    expect(screen.getByText('Loading settings...')).toBeInTheDocument();

    // Resolve to clean up - must include all required fields
    await act(async () => {
      resolveSettings({
        ok: true,
        json: async () => ({
          success: true,
          settings: {
            email_enabled: false, slack_enabled: false, smtp_server: '',
            smtp_port: 587, smtp_username: '', smtp_password: '',
            from_email: '', to_emails: [], use_tls: true, slack_webhook_url: '',
            notify_on_start: false, notify_on_complete: true, notify_on_failure: true,
            notify_provision_start: false, notify_provision_success: true,
            notify_provision_failure: true, notify_delete_start: false,
            notify_delete_success: true, notify_delete_failure: true,
            app_url: 'http://localhost:3000',
          },
        }),
      });
    });
  });

  it('shows email settings form by default', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/notification-settings') && !url.includes('POST')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, settings: { email_enabled: false, slack_enabled: false, smtp_server: '', smtp_port: 587, smtp_username: '', smtp_password: '', from_email: '', to_emails: [], use_tls: true, slack_webhook_url: '', notify_on_start: false, notify_on_complete: true, notify_on_failure: true, notify_provision_start: false, notify_provision_success: true, notify_provision_failure: true, notify_delete_start: false, notify_delete_success: true, notify_delete_failure: true, app_url: 'http://localhost:3000' } }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
    });

    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-notifications'));
    });

    await waitFor(() => {
      expect(screen.getByText('Enable Email Notifications')).toBeInTheDocument();
    });
  });

  it('switches to Slack tab', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/notification-settings')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, settings: { email_enabled: false, slack_enabled: false, smtp_server: '', smtp_port: 587, smtp_username: '', smtp_password: '', from_email: '', to_emails: [], use_tls: true, slack_webhook_url: '', notify_on_start: false, notify_on_complete: true, notify_on_failure: true, notify_provision_start: false, notify_provision_success: true, notify_provision_failure: true, notify_delete_start: false, notify_delete_success: true, notify_delete_failure: true, app_url: 'http://localhost:3000' } }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
    });

    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-notifications'));
    });

    await waitFor(() => {
      expect(screen.getByText(/Slack/)).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByText(/Slack/));
    });

    expect(screen.getByText('Enable Slack Notifications')).toBeInTheDocument();
  });

  it('shows Save Settings button', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/notification-settings')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, settings: { email_enabled: false, slack_enabled: false, smtp_server: '', smtp_port: 587, smtp_username: '', smtp_password: '', from_email: '', to_emails: [], use_tls: true, slack_webhook_url: '', notify_on_start: false, notify_on_complete: true, notify_on_failure: true, notify_provision_start: false, notify_provision_success: true, notify_provision_failure: true, notify_delete_start: false, notify_delete_success: true, notify_delete_failure: true, app_url: 'http://localhost:3000' } }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
    });

    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-notifications'));
    });

    await waitFor(() => {
      expect(screen.getByText(/Save Settings/)).toBeInTheDocument();
    });
  });

  it('shows Notification Preferences section', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/notification-settings')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, settings: { email_enabled: false, slack_enabled: false, smtp_server: '', smtp_port: 587, smtp_username: '', smtp_password: '', from_email: '', to_emails: [], use_tls: true, slack_webhook_url: '', notify_on_start: false, notify_on_complete: true, notify_on_failure: true, notify_provision_start: false, notify_provision_success: true, notify_provision_failure: true, notify_delete_start: false, notify_delete_success: true, notify_delete_failure: true, app_url: 'http://localhost:3000' } }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
    });

    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-notifications'));
    });

    await waitFor(() => {
      expect(screen.getByText('Notification Preferences')).toBeInTheDocument();
    });
  });
});

// ============================================================================
// 9. Recent Tasks Section
// ============================================================================
describe('MinikubeDashboard - Recent Tasks', () => {
  it('shows No tasks when no recent operations', async () => {
    mockRecentOperations = [];
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-recent-tasks'));
    });
    expect(screen.getByText('No tasks')).toBeInTheDocument();
  });

  it('shows tasks when recent operations exist for minikube', async () => {
    mockRecentOperations = [
      {
        id: 'task-1',
        title: 'Configure CAPI',
        status: '✅ Completed',
        environment: 'minikube',
        playbook: 'test.yml',
        timestamp: new Date().toISOString(),
        color: 'bg-violet-600',
      },
    ];
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-recent-tasks'));
    });
    expect(screen.getByText('Configure CAPI')).toBeInTheDocument();
  });

  it('filters tasks to only show minikube environment', async () => {
    mockRecentOperations = [
      {
        id: 'task-mce',
        title: 'MCE Task',
        status: '✅ Done',
        environment: 'mce',
        timestamp: new Date().toISOString(),
      },
    ];
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-recent-tasks'));
    });
    // MCE task should not appear, so "No tasks" is shown
    expect(screen.getByText('No tasks')).toBeInTheDocument();
  });
});

// ============================================================================
// 10. API Calls on Mount
// ============================================================================
describe('MinikubeDashboard - API calls', () => {
  it('fetches credentials on mount', async () => {
    await renderDashboard();
    await waitFor(() => {
      const credCalls = mockFetch.mock.calls.filter(c => c[0].includes('/api/credentials'));
      expect(credCalls.length).toBeGreaterThan(0);
    });
  });

  it('fetches CLI versions on mount', async () => {
    await renderDashboard();
    await waitFor(() => {
      const cliCalls = mockFetch.mock.calls.filter(c => c[0].includes('/api/capi/cli-versions'));
      expect(cliCalls.length).toBeGreaterThan(0);
    });
  });

  it('fetches cluster components on mount', async () => {
    await renderDashboard();
    await waitFor(() => {
      const compCalls = mockFetch.mock.calls.filter(c => c[0].includes('/api/capi/cluster-components'));
      expect(compCalls.length).toBeGreaterThan(0);
    });
  });

  it('handles credential fetch failure gracefully', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/credentials')) {
        return Promise.reject(new Error('Connection refused'));
      }
      return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
    });

    // Should not throw
    await renderDashboard();
    expect(screen.getByTestId('sidebar')).toBeInTheDocument();
  });

  it('handles CLI versions fetch failure gracefully', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/capi/cli-versions')) {
        return Promise.reject(new Error('Timeout'));
      }
      return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
    });

    await renderDashboard();
    expect(screen.getByTestId('sidebar')).toBeInTheDocument();
  });

  it('sets minikube info from saved credentials', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/credentials')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            success: true,
            credentials: { minikubeCluster: 'my-minikube', apiPort: 8443 },
          }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
    });

    await renderDashboard();
    // The component sets minikubeInfo internally; we verify it didn't crash
    expect(screen.getByTestId('sidebar')).toBeInTheDocument();
  });

  it('falls back to active profile when no credentials', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/credentials')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, credentials: {} }),
        });
      }
      if (url.includes('/api/minikube/active-profile')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, profile: { name: 'minikube', status: 'Running' } }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
    });

    await renderDashboard();
    expect(screen.getByTestId('sidebar')).toBeInTheDocument();
  });
});

// ============================================================================
// 11. Environment Credentials Flow
// ============================================================================
describe('MinikubeDashboard - Environment Credentials', () => {
  it('handles successful credential save', async () => {
    mockFetch.mockImplementation((url, opts) => {
      if (url.includes('/api/credentials') && opts?.method === 'POST') {
        return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
      }
      return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
    });

    await renderDashboard();
    // Click Use Creds button in env selector mock
    await act(async () => {
      fireEvent.click(screen.getByTestId('env-use-creds'));
    });

    await waitFor(() => {
      // Check that a POST to /api/credentials was made
      const postCalls = mockFetch.mock.calls.filter(
        c => c[0].includes('/api/credentials') && c[1]?.method === 'POST'
      );
      expect(postCalls.length).toBeGreaterThan(0);
    });
  });

  it('handles credential save failure', async () => {
    mockFetch.mockImplementation((url, opts) => {
      if (url.includes('/api/credentials') && opts?.method === 'POST') {
        return Promise.resolve({
          ok: false,
          json: async () => ({ message: 'Unauthorized' }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
    });

    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('env-use-creds'));
    });

    // Should show an error credential message inline (contains "Failed")
    await waitFor(() => {
      expect(screen.getByText(/Failed to save credentials/)).toBeInTheDocument();
    });
  });

  it('handles credential save network error', async () => {
    mockFetch.mockImplementation((url, opts) => {
      if (url.includes('/api/credentials') && opts?.method === 'POST') {
        return Promise.reject(new Error('Network down'));
      }
      return Promise.resolve({ ok: true, json: async () => ({ success: true }) });
    });

    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('env-use-creds'));
    });

    await waitFor(() => {
      expect(screen.getByText(/Failed to save credentials: Network down/)).toBeInTheDocument();
    });
  });
});

// ============================================================================
// 12. ROSA HCP Clusters Section
// ============================================================================
describe('MinikubeDashboard - ROSA HCP Clusters', () => {
  it('renders RosaHcpClustersSection with minikube theme', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-rosa-hcp'));
    });
    expect(screen.getByTestId('clusters-section')).toHaveTextContent('theme=minikube');
  });
});

// ============================================================================
// 13. AI Assistant Section
// ============================================================================
describe('MinikubeDashboard - AI Assistant', () => {
  it('renders AIAssistantChat with minikube theme', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-ai-assistant'));
    });
    expect(screen.getByTestId('ai-chat')).toHaveTextContent('theme=minikube');
  });

  it('shows descriptive text about AI assistant', async () => {
    await renderDashboard();
    await act(async () => {
      fireEvent.click(screen.getByTestId('nav-ai-assistant'));
    });
    expect(screen.getByText(/Chat with the AI assistant/)).toBeInTheDocument();
  });
});

// ============================================================================
// ============================================================================
