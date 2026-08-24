import React, { useState, useEffect } from 'react';
import { CheckCircleIcon, ExclamationCircleIcon, GlobeAltIcon, ClockIcon } from '@heroicons/react/24/outline';
import PropTypes from 'prop-types';

const ActiveEnvironmentBanner = ({ verificationTimestamp = null, environment = 'mce', mceInfo = null }) => {
  const [credentials, setCredentials] = useState(null);
  const [minikubeInfo, setMinikubeInfo] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();
  }, [environment]);

  const fetchData = async () => {
    try {
      if (environment === 'minikube') {
        // Fetch selected minikube cluster from credentials (not active profile)
        const credResponse = await fetch('http://localhost:8000/api/credentials');
        const credData = await credResponse.json();

        // Check for either minikubeCluster or clusterName field
        const savedCluster = credData.credentials?.minikubeCluster || credData.credentials?.clusterName;

        if (credData.success && savedCluster) {
          // User has selected a minikube cluster
          setMinikubeInfo({
            name: savedCluster,
            api_url: `https://127.0.0.1:${credData.credentials.apiPort || 8443}`,
            status: 'Running',
          });
        } else {
          // Fallback to active profile if no credentials saved
          const response = await fetch('http://localhost:8000/api/minikube/active-profile');
          const data = await response.json();
          if (data.success && data.profile) {
            setMinikubeInfo(data.profile);
          }
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
      <div className="bg-gradient-to-r from-purple-50 to-violet-50 border-l-4 border-purple-500 p-3 mb-6 rounded-r-lg shadow-md hover:shadow-lg transition-shadow">
        <div className="flex items-center">
          <div className="flex items-center justify-center w-8 h-8 bg-purple-100 rounded-full mr-3 flex-shrink-0">
            <GlobeAltIcon className="h-4 w-4 text-purple-600" />
          </div>
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
    <div className="bg-gradient-to-r from-cyan-50 to-blue-50 border-l-4 border-cyan-500 p-3 mb-6 rounded-r-lg shadow-md hover:shadow-lg transition-shadow">
      <div className="flex items-center">
        <div className="flex items-center justify-center w-8 h-8 bg-cyan-100 rounded-full mr-3 flex-shrink-0">
          <GlobeAltIcon className="h-4 w-4 text-cyan-600" />
        </div>
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
          {mceInfo && (
            <div className="flex items-center gap-2 mt-1.5 ml-11 flex-wrap">
              {mceInfo.ocpVersion && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
                  OCP {mceInfo.ocpVersion}
                </span>
              )}
              {mceInfo.acmVersion && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
                  ACM {mceInfo.acmVersion}
                </span>
              )}
              {mceInfo.version && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-cyan-100 text-cyan-800">
                  MCE {mceInfo.version}
                </span>
              )}
              {(mceInfo.capiImage || mceInfo.capaImage) && (
                <span className="text-gray-300 mx-0.5">|</span>
              )}
              {mceInfo.capiImage && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono text-gray-500 bg-gray-100" title={mceInfo.capiImage}>
                  CAPI: {mceInfo.capiImage.split('/').pop().split('@')[0]}
                </span>
              )}
              {mceInfo.capaImage && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono text-gray-500 bg-gray-100" title={mceInfo.capaImage}>
                  CAPA: {mceInfo.capaImage.split('/').pop().split('@')[0]}
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

ActiveEnvironmentBanner.propTypes = {
  verificationTimestamp: PropTypes.string,
  environment: PropTypes.oneOf(['mce', 'minikube']),
  mceInfo: PropTypes.object,
};

export default ActiveEnvironmentBanner;
