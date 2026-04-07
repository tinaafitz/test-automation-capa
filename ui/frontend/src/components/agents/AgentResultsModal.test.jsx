/**
 * Tests for AgentResultsModal component.
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

jest.mock('@heroicons/react/24/outline', () => ({
  XMarkIcon: (props) => <svg data-testid="x-icon" {...props} />,
  CheckCircleIcon: (props) => <svg data-testid="check-icon" {...props} />,
  ExclamationTriangleIcon: (props) => <svg data-testid="warning-icon" {...props} />,
  InformationCircleIcon: (props) => <svg data-testid="info-icon" {...props} />,
  SparklesIcon: (props) => <svg data-testid="sparkles-icon" {...props} />,
}));

import AgentResultsModal from './AgentResultsModal';

describe('AgentResultsModal', () => {
  it('renders nothing when not open', () => {
    const { container } = render(<AgentResultsModal isOpen={false} onClose={() => {}} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders modal when open', () => {
    render(<AgentResultsModal isOpen={true} onClose={() => {}} />);
    expect(screen.getByText(/Codebase Analysis Results/)).toBeInTheDocument();
  });

  it('shows explore agent title', () => {
    render(<AgentResultsModal isOpen={true} onClose={() => {}} agentType="explore" />);
    expect(screen.getByText(/Codebase Analysis Results/)).toBeInTheDocument();
  });

  it('shows plan agent title', () => {
    render(<AgentResultsModal isOpen={true} onClose={() => {}} agentType="plan" />);
    expect(screen.getByText(/Configuration Plan/)).toBeInTheDocument();
  });

  it('shows general agent title', () => {
    render(<AgentResultsModal isOpen={true} onClose={() => {}} agentType="general" />);
    expect(screen.getByText(/Troubleshooting Results/)).toBeInTheDocument();
  });

  it('renders findings', () => {
    render(
      <AgentResultsModal
        isOpen={true}
        onClose={() => {}}
        results={{ findings: ['Found issue in VPC config', 'Missing IAM role'] }}
      />
    );
    expect(screen.getByText('Found issue in VPC config')).toBeInTheDocument();
    expect(screen.getByText('Missing IAM role')).toBeInTheDocument();
  });

  it('renders recommendations', () => {
    render(
      <AgentResultsModal
        isOpen={true}
        onClose={() => {}}
        results={{ recommendations: ['Update IAM policy'] }}
      />
    );
    expect(screen.getByText('Update IAM policy')).toBeInTheDocument();
  });

  it('calls onClose when close button clicked', () => {
    const onClose = jest.fn();
    render(<AgentResultsModal isOpen={true} onClose={onClose} />);
    const closeButtons = screen.getAllByTestId('x-icon');
    fireEvent.click(closeButtons[0].closest('button'));
    expect(onClose).toHaveBeenCalled();
  });

  it('renders with empty results', () => {
    render(<AgentResultsModal isOpen={true} onClose={() => {}} results={{}} />);
    expect(document.body).toBeTruthy();
  });

  it('renders diagnosis and root cause', () => {
    render(
      <AgentResultsModal
        isOpen={true}
        onClose={() => {}}
        agentType="general"
        results={{
          diagnosis: 'VPC endpoint deletion blocked',
          root_cause: 'Security groups still attached',
        }}
      />
    );
    expect(screen.getByText('VPC endpoint deletion blocked')).toBeInTheDocument();
    expect(screen.getByText('Security groups still attached')).toBeInTheDocument();
  });
});
