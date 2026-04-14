import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowPathIcon } from '@heroicons/react/24/outline';
import CapaSidebar from '../components/sidebar/CapaSidebar';
import AWSUsageTrend from '../components/charts/AWSUsageTrend';

const AWSUsageDashboard = ({ inline = false }) => {
  const navigate = useNavigate();
  const [usage, setUsage] = useState(null);
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [error, setError] = useState(null);
  const [billedResources, setBilledResources] = useState([]);
  const [freeResources, setFreeResources] = useState([]);
  const [configLoading, setConfigLoading] = useState(true);
  const [expandedResource, setExpandedResource] = useState(null);
  const [detailsCache, setDetailsCache] = useState({});
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [creatorFilter, setCreatorFilter] = useState('all');
  const [availableCreators, setAvailableCreators] = useState([]);
  const [refreshingKey, setRefreshingKey] = useState(null);

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

  // Auto-fetch usage data when rendered inline
  useEffect(() => {
    if (inline && !usage && !loading) {
      fetchUsage();
    }
  }, [inline, configLoading]);

  const fetchUsage = async () => {
    setLoading(true);
    setError(null);
    setDetailsCache({});
    setExpandedResource(null);
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

  const toggleResourceDetails = async (resourceKey) => {
    // If already expanded, collapse it
    if (expandedResource === resourceKey) {
      setExpandedResource(null);
      return;
    }

    setExpandedResource(resourceKey);

    // Use cached data if available
    if (detailsCache[resourceKey]) {
      const cached = detailsCache[resourceKey];
      setAvailableCreators(cached.creators);
      setCreatorFilter('all');
      return;
    }

    setDetailsLoading(true);
    try {
      const response = await fetch(`http://localhost:8000/api/aws/resource-details/${resourceKey}`);
      const data = await response.json();

      if (data.success) {
        const details = data.details;
        const creators = new Set();
        details.forEach(resource => {
          const createdBy = resource.tags?.CreatedBy || resource.tags?.ManagedBy || 'unknown';
          creators.add(createdBy);
        });
        const creatorList = ['all', ...Array.from(creators).sort()];
        setDetailsCache(prev => ({ ...prev, [resourceKey]: { details, creators: creatorList } }));
        setAvailableCreators(creatorList);
        setCreatorFilter('all');
      } else {
        setError(data.message || 'Failed to fetch resource details');
      }
    } catch (err) {
      setError(`Error fetching details: ${err.message}`);
    } finally {
      setDetailsLoading(false);
    }
  };

  const refreshResourceDetails = async (resourceKey) => {
    setDetailsLoading(true);
    setDetailsCache(prev => { const next = { ...prev }; delete next[resourceKey]; return next; });
    try {
      const response = await fetch(`http://localhost:8000/api/aws/resource-details/${resourceKey}`);
      const data = await response.json();

      if (data.success) {
        const details = data.details;
        const creators = new Set();
        details.forEach(resource => {
          const createdBy = resource.tags?.CreatedBy || resource.tags?.ManagedBy || 'unknown';
          creators.add(createdBy);
        });
        const creatorList = ['all', ...Array.from(creators).sort()];
        setDetailsCache(prev => ({ ...prev, [resourceKey]: { details, creators: creatorList } }));
        setAvailableCreators(creatorList);
        setCreatorFilter('all');
      } else {
        setError(data.message || 'Failed to fetch resource details');
      }
    } catch (err) {
      setError(`Error fetching details: ${err.message}`);
    } finally {
      setDetailsLoading(false);
    }
  };

  const refreshSingleResource = async (e, resourceKey) => {
    e.stopPropagation();
    setRefreshingKey(resourceKey);
    try {
      const response = await fetch(`http://localhost:8000/api/aws/usage/${resourceKey}`);
      const data = await response.json();
      if (data.success) {
        setUsage(prev => ({ ...prev, [resourceKey]: data.count }));
        // Clear cached details for this resource so next expand fetches fresh data
        setDetailsCache(prev => { const next = { ...prev }; delete next[resourceKey]; return next; });
      }
    } catch (err) {
      // silently fail
    } finally {
      setRefreshingKey(null);
    }
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

  // Inline details table component
  const InlineDetailsTable = () => {
    if (detailsLoading) {
      return (
        <div className="py-3 px-4 bg-gray-50 border-t border-gray-200">
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <ArrowPathIcon className="h-4 w-4 animate-spin" />
            Loading details...
          </div>
        </div>
      );
    }

    const cached = detailsCache[expandedResource];
    if (!cached || cached.details.length === 0) {
      return (
        <div className="py-3 px-4 bg-gray-50 border-t border-gray-200">
          <p className="text-sm text-gray-500">No details available</p>
        </div>
      );
    }

    const resourceDetails = cached.details;
    const filtered = resourceDetails.filter(r =>
      creatorFilter === 'all' || r.tags?.CreatedBy === creatorFilter || r.tags?.ManagedBy === creatorFilter
    );
    const hasState = resourceDetails.some(r => r.state);
    const hasCreated = resourceDetails.some(r => r.created_at || r.launch_time);
    const hasVpc = resourceDetails.some(r => r.vpc_id);

    return (
      <div className="bg-gray-50 border-t border-gray-200 px-3 py-2">
        {/* Filter row */}
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs text-gray-500">
            <strong>{filtered.length}</strong> resources
            {creatorFilter !== 'all' && ` by ${creatorFilter}`}
          </p>
          <div className="flex items-center gap-2">
            {availableCreators.length > 2 && (
              <select
                value={creatorFilter}
                onChange={(e) => setCreatorFilter(e.target.value)}
                className="text-xs border border-gray-300 rounded px-1.5 py-0.5 bg-white"
              >
                {availableCreators.map(creator => (
                  <option key={creator} value={creator}>
                    {creator === 'all' ? 'All Creators' : creator}
                  </option>
                ))}
              </select>
            )}
            <button
              onClick={(e) => { e.stopPropagation(); refreshResourceDetails(expandedResource); }}
              disabled={detailsLoading}
              className="text-xs text-blue-500 hover:text-blue-700 flex items-center gap-1 disabled:opacity-50"
            >
              <ArrowPathIcon className={`h-3 w-3 ${detailsLoading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
            <button
              onClick={() => setExpandedResource(null)}
              className="text-xs text-gray-400 hover:text-gray-600"
            >
              Close
            </button>
          </div>
        </div>

        {/* Table */}
        <div className="border border-gray-200 rounded overflow-hidden bg-white">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-100 border-b border-gray-200">
                <th className="text-left px-2 py-1.5 font-semibold text-gray-600">Name</th>
                <th className="text-left px-2 py-1.5 font-semibold text-gray-600">ID</th>
                {hasState && <th className="text-left px-2 py-1.5 font-semibold text-gray-600">State</th>}
                {hasCreated && <th className="text-left px-2 py-1.5 font-semibold text-gray-600">Created</th>}
                {hasVpc && <th className="text-left px-2 py-1.5 font-semibold text-gray-600">VPC</th>}
                <th className="text-left px-2 py-1.5 font-semibold text-gray-600">Tags</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((resource, index) => {
                const created = resource.created_at || resource.launch_time;
                const age = created ? (() => {
                  const d = Math.floor((new Date() - new Date(created)) / (1000 * 60 * 60 * 24));
                  return d === 0 ? 'today' : d === 1 ? '1d ago' : `${d}d ago`;
                })() : null;
                const clusterTag = resource.tags?.['api.openshift.com/name'] || resource.tags?.['kubernetes.io/cluster'] || resource.tags?.['sigs.k8s.io/cluster-api-provider-aws/cluster-name'];
                const creator = resource.tags?.CreatedBy || resource.tags?.ManagedBy;
                const tagCount = resource.tags ? Object.keys(resource.tags).length : 0;

                return (
                  <tr key={index} className="border-b border-gray-100 last:border-0 hover:bg-gray-50">
                    <td className="px-2 py-1.5">
                      <span className="font-medium text-gray-900">{resource.name || 'Unnamed'}</span>
                    </td>
                    <td className="px-2 py-1.5">
                      <span className="text-gray-500 font-mono">{resource.id ? resource.id.slice(-20) : '-'}</span>
                    </td>
                    {hasState && (
                      <td className="px-2 py-1.5">
                        {resource.state && (
                          <span className={`inline-block px-1.5 py-0.5 font-medium rounded ${resource.state === 'available' || resource.state === 'running' || resource.state === 'in-use' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-700'}`}>
                            {resource.state}
                          </span>
                        )}
                      </td>
                    )}
                    {hasCreated && (
                      <td className="px-2 py-1.5">
                        {age && <span className="text-gray-600">{age}</span>}
                      </td>
                    )}
                    {hasVpc && (
                      <td className="px-2 py-1.5">
                        <span className="text-gray-600">{resource.vpc_name || (resource.vpc_id ? resource.vpc_id.slice(-8) : '-')}</span>
                      </td>
                    )}
                    <td className="px-2 py-1.5">
                      <div className="flex items-center gap-1 flex-wrap">
                        {clusterTag && (
                          <span className="inline-block px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded font-medium">{clusterTag}</span>
                        )}
                        {creator && (
                          <span className="inline-block px-1.5 py-0.5 bg-purple-100 text-purple-700 rounded font-medium">{creator}</span>
                        )}
                        {tagCount > 0 && !clusterTag && !creator && (
                          <span className="text-gray-400">{tagCount} tags</span>
                        )}
                        {tagCount === 0 && (
                          <span className="text-gray-300">&mdash;</span>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  // Render a resource bar row with optional inline expansion
  const ResourceBarRow = ({ resource, showCost }) => {
    const count = usage[resource.key];
    const cost = showCost ? calculateCost(resource) : null;
    const isError = count === 'error';
    const usagePct = !isError && count !== undefined ? Math.round((count / resource.threshold) * 100) : 0;
    const barColor = usagePct >= 90 ? 'bg-red-500' : usagePct >= 70 ? 'bg-yellow-400' : 'bg-blue-500';
    const barBg = usagePct >= 90 ? 'bg-red-100' : usagePct >= 70 ? 'bg-yellow-100' : 'bg-blue-100';
    const isExpanded = expandedResource === resource.key;

    return (
      <div className={`${isExpanded ? 'bg-gray-50 rounded-lg border border-gray-200 -mx-1 px-1' : ''}`}>
        <div
          onClick={() => count > 0 && !isError && toggleResourceDetails(resource.key)}
          className={`group ${count > 0 && !isError ? 'cursor-pointer' : 'cursor-default'}`}
        >
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-2">
              <span className="text-sm">{resource.icon}</span>
              <span className="text-sm font-medium text-gray-900">{resource.label}</span>
              <button
                onClick={(e) => refreshSingleResource(e, resource.key)}
                disabled={refreshingKey === resource.key}
                className="opacity-0 group-hover:opacity-100 transition-opacity text-gray-400 hover:text-blue-600 disabled:opacity-100"
                title="Refresh this resource"
              >
                <ArrowPathIcon className={`h-3.5 w-3.5 ${refreshingKey === resource.key ? 'animate-spin text-blue-500' : ''}`} />
              </button>
              {count > 0 && !isError && !isExpanded && (
                <span className="text-xs text-blue-600 font-semibold opacity-0 group-hover:opacity-100 transition-opacity">Details &rarr;</span>
              )}
              {isExpanded && (
                <span className="text-xs text-blue-600 font-semibold">&#x25BC;</span>
              )}
            </div>
            <div className="flex items-center gap-3">
              {isError ? (
                <span className="text-xs text-red-600 font-medium">Error</span>
              ) : (
                <>
                  <span className="text-sm font-bold text-gray-900">{count?.toLocaleString() || '0'}</span>
                  <span className="text-xs text-gray-400">/ {resource.threshold.toLocaleString()}</span>
                  <span className={`text-xs font-semibold min-w-[32px] text-right ${usagePct >= 90 ? 'text-red-600' : usagePct >= 70 ? 'text-yellow-600' : 'text-gray-500'}`}>{usagePct}%</span>
                  {showCost && resource.costType === 'fixed' && cost ? (
                    <span className="text-xs font-bold text-orange-600 min-w-[70px] text-right">${cost}/mo</span>
                  ) : showCost && resource.costType === 'variable' ? (
                    <span className="text-xs font-semibold text-orange-600 min-w-[70px] text-right">Variable</span>
                  ) : showCost ? (
                    <span className="min-w-[70px]"></span>
                  ) : null}
                </>
              )}
            </div>
          </div>
          {!isError && (
            <div className={`w-full ${barBg} rounded-full h-2 group-hover:h-2.5 transition-all`}>
              <div className={`h-full rounded-full ${barColor} transition-all duration-500`} style={{ width: `${Math.max(Math.min(usagePct, 100), 1)}%` }}></div>
            </div>
          )}
        </div>
        {isExpanded && <InlineDetailsTable />}
      </div>
    );
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
    onAIAssistantClick: () => navigate('/mce'),
    onTerminalClick: () => navigate('/mce'),
    onNotificationsClick: () => navigate('/mce'),
    onRecentTasksClick: () => navigate('/mce'),
    onAWSUsageClick: () => navigate('/aws-usage'),
  };

  const contentBody = (
        <div className={inline ? "" : "p-6"}>
          {/* Description + Refresh */}
          <div className="mb-4 flex items-start justify-between">
            <div>
              <p className="text-gray-600 text-sm">
                Monitor your AWS resource counts across all services
              </p>
              <p className="text-gray-500 text-xs mt-1 flex items-center gap-1">
                <span className="inline-block w-1 h-1 rounded-full bg-gray-400"></span>
                {lastUpdated
                  ? `Last updated: ${lastUpdated.toLocaleString()}`
                  : 'Data may take a few minutes to load as it queries all AWS resources'}
              </p>
            </div>
            {inline && (
              <button
                onClick={fetchUsage}
                disabled={loading}
                className={`
                  flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm
                  transition-all duration-200 shadow-sm whitespace-nowrap
                  ${loading
                    ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                    : 'bg-orange-500 text-white hover:bg-orange-600 hover:shadow-md'
                  }
                `}
              >
                <ArrowPathIcon className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                {loading ? 'Loading...' : 'Refresh Data'}
              </button>
            )}
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
              {/* Top Row: Cost Summary (left) + Usage Trend (right) */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
                {/* Cost Summary */}
                {(() => {
                  const natCost = usage.nat_gateways > 0 ? calculateCost(resourceConfig.find(r => r.key === 'nat_gateways')) : null;
                  const route53Cost = usage.route53_zones > 0 ? calculateCost(resourceConfig.find(r => r.key === 'route53_zones')) : null;
                  const totalCost = (parseFloat(natCost || 0) + parseFloat(route53Cost || 0)).toFixed(2);

                  return (
                    <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
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
                                <p className="text-xs text-gray-500">{usage.nat_gateways} × $32.40/mo</p>
                              </div>
                            </div>
                            <p className="text-base font-bold text-blue-600">${natCost}</p>
                          </div>
                        )}
                        {route53Cost && (
                          <div className="flex items-center justify-between py-2 px-3 bg-gray-50 rounded">
                            <div className="flex items-center gap-2">
                              <span className="text-sm">🌐</span>
                              <div>
                                <p className="text-sm font-medium text-gray-900">Route53 Zones</p>
                                <p className="text-xs text-gray-500">{usage.route53_zones} × $0.50/mo</p>
                              </div>
                            </div>
                            <p className="text-base font-bold text-cyan-600">${route53Cost}</p>
                          </div>
                        )}
                        {!natCost && !route53Cost && (
                          <p className="text-sm text-gray-500 text-center py-4">No billable resources</p>
                        )}
                        <div className="flex items-center justify-between py-2 px-3 bg-green-50 rounded border border-green-200">
                          <div className="flex items-center gap-2">
                            <span className="text-sm">💵</span>
                            <p className="text-sm font-bold text-gray-900">Total</p>
                          </div>
                          <p className="text-lg font-bold text-green-700">${totalCost}/mo</p>
                        </div>
                      </div>
                      {/* Status Guide */}
                      <div className="mt-3 pt-3 border-t border-gray-200">
                        <div className="flex items-center gap-3 flex-wrap">
                          <span className="text-xs font-semibold text-gray-700">Status:</span>
                          <div className="flex items-center gap-1">
                            <div className="w-2.5 h-2.5 bg-green-100 border border-green-300 rounded"></div>
                            <span className="text-xs text-gray-600">Safe</span>
                          </div>
                          <div className="flex items-center gap-1">
                            <div className="w-2.5 h-2.5 bg-yellow-100 border border-yellow-300 rounded"></div>
                            <span className="text-xs text-gray-600">Warning</span>
                          </div>
                          <div className="flex items-center gap-1">
                            <div className="w-2.5 h-2.5 bg-red-100 border border-red-300 rounded"></div>
                            <span className="text-xs text-gray-600">Critical</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })()}

                {/* Usage Trend Chart */}
                <div className="lg:col-span-2">
                  <AWSUsageTrend />
                </div>
              </div>

              {/* Resources — side by side */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Billed Resources — horizontal bar chart */}
              <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4">
                <div className="flex items-center gap-2 mb-4">
                  <span className="text-lg">💰</span>
                  <h3 className="text-base font-bold text-gray-900">Resources with Costs</h3>
                  <span className="text-xs text-gray-500 italic">These resources incur monthly charges</span>
                </div>
                <div className="space-y-3">
                  {billedResources.map((resource) => (
                    <ResourceBarRow key={resource.key} resource={resource} showCost={true} />
                  ))}
                </div>
              </div>

              {/* Quota Management Resources — horizontal bar chart */}
              <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4">
                <div className="flex items-center gap-2 mb-4">
                  <span className="text-lg">📊</span>
                  <h3 className="text-base font-bold text-gray-900">Quota Usage</h3>
                  <span className="text-xs text-gray-500 italic">No direct costs — monitor for quota limits</span>
                </div>
                <div className="space-y-3">
                  {freeResources.map((resource) => (
                    <ResourceBarRow key={resource.key} resource={resource} showCost={false} />
                  ))}
                </div>
              </div>
              </div>
            </>
          )}
        </div>
  );

  if (inline) {
    return contentBody;
  }

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
          {contentBody}
        </div>
      </div>
    </div>
  );
};

export default AWSUsageDashboard;
