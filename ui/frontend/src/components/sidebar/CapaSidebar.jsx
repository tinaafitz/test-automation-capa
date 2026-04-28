/* eslint-disable no-unused-vars */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ChartBarIcon,
  Cog6ToothIcon,
  CheckCircleIcon,
  BellIcon,
  PlusCircleIcon,
  TrashIcon,
  ArrowPathIcon,
  ClockIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  Bars3Icon,
  KeyIcon,
  GlobeAltIcon,
  RocketLaunchIcon,
  CloudIcon,
  DocumentTextIcon,
  BoltIcon,
  QueueListIcon,
  CpuChipIcon,
} from '@heroicons/react/24/outline';
import { useRecentOperationsContext, useApiStatusContext } from '../../store/AppContext';

/**
 * CapaSidebar - Navigation sidebar for CAPA automation
 *
 * Features:
 * - Navigation menu with icons
 * - Tasks section (expandable)
 * - Clean gray background
 * - Active state highlighting
 */
const CapaSidebar = ({
  onComponentsClick,
  onVerifyClick,
  onConfigureClick,
  onReconfigureClick,
  onProvisionClick,
  onRosaHcpClustersClick,
  onResourcesClick,
  onEnvironmentsClick,
  onCredentialsClick,
  onAIAssistantClick,
  onTerminalClick,
  onNotificationsClick,
  onRecentTasksClick,
  onAWSUsageClick,
  onAgentDashboardClick,
  onWorkflowsClick,
  onClusterActionsClick,
  onOrchestratorClick,
  activeSection = 'credentials',
  environment = 'mce' // 'mce' or 'minikube'
}) => {
  const [isRecentTasksExpanded, setIsRecentTasksExpanded] = useState(true);
  const recentOps = useRecentOperationsContext();
  const apiStatus = useApiStatusContext();

  // Get recent operations filtered by current environment
  const recentTests = (recentOps.recentOperations || []).filter(
    (op) => op.environment === environment
  );

  // Format timestamp for display
  const formatTime = (timestamp) => {
    if (!timestamp) return '';
    const date = typeof timestamp === 'number' ? new Date(timestamp) : new Date(timestamp);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  // Get status icon based on operation status
  const getStatusIcon = (status) => {
    if (!status) return '⏳';
    // Handle object status (with {status, output} structure)
    const statusStr = typeof status === 'object' ? (status.status || '') : String(status);
    const lower = statusStr.toLowerCase();
    // Check failure/warning first — status text may contain mixed emoji from detailed messages
    if (lower.includes('fail') && !lower.includes('configuration')) return '❌';
    if (lower.includes('error') || lower.includes('authentication failed')) return '❌';
    if (lower.includes('warn')) return '⚠️';
    // Configuration Required is not a failure or running state - it's complete but needs action
    if (statusStr.includes('🆕') || lower.includes('configuration required')) return '🆕';
    if (lower.includes('success') || lower.includes('verified') || lower.includes('passed')) return '✅';
    // Only show hourglass for things that are actually in progress
    if (lower.includes('running') || lower.includes('verifying') || lower.includes('in progress')) return '⏳';
    // Default for completed tasks without explicit status
    return '📄';
  };

  // Navigation menu items grouped by section
  const menuGroups = [
    {
      label: 'SETUP',
      items: [
        {
          id: 'environments',
          label: 'Environments',
          icon: <GlobeAltIcon className="h-5 w-5" />,
          onClick: onEnvironmentsClick,
          showInEnvironments: ['minikube']
        },
        {
          id: 'credentials',
          label: 'Credentials',
          icon: <KeyIcon className="h-5 w-5" />,
          onClick: onCredentialsClick,
          showInEnvironments: ['mce']
        },
        {
          id: 'verify',
          label: 'Verify',
          icon: <CheckCircleIcon className="h-5 w-5" />,
          onClick: onVerifyClick,
          showInEnvironments: ['mce']
        },
        {
          id: 'configure',
          label: 'Configure',
          icon: <Cog6ToothIcon className="h-5 w-5" />,
          onClick: onConfigureClick
        },
        {
          id: 'reconfigure',
          label: 'Set Custom CAPA Image',
          icon: <ArrowPathIcon className="h-5 w-5" />,
          onClick: onReconfigureClick,
          showInEnvironments: ['minikube']
        },
      ],
    },
    {
      label: 'CLUSTERS',
      items: [
        {
          id: 'workflows',
          label: 'Workflows',
          icon: <QueueListIcon className="h-5 w-5" />,
          onClick: onWorkflowsClick
        },
        {
          id: 'rosa-hcp-clusters',
          label: 'ROSA HCP Clusters',
          icon: <CloudIcon className="h-5 w-5" />,
          onClick: onRosaHcpClustersClick
        },
        {
          id: 'provision',
          label: 'Provision',
          icon: <RocketLaunchIcon className="h-5 w-5" />,
          onClick: onProvisionClick
        },
        {
          id: 'resources',
          label: 'CAPA Resources',
          icon: <DocumentTextIcon className="h-5 w-5" />,
          onClick: onResourcesClick
        },
        {
          id: 'cluster-actions',
          label: 'Cluster Actions',
          icon: <BoltIcon className="h-5 w-5" />,
          onClick: onClusterActionsClick,
          showInEnvironments: ['mce']
        },
        {
          id: 'orchestrator',
          label: 'Workflow Orchestrator',
          icon: <BoltIcon className="h-5 w-5" />,
          onClick: onOrchestratorClick,
          showInEnvironments: ['mce']
        },
      ],
    },
    {
      label: 'TOOLS',
      items: [
        {
          id: 'recent-tasks',
          label: 'Task Summary',
          icon: <ClockIcon className="h-5 w-5" />,
          onClick: onRecentTasksClick
        },
      ],
    },
  ];

  // Filter items per group based on environment
  const filteredGroups = menuGroups.map(group => ({
    ...group,
    items: group.items.filter(item => {
      if (!item.showInEnvironments) return true;
      return item.showInEnvironments.includes(environment);
    }),
  })).filter(group => group.items.length > 0);

  const [showEnvMenu, setShowEnvMenu] = useState(false);
  const navigate = useNavigate();

  const handleEnvironmentSwitch = (url) => {
    navigate(url);
    setShowEnvMenu(false); // Close menu after navigation
  };

  return (
    <div className="w-72 bg-gray-50 border-r border-gray-200 flex flex-col h-full">
      {/* Sidebar Title - White background with black text */}
      <div className="flex-shrink-0 bg-white px-4 py-4 border-b border-gray-300 h-[72px] relative">
        <div className="flex items-center justify-between gap-3">
          <h1 className="text-2xl font-bold text-gray-900 leading-tight flex-1">CAPA Automation</h1>
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
                onClick={() => handleEnvironmentSwitch('/')}
                className="w-full px-4 py-2.5 text-left hover:bg-green-50 transition-colors flex items-center gap-3"
              >
                <span className="text-lg">🏠</span>
                <span className="text-sm font-medium text-gray-900">At a Glance</span>
              </button>
              <button
                onClick={() => handleEnvironmentSwitch('/mce')}
                className="w-full px-4 py-2.5 text-left hover:bg-blue-50 transition-colors flex items-center gap-3"
              >
                <span className="text-lg">🌐</span>
                <span className="text-sm font-medium text-gray-900">MCE Environment</span>
              </button>
              <button
                onClick={() => handleEnvironmentSwitch('/minikube')}
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
      <div className="flex-shrink-0 border-b border-gray-200">
        <nav className="py-1">
          {filteredGroups.map((group, groupIndex) => (
            <div key={group.label}>
              {groupIndex > 0 && <div className="mx-4 my-1.5 border-t border-gray-200" />}
              <div className="px-4 pt-3 pb-1">
                <span className="text-xs font-bold tracking-widest text-gray-400 uppercase">
                  {group.label}
                </span>
              </div>
              {group.items.map((item) => (
                <button
                  key={item.id}
                  onClick={() => {
                    if (typeof item.onClick === 'function') item.onClick();
                  }}
                  className={`
                    w-full flex items-center gap-3 px-4 py-2 text-left text-sm
                    transition-all duration-150 ease-in-out
                    ${activeSection === item.id
                      ? 'bg-blue-50 text-blue-700 border-l-4 border-blue-500 font-semibold'
                      : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                    }
                  `}
                >
                  <span className={activeSection === item.id
                    ? 'text-blue-500' : 'text-gray-400'}>
                    {item.icon}
                  </span>
                  <span className="flex-1">{item.label}</span>
                </button>
              ))}
            </div>
          ))}
        </nav>
      </div>

      {/* Recent Task Section */}
      {recentTests.length > 0 && (
        <div className="flex-1 border-t border-gray-200 bg-gray-50 overflow-hidden flex flex-col">
          <div className="px-4 pt-3 pb-1.5 flex-shrink-0">
            <span className="text-xs font-bold tracking-widest text-gray-400 uppercase">
              Recent Tasks ({recentTests.length})
            </span>
          </div>
          <div className="px-3 pb-3 space-y-1.5 flex-1 overflow-y-auto">
            {recentTests.map((task, index) => {
              const status = typeof task.status === 'object' ? task.status.status : task.status;
              const statusIcon = getStatusIcon(task.status);
              const statusText = String(status).replace(/[✅❌⚠️⏳]/g, '').trim();

              return (
                <div
                  key={task.id || index}
                  onClick={onRecentTasksClick}
                  className="bg-white rounded-md border border-gray-200 p-2.5 cursor-pointer hover:bg-blue-50 hover:border-blue-300 transition-all duration-150"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium text-gray-800 truncate">
                        {task.title}
                      </div>
                      <div className="text-[11px] text-gray-500 mt-0.5 truncate">
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
      <div className="flex-shrink-0 border-t border-gray-200 px-4 py-3 bg-white">
        <div className="flex items-center gap-2">
          <GlobeAltIcon className="h-4 w-4 text-gray-400" />
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
            {environment === 'minikube' ? 'Minikube' : 'MCE'} Environment
          </span>
        </div>
      </div>
    </div>
  );
};

export default CapaSidebar;
