/**
 * Tests for AgentButton component.
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import AgentButton from './AgentButton';

describe('AgentButton', () => {
  it('renders with default label', () => {
    render(<AgentButton onClick={() => {}} />);
    expect(screen.getByText('Ask AI Agent')).toBeInTheDocument();
  });

  it('renders with custom label', () => {
    render(<AgentButton onClick={() => {}} label="Diagnose" />);
    expect(screen.getByText('Diagnose')).toBeInTheDocument();
  });

  it('calls onClick when clicked', () => {
    const onClick = jest.fn();
    render(<AgentButton onClick={onClick} label="Click Me" />);
    fireEvent.click(screen.getByText('Click Me'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('does not call onClick when disabled', () => {
    const onClick = jest.fn();
    render(<AgentButton onClick={onClick} label="Disabled" disabled={true} />);
    fireEvent.click(screen.getByText('Disabled'));
    expect(onClick).not.toHaveBeenCalled();
  });

  it('shows loading state', () => {
    render(<AgentButton onClick={() => {}} loading={true} />);
    expect(screen.getByText('Thinking...')).toBeInTheDocument();
  });

  it('does not call onClick when loading', () => {
    const onClick = jest.fn();
    render(<AgentButton onClick={onClick} loading={true} />);
    fireEvent.click(screen.getByText('Thinking...'));
    expect(onClick).not.toHaveBeenCalled();
  });

  it('renders secondary variant', () => {
    const { container } = render(
      <AgentButton onClick={() => {}} variant="secondary" label="Secondary" />
    );
    expect(container.querySelector('button').className).toContain('from-gray');
  });

  it('renders danger variant', () => {
    const { container } = render(
      <AgentButton onClick={() => {}} variant="danger" label="Danger" />
    );
    expect(container.querySelector('button').className).toContain('from-red');
  });

  it('renders small size', () => {
    const { container } = render(
      <AgentButton onClick={() => {}} size="small" label="Small" />
    );
    expect(container.querySelector('button').className).toContain('text-sm');
  });

  it('renders large size', () => {
    const { container } = render(
      <AgentButton onClick={() => {}} size="large" label="Large" />
    );
    expect(container.querySelector('button').className).toContain('text-lg');
  });

  it('applies custom className', () => {
    const { container } = render(
      <AgentButton onClick={() => {}} className="custom-class" />
    );
    expect(container.querySelector('button').className).toContain('custom-class');
  });
});
