import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowPathIcon, ChevronDownIcon, ChevronRightIcon } from '@heroicons/react/24/outline';
import CapaSidebar from '../components/sidebar/CapaSidebar';
import { buildApiUrl } from '../config/api';

const CACHE_KEY = 'agent-dashboard-cache';
const _loadCache = () => {
  try {
    const c = JSON.parse(sessionStorage.getItem(CACHE_KEY));
    return c && c.metrics ? c : null;
  } catch { return null; }
};
const _saveCache = (cache) => {
  try { sessionStorage.setItem(CACHE_KEY, JSON.stringify(cache)); } catch {}
};

const STATE_COLORS = {
  resolved: '#22c55e', failed: '#ef4444', remediating: '#f97316', diagnosing: '#3b82f6', detected: '#eab308',
};

const STAGE_COLORS = {
  monitor: '#3b82f6', diagnose: '#a855f7', remediate: '#FF9900', learn: '#10b981',
};

const TIME_SAVED_EST = {
  rosanetwork_stuck_deletion: 45, cloudformation_deletion_failure: 30,
  rosaroleconfig_stuck_deletion: 15, api_rate_limit: 5, ocm_auth_failure: 15,
};

const dashboardStyles = `
  @keyframes pulse-glow {
    0%, 100% { box-shadow: 0 0 4px 2px rgba(16, 185, 129, 0.2); }
    50% { box-shadow: 0 0 8px 4px rgba(16, 185, 129, 0.4); }
  }
  @keyframes bar-fill {
    from { transform: scaleX(0); }
    to { transform: scaleX(1); }
  }
  @keyframes fade-in-up {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .agent-dot-active { animation: pulse-glow 2s ease-in-out infinite; border-radius: 50%; }
  .bar-animate { transform-origin: left; animation: bar-fill 0.7s ease-out forwards; }
  .fade-in { animation: fade-in-up 0.4s ease-out forwards; }
`;

