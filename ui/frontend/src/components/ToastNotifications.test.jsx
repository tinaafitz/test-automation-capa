/**
 * Tests for ToastNotifications component.
 */

import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';

// Mock AppContext
const mockDispatch = jest.fn();
const mockNotifications = [];

jest.mock('../store/AppContext', () => ({
  useApp: () => ({ notifications: mockNotifications }),
  useAppDispatch: () => mockDispatch,
  AppActionTypes: {
    REMOVE_NOTIFICATION: 'REMOVE_NOTIFICATION',
  },
}));

import ToastNotifications from './ToastNotifications';

beforeEach(() => {
  jest.clearAllMocks();
  jest.useFakeTimers();
  mockNotifications.length = 0;
});

afterEach(() => {
  jest.useRealTimers();
});

describe('ToastNotifications', () => {
  it('renders empty when no notifications', () => {
    const { container } = render(<ToastNotifications />);
    expect(container.firstChild).toBeTruthy();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('renders a success notification', () => {
    mockNotifications.push({
      id: 'n1',
      type: 'success',
      title: 'Cluster Created',
      message: 'ROSA cluster is ready',
      duration: 5000,
    });
    render(<ToastNotifications />);
    expect(screen.getByText('Cluster Created')).toBeInTheDocument();
    expect(screen.getByText('ROSA cluster is ready')).toBeInTheDocument();
  });

  it('renders an error notification', () => {
    mockNotifications.push({
      id: 'n2',
      type: 'error',
      message: 'Provisioning failed',
    });
    render(<ToastNotifications />);
    expect(screen.getByText('Provisioning failed')).toBeInTheDocument();
  });

  it('renders a warning notification', () => {
    mockNotifications.push({
      id: 'n3',
      type: 'warning',
      message: 'Cluster is degraded',
    });
    render(<ToastNotifications />);
    expect(screen.getByText('Cluster is degraded')).toBeInTheDocument();
  });

  it('renders an info notification', () => {
    mockNotifications.push({
      id: 'n4',
      type: 'info',
      message: 'Checking status...',
    });
    render(<ToastNotifications />);
    expect(screen.getByText('Checking status...')).toBeInTheDocument();
  });

  it('dispatches remove when dismiss button clicked', () => {
    mockNotifications.push({
      id: 'n5',
      type: 'success',
      message: 'Done',
    });
    render(<ToastNotifications />);
    const dismissBtn = screen.getByRole('button');
    fireEvent.click(dismissBtn);
    expect(mockDispatch).toHaveBeenCalledWith({
      type: 'REMOVE_NOTIFICATION',
      payload: 'n5',
    });
  });

  it('auto-removes notification after duration', () => {
    mockNotifications.push({
      id: 'n6',
      type: 'info',
      message: 'Auto dismiss',
      duration: 3000,
    });
    render(<ToastNotifications />);
    act(() => {
      jest.advanceTimersByTime(3100);
    });
    expect(mockDispatch).toHaveBeenCalledWith({
      type: 'REMOVE_NOTIFICATION',
      payload: 'n6',
    });
  });

  it('renders multiple notifications', () => {
    mockNotifications.push(
      { id: 'a', type: 'success', message: 'First' },
      { id: 'b', type: 'error', message: 'Second' },
    );
    render(<ToastNotifications />);
    expect(screen.getByText('First')).toBeInTheDocument();
    expect(screen.getByText('Second')).toBeInTheDocument();
  });
});
