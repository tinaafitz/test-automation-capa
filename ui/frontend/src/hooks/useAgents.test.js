/**
 * Tests for useAgents hook.
 */

import { renderHook, act } from '@testing-library/react';
import useAgents from './useAgents';

// Mock fetch globally
const mockFetch = jest.fn();
global.fetch = mockFetch;

beforeEach(() => {
  mockFetch.mockReset();
});

describe('useAgents', () => {
  describe('initial state', () => {
    it('starts with empty agents list', () => {
      const { result } = renderHook(() => useAgents());
      expect(result.current.activeAgents).toEqual([]);
      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBeNull();
    });
  });

  describe('spawnExploreAgent', () => {
    it('spawns explore agent successfully', async () => {
      const agentData = { agent_id: 'a1', type: 'explore', status: 'completed' };
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => agentData,
      });

      const { result } = renderHook(() => useAgents());
      let data;
      await act(async () => {
        data = await result.current.spawnExploreAgent('find errors', 'quick');
      });

      expect(data).toEqual(agentData);
      expect(result.current.activeAgents).toHaveLength(1);
      expect(result.current.loading).toBe(false);
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/agents/explore',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ prompt: 'find errors', thoroughness: 'quick', context: null }),
        })
      );
    });

    it('handles explore agent failure', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        statusText: 'Internal Server Error',
      });

      const { result } = renderHook(() => useAgents());
      await act(async () => {
        await expect(result.current.spawnExploreAgent('find errors')).rejects.toThrow(
          'Failed to spawn Explore agent'
        );
      });

      expect(result.current.error).toContain('Failed to spawn Explore agent');
      expect(result.current.loading).toBe(false);
    });
  });

  describe('spawnPlanAgent', () => {
    it('spawns plan agent successfully', async () => {
      const agentData = { agent_id: 'a2', type: 'plan', status: 'completed' };
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => agentData,
      });

      const { result } = renderHook(() => useAgents());
      await act(async () => {
        await result.current.spawnPlanAgent('design cluster', { version: '4.14' });
      });

      expect(result.current.activeAgents).toHaveLength(1);
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/agents/plan',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ prompt: 'design cluster', requirements: { version: '4.14' } }),
        })
      );
    });
  });

  describe('spawnGeneralAgent', () => {
    it('spawns general agent successfully', async () => {
      const agentData = { agent_id: 'a3', type: 'general', status: 'completed' };
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => agentData,
      });

      const { result } = renderHook(() => useAgents());
      await act(async () => {
        await result.current.spawnGeneralAgent('fix issue', 'diagnose', { cluster: 'c1' });
      });

      expect(result.current.activeAgents).toHaveLength(1);
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/agents/general',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            prompt: 'fix issue',
            task_type: 'diagnose',
            context: { cluster: 'c1' },
          }),
        })
      );
    });
  });

  describe('getAgentStatus', () => {
    it('fetches and updates agent status', async () => {
      // First spawn an agent
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ agent_id: 'a1', type: 'explore', status: 'running' }),
      });

      const { result } = renderHook(() => useAgents());
      await act(async () => {
        await result.current.spawnExploreAgent('test');
      });

      // Then check status
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ agent_id: 'a1', type: 'explore', status: 'completed' }),
      });

      await act(async () => {
        await result.current.getAgentStatus('a1');
      });

      expect(result.current.activeAgents[0].status).toBe('completed');
    });

    it('handles status check failure', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        statusText: 'Not Found',
      });

      const { result } = renderHook(() => useAgents());
      await act(async () => {
        await expect(result.current.getAgentStatus('nonexistent')).rejects.toThrow(
          'Failed to get agent status'
        );
      });
      expect(result.current.error).toBeTruthy();
    });
  });

  describe('listActiveAgents', () => {
    it('fetches and sets active agents list', async () => {
      const agents = [
        { agent_id: 'a1', type: 'explore' },
        { agent_id: 'a2', type: 'plan' },
      ];
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, agents }),
      });

      const { result } = renderHook(() => useAgents());
      await act(async () => {
        await result.current.listActiveAgents();
      });

      expect(result.current.activeAgents).toEqual(agents);
      expect(result.current.loading).toBe(false);
    });

    it('handles list failure', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        statusText: 'Server Error',
      });

      const { result } = renderHook(() => useAgents());
      await act(async () => {
        await expect(result.current.listActiveAgents()).rejects.toThrow('Failed to list agents');
      });
    });
  });

  describe('clearError', () => {
    it('clears error state', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        statusText: 'Error',
      });

      const { result } = renderHook(() => useAgents());
      await act(async () => {
        try {
          await result.current.spawnExploreAgent('test');
        } catch {}
      });

      expect(result.current.error).toBeTruthy();

      act(() => {
        result.current.clearError();
      });

      expect(result.current.error).toBeNull();
    });
  });

  describe('removeAgent', () => {
    it('removes agent from local state', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ agent_id: 'a1', type: 'explore' }),
      });

      const { result } = renderHook(() => useAgents());
      await act(async () => {
        await result.current.spawnExploreAgent('test');
      });

      expect(result.current.activeAgents).toHaveLength(1);

      act(() => {
        result.current.removeAgent('a1');
      });

      expect(result.current.activeAgents).toHaveLength(0);
    });
  });
});
