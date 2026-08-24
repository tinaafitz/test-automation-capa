import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowPathIcon, ChevronDownIcon, ChevronUpIcon } from '@heroicons/react/24/outline';
import CapaSidebar from '../components/sidebar/CapaSidebar';
import AWSUsageTrend, { Sparkline, RESOURCE_COLORS } from '../components/charts/AWSUsageTrend';

const AWS_CACHE_KEY = 'aws-usage-cache';
const _loadCache = () => {
  try {
    const c = JSON.parse(sessionStorage.getItem(AWS_CACHE_KEY));
    if (!c) return { usage: null, lastUpdated: null, billedResources: [], freeResources: [], region: null };
    return { usage: c.usage || null, lastUpdated: c.lastUpdated || null, billedResources: c.billedResources || [], freeResources: c.freeResources || [], region: c.region || null };
  } catch { return { usage: null, lastUpdated: null, billedResources: [], freeResources: [], region: null }; }
};
const _saveCache = (cache) => {
  try { sessionStorage.setItem(AWS_CACHE_KEY, JSON.stringify(cache)); } catch {}
};

const AWS_ICONS = {
  nat_gateways: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z',
  route53_zones: 'M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z',
  ec2_instances: 'M20 18c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2H4c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2H0v2h24v-2h-4zM4 6h16v10H4V6z',
  ebs_volumes: 'M2 20h20v-4H2v4zm2-3h2v2H4v-2zM2 4v4h20V4H2zm4 3H4V5h2v2zm-4 7h20v-4H2v4zm2-3h2v2H4v-2z',
  load_balancers: 'M4 15h16v-2H4v2zm0 4h16v-2H4v2zm0-8h16V9H4v2zm0-6v2h16V5H4z',
  s3_buckets: 'M18 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 4h5v8l-2.5-1.5L6 12V4z',
  instance_profiles: 'M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z',
  cloudformation_stacks: 'M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-5 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z',
  iam_roles: 'M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z',
  vpcs: 'M21 3H3c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h18c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H3V5h18v14zM5 15h14v2H5zm0-4h14v2H5zm0-4h14v2H5z',
  security_groups: 'M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z',
};

const ServiceIcon = ({ resourceKey, size = 16, className = '' }) => {
  const path = AWS_ICONS[resourceKey];
  if (!path) return null;
  const color = RESOURCE_COLORS[resourceKey] || '#545B64';
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill={color} className={className}>
      <path d={path} />
    </svg>
  );
};

const AWS_CONSOLE_URLS = {
  nat_gateways: 'vpc/home#NatGateways:',
  route53_zones: 'route53/v2/hostedzones#',
  ec2_instances: 'ec2/home#Instances:',
  ebs_volumes: 'ec2/home#Volumes:',
  load_balancers: 'ec2/home#LoadBalancers:',
  s3_buckets: 's3/buckets',
  instance_profiles: 'iam/home#/roles',
  cloudformation_stacks: 'cloudformation/home#/stacks',
  iam_roles: 'iam/home#/roles',
  vpcs: 'vpc/home#vpcs:',
  security_groups: 'ec2/home#SecurityGroups:',
};

const getConsoleUrl = (key, region) => {
  const path = AWS_CONSOLE_URLS[key];
  if (!path) return null;
  if (key === 's3_buckets' || key === 'iam_roles' || key === 'instance_profiles') {
    return `https://console.aws.amazon.com/${path}`;
  }
  return `https://${region || 'us-east-1'}.console.aws.amazon.com/${path}`;
};

const AUTO_REFRESH_INTERVAL = 5 * 60 * 1000;

const CountUp = ({ value }) => {
  const [display, setDisplay] = useState(0);
  const prev = useRef(0);
  useEffect(() => {
    if (value === undefined || value === null || value === 'error') { setDisplay(value); return; }
    const start = prev.current;
    const diff = value - start;
    if (diff === 0) { setDisplay(value); return; }
    const duration = 600;
    const startTime = performance.now();
    const animate = (now) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.round(start + diff * eased));
      if (progress < 1) requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
    prev.current = value;
  }, [value]);
  if (display === 'error') return <span className="text-red-600">Error</span>;
  return <>{display?.toLocaleString() ?? '-'}</>;
};

const StatusDot = ({ pct }) => {
  const color = pct >= 90 ? 'bg-red-500' : pct >= 70 ? 'bg-amber-500' : 'bg-emerald-500';
  return <span className={`inline-block w-2 h-2 rounded-full ${color}`} />;
};

