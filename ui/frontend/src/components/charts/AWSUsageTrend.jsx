import React, { useState, useEffect } from 'react';
import { ArrowPathIcon } from '@heroicons/react/24/outline';

export const RESOURCE_COLORS = {
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

export const RESOURCE_LABELS = {
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

export const Sparkline = ({ data, dataKey, width = 80, height = 24, color }) => {
  if (!data || data.length < 2) return null;
  const values = data.map(d => d[dataKey] || 0);
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = max - min || 1;
  const points = values.map((v, i) => {
    const x = (i / (values.length - 1)) * width;
    const y = height - ((v - min) / range) * (height - 4) - 2;
    return `${x},${y}`;
  });
  return (
    <svg width={width} height={height} className="inline-block">
      <polyline
        points={points.join(' ')}
        fill="none"
        stroke={color || RESOURCE_COLORS[dataKey] || '#0073BB'}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
};

const AWSUsageTrend = ({ selectedResources: externalSelected, onToggleResource, height: propHeight }) => {
  const [trendData, setTrendData] = useState([]);
  const [resourceKeys, setResourceKeys] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [timeRange, setTimeRange] = useState('30d');
  const [internalSelected, setInternalSelected] = useState(new Set());
  const [hoveredPoint, setHoveredPoint] = useState(null);

  const selected = externalSelected || internalSelected;
  const isControlled = !!externalSelected;

  const TIME_RANGES = [
    { key: '1h', label: '1h', hours: 1 },
    { key: '24h', label: '24h', hours: 24 },
    { key: '7d', label: '7d', days: 7 },
    { key: '30d', label: '30d', days: 30 },
  ];

  const fetchTrend = async () => {
    setLoading(true);
    setError(null);
    try {
      const range = TIME_RANGES.find(r => r.key === timeRange) || TIME_RANGES[3];
      const param = range.hours ? `hours=${range.hours}` : `days=${range.days}`;
      const response = await fetch(`http://localhost:8000/api/aws/usage-trend?${param}`);
      const data = await response.json();

      if (data.success) {
        setTrendData(data.trend || []);
        const keys = data.resource_keys || [];
        setResourceKeys(keys);
        if (!isControlled && internalSelected.size === 0 && data.trend?.length > 0) {
          const defaultKeys = ['nat_gateways', 'vpcs', 'route53_zones']
            .filter(k => keys.includes(k));
          setInternalSelected(new Set(defaultKeys.length > 0 ? defaultKeys : keys.slice(0, 3)));
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
  }, [timeRange]);

  const toggleResource = (key) => {
    if (onToggleResource) {
      onToggleResource(key);
    } else {
      setInternalSelected(prev => {
        const next = new Set(prev);
        if (next.has(key)) {
          next.delete(key);
        } else {
          next.add(key);
        }
        return next;
      });
    }
  };

  const chartHeight = propHeight || 300;
  const chartPadding = { top: 15, right: 20, bottom: 30, left: 45 };
  const chartWidth = 1400;
  const innerWidth = chartWidth - chartPadding.left - chartPadding.right;
  const innerHeight = chartHeight - chartPadding.top - chartPadding.bottom;

  const activeKeys = [...selected];
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

  const getPath = (key) => {
    if (trendData.length === 0) return '';
    const points = trendData.map((d, i) => {
      const x = chartPadding.left + (i / Math.max(trendData.length - 1, 1)) * innerWidth;
      const y = chartPadding.top + innerHeight - ((d[key] || 0) / yMax) * innerHeight;
      return `${x},${y}`;
    });
    return `M${points.join('L')}`;
  };

  const xLabels = [];
  if (trendData.length > 0) {
    const step = Math.max(1, Math.floor(trendData.length / 8));
    for (let i = 0; i < trendData.length; i += step) {
      xLabels.push({
        index: i,
        label: formatDateShort(trendData[i].timestamp),
        x: chartPadding.left + (i / Math.max(trendData.length - 1, 1)) * innerWidth,
      });
    }
  }

  const yLabels = [0, 0.25, 0.5, 0.75, 1].map(pct => ({
    value: Math.round(yMax * pct),
    y: chartPadding.top + innerHeight - pct * innerHeight,
  }));

  if (activeKeys.length === 0) {
    return null;
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          {activeKeys.map(key => (
            <span key={key} className="flex items-center gap-1.5 text-xs font-medium text-[#545B64]">
              <span className="w-3 h-0.5 rounded" style={{ backgroundColor: RESOURCE_COLORS[key] || '#6b7280' }} />
              {RESOURCE_LABELS[key] || key}
            </span>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <div className="flex bg-gray-100 rounded-lg p-0.5 border border-gray-200">
            {TIME_RANGES.map(r => (
              <button
                key={r.key}
                onClick={() => setTimeRange(r.key)}
                className={`px-2.5 py-1 rounded-md text-xs font-semibold transition-colors ${
                  timeRange === r.key
                    ? 'bg-white text-[#232F3E] shadow-sm border border-gray-200'
                    : 'text-[#545B64] hover:text-[#232F3E]'
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
          <button
            onClick={fetchTrend}
            disabled={loading}
            className="px-3 py-1.5 text-[#0073BB] hover:text-[#005C99] rounded-md text-xs transition-colors disabled:opacity-50 font-medium flex items-center gap-1"
          >
            <ArrowPathIcon className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="text-center py-4 text-sm text-red-600">{error}</div>
      )}

      {loading && trendData.length === 0 && (
        <div className="text-center py-8 text-[#545B64]">
          <ArrowPathIcon className="h-5 w-5 animate-spin mx-auto mb-2" />
          <p className="text-sm">Loading trend data...</p>
        </div>
      )}

      {trendData.length > 1 && activeKeys.length > 0 && (
        <>
          <div className="relative rounded-lg bg-white overflow-hidden border border-gray-100">
            <svg
              viewBox={`0 0 ${chartWidth} ${chartHeight}`}
              className="w-full"
              preserveAspectRatio="xMidYMid meet"
              onMouseLeave={() => setHoveredPoint(null)}
            >
              {yLabels.map(({ value, y }) => (
                <g key={value}>
                  <line
                    x1={chartPadding.left} y1={y}
                    x2={chartWidth - chartPadding.right} y2={y}
                    stroke="#e5e7eb" strokeWidth="1" strokeDasharray={value === 0 ? "0" : "4,4"}
                  />
                  <text x={chartPadding.left - 8} y={y + 4} textAnchor="end" fontSize="11" fill="#879596">
                    {value}
                  </text>
                </g>
              ))}

              {xLabels.map(({ label, x }, i) => (
                <text key={i} x={x} y={chartHeight - 8} textAnchor="middle" fontSize="11" fill="#879596">
                  {label}
                </text>
              ))}

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

              {activeKeys.map(key =>
                trendData.map((d, i) => {
                  const x = chartPadding.left + (i / Math.max(trendData.length - 1, 1)) * innerWidth;
                  const y = chartPadding.top + innerHeight - ((d[key] || 0) / yMax) * innerHeight;
                  return (
                    <circle
                      key={`${key}-${i}`}
                      cx={x} cy={y} r="3"
                      fill={RESOURCE_COLORS[key] || '#6b7280'}
                      stroke="white" strokeWidth="1.5"
                      className="cursor-pointer"
                      onMouseEnter={() => setHoveredPoint({ x, y, key, index: i, value: d[key] || 0, timestamp: d.timestamp })}
                    />
                  );
                })
              )}

              {hoveredPoint && (
                <g>
                  <rect
                    x={Math.min(hoveredPoint.x + 10, chartWidth - 160)}
                    y={Math.max(hoveredPoint.y - 45, 5)}
                    width="150" height="40" rx="6"
                    fill="#232F3E" fillOpacity="0.95"
                  />
                  <text
                    x={Math.min(hoveredPoint.x + 18, chartWidth - 152)}
                    y={Math.max(hoveredPoint.y - 28, 22)}
                    fontSize="11" fill="#879596"
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
          <p className="text-[11px] text-[#879596] mt-2 text-center">
            {trendData.length} snapshots collected
          </p>
        </>
      )}
    </div>
  );
};

export default AWSUsageTrend;
