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
            namespace: 'default'  // Default namespace for scanning
          }),
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        data = await response.json();

        // Extract RosaControlPlane resources (actual ROSA HCP clusters)
        if (data.success && Array.isArray(data.resources)) {
          const rosaHcpClusters = data.resources
            .filter(r => r.type === 'RosaControlPlane')
            .map(r => ({
              name: r.name,
              namespace: r.namespace || 'ns-rosa-hcp',
              status: r.status || 'Unknown',
              version: r.version || 'N/A',
              age: r.age || 'N/A',
              region: 'us-west-2', // Minikube clusters are in us-west-2
            }));
          setClusters(rosaHcpClusters);
        } else {
          setClusters([]);
        }
      } else {
        // For MCE, use the regular ROSA clusters endpoint
        response = await fetch(buildApiUrl(API_ENDPOINTS.ROSA_CLUSTERS));

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        data = await response.json();
        const validatedData = validateApiResponse(data, ['success']);

        if (validatedData.success) {
          const clusterList = Array.isArray(validatedData.clusters) ? validatedData.clusters : [];
          setClusters(clusterList);
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

      // Call Ansible playbook endpoint
      const response = await fetch(buildApiUrl(API_ENDPOINTS.ANSIBLE_RUN_PLAYBOOK), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          playbook: 'playbooks/delete_rosa_hcp_cluster.yml',
          description: `Delete ROSA HCP Cluster: ${clusterName}`,
          extra_vars: {
            cluster_name: clusterName,
            capi_namespace: namespace || 'ns-rosa-hcp',
          },
        }),
      });

      const result = await response.json();
      console.log('📊 Delete API response:', result);

      if (!result.success || !result.job_id) {
        throw new Error(result.message || 'Failed to start deletion');
      }

      const jobId = result.job_id;
      console.log(`🔍 Polling job status for job_id: ${jobId}`);

      // Poll for job completion
      const pollJobStatus = async () => {
        const maxAttempts = 2100; // 35 minutes max (20 min RCP + 15 min Network)
        let attempts = 0;

        while (attempts < maxAttempts) {
          attempts++;
          console.log(`📡 Polling attempt ${attempts}/${maxAttempts}`);

          const jobResponse = await fetch(buildApiUrl(`/api/jobs/${jobId}`));
          const jobData = await jobResponse.json();
          console.log(`📋 Job status:`, jobData);

          // Fetch logs regardless of status to show real-time output
          const logsResponse = await fetch(buildApiUrl(`/api/jobs/${jobId}/logs`));
          const logsData = await logsResponse.json();
          const currentOutput = logsData.logs ? logsData.logs.join('\n') : '';

          if (jobData.status === 'completed') {
            // Success - update with final logs
            const output = currentOutput || 'Deletion completed successfully';

            updateRecentOperationStatus(deleteId, '✅ Cluster deleted successfully!', output);
            const successResults = {
              success: true,
              timestamp: new Date().toISOString(),
              clusterName,
              output,
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

            updateRecentOperationStatus(deleteId, '❌ Deletion failed', output);
            const failureResults = {
              success: false,
              timestamp: new Date().toISOString(),
              clusterName,
              output,
            };
            console.log('❌ Setting deletion results (failure):', failureResults);
            setDeletionResults(failureResults);
            setIsDeleting(false);
            return;
          }

          // Still running - update with current logs every 5 seconds
          if (attempts % 5 === 0 && currentOutput) {
            updateRecentOperationStatus(deleteId, '🗑️ Deleting...', currentOutput);
            // Also update the inline display
            setDeletionResults({
              success: true,
              timestamp: new Date().toISOString(),
              clusterName,
              output: currentOutput,
            });
          }

          // Wait and poll again
          await new Promise((resolve) => setTimeout(resolve, 1000)); // Wait 1 second
        }

        // Timeout
        throw new Error('Deletion timed out after 35 minutes');
      };

      await pollJobStatus();

    } catch (error) {
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
    }
  };

  // Auto-fetch clusters on mount
  useEffect(() => {
    fetchClusters();
  }, [fetchClusters]);

  // Clear clusters when connection is lost
  useEffect(() => {
    if (ocpStatus && !ocpStatus.connected) {
      setClusters([]);
      setClustersError(null);
    }
  }, [ocpStatus?.connected]);

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
          <div className={`rounded-lg border-2 p-6 ${deletionResults.success ? 'bg-green-50 border-green-300' : 'bg-red-50 border-red-300'}`}>
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
