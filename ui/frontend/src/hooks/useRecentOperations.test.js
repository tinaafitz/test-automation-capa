/**
 * Tests for useRecentOperations hook.
 */

import { renderHook, act } from '@testing-library/react';
import { useRecentOperations } from './useRecentOperations';

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
    _getStore: () => store,
  };
})();

Object.defineProperty(window, 'localStorage', { value: localStorageMock });

beforeEach(() => {
  localStorageMock.clear();
  jest.clearAllMocks();
});

describe('useRecentOperations', () => {
  describe('initial state', () => {
    it('starts with empty operations', () => {
      const { result } = renderHook(() => useRecentOperations());
      expect(result.current.recentOperations).toEqual([]);
    });

    it('persists operations to localStorage on change', async () => {
      const { result } = renderHook(() => useRecentOperations());
      act(() => {
        result.current.addToRecent({ id: 'op-persist', type: 'test' });
      });
      // The useEffect that persists to localStorage is triggered by state change
      // Check that setItem was called with the operations
      expect(localStorageMock.setItem).toHaveBeenCalledWith(
        'recentOperations',
        expect.stringContaining('op-persist')
      );
    });

    it('handles corrupted localStorage gracefully', () => {
      localStorageMock.setItem('recentOperations', 'not-json');
      const { result } = renderHook(() => useRecentOperations());
      expect(result.current.recentOperations).toEqual([]);
    });

    it('handles non-array localStorage value', () => {
      localStorageMock.setItem('recentOperations', JSON.stringify({ not: 'array' }));
      const { result } = renderHook(() => useRecentOperations());
      expect(result.current.recentOperations).toEqual([]);
    });

    it('starts with collapsed states as false', () => {
      const { result } = renderHook(() => useRecentOperations());
      expect(result.current.recentOperationsCollapsed).toBe(false);
      expect(result.current.recentOperationsOutputCollapsed).toBe(false);
    });
  });

  describe('addToRecent', () => {
    it('adds operation to the beginning', () => {
      const { result } = renderHook(() => useRecentOperations());
      act(() => {
        result.current.addToRecent({ id: 'op-1', type: 'provision' });
      });
      expect(result.current.recentOperations).toHaveLength(1);
      expect(result.current.recentOperations[0].id).toBe('op-1');
    });

    it('generates id and timestamp if not provided', () => {
      const { result } = renderHook(() => useRecentOperations());
      act(() => {
        result.current.addToRecent({ type: 'delete' });
      });
      expect(result.current.recentOperations[0].id).toMatch(/^op-/);
      expect(result.current.recentOperations[0].timestamp).toBeTruthy();
    });

    it('sets default status to Starting', () => {
      const { result } = renderHook(() => useRecentOperations());
      act(() => {
        result.current.addToRecent({ id: 'op-1' });
      });
      expect(result.current.recentOperations[0].status).toContain('Starting');
    });

    it('deduplicates by id', () => {
      const { result } = renderHook(() => useRecentOperations());
      act(() => {
        result.current.addToRecent({ id: 'op-1', type: 'v1' });
      });
      act(() => {
        result.current.addToRecent({ id: 'op-1', type: 'v2' });
      });
      expect(result.current.recentOperations).toHaveLength(1);
      expect(result.current.recentOperations[0].type).toBe('v2');
    });

    it('caps at 50 operations', () => {
      const { result } = renderHook(() => useRecentOperations());
      act(() => {
        for (let i = 0; i < 55; i++) {
          result.current.addToRecent({ id: `op-${i}`, type: 'test' });
        }
      });
      expect(result.current.recentOperations.length).toBeLessThanOrEqual(50);
    });
  });

  describe('updateRecentOperationStatus', () => {
    it('updates status of existing operation', () => {
      const { result } = renderHook(() => useRecentOperations());
      act(() => {
        result.current.addToRecent({ id: 'op-1', status: 'running' });
      });
      act(() => {
        result.current.updateRecentOperationStatus('op-1', 'completed', 'output text');
      });
      expect(result.current.recentOperations[0].status).toBe('completed');
      expect(result.current.recentOperations[0].output).toBe('output text');
      expect(result.current.recentOperations[0].completedAt).toBeTruthy();
    });

    it('does not modify other operations', () => {
      const { result } = renderHook(() => useRecentOperations());
      act(() => {
        result.current.addToRecent({ id: 'op-1', status: 'running' });
        result.current.addToRecent({ id: 'op-2', status: 'pending' });
      });
      act(() => {
        result.current.updateRecentOperationStatus('op-1', 'done');
      });
      const op2 = result.current.recentOperations.find((op) => op.id === 'op-2');
      expect(op2.status).toBe('pending');
    });

    it('merges extra fields', () => {
      const { result } = renderHook(() => useRecentOperations());
      act(() => {
        result.current.addToRecent({ id: 'op-1' });
      });
      act(() => {
        result.current.updateRecentOperationStatus('op-1', 'done', undefined, {
          exitCode: 0,
        });
      });
      expect(result.current.recentOperations[0].exitCode).toBe(0);
    });
  });

  describe('removeRecentOperation', () => {
    it('removes operation by id', () => {
      const { result } = renderHook(() => useRecentOperations());
      act(() => {
        result.current.addToRecent({ id: 'op-1' });
        result.current.addToRecent({ id: 'op-2' });
      });
      act(() => {
        result.current.removeRecentOperation('op-1');
      });
      expect(result.current.recentOperations).toHaveLength(1);
      expect(result.current.recentOperations[0].id).toBe('op-2');
    });
  });

  describe('clearRecentOperations', () => {
    it('clears all operations', () => {
      const { result } = renderHook(() => useRecentOperations());
      act(() => {
        result.current.addToRecent({ id: 'op-1' });
        result.current.addToRecent({ id: 'op-2' });
      });
      act(() => {
        result.current.clearRecentOperations();
      });
      expect(result.current.recentOperations).toEqual([]);
    });

    it('removes from localStorage', () => {
      const { result } = renderHook(() => useRecentOperations());
      act(() => {
        result.current.addToRecent({ id: 'op-1' });
      });
      act(() => {
        result.current.clearRecentOperations();
      });
      expect(localStorageMock.removeItem).toHaveBeenCalledWith('recentOperations');
    });
  });

  describe('loading states', () => {
    it('tracks loading state for operation', () => {
      const { result } = renderHook(() => useRecentOperations());
      act(() => {
        result.current.setOperationLoading('op-1', true);
      });
      expect(result.current.isOperationLoading('op-1')).toBe(true);
    });

    it('clears loading state', () => {
      const { result } = renderHook(() => useRecentOperations());
      act(() => {
        result.current.setOperationLoading('op-1', true);
      });
      act(() => {
        result.current.setOperationLoading('op-1', false);
      });
      expect(result.current.isOperationLoading('op-1')).toBe(false);
    });
  });

  describe('getOperationsByEnvironment', () => {
    it('filters by environment', () => {
      const { result } = renderHook(() => useRecentOperations());
      act(() => {
        result.current.addToRecent({ id: 'op-1', environment: 'mce' });
        result.current.addToRecent({ id: 'op-2', environment: 'minikube' });
      });
      const mceOps = result.current.getOperationsByEnvironment('mce');
      expect(mceOps).toHaveLength(1);
      expect(mceOps[0].id).toBe('op-1');
    });

    it('returns ops without environment when filtering by all', () => {
      const { result } = renderHook(() => useRecentOperations());
      act(() => {
        result.current.addToRecent({ id: 'op-1' });
      });
      const allOps = result.current.getOperationsByEnvironment('all');
      expect(allOps).toHaveLength(1);
    });
  });

  describe('getGroupedOperations', () => {
    it('groups operations by time', () => {
      const { result } = renderHook(() => useRecentOperations());
      act(() => {
        result.current.addToRecent({
          id: 'op-today',
          timestamp: new Date().toISOString(),
        });
      });
      const groups = result.current.getGroupedOperations();
      expect(groups.today.length).toBeGreaterThanOrEqual(1);
      expect(groups).toHaveProperty('yesterday');
      expect(groups).toHaveProperty('thisWeek');
      expect(groups).toHaveProperty('older');
    });

    it('returns empty groups when no operations', () => {
      const { result } = renderHook(() => useRecentOperations());
      const groups = result.current.getGroupedOperations();
      expect(groups.today).toEqual([]);
      expect(groups.yesterday).toEqual([]);
      expect(groups.thisWeek).toEqual([]);
      expect(groups.older).toEqual([]);
    });
  });

  describe('collapse toggles', () => {
    it('toggles operations collapsed', () => {
      const { result } = renderHook(() => useRecentOperations());
      act(() => {
        result.current.setRecentOperationsCollapsed(true);
      });
      expect(result.current.recentOperationsCollapsed).toBe(true);
    });

    it('toggles output collapsed', () => {
      const { result } = renderHook(() => useRecentOperations());
      act(() => {
        result.current.setRecentOperationsOutputCollapsed(true);
      });
      expect(result.current.recentOperationsOutputCollapsed).toBe(true);
    });
  });
});