const AWSUsageDashboard = ({ inline = false }) => {
  const cached = _loadCache();
  const navigate = useNavigate();
  const [usage, setUsage] = useState(cached.usage);
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(cached.lastUpdated ? new Date(cached.lastUpdated) : null);
  const [error, setError] = useState(null);
  const [billedResources, setBilledResources] = useState(cached.billedResources);
  const [freeResources, setFreeResources] = useState(cached.freeResources);
  const [region, setRegion] = useState(cached.region);
  const [configLoading, setConfigLoading] = useState(cached.billedResources.length === 0);
  const [expandedResource, setExpandedResource] = useState(null);
  const [detailsCache, setDetailsCache] = useState({});
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [creatorFilter, setCreatorFilter] = useState('all');
  const [availableCreators, setAvailableCreators] = useState([]);
  const [refreshingKey, setRefreshingKey] = useState(null);
  const [sortField, setSortField] = useState('name');
  const [sortDir, setSortDir] = useState('asc');
  const [trendData, setTrendData] = useState([]);
  const [chartResources, setChartResources] = useState(new Set());
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [activeFilter, setActiveFilter] = useState(null);
  const [chartCollapsed, setChartCollapsed] = useState(false);
  const countdownRef = useRef(null);
  const autoRefreshRef = useRef(null);

  const STAT_RESOURCE_MAP = {
    'Est. Clusters': ['nat_gateways'],
    'Compute': ['ec2_instances'],
    'Network': ['vpcs', 'security_groups', 'nat_gateways'],
    'Storage': ['ebs_volumes', 's3_buckets'],
    'IAM': ['iam_roles', 'instance_profiles'],
    'Infra Stacks': ['cloudformation_stacks'],
  };

  const resourceConfig = [...billedResources, ...freeResources];

  // Pre-select top 3 resources by count when usage data first loads
  useEffect(() => {
    if (!usage || chartResources.size > 0) return;
    const entries = Object.entries(usage)
      .filter(([, v]) => typeof v === 'number' && v > 0)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3);
    if (entries.length > 0) {
      setChartResources(new Set(entries.map(([k]) => k)));
    }
  }, [usage]);

  useEffect(() => {
    const fetchTrend = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/aws/usage-trend?days=30');
        const data = await response.json();
        if (data.success) setTrendData(data.trend || []);
      } catch {}
    };
    fetchTrend();
  }, []);

  useEffect(() => {
    if (cached.billedResources.length > 0) {
      setConfigLoading(false);
      return;
    }
    const fetchConfig = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/aws/usage-config');
        const data = await response.json();
        if (data.success) {
          const billed = data.billedResources || [];
          const free = data.freeResources || [];
          const reg = data.metadata?.region || 'us-west-2';
          setBilledResources(billed);
          setFreeResources(free);
          setRegion(reg);
          const c = _loadCache();
          c.billedResources = billed;
          c.freeResources = free;
          c.region = reg;
          _saveCache(c);
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

  useEffect(() => {
    if (inline && !usage && !loading) {
      fetchUsage();
    }
  }, [inline, configLoading]);

  const handleKeyPress = useCallback((e) => {
    if (e.key === 'r' || e.key === 'R') {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;
      fetchUsage();
    }
  }, []);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [handleKeyPress]);

  useEffect(() => {
    if (autoRefresh) {
      setCountdown(AUTO_REFRESH_INTERVAL / 1000);
      countdownRef.current = setInterval(() => {
        setCountdown(prev => {
          if (prev <= 1) return AUTO_REFRESH_INTERVAL / 1000;
          return prev - 1;
        });
      }, 1000);
      autoRefreshRef.current = setInterval(() => {
        fetchUsage();
      }, AUTO_REFRESH_INTERVAL);
    }
    return () => {
      if (countdownRef.current) clearInterval(countdownRef.current);
      if (autoRefreshRef.current) clearInterval(autoRefreshRef.current);
    };
  }, [autoRefresh]);

  const fetchUsage = async () => {
    setLoading(true);
    setError(null);
    setDetailsCache({});
    setExpandedResource(null);
    try {
      const response = await fetch('http://localhost:8000/api/aws/usage');
      const data = await response.json();
      if (data.success) {
        const ts = new Date(data.timestamp);
        setUsage(data.usage);
        setLastUpdated(ts);
        const c = _loadCache();
        c.usage = data.usage;
        c.lastUpdated = ts;
        _saveCache(c);
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
    if (expandedResource === resourceKey) {
      setExpandedResource(null);
      return;
    }
    setExpandedResource(resourceKey);
    setSortField('name');
    setSortDir('asc');
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
        setUsage(prev => {
          const updated = { ...prev, [resourceKey]: data.count };
          const c = _loadCache();
          c.usage = updated;
          _saveCache(c);
          return updated;
        });
        setDetailsCache(prev => { const next = { ...prev }; delete next[resourceKey]; return next; });
      }
    } catch {} finally {
      setRefreshingKey(null);
    }
  };

  const calculateCost = (resource) => {
    if (!usage || !resource || !resource.costPerMonth) return null;
    const count = usage[resource.key];
    if (count === 'error' || count === undefined) return null;
    return (count * resource.costPerMonth).toFixed(2);
  };

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDir(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('asc');
    }
  };

  const SortIcon = ({ field }) => {
    if (sortField !== field) return <ChevronUpIcon className="h-3 w-3 text-gray-300" />;
    return sortDir === 'asc'
      ? <ChevronUpIcon className="h-3 w-3 text-[#232F3E]" />
      : <ChevronDownIcon className="h-3 w-3 text-[#232F3E]" />;
  };

  const InlineDetailsTable = () => {
    if (detailsLoading) {
      return (
        <div className="py-4 px-4 bg-[#FAFAFA] border-t border-gray-200">
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <ArrowPathIcon className="h-4 w-4 animate-spin" />
            Loading resources...
          </div>
        </div>
      );
    }

    const cached = detailsCache[expandedResource];
    if (!cached || cached.details.length === 0) {
      return (
        <div className="py-4 px-4 bg-[#FAFAFA] border-t border-gray-200">
          <p className="text-sm text-gray-500">No resources found</p>
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

    const sorted = [...filtered].sort((a, b) => {
      let aVal, bVal;
      switch (sortField) {
        case 'name': aVal = (a.name || '').toLowerCase(); bVal = (b.name || '').toLowerCase(); break;
        case 'id': aVal = a.id || ''; bVal = b.id || ''; break;
        case 'state': aVal = a.state || ''; bVal = b.state || ''; break;
        case 'created': aVal = a.created_at || a.launch_time || ''; bVal = b.created_at || b.launch_time || ''; break;
        default: aVal = ''; bVal = '';
      }
      if (aVal < bVal) return sortDir === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });

    return (
      <div className="bg-[#FAFAFA] border-t border-gray-200">
        <div className="flex items-center justify-between px-4 py-2 border-b border-gray-100">
          <p className="text-xs text-gray-600 font-medium">
            {filtered.length} resource{filtered.length !== 1 ? 's' : ''}
            {creatorFilter !== 'all' && <span className="text-gray-400"> filtered by {creatorFilter}</span>}
          </p>
          <div className="flex items-center gap-3">
            {availableCreators.length > 2 && (
              <select
                value={creatorFilter}
                onChange={(e) => setCreatorFilter(e.target.value)}
                className="text-xs border border-gray-300 rounded px-2 py-1 bg-white focus:border-[#FF9900] focus:ring-1 focus:ring-[#FF9900] outline-none"
              >
                {availableCreators.map(creator => (
                  <option key={creator} value={creator}>
                    {creator === 'all' ? 'All creators' : creator}
                  </option>
                ))}
              </select>
            )}
            <button
              onClick={(e) => { e.stopPropagation(); refreshResourceDetails(expandedResource); }}
              className="text-xs text-[#0073BB] hover:text-[#005C99] flex items-center gap-1 font-medium"
            >
              <ArrowPathIcon className={`h-3 w-3 ${detailsLoading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-[#FAFAFA] border-b border-gray-200">
                <th onClick={() => handleSort('name')} className="text-left px-4 py-2 font-semibold text-[#545B64] cursor-pointer hover:text-[#232F3E] select-none">
                  <span className="flex items-center gap-1">Name <SortIcon field="name" /></span>
                </th>
                <th onClick={() => handleSort('id')} className="text-left px-4 py-2 font-semibold text-[#545B64] cursor-pointer hover:text-[#232F3E] select-none">
                  <span className="flex items-center gap-1">Resource ID <SortIcon field="id" /></span>
                </th>
                {hasState && (
                  <th onClick={() => handleSort('state')} className="text-left px-4 py-2 font-semibold text-[#545B64] cursor-pointer hover:text-[#232F3E] select-none">
                    <span className="flex items-center gap-1">Status <SortIcon field="state" /></span>
                  </th>
                )}
                {hasCreated && (
                  <th onClick={() => handleSort('created')} className="text-left px-4 py-2 font-semibold text-[#545B64] cursor-pointer hover:text-[#232F3E] select-none">
                    <span className="flex items-center gap-1">Age <SortIcon field="created" /></span>
                  </th>
                )}
                {hasVpc && <th className="text-left px-4 py-2 font-semibold text-[#545B64]">VPC</th>}
                <th className="text-left px-4 py-2 font-semibold text-[#545B64]">Tags</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((resource, index) => {
                const created = resource.created_at || resource.launch_time;
                const age = created ? (() => {
                  const d = Math.floor((new Date() - new Date(created)) / (1000 * 60 * 60 * 24));
                  return d === 0 ? 'today' : d === 1 ? '1d' : `${d}d`;
                })() : null;
                const clusterTag = resource.tags?.['api.openshift.com/name'] || resource.tags?.['kubernetes.io/cluster'] || resource.tags?.['sigs.k8s.io/cluster-api-provider-aws/cluster-name'];
                const creator = resource.tags?.CreatedBy || resource.tags?.ManagedBy;
                const tagCount = resource.tags ? Object.keys(resource.tags).length : 0;

                return (
                  <tr key={index} className={`border-b border-gray-100 last:border-0 hover:bg-[#F1F8FF] ${index % 2 === 0 ? 'bg-white' : 'bg-[#FAFAFA]'}`}>
                    <td className="px-4 py-2">
                      <span className="font-medium text-[#0073BB]">{resource.name || 'Unnamed'}</span>
                    </td>
                    <td className="px-4 py-2">
                      <span className="text-[#545B64] font-mono text-xs">{resource.id || '-'}</span>
                    </td>
                    {hasState && (
                      <td className="px-4 py-2">
                        {resource.state && (
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${
                            resource.state === 'available' || resource.state === 'running' || resource.state === 'in-use'
                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                              : 'bg-gray-50 text-gray-600 border border-gray-200'
                          }`}>
                            <span className={`w-1.5 h-1.5 rounded-full ${
                              resource.state === 'available' || resource.state === 'running' || resource.state === 'in-use'
                                ? 'bg-emerald-500' : 'bg-gray-400'
                            }`} />
                            {resource.state}
                          </span>
                        )}
                      </td>
                    )}
                    {hasCreated && (
                      <td className="px-4 py-2 text-[#545B64]">{age || '-'}</td>
                    )}
                    {hasVpc && (
                      <td className="px-4 py-2">
                        <span className="text-[#545B64] font-mono text-xs">{resource.vpc_name || (resource.vpc_id ? resource.vpc_id.slice(-12) : '-')}</span>
                      </td>
                    )}
                    <td className="px-4 py-2">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {clusterTag && (
                          <span className="inline-block px-1.5 py-0.5 bg-[#E8F4FD] text-[#0073BB] rounded text-xs font-medium border border-[#D4E8F7]">{clusterTag}</span>
                        )}
                        {creator && (
                          <span className="inline-block px-1.5 py-0.5 bg-purple-50 text-purple-700 rounded text-xs font-medium border border-purple-200">{creator}</span>
                        )}
                        {tagCount > 0 && !clusterTag && !creator && (
                          <span className="text-[#545B64]">{tagCount} tags</span>
                        )}
                        {tagCount === 0 && <span className="text-gray-300">-</span>}
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

  const toggleChartResource = (key) => {
    setChartResources(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        if (next.size >= 3) {
          const first = next.values().next().value;
          next.delete(first);
        }
        next.add(key);
      }
      return next;
    });
  };

  const MetricCard = ({ resource, showCost = false }) => {
    const count = usage?.[resource.key];
    const isError = count === 'error';
    const usagePct = !isError && count !== undefined ? Math.round((count / resource.threshold) * 100) : 0;
    const cost = showCost ? calculateCost(resource) : null;
    const isExpanded = expandedResource === resource.key;
    const isCharted = chartResources.has(resource.key);
    const sparkColor = RESOURCE_COLORS[resource.key] || '#0073BB';

    const isEmpty = !isError && (count === 0 || count === undefined);
    const matchesFilter = activeFilter ? (STAT_RESOURCE_MAP[activeFilter] || []).includes(resource.key) : true;
    const isDimmed = activeFilter && !matchesFilter;

    return (
      <div className={`rounded-lg border transition-all ${isDimmed ? 'opacity-30 pointer-events-none' : ''} ${isExpanded ? 'bg-white border-[#0073BB] shadow-md col-span-full' : isEmpty ? 'bg-gray-50/50 border-gray-200 opacity-60 hover:opacity-100 hover:bg-white' : 'bg-white border-gray-200 hover:shadow-sm'} ${!isExpanded ? 'hover:border-l-[#0073BB] hover:border-l-[3px]' : ''}`}>
        <div
          onClick={() => count > 0 && !isError && toggleResourceDetails(resource.key)}
          className={`p-4 ${count > 0 && !isError ? 'cursor-pointer' : ''} group`}
        >
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <ServiceIcon resourceKey={resource.key} size={14} />
              <StatusDot pct={usagePct} />
              <span className="text-xs font-semibold text-[#545B64] uppercase tracking-wide">{resource.label}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <button
                onClick={(e) => refreshSingleResource(e, resource.key)}
                disabled={refreshingKey === resource.key}
                className="opacity-0 group-hover:opacity-100 transition-opacity text-gray-400 hover:text-[#0073BB]"
                title="Refresh"
              >
                <ArrowPathIcon className={`h-3.5 w-3.5 ${refreshingKey === resource.key ? 'animate-spin text-[#0073BB]' : ''}`} />
              </button>
              {isExpanded && <ChevronUpIcon className="h-3.5 w-3.5 text-[#0073BB]" />}
              {!isExpanded && count > 0 && !isError && <ChevronDownIcon className="h-3.5 w-3.5 text-gray-300 group-hover:text-[#0073BB]" />}
            </div>
          </div>

          <div className="flex items-end justify-between">
            <div>
              {isError ? (
                <span className="text-2xl font-bold text-red-600">Error</span>
              ) : (
                <span className="text-3xl font-bold text-[#232F3E]"><CountUp value={count} /></span>
              )}
              <span className="text-sm text-[#879596] ml-1">/ {resource.threshold.toLocaleString()}</span>
            </div>
            {showCost && !isError && (
              <div className="text-right">
                {cost ? (
                  <span className="text-sm font-bold text-[#FF9900]">${cost}<span className="text-xs font-normal text-[#879596]">/mo</span></span>
                ) : resource.costType === 'variable' ? (
                  <span className="text-xs font-medium text-[#879596]">Variable</span>
                ) : null}
              </div>
            )}
          </div>

          {!isError && (
            <div className="mt-3 w-full bg-gray-100 rounded-full h-1.5">
              <div
                className={`h-full rounded-full transition-all duration-500 ${usagePct >= 90 ? 'bg-red-500' : usagePct >= 70 ? 'bg-amber-500' : 'bg-[#0073BB]'}`}
                style={{ width: `${Math.max(Math.min(usagePct, 100), 1)}%` }}
              />
            </div>
          )}

          <div className="flex items-center justify-between mt-1.5">
            <div className="flex items-center gap-2">
              <Sparkline data={trendData} dataKey={resource.key} color={sparkColor} width={64} height={20} />
              <span className="text-xs text-[#879596]">{resource.description}</span>
            </div>
            <div className="flex items-center gap-2">
              <a
                href={getConsoleUrl(resource.key, region)}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="text-xs px-1.5 py-0.5 rounded border border-gray-200 text-[#879596] hover:border-[#0073BB] hover:text-[#0073BB] transition-all opacity-0 group-hover:opacity-100"
              >
                AWS ↗
              </a>
              <button
                onClick={(e) => { e.stopPropagation(); toggleChartResource(resource.key); }}
                className={`text-xs px-1.5 py-0.5 rounded border transition-all ${isCharted ? 'border-[#0073BB] bg-[#E8F4FD] text-[#0073BB] font-semibold' : 'border-gray-200 text-[#879596] hover:border-[#0073BB] hover:text-[#0073BB]'}`}
              >
                {isCharted ? 'Charted' : 'Chart'}
              </button>
              <span className={`text-xs font-semibold ${usagePct >= 90 ? 'text-red-600' : usagePct >= 70 ? 'text-amber-600' : 'text-[#879596]'}`}>{usagePct}%</span>
            </div>
          </div>
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
    onAIAssistantClick: () => navigate('/mce'),
    onTerminalClick: () => navigate('/mce'),
    onNotificationsClick: () => navigate('/mce'),
    onRecentTasksClick: () => navigate('/mce'),
    onAWSUsageClick: () => navigate('/aws-usage'),
  };

  const contentBody = (
    <div className={inline ? "" : "p-6"}>
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
          <p className="text-red-700 font-medium text-sm">Error</p>
          <p className="text-red-600 text-xs mt-1">{error}</p>
        </div>
      )}

      {configLoading && (
        <div className="bg-white border border-gray-200 rounded-lg p-12 text-center">
          <ArrowPathIcon className="h-8 w-8 animate-spin text-[#0073BB] mx-auto mb-3" />
          <p className="text-[#232F3E] font-medium">Loading AWS resource configuration...</p>
          <p className="text-[#545B64] text-sm mt-1">Fetching resource thresholds and quotas</p>
        </div>
      )}

      {!configLoading && !usage && !loading && !error && (
        <div className="bg-white border border-gray-200 rounded-lg p-12 text-center">
          <div className="w-12 h-12 bg-[#FF9900]/10 rounded-full flex items-center justify-center mx-auto mb-4">
            <ArrowPathIcon className="h-6 w-6 text-[#FF9900]" />
          </div>
          <p className="text-[#232F3E] text-lg font-semibold">Load AWS Resource Usage</p>
          <p className="text-[#545B64] text-sm mt-2">Query your AWS account for current resource counts and quota usage</p>
          <button
            onClick={fetchUsage}
            className="mt-4 px-6 py-2.5 bg-[#FF9900] text-white rounded-lg font-medium text-sm hover:bg-[#EC7211] transition-colors shadow-sm"
          >
            Refresh Data
          </button>
        </div>
      )}

      {usage && (
        <>
          {/* Summary + Resource Metric Cards */}
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <h2 className="text-sm font-semibold text-[#232F3E] uppercase tracking-wide">Service Quotas & Usage</h2>
              {activeFilter && (
                <button
                  onClick={() => setActiveFilter(null)}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-[#E8F4FD] text-[#0073BB] border border-[#D4E8F7] hover:bg-[#D4E8F7] transition-colors"
                >
                  Filtered: {activeFilter}
                  <span className="text-[#0073BB]/60 hover:text-[#0073BB] ml-0.5">&times;</span>
                </button>
              )}
            </div>
            <p className="text-xs text-[#879596]">
              {resourceConfig.length} services monitored · <span className="text-[#232F3E] font-medium">{resourceConfig.filter(r => usage[r.key] > 0 && usage[r.key] !== 'error').length} with active resources</span>
            </p>
          </div>
          {/* Quick Stats Row */}
          <div className="grid grid-cols-6 gap-2.5 mb-5 bg-gradient-to-r from-gray-50 via-white to-gray-50 rounded-lg p-2.5 border border-gray-100">
            {[
              { label: 'Est. Clusters', value: Math.round((usage.nat_gateways || 0) / 2), color: '#0073bb', bg: '#E8F4FD' },
              { label: 'Compute', value: usage.ec2_instances || 0, color: '#1b660f', bg: '#E9F5E9' },
              { label: 'Network', value: (usage.vpcs || 0) + (usage.security_groups || 0) + (usage.nat_gateways || 0), color: '#8c6800', bg: '#FFF8E1' },
              { label: 'Storage', value: (usage.ebs_volumes || 0) + (usage.s3_buckets || 0), color: '#c23127', bg: '#FEECEB' },
              { label: 'IAM', value: (usage.iam_roles || 0) + (usage.instance_profiles || 0), color: '#7d2105', bg: '#FBE9E7' },
              { label: 'Infra Stacks', value: usage.cloudformation_stacks || 0, color: '#0073bb', bg: '#E8F4FD' },
            ].map((stat) => {
              const isActive = activeFilter === stat.label;
              const hasFilter = activeFilter !== null;
              return (
                <div
                  key={stat.label}
                  onClick={() => setActiveFilter(prev => prev === stat.label ? null : stat.label)}
                  className={`bg-white border rounded-lg px-3 py-2.5 text-center cursor-pointer transition-all ${
                    isActive
                      ? 'border-transparent shadow-md ring-2'
                      : hasFilter
                        ? 'border-gray-200 opacity-50 hover:opacity-75'
                        : 'border-gray-200 hover:shadow-sm'
                  }`}
                  style={{
                    borderTop: `3px solid ${stat.color}`,
                    ...(isActive ? { ringColor: stat.color, boxShadow: `0 0 0 2px ${stat.color}33, 0 4px 6px -1px rgba(0,0,0,0.1)` } : {}),
                  }}
                >
                  <p className="text-xl font-bold" style={{ color: stat.color }}>{stat.value}</p>
                  <p className="text-xs uppercase tracking-wider font-semibold mt-0.5" style={{ color: '#879596' }}>{stat.label}</p>
                </div>
              );
            })}
          </div>

          {/* Trend Chart — collapsible */}
          <div className="bg-white border border-gray-200 rounded-lg mb-5">
            <div
              onClick={() => setChartCollapsed(prev => !prev)}
              className="flex items-center justify-between px-4 py-2.5 cursor-pointer select-none hover:bg-gray-50 transition-colors rounded-t-lg"
            >
              <span className="text-xs font-semibold text-[#545B64] uppercase tracking-wide">Usage Trend</span>
              {chartCollapsed
                ? <ChevronDownIcon className="h-4 w-4 text-[#879596]" />
                : <ChevronUpIcon className="h-4 w-4 text-[#879596]" />
              }
            </div>
            {!chartCollapsed && (
              <div className="px-4 pb-4">
                {chartResources.size > 0 ? (
                  <AWSUsageTrend
                    selectedResources={chartResources}
                    onToggleResource={toggleChartResource}
                    height={200}
                  />
                ) : (
                  <div className="flex items-center justify-center" style={{ height: 200 }}>
                    <p className="text-sm text-[#879596]">Select resources to chart using the <span className="font-medium text-[#545B64]">Chart</span> button on resource cards below</p>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {(() => {
              const sorted = [...resourceConfig].sort((a, b) => {
                const aCount = usage[a.key] || 0;
                const bCount = usage[b.key] || 0;
                const aActive = aCount > 0 && aCount !== 'error' ? 1 : 0;
                const bActive = bCount > 0 && bCount !== 'error' ? 1 : 0;
                if (aActive !== bActive) return bActive - aActive;
                return 0;
              });
              const totalResources = Object.values(usage).reduce((sum, v) => sum + (typeof v === 'number' ? v : 0), 0);
              const activeServices = sorted.filter(r => (usage[r.key] || 0) > 0 && usage[r.key] !== 'error').length;
              const remainder = sorted.length % 4;
              return (
                <>
                  {sorted.map((resource) => (
                    <MetricCard
                      key={resource.key}
                      resource={resource}
                      showCost={billedResources.some(r => r.key === resource.key)}
                    />
                  ))}
                  {remainder > 0 && (
                    <div className={`rounded-lg border border-dashed border-gray-300 bg-gradient-to-br from-gray-50 to-white p-4 flex flex-col justify-center items-center text-center transition-all ${activeFilter ? 'opacity-30 pointer-events-none' : ''}`}>
                      <p className="text-3xl font-bold text-[#232F3E]">{totalResources}</p>
                      <p className="text-xs uppercase tracking-wider text-[#879596] font-semibold mt-1">Total Resources</p>
                      <p className="text-xs text-[#545B64] mt-2">{activeServices} of {sorted.length} services active</p>
                      <div className="flex gap-1 mt-2">
                        {sorted.map(r => {
                          const count = usage[r.key] || 0;
                          const active = count > 0 && count !== 'error';
                          return <span key={r.key} className={`w-2 h-2 rounded-sm ${active ? 'bg-emerald-400' : 'bg-gray-200'}`} title={r.label} />;
                        })}
                      </div>
                    </div>
                  )}
                </>
              );
            })()}
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
      <div className="flex-1 overflow-auto bg-[#F2F3F3]">
        {/* AWS-style Header */}
        <div className="px-6 py-4 flex items-center justify-between h-[72px]" style={{ background: '#232F3E' }}>
          <div className="flex items-center gap-4">
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-xl font-bold text-white tracking-tight">AWS Resource Usage</h1>
                {region && (
                  <a
                    href={`https://${region}.console.aws.amazon.com/console/home?region=${region}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-2 py-0.5 rounded text-xs font-medium bg-[#37475A] text-[#D5DBDB] border border-[#4A5568] hover:bg-[#4A5568] hover:text-white transition-colors"
                  >
                    {region}
                  </a>
                )}
                {usage && (() => {
                  const natCost = calculateCost(resourceConfig.find(r => r.key === 'nat_gateways'));
                  const r53Cost = calculateCost(resourceConfig.find(r => r.key === 'route53_zones'));
                  const total = (parseFloat(natCost || 0) + parseFloat(r53Cost || 0)).toFixed(2);
                  return total > 0 ? (
                    <span className="px-2 py-0.5 rounded text-xs font-medium bg-[#FF9900]/20 text-[#FF9900] border border-[#FF9900]/30">
                      ${total}/mo
                    </span>
                  ) : null;
                })()}
              </div>
              {lastUpdated && (
                <p className="text-[#879596] text-xs mt-0.5">
                  Last updated {lastUpdated.toLocaleString()}
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setAutoRefresh(prev => !prev)}
              className={`px-3 py-2 rounded text-xs font-medium transition-all ${
                autoRefresh
                  ? 'bg-[#37475A] text-[#FF9900] border border-[#FF9900]/30'
                  : 'bg-[#37475A] text-[#879596] border border-[#4A5568] hover:text-[#D5DBDB]'
              }`}
              title="Auto-refresh every 5 minutes"
            >
              {autoRefresh ? `Auto ${Math.floor(countdown / 60)}:${String(countdown % 60).padStart(2, '0')}` : 'Auto'}
            </button>
            <button
              onClick={fetchUsage}
              disabled={loading}
              className={`flex items-center gap-2 px-5 py-2 rounded font-medium text-sm transition-all ${
                loading
                  ? 'bg-[#37475A] text-[#879596] cursor-not-allowed'
                  : 'bg-[#FF9900] text-[#232F3E] hover:bg-[#EC7211] shadow-sm'
              }`}
              title="Refresh data (R)"
            >
              <ArrowPathIcon className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              {loading ? 'Loading...' : 'Refresh Data'}
            </button>
          </div>
        </div>

        {/* Breadcrumb bar */}
        <div className="bg-white border-b border-gray-200 px-6 py-2">
          <div className="flex items-center gap-2 text-xs text-[#545B64]">
            <span className="hover:text-[#0073BB] cursor-pointer" onClick={() => navigate('/mce')}>Home</span>
            <span className="text-gray-300">/</span>
            <span className="font-medium text-[#232F3E]">AWS Resource Usage</span>
          </div>
        </div>

        {/* Cost & Health Summary Strip */}
        {usage && (() => {
          const totalMonthlyCost = billedResources.reduce(
            (sum, r) => sum + (r.costPerMonth && usage?.[r.key] && usage[r.key] !== 'error' ? r.costPerMonth * usage[r.key] : 0), 0
          );
          const billedCount = billedResources.filter(r => usage?.[r.key] > 0 && usage[r.key] !== 'error').length;
          const freeCount = freeResources.filter(r => usage?.[r.key] > 0 && usage[r.key] !== 'error').length;

          const costDrivers = billedResources
            .map(r => ({ ...r, totalCost: r.costPerMonth && usage?.[r.key] && usage[r.key] !== 'error' ? r.costPerMonth * usage[r.key] : 0 }))
            .filter(r => r.totalCost > 0)
            .sort((a, b) => b.totalCost - a.totalCost)
            .slice(0, 3);

          const allResources = [...billedResources, ...freeResources];
          const quotaBuckets = allResources.reduce((acc, r) => {
            const count = usage?.[r.key];
            if (!count || count === 'error' || !r.threshold) return acc;
            const pct = (count / r.threshold) * 100;
            if (pct >= 80) acc.red++;
            else if (pct >= 50) acc.amber++;
            else acc.green++;
            return acc;
          }, { green: 0, amber: 0, red: 0 });
          const quotaTotal = quotaBuckets.green + quotaBuckets.amber + quotaBuckets.red;
          const atRisk = quotaBuckets.amber + quotaBuckets.red;

          return (
            <div className="bg-white border-b border-gray-200 px-6 py-4 shrink-0">
              <div className="grid grid-cols-12 gap-4 items-center">
                {/* Cost + Health Summary */}
                <div className="col-span-3 bg-gradient-to-br from-emerald-50 to-white border border-emerald-200 rounded-lg p-4">
                  <p className="text-xs uppercase tracking-wider text-emerald-600 font-semibold mb-1">Monthly Cost</p>
                  <p className="text-3xl font-bold" style={{ color: '#059669' }}>
                    ${totalMonthlyCost.toFixed(2)}
                  </p>
                  <div className="flex gap-2 mt-2">
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-[#FFF3E0] text-[#FF9900] border border-[#FFE0B2]">
                      {billedCount} billed
                    </span>
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-[#545B64] border border-gray-200">
                      {freeCount} free
                    </span>
                  </div>
                </div>

                {/* Top Cost Drivers */}
                {(() => {
                  const variableResources = billedResources.filter(r => !r.costPerMonth && usage?.[r.key] > 0 && usage[r.key] !== 'error');
                  const variableCount = variableResources.length;
                  return (
                    <div className="col-span-6">
                      <p className="text-xs uppercase tracking-wider text-[#879596] font-semibold mb-2">Cost Breakdown</p>
                      <div className="grid grid-cols-3 gap-2">
                        {costDrivers.map(r => (
                          <div key={r.key} className="bg-gray-50 border border-gray-200 rounded-lg px-3 py-2.5 flex items-center gap-2.5">
                            <ServiceIcon resourceKey={r.key} size={18} />
                            <div className="min-w-0">
                              <p className="text-xs font-semibold text-[#232F3E] truncate">{r.label}</p>
                              <p className="text-xs text-[#879596]">
                                {usage[r.key]} x ${r.costPerMonth}
                              </p>
                              <p className="text-sm font-bold" style={{ color: '#FF9900' }}>${r.totalCost.toFixed(2)}<span className="text-xs font-normal text-[#879596]">/mo</span></p>
                            </div>
                          </div>
                        ))}
                        {costDrivers.length < 3 && (
                          <div className="bg-gradient-to-br from-amber-50 to-white border border-amber-200 rounded-lg px-3 py-2.5">
                            <p className="text-xs font-semibold text-[#232F3E]">Variable Costs</p>
                            <p className="text-xs text-[#879596] mt-0.5">
                              {variableCount} service{variableCount !== 1 ? 's' : ''} (EC2, EBS, LB, S3)
                            </p>
                            <p className="text-sm font-medium mt-0.5" style={{ color: '#d97706' }}>Usage-based pricing</p>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })()}

                {/* Resource Health */}
                <div className="col-span-3 bg-gray-50 border border-gray-200 rounded-lg p-4">
                  <p className="text-xs uppercase tracking-wider text-[#879596] font-semibold mb-2">Resource Health</p>
                  {quotaTotal > 0 ? (
                    <>
                      <div className="flex w-full h-3 rounded-full overflow-hidden bg-gray-200">
                        {quotaBuckets.green > 0 && <div className="bg-emerald-500 transition-all" style={{ width: `${(quotaBuckets.green / quotaTotal) * 100}%` }} />}
                        {quotaBuckets.amber > 0 && <div className="bg-amber-400 transition-all" style={{ width: `${(quotaBuckets.amber / quotaTotal) * 100}%` }} />}
                        {quotaBuckets.red > 0 && <div className="bg-red-500 transition-all" style={{ width: `${(quotaBuckets.red / quotaTotal) * 100}%` }} />}
                      </div>
                      <div className="flex items-center gap-3 mt-1.5 mb-2">
                        <span className="flex items-center gap-1 text-xs font-medium text-gray-600">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />{quotaBuckets.green} ok
                        </span>
                        {quotaBuckets.amber > 0 && (
                          <span className="flex items-center gap-1 text-xs font-semibold text-amber-600">
                            <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />{quotaBuckets.amber} warn
                          </span>
                        )}
                        {quotaBuckets.red > 0 && (
                          <span className="flex items-center gap-1 text-xs font-bold text-red-600">
                            <span className="w-1.5 h-1.5 rounded-full bg-red-500" />{quotaBuckets.red} critical
                          </span>
                        )}
                      </div>
                      <div className="space-y-1">
                        {allResources
                          .filter(r => usage?.[r.key] > 0 && usage[r.key] !== 'error' && r.threshold)
                          .sort((a, b) => ((usage[b.key] || 0) / b.threshold) - ((usage[a.key] || 0) / a.threshold))
                          .slice(0, 5)
                          .map(r => {
                            const pct = Math.round(((usage[r.key] || 0) / r.threshold) * 100);
                            const barColor = pct >= 80 ? '#ef4444' : pct >= 50 ? '#f59e0b' : '#22c55e';
                            return (
                              <div key={r.key} className="flex items-center gap-2">
                                <span className="text-xs w-[60px] truncate" style={{ color: '#545B64' }}>{r.label?.split(' ')[0]}</span>
                                <div className="flex-1 h-1.5 rounded-full bg-gray-200 overflow-hidden">
                                  <div className="h-full rounded-full transition-all" style={{ width: `${Math.max(pct, 2)}%`, backgroundColor: barColor }} />
                                </div>
                                <span className="text-xs font-semibold w-[30px] text-right" style={{ color: barColor }}>{pct}%</span>
                              </div>
                            );
                          })}
                      </div>
                    </>
                  ) : (
                    <p className="text-xs text-[#879596]">No quota data</p>
                  )}
                </div>
              </div>
            </div>
          );
        })()}

        <div className="p-6">
          {contentBody}
        </div>
      </div>
    </div>
  );
};

export default AWSUsageDashboard;
