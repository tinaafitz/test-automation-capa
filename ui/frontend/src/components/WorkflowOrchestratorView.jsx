import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  PlayIcon,
  StopIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  XCircleIcon,
  ClockIcon,
  EyeIcon,
  BoltIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  CommandLineIcon,
  RocketLaunchIcon,
  KeyIcon,
  CloudIcon,
  ServerIcon,
  Cog6ToothIcon,
  CubeIcon,
  XMarkIcon,
  ArrowDownIcon,
} from '@heroicons/react/24/outline';
import { buildApiUrl } from '../config/api';

const STATUS_STYLES = {
  pending: {
    card: 'border-gray-200 bg-white shadow-sm hover:shadow-md',
    iconBg: 'bg-gray-50 border border-gray-200',
    iconText: 'text-gray-400',
    badgeBg: 'bg-gray-100',
    badgeText: 'text-gray-600',
    icon: ClockIcon,
    label: 'Pending',
    accentBar: 'bg-gray-300',
    dot: 'bg-gray-400',
  },
  running: {
    card: 'border-blue-400 bg-gradient-to-r from-blue-50 to-white ring-2 ring-blue-100 shadow-md shadow-blue-100/50',
    iconBg: 'bg-blue-100 border-2 border-blue-400 ring-2 ring-blue-200',
    iconText: 'text-blue-600',
    badgeBg: 'bg-blue-100',
    badgeText: 'text-blue-700',
    icon: ArrowPathIcon,
    label: 'Running',
    accentBar: 'bg-blue-500',
    dot: 'bg-blue-500',
  },
  succeeded: {
    card: 'border-emerald-400 bg-gradient-to-r from-emerald-50 to-white shadow-sm hover:shadow-md',
    iconBg: 'bg-emerald-100 border border-emerald-300',
    iconText: 'text-emerald-600',
    badgeBg: 'bg-emerald-100',
    badgeText: 'text-emerald-700',
    icon: CheckCircleIcon,
    label: 'Succeeded',
    accentBar: 'bg-emerald-500',
    dot: 'bg-emerald-500',
  },
  failed: {
    card: 'border-red-400 bg-gradient-to-r from-red-50 to-white shadow-sm hover:shadow-md',
    iconBg: 'bg-red-100 border border-red-300',
    iconText: 'text-red-600',
    badgeBg: 'bg-red-100',
    badgeText: 'text-red-700',
    icon: XCircleIcon,
    label: 'Failed',
    accentBar: 'bg-red-500',
    dot: 'bg-red-500',
  },
  cancelled: {
    card: 'border-amber-300 bg-gradient-to-r from-amber-50 to-white shadow-sm hover:shadow-md',
    iconBg: 'bg-amber-100 border border-amber-300',
    iconText: 'text-amber-600',
    badgeBg: 'bg-amber-100',
    badgeText: 'text-amber-700',
    icon: StopIcon,
    label: 'Cancelled',
    accentBar: 'bg-amber-400',
    dot: 'bg-amber-400',
  },
  timed_out: {
    card: 'border-orange-300 bg-gradient-to-r from-orange-50 to-white shadow-sm hover:shadow-md',
    iconBg: 'bg-orange-100 border border-orange-300',
    iconText: 'text-orange-600',
    badgeBg: 'bg-orange-100',
    badgeText: 'text-orange-700',
    icon: ClockIcon,
    label: 'Timed Out',
    accentBar: 'bg-orange-400',
    dot: 'bg-orange-400',
  },
};

