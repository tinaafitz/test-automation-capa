/* eslint-disable no-unused-vars, no-console */
import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import {
  MagnifyingGlassIcon,
  FunnelIcon,
  CheckCircleIcon,
  XCircleIcon,
  ExclamationCircleIcon,
  ClockIcon,
  QuestionMarkCircleIcon,
  ClipboardDocumentIcon,
  ArrowPathIcon,
  KeyIcon,
  PlusIcon,
  TrashIcon,
} from '@heroicons/react/24/outline';

const getStatusConfig = (theme = 'mce') => {
  const progressColors = theme === 'minikube'
    ? { color: 'text-violet-600', bgColor: 'bg-violet-50', borderColor: 'border-violet-200' }
    : { color: 'text-blue-600', bgColor: 'bg-blue-50', borderColor: 'border-blue-200' };

  return {
    pass: {
      emoji: '✅',
      label: 'Pass',
      color: 'text-green-600',
      bgColor: 'bg-green-50',
      borderColor: 'border-green-200',
      icon: CheckCircleIcon,
    },
    fail: {
      emoji: '❌',
      label: 'Fail',
      color: 'text-red-600',
      bgColor: 'bg-red-50',
      borderColor: 'border-red-200',
      icon: XCircleIcon,
    },
    creating: {
      emoji: '🔄',
      label: 'Creating...',
      color: 'text-yellow-600',
      bgColor: 'bg-yellow-50',
      borderColor: 'border-yellow-200',
      icon: ArrowPathIcon,
    },
    in_progress: {
      emoji: '⏳',
      label: 'In Progress',
      ...progressColors,
      icon: ClockIcon,
    },
  };
};

