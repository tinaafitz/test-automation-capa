import React, { useState, useEffect } from 'react';
import { CheckCircleIcon, ExclamationCircleIcon, GlobeAltIcon, ClockIcon } from '@heroicons/react/24/outline';
import PropTypes from 'prop-types';

const ActiveEnvironmentBanner = ({ verificationTimestamp = null, environment = 'mce' }) => {
  const [credentials, setCredentials] = useState(null);
  const [minikubeInfo, setMinikubeInfo] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();
  }, [environment]);

  const fetchData = async () => {
    try {
      if (environment === 'minikube') {
        // Fetch active minikube cluster info
        const response = await fetch('http://localhost:8000/api/minikube/active-profile');
        const data = await response.json();
        if (data.success && data.profile) {
          setMinikubeInfo(data.profile);
        }
      } else {
        // Fetch MCE credentials
        const credResponse = await fetch('http://localhost:8000/api/credentials');
        const credData = await credResponse.json();

        if (credData.success) {
          setCredentials(credData.credentials);
        }
      }
    } catch (error) {
      console.error('Error fetching environment data:', error);
    } finally {
      setLoading(false);
    }
  };

  const extractClusterName = (apiUrl) => {
    if (!apiUrl) return 'Not configured';
    // Extract cluster name from URL like https://api.qe6-vmware-ibm.install.dev09.red-chesterfield.com:6443
    try {
      const url = new URL(apiUrl);
      const hostname = url.hostname;
      // Get the first part before the first dot (e.g., "api.qe6-vmware-ibm" -> "qe6-vmware-ibm")
      const parts = hostname.split('.');
      if (parts[0] === 'api' && parts.length > 1) {
        return parts[1];
      }
      return parts[0];
    } catch {
      return 'Invalid URL';
    }
  };

  if (loading) {
    return null; // Don't show while loading
  }

  // Minikube environment
  if (environment === 'minikube') {
    if (!minikubeInfo) {
      return (
        <div className="bg-yellow-50 border-l-4 border-yellow-400 p-3 mb-4">
          <div className="flex items-center">
            <ExclamationCircleIcon className="h-5 w-5 text-yellow-400 mr-3" />
            <div className="flex-1">
              <p className="text-sm font-medium text-yellow-800">
                No minikube cluster active
              </p>
              <p className="text-xs text-yellow-700 mt-0.5">
                Create or start a minikube cluster to get started
              </p>
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className="bg-gradient-to-r from-purple-50 to-violet-50 border-l-4 border-purple-500 p-3 mb-4 rounded-r-lg shadow-sm">
        <div className="flex items-center">
          <GlobeAltIcon className="h-5 w-5 text-purple-600 mr-3 flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-semibold text-gray-900">Active Environment:</span>
              <span className="text-sm font-medium text-purple-700">{minikubeInfo.name}</span>
              <span className="text-gray-400">•</span>
              <span className="text-xs text-gray-600 font-mono truncate">
                {minikubeInfo.api_url || 'Starting...'}
              </span>
              <span className="text-gray-400">•</span>
              <div className="flex items-center gap-1 text-xs">
                <CheckCircleIcon className="h-3.5 w-3.5 text-green-600" />
                <span className="text-gray-600 font-medium">{minikubeInfo.status || 'Running'}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // MCE environment
  if (!credentials || !credentials.OCP_HUB_API_URL) {
    return (
      <div className="bg-yellow-50 border-l-4 border-yellow-400 p-3 mb-4">
        <div className="flex items-center">
          <ExclamationCircleIcon className="h-5 w-5 text-yellow-400 mr-3" />
          <div className="flex-1">
            <p className="text-sm font-medium text-yellow-800">
              No environment selected
            </p>
            <p className="text-xs text-yellow-700 mt-0.5">
              Please configure credentials or select an environment to get started
            </p>
          </div>
        </div>
      </div>
    );
  }

  const clusterName = extractClusterName(credentials.OCP_HUB_API_URL);

  const formatLastVerified = (timestamp) => {
    if (!timestamp) return null;
    try {
      const date = new Date(timestamp);
      return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return null;
    }
  };

  return (
    <div className="bg-gradient-to-r from-cyan-50 to-blue-50 border-l-4 border-cyan-500 p-3 mb-4 rounded-r-lg shadow-sm">
      <div className="flex items-center">
        <GlobeAltIcon className="h-5 w-5 text-cyan-600 mr-3 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-gray-900">Active Environment:</span>
            <span className="text-sm font-medium text-cyan-700">{clusterName}</span>
            <span className="text-gray-400">•</span>
            <span className="text-xs text-gray-600 font-mono truncate">
              {credentials.OCP_HUB_API_URL}
            </span>
            <span className="text-gray-400">•</span>
            {verificationTimestamp ? (
              <div className="flex items-center gap-1 text-xs text-gray-600">
                <ClockIcon className="h-3.5 w-3.5 text-green-600" />
                <span>Verified: {formatLastVerified(verificationTimestamp)}</span>
              </div>
            ) : (
              <div className="flex items-center gap-1 text-xs text-orange-600">
                <ExclamationCircleIcon className="h-3.5 w-3.5" />
                <span className="font-medium">Not verified</span>
              </div>
            )}
            <CheckCircleIcon className="h-4 w-4 text-green-500 flex-shrink-0" />
          </div>
        </div>
      </div>
    </div>
  );
};

ActiveEnvironmentBanner.propTypes = {
  verificationTimestamp: PropTypes.string,
  environment: PropTypes.oneOf(['mce', 'minikube']),
};

export default ActiveEnvironmentBanner;
