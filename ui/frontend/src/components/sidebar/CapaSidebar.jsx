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
  onTestClick,
  onTestSuiteDashboardClick,
  onTestAutomationClick,
  onAIAssistantClick,
  onHelmChartMatrixClick,
  onTerminalClick,
  onNotificationsClick,
  onRecentTasksClick,
  activeSection = 'environments',
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
    if (statusStr.includes('✅') || statusStr.toLowerCase().includes('success') || statusStr.toLowerCase().includes('verified')) return '✅';
    if (statusStr.includes('❌') || (statusStr.toLowerCase().includes('fail') && !statusStr.toLowerCase().includes('configuration'))) return '❌';
    if (statusStr.includes('⚠️') || statusStr.toLowerCase().includes('warn')) return '⚠️';
    // Configuration Required is not a failure or running state - it's complete but needs action
    if (statusStr.includes('🆕') || statusStr.toLowerCase().includes('configuration required')) return '🆕';
    // Only show hourglass for things that are actually in progress
    if (statusStr.includes('⏳') || statusStr.toLowerCase().includes('running') || statusStr.toLowerCase().includes('verifying')) return '⏳';
    // Default for completed tasks without explicit status
    return '📄';
  };

  // Navigation menu items
  const allMenuItems = [
    {
      id: 'environments',
      label: 'Environments',
      icon: <span className="text-lg">🌍</span>,
      onClick: onEnvironmentsClick
    },
    {
      id: 'credentials',
      label: 'Credentials',
      icon: <span className="text-lg">🔑</span>,
      onClick: onCredentialsClick,
      showInEnvironments: ['mce'] // Only show in MCE, not minikube
    },
    {
      id: 'verify',
      label: 'Verify',
      icon: <CheckCircleIcon className="h-5 w-5" />,
      onClick: onVerifyClick,
      showInEnvironments: ['mce'] // Only show in MCE, not minikube
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
      showInEnvironments: ['minikube'] // Only show in Minikube, not MCE
    },
    {
      id: 'provision',
      label: 'Provision',
      icon: <span className="text-lg">🚀</span>,
      onClick: onProvisionClick
    },
    {
      id: 'resources',
      label: 'CAPA Resources',
      icon: <span className="text-lg">📄</span>,
      onClick: onResourcesClick
    },
    {
      id: 'rosa-hcp-clusters',
      label: 'ROSA HCP Clusters',
      icon: <span className="text-lg">☁️</span>,
      onClick: onRosaHcpClustersClick
    },
    {
      id: 'test-automation',
      label: 'Playbooks',
      icon: <ArrowPathIcon className="h-5 w-5" />,
      onClick: onTestAutomationClick
    },
    {
      id: 'test-suite-dashboard',
      label: 'Feature Test Dashboard',
      icon: <span className="text-lg">🧪</span>,
      onClick: onTestSuiteDashboardClick,
      showInEnvironments: ['mce'] // Only show in MCE, not minikube
    },
    {
      id: 'helm-chart-matrix',
      label: 'Helm Chart Test Matrix',
      icon: <span className="text-lg">📊</span>,
      onClick: onHelmChartMatrixClick
    },
    {
      id: 'terminal',
      label: 'Terminal',
      icon: <span className="text-lg">💻</span>,
      onClick: onTerminalClick
    },
    {
      id: 'notifications',
      label: 'Notifications',
      icon: <BellIcon className="h-5 w-5" />,
      onClick: onNotificationsClick
    },
    {
      id: 'recent-tasks',
      label: 'Task Summary',
      icon: <ClockIcon className="h-5 w-5" />,
      onClick: onRecentTasksClick
    },
    {
      id: 'ai-assistant',
      label: 'AI Assistant',
      icon: <span className="text-lg">🤖</span>,
      onClick: onAIAssistantClick
    },
  ];

  // Filter menu items based on environment
  const menuItems = allMenuItems.filter(item => {
    // If item doesn't specify environments, show it in all environments
    if (!item.showInEnvironments) return true;
    // Otherwise, only show if current environment is in the list
    return item.showInEnvironments.includes(environment);
  });

  const [showEnvMenu, setShowEnvMenu] = useState(false);
  const navigate = useNavigate();

  const handleEnvironmentSwitch = (url) => {
    navigate(url);
    setShowEnvMenu(false); // Close menu after navigation
  };

  return (
    <div className="w-72 bg-gray-100 border-r border-gray-300 flex flex-col h-full">
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
                <span className="text-sm font-medium text-gray-900">Main Dashboard</span>
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
      <div className="flex-shrink-0 border-b border-gray-300">
        <nav className="py-2">
          {menuItems.map((item) => (
            <div key={item.id}>
              {/* Menu Item */}
              <button
                onClick={() => {
                  if (typeof item.onClick === 'function') item.onClick();
                }}
                className={`
                  w-full flex items-center gap-3 px-4 py-2.5 text-left text-sm
                  transition-all duration-150 ease-in-out
                  ${activeSection === item.id
                    ? 'bg-blue-100 text-blue-900 border-l-4 border-blue-600 font-medium shadow-sm'
                    : 'text-gray-700 hover:bg-gray-200 hover:shadow-sm hover:translate-x-0.5'
                  }
                `}
              >
                <span className={activeSection === item.id
                  ? 'text-blue-600' : 'text-gray-500'}>
                  {item.icon}
                </span>
                <span className="flex-1">{item.label}</span>
              </button>
            </div>
          ))}
        </nav>
      </div>

      {/* Recent Task Section */}
      {recentTests.length > 0 && (
        <div className="flex-1 border-t border-gray-300 bg-gray-100 overflow-hidden flex flex-col">
          <div className="px-4 py-2.5 text-sm text-gray-700 font-medium flex-shrink-0">
            Recent Tasks ({recentTests.length})
          </div>
          <div className="px-4 pb-3 space-y-2 flex-1 overflow-y-auto">
            {recentTests.map((task, index) => {
              const status = typeof task.status === 'object' ? task.status.status : task.status;
              const statusIcon = getStatusIcon(task.status);
              // Remove emoji from status text since we show it as an icon
              const statusText = String(status).replace(/[✅❌⚠️⏳]/g, '').trim();

              return (
                <div
                  key={task.id || index}
                  onClick={onRecentTasksClick}
                  className="bg-white rounded border border-gray-200 p-2 cursor-pointer hover:bg-gray-50 hover:border-blue-400 transition-colors"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium text-gray-900 truncate">
                        {task.title}
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
      <div className="flex-shrink-0 border-t border-gray-300 px-4 py-3 text-sm font-semibold bg-gray-50">
        <div className="flex items-center gap-2">
          <span className="text-base">{environment === 'minikube' ? '🔮' : '🌐'}</span>
          <span className="text-gray-700">{environment === 'minikube' ? 'Minikube Environment' : 'MCE Environment'}</span>
        </div>
      </div>
    </div>
  );
};

export default CapaSidebar;
