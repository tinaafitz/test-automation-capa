import React, { useState, useEffect } from 'react';
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
  const [expandedPattern, setExpandedPattern] = useState(null);
  const [expandedDiagnose, setExpandedDiagnose] = useState(null);
  const [expandedRemediate, setExpandedRemediate] = useState(null);
  const [expandedLearn, setExpandedLearn] = useState(null);
  const [showAllPatterns, setShowAllPatterns] = useState(true);
  const [collapsedCards, setCollapsedCards] = useState({});
  const toggleCard = (key) => setCollapsedCards(prev => ({ ...prev, [key]: !prev[key] }));
  const [dateRange, setDateRange] = useState('all');
  const [operationFilter, setOperationFilter] = useState('');
  const [remediateSortKey, setRemediateSortKey] = useState('success');
  const [remediateSortDir, setRemediateSortDir] = useState('desc');

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

  const topPatterns = (kb?.most_triggered || []).filter(p => p.count > 0);
  const hrs = Math.floor((roi?.total_manual_minutes_saved || 0) / 60);
  const mins = (roi?.total_manual_minutes_saved || 0) % 60;

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

  const StageHeader = ({ num, label, agentKey, color }) => {
    const active = statuses[agentKey]?.status === 'active';
    return (
      <div className="flex items-center gap-2.5 px-4 py-2.5 border-b border-gray-200 bg-gray-50/50">
        <span className="w-5 h-5 rounded inline-flex items-center justify-center text-[11px] font-extrabold"
          style={{ background: `${color}14`, color, border: `1px solid ${color}30` }}>{num}</span>
        <span className="text-sm font-bold uppercase tracking-wider" style={{ color: '#232F3E' }}>{label}</span>
        <span className={active ? 'agent-dot-active' : ''}
          style={{ width: 7, height: 7, borderRadius: '50%', backgroundColor: active ? '#22c55e' : '#d1d5db', display: 'inline-block' }} />
      </div>
    );
  };

  return (
    <div className="flex h-screen bg-[#F2F3F3]">
      <style>{dashboardStyles}</style>
      <CapaSidebar {...sidebarHandlers} activeSection="agent-dashboard" environment="mce" />
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* AWS-style Header */}
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
                <button key={r.key}
                  onClick={() => setOperationFilter(r.key)}
                  className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                    operationFilter === r.key
                      ? 'bg-[#37475A] text-white' : 'bg-transparent text-[#879596] hover:text-[#D5DBDB]'
                  }`}>
                  {r.label}
                </button>
              ))}
            </div>
            <div className="flex items-center rounded overflow-hidden border border-[#4A5568]">
              {DATE_RANGES.map(r => (
                <button key={r.key}
                  onClick={() => setDateRange(r.key)}
                  className={`px-2.5 py-1.5 text-xs font-medium transition-colors ${
                    dateRange === r.key
                      ? 'bg-[#37475A] text-white' : 'bg-transparent text-[#879596] hover:text-[#D5DBDB]'
                  }`}>
                  {r.label}
                </button>
              ))}
            </div>
            <button onClick={fetchAll} disabled={loading}
              className={`flex items-center gap-2 px-5 py-2 rounded font-medium text-sm transition-all ${
                loading
                  ? 'bg-[#37475A] text-[#879596] cursor-not-allowed'
                  : 'bg-[#FF9900] text-[#232F3E] hover:bg-[#EC7211] shadow-sm'
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

        {/* Pipeline Flow \u2014 Step Functions style */}
        {data && (
          <div className="bg-white border-b border-gray-200 px-6 py-3 shrink-0">
            <div className="flex items-center justify-center gap-0">
              {[
                { label: 'Monitor', value: kb?.total_patterns || 0, unit: 'patterns', color: STAGE_COLORS.monitor },
                { label: 'Diagnose', value: totalStates, unit: 'detected', color: STAGE_COLORS.diagnose },
                { label: 'Remediate', value: m?.total_remediated || 0, unit: 'fixed', color: STAGE_COLORS.remediate },
                { label: 'Learn', value: kb?.total_outcomes || 0, unit: 'outcomes', color: STAGE_COLORS.learn },
              ].map((stage, idx) => (
                <React.Fragment key={stage.label}>
                  {idx > 0 && (
                    <div className="flex items-center px-1">
                      <div className="w-8 h-px bg-gray-300" />
                      <svg width="8" height="12" viewBox="0 0 8 12" className="text-gray-300 -ml-px">
                        <path d="M1 1 L7 6 L1 11" fill="none" stroke="currentColor" strokeWidth="1.5" />
                      </svg>
                    </div>
                  )}
                  <div className="flex items-center gap-3 px-5 py-2 bg-white border border-gray-200 rounded-lg"
                    style={{ borderLeft: `3px solid ${stage.color}` }}>
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: stage.color }}>{stage.label}</p>
                      <p className="text-xs text-[#879596]">{stage.unit}</p>
                    </div>
                    <span className="text-2xl font-bold text-[#232F3E]">{stage.value}</span>
                  </div>
                </React.Fragment>
              ))}
            </div>
          </div>
        )}

        {error && (
          <div className="mx-6 mt-3 rounded-lg p-3 text-sm shrink-0 bg-red-50 border border-red-200 text-red-700">
            {error}
          </div>
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

        {data && (
          <div className="flex-1 overflow-hidden fade-in flex flex-col p-4" style={{ minHeight: 0 }}>
            <div className="flex flex-col flex-1 overflow-hidden gap-3" style={{ minHeight: 0 }}>

              {/* ── ROW 1: MONITOR + DIAGNOSE ── */}
              <div style={{ display: 'flex', gap: 12, flex: '1 1 0', minHeight: 0 }}>

                {/* 1. MONITOR — compact left panel (light theme) */}
                <div className="bg-white border border-gray-200 rounded-lg flex flex-col shadow-sm" style={{ borderLeftColor: STAGE_COLORS.monitor, borderLeftWidth: 3, width: '38%', flexShrink: 0 }}>
                  <StageHeader num="1" label="Monitor" agentKey="monitor" color={STAGE_COLORS.monitor} />
                  <div className="px-4 py-3 flex flex-col flex-1 overflow-hidden">
                    {/* Hero metric */}
                    <div className="flex items-center gap-3 mb-4">
                      <span className="text-5xl font-black" style={{ color: '#232F3E' }}>{kb?.total_patterns || 0}</span>
                      <div>
                        <p className="text-xs uppercase tracking-widest" style={{ color: '#879596' }}>patterns</p>
                        <p className="text-xs uppercase tracking-widest" style={{ color: '#879596' }}>watched</p>
                      </div>
                      <div className="flex flex-wrap gap-1.5 ml-auto">
                        <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                          {kb?.auto_fix_enabled || 0} auto-fix
                        </span>
                        <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-gray-50 text-gray-500 border border-gray-200">
                          {kb?.auto_fix_disabled || 0} manual
                        </span>
                      </div>
                    </div>
                    {/* Severity badges */}
                    {kb?.by_severity && (
                      <div className="flex flex-wrap gap-1.5 mb-4">
                        {Object.entries(kb.by_severity).sort(([,a],[,b]) => b - a).map(([sev, count]) => {
                          const sc = {
                            critical: 'bg-red-50 text-red-700 border-red-200',
                            high: 'bg-orange-50 text-orange-700 border-orange-200',
                            medium: 'bg-yellow-50 text-yellow-700 border-yellow-200',
                            low: 'bg-blue-50 text-blue-600 border-blue-200',
                          }[sev] || 'bg-blue-50 text-blue-600 border-blue-200';
                          return (
                            <span key={sev} className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${sc}`}>
                              {sev} {count}
                            </span>
                          );
                        })}
                      </div>
                    )}
                    {/* Section toggle */}
                    <div className="flex items-center justify-between pt-3 mb-2 border-t border-gray-200 cursor-pointer"
                      onClick={() => toggleCard('monitor-list')}>
                      <div className="flex items-center gap-1 text-[11px] uppercase tracking-wider font-semibold" style={{ color: '#545B64' }}>
                        {collapsedCards['monitor-list']
                          ? <ChevronRightIcon className="h-3.5 w-3.5 text-gray-400" />
                          : <ChevronDownIcon className="h-3.5 w-3.5 text-gray-400" />}
                        {showAllPatterns ? 'All Patterns' : 'In Use'}
                      </div>
                      <div className="flex rounded-md overflow-hidden border border-gray-300">
                        <button onClick={(e) => { e.stopPropagation(); setShowAllPatterns(true); }}
                          className={`text-[10px] font-semibold px-2.5 py-0.5 border-none cursor-pointer ${showAllPatterns ? 'bg-blue-500 text-white' : 'bg-white text-gray-500 hover:bg-gray-50'}`}>
                          All ({patterns.length})
                        </button>
                        <button onClick={(e) => { e.stopPropagation(); setShowAllPatterns(false); }}
                          className={`text-[10px] font-semibold px-2.5 py-0.5 border-none cursor-pointer ${!showAllPatterns ? 'bg-blue-500 text-white' : 'bg-white text-gray-500 hover:bg-gray-50'}`}
                          style={{ borderLeft: '1px solid #d1d5db' }}>
                          In Use ({topPatterns.length})
                        </button>
                      </div>
                    </div>
                    {/* Pattern list */}
                    {!collapsedCards['monitor-list'] && <div className="space-y-0.5 overflow-y-auto flex-1" style={{ minHeight: 0 }}>
                      {(() => {
                        const triggerMap = {};
                        (kb?.most_triggered || []).forEach(p => { triggerMap[p.type] = p; });
                        const allPatterns = patterns.map(p => ({
                          ...p,
                          count: triggerMap[p.type]?.count || 0,
                          first_seen: triggerMap[p.type]?.first_seen,
                          last_seen: triggerMap[p.type]?.last_seen,
                          outcome_success: triggerMap[p.type]?.success || 0,
                          outcome_failed: triggerMap[p.type]?.failed || 0,
                          outcome_rate: triggerMap[p.type]?.success_rate,
                        })).sort((a, b) => b.count - a.count)
                          .filter(p => showAllPatterns || p.count > 0);
                        const maxCount = allPatterns[0]?.count || 1;
                        return allPatterns.length > 0 ? allPatterns.map(p => {
                          const isExpanded = expandedPattern === p.type;
                          const pct = Math.round((p.learned_confidence || 0) * 100);
                          const sevColor = {
                            critical: '#dc2626', high: '#ea580c', medium: '#ca8a04', low: '#2563eb',
                          }[p.severity] || '#2563eb';
                          return (
                            <div key={p.type}>
                              <div className={`py-1.5 px-2 -mx-2 rounded cursor-pointer transition-colors ${isExpanded ? 'bg-blue-50' : 'hover:bg-gray-50'}`}
                                onClick={() => setExpandedPattern(isExpanded ? null : p.type)}>
                                <div className="flex justify-between items-center mb-0.5">
                                  <div className="flex items-center gap-1.5">
                                    {isExpanded
                                      ? <ChevronDownIcon className="h-3 w-3 text-blue-400 shrink-0" />
                                      : <ChevronRightIcon className="h-3 w-3 text-gray-400 shrink-0" />}
                                    <span className="text-[12px]" style={{ color: '#232F3E' }}>{p.type.replace(/_/g, ' ')}</span>
                                  </div>
                                  <div className="flex items-center gap-1.5">
                                    <span className={`text-[10px] px-1.5 py-0 rounded-full font-semibold border ${
                                      p.auto_fix ? 'bg-emerald-50 text-emerald-600 border-emerald-200' : 'bg-gray-50 text-gray-400 border-gray-200'
                                    }`}>
                                      {p.auto_fix ? 'auto' : 'manual'}
                                    </span>
                                    <span className="text-[13px] font-bold" style={{ color: '#232F3E' }}>{p.count}</span>
                                  </div>
                                </div>
                                {p.count > 0 && (
                                  <div className="bg-gray-100 rounded-full h-1.5 ml-5">
                                    <div className="h-full rounded-full bar-animate bg-blue-400" style={{ width: `${(p.count / maxCount) * 100}%` }} />
                                  </div>
                                )}
                              </div>
                              {isExpanded && (
                                <div className="ml-6 mt-1 mb-2 pl-3 border-l-2 border-blue-300">
                                  {p.description && (
                                    <p className="text-[11px] mb-2" style={{ color: '#545B64' }}>{p.description}</p>
                                  )}
                                  {p.pattern && (
                                    <p className="text-[10px] font-mono mb-2 px-2 py-1 rounded bg-gray-50 border border-gray-200" style={{ color: '#545B64' }}>{p.pattern}</p>
                                  )}
                                  <div className="flex flex-wrap gap-x-4 gap-y-1">
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] uppercase" style={{ color: '#879596' }}>Severity:</span>
                                      <span className="text-[11px] font-semibold" style={{ color: sevColor }}>{p.severity || 'unknown'}</span>
                                    </div>
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] uppercase" style={{ color: '#879596' }}>Confidence:</span>
                                      <span className="text-[11px] font-bold" style={{ color: pct >= 80 ? '#16a34a' : pct >= 50 ? '#ca8a04' : '#dc2626' }}>{pct}%</span>
                                    </div>
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] uppercase" style={{ color: '#879596' }}>Triggered:</span>
                                      <span className="text-[11px] font-bold" style={{ color: '#232F3E' }}>{p.count}x</span>
                                    </div>
                                    {p.first_seen && (
                                      <div className="flex items-center gap-1">
                                        <span className="text-[10px] uppercase" style={{ color: '#879596' }}>First:</span>
                                        <span className="text-[11px]" style={{ color: '#545B64' }}>{new Date(p.first_seen).toLocaleDateString()}</span>
                                      </div>
                                    )}
                                    {p.last_seen && (
                                      <div className="flex items-center gap-1">
                                        <span className="text-[10px] uppercase" style={{ color: '#879596' }}>Last:</span>
                                        <span className="text-[11px]" style={{ color: '#545B64' }}>{new Date(p.last_seen).toLocaleDateString()}</span>
                                      </div>
                                    )}
                                    {p.outcome_rate != null && (
                                      <div className="flex items-center gap-1">
                                        <span className="text-[10px] uppercase" style={{ color: '#879596' }}>Success:</span>
                                        <span className="text-[11px] font-bold" style={{ color: p.outcome_rate >= 80 ? '#16a34a' : '#ca8a04' }}>{p.outcome_rate}%</span>
                                        <span className="text-[10px]" style={{ color: '#879596' }}>({p.outcome_success}W {p.outcome_failed}F)</span>
                                      </div>
                                    )}
                                    {p.consecutive_successes > 0 && (
                                      <div className="flex items-center gap-1">
                                        <span className="text-[10px] uppercase" style={{ color: '#879596' }}>Streak:</span>
                                        <span className="text-[11px] font-bold text-green-600">{p.consecutive_successes}W</span>
                                      </div>
                                    )}
                                    {p.consecutive_failures > 0 && (
                                      <div className="flex items-center gap-1">
                                        <span className="text-[10px] uppercase" style={{ color: '#879596' }}>Streak:</span>
                                        <span className="text-[11px] font-bold text-red-600">{p.consecutive_failures}F</span>
                                      </div>
                                    )}
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] uppercase" style={{ color: '#879596' }}>Fix:</span>
                                      <span className="text-[11px] font-semibold" style={{ color: p.auto_fix ? '#16a34a' : '#545B64' }}>
                                        {p.auto_fix ? 'Automated remediation' : 'Manual intervention required'}
                                      </span>
                                    </div>
                                  </div>
                                  {pct > 0 && (
                                    <div className="mt-2">
                                      <div className="flex items-center gap-2 mb-0.5">
                                        <span className="text-[10px] uppercase" style={{ color: '#879596' }}>Confidence</span>
                                        <span className="text-[11px] font-bold" style={{ color: '#232F3E' }}>{pct}%</span>
                                      </div>
                                      <div className="bg-gray-100 rounded-full h-1.5">
                                        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: confidenceColor(pct) }} />
                                      </div>
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          );
                        }) : <p className="text-xs" style={{ color: '#879596' }}>No patterns loaded</p>;
                      })()}
                    </div>}
                  </div>
                </div>

                {/* 2. DIAGNOSE — wider right panel (light theme) */}
                <div className="bg-white border border-gray-200 rounded-lg flex flex-col shadow-sm" style={{ borderLeftColor: STAGE_COLORS.diagnose, borderLeftWidth: 3, flex: 1, minHeight: 0 }}>
                  <StageHeader num="2" label="Diagnose" agentKey="diagnostic" color={STAGE_COLORS.diagnose} />
                  <div className="px-4 py-3 flex flex-col flex-1 overflow-hidden">
                    {/* Hero metric + state distribution */}
                    <div className="flex items-center gap-4 mb-4">
                      <div className="flex items-center gap-3">
                        <span className="text-5xl font-black" style={{ color: STAGE_COLORS.diagnose }}>{totalStates}</span>
                        <div>
                          <p className="text-xs uppercase tracking-widest" style={{ color: '#879596' }}>issues</p>
                          <p className="text-xs uppercase tracking-widest" style={{ color: '#879596' }}>detected</p>
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-x-3 gap-y-1 ml-auto">
                        {Object.entries(STATE_COLORS).map(([key, color]) => (
                          <div key={key} className="text-center px-2 py-1 rounded-md bg-gray-50 border border-gray-100">
                            <p className="text-lg font-bold" style={{ color }}>{dist[key] || 0}</p>
                            <p className="text-[9px] uppercase tracking-wider" style={{ color: '#879596' }}>{key}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                    {/* Section toggle */}
                    <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider font-semibold mb-2 pt-3 shrink-0 border-t border-gray-200 cursor-pointer"
                      style={{ color: '#545B64' }}
                      onClick={() => toggleCard('diagnose-list')}>
                      {collapsedCards['diagnose-list']
                        ? <ChevronRightIcon className="h-3.5 w-3.5 text-gray-400" />
                        : <ChevronDownIcon className="h-3.5 w-3.5 text-gray-400" />}
                      Pattern Confidence
                    </div>
                    {/* Confidence list */}
                    {!collapsedCards['diagnose-list'] && <div className="space-y-1 overflow-y-auto flex-1" style={{ minHeight: 0 }}>
                      {patterns.length === 0 ? (
                        <p className="text-xs py-2" style={{ color: '#879596' }}>No patterns loaded</p>
                      ) : patterns.sort((a, b) => (b.learned_confidence || 0) - (a.learned_confidence || 0)).map(p => {
                        const pct = Math.round((p.learned_confidence || 0) * 100);
                        const isExp = expandedDiagnose === p.type;
                        const triggerInfo = (kb?.most_triggered || []).find(t => t.type === p.type) || {};
                        const triggerCount = triggerInfo.count || 0;
                        const sevColor = { critical: '#dc2626', high: '#ea580c', medium: '#ca8a04', low: '#2563eb' }[p.severity] || '#2563eb';
                        return (
                          <div key={p.type}>
                            <div className={`py-1.5 px-2 -mx-2 rounded cursor-pointer transition-colors ${isExp ? 'bg-purple-50' : 'hover:bg-gray-50'}`}
                              onClick={() => setExpandedDiagnose(isExp ? null : p.type)}>
                              <div className="flex items-center justify-between mb-0.5">
                                <div className="flex items-center gap-1.5 min-w-0 flex-1">
                                  {isExp
                                    ? <ChevronDownIcon className="h-3 w-3 text-purple-400 shrink-0" />
                                    : <ChevronRightIcon className="h-3 w-3 text-gray-400 shrink-0" />}
                                  <span className="text-[12px] truncate" style={{ color: '#232F3E' }} title={p.description}>
                                    {p.type.replace(/_/g, ' ')}
                                  </span>
                                </div>
                                <div className="flex items-center gap-1.5">
                                  <span className={`text-[10px] px-1.5 py-0 rounded-full font-semibold border ${
                                    p.auto_fix ? 'bg-emerald-50 text-emerald-600 border-emerald-200' : 'bg-gray-50 text-gray-400 border-gray-200'
                                  }`}>
                                    {p.auto_fix ? 'auto' : 'manual'}
                                  </span>
                                  {p.consecutive_successes > 0 && <span className="text-[10px] font-bold text-green-600">{p.consecutive_successes}W</span>}
                                  {p.consecutive_failures > 0 && <span className="text-[10px] font-bold text-red-600">{p.consecutive_failures}F</span>}
                                  <span className="text-[13px] font-bold w-[36px] text-right" style={{ color: '#232F3E' }}>{pct}%</span>
                                </div>
                              </div>
                              <div className="bg-gray-100 rounded-full h-1.5 ml-5">
                                <div className="h-full rounded-full bar-animate" style={{ width: `${Math.max(pct, 1)}%`, background: confidenceColor(pct) }} />
                              </div>
                            </div>
                            {isExp && (
                              <div className="ml-6 mt-1 mb-2 pl-3 border-l-2 border-purple-300">
                                {p.description && <p className="text-[11px] mb-2" style={{ color: '#545B64' }}>{p.description}</p>}
                                <div className="flex flex-wrap gap-x-4 gap-y-1">
                                  <div className="flex items-center gap-1">
                                    <span className="text-[10px] uppercase" style={{ color: '#879596' }}>Severity:</span>
                                    <span className="text-[11px] font-semibold" style={{ color: sevColor }}>{p.severity || 'unknown'}</span>
                                  </div>
                                  <div className="flex items-center gap-1">
                                    <span className="text-[10px] uppercase" style={{ color: '#879596' }}>Confidence:</span>
                                    <span className="text-[11px] font-bold" style={{ color: pct >= 80 ? '#16a34a' : pct >= 50 ? '#ca8a04' : '#dc2626' }}>{pct}%</span>
                                  </div>
                                  <div className="flex items-center gap-1">
                                    <span className="text-[10px] uppercase" style={{ color: '#879596' }}>Triggered:</span>
                                    <span className="text-[11px] font-bold" style={{ color: '#232F3E' }}>{triggerCount}x</span>
                                  </div>
                                  {triggerInfo.first_seen && (
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] uppercase" style={{ color: '#879596' }}>First:</span>
                                      <span className="text-[11px]" style={{ color: '#545B64' }}>{new Date(triggerInfo.first_seen).toLocaleDateString()}</span>
                                    </div>
                                  )}
                                  {triggerInfo.last_seen && (
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] uppercase" style={{ color: '#879596' }}>Last:</span>
                                      <span className="text-[11px]" style={{ color: '#545B64' }}>{new Date(triggerInfo.last_seen).toLocaleDateString()}</span>
                                    </div>
                                  )}
                                  {triggerInfo.success_rate != null && (
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] uppercase" style={{ color: '#879596' }}>Success:</span>
                                      <span className="text-[11px] font-bold" style={{ color: triggerInfo.success_rate >= 80 ? '#16a34a' : '#ca8a04' }}>{triggerInfo.success_rate}%</span>
                                      <span className="text-[10px]" style={{ color: '#879596' }}>({triggerInfo.success || 0}W {triggerInfo.failed || 0}F)</span>
                                    </div>
                                  )}
                                  {p.consecutive_successes > 0 && (
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] uppercase" style={{ color: '#879596' }}>Win Streak:</span>
                                      <span className="text-[11px] font-bold text-green-600">{p.consecutive_successes}</span>
                                    </div>
                                  )}
                                  {p.consecutive_failures > 0 && (
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] uppercase" style={{ color: '#879596' }}>Fail Streak:</span>
                                      <span className="text-[11px] font-bold text-red-600">{p.consecutive_failures}</span>
                                    </div>
                                  )}
                                  <div className="flex items-center gap-1">
                                    <span className="text-[10px] uppercase" style={{ color: '#879596' }}>Remediation:</span>
                                    <span className="text-[11px] font-semibold" style={{ color: p.auto_fix ? '#16a34a' : '#545B64' }}>
                                      {p.auto_fix ? 'Automated' : 'Manual'}
                                    </span>
                                  </div>
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>}
                  </div>
                </div>

              </div>


              {/* ── ROW 2: REMEDIATE + LEARN ── */}
              <div style={{ display: 'flex', gap: 12, flex: '1 1 0', minHeight: 0 }}>

              {/* 3. REMEDIATE */}
              <div className="border border-gray-200 rounded-lg bg-white flex flex-col" style={{ borderTopColor: '#FF9900', borderTopWidth: 3, flex: '1.4 1 0', minHeight: 0 }}>
                <div className="px-4 py-2.5 border-b border-gray-200 flex items-center gap-2">
                  <span className="inline-flex items-center justify-center w-5 h-5 rounded text-[11px] font-extrabold"
                    style={{ background: '#FFF3E0', color: '#FF9900', border: '1px solid #FFE0B2' }}>3</span>
                  <span className="text-sm font-extrabold uppercase tracking-wide" style={{ color: '#FF9900' }}>Remediate</span>
                  <span className={statuses.remediation?.status === 'active' ? 'agent-dot-active' : ''}
                    style={{ width: 7, height: 7, borderRadius: '50%', backgroundColor: statuses.remediation?.status === 'active' ? '#22c55e' : '#d1d5db', display: 'inline-block' }} />
                </div>
                <div className="px-4 py-3 flex-1 flex flex-col overflow-hidden">
                  {/* Stat tiles row */}
                  <div className="grid grid-cols-4 gap-3 mb-4 shrink-0">
                    {[
                      { label: 'Detected', value: m?.total_detected || 0, color: '#232F3E' },
                      { label: 'Fixed', value: m?.total_remediated || 0, color: '#16a34a' },
                      { label: 'Failed', value: m?.total_failed || 0, color: '#dc2626' },
                      { label: 'Success Rate', value: `${m?.success_rate || 0}%`, color: (m?.success_rate || 0) >= 80 ? '#16a34a' : '#d97706' },
                    ].map(tile => (
                      <div key={tile.label} className="bg-gray-50 border border-gray-200 rounded-md px-3 py-2 text-center">
                        <p className="text-[10px] font-semibold uppercase tracking-wider mb-0.5" style={{ color: '#879596' }}>{tile.label}</p>
                        <p className="text-xl font-bold" style={{ color: tile.color }}>{tile.value}</p>
                      </div>
                    ))}
                  </div>

                  {/* Success rate bar */}
                  <div className="mb-4 shrink-0">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-medium" style={{ color: '#545B64' }}>Overall Success Rate</span>
                      <span className="text-xs font-bold" style={{ color: (m?.success_rate || 0) >= 80 ? '#16a34a' : '#d97706' }}>{m?.success_rate || 0}%</span>
                    </div>
                    <div className="bg-gray-100 rounded-full h-2 overflow-hidden">
                      <div className="h-full rounded-full bar-animate" style={{
                        width: `${m?.success_rate || 0}%`,
                        backgroundColor: (m?.success_rate || 0) >= 80 ? '#16a34a' : '#d97706',
                      }} />
                    </div>
                    {/* Stacked proportion bar */}
                    {(m?.total_remediated || 0) + (m?.total_failed || 0) > 0 && (
                      <div className="flex rounded-full h-1.5 overflow-hidden mt-2">
                        <div style={{ width: `${((m?.total_remediated || 0) / ((m?.total_remediated || 0) + (m?.total_failed || 0))) * 100}%`, backgroundColor: '#16a34a' }} />
                        <div style={{ width: `${((m?.total_failed || 0) / ((m?.total_remediated || 0) + (m?.total_failed || 0))) * 100}%`, backgroundColor: '#dc2626' }} />
                      </div>
                    )}
                  </div>

                  {/* Issue type table */}
                  {m?.by_issue_type && Object.keys(m.by_issue_type).length > 0 && (
                    <div className="flex flex-col flex-1 overflow-hidden border-t border-gray-200 pt-3">
                      <div className="flex items-center justify-between mb-2 shrink-0 cursor-pointer px-1"
                        onClick={() => toggleCard('remediate-list')}>
                        <span className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: '#545B64' }}>By Issue Type</span>
                        {collapsedCards['remediate-list']
                          ? <ChevronRightIcon className="w-3.5 h-3.5" style={{ color: '#879596' }} />
                          : <ChevronDownIcon className="w-3.5 h-3.5" style={{ color: '#879596' }} />}
                      </div>
                      {!collapsedCards['remediate-list'] && (
                        <div className="flex-1 overflow-hidden flex flex-col" style={{ minHeight: 0 }}>
                          {/* Table header */}
                          <div className="grid shrink-0 text-[10px] font-semibold uppercase tracking-wider px-2 py-1.5 bg-gray-50 border-b border-gray-200 rounded-t"
                            style={{ color: '#879596', gridTemplateColumns: '1fr 52px 48px 52px 70px' }}>
                            {[
                              { key: 'type', label: 'Type' },
                              { key: 'success', label: 'Success' },
                              { key: 'failed', label: 'Failed' },
                              { key: 'rate', label: 'Rate' },
                              { key: 'latest', label: 'Last Seen' },
                            ].map(col => (
                              <button key={col.key}
                                className="flex items-center gap-0.5 text-left hover:text-gray-700 transition-colors"
                                onClick={(e) => { e.stopPropagation(); setRemediateSortKey(col.key); setRemediateSortDir(prev => remediateSortKey === col.key ? (prev === 'asc' ? 'desc' : 'asc') : 'desc'); }}>
                                {col.label}
                                {remediateSortKey === col.key && (
                                  <span className="text-[8px]">{remediateSortDir === 'asc' ? '\u25B2' : '\u25BC'}</span>
                                )}
                              </button>
                            ))}
                          </div>
                          {/* Table rows */}
                          <div className="overflow-y-auto flex-1" style={{ minHeight: 0 }}>
                            {Object.entries(m.by_issue_type)
                              .sort(([aType, aInfo], [bType, bInfo]) => {
                                const dir = remediateSortDir === 'asc' ? 1 : -1;
                                if (remediateSortKey === 'type') return dir * aType.localeCompare(bType);
                                if (remediateSortKey === 'success') return dir * ((aInfo.success || 0) - (bInfo.success || 0));
                                if (remediateSortKey === 'failed') return dir * ((aInfo.failed || 0) - (bInfo.failed || 0));
                                if (remediateSortKey === 'rate') return dir * ((aInfo.rate || 0) - (bInfo.rate || 0));
                                if (remediateSortKey === 'latest') return dir * (new Date(aInfo.latest || 0) - new Date(bInfo.latest || 0));
                                return 0;
                              })
                              .map(([type, info]) => {
                              const isExp = expandedRemediate === type;
                              const patternInfo = patterns.find(p => p.type === type);
                              const timeSavedPerFix = { rosanetwork_stuck_deletion: 45, cloudformation_deletion_failure: 30, rosaroleconfig_stuck_deletion: 15, api_rate_limit: 5, ocm_auth_failure: 15 }[type] || 30;
                              const totalTimeSaved = (info.success || 0) * timeSavedPerFix;
                              return (
                                <div key={type} className={`border-b border-gray-100 ${isExp ? 'bg-orange-50/40' : 'hover:bg-gray-50'} transition-colors`}>
                                  <div className="grid items-center px-2 py-2 cursor-pointer"
                                    style={{ gridTemplateColumns: '1fr 52px 48px 52px 70px' }}
                                    onClick={() => setExpandedRemediate(isExp ? null : type)}>
                                    <div className="flex items-center gap-1.5">
                                      {isExp
                                        ? <ChevronDownIcon className="w-3 h-3 shrink-0" style={{ color: '#FF9900' }} />
                                        : <ChevronRightIcon className="w-3 h-3 shrink-0" style={{ color: '#879596' }} />}
                                      <span className="text-xs font-medium truncate" style={{ color: '#232F3E' }}>{type.replace(/_/g, ' ')}</span>
                                    </div>
                                    <span className="text-xs font-semibold" style={{ color: '#16a34a' }}>{info.success || 0}</span>
                                    <span className="text-xs font-semibold" style={{ color: (info.failed || 0) > 0 ? '#dc2626' : '#879596' }}>{info.failed || 0}</span>
                                    <span className="text-xs font-bold" style={{ color: (info.rate || 0) >= 80 ? '#16a34a' : '#d97706' }}>{info.rate || 0}%</span>
                                    <span className="text-[10px]" style={{ color: '#879596' }}>
                                      {info.latest ? new Date(info.latest).toLocaleDateString() : '--'}
                                    </span>
                                  </div>
                                  {isExp && (
                                    <div className="px-3 pb-3 pt-1 ml-5 border-l-2" style={{ borderColor: '#FF9900' }}>
                                      {patternInfo?.description && (
                                        <p className="text-[11px] mb-2.5 leading-relaxed" style={{ color: '#545B64' }}>{patternInfo.description}</p>
                                      )}
                                      <div className="grid grid-cols-3 gap-x-4 gap-y-2 text-[11px]">
                                        <div>
                                          <span className="font-medium" style={{ color: '#879596' }}>Time saved</span>
                                          <p className="font-bold" style={{ color: '#16a34a' }}>~{totalTimeSaved} min</p>
                                        </div>
                                        {info.earliest && (
                                          <div>
                                            <span className="font-medium" style={{ color: '#879596' }}>First seen</span>
                                            <p style={{ color: '#545B64' }}>{new Date(info.earliest).toLocaleDateString()}</p>
                                          </div>
                                        )}
                                        {info.latest && (
                                          <div>
                                            <span className="font-medium" style={{ color: '#879596' }}>Last seen</span>
                                            <p style={{ color: '#545B64' }}>{new Date(info.latest).toLocaleString()}</p>
                                          </div>
                                        )}
                                        {patternInfo && (
                                          <>
                                            <div>
                                              <span className="font-medium" style={{ color: '#879596' }}>Fix type</span>
                                              <p className="font-semibold" style={{ color: patternInfo.auto_fix ? '#16a34a' : '#545B64' }}>
                                                {patternInfo.auto_fix ? 'Automated' : 'Manual'}
                                              </p>
                                            </div>
                                            <div>
                                              <span className="font-medium" style={{ color: '#879596' }}>Confidence</span>
                                              <p className="font-bold" style={{ color: '#232F3E' }}>{Math.round((patternInfo.learned_confidence || 0) * 100)}%</p>
                                            </div>
                                          </>
                                        )}
                                        <div>
                                          <span className="font-medium" style={{ color: '#879596' }}>Rate bar</span>
                                          <div className="bg-gray-100 rounded-full h-1.5 mt-1 overflow-hidden">
                                            <div className="h-full rounded-full" style={{
                                              width: `${info.rate || 0}%`,
                                              backgroundColor: (info.rate || 0) >= 80 ? '#16a34a' : '#d97706',
                                            }} />
                                          </div>
                                        </div>
                                      </div>
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* 4. LEARN — AWS Console light theme */}
              <div className="flex flex-col bg-white border border-gray-200 rounded-lg" style={{ borderTop: '3px solid #10b981', flex: '1 1 0', minHeight: 0 }}>
                {/* Stage Header */}
                <div className="px-4 py-2.5 border-b border-gray-200 flex items-center gap-2">
                  <span className="w-5 h-5 rounded inline-flex items-center justify-center text-[11px] font-extrabold bg-emerald-50 text-emerald-600 border border-emerald-200">4</span>
                  <span className="text-sm font-extrabold uppercase tracking-widest text-emerald-600">Learn</span>
                  <span className={statuses.learning?.status === 'active' ? 'agent-dot-active' : ''}
                    style={{ width: 7, height: 7, borderRadius: '50%', backgroundColor: statuses.learning?.status === 'active' ? '#10b981' : '#d1d5db', display: 'inline-block' }} />
                </div>

                <div className="flex-1 flex flex-col overflow-hidden px-4 py-3">
                  {/* Hero Stats */}
                  <div className="flex items-center gap-3 mb-4 shrink-0">
                    <span className="text-5xl font-black" style={{ color: '#232F3E' }}>{kb?.total_outcomes || 0}</span>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-widest" style={{ color: '#545B64' }}>outcomes</p>
                      <p className="text-xs font-semibold uppercase tracking-widest" style={{ color: '#545B64' }}>learned</p>
                    </div>
                    <div className="flex flex-wrap gap-1.5 ml-auto">
                      <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                        {m?.success_rate || 0}% success
                      </span>
                      <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-gray-50 text-gray-600 border border-gray-200">
                        {patterns.filter(p => (p.consecutive_successes || 0) > 0 || (p.consecutive_failures || 0) > 0).length} adjusted
                      </span>
                    </div>
                  </div>

                  {/* Scrollable list content */}
                  <div className="flex-1 overflow-y-auto" style={{ minHeight: 0 }}>

                  {/* Confidence Learned — sortable table */}
                  {patterns.length > 0 && (
                    <div className="mb-4 pb-4 border-b border-gray-100">
                      <button className="flex items-center gap-1.5 w-full text-left py-1 group"
                        onClick={() => toggleCard('learn-confidence')}>
                        {collapsedCards['learn-confidence']
                          ? <ChevronRightIcon className="h-3.5 w-3.5 text-gray-400 group-hover:text-gray-600" />
                          : <ChevronDownIcon className="h-3.5 w-3.5 text-gray-400 group-hover:text-gray-600" />}
                        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: '#545B64' }}>Confidence Learned</span>
                      </button>
                      {!collapsedCards['learn-confidence'] && (() => {
                        const learnedPatterns = patterns
                          .filter(p => (p.consecutive_successes || 0) > 0 || (p.consecutive_failures || 0) > 0 || (p.learned_confidence || 0) > 0)
                          .sort((a, b) => (b.learned_confidence || 0) - (a.learned_confidence || 0));
                        return learnedPatterns.length > 0 ? (
                          <div className="mt-2">
                            {/* Table header */}
                            <div className="grid grid-cols-[1fr_80px_90px_64px] gap-2 px-2 pb-1.5 border-b border-gray-100">
                              <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: '#879596' }}>Pattern</span>
                              <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: '#879596' }}>Streak</span>
                              <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: '#879596' }}>Confidence</span>
                              <span className="text-[10px] font-semibold uppercase tracking-wider text-right" style={{ color: '#879596' }}>Status</span>
                            </div>
                            {/* Table rows */}
                            <div className="divide-y divide-gray-50">
                              {learnedPatterns.map(p => {
                                const pct = Math.round((p.learned_confidence || 0) * 100);
                                const learnKey = `learn-${p.type}`;
                                const isExp = expandedLearn === learnKey;
                                const streak = (p.consecutive_successes || 0) > 0
                                  ? { count: p.consecutive_successes, label: 'wins', dir: 'up' }
                                  : (p.consecutive_failures || 0) > 0
                                    ? { count: p.consecutive_failures, label: 'fails', dir: 'down' }
                                    : null;
                                const confColor = pct >= 80 ? 'text-emerald-700' : pct >= 50 ? 'text-amber-700' : 'text-red-700';
                                const barBg = pct >= 80 ? 'bg-emerald-500' : pct >= 50 ? 'bg-amber-400' : 'bg-red-400';
                                return (
                                  <div key={p.type}>
                                    <div className={`grid grid-cols-[1fr_80px_90px_64px] gap-2 px-2 py-2 cursor-pointer rounded transition-colors ${isExp ? 'bg-emerald-50/50' : 'hover:bg-gray-50'}`}
                                      onClick={() => setExpandedLearn(isExp ? null : learnKey)}>
                                      <div className="flex items-center gap-1.5 min-w-0">
                                        {isExp
                                          ? <ChevronDownIcon className="h-3 w-3 text-emerald-500 shrink-0" />
                                          : <ChevronRightIcon className="h-3 w-3 text-gray-400 shrink-0" />}
                                        <span className="text-[12px] truncate" style={{ color: '#232F3E' }}>{p.type.replace(/_/g, ' ')}</span>
                                      </div>
                                      <div className="flex items-center">
                                        {streak ? (
                                          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${
                                            streak.dir === 'up'
                                              ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                                              : 'bg-red-50 text-red-700 border-red-200'
                                          }`}>
                                            {streak.dir === 'up' ? '\u2191' : '\u2193'}{streak.count} {streak.label}
                                          </span>
                                        ) : <span className="text-[10px]" style={{ color: '#879596' }}>--</span>}
                                      </div>
                                      <div className="flex items-center gap-2">
                                        <div className="flex-1 h-1.5 rounded-full bg-gray-100 overflow-hidden">
                                          <div className={`h-full rounded-full ${barBg}`} style={{ width: `${Math.max(pct, 2)}%` }} />
                                        </div>
                                        <span className={`text-[12px] font-bold w-[32px] text-right ${confColor}`}>{pct}%</span>
                                      </div>
                                      <div className="flex justify-end">
                                        <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${p.auto_fix ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-gray-50 text-gray-500 border-gray-200'}`}>
                                          {p.auto_fix ? 'auto' : 'manual'}
                                        </span>
                                      </div>
                                    </div>
                                    {isExp && (() => {
                                      const triggerInfo = (kb?.most_triggered || []).find(t => t.type === p.type) || {};
                                      return (
                                        <div className="ml-6 mr-2 mb-2 p-3 rounded-md bg-gray-50 border border-gray-100">
                                          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[11px]">
                                            <div><span style={{ color: '#879596' }}>Confidence:</span> <span className="font-bold" style={{ color: '#232F3E' }}>{pct}%</span></div>
                                            {(p.consecutive_successes || 0) > 0 && (
                                              <div><span style={{ color: '#879596' }}>Win streak:</span> <span className="font-bold text-emerald-600">{p.consecutive_successes}</span></div>
                                            )}
                                            {(p.consecutive_failures || 0) > 0 && (
                                              <div><span style={{ color: '#879596' }}>Fail streak:</span> <span className="font-bold text-red-600">{p.consecutive_failures}</span></div>
                                            )}
                                            {triggerInfo.success_rate != null && (
                                              <div><span style={{ color: '#879596' }}>Success rate:</span> <span className={`font-bold ${triggerInfo.success_rate >= 80 ? 'text-emerald-600' : 'text-amber-600'}`}>{triggerInfo.success_rate}%</span> <span style={{ color: '#879596' }}>({triggerInfo.success || 0}W {triggerInfo.failed || 0}F)</span></div>
                                            )}
                                            {triggerInfo.first_seen && (
                                              <div><span style={{ color: '#879596' }}>First seen:</span> <span style={{ color: '#545B64' }}>{new Date(triggerInfo.first_seen).toLocaleDateString()}</span></div>
                                            )}
                                            {triggerInfo.last_seen && (
                                              <div><span style={{ color: '#879596' }}>Last seen:</span> <span style={{ color: '#545B64' }}>{new Date(triggerInfo.last_seen).toLocaleDateString()}</span></div>
                                            )}
                                            {p.last_adjusted && (
                                              <div><span style={{ color: '#879596' }}>Adjusted:</span> <span style={{ color: '#545B64' }}>{new Date(p.last_adjusted).toLocaleString()}</span></div>
                                            )}
                                            <div><span style={{ color: '#879596' }}>Auto-fix:</span> <span className={`font-semibold ${p.auto_fix ? 'text-emerald-600' : 'text-gray-500'}`}>{p.auto_fix ? 'Enabled' : 'Requires review'}</span></div>
                                          </div>
                                          {p.adjustment_reason && (
                                            <p className="text-[10px] mt-2" style={{ color: '#879596' }}>Reason: {p.adjustment_reason}</p>
                                          )}
                                          <p className="text-[11px] mt-1.5 italic" style={{ color: '#879596' }}>
                                            {pct >= 80 ? 'High confidence \u2014 agent reliably resolves this pattern.'
                                              : pct >= 50 ? 'Moderate confidence \u2014 still learning, more outcomes needed.'
                                              : pct > 0 ? 'Low confidence \u2014 recent failures reduced trust. Will re-diagnose before remediating.'
                                              : 'No confidence data yet \u2014 awaiting first outcome.'}
                                          </p>
                                        </div>
                                      );
                                    })()}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        ) : (
                          <p className="text-xs py-2" style={{ color: '#879596' }}>No confidence adjustments yet \u2014 awaiting remediation outcomes</p>
                        );
                      })()}
                    </div>
                  )}

                  {/* Remediation Timeline — CloudTrail-style event list */}
                  {events.length > 0 && (
                    <div>
                      <button className="flex items-center gap-1.5 w-full text-left py-1 group"
                        onClick={() => toggleCard('learn-timeline')}>
                        {collapsedCards['learn-timeline']
                          ? <ChevronRightIcon className="h-3.5 w-3.5 text-gray-400 group-hover:text-gray-600" />
                          : <ChevronDownIcon className="h-3.5 w-3.5 text-gray-400 group-hover:text-gray-600" />}
                        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: '#545B64' }}>Remediation Timeline</span>
                        <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-500 ml-1">{Math.min(events.length, 8)}</span>
                      </button>
                      {!collapsedCards['learn-timeline'] && (
                        <div className="mt-2 divide-y divide-gray-100">
                          {events.slice(0, 8).map((e, i) => {
                            const actKey = `act-${i}`;
                            const isExp = expandedLearn === actKey;
                            const patternInfo = patterns.find(p => p.type === e.issue_type);
                            const duration = e.duration || (e.state === 'resolved' ? '~2m' : e.state === 'failed' ? '~3m' : '\u2014');
                            const stateFlow = ['detected', 'diagnosing', e.state].filter(Boolean);
                            const stateBadge = {
                              resolved: 'bg-emerald-50 text-emerald-700 border-emerald-200',
                              failed: 'bg-red-50 text-red-700 border-red-200',
                              remediating: 'bg-amber-50 text-amber-700 border-amber-200',
                              diagnosing: 'bg-blue-50 text-blue-700 border-blue-200',
                              detected: 'bg-gray-50 text-gray-600 border-gray-200',
                            }[e.state] || 'bg-gray-50 text-gray-600 border-gray-200';
                            const dotColor = e.state === 'resolved' ? 'bg-emerald-400' : e.state === 'failed' ? 'bg-red-400' : 'bg-amber-400';
                            return (
                              <div key={i}>
                                <div className={`flex items-center gap-3 px-2 py-2.5 cursor-pointer rounded transition-colors ${isExp ? 'bg-blue-50/40' : 'hover:bg-gray-50'}`}
                                  onClick={() => setExpandedLearn(isExp ? null : actKey)}>
                                  <span className={`w-2 h-2 rounded-full ${dotColor} shrink-0`} />
                                  <span className="text-[12px] font-medium truncate" style={{ color: '#232F3E', flex: 1 }}>
                                    {(e.issue_type || '').replace(/_/g, ' ')}
                                  </span>
                                  <span className="flex items-center gap-1 shrink-0">
                                    {stateFlow.map((st, si) => {
                                      const flowColor = {
                                        resolved: 'text-emerald-600', failed: 'text-red-600', remediating: 'text-amber-600',
                                        diagnosing: 'text-blue-600', detected: 'text-gray-500',
                                      }[st] || 'text-gray-500';
                                      return (
                                        <React.Fragment key={si}>
                                          {si > 0 && <ChevronRightIcon className="h-2.5 w-2.5 text-gray-300" />}
                                          <span className={`text-[10px] font-medium ${flowColor}`}>{st}</span>
                                        </React.Fragment>
                                      );
                                    })}
                                  </span>
                                  <span className={`text-[10px] font-medium px-2 py-0.5 rounded border shrink-0 ${stateBadge}`}>
                                    {e.state || 'unknown'}
                                  </span>
                                  <span className="text-[10px] font-mono shrink-0" style={{ color: '#879596' }}>{duration}</span>
                                  {isExp
                                    ? <ChevronDownIcon className="h-3 w-3 text-gray-400 shrink-0" />
                                    : <ChevronRightIcon className="h-3 w-3 text-gray-400 shrink-0" />}
                                </div>
                                {isExp && (
                                  <div className="ml-7 mr-2 mb-2 p-3 rounded-md bg-gray-50 border border-gray-100">
                                    <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[11px]">
                                      <div><span style={{ color: '#879596' }}>State:</span> <span className={`font-bold ${
                                        { resolved: 'text-emerald-700', failed: 'text-red-700', remediating: 'text-amber-700', diagnosing: 'text-blue-700' }[e.state] || 'text-gray-600'
                                      }`}>{e.state || 'unknown'}</span></div>
                                      <div><span style={{ color: '#879596' }}>Issue:</span> <span className="font-semibold" style={{ color: '#232F3E' }}>{(e.issue_type || '').replace(/_/g, ' ')}</span></div>
                                      {e.cluster && (
                                        <div><span style={{ color: '#879596' }}>Cluster:</span> <span className="font-semibold text-blue-600">{e.cluster}</span></div>
                                      )}
                                      {e.agent && (
                                        <div><span style={{ color: '#879596' }}>Agent:</span> <span className="font-semibold text-purple-600">{e.agent}</span></div>
                                      )}
                                      {patternInfo && (
                                        <>
                                          <div><span style={{ color: '#879596' }}>Severity:</span> <span className={`font-bold ${{ critical: 'text-red-600', high: 'text-orange-600', medium: 'text-amber-600', low: 'text-blue-600' }[patternInfo.severity] || 'text-blue-600'}`}>{patternInfo.severity}</span></div>
                                          <div><span style={{ color: '#879596' }}>Confidence:</span> <span className="font-bold" style={{ color: '#232F3E' }}>{Math.round((patternInfo.learned_confidence || 0) * 100)}%</span></div>
                                          <div><span style={{ color: '#879596' }}>Fix:</span> <span className={`font-semibold ${patternInfo.auto_fix ? 'text-emerald-600' : 'text-gray-500'}`}>{patternInfo.auto_fix ? 'Automated' : 'Manual'}</span></div>
                                        </>
                                      )}
                                      <div><span style={{ color: '#879596' }}>Duration:</span> <span className="font-bold" style={{ color: '#232F3E' }}>{duration}</span></div>
                                    </div>
                                    {patternInfo?.description && (
                                      <p className="text-[11px] mt-2" style={{ color: '#545B64' }}>{patternInfo.description}</p>
                                    )}
                                    {e.timestamp && (
                                      <p className="text-[10px] mt-1" style={{ color: '#879596' }}>{e.timestamp}</p>
                                    )}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  )}

                  </div>{/* end scrollable list content */}
                </div>
              </div>

              </div>{/* end ROW 2 */}

            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default AgentDashboard;
