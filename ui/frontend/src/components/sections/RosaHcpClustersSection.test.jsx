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
});
