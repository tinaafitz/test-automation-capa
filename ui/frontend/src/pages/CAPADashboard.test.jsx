/**
 * Tests for CAPADashboard page component.
 */

import React from 'react';
import { render, screen, act } from '@testing-library/react';

jest.mock('react-router-dom', () => ({
  useNavigate: () => jest.fn(),
}));

jest.mock('@heroicons/react/24/outline', () => ({
  CheckCircleIcon: (props) => <svg data-testid="check-icon" {...props} />,
  Cog6ToothIcon: (props) => <svg data-testid="cog-icon" {...props} />,
  ClockIcon: (props) => <svg data-testid="clock-icon" {...props} />,
  TrashIcon: (props) => <svg data-testid="trash-icon" {...props} />,
}));

jest.mock('../components/sidebar/CapaSidebar', () => (props) => (
  <div data-testid="sidebar">Sidebar</div>
));

jest.mock('../components/sections/RosaHcpClustersSection', () => (props) => (
  <div data-testid="clusters-section">Clusters</div>
));

jest.mock('../components/modals/CredentialsModal', () => (props) => (
  props.isOpen ? <div data-testid="creds-modal">Creds</div> : null
));

jest.mock('../components/MCEEnvironmentSelector', () => (props) => (
  <div data-testid="env-selector">Env Selector</div>
));

jest.mock('../components/ActiveEnvironmentBanner', () => (props) => (
  <div data-testid="env-banner">Banner</div>
));

jest.mock('../components/YamlEditorModal', () => ({
  YamlEditorModal: () => null,
}));

jest.mock('../components/RosaProvisionModal', () => ({
  RosaProvisionModal: () => null,
}));

jest.mock('../components/sections/TestSuiteDashboard', () => () => (
  <div data-testid="test-suite-dashboard">Test Suite</div>
));

jest.mock('../components/sections/TestSuiteSection', () => () => (
  <div data-testid="test-suite-section">Test Section</div>
));

jest.mock('../components/ResourcesViewer', () => () => (
  <div data-testid="resources-viewer">Resources</div>
));

jest.mock('../components/chat/AIAssistantChat', () => ({
  AIAssistantChat: () => <div data-testid="ai-chat">AI Chat</div>,
}));

jest.mock('../components/NotificationSettingsInline', () => () => (
  <div data-testid="notifications">Notifications</div>
));

jest.mock('../components/WorkflowBuilder', () => () => (
  <div data-testid="workflow-builder">Workflow</div>
));

jest.mock('../store/AppContext', () => ({
  useApiStatusContext: () => ({ connected: true }),
  useRecentOperationsContext: () => ({
    operations: [],
    addOperation: jest.fn(),
    removeOperation: jest.fn(),
    clearAll: jest.fn(),
  }),
  useApp: () => ({ theme: 'mce' }),
  useAppDispatch: () => jest.fn(),
  AppActionTypes: { SET_ACTIVE_SECTION: 'SET_ACTIVE_SECTION' },
}));

jest.mock('../config/api', () => ({
  buildApiUrl: (path) => `http://localhost:8000${path}`,
  API_ENDPOINTS: { ROSA_CLUSTERS: '/api/rosa/clusters' },
  validateApiResponse: jest.fn(),
  extractSafeErrorMessage: jest.fn((e) => e.message),
}));

const mockFetch = jest.fn();
global.fetch = mockFetch;

import CAPADashboard from './CAPADashboard';

beforeEach(() => {
  mockFetch.mockReset();
  mockFetch.mockResolvedValue({
    ok: true,
    json: async () => ({ success: true }),
  });
});

describe('CAPADashboard', () => {
  it('renders sidebar', async () => {
    await act(async () => {
      render(<CAPADashboard />);
    });
    expect(screen.getByTestId('sidebar')).toBeInTheDocument();
  });

  it('renders environment banner', async () => {
    await act(async () => {
      render(<CAPADashboard />);
    });
    expect(screen.getByTestId('env-banner')).toBeInTheDocument();
  });

  it('renders without crashing', async () => {
    await act(async () => {
      render(<CAPADashboard />);
    });
    expect(document.body).toBeTruthy();
  });
});
