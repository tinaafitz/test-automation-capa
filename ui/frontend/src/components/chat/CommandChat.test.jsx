/**
 * Tests for CommandChat component.
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

jest.mock('@heroicons/react/24/outline', () => ({
  CommandLineIcon: (props) => <svg data-testid="cmd-icon" {...props} />,
  XMarkIcon: (props) => <svg data-testid="x-icon" {...props} />,
  PaperAirplaneIcon: (props) => <svg data-testid="send-icon" {...props} />,
  CheckCircleIcon: (props) => <svg data-testid="check-icon" {...props} />,
  ExclamationCircleIcon: (props) => <svg data-testid="exclaim-icon" {...props} />,
  ClockIcon: (props) => <svg data-testid="clock-icon" {...props} />,
}));

import { CommandChat } from './CommandChat';

describe('CommandChat', () => {
  it('renders toggle button', () => {
    render(<CommandChat />);
    expect(screen.getByTestId('cmd-icon')).toBeInTheDocument();
  });

  it('shows chat panel when opened', () => {
    render(<CommandChat />);
    // Click the button to open
    const button = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(button);
    expect(screen.getByText(/ROSA Command Chat/)).toBeInTheDocument();
  });

  it('shows welcome message when opened', () => {
    render(<CommandChat />);
    const button = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(button);
    expect(screen.getByText(/Welcome to ROSA Command Chat/)).toBeInTheDocument();
  });

  it('shows example commands', () => {
    render(<CommandChat />);
    const button = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(button);
    expect(screen.getByText(/provision rosa cluster/)).toBeInTheDocument();
  });

  it('has input field when open', () => {
    render(<CommandChat />);
    const button = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(button);
    expect(screen.getByPlaceholderText(/Enter command/i)).toBeInTheDocument();
  });

  it('closes when close button clicked', () => {
    render(<CommandChat />);
    const openBtn = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(openBtn);
    expect(screen.getByText(/ROSA Command Chat/)).toBeInTheDocument();
    const closeBtn = screen.getByTestId('x-icon').closest('button');
    fireEvent.click(closeBtn);
    expect(screen.queryByText(/ROSA Command Chat/)).toBeNull();
  });
});
