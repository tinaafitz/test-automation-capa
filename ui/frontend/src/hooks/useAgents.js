import { useState, useCallback } from 'react';

/**
 * useAgents - React hook for interacting with agent service
 *
 * Provides:
 * - Agent spawning (Explore, Plan, General)
 * - Status checking
 * - Session management
 * - Error handling
 */
const useAgents = () => {
  const [activeAgents, setActiveAgents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const API_BASE = 'http://localhost:8000/api';

  /**
   * Spawn an Explore agent to search codebase
   */
  const spawnExploreAgent = useCallback(async (prompt, thoroughness = 'medium', context = null) => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/agents/explore`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt,
          thoroughness,
          context
        })
      });

      if (!response.ok) {
        throw new Error(`Failed to spawn Explore agent: ${response.statusText}`);
      }

      const data = await response.json();

      // Add to active agents
      setActiveAgents(prev => [...prev, data]);

      return data;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Spawn a Plan agent to design configurations
   */
  const spawnPlanAgent = useCallback(async (prompt, requirements = null) => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/agents/plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt,
          requirements
        })
      });

      if (!response.ok) {
        throw new Error(`Failed to spawn Plan agent: ${response.statusText}`);
      }

      const data = await response.json();

      // Add to active agents
      setActiveAgents(prev => [...prev, data]);

      return data;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Spawn a General-Purpose agent for troubleshooting
   */
  const spawnGeneralAgent = useCallback(async (prompt, taskType = 'troubleshoot', context = null) => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/agents/general`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt,
          task_type: taskType,
          context
        })
      });

      if (!response.ok) {
        throw new Error(`Failed to spawn General agent: ${response.statusText}`);
      }

      const data = await response.json();

      // Add to active agents
      setActiveAgents(prev => [...prev, data]);

      return data;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Get status of a specific agent
   */
  const getAgentStatus = useCallback(async (agentId) => {
    try {
      const response = await fetch(`${API_BASE}/agents/${agentId}`);

      if (!response.ok) {
        throw new Error(`Failed to get agent status: ${response.statusText}`);
      }

      const data = await response.json();

      // Update in active agents list
      setActiveAgents(prev =>
        prev.map(agent => agent.agent_id === agentId ? data : agent)
      );

      return data;
    } catch (err) {
      setError(err.message);
      throw err;
    }
  }, []);

  /**
   * List all active agents
   */
  const listActiveAgents = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/agents`);

      if (!response.ok) {
        throw new Error(`Failed to list agents: ${response.statusText}`);
      }

      const data = await response.json();

      if (data.success && data.agents) {
        setActiveAgents(data.agents);
      }

      return data.agents || [];
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Clear error state
   */
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  /**
   * Remove agent from local state
   */
  const removeAgent = useCallback((agentId) => {
    setActiveAgents(prev => prev.filter(agent => agent.agent_id !== agentId));
  }, []);

  return {
    // State
    activeAgents,
    loading,
    error,

    // Actions
    spawnExploreAgent,
    spawnPlanAgent,
    spawnGeneralAgent,
    getAgentStatus,
    listActiveAgents,
    clearError,
    removeAgent
  };
};

export default useAgents;
