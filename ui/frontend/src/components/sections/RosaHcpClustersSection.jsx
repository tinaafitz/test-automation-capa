import React, { useState, useEffect, useCallback, useRef } from 'react';
import PropTypes from 'prop-types';
import {
  useApp,
  useAppDispatch,
  useApiStatusContext,
  useRecentOperationsContext,
} from '../../store/AppContext';
import { AppActionTypes } from '../../store/AppContext';
import {
  ChartBarIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  ArrowPathIcon,
  TrashIcon,
  ChevronUpDownIcon,
} from '@heroicons/react/24/outline';
import {
  buildApiUrl,
  API_ENDPOINTS,
  validateApiResponse,
  extractSafeErrorMessage,
} from '../../config/api';
import ProvisionFailureAgentPanel from '../agents/ProvisionFailureAgentPanel';

const RosaHcpClustersSection = ({ theme = 'mce' }) => {
  const app = useApp();
  const dispatch = useAppDispatch();
  const apiStatus = useApiStatusContext();
  const recentOps = useRecentOperationsContext();
  const { ocpStatus } = apiStatus;
  const { addToRecent, updateRecentOperationStatus } = recentOps;

  // Get theme colors
  const getThemeColors = () => {
    switch (theme) {
      case 'minikube':
        return {
          headerGradient: 'from-purple-600 to-violet-600',
          hoverGradient: 'hover:from-purple-700 hover:to-violet-700',
          border: 'border-purple-200',
          lightBg: 'from-purple-50 to-violet-50',
          lightBorder: 'border-purple-200',
          buttonBg: '#8B5CF6', // purple-600
          buttonBgHover: '#7C3AED', // purple-700
        };
      case 'mce':
      default:
        return {
          headerGradient: 'from-cyan-600 to-blue-600',
          hoverGradient: 'hover:from-cyan-700 hover:to-blue-700',
          border: 'border-cyan-200',
          lightBg: 'from-cyan-50 to-blue-50',
          lightBorder: 'border-cyan-200',
          buttonBg: '#2684FF', // blue
          buttonBgHover: '#0065FF', // darker blue
        };
    }
  };

  const colors = getThemeColors();

  // Cluster monitoring state
  const [clusters, setClusters] = useState([]);
  const [clustersLoading, setClustersLoading] = useState(false);
  const [clustersError, setClustersError] = useState(null);

  // Sort state
  const [sortField, setSortField] = useState('created');
  const [sortDirection, setSortDirection] = useState('desc');

  // Deletion state
  const [deletionResults, setDeletionResults] = useState(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [copySuccess, setCopySuccess] = useState('');
  const [clusterPendingDeletion, setClusterPendingDeletion] = useState(null);
  const [expandedAgentRows, setExpandedAgentRows] = useState({});

  // AbortController for canceling polling on unmount
  const deletionAbortController = useRef(null);
  // Track active delete job ID so we can resume on remount
  const activeDeleteJobId = useRef(null);

  // Cluster section state
  const getClusterSectionCollapsedState = () => {
    const sectionId = 'capi-rosa-hcp-clusters';
    return app.collapsedSections?.has(sectionId) || false;
  };

  const toggleClusterSection = () => {
    const sectionId = 'capi-rosa-hcp-clusters';
    dispatch({ type: AppActionTypes.TOGGLE_SECTION, payload: sectionId });
  };

  // Fetch clusters function
  const fetchClusters = useCallback(async () => {
    setClustersLoading(true);
    setClustersError(null);
    try {
      // Use different endpoints based on theme
      let response;
      let data;

      if (theme === 'minikube') {
        // For Minikube, get active resources from saved Minikube cluster
        const credResponse = await fetch(buildApiUrl('/api/credentials'));
        const credData = await credResponse.json();
        const clusterName = credData.credentials?.minikubeCluster || credData.credentials?.clusterName || 'sat-minikube-test';

        response = await fetch(buildApiUrl('/api/minikube/get-active-resources'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            cluster_name: clusterName,
            namespace: 'ns-rosa-hcp'
          }),
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        data = await response.json();

        // Extract RosaControlPlane resources (actual ROSA HCP clusters)
        if (data.success && Array.isArray(data.resources)) {
          const rosaHcpClusters = data.resources
            .filter(r => r.type === 'ROSAControlPlane')
            .map(r => ({
              name: r.name,
              namespace: r.namespace || 'ns-rosa-hcp',
              status: r.status || 'Unknown',
              version: r.version || 'N/A',
              age: r.age || 'N/A',
              region: 'us-west-2',
            }));
          setClusters(rosaHcpClusters);
        } else {
          setClusters([]);
        }
      } else {
        // For MCE, use the regular ROSA clusters endpoint and filter out minikube-provisioned clusters
        const credResponse = await fetch(buildApiUrl('/api/credentials'));
        const credData = await credResponse.json();
        const minikubeClusterName = credData.credentials?.minikubeCluster || credData.credentials?.clusterName || 'sat-minikube-test';

        const [rosaResponse, minikubeResponse] = await Promise.all([
          fetch(buildApiUrl(API_ENDPOINTS.ROSA_CLUSTERS)),
          fetch(buildApiUrl('/api/minikube/get-active-resources'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cluster_name: minikubeClusterName, namespace: 'ns-rosa-hcp' }),
          }).catch(() => null),
        ]);

        if (!rosaResponse.ok) {
          throw new Error(`HTTP ${rosaResponse.status}: ${rosaResponse.statusText}`);
        }

        data = await rosaResponse.json();
        const validatedData = validateApiResponse(data, ['success']);

        // Get minikube cluster names to exclude
        let minikubeClusterNames = [];
        if (minikubeResponse && minikubeResponse.ok) {
          try {
            const minikubeData = await minikubeResponse.json();
            if (minikubeData.success && Array.isArray(minikubeData.resources)) {
              minikubeClusterNames = minikubeData.resources
                .filter(r => r.type === 'ROSAControlPlane')
                .map(r => r.name);
            }
          } catch (e) { /* ignore minikube fetch errors */ }
        }

        if (validatedData.success) {
          const clusterList = Array.isArray(validatedData.clusters) ? validatedData.clusters : [];
          // Filter out minikube-provisioned clusters
          const mceOnlyClusters = minikubeClusterNames.length > 0
            ? clusterList.filter(c => !minikubeClusterNames.includes(c.name))
            : clusterList;
          setClusters(mceOnlyClusters);
        } else {
          throw new Error(validatedData.message || 'API returned failure status');
        }
      }
    } catch (error) {
      const safeErrorMessage = extractSafeErrorMessage(error);
      setClustersError(safeErrorMessage);
    } finally {
      setClustersLoading(false);
    }
    // eslint-disable-next-line
  }, []);

  // Copy handler for playbook output
  const handleCopyOutput = (text) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopySuccess('Copied!');
      setTimeout(() => setCopySuccess(''), 2000);
    }).catch(err => {
      console.error('Failed to copy text: ', err);
      setCopySuccess('Failed to copy');
      setTimeout(() => setCopySuccess(''), 2000);
    });
  };

  // Show delete confirmation
  const handleDeleteCluster = (clusterName, namespace) => {
    setClusterPendingDeletion({ name: clusterName, namespace });
  };

  // Actually execute the deletion after confirmation
  const executeDeleteCluster = async (clusterName, namespace) => {
    const deleteId = `delete-cluster-${Date.now()}`;

    // Clear the pending deletion
    setClusterPendingDeletion(null);

    // Clear previous results and set loading state
    setDeletionResults(null);
    setIsDeleting(true);

    // Create abort controller for this deletion operation
    const controller = new AbortController();
    deletionAbortController.current = controller;

    try {
      console.log(`🗑️ Deleting cluster: ${clusterName} in namespace: ${namespace}`);

      // Immediately show "Starting..." state
      setDeletionResults({
        success: true,
        timestamp: new Date().toISOString(),
        clusterName,
        output: `🚀 Starting deletion for ${clusterName}...\n\nInitializing ROSA HCP cluster deletion...\nCluster: ${clusterName}\nNamespace: ${namespace}\n\nConnecting to backend...`,
      });

      // Add to recent operations
      addToRecent({
        id: deleteId,
        title: `🗑️ Delete ROSA HCP Cluster: ${clusterName}`,
        color: 'bg-red-600',
        status: '🚀 Starting deletion...',
        environment: 'mce',
        playbook: 'playbooks/delete_rosa_hcp_cluster.yml',
        output: `Initializing ROSA HCP cluster deletion...\nCluster: ${clusterName}\nNamespace: ${namespace}\n\nConnecting to backend...`,
      });

      // For Minikube, get the cluster context so the delete playbook targets
      // the correct cluster instead of logging into the MCE hub.
      let clusterContext = null;
      if (theme === 'minikube') {
        try {
          const credResponse = await fetch(buildApiUrl('/api/credentials'));
          const credData = await credResponse.json();
          clusterContext = credData.credentials?.minikubeCluster || credData.credentials?.clusterName || null;
        } catch (e) {
          console.warn('Could not fetch minikube cluster context:', e);
        }
      }

      // Call Ansible playbook endpoint
      const deleteExtraVars = {
        cluster_name: clusterName,
        capi_namespace: namespace || 'ns-rosa-hcp',
      };
      if (clusterContext) {
        deleteExtraVars.cluster_context = clusterContext;
      }

      const response = await fetch(buildApiUrl(API_ENDPOINTS.ANSIBLE_RUN_PLAYBOOK), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          playbook: 'playbooks/delete_rosa_hcp_cluster.yml',
          description: `Delete ROSA HCP Cluster: ${clusterName}`,
          extra_vars: deleteExtraVars,
        }),
      });

      const result = await response.json();
      console.log('📊 Delete API response:', result);

      if (!result.success || !result.job_id) {
        throw new Error(result.message || 'Failed to start deletion');
      }

      const jobId = result.job_id;
      activeDeleteJobId.current = jobId;
      console.log(`🔍 Polling job status for job_id: ${jobId}`);

      // Poll for job completion
      const pollJobStatus = async () => {
        const maxAttempts = 4800; // 80 minutes max (23 min RCP + 33 min Network + 13 min RoleConfig + overhead)
        let attempts = 0;

        while (attempts < maxAttempts) {
          // Check if aborted
          if (controller.signal.aborted) {
            console.log('⏹️ Polling canceled - component unmounted');
            return;
          }

          attempts++;
          console.log(`📡 Polling attempt ${attempts}/${maxAttempts}`);

          try {
            // Add abort signal to fetch requests
            const jobResponse = await fetch(buildApiUrl(`/api/jobs/${jobId}`), {
              signal: controller.signal
            });
            const jobData = await jobResponse.json();
            console.log(`📋 Job status:`, jobData);

            // Fetch logs and agent stats for real-time output
            const [logsResponse, agentResponse] = await Promise.all([
              fetch(buildApiUrl(`/api/jobs/${jobId}/logs`), { signal: controller.signal }),
              fetch(buildApiUrl(`/api/jobs/${jobId}/agent-stats`), { signal: controller.signal }).catch(() => null),
            ]);
            const logsData = await logsResponse.json();
            const currentOutput = logsData.logs ? logsData.logs.join('\n') : '';
            const agentStats = agentResponse ? await agentResponse.json().catch(() => null) : null;

            if (jobData.status === 'completed') {
              // Success - re-fetch agent stats after a short delay to ensure
              // any in-flight remediation has finished recording its results
              await new Promise(resolve => setTimeout(resolve, 2000));
              const finalAgentResponse = await fetch(buildApiUrl(`/api/jobs/${jobId}/agent-stats`)).catch(() => null);
              const finalAgentStats = finalAgentResponse ? await finalAgentResponse.json().catch(() => null) : null;
              const finalStats = finalAgentStats?.agent_stats || agentStats?.agent_stats || null;

              const output = currentOutput || 'Deletion completed successfully';

              updateRecentOperationStatus(deleteId, '✅ Cluster deleted successfully!', output, { agentStats: finalStats });
              const successResults = {
                success: true,
                timestamp: new Date().toISOString(),
                clusterName,
                output,
                agentStats: finalStats,
              };
              console.log('✅ Setting deletion results (success):', successResults);
              setDeletionResults(successResults);
              setIsDeleting(false);

              // Refresh cluster list
              await fetchClusters();
              return;
            } else if (jobData.status === 'failed') {
              // Failure - update with error logs
              const output = currentOutput || (jobData.error || jobData.message || 'Deletion failed');

              updateRecentOperationStatus(deleteId, '❌ Deletion failed', output, { agentStats: agentStats?.agent_stats || null });
              const failureResults = {
                success: false,
                timestamp: new Date().toISOString(),
                clusterName,
                output,
                agentStats: agentStats?.agent_stats || null,
              };
              console.log('❌ Setting deletion results (failure):', failureResults);
              setDeletionResults(failureResults);
              setIsDeleting(false);
              return;
            }

            // Still running - update with current logs every poll
            if (currentOutput) {
              updateRecentOperationStatus(deleteId, '🗑️ Deleting...', currentOutput, { agentStats: agentStats?.agent_stats || null });
              // Also update the inline display with agent stats
              setDeletionResults({
                success: true,
                timestamp: new Date().toISOString(),
                clusterName,
                output: currentOutput,
                agentStats: agentStats?.agent_stats || null,
                isRunning: true,
              });
            }

            // Use abortable timeout
            await new Promise((resolve, reject) => {
              const timeoutId = setTimeout(resolve, 1000);
              controller.signal.addEventListener('abort', () => {
                clearTimeout(timeoutId);
                reject(new DOMException('Aborted', 'AbortError'));
              });
            });

          } catch (error) {
            if (error.name === 'AbortError') {
              console.log('⏹️ Fetch aborted');
              return;
            }
            throw error;
          }
        }

        // Timeout
        throw new Error('Deletion timed out after 80 minutes');
      };

      await pollJobStatus();

    } catch (error) {
      if (error.name === 'AbortError') {
        console.log('⏹️ Deletion polling canceled');
        return;
      }
      console.error('Deletion error:', error);
      const errorMsg = extractSafeErrorMessage(error);
      updateRecentOperationStatus(deleteId, '❌ Deletion error', errorMsg);
      setDeletionResults({
        success: false,
        timestamp: new Date().toISOString(),
        clusterName,
        output: errorMsg,
      });
      setIsDeleting(false);
    } finally {
      deletionAbortController.current = null;
      activeDeleteJobId.current = null;
    }
  };

  // Auto-fetch clusters on mount
  useEffect(() => {
    fetchClusters();
  }, [fetchClusters]);

  // Resume polling for any running delete jobs on mount/remount
  useEffect(() => {
    const resumeDeletePolling = async () => {
      try {
        const response = await fetch(buildApiUrl('/api/jobs'));
        const data = await response.json();
        const jobs = data.jobs || [];

        // Find any running delete job
        const runningDelete = jobs.find(
          (j) => j.status === 'running' && j.description && j.description.includes('Delete ROSA HCP')
        );

        if (runningDelete) {
          const jobId = runningDelete.id;
          const clusterName = runningDelete.description.replace('Delete ROSA HCP Cluster: ', '');
          console.log(`🔄 Resuming delete polling for ${clusterName} (job: ${jobId})`);

          activeDeleteJobId.current = jobId;
          setIsDeleting(true);

          const controller = new AbortController();
          deletionAbortController.current = controller;

          // Start polling loop
          // Find the matching recent operation for this deletion
          const matchingOp = (recentOps.recentOperations || []).find(
            (op) => op.title && op.title.includes(clusterName) && op.title.includes('Delete')
          );
          const resumeDeleteId = matchingOp?.id;

          const poll = async () => {
            let resumeAttempts = 0;
            const maxResumeAttempts = 4800; // 80 minutes max
            while (!controller.signal.aborted && resumeAttempts < maxResumeAttempts) {
              resumeAttempts++;
              try {
                const [logsRes, agentRes, jobRes] = await Promise.all([
                  fetch(buildApiUrl(`/api/jobs/${jobId}/logs`), { signal: controller.signal }),
                  fetch(buildApiUrl(`/api/jobs/${jobId}/agent-stats`), { signal: controller.signal }).catch(() => null),
                  fetch(buildApiUrl(`/api/jobs/${jobId}`), { signal: controller.signal }),
                ]);
                const logsData = await logsRes.json();
                const agentStats = agentRes ? await agentRes.json().catch(() => null) : null;
                const jobData = await jobRes.json();
                const currentOutput = logsData.logs ? logsData.logs.join('\n') : '';

                const isDone = jobData.status === 'completed' || jobData.status === 'failed';
                const stats = agentStats?.agent_stats || null;

                setDeletionResults({
                  success: jobData.status !== 'failed',
                  timestamp: new Date().toISOString(),
                  clusterName,
                  output: currentOutput || 'Waiting for output...',
                  agentStats: stats,
                  isRunning: !isDone,
                });

                // Update Task Summary with agent stats
                // Re-lookup the operation each poll in case it wasn't available at resume start
                const opId = resumeDeleteId || (recentOps.recentOperations || []).find(
                  (op) => op.title && op.title.includes(clusterName) && op.title.includes('Delete')
                )?.id;
                if (opId) {
                  const status = isDone
                    ? (jobData.status === 'completed' ? '✅ Cluster deleted successfully!' : '❌ Deletion failed')
                    : '🗑️ Deleting...';
                  updateRecentOperationStatus(opId, status, currentOutput, { agentStats: stats });
                }

                if (isDone) {
                  setIsDeleting(false);
                  activeDeleteJobId.current = null;
                  deletionAbortController.current = null;
                  if (jobData.status === 'completed') {
                    await fetchClusters();
                  }
                  return;
                }

                await new Promise((resolve) => setTimeout(resolve, 2000));
              } catch (err) {
                if (err.name === 'AbortError') return;
                console.error('Resume polling error:', err);
                return;
              }
            }
          };

          poll();
        }
      } catch (err) {
        console.error('Failed to check for running delete jobs:', err);
      }
    };

    resumeDeletePolling();
    // eslint-disable-next-line
  }, []);

  // Clear clusters when connection is lost
  useEffect(() => {
    if (ocpStatus && !ocpStatus.connected) {
      setClusters([]);
      setClustersError(null);
    }
  }, [ocpStatus?.connected]);

  // Cleanup on component unmount - abort any active deletion polling
  useEffect(() => {
    return () => {
      if (deletionAbortController.current) {
        console.log('🧹 Cleaning up: Aborting active deletion polling');
        deletionAbortController.current.abort();
      }
    };
  }, []);

  // Format date for display
  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { day: '2-digit', month: 'short', year: 'numeric' });
  };

  // Handle sort
  const handleSort = (field) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  // Sort clusters
  const sortedClusters = [...clusters].sort((a, b) => {
    let aVal = a[sortField];
    let bVal = b[sortField];

    if (sortField === 'created') {
      aVal = new Date(aVal || 0).getTime();
      bVal = new Date(bVal || 0).getTime();
    } else if (sortField === 'region') {
      aVal = aVal || '';
      bVal = bVal || '';
    } else {
      aVal = String(aVal || '').toLowerCase();
      bVal = String(bVal || '').toLowerCase();
    }

    if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
    if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
    return 0;
  });

  // Render sort header
  const SortHeader = ({ field, children }) => (
    <th
      scope="col"
      className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 select-none"
      onClick={() => handleSort(field)}
    >
      <div className="flex items-center gap-1">
        {children}
        <ChevronUpDownIcon className={`h-4 w-4 ${sortField === field ? 'text-blue-600' : 'text-gray-400'}`} />
      </div>
    </th>
  );

  return (
    <div className="space-y-6">
      {/* Title and Refresh Button */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-blue-900">ROSA HCP Clusters</h2>
        <button
          onClick={fetchClusters}
          disabled={clustersLoading}
          className="px-4 py-2 text-white rounded transition-colors disabled:opacity-50 font-medium flex items-center gap-2"
          style={!clustersLoading ? { backgroundColor: colors.buttonBg } : {}}
          onMouseEnter={(e) => !clustersLoading && (e.currentTarget.style.backgroundColor = colors.buttonBgHover)}
          onMouseLeave={(e) => !clustersLoading && (e.currentTarget.style.backgroundColor = colors.buttonBg)}
        >
          <ArrowPathIcon className={`h-4 w-4 ${clustersLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
        {/* Cluster Table */}
        {clustersError ? (
          <div className="text-center py-8 text-red-600 p-6">
            <p className="text-sm">Failed to load clusters</p>
            <p className="text-xs mt-2">{clustersError}</p>
          </div>
        ) : clustersLoading ? (
          <div className="text-center py-8 text-gray-500 p-6">
            <ArrowPathIcon className="h-8 w-8 animate-spin mx-auto mb-2" />
            <p className="text-sm">Loading clusters...</p>
          </div>
        ) : clusters.length === 0 ? (
          <div className="text-center py-8 text-gray-500 p-6">
            <p className="text-sm">No ROSA HCP clusters found</p>
            <p className="text-xs mt-2">Clusters will appear here when provisioned</p>
          </div>
        ) : (
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <SortHeader field="name">Name</SortHeader>
                <SortHeader field="status">Status</SortHeader>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Type
                </th>
                <SortHeader field="created">Created</SortHeader>
                <SortHeader field="version">Version</SortHeader>
                <SortHeader field="region">Provider (Region)</SortHeader>
                <th scope="col" className="relative px-6 py-3">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {sortedClusters.map((cluster, idx) => (
                <tr key={cluster.name || idx} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <a href="#" className="text-sm font-medium text-blue-600 hover:text-blue-800">
                      {cluster.name}
                    </a>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center gap-1.5">
                      <span className={`inline-block w-2 h-2 rounded-full ${
                        cluster.status === 'ready' ? 'bg-green-500' :
                        cluster.status === 'provisioning' ? 'bg-yellow-500 animate-pulse' :
                        'bg-red-500'
                      }`}></span>
                      <span className="text-sm text-gray-900 capitalize">{cluster.status}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    ROSA
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    {formatDate(cluster.created)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    {cluster.version || 'N/A'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    AWS ({cluster.region})
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button
                      onClick={() => handleDeleteCluster(cluster.name, cluster.namespace)}
                      className="text-gray-400 hover:text-red-600"
                      title={`Delete cluster ${cluster.name}`}
                    >
                      <TrashIcon className="h-5 w-5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Delete Confirmation Modal/Panel - Outside table */}
      {clusterPendingDeletion && (
        <div className="mt-4">
          <div className="bg-red-50 border border-red-300 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <span className="text-2xl">⚠️</span>
              <div className="flex-1">
                <h4 className="font-semibold text-red-900 mb-2">
                  Confirm Deletion
                </h4>
                <p className="text-sm text-red-800 mb-4">
                  Are you sure you want to delete cluster <strong>{clusterPendingDeletion.name}</strong>?
                  This action cannot be undone and will remove all associated resources.
                </p>
                <div className="flex gap-3">
                  <button
                    onClick={() => executeDeleteCluster(clusterPendingDeletion.name, clusterPendingDeletion.namespace)}
                    className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-md transition-colors font-medium text-sm"
                  >
                    Yes, Delete Cluster
                  </button>
                  <button
                    onClick={() => setClusterPendingDeletion(null)}
                    className="px-4 py-2 bg-gray-200 hover:bg-gray-300 text-gray-800 rounded-md transition-colors font-medium text-sm"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Deletion Results Display - Inline Playbook Output */}
      {deletionResults && (
        <div className="mt-6 space-y-4">
          <div className={`rounded-lg border-2 p-6 ${isDeleting ? 'bg-blue-50 border-blue-300' : deletionResults.success ? 'bg-green-50 border-green-300' : 'bg-red-50 border-red-300'}`}>
            <div className="flex items-center gap-3 mb-4">
              {deletionResults.success ? (
                <span className="text-2xl">✅</span>
              ) : (
                <span className="text-xl">❌</span>
              )}
              <h3 className="text-lg font-semibold text-gray-900">
                {isDeleting ? `Deleting ${deletionResults.clusterName}...` : deletionResults.success ? 'Deletion Completed' : 'Deletion Failed'}
              </h3>
            </div>

            {/* AI Agent Summary */}
            {deletionResults.agentStats?.enabled && (
              <div className={`mb-4 rounded-lg p-3 text-sm ${
                deletionResults.agentStats.issues_detected > 0
                  ? 'bg-yellow-50 border border-yellow-300'
                  : 'bg-gray-50 border border-gray-200'
              }`}>
                <div className="flex items-center gap-4 mb-2">
                  <span className="font-medium text-gray-700">
                    {deletionResults.agentStats.issues_detected > 0 ? '\uD83E\uDD16' : '\uD83D\uDEE1\uFE0F'} AI Agent
                    {deletionResults.isRunning ? ': Monitoring' : ': Summary'}
                  </span>
                  <span>Resources: {deletionResults.agentStats.issues_detected}</span>
                  <span>Fixes: {deletionResults.agentStats.interventions}</span>
                  {deletionResults.agentStats.total_checks > 0 && (
                    <span className="text-gray-500">({deletionResults.agentStats.total_checks} checks)</span>
                  )}
                  {deletionResults.agentStats.interventions > 0 ? (
                    <span className="text-green-700 font-medium">
                      Agent auto-fixed {deletionResults.agentStats.interventions} issue(s)
                    </span>
                  ) : deletionResults.agentStats.issues_detected > 0 ? (
                    <span className="text-green-700 font-medium">
                      Agent monitored {deletionResults.agentStats.issues_detected} resource(s) — all deleted cleanly
                    </span>
                  ) : null}
                </div>
                {/* Per-resource agent activity details */}
                {deletionResults.agentStats.resource_details?.length > 0 && !deletionResults.isRunning && (
                  <div className="mt-2 pt-2 border-t border-yellow-200 space-y-1">
                    {deletionResults.agentStats.resource_details.map((detail, idx) => {
                      const statusIcon = detail.status === 'resolved' ? '\u2705'
                        : detail.status === 'failed' ? '\u26A0\uFE0F'
                        : detail.status === 'detected' ? '\uD83D\uDD0D'
                        : '\u2139\uFE0F';
                      const issueLabel = detail.issue_type?.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) || 'Unknown';
                      const timeline = detail.timeline || [];
                      const actionLabels = {
                        remove_finalizers: 'Removed finalizers',
                        retry_cloudformation_delete: 'Cleaned up VPC dependencies',
                        log_and_continue: 'Monitored (waiting)',
                      };
                      // Show meaningful actions (skip repeated log_and_continue)
                      const meaningfulActions = [];
                      let waitCount = 0;
                      for (const entry of timeline) {
                        if (entry.action === 'log_and_continue') {
                          waitCount++;
                        } else {
                          if (waitCount > 0) {
                            meaningfulActions.push({ action: 'log_and_continue', count: waitCount });
                            waitCount = 0;
                          }
                          meaningfulActions.push(entry);
                        }
                      }
                      if (waitCount > 0) {
                        meaningfulActions.push({ action: 'log_and_continue', count: waitCount });
                      }
                      const isExpanded = expandedAgentRows[idx];
                      const actualFixes = meaningfulActions.filter(a => a.action !== 'log_and_continue' && !(a.result && a.result.includes('already deleted')));
                      const confirmations = meaningfulActions.filter(a => a.result && a.result.includes('already deleted'));
                      const fixCount = actualFixes.length;
                      const confirmCount = confirmations.length;
                      const totalChecks = timeline.length;
                      return (
                        <div key={idx} className="text-xs text-gray-600">
                          <div
                            className="flex items-start gap-2 cursor-pointer hover:bg-yellow-100 rounded px-1 py-0.5 -mx-1"
                            onClick={() => setExpandedAgentRows(prev => ({ ...prev, [idx]: !prev[idx] }))}
                          >
                            <span className="flex-shrink-0 text-gray-400 w-3">{isExpanded ? '\u25BC' : '\u25B6'}</span>
                            <span className="flex-shrink-0">{statusIcon}</span>
                            <div className="flex-1">
                              <span className="font-medium text-gray-700">{detail.resource_key}</span>
                              <span className="mx-1">&mdash;</span>
                              <span>{issueLabel}</span>
                              <span className="ml-2 text-gray-400">
                                ({totalChecks} check{totalChecks !== 1 ? 's' : ''}{fixCount > 0 ? `, ${fixCount} fix${fixCount !== 1 ? 'es' : ''}` : ''}{confirmCount > 0 && fixCount === 0 ? ', confirmed deleted' : ''})
                              </span>
                            </div>
                          </div>
                          {isExpanded && (
                            <div className="ml-7 mt-1 mb-2 space-y-0.5">
                              {detail.diagnosis && (
                                <div className="text-gray-500 italic mb-1">Diagnosis: {detail.diagnosis}</div>
                              )}
                              {timeline.map((entry, i) => {
                                const isAlreadyDeleted = entry.result && entry.result.includes('already deleted');
                                const rawLabel = actionLabels[entry.action] || entry.action || 'Check';
                                const actionLabel = isAlreadyDeleted ? 'Confirmed deleted' : rawLabel;
                                const isWait = entry.action === 'log_and_continue';
                                const timestamp = entry.time ? new Date(entry.time).toLocaleTimeString() : '';
                                const confidence = entry.confidence ? `${Math.round(entry.confidence * 100)}%` : '';
                                return (
                                  <div key={i} className={`flex flex-col ${isWait ? 'text-gray-400' : 'text-gray-600'}`}>
                                    <div className="flex items-start gap-1">
                                      <span className="text-gray-300 flex-shrink-0">{'\u2192'}</span>
                                      {timestamp && <span className="text-gray-400 flex-shrink-0 font-mono">{timestamp}</span>}
                                      <span className={isWait ? '' : 'text-green-700 font-medium'}>
                                        {actionLabel}
                                      </span>
                                      {confidence && !isWait && (
                                        <span className="text-gray-400 ml-1">[{confidence}]</span>
                                      )}
                                    </div>
                                    {entry.detail && !entry.detail.includes('no intervention') && (
                                      <div className="ml-5 text-gray-400 break-all">{entry.detail}</div>
                                    )}
                                    {entry.result && (
                                      <div className="ml-5 text-green-600 break-all">{entry.result}</div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {/* Output Display */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-sm font-medium text-gray-700">Playbook Output:</h4>
                <button
                  onClick={() => handleCopyOutput(deletionResults.output || 'No output available')}
                  className="px-3 py-1 text-white rounded text-xs font-medium transition-colors"
                  style={{ backgroundColor: colors.buttonBg }}
                  onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = colors.buttonBgHover)}
                  onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = colors.buttonBg)}
                >
                  {copySuccess || '📋 Copy'}
                </button>
              </div>
              <div className="bg-gray-900 text-gray-100 rounded p-4 max-h-96 overflow-y-auto font-mono text-sm">
                <pre className="whitespace-pre-wrap">
                  {deletionResults.output || 'No output available'}
                </pre>
              </div>
            </div>
          </div>

          {/* AI Agent Panel - Show when deletion fails */}
          {!deletionResults.success && !isDeleting && (
            <ProvisionFailureAgentPanel
              clusterName={deletionResults.clusterName}
              errorMessage="Cluster deletion failed"
              errorLogs={deletionResults.output || ''}
              onRetry={() => executeDeleteCluster(deletionResults.clusterName, 'ns-rosa-hcp')}
              onClose={() => setDeletionResults(null)}
              addToRecentOperations={addToRecent}
            />
          )}
        </div>
      )}
    </div>
  );
};

RosaHcpClustersSection.propTypes = {
  theme: PropTypes.string,
};

export default RosaHcpClustersSection;
