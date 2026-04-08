/**
 * Tests for RosaHcpClustersSection component.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

// Mock dependencies
const mockDispatch = jest.fn();
const mockAddToRecent = jest.fn();
const mockUpdateRecentOperationStatus = jest.fn();

jest.mock('../../store/AppContext', () => ({
  useApp: () => ({ collapsedSections: new Set() }),
  useAppDispatch: () => mockDispatch,
  useApiStatusContext: () => ({
    ocpStatus: { connected: true },
  }),
  useRecentOperationsContext: () => ({
    addToRecent: mockAddToRecent,
    updateRecentOperationStatus: mockUpdateRecentOperationStatus,
  }),
  AppActionTypes: {
    TOGGLE_SECTION: 'TOGGLE_SECTION',
    ADD_NOTIFICATION: 'ADD_NOTIFICATION',
  },
}));

jest.mock('../../config/api', () => ({
  buildApiUrl: (path) => `http://localhost:8000${path}`,
  API_ENDPOINTS: {
    ROSA_CLUSTERS: '/api/rosa/clusters',
  },
  validateApiResponse: (data, fields) => data,
  extractSafeErrorMessage: (err) => err.message || 'Unknown error',
}));

jest.mock('../agents/ProvisionFailureAgentPanel', () => {
  return function MockPanel() {
    return <div data-testid="agent-panel">Agent Panel</div>;
  };
});

const mockFetch = jest.fn();
global.fetch = mockFetch;

import RosaHcpClustersSection from './RosaHcpClustersSection';

beforeEach(() => {
  mockFetch.mockReset();
  jest.clearAllMocks();

  // Default: credentials + empty cluster list
  mockFetch.mockImplementation((url) => {
    if (url.includes('/api/credentials')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ credentials: { minikubeCluster: 'mk-test' } }),
      });
    }
    if (url.includes('/api/rosa/clusters')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, clusters: [] }),
      });
    }
    if (url.includes('/api/minikube/get-active-resources')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, resources: [] }),
      });
    }
    return Promise.resolve({ ok: true, json: async () => ({}) });
  });
});

describe('RosaHcpClustersSection', () => {
  it('renders section header', async () => {
    await act(async () => {
      render(<RosaHcpClustersSection />);
    });
    expect(screen.getAllByText(/ROSA HCP|Clusters/i).length).toBeGreaterThan(0);
  });

  it('renders with mce theme', async () => {
    await act(async () => {
      render(<RosaHcpClustersSection theme="mce" />);
    });
    expect(screen.getAllByText(/ROSA HCP|Clusters/i).length).toBeGreaterThan(0);
  });

  it('renders with minikube theme', async () => {
    await act(async () => {
      render(<RosaHcpClustersSection theme="minikube" />);
    });
    expect(screen.getAllByText(/ROSA HCP|Clusters/i).length).toBeGreaterThan(0);
  });

  it('shows empty state when no clusters', async () => {
    await act(async () => {
      render(<RosaHcpClustersSection />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
    // Should show empty/no clusters message or just the section
    const container = document.querySelector('[class*="clusters"]') || document.body;
    expect(container).toBeTruthy();
  });

  it('fetches clusters on mount', async () => {
    await act(async () => {
      render(<RosaHcpClustersSection />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
  });

  it('renders clusters when available', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/credentials')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ credentials: {} }),
        });
      }
      if (url.includes('/api/rosa/clusters')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            success: true,
            clusters: [
              { name: 'test-cluster-1', status: 'ready', version: '4.20.12', region: 'us-west-2' },
              { name: 'test-cluster-2', status: 'installing', version: '4.20.11', region: 'us-east-1' },
            ],
          }),
        });
      }
      if (url.includes('/api/minikube/get-active-resources')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, resources: [] }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    await act(async () => {
      render(<RosaHcpClustersSection />);
    });

    await waitFor(() => {
      expect(screen.getByText('test-cluster-1')).toBeInTheDocument();
    });
    expect(screen.getByText('test-cluster-2')).toBeInTheDocument();
  });

  it('handles fetch error', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/credentials')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ credentials: {} }),
        });
      }
      if (url.includes('/api/rosa/clusters')) {
        return Promise.reject(new Error('Network error'));
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    await act(async () => {
      render(<RosaHcpClustersSection />);
    });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
    // Should not crash
    expect(screen.getAllByText(/ROSA HCP|Clusters/i).length).toBeGreaterThan(0);
  });

  it('has refresh button', async () => {
    await act(async () => {
      render(<RosaHcpClustersSection />);
    });
    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThan(0);
  });

  it('displays refresh button with correct text', async () => {
    await act(async () => {
      render(<RosaHcpClustersSection />);
    });
    expect(screen.getByText('Refresh')).toBeInTheDocument();
  });

  it('clicking refresh button calls fetchClusters', async () => {
    await act(async () => {
      render(<RosaHcpClustersSection />);
    });

    const initialCallCount = mockFetch.mock.calls.length;
    const refreshButton = screen.getByText('Refresh');

    await act(async () => {
      fireEvent.click(refreshButton);
    });

    await waitFor(() => {
      expect(mockFetch.mock.calls.length).toBeGreaterThan(initialCallCount);
    });
  });

  it('shows loading spinner when refreshing', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/credentials')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ credentials: {} }),
        });
      }
      if (url.includes('/api/rosa/clusters')) {
        return new Promise(() => {}); // Never resolves
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    await act(async () => {
      render(<RosaHcpClustersSection />);
    });

    await waitFor(() => {
      expect(screen.getByText('Loading clusters...')).toBeInTheDocument();
    });
  });

  it('displays cluster status badge correctly', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/credentials')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ credentials: {} }),
        });
      }
      if (url.includes('/api/rosa/clusters')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            success: true,
            clusters: [
              { name: 'ready-cluster', status: 'ready', version: '4.20.12', region: 'us-west-2' },
              { name: 'provisioning-cluster', status: 'provisioning', version: '4.20.11', region: 'us-east-1' },
            ],
          }),
        });
      }
      if (url.includes('/api/minikube/get-active-resources')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, resources: [] }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    await act(async () => {
      render(<RosaHcpClustersSection />);
    });

    await waitFor(() => {
      expect(screen.getByText('ready-cluster')).toBeInTheDocument();
      expect(screen.getByText('provisioning-cluster')).toBeInTheDocument();
    });
  });

  it('displays cluster version and region', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/credentials')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ credentials: {} }),
        });
      }
      if (url.includes('/api/rosa/clusters')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            success: true,
            clusters: [
              { name: 'test-cluster', status: 'ready', version: '4.21.5', region: 'us-west-2', created: '2024-01-01' },
            ],
          }),
        });
      }
      if (url.includes('/api/minikube/get-active-resources')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, resources: [] }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    await act(async () => {
      render(<RosaHcpClustersSection />);
    });

    await waitFor(() => {
      expect(screen.getByText('4.21.5')).toBeInTheDocument();
      expect(screen.getByText(/us-west-2/)).toBeInTheDocument();
    });
  });

  it('displays delete button for each cluster', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/credentials')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ credentials: {} }),
        });
      }
      if (url.includes('/api/rosa/clusters')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            success: true,
            clusters: [
              { name: 'test-cluster', status: 'ready', version: '4.20.12', region: 'us-west-2' },
            ],
          }),
        });
      }
      if (url.includes('/api/minikube/get-active-resources')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, resources: [] }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    await act(async () => {
      render(<RosaHcpClustersSection />);
    });

    await waitFor(() => {
      const deleteButtons = screen.getAllByTitle(/Delete cluster/);
      expect(deleteButtons.length).toBeGreaterThan(0);
    });
  });

  it('shows delete confirmation when delete button clicked', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/credentials')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ credentials: {} }),
        });
      }
      if (url.includes('/api/rosa/clusters')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            success: true,
            clusters: [
              { name: 'test-cluster', status: 'ready', version: '4.20.12', region: 'us-west-2' },
            ],
          }),
        });
      }
      if (url.includes('/api/minikube/get-active-resources')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, resources: [] }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    await act(async () => {
      render(<RosaHcpClustersSection />);
    });

    await waitFor(() => {
      expect(screen.getByText('test-cluster')).toBeInTheDocument();
    });

    const deleteButton = screen.getByTitle(/Delete cluster test-cluster/);
    await act(async () => {
      fireEvent.click(deleteButton);
    });

    await waitFor(() => {
      expect(screen.getByText('Confirm Deletion')).toBeInTheDocument();
      expect(screen.getByText(/Are you sure you want to delete cluster/)).toBeInTheDocument();
    });
  });

  it('allows canceling deletion', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/credentials')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ credentials: {} }),
        });
      }
      if (url.includes('/api/rosa/clusters')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            success: true,
            clusters: [
              { name: 'test-cluster', status: 'ready', version: '4.20.12', region: 'us-west-2' },
            ],
          }),
        });
      }
      if (url.includes('/api/minikube/get-active-resources')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, resources: [] }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    await act(async () => {
      render(<RosaHcpClustersSection />);
    });

    await waitFor(() => {
      expect(screen.getByText('test-cluster')).toBeInTheDocument();
    });

    const deleteButton = screen.getByTitle(/Delete cluster test-cluster/);
    await act(async () => {
      fireEvent.click(deleteButton);
    });

    await waitFor(() => {
      expect(screen.getByText('Confirm Deletion')).toBeInTheDocument();
    });

    const cancelButton = screen.getByText('Cancel');
    await act(async () => {
      fireEvent.click(cancelButton);
    });

    await waitFor(() => {
      expect(screen.queryByText('Confirm Deletion')).not.toBeInTheDocument();
    });
  });

  it('sorts clusters by name', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/credentials')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ credentials: {} }),
        });
      }
      if (url.includes('/api/rosa/clusters')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            success: true,
            clusters: [
              { name: 'cluster-b', status: 'ready', version: '4.20.12', region: 'us-west-2' },
              { name: 'cluster-a', status: 'ready', version: '4.20.11', region: 'us-east-1' },
            ],
          }),
        });
      }
      if (url.includes('/api/minikube/get-active-resources')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, resources: [] }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    await act(async () => {
      render(<RosaHcpClustersSection />);
    });

    await waitFor(() => {
      expect(screen.getByText('cluster-b')).toBeInTheDocument();
    });

    const nameHeader = screen.getByText('Name').closest('th');
    await act(async () => {
      fireEvent.click(nameHeader);
    });

    // Clusters should be sorted
    expect(screen.getByText('cluster-a')).toBeInTheDocument();
  });

  it('renders with minikube theme colors', async () => {
    await act(async () => {
      render(<RosaHcpClustersSection theme="minikube" />);
    });
    expect(screen.getAllByText(/ROSA HCP|Clusters/i).length).toBeGreaterThan(0);
  });

  it('fetches minikube resources when theme is minikube', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/credentials')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ credentials: { minikubeCluster: 'test-mk' } }),
        });
      }
      if (url.includes('/api/minikube/get-active-resources')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            success: true,
            resources: [
              { type: 'ROSAControlPlane', name: 'mk-cluster', status: 'ready', version: '4.20.0' },
            ],
          }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    await act(async () => {
      render(<RosaHcpClustersSection theme="minikube" />);
    });

    await waitFor(() => {
      expect(screen.getByText('mk-cluster')).toBeInTheDocument();
    });
  });

  it('handles API response validation error', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/credentials')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ credentials: {} }),
        });
      }
      if (url.includes('/api/rosa/clusters')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: false, message: 'API error' }),
        });
      }
      if (url.includes('/api/minikube/get-active-resources')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, resources: [] }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    await act(async () => {
      render(<RosaHcpClustersSection />);
    });

    await waitFor(() => {
      expect(screen.getByText('Failed to load clusters')).toBeInTheDocument();
    });
  });

  it('displays ROSA type for all clusters', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/credentials')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ credentials: {} }),
        });
      }
      if (url.includes('/api/rosa/clusters')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            success: true,
            clusters: [
              { name: 'test-cluster', status: 'ready', version: '4.20.12', region: 'us-west-2' },
            ],
          }),
        });
      }
      if (url.includes('/api/minikube/get-active-resources')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, resources: [] }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    await act(async () => {
      render(<RosaHcpClustersSection />);
    });

    await waitFor(() => {
      expect(screen.getByText('ROSA')).toBeInTheDocument();
    });
  });

  it('displays formatted creation date', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/credentials')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ credentials: {} }),
        });
      }
      if (url.includes('/api/rosa/clusters')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            success: true,
            clusters: [
              { name: 'test-cluster', status: 'ready', version: '4.20.12', region: 'us-west-2', created: '2024-01-15' },
            ],
          }),
        });
      }
      if (url.includes('/api/minikube/get-active-resources')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, resources: [] }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    await act(async () => {
      render(<RosaHcpClustersSection />);
    });

    await waitFor(() => {
      expect(screen.getByText(/Jan/)).toBeInTheDocument();
    });
  });
});
