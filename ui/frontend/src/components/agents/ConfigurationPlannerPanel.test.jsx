/**
 * Tests for ConfigurationPlannerPanel component.
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

jest.mock('@heroicons/react/24/outline', () => ({
  LightBulbIcon: (props) => <svg data-testid="lightbulb-icon" {...props} />,
  SparklesIcon: (props) => <svg data-testid="sparkles-icon" {...props} />,
  CheckCircleIcon: (props) => <svg data-testid="check-icon" {...props} />,
}));

jest.mock('./AgentButton', () => (props) => (
  <button data-testid="agent-button" onClick={props.onClick} disabled={props.disabled || props.loading}>
    {props.loading ? 'Loading...' : props.label || 'Plan'}
  </button>
));

jest.mock('./AgentResultsModal', () => (props) => (
  props.isOpen ? <div data-testid="results-modal">Results</div> : null
));

jest.mock('./AgentStatusBadge', () => (props) => (
  <span data-testid="status-badge">{props.status}</span>
));

const mockSpawnPlanAgent = jest.fn();
jest.mock('../../hooks/useAgents', () => () => ({
  spawnPlanAgent: mockSpawnPlanAgent,
  loading: false,
  error: null,
}));

import ConfigurationPlannerPanel from './ConfigurationPlannerPanel';

beforeEach(() => {
  mockSpawnPlanAgent.mockReset();
});

describe('ConfigurationPlannerPanel', () => {
  it('renders the panel', () => {
    render(<ConfigurationPlannerPanel />);
    expect(screen.getByTestId('agent-button')).toBeInTheDocument();
  });

  it('renders with requirements', () => {
    render(
      <ConfigurationPlannerPanel
        requirements={{ openshift_version: '4.14', region: 'us-east-1' }}
      />
    );
    expect(screen.getByTestId('agent-button')).toBeInTheDocument();
  });

  it('renders compact mode', () => {
    const { container } = render(
      <ConfigurationPlannerPanel compact={true} />
    );
    expect(container).toBeTruthy();
  });

  it('triggers plan agent on button click', () => {
    mockSpawnPlanAgent.mockResolvedValue({ plan: { steps: ['Step 1'] } });
    render(<ConfigurationPlannerPanel />);
    fireEvent.click(screen.getByTestId('agent-button'));
    expect(mockSpawnPlanAgent).toHaveBeenCalled();
  });

  it('does not show results modal initially', () => {
    render(<ConfigurationPlannerPanel />);
    expect(screen.queryByTestId('results-modal')).toBeNull();
  });
});
