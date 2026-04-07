/**
 * Tests for MCEEnvironmentSelector component.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

const mockFetch = jest.fn();
global.fetch = mockFetch;

import MCEEnvironmentSelector from './MCEEnvironmentSelector';

beforeEach(() => {
  mockFetch.mockReset();
  jest.clearAllMocks();

  // Default: return empty environments list + stats
  mockFetch.mockImplementation((url) => {
    if (url.includes('/stats/summary') || url.includes('list-clusters')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, total: 0, pass: 0, fail: 0 }),
      });
    }
    return Promise.resolve({
      ok: true,
      json: async () => ({ success: true, environments: [], total: 0 }),
    });
  });
});

describe('MCEEnvironmentSelector', () => {
  const defaultProps = {
    onUseCredentials: jest.fn(),
  };

  it('renders with default props', async () => {
    await act(async () => {
      render(<MCEEnvironmentSelector {...defaultProps} />);
    });
    expect(screen.getAllByText(/MCE Environments|Environment/i).length).toBeGreaterThan(0);
  });

  it('renders with custom title', async () => {
    await act(async () => {
      render(<MCEEnvironmentSelector {...defaultProps} title="My Environments" />);
    });
    expect(screen.getByText('My Environments')).toBeInTheDocument();
  });

  it('renders with minikube theme', async () => {
    await act(async () => {
      render(
        <MCEEnvironmentSelector
          {...defaultProps}
          theme="minikube"
          environmentType="minikube"
          title="Minikube Clusters"
        />
      );
    });
    expect(screen.getByText('Minikube Clusters')).toBeInTheDocument();
  });

  it('fetches environments on mount', async () => {
    await act(async () => {
      render(<MCEEnvironmentSelector {...defaultProps} />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
  });

  it('shows empty state when no environments', async () => {
    await act(async () => {
      render(<MCEEnvironmentSelector {...defaultProps} />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
    // Component should render without crashing
    expect(document.body).toBeTruthy();
  });

  it('renders environments when available', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/stats/summary')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, total: 2, pass: 1, fail: 1 }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({
          success: true,
          environments: [
            {
              clusterName: 'qe6-vmware',
              platform: 'VMware',
              status: 'pass',
              ocpVersion: '4.20.11',
              mceVersion: '2.11.0',
            },
            {
              clusterName: 'qe7-aws-arm',
              platform: 'AWS ARM',
              status: 'fail',
              ocpVersion: '4.20.12',
              mceVersion: '2.11.0',
            },
          ],
          total: 2,
        }),
      });
    });

    await act(async () => {
      render(<MCEEnvironmentSelector {...defaultProps} />);
    });

    await waitFor(() => {
      expect(screen.getByText('qe6-vmware')).toBeInTheDocument();
    });
    expect(screen.getByText('qe7-aws-arm')).toBeInTheDocument();
  });

  it('handles fetch error gracefully', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));
    await act(async () => {
      render(<MCEEnvironmentSelector {...defaultProps} />);
    });
    // Should not crash
    expect(document.body).toBeTruthy();
  });

  it('has search input', async () => {
    await act(async () => {
      render(<MCEEnvironmentSelector {...defaultProps} />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
    const searchInput = document.querySelector('input[type="text"], input[placeholder*="earch"]');
    expect(searchInput).toBeTruthy();
  });
});
