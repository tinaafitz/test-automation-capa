import React, { useState, useEffect } from 'react';
import { ArrowPathIcon } from '@heroicons/react/24/outline';

const RESOURCE_COLORS = {
  nat_gateways: '#f97316',
  route53_zones: '#06b6d4',
  vpcs: '#8b5cf6',
  iam_roles: '#ec4899',
  ec2_instances: '#3b82f6',
  ebs_volumes: '#10b981',
  load_balancers: '#f59e0b',
  security_groups: '#6366f1',
  s3_buckets: '#14b8a6',
  cloudformation_stacks: '#ef4444',
  instance_profiles: '#a855f7',
};

const RESOURCE_LABELS = {
  nat_gateways: 'NAT Gateways',
  route53_zones: 'Route53 Zones',
  vpcs: 'VPCs',
  iam_roles: 'IAM Roles',
  ec2_instances: 'EC2 Instances',
  ebs_volumes: 'EBS Volumes',
  load_balancers: 'Load Balancers',
  security_groups: 'Security Groups',
  s3_buckets: 'S3 Buckets',
  cloudformation_stacks: 'CF Stacks',
  instance_profiles: 'Instance Profiles',
};

const AWSUsageTrend = () => {
  const [trendData, setTrendData] = useState([]);
  const [resourceKeys, setResourceKeys] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [days, setDays] = useState(30);
  const [selectedResources, setSelectedResources] = useState(new Set());
  const [hoveredPoint, setHoveredPoint] = useState(null);

  const fetchTrend = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`http://localhost:8000/api/aws/usage-trend?days=${days}`);
      const data = await response.json();

      if (data.success) {
        setTrendData(data.trend || []);
        const keys = data.resource_keys || [];
        setResourceKeys(keys);
        // Default: show key infrastructure resources (similar scale, not IAM which dominates)
        if (selectedResources.size === 0 && data.trend?.length > 0) {
          const defaultKeys = ['nat_gateways', 'vpcs', 'route53_zones', 'ec2_instances', 'ebs_volumes']
            .filter(k => keys.includes(k));
          setSelectedResources(new Set(defaultKeys.length > 0 ? defaultKeys : keys.slice(0, 5)));
        }
      } else {
        setError(data.message || 'Failed to load trend data');
      }
    } catch (err) {
      setError('Failed to fetch trend data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTrend();
  }, [days]);

  const toggleResource = (key) => {
    setSelectedResources(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  // Chart rendering
  const chartHeight = 200;
  const chartPadding = { top: 15, right: 20, bottom: 30, left: 45 };
  const chartWidth = 900;
  const innerWidth = chartWidth - chartPadding.left - chartPadding.right;
  const innerHeight = chartHeight - chartPadding.top - chartPadding.bottom;

  // Calculate scales
  const activeKeys = [...selectedResources];
  const allValues = trendData.flatMap(d => activeKeys.map(k => d[k] || 0));
  const maxValue = Math.max(...allValues, 1);
  const yMax = Math.ceil(maxValue * 1.15 / 5) * 5;

  const formatDate = (isoStr) => {
    const d = new Date(isoStr);
    return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
  };

  const formatDateShort = (isoStr) => {
    const d = new Date(isoStr);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  };

  // Generate SVG paths for each resource
  const getPath = (key) => {
    if (trendData.length === 0) return '';
    const points = trendData.map((d, i) => {
      const x = chartPadding.left + (i / Math.max(trendData.length - 1, 1)) * innerWidth;
      const y = chartPadding.top + innerHeight - ((d[key] || 0) / yMax) * innerHeight;
      return `${x},${y}`;
    });
    return `M${points.join('L')}`;
  };

  // X-axis labels (show ~6 labels)
  const xLabels = [];
  if (trendData.length > 0) {
    const step = Math.max(1, Math.floor(trendData.length / 6));
    for (let i = 0; i < trendData.length; i += step) {
      xLabels.push({
        index: i,
        label: formatDateShort(trendData[i].timestamp),
        x: chartPadding.left + (i / Math.max(trendData.length - 1, 1)) * innerWidth,
      });
    }
  }

  // Y-axis labels
  const yLabels = [0, 0.25, 0.5, 0.75, 1].map(pct => ({
    value: Math.round(yMax * pct),
    y: chartPadding.top + innerHeight - pct * innerHeight,
  }));

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
      {/* Header */}
      <div className="bg-gray-50 border-b border-gray-200 px-4 py-3">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-gray-900">Resource Usage Trend</h3>
            <p className="text-xs text-gray-500 mt-0.5">Historical resource counts over time</p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="text-sm border border-gray-300 rounded-md px-2 py-1.5 bg-white"
            >
              <option value={7}>7 days</option>
              <option value={14}>14 days</option>
              <option value={30}>30 days</option>
              <option value={90}>90 days</option>
            </select>
            <button
              onClick={fetchTrend}
              disabled={loading}
              className="px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-700 rounded-md text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium flex items-center gap-2 border border-blue-200"
            >
              <ArrowPathIcon className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="p-4">
        {error && (
          <div className="text-center py-6 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-sm text-red-600">{error}</p>
          </div>
        )}

        {loading && trendData.length === 0 && (
          <div className="text-center py-8 text-gray-500">
            <ArrowPathIcon className="h-6 w-6 animate-spin mx-auto mb-2" />
            <p className="text-sm">Loading trend data...</p>
          </div>
        )}

        {!loading && trendData.length === 0 && !error && (
          <div className="text-center py-8">
            <p className="text-sm text-gray-500 mb-1">No historical data yet</p>
            <p className="text-xs text-gray-400">Refresh the AWS Usage page to start collecting snapshots</p>
          </div>
        )}

        {trendData.length === 1 && (
          <div className="text-center py-6 bg-blue-50 border border-blue-200 rounded-lg">
            <p className="text-sm font-medium text-blue-700">First snapshot collected!</p>
            <p className="text-xs text-blue-500 mt-1">Refresh the AWS Usage page again to add more data points and see the trend chart.</p>
            <div className="mt-3 grid grid-cols-3 gap-2 max-w-lg mx-auto">
              {resourceKeys.slice(0, 6).map(key => (
                <div key={key} className="bg-white rounded px-2 py-1.5 border border-blue-100">
                  <div className="text-xs text-gray-500">{RESOURCE_LABELS[key] || key}</div>
                  <div className="text-sm font-bold" style={{ color: RESOURCE_COLORS[key] || '#6b7280' }}>
                    {trendData[0][key] || 0}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {trendData.length > 1 && (
          <>
            {/* SVG Chart */}
            <div className="relative border border-gray-200 rounded-lg bg-white overflow-hidden">
              <svg
                viewBox={`0 0 ${chartWidth} ${chartHeight}`}
                className="w-full"
                style={{ height: '200px' }}
                onMouseLeave={() => setHoveredPoint(null)}
              >
                {/* Grid lines */}
                {yLabels.map(({ value, y }) => (
                  <g key={value}>
                    <line
                      x1={chartPadding.left} y1={y}
                      x2={chartWidth - chartPadding.right} y2={y}
                      stroke="#e5e7eb" strokeWidth="1" strokeDasharray={value === 0 ? "0" : "4,4"}
                    />
                    <text x={chartPadding.left - 8} y={y + 4} textAnchor="end" fontSize="11" fill="#6b7280">
                      {value}
                    </text>
                  </g>
                ))}

                {/* X-axis labels */}
                {xLabels.map(({ label, x }, i) => (
                  <text key={i} x={x} y={chartHeight - 8} textAnchor="middle" fontSize="11" fill="#6b7280">
                    {label}
                  </text>
                ))}

                {/* Lines */}
                {activeKeys.map(key => (
                  <path
                    key={key}
                    d={getPath(key)}
                    fill="none"
                    stroke={RESOURCE_COLORS[key] || '#6b7280'}
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                ))}

                {/* Data points */}
                {activeKeys.map(key =>
                  trendData.map((d, i) => {
                    const x = chartPadding.left + (i / Math.max(trendData.length - 1, 1)) * innerWidth;
                    const y = chartPadding.top + innerHeight - ((d[key] || 0) / yMax) * innerHeight;
                    return (
                      <circle
                        key={`${key}-${i}`}
                        cx={x} cy={y} r="3.5"
                        fill={RESOURCE_COLORS[key] || '#6b7280'}
                        stroke="white" strokeWidth="1.5"
                        className="cursor-pointer"
                        onMouseEnter={() => setHoveredPoint({ x, y, key, index: i, value: d[key] || 0, timestamp: d.timestamp })}
                      />
                    );
                  })
                )}

                {/* Tooltip */}
                {hoveredPoint && (
                  <g>
                    <rect
                      x={Math.min(hoveredPoint.x + 10, chartWidth - 160)}
                      y={Math.max(hoveredPoint.y - 45, 5)}
                      width="150" height="40" rx="6"
                      fill="#1f2937" fillOpacity="0.95"
                    />
                    <text
                      x={Math.min(hoveredPoint.x + 18, chartWidth - 152)}
                      y={Math.max(hoveredPoint.y - 28, 22)}
                      fontSize="11" fill="#9ca3af"
                    >
                      {formatDate(hoveredPoint.timestamp)}
                    </text>
                    <text
                      x={Math.min(hoveredPoint.x + 18, chartWidth - 152)}
                      y={Math.max(hoveredPoint.y - 12, 38)}
                      fontSize="12" fill="white" fontWeight="bold"
                    >
                      {RESOURCE_LABELS[hoveredPoint.key] || hoveredPoint.key}: {hoveredPoint.value}
                    </text>
                  </g>
                )}
              </svg>
            </div>

            {/* Resource toggles */}
            <div className="mt-3 flex flex-wrap gap-2">
              {resourceKeys.map(key => (
                <button
                  key={key}
                  onClick={() => toggleResource(key)}
                  className={`px-2.5 py-1 rounded-md text-xs font-medium border transition-all ${
                    selectedResources.has(key)
                      ? 'border-transparent text-white shadow-sm'
                      : 'border-gray-300 text-gray-500 bg-white hover:bg-gray-50'
                  }`}
                  style={selectedResources.has(key) ? { backgroundColor: RESOURCE_COLORS[key] || '#6b7280' } : {}}
                >
                  {RESOURCE_LABELS[key] || key}
                </button>
              ))}
            </div>

            <p className="text-xs text-gray-400 mt-2 text-center">
              {trendData.length} snapshot{trendData.length !== 1 ? 's' : ''} collected
            </p>
          </>
        )}
      </div>
    </div>
  );
};

export default AWSUsageTrend;
