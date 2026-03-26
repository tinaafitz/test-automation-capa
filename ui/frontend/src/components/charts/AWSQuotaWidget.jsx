import React, { useState, useEffect } from 'react';
import { ArrowPathIcon } from '@heroicons/react/24/outline';
import { buildApiUrl } from '../../config/api';

const AWSQuotaWidget = () => {
  const [usage, setUsage] = useState(null);
  const [config, setConfig] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [usageRes, configRes] = await Promise.all([
        fetch(buildApiUrl('/api/aws/usage')),
        fetch(buildApiUrl('/api/aws/usage-config')),
      ]);
      const usageData = await usageRes.json();
      const configData = await configRes.json();

      if (usageData.success) {
        setUsage(usageData.usage);
        setLastUpdated(new Date(usageData.timestamp));
      }
      if (configData.success) {
        setConfig([...(configData.billedResources || []), ...(configData.freeResources || [])]);
      }
    } catch (err) {
      setError('Failed to load AWS data');
    } finally {
      setLoading(false);
    }
  };

  const getBarColor = (count, threshold) => {
    if (count === 'error') return 'bg-red-400';
    const pct = count / threshold;
    if (pct >= 0.9) return 'bg-red-500';
    if (pct >= 0.7) return 'bg-yellow-500';
    return 'bg-green-500';
  };

  const getTextColor = (count, threshold) => {
    if (count === 'error') return 'text-red-600';
    const pct = count / threshold;
    if (pct >= 0.9) return 'text-red-600';
    if (pct >= 0.7) return 'text-yellow-600';
    return 'text-green-600';
  };

  // Calculate total estimated monthly cost
  const getTotalCost = () => {
    if (!usage || config.length === 0) return null;
    let total = 0;
    config.forEach(r => {
      if (r.costPerMonth && usage[r.key] && usage[r.key] !== 'error') {
        total += usage[r.key] * r.costPerMonth;
      }
    });
    return total > 0 ? total.toFixed(2) : null;
  };

  // Key resources to show in the compact widget
  const getDisplayResources = () => {
    if (!usage || config.length === 0) return [];
    // Show top 5 resources sorted by usage percentage (highest first)
    return config
      .filter(r => usage[r.key] !== undefined && usage[r.key] !== 'error')
      .map(r => ({
        ...r,
        count: usage[r.key],
        pct: Math.round((usage[r.key] / r.threshold) * 100),
      }))
      .sort((a, b) => b.pct - a.pct)
      .slice(0, 5);
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
      {/* Header */}
      <div className="bg-gray-50 border-b border-gray-200 px-4 py-3">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold text-gray-900">AWS Resource Quota</h3>
          <button
            onClick={fetchData}
            disabled={loading}
            className="px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-700 rounded-md text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium flex items-center gap-2 border border-blue-200"
          >
            <ArrowPathIcon className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
        {lastUpdated && (
          <p className="text-xs text-gray-500 mt-1">
            Updated: {lastUpdated.toLocaleTimeString()}
          </p>
        )}
      </div>

      {/* Content */}
      <div className="p-4">
        {error && (
          <div className="text-center py-6 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-sm text-red-600">{error}</p>
          </div>
        )}

        {loading && !usage && (
          <div className="text-center py-8 text-gray-500">
            <ArrowPathIcon className="h-6 w-6 animate-spin mx-auto mb-2" />
            <p className="text-sm">Loading AWS usage...</p>
          </div>
        )}

        {!usage && !loading && !error && (
          <div className="text-center py-8">
            <p className="text-sm text-gray-500">Click Refresh to load data</p>
          </div>
        )}

        {usage && (
          <>
            {/* Total Cost Badge */}
            {getTotalCost() && (
              <div className="mb-3 bg-gradient-to-r from-green-50 to-emerald-50 border border-green-200 rounded-lg px-3 py-2 flex items-center justify-between">
                <span className="text-sm font-medium text-gray-700">Est. Monthly Cost</span>
                <span className="text-lg font-bold text-green-700">${getTotalCost()}</span>
              </div>
            )}

            {/* Resource bars - top 5 by usage */}
            <div className="space-y-2.5">
              {getDisplayResources().map(r => (
                <div key={r.key}>
                  <div className="flex items-center justify-between mb-0.5">
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm">{r.icon}</span>
                      <span className="text-sm font-medium text-gray-700 truncate max-w-[140px]">
                        {r.label}
                      </span>
                    </div>
                    <span className={`text-sm font-bold ${getTextColor(r.count, r.threshold)}`}>
                      {r.count}/{r.threshold.toLocaleString()} ({r.pct}%)
                    </span>
                  </div>
                  <div className="w-full bg-gray-100 rounded-full h-2">
                    <div
                      className={`h-2 rounded-full transition-all duration-500 ${getBarColor(r.count, r.threshold)}`}
                      style={{ width: `${Math.min(r.pct, 100)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>

            {/* Status legend */}
            <div className="mt-3 pt-3 border-t border-gray-100 flex items-center justify-center gap-3">
              <div className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full bg-green-500" />
                <span className="text-[10px] text-gray-500">&lt;70%</span>
              </div>
              <div className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full bg-yellow-500" />
                <span className="text-[10px] text-gray-500">70-89%</span>
              </div>
              <div className="flex items-center gap-1">
                <div className="w-2 h-2 rounded-full bg-red-500" />
                <span className="text-[10px] text-gray-500">&ge;90%</span>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default AWSQuotaWidget;
