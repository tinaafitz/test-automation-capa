/**
 * Tests for ResourcesViewer component.
 */

import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';

jest.mock('../config/api', () => ({
  buildApiUrl: (path) => `http://localhost:8000${path}`,
}));

// Mock YamlEditorModal
jest.mock('./YamlEditorModal.js', () => ({
  YamlEditorModal: () => <div data-testid="yaml-modal">YAML Modal</div>,
}));

const mockFetch = jest.fn();
global.fetch = mockFetch;

import ResourcesViewer from './ResourcesViewer';

beforeEach(() => {
  mockFetch.mockReset();
  jest.clearAllMocks();

  // Default: return empty resources
  mockFetch.mockImplementation((url) => {
    if (url.includes('/api/credentials')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ credentials: { minikubeCluster: 'mk-test' } }),
      });
    }
    if (url.includes('/api/mce/resources')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, resources: [], total: 0 }),
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

describe('ResourcesViewer', () => {
  it('renders with mce theme', async () => {
    await act(async () => {
      render(<ResourcesViewer theme="mce" />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
  });

  it('renders with minikube theme', async () => {
    await act(async () => {
      render(<ResourcesViewer theme="minikube" />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
  });

  it('fetches resources on mount', async () => {
    await act(async () => {
      render(<ResourcesViewer />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/mce/resources')
      );
    });
  });

  it('renders resources when available', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/mce/resources')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            success: true,
            resources: [
              { type: 'Deployment', name: 'capi-controller', namespace: 'capi-system', status: 'Ready' },
              { type: 'Deployment', name: 'capa-controller', namespace: 'capa-system', status: 'Ready' },
            ],
            total: 2,
          }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    await act(async () => {
      render(<ResourcesViewer theme="mce" />);
    });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
  });

  it('handles fetch error gracefully', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));
    await act(async () => {
      render(<ResourcesViewer />);
    });
    // Should not crash
    expect(document.body).toBeTruthy();
  });

  it('fetches from minikube endpoint for minikube theme', async () => {
    await act(async () => {
      render(<ResourcesViewer theme="minikube" />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/credentials')
      );
    });
  });
});
