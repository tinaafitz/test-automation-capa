import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  PlayIcon,
  StopIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  XCircleIcon,
  ClockIcon,
  EyeIcon,
} from '@heroicons/react/24/outline';
import { buildApiUrl } from '../config/api';

const STATUS_STYLES = {
  pending:   { bg: 'bg-gray-100',   text: 'text-gray-600',   border: 'border-gray-300',   icon: ClockIcon,       label: 'Pending' },
  running:   { bg: 'bg-blue-50',    text: 'text-blue-700',   border: 'border-blue-400',   icon: ArrowPathIcon,   label: 'Running' },
  succeeded: { bg: 'bg-green-50',   text: 'text-green-700',  border: 'border-green-400',  icon: CheckCircleIcon, label: 'Succeeded' },
  failed:    { bg: 'bg-red-50',     text: 'text-red-700',    border: 'border-red-400',    icon: XCircleIcon,     label: 'Failed' },
  cancelled: { bg: 'bg-yellow-50',  text: 'text-yellow-700', border: 'border-yellow-400', icon: StopIcon,        label: 'Cancelled' },
  timed_out: { bg: 'bg-orange-50',  text: 'text-orange-700', border: 'border-orange-400', icon: ClockIcon,       label: 'Timed Out' },
};

function StatusBadge({ status }) {
  const style = STATUS_STYLES[status] || STATUS_STYLES.pending;
  const Icon = style.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${style.bg} ${style.text}`}>
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
  return `${m}m ${s}s`;
}

function StepCard({ step, isParallel }) {
  const style = STATUS_STYLES[step.status] || STATUS_STYLES.pending;
  return (
    <div className={`border-l-4 ${style.border} rounded-lg p-3 ${style.bg} transition-all duration-300`}>
      <div className="flex items-center justify-between mb-1">
        <span className="font-medium text-sm text-gray-800">{step.name}</span>
        <StatusBadge status={step.status} />
      </div>
      <div className="text-xs text-gray-500 space-y-0.5">
        <div>Resource: <span className="font-mono">{step.resource}</span></div>
        <div className="flex gap-4">
          <span>Elapsed: {formatElapsed(step.elapsed_seconds)}</span>
          <span>Timeout: {formatElapsed(step.timeout_seconds)}</span>
        </div>
        {step.error && (
          <div className="mt-1 text-red-600 bg-red-50 rounded p-1.5 text-xs break-words">
            {step.error}
          </div>
        )}
      </div>
    </div>
  );
}

function ExecutionGraph({ execution }) {
  if (!execution) return null;

  const { steps, parallel_groups } = execution;
  const stepEntries = Object.entries(steps || {});
  const parallelStepNames = new Set((parallel_groups || []).flat());
  const rendered = new Set();

  const elements = [];
  for (const [name, step] of stepEntries) {
    if (rendered.has(name)) continue;

    if (parallelStepNames.has(name)) {
      const groupSteps = stepEntries.filter(([n]) => parallelStepNames.has(n) && !rendered.has(n));
      groupSteps.forEach(([n]) => rendered.add(n));
      elements.push(
        <div key={`parallel-${name}`} className="border-2 border-dashed border-blue-300 rounded-lg p-3 bg-blue-50/30">
          <div className="text-xs font-semibold text-blue-600 uppercase tracking-wide mb-2">
            ⚡ Parallel Execution
          </div>
          <div className={`grid grid-cols-1 ${groupSteps.length >= 3 ? 'md:grid-cols-3' : 'md:grid-cols-2'} gap-2`}>
            {groupSteps.map(([n, s]) => (
              <StepCard key={n} step={s} isParallel={true} />
            ))}
          </div>
        </div>
      );
    } else {
      rendered.add(name);
      elements.push(<StepCard key={name} step={step} isParallel={false} />);
    }
  }

  return <div className="space-y-3">{elements}</div>;
}

function ExecutionHistoryRow({ exec, onSelect, isSelected }) {
  return (
    <tr
      className={`cursor-pointer hover:bg-gray-50 transition ${isSelected ? 'bg-blue-50' : ''}`}
      onClick={() => onSelect(exec.execution_id)}
    >
      <td className="px-3 py-2 text-xs font-mono text-gray-700">{exec.execution_id}</td>
      <td className="px-3 py-2 text-xs">{exec.state_machine}</td>
      <td className="px-3 py-2"><StatusBadge status={exec.status} /></td>
      <td className="px-3 py-2 text-xs text-gray-500">{formatElapsed(exec.elapsed_seconds)}</td>
      <td className="px-3 py-2 text-xs text-gray-500">
        {exec.created_at ? new Date(exec.created_at).toLocaleString() : '—'}
      </td>
    </tr>
  );
}

export default function StepFunctionsView() {
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
      const res = await fetch(buildApiUrl('/api/stepfunctions/state-machines'));
      const data = await res.json();
      setStateMachines(data.state_machines || []);
    } catch (e) {
      console.error('Failed to fetch state machines:', e);
    }
  }, []);

  const fetchExecutions = useCallback(async () => {
    try {
      const res = await fetch(buildApiUrl('/api/stepfunctions/executions'));
      const data = await res.json();
      setExecutions(data.executions || []);
    } catch (e) {
      console.error('Failed to fetch executions:', e);
    }
  }, []);

  const fetchExecutionDetail = useCallback(async (id) => {
    try {
      const res = await fetch(buildApiUrl(`/api/stepfunctions/executions/${id}`));
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

  // Poll running executions
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
      const res = await fetch(buildApiUrl('/api/stepfunctions/plan'), {
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
      const res = await fetch(buildApiUrl('/api/stepfunctions/execute'), {
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
      await fetch(buildApiUrl(`/api/stepfunctions/executions/${id}/cancel`), { method: 'POST' });
      fetchExecutionDetail(id);
      fetchExecutions();
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-bold text-gray-900">Step Functions Orchestration</h2>
        <p className="text-sm text-gray-500 mt-1">
          Parallel execution of provisioning steps — network, IAM roles, and OIDC run concurrently.
        </p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
          {error}
          <button className="ml-2 text-red-500 underline" onClick={() => setError('')}>dismiss</button>
        </div>
      )}

      {/* Launch Panel */}
      <div className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-700">Launch Execution</h3>
          {credentialsLoaded && (
            <div className="flex items-center gap-2 text-xs">
              <span className={credentials.AWS_ACCESS_KEY_ID ? 'text-green-600' : 'text-red-500'}>
                AWS {credentials.AWS_ACCESS_KEY_ID ? 'OK' : 'Missing'}
              </span>
              <span className="text-gray-300">|</span>
              <span className={credentials.OCM_CLIENT_ID ? 'text-green-600' : 'text-red-500'}>
                OCM {credentials.OCM_CLIENT_ID ? 'OK' : 'Missing'}
              </span>
              <span className="text-gray-300">|</span>
              <span className={credentials.OCP_HUB_API_URL ? 'text-green-600' : 'text-red-500'}>
                OCP {credentials.OCP_HUB_API_URL ? 'OK' : 'Missing'}
              </span>
            </div>
          )}
        </div>
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="block text-xs text-gray-500 mb-1">State Machine</label>
            <select
              className="border border-gray-300 rounded-md px-3 py-1.5 text-sm bg-white"
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
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-md text-sm border border-gray-300 transition"
            onClick={handlePreview}
          >
            <EyeIcon className="h-4 w-4" />
            Preview Plan
          </button>
          <button
            className="inline-flex items-center gap-1.5 px-4 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium transition disabled:opacity-50"
            onClick={handleLaunch}
            disabled={launching || !credentialsLoaded || !envName}
          >
            <PlayIcon className="h-4 w-4" />
            {launching ? 'Launching...' : 'Launch'}
          </button>
        </div>
      </div>

      {/* Variables Panel */}
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
        <button
          className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-gray-50 transition"
          onClick={() => setShowVars(!showVars)}
        >
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-gray-700">Variables</h3>
            <span className="text-xs text-gray-400">{Object.keys(vars).length} configured</span>
          </div>
          <span className="text-gray-400 text-xs">{showVars ? 'Hide' : 'Show'}</span>
        </button>
        {showVars && (
          <div className="px-4 pb-4 border-t border-gray-100">
            <div className="space-y-1.5 mt-3">
              {Object.entries(vars).map(([key, val]) => {
                const isSecret = /secret|password|key/i.test(key) && !/region|namespace|version|cidr|count|prefix|name/i.test(key);
                return (
                  <div key={key} className="flex items-center gap-2">
                    <input
                      type="text"
                      className="border border-gray-200 rounded px-2 py-1 text-xs font-mono w-48 bg-gray-50"
                      defaultValue={key}
                      onBlur={(e) => handleRenameVar(key, e.target.value)}
                    />
                    <span className="text-gray-300">=</span>
                    <input
                      type={isSecret ? 'password' : 'text'}
                      className="border border-gray-200 rounded px-2 py-1 text-xs font-mono flex-1"
                      value={val}
                      onChange={(e) => handleVarChange(key, e.target.value)}
                    />
                    <button
                      className="text-gray-300 hover:text-red-500 text-xs px-1 transition"
                      onClick={() => handleRemoveVar(key)}
                      title="Remove"
                    >
                      x
                    </button>
                  </div>
                );
              })}
            </div>
            <button
              className="mt-2 text-xs text-blue-600 hover:text-blue-800"
              onClick={handleAddVar}
            >
              + Add variable
            </button>
          </div>
        )}
      </div>

      {/* Execution Plan Preview */}
      {showPlan && plan && (
        <div className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-700">Execution Plan (Dry Run)</h3>
            <button className="text-xs text-gray-400 hover:text-gray-600" onClick={() => setShowPlan(false)}>close</button>
          </div>
          <div className="grid grid-cols-2 gap-4 mb-3 text-xs">
            <div className="bg-gray-50 rounded p-2">
              <span className="text-gray-500">Sequential estimate:</span>{' '}
              <span className="font-semibold">{formatElapsed(plan.estimated_time_sequential_seconds)}</span>
            </div>
            <div className="bg-green-50 rounded p-2">
              <span className="text-gray-500">Parallel estimate:</span>{' '}
              <span className="font-semibold text-green-700">{formatElapsed(plan.estimated_time_parallel_seconds)}</span>
              <span className="text-green-600 ml-1">
                (saves ~{formatElapsed(plan.estimated_time_sequential_seconds - plan.estimated_time_parallel_seconds)})
              </span>
            </div>
          </div>
          <div className="space-y-2">
            {(plan.steps || []).map((step, i) => (
              <div key={i} className={`flex items-center gap-3 text-xs p-2 rounded ${step.parallel ? 'bg-blue-50 ml-4 border-l-2 border-blue-300' : 'bg-gray-50'}`}>
                <span className="font-medium w-48">{step.name}</span>
                <span className="font-mono text-gray-500 w-64">{step.task_file}</span>
                <span className="text-gray-400">timeout: {formatElapsed(step.timeout_seconds)}</span>
                {step.parallel && <span className="text-blue-600 text-xs font-medium">PARALLEL</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Live / Selected Execution */}
      {selectedExecution && (
        <div className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h3 className="text-sm font-semibold text-gray-700">
                Execution: <span className="font-mono">{selectedExecution.execution_id}</span>
              </h3>
              <div className="flex items-center gap-3 mt-1">
                <StatusBadge status={selectedExecution.status} />
                <span className="text-xs text-gray-500">
                  Mode: {selectedExecution.mode} | Elapsed: {formatElapsed(selectedExecution.elapsed_seconds)}
                </span>
              </div>
            </div>
            {selectedExecution.status === 'running' && (
              <button
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-red-100 hover:bg-red-200 text-red-700 rounded-md text-sm transition"
                onClick={() => handleCancel(selectedExecution.execution_id)}
              >
                <StopIcon className="h-4 w-4" />
                Cancel
              </button>
            )}
          </div>
          <ExecutionGraph execution={selectedExecution} />
          {selectedExecution.error && (
            <div className="mt-3 bg-red-50 border border-red-200 rounded p-2 text-sm text-red-700">
              {selectedExecution.error}
            </div>
          )}
        </div>
      )}

      {/* Execution History */}
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-gray-700">Execution History</h3>
          <button
            className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1"
            onClick={fetchExecutions}
          >
            <ArrowPathIcon className="h-3.5 w-3.5" /> Refresh
          </button>
        </div>
        {executions.length === 0 ? (
          <div className="p-6 text-center text-sm text-gray-400">
            No executions yet. Launch one above to get started.
          </div>
        ) : (
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="px-3 py-2 text-xs font-medium text-gray-500">ID</th>
                <th className="px-3 py-2 text-xs font-medium text-gray-500">State Machine</th>
                <th className="px-3 py-2 text-xs font-medium text-gray-500">Status</th>
                <th className="px-3 py-2 text-xs font-medium text-gray-500">Elapsed</th>
                <th className="px-3 py-2 text-xs font-medium text-gray-500">Started</th>
              </tr>
            </thead>
            <tbody>
              {executions.map((exec) => (
                <ExecutionHistoryRow
                  key={exec.execution_id}
                  exec={exec}
                  onSelect={(id) => fetchExecutionDetail(id)}
                  isSelected={selectedExecution?.execution_id === exec.execution_id}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
