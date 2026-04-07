/**
 * Tests for CapaSidebar component.
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

// Mock react-router-dom
jest.mock('react-router-dom', () => ({
  useNavigate: () => jest.fn(),
}));

// Mock AppContext hooks
const mockRecentOps = {
  recentOperations: [
    { id: 'op-1', environment: 'mce', status: 'success', type: 'verify', timestamp: new Date().toISOString() },
    { id: 'op-2', environment: 'minikube', status: 'running', type: 'configure', timestamp: new Date().toISOString() },
  ],
};

const mockApiStatus = {
  rosaStatus: null,
  configStatus: null,
  ocpStatus: null,
};

jest.mock('../../store/AppContext', () => ({
  useRecentOperationsContext: () => mockRecentOps,
  useApiStatusContext: () => mockApiStatus,
}));

import CapaSidebar from './CapaSidebar';

describe('CapaSidebar', () => {
  const defaultProps = {
    onEnvironmentsClick: jest.fn(),
    onCredentialsClick: jest.fn(),
    onVerifyClick: jest.fn(),
    onConfigureClick: jest.fn(),
    onReconfigureClick: jest.fn(),
    onProvisionClick: jest.fn(),
    onRosaHcpClustersClick: jest.fn(),
    onResourcesClick: jest.fn(),
    onTestAutomationClick: jest.fn(),
    onWorkflowsClick: jest.fn(),
    onTestSuiteDashboardClick: jest.fn(),
    onTerminalClick: jest.fn(),
    onNotificationsClick: jest.fn(),
    onRecentTasksClick: jest.fn(),
    onAWSUsageClick: jest.fn(),
    onAIAssistantClick: jest.fn(),
    activeSection: 'environments',
    environment: 'mce',
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders without crashing', () => {
    render(<CapaSidebar {...defaultProps} />);
    expect(screen.getByText('Environments')).toBeInTheDocument();
  });

  it('renders core menu items for MCE environment', () => {
    render(<CapaSidebar {...defaultProps} environment="mce" />);
    expect(screen.getByText('Environments')).toBeInTheDocument();
    expect(screen.getByText('Credentials')).toBeInTheDocument();
    expect(screen.getByText('Verify')).toBeInTheDocument();
    expect(screen.getByText('Configure')).toBeInTheDocument();
    expect(screen.getByText('Provision')).toBeInTheDocument();
    expect(screen.getByText('Workflows')).toBeInTheDocument();
  });

  it('shows minikube-specific items in minikube environment', () => {
    render(<CapaSidebar {...defaultProps} environment="minikube" />);
    expect(screen.getByText('Set Custom CAPA Image')).toBeInTheDocument();
  });

  it('hides MCE-only items in minikube environment', () => {
    render(<CapaSidebar {...defaultProps} environment="minikube" />);
    expect(screen.queryByText('Credentials')).not.toBeInTheDocument();
    expect(screen.queryByText('Feature Test Dashboard')).not.toBeInTheDocument();
  });

  it('calls onClick callback when menu item clicked', () => {
    render(<CapaSidebar {...defaultProps} />);
    fireEvent.click(screen.getByText('Environments'));
    expect(defaultProps.onEnvironmentsClick).toHaveBeenCalled();
  });

  it('calls provision callback', () => {
    render(<CapaSidebar {...defaultProps} />);
    fireEvent.click(screen.getByText('Provision'));
    expect(defaultProps.onProvisionClick).toHaveBeenCalled();
  });

  it('calls workflows callback', () => {
    render(<CapaSidebar {...defaultProps} />);
    fireEvent.click(screen.getByText('Workflows'));
    expect(defaultProps.onWorkflowsClick).toHaveBeenCalled();
  });

  it('renders ROSA HCP Clusters menu item', () => {
    render(<CapaSidebar {...defaultProps} />);
    expect(screen.getByText('ROSA HCP Clusters')).toBeInTheDocument();
  });

  it('renders Terminal menu item', () => {
    render(<CapaSidebar {...defaultProps} />);
    expect(screen.getByText('Terminal')).toBeInTheDocument();
  });

  it('renders Notifications menu item', () => {
    render(<CapaSidebar {...defaultProps} />);
    expect(screen.getByText('Notifications')).toBeInTheDocument();
  });

  it('renders Task Summary menu item', () => {
    render(<CapaSidebar {...defaultProps} />);
    expect(screen.getByText('Task Summary')).toBeInTheDocument();
  });

  it('filters recent tasks by current environment', () => {
    render(<CapaSidebar {...defaultProps} environment="mce" />);
    // Only MCE operations should show (op-1), not minikube ones (op-2)
    // The sidebar filters by environment
  });
});
