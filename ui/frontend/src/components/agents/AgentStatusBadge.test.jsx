/**
 * Tests for AgentStatusBadge component.
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import AgentStatusBadge from './AgentStatusBadge';

describe('AgentStatusBadge', () => {
  it('renders pending status by default', () => {
    render(<AgentStatusBadge />);
    expect(screen.getByText('Pending')).toBeInTheDocument();
  });

  it('renders spawning status', () => {
    render(<AgentStatusBadge status="spawning" />);
    expect(screen.getByText('Initializing')).toBeInTheDocument();
  });

  it('renders running status', () => {
    render(<AgentStatusBadge status="running" />);
    expect(screen.getByText('Analyzing')).toBeInTheDocument();
  });

  it('renders completed status', () => {
    render(<AgentStatusBadge status="completed" />);
    expect(screen.getByText('Completed')).toBeInTheDocument();
  });

  it('renders failed status', () => {
    render(<AgentStatusBadge status="failed" />);
    expect(screen.getByText('Failed')).toBeInTheDocument();
  });

  it('renders without icon when showIcon is false', () => {
    const { container } = render(<AgentStatusBadge status="completed" showIcon={false} />);
    expect(screen.getByText('Completed')).toBeInTheDocument();
    // Should not have an SVG icon
    expect(container.querySelector('svg')).toBeNull();
  });

  it('renders small size', () => {
    const { container } = render(<AgentStatusBadge status="pending" size="small" />);
    expect(container.firstChild.className).toContain('text-xs');
  });

  it('renders large size', () => {
    const { container } = render(<AgentStatusBadge status="pending" size="large" />);
    expect(container.firstChild.className).toContain('text-base');
  });

  it('falls back to pending for unknown status', () => {
    render(<AgentStatusBadge status="unknown-status" />);
    expect(screen.getByText('Pending')).toBeInTheDocument();
  });
});
