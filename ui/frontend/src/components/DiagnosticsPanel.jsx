import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  ChevronRightIcon, ChevronDownIcon, ArrowPathIcon,
  ArrowDownTrayIcon, ClipboardDocumentIcon,
  CheckCircleIcon, ExclamationTriangleIcon, XCircleIcon,
} from '@heroicons/react/24/outline';
import { buildApiUrl, extractSafeErrorMessage } from '../config/api';

const SEV = { OK: 'ok', WARN: 'warning', ERR: 'error' };

const SEV_STYLES = {
  [SEV.OK]: 'bg-emerald-50 border-emerald-200 text-emerald-800',
  [SEV.WARN]: 'bg-amber-50 border-amber-200 text-amber-800',
  [SEV.ERR]: 'bg-red-50 border-red-200 text-red-800',
};
const SEV_ICONS = {
  [SEV.OK]: <CheckCircleIcon className="h-4 w-4 text-emerald-600" />,
  [SEV.WARN]: <ExclamationTriangleIcon className="h-4 w-4 text-amber-600" />,
  [SEV.ERR]: <XCircleIcon className="h-4 w-4 text-red-600" />,
};
const SEV_DOT = { [SEV.OK]: 'text-emerald-500', [SEV.WARN]: 'text-amber-500', [SEV.ERR]: 'text-red-500' };

const SECTIONS = {
  rosa_ocm_state: 'Cluster State', capi_resources: 'CAPI Resources',
  controller_health: 'Controller Health', controller_logs: 'Controller Logs',
  k8s_events: 'Events', aws_resources: 'AWS State',
  agent_history: 'Agent History', deletion_analysis: 'Deletion Analysis',
  node_status: 'Node Status',
};

function computeSeverity(key, s) {
  if (!s) return SEV.OK;
  if (s.error) return SEV.ERR;
  switch (key) {
    case 'rosa_ocm_state':
      return s.state === 'error' ? SEV.ERR : s.state === 'uninstalling' ? SEV.WARN : SEV.OK;
    case 'capi_resources': {
      const res = s.resources || [];
      if (res.some(r => r.ready === false && !r.deletionTimestamp)) return SEV.ERR;
      if (res.some(r => r.deletionTimestamp || r.finalizers?.length)) return SEV.WARN;
      return SEV.OK;
    }
    case 'controller_health':
      return [s.capa_controller, s.capi_controller].filter(Boolean).some(c => !c.available) ? SEV.ERR : SEV.OK;
    case 'controller_logs': {
      const n = (s.capa_errors?.length || 0) + (s.capi_errors?.length || 0);
      return n > 5 ? SEV.ERR : n > 0 ? SEV.WARN : SEV.OK;
    }
    case 'k8s_events':
      return (s.events || []).some(e => e.type === 'Warning') ? SEV.WARN : SEV.OK;
    case 'aws_resources': {
      const cf = s.cloudformation || {};
      if (cf.status === 'DELETE_FAILED' || cf.failed_resources?.length) return SEV.ERR;
      return cf.status?.includes('IN_PROGRESS') ? SEV.WARN : SEV.OK;
    }
    case 'agent_history':
      return (s.remediation_outcomes || []).length > 0 ? SEV.WARN : SEV.OK;
    case 'deletion_analysis':
      return (s.stuck_timeline || []).some(t => t.status === 'likely_stuck') ? SEV.ERR : SEV.WARN;
    case 'node_status':
      return s.ready_replicas != null && s.replicas != null && s.ready_replicas < s.replicas ? SEV.ERR : SEV.OK;
    default: return SEV.OK;
  }
}

// --- Shared helpers ---

function KVGrid({ items }) {
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
      {items.map(([k, v]) => (
        <div key={k} className="flex justify-between col-span-1">
          <dt className="font-medium text-gray-500">{k}</dt>
          <dd className="text-gray-900">{v ?? '--'}</dd>
        </div>
      ))}
    </dl>
  );
}

const BTN = 'px-3 py-1.5 text-sm font-medium rounded-lg text-gray-600 hover:bg-gray-100 transition-colors';

// --- Section renderers ---

function RenderClusterState({ data: d }) {
  if (!d) return null;
  return <KVGrid items={[['State', d.state], ['Version', d.version], ['Region', d.region],
    ['Error Code', d.error_code], ['Error', d.error_message]].filter(([, v]) => v != null)} />;
}

