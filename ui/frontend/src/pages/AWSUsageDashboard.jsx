import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowPathIcon } from '@heroicons/react/24/outline';
import CapaSidebar from '../components/sidebar/CapaSidebar';
import AWSUsageTrend from '../components/charts/AWSUsageTrend';

const AWSUsageDashboard = () => {
  const navigate = useNavigate();
  const [usage, setUsage] = useState(null);
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [error, setError] = useState(null);
  const [billedResources, setBilledResources] = useState([]);
  const [freeResources, setFreeResources] = useState([]);
  const [configLoading, setConfigLoading] = useState(true);
  const [selectedResource, setSelectedResource] = useState(null);
  const [resourceDetails, setResourceDetails] = useState(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [creatorFilter, setCreatorFilter] = useState('all');
  const [availableCreators, setAvailableCreators] = useState([]);

  // Combine all resources for rendering
  const resourceConfig = [...billedResources, ...freeResources];

  // Fetch resource configuration on component mount
  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/aws/usage-config');
        const data = await response.json();

        if (data.success) {
          setBilledResources(data.billedResources || []);
          setFreeResources(data.freeResources || []);
        } else {
          setError(data.message || 'Failed to load AWS configuration');
        }
      } catch (err) {
        setError(`Error loading configuration: ${err.message}`);
      } finally {
        setConfigLoading(false);
      }
    };

    fetchConfig();
  }, []);

  const fetchUsage = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('http://localhost:8000/api/aws/usage');
      const data = await response.json();

      if (data.success) {
        setUsage(data.usage);
        setLastUpdated(new Date(data.timestamp));
      } else {
        setError(data.message || 'Failed to fetch AWS usage data');
      }
    } catch (err) {
      setError(`Error fetching data: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const fetchResourceDetails = async (resourceType) => {
    setDetailsLoading(true);
    setSelectedResource(resourceType);
    try {
      const response = await fetch(`http://localhost:8000/api/aws/resource-details/${resourceType}`);
      const data = await response.json();

      if (data.success) {
        setResourceDetails(data.details);

        // Extract unique creators from tags
        const creators = new Set();
        data.details.forEach(resource => {
          const createdBy = resource.tags?.CreatedBy || resource.tags?.ManagedBy || 'unknown';
          creators.add(createdBy);
        });
        setAvailableCreators(['all', ...Array.from(creators).sort()]);
        setCreatorFilter('all'); // Reset filter when viewing new resource type
      } else {
        setError(data.message || 'Failed to fetch resource details');
      }
    } catch (err) {
      setError(`Error fetching details: ${err.message}`);
    } finally {
      setDetailsLoading(false);
    }
  };

  const closeDetailsModal = () => {
    setSelectedResource(null);
    setResourceDetails(null);
  };

  // Get status color based on count and threshold
  const getStatusColor = (count, threshold) => {
    if (count === 'error') return 'bg-red-100 border-red-300';
    if (count >= threshold * 0.9) return 'bg-red-100 border-red-300';
    if (count >= threshold * 0.7) return 'bg-yellow-100 border-yellow-300';
    return 'bg-green-100 border-green-300';
  };

  // Get text color based on count and threshold
  const getTextColor = (count, threshold) => {
    if (count === 'error') return 'text-red-700';
    if (count >= threshold * 0.9) return 'text-red-700';
    if (count >= threshold * 0.7) return 'text-yellow-700';
    return 'text-green-700';
  };

  // Calculate estimated monthly cost
  const calculateCost = (resource) => {
    if (!usage || !resource || !resource.costPerMonth) return null;
    const count = usage[resource.key];
    if (count === 'error' || count === undefined) return null;
    return (count * resource.costPerMonth).toFixed(2);
  };

  const sidebarHandlers = {
    onComponentsClick: () => navigate('/mce'),
    onVerifyClick: () => navigate('/mce'),
    onConfigureClick: () => navigate('/mce'),
    onProvisionClick: () => navigate('/mce'),
    onRosaHcpClustersClick: () => navigate('/mce'),
    onResourcesClick: () => navigate('/mce'),
    onEnvironmentsClick: () => navigate('/mce'),
    onCredentialsClick: () => navigate('/mce'),
    onTestClick: () => navigate('/mce'),
    onTestSuiteDashboardClick: () => navigate('/mce'),
    onTestAutomationClick: () => navigate('/mce'),
    onAIAssistantClick: () => navigate('/mce'),
    onHelmChartMatrixClick: () => navigate('/mce'),
    onTerminalClick: () => navigate('/mce'),
    onNotificationsClick: () => navigate('/mce'),
    onRecentTasksClick: () => navigate('/mce'),
    onAWSUsageClick: () => navigate('/aws-usage'),
  };

  return (
    <div className="flex h-screen bg-gray-50">
      <CapaSidebar
        {...sidebarHandlers}
        activeSection="aws-usage"
        environment="mce"
      />

      <div className="flex-1 overflow-auto" style={{ backgroundColor: '#FFF5F0' }}>
        {/* Header - Softer AWS Orange Theme */}
        <div className="text-white px-6 py-4 shadow-lg flex items-center justify-between h-[72px]" style={{ background: 'linear-gradient(to right, #FF9900, #FF8C00)' }}>
          <div>
            <h1 className="text-2xl font-bold leading-tight tracking-tight">AWS Resource Usage</h1>
            {lastUpdated && (
              <p className="text-orange-100 text-xs mt-0.5">
                Last updated: {lastUpdated.toLocaleString()}
              </p>
            )}
          </div>
          <button
            onClick={fetchUsage}
            disabled={loading}
            className={`
              flex items-center gap-2 px-6 py-2.5 rounded-lg font-medium text-sm
              transition-all duration-200 shadow-md
              ${loading
                ? 'bg-white/20 text-white/50 cursor-not-allowed'
                : 'bg-white text-orange-600 hover:bg-orange-50 hover:shadow-lg'
              }
            `}
          >
            <ArrowPathIcon className={`h-5 w-5 ${loading ? 'animate-spin' : ''}`} />
            {loading ? 'Loading...' : 'Refresh Data'}
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          {/* Description */}
          <div className="mb-4">
            <p className="text-gray-600 text-sm">
              Monitor your AWS resource counts across all services
            </p>
            <p className="text-gray-500 text-xs mt-1 flex items-center gap-1">
              <span className="inline-block w-1 h-1 rounded-full bg-gray-400"></span>
              Data may take a few minutes to load as it queries all AWS resources
            </p>
          </div>

          {error && (
            <div className="bg-red-50 border border-red-300 rounded-lg p-4 mb-6">
              <p className="text-red-700 font-medium">Error</p>
              <p className="text-red-600 text-sm mt-1">{error}</p>
            </div>
          )}

          {configLoading && (
            <div className="bg-blue-50 border border-blue-300 rounded-lg p-8 text-center">
              <p className="text-blue-700 text-lg font-medium">
                Loading AWS resource configuration...
              </p>
              <p className="text-blue-600 text-sm mt-2">
                Fetching resource thresholds and AWS quotas
              </p>
            </div>
          )}

          {!configLoading && !usage && !loading && !error && (
            <div className="bg-blue-50 border border-blue-300 rounded-lg p-8 text-center">
              <p className="text-blue-700 text-lg font-medium">
                Click "Refresh Data" to load AWS resource usage
              </p>
              <p className="text-blue-600 text-sm mt-2">
                This will query your AWS account for current resource counts
              </p>
              <p className="text-blue-500 text-xs mt-1 italic">
                Note: Loading may take a few minutes as it queries all AWS services
              </p>
            </div>
          )}

          {usage && (
            <>
              {/* Cost Summary - List format */}
              {(() => {
                // Calculate costs for resources with usage > 0
                const natCost = usage.nat_gateways > 0 ? calculateCost(resourceConfig.find(r => r.key === 'nat_gateways')) : null;
                const route53Cost = usage.route53_zones > 0 ? calculateCost(resourceConfig.find(r => r.key === 'route53_zones')) : null;
                const totalCost = (parseFloat(natCost || 0) + parseFloat(route53Cost || 0)).toFixed(2);

                // Only show cost summary if there are actual costs
                if (!natCost && !route53Cost) return null;

                return (
                  <div className="mb-4 bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
                    <div className="flex items-center gap-2 mb-3">
                      <span className="text-lg">💰</span>
                      <h2 className="text-base font-bold text-gray-900">Cost Summary</h2>
                    </div>
                    <div className="space-y-2">
                      {natCost && (
                        <div className="flex items-center justify-between py-2 px-3 bg-gray-50 rounded">
                          <div className="flex items-center gap-2">
                            <span className="text-sm">🌉</span>
                            <div>
                              <p className="text-sm font-medium text-gray-900">NAT Gateways</p>
                              <p className="text-xs text-gray-500">{usage.nat_gateways} gateways × $32.40/month</p>
                            </div>
                          </div>
                          <p className="text-lg font-bold text-blue-600">${natCost}</p>
                        </div>
                      )}
                      {route53Cost && (
                        <div className="flex items-center justify-between py-2 px-3 bg-gray-50 rounded">
                          <div className="flex items-center gap-2">
                            <span className="text-sm">🌐</span>
                            <div>
                              <p className="text-sm font-medium text-gray-900">Route53 Zones</p>
                              <p className="text-xs text-gray-500">{usage.route53_zones} zones × $0.50/month</p>
                            </div>
                          </div>
                          <p className="text-lg font-bold text-cyan-600">${route53Cost}</p>
                        </div>
                      )}
                      <div className="flex items-center justify-between py-2 px-3 bg-green-50 rounded border border-green-200 mt-2">
                        <div className="flex items-center gap-2">
                          <span className="text-sm">💵</span>
                          <p className="text-sm font-bold text-gray-900">Total Estimated Cost</p>
                        </div>
                        <p className="text-xl font-bold text-green-700">${totalCost}/month</p>
                      </div>
                    </div>
                  </div>
                );
              })()}

              {/* Status Guide */}
              <div className="mb-4 bg-white border border-gray-200 rounded-lg p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <span className="text-xs font-semibold text-gray-700">Status Guide:</span>
                    <div className="flex items-center gap-2">
                      <div className="flex items-center gap-1">
                        <div className="w-3 h-3 bg-green-100 border border-green-300 rounded"></div>
                        <span className="text-xs text-gray-600">Safe (&lt;70%)</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <div className="w-3 h-3 bg-yellow-100 border border-yellow-300 rounded"></div>
                        <span className="text-xs text-gray-600">Warning (70-89%)</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <div className="w-3 h-3 bg-red-100 border border-red-300 rounded"></div>
                        <span className="text-xs text-gray-600">Critical (≥90%)</span>
                      </div>
                    </div>
                  </div>
                  <span className="text-xs text-gray-500 italic">Based on AWS service limits</span>
                </div>
              </div>

              {/* Usage Trend Chart */}
              <div className="mb-4">
                <AWSUsageTrend />
              </div>

              {/* Billed Resources Section */}
              <div className="mb-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-lg">💰</span>
                  <h3 className="text-base font-bold text-gray-900">Resources with Costs</h3>
                  <span className="text-xs text-gray-500 italic">These resources incur monthly charges</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {billedResources.map((resource) => {
                    const count = usage[resource.key];
                    const cost = calculateCost(resource);
                    const isError = count === 'error';
                    const statusColor = getStatusColor(count, resource.threshold);
                    const textColor = getTextColor(count, resource.threshold);

                    return (
                      <div
                        key={resource.key}
                        onClick={() => count > 0 && !isError && fetchResourceDetails(resource.key)}
                        className={`
                          border-2 rounded-lg p-3 transition-all duration-300
                          hover:shadow-xl hover:scale-102
                          ${statusColor}
                          ${count > 0 && !isError ? 'cursor-pointer' : 'cursor-default'}
                        `}
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="flex items-center gap-1.5 mb-1">
                              <span className="text-base">{resource.icon}</span>
                              <h3 className="font-semibold text-gray-900 text-xs">
                                {resource.label}
                              </h3>
                            </div>

                            <p className="text-xs text-gray-500 mb-1.5">
                              {resource.description}
                            </p>

                            <div className="flex items-center gap-2">
                              <div className={`text-2xl font-bold ${textColor} mb-0.5`}>
                                {isError ? '⚠️' : count?.toLocaleString() || '0'}
                              </div>
                              {count > 0 && !isError && (
                                <span className="text-xs text-blue-600 font-semibold underline cursor-pointer">
                                  Details →
                                </span>
                              )}
                            </div>

                            {isError && (
                              <p className="text-xs text-red-600 font-medium">
                                Failed to fetch
                              </p>
                            )}

                            {!isError && count >= resource.threshold * 0.7 && (
                              <p className="text-xs font-medium">
                                {count >= resource.threshold * 0.9
                                  ? '🔴 Critical: Near limit'
                                  : '🟡 Warning: High usage'}
                              </p>
                            )}

                            {!isError && (
                              <div className="mt-0.5">
                                <p className="text-xs text-gray-500">
                                  Limit: {resource.threshold.toLocaleString()} ({Math.round((count / resource.threshold) * 100)}% used)
                                </p>
                              </div>
                            )}

                            {/* Cost display for billed resources */}
                            {!isError && (
                              <div className="mt-1.5 pt-1.5 border-t border-orange-200 bg-orange-50/50 -mx-3 -mb-3 px-3 py-1.5 rounded-b-lg">
                                <p className="text-xs text-gray-600 font-medium">Est. Monthly Cost</p>
                                {resource.costType === 'fixed' && cost ? (
                                  <p className="text-sm font-bold text-orange-600">
                                    ${cost}
                                  </p>
                                ) : resource.costType === 'variable' ? (
                                  <p className="text-xs font-semibold text-orange-600">
                                    Variable
                                  </p>
                                ) : (
                                  <p className="text-xs font-semibold text-gray-500">
                                    $0.00
                                  </p>
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Free Resources Section */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-lg">📊</span>
                  <h3 className="text-base font-bold text-gray-900">Quota Management Resources</h3>
                  <span className="text-xs text-gray-500 italic">No direct costs - monitor for quota limits only</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5 gap-3">
                  {freeResources.map((resource) => {
                    const count = usage[resource.key];
                    const isError = count === 'error';
                    const statusColor = getStatusColor(count, resource.threshold);
                    const textColor = getTextColor(count, resource.threshold);

                    return (
                      <div
                        key={resource.key}
                        onClick={() => count > 0 && !isError && fetchResourceDetails(resource.key)}
                        className={`
                          border-2 rounded-lg p-3 transition-all duration-300
                          hover:shadow-xl hover:scale-102
                          ${statusColor}
                          ${count > 0 && !isError ? 'cursor-pointer' : 'cursor-default'}
                        `}
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <div className="flex items-center gap-1.5 mb-1">
                              <span className="text-base">{resource.icon}</span>
                              <h3 className="font-semibold text-gray-900 text-xs">
                                {resource.label}
                              </h3>
                            </div>

                            <p className="text-xs text-gray-500 mb-1.5">
                              {resource.description}
                            </p>

                            <div className="flex items-center gap-2">
                              <div className={`text-2xl font-bold ${textColor} mb-0.5`}>
                                {isError ? '⚠️' : count?.toLocaleString() || '0'}
                              </div>
                              {count > 0 && !isError && (
                                <span className="text-xs text-blue-600 font-semibold underline cursor-pointer">
                                  Details →
                                </span>
                              )}
                            </div>

                            {isError && (
                              <p className="text-xs text-red-600 font-medium">
                                Failed to fetch
                              </p>
                            )}

                            {!isError && count >= resource.threshold * 0.7 && (
                              <p className="text-xs font-medium">
                                {count >= resource.threshold * 0.9
                                  ? '🔴 Critical: Near limit'
                                  : '🟡 Warning: High usage'}
                              </p>
                            )}

                            {!isError && (
                              <div className="mt-0.5">
                                <p className="text-xs text-gray-500">
                                  Limit: {resource.threshold.toLocaleString()} ({Math.round((count / resource.threshold) * 100)}% used)
                                </p>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Resource Details Modal */}
      {selectedResource && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-2xl max-w-6xl w-full max-h-[90vh] overflow-hidden flex flex-col">
            {/* Modal Header */}
            <div className="bg-gradient-to-r from-orange-500 to-orange-600 text-white px-6 py-4 flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold">
                  {resourceConfig.find(r => r.key === selectedResource)?.label || 'Resource Details'}
                </h2>
                <p className="text-orange-100 text-sm mt-1">
                  Click-to-drill down view showing creation time, tags, and metadata
                </p>
              </div>
              <button
                onClick={closeDetailsModal}
                className="text-white hover:bg-white/20 rounded-full p-2 transition-colors"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Modal Content */}
            <div className="flex-1 overflow-auto p-6">
              {detailsLoading ? (
                <div className="flex items-center justify-center h-64">
                  <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-orange-500 mx-auto mb-4"></div>
                    <p className="text-gray-600">Loading resource details...</p>
                  </div>
                </div>
              ) : resourceDetails && resourceDetails.length > 0 ? (
                <div className="space-y-4">
                  {/* Filter and Summary */}
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <p className="text-sm text-blue-800">
                          <strong>Found {resourceDetails.filter(r => creatorFilter === 'all' || r.tags?.CreatedBy === creatorFilter || r.tags?.ManagedBy === creatorFilter).length} resource{resourceDetails.filter(r => creatorFilter === 'all' || r.tags?.CreatedBy === creatorFilter || r.tags?.ManagedBy === creatorFilter).length !== 1 ? 's' : ''}</strong>
                          {creatorFilter !== 'all' && ` created by ${creatorFilter}`}
                          {' '}- Sorted by creation time (most recent first)
                        </p>
                      </div>
                      {availableCreators.length > 2 && (
                        <div className="flex items-center gap-2">
                          <label className="text-xs font-semibold text-blue-800">Filter by Creator:</label>
                          <select
                            value={creatorFilter}
                            onChange={(e) => setCreatorFilter(e.target.value)}
                            className="text-sm border border-blue-300 rounded px-3 py-1 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                          >
                            {availableCreators.map(creator => (
                              <option key={creator} value={creator}>
                                {creator === 'all' ? 'All Creators' : creator}
                              </option>
                            ))}
                          </select>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Resource Cards */}
                  {resourceDetails
                    .filter(r => creatorFilter === 'all' || r.tags?.CreatedBy === creatorFilter || r.tags?.ManagedBy === creatorFilter)
                    .map((resource, index) => (
                    <div key={index} className="border border-gray-200 rounded-lg p-4 hover:shadow-lg transition-shadow bg-white">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {/* Left Column */}
                        <div>
                          <div className="mb-3">
                            <h3 className="text-lg font-bold text-gray-900 mb-1">
                              {resource.name || 'Unnamed Resource'}
                            </h3>
                            <p className="text-xs text-gray-500 font-mono">{resource.id}</p>
                          </div>

                          {resource.created_at && (
                            <div className="mb-2">
                              <span className="text-xs font-semibold text-gray-600">Created:</span>
                              <p className="text-sm text-gray-900">
                                {new Date(resource.created_at).toLocaleString()}
                              </p>
                              <p className="text-xs text-gray-500 mt-1">
                                {(() => {
                                  const created = new Date(resource.created_at);
                                  const now = new Date();
                                  const diffDays = Math.floor((now - created) / (1000 * 60 * 60 * 24));
                                  if (diffDays === 0) return '🔴 Created today';
                                  if (diffDays === 1) return '🟡 Created yesterday';
                                  if (diffDays <= 7) return `🟡 Created ${diffDays} days ago`;
                                  return `Created ${diffDays} days ago`;
                                })()}
                              </p>
                            </div>
                          )}

                          {resource.launch_time && (
                            <div className="mb-2">
                              <span className="text-xs font-semibold text-gray-600">Launched:</span>
                              <p className="text-sm text-gray-900">
                                {new Date(resource.launch_time).toLocaleString()}
                              </p>
                            </div>
                          )}

                          {resource.vpc_id && (
                            <div className="mb-2">
                              <span className="text-xs font-semibold text-gray-600">VPC:</span>
                              <p className="text-sm text-gray-900">{resource.vpc_name || resource.vpc_id}</p>
                            </div>
                          )}

                          {resource.subnet_id && (
                            <div className="mb-2">
                              <span className="text-xs font-semibold text-gray-600">Subnet:</span>
                              <p className="text-sm text-gray-900 font-mono">{resource.subnet_id}</p>
                            </div>
                          )}

                          {resource.public_ip && resource.public_ip !== 'N/A' && (
                            <div className="mb-2">
                              <span className="text-xs font-semibold text-gray-600">Public IP:</span>
                              <p className="text-sm text-gray-900 font-mono">{resource.public_ip}</p>
                            </div>
                          )}

                          {resource.state && (
                            <div className="mb-2">
                              <span className="text-xs font-semibold text-gray-600">State:</span>
                              <span className="ml-2 inline-block px-2 py-1 text-xs font-semibold rounded bg-green-100 text-green-800">
                                {resource.state}
                              </span>
                            </div>
                          )}

                          {resource.description && (
                            <div className="mb-2">
                              <span className="text-xs font-semibold text-gray-600">Description:</span>
                              <p className="text-sm text-gray-900">{resource.description}</p>
                            </div>
                          )}

                          {resource.ingress_rules !== undefined && (
                            <div className="mb-2">
                              <span className="text-xs font-semibold text-gray-600">Inbound Rules:</span>
                              <span className="ml-2 inline-block px-2 py-1 text-xs font-semibold rounded bg-blue-100 text-blue-800">
                                {resource.ingress_rules} {resource.ingress_rules === 1 ? 'rule' : 'rules'}
                              </span>
                            </div>
                          )}

                          {resource.egress_rules !== undefined && (
                            <div className="mb-2">
                              <span className="text-xs font-semibold text-gray-600">Outbound Rules:</span>
                              <span className="ml-2 inline-block px-2 py-1 text-xs font-semibold rounded bg-purple-100 text-purple-800">
                                {resource.egress_rules} {resource.egress_rules === 1 ? 'rule' : 'rules'}
                              </span>
                            </div>
                          )}
                        </div>

                        {/* Right Column - Tags */}
                        <div>
                          <h4 className="text-sm font-bold text-gray-700 mb-2">Tags & Metadata:</h4>
                          {resource.tags && Object.keys(resource.tags).length > 0 ? (
                            <div className="bg-gray-50 rounded p-3 max-h-64 overflow-auto">
                              <table className="w-full text-xs">
                                <tbody>
                                  {Object.entries(resource.tags).map(([key, value]) => (
                                    <tr key={key} className="border-b border-gray-200 last:border-0">
                                      <td className="py-1 pr-2 font-semibold text-gray-600 align-top">{key}:</td>
                                      <td className="py-1 text-gray-900 break-all">{value}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>

                              {/* Highlight important tags */}
                              {(resource.tags['kubernetes.io/cluster'] || resource.tags['sigs.k8s.io/cluster-api-provider-aws/cluster-name']) && (
                                <div className="mt-3 p-2 bg-blue-50 border border-blue-200 rounded">
                                  <p className="text-xs font-semibold text-blue-800">
                                    🔍 Created by: CAPA/Kubernetes automation
                                  </p>
                                  <p className="text-xs text-blue-600 mt-1">
                                    Cluster: {resource.tags['kubernetes.io/cluster'] || resource.tags['sigs.k8s.io/cluster-api-provider-aws/cluster-name']}
                                  </p>
                                </div>
                              )}

                              {(resource.tags['CreatedBy'] || resource.tags['ManagedBy']) && (
                                <div className="mt-3 p-2 bg-purple-50 border border-purple-200 rounded">
                                  <p className="text-xs font-semibold text-purple-800">
                                    👤 Creator: {resource.tags['CreatedBy'] || resource.tags['ManagedBy']}
                                  </p>
                                  {resource.tags['CreatedAt'] && (
                                    <p className="text-xs text-purple-600 mt-1">
                                      Created: {new Date(resource.tags['CreatedAt']).toLocaleString()}
                                    </p>
                                  )}
                                  {resource.tags['CreatedByArn'] && (
                                    <p className="text-xs text-purple-600 mt-1 font-mono break-all">
                                      ARN: {resource.tags['CreatedByArn']}
                                    </p>
                                  )}
                                </div>
                              )}
                            </div>
                          ) : (
                            <p className="text-sm text-gray-500 italic">No tags available</p>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-12">
                  <p className="text-gray-600">No details available</p>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="bg-gray-50 px-6 py-4 border-t border-gray-200">
              <button
                onClick={closeDetailsModal}
                className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AWSUsageDashboard;
