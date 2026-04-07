/**
 * Tests for useApiStatus hook.
 */

import { renderHook, act } from '@testing-library/react';
import { useApiStatus } from './useApiStatus';

// Mock fetch globally
const mockFetch = jest.fn();
global.fetch = mockFetch;

beforeEach(() => {
  mockFetch.mockReset();
  // Default: all endpoints return success
  mockFetch.mockResolvedValue({
    ok: true,
    json: async () => ({ status: 'ok' }),
  });
});

describe('useApiStatus', () => {
  describe('initial state', () => {
    it('starts with null status values', () => {
      const { result } = renderHook(() => useApiStatus());
      expect(result.current.rosaStatus).toBeNull();
      expect(result.current.configStatus).toBeNull();
      expect(result.current.ocpStatus).toBeNull();
      expect(result.current.mceFeatures).toEqual([]);
      expect(result.current.mceInfo).toBeNull();
    });

    it('provides refreshAllStatus function', () => {
      const { result } = renderHook(() => useApiStatus());
      expect(typeof result.current.refreshAllStatus).toBe('function');
    });

    it('provides individual setters', () => {
      const { result } = renderHook(() => useApiStatus());
      expect(typeof result.current.setRosaStatus).toBe('function');
      expect(typeof result.current.setConfigStatus).toBe('function');
      expect(typeof result.current.setOcpStatus).toBe('function');
      expect(typeof result.current.setMceFeatures).toBe('function');
    });
  });

  describe('refreshAllStatus', () => {
    it('fetches all status endpoints', async () => {
      const { result } = renderHook(() => useApiStatus());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      // Should have called ROSA, config, and OCP endpoints
      expect(mockFetch).toHaveBeenCalled();
      const urls = mockFetch.mock.calls.map((c) => c[0]);
      expect(urls.some((u) => u.includes('/api/rosa/status'))).toBe(true);
      expect(urls.some((u) => u.includes('/api/config/status'))).toBe(true);
      expect(urls.some((u) => u.includes('/api/ocp/connection-status'))).toBe(true);
    });

    it('sets error state on ROSA fetch failure', async () => {
      mockFetch.mockImplementation((url) => {
        if (url.includes('/api/rosa/status')) {
          return Promise.reject(new Error('Network error'));
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ status: 'ok', connected: false }),
        });
      });

      const { result } = renderHook(() => useApiStatus());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.rosaStatus).toEqual(
        expect.objectContaining({ authenticated: false, status: 'error' })
      );
    });

    it('sets error state on config fetch failure', async () => {
      mockFetch.mockImplementation((url) => {
        if (url.includes('/api/config/status')) {
          return Promise.reject(new Error('Network error'));
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ status: 'ok', connected: false }),
        });
      });

      const { result } = renderHook(() => useApiStatus());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.configStatus).toEqual(
        expect.objectContaining({ configured: false, status: 'error' })
      );
    });

    it('sets error state on OCP fetch failure', async () => {
      mockFetch.mockImplementation((url) => {
        if (url.includes('/api/ocp/connection-status')) {
          return Promise.reject(new Error('Network error'));
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ status: 'ok' }),
        });
      });

      const { result } = renderHook(() => useApiStatus());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.ocpStatus).toEqual(
        expect.objectContaining({ connected: false, status: 'error' })
      );
    });

    it('fetches MCE features when OCP is connected', async () => {
      mockFetch.mockImplementation((url) => {
        if (url.includes('/api/ocp/connection-status')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ connected: true }),
          });
        }
        if (url.includes('/api/mce/features')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              features: [{ component: 'capi', status: 'installed' }],
              mce_info: { name: 'mce-1' },
            }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ status: 'ok' }),
        });
      });

      const { result } = renderHook(() => useApiStatus());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.mceFeatures).toEqual([{ component: 'capi', status: 'installed' }]);
      expect(result.current.mceInfo).toEqual({ name: 'mce-1' });
    });
  });

  describe('individual setters', () => {
    it('updates rosaStatus via setter', () => {
      const { result } = renderHook(() => useApiStatus());
      act(() => {
        result.current.setRosaStatus({ authenticated: true });
      });
      expect(result.current.rosaStatus).toEqual({ authenticated: true });
    });

    it('updates configStatus via setter', () => {
      const { result } = renderHook(() => useApiStatus());
      act(() => {
        result.current.setConfigStatus({ configured: true });
      });
      expect(result.current.configStatus).toEqual({ configured: true });
    });
  });
});
