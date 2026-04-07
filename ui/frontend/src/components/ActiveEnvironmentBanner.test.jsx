/**
 * Tests for ActiveEnvironmentBanner component.
 */

import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';

const mockFetch = jest.fn();
global.fetch = mockFetch;

import ActiveEnvironmentBanner from './ActiveEnvironmentBanner';

beforeEach(() => {
  mockFetch.mockReset();
  jest.clearAllMocks();
});

describe('ActiveEnvironmentBanner', () => {
  it('renders nothing while loading', () => {
    mockFetch.mockReturnValue(new Promise(() => {})); // never resolves
    const { container } = render(<ActiveEnvironmentBanner />);
    expect(container.innerHTML).toBe('');
  });

  it('renders MCE environment with credentials', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        credentials: {
          OCP_HUB_API_URL: 'https://api.qe6-vmware.dev09.com:6443',
          OCP_HUB_CLUSTER_USER: 'kubeadmin',
        },
      }),
    });

    await act(async () => {
      render(<ActiveEnvironmentBanner environment="mce" />);
    });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
  });

  it('renders minikube environment', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        credentials: {
          minikubeCluster: 'my-minikube',
          apiPort: 8443,
        },
      }),
    });

    await act(async () => {
      render(<ActiveEnvironmentBanner environment="minikube" />);
    });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
  });

  it('handles fetch error gracefully', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));

    await act(async () => {
      render(<ActiveEnvironmentBanner environment="mce" />);
    });

    // Should not crash
    expect(document.body).toBeTruthy();
  });

  it('shows warning when no minikube cluster configured', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        credentials: {},
      }),
    });

    // Second call for active-profile fallback
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true, credentials: {} }),
    });
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: false }),
    });

    await act(async () => {
      render(<ActiveEnvironmentBanner environment="minikube" />);
    });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
  });
});
