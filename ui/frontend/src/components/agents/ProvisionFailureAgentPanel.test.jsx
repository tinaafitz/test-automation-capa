/**
 * Tests for ProvisionFailureAgentPanel component.
 */

import React from 'react';
import { render, screen } from '@testing-library/react';

jest.mock('@heroicons/react/24/outline', () => ({
  ExclamationTriangleIcon: (props) => <svg data-testid="warning-icon" {...props} />,
  SparklesIcon: (props) => <svg data-testid="sparkles-icon" {...props} />,
  MagnifyingGlassIcon: (props) => <svg data-testid="search-icon" {...props} />,
  WrenchIcon: (props) => <svg data-testid="wrench-icon" {...props} />,
}));

jest.mock('./AgentButton', () => (props) => (
  <button data-testid={`agent-btn-${props.label || 'default'}`} onClick={props.onClick} disabled={props.disabled || props.loading}>
    {props.loading ? 'Loading...' : props.label}
  </button>
));

jest.mock('./AgentResultsModal', () => (props) => (
  props.isOpen ? <div data-testid="results-modal">Results</div> : null
));

jest.mock('./AgentStatusBadge', () => (props) => (
  <span data-testid="status-badge">{props.status}</span>
));

jest.mock('../../hooks/useAgents', () => () => ({
  spawnExploreAgent: jest.fn(),
  spawnGeneralAgent: jest.fn(),
  loading: false,
  error: null,
}));

import ProvisionFailureAgentPanel from './ProvisionFailureAgentPanel';

describe('ProvisionFailureAgentPanel', () => {
  it('renders with cluster name and error', () => {
    render(
      <ProvisionFailureAgentPanel
        clusterName="test-cluster"
        errorMessage="IAM role not found"
        autoAnalyze={false}
      />
    );
    expect(screen.getByText(/test-cluster/)).toBeInTheDocument();
    expect(screen.getByText(/IAM role not found/)).toBeInTheDocument();
  });

  it('renders provisioning label for non-delete errors', () => {
    render(
      <ProvisionFailureAgentPanel
        clusterName="my-cluster"
        errorMessage="Timeout waiting for cluster"
        autoAnalyze={false}
      />
    );
    expect(screen.getByText(/Provisioning Failed/i)).toBeInTheDocument();
  });

  it('renders deletion label for delete errors', () => {
    render(
      <ProvisionFailureAgentPanel
        clusterName="my-cluster"
        errorMessage="Cluster deletion failed"
        autoAnalyze={false}
      />
    );
    expect(screen.getByText(/Deletion Failed/i)).toBeInTheDocument();
  });

  it('renders agent action buttons', () => {
    render(
      <ProvisionFailureAgentPanel
        clusterName="test-cluster"
        errorMessage="Error"
        autoAnalyze={false}
      />
    );
    expect(screen.getByTestId('agent-btn-Investigate Failure')).toBeTruthy();
    expect(screen.getByTestId('agent-btn-Diagnose & Suggest Fixes')).toBeTruthy();
  });

  it('renders without crashing with minimal props', () => {
    render(
      <ProvisionFailureAgentPanel
        clusterName="c1"
        errorMessage="err"
        autoAnalyze={false}
      />
    );
    expect(document.body).toBeTruthy();
  });
});
