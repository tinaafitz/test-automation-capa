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
  StarIcon,
  CheckCircleIcon,
  XCircleIcon,
  ExclamationTriangleIcon,
  ArrowTopRightOnSquareIcon,
} from '@heroicons/react/24/outline';
import {
  buildApiUrl,
  API_ENDPOINTS,
  validateApiResponse,
  extractSafeErrorMessage,
} from '../../config/api';
import ProvisionFailureAgentPanel from '../agents/ProvisionFailureAgentPanel';
import DiagnosticsPanel from '../DiagnosticsPanel';
import {
  derivePhases,
  parseHubSuccess,
  HubPhaseList,
  HubPhaseMinimap,
  HubLogTerminal,
} from './mceHubProgress';

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

  // "Make this my MCE hub" state (mirrors the deletion state block above)
  const [clusterPendingHub, setClusterPendingHub] = useState(null); // cluster row awaiting config/preflight
  const [hubConfig, setHubConfig] = useState(null);                 // editable extra_vars for the pending hub
  const [hubResults, setHubResults] = useState(null);              // running/success/fail results card state
  const [isBuildingHub, setIsBuildingHub] = useState(false);
  const [hubStartedAt, setHubStartedAt] = useState(null);          // ms epoch for elapsed timer
  const [hubElapsed, setHubElapsed] = useState(0);                 // seconds elapsed (drives ⏱)
  const [credsPreflight, setCredsPreflight] = useState(null);      // { ocm, aws } from /api/credentials
  const [buildingClusterName, setBuildingClusterName] = useState(null); // drives per-row "Building hub…" spinner (STATE, not ref)
  const hubAbortController = useRef(null);
  const activeHubJobId = useRef(null);        // the REAL backend job_id of the in-flight hub build (for direct cancel)
  const hubBuildingClusterName = useRef(null); // cluster identity of the in-flight build (separate from the job-id ref)
  const hubLaunchInFlight = useRef(false);    // synchronous single-flight lock (guards two fast clicks)
  const pendingHubCluster = useRef(null);     // tracks which cluster the creds preflight fetch is for (m3 guard)

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

  // ==========================================================================
  // "Make this my MCE hub" flow (modeled 1:1 on the delete flow above)
  // ==========================================================================

  // The only gate that enables the row button. Deeper creds check happens in
  // the pre-run panel, not on the row (so we don't block the row on async work).
  const isClusterReady = (cluster) => cluster?.status === 'ready';

  // Whether an mce_channel is a dev/RC channel that needs the acm-d pull secret.
  const isDevChannel = (channel) => /^stable-5/i.test(channel || '');

  // Open the pre-run config + preflight card for a cluster.
  const handleMakeHub = async (cluster) => {
    // Block opening/launching another card while one build is already in flight
    // (single-flight; opening cluster A's card must not race with a build).
    if (isBuildingHub || hubLaunchInFlight.current) return;

    // Mark which cluster this preflight fetch is for, so a late /api/credentials
    // response for a since-closed / different card is ignored (m3).
    pendingHubCluster.current = cluster.name;
    // Show the card immediately with a not-yet-verified preflight; the async
    // creds result fills it in below (guarded).
    setCredsPreflight(null);
    setHubConfig({
      cluster_name: cluster.name,
      capi_namespace: cluster.namespace || 'ns-rosa-hcp',
      minikube_context: 'minikube',
      mce_channel: 'stable-2.8',
    });
    setClusterPendingHub(cluster);

    // Prefill config from the row + credentials (minikube context default).
    let minikubeContext = 'minikube';
    let ocmOk = false;
    let awsOk = false;
    try {
      const credResponse = await fetch(buildApiUrl('/api/credentials'));
      const credData = await credResponse.json();
      const creds = credData.credentials || {};
      minikubeContext =
        creds.minikubeCluster || creds.clusterName || 'minikube';
      // Creds preflight: verify OCM + AWS values are present and non-placeholder.
      const nonEmpty = (v) =>
        typeof v === 'string' &&
        v.trim() !== '' &&
        !/placeholder|changeme|xxx/i.test(v);
      ocmOk = nonEmpty(creds.ocmClientId) && nonEmpty(creds.ocmClientSecret);
      awsOk =
        nonEmpty(creds.awsAccessKeyId) && nonEmpty(creds.awsSecretAccessKey);
    } catch (e) {
      console.warn('Could not fetch credentials for hub preflight:', e);
    }

    // Ignore the result if the pending cluster changed (card closed or a
    // different cluster's card opened) while this fetch was in flight.
    if (pendingHubCluster.current !== cluster.name) return;

    setCredsPreflight({ ocm: ocmOk, aws: awsOk });
    setHubConfig((c) =>
      c && c.cluster_name === cluster.name
        ? { ...c, minikube_context: minikubeContext }
        : c
    );
  };

  // Launch the hub build + poll the job (abortable, long budget) — mirrors
  // executeDeleteCluster.
  const executeMakeHub = async (cluster, cfg) => {
    // Synchronous single-flight lock at the TOP: guard re-entry so two fast
    // clicks (or A-then-B) can't both launch.
    if (hubLaunchInFlight.current || isBuildingHub) return;
    hubLaunchInFlight.current = true;

    const hubOpId = `make-hub-${Date.now()}`;
    const clusterName = cluster.name;

    // Close the config card and reset results.
    pendingHubCluster.current = null;
    setClusterPendingHub(null);
    setHubResults(null);
    setIsBuildingHub(true);
    setBuildingClusterName(clusterName);
    hubBuildingClusterName.current = clusterName;
    const startedAt = Date.now();
    setHubStartedAt(startedAt);
    setHubElapsed(0);

    const controller = new AbortController();
    hubAbortController.current = controller;

    try {
      // Immediately show a "Starting..." state.
      setHubResults({
        success: true,
        isRunning: true,
        timestamp: new Date().toISOString(),
        clusterName,
        output: `🚀 Starting MCE hub build for ${clusterName}...\n\nInstalling + configuring MultiCluster Engine and enabling CAPI/CAPA...\nCluster: ${clusterName}\nCAPI namespace: ${cfg.capi_namespace}\nMinikube context: ${cfg.minikube_context}\nMCE channel: ${cfg.mce_channel}\n\nConnecting to backend...`,
      });

      addToRecent({
        id: hubOpId,
        title: `★ Make MCE hub: ${clusterName}`,
        color: 'bg-purple-600',
        status: '🚀 Starting hub build...',
        environment: 'minikube',
        playbook: 'playbooks/install_mce_on_provisioned_cluster.yml',
        output: `Initializing MCE hub build...\nCluster: ${clusterName}\n\nConnecting to backend...`,
      });

      // The four suite-15 extra_vars — nothing else (mce_source_mode deferred).
      const extraVars = {
        cluster_name: cfg.cluster_name,
        capi_namespace: cfg.capi_namespace || 'ns-rosa-hcp',
        minikube_context: cfg.minikube_context || 'minikube',
        mce_channel: cfg.mce_channel || 'stable-2.8',
      };

      const response = await fetch(
        buildApiUrl(API_ENDPOINTS.ANSIBLE_RUN_PLAYBOOK),
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            playbook: 'playbooks/install_mce_on_provisioned_cluster.yml',
            description: `Make MCE hub: ${clusterName}`,
            extra_vars: extraVars,
          }),
        }
      );

      const result = await response.json();
      if (!result.success || !result.job_id) {
        throw new Error(result.message || 'Failed to start MCE hub build');
      }

      const jobId = result.job_id;
      activeHubJobId.current = jobId; // REAL backend job_id — Cancel POSTs directly to this

      // Poll for job completion with incremental log cursor.
      const pollJobStatus = async () => {
        // WALL-CLOCK budget: stop only when real elapsed time exceeds the
        // timeout, regardless of per-poll network latency. 150 min sits
        // comfortably above the 7200s/120min backend suite timeout.
        const TIMEOUT_MS = 150 * 60 * 1000;
        let logCursor = 0;
        let accumulatedLogs = [];

        while (Date.now() - startedAt <= TIMEOUT_MS) {
          if (controller.signal.aborted) return;

          try {
            const [jobResponse, logsResponse] = await Promise.all([
              fetch(buildApiUrl(`/api/jobs/${jobId}`), {
                signal: controller.signal,
              }),
              fetch(buildApiUrl(`/api/jobs/${jobId}/logs?since=${logCursor}`), {
                signal: controller.signal,
              }),
            ]);
            const jobData = await jobResponse.json();
            const logsData = await logsResponse.json();

            // Incremental cursor bookkeeping (mirrors WorkflowBuilder).
            if ((logsData.since ?? logCursor) === 0) {
              accumulatedLogs = [];
            }
            const newLines = (logsData.logs || []).filter((l) => l.trim());
            if (newLines.length > 0) {
              accumulatedLogs = accumulatedLogs.concat(newLines);
            }
            if (typeof logsData.total === 'number') {
              logCursor = logsData.total;
            }
            const currentOutput = accumulatedLogs.join('\n');

            // Terminal detection: anything that is NOT still-in-progress is
            // terminal. `completed` → success; any other terminal status
            // (failed / cancelled / error / unknown) → failure, with the
            // status surfaced in the error message.
            const status = jobData.status;
            const inProgress =
              status === 'running' ||
              status === 'pending' ||
              status === 'queued';

            if (!inProgress) {
              if (status === 'completed') {
                const output = currentOutput || 'MCE hub build completed.';
                const parsed = parseHubSuccess(output);
                updateRecentOperationStatus(
                  hubOpId,
                  '✅ MCE hub ready!',
                  output
                );
                setHubResults({
                  success: true,
                  isRunning: false,
                  timestamp: new Date().toISOString(),
                  clusterName,
                  output,
                  startedAt,
                  finishedAt: Date.now(),
                  ...parsed,
                });
                setIsBuildingHub(false);
                await fetchClusters();
                return;
              }
              // Non-completed terminal status → failure.
              const statusNote = `MCE hub build ended with status "${status}"`;
              const output =
                currentOutput ||
                jobData.error ||
                jobData.message ||
                statusNote;
              updateRecentOperationStatus(hubOpId, '❌ Hub build failed', output);
              setHubResults({
                success: false,
                isRunning: false,
                timestamp: new Date().toISOString(),
                clusterName,
                output: currentOutput ? output : statusNote,
                startedAt,
                finishedAt: Date.now(),
              });
              setIsBuildingHub(false);
              return;
            }

            // Still running — update live output every poll.
            updateRecentOperationStatus(
              hubOpId,
              '★ Building hub...',
              currentOutput
            );
            setHubResults({
              success: true,
              isRunning: true,
              timestamp: new Date().toISOString(),
              clusterName,
              output: currentOutput || 'Waiting for output...',
              startedAt,
            });

            // Abortable 3s wait (same interval as WorkflowBuilder).
            await new Promise((resolve, reject) => {
              const timeoutId = setTimeout(resolve, 3000);
              controller.signal.addEventListener('abort', () => {
                clearTimeout(timeoutId);
                reject(new DOMException('Aborted', 'AbortError'));
              });
            });
          } catch (error) {
            if (error.name === 'AbortError') return;
            throw error;
          }
        }

        throw new Error('MCE hub build timed out after 150 minutes');
      };

      await pollJobStatus();
    } catch (error) {
      if (error.name === 'AbortError') return;
      console.error('MCE hub build error:', error);
      const errorMsg = extractSafeErrorMessage(error);
      updateRecentOperationStatus(hubOpId, '❌ Hub build error', errorMsg);
      setHubResults({
        success: false,
        isRunning: false,
        timestamp: new Date().toISOString(),
        clusterName,
        output: errorMsg,
      });
      setIsBuildingHub(false);
    } finally {
      hubAbortController.current = null;
      activeHubJobId.current = null;
      hubBuildingClusterName.current = null;
      hubLaunchInFlight.current = false;
      setBuildingClusterName(null);
    }
  };

  // Auto-fetch clusters on mount + poll every 30 seconds
  useEffect(() => {
    fetchClusters();
    const interval = setInterval(fetchClusters, 30000);
    return () => clearInterval(interval);
  }, [fetchClusters]);

  // Live elapsed timer for the running hub build (⏱ in the progress card).
  useEffect(() => {
    if (!isBuildingHub || !hubStartedAt) return;
    const interval = setInterval(() => {
      setHubElapsed(Math.floor((Date.now() - hubStartedAt) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [isBuildingHub, hubStartedAt]);

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

  // Resume polling for any running MCE-hub build on mount/remount (matches on
  // the "Make MCE hub" description prefix) — mirrors the delete resume effect.
  useEffect(() => {
    const resumeHubPolling = async () => {
      try {
        const response = await fetch(buildApiUrl('/api/jobs'));
        const data = await response.json();
        const jobs = data.jobs || [];

        const HUB_PREFIX = 'Make MCE hub: ';
        // Only exact-prefixed descriptions with a non-empty cluster name; guard
        // against missing/oddly-formatted descriptions.
        const runningHubs = jobs.filter(
          (j) =>
            j.status === 'running' &&
            typeof j.description === 'string' &&
            j.description.startsWith(HUB_PREFIX) &&
            j.description.slice(HUB_PREFIX.length).trim() !== ''
        );

        if (runningHubs.length === 0) return;

        // Pick exactly ONE deterministically (most recently started, then by id)
        // so we never attach more than one poll loop.
        const runningHub = runningHubs.slice().sort((a, b) => {
          const at = a.started_at ? new Date(a.started_at).getTime() : 0;
          const bt = b.started_at ? new Date(b.started_at).getTime() : 0;
          if (bt !== at) return bt - at;
          return String(b.id).localeCompare(String(a.id));
        })[0];

        const jobId = runningHub.id;
        const clusterName = runningHub.description.slice(HUB_PREFIX.length).trim();

        // Use the discovered job's REAL job_id for cancel/poll.
        activeHubJobId.current = jobId;
        hubBuildingClusterName.current = clusterName;
        hubLaunchInFlight.current = true; // keep single-flight lock held while resumed build runs
        setIsBuildingHub(true);
        setBuildingClusterName(clusterName);
        const startedAt = runningHub.started_at
          ? new Date(runningHub.started_at).getTime()
          : Date.now();
        setHubStartedAt(startedAt);
        setHubElapsed(Math.floor((Date.now() - startedAt) / 1000));

        const controller = new AbortController();
        hubAbortController.current = controller;

        const matchingOp = (recentOps.recentOperations || []).find(
          (op) => op.title && op.title.includes(clusterName) && op.title.includes('MCE hub')
        );
        const resumeHubOpId = matchingOp?.id;

        const poll = async () => {
          // WALL-CLOCK budget using the job's REAL started_at as the clock
          // origin (a browser refresh 90 min in must not restart the budget).
          const TIMEOUT_MS = 150 * 60 * 1000;
          let logCursor = 0;
          let accumulatedLogs = [];
          while (!controller.signal.aborted && Date.now() - startedAt <= TIMEOUT_MS) {
            try {
              const [logsRes, jobRes] = await Promise.all([
                fetch(buildApiUrl(`/api/jobs/${jobId}/logs?since=${logCursor}`), {
                  signal: controller.signal,
                }),
                fetch(buildApiUrl(`/api/jobs/${jobId}`), {
                  signal: controller.signal,
                }),
              ]);
              const logsData = await logsRes.json();
              const jobData = await jobRes.json();

              if ((logsData.since ?? logCursor) === 0) accumulatedLogs = [];
              const newLines = (logsData.logs || []).filter((l) => l.trim());
              if (newLines.length > 0) accumulatedLogs = accumulatedLogs.concat(newLines);
              if (typeof logsData.total === 'number') logCursor = logsData.total;
              const currentOutput = accumulatedLogs.join('\n');

              // Terminal detection: any non-in-progress status is terminal;
              // only `completed` is success.
              const status = jobData.status;
              const inProgress =
                status === 'running' ||
                status === 'pending' ||
                status === 'queued';
              const isDone = !inProgress;
              const failed = isDone && status !== 'completed';
              const parsed = isDone && !failed ? parseHubSuccess(currentOutput) : {};
              const statusNote = `MCE hub build ended with status "${status}"`;

              setHubResults({
                success: !failed,
                isRunning: !isDone,
                timestamp: new Date().toISOString(),
                clusterName,
                output:
                  currentOutput ||
                  (isDone ? statusNote : 'Waiting for output...'),
                startedAt,
                ...(isDone ? { finishedAt: Date.now() } : {}),
                ...parsed,
              });

              const opId =
                resumeHubOpId ||
                (recentOps.recentOperations || []).find(
                  (op) => op.title && op.title.includes(clusterName) && op.title.includes('MCE hub')
                )?.id;
              if (opId) {
                const opStatus = isDone
                  ? failed
                    ? '❌ Hub build failed'
                    : '✅ MCE hub ready!'
                  : '★ Building hub...';
                updateRecentOperationStatus(opId, opStatus, currentOutput);
              }

              if (isDone) {
                setIsBuildingHub(false);
                setBuildingClusterName(null);
                activeHubJobId.current = null;
                hubBuildingClusterName.current = null;
                hubLaunchInFlight.current = false;
                hubAbortController.current = null;
                if (!failed) await fetchClusters();
                return;
              }

              await new Promise((resolve) => setTimeout(resolve, 3000));
            } catch (err) {
              if (err.name === 'AbortError') return;
              console.error('Hub resume polling error:', err);
              return;
            }
          }
        };

        poll();
      } catch (err) {
        console.error('Failed to check for running hub jobs:', err);
      }
    };

    resumeHubPolling();
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
      if (hubAbortController.current) {
        console.log('🧹 Cleaning up: Aborting active MCE hub polling');
        hubAbortController.current.abort();
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
        <h2 className="text-2xl font-bold bg-gradient-to-r from-blue-600 to-cyan-500 bg-clip-text text-transparent">ROSA HCP Clusters</h2>
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

      <div className="bg-white rounded-lg shadow-md border border-gray-100 overflow-hidden">
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
                    {(() => {
                      const ready = isClusterReady(cluster);
                      // A hub build is "pending" once a config card is open, and
                      // "building" once launched. Disable EVERY row's button in
                      // either case (single-flight across the whole section).
                      const hubBusy = !!clusterPendingHub || isBuildingHub;
                      // Per-row spinner reads from STATE so it renders on the
                      // correct row (not a ref, which wouldn't re-render).
                      const buildingThis =
                        isBuildingHub && buildingClusterName === cluster.name;
                      const enabled = ready && !hubBusy;
                      return (
                        <button
                          onClick={() => handleMakeHub(cluster)}
                          disabled={!ready || hubBusy}
                          title={
                            !ready
                              ? 'Cluster must be Ready'
                              : 'Install + configure MCE and enable CAPI/CAPA'
                          }
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 mr-3 text-sm font-medium text-white rounded transition-colors disabled:opacity-50"
                          style={
                            enabled
                              ? { backgroundColor: colors.buttonBg }
                              : {}
                          }
                          onMouseEnter={(e) =>
                            enabled &&
                            (e.currentTarget.style.backgroundColor = colors.buttonBgHover)
                          }
                          onMouseLeave={(e) =>
                            enabled &&
                            (e.currentTarget.style.backgroundColor = colors.buttonBg)
                          }
                        >
                          {buildingThis ? (
                            <>
                              <ArrowPathIcon className="h-4 w-4 animate-spin" />
                              Building hub…
                            </>
                          ) : (
                            <>
                              <StarIcon className="h-4 w-4" />
                              Make this my MCE hub
                            </>
                          )}
                        </button>
                      );
                    })()}
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

      {/* Make MCE Hub - Pre-run config + preflight card (inline, not a modal) */}
      {clusterPendingHub && hubConfig && (() => {
        const devChannel = isDevChannel(hubConfig.mce_channel);
        const credsOk =
          credsPreflight && credsPreflight.ocm && credsPreflight.aws;
        // Launch blocked if creds missing, or dev channel selected (acm-d pull
        // secret guardrail — we cannot verify it, so we block dev/RC channels).
        const launchBlocked = !credsOk || devChannel;
        return (
          <div className="mt-4">
            <div className="bg-purple-50 border border-purple-300 rounded-lg p-4">
              <div className="flex items-start gap-3">
                <StarIcon className="h-6 w-6 text-purple-600 flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <h4 className="font-semibold text-purple-900 mb-1">
                    Make &ldquo;{clusterPendingHub.name}&rdquo; your MCE test hub
                  </h4>
                  <p className="text-sm text-purple-800 mb-4">
                    This installs + configures MultiCluster Engine and enables
                    CAPI/CAPA. Estimated 30&ndash;110 min. You can cancel, but a
                    partial install may need cleanup.
                  </p>

                  {/* PREFLIGHT */}
                  <div className="mb-4">
                    <h5 className="text-xs font-semibold text-purple-900 uppercase tracking-wider mb-2">
                      Preflight
                    </h5>
                    <div className="flex flex-wrap gap-x-8 gap-y-1 text-sm">
                      <span className="flex items-center gap-1.5">
                        {credsPreflight?.ocm ? (
                          <CheckCircleIcon className="h-4 w-4 text-green-600" />
                        ) : (
                          <XCircleIcon className="h-4 w-4 text-red-600" />
                        )}
                        <span className={credsPreflight?.ocm ? 'text-gray-700' : 'text-red-700'}>
                          OCM credentials {credsPreflight?.ocm ? 'present' : 'missing'}
                        </span>
                      </span>
                      <span className="flex items-center gap-1.5">
                        {credsPreflight?.aws ? (
                          <CheckCircleIcon className="h-4 w-4 text-green-600" />
                        ) : (
                          <XCircleIcon className="h-4 w-4 text-red-600" />
                        )}
                        <span className={credsPreflight?.aws ? 'text-gray-700' : 'text-red-700'}>
                          AWS credentials {credsPreflight?.aws ? 'present' : 'missing'}
                        </span>
                      </span>
                    </div>
                    {!credsOk && (
                      <p className="text-xs text-red-700 mt-1">
                        Add OCM + AWS credentials in the Credentials / Environments
                        section before launching.
                      </p>
                    )}
                  </div>

                  {/* CONFIGURATION */}
                  <div className="mb-4">
                    <h5 className="text-xs font-semibold text-purple-900 uppercase tracking-wider mb-2">
                      Configuration
                    </h5>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-2xl">
                      <label className="text-sm">
                        <span className="block text-gray-600 mb-1">Cluster name</span>
                        <input
                          type="text"
                          value={hubConfig.cluster_name}
                          readOnly
                          className="w-full px-3 py-1.5 border border-gray-300 rounded bg-gray-100 text-gray-700 text-sm"
                        />
                      </label>
                      <label className="text-sm">
                        <span className="block text-gray-600 mb-1">CAPI namespace</span>
                        <input
                          type="text"
                          value={hubConfig.capi_namespace}
                          onChange={(e) =>
                            setHubConfig((c) => ({ ...c, capi_namespace: e.target.value }))
                          }
                          className="w-full px-3 py-1.5 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-purple-300"
                        />
                      </label>
                      <label className="text-sm">
                        <span className="block text-gray-600 mb-1">Minikube context</span>
                        <input
                          type="text"
                          value={hubConfig.minikube_context}
                          onChange={(e) =>
                            setHubConfig((c) => ({ ...c, minikube_context: e.target.value }))
                          }
                          className="w-full px-3 py-1.5 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-purple-300"
                        />
                      </label>
                      <label className="text-sm">
                        <span className="block text-gray-600 mb-1">MCE channel</span>
                        <input
                          type="text"
                          value={hubConfig.mce_channel}
                          onChange={(e) =>
                            setHubConfig((c) => ({ ...c, mce_channel: e.target.value }))
                          }
                          className="w-full px-3 py-1.5 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-purple-300"
                        />
                      </label>
                    </div>
                  </div>

                  {/* acm-d pull-secret guardrail — only for stable-5.x (dev/RC) */}
                  {devChannel && (
                    <div className="mb-4 flex items-start gap-2 bg-yellow-50 border border-yellow-300 rounded p-3">
                      <ExclamationTriangleIcon className="h-5 w-5 text-yellow-600 flex-shrink-0 mt-0.5" />
                      <p className="text-xs text-yellow-800">
                        Dev catalog / stable-5.x requires the acm-d pull secret on
                        the target cluster. Add it (or switch to a GA stable-2.x
                        channel) before launching &mdash; the install will otherwise
                        stall pulling the dev catalog image
                        (<code>quay.io:443/acm-d/mce-dev-catalog</code>).
                      </p>
                    </div>
                  )}

                  <div className="flex gap-3">
                    <button
                      onClick={() => executeMakeHub(clusterPendingHub, hubConfig)}
                      disabled={launchBlocked}
                      className="inline-flex items-center gap-1.5 px-4 py-2 text-white rounded-md transition-colors font-medium text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                      style={!launchBlocked ? { backgroundColor: colors.buttonBg } : {}}
                    >
                      <StarIcon className="h-4 w-4" />
                      Launch hub build
                    </button>
                    <button
                      onClick={() => {
                        pendingHubCluster.current = null;
                        setClusterPendingHub(null);
                        setHubConfig(null);
                        setCredsPreflight(null);
                      }}
                      className="px-4 py-2 bg-gray-200 hover:bg-gray-300 text-gray-800 rounded-md transition-colors font-medium text-sm"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        );
      })()}

      {/* Make MCE Hub - Results / progress card (mirrors deletion results) */}
      {hubResults && (() => {
        const phases = derivePhases(hubResults.output, {
          isRunning: hubResults.isRunning,
          isFailed: !hubResults.success,
          isDone: !hubResults.isRunning,
        });
        const fmtDur = (secs) => {
          if (secs == null) return '';
          const m = Math.floor(secs / 60);
          const s = secs % 60;
          const h = Math.floor(m / 60);
          if (h > 0) return `${h}:${String(m % 60).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
          return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
        };
        const elapsed = hubResults.isRunning
          ? hubElapsed
          : hubResults.startedAt && hubResults.finishedAt
            ? Math.floor((hubResults.finishedAt - hubResults.startedAt) / 1000)
            : null;
        return (
          <div className="mt-6 space-y-4">
            <div
              className={`rounded-lg border-2 p-6 ${
                hubResults.isRunning
                  ? 'bg-blue-50 border-blue-300'
                  : hubResults.success
                    ? 'bg-green-50 border-green-300'
                    : 'bg-red-50 border-red-300'
              }`}
            >
              <div className="flex items-center gap-3 mb-4">
                {hubResults.isRunning ? (
                  <StarIcon className="h-6 w-6 text-blue-600 animate-pulse" />
                ) : hubResults.success ? (
                  <span className="text-2xl">✅</span>
                ) : (
                  <span className="text-xl">❌</span>
                )}
                <h3 className="text-lg font-semibold text-gray-900">
                  {hubResults.isRunning
                    ? `Building MCE hub on ${hubResults.clusterName}…`
                    : hubResults.success
                      ? `MCE hub ready on ${hubResults.clusterName}`
                      : `MCE hub build failed on ${hubResults.clusterName}`}
                </h3>
                {elapsed != null && (
                  <span className="text-sm font-mono text-gray-600">⏱ {fmtDur(elapsed)}</span>
                )}
                {hubResults.isRunning && activeHubJobId.current && (
                  <button
                    onClick={async () => {
                      try {
                        // Cancel the REAL backend job directly by its job_id
                        // (mirrors the delete flow's cancel) — no description
                        // re-resolution that could silently no-op.
                        await fetch(
                          buildApiUrl(`/api/jobs/${activeHubJobId.current}/cancel`),
                          { method: 'POST' }
                        );
                        if (hubAbortController.current) {
                          hubAbortController.current.abort();
                        }
                        setIsBuildingHub(false);
                        setBuildingClusterName(null);
                        hubLaunchInFlight.current = false;
                      } catch (e) {
                        console.error('Failed to cancel hub build:', e);
                      }
                    }}
                    className="ml-auto px-4 py-1.5 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded-md transition-colors"
                    title="A partial MCE install may require manual cleanup"
                  >
                    ⛔ Cancel hub build
                  </button>
                )}
              </div>

              {/* Success summary card (parsed from print-only playbook log) */}
              {!hubResults.isRunning && hubResults.success && (
                <div className="mb-4 rounded-lg bg-white border border-green-200 p-4 text-sm">
                  <div className="flex flex-wrap gap-x-8 gap-y-1 mb-2">
                    <span className="text-gray-700">
                      MCE version:{' '}
                      <span className="font-medium">{hubResults.mceVersion || 'n/a'}</span>
                    </span>
                    <span className="flex items-center gap-1 text-gray-700">
                      <CheckCircleIcon className={`h-4 w-4 ${hubResults.capiCapaEnabled ? 'text-green-600' : 'text-gray-400'}`} />
                      CAPI/CAPA {hubResults.capiCapaEnabled ? 'enabled' : 'unknown'}
                    </span>
                    {elapsed != null && (
                      <span className="text-gray-700">Duration: {fmtDur(elapsed)}</span>
                    )}
                  </div>
                  {hubResults.consoleUrl && (
                    <div className="flex items-center gap-2">
                      <span className="text-gray-600">Console:</span>
                      <a
                        href={hubResults.consoleUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-purple-700 hover:text-purple-900 font-medium break-all"
                      >
                        {hubResults.consoleUrl}
                        <ArrowTopRightOnSquareIcon className="h-4 w-4 flex-shrink-0" />
                      </a>
                      <button
                        onClick={() => handleCopyOutput(hubResults.consoleUrl)}
                        className="px-2 py-0.5 text-xs rounded bg-gray-200 hover:bg-gray-300"
                      >
                        {copySuccess || '📋'}
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Phases + minimap */}
              <div className="mb-4">
                <h4 className="text-sm font-medium text-gray-700 mb-2">Phases</h4>
                <HubPhaseList phases={phases} />
                <div className="mt-3">
                  <HubPhaseMinimap phases={phases} />
                </div>
              </div>

              {/* Live colorized playbook output */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-sm font-medium text-gray-700">Playbook Output:</h4>
                  <button
                    onClick={() => handleCopyOutput(hubResults.output || 'No output available')}
                    className="px-3 py-1 text-white rounded text-xs font-medium transition-colors"
                    style={{ backgroundColor: colors.buttonBg }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = colors.buttonBgHover)}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = colors.buttonBg)}
                  >
                    {copySuccess || '📋 Copy'}
                  </button>
                </div>
                <HubLogTerminal logs={hubResults.output} isRunning={hubResults.isRunning} />
              </div>

              {/* Failure: retry / dismiss */}
              {!hubResults.isRunning && !hubResults.success && (() => {
                // Resolve the REAL cluster row for retry; if it's gone (e.g. no
                // longer listed), disable retry rather than fabricating a row.
                const retryCluster = clusters.find(
                  (c) => c.name === hubResults.clusterName
                );
                return (
                <div className="mt-4 flex gap-3">
                  <button
                    onClick={() => retryCluster && handleMakeHub(retryCluster)}
                    disabled={!retryCluster}
                    title={
                      retryCluster
                        ? 'Retry the MCE hub build'
                        : 'Cluster no longer available'
                    }
                    className="inline-flex items-center gap-1.5 px-4 py-2 text-white rounded-md transition-colors font-medium text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                    style={retryCluster ? { backgroundColor: colors.buttonBg } : {}}
                  >
                    <ArrowPathIcon className="h-4 w-4" />
                    Retry
                  </button>
                  <button
                    onClick={() => setHubResults(null)}
                    className="px-4 py-2 bg-gray-200 hover:bg-gray-300 text-gray-800 rounded-md transition-colors font-medium text-sm"
                  >
                    Dismiss
                  </button>
                </div>
                );
              })()}
            </div>
          </div>
        );
      })()}

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
              {isDeleting && activeDeleteJobId.current && (
                <button
                  onClick={async () => {
                    try {
                      await fetch(buildApiUrl(`/api/jobs/${activeDeleteJobId.current}/cancel`), { method: 'POST' });
                      if (deletionAbortController.current) {
                        deletionAbortController.current.abort();
                      }
                    } catch (e) {
                      console.error('Failed to cancel deletion:', e);
                    }
                  }}
                  className="ml-auto px-4 py-1.5 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded-md transition-colors"
                >
                  Abort Deletion
                </button>
              )}
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

          {/* Cluster Diagnostics Panel */}
          {deletionResults.clusterName && (
            <div className="mt-4">
              <DiagnosticsPanel
                clusterName={deletionResults.clusterName}
                isRunning={isDeleting}
                autoRefresh={true}
              />
            </div>
          )}

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
