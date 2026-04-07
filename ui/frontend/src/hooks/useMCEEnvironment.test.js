/**
 * Tests for useMCEEnvironment hook.
 */

import { renderHook, act } from '@testing-library/react';
import { useMCEEnvironment } from './useMCEEnvironment';

// Mock fetch globally
const mockFetch = jest.fn();
global.fetch = mockFetch;

beforeEach(() => {
  mockFetch.mockReset();
  mockFetch.mockResolvedValue({
    ok: true,
    json: async () => ({ success: true, resources: [] }),
  });
});

describe('useMCEEnvironment', () => {
  describe('initial state', () => {
    it('starts with null MCE info', () => {
      const { result } = renderHook(() => useMCEEnvironment());
      expect(result.current.mceInfo).toBeNull();
      expect(result.current.mceFeatures).toEqual([]);
      expect(result.current.mceActiveResources).toEqual([]);
      expect(result.current.mceLastVerified).toBeNull();
    });

    it('starts with default sort settings', () => {
      const { result } = renderHook(() => useMCEEnvironment());
      expect(result.current.mceSortField).toBe('type');
      expect(result.current.mceSortDirection).toBe('asc');
      expect(result.current.mceComponentSortField).toBe('component');
      expect(result.current.mceComponentSortDirection).toBe('asc');
    });

    it('starts with collapsed states as false', () => {
      const { result } = renderHook(() => useMCEEnvironment());
      expect(result.current.mceConfigurationCollapsed).toBe(false);
      expect(result.current.mceRecentOpsCollapsed).toBe(false);
    });
  });

  describe('collapse toggles', () => {
    it('toggles configuration collapsed', () => {
      const { result } = renderHook(() => useMCEEnvironment());
      act(() => {
        result.current.setMceConfigurationCollapsed(true);
      });
      expect(result.current.mceConfigurationCollapsed).toBe(true);
    });

    it('toggles recent ops collapsed', () => {
      const { result } = renderHook(() => useMCEEnvironment());
      act(() => {
        result.current.setMceRecentOpsCollapsed(true);
      });
      expect(result.current.mceRecentOpsCollapsed).toBe(true);
    });
  });

  describe('sort controls', () => {
    it('updates resource sort field', () => {
      const { result } = renderHook(() => useMCEEnvironment());
      act(() => {
        result.current.setMceSortField('name');
      });
      expect(result.current.mceSortField).toBe('name');
    });

    it('updates resource sort direction', () => {
      const { result } = renderHook(() => useMCEEnvironment());
      act(() => {
        result.current.setMceSortDirection('desc');
      });
      expect(result.current.mceSortDirection).toBe('desc');
    });

    it('updates component sort field', () => {
      const { result } = renderHook(() => useMCEEnvironment());
      act(() => {
        result.current.setMceComponentSortField('status');
      });
      expect(result.current.mceComponentSortField).toBe('status');
    });

    it('updates component sort direction', () => {
      const { result } = renderHook(() => useMCEEnvironment());
      act(() => {
        result.current.setMceComponentSortDirection('desc');
      });
      expect(result.current.mceComponentSortDirection).toBe('desc');
    });
  });

  describe('loading states', () => {
    it('starts not loading', () => {
      const { result } = renderHook(() => useMCEEnvironment());
      expect(result.current.mceLoading).toBe(false);
      expect(result.current.mceResourcesLoading).toBe(false);
    });
  });

  describe('setters', () => {
    it('sets MCE info', () => {
      const { result } = renderHook(() => useMCEEnvironment());
      act(() => {
        result.current.setMceInfo({ name: 'mce-test', version: '2.5' });
      });
      expect(result.current.mceInfo).toEqual({ name: 'mce-test', version: '2.5' });
    });

    it('sets MCE features', () => {
      const { result } = renderHook(() => useMCEEnvironment());
      act(() => {
        result.current.setMceFeatures([{ component: 'capi', status: 'installed' }]);
      });
      expect(result.current.mceFeatures).toEqual([{ component: 'capi', status: 'installed' }]);
    });

    it('sets MCE active resources', () => {
      const { result } = renderHook(() => useMCEEnvironment());
      act(() => {
        result.current.setMceActiveResources([{ type: 'ROSANetwork', name: 'rn1' }]);
      });
      expect(result.current.mceActiveResources).toEqual([{ type: 'ROSANetwork', name: 'rn1' }]);
    });
  });
});
