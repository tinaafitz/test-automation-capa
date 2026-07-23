import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowPathIcon } from '@heroicons/react/24/outline';
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
    0%, 100% { box-shadow: 0 0 4px 2px rgba(34, 197, 94, 0.3); }
    50% { box-shadow: 0 0 10px 4px rgba(34, 197, 94, 0.6); }
  }
  @keyframes gradient-shift {
    0% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
  }
  @keyframes bar-fill {
    from { transform: scaleX(0); }
    to { transform: scaleX(1); }
  }
  @keyframes fade-in-up {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .aws-card {
    background: #161c28;
    border: 1px solid #2a3344;
    border-radius: 4px;
    transition: border-color 0.2s ease;
  }
  .aws-card:hover {
    border-color: #3b4a60;
  }
  .aws-card-header {
    padding: 10px 16px;
    border-bottom: 1px solid #2a3344;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .aws-card-body { padding: 10px 14px; }
  .squid-ink { background-color: #0f1419; }
  .gradient-text-gold {
    background: linear-gradient(135deg, #FF9900, #FFCC66);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
  }
  .gradient-text-cyan {
    background: linear-gradient(135deg, #00bcd4, #4dd0e1);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
  }
  .gradient-text-green {
    background: linear-gradient(135deg, #10b981, #34d399);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
  }
  .agent-dot-active { animation: pulse-glow 2s ease-in-out infinite; border-radius: 50%; }
  .bar-animate { transform-origin: left; animation: bar-fill 0.7s ease-out forwards; }
  .fade-in { animation: fade-in-up 0.4s ease-out forwards; }
  .header-accent {
    height: 2px;
    background: linear-gradient(90deg, #FF9900, #FFCC66, #FF9900);
    background-size: 200% auto;
    animation: gradient-shift 4s ease infinite;
  }
  .refresh-btn {
    background: rgba(255, 153, 0, 0.08);
    border: 1px solid rgba(255, 153, 0, 0.25);
    color: #FF9900;
    transition: all 0.2s ease;
  }
  .refresh-btn:hover {
    background: rgba(255, 153, 0, 0.15);
    border-color: rgba(255, 153, 0, 0.5);
    box-shadow: 0 0 16px rgba(255, 153, 0, 0.15);
  }
  .donut-glow { filter: drop-shadow(0 0 8px rgba(255, 153, 0, 0.25)); }
  .scrollbar-dark::-webkit-scrollbar { width: 4px; }
  .scrollbar-dark::-webkit-scrollbar-track { background: transparent; }
  .scrollbar-dark::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 4px; }
  .scrollbar-dark::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.15); }
  .stage-num {
    width: 20px; height: 20px; border-radius: 4px; display: inline-flex;
    align-items: center; justify-content: center; font-size: 11px; font-weight: 800;
  }
  .stage-title { font-size: 14px; font-weight: 800; letter-spacing: 0.05em; text-transform: uppercase; }
  .pattern-row {
    cursor: pointer;
    padding: 6px 8px;
    margin: 0 -8px;
    border-radius: 4px;
    transition: background 0.15s ease;
  }
  .pattern-row:hover { background: rgba(255,255,255,0.03); }
  .pattern-row.expanded { background: rgba(59,130,246,0.06); }
  .pattern-detail {
    overflow: hidden;
    transition: max-height 0.25s ease, opacity 0.2s ease;
  }
  .activity-row {
    border-left: 2px solid transparent;
    padding-left: 8px;
    transition: background 0.15s ease;
  }
  .activity-row:hover { background: rgba(255,255,255,0.03); border-radius: 4px; }
  .pipeline-arrow {
    color: #2a3344;
    font-size: 14px;
    display: flex;
    align-items: center;
    padding: 0 2px;
  }
  .section-toggle {
    cursor: pointer;
    padding: 4px 8px;
    margin: 0 -8px;
    border-radius: 4px;
    transition: background 0.15s ease;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .section-toggle:hover { background: rgba(255,255,255,0.03); }
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

  const DATE_RANGES = [
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
      const metricsUrl = sinceParam
        ? `/api/agents/remediation-metrics?since=${encodeURIComponent(sinceParam)}`
        : '/api/agents/remediation-metrics';
      const dashUrl = sinceParam
        ? `/api/agents/dashboard?since=${encodeURIComponent(sinceParam)}`
        : '/api/agents/dashboard';
      const [dashRes, metricsRes, confRes, kbRes, roiRes] = await Promise.all([
        fetch(buildApiUrl(dashUrl)),
        fetch(buildApiUrl(metricsUrl)),
        fetch(buildApiUrl('/api/agents/confidence')),
        fetch(buildApiUrl('/api/agents/knowledge-base')),
        fetch(buildApiUrl('/api/agents/roi')),
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
  useEffect(() => { fetchAll(); }, [dateRange]);
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

  // Donut
  const radius = 52, stroke = 12, circ = 2 * Math.PI * radius;
  let offset = 0;
  const segments = Object.entries(STATE_COLORS).map(([key, color]) => {
    const count = dist[key] || 0;
    if (count === 0 || totalStates === 0) return null;
    const dash = (count / totalStates) * circ;
    const seg = <circle key={key} cx="60" cy="60" r={radius} fill="none" stroke={color} strokeWidth={stroke}
      strokeDasharray={`${dash} ${circ - dash}`} strokeDashoffset={-offset}
      transform="rotate(-90 60 60)" strokeLinecap="round" />;
    offset += dash;
    return seg;
  });

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

  const confidenceBarGradient = (pct) => {
    if (pct >= 80) return 'linear-gradient(90deg, #10b981, #34d399)';
    if (pct >= 50) return 'linear-gradient(90deg, #eab308, #FF9900)';
    return 'linear-gradient(90deg, #ef4444, #f97316)';
  };

  const StageHeader = ({ num, label, agentKey, color }) => {
    const active = statuses[agentKey]?.status === 'active';
    return (
      <div className="aws-card-header">
        <span className="stage-num" style={{ background: `${color}20`, color, border: `1px solid ${color}40` }}>{num}</span>
        <span className="stage-title" style={{ color }}>{label}</span>
        <span className={active ? 'agent-dot-active' : ''}
          style={{ width: 7, height: 7, borderRadius: '50%', backgroundColor: active ? '#22c55e' : '#2d3748', display: 'inline-block' }} />
      </div>
    );
  };

  return (
    <div className="flex h-screen squid-ink">
      <style>{dashboardStyles}</style>
      <CapaSidebar {...sidebarHandlers} activeSection="agent-dashboard" environment="mce" />
      <div className="flex-1 flex flex-col overflow-hidden squid-ink">
        {/* Header */}
        <div className="px-5 py-2 flex items-center justify-between shrink-0"
          style={{ background: '#161c28', borderBottom: '1px solid #2a3344' }}>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2.5">
              <div style={{ width: 30, height: 30, borderRadius: 6, background: 'linear-gradient(135deg, #FF9900, #FFCC66)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <span style={{ fontSize: 13, fontWeight: 900, color: '#0f1419' }}>AI</span>
              </div>
              <h1 className="text-2xl font-bold tracking-tight" style={{ color: '#d5dbdb' }}>AI Agent Pipeline</h1>
            </div>
          </div>
          <div className="flex items-center gap-5">
            <div className="flex items-center gap-1 rounded p-0.5" style={{ background: '#1e2736' }}>
              {DATE_RANGES.map(r => (
                <button key={r.key}
                  onClick={() => { setDateRange(r.key); }}
                  className={`px-2.5 py-1 rounded text-[11px] font-semibold transition-colors ${
                    dateRange === r.key
                      ? 'text-white' : 'text-gray-500 hover:text-gray-300'
                  }`}
                  style={dateRange === r.key ? { background: '#2a3344' } : {}}>
                  {r.label}
                </button>
              ))}
            </div>
            {data?.metrics && (
              <div className="text-[10px] text-gray-500 text-right leading-tight">
                {data.metrics.earliest_event && data.metrics.latest_event && (
                  <div>Data: {new Date(data.metrics.earliest_event).toLocaleDateString()} &ndash; {new Date(data.metrics.latest_event).toLocaleDateString()}</div>
                )}
                {data.lastUpdated && (
                  <div>Refreshed: {new Date(data.lastUpdated).toLocaleTimeString()}</div>
                )}
              </div>
            )}
            <button onClick={fetchAll} disabled={loading}
              className={`refresh-btn flex items-center gap-1.5 px-4 py-1.5 rounded font-semibold text-xs ${loading ? 'opacity-50' : ''}`}>
              <ArrowPathIcon className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
              {loading ? 'Loading' : 'Refresh'}
            </button>
          </div>
        </div>
        <div className="header-accent shrink-0" />

        {data && (
          <div className="shrink-0 flex items-center justify-center gap-0 px-5 py-2" style={{ background: '#161c28', borderBottom: '1px solid #2a3344' }}>
            {[
              { label: 'Monitor', value: kb?.total_patterns || 0, unit: 'patterns', color: STAGE_COLORS.monitor },
              { label: 'Diagnose', value: totalStates, unit: 'detected', color: STAGE_COLORS.diagnose },
              { label: 'Remediate', value: m?.total_remediated || 0, unit: 'fixed', color: STAGE_COLORS.remediate },
              { label: 'Learn', value: kb?.total_outcomes || 0, unit: 'outcomes', color: STAGE_COLORS.learn },
            ].map((stage, idx) => (
              <React.Fragment key={stage.label}>
                {idx > 0 && <span className="text-lg" style={{ color: '#3b4a60', padding: '0 10px', fontWeight: 300 }}>{'\u2192'}</span>}
                <div className="flex items-center gap-2" style={{ background: `${stage.color}10`, border: `1px solid ${stage.color}20`, borderRadius: 20, padding: '4px 14px' }}>
                  <span className="text-sm font-extrabold uppercase tracking-wider" style={{ color: stage.color }}>{stage.label}</span>
                  <span className="text-base font-black" style={{ color: '#d5dbdb' }}>{stage.value}</span>
                  <span className="text-xs" style={{ color: '#5a6a7a' }}>{stage.unit}</span>
                </div>
              </React.Fragment>
            ))}
          </div>
        )}

        {error && (
          <div className="mx-4 mt-3 rounded p-2.5 text-xs shrink-0"
            style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', color: '#fca5a5' }}>
            {error}
          </div>
        )}

        {!data && !loading && !error && (
          <div className="m-5 aws-card p-8 text-center fade-in">
            <p className="text-base font-semibold gradient-text-gold">Click Refresh to load agent data</p>
          </div>
        )}

        {data && (
          <div className="flex-1 overflow-hidden fade-in flex flex-col" style={{ padding: 10, minHeight: 0 }}>
            <div className="flex flex-col flex-1 overflow-hidden" style={{ gap: 8, minHeight: 0 }}>

              {/* ── ROW 1: MONITOR + DIAGNOSE ── */}
              <div style={{ display: 'flex', gap: 8, flex: '1 1 0', minHeight: 0 }}>

                {/* 1. MONITOR — compact left panel */}
                <div className="aws-card flex flex-col" style={{ borderTopColor: STAGE_COLORS.monitor, borderTopWidth: 2, width: '38%', flexShrink: 0 }}>
                  <StageHeader num="1" label="Monitor" agentKey="monitor" color={STAGE_COLORS.monitor} />
                  <div className="aws-card-body flex flex-col flex-1 overflow-hidden">
                    <div className="flex items-center gap-3 mb-3">
                      <span className="text-5xl font-black" style={{ color: '#d5dbdb' }}>{kb?.total_patterns || 0}</span>
                      <div>
                        <p className="text-xs uppercase tracking-widest" style={{ color: '#5a6a7a' }}>patterns</p>
                        <p className="text-xs uppercase tracking-widest" style={{ color: '#5a6a7a' }}>watched</p>
                      </div>
                      <div className="flex flex-wrap gap-1.5 ml-auto">
                        <span className="text-[11px] font-semibold px-2 py-0.5 rounded" style={{ background: 'rgba(16,185,129,0.12)', border: '1px solid rgba(16,185,129,0.2)', color: '#6ee7b7' }}>
                          {kb?.auto_fix_enabled || 0} auto-fix
                        </span>
                        <span className="text-[11px] font-semibold px-2 py-0.5 rounded" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid #2a3344', color: '#6b7f8e' }}>
                          {kb?.auto_fix_disabled || 0} manual
                        </span>
                      </div>
                    </div>
                    {kb?.by_severity && (
                      <div className="flex flex-wrap gap-1.5 mb-3">
                        {Object.entries(kb.by_severity).sort(([,a],[,b]) => b - a).map(([sev, count]) => {
                          const sc = {
                            critical: { bg: 'rgba(239,68,68,0.12)', border: 'rgba(239,68,68,0.25)', text: '#fca5a5' },
                            high: { bg: 'rgba(249,115,22,0.12)', border: 'rgba(249,115,22,0.25)', text: '#fdba74' },
                            medium: { bg: 'rgba(234,179,8,0.12)', border: 'rgba(234,179,8,0.25)', text: '#fde047' },
                            low: { bg: 'rgba(59,130,246,0.12)', border: 'rgba(59,130,246,0.25)', text: '#93c5fd' },
                          }[sev] || { bg: 'rgba(59,130,246,0.12)', border: 'rgba(59,130,246,0.25)', text: '#93c5fd' };
                          return (
                            <span key={sev} className="text-[11px] font-semibold px-2 py-0.5 rounded"
                              style={{ background: sc.bg, border: `1px solid ${sc.border}`, color: sc.text }}>
                              {sev} {count}
                            </span>
                          );
                        })}
                      </div>
                    )}
                    <div className="section-toggle items-center justify-between pt-2 mb-2" style={{ borderTop: '1px solid #2a3344' }}
                      onClick={() => toggleCard('monitor-list')}>
                      <p className="text-[10px] uppercase tracking-wider flex items-center gap-1" style={{ color: '#5a6a7a' }}>
                        <span style={{ fontSize: 8 }}>{collapsedCards['monitor-list'] ? '\u25B6' : '\u25BC'}</span>
                        {showAllPatterns ? 'All Patterns' : 'In Use'}
                      </p>
                      <div className="flex rounded overflow-hidden" style={{ border: '1px solid #2a3344' }}>
                        <button onClick={() => setShowAllPatterns(true)}
                          className="text-[10px] font-semibold px-2.5 py-0.5"
                          style={{ background: showAllPatterns ? '#3b82f6' : 'transparent', color: showAllPatterns ? '#fff' : '#5a6a7a', border: 'none', cursor: 'pointer' }}>
                          All ({patterns.length})
                        </button>
                        <button onClick={() => setShowAllPatterns(false)}
                          className="text-[10px] font-semibold px-2.5 py-0.5"
                          style={{ background: !showAllPatterns ? '#3b82f6' : 'transparent', color: !showAllPatterns ? '#fff' : '#5a6a7a', border: 'none', borderLeft: '1px solid #2a3344', cursor: 'pointer' }}>
                          In Use ({topPatterns.length})
                        </button>
                      </div>
                    </div>
                    {!collapsedCards['monitor-list'] && <div className="space-y-0.5 overflow-y-auto scrollbar-dark flex-1" style={{ minHeight: 0 }}>
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
                            critical: '#fca5a5', high: '#fdba74', medium: '#fde047', low: '#93c5fd',
                          }[p.severity] || '#93c5fd';
                          return (
                            <div key={p.type}>
                              <div className={`pattern-row ${isExpanded ? 'expanded' : ''}`}
                                onClick={() => setExpandedPattern(isExpanded ? null : p.type)}>
                                <div className="flex justify-between items-center mb-0.5">
                                  <div className="flex items-center gap-1.5">
                                    <span style={{ color: '#3b82f6', fontSize: 10, opacity: 0.5 }}>{isExpanded ? '\u25BC' : '\u25B6'}</span>
                                    <span className="text-[12px]" style={{ color: '#b0bec5' }}>{p.type.replace(/_/g, ' ')}</span>
                                  </div>
                                  <div className="flex items-center gap-1.5">
                                    <span className="text-[10px] px-1.5 py-0 rounded font-semibold" style={{
                                      background: p.auto_fix ? 'rgba(16,185,129,0.10)' : 'rgba(255,255,255,0.03)',
                                      color: p.auto_fix ? '#6ee7b7' : '#4a5568',
                                      border: p.auto_fix ? '1px solid rgba(16,185,129,0.15)' : '1px solid #222d3d',
                                    }}>
                                      {p.auto_fix ? 'auto' : 'manual'}
                                    </span>
                                    <span className="text-[13px] font-bold" style={{ color: '#d5dbdb' }}>{p.count}</span>
                                  </div>
                                </div>
                                {p.count > 0 && (
                                  <div className="rounded-sm h-2 ml-4" style={{ background: '#1a2332' }}>
                                    <div className="h-full rounded-sm bar-animate" style={{ width: `${(p.count / maxCount) * 100}%`, background: 'linear-gradient(90deg, #3b82f6, #60a5fa)' }} />
                                  </div>
                                )}
                              </div>
                              {isExpanded && (
                                <div className="pattern-detail ml-5 mt-1 mb-2 pl-3" style={{ borderLeft: '2px solid #3b82f6' }}>
                                  {p.description && (
                                    <p className="text-[11px] mb-2" style={{ color: '#8899aa' }}>{p.description}</p>
                                  )}
                                  {p.pattern && (
                                    <p className="text-[10px] font-mono mb-2 px-2 py-1 rounded" style={{ color: '#6b7f8e', background: '#1a2332' }}>{p.pattern}</p>
                                  )}
                                  <div className="flex flex-wrap gap-x-4 gap-y-1">
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Severity:</span>
                                      <span className="text-[11px] font-semibold" style={{ color: sevColor }}>{p.severity || 'unknown'}</span>
                                    </div>
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Confidence:</span>
                                      <span className="text-[11px] font-bold" style={{ color: pct >= 80 ? '#22c55e' : pct >= 50 ? '#eab308' : '#ef4444' }}>{pct}%</span>
                                    </div>
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Triggered:</span>
                                      <span className="text-[11px] font-bold" style={{ color: '#d5dbdb' }}>{p.count}x</span>
                                    </div>
                                    {p.first_seen && (
                                      <div className="flex items-center gap-1">
                                        <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>First:</span>
                                        <span className="text-[11px]" style={{ color: '#8899aa' }}>{new Date(p.first_seen).toLocaleDateString()}</span>
                                      </div>
                                    )}
                                    {p.last_seen && (
                                      <div className="flex items-center gap-1">
                                        <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Last:</span>
                                        <span className="text-[11px]" style={{ color: '#8899aa' }}>{new Date(p.last_seen).toLocaleDateString()}</span>
                                      </div>
                                    )}
                                    {p.outcome_rate != null && (
                                      <div className="flex items-center gap-1">
                                        <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Success:</span>
                                        <span className="text-[11px] font-bold" style={{ color: p.outcome_rate >= 80 ? '#22c55e' : '#eab308' }}>{p.outcome_rate}%</span>
                                        <span className="text-[10px]" style={{ color: '#5a6a7a' }}>({p.outcome_success}W {p.outcome_failed}F)</span>
                                      </div>
                                    )}
                                    {p.consecutive_successes > 0 && (
                                      <div className="flex items-center gap-1">
                                        <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Streak:</span>
                                        <span className="text-[11px] font-bold" style={{ color: '#22c55e' }}>{p.consecutive_successes}W</span>
                                      </div>
                                    )}
                                    {p.consecutive_failures > 0 && (
                                      <div className="flex items-center gap-1">
                                        <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Streak:</span>
                                        <span className="text-[11px] font-bold" style={{ color: '#ef4444' }}>{p.consecutive_failures}F</span>
                                      </div>
                                    )}
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Fix:</span>
                                      <span className="text-[11px] font-semibold" style={{ color: p.auto_fix ? '#6ee7b7' : '#8899aa' }}>
                                        {p.auto_fix ? 'Automated remediation' : 'Manual intervention required'}
                                      </span>
                                    </div>
                                  </div>
                                  {pct > 0 && (
                                    <div className="mt-2">
                                      <div className="flex items-center gap-2 mb-0.5">
                                        <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Confidence</span>
                                        <span className="text-[11px] font-bold" style={{ color: '#d5dbdb' }}>{pct}%</span>
                                      </div>
                                      <div className="rounded-sm h-1.5" style={{ background: '#1a2332' }}>
                                        <div className="h-full rounded-sm" style={{ width: `${pct}%`, background: confidenceBarGradient(pct) }} />
                                      </div>
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          );
                        }) : <p className="text-xs" style={{ color: '#5a6a7a' }}>No patterns loaded</p>;
                      })()}
                    </div>}
                  </div>
                </div>

                {/* 2. DIAGNOSE — wider right panel */}
                <div className="aws-card flex flex-col" style={{ borderTopColor: STAGE_COLORS.diagnose, borderTopWidth: 2, flex: 1, minHeight: 0 }}>
                  <StageHeader num="2" label="Diagnose" agentKey="diagnostic" color={STAGE_COLORS.diagnose} />
                  <div className="aws-card-body flex flex-col flex-1 overflow-hidden">
                    <div className="flex items-center gap-4 mb-3">
                      <div className="flex items-center gap-3">
                        <span className="text-5xl font-black" style={{ color: STAGE_COLORS.diagnose }}>{totalStates}</span>
                        <div>
                          <p className="text-xs uppercase tracking-widest" style={{ color: '#5a6a7a' }}>issues</p>
                          <p className="text-xs uppercase tracking-widest" style={{ color: '#5a6a7a' }}>detected</p>
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-x-3 gap-y-1 ml-auto">
                        {Object.entries(STATE_COLORS).map(([key, color]) => (
                          <div key={key} className="text-center">
                            <p className="text-lg font-bold" style={{ color }}>{dist[key] || 0}</p>
                            <p className="text-[9px] uppercase tracking-wider" style={{ color: '#5a6a7a' }}>{key}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                    <p className="section-toggle text-[10px] uppercase tracking-wider mb-2 pt-2 shrink-0"
                      style={{ borderTop: '1px solid #2a3344', color: '#5a6a7a' }}
                      onClick={() => toggleCard('diagnose-list')}>
                      <span style={{ fontSize: 8 }}>{collapsedCards['diagnose-list'] ? '\u25B6' : '\u25BC'}</span>
                      Pattern Confidence
                    </p>
                    {!collapsedCards['diagnose-list'] && <div className="space-y-2.5 overflow-y-auto scrollbar-dark flex-1" style={{ minHeight: 0 }}>
                      {patterns.length === 0 ? (
                        <p className="text-xs py-2" style={{ color: '#5a6a7a' }}>No patterns loaded</p>
                      ) : patterns.sort((a, b) => (b.learned_confidence || 0) - (a.learned_confidence || 0)).map(p => {
                        const pct = Math.round((p.learned_confidence || 0) * 100);
                        const isExp = expandedDiagnose === p.type;
                        const triggerInfo = (kb?.most_triggered || []).find(t => t.type === p.type) || {};
                        const triggerCount = triggerInfo.count || 0;
                        const sevColor = { critical: '#fca5a5', high: '#fdba74', medium: '#fde047', low: '#93c5fd' }[p.severity] || '#93c5fd';
                        return (
                          <div key={p.type}>
                            <div className={`pattern-row ${isExp ? 'expanded' : ''}`}
                              onClick={() => setExpandedDiagnose(isExp ? null : p.type)}>
                              <div className="flex items-center justify-between mb-0.5">
                                <div className="flex items-center gap-1.5 min-w-0 flex-1">
                                  <span style={{ color: '#a855f7', fontSize: 10, opacity: 0.5 }}>{isExp ? '\u25BC' : '\u25B6'}</span>
                                  <span className="text-[12px] truncate" style={{ color: '#b0bec5' }} title={p.description}>
                                    {p.type.replace(/_/g, ' ')}
                                  </span>
                                </div>
                                <div className="flex items-center gap-1.5">
                                  <span className="text-[10px] px-1.5 py-0 rounded font-semibold" style={{
                                    background: p.auto_fix ? 'rgba(16,185,129,0.12)' : 'rgba(255,255,255,0.04)',
                                    color: p.auto_fix ? '#6ee7b7' : '#5a6a7a',
                                    border: p.auto_fix ? '1px solid rgba(16,185,129,0.2)' : '1px solid #2a3344',
                                  }}>
                                    {p.auto_fix ? 'auto' : 'manual'}
                                  </span>
                                  {p.consecutive_successes > 0 && <span className="text-[10px] font-bold" style={{ color: '#22c55e' }}>{p.consecutive_successes}W</span>}
                                  {p.consecutive_failures > 0 && <span className="text-[10px] font-bold" style={{ color: '#ef4444' }}>{p.consecutive_failures}F</span>}
                                  <span className="text-[13px] font-bold w-[36px] text-right" style={{ color: '#d5dbdb' }}>{pct}%</span>
                                </div>
                              </div>
                              <div className="rounded-sm h-2 ml-4" style={{ background: '#1a2332' }}>
                                <div className="h-full rounded-sm bar-animate" style={{ width: `${Math.max(pct, 1)}%`, background: confidenceBarGradient(pct) }} />
                              </div>
                            </div>
                            {isExp && (
                              <div className="pattern-detail ml-5 mt-1 mb-2 pl-3" style={{ borderLeft: '2px solid #a855f7' }}>
                                {p.description && <p className="text-[11px] mb-2" style={{ color: '#8899aa' }}>{p.description}</p>}
                                <div className="flex flex-wrap gap-x-4 gap-y-1">
                                  <div className="flex items-center gap-1">
                                    <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Severity:</span>
                                    <span className="text-[11px] font-semibold" style={{ color: sevColor }}>{p.severity || 'unknown'}</span>
                                  </div>
                                  <div className="flex items-center gap-1">
                                    <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Confidence:</span>
                                    <span className="text-[11px] font-bold" style={{ color: pct >= 80 ? '#22c55e' : pct >= 50 ? '#eab308' : '#ef4444' }}>{pct}%</span>
                                  </div>
                                  <div className="flex items-center gap-1">
                                    <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Triggered:</span>
                                    <span className="text-[11px] font-bold" style={{ color: '#d5dbdb' }}>{triggerCount}x</span>
                                  </div>
                                  {triggerInfo.first_seen && (
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>First:</span>
                                      <span className="text-[11px]" style={{ color: '#8899aa' }}>{new Date(triggerInfo.first_seen).toLocaleDateString()}</span>
                                    </div>
                                  )}
                                  {triggerInfo.last_seen && (
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Last:</span>
                                      <span className="text-[11px]" style={{ color: '#8899aa' }}>{new Date(triggerInfo.last_seen).toLocaleDateString()}</span>
                                    </div>
                                  )}
                                  {triggerInfo.success_rate != null && (
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Success:</span>
                                      <span className="text-[11px] font-bold" style={{ color: triggerInfo.success_rate >= 80 ? '#22c55e' : '#eab308' }}>{triggerInfo.success_rate}%</span>
                                      <span className="text-[10px]" style={{ color: '#5a6a7a' }}>({triggerInfo.success || 0}W {triggerInfo.failed || 0}F)</span>
                                    </div>
                                  )}
                                  {p.consecutive_successes > 0 && (
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Win Streak:</span>
                                      <span className="text-[11px] font-bold" style={{ color: '#22c55e' }}>{p.consecutive_successes}</span>
                                    </div>
                                  )}
                                  {p.consecutive_failures > 0 && (
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Fail Streak:</span>
                                      <span className="text-[11px] font-bold" style={{ color: '#ef4444' }}>{p.consecutive_failures}</span>
                                    </div>
                                  )}
                                  <div className="flex items-center gap-1">
                                    <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Remediation:</span>
                                    <span className="text-[11px] font-semibold" style={{ color: p.auto_fix ? '#6ee7b7' : '#8899aa' }}>
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
              <div style={{ display: 'flex', gap: 8, flex: '1 1 0', minHeight: 0 }}>

              {/* 3. REMEDIATE */}
              <div className="aws-card flex flex-col" style={{ borderTopColor: STAGE_COLORS.remediate, borderTopWidth: 2, flex: '1.4 1 0', minHeight: 0 }}>
                <StageHeader num="3" label="Remediate" agentKey="remediation" color={STAGE_COLORS.remediate} />
                <div className="aws-card-body flex-1 flex flex-col overflow-hidden">
                  <div className="shrink-0">
                    <div className="flex items-start gap-5 mb-3">
                      <div className="relative donut-glow shrink-0">
                        <svg width="160" height="160" viewBox="0 0 120 120">
                          <circle cx="60" cy="60" r={radius} fill="none" stroke="#1a2332" strokeWidth={stroke} />
                          {segments}
                        </svg>
                        <div className="absolute inset-0 flex items-center justify-center">
                          <div className="text-center">
                            <p className="text-5xl font-black gradient-text-gold">{m?.total_remediated || 0}</p>
                            <p className="text-[8px] uppercase tracking-widest" style={{ color: '#5a6a7a' }}>remediated</p>
                          </div>
                        </div>
                      </div>
                      <div className="space-y-2 flex-1">
                        <div className="flex justify-between items-baseline"><span className="text-[13px]" style={{ color: '#8899aa' }}>Detected</span><span className="text-lg font-bold" style={{ color: '#d5dbdb' }}>{m?.total_detected || 0}</span></div>
                        <div className="flex justify-between items-baseline"><span className="text-[13px]" style={{ color: '#8899aa' }}>Fixed</span><span className="text-lg font-bold" style={{ color: '#22c55e' }}>{m?.total_remediated || 0}</span></div>
                        <div className="flex justify-between items-baseline"><span className="text-[13px]" style={{ color: '#8899aa' }}>Failed</span><span className="text-lg font-bold" style={{ color: '#ef4444' }}>{m?.total_failed || 0}</span></div>
                        <div className="flex justify-between items-baseline">
                          <span className="text-[13px]" style={{ color: '#8899aa' }}>Success Rate</span>
                          <span className="text-lg font-bold" style={{ color: (m?.success_rate || 0) >= 80 ? '#22c55e' : '#eab308' }}>{m?.success_rate || 0}%</span>
                        </div>
                      </div>
                    </div>
                    <div className="rounded-sm h-3 mb-3" style={{ background: '#1a2332' }}>
                      <div className="h-full rounded-sm bar-animate" style={{
                        width: `${m?.success_rate || 0}%`,
                        background: (m?.success_rate || 0) >= 80 ? 'linear-gradient(90deg, #10b981, #34d399)' : 'linear-gradient(90deg, #eab308, #FF9900)',
                      }} />
                    </div>
                  </div>
                  {m?.by_issue_type && Object.keys(m.by_issue_type).length > 0 && (
                    <div className="pt-3 flex flex-col flex-1 overflow-hidden" style={{ borderTop: '1px solid #2a3344' }}>
                      <p className="section-toggle text-[10px] uppercase tracking-wider mb-2 shrink-0"
                        style={{ color: '#5a6a7a' }}
                        onClick={() => toggleCard('remediate-list')}>
                        <span style={{ fontSize: 8 }}>{collapsedCards['remediate-list'] ? '\u25B6' : '\u25BC'}</span>
                        By Issue Type
                      </p>
                      {!collapsedCards['remediate-list'] && <div className="space-y-0.5 overflow-y-auto scrollbar-dark flex-1" style={{ minHeight: 0 }}>
                        {Object.entries(m.by_issue_type).map(([type, info]) => {
                          const isExp = expandedRemediate === type;
                          const patternInfo = patterns.find(p => p.type === type);
                          return (
                            <div key={type}>
                              <div className={`pattern-row ${isExp ? 'expanded' : ''}`}
                                onClick={() => setExpandedRemediate(isExp ? null : type)}>
                                <div className="flex justify-between items-center mb-0.5">
                                  <div className="flex items-center gap-1.5">
                                    <span style={{ color: '#FF9900', fontSize: 10, opacity: 0.5 }}>{isExp ? '\u25BC' : '\u25B6'}</span>
                                    <span className="text-[12px]" style={{ color: '#b0bec5' }}>{type.replace(/_/g, ' ')}</span>
                                  </div>
                                  <span className="text-[12px] flex items-center gap-2" style={{ color: '#8899aa' }}>
                                    {info.latest && <span className="text-[10px]" style={{ color: '#5a6a7a' }}>{new Date(info.latest).toLocaleDateString()}</span>}
                                    <span style={{ color: '#22c55e' }}>{info.success || 0}</span>
                                    {(info.failed || 0) > 0 && <span style={{ color: '#ef4444' }}> / {info.failed}</span>}
                                  </span>
                                </div>
                                <div className="rounded-sm h-1.5 ml-4" style={{ background: '#1a2332' }}>
                                  <div className="h-full rounded-sm bar-animate" style={{
                                    width: `${info.rate || 0}%`,
                                    background: 'linear-gradient(90deg, #FF9900, #FFCC66)',
                                  }} />
                                </div>
                              </div>
                              {isExp && (
                                <div className="pattern-detail ml-5 mt-1 mb-2 pl-3" style={{ borderLeft: '2px solid #FF9900' }}>
                                  {patternInfo?.description && (
                                    <p className="text-[11px] mb-2" style={{ color: '#8899aa' }}>{patternInfo.description}</p>
                                  )}
                                  <div className="flex flex-wrap gap-x-4 gap-y-1">
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Success:</span>
                                      <span className="text-[11px] font-bold" style={{ color: '#22c55e' }}>{info.success || 0}</span>
                                    </div>
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Failed:</span>
                                      <span className="text-[11px] font-bold" style={{ color: '#ef4444' }}>{info.failed || 0}</span>
                                    </div>
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Rate:</span>
                                      <span className="text-[11px] font-bold" style={{ color: (info.rate || 0) >= 80 ? '#22c55e' : '#eab308' }}>{info.rate || 0}%</span>
                                    </div>
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Time saved:</span>
                                      <span className="text-[11px] font-bold" style={{ color: '#6ee7b7' }}>
                                        ~{(info.success || 0) * ({'rosanetwork_stuck_deletion': 45, 'cloudformation_deletion_failure': 30, 'rosaroleconfig_stuck_deletion': 15, 'api_rate_limit': 5, 'ocm_auth_failure': 15}[type] || 30)} min
                                      </span>
                                    </div>
                                    {info.earliest && (
                                      <div className="flex items-center gap-1">
                                        <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>First:</span>
                                        <span className="text-[11px]" style={{ color: '#8899aa' }}>{new Date(info.earliest).toLocaleDateString()}</span>
                                      </div>
                                    )}
                                    {info.latest && (
                                      <div className="flex items-center gap-1">
                                        <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Last:</span>
                                        <span className="text-[11px]" style={{ color: '#8899aa' }}>{new Date(info.latest).toLocaleString()}</span>
                                      </div>
                                    )}
                                    {patternInfo && (
                                      <>
                                        <div className="flex items-center gap-1">
                                          <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Fix:</span>
                                          <span className="text-[11px] font-semibold" style={{ color: patternInfo.auto_fix ? '#6ee7b7' : '#8899aa' }}>
                                            {patternInfo.auto_fix ? 'Automated' : 'Manual'}
                                          </span>
                                        </div>
                                        <div className="flex items-center gap-1">
                                          <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Confidence:</span>
                                          <span className="text-[11px] font-bold" style={{ color: '#d5dbdb' }}>{Math.round((patternInfo.learned_confidence || 0) * 100)}%</span>
                                        </div>
                                      </>
                                    )}
                                  </div>
                                  {patternInfo?.description && (
                                    <p className="text-[11px] mt-1.5" style={{ color: '#8899aa' }}>{patternInfo.description}</p>
                                  )}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>}
                    </div>
                  )}
                </div>
              </div>

              {/* 4. LEARN */}
              <div className="aws-card flex flex-col" style={{ borderTopColor: STAGE_COLORS.learn, borderTopWidth: 2, flex: '1 1 0', minHeight: 0 }}>
                <StageHeader num="4" label="Learn" agentKey="learning" color={STAGE_COLORS.learn} />
                <div className="aws-card-body flex-1 flex flex-col overflow-hidden">
                  {/* Learn Hero */}
                  <div className="flex items-center gap-3 mb-3 shrink-0">
                    <span className="text-5xl font-black" style={{ color: '#d5dbdb' }}>{kb?.total_outcomes || 0}</span>
                    <div>
                      <p className="text-xs uppercase tracking-widest" style={{ color: '#5a6a7a' }}>outcomes</p>
                      <p className="text-xs uppercase tracking-widest" style={{ color: '#5a6a7a' }}>learned</p>
                    </div>
                    <div className="flex flex-wrap gap-1.5 ml-auto">
                      <span className="text-[11px] font-semibold px-2 py-0.5 rounded" style={{ background: 'rgba(16,185,129,0.12)', border: '1px solid rgba(16,185,129,0.2)', color: '#6ee7b7' }}>
                        {m?.success_rate || 0}% success
                      </span>
                      <span className="text-[11px] font-semibold px-2 py-0.5 rounded" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid #2a3344', color: '#6b7f8e' }}>
                        {patterns.filter(p => (p.consecutive_successes || 0) > 0 || (p.consecutive_failures || 0) > 0).length} adjusted
                      </span>
                    </div>
                  </div>

                  {/* Scrollable list content */}
                  <div className="flex-1 overflow-y-auto scrollbar-dark" style={{ minHeight: 0 }}>
                  {/* Confidence Learned — what the agent learned */}
                  {patterns.length > 0 && (
                    <div className="mb-3 pb-3" style={{ borderBottom: '1px solid #2a3344' }}>
                      <p className="section-toggle text-xs font-semibold uppercase tracking-wider mb-2"
                        style={{ color: '#5a6a7a' }}
                        onClick={() => toggleCard('learn-confidence')}>
                        <span style={{ fontSize: 8 }}>{collapsedCards['learn-confidence'] ? '\u25B6' : '\u25BC'}</span>
                        Confidence Learned
                      </p>
                      {!collapsedCards['learn-confidence'] && <div className="space-y-1">
                        {patterns
                          .filter(p => (p.consecutive_successes || 0) > 0 || (p.consecutive_failures || 0) > 0 || (p.learned_confidence || 0) > 0)
                          .sort((a, b) => (b.learned_confidence || 0) - (a.learned_confidence || 0))
                          .map(p => {
                            const pct = Math.round((p.learned_confidence || 0) * 100);
                            const learnKey = `learn-${p.type}`;
                            const isExp = expandedLearn === learnKey;
                            const streak = (p.consecutive_successes || 0) > 0
                              ? { count: p.consecutive_successes, label: 'wins', color: '#22c55e', icon: '\u2191' }
                              : (p.consecutive_failures || 0) > 0
                                ? { count: p.consecutive_failures, label: 'fails', color: '#ef4444', icon: '\u2193' }
                                : null;
                            return (
                              <div key={p.type}>
                                <div className={`pattern-row ${isExp ? 'expanded' : ''}`}
                                  onClick={() => setExpandedLearn(isExp ? null : learnKey)}>
                                  <div className="flex justify-between items-center mb-0.5">
                                    <div className="flex items-center gap-1.5" style={{ maxWidth: '55%' }}>
                                      <span style={{ color: '#10b981', fontSize: 10, opacity: 0.5 }}>{isExp ? '\u25BC' : '\u25B6'}</span>
                                      <span className="text-sm truncate" style={{ color: '#b0bec5' }}>{p.type.replace(/_/g, ' ')}</span>
                                    </div>
                                    <div className="flex items-center gap-2">
                                      {streak && (
                                        <span className="text-xs font-bold" style={{ color: streak.color }}>
                                          {streak.icon}{streak.count} {streak.label}
                                        </span>
                                      )}
                                      <span className="text-sm font-bold" style={{ color: pct >= 80 ? '#22c55e' : pct >= 50 ? '#eab308' : '#ef4444' }}>{pct}%</span>
                                    </div>
                                  </div>
                                  <div className="rounded-sm h-1.5 ml-4" style={{ background: '#1a2332' }}>
                                    <div className="h-full rounded-sm bar-animate" style={{ width: `${pct}%`, background: confidenceBarGradient(pct) }} />
                                  </div>
                                </div>
                                {isExp && (() => {
                                  const triggerInfo = (kb?.most_triggered || []).find(t => t.type === p.type) || {};
                                  return (
                                  <div className="pattern-detail ml-5 mt-1 mb-2 pl-3" style={{ borderLeft: '2px solid #10b981' }}>
                                    <div className="flex flex-wrap gap-x-4 gap-y-1">
                                      <div className="flex items-center gap-1">
                                        <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Confidence:</span>
                                        <span className="text-[11px] font-bold" style={{ color: '#d5dbdb' }}>{pct}%</span>
                                      </div>
                                      {(p.consecutive_successes || 0) > 0 && (
                                        <div className="flex items-center gap-1">
                                          <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Win streak:</span>
                                          <span className="text-[11px] font-bold" style={{ color: '#22c55e' }}>{p.consecutive_successes}</span>
                                        </div>
                                      )}
                                      {(p.consecutive_failures || 0) > 0 && (
                                        <div className="flex items-center gap-1">
                                          <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Fail streak:</span>
                                          <span className="text-[11px] font-bold" style={{ color: '#ef4444' }}>{p.consecutive_failures}</span>
                                        </div>
                                      )}
                                      {triggerInfo.success_rate != null && (
                                        <div className="flex items-center gap-1">
                                          <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Success rate:</span>
                                          <span className="text-[11px] font-bold" style={{ color: triggerInfo.success_rate >= 80 ? '#22c55e' : '#eab308' }}>{triggerInfo.success_rate}%</span>
                                          <span className="text-[10px]" style={{ color: '#5a6a7a' }}>({triggerInfo.success || 0}W {triggerInfo.failed || 0}F)</span>
                                        </div>
                                      )}
                                      {triggerInfo.first_seen && (
                                        <div className="flex items-center gap-1">
                                          <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>First:</span>
                                          <span className="text-[11px]" style={{ color: '#8899aa' }}>{new Date(triggerInfo.first_seen).toLocaleDateString()}</span>
                                        </div>
                                      )}
                                      {triggerInfo.last_seen && (
                                        <div className="flex items-center gap-1">
                                          <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Last:</span>
                                          <span className="text-[11px]" style={{ color: '#8899aa' }}>{new Date(triggerInfo.last_seen).toLocaleDateString()}</span>
                                        </div>
                                      )}
                                      {p.last_adjusted && (
                                        <div className="flex items-center gap-1">
                                          <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Adjusted:</span>
                                          <span className="text-[11px]" style={{ color: '#8899aa' }}>{new Date(p.last_adjusted).toLocaleString()}</span>
                                        </div>
                                      )}
                                      <div className="flex items-center gap-1">
                                        <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Auto-fix:</span>
                                        <span className="text-[11px] font-semibold" style={{ color: p.auto_fix ? '#6ee7b7' : '#8899aa' }}>
                                          {p.auto_fix ? 'Enabled' : 'Requires review'}
                                        </span>
                                      </div>
                                    </div>
                                    {p.adjustment_reason && (
                                      <p className="text-[10px] mt-1.5" style={{ color: '#6b7f8e' }}>
                                        Reason: {p.adjustment_reason}
                                      </p>
                                    )}
                                    <p className="text-[11px] mt-1" style={{ color: '#6b7f8e' }}>
                                      {pct >= 80 ? 'High confidence — agent reliably resolves this pattern.'
                                        : pct >= 50 ? 'Moderate confidence — still learning, more outcomes needed.'
                                        : pct > 0 ? 'Low confidence — recent failures reduced trust. Will re-diagnose before remediating.'
                                        : 'No confidence data yet — awaiting first outcome.'}
                                    </p>
                                  </div>
                                  );
                                })()}
                              </div>
                            );
                          })}
                        {patterns.filter(p => (p.consecutive_successes || 0) > 0 || (p.consecutive_failures || 0) > 0 || (p.learned_confidence || 0) > 0).length === 0 && (
                          <p className="text-xs py-1" style={{ color: '#5a6a7a' }}>No confidence adjustments yet — awaiting remediation outcomes</p>
                        )}
                      </div>}
                    </div>
                  )}

                  {/* Remediation Timeline */}
                  {events.length > 0 && (
                    <div className="pt-3" style={{ borderTop: '1px solid #2a3344' }}>
                      <p className="section-toggle text-xs font-semibold uppercase tracking-wider mb-2"
                        style={{ color: '#5a6a7a' }}
                        onClick={() => toggleCard('learn-timeline')}>
                        <span style={{ fontSize: 8 }}>{collapsedCards['learn-timeline'] ? '\u25B6' : '\u25BC'}</span>
                        Remediation Timeline
                      </p>
                      {!collapsedCards['learn-timeline'] && <div className="space-y-0.5">
                        {events.slice(0, 8).map((e, i) => {
                          const actKey = `act-${i}`;
                          const isExp = expandedLearn === actKey;
                          const stateColor = STATE_COLORS[e.state] || '#2a3344';
                          const dotColor = e.state === 'resolved' ? '#22c55e' : e.state === 'failed' ? '#ef4444' : '#f97316';
                          const patternInfo = patterns.find(p => p.type === e.issue_type);
                          const duration = e.duration || (e.state === 'resolved' ? '~2m' : e.state === 'failed' ? '~3m' : '\u2014');
                          const stateFlow = ['detected', 'diagnosing', e.state].filter(Boolean);
                          return (
                            <div key={i}>
                              <div className={`pattern-row ${isExp ? 'expanded' : ''}`}
                                onClick={() => setExpandedLearn(isExp ? null : actKey)}>
                                <div className="activity-row flex items-center gap-2 text-[12px] py-0.5"
                                  style={{ borderLeftColor: stateColor }}>
                                  <span style={{ width: 7, height: 7, borderRadius: '50%', backgroundColor: dotColor, display: 'inline-block', flexShrink: 0 }} />
                                  <span className="truncate" style={{ color: '#FFCC66', flex: 1 }}>{(e.issue_type || '').replace(/_/g, ' ')}</span>
                                  <span className="flex items-center gap-0.5 shrink-0">
                                    {stateFlow.map((st, si) => (
                                      <React.Fragment key={si}>
                                        {si > 0 && <span style={{ color: '#2a3344', fontSize: 10 }}>{'\u2192'}</span>}
                                        <span className="text-[10px] font-semibold" style={{ color: STATE_COLORS[st] || '#5a6a7a' }}>{st}</span>
                                      </React.Fragment>
                                    ))}
                                  </span>
                                  <span className="text-[10px] font-mono shrink-0" style={{ color: '#5a6a7a' }}>{duration}</span>
                                </div>
                              </div>
                              {isExp && (
                                <div className="pattern-detail ml-5 mt-1 mb-2 pl-3" style={{ borderLeft: `2px solid ${stateColor}` }}>
                                  <div className="flex flex-wrap gap-x-4 gap-y-1">
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>State:</span>
                                      <span className="text-[11px] font-bold" style={{ color: stateColor }}>{e.state || 'unknown'}</span>
                                    </div>
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Issue:</span>
                                      <span className="text-[11px] font-semibold" style={{ color: '#d5dbdb' }}>{(e.issue_type || '').replace(/_/g, ' ')}</span>
                                    </div>
                                    {e.cluster && (
                                      <div className="flex items-center gap-1">
                                        <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Cluster:</span>
                                        <span className="text-[11px] font-semibold" style={{ color: '#00bcd4' }}>{e.cluster}</span>
                                      </div>
                                    )}
                                    {e.agent && (
                                      <div className="flex items-center gap-1">
                                        <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Agent:</span>
                                        <span className="text-[11px] font-semibold" style={{ color: '#a855f7' }}>{e.agent}</span>
                                      </div>
                                    )}
                                    {patternInfo && (
                                      <>
                                        <div className="flex items-center gap-1">
                                          <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Severity:</span>
                                          <span className="text-[11px] font-bold" style={{ color: { critical: '#fca5a5', high: '#fdba74', medium: '#fde047', low: '#93c5fd' }[patternInfo.severity] || '#93c5fd' }}>{patternInfo.severity}</span>
                                        </div>
                                        <div className="flex items-center gap-1">
                                          <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Confidence:</span>
                                          <span className="text-[11px] font-bold" style={{ color: '#d5dbdb' }}>{Math.round((patternInfo.learned_confidence || 0) * 100)}%</span>
                                        </div>
                                        <div className="flex items-center gap-1">
                                          <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Fix:</span>
                                          <span className="text-[11px] font-semibold" style={{ color: patternInfo.auto_fix ? '#6ee7b7' : '#8899aa' }}>
                                            {patternInfo.auto_fix ? 'Automated' : 'Manual'}
                                          </span>
                                        </div>
                                      </>
                                    )}
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] uppercase" style={{ color: '#5a6a7a' }}>Duration:</span>
                                      <span className="text-[11px] font-bold" style={{ color: '#d5dbdb' }}>{duration}</span>
                                    </div>
                                  </div>
                                  {patternInfo?.description && (
                                    <p className="text-[11px] mt-1.5" style={{ color: '#6b7f8e' }}>{patternInfo.description}</p>
                                  )}
                                  {e.timestamp && (
                                    <p className="text-[10px] mt-1" style={{ color: '#4a5568' }}>{e.timestamp}</p>
                                  )}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>}
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
