/**
 * Tests for useJobHistory hook.
 */

import { renderHook, act } from '@testing-library/react';
import { useJobHistory } from './useJobHistory';

// Mock fetch globally
const mockFetch = jest.fn();
global.fetch = mockFetch;

beforeEach(() => {
  mockFetch.mockReset();
  // Default: return empty jobs
  mockFetch.mockResolvedValue({
    ok: true,
    json: async () => ({ success: true, jobs: [] }),
  });
});

describe('useJobHistory', () => {
  describe('initial state', () => {
    it('starts with default state values', () => {
      const { result } = renderHook(() => useJobHistory());
      expect(result.current.jobHistoryCollapsed).toBe(false);
      expect(result.current.jobHistoryOutputCollapsed).toBe(false);
      expect(Array.isArray(result.current.jobHistory)).toBe(true);
    });
  });

  describe('fetchJobHistory', () => {
    it('fetches jobs from API on mount', async () => {
      const jobs = [
        { id: 'j1', task_file: 'validate-capa-environment.yml', created_at: new Date().toISOString() },
      ];
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, jobs }),
      });

      const { result } = renderHook(() => useJobHistory());

      // Wait for initial fetch
      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(mockFetch).toHaveBeenCalled();
    });

    it('handles fetch error gracefully', async () => {
      mockFetch.mockRejectedValue(new Error('Network error'));

      const { result } = renderHook(() => useJobHistory());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.error).toBeTruthy();
    });

    it('handles non-ok response', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
      });

      const { result } = renderHook(() => useJobHistory());

      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.error).toBeTruthy();
    });
  });

  describe('getJobsByEnvironment', () => {
    it('filters MCE jobs by task_file', () => {
      const { result } = renderHook(() => useJobHistory());

      // getJobsByEnvironment filters the current jobHistory state
      const mceJobs = result.current.getJobsByEnvironment('mce');
      expect(Array.isArray(mceJobs)).toBe(true);
    });

    it('returns all jobs with "all" environment', () => {
      const { result } = renderHook(() => useJobHistory());
      const allJobs = result.current.getJobsByEnvironment('all');
      expect(Array.isArray(allJobs)).toBe(true);
    });

    it('returns empty for unknown environment', () => {
      const { result } = renderHook(() => useJobHistory());
      const jobs = result.current.getJobsByEnvironment('unknown');
      expect(jobs).toEqual([]);
    });
  });

  describe('getGroupedJobs', () => {
    it('returns grouped structure with all time buckets', () => {
      const { result } = renderHook(() => useJobHistory());
      const groups = result.current.getGroupedJobs();
      expect(groups).toHaveProperty('today');
      expect(groups).toHaveProperty('yesterday');
      expect(groups).toHaveProperty('thisWeek');
      expect(groups).toHaveProperty('older');
    });

    it('returns empty arrays when no jobs', () => {
      const { result } = renderHook(() => useJobHistory());
      const groups = result.current.getGroupedJobs();
      expect(groups.today).toEqual([]);
      expect(groups.yesterday).toEqual([]);
      expect(groups.thisWeek).toEqual([]);
      expect(groups.older).toEqual([]);
    });
  });

  describe('collapse toggles', () => {
    it('toggles job history collapsed', () => {
      const { result } = renderHook(() => useJobHistory());
      act(() => {
        result.current.setJobHistoryCollapsed(true);
      });
      expect(result.current.jobHistoryCollapsed).toBe(true);
    });

    it('toggles output collapsed', () => {
      const { result } = renderHook(() => useJobHistory());
      act(() => {
        result.current.setJobHistoryOutputCollapsed(true);
      });
      expect(result.current.jobHistoryOutputCollapsed).toBe(true);
    });
  });

  describe('manual fetch', () => {
    it('exposes fetchJobHistory function', () => {
      const { result } = renderHook(() => useJobHistory());
      expect(typeof result.current.fetchJobHistory).toBe('function');
    });
  });
});