function StatusBadge({ status }) {
  const style = STATUS_STYLES[status] || STATUS_STYLES.pending;
  const Icon = style.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold uppercase tracking-wide ${style.badgeBg} ${style.badgeText}`}>
      <Icon className={`h-3.5 w-3.5 ${status === 'running' ? 'animate-spin' : ''}`} />
      {style.label}
    </span>
  );
}

function formatElapsed(seconds) {
  if (seconds == null) return '—';
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m >= 60) {
    const h = Math.floor(m / 60);
    const rm = m % 60;
    return rm > 0 ? `${h}h ${rm}m` : `${h}h`;
  }
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

function relativeTime(dateStr) {
  if (!dateStr) return '—';
  const now = new Date();
  const d = new Date(dateStr);
  const diffMs = now - d;
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  const weeks = Math.floor(days / 7);
  if (weeks < 5) return `${weeks}w ago`;
  return d.toLocaleDateString();
}

function StepCard({ step, clusterName }) {
  const style = STATUS_STYLES[step.status] || STATUS_STYLES.pending;
  const Icon = style.icon;
  const showCluster = clusterName && (step.resource || '').match(/provision|delete|upgrade/i);

  return (
    <div className={`rounded-xl border-2 ${style.card} transition-all duration-300 overflow-hidden`}>
      <div className={`h-0.5 ${style.accentBar} transition-all duration-500`} />

      {step.status === 'running' && (
        <div className="h-0.5 bg-blue-100 overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-blue-400 via-blue-500 to-blue-400"
            style={{ width: '40%', animation: 'shimmer 3s ease-in-out infinite' }}
          />
        </div>
      )}

      <div className="flex items-center gap-3 px-4 py-3">
        <div className={`w-7 h-7 rounded-full ${style.iconBg} flex items-center justify-center flex-shrink-0 ${step.status === 'running' ? 'animate-pulse' : ''}`}>
          <Icon className={`h-4 w-4 ${style.iconText} ${step.status === 'running' ? 'animate-spin' : ''}`} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-gray-900 truncate">{step.name}</span>
            {showCluster && (
              <span className="text-[10px] px-1.5 py-0.5 bg-slate-100 text-slate-500 rounded-md font-mono border border-slate-200">
                {clusterName}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
            <span className="flex items-center gap-1">
              <CubeIcon className="h-3 w-3" />
              <span className="font-mono">{step.resource}</span>
            </span>
            <span className="text-gray-300">|</span>
            <span>Elapsed: <span className="font-mono font-medium">{formatElapsed(step.elapsed_seconds)}</span></span>
            <span className="text-gray-300">|</span>
            <span>Timeout: <span className="font-mono">{formatElapsed(step.timeout_seconds)}</span></span>
          </div>
        </div>

        <StatusBadge status={step.status} />
      </div>

      {step.error && (
        <div className="mx-4 mb-3 text-red-600 bg-red-50 border border-red-200 rounded-lg p-2.5 text-xs break-words">
          {step.error}
        </div>
      )}

      {step.sub_execution_id && (
        <div className="mx-4 mb-3 text-xs text-blue-600 bg-blue-50 border border-blue-200 rounded-lg px-2.5 py-1.5">
          Sub-execution: <span className="font-mono">{step.sub_execution_id}</span>
        </div>
      )}
    </div>
  );
}

function StepConnector({ prevStatus }) {
  const color = prevStatus === 'running' ? 'text-blue-400' : prevStatus === 'succeeded' ? 'text-emerald-400' : 'text-gray-300';
  const barColor = prevStatus === 'running' ? 'bg-blue-400' : prevStatus === 'succeeded' ? 'bg-emerald-400' : 'bg-gray-300';
  return (
    <div className="flex flex-col items-center py-0.5">
      <div className={`w-0.5 h-3 ${barColor} rounded-full`} />
      <ArrowDownIcon className={`h-4 w-4 -mt-0.5 ${color}`} />
    </div>
  );
}

function ExecutionGraph({ execution }) {
  if (!execution) return null;

  const { steps, parallel_groups, input } = execution;
  const stepEntries = Object.entries(steps || {});
  const parallelStepNames = new Set((parallel_groups || []).flat());
  const rendered = new Set();
  const prefix = (input || {}).name_prefix || '';
  const clusterName = prefix ? `${prefix}-rosa-hcp` : (input || {}).cluster_name || '';

  const elements = [];
  let prevStatus = null;

  for (const [name, step] of stepEntries) {
    if (rendered.has(name)) continue;

    if (parallelStepNames.has(name)) {
      const groupSteps = stepEntries.filter(([n]) => parallelStepNames.has(n) && !rendered.has(n));
      groupSteps.forEach(([n]) => rendered.add(n));

      if (prevStatus !== null) {
        elements.push(<StepConnector key={`conn-${name}`} prevStatus={prevStatus} />);
      }

      elements.push(
        <div key={`parallel-${name}`} className="rounded-xl border-2 border-dashed border-blue-300 bg-gradient-to-r from-blue-50/50 to-white p-4 shadow-sm">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center">
              <BoltIcon className="h-3.5 w-3.5 text-white" />
            </div>
            <span className="text-xs font-bold text-blue-700 uppercase tracking-wider">Parallel Execution</span>
            <span className="text-[10px] px-1.5 py-0.5 bg-blue-100 text-blue-600 rounded-full font-bold">
              {groupSteps.length} tasks
            </span>
          </div>
          <div className={`grid grid-cols-1 ${groupSteps.length >= 3 ? 'md:grid-cols-3' : 'md:grid-cols-2'} gap-3`}>
            {groupSteps.map(([n, s]) => (
              <StepCard key={n} step={s} clusterName={clusterName} />
            ))}
          </div>
        </div>
      );
      const lastGroupStep = groupSteps[groupSteps.length - 1];
      prevStatus = lastGroupStep ? lastGroupStep[1].status : null;
    } else {
      if (prevStatus !== null) {
        elements.push(<StepConnector key={`conn-${name}`} prevStatus={prevStatus} />);
      }
      rendered.add(name);
      elements.push(<StepCard key={name} step={step} clusterName={clusterName} />);
      prevStatus = step.status;
    }
  }

  return <div className="space-y-0 max-w-3xl mx-auto">{elements}</div>;
}

export default function WorkflowOrchestratorView() {
  const [stateMachines, setStateMachines] = useState([]);
  const [executions, setExecutions] = useState([]);
  const [selectedExecution, setSelectedExecution] = useState(null);
  const [liveExecution, setLiveExecution] = useState(null);
  const [plan, setPlan] = useState(null);
  const [showPlan, setShowPlan] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState('');
  const [selectedSM, setSelectedSM] = useState('rosa-hcp-provision');
  const [credentials, setCredentials] = useState({});
  const [credentialsLoaded, setCredentialsLoaded] = useState(false);
  const [envName, setEnvName] = useState('');
  const [vars, setVars] = useState({});
  const [showVars, setShowVars] = useState(false);
  const [showExecution, setShowExecution] = useState(true);
  const [showHistory, setShowHistory] = useState(true);
  const pollingRef = useRef(null);

  const extractEnvName = (apiUrl) => {
    if (!apiUrl) return '';
    try {
      const hostname = new URL(apiUrl).hostname;
      const parts = hostname.split('.');
      return parts[0] === 'api' && parts.length > 1 ? parts[1] : parts[0];
    } catch {
      return '';
    }
  };

  const buildDefaultVars = useCallback((creds) => {
    const defaults = {};
    defaults.name_prefix = '';
    if (creds.AWS_ACCESS_KEY_ID) defaults.AWS_ACCESS_KEY_ID = creds.AWS_ACCESS_KEY_ID;
    if (creds.AWS_SECRET_ACCESS_KEY) defaults.AWS_SECRET_ACCESS_KEY = creds.AWS_SECRET_ACCESS_KEY;
    if (creds.AWS_REGION) defaults.aws_region = creds.AWS_REGION;
    if (creds.OCM_CLIENT_ID) defaults.OCM_CLIENT_ID = creds.OCM_CLIENT_ID;
    if (creds.OCM_CLIENT_SECRET) defaults.OCM_CLIENT_SECRET = creds.OCM_CLIENT_SECRET;
    if (creds.OCP_HUB_API_URL) defaults.OCP_HUB_API_URL = creds.OCP_HUB_API_URL;
    if (creds.OCP_HUB_CLUSTER_USER) defaults.OCP_HUB_CLUSTER_USER = creds.OCP_HUB_CLUSTER_USER;
    if (creds.OCP_HUB_CLUSTER_PASSWORD) defaults.OCP_HUB_CLUSTER_PASSWORD = creds.OCP_HUB_CLUSTER_PASSWORD;
    defaults.capi_namespace = 'ns-rosa-hcp';
    defaults.openshift_version = '4.20.10';
    defaults.create_rosa_roles = 'true';
    defaults.create_rosa_network = 'true';
    defaults.availability_zone_count = '2';
    defaults.network_cidr = '10.0.0.0/16';
    return defaults;
  }, []);

  const fetchCredentials = useCallback(async () => {
    try {
      const res = await fetch(buildApiUrl('/api/credentials'));
      const data = await res.json();
      if (data.success && data.credentials) {
        setCredentials(data.credentials);
        setEnvName(extractEnvName(data.credentials.OCP_HUB_API_URL));
        setVars((prev) => Object.keys(prev).length === 0 ? buildDefaultVars(data.credentials) : prev);
        setCredentialsLoaded(true);
      }
    } catch (e) {
      console.error('Failed to fetch credentials:', e);
    }
  }, [buildDefaultVars]);

  const fetchStateMachines = useCallback(async () => {
    try {
      const res = await fetch(buildApiUrl('/api/orchestrator/state-machines'));
      const data = await res.json();
      setStateMachines(data.state_machines || []);
    } catch (e) {
      console.error('Failed to fetch state machines:', e);
    }
  }, []);

  const fetchExecutions = useCallback(async () => {
    try {
      const res = await fetch(buildApiUrl('/api/orchestrator/executions'));
      const data = await res.json();
      setExecutions(data.executions || []);
    } catch (e) {
      console.error('Failed to fetch executions:', e);
    }
  }, []);

  const fetchExecutionDetail = useCallback(async (id) => {
    try {
      const res = await fetch(buildApiUrl(`/api/orchestrator/executions/${id}`));
      const data = await res.json();
      setSelectedExecution(data);
      if (data.status === 'running') {
        setLiveExecution(data);
      } else {
        setLiveExecution(null);
      }
    } catch (e) {
      console.error('Failed to fetch execution:', e);
    }
  }, []);

  useEffect(() => {
    fetchStateMachines();
    fetchExecutions();
    fetchCredentials();
  }, [fetchStateMachines, fetchExecutions, fetchCredentials]);

  useEffect(() => {
    if (liveExecution && (liveExecution.status === 'running' || liveExecution.status === 'pending')) {
      pollingRef.current = setInterval(() => {
        fetchExecutionDetail(liveExecution.execution_id);
        fetchExecutions();
      }, 3000);
    }
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [liveExecution, fetchExecutionDetail, fetchExecutions]);

  const buildInputParams = () => {
    const params = {};
    for (const [k, v] of Object.entries(vars)) {
      if (v !== '') params[k] = v;
    }
    return params;
  };

  const handleVarChange = (key, value) => {
    setVars((prev) => ({ ...prev, [key]: value }));
  };

  const handleAddVar = () => {
    const key = `custom_${Object.keys(vars).length}`;
    setVars((prev) => ({ ...prev, [key]: '' }));
  };

  const handleRemoveVar = (key) => {
    setVars((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const handleRenameVar = (oldKey, newKey) => {
    if (oldKey === newKey || !newKey.trim()) return;
    setVars((prev) => {
      const next = {};
      for (const [k, v] of Object.entries(prev)) {
        next[k === oldKey ? newKey : k] = v;
      }
      return next;
    });
  };

  const handlePreview = async () => {
    setError('');
    try {
      const res = await fetch(buildApiUrl('/api/orchestrator/plan'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          state_machine: selectedSM,
          input_params: buildInputParams(),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Plan failed');
      setPlan(data);
      setShowPlan(true);
    } catch (e) {
      setError(e.message);
    }
  };

  const handleLaunch = async () => {
    if (!credentialsLoaded || !envName) {
      setError('No active environment configured — set credentials first');
      return;
    }
    setError('');
    setLaunching(true);
    try {
      const res = await fetch(buildApiUrl('/api/orchestrator/execute'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          state_machine: selectedSM,
          input_params: buildInputParams(),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Launch failed');
      setSelectedExecution(data);
      setLiveExecution(data);
      setShowPlan(false);
      fetchExecutions();
    } catch (e) {
      setError(e.message);
    } finally {
      setLaunching(false);
    }
  };

  const handleCancel = async (id) => {
    try {
      await fetch(buildApiUrl(`/api/orchestrator/executions/${id}/cancel`), { method: 'POST' });
      fetchExecutionDetail(id);
      fetchExecutions();
    } catch (e) {
      setError(e.message);
    }
  };

  const handleResume = async (id) => {
    setError('');
    try {
      const res = await fetch(buildApiUrl(`/api/orchestrator/executions/${id}/resume`), { method: 'POST' });
      if (!res.ok) {
        const data = await res.json();
        setError(data.detail || 'Failed to resume');
        return;
      }
      const data = await res.json();
      setSelectedExecution(data);
      setLiveExecution(data);
      fetchExecutions();
    } catch (e) {
      setError(e.message);
    }
  };

  const isCredentialKey = (key) =>
    /SECRET|PASSWORD|KEY|CLIENT_ID|CLIENT_SECRET|TOKEN/i.test(key) &&
    !/region|namespace|version|cidr|count|prefix|name_prefix/i.test(key);

  const isSecretValue = (key) =>
    /SECRET|PASSWORD|ACCESS_KEY/i.test(key) &&
    !/region|namespace|version|cidr|count|prefix|name/i.test(key);

  const credentialVars = Object.entries(vars).filter(([k]) => isCredentialKey(k));
  const configVars = Object.entries(vars).filter(([k]) => !isCredentialKey(k));

  const stats = useMemo(() => {
    const succeeded = executions.filter((e) => e.status === 'succeeded').length;
    const failed = executions.filter((e) => e.status === 'failed').length;
    const running = executions.filter((e) => e.status === 'running').length;
    const total = executions.length;
    const successRate = total > 0 ? Math.round((succeeded / total) * 100) : 0;
    const avgDuration = total > 0
      ? Math.round(executions.reduce((sum, e) => sum + (e.elapsed_seconds || 0), 0) / total)
      : 0;
    const lastRun = executions.length > 0 ? executions[0] : null;
    return { succeeded, failed, running, total, successRate, avgDuration, lastRun };
  }, [executions]);

  const executionProgressPct = selectedExecution?.steps
    ? Math.round(
        (Object.values(selectedExecution.steps).filter((s) => s.status === 'succeeded').length /
          Object.values(selectedExecution.steps).length) *
          100
      )
    : 0;

  const execHeaderGradient =
    selectedExecution?.status === 'running'
      ? 'bg-gradient-to-r from-blue-600 to-indigo-600'
      : selectedExecution?.status === 'succeeded'
      ? 'bg-gradient-to-r from-emerald-600 to-teal-600'
      : selectedExecution?.status === 'failed'
      ? 'bg-gradient-to-r from-red-600 to-rose-600'
      : 'bg-gradient-to-r from-slate-700 to-slate-800';

  return (
    <div className="space-y-5">
      <style>{`@keyframes shimmer { 0% { transform: translateX(-100%); } 100% { transform: translateX(350%); } }`}</style>

      {/* ── Launch Card ── */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
        <div className="flex items-end gap-4 flex-wrap">
          <div className="min-w-[200px]">
            <label className="block text-sm font-medium text-gray-700 mb-1.5">Workflow</label>
            <select
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              value={selectedSM}
              onChange={(e) => setSelectedSM(e.target.value)}
            >
              {stateMachines.map((sm) => (
                <option key={sm.name} value={sm.name}>{sm.name}</option>
              ))}
              {stateMachines.length === 0 && <option value="rosa-hcp-provision">rosa-hcp-provision</option>}
            </select>
          </div>

          <button
            className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 rounded-lg text-sm font-medium transition-colors"
            onClick={handlePreview}
          >
            <EyeIcon className="h-4 w-4" />
            Preview Plan
          </button>

          <button
            className="inline-flex items-center gap-2 px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            onClick={handleLaunch}
            disabled={launching || !credentialsLoaded || !envName}
          >
            {launching ? (
              <>
                <ArrowPathIcon className="h-4 w-4 animate-spin" />
                Launching...
              </>
            ) : (
              <>
                <PlayIcon className="h-4 w-4" />
                Launch
              </>
            )}
          </button>

          {credentialsLoaded && (
            <div className="flex items-center gap-1.5 ml-2">
              {[
                { label: 'AWS', ok: !!credentials.AWS_ACCESS_KEY_ID },
                { label: 'OCM', ok: !!credentials.OCM_CLIENT_ID },
                { label: 'OCP', ok: !!credentials.OCP_HUB_API_URL },
              ].map(({ label, ok }) => (
                <span
                  key={label}
                  className={`text-xs font-medium ${ok ? 'text-emerald-600' : 'text-red-500'}`}
                >
                  {label} {ok ? 'OK' : '—'}
                </span>
              ))}
            </div>
          )}

          <div className="ml-auto flex items-center gap-4">
            <button
              className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 transition-colors"
              onClick={() => setShowVars(!showVars)}
            >
              <Cog6ToothIcon className="h-4 w-4" />
              Variables
              <span className="text-[10px] px-1.5 py-0.5 bg-gray-100 text-gray-500 rounded-full font-medium">
                {Object.keys(vars).length}
              </span>
              {showVars ? <ChevronDownIcon className="h-3 w-3" /> : <ChevronRightIcon className="h-3 w-3" />}
            </button>
          </div>
        </div>

        {/* Summary line */}
        {stats.total > 0 && (
          <div className="mt-4 pt-4 border-t border-gray-100 flex items-center gap-6 text-xs text-gray-400">
            <span>{stats.total} runs</span>
            <span className="text-emerald-600">{stats.succeeded} passed</span>
            <span className="text-red-500">{stats.failed} failed</span>
            <span>{stats.successRate}% success rate</span>
            <span>avg {formatElapsed(stats.avgDuration)}</span>
            <div className="flex-1" />
            <div className="flex h-1.5 w-28 rounded-full overflow-hidden bg-gray-100">
              {stats.succeeded > 0 && (
                <div className="h-full bg-emerald-400" style={{ width: `${(stats.succeeded / stats.total) * 100}%` }} />
              )}
              {stats.failed > 0 && (
                <div className="h-full bg-red-400" style={{ width: `${(stats.failed / stats.total) * 100}%` }} />
              )}
            </div>
          </div>
        )}

        {/* Inline Variables */}
        {showVars && (
          <div className="mt-4 pt-4 border-t border-gray-100">
            {credentialVars.length > 0 && (
              <div className="mb-4">
                <div className="flex items-center gap-2 mb-2">
                  <KeyIcon className="h-3.5 w-3.5 text-amber-500" />
                  <span className="text-[10px] font-bold tracking-widest text-amber-500 uppercase">Credentials</span>
                </div>
                <div className="space-y-1.5 bg-amber-50/50 rounded-lg p-3 border border-amber-100">
                  {credentialVars.map(([key, val]) => (
                    <div key={key} className="flex items-center gap-2 group">
                      <input
                        type="text"
                        className="border border-gray-200 rounded-lg px-2.5 py-1.5 text-xs font-mono w-48 bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        defaultValue={key}
                        onBlur={(e) => handleRenameVar(key, e.target.value)}
                      />
                      <span className="text-gray-300 text-xs">=</span>
                      <input
                        type={isSecretValue(key) ? 'password' : 'text'}
                        className="border border-gray-200 rounded-lg px-2.5 py-1.5 text-xs font-mono flex-1 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        value={val}
                        onChange={(e) => handleVarChange(key, e.target.value)}
                      />
                      <button
                        className="p-1 text-gray-300 hover:text-red-500 hover:bg-red-50 rounded-md transition-all opacity-0 group-hover:opacity-100"
                        onClick={() => handleRemoveVar(key)}
                        title="Remove"
                      >
                        <XMarkIcon className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {configVars.length > 0 && (
              <div className="mb-3">
                <div className="flex items-center gap-2 mb-2">
                  <Cog6ToothIcon className="h-3.5 w-3.5 text-gray-400" />
                  <span className="text-[10px] font-bold tracking-widest text-gray-400 uppercase">Cluster Configuration</span>
                </div>
                <div className="space-y-1.5 bg-gray-50 rounded-lg p-3 border border-gray-100">
                  {configVars.map(([key, val]) => (
                    <div key={key} className="flex items-center gap-2 group">
                      <input
                        type="text"
                        className="border border-gray-200 rounded-lg px-2.5 py-1.5 text-xs font-mono w-48 bg-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        defaultValue={key}
                        onBlur={(e) => handleRenameVar(key, e.target.value)}
                      />
                      <span className="text-gray-300 text-xs">=</span>
                      <input
                        type="text"
                        className="border border-gray-200 rounded-lg px-2.5 py-1.5 text-xs font-mono flex-1 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        value={val}
                        onChange={(e) => handleVarChange(key, e.target.value)}
                      />
                      <button
                        className="p-1 text-gray-300 hover:text-red-500 hover:bg-red-50 rounded-md transition-all opacity-0 group-hover:opacity-100"
                        onClick={() => handleRemoveVar(key)}
                        title="Remove"
                      >
                        <XMarkIcon className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <button
              className="text-xs text-blue-600 hover:text-blue-800 font-medium"
              onClick={handleAddVar}
            >
              + Add variable
            </button>
          </div>
        )}
      </div>

      {/* Error Banner */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-start gap-3">
          <XCircleIcon className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
          <p className="flex-1 text-sm text-red-700 font-medium">{error}</p>
          <button
            className="text-red-400 hover:text-red-600 transition-colors flex-shrink-0"
            onClick={() => setError('')}
          >
            <XMarkIcon className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Execution Plan Preview */}
      {showPlan && plan && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3 bg-gradient-to-r from-slate-700 to-slate-800">
            <div className="flex items-center gap-2.5">
              <EyeIcon className="h-4 w-4 text-slate-300" />
              <h3 className="text-sm font-semibold text-white">Execution Plan (Dry Run)</h3>
            </div>
            <button
              className="text-slate-400 hover:text-white transition-colors"
              onClick={() => setShowPlan(false)}
            >
              <XMarkIcon className="h-4 w-4" />
            </button>
          </div>

          <div className="p-5">
            <div className="grid grid-cols-3 gap-4 mb-5">
              <div className="bg-gray-50 border border-gray-200 rounded-xl px-4 py-3 text-center">
                <div className="text-[10px] font-bold tracking-widest text-gray-400 uppercase mb-1">Sequential</div>
                <div className="text-xl font-bold text-gray-700">{formatElapsed(plan.estimated_time_sequential_seconds)}</div>
              </div>
              <div className="bg-gradient-to-br from-emerald-50 to-white border border-emerald-200 rounded-xl px-4 py-3 text-center ring-2 ring-emerald-100">
                <div className="text-[10px] font-bold tracking-widest text-emerald-500 uppercase mb-1">Parallel</div>
                <div className="text-xl font-bold text-emerald-700">{formatElapsed(plan.estimated_time_parallel_seconds)}</div>
              </div>
              <div className="bg-gradient-to-br from-blue-50 to-white border border-blue-200 rounded-xl px-4 py-3 text-center">
                <div className="text-[10px] font-bold tracking-widest text-blue-500 uppercase mb-1">Time Saved</div>
                <div className="text-xl font-bold text-blue-700">
                  ~{formatElapsed((plan.estimated_time_sequential_seconds || 0) - (plan.estimated_time_parallel_seconds || 0))}
                </div>
              </div>
            </div>

            <div className="space-y-2">
              {(plan.steps || []).map((step, i) => (
                <div
                  key={i}
                  className={`flex items-center gap-3 px-4 py-2.5 rounded-xl border transition-all ${
                    step.parallel
                      ? 'bg-gradient-to-r from-blue-50 to-white border-blue-200 ml-6'
                      : 'bg-white border-gray-200 hover:shadow-sm'
                  }`}
                >
                  <div
                    className={`w-6 h-6 rounded-lg flex items-center justify-center text-white text-[10px] font-bold ${
                      step.parallel
                        ? 'bg-gradient-to-br from-blue-500 to-indigo-600'
                        : 'bg-gradient-to-br from-gray-400 to-gray-500'
                    }`}
                  >
                    {i + 1}
                  </div>
                  <span className="font-semibold text-sm text-gray-800 w-48 shrink-0 truncate">{step.name}</span>
                  <span className="font-mono text-xs text-gray-400 flex-1 truncate">{step.task_file}</span>
                  <span className="text-[10px] px-2 py-0.5 bg-gray-100 text-gray-500 rounded-md font-mono shrink-0">
                    {formatElapsed(step.timeout_seconds)}
                  </span>
                  {step.parallel && (
                    <span className="text-[10px] px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full font-semibold uppercase tracking-wider shrink-0">
                      Parallel
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Live / Selected Execution */}
      {selectedExecution && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-lg overflow-hidden">
          <div
            className={`flex items-center justify-between px-5 py-3 cursor-pointer ${execHeaderGradient}`}
            onClick={() => setShowExecution(!showExecution)}
          >
            <div className="flex items-center gap-3">
              {showExecution ? (
                <ChevronDownIcon className="h-4 w-4 text-white/70" />
              ) : (
                <ChevronRightIcon className="h-4 w-4 text-white/70" />
              )}
              {selectedExecution.status === 'running' ? (
                <ArrowPathIcon className="h-5 w-5 text-white animate-spin" />
              ) : selectedExecution.status === 'succeeded' ? (
                <CheckCircleIcon className="h-5 w-5 text-white" />
              ) : selectedExecution.status === 'failed' ? (
                <XCircleIcon className="h-5 w-5 text-white" />
              ) : (
                <ClockIcon className="h-5 w-5 text-white/70" />
              )}
              <div>
                <span className="text-sm font-semibold text-white">
                  Execution: <span className="font-mono">{(selectedExecution.execution_id || '').slice(0, 16)}...</span>
                </span>
                <div className="flex items-center gap-3 mt-0.5">
                  <span className="text-xs text-white/70">Mode: {selectedExecution.mode}</span>
                  <span className="text-xs text-white/70">Elapsed: {formatElapsed(selectedExecution.elapsed_seconds)}</span>
                </div>
              </div>
            </div>
            <div className="flex gap-2 items-center" onClick={(e) => e.stopPropagation()}>
              {selectedExecution.status === 'running' && (
                <button
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white/10 hover:bg-white/20 text-white border border-white/20 rounded-lg text-sm font-medium transition-all"
                  onClick={() => handleCancel(selectedExecution.execution_id)}
                >
                  <StopIcon className="h-4 w-4" />
                  Cancel
                </button>
              )}
              {(selectedExecution.status === 'failed' || selectedExecution.status === 'cancelled') && (
                <button
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white/10 hover:bg-white/20 text-white border border-white/20 rounded-lg text-sm font-medium transition-all"
                  onClick={() => handleResume(selectedExecution.execution_id)}
                >
                  <ArrowPathIcon className="h-4 w-4" />
                  Resume
                </button>
              )}
              <button
                className="p-1 text-white/40 hover:text-white hover:bg-white/10 rounded-lg transition-all ml-1"
                onClick={() => { setSelectedExecution(null); setLiveExecution(null); }}
                title="Close"
              >
                <XMarkIcon className="h-4 w-4" />
              </button>
            </div>
          </div>

          {showExecution && (
            <>
              {selectedExecution.status === 'running' && (
                <div className="h-1 bg-blue-100 overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-blue-400 to-blue-500 animate-pulse transition-all duration-500"
                    style={{ width: `${executionProgressPct}%` }}
                  />
                </div>
              )}

              <div className="p-5">
                <ExecutionGraph execution={selectedExecution} />
              </div>

              {selectedExecution.error && (
                <div className="mx-5 mb-5 bg-red-50 border border-red-200 rounded-xl p-3 text-sm text-red-700 flex items-start gap-2">
                  <XCircleIcon className="h-4 w-4 text-red-500 flex-shrink-0 mt-0.5" />
                  <span>{selectedExecution.error}</span>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ── Execution History ── */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div
          className="flex items-center justify-between px-5 py-3 border-b border-gray-100 cursor-pointer hover:bg-gray-50/50 transition-colors"
          onClick={() => setShowHistory(!showHistory)}
        >
          <div className="flex items-center gap-2">
            {showHistory ? (
              <ChevronDownIcon className="h-4 w-4 text-gray-400" />
            ) : (
              <ChevronRightIcon className="h-4 w-4 text-gray-400" />
            )}
            <h3 className="text-sm font-semibold text-gray-700">Workflow Execution History</h3>
          </div>

          <div className="flex items-center gap-3" onClick={(e) => e.stopPropagation()}>
            {stats.total > 0 && (
              <div className="flex items-center gap-2">
                <div className="flex h-2.5 w-32 rounded-full overflow-hidden bg-gray-100">
                  {stats.succeeded > 0 && (
                    <div
                      className="h-full bg-gradient-to-r from-emerald-400 to-emerald-500 transition-all duration-700"
                      style={{ width: `${(stats.succeeded / stats.total) * 100}%` }}
                    />
                  )}
                  {stats.failed > 0 && (
                    <div
                      className="h-full bg-gradient-to-r from-red-400 to-red-500 transition-all duration-700"
                      style={{ width: `${(stats.failed / stats.total) * 100}%` }}
                    />
                  )}
                  {stats.running > 0 && (
                    <div
                      className="h-full bg-gradient-to-r from-blue-400 to-blue-500 animate-pulse"
                      style={{ width: `${(stats.running / stats.total) * 100}%` }}
                    />
                  )}
                </div>
                <div className="flex items-center gap-2 text-[10px] text-gray-400">
                  <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />{stats.succeeded}</span>
                  <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-red-500" />{stats.failed}</span>
                </div>
              </div>
            )}

            <button
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-gray-50 hover:bg-gray-100 text-gray-600 border border-gray-200 rounded-lg text-xs font-medium transition-all"
              onClick={fetchExecutions}
            >
              <ArrowPathIcon className="h-3.5 w-3.5" />
              Refresh
            </button>
          </div>
        </div>

        {!showHistory ? null : executions.length === 0 ? (
          <div className="p-12 text-center">
            <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-gray-50 via-gray-100 to-slate-100 flex items-center justify-center border border-gray-200/50">
              <CommandLineIcon className="h-8 w-8 text-gray-300" />
            </div>
            <p className="text-sm text-gray-500 font-medium">No executions yet</p>
            <p className="text-xs text-gray-400 mt-1">Launch one above to get started.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="bg-gray-50/80 border-b border-gray-100">
                  <th className="pl-5 pr-3 py-2 text-[10px] font-semibold text-gray-400 uppercase tracking-wider w-8"></th>
                  <th className="px-3 py-2 text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Execution</th>
                  <th className="px-3 py-2 text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Workflow</th>
                  <th className="px-3 py-2 text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Status</th>
                  <th className="px-3 py-2 text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Duration</th>
                  <th className="px-3 py-2 text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Started</th>
                </tr>
              </thead>
              <tbody>
                {executions.map((exec, idx) => {
                  const isSelected = selectedExecution?.execution_id === exec.execution_id;
                  const statusStyle = STATUS_STYLES[exec.status] || STATUS_STYLES.pending;
                  const StatusIcon = statusStyle.icon;
                  return (
                    <tr
                      key={exec.execution_id}
                      className={`cursor-pointer transition-all duration-150 border-b border-gray-50 last:border-0 ${
                        isSelected
                          ? 'bg-blue-50/50'
                          : idx % 2 === 0 ? 'bg-white hover:bg-gray-50/50' : 'bg-gray-50/20 hover:bg-gray-50/50'
                      }`}
                      onClick={() => fetchExecutionDetail(exec.execution_id)}
                    >
                      <td className="pl-5 pr-1 py-2">
                        {isSelected ? (
                          <div className="w-1.5 h-5 rounded-full bg-blue-500" />
                        ) : (
                          <div className="w-1.5 h-5 rounded-full bg-transparent group-hover:bg-gray-200" />
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <span className="text-xs font-mono text-gray-500">{(exec.execution_id || '').slice(0, 12)}</span>
                      </td>
                      <td className="px-3 py-2">
                        <span className="text-xs text-gray-600">{exec.state_machine}</span>
                      </td>
                      <td className="px-3 py-2">
                        <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md" style={{ backgroundColor: exec.status === 'succeeded' ? '#f0fdf4' : exec.status === 'failed' ? '#fef2f2' : exec.status === 'running' ? '#eff6ff' : '#f9fafb' }}>
                          <StatusIcon className={`h-3.5 w-3.5 ${statusStyle.iconText} ${exec.status === 'running' ? 'animate-spin' : ''}`} />
                          <span className={`text-xs font-semibold ${statusStyle.badgeText}`}>
                            {statusStyle.label}
                          </span>
                        </div>
                      </td>
                      <td className="px-3 py-2">
                        <span className="text-xs font-mono text-gray-500">{formatElapsed(exec.elapsed_seconds)}</span>
                      </td>
                      <td className="px-3 py-2">
                        <span className="text-xs text-gray-600">{relativeTime(exec.created_at)}</span>
                        <span className="text-[10px] text-gray-300 ml-1.5">
                          {exec.created_at ? new Date(exec.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : ''}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
