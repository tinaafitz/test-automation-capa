import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowPathIcon } from '@heroicons/react/24/outline';
import CapaSidebar from '../components/sidebar/CapaSidebar';

const AWSUsageDashboard = () => {
  const navigate = useNavigate();
  const [usage, setUsage] = useState(null);
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [error, setError] = useState(null);
  const [billedResources, setBilledResources] = useState([]);
  const [freeResources, setFreeResources] = useState([]);
  const [configLoading, setConfigLoading] = useState(true);

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
    if (!usage || !resource.costPerMonth) return null;
    const count = usage[resource.key];
    if (count === 'error' || count === undefined) return null;
    return (count * resource.costPerMonth).toFixed(2);
  };

  return (
    <div className="flex h-screen bg-gray-50">
      <CapaSidebar
        activeSection="aws-usage"
        environment="mce"
        onEnvironmentsClick={() => navigate('/mce')}
        onAWSUsageClick={() => navigate('/aws-usage')}
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
                        className={`
                          border-2 rounded-lg p-3 transition-all duration-300
                          hover:shadow-xl hover:scale-102
                          ${statusColor}
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

                            <div className={`text-2xl font-bold ${textColor} mb-0.5`}>
                              {isError ? '⚠️' : count?.toLocaleString() || '0'}
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
                        className={`
                          border-2 rounded-lg p-3 transition-all duration-300
                          hover:shadow-xl hover:scale-102
                          ${statusColor}
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

                            <div className={`text-2xl font-bold ${textColor} mb-0.5`}>
                              {isError ? '⚠️' : count?.toLocaleString() || '0'}
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
    </div>
  );
};

export default AWSUsageDashboard;