function RenderCapiResources({ data: d }) {
  const res = d?.resources || [];
  if (!res.length) return <p className="text-sm text-gray-500">No CAPI resources found.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>{['Type', 'Name', 'Ready', 'Deleting', 'Finalizers'].map(h =>
            <th key={h} className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">{h}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {res.map((r, i) => (
            <tr key={i}>
              <td className="px-3 py-2 font-medium text-gray-900">{r.type}</td>
              <td className="px-3 py-2 text-gray-700">{r.name}</td>
              <td className="px-3 py-2">
                {r.ready === true ? <span className="text-emerald-600 font-medium">True</span>
                  : r.ready === false ? <span className="text-red-600 font-medium">False</span>
                  : <span className="text-gray-400">--</span>}
              </td>
              <td className="px-3 py-2 text-gray-700">{r.deletionTimestamp ? 'Yes' : '--'}</td>
              <td className="px-3 py-2 text-gray-500 text-xs">{r.finalizers?.join(', ') || '--'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RenderControllerHealth({ data: d }) {
  if (!d) return null;
  return (
    <div className="flex gap-4">
      {[['CAPA Controller', d.capa_controller], ['CAPI Controller', d.capi_controller]]
        .filter(([, c]) => c).map(([label, c]) => (
          <div key={label} className={`flex-1 rounded-lg border p-3 text-sm ${c.available ? 'border-emerald-200 bg-emerald-50' : 'border-red-200 bg-red-50'}`}>
            <p className="font-medium text-gray-900">{label}</p>
            <p className="mt-1 text-gray-600">
              Replicas: {c.ready_replicas}/{c.desired_replicas}
              <span className={`ml-2 font-medium ${c.available ? 'text-emerald-700' : 'text-red-700'}`}>
                {c.available ? 'Available' : 'Unavailable'}
              </span>
            </p>
          </div>
        ))}
    </div>
  );
}

function RenderControllerLogs({ data: d }) {
  const lines = [...(d?.capa_errors || []).map(l => `[CAPA] ${l}`), ...(d?.capi_errors || []).map(l => `[CAPI] ${l}`)];
  return (
    <div className="bg-gray-900 rounded-lg p-3 font-mono text-xs max-h-48 overflow-y-auto">
      {lines.length === 0 ? <span className="text-emerald-400">No errors</span>
        : lines.map((l, i) => <div key={i} className="text-red-400 leading-5">{l}</div>)}
    </div>
  );
}

function RenderEvents({ data: d }) {
  const events = d?.events || [];
  if (!events.length) return <p className="text-sm text-gray-500">No events.</p>;
  const isWarn = t => t === 'Warning';
  return (
    <ul className="space-y-1 text-sm">
      {events.map((ev, i) => (
        <li key={i} className={`flex items-start gap-2 py-1 ${isWarn(ev.type) ? 'text-amber-700' : 'text-gray-600'}`}>
          <span className="shrink-0 text-xs text-gray-400 w-36">{ev.last_seen}</span>
          <span className={`shrink-0 text-xs font-medium px-1.5 py-0.5 rounded ${isWarn(ev.type) ? 'bg-amber-100 text-amber-700' : 'bg-gray-100 text-gray-600'}`}>{ev.type}</span>
          <span className="font-medium shrink-0">{ev.reason}</span>
          <span className="text-gray-500 truncate">{ev.message}</span>
          {ev.count > 1 && <span className="text-xs text-gray-400">x{ev.count}</span>}
        </li>
      ))}
    </ul>
  );
}

function RenderAwsResources({ data: d }) {
  if (!d) return null;
  const cf = d.cloudformation || {}, vpc = d.vpc || {}, failed = cf.failed_resources || [];
  return (
    <div className="space-y-3">
      <KVGrid items={[['Stack Name', cf.stack_name], ['Stack Status', cf.status],
        ['Status Reason', cf.status_reason], ['VPC ID', vpc.vpc_id], ['VPC CIDR', vpc.cidr]].filter(([, v]) => v != null)} />
      {failed.length > 0 && (
        <div className="border border-red-200 rounded-lg p-3 bg-red-50">
          <p className="text-sm font-medium text-red-800 mb-1">Failed Resources</p>
          <ul className="text-xs text-red-700 space-y-0.5">
            {failed.map((r, i) => <li key={i}>{typeof r === 'string' ? r : JSON.stringify(r)}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}

function RenderAgentHistory({ data: d }) {
  if (!d) return null;
  const outcomes = d.remediation_outcomes || [];
  return (
    <div className="space-y-3">
      {outcomes.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {outcomes.map((o, i) => (
            <div key={i} className="border border-gray-200 rounded-lg p-2 text-xs">
              <p className="font-medium text-gray-900">{o.issue_type || o.pattern || 'Remediation'}</p>
              <p className="text-gray-500 mt-0.5">{o.action || o.fix_type || '--'}</p>
              <p className={`mt-0.5 font-medium ${o.success ? 'text-emerald-600' : 'text-red-600'}`}>
                {o.success ? 'Success' : 'Failed'}</p>
            </div>
          ))}
        </div>
      ) : <p className="text-sm text-gray-500">No remediation outcomes.</p>}
      {(d.provision_sidecar || d.deletion_sidecar) && (
        <div className="bg-gray-900 rounded-lg p-3 font-mono text-xs max-h-36 overflow-y-auto text-gray-300">
          {d.provision_sidecar && <div className="mb-2"><span className="text-emerald-400">--- Provision Sidecar ---</span><br />{d.provision_sidecar}</div>}
          {d.deletion_sidecar && <div><span className="text-amber-400">--- Deletion Sidecar ---</span><br />{d.deletion_sidecar}</div>}
        </div>
      )}
    </div>
  );
}

function RenderDeletionAnalysis({ data: d }) {
  if (!d) return null;
  const deps = d.vpc_dependencies || {};
  return (
    <div className="space-y-3">
      {d.ocm_state && (
        <div className="flex items-center gap-2 text-sm">
          <span className="font-medium text-gray-500">OCM State:</span>
          <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-700">{d.ocm_state}</span>
        </div>
      )}
      {d.finalizers?.length > 0 && (
        <div>
          <p className="text-xs font-medium text-gray-500 mb-1">Finalizers</p>
          <ul className="text-xs text-gray-700 space-y-0.5">
            {d.finalizers.map((f, i) => <li key={i} className="font-mono">{typeof f === 'string' ? f : `${f.resource}: ${f.finalizer}`}</li>)}
          </ul>
        </div>
      )}
      {(deps.endpoints || deps.enis || deps.security_groups) && (
        <table className="min-w-full divide-y divide-gray-200 text-xs">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-3 py-2 text-left font-medium text-gray-500 uppercase">Dependency</th>
              <th className="px-3 py-2 text-left font-medium text-gray-500 uppercase">Count</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {[['VPC Endpoints', deps.endpoints], ['ENIs', deps.enis], ['Security Groups', deps.security_groups]]
              .filter(([, v]) => v != null).map(([label, val]) => (
                <tr key={label}>
                  <td className="px-3 py-2 text-gray-700">{label}</td>
                  <td className="px-3 py-2 font-medium text-gray-900">{Array.isArray(val) ? val.length : val}</td>
                </tr>
              ))}
          </tbody>
        </table>
      )}
      {d.stuck_timeline?.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-gray-500">Stuck Timeline</p>
          {d.stuck_timeline.map((t, i) => (
            <div key={i} className="flex items-center gap-2 text-xs">
              <span className={`w-2 h-2 rounded-full ${t.status === 'likely_stuck' ? 'bg-red-500' : 'bg-amber-400'}`} />
              <span className="text-gray-500 w-28 shrink-0">{t.timestamp || t.time}</span>
              <span className="text-gray-700">{t.message || t.description || t.status}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function RenderNodeStatus({ data: d }) {
  if (!d) return null;
  return (
    <div className="flex gap-6 text-sm">
      {[['Replicas', d.replicas], ['Ready', d.ready_replicas], ['Available', d.available_replicas]].map(([l, v]) => (
        <div key={l}><span className="text-gray-500">{l}: </span><span className="font-medium text-gray-900">{v ?? '--'}</span></div>
      ))}
    </div>
  );
}

const RENDERERS = {
  rosa_ocm_state: RenderClusterState, capi_resources: RenderCapiResources,
  controller_health: RenderControllerHealth, controller_logs: RenderControllerLogs,
  k8s_events: RenderEvents, aws_resources: RenderAwsResources,
  agent_history: RenderAgentHistory, deletion_analysis: RenderDeletionAnalysis,
  node_status: RenderNodeStatus,
};

// --- Main component ---

const DiagnosticsPanel = ({ clusterName, isRunning = false, autoRefresh = true }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(false);
  const [expandedSections, setExpandedSections] = useState(new Set());
  const [copied, setCopied] = useState(false);
  const intervalRef = useRef(null);
  const hasAutoExpanded = useRef(false);

  const fetchData = useCallback(async () => {
    if (!clusterName) return;
    setLoading(true);
    try {
      const resp = await fetch(buildApiUrl(`/api/clusters/${clusterName}/must-gather`));
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const result = await resp.json();
      setData(result);
      setError(null);
      if (!hasAutoExpanded.current && result.sections) {
        const hasErr = Object.entries(result.sections).some(
          ([k, s]) => computeSeverity(k, s) === SEV.ERR
        );
        if (hasErr) { setExpanded(true); hasAutoExpanded.current = true; }
      }
    } catch (err) {
      setError(extractSafeErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [clusterName]);

  useEffect(() => { fetchData(); return () => clearInterval(intervalRef.current); }, [fetchData]);

  useEffect(() => {
    clearInterval(intervalRef.current);
    if (isRunning && autoRefresh) intervalRef.current = setInterval(fetchData, 30000);
    return () => clearInterval(intervalRef.current);
  }, [isRunning, autoRefresh, fetchData]);

  const handleDownload = async () => {
    try {
      const resp = await fetch(buildApiUrl(`/api/clusters/${clusterName}/must-gather?download=true`));
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `must-gather-${clusterName}-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) { console.error('Download failed:', err); }
  };

  const handleCopy = async () => {
    if (!data) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(data, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) { console.error('Copy failed:', err); }
  };

  const toggleSection = (key) => {
    setExpandedSections(prev => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  };

  // Compute severity summary
  const counts = { [SEV.OK]: 0, [SEV.WARN]: 0, [SEV.ERR]: 0 };
  const sevMap = {};
  if (data?.sections) {
    for (const key of Object.keys(SECTIONS)) {
      if (key === 'deletion_analysis' && !data.sections[key]) continue;
      const sev = computeSeverity(key, data.sections[key]);
      sevMap[key] = sev;
      counts[sev]++;
    }
  }
  const hasErrors = counts[SEV.ERR] > 0;
  const headerBg = hasErrors ? 'bg-red-50 border-red-200' : 'bg-gray-50 border-gray-200';

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100">
      <button onClick={() => setExpanded(!expanded)}
        className={`w-full flex items-center justify-between px-4 py-3 rounded-lg border ${headerBg} transition-colors`}>
        <div className="flex items-center gap-2">
          {expanded ? <ChevronDownIcon className="h-4 w-4 text-gray-500" /> : <ChevronRightIcon className="h-4 w-4 text-gray-500" />}
          <span className="text-sm font-semibold text-gray-900">Cluster Diagnostics</span>
          {loading && <ArrowPathIcon className="h-4 w-4 text-gray-400 animate-spin" />}
        </div>
        {data && (
          <div className="flex items-center gap-3 text-xs font-medium">
            {counts[SEV.OK] > 0 && <span className={SEV_DOT[SEV.OK]}>&#9679; {counts[SEV.OK]} OK</span>}
            {counts[SEV.WARN] > 0 && <span className={SEV_DOT[SEV.WARN]}>&#9679; {counts[SEV.WARN]} Warning</span>}
            {counts[SEV.ERR] > 0 && <span className={SEV_DOT[SEV.ERR]}>&#9679; {counts[SEV.ERR]} Error</span>}
          </div>
        )}
        <div className="flex items-center gap-1.5" onClick={e => e.stopPropagation()}>
          {error && <span className="text-xs text-red-600 mr-2">{error}</span>}
          {!isRunning && <button onClick={fetchData} className={BTN} title="Refresh"><ArrowPathIcon className="h-4 w-4" /></button>}
          <button onClick={handleDownload} className={BTN} title="Download Report"><ArrowDownTrayIcon className="h-4 w-4" /></button>
          <button onClick={handleCopy} className={BTN} title={copied ? 'Copied!' : 'Copy'}>
            {copied ? <CheckCircleIcon className="h-4 w-4 text-emerald-500" /> : <ClipboardDocumentIcon className="h-4 w-4" />}
          </button>
        </div>
      </button>

      {expanded && data?.sections && (
        <div className="p-4 space-y-2">
          {Object.keys(SECTIONS).map(key => {
            const section = data.sections[key];
            if (key === 'deletion_analysis' && !section) return null;
            const sev = sevMap[key] || SEV.OK;
            const Renderer = RENDERERS[key];
            const isOpen = expandedSections.has(key);
            return (
              <div key={key} className={`border rounded-lg ${SEV_STYLES[sev]}`}>
                <button onClick={() => toggleSection(key)} className="w-full flex items-center gap-2 px-3 py-2 text-left">
                  {isOpen ? <ChevronDownIcon className="h-4 w-4 shrink-0" /> : <ChevronRightIcon className="h-4 w-4 shrink-0" />}
                  {SEV_ICONS[sev]}
                  <span className="text-sm font-medium">{SECTIONS[key]}</span>
                </button>
                {isOpen && (
                  <div className="px-3 pb-3">
                    {section ? <Renderer data={section} /> : <p className="text-sm text-gray-500">No data available.</p>}
                  </div>
                )}
              </div>
            );
          })}
          {data.generated_at && (
            <p className="text-xs text-gray-400 text-right pt-1">Generated: {new Date(data.generated_at).toLocaleString()}</p>
          )}
        </div>
      )}
    </div>
  );
};

export default DiagnosticsPanel;
