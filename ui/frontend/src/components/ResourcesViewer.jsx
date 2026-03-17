import React, { useState, useEffect } from 'react';
import { ChevronRightIcon, ChevronDownIcon, ArrowPathIcon } from '@heroicons/react/24/outline';
import { buildApiUrl } from '../config/api';
import { YamlEditorModal } from './YamlEditorModal.js';

const ResourcesViewer = ({ theme = 'mce' }) => {
  const [resources, setResources] = useState([]);
  const [loading, setLoading] = useState(false); // Changed to false so it doesn't show loading spinner on mount
  const [expandedNamespaces, setExpandedNamespaces] = useState(new Set());
  const [totalCount, setTotalCount] = useState(0);
  const [selectedResource, setSelectedResource] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [showYamlModal, setShowYamlModal] = useState(false);
  const [loadingYaml, setLoadingYaml] = useState(false);
  const [activeClusterName, setActiveClusterName] = useState('');

  // Auto-fetch resources on mount
  useEffect(() => {
    fetchResources();
  }, [theme]); // Re-fetch when theme changes

  const fetchResources = async () => {
    setLoading(true);
    try {
      let response, data;

      if (theme === 'minikube') {
        // For Minikube, get active resources from saved Minikube cluster
        const credResponse = await fetch(buildApiUrl('/api/credentials'));
        const credData = await credResponse.json();
        const clusterName = credData.credentials?.minikubeCluster || credData.credentials?.clusterName || 'sat-minikube-test';
        setActiveClusterName(clusterName);

        // Fetch resources from multiple namespaces in parallel with timeout
        const namespaces = ['ns-rosa-hcp', 'capa-system', 'default'];

        const fetchWithTimeout = (namespace, timeoutMs = 8000) => {
          return Promise.race([
            fetch(buildApiUrl('/api/minikube/get-active-resources'), {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                cluster_name: clusterName,
                namespace: namespace
              }),
            }).then(r => r.json()),
            new Promise((_, reject) =>
              setTimeout(() => reject(new Error(`Timeout fetching ${namespace}`)), timeoutMs)
            )
          ]).catch(err => {
            console.warn(`Failed to fetch resources from namespace ${namespace}:`, err.message);
            return { success: false, resources: [] };
          });
        };

        // Fetch all namespaces in parallel
        const results = await Promise.all(
          namespaces.map(ns => fetchWithTimeout(ns))
        );

        // Combine all successful results
        const allResources = results.flatMap(result =>
          result.success && Array.isArray(result.resources) ? result.resources : []
        );

        setResources(allResources);
        setTotalCount(allResources.length);
      } else {
        // For MCE, use the regular endpoint
        response = await fetch(buildApiUrl('/api/mce/resources'));
        data = await response.json();

        if (data.success && data.resources) {
          setResources(data.resources);
          setTotalCount(data.total || data.resources.length || 0);
        }
      }
    } catch (error) {
      console.error('Failed to fetch CAPI resources:', error);
    } finally {
      setLoading(false);
    }
  };

  const toggleNamespace = (namespace) => {
    const newExpanded = new Set(expandedNamespaces);
    if (newExpanded.has(namespace)) {
      newExpanded.delete(namespace);
    } else {
      newExpanded.add(namespace);
    }
    setExpandedNamespaces(newExpanded);
  };

  const handleResourceClick = async (resource) => {
    setLoadingYaml(true);

    // Map display types back to kubectl resource types
    const typeMap = {
      'Secret (ROSA Creds)': 'secret',
      'Secret (AWS Creds)': 'secret',
      'AWSClusterControllerIdentity': 'awsclustercontrolleridentity',
    };
    const rawType = resource.type || resource.kind;
    const kubectlType = typeMap[rawType] || rawType.toLowerCase();

    const requestPayload = {
      cluster_name: activeClusterName,
      resource_type: kubectlType,
      resource_name: resource.name,
      namespace: resource.namespace || '',
    };

    const endpoint = theme === 'minikube'
      ? '/api/minikube/get-resource-detail'
      : '/api/ocp/get-resource-detail';

    try {
      const response = await fetch(buildApiUrl(endpoint), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestPayload),
      });

      const data = await response.json();

      if (data.success && data.data) {
        setSelectedResource({
          yaml_content: data.data,
          cluster_name: resource.name,
          feature_type: 'resource-view',
        });
        setShowYamlModal(true);
      } else {
        console.error('Failed to fetch resource YAML:', data.message || 'Unknown error');
        setErrorMessage(`Failed to fetch YAML: ${data.message || 'Unknown error'}`);
        setTimeout(() => setErrorMessage(''), 5000);
      }
    } catch (error) {
      console.error('Error fetching resource YAML:', error);
      setErrorMessage(`Error fetching YAML: ${error.message}`);
      setTimeout(() => setErrorMessage(''), 5000);
    } finally {
      setLoadingYaml(false);
    }
  };

  const groupedResources = resources.reduce((acc, resource) => {
    const ns = resource.namespace || 'default';
    if (!acc[ns]) {
      acc[ns] = [];
    }
    acc[ns].push(resource);
    return acc;
  }, {});

  // Sort namespaces alphabetically
  const sortedNamespaces = Object.keys(groupedResources).sort();

  const themeColors = theme === 'mce'
    ? { primary: '#2684FF', hover: '#0065FF', border: 'border-cyan-200' }
    : { primary: '#8B5CF6', hover: '#7C3AED', border: 'border-purple-200' };

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div className="text-center py-12">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-cyan-600"></div>
          <p className="mt-4 text-gray-600">Loading resources...</p>
        </div>
      </div>
    );
  }

  // If a resource is selected, show YAML viewer inline
  if (showYamlModal && selectedResource) {
    return (
      <div className="space-y-4">
        {/* Back button */}
        <button
          onClick={() => {
            setShowYamlModal(false);
            setSelectedResource(null);
          }}
          className="flex items-center gap-2 px-4 py-2 text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors font-medium"
        >
          ← Back to Resources
        </button>

        {/* Inline YAML viewer */}
        <YamlEditorModal
          isOpen={true}
          inline={true}
          onClose={() => {
            setShowYamlModal(false);
            setSelectedResource(null);
          }}
          yamlData={selectedResource}
          readOnly={true}
        />
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xl">🔧</span>
          <div>
            <h3 className="text-lg font-semibold text-gray-900">Resources</h3>
            <p className="text-sm text-gray-600">{totalCount} total</p>
          </div>
        </div>
        <button
          onClick={fetchResources}
          className="flex items-center gap-2 px-3 py-1.5 text-sm text-white rounded transition-colors"
          style={{ backgroundColor: themeColors.primary }}
          onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = themeColors.hover)}
          onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = themeColors.primary)}
        >
          <ArrowPathIcon className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {/* Error Message */}
      {errorMessage && (
        <div className="mx-6 mt-2 p-3 bg-red-50 border border-red-200 rounded-lg flex items-center justify-between">
          <span className="text-sm text-red-700">{errorMessage}</span>
          <button onClick={() => setErrorMessage('')} className="text-red-500 hover:text-red-700 text-sm font-medium ml-4">Dismiss</button>
        </div>
      )}

      {/* Resources List */}
      <div className="px-6 py-4">
        {Object.keys(groupedResources).length === 0 ? (
          <div className="text-center py-12 bg-gray-50 border-2 border-dashed border-gray-300 rounded-lg">
            <p className="text-gray-600">No CAPI/CAPA resources found</p>
            <p className="text-sm text-gray-500 mt-2">Resources will appear here after provisioning clusters</p>
          </div>
        ) : (
          <div className="space-y-2">
            {sortedNamespaces.map((namespace) => {
              const nsResources = groupedResources[namespace];
              return (
              <div key={namespace} className="border border-gray-200 rounded-lg overflow-hidden">
                {/* Namespace Header */}
                <button
                  onClick={() => toggleNamespace(namespace)}
                  className="w-full px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors flex items-center justify-between"
                >
                  <div className="flex items-center gap-2">
                    {expandedNamespaces.has(namespace) ? (
                      <ChevronDownIcon className="h-4 w-4 text-gray-600" />
                    ) : (
                      <ChevronRightIcon className="h-4 w-4 text-gray-600" />
                    )}
                    <span className="font-medium text-gray-900">{namespace}</span>
                  </div>
                  <span className="px-2 py-1 bg-white rounded text-xs font-medium text-gray-700">
                    {nsResources.length}
                  </span>
                </button>

                {/* Resource Items */}
                {expandedNamespaces.has(namespace) && (
                  <div className="divide-y divide-gray-100">
                    {nsResources.map((resource, idx) => (
                      <button
                        key={idx}
                        onClick={() => handleResourceClick(resource)}
                        disabled={loadingYaml}
                        className="w-full px-4 py-3 hover:bg-gray-50 transition-colors text-left disabled:opacity-50"
                      >
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-medium text-gray-900">
                            {resource.name}
                          </span>
                          <span className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs font-medium">
                            {resource.type || resource.kind}
                          </span>
                          {resource.status && (
                            <span
                              className={`px-2 py-0.5 rounded text-xs font-medium ${
                                resource.status === 'Ready' || resource.status === 'Running'
                                  ? 'bg-green-100 text-green-700'
                                  : resource.status === 'Pending'
                                  ? 'bg-yellow-100 text-yellow-700'
                                  : 'bg-gray-100 text-gray-700'
                              }`}
                            >
                              {resource.status}
                            </span>
                          )}
                        </div>
                        {resource.age && (
                          <div className="text-xs text-gray-500 mt-1">
                            Age: {resource.age}
                          </div>
                        )}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default ResourcesViewer;
