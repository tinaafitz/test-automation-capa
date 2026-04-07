/**
 * Tests for useMinikubeEnvironment hook.
 */

import { renderHook, act } from '@testing-library/react';
import { useMinikubeEnvironment } from './useMinikubeEnvironment';

// Mock fetch globally
const mockFetch = jest.fn();
global.fetch = mockFetch;

// Mock localStorage
const localStorageMock = (() => {
  let store = {};
  return {
    getItem: jest.fn((key) => store[key] || null),
    setItem: jest.fn((key, value) => {
      store[key] = value;
    }),
    removeItem: jest.fn((key) => {
      delete store[key];
    }),
    clear: jest.fn(() => {
      store = {};
    }),
  };
})();

Object.defineProperty(window, 'localStorage', { value: localStorageMock });

beforeEach(() => {
  mockFetch.mockReset();
  localStorageMock.clear();
  // Default: return empty response
  mockFetch.mockResolvedValue({
    ok: true,
    json: async () => ({ success: true, clusters: [] }),
  });
});

describe('useMinikubeEnvironment', () => {
  describe('initial state', () => {
    it('starts with null cluster info', () => {
      const { result } = renderHook(() => useMinikubeEnvironment());
      expect(result.current.minikubeClusterInfo).toBeNull();
      expect(result.current.minikubeActiveResources).toEqual([]);
      expect(result.current.minikubeClusters).toEqual([]);
    });

    it('starts with default sort settings', () => {
      const { result } = renderHook(() => useMinikubeEnvironment());
      expect(result.current.minikubeSortField).toBe('type');
      expect(result.current.minikubeSortDirection).toBe('asc');
    });

    it('starts with collapsed states as false', () => {
      const { result } = renderHook(() => useMinikubeEnvironment());
      expect(result.current.minikubeConfigurationCollapsed).toBe(false);
      expect(result.current.minikubeOperationsOutputCollapsed).toBe(false);
      expect(result.current.minikubeRecentOpsCollapsed).toBe(false);
    });

    it('persists selected cluster to localStorage via setter', () => {
      const { result } = renderHook(() => useMinikubeEnvironment());
      act(() => {
        result.current.setSelectedMinikubeCluster('my-cluster');
      });
      expect(result.current.selectedMinikubeCluster).toBe('my-cluster');
    });
  });

  describe('collapse toggles', () => {
    it('toggles configuration collapsed', () => {
      const { result } = renderHook(() => useMinikubeEnvironment());
      act(() => {
        result.current.setMinikubeConfigurationCollapsed(true);
      });
      expect(result.current.minikubeConfigurationCollapsed).toBe(true);
    });

    it('toggles operations output collapsed', () => {
      const { result } = renderHook(() => useMinikubeEnvironment());
      act(() => {
        result.current.setMinikubeOperationsOutputCollapsed(true);
      });
      expect(result.current.minikubeOperationsOutputCollapsed).toBe(true);
    });
  });

  describe('sort controls', () => {
    it('updates sort field', () => {
      const { result } = renderHook(() => useMinikubeEnvironment());
      act(() => {
        result.current.setMinikubeSortField('name');
      });
      expect(result.current.minikubeSortField).toBe('name');
    });

    it('updates sort direction', () => {
      const { result } = renderHook(() => useMinikubeEnvironment());
      act(() => {
        result.current.setMinikubeSortDirection('desc');
      });
      expect(result.current.minikubeSortDirection).toBe('desc');
    });
  });

  describe('cluster input', () => {
    it('updates cluster input value', () => {
      const { result } = renderHook(() => useMinikubeEnvironment());
      act(() => {
        result.current.setMinikubeClusterInput('test-cluster');
      });
      expect(result.current.minikubeClusterInput).toBe('test-cluster');
    });
  });

  describe('fetchMinikubeActiveResources', () => {
    it('requires cluster name and namespace', async () => {
      const { result } = renderHook(() => useMinikubeEnvironment());
      await act(async () => {
        await result.current.fetchMinikubeActiveResources(null, null);
      });
      expect(mockFetch).not.toHaveBeenCalledWith(
        expect.stringContaining('/api/minikube/get-active-resources'),
        expect.anything()
      );
    });
  });

  describe('loading states', () => {
    it('starts not loading', () => {
      const { result } = renderHook(() => useMinikubeEnvironment());
      expect(result.current.minikubeLoading).toBe(false);
      expect(result.current.minikubeResourcesLoading).toBe(false);
    });
  });
});
