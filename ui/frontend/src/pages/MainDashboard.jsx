import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bars3Icon, ClockIcon, ArrowPathIcon, TrashIcon, ChevronUpDownIcon, ChevronDownIcon, ChevronRightIcon, BellIcon } from '@heroicons/react/24/outline';
import { useRecentOperationsContext } from '../store/AppContext';
import { buildApiUrl, API_ENDPOINTS } from '../config/api';
import JenkinsTestResultsTrend from '../components/charts/JenkinsTestResultsTrend';
import GitHubRepoActivity from '../components/charts/GitHubRepoActivity';
import AWSQuotaWidget from '../components/charts/AWSQuotaWidget';
import { AIAssistantChat } from '../components/chat/AIAssistantChat';
import NotificationSettingsInline from '../components/NotificationSettingsInline';
import AWSUsageDashboard from './AWSUsageDashboard';

// Module-level cache survives component unmount/remount
let _clustersCache = { clusters: [], lastFetched: null };

// Component to fetch and display clusters from both environments
const CombinedRosaHcpClusters = ({ onRefresh }) => {
  const [clusters, setClusters] = useState(_clustersCache.clusters);
  const [loading, setLoading] = useState(false);
  const [sortField, setSortField] = useState('created');
  const [sortDirection, setSortDirection] = useState('desc');
  const [error, setError] = useState(null);
  const [selectedCluster, setSelectedCluster] = useState(null);

  const fetchClusters = async () => {
    setLoading(true);
    setError(null);

    try {
      // Fetch credentials to get Minikube cluster name
      const credResponse = await fetch(buildApiUrl('/api/credentials'));
      const credData = await credResponse.json();
      const minikubeClusterName = credData.credentials?.minikubeCluster || credData.credentials?.clusterName || 'sat-minikube-test';

      // Fetch actual ROSA HCP clusters from AWS and Minikube resources in parallel
      const [rosaResponse, minikubeResourcesResponse] = await Promise.all([
        fetch(buildApiUrl(API_ENDPOINTS.ROSA_CLUSTERS)),
        fetch(buildApiUrl('/api/minikube/get-active-resources'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            cluster_name: minikubeClusterName,
            namespace: 'ns-rosa-hcp'
          }),
        })
      ]);

      const rosaData = await rosaResponse.json();
      const minikubeData = await minikubeResourcesResponse.json();

      if (rosaData.success && Array.isArray(rosaData.clusters)) {
        // Get list of cluster names provisioned via Minikube (from RosaControlPlane resources)
        const minikubeClusters = minikubeData.success && Array.isArray(minikubeData.resources)
          ? minikubeData.resources
              .filter(r => r.type === 'RosaControlPlane')
              .map(r => r.name)
          : [];

        // Label each ROSA cluster based on which environment provisioned it
        const allClusters = rosaData.clusters.map(c => {
          const isMinikube = minikubeClusters.includes(c.name);
          return {
            ...c,
            environment: isMinikube ? 'minikube' : 'mce',
            environmentLabel: isMinikube ? 'Minikube' : 'MCE'
          };
        });

        setClusters(allClusters);
        _clustersCache.clusters = allClusters;
        _clustersCache.lastFetched = Date.now();
      } else {
        setClusters([]);
        _clustersCache.clusters = [];
      }
    } catch (err) {
      setError(err.message || 'Failed to load clusters');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchClusters();
  }, []);

  // Expose fetch function to parent
  useEffect(() => {
    if (onRefresh) {
      onRefresh.current = fetchClusters;
    }
  }, [onRefresh]);

  // Format date for display
  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { day: '2-digit', month: 'short', year: 'numeric' });
  };

  // Handle sort
  const handleSort = (field) => {
    if (sortField === field) {
      // Toggle direction if same field
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      // New field, default to ascending
      setSortField(field);
      setSortDirection('asc');
    }
  };

  // Sort clusters
  const sortedClusters = [...clusters].sort((a, b) => {
    let aVal = a[sortField];
    let bVal = b[sortField];

    // Handle special cases
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

  // Render sort indicator
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
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden max-h-[400px] overflow-y-auto">
      {/* Cluster Table */}
      {error ? (
        <div className="text-center py-8 text-red-600 p-6">
          <p className="text-sm">Failed to load clusters</p>
          <p className="text-xs mt-2">{error}</p>
        </div>
      ) : loading && clusters.length === 0 ? (
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
              <tr key={`${cluster.environment}-${cluster.name}-${idx}`} className="hover:bg-gray-50">
                <td className="px-6 py-4 whitespace-nowrap">
                  <div className="flex items-center gap-2">
                    <a href="#" className="text-sm font-medium text-blue-600 hover:text-blue-800">
                      {cluster.name}
                    </a>
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                      cluster.environment === 'mce'
                        ? 'bg-blue-100 text-blue-800'
                        : 'bg-purple-100 text-purple-800'
                    }`}>
                      {cluster.environmentLabel}
                    </span>
                  </div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <div className="flex items-center gap-1.5">
                    <span className={`inline-block w-2.5 h-2.5 rounded-full ${
                      cluster.status === 'ready' ? 'bg-green-500' :
                      cluster.status === 'installing' ? 'bg-blue-500 animate-pulse' :
                      cluster.status === 'waiting' ? 'bg-yellow-500 animate-pulse' :
                      cluster.status === 'uninstalling' ? 'bg-orange-500 animate-pulse' :
                      cluster.status === 'error' ? 'bg-red-500' :
                      'bg-gray-400'
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
                    onClick={() => { console.log(`Delete cluster: ${cluster.name}`); setError('Delete cluster functionality coming soon'); setTimeout(() => setError(null), 5000); }}
                    className="text-gray-400 hover:text-red-600"
                    title="Delete cluster"
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
  );
};

const MainDashboard = () => {
  const navigate = useNavigate();
  const [showEnvMenu, setShowEnvMenu] = useState(false);
  const recentOps = useRecentOperationsContext();
  const [tasksRefreshKey, setTasksRefreshKey] = useState(0);
  const clustersRefreshRef = React.useRef(null);
  const [activeSection, setActiveSection] = useState(null);
  const [expandedTasks, setExpandedTasks] = useState(new Set());

  // Refs for scrolling to sections
  const clustersRef = React.useRef(null);
  const tasksRef = React.useRef(null);
  const jenkinsRef = React.useRef(null);

  // Scroll to section
  const scrollToSection = (ref, sectionId) => {
    setActiveSection(sectionId);
    ref.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  // Toggle task expansion
  const toggleTaskExpansion = (taskId) => {
    setExpandedTasks(prev => {
      const newSet = new Set(prev);
      if (newSet.has(taskId)) {
        newSet.delete(taskId);
      } else {
        newSet.add(taskId);
      }
      return newSet;
    });
  };

  // Copy handler for task output
  const [copySuccess, setCopySuccess] = useState('');
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

  // Refresh recent tasks - reload from localStorage
  const handleRefreshTasks = () => {
    try {
      const saved = localStorage.getItem('recentOperations');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed)) {
          recentOps.setRecentOperations(parsed);
        }
      }
    } catch (error) {
      console.error('Failed to reload recent operations:', error);
    }
    setTasksRefreshKey(prev => prev + 1);
  };

  // Get all recent operations from both environments
  const allRecentTasks = recentOps.recentOperations || [];

  // Get status icon
  const getStatusIcon = (status) => {
    if (!status) return '⏳';
    const statusStr = typeof status === 'object' ? (status.status || '') : String(status);
    const lower = statusStr.toLowerCase();
    // Check failure/warning first — status text may contain mixed emoji from detailed messages
    if (lower.includes('fail') || lower.includes('error') || lower.includes('authentication failed')) return '❌';
    if (lower.includes('warn')) return '⚠️';
    if (lower.includes('success') || lower.includes('passed') || lower.includes('verified')) return '✅';
    if (statusStr.includes('🆕')) return '🆕';
    if (lower.includes('running') || lower.includes('in progress')) return '⏳';
    return '📄';
  };

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <div className="w-72 bg-gray-100 border-r border-gray-300 flex flex-col h-full">
        {/* Sidebar Title */}
        <div className="flex-shrink-0 bg-white px-4 py-4 border-b border-gray-300 h-[72px] relative">
          <div className="flex items-center justify-between gap-3">
            <h1 className="text-2xl font-bold text-gray-900 leading-tight flex-1 cursor-pointer" onClick={() => setActiveSection(null)}>CAPA Automation</h1>
            <button
              onClick={() => setShowEnvMenu(!showEnvMenu)}
              className="p-2 hover:bg-gray-100 rounded transition-colors flex-shrink-0"
              title="Environment Menu"
            >
              <Bars3Icon className="h-6 w-6 text-gray-600" />
            </button>
          </div>

          {/* Environment Menu */}
          {showEnvMenu && (
            <div className="absolute top-[72px] left-0 right-0 bg-white border-b border-gray-300 shadow-lg z-50">
              <div className="py-2">
                <button
                  onClick={() => { navigate('/tour'); setShowEnvMenu(false); }}
                  className="w-full px-4 py-2.5 text-left hover:bg-indigo-50 transition-colors flex items-center gap-3"
                >
                  <span className="text-lg">TV</span>
                  <span className="text-sm font-medium text-gray-900">A Guided Tour</span>
                </button>
                <button
                  onClick={() => { navigate('/'); setShowEnvMenu(false); }}
                  className="w-full px-4 py-2.5 text-left bg-gradient-to-r from-gray-100 to-gray-50 border-l-4 border-gray-500 transition-colors flex items-center gap-3"
                >
                  <span className="text-lg">🏠</span>
                  <span className="text-sm font-medium text-gray-900">At a Glance</span>
                </button>
                <button
                  onClick={() => { navigate('/mce'); setShowEnvMenu(false); }}
                  className="w-full px-4 py-2.5 text-left hover:bg-blue-50 transition-colors flex items-center gap-3"
                >
                  <span className="text-lg">🌐</span>
                  <span className="text-sm font-medium text-gray-900">MCE Environment</span>
                </button>
                <button
                  onClick={() => { navigate('/minikube'); setShowEnvMenu(false); }}
                  className="w-full px-4 py-2.5 text-left hover:bg-purple-50 transition-colors flex items-center gap-3"
                >
                  <span className="text-lg">🔮</span>
                  <span className="text-sm font-medium text-gray-900">Minikube Environment</span>
                </button>
                <a
                  href="https://jenkins-csb-rhacm-tests.dno.corp.redhat.com/job/CI-Jobs/job/capi_tests/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-full px-4 py-2.5 text-left hover:bg-green-50 transition-colors flex items-center gap-3 block"
                >
                  <span className="text-lg">🤖</span>
                  <span className="text-sm font-medium text-gray-900">Jenkins Dashboard</span>
                </a>
                <a
                  href="https://github.com/tinaafitz/test-automation-capa"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-full px-4 py-2.5 text-left hover:bg-gray-50 transition-colors flex items-center gap-3 block"
                >
                  <span className="text-lg">📦</span>
                  <span className="text-sm font-medium text-gray-900">GitHub Repository</span>
                </a>
                <a
                  href="https://console.dev.redhat.com/openshift/clusters/list"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-full px-4 py-2.5 text-left hover:bg-red-50 transition-colors flex items-center gap-3 block"
                >
                  <span className="text-lg">🔴</span>
                  <span className="text-sm font-medium text-gray-900">OpenShift Staging Cluster List</span>
                </a>
              </div>
            </div>
          )}
        </div>

        {/* Navigation Menu */}
        <div className="flex-shrink-0 border-b border-gray-300">
          <nav className="py-2">
            <button
              onClick={() => setActiveSection('notifications')}
              className={`
                w-full flex items-center gap-3 px-4 py-2.5 text-left text-sm
                transition-all duration-150 ease-in-out
                ${activeSection === 'notifications'
                  ? 'bg-blue-100 text-blue-900 border-l-4 border-blue-600 font-medium shadow-sm'
                  : 'text-gray-700 hover:bg-gray-200 hover:shadow-sm hover:translate-x-0.5'
                }
              `}
            >
              <BellIcon className={`h-5 w-5 ${activeSection === 'notifications' ? 'text-blue-600' : 'text-gray-500'}`} />
              <span className="flex-1">Notifications</span>
            </button>
            <button
              onClick={() => setActiveSection('ai-assistant')}
              className={`
                w-full flex items-center gap-3 px-4 py-2.5 text-left text-sm
                transition-all duration-150 ease-in-out
                ${activeSection === 'ai-assistant'
                  ? 'bg-blue-100 text-blue-900 border-l-4 border-blue-600 font-medium shadow-sm'
                  : 'text-gray-700 hover:bg-gray-200 hover:shadow-sm hover:translate-x-0.5'
                }
              `}
            >
              <span className={activeSection === 'ai-assistant' ? 'text-blue-600 text-lg' : 'text-gray-500 text-lg'}>
                🤖
              </span>
              <span className="flex-1">AI Assistant</span>
            </button>
            <button
              onClick={() => setActiveSection('aws-usage')}
              className={`
                w-full flex items-center gap-3 px-4 py-2.5 text-left text-sm
                transition-all duration-150 ease-in-out
                ${activeSection === 'aws-usage'
                  ? 'bg-blue-100 text-blue-900 border-l-4 border-blue-600 font-medium shadow-sm'
                  : 'text-gray-700 hover:bg-gray-200 hover:shadow-sm hover:translate-x-0.5'
                }
              `}
            >
              <span className={activeSection === 'aws-usage' ? 'text-blue-600 text-lg' : 'text-gray-500 text-lg'}>
                ☁️
              </span>
              <span className="flex-1">AWS Usage</span>
            </button>
          </nav>
        </div>

        {/* Recent Task Section */}
        {allRecentTasks.length > 0 && (
          <div className="flex-1 border-t border-gray-300 bg-gray-100 overflow-hidden flex flex-col">
            <div className="px-4 py-2.5 text-sm text-gray-700 font-medium flex-shrink-0">
              Recent Tasks ({allRecentTasks.length})
            </div>
            <div className="px-4 pb-3 space-y-2 flex-1 overflow-y-auto">
              {allRecentTasks.slice(0, 10).map((task, index) => {
                const status = typeof task.status === 'object' ? task.status.status : task.status;
                const statusIcon = getStatusIcon(task.status);
                // Remove emoji from status text since we show it as an icon
                const statusText = String(status).replace(/[✅❌⚠️⏳🆕]/g, '').trim();

                return (
                  <div
                    key={task.id || index}
                    onClick={() => scrollToSection(tasksRef, 'task-summary')}
                    className="bg-white rounded border border-gray-200 p-2 cursor-pointer hover:bg-gray-50 hover:border-blue-400 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium text-gray-900 truncate">
                          {task.title}
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                            task.environment === 'mce'
                              ? 'bg-blue-100 text-blue-800'
                              : 'bg-purple-100 text-purple-800'
                          }`}>
                            {task.environment === 'mce' ? 'MCE' : 'Minikube'}
                          </span>
                        </div>
                        <div className="text-xs text-gray-600 mt-1 truncate">
                          {statusText}
                        </div>
                      </div>
                      <div className="flex-shrink-0">
                        <span className="text-sm">{statusIcon}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Sidebar Footer */}
        {allRecentTasks.length === 0 && <div className="flex-1"></div>}
        <div
          onClick={() => setActiveSection(null)}
          className="flex-shrink-0 border-t border-gray-300 px-4 py-3 text-sm font-semibold bg-gray-50 cursor-pointer hover:bg-gray-100 transition-colors"
        >
          <div className="flex items-center gap-2">
            <span className="text-base">🏠</span>
            <span className="text-gray-700">At a Glance</span>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Side - Main Content */}
        <div className="flex-1 overflow-y-auto">
          {/* Page Header - Lighter Bar */}
          <div className="bg-gradient-to-r from-blue-50 to-indigo-50 px-6 py-4 shadow-md flex items-center h-[72px] border-b border-blue-100">
            <div>
              <h1 className="text-2xl font-bold leading-tight tracking-tight text-gray-800">
                {activeSection === 'notifications' ? 'Notifications' : activeSection === 'ai-assistant' ? 'AI Assistant' : activeSection === 'aws-usage' ? 'AWS Usage' : 'At a Glance'}
              </h1>
            </div>
          </div>

          <div className="p-6 space-y-8">

          {/* Notifications View */}
          {activeSection === 'notifications' && (
            <div className="space-y-6">
              <h2 className="text-2xl font-bold text-blue-900">Notification Settings</h2>
              <NotificationSettingsInline />
            </div>
          )}

          {/* AI Assistant View */}
          {activeSection === 'ai-assistant' && (
            <div className="space-y-6">
              <h2 className="text-2xl font-bold text-blue-900">AI Assistant</h2>
              <p className="text-gray-600">
                Chat with the AI assistant to get help with CAPI/CAPA automation, troubleshooting, and best practices.
              </p>
              <AIAssistantChat inline={true} />
            </div>
          )}

          {/* AWS Usage View */}
          {activeSection === 'aws-usage' && (
            <div className="space-y-6">
              <h2 className="text-2xl font-bold text-blue-900">AWS Resource Usage</h2>
              <AWSUsageDashboard inline={true} />
            </div>
          )}

          {/* Default: At a Glance View */}
          {activeSection !== 'notifications' && activeSection !== 'ai-assistant' && activeSection !== 'aws-usage' && (
          <>
          {/* ROSA HCP Clusters */}
          <div ref={clustersRef} className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-semibold text-gray-900">ROSA HCP Clusters</h2>
              <button
                onClick={() => clustersRefreshRef.current?.()}
                className="px-4 py-2 bg-blue-50 hover:bg-blue-100 text-blue-700 rounded-md transition-colors font-medium flex items-center gap-2 border border-blue-200"
              >
                <ArrowPathIcon className="h-4 w-4" />
                Refresh
              </button>
            </div>
            <CombinedRosaHcpClusters onRefresh={clustersRefreshRef} />
          </div>

          {/* Task Summary */}
          <div ref={tasksRef} className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-semibold text-gray-900">Task Summary</h2>
              <div className="flex items-center gap-2">
                {allRecentTasks.length > 0 && (
                  <button
                    onClick={() => { recentOps.clearRecentOperations(); setTasksRefreshKey(prev => prev + 1); }}
                    className="px-4 py-2 bg-red-50 hover:bg-red-100 text-red-700 rounded-md transition-colors font-medium flex items-center gap-2 border border-red-200 text-sm"
                  >
                    <TrashIcon className="h-4 w-4" />
                    Clear All
                  </button>
                )}
                <button
                  onClick={handleRefreshTasks}
                  className="px-4 py-2 bg-blue-50 hover:bg-blue-100 text-blue-700 rounded-md transition-colors font-medium flex items-center gap-2 border border-blue-200"
                >
                  <ArrowPathIcon className="h-4 w-4" />
                  Refresh
                </button>
              </div>
            </div>
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 max-h-[calc(100vh-580px)] overflow-y-auto" key={tasksRefreshKey}>
              {allRecentTasks.length === 0 ? (
                <div className="text-center py-12">
                  <ClockIcon className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                  <p className="text-gray-600">No recent tasks</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {allRecentTasks.map((task, index) => {
                    const isExpanded = expandedTasks.has(task.id || index);
                    return (
                      <div key={task.id || index} className="border border-gray-200 rounded-lg hover:shadow-sm transition-shadow">
                        {/* Task Header - Clickable to expand/collapse */}
                        <div
                          onClick={() => toggleTaskExpansion(task.id || index)}
                          className="flex items-start justify-between p-3 cursor-pointer hover:bg-gray-50"
                        >
                          <div className="flex items-center gap-3 flex-1 min-w-0">
                            {isExpanded ? (
                              <ChevronDownIcon className="h-4 w-4 text-gray-400 flex-shrink-0" />
                            ) : (
                              <ChevronRightIcon className="h-4 w-4 text-gray-400 flex-shrink-0" />
                            )}
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <h3 className="font-semibold text-gray-900 text-sm">{task.title}</h3>
                                <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                                  task.environment === 'mce'
                                    ? 'bg-blue-100 text-blue-800'
                                    : 'bg-purple-100 text-purple-800'
                                }`}>
                                  {task.environment === 'mce' ? 'MCE' : 'Minikube'}
                                </span>
                                <span className="text-sm">{getStatusIcon(task.status)}</span>
                              </div>
                              <p className="text-xs text-gray-500 mt-1">
                                {task.timestamp ? new Date(task.timestamp).toLocaleString() : 'No timestamp'}
                              </p>
                            </div>
                          </div>
                        </div>

                        {/* Task Details - Expanded */}
                        {isExpanded && (
                          <div className="px-3 pb-3 space-y-3 border-t border-gray-100 pt-3">
                            {/* Task Details */}
                            <div className="space-y-2 text-sm">
                              {task.playbook && (
                                <div className="flex items-center gap-2">
                                  <span className="font-medium text-gray-700">Playbook:</span>
                                  <span className="text-gray-600 font-mono text-xs">{task.playbook}</span>
                                </div>
                              )}
                              {task.status && (
                                <div className="flex items-start gap-2">
                                  <span className="font-medium text-gray-700">Status:</span>
                                  <span className="text-gray-600">
                                    {typeof task.status === 'object' ? task.status.status : task.status}
                                  </span>
                                </div>
                              )}
                            </div>

                            {/* Task Output */}
                            {task.output && (
                              <div>
                                <div className="flex items-center justify-between mb-2">
                                  <h4 className="text-xs font-medium text-gray-700">Task Output:</h4>
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleCopyOutput(typeof task.output === 'object' ? task.output.output : task.output);
                                    }}
                                    className="px-2 py-1 bg-gray-200 text-gray-700 rounded text-xs font-medium transition-colors hover:bg-gray-300"
                                  >
                                    {copySuccess || '📋 Copy'}
                                  </button>
                                </div>
                                <div className="bg-gray-900 text-green-400 p-3 rounded-lg font-mono text-xs overflow-x-auto max-h-60 overflow-y-auto">
                                  <pre className="whitespace-pre-wrap">
                                    {typeof task.output === 'object' ? task.output.output : task.output}
                                  </pre>
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
          </>
          )}
          </div>
        </div>

        {/* Right Sidebar - Monitoring */}
        <div className="w-96 border-l border-gray-300 bg-gray-50 overflow-y-auto">
          <div className="p-4 space-y-5">
            {/* AWS Resource Quota */}
            <div>
              <AWSQuotaWidget />
            </div>

            {/* Jenkins Test Results */}
            <div ref={jenkinsRef}>
              <JenkinsTestResultsTrend />
            </div>

            {/* GitHub Activity */}
            <div>
              <GitHubRepoActivity />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MainDashboard;