const MCEEnvironmentSelector = ({
  onUseCredentials,
  title = 'MCE Environments',
  titleSingular = 'MCE Environment',
  theme = 'mce',
  environmentType = 'mce' // 'mce' or 'minikube'
}) => {
  // API endpoints based on environment type
  const apiEndpoints = {
    mce: {
      list: 'http://localhost:8000/api/mce-environments',
      stats: 'http://localhost:8000/api/mce-environments/stats/summary',
      create: 'http://localhost:8000/api/mce-environments',
      get: (clusterName) => `http://localhost:8000/api/mce-environments/${clusterName}`,
      updateStatus: (clusterName) => `http://localhost:8000/api/mce-environments/${clusterName}/status`,
    },
    minikube: {
      list: 'http://localhost:8000/api/minikube/list-clusters',
      stats: 'http://localhost:8000/api/minikube/list-clusters', // Reuse list endpoint for now
      create: 'http://localhost:8000/api/minikube/create-cluster', // Creates actual Minikube cluster
      get: (clusterName) => `http://localhost:8000/api/minikube/verify-cluster`,
      updateStatus: (clusterName) => `http://localhost:8000/api/minikube/list-clusters`, // No status updates for minikube yet
    }
  };

  const endpoints = apiEndpoints[environmentType];

  // Theme colors
  const themeColors = {
    mce: {
      primary: 'text-cyan-600',
      primaryHover: 'hover:text-cyan-800',
      primaryBg: 'bg-cyan-50',
      primaryBorder: 'border-cyan-500',
      title: 'text-blue-900',
      buttonHover: 'hover:bg-blue-50',
      buttonBg: '#2684FF',
      buttonBgHover: '#0065FF',
      inputBorder: '#2684FF'
    },
    minikube: {
      primary: 'text-violet-600',
      primaryHover: 'hover:text-violet-800',
      primaryBg: 'bg-violet-50',
      primaryBorder: 'border-violet-500',
      title: 'text-purple-900',
      buttonHover: 'hover:bg-violet-50',
      buttonBg: '#8B5CF6',
      buttonBgHover: '#7C3AED',
      inputBorder: '#8B5CF6'
    }
  };

  const colors = themeColors[theme];
  const [environments, setEnvironments] = useState([]);
  const [filteredEnvironments, setFilteredEnvironments] = useState([]);
  const [selectedEnv, setSelectedEnv] = useState(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [platformFilter, setPlatformFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [showFilters, setShowFilters] = useState(false);
  const [stats, setStats] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [copiedCommand, setCopiedCommand] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [createMessage, setCreateMessage] = useState('');
  const [createMessageType, setCreateMessageType] = useState(''); // 'success' or 'error'
  const [deletingCluster, setDeletingCluster] = useState(null); // Track which cluster is being deleted
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(null); // Track which cluster to confirm delete
  const [newEnv, setNewEnv] = useState({
    clusterName: '',
    platform: '',
    ocpVersion: '',
    consoleUrl: '',
    username: '',
    password: '',
    jira: '',
    polarion: '',
    notes: '',
    installMethod: 'clusterctl', // For Minikube: clusterctl or helm
  });

  // Fetch environments on mount
  useEffect(() => {
    fetchEnvironments();
    fetchStats();
  }, []);

  // Filter environments when filters change
  useEffect(() => {
    filterEnvironments();
  }, [environments, searchQuery, platformFilter, statusFilter]);

  const fetchEnvironments = async () => {
    try {
      setLoading(true);
      const response = await fetch(endpoints.list);
      const data = await response.json();

      if (environmentType === 'minikube') {
        // For Minikube, the response is { clusters: [...], minikube_installed: true }
        // Convert cluster names to environment objects
        const clusterNames = data.clusters || [];

        // Check configuration status for each cluster
        const clusterEnvsPromises = clusterNames.map(async (name) => {
          // Preserve existing status and notes if cluster is already tracked
          const existingEnv = environments.find(env => env.clusterName === name);

          // Check if cluster has CAPI/CAPA configured
          let configured = false;
          try {
            const componentResponse = await fetch(`http://localhost:8000/api/capi/component-versions?environment=minikube&cluster_name=${name}`);
            const componentData = await componentResponse.json();
            configured = componentData.components && componentData.components.length > 0;
          } catch (err) {
            console.log(`Could not check configuration for ${name}:`, err);
          }

          return {
            clusterName: name,
            name: name,
            status: existingEnv?.status || 'pass', // Preserve existing status or default to pass
            platform: 'Minikube',
            notes: existingEnv?.notes || (configured ? 'Configured with CAPI/CAPA' : 'Not configured'),
            configured: configured, // Add configured flag
            lastAccessed: existingEnv?.lastAccessed || new Date().toISOString(),
            jira: existingEnv?.jira,
            polarion: existingEnv?.polarion,
          };
        });

        const clusterEnvs = await Promise.all(clusterEnvsPromises);
        setEnvironments(clusterEnvs);
      } else if (data.success) {
        setEnvironments(data.environments || data.clusters || []);
      }
    } catch (error) {
      console.error(`Error fetching ${environmentType} environments:`, error);
    } finally {
      setLoading(false);
    }
  };

  const fetchStats = async () => {
    try {
      const response = await fetch(endpoints.stats);
      const data = await response.json();

      if (data.success) {
        setStats(data.stats);
      }
    } catch (error) {
      console.error('Error fetching stats:', error);
    }
  };

  const filterEnvironments = () => {
    let filtered = [...environments];

    // Search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (env) =>
          env.clusterName?.toLowerCase().includes(query) ||
          env.platform?.toLowerCase().includes(query) ||
          env.jira?.toLowerCase().includes(query) ||
          env.polarion?.toLowerCase().includes(query) ||
          env.notes?.toLowerCase().includes(query)
      );
    }

    // Platform filter
    if (platformFilter !== 'all') {
      filtered = filtered.filter((env) =>
        env.platform?.toLowerCase().includes(platformFilter.toLowerCase())
      );
    }

    // Status filter
    if (statusFilter !== 'all') {
      filtered = filtered.filter((env) => env.status === statusFilter);
    }

    setFilteredEnvironments(filtered);
  };

  const selectEnvironment = async (clusterName) => {
    try {
      // Clear any previous error messages
      setErrorMessage('');

      let response;

      if (environmentType === 'minikube') {
        // For minikube, verify-cluster is a POST endpoint
        console.log('🔍 Selecting Minikube cluster:', clusterName);
        response = await fetch('http://localhost:8000/api/minikube/verify-cluster', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ cluster_name: clusterName }),
        });
      } else {
        // For MCE, use the GET endpoint
        response = await fetch(endpoints.get(clusterName));
      }

      const data = await response.json();
      console.log('📡 Cluster selection response:', data);

      if (environmentType === 'minikube') {
        // For minikube, construct a selectedEnv object from the verify response
        if (data.exists && data.accessible) {
          console.log('✅ Minikube cluster verified, showing details');
          setSelectedEnv({
            clusterName: clusterName,
            name: clusterName,
            platform: 'Minikube',
            status: 'pass',
            clusterStatus: data.status || 'Running',
            ocpVersion: data.cluster_info?.kubernetesVersion || 'N/A',
            lastAccessed: new Date().toISOString(),
            loginCommand: `kubectl config use-context ${clusterName}`,
            // Add any additional info from the verification response
            ...data.cluster_info,
          });
        } else {
          console.warn('⚠️ Minikube cluster verification failed:', data);
          setErrorMessage(`Failed to verify cluster "${clusterName}". The cluster may not be running or accessible.`);
        }
      } else if (data.success) {
        setSelectedEnv(data.environment || data.cluster);
      }
    } catch (error) {
      console.error('❌ Error fetching environment details:', error);
      setErrorMessage(`Error selecting cluster: ${error.message}`);
    }
  };

  const updateStatus = async (clusterName, status, notes) => {
    try {
      const response = await fetch(
        endpoints.updateStatus(clusterName),
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status, notes }),
        }
      );

      const data = await response.json();

      if (data.success) {
        // Refresh environments
        await fetchEnvironments();
        await fetchStats();

        // Update selected environment if it's the one we updated
        if (selectedEnv?.clusterName === clusterName) {
          await selectEnvironment(clusterName);
        }
      }
    } catch (error) {
      console.error('Error updating status:', error);
    }
  };

  const copyLoginCommand = (command) => {
    navigator.clipboard.writeText(command);
    setCopiedCommand(true);
    setTimeout(() => setCopiedCommand(false), 2000);
  };

  const handleUseCredentials = async () => {
    if (selectedEnv && onUseCredentials) {
      let credentials;

      if (environmentType === 'minikube') {
        // For Minikube clusters, use the cluster name directly
        credentials = {
          clusterName: selectedEnv.clusterName || selectedEnv.name,
          minikubeCluster: selectedEnv.clusterName || selectedEnv.name,
        };
      } else {
        // For MCE/OpenShift clusters, extract API URL from console URL
        const apiUrl = `https://api.${selectedEnv.consoleUrl.split('apps.')[1].replace(/\/$/, '')}:6443`;
        credentials = {
          OCP_HUB_API_URL: apiUrl,
          OCP_HUB_CLUSTER_USER: 'kubeadmin',
          OCP_HUB_CLUSTER_PASSWORD: selectedEnv.password,
          clusterName: selectedEnv.clusterName,
        };
      }

      // Call the parent handler and wait for it to complete
      await onUseCredentials(credentials);

      // Return to the environments list after saving
      setSelectedEnv(null);
    }
  };

  const handleAddEnvironment = async () => {
    try {
      if (environmentType === 'minikube') {
        // For Minikube, create an actual cluster
        console.log('Creating Minikube cluster:', newEnv.clusterName);
        console.log('Installation method:', newEnv.installMethod);

        // Immediately add cluster to UI with "Creating..." status (optimistic update)
        const pendingCluster = {
          clusterName: newEnv.clusterName,
          name: newEnv.clusterName,
          status: 'creating',
          platform: 'Minikube',
          notes: newEnv.notes || 'Creating cluster...',
          lastAccessed: new Date().toISOString(),
          jira: newEnv.jira,
          polarion: newEnv.polarion,
        };

        setEnvironments(prev => [pendingCluster, ...prev]);

        // Show inline message
        setCreateMessage(`Creating cluster '${newEnv.clusterName}'...`);
        setCreateMessageType('info');

        // Close modal immediately
        setShowAddModal(false);

        // Reset form
        const clusterName = newEnv.clusterName;
        setNewEnv({
          clusterName: '',
          platform: '',
          ocpVersion: '',
          consoleUrl: '',
          username: '',
          password: '',
          jira: '',
          polarion: '',
          notes: '',
          installMethod: 'clusterctl',
        });

        // Start cluster creation in background
        const response = await fetch('http://localhost:8000/api/minikube/create-cluster', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            cluster_name: clusterName,
            install_method: newEnv.installMethod,
          }),
        });

        console.log('Response status:', response.status);
        console.log('Response ok:', response.ok);

        // Check if response is JSON
        const contentType = response.headers.get('content-type');
        console.log('Content-Type:', contentType);

        if (!contentType || !contentType.includes('application/json')) {
          const text = await response.text();
          console.error('Non-JSON response:', text);
          throw new Error(`Server returned non-JSON response: ${text.substring(0, 100)}`);
        }

        const data = await response.json();
        console.log('Response data:', data);

        if (data.success && data.job_id) {
          // Async creation started - poll for job completion
          setCreateMessage(`Creating cluster '${clusterName}'... (job: ${data.job_id.substring(0, 8)})`);
          setCreateMessageType('info');

          const pollJob = async () => {
            const maxAttempts = 300; // 5 minutes max (1s intervals)
            let attempts = 0;

            while (attempts < maxAttempts) {
              attempts++;
              try {
                const jobResponse = await fetch(`http://localhost:8000/api/jobs/${data.job_id}`);
                const jobData = await jobResponse.json();

                // Update notes with latest log line
                const logsResponse = await fetch(`http://localhost:8000/api/jobs/${data.job_id}/logs`);
                const logsData = await logsResponse.json();
                const lastLog = logsData.logs?.filter(l => l.trim()).slice(-1)[0] || 'Creating...';

                setEnvironments(prev => prev.map(env =>
                  env.clusterName === clusterName
                    ? { ...env, notes: lastLog }
                    : env
                ));

                if (jobData.status === 'completed') {
                  setEnvironments(prev => prev.map(env =>
                    env.clusterName === clusterName
                      ? { ...env, status: 'pass', notes: 'Cluster created successfully' }
                      : env
                  ));
                  await fetchEnvironments();
                  setCreateMessage(`Cluster '${clusterName}' created successfully!`);
                  setCreateMessageType('success');
                  setTimeout(() => { setCreateMessage(''); setCreateMessageType(''); }, 3000);
                  return;
                } else if (jobData.status === 'failed') {
                  const errorMsg = jobData.message || 'Creation failed';
                  setEnvironments(prev => prev.map(env =>
                    env.clusterName === clusterName
                      ? { ...env, status: 'fail', notes: `Failed: ${errorMsg}` }
                      : env
                  ));
                  setCreateMessage(`Failed to create cluster: ${errorMsg}`);
                  setCreateMessageType('error');
                  return;
                }

                await new Promise(resolve => setTimeout(resolve, 1000));
              } catch (err) {
                console.error('Error polling job:', err);
                await new Promise(resolve => setTimeout(resolve, 2000));
              }
            }

            // Timeout
            setEnvironments(prev => prev.map(env =>
              env.clusterName === clusterName
                ? { ...env, status: 'fail', notes: 'Creation timed out' }
                : env
            ));
            setCreateMessage('Cluster creation timed out');
            setCreateMessageType('error');
          };

          pollJob();
        } else if (data.success) {
          // Synchronous success (shouldn't happen with new backend, but handle gracefully)
          setEnvironments(prev => prev.map(env =>
            env.clusterName === clusterName
              ? { ...env, status: 'pass', notes: 'Cluster created successfully' }
              : env
          ));
          await fetchEnvironments();
          setCreateMessage(`Cluster '${clusterName}' created successfully!`);
          setCreateMessageType('success');
          setTimeout(() => { setCreateMessage(''); setCreateMessageType(''); }, 3000);
        } else {
          // Backend returned success: false with error details
          const errorMsg = data.message || data.error || 'Unknown error';
          const suggestion = data.suggestion ? `Suggestion: ${data.suggestion}` : '';
          console.error('Backend error:', errorMsg);

          // Update cluster status to failed
          setEnvironments(prev => prev.map(env =>
            env.clusterName === clusterName
              ? { ...env, status: 'fail', notes: `Failed: ${errorMsg}${suggestion ? '. ' + suggestion : ''}` }
              : env
          ));

          // Show inline error message
          setCreateMessage(`Failed to create cluster: ${errorMsg}${suggestion ? '. ' + suggestion : ''}`);
          setCreateMessageType('error');
        }
      } else {
        // For MCE, store environment metadata
        const response = await fetch(endpoints.create, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(newEnv),
        });

        const data = await response.json();

        if (data.success) {
          // Show inline success message
          setCreateMessage(`Environment added successfully!`);
          setCreateMessageType('success');

          // Reset form
          setNewEnv({
            clusterName: '',
            platform: '',
            ocpVersion: '',
            consoleUrl: '',
            username: '',
            password: '',
            jira: '',
            polarion: '',
            notes: '',
            installMethod: 'clusterctl',
          });

          // Refresh environments
          await fetchEnvironments();
          await fetchStats();

          // Auto-hide modal after 3 seconds
          setTimeout(() => {
            setShowAddModal(false);
            setCreateMessage('');
            setCreateMessageType('');
          }, 3000);
        } else {
          // Show inline error message
          setCreateMessage(`Failed to add environment: ${data.message || 'Unknown error'}`);
          setCreateMessageType('error');
        }
      }
    } catch (error) {
      console.error('Error adding environment (caught exception):', error);
      console.error('Error stack:', error.stack);

      // Provide more helpful error messages
      let errorMsg = error.message || error.toString();
      if (error.message && error.message.includes('Failed to fetch')) {
        errorMsg = 'Cannot connect to backend server. Make sure the backend is running on http://localhost:8000';
      }

      // Show inline error message
      setCreateMessage(`Error: ${errorMsg}`);
      setCreateMessageType('error');
    }
  };

  const handleDeleteCluster = async (clusterName) => {
    if (environmentType !== 'minikube') {
      console.warn('Delete is only supported for Minikube clusters');
      return;
    }

    try {
      setDeletingCluster(clusterName);
      setShowDeleteConfirm(null);

      console.log('Deleting Minikube cluster:', clusterName);

      const response = await fetch('http://localhost:8000/api/minikube/delete-cluster', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cluster_name: clusterName }),
      });

      const data = await response.json();
      console.log('Delete response:', data);

      if (data.success) {
        // Remove cluster from UI
        setEnvironments(prev => prev.filter(env => env.clusterName !== clusterName));

        // Show success message
        setCreateMessage(`Cluster '${clusterName}' deleted successfully`);
        setCreateMessageType('success');

        // Refresh environments to sync with backend
        await fetchEnvironments();

        // Clear message after 3 seconds
        setTimeout(() => {
          setCreateMessage('');
          setCreateMessageType('');
        }, 3000);
      } else {
        // Show error message
        setCreateMessage(`Failed to delete cluster: ${data.message || 'Unknown error'}`);
        setCreateMessageType('error');

        // Clear message after 5 seconds
        setTimeout(() => {
          setCreateMessage('');
          setCreateMessageType('');
        }, 5000);
      }
    } catch (error) {
      console.error('Error deleting cluster:', error);
      setCreateMessage(`Error deleting cluster: ${error.message}`);
      setCreateMessageType('error');

      setTimeout(() => {
        setCreateMessage('');
        setCreateMessageType('');
      }, 5000);
    } finally {
      setDeletingCluster(null);
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    try {
      const date = new Date(dateString);
      return (
        date.toLocaleDateString() +
        ' ' +
        date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      );
    } catch {
      return 'N/A';
    }
  };

  const StatusBadge = ({ status }) => {
    const STATUS_CONFIG = getStatusConfig(theme);
    const config = STATUS_CONFIG[status];

    // Don't render badge if status is not in our config
    if (!config) return null;

    const Icon = config.icon;
    const isAnimated = status === 'creating' || status === 'in_progress';

    return (
      <span
        className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium ${config.color} ${config.bgColor} border ${config.borderColor}`}
      >
        <Icon className={`w-4 h-4 ${isAnimated ? 'animate-spin' : ''}`} />
        {config.label}
      </span>
    );
  };

  return (
    <div className="space-y-6">
      {/* Title */}
      <h2 className={`text-2xl font-bold ${colors.title}`}>
        {selectedEnv ? titleSingular : title}
        {selectedEnv && (
          <>
            <span className="text-gray-400 mx-2">›</span>
            <span className={colors.primary}>{selectedEnv.clusterName}</span>
          </>
        )}
      </h2>

      {/* Search and Filters - Hidden when viewing single environment */}
      {!selectedEnv && (
        <div className="bg-white rounded-lg shadow p-4 space-y-4">
        <div className="flex flex-col md:flex-row gap-4">
          {/* Search */}
          <div className="flex-1 relative">
            <MagnifyingGlassIcon className="w-5 h-5 absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="Search by cluster, platform, Jira, Polarion..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border rounded focus:ring-2 focus:border-transparent"
              style={{ borderColor: colors.inputBorder }}
            />
          </div>

          {/* Filter Toggle */}
          <button
            onClick={() => setShowFilters(!showFilters)}
            className="flex items-center gap-2 px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded transition-colors"
          >
            <FunnelIcon className="w-5 h-5" />
            Filters
          </button>

          {/* Refresh */}
          <button
            onClick={() => {
              fetchEnvironments();
              fetchStats();
            }}
            className="flex items-center gap-2 px-4 py-2 text-white rounded transition-colors"
            style={{ backgroundColor: colors.buttonBg }}
            onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = colors.buttonBgHover)}
            onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = colors.buttonBg)}
          >
            <ArrowPathIcon className="w-5 h-5" />
            Refresh
          </button>

          {/* Add Environment */}
          <button
            onClick={() => {
              setShowAddModal(true);
              setCreateMessage('');
              setCreateMessageType('');
            }}
            className="flex items-center gap-2 px-4 py-2 text-white rounded transition-colors"
            style={{ backgroundColor: colors.buttonBg }}
            onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = colors.buttonBgHover)}
            onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = colors.buttonBg)}
          >
            <PlusIcon className="w-5 h-5" />
            Add
          </button>
        </div>

        {/* Filter Options */}
        {showFilters && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4 border-t">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Platform</label>
              <select
                value={platformFilter}
                onChange={(e) => setPlatformFilter(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-cyan-500"
              >
                <option value="all">All Platforms</option>
                <option value="IBM Power">IBM Power</option>
                <option value="AWS-ARM">AWS ARM</option>
                <option value="AWS">AWS x86</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Test Status</label>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-cyan-500"
              >
                <option value="all">All Statuses</option>
                <option value="pass">✅ Pass</option>
                <option value="fail">❌ Fail</option>
                <option value="in_progress">⏳ In Progress</option>
              </select>
            </div>
          </div>
        )}

        {/* Add Environment Form - Inline */}
        {showAddModal && (
          <div className="pt-4 border-t mt-4">
            <h3 className="text-lg font-semibold text-green-700 mb-4">
              {environmentType === 'minikube' ? 'Add New Minikube Cluster' : 'Add New Environment'}
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Cluster Name */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Cluster Name *
                </label>
                <input
                  type="text"
                  value={newEnv.clusterName}
                  onChange={(e) => setNewEnv({ ...newEnv, clusterName: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500"
                  placeholder={environmentType === 'minikube' ? 'e.g., minikube' : 'e.g., cqu-2135-zup'}
                />
              </div>

              {/* MCE-specific fields - Only show for MCE environment type */}
              {environmentType === 'mce' && (
                <>
                  {/* Platform */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Platform
                    </label>
                    <select
                      value={newEnv.platform}
                      onChange={(e) => setNewEnv({ ...newEnv, platform: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500"
                    >
                      <option value="">Select platform...</option>
                      <option value="AWS">AWS x86</option>
                      <option value="AWS-ARM">AWS ARM</option>
                      <option value="IBM Power">IBM Power</option>
                      <option value="IBM Z">IBM Z</option>
                      <option value="Azure">Azure</option>
                      <option value="GCP">GCP</option>
                    </select>
                  </div>

                  {/* OCP Version */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      OCP Version
                    </label>
                    <input
                      type="text"
                      value={newEnv.ocpVersion}
                      onChange={(e) => setNewEnv({ ...newEnv, ocpVersion: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500"
                      placeholder="e.g., 4.19.21"
                    />
                  </div>

                  {/* Console URL */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Console URL *
                    </label>
                    <input
                      type="text"
                      value={newEnv.consoleUrl}
                      onChange={(e) => setNewEnv({ ...newEnv, consoleUrl: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500"
                      placeholder="https://console-openshift-console.apps..."
                    />
                  </div>

                  {/* Username */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Username *
                    </label>
                    <input
                      type="text"
                      value={newEnv.username}
                      onChange={(e) => setNewEnv({ ...newEnv, username: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500"
                      placeholder="kubeadmin"
                    />
                  </div>

                  {/* Password */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Password *
                    </label>
                    <input
                      type="password"
                      value={newEnv.password}
                      onChange={(e) => setNewEnv({ ...newEnv, password: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500"
                      placeholder="kubeadmin password"
                    />
                  </div>
                </>
              )}

              {/* Jira */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Jira Ticket
                </label>
                <input
                  type="text"
                  value={newEnv.jira}
                  onChange={(e) => setNewEnv({ ...newEnv, jira: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500"
                  placeholder="e.g., ACM-24815"
                />
              </div>

              {/* Polarion */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Polarion Test Plan
                </label>
                <input
                  type="text"
                  value={newEnv.polarion}
                  onChange={(e) => setNewEnv({ ...newEnv, polarion: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500"
                  placeholder="e.g., RHACM4K-12345"
                />
              </div>

              {/* Notes - Full Width */}
              <div className="md:col-span-2">
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Notes
                </label>
                <textarea
                  value={newEnv.notes}
                  onChange={(e) => setNewEnv({ ...newEnv, notes: e.target.value })}
                  rows={2}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500"
                  placeholder="Any additional notes about this cluster..."
                />
              </div>
            </div>

            {/* Inline Message Display */}
            {createMessage && (
              <div className={`mt-4 p-4 rounded-lg border ${
                createMessageType === 'success'
                  ? 'bg-green-50 border-green-200 text-green-800'
                  : 'bg-red-50 border-red-200 text-red-800'
              }`}>
                <div className="flex items-start gap-3">
                  <span className="text-xl flex-shrink-0">
                    {createMessageType === 'success' ? '✅' : '❌'}
                  </span>
                  <div className="flex-1">
                    <p className="text-sm font-medium">{createMessage}</p>
                  </div>
                </div>
              </div>
            )}

            {/* Action Buttons */}
            <div className="flex justify-end gap-3 mt-4">
              <button
                onClick={() => {
                  setShowAddModal(false);
                  setCreateMessage('');
                  setCreateMessageType('');
                }}
                className="px-4 py-2 border border-gray-300 rounded text-gray-700 hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleAddEnvironment}
                disabled={
                  environmentType === 'minikube'
                    ? !newEnv.clusterName
                    : (!newEnv.consoleUrl || !newEnv.username || !newEnv.password)
                }
                className="px-4 py-2 text-white rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-gray-400"
                style={
                  {
                    backgroundColor: (environmentType === 'minikube'
                      ? newEnv.clusterName
                      : (newEnv.consoleUrl && newEnv.username && newEnv.password))
                        ? colors.buttonBg
                        : '#9CA3AF' // gray-400 for disabled state
                  }
                }
                onMouseEnter={(e) =>
                  (environmentType === 'minikube' ? newEnv.clusterName : (newEnv.consoleUrl && newEnv.username && newEnv.password)) &&
                  (e.currentTarget.style.backgroundColor = colors.buttonBgHover)
                }
                onMouseLeave={(e) =>
                  (environmentType === 'minikube' ? newEnv.clusterName : (newEnv.consoleUrl && newEnv.username && newEnv.password)) &&
                  (e.currentTarget.style.backgroundColor = colors.buttonBg)
                }
              >
                {environmentType === 'minikube' ? 'Add Cluster' : 'Add Environment'}
              </button>
            </div>
          </div>
        )}
        </div>
      )}

      {/* Error Message Display */}
      {errorMessage && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
          <div className="flex items-start gap-3">
            <ExclamationCircleIcon className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-medium text-red-800">{errorMessage}</p>
            </div>
            <button
              onClick={() => setErrorMessage('')}
              className="text-red-600 hover:text-red-800 text-sm font-medium"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Success/Error Message for Create/Delete Operations */}
      {!selectedEnv && createMessage && (
        <div className={`rounded-lg p-4 mb-4 border ${
          createMessageType === 'success'
            ? 'bg-green-50 border-green-200'
            : 'bg-red-50 border-red-200'
        }`}>
          <div className="flex items-start gap-3">
            {createMessageType === 'success' ? (
              <CheckCircleIcon className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
            ) : (
              <XCircleIcon className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
            )}
            <div className="flex-1">
              <p className={`text-sm font-medium ${
                createMessageType === 'success' ? 'text-green-800' : 'text-red-800'
              }`}>
                {createMessage}
              </p>
            </div>
            <button
              onClick={() => {
                setCreateMessage('');
                setCreateMessageType('');
              }}
              className={`text-sm font-medium ${
                createMessageType === 'success'
                  ? 'text-green-600 hover:text-green-800'
                  : 'text-red-600 hover:text-red-800'
              }`}
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Environments List or Selected Environment */}
      {!selectedEnv ? (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
          {loading ? (
            <div className="p-12 text-center text-gray-500">
              <ArrowPathIcon className="w-8 h-8 mx-auto mb-2 animate-spin" />
              Loading environments...
            </div>
          ) : filteredEnvironments.length === 0 ? (
            <div className="p-12 text-center text-gray-500">
              <QuestionMarkCircleIcon className="w-12 h-12 mx-auto mb-2 text-gray-400" />
              <p>No environments found</p>
              <p className="text-sm mt-2">Try adjusting your search or filters</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-100">
              {filteredEnvironments.map((env) => (
                <div
                  key={env.clusterName}
                  className={`py-2 px-6 ${colors.buttonHover} transition-colors`}
                >
                  {/* Cluster Name and Status - Jenkins style */}
                  <div className="flex items-center gap-3 mb-1">
                    <button
                      onClick={() => selectEnvironment(env.clusterName)}
                      className={`${colors.primary} ${colors.primaryHover} font-medium text-base hover:underline`}
                    >
                      {env.clusterName}
                    </button>
                    <StatusBadge status={env.status} />

                    {/* Delete button for Minikube clusters */}
                    {environmentType === 'minikube' && (
                      <div className="ml-auto flex items-center gap-2">
                        {showDeleteConfirm === env.clusterName ? (
                          <div className="flex items-center gap-2 px-3 py-2 bg-red-50 border border-red-200 rounded-lg">
                            <span className="text-sm font-medium text-red-800">Delete this cluster?</span>
                            <button
                              onClick={() => handleDeleteCluster(env.clusterName)}
                              disabled={deletingCluster === env.clusterName}
                              className="px-3 py-1.5 text-sm font-medium bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                            >
                              {deletingCluster === env.clusterName ? (
                                <span className="flex items-center gap-2">
                                  <ArrowPathIcon className="w-4 h-4 animate-spin" />
                                  Deleting...
                                </span>
                              ) : (
                                'Yes, Delete'
                              )}
                            </button>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setShowDeleteConfirm(null);
                              }}
                              disabled={deletingCluster === env.clusterName}
                              className="px-3 py-1.5 text-sm font-medium bg-white border border-gray-300 text-gray-700 rounded hover:bg-gray-50 disabled:opacity-50 transition-colors"
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setShowDeleteConfirm(env.clusterName);
                            }}
                            disabled={deletingCluster !== null}
                            className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            title="Delete cluster"
                          >
                            <TrashIcon className="w-5 h-5" />
                          </button>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Metadata as simple bullet list - Jenkins style */}
                  <div className="ml-1">
                    <div className="flex items-start gap-2 text-sm text-gray-700">
                      <span className="text-gray-400 mt-1">•</span>
                      <span>
                        <span className="text-gray-600">Platform:</span>{' '}
                        <span className="text-gray-900">{env.platform || 'unknown'}</span>
                        {environmentType === 'minikube' && env.configured !== undefined && (
                          <>
                            <span className="text-gray-400 mx-2">|</span>
                            <span className="text-gray-600">CAPI/CAPA:</span>{' '}
                            <span className={env.configured ? 'text-green-600 font-medium' : 'text-gray-500'}>
                              {env.configured ? '✓ Configured' : 'Not Configured'}
                            </span>
                          </>
                        )}
                        {env.ocpVersion && (
                          <>
                            <span className="text-gray-400 mx-2">|</span>
                            <span className="text-gray-600">OCP:</span>{' '}
                            <span className="text-gray-900">{env.ocpVersion}</span>
                          </>
                        )}
                        {env.jira && (
                          <>
                            <span className="text-gray-400 mx-2">|</span>
                            <span className="text-gray-600">Jira:</span>{' '}
                            <span className="text-gray-900">{env.jira}</span>
                          </>
                        )}
                      </span>
                    </div>

                    {env.notes && !env.notes.includes('PRE-UPGRADE') && !env.notes.includes('POST-UPGRADE') && !env.notes.includes('total failures') && (
                      <div className="flex items-start gap-2 text-sm text-gray-700">
                        <span className="text-gray-400 mt-1">•</span>
                        <span>
                          <span className="text-gray-600">Notes:</span>{' '}
                          <span className="text-gray-800">{env.notes}</span>
                        </span>
                      </div>
                    )}

                    <div className="flex items-start gap-2 text-sm text-gray-500">
                      <span className="text-gray-400 mt-1">•</span>
                      <span>
                        <span className="text-gray-600">Last Used:</span>{' '}
                        {formatDate(env.lastAccessed)}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        /* Selected Environment Details - Replaces List */
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
          <div className="p-4 space-y-3">
              {/* Back Button */}
              <button
                onClick={() => setSelectedEnv(null)}
                className={`flex items-center gap-2 ${colors.primary} ${colors.primaryHover} font-medium mb-4`}
              >
                ← Back to Environments
              </button>
              {/* Connection Info */}
              <div className="bg-gray-50 rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="font-semibold text-gray-900">Connection Details</h3>
                  {onUseCredentials && (
                    <button
                      onClick={handleUseCredentials}
                      className="flex items-center gap-2 px-4 py-2 text-white text-sm font-medium rounded transition-colors"
                      style={{ backgroundColor: colors.buttonBg }}
                      onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = colors.buttonBgHover)}
                      onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = colors.buttonBg)}
                    >
                      <KeyIcon className="w-4 h-4" />
                      Use This Environment
                    </button>
                  )}
                </div>
                <div className="space-y-2 text-sm">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <span className="text-gray-600">Platform:</span>
                      <span className="ml-2 font-medium">{selectedEnv.platform}</span>
                    </div>
                    <div>
                      <span className="text-gray-600">OCP Version:</span>
                      <span className="ml-2 font-medium">{selectedEnv.ocpVersion}</span>
                    </div>
                    <div>
                      <span className="text-gray-600">Status:</span>
                      <span className="ml-2 font-medium">{selectedEnv.clusterStatus}</span>
                    </div>
                    <div>
                      <span className="text-gray-600">Last Used:</span>
                      <span className="ml-2 font-medium">{formatDate(selectedEnv.lastAccessed)}</span>
                    </div>
                  </div>

                  <div className="pt-3 border-t">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-gray-600 font-medium text-sm">Login Command</span>
                      <button
                        onClick={() => copyLoginCommand(selectedEnv.loginCommand)}
                        className={`flex items-center gap-1.5 px-3 py-1.5 bg-white border border-gray-300 hover:bg-gray-50 ${colors.primaryBorder} text-gray-700 text-xs rounded-md transition-all`}
                      >
                        <ClipboardDocumentIcon className="w-3.5 h-3.5" />
                        {copiedCommand ? 'Copied!' : 'Copy'}
                      </button>
                    </div>
                    <div className="relative bg-slate-50 border border-slate-200 rounded-md p-3 hover:border-slate-300 transition-colors">
                      <code className="block font-mono text-xs text-slate-700 overflow-x-auto whitespace-nowrap">
                        {selectedEnv.loginCommand}
                      </code>
                    </div>
                  </div>
                </div>
              </div>
          </div>
        </div>
      )}
    </div>
  );
};

MCEEnvironmentSelector.propTypes = {
  onUseCredentials: PropTypes.func,
  title: PropTypes.string,
  titleSingular: PropTypes.string,
  theme: PropTypes.oneOf(['mce', 'minikube']),
  environmentType: PropTypes.oneOf(['mce', 'minikube']),
};

export default MCEEnvironmentSelector;
