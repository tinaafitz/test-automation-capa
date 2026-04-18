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

const AgentDashboard = () => {
  const cached = _loadCache();
  const navigate = useNavigate();
  const [data, setData] = useState(cached);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchAll = async () => {
    setLoading(true);
    setError(null);
    try {
      const [dashRes, metricsRes, confRes, kbRes, roiRes] = await Promise.all([
        fetch(buildApiUrl('/api/agents/dashboard')),
        fetch(buildApiUrl('/api/agents/remediation-metrics')),
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

  // Donut math
  const radius = 38, stroke = 12, circ = 2 * Math.PI * radius;
  let offset = 0;
  const segments = Object.entries(STATE_COLORS).map(([key, color]) => {
    const count = dist[key] || 0;
    if (count === 0 || totalStates === 0) return null;
    const dash = (count / totalStates) * circ;
    const seg = <circle key={key} cx="50" cy="50" r={radius} fill="none" stroke={color} strokeWidth={stroke} strokeDasharray={`${dash} ${circ - dash}`} strokeDashoffset={-offset} transform="rotate(-90 50 50)" />;
    offset += dash;
    return seg;
  });

  // Top patterns by trigger count
  const topPatterns = (kb?.most_triggered || []).filter(p => p.count > 0);

  // Hours/mins saved
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

  return (
    <div className="flex h-screen bg-gray-50">
      <CapaSidebar {...sidebarHandlers} activeSection="agent-dashboard" environment="mce" />
      <div className="flex-1 overflow-auto" style={{ backgroundColor: '#F5F0FF' }}>
        {/* Header */}
        <div className="text-white px-6 py-4 shadow-lg flex items-center justify-between h-[72px]" style={{ background: 'linear-gradient(to right, #7C3AED, #6D28D9)' }}>
          <div>
            <h1 className="text-2xl font-bold leading-tight">AI Agent Dashboard</h1>
            {data?.lastUpdated && <p className="text-purple-200 text-xs mt-0.5">Last updated: {new Date(data.lastUpdated).toLocaleString()}</p>}
          </div>
          <button onClick={fetchAll} disabled={loading}
            className={`flex items-center gap-2 px-5 py-2 rounded-lg font-medium text-sm shadow-md transition-all ${loading ? 'bg-white/20 text-white/50' : 'bg-white text-purple-600 hover:bg-purple-50'}`}>
            <ArrowPathIcon className={`h-5 w-5 ${loading ? 'animate-spin' : ''}`} />
            {loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>

        {error && <div className="mx-6 mt-4 bg-red-50 border border-red-300 rounded-lg p-3 text-red-700 text-sm">{error}</div>}

        {!data && !loading && !error && (
          <div className="m-6 bg-purple-50 border border-purple-300 rounded-lg p-8 text-center">
            <p className="text-purple-700 text-lg font-medium">Click "Refresh" to load agent data</p>
          </div>
        )}

        {data && (
          <div className="p-4 space-y-4">
            {/* Row 1: ROI hero cards + Agent status */}
            <div className="grid grid-cols-4 gap-3">
              <div className="bg-white border-2 border-purple-200 rounded-lg p-4 shadow-sm text-center">
                <p className="text-xs text-purple-600 font-medium">Clusters Saved</p>
                <p className="text-3xl font-bold text-purple-700">{roi?.clusters_saved || 0}</p>
                <p className="text-xs text-gray-400">{roi?.total_interventions || 0} interventions</p>
              </div>
              <div className="bg-white border-2 border-purple-200 rounded-lg p-4 shadow-sm text-center">
                <p className="text-xs text-purple-600 font-medium">Time Saved</p>
                <p className="text-3xl font-bold text-purple-700">{hrs > 0 ? `${hrs}h ${mins}m` : `${mins}m`}</p>
                <p className="text-xs text-gray-400">vs manual remediation</p>
              </div>
              <div className="bg-white border-2 border-purple-200 rounded-lg p-4 shadow-sm text-center">
                <p className="text-xs text-purple-600 font-medium">Cost Avoided</p>
                <p className="text-3xl font-bold text-green-600">${(roi?.total_cost_avoided_usd || 0).toLocaleString()}</p>
                <p className="text-xs text-gray-400">orphaned resources cleaned</p>
              </div>
              <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
                <p className="text-xs text-gray-500 font-medium mb-2">Agents</p>
                <div className="grid grid-cols-2 gap-1.5">
                  {['monitor', 'diagnostic', 'remediation', 'learning'].map(a => {
                    const active = statuses[a]?.status === 'active';
                    return (
                      <div key={a} className="flex items-center gap-1.5">
                        <span className={`w-2 h-2 rounded-full ${active ? 'bg-green-500 animate-pulse' : 'bg-gray-300'}`} />
                        <span className="text-xs text-gray-700 capitalize">{a}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Row 2: Metrics + Donut + Confidence */}
            <div className="grid grid-cols-12 gap-3">
              {/* Remediation metrics */}
              <div className="col-span-3 bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
                <p className="text-sm font-semibold text-gray-700 mb-3">Remediation</p>
                <div className="space-y-2">
                  <div className="flex justify-between"><span className="text-xs text-gray-500">Detected</span><span className="text-sm font-bold">{m?.total_detected || 0}</span></div>
                  <div className="flex justify-between"><span className="text-xs text-gray-500">Remediated</span><span className="text-sm font-bold text-green-600">{m?.total_remediated || 0}</span></div>
                  <div className="flex justify-between"><span className="text-xs text-gray-500">Failed</span><span className="text-sm font-bold text-red-600">{m?.total_failed || 0}</span></div>
                  <div className="border-t border-gray-100 pt-2 flex justify-between">
                    <span className="text-xs text-gray-500">Success Rate</span>
                    <span className={`text-sm font-bold ${(m?.success_rate || 0) >= 80 ? 'text-green-600' : 'text-yellow-600'}`}>{m?.success_rate || 0}%</span>
                  </div>
                  {roi?.avg_agent_fix_seconds && (
                    <div className="flex justify-between"><span className="text-xs text-gray-500">Avg Fix Time</span><span className="text-sm font-bold">{roi.avg_agent_fix_seconds}s</span></div>
                  )}
                </div>
              </div>

              {/* Donut chart */}
              <div className="col-span-2 bg-white border border-gray-200 rounded-lg p-4 shadow-sm flex flex-col items-center justify-center">
                {totalStates > 0 ? (
                  <>
                    <div className="relative">
                      <svg width="100" height="100" viewBox="0 0 100 100">{segments}</svg>
                      <div className="absolute inset-0 flex items-center justify-center">
                        <div className="text-center"><p className="text-lg font-bold">{totalStates}</p><p className="text-[10px] text-gray-400">issues</p></div>
                      </div>
                    </div>
                    <div className="flex flex-wrap justify-center gap-x-2 gap-y-0.5 mt-2">
                      {Object.entries(STATE_COLORS).map(([key, color]) => {
                        const c = dist[key] || 0;
                        if (c === 0) return null;
                        return <div key={key} className="flex items-center gap-1"><div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} /><span className="text-[10px] text-gray-600">{key} {c}</span></div>;
                      })}
                    </div>
                  </>
                ) : (
                  <p className="text-xs text-gray-400">No issues tracked</p>
                )}
              </div>

              {/* Confidence scores */}
              <div className="col-span-7 bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
                <p className="text-sm font-semibold text-gray-700 mb-2">Pattern Confidence</p>
                <div className="space-y-1.5 max-h-[180px] overflow-y-auto">
                  {patterns.length === 0 ? (
                    <p className="text-xs text-gray-400 text-center py-4">No patterns loaded</p>
                  ) : patterns.sort((a, b) => (b.learned_confidence || 0) - (a.learned_confidence || 0)).map(p => {
                    const pct = Math.round((p.learned_confidence || 0) * 100);
                    const barColor = pct >= 80 ? 'bg-green-500' : pct >= 50 ? 'bg-yellow-400' : 'bg-red-400';
                    return (
                      <div key={p.type} className="flex items-center gap-2">
                        <span className="text-[11px] text-gray-700 min-w-[180px] truncate" title={p.description}>{p.type.replace(/_/g, ' ')}</span>
                        <div className="flex-1 bg-gray-100 rounded-full h-1.5"><div className={`h-full rounded-full ${barColor}`} style={{ width: `${pct}%` }} /></div>
                        <span className="text-[11px] font-semibold text-gray-600 w-[30px] text-right">{pct}%</span>
                        <span className={`text-[10px] px-1 py-0.5 rounded ${p.auto_fix ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                          {p.auto_fix ? 'auto' : 'manual'}
                        </span>
                        {p.consecutive_successes > 0 && <span className="text-[10px] text-green-600">{p.consecutive_successes}W</span>}
                        {p.consecutive_failures > 0 && <span className="text-[10px] text-red-600">{p.consecutive_failures}F</span>}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Row 3: KB health + Trend + Recent activity */}
            <div className="grid grid-cols-12 gap-3">
              {/* Knowledge base */}
              <div className="col-span-3 bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
                <p className="text-sm font-semibold text-gray-700 mb-2">Knowledge Base</p>
                <div className="space-y-1.5">
                  <div className="flex justify-between"><span className="text-xs text-gray-500">Patterns</span><span className="text-sm font-bold">{kb?.total_patterns || 0}</span></div>
                  <div className="flex justify-between"><span className="text-xs text-gray-500">Auto-fix</span><span className="text-sm font-bold text-green-600">{kb?.auto_fix_enabled || 0}</span></div>
                  <div className="flex justify-between"><span className="text-xs text-gray-500">Manual</span><span className="text-sm font-bold text-gray-600">{kb?.auto_fix_disabled || 0}</span></div>
                  <div className="flex justify-between"><span className="text-xs text-gray-500">Outcomes</span><span className="text-sm font-bold text-purple-600">{kb?.total_outcomes || 0}</span></div>
                </div>
                {/* Severity badges */}
                {kb?.by_severity && (
                  <div className="flex flex-wrap gap-1 mt-3">
                    {Object.entries(kb.by_severity).map(([sev, count]) => (
                      <span key={sev} className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                        sev === 'critical' ? 'bg-red-100 text-red-700' : sev === 'high' ? 'bg-orange-100 text-orange-700' : sev === 'medium' ? 'bg-yellow-100 text-yellow-700' : 'bg-blue-100 text-blue-700'
                      }`}>{sev} {count}</span>
                    ))}
                  </div>
                )}
                {/* Coverage gaps */}
                {kb?.never_triggered?.length > 0 && (
                  <div className="mt-3 pt-2 border-t border-gray-100">
                    <p className="text-[10px] text-yellow-600 font-medium">{kb.never_triggered.length} patterns never triggered</p>
                  </div>
                )}
              </div>

              {/* Trend + top triggers */}
              <div className="col-span-4 bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
                <p className="text-sm font-semibold text-gray-700 mb-2">Top Triggers & Trend</p>
                {/* Top triggered patterns */}
                {topPatterns.length > 0 && (
                  <div className="space-y-1.5 mb-3">
                    {topPatterns.slice(0, 5).map(p => {
                      const maxCount = topPatterns[0]?.count || 1;
                      return (
                        <div key={p.type} className="flex items-center gap-2">
                          <span className="text-[11px] text-gray-700 min-w-[150px] truncate">{p.type.replace(/_/g, ' ')}</span>
                          <div className="flex-1 bg-gray-100 rounded-full h-1.5"><div className="h-full rounded-full bg-purple-500" style={{ width: `${(p.count / maxCount) * 100}%` }} /></div>
                          <span className="text-[11px] font-semibold text-gray-600 w-[24px] text-right">{p.count}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
                {/* Monthly cost trend */}
                {roi?.cost_trend?.length > 0 && (
                  <div className="border-t border-gray-100 pt-2">
                    <p className="text-[10px] text-gray-400 mb-1">Monthly Cost Avoided</p>
                    {roi.cost_trend.map(ct => (
                      <div key={ct.month} className="flex items-center gap-2 mb-1">
                        <span className="text-[11px] text-gray-600 w-[50px]">{ct.month}</span>
                        <div className="flex-1 bg-gray-100 rounded-full h-2">
                          <div className="h-full rounded-full bg-green-500" style={{ width: `${Math.min((ct.cost_avoided / Math.max(...roi.cost_trend.map(c => c.cost_avoided), 1)) * 100, 100)}%` }} />
                        </div>
                        <span className="text-[11px] font-bold text-green-600 w-[45px] text-right">${ct.cost_avoided}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Recent activity */}
              <div className="col-span-5 bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
                <p className="text-sm font-semibold text-gray-700 mb-2">Recent Activity ({events.length})</p>
                {events.length === 0 ? (
                  <p className="text-xs text-gray-400 text-center py-4">No recent agent activity</p>
                ) : (
                  <div className="max-h-[180px] overflow-y-auto space-y-1.5">
                    {events.slice(0, 20).map((e, i) => (
                      <div key={i} className="flex items-center gap-2 text-[11px]">
                        <span className="text-gray-400 font-mono w-[110px] shrink-0">
                          {e.timestamp ? new Date(e.timestamp).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''}
                        </span>
                        <span className="text-purple-700 bg-purple-50 px-1 py-0.5 rounded truncate max-w-[140px]">
                          {(e.issue_type || '').replace(/_/g, ' ')}
                        </span>
                        {e.state && (
                          <span className="px-1 py-0.5 rounded text-[10px] font-medium" style={{
                            backgroundColor: STATE_COLORS[e.state] ? `${STATE_COLORS[e.state]}20` : '#f3f4f6',
                            color: STATE_COLORS[e.state] || '#6b7280',
                          }}>{e.state}</span>
                        )}
                        {e.confidence > 0 && <span className="text-gray-400 ml-auto">{Math.round(e.confidence * 100)}%</span>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Row 4: Agent vs Manual comparison (compact) */}
            {roi?.avg_agent_fix_seconds && (
              <div className="bg-white border border-gray-200 rounded-lg p-3 shadow-sm">
                <div className="flex items-center gap-6">
                  <span className="text-sm font-semibold text-gray-700">Agent vs Manual:</span>
                  <div className="flex items-center gap-2 flex-1">
                    <span className="text-xs text-gray-500 w-[50px]">Agent</span>
                    <div className="flex-1 bg-gray-100 rounded-full h-2.5"><div className="h-full rounded-full bg-green-500" style={{ width: '3%' }} /></div>
                    <span className="text-xs font-bold text-green-600 w-[40px]">{roi.avg_agent_fix_seconds}s</span>
                  </div>
                  <div className="flex items-center gap-2 flex-1">
                    <span className="text-xs text-gray-500 w-[50px]">Manual</span>
                    <div className="flex-1 bg-gray-100 rounded-full h-2.5"><div className="h-full rounded-full bg-red-500" style={{ width: '100%' }} /></div>
                    <span className="text-xs font-bold text-red-600 w-[40px]">~45m</span>
                  </div>
                  <span className="text-xs text-purple-600 font-bold">~{Math.round(2700 / roi.avg_agent_fix_seconds)}x faster</span>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default AgentDashboard;
