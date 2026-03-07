import React from 'react';
import {
  CheckCircleIcon,
  ExclamationCircleIcon,
  ArrowPathIcon
} from '@heroicons/react/24/outline';

/**
 * AgentStatusBadge - Status indicator for agent operations
 *
 * Features:
 * - Color-coded status display
 * - Loading animation
 * - Icon representation
 * - Compact design
 */
const AgentStatusBadge = ({
  status = "pending", // pending, spawning, running, completed, failed
  showIcon = true,
  size = "medium" // small, medium, large
}) => {
  // Status configurations
  const statusConfig = {
    pending: {
      label: "Pending",
      color: "bg-gray-100 text-gray-700 border-gray-300",
      icon: <div className="h-2 w-2 rounded-full bg-gray-500"></div>
    },
    spawning: {
      label: "Initializing",
      color: "bg-blue-50 text-blue-700 border-blue-300",
      icon: <ArrowPathIcon className="h-4 w-4 animate-spin" />
    },
    running: {
      label: "Analyzing",
      color: "bg-purple-50 text-purple-700 border-purple-300",
      icon: <ArrowPathIcon className="h-4 w-4 animate-spin" />
    },
    completed: {
      label: "Completed",
      color: "bg-green-50 text-green-700 border-green-300",
      icon: <CheckCircleIcon className="h-4 w-4" />
    },
    failed: {
      label: "Failed",
      color: "bg-red-50 text-red-700 border-red-300",
      icon: <ExclamationCircleIcon className="h-4 w-4" />
    }
  };

  // Size configurations
  const sizeConfig = {
    small: "px-2 py-1 text-xs",
    medium: "px-3 py-1.5 text-sm",
    large: "px-4 py-2 text-base"
  };

  const config = statusConfig[status] || statusConfig.pending;

  return (
    <div className={`
      inline-flex items-center gap-2 rounded-full border
      ${config.color}
      ${sizeConfig[size]}
      font-medium
    `}>
      {showIcon && config.icon}
      <span>{config.label}</span>
    </div>
  );
};

export default AgentStatusBadge;