const AgentDashboard = () => {
  const cached = _loadCache();
  const navigate = useNavigate();
  const [data, setData] = useState(cached);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expandedActivity, setExpandedActivity] = useState(null);
  const [expandedKnowledge, setExpandedKnowledge] = useState(null);
  const [dateRange, setDateRange] = useState('all');
  const [operationFilter, setOperationFilter] = useState('');
  const [knowledgeSortKey, setKnowledgeSortKey] = useState('hits');
  const [knowledgeSortDir, setKnowledgeSortDir] = useState('desc');
  const [knowledgeFilter, setKnowledgeFilter] = useState('all');
  const [timelineSort, setTimelineSort] = useState('newest');

  const DATE_RANGES = [
    { key: '1h', label: '1h', hours: 1 },
    { key: '24h', label: '24h', hours: 24 },
    { key: '7d', label: '7d', hours: 168 },
    { key: '30d', label: '30d', hours: 720 },
    { key: 'all', label: 'All', hours: 0 },
  ];

  const getSinceParam = (rangeKey) => {
    const range = DATE_RANGES.find(r => r.key === rangeKey);
    if (!range || range.hours === 0) return '';
    const d = new Date(Date.now() - range.hours * 3600000);
    return d.toISOString();
  };

  const fetchAll = async () => {
    setLoading(true);
    setError(null);
    try {
      const sinceParam = getSinceParam(dateRange);
      const opParam = operationFilter ? `&operation_type=${operationFilter}` : '';
      const baseMetrics = sinceParam
        ? `/api/agents/remediation-metrics?since=${encodeURIComponent(sinceParam)}${opParam}`
        : `/api/agents/remediation-metrics?${opParam.slice(1)}`;
      const metricsUrl = baseMetrics.endsWith('?') ? baseMetrics.slice(0, -1) : baseMetrics;
      const baseDash = sinceParam
        ? `/api/agents/dashboard?since=${encodeURIComponent(sinceParam)}${opParam}`
        : `/api/agents/dashboard?${opParam.slice(1)}`;
      const dashUrl = baseDash.endsWith('?') ? baseDash.slice(0, -1) : baseDash;
      const [dashRes, metricsRes, confRes, kbRes, roiRes] = await Promise.all([
        fetch(buildApiUrl(dashUrl)),
        fetch(buildApiUrl(metricsUrl)),
        fetch(buildApiUrl('/api/agents/confidence')),
        fetch(buildApiUrl('/api/agents/knowledge-base')),
        fetch(buildApiUrl(operationFilter ? `/api/agents/roi?operation_type=${operationFilter}` : '/api/agents/roi')),
      ]);
      const [dash, metrics, conf, kb, roi] = await Promise.all([
        dashRes.json(), metricsRes.json(), confRes.json(), kbRes.json(), roiRes.json(),
      ]);
      const d = {
        dashboard: dash, metrics: metrics.metrics, confidence: conf,
        kb: kb.health, roi: roi.roi, lastUpdated: new Date(),
      };
      setData(d);
      _saveCache(d);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { if (!data) fetchAll(); }, []);
  useEffect(() => { fetchAll(); }, [dateRange, operationFilter]);
  useEffect(() => {
    const interval = setInterval(fetchAll, 30000);
    return () => clearInterval(interval);
  }, []);

  const m = data?.metrics;
  const roi = data?.roi;
  const kb = data?.kb;
  const patterns = data?.confidence?.patterns || [];
  const dist = data?.dashboard?.state_distribution || {};
  const events = data?.dashboard?.pipeline_activity || [];
  const statuses = data?.dashboard?.overview?.agent_statuses || {};
  const totalStates = Object.values(dist).reduce((s, v) => s + v, 0);
  const hrs = Math.floor((roi?.total_manual_minutes_saved || 0) / 60);
  const mins = (roi?.total_manual_minutes_saved || 0) % 60;

  const mergedPatterns = useMemo(() => {
    const triggerMap = {};
    (kb?.most_triggered || []).forEach(p => { triggerMap[p.type] = p; });
    return patterns.map(p => ({
      ...p,
      count: triggerMap[p.type]?.count || 0,
      first_seen: triggerMap[p.type]?.first_seen,
      last_seen: triggerMap[p.type]?.last_seen,
      outcome_success: triggerMap[p.type]?.success || 0,
      outcome_failed: triggerMap[p.type]?.failed || 0,
      outcome_rate: triggerMap[p.type]?.success_rate,
    }));
  }, [patterns, kb]);

  const sidebarHandlers = {
    onComponentsClick: () => navigate('/mce'), onVerifyClick: () => navigate('/mce'),
    onConfigureClick: () => navigate('/mce'), onProvisionClick: () => navigate('/mce'),
    onRosaHcpClustersClick: () => navigate('/mce'), onResourcesClick: () => navigate('/mce'),
    onEnvironmentsClick: () => navigate('/mce'), onCredentialsClick: () => navigate('/mce'),
    onAIAssistantClick: () => navigate('/mce'), onTerminalClick: () => navigate('/mce'),
    onNotificationsClick: () => navigate('/mce'), onRecentTasksClick: () => navigate('/mce'),
    onAWSUsageClick: () => navigate('/aws-usage'), onAgentDashboardClick: () => {},
  };

  const confidenceColor = (pct) => {
    if (pct >= 80) return '#059669';
    if (pct >= 50) return '#d97706';
    return '#dc2626';
  };

  return (
    <div className="flex h-screen bg-[#F2F3F3]">
      <style>{dashboardStyles}</style>
      <CapaSidebar {...sidebarHandlers} activeSection="agent-dashboard" environment="mce" />
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 flex items-center justify-between h-[72px] shrink-0" style={{ background: '#232F3E' }}>
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-md flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, #FF9900, #EC7211)' }}>
              <span className="text-xs font-black text-white">AI</span>
            </div>
            <div>
              <h1 className="text-xl font-bold text-white tracking-tight">AI Agent Pipeline</h1>
              {data?.lastUpdated && (
                <p className="text-[#879596] text-xs mt-0.5">
                  Last updated {new Date(data.lastUpdated).toLocaleString()}
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center rounded overflow-hidden border border-[#4A5568]">
              {[{ key: '', label: 'All' }, { key: 'provision', label: 'Provision' }, { key: 'delete', label: 'Delete' }].map(r => (
                <button key={r.key} onClick={() => setOperationFilter(r.key)}
                  className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                    operationFilter === r.key ? 'bg-[#37475A] text-white' : 'bg-transparent text-[#879596] hover:text-[#D5DBDB]'
                  }`}>{r.label}</button>
              ))}
            </div>
            <div className="flex items-center rounded overflow-hidden border border-[#4A5568]">
              {DATE_RANGES.map(r => (
                <button key={r.key} onClick={() => setDateRange(r.key)}
                  className={`px-2.5 py-1.5 text-xs font-medium transition-colors ${
                    dateRange === r.key ? 'bg-[#37475A] text-white' : 'bg-transparent text-[#879596] hover:text-[#D5DBDB]'
                  }`}>{r.label}</button>
              ))}
            </div>
            <button onClick={fetchAll} disabled={loading}
              className={`flex items-center gap-2 px-5 py-2 rounded font-medium text-sm transition-all ${
                loading ? 'bg-[#37475A] text-[#879596] cursor-not-allowed' : 'bg-[#FF9900] text-[#232F3E] hover:bg-[#EC7211] shadow-sm'
              }`}>
              <ArrowPathIcon className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              {loading ? 'Loading...' : 'Refresh'}
            </button>
          </div>
        </div>

        {/* Breadcrumb */}
        <div className="bg-white border-b border-gray-200 px-6 py-2 shrink-0">
          <div className="flex items-center gap-2 text-xs text-[#545B64]">
            <span className="hover:text-[#0073BB] cursor-pointer" onClick={() => navigate('/mce')}>Home</span>
            <span className="text-gray-300">/</span>
            <span className="font-medium text-[#232F3E]">AI Agent Pipeline</span>
          </div>
        </div>

        {/* Pipeline Strip + ROI Stats */}
        {data && (
          <div className="bg-white border-b border-gray-200 px-6 py-3 shrink-0">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-0">
                {[
                  { label: 'Monitor', value: kb?.total_patterns || 0, unit: 'patterns', color: STAGE_COLORS.monitor, key: 'monitor' },
                  { label: 'Diagnose', value: totalStates, unit: 'detected', color: STAGE_COLORS.diagnose, key: 'diagnostic' },
                  { label: 'Remediate', value: m?.total_remediated || 0, unit: 'fixed', color: STAGE_COLORS.remediate, key: 'remediation' },
                  { label: 'Learn', value: kb?.total_outcomes || 0, unit: 'outcomes', color: STAGE_COLORS.learn, key: 'learning' },
                ].map((stage, idx, arr) => (
                  <React.Fragment key={stage.label}>
                    {idx > 0 && (() => {
                      const prev = arr[idx - 1];
                      const gradId = `arrow-grad-${prev.label}-${stage.label}`;
                      return (
                        <svg width="32" height="20" viewBox="0 0 32 20" className="mx-0.5 shrink-0">
                          <defs>
                            <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="0%">
                              <stop offset="0%" stopColor={prev.color} />
                              <stop offset="100%" stopColor={stage.color} />
                            </linearGradient>
                          </defs>
                          <line x1="0" y1="10" x2="22" y2="10" stroke={`url(#${gradId})`} strokeWidth="2" />
                          <polygon points="20,5 30,10 20,15" fill={stage.color} />
                        </svg>
                      );
                    })()}
                    <div className="flex items-center gap-2.5 px-3.5 py-1.5 bg-white border border-gray-200 rounded-md"
                      style={{ borderLeft: `3px solid ${stage.color}` }}>
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: stage.color }}>{stage.label}</p>
                        <p className="text-xs text-[#879596]">{stage.unit}</p>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-2xl font-bold text-[#232F3E]">{stage.value}</span>
                        {statuses[stage.key]?.status === 'active' && (
                          <span className="agent-dot-active"
                            style={{ width: 6, height: 6, backgroundColor: '#22c55e', display: 'inline-block' }} />
                        )}
                      </div>
                    </div>
                  </React.Fragment>
                ))}
              </div>
              <div className="flex items-center gap-2">
                {[
                  { label: 'Time Saved', value: `${hrs}h ${mins}m`, color: '#232F3E' },
                  { label: 'Cost Avoided', value: `$${roi?.total_cost_avoided_usd || 0}`, color: '#16a34a' },
                  { label: 'Clusters Saved', value: roi?.clusters_saved || 0, color: '#3b82f6' },
                  { label: 'Success Rate', value: m?.success_rate != null ? `${m.success_rate}%` : '--',
                    color: (m?.success_rate || 0) >= 80 ? '#059669' : (m?.success_rate || 0) >= 50 ? '#d97706' : '#dc2626' },
                ].map(tile => (
                  <div key={tile.label} className="bg-gray-50 border border-gray-200 rounded-md px-3 py-1.5 text-center">
                    <p className="text-xs font-semibold uppercase tracking-wider text-[#879596]">{tile.label}</p>
                    <p className="text-lg font-bold" style={{ color: tile.color }}>{tile.value}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="mx-6 mt-3 rounded-lg p-3 text-sm shrink-0 bg-red-50 border border-red-200 text-red-700">{error}</div>
        )}

        {!data && !loading && !error && (
          <div className="m-6 bg-white border border-gray-200 rounded-lg p-12 text-center fade-in">
            <div className="w-12 h-12 bg-[#FF9900]/10 rounded-full flex items-center justify-center mx-auto mb-4">
              <ArrowPathIcon className="h-6 w-6 text-[#FF9900]" />
            </div>
            <p className="text-[#232F3E] text-lg font-semibold">Load Agent Pipeline Data</p>
            <p className="text-[#545B64] text-sm mt-2">Click Refresh to load agent monitoring and remediation data</p>
            <button onClick={fetchAll}
              className="mt-4 px-6 py-2.5 bg-[#FF9900] text-[#232F3E] rounded-lg font-medium text-sm hover:bg-[#EC7211] transition-colors shadow-sm">
              Refresh Data
            </button>
          </div>
        )}

        {/* Main Content: Activity (left) + Knowledge (right) */}
        {data && (
          <div className="flex-1 overflow-hidden fade-in flex gap-3 p-4" style={{ minHeight: 0 }}>

            {/* ── LEFT: Activity & Remediation ── */}
            <div className="flex flex-col" style={{ flex: '1.2 1 0', minHeight: 0 }}>
              <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden flex flex-col h-full">
                <div className="px-4 py-2.5 border-b border-gray-200 bg-gray-50/50 flex items-center justify-between shrink-0">
                  <span className="text-base font-bold uppercase tracking-wider" style={{ color: '#232F3E' }}>Activity & Remediation</span>
                  <div className="flex items-center gap-1.5">
                    {Object.entries(STATE_COLORS).map(([key, color]) => (
                      <span key={key} className="inline-flex items-center gap-1 text-xs font-semibold px-1.5 py-0.5 rounded-full border"
                        style={{ color, borderColor: `${color}40`, backgroundColor: `${color}0A` }}>
                        <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
                        {dist?.[key] || 0}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="flex gap-2 px-4 py-2.5 shrink-0">
                  {[
                    { label: 'Detected', value: m?.total_detected || 0, color: '#232F3E' },
                    { label: 'Fixed', value: m?.total_remediated || 0, color: '#16a34a' },
                    { label: 'Failed', value: m?.total_failed || 0, color: '#dc2626' },
                    { label: 'Success Rate', value: `${m?.success_rate || 0}%`, color: confidenceColor(m?.success_rate || 0) },
                  ].map(tile => (
                    <div key={tile.label} className="bg-gray-50 border border-gray-200 rounded-md px-3 py-1.5 text-center flex-1">
                      <p className="text-xs font-semibold uppercase tracking-wider mb-0.5" style={{ color: '#879596' }}>{tile.label}</p>
                      <p className="text-2xl font-bold" style={{ color: tile.color }}>{tile.value}</p>
                    </div>
                  ))}
                </div>

                <div className="px-4 pb-2 shrink-0">
                  {(() => {
                    const activeEvents = (events || []).filter(e => e.state === 'detected' || e.state === 'diagnosing' || e.state === 'remediating');
                    if (activeEvents.length === 0) {
                      return (
                        <div className="flex items-center gap-2 py-1.5 px-2 rounded-md bg-gray-50 border border-gray-100">
                          <span className="w-2 h-2 rounded-full bg-gray-300 shrink-0" />
                          <span className="text-xs" style={{ color: '#879596' }}>No active issues — pipeline idle</span>
                        </div>
                      );
                    }
                    return (
                      <div className="space-y-1.5">
                        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: '#545B64' }}>Active Issues</span>
                        {activeEvents.map((e, i) => {
                          const stateFlow = ['detected', 'diagnosing', e.state].filter((v, idx, arr) => arr.indexOf(v) === idx);
                          return (
                            <div key={`active-${i}`} className="flex items-center gap-2 py-1.5 px-2 rounded-md bg-amber-50/50 border border-amber-100">
                              <span className="w-2 h-2 rounded-full bg-green-400 shrink-0 agent-dot-active" />
                              <span className="text-sm font-medium truncate" style={{ color: '#232F3E' }}>
                                {(e.issue_type || '').replace(/_/g, ' ')}
                              </span>
                              <span className="flex items-center gap-0.5 ml-auto shrink-0">
                                {stateFlow.map((st, si) => {
                                  const flowColor = { resolved: 'text-emerald-600', failed: 'text-red-600', remediating: 'text-amber-600', diagnosing: 'text-blue-600', detected: 'text-gray-500' }[st] || 'text-gray-500';
                                  const isCurrent = st === e.state;
                                  return (
                                    <React.Fragment key={si}>
                                      {si > 0 && <ChevronRightIcon className="h-2.5 w-2.5 text-gray-300" />}
                                      <span className={`text-xs ${isCurrent ? 'font-bold' : 'font-medium'} ${flowColor}`}>{st}</span>
                                    </React.Fragment>
                                  );
                                })}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    );
                  })()}
                </div>

                <div className="flex-1 overflow-hidden flex flex-col border-t border-gray-200" style={{ minHeight: 0 }}>
                  <div className="px-4 pt-2.5 pb-1.5 shrink-0 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: '#545B64' }}>Timeline</span>
                      <span className="text-xs font-medium px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-500">
                        {Math.min((events || []).length, 20)}
                      </span>
                    </div>
                    <button
                      onClick={() => setTimelineSort(prev => prev === 'newest' ? 'oldest' : 'newest')}
                      className="text-xs font-medium px-2 py-0.5 rounded border border-gray-200 hover:bg-gray-50 transition-colors"
                      style={{ color: '#545B64' }}>
                      {timelineSort === 'newest' ? 'Newest first ▼' : 'Oldest first ▲'}
                    </button>
                  </div>
                  <div className="flex-1 overflow-y-auto px-4 pb-3" style={{ minHeight: 0 }}>
                    {(!events || events.length === 0) ? (
                      <p className="text-xs py-2" style={{ color: '#879596' }}>No pipeline activity recorded</p>
                    ) : (
                      <div className="divide-y divide-gray-100">
                        {[...events]
                          .sort((a, b) => {
                            const ta = new Date(a.timestamp || 0).getTime();
                            const tb = new Date(b.timestamp || 0).getTime();
                            return timelineSort === 'newest' ? tb - ta : ta - tb;
                          })
                          .slice(0, 20).map((e, i) => {
                          const actKey = `activity-${e.timestamp || ''}-${e.issue_type || ''}-${i}`;
                          const isExp = expandedActivity === actKey;
                          const patternInfo = (patterns || []).find(p => p.type === e.issue_type);
                          const duration = e.duration || (e.state === 'resolved' ? '~2m' : e.state === 'failed' ? '~3m' : '—');
                          const stateFlow = ['detected', 'diagnosing', e.state].filter((v, idx, arr) => arr.indexOf(v) === idx);
                          const dotColor = e.state === 'resolved' ? 'bg-emerald-400' : e.state === 'failed' ? 'bg-red-400' : 'bg-amber-400';
                          const stateBadge = { resolved: 'bg-emerald-50 text-emerald-700 border-emerald-200', failed: 'bg-red-50 text-red-700 border-red-200', remediating: 'bg-amber-50 text-amber-700 border-amber-200', diagnosing: 'bg-blue-50 text-blue-700 border-blue-200', detected: 'bg-gray-50 text-gray-600 border-gray-200' }[e.state] || 'bg-gray-50 text-gray-600 border-gray-200';
                          const ts = e.timestamp ? new Date(e.timestamp) : null;
                          const dateStr = ts ? ts.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '';
                          const timeStr = ts ? ts.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }) : '';
                          return (
                            <div key={actKey}>
                              <div className={`flex items-center gap-2 px-1.5 py-2.5 cursor-pointer rounded transition-colors ${isExp ? 'bg-blue-50/40' : 'hover:bg-gray-50'}`}
                                onClick={() => setExpandedActivity(isExp ? null : actKey)}>
                                <span className={`w-2.5 h-2.5 rounded-full ${dotColor} shrink-0`} />
                                <div className="min-w-0 flex-1">
                                  <span className="text-sm font-medium truncate block" style={{ color: '#232F3E' }}>
                                    {(e.issue_type || '').replace(/_/g, ' ')}
                                  </span>
                                  {ts && (
                                    <span className="text-xs" style={{ color: '#879596' }}>{dateStr} {timeStr}</span>
                                  )}
                                </div>
                                <span className="flex items-center gap-0.5 shrink-0">
                                  {stateFlow.map((st, si) => {
                                    const flowColor = { resolved: 'text-emerald-600', failed: 'text-red-600', remediating: 'text-amber-600', diagnosing: 'text-blue-600', detected: 'text-gray-500' }[st] || 'text-gray-500';
                                    return (
                                      <React.Fragment key={si}>
                                        {si > 0 && <ChevronRightIcon className="h-2.5 w-2.5 text-gray-300" />}
                                        <span className={`text-xs font-medium ${flowColor}`}>{st}</span>
                                      </React.Fragment>
                                    );
                                  })}
                                </span>
                                <span className={`text-xs font-medium px-1.5 py-0.5 rounded border shrink-0 ${stateBadge}`}>{e.state || 'unknown'}</span>
                                <span className="text-xs font-mono shrink-0" style={{ color: '#879596' }}>{duration}</span>
                                {isExp ? <ChevronDownIcon className="h-3.5 w-3.5 text-gray-400 shrink-0" /> : <ChevronRightIcon className="h-3.5 w-3.5 text-gray-400 shrink-0" />}
                              </div>
                              {isExp && (
                                <div className="ml-5 mr-1 mb-2 p-3 rounded-md bg-gray-50 border border-gray-100">
                                  <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
                                    <div><span style={{ color: '#879596' }}>State:</span> <span className={`font-bold ${{ resolved: 'text-emerald-700', failed: 'text-red-700', remediating: 'text-amber-700', diagnosing: 'text-blue-700' }[e.state] || 'text-gray-600'}`}>{e.state || 'unknown'}</span></div>
                                    <div><span style={{ color: '#879596' }}>Issue:</span> <span className="font-semibold" style={{ color: '#232F3E' }}>{(e.issue_type || '').replace(/_/g, ' ')}</span></div>
                                    {e.cluster && <div><span style={{ color: '#879596' }}>Cluster:</span> <span className="font-semibold text-blue-600">{e.cluster}</span></div>}
                                    {e.agent && <div><span style={{ color: '#879596' }}>Agent:</span> <span className="font-semibold text-purple-600">{e.agent}</span></div>}
                                    {patternInfo && (
                                      <>
                                        <div><span style={{ color: '#879596' }}>Severity:</span> <span className={`font-bold ${{ critical: 'text-red-600', high: 'text-orange-600', medium: 'text-amber-600', low: 'text-blue-600' }[patternInfo.severity] || 'text-blue-600'}`}>{patternInfo.severity}</span></div>
                                        <div><span style={{ color: '#879596' }}>Confidence:</span> <span className="font-bold" style={{ color: '#232F3E' }}>{Math.round((patternInfo.learned_confidence || 0) * 100)}%</span></div>
                                        <div><span style={{ color: '#879596' }}>Fix:</span> <span className={`font-semibold ${patternInfo.auto_fix ? 'text-emerald-600' : 'text-gray-500'}`}>{patternInfo.auto_fix ? 'Automated' : 'Manual'}</span></div>
                                      </>
                                    )}
                                    <div><span style={{ color: '#879596' }}>Duration:</span> <span className="font-bold" style={{ color: '#232F3E' }}>{duration}</span></div>
                                    {ts && <div><span style={{ color: '#879596' }}>Time:</span> <span className="font-semibold" style={{ color: '#232F3E' }}>{ts.toLocaleString()}</span></div>}
                                  </div>
                                  {patternInfo?.description && <p className="text-xs mt-2" style={{ color: '#545B64' }}>{patternInfo.description}</p>}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* ── RIGHT: Agent Knowledge ── */}
            <div className="flex flex-col" style={{ flex: '1 1 0', minHeight: 0 }}>
              <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden flex flex-col h-full">
                <div className="px-4 py-2.5 border-b border-gray-200 bg-gray-50/50 flex items-center justify-between shrink-0">
                  <div className="flex items-center gap-2">
                    <span className="text-base font-bold uppercase tracking-wider" style={{ color: '#232F3E' }}>Agent Knowledge</span>
                    <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                      {mergedPatterns?.length || 0}
                    </span>
                  </div>
                  <div className="flex rounded-md overflow-hidden border border-gray-300">
                    <button onClick={() => setKnowledgeFilter('all')}
                      className={`text-xs font-semibold px-2.5 py-0.5 border-none cursor-pointer ${knowledgeFilter === 'all' ? 'bg-blue-500 text-white' : 'bg-white text-gray-500 hover:bg-gray-50'}`}>All</button>
                    <button onClick={() => setKnowledgeFilter('active')}
                      className={`text-xs font-semibold px-2.5 py-0.5 border-none cursor-pointer ${knowledgeFilter === 'active' ? 'bg-blue-500 text-white' : 'bg-white text-gray-500 hover:bg-gray-50'}`}
                      style={{ borderLeft: '1px solid #d1d5db' }}>Active</button>
                  </div>
                </div>

                <div className="shrink-0">
                  <div className="grid text-xs font-semibold uppercase tracking-wider px-2 py-1.5 bg-gray-50 border-b border-gray-200"
                    style={{ color: '#879596', gridTemplateColumns: '1fr 48px 60px 90px 52px' }}>
                    {[
                      { key: 'type', label: 'Pattern' },
                      { key: 'hits', label: 'Hits' },
                      { key: 'streak', label: 'Streak' },
                      { key: 'confidence', label: 'Confidence' },
                      { key: 'status', label: 'Status' },
                    ].map(col => (
                      <button key={col.key}
                        className="flex items-center gap-0.5 text-left hover:text-gray-700 transition-colors"
                        onClick={() => {
                          if (knowledgeSortKey === col.key) {
                            setKnowledgeSortDir(prev => prev === 'asc' ? 'desc' : 'asc');
                          } else {
                            setKnowledgeSortKey(col.key);
                            setKnowledgeSortDir('desc');
                          }
                        }}>
                        {col.label}
                        {knowledgeSortKey === col.key && <span className="text-[8px]">{knowledgeSortDir === 'asc' ? '▲' : '▼'}</span>}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="flex-1 overflow-y-auto" style={{ minHeight: 0 }}>
                  {(() => {
                    const filtered = (mergedPatterns || []).filter(p => knowledgeFilter === 'all' || (p.count || 0) > 0);
                    const sorted = [...filtered].sort((a, b) => {
                      const dir = knowledgeSortDir === 'asc' ? 1 : -1;
                      switch (knowledgeSortKey) {
                        case 'type': return dir * (a.type || '').localeCompare(b.type || '');
                        case 'hits': return dir * ((a.count || 0) - (b.count || 0));
                        case 'streak': return dir * (((a.consecutive_successes || 0) - (a.consecutive_failures || 0)) - ((b.consecutive_successes || 0) - (b.consecutive_failures || 0)));
                        case 'confidence': return dir * ((a.learned_confidence || 0) - (b.learned_confidence || 0));
                        case 'status': return dir * ((a.auto_fix ? 1 : 0) - (b.auto_fix ? 1 : 0));
                        default: return dir * ((a.count || 0) - (b.count || 0));
                      }
                    });

                    return sorted.length > 0 ? sorted.map(p => {
                      const isExpanded = expandedKnowledge === p.type;
                      const pct = Math.round((p.learned_confidence || 0) * 100);
                      const hasWinStreak = (p.consecutive_successes || 0) > 0;
                      const hasFailStreak = (p.consecutive_failures || 0) > 0;
                      const timeSavedPerFix = TIME_SAVED_EST[p.type] || 30;
                      const totalTimeSaved = (p.outcome_success || 0) * timeSavedPerFix;
                      const sevColor = { critical: '#dc2626', high: '#ea580c', medium: '#ca8a04', low: '#2563eb' }[p.severity] || '#2563eb';

                      return (
                        <div key={p.type} className={`border-b border-gray-100 ${isExpanded ? 'bg-blue-50/40' : 'hover:bg-gray-50'} transition-colors`}>
                          <div className="grid items-center px-2 py-2 cursor-pointer"
                            style={{ gridTemplateColumns: '1fr 48px 60px 90px 52px' }}
                            onClick={() => setExpandedKnowledge(isExpanded ? null : p.type)}>
                            <div className="flex items-center gap-1.5 min-w-0">
                              {isExpanded ? <ChevronDownIcon className="h-3 w-3 text-blue-400 shrink-0" /> : <ChevronRightIcon className="h-3 w-3 text-gray-400 shrink-0" />}
                              <span className="text-sm font-medium truncate" style={{ color: '#232F3E' }} title={p.description || p.type}>{(p.type || '').replace(/_/g, ' ')}</span>
                            </div>
                            <span className="text-xs font-bold" style={{ color: (p.count || 0) > 0 ? '#232F3E' : '#879596' }}>{p.count || 0}</span>
                            <div>
                              {hasWinStreak ? (
                                <span className="text-xs font-bold px-1.5 py-0.5 rounded border bg-emerald-50 text-emerald-700 border-emerald-200">{'↑'}{p.consecutive_successes}W</span>
                              ) : hasFailStreak ? (
                                <span className="text-xs font-bold px-1.5 py-0.5 rounded border bg-red-50 text-red-700 border-red-200">{'↓'}{p.consecutive_failures}F</span>
                              ) : (
                                <span className="text-xs" style={{ color: '#879596' }}>--</span>
                              )}
                            </div>
                            <div className="flex items-center gap-1.5">
                              <div className="flex-1 h-1.5 rounded-full bg-gray-100 overflow-hidden">
                                <div className="h-full rounded-full" style={{ width: `${Math.max(pct, 2)}%`, backgroundColor: confidenceColor(pct) }} />
                              </div>
                              <span className="text-xs font-bold w-[28px] text-right" style={{ color: confidenceColor(pct) }}>{pct}%</span>
                            </div>
                            <span className={`text-xs font-semibold px-1.5 py-0.5 rounded border ${p.auto_fix ? 'bg-emerald-50 text-emerald-600 border-emerald-200' : 'bg-gray-50 text-gray-400 border-gray-200'}`}>
                              {p.auto_fix ? 'auto' : 'manual'}
                            </span>
                          </div>

                          {isExpanded && (
                            <div className="ml-6 border-l-2 border-blue-300 p-3 mb-2 mr-2">
                              {p.description && <p className="text-xs mb-2.5 leading-relaxed" style={{ color: '#545B64' }}>{p.description}</p>}
                              {p.pattern && <p className="text-xs font-mono mb-2.5 px-2 py-1.5 rounded bg-gray-50 border border-gray-200 break-all" style={{ color: '#545B64' }}>{p.pattern}</p>}
                              <div className="grid grid-cols-3 gap-x-4 gap-y-2 text-xs">
                                <div>
                                  <span className="font-medium" style={{ color: '#879596' }}>Severity</span>
                                  <p className="font-bold" style={{ color: sevColor }}>{p.severity || 'unknown'}</p>
                                </div>
                                <div>
                                  <span className="font-medium" style={{ color: '#879596' }}>Confidence</span>
                                  <div className="flex items-center gap-1.5 mt-0.5">
                                    <div className="flex-1 h-1.5 rounded-full bg-gray-100 overflow-hidden">
                                      <div className="h-full rounded-full" style={{ width: `${Math.max(pct, 2)}%`, backgroundColor: confidenceColor(pct) }} />
                                    </div>
                                    <span className="font-bold" style={{ color: confidenceColor(pct) }}>{pct}%</span>
                                  </div>
                                </div>
                                <div>
                                  <span className="font-medium" style={{ color: '#879596' }}>Triggered</span>
                                  <p className="font-bold" style={{ color: '#232F3E' }}>{p.count || 0}x</p>
                                </div>
                                {p.first_seen && <div><span className="font-medium" style={{ color: '#879596' }}>First seen</span><p style={{ color: '#545B64' }}>{new Date(p.first_seen).toLocaleDateString()}</p></div>}
                                {p.last_seen && <div><span className="font-medium" style={{ color: '#879596' }}>Last seen</span><p style={{ color: '#545B64' }}>{new Date(p.last_seen).toLocaleDateString()}</p></div>}
                                {p.outcome_rate != null && (
                                  <div>
                                    <span className="font-medium" style={{ color: '#879596' }}>Success rate</span>
                                    <p><span className="font-bold" style={{ color: (p.outcome_rate || 0) >= 80 ? '#16a34a' : '#d97706' }}>{p.outcome_rate}%</span> <span style={{ color: '#879596' }}>({p.outcome_success || 0}W {p.outcome_failed || 0}F)</span></p>
                                  </div>
                                )}
                                <div>
                                  <span className="font-medium" style={{ color: '#879596' }}>Streak</span>
                                  <p>{hasWinStreak ? <span className="font-bold text-emerald-600">{p.consecutive_successes} wins</span> : hasFailStreak ? <span className="font-bold text-red-600">{p.consecutive_failures} fails</span> : <span style={{ color: '#879596' }}>None</span>}</p>
                                </div>
                                <div>
                                  <span className="font-medium" style={{ color: '#879596' }}>Fix type</span>
                                  <p className="font-semibold" style={{ color: p.auto_fix ? '#16a34a' : '#545B64' }}>{p.auto_fix ? 'Automated remediation' : 'Manual intervention required'}</p>
                                </div>
                                <div>
                                  <span className="font-medium" style={{ color: '#879596' }}>Time saved</span>
                                  <p className="font-bold" style={{ color: '#16a34a' }}>~{timeSavedPerFix}min/fix{totalTimeSaved > 0 ? ` (${totalTimeSaved}min total)` : ''}</p>
                                </div>
                              </div>
                              {p.adjustment_reason && (
                                <p className="text-xs mt-2.5" style={{ color: '#879596' }}>
                                  Adjustment: {p.adjustment_reason}
                                  {p.last_adjusted && <span className="ml-1">({new Date(p.last_adjusted).toLocaleString()})</span>}
                                </p>
                              )}
                              <p className="text-xs mt-2 italic" style={{ color: '#879596' }}>
                                {pct >= 80 ? 'High confidence — agent reliably resolves this pattern.'
                                  : pct >= 50 ? 'Moderate confidence — still learning, more outcomes needed.'
                                  : pct > 0 ? 'Low confidence — recent failures reduced trust. Will re-diagnose before remediating.'
                                  : 'No confidence data yet — awaiting first outcome.'}
                              </p>
                            </div>
                          )}
                        </div>
                      );
                    }) : (
                      <div className="px-4 py-6 text-center">
                        <p className="text-xs" style={{ color: '#879596' }}>No patterns loaded</p>
                      </div>
                    );
                  })()}
                </div>
              </div>
            </div>

          </div>
        )}
      </div>
    </div>
  );
};

export default AgentDashboard;
