import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  ArrowPathIcon,
  CheckCircleIcon,
  XCircleIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  PlayIcon,
  MagnifyingGlassIcon,
  ExclamationTriangleIcon,
  ArrowUpIcon,
  LockClosedIcon,
  InformationCircleIcon,
  PlusIcon,
  ClockIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { buildApiUrl } from '../config/api';

// Suite icon map
const suiteIcons = {
  server: (
    <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M2 5a2 2 0 012-2h12a2 2 0 012 2v2a2 2 0 01-2 2H4a2 2 0 01-2-2V5zm14 1a1 1 0 11-2 0 1 1 0 012 0zM2 13a2 2 0 012-2h12a2 2 0 012 2v2a2 2 0 01-2 2H4a2 2 0 01-2-2v-2zm14 1a1 1 0 11-2 0 1 1 0 012 0z" clipRule="evenodd" />
    </svg>
  ),
  shield: (
    <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M10 1.944A11.954 11.954 0 012.166 5C2.056 5.649 2 6.319 2 7c0 5.225 3.34 9.67 8 11.317C14.66 16.67 18 12.225 18 7c0-.682-.057-1.35-.166-2.001A11.954 11.954 0 0110 1.944zM11 14a1 1 0 11-2 0 1 1 0 012 0zm0-7a1 1 0 10-2 0v3a1 1 0 102 0V7z" clipRule="evenodd" />
    </svg>
  ),
  scale: (
    <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M10 2a1 1 0 011 1v1.323l3.954 1.582 1.599-.8a1 1 0 01.894 1.79l-1.233.616 1.738 5.42a1 1 0 01-.285 1.05A3.989 3.989 0 0115 15a3.989 3.989 0 01-2.667-1.019 1 1 0 01-.285-1.05l1.715-5.349L11 6.477V16h2a1 1 0 110 2H7a1 1 0 110-2h2V6.477L6.237 7.582l1.715 5.349a1 1 0 01-.285 1.05A3.989 3.989 0 015 15a3.989 3.989 0 01-2.667-1.019 1 1 0 01-.285-1.05l1.738-5.42-1.233-.617a1 1 0 01.894-1.788l1.599.799L9 4.323V3a1 1 0 011-1z" clipRule="evenodd" />
    </svg>
  ),
  'arrow-up': <ArrowUpIcon className="h-5 w-5" />,
  cpu: (
    <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M6 2a2 2 0 00-2 2v12a2 2 0 002 2h8a2 2 0 002-2V4a2 2 0 00-2-2H6zm4 3a1 1 0 011 1v4.586l1.707-1.707a1 1 0 111.414 1.414l-3.414 3.414a1 1 0 01-1.414 0L5.879 10.293a1 1 0 111.414-1.414L9 10.586V6a1 1 0 011-1z" clipRule="evenodd" />
    </svg>
  ),
  globe: (
    <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM4.332 8.027a6.012 6.012 0 011.912-2.706C6.512 5.73 6.974 6 7.5 6A1.5 1.5 0 019 7.5V8a2 2 0 004 0 2 2 0 011.523-1.943A5.977 5.977 0 0116 10c0 .34-.028.675-.083 1H15a2 2 0 00-2 2v2.197A5.973 5.973 0 0110 16v-2a2 2 0 00-2-2 2 2 0 01-2-2 2 2 0 00-1.668-1.973z" clipRule="evenodd" />
    </svg>
  ),
  database: (
    <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
      <path d="M3 12v3c0 1.657 3.134 3 7 3s7-1.343 7-3v-3c0 1.657-3.134 3-7 3s-7-1.343-7-3z" />
      <path d="M3 7v3c0 1.657 3.134 3 7 3s7-1.343 7-3V7c0 1.657-3.134 3-7 3S3 8.657 3 7z" />
      <path d="M17 5c0 1.657-3.134 3-7 3S3 6.657 3 5s3.134-3 7-3 7 1.343 7 3z" />
    </svg>
  ),
  tag: (
    <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M17.707 9.293a1 1 0 010 1.414l-7 7a1 1 0 01-1.414 0l-7-7A.997.997 0 012 10V5a3 3 0 013-3h5c.256 0 .512.098.707.293l7 7zM5 6a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
    </svg>
  ),
  wrench: (
    <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clipRule="evenodd" />
    </svg>
  ),
};

const suiteGradients = {
  'cluster-config': 'from-blue-500 to-indigo-600',
  'security-auth': 'from-red-500 to-rose-600',
  'machine-pool-scaling': 'from-emerald-500 to-teal-600',
  'version-lifecycle': 'from-violet-500 to-purple-600',
  'node-config': 'from-amber-500 to-orange-600',
  'network-connectivity': 'from-cyan-500 to-blue-600',
  'storage-registry': 'from-pink-500 to-rose-500',
  'domain-useragent': 'from-slate-500 to-gray-600',
  'day2-operations': 'from-fuchsia-500 to-purple-600',
};

const phaseColors = {
  Day1: { bg: 'bg-emerald-100', text: 'text-emerald-700' },
  Day2: { bg: 'bg-blue-100', text: 'text-blue-700' },
};

// ============================================================================
// Feature Card Component
// ============================================================================
const FeatureCard = ({ feature, clusterStatus, onToggle, selectedActions }) => {
  const isSelected = selectedActions.some(a => a.feature_id === feature.id);
  const currentAction = selectedActions.find(a => a.feature_id === feature.id);
  const isMutable = feature.mutable;
  const isDestructive = feature.destructive;

  const getLiveValue = () => {
    if (!clusterStatus?.cluster_found) return null;
    switch (feature.id) {
      case 'control_plane_upgrade': return clusterStatus.version;
      case 'channel_group': return clusterStatus.channel_group;
      case 'domain_prefix': return clusterStatus.domain_prefix;
      case 'additional_tags': return JSON.stringify(clusterStatus.additional_tags || {});
      default: return null;
    }
  };

  const liveValue = getLiveValue();
  // Machine pool upgrade uses the machine pool's available upgrades, not the control plane's
  const availableUpgrades = feature.id === 'machine_pool_upgrade'
    ? (clusterStatus?.machine_pools?.[0]?.available_upgrades || [])
    : (clusterStatus?.available_upgrades || []);

  return (
    <div className={`relative rounded-lg border transition-all duration-200 ${
      isSelected
        ? isDestructive
          ? 'border-red-300 bg-gradient-to-r from-red-50 to-white ring-2 ring-red-100 shadow-md'
          : 'border-blue-300 bg-gradient-to-r from-blue-50 to-white ring-2 ring-blue-100 shadow-md'
        : isMutable
          ? 'border-gray-200 bg-white hover:shadow-sm hover:border-gray-300'
          : 'border-gray-100 bg-gray-50/50'
    }`}>
      <div className="px-4 py-3">
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 mt-0.5">
            {isMutable ? (
              <input
                type="checkbox"
                checked={isSelected}
                onChange={() => onToggle(feature)}
                className={`h-4 w-4 rounded border-gray-300 focus:ring-2 ${
                  isDestructive ? 'text-red-600 focus:ring-red-500' : 'text-blue-600 focus:ring-blue-500'
                }`}
              />
            ) : (
              <LockClosedIcon className="h-4 w-4 text-gray-300 mt-0.5" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-gray-900">{feature.name}</span>
              {!isMutable && <span className="text-[9px] px-1.5 py-0.5 bg-gray-100 text-gray-500 rounded-full font-semibold uppercase tracking-wider">Immutable</span>}
              {isDestructive && <span className="text-[9px] px-1.5 py-0.5 bg-red-100 text-red-600 rounded-full font-semibold uppercase tracking-wider">Destructive</span>}
            </div>
            <p className="text-xs text-gray-500 mt-0.5">{feature.description}</p>
            {liveValue !== null && (
              <div className="flex items-center gap-1.5 mt-1.5">
                <span className="text-[10px] text-gray-400 uppercase tracking-wider font-medium">Current:</span>
                <span className="text-xs font-mono px-1.5 py-0.5 bg-slate-100 text-slate-700 rounded border border-slate-200">{liveValue || '(empty)'}</span>
              </div>
            )}
            {feature.type === 'version' && availableUpgrades.length > 0 && (
              <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                <span className="text-[10px] text-gray-400 uppercase tracking-wider font-medium">Available:</span>
                {availableUpgrades.slice(0, 5).map((v) => (
                  <button key={v} onClick={() => onToggle(feature, v)}
                    className={`text-[11px] font-mono px-2 py-0.5 rounded-md border transition-colors ${
                      currentAction?.target_value === v
                        ? 'bg-indigo-100 border-blue-300 text-blue-700 font-semibold'
                        : 'bg-white border-gray-200 text-gray-600 hover:bg-blue-50 hover:border-blue-200'
                    }`}>{v}</button>
                ))}
              </div>
            )}
            {isSelected && feature.type === 'select' && (
              <div className="mt-2">
                <select value={currentAction?.target_value || feature.default}
                  onChange={(e) => onToggle(feature, e.target.value)}
                  className="text-xs border border-gray-300 rounded-md px-2 py-1.5 focus:ring-2 focus:ring-blue-500">
                  {(feature.options || []).map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                </select>
              </div>
            )}
            {isSelected && feature.type === 'number' && (
              <div className="mt-2">
                <input type="number" value={currentAction?.target_value ?? feature.default}
                  onChange={(e) => onToggle(feature, parseInt(e.target.value) || 0)}
                  className="text-xs border border-gray-300 rounded-md px-2 py-1.5 w-24 focus:ring-2 focus:ring-blue-500" />
              </div>
            )}
            {isSelected && feature.type === 'string' && (
              <div className="mt-2">
                <input type="text" value={currentAction?.target_value || ''} placeholder={feature.placeholder || ''}
                  onChange={(e) => onToggle(feature, e.target.value)}
                  className="text-xs border border-gray-300 rounded-md px-2 py-1.5 w-48 focus:ring-2 focus:ring-blue-500"
                  maxLength={feature.max_length} />
              </div>
            )}
            {isSelected && feature.type === 'key_value' && (
              <div className="mt-2">
                <textarea value={typeof currentAction?.target_value === 'object' ? JSON.stringify(currentAction.target_value, null, 2) : currentAction?.target_value || '{}'}
                  onChange={(e) => { try { onToggle(feature, JSON.parse(e.target.value)); } catch {} }}
                  placeholder='{"key": "value"}'
                  className="text-xs font-mono border border-gray-300 rounded-md px-2 py-1.5 w-64 h-16 focus:ring-2 focus:ring-blue-500" />
              </div>
            )}
            {isSelected && feature.type === 'range' && (
              <div className="mt-2 flex items-center gap-2">
                <label className="text-xs text-gray-500">Min:</label>
                <input type="number" value={currentAction?.target_value?.min ?? feature.default?.min ?? 1}
                  onChange={(e) => onToggle(feature, { ...currentAction?.target_value, min: parseInt(e.target.value) || 0 })}
                  className="text-xs border border-gray-300 rounded-md px-2 py-1.5 w-16 focus:ring-2 focus:ring-blue-500" />
                <label className="text-xs text-gray-500">Max:</label>
                <input type="number" value={currentAction?.target_value?.max ?? feature.default?.max ?? 3}
                  onChange={(e) => onToggle(feature, { ...currentAction?.target_value, max: parseInt(e.target.value) || 0 })}
                  className="text-xs border border-gray-300 rounded-md px-2 py-1.5 w-16 focus:ring-2 focus:ring-blue-500" />
              </div>
            )}
            {isSelected && feature.type === 'list' && (
              <div className="mt-2">
                <input type="text" value={Array.isArray(currentAction?.target_value) ? currentAction.target_value.join(', ') : ''}
                  onChange={(e) => onToggle(feature, e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                  placeholder="item1, item2, item3"
                  className="text-xs border border-gray-300 rounded-md px-2 py-1.5 w-64 focus:ring-2 focus:ring-blue-500" />
              </div>
            )}
          </div>
          <span className="text-[10px] px-2 py-0.5 bg-slate-100 text-slate-500 rounded-md font-mono border border-slate-200 flex-shrink-0">
            {feature.resource || 'Action'}
          </span>
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// Suite Accordion
// ============================================================================
const SuiteAccordion = ({ suite, isExpanded, onToggle, clusterStatus, selectedActions, onFeatureToggle }) => {
  const gradient = suiteGradients[suite.id] || 'from-gray-500 to-gray-600';
  const icon = suiteIcons[suite.icon] || suiteIcons.wrench;
  const phase = phaseColors[suite.phase] || phaseColors.Day1;
  const selectedCount = suite.features.filter(f => selectedActions.some(a => a.feature_id === f.id)).length;
  const mutableCount = suite.features.filter(f => f.mutable).length;

  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm hover:shadow-md transition-all duration-200 overflow-hidden">
      <button onClick={onToggle} className="w-full flex items-center gap-4 px-5 py-4 text-left hover:bg-blue-50/50 transition-colors">
        <div className={`w-10 h-10 rounded-lg bg-gradient-to-br ${gradient} flex items-center justify-center text-white flex-shrink-0 shadow-md ring-1 ring-white/50`}>{icon}</div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold text-gray-900">{suite.name}</h3>
            <span className={`text-[10px] px-2 py-0.5 rounded-md font-bold uppercase tracking-tight ${phase.bg} ${phase.text}`}>{suite.phase}</span>
            {selectedCount > 0 && <span className="text-[10px] px-2 py-0.5 bg-blue-100 text-blue-700 rounded-md font-bold">{selectedCount} selected</span>}
          </div>
          <p className="text-xs text-gray-500 mt-0.5">{suite.description}</p>
          <div className="flex items-center gap-3 mt-1">
            <span className="text-[10px] text-gray-400">{suite.features.length} features ({mutableCount} mutable)</span>
            <span className="text-[10px] text-gray-300">|</span>
            <span className="text-[10px] text-gray-400">{suite.category}</span>
          </div>
        </div>
        {isExpanded ? <ChevronDownIcon className="h-5 w-5 text-gray-400" /> : <ChevronRightIcon className="h-5 w-5 text-gray-400" />}
      </button>
      {isExpanded && (
        <div className="px-5 pb-4 pt-1 space-y-2 border-t border-gray-100">
          {suite.features.map((feature) => (
            <FeatureCard key={feature.id} feature={feature} clusterStatus={clusterStatus} selectedActions={selectedActions} onToggle={onFeatureToggle} />
          ))}
        </div>
      )}
    </div>
  );
};

// ============================================================================
// Live Execution Panel — polls job status and shows logs
// ============================================================================
const ExecutionPanel = ({ results, clusterStatus, onClose, onComplete }) => {
  const [liveResults, setLiveResults] = useState(results);
  const [logs, setLogs] = useState({});
  const logsRef = useRef(null);
  const [activeJobId, setActiveJobId] = useState(null);

  // Find running jobs and poll them
  useEffect(() => {
    const runningJobs = (liveResults || []).filter(r => r.status === 'running' && r.job_id);
    if (runningJobs.length === 0) return;

    // Auto-select first running job for log display
    if (!activeJobId && runningJobs.length > 0) {
      setActiveJobId(runningJobs[0].job_id);
    }

    const interval = setInterval(async () => {
      let allDone = true;
      const updated = [...liveResults];

      for (let i = 0; i < updated.length; i++) {
        const r = updated[i];
        if (r.status !== 'running' || !r.job_id) continue;

        try {
          const [statusRes, logsRes] = await Promise.all([
            fetch(buildApiUrl(`/api/jobs/${r.job_id}`)),
            fetch(buildApiUrl(`/api/jobs/${r.job_id}/logs`)),
          ]);

          if (statusRes.ok) {
            const job = await statusRes.json();
            if (job.status === 'completed') {
              updated[i] = { ...r, status: 'completed', message: `${r.message} - Done` };
            } else if (job.status === 'failed') {
              updated[i] = { ...r, status: 'failed', message: `${r.message} - Failed` };
            } else {
              allDone = false;
            }
          } else if (statusRes.status === 404) {
            updated[i] = { ...r, status: 'completed', message: `${r.message} - Done` };
          } else {
            allDone = false;
          }

          if (logsRes.ok) {
            const logsData = await logsRes.json();
            setLogs(prev => ({ ...prev, [r.job_id]: (logsData.logs || []).filter(l => l.trim()) }));
          }
        } catch {
          allDone = false;
        }
      }

      setLiveResults(updated);
      if (allDone && onComplete) onComplete();
    }, 3000);

    return () => clearInterval(interval);
  }, [liveResults, activeJobId, onComplete]);

  // Auto-scroll logs
  useEffect(() => {
    if (logsRef.current) {
      logsRef.current.scrollTop = logsRef.current.scrollHeight;
    }
  }, [logs, activeJobId]);

  const activeLog = activeJobId ? (logs[activeJobId] || []) : [];
  const hasRunning = (liveResults || []).some(r => r.status === 'running');

  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-lg overflow-hidden">
      {/* Header */}
      <div className={`flex items-center justify-between px-5 py-3 ${hasRunning ? 'bg-gradient-to-r from-blue-600 to-indigo-600' : 'bg-gradient-to-r from-emerald-600 to-teal-600'}`}>
        <div className="flex items-center gap-2">
          {hasRunning ? <ArrowPathIcon className="h-4 w-4 text-white animate-spin" /> : <CheckCircleIcon className="h-4 w-4 text-white" />}
          <span className="text-sm font-semibold text-white">
            {hasRunning ? 'Executing Actions...' : 'Execution Complete'}
          </span>
          <span className="text-xs text-white/70 ml-2">
            {(liveResults || []).filter(r => r.status === 'completed').length}/{(liveResults || []).length} done
          </span>
        </div>
        <button onClick={onClose} className="p-1 text-white/70 hover:text-white transition-colors">
          <XMarkIcon className="h-4 w-4" />
        </button>
      </div>

      {/* Action results list */}
      <div className="px-4 py-3 space-y-2 border-b border-gray-200">
        {(liveResults || []).map((result, i) => (
          <div key={i}
            onClick={() => result.job_id && setActiveJobId(result.job_id)}
            className={`flex items-center gap-3 px-3 py-2 rounded-lg border transition-all ${
              result.job_id === activeJobId ? 'border-blue-300 bg-blue-50 ring-1 ring-blue-200' :
              result.status === 'error' || result.status === 'failed' ? 'border-red-200 bg-red-50' :
              result.status === 'completed' ? 'border-emerald-200 bg-emerald-50' :
              result.status === 'running' ? 'border-blue-200 bg-blue-50' :
              'border-gray-200 bg-gray-50'
            } ${result.job_id ? 'cursor-pointer hover:shadow-sm' : ''}`}
          >
            {result.status === 'running' ? <ArrowPathIcon className="h-4 w-4 text-blue-500 animate-spin flex-shrink-0" /> :
             result.status === 'completed' ? <CheckCircleIcon className="h-4 w-4 text-emerald-500 flex-shrink-0" /> :
             result.status === 'failed' || result.status === 'error' ? <XCircleIcon className="h-4 w-4 text-red-500 flex-shrink-0" /> :
             <ClockIcon className="h-4 w-4 text-gray-400 flex-shrink-0" />}
            <div className="flex-1 min-w-0">
              <span className="text-sm font-medium text-gray-900">{result.feature_id}</span>
              {result.target_value && (
                <span className="text-xs font-mono ml-2">
                  {result.feature_id === 'machine_pool_upgrade' && clusterStatus?.machine_pools?.[0]?.version
                    ? <span className="text-gray-400">{clusterStatus.machine_pools[0].version}</span>
                    : result.feature_id === 'control_plane_upgrade' && clusterStatus?.version
                    ? <span className="text-gray-400">{clusterStatus.version}</span>
                    : null}
                  {(result.feature_id === 'machine_pool_upgrade' || result.feature_id === 'control_plane_upgrade') && <span className="text-gray-400 mx-1">→</span>}
                  <span className="text-blue-600 font-semibold">{result.target_value}</span>
                </span>
              )}
              {!result.target_value && <span className="text-xs text-gray-500 ml-2">{result.message}</span>}
            </div>
            <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase ${
              result.status === 'running' ? 'bg-blue-100 text-blue-600' :
              result.status === 'completed' ? 'bg-emerald-100 text-emerald-600' :
              result.status === 'failed' || result.status === 'error' ? 'bg-red-100 text-red-600' :
              'bg-gray-100 text-gray-500'
            }`}>{result.status}</span>
          </div>
        ))}
      </div>

      {/* Live log output */}
      {activeJobId && activeLog.length > 0 && (
        <div>
          <div className="px-4 py-2 bg-slate-800 flex items-center justify-between">
            <span className="text-xs text-slate-400 font-mono">Job: {activeJobId.slice(0, 8)}</span>
            <span className="text-xs text-slate-500">{activeLog.length} lines</span>
          </div>
          <div ref={logsRef} className="bg-gray-900 text-gray-100 p-3 max-h-64 overflow-y-auto font-mono text-xs leading-relaxed">
            {activeLog.map((line, i) => (
              <div key={i} className={
                line.includes('TASK [') ? 'text-cyan-400 mt-1' :
                line.includes('ok:') ? 'text-green-400' :
                line.includes('changed:') ? 'text-yellow-400' :
                line.includes('fatal:') || line.includes('FAILED') ? 'text-red-400 font-bold' :
                line.includes('PLAY RECAP') ? 'text-cyan-300 mt-2 font-bold' :
                line.includes('skipping:') ? 'text-gray-500' :
                line.includes('AGENT-SIDECAR') ? 'text-yellow-300' :
                'text-gray-300'
              }>{line}</div>
            ))}
            {hasRunning && <div className="text-blue-400 animate-pulse mt-1">&#9611;</div>}
          </div>
        </div>
      )}
    </div>
  );
};

// ============================================================================
// Action History Panel
// ============================================================================
const HistoryPanel = ({ clusterName, isOpen, onClose }) => {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    const url = clusterName
      ? buildApiUrl(`/api/cluster-actions/history?cluster_name=${clusterName}`)
      : buildApiUrl('/api/cluster-actions/history');
    fetch(url)
      .then(r => r.ok ? r.json() : { history: [] })
      .then(data => setHistory(data.history || []))
      .catch(() => setHistory([]))
      .finally(() => setLoading(false));
  }, [isOpen, clusterName]);

  if (!isOpen) return null;

  const formatTime = (ts) => {
    if (!ts) return '';
    const d = new Date(ts);
    return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 bg-gradient-to-r from-slate-700 to-slate-800 border-b border-gray-200">
        <div className="flex items-center gap-2">
          <ClockIcon className="h-4 w-4 text-slate-300" />
          <span className="text-sm font-semibold text-white">Action History</span>
          {clusterName && <span className="text-xs text-slate-400 ml-1">- {clusterName}</span>}
          <span className="text-[10px] px-1.5 py-0.5 bg-slate-600 text-slate-300 rounded-full font-bold">{history.length}</span>
        </div>
        <button onClick={onClose} className="p-1 text-slate-400 hover:text-white transition-colors">
          <XMarkIcon className="h-4 w-4" />
        </button>
      </div>
      <div className="max-h-72 overflow-y-auto">
        {loading ? (
          <div className="text-center py-8"><ArrowPathIcon className="h-5 w-5 text-gray-400 animate-spin mx-auto" /></div>
        ) : history.length === 0 ? (
          <div className="text-center py-8"><p className="text-xs text-gray-400">No actions recorded yet</p></div>
        ) : (
          <div className="divide-y divide-gray-100">
            {history.map((entry, i) => (
              <div key={i} className="px-4 py-2.5 hover:bg-gray-50 transition-colors">
                <div className="flex items-center gap-2">
                  {entry.status === 'completed' ? <CheckCircleIcon className="h-3.5 w-3.5 text-emerald-500 flex-shrink-0" /> :
                   entry.status === 'running' ? <ArrowPathIcon className="h-3.5 w-3.5 text-blue-500 flex-shrink-0" /> :
                   entry.status === 'error' || entry.status === 'failed' ? <XCircleIcon className="h-3.5 w-3.5 text-red-500 flex-shrink-0" /> :
                   <ClockIcon className="h-3.5 w-3.5 text-gray-400 flex-shrink-0" />}
                  <span className="text-sm font-medium text-gray-900">{entry.feature_name}</span>
                  <span className="text-[10px] text-gray-400 ml-auto">{formatTime(entry.timestamp)}</span>
                </div>
                <div className="flex items-center gap-3 mt-0.5 ml-5">
                  <span className="text-xs text-gray-500">{entry.cluster_name}</span>
                  {entry.target_value && <span className="text-[10px] font-mono px-1.5 py-0 bg-gray-100 text-gray-600 rounded">{String(entry.target_value).slice(0, 30)}</span>}
                  {entry.message && <span className="text-[10px] text-gray-400 truncate max-w-[200px]">{entry.message}</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

// ============================================================================
// Spec Builder Panel
// ============================================================================
const SpecBuilder = ({ clusterName, namespace, clusterStatus, onExecute, onClose }) => {
  const [specs, setSpecs] = useState([]);
  const [selectedSpec, setSelectedSpec] = useState(null);
  const [specData, setSpecData] = useState(null);
  const [plan, setPlan] = useState(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [overrides, setOverrides] = useState({});
  const [activeTab, setActiveTab] = useState('profiles'); // profiles | custom

  // Load available specs
  useEffect(() => {
    fetch(buildApiUrl('/api/cluster-specs'))
      .then(r => r.ok ? r.json() : { specs: [] })
      .then(data => setSpecs(data.specs || []))
      .catch(() => setSpecs([]));
  }, []);

  // Load spec details when selected
  useEffect(() => {
    if (!selectedSpec) { setSpecData(null); setPlan(null); return; }
    fetch(buildApiUrl(`/api/cluster-specs/${selectedSpec}`))
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.success) setSpecData(data.spec);
      })
      .catch(() => setSpecData(null));
  }, [selectedSpec]);

  const generatePlan = async () => {
    if (!specData) return;
    setPlanLoading(true);
    setPlan(null);
    try {
      const finalOverrides = { ...overrides };
      if (clusterName && !finalOverrides.cluster) finalOverrides.cluster = clusterName;
      if (namespace && !finalOverrides.namespace) finalOverrides.namespace = namespace;

      const res = await fetch(buildApiUrl('/api/cluster-specs/plan'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ spec: specData, overrides: finalOverrides }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.success) setPlan(data.plan);
      }
    } catch (e) { console.error('Plan failed:', e); }
    finally { setPlanLoading(false); }
  };

  const executeSpec = async () => {
    if (!specData) return;
    setExecuting(true);
    try {
      const finalOverrides = { ...overrides };
      if (clusterName && !finalOverrides.cluster) finalOverrides.cluster = clusterName;
      if (namespace && !finalOverrides.namespace) finalOverrides.namespace = namespace;

      const res = await fetch(buildApiUrl('/api/cluster-specs/execute'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ spec: specData, overrides: finalOverrides }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.success && onExecute) {
          onExecute(data.results);
        }
      }
    } catch (e) { console.error('Execute failed:', e); }
    finally { setExecuting(false); }
  };

  const actionIcons = { create: '🚀', upgrade: '⬆️', apply: '🔧', delete: '🗑️', test: '🧪' };
  const actionColors = {
    create: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    upgrade: 'bg-blue-100 text-blue-700 border-blue-200',
    apply: 'bg-amber-100 text-amber-700 border-amber-200',
    delete: 'bg-red-100 text-red-700 border-red-200',
    test: 'bg-purple-100 text-purple-700 border-purple-200',
  };

  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 bg-gradient-to-r from-violet-600 to-purple-600">
        <div className="flex items-center gap-2">
          <span className="text-sm">📋</span>
          <span className="text-sm font-semibold text-white">Cluster Specs</span>
          <span className="text-xs text-white/60 ml-1">Declarative cluster lifecycle</span>
        </div>
        <button onClick={onClose} className="p-1 text-white/70 hover:text-white transition-colors">
          <XMarkIcon className="h-4 w-4" />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-200">
        {[['profiles', 'Profiles'], ['custom', 'Custom Spec']].map(([id, label]) => (
          <button key={id} onClick={() => setActiveTab(id)}
            className={`flex-1 text-xs font-medium py-2.5 transition-colors ${
              activeTab === id ? 'text-violet-700 border-b-2 border-violet-600 bg-violet-50' : 'text-gray-500 hover:text-gray-700'
            }`}>{label}</button>
        ))}
      </div>

      <div className="p-4 space-y-4">
        {activeTab === 'profiles' && (
          <>
            {/* Spec cards grouped by category (Day2 only — create profiles live in New Cluster) */}
            {[['features', 'Features', 'Individual actions'], ['workflows', 'Workflows', 'Multi-step sequences']].map(([cat, label, desc]) => {
              const catSpecs = specs.filter(s => s.category === cat);
              if (catSpecs.length === 0) return null;
              return (
                <div key={cat}>
                  <div className="flex items-baseline gap-2 mb-2">
                    <h4 className="text-xs font-semibold text-gray-700 uppercase tracking-wider">{label}</h4>
                    <span className="text-[10px] text-gray-400">{desc}</span>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    {catSpecs.map(spec => (
                      <button key={spec.id} onClick={() => setSelectedSpec(spec.id)}
                        className={`text-left p-3 rounded-xl border-2 transition-all ${
                          selectedSpec === spec.id
                            ? 'border-violet-400 bg-violet-50 ring-1 ring-violet-200 shadow-sm'
                            : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm'
                        }`}>
                        <div className="flex items-center gap-2">
                          <span className="text-base">{actionIcons[spec.action] || '▶️'}</span>
                          <span className="text-sm font-semibold text-gray-900">{spec.name}</span>
                        </div>
                        <div className="flex items-center gap-2 mt-1.5">
                          <span className={`text-[10px] px-1.5 py-0.5 rounded-full border font-semibold ${actionColors[spec.action] || 'bg-gray-100 text-gray-600'}`}>
                            {spec.action}
                          </span>
                          {spec.version && <span className="text-[10px] font-mono text-gray-500">v{spec.version}</span>}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}

            {/* Overrides */}
            {selectedSpec && specData && (
              <div className="space-y-3 bg-gray-50 rounded-xl p-4 border border-gray-200">
                <h4 className="text-xs font-semibold text-gray-700 uppercase tracking-wider">Overrides</h4>
                <div className="grid grid-cols-2 gap-3">
                  {specData.spec?.action === 'create' && (
                    <div>
                      <label className="text-[10px] font-medium text-gray-500 uppercase">Name Prefix</label>
                      <input type="text" placeholder="e.g., test1"
                        value={overrides.name_prefix || ''} onChange={e => setOverrides(prev => ({ ...prev, name_prefix: e.target.value }))}
                        className="w-full text-sm border border-gray-300 rounded-lg px-2.5 py-1.5 mt-0.5 focus:ring-2 focus:ring-violet-500" />
                    </div>
                  )}
                  {['upgrade', 'apply', 'delete'].includes(specData.spec?.action) && (
                    <div>
                      <label className="text-[10px] font-medium text-gray-500 uppercase">Cluster</label>
                      <input type="text" placeholder={clusterName || 'cluster name'}
                        value={overrides.cluster || clusterName || ''} onChange={e => setOverrides(prev => ({ ...prev, cluster: e.target.value }))}
                        className="w-full text-sm border border-gray-300 rounded-lg px-2.5 py-1.5 mt-0.5 focus:ring-2 focus:ring-violet-500" />
                    </div>
                  )}
                  {specData.spec?.action === 'upgrade' && (
                    <div>
                      <label className="text-[10px] font-medium text-gray-500 uppercase">Target Version</label>
                      {clusterStatus?.available_upgrades?.length > 0 ? (
                        <select value={overrides.version || ''} onChange={e => setOverrides(prev => ({ ...prev, version: e.target.value }))}
                          className="w-full text-sm border border-gray-300 rounded-lg px-2.5 py-1.5 mt-0.5 focus:ring-2 focus:ring-violet-500">
                          <option value="">Select version...</option>
                          {clusterStatus.available_upgrades.map(v => <option key={v} value={v}>{v}</option>)}
                        </select>
                      ) : (
                        <input type="text" placeholder="4.20.12"
                          value={overrides.version || ''} onChange={e => setOverrides(prev => ({ ...prev, version: e.target.value }))}
                          className="w-full text-sm border border-gray-300 rounded-lg px-2.5 py-1.5 mt-0.5 focus:ring-2 focus:ring-violet-500" />
                      )}
                    </div>
                  )}
                  <div>
                    <label className="text-[10px] font-medium text-gray-500 uppercase">Region</label>
                    <select value={overrides.region || specData.spec?.region || 'us-west-2'}
                      onChange={e => setOverrides(prev => ({ ...prev, region: e.target.value }))}
                      className="w-full text-sm border border-gray-300 rounded-lg px-2.5 py-1.5 mt-0.5 focus:ring-2 focus:ring-violet-500">
                      {['us-west-2', 'us-east-1', 'us-east-2', 'eu-west-1', 'ap-southeast-1'].map(r =>
                        <option key={r} value={r}>{r}</option>
                      )}
                    </select>
                  </div>
                </div>

                {/* Show spec YAML preview */}
                {specData.spec?.actions && specData.spec.actions.length > 0 && (
                  <div className="mt-3">
                    <label className="text-[10px] font-medium text-gray-500 uppercase">Action Sequence</label>
                    <div className="mt-1 space-y-1">
                      {specData.spec.actions.map((a, i) => (
                        <div key={i} className="flex items-center gap-2 text-xs text-gray-700">
                          <span className="text-gray-400 font-mono w-4 text-right">{i + 1}.</span>
                          <span className="font-medium">{a.feature}</span>
                          {a.value && <span className="font-mono text-gray-500">= {typeof a.value === 'object' ? JSON.stringify(a.value) : String(a.value)}</span>}
                          {a.wait === false && <span className="text-[9px] px-1 bg-amber-100 text-amber-700 rounded">no-wait</span>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {specData.spec?.features && Object.keys(specData.spec.features).length > 0 && (
                  <div className="mt-3">
                    <label className="text-[10px] font-medium text-gray-500 uppercase">Features</label>
                    <div className="flex flex-wrap gap-1.5 mt-1">
                      {Object.entries(specData.spec.features).map(([k, v]) => (
                        <span key={k} className="text-[10px] px-2 py-0.5 bg-white border border-gray-200 rounded-full font-mono">
                          {k}={typeof v === 'object' ? '...' : String(v)}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Plan preview */}
            {plan && (
              <div className="bg-slate-50 rounded-xl border border-slate-200 overflow-hidden">
                <div className="px-4 py-2 bg-slate-100 border-b border-slate-200">
                  <span className="text-xs font-semibold text-slate-700">Execution Plan ({plan.length} step{plan.length !== 1 ? 's' : ''})</span>
                </div>
                <div className="p-3 space-y-2">
                  {plan.map((step, i) => (
                    <div key={i} className="flex items-center gap-3 px-3 py-2 rounded-lg bg-white border border-slate-200">
                      <span className="text-sm">{step.type === 'playbook' ? '📦' : '🔧'}</span>
                      <div className="flex-1 min-w-0">
                        <span className="text-xs font-medium text-gray-900">{step.name}</span>
                        {step.depends_on && <span className="text-[10px] text-gray-400 ml-2">after {step.depends_on}</span>}
                      </div>
                      <span className="text-[9px] px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded-full uppercase font-semibold">{step.type}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {activeTab === 'custom' && (
          <div className="space-y-3">
            <p className="text-xs text-gray-500">Create specs via CLI or YAML files in <code className="bg-gray-100 px-1 rounded">specs/</code> directory:</p>
            <div className="bg-gray-900 rounded-xl p-4 font-mono text-xs text-gray-300 space-y-1 overflow-x-auto">
              <div><span className="text-gray-500"># Create from profile</span></div>
              <div><span className="text-emerald-400">./capa</span> create --profile default -e name_prefix=test1</div>
              <div className="mt-2"><span className="text-gray-500"># Upgrade (auto-sequences CP then MP)</span></div>
              <div><span className="text-emerald-400">./capa</span> upgrade -c {clusterName || 'cluster-name'} --version 4.20.12</div>
              <div className="mt-2"><span className="text-gray-500"># Apply Day2 actions from spec file</span></div>
              <div><span className="text-emerald-400">./capa</span> apply -f specs/day2-test.yml -c {clusterName || 'cluster-name'}</div>
              <div className="mt-2"><span className="text-gray-500"># Dry run (show plan only)</span></div>
              <div><span className="text-emerald-400">./capa</span> plan --profile upgrade -c {clusterName || 'cluster-name'} -v 4.20.12</div>
            </div>
          </div>
        )}

        {/* Action buttons */}
        <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
          {selectedSpec && specData && (
            <>
              <button onClick={generatePlan} disabled={planLoading}
                className="px-4 py-2 text-xs font-medium text-violet-700 bg-white border border-violet-300 rounded-lg hover:bg-violet-50 disabled:opacity-40 flex items-center gap-1.5">
                {planLoading ? <ArrowPathIcon className="h-3.5 w-3.5 animate-spin" /> : <MagnifyingGlassIcon className="h-3.5 w-3.5" />}
                Preview Plan
              </button>
              <button onClick={executeSpec} disabled={executing || !plan}
                className="px-5 py-2 text-xs font-semibold text-white bg-gradient-to-r from-violet-600 to-purple-600 rounded-lg hover:from-violet-700 hover:to-purple-700 disabled:opacity-40 flex items-center gap-1.5">
                {executing ? <><ArrowPathIcon className="h-3.5 w-3.5 animate-spin" /> Running...</> : <><PlayIcon className="h-3.5 w-3.5" /> Execute Spec</>}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// New Cluster Mode Panel
// ============================================================================
const NewClusterPanel = ({ registry, onClose, onProvision }) => {
  const [namePrefix, setNamePrefix] = useState('');
  const [selectedFeatures, setSelectedFeatures] = useState({});
  const [provisioning, setProvisioning] = useState(false);
  const [createSpecs, setCreateSpecs] = useState([]);
  const [selectedProfile, setSelectedProfile] = useState(null);

  const day1Suites = (registry?.suites || []).filter(s => s.phase === 'Day1');

  // Load create-only spec profiles
  useEffect(() => {
    fetch(buildApiUrl('/api/cluster-specs'))
      .then(r => r.ok ? r.json() : { specs: [] })
      .then(data => setCreateSpecs((data.specs || []).filter(s => s.action === 'create')))
      .catch(() => setCreateSpecs([]));
  }, []);

  const applyProfile = (specId) => {
    if (selectedProfile === specId) { setSelectedProfile(null); return; }
    setSelectedProfile(specId);
    fetch(buildApiUrl(`/api/cluster-specs/${specId}`))
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.success && data.spec?.spec?.features) {
          setSelectedFeatures(data.spec.spec.features);
        }
      })
      .catch(() => {});
  };

  const toggleFeature = (featureId, value) => {
    setSelectedFeatures(prev => {
      if (prev[featureId] !== undefined && value === undefined) {
        const updated = { ...prev };
        delete updated[featureId];
        return updated;
      }
      return { ...prev, [featureId]: value ?? true };
    });
  };

  const handleProvision = async () => {
    if (!namePrefix.trim()) return;
    setProvisioning(true);
    try {
      const res = await fetch(buildApiUrl('/api/cluster-actions/provision'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name_prefix: namePrefix,
          features: selectedFeatures,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        onProvision(data);
      }
    } catch (e) {
      console.error('Failed to provision:', e);
    } finally {
      setProvisioning(false);
    }
  };

  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-lg overflow-hidden">
      <div className="bg-gradient-to-r from-emerald-600 to-teal-600 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              <PlusIcon className="h-5 w-5" /> New Cluster
            </h3>
            <p className="text-emerald-200 text-sm mt-0.5">Configure Day1 features and provision a new ROSA HCP cluster</p>
          </div>
          <button onClick={onClose} className="p-1.5 text-emerald-200 hover:text-white transition-colors">
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>
      </div>

      <div className="p-6 space-y-4">
        {/* Name prefix */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Name Prefix</label>
          <input type="text" value={namePrefix} onChange={(e) => setNamePrefix(e.target.value)}
            placeholder="e.g., qe6 (creates qe6-rosa-hcp)"
            className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2.5 focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500" />
          {namePrefix && <p className="text-xs text-gray-400 mt-1">Cluster name: <span className="font-mono text-emerald-600">{namePrefix}-rosa-hcp</span></p>}
        </div>

        {/* Profile presets */}
        {createSpecs.length > 0 && (
          <div>
            <h4 className="text-sm font-semibold text-gray-700 mb-2">Start from Profile <span className="text-gray-400 font-normal">(optional)</span></h4>
            <div className="flex flex-wrap gap-2">
              {createSpecs.map(spec => (
                <button key={spec.id} onClick={() => applyProfile(spec.id)}
                  className={`text-xs px-3 py-1.5 rounded-lg border transition-all flex items-center gap-1.5 ${
                    selectedProfile === spec.id
                      ? 'border-emerald-400 bg-emerald-50 text-emerald-700 font-semibold ring-1 ring-emerald-200'
                      : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300 hover:bg-gray-50'
                  }`}>
                  <span>{spec.name}</span>
                  {spec.features.length > 0 && <span className="text-[9px] text-gray-400">({spec.features.length})</span>}
                </button>
              ))}
            </div>
            {selectedProfile && (
              <p className="text-[10px] text-emerald-600 mt-1.5">Profile applied — features pre-filled below. Customize as needed.</p>
            )}
          </div>
        )}

        {/* Day1 feature selection */}
        <div>
          <h4 className="text-sm font-semibold text-gray-700 mb-2">Day1 Features <span className="text-gray-400 font-normal">{selectedProfile ? '(from profile)' : '(optional)'}</span></h4>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {day1Suites.map(suite => (
              <div key={suite.id}>
                <p className="text-[10px] uppercase tracking-wider text-gray-400 font-semibold mb-1">{suite.name}</p>
                <div className="space-y-1 ml-2">
                  {suite.features.filter(f => !f.mutable || f.type !== 'action').map(feature => (
                    <div key={feature.id} className="flex items-center gap-2">
                      {feature.type === 'boolean' ? (
                        <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                          <input type="checkbox" checked={selectedFeatures[feature.id] || false}
                            onChange={(e) => toggleFeature(feature.id, e.target.checked)}
                            className="h-3.5 w-3.5 text-emerald-600 rounded border-gray-300" />
                          {feature.name}
                        </label>
                      ) : feature.type === 'select' ? (
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-gray-700">{feature.name}:</span>
                          <select value={selectedFeatures[feature.id] || feature.default}
                            onChange={(e) => toggleFeature(feature.id, e.target.value)}
                            className="text-xs border border-gray-300 rounded px-2 py-1">
                            {(feature.options || []).map(o => <option key={o} value={o}>{o}</option>)}
                          </select>
                        </div>
                      ) : feature.type === 'string' ? (
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-gray-700">{feature.name}:</span>
                          <input type="text" value={selectedFeatures[feature.id] || ''} placeholder={feature.placeholder || ''}
                            onChange={(e) => toggleFeature(feature.id, e.target.value)}
                            className="text-xs border border-gray-300 rounded px-2 py-1 w-32" maxLength={feature.max_length} />
                        </div>
                      ) : feature.type === 'number' ? (
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-gray-700">{feature.name}:</span>
                          <input type="number" value={selectedFeatures[feature.id] ?? feature.default}
                            onChange={(e) => toggleFeature(feature.id, parseInt(e.target.value) || 0)}
                            className="text-xs border border-gray-300 rounded px-2 py-1 w-20" />
                        </div>
                      ) : feature.type === 'key_value' ? (
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-gray-700">{feature.name}:</span>
                          <textarea value={typeof selectedFeatures[feature.id] === 'object' ? JSON.stringify(selectedFeatures[feature.id], null, 2) : selectedFeatures[feature.id] || '{}'}
                            onChange={(e) => { try { toggleFeature(feature.id, JSON.parse(e.target.value)); } catch {} }}
                            placeholder='{"key": "value"}'
                            className="text-xs font-mono border border-gray-300 rounded px-2 py-1 w-48 h-12" />
                        </div>
                      ) : feature.type === 'range' ? (
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-gray-700">{feature.name}:</span>
                          <input type="number" value={(selectedFeatures[feature.id] || feature.default)?.min ?? 1}
                            onChange={(e) => toggleFeature(feature.id, { ...(selectedFeatures[feature.id] || feature.default), min: parseInt(e.target.value) || 0 })}
                            className="text-xs border border-gray-300 rounded px-2 py-1 w-14" placeholder="min" />
                          <span className="text-xs text-gray-400">-</span>
                          <input type="number" value={(selectedFeatures[feature.id] || feature.default)?.max ?? 3}
                            onChange={(e) => toggleFeature(feature.id, { ...(selectedFeatures[feature.id] || feature.default), max: parseInt(e.target.value) || 0 })}
                            className="text-xs border border-gray-300 rounded px-2 py-1 w-14" placeholder="max" />
                        </div>
                      ) : feature.type === 'list' ? (
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-gray-700">{feature.name}:</span>
                          <input type="text" value={Array.isArray(selectedFeatures[feature.id]) ? selectedFeatures[feature.id].join(', ') : ''}
                            onChange={(e) => toggleFeature(feature.id, e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                            placeholder="item1, item2"
                            className="text-xs border border-gray-300 rounded px-2 py-1 w-48" />
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Summary */}
        {Object.keys(selectedFeatures).length > 0 && (
          <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3">
            <p className="text-xs font-semibold text-emerald-700 mb-1">{Object.keys(selectedFeatures).length} features configured</p>
            <div className="flex flex-wrap gap-1">
              {Object.entries(selectedFeatures).map(([id, val]) => (
                <span key={id} className="text-[10px] px-1.5 py-0.5 bg-emerald-100 text-emerald-700 rounded-md font-mono">
                  {id}={String(val).slice(0, 15)}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="flex justify-end gap-2 px-6 py-4 bg-gray-50 border-t border-gray-100">
        <button onClick={onClose} className="px-4 py-2 text-sm text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50">Cancel</button>
        <button onClick={handleProvision} disabled={!namePrefix.trim() || provisioning}
          className="px-5 py-2 text-sm font-semibold text-white bg-gradient-to-r from-emerald-600 to-teal-600 rounded-lg hover:from-emerald-700 hover:to-teal-700 disabled:opacity-40 flex items-center gap-2">
          {provisioning ? <><ArrowPathIcon className="h-4 w-4 animate-spin" /> Provisioning...</> : <><PlayIcon className="h-4 w-4" /> Provision Cluster</>}
        </button>
      </div>
    </div>
  );
};

// ============================================================================
// Main ClusterActions Component
// ============================================================================
const ClusterActions = () => {
  const [registry, setRegistry] = useState(null);
  const [loading, setLoading] = useState(true);
  const [clusterName, setClusterName] = useState('');
  const [namespace, setNamespace] = useState('ns-rosa-hcp');
  const [clusterStatus, setClusterStatus] = useState(null);
  const [loadingStatus, setLoadingStatus] = useState(false);
  const [expandedSuites, setExpandedSuites] = useState({});
  const [selectedActions, setSelectedActions] = useState([]);
  const [executing, setExecuting] = useState(false);
  const [executionResults, setExecutionResults] = useState(null);
  const [searchFilter, setSearchFilter] = useState('');
  const [phaseFilter, setPhaseFilter] = useState('all');
  const [discoveredClusters, setDiscoveredClusters] = useState(null);
  const [discovering, setDiscovering] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [showSpecs, setShowSpecs] = useState(false);
  const [showNewCluster, setShowNewCluster] = useState(false);
  const [provisionResult, setProvisionResult] = useState(null);

  useEffect(() => { fetchRegistry(); }, []);

  const fetchRegistry = async () => {
    setLoading(true);
    try {
      const res = await fetch(buildApiUrl('/api/cluster-actions/features'));
      if (res.ok) { const data = await res.json(); setRegistry(data.registry); }
    } catch (e) { console.error('Failed to fetch feature registry:', e); }
    finally { setLoading(false); }
  };

  const fetchClusterStatus = useCallback(async () => {
    if (!clusterName.trim()) return;
    setLoadingStatus(true);
    try {
      const res = await fetch(buildApiUrl(`/api/cluster-actions/cluster/${clusterName}/status?namespace=${namespace}`));
      if (res.ok) { const data = await res.json(); setClusterStatus(data.status); }
    } catch (e) { setClusterStatus({ cluster_found: false, error: 'Connection failed' }); }
    finally { setLoadingStatus(false); }
  }, [clusterName, namespace]);

  const discoverClusters = async () => {
    setDiscovering(true);
    try {
      const res = await fetch(buildApiUrl('/api/cluster-actions/discover'));
      if (res.ok) {
        const data = await res.json();
        if (data.success) {
          setDiscoveredClusters({
            success: true,
            clusters: (data.clusters || []).map(c => ({
              name: c.name, namespace: c.namespace || 'ns-rosa-hcp', version: c.version || '',
              ready: c.ready ?? false, channel_group: c.channel_group || 'stable',
              available_upgrades: c.available_upgrades || [], region: c.region || '', status: c.ready ? 'ready' : 'not ready',
            })),
            count: data.count || (data.clusters || []).length,
          });
        } else {
          setDiscoveredClusters({ success: false, clusters: [], error: data.error || 'Failed' });
        }
      }
    } catch (e) { setDiscoveredClusters({ success: false, clusters: [], error: 'Connection failed' }); }
    finally { setDiscovering(false); }
  };

  const selectCluster = (cluster) => {
    setClusterName(cluster.name);
    setNamespace(cluster.namespace);
    setDiscoveredClusters(null);
    setTimeout(async () => {
      setLoadingStatus(true);
      try {
        const res = await fetch(buildApiUrl(`/api/cluster-actions/cluster/${cluster.name}/status?namespace=${cluster.namespace}`));
        if (res.ok) { const data = await res.json(); setClusterStatus(data.status); }
      } catch { setClusterStatus({ cluster_found: false, error: 'Connection failed' }); }
      finally { setLoadingStatus(false); }
    }, 0);
  };

  const toggleSuite = (suiteId) => { setExpandedSuites(prev => ({ ...prev, [suiteId]: !prev[suiteId] })); };

  const handleFeatureToggle = (feature, targetValue) => {
    setSelectedActions(prev => {
      const existing = prev.find(a => a.feature_id === feature.id);
      if (existing) {
        if (targetValue !== undefined) return prev.map(a => a.feature_id === feature.id ? { ...a, target_value: targetValue } : a);
        return prev.filter(a => a.feature_id !== feature.id);
      }
      return [...prev, { feature_id: feature.id, feature_name: feature.name, target_value: targetValue !== undefined ? targetValue : feature.default, destructive: feature.destructive || false }];
    });
  };

  const executeActions = async () => {
    if (selectedActions.length === 0 || !clusterName.trim()) return;
    const hasDestructive = selectedActions.some(a => a.destructive);
    if (hasDestructive) {
      if (!window.confirm(`WARNING: Destructive actions on "${clusterName}".\n\n${selectedActions.filter(a => a.destructive).map(a => `  - ${a.feature_name}`).join('\n')}\n\nProceed?`)) return;
    }
    setExecuting(true);
    setExecutionResults(null);
    try {
      const res = await fetch(buildApiUrl('/api/cluster-actions/execute'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cluster_name: clusterName, namespace,
          actions: selectedActions.map(a => ({ feature_id: a.feature_id, target_value: a.target_value })),
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setExecutionResults(data.results);
      }
    } catch (e) { console.error('Failed to execute:', e); }
    finally { setExecuting(false); }
  };

  const handleProvision = (data) => {
    setProvisionResult(data);
    setShowNewCluster(false);
    // Set as active cluster
    if (data.cluster_name) {
      setClusterName(data.cluster_name);
    }
    // Show the job in execution panel
    if (data.job_id) {
      setExecutionResults([{
        feature_id: 'provision',
        status: 'running',
        job_id: data.job_id,
        message: `Provisioning ${data.cluster_name}`,
        playbook: 'playbooks/create_rosa_hcp_cluster.yml',
      }]);
    }
  };

  // Cluster Actions shows all features with applies_to including 'apply' (actionable on running clusters)
  const actionableSuites = (registry?.suites || [])
    .map(suite => ({
      ...suite,
      features: suite.features.filter(f =>
        f.applies_to?.includes('apply') || f.applies_to?.includes('upgrade') || f.applies_to?.includes('delete')
      ),
    }))
    .filter(suite => suite.features.length > 0);
  const filteredSuites = actionableSuites.filter(suite => {
    const matchesSearch = !searchFilter || suite.name.toLowerCase().includes(searchFilter.toLowerCase()) ||
      suite.description.toLowerCase().includes(searchFilter.toLowerCase()) ||
      suite.features.some(f => f.name.toLowerCase().includes(searchFilter.toLowerCase()));
    return matchesSearch;
  });

  const totalFeatures = actionableSuites.reduce((acc, s) => acc + s.features.length, 0);
  const mutableFeatures = actionableSuites.reduce((acc, s) => acc + s.features.filter(f => f.mutable).length, 0);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <ArrowPathIcon className="h-8 w-8 text-indigo-500 animate-spin mx-auto mb-3" />
        <p className="text-sm text-gray-500 ml-3">Loading feature registry...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="bg-gradient-to-r from-blue-600 to-cyan-500 px-6 py-5 shadow-md">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-bold text-white">Cluster Actions</h2>
              <p className="text-indigo-200 text-sm mt-1">All actionable features for ROSA HCP cluster lifecycle management.</p>
            </div>
            <div className="flex items-center gap-3">
              <div className="text-right"><div className="text-2xl font-bold text-white">{totalFeatures}</div><div className="text-xs text-indigo-200">features</div></div>
              <div className="w-px h-10 bg-indigo-400/30" />
              <div className="text-right"><div className="text-2xl font-bold text-white">{mutableFeatures}</div><div className="text-xs text-indigo-200">mutable</div></div>
              <div className="w-px h-10 bg-indigo-400/30" />
              <div className="text-right"><div className="text-2xl font-bold text-white">{actionableSuites.length}</div><div className="text-xs text-indigo-200">suites</div></div>
            </div>
          </div>
        </div>

        {/* Cluster selector */}
        <div className="px-6 py-5 bg-white border-t border-gray-200">
          <div className="flex items-center gap-4">
            <div className="flex-1 max-w-xs">
              <label className="block text-xs font-medium text-gray-600 mb-1">Cluster Name</label>
              <input type="text" value={clusterName} onChange={(e) => setClusterName(e.target.value)}
                placeholder="e.g., qe6-rosa-hcp"
                className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
            </div>
            <div className="w-36">
              <label className="block text-xs font-medium text-gray-600 mb-1">Namespace</label>
              <input type="text" value={namespace} onChange={(e) => setNamespace(e.target.value)}
                className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
            </div>
            <div className="flex items-end gap-2 mt-5">
              <button onClick={fetchClusterStatus} disabled={!clusterName.trim() || loadingStatus}
                className="px-4 py-2.5 text-sm font-semibold text-white bg-gradient-to-r from-blue-600 to-cyan-600 rounded-lg hover:from-blue-700 hover:to-cyan-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-sm hover:shadow-md flex items-center gap-2">
                {loadingStatus ? <ArrowPathIcon className="h-4 w-4 animate-spin" /> : <MagnifyingGlassIcon className="h-4 w-4" />}
                {loadingStatus ? 'Loading...' : 'Load Cluster'}
              </button>
              <button onClick={discoverClusters} disabled={discovering}
                className="px-4 py-2.5 text-sm font-semibold text-blue-600 bg-white border border-blue-200 rounded-lg hover:bg-blue-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-2">
                {discovering ? <ArrowPathIcon className="h-4 w-4 animate-spin" /> : <MagnifyingGlassIcon className="h-4 w-4" />}
                {discovering ? 'Discovering...' : 'Discover Clusters'}
              </button>
            </div>

            {clusterStatus && (
              <div className="flex items-center gap-2 mt-5 ml-2">
                {clusterStatus.cluster_found ? (
                  <>
                    <CheckCircleIcon className="h-5 w-5 text-emerald-500" />
                    <div>
                      <span className="text-sm font-medium text-emerald-700">Connected</span>
                      <span className="text-xs text-gray-500 ml-2">v{clusterStatus.version}</span>
                      {clusterStatus.ready && <span className="text-[10px] px-1.5 py-0.5 bg-emerald-100 text-emerald-700 rounded-full font-semibold ml-2">Ready</span>}
                    </div>
                  </>
                ) : (
                  <><XCircleIcon className="h-5 w-5 text-red-500" /><span className="text-sm text-red-600">Not found</span></>
                )}
              </div>
            )}
          </div>

          {/* Discovered clusters */}
          {discoveredClusters && (
            <div className="mt-4 border border-gray-200 rounded-xl bg-white overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2.5 bg-gradient-to-r from-slate-50 to-gray-50 border-b border-gray-200">
                <span className="text-sm font-semibold text-gray-800">
                  {discoveredClusters.success ? `${discoveredClusters.count || 0} cluster${(discoveredClusters.count || 0) !== 1 ? 's' : ''} found` : 'Discovery failed'}
                </span>
                <button onClick={() => setDiscoveredClusters(null)} className="text-xs text-gray-400 hover:text-gray-600">Dismiss</button>
              </div>
              {discoveredClusters.error && <div className="px-4 py-3 text-sm text-red-600 bg-red-50 border-b border-red-100">{discoveredClusters.error}</div>}
              {(discoveredClusters.clusters || []).length > 0 && (
                <div className="divide-y divide-gray-100">
                  {discoveredClusters.clusters.map((cluster, i) => (
                    <button key={i} onClick={() => selectCluster(cluster)}
                      className="w-full flex items-center gap-4 px-4 py-3 text-left hover:bg-blue-50 transition-colors group">
                      <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${cluster.ready ? 'bg-emerald-400' : 'bg-amber-400'}`} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-gray-900 group-hover:text-blue-700">{cluster.name}</span>
                          {cluster.ready && <span className="text-[9px] px-1.5 py-0.5 bg-emerald-100 text-emerald-700 rounded-full font-bold uppercase">Ready</span>}
                        </div>
                        <div className="flex items-center gap-3 mt-0.5">
                          <span className="text-xs text-gray-500">v{cluster.version}</span>
                          <span className="text-xs text-gray-400">{cluster.namespace}</span>
                          {cluster.region && cluster.region !== 'N/A' && <span className="text-xs text-gray-400">{cluster.region}</span>}
                          {cluster.status && cluster.status !== 'ready' && <span className="text-[10px] px-1.5 py-0 bg-amber-100 text-amber-700 rounded font-medium">{cluster.status}</span>}
                        </div>
                      </div>
                      {(cluster.available_upgrades || []).length > 0 && (
                        <span className="text-[10px] px-2 py-0.5 bg-violet-100 text-violet-700 rounded-full font-semibold flex-shrink-0">
                          {cluster.available_upgrades.length} upgrade{cluster.available_upgrades.length !== 1 ? 's' : ''}
                        </span>
                      )}
                      <ChevronRightIcon className="h-4 w-4 text-gray-300 group-hover:text-indigo-500 flex-shrink-0" />
                    </button>
                  ))}
                </div>
              )}
              {discoveredClusters.success && (discoveredClusters.clusters || []).length === 0 && (
                <div className="px-4 py-6 text-center">
                  <p className="text-sm text-gray-500">No clusters found</p>
                  <p className="text-xs text-gray-400 mt-1">Try provisioning a cluster first</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="relative">
            <MagnifyingGlassIcon className="h-4 w-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input type="text" placeholder="Search features..." value={searchFilter} onChange={(e) => setSearchFilter(e.target.value)}
              className="text-sm border border-gray-300 rounded-lg pl-9 pr-3 py-2.5 w-56 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white hover:border-gray-400 transition-colors shadow-sm" />
          </div>
          <span className="text-xs px-3 py-1.5 rounded-lg font-medium bg-violet-100 text-violet-700">Day2</span>
          <button onClick={() => {
            const allExpanded = filteredSuites.every(s => expandedSuites[s.id]);
            const newState = {};
            filteredSuites.forEach(s => { newState[s.id] = !allExpanded; });
            setExpandedSuites(newState);
          }} className="text-xs px-3 py-1.5 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors">
            {filteredSuites.every(s => expandedSuites[s.id]) ? 'Collapse All' : 'Expand All'}
          </button>
          <button onClick={() => setShowHistory(!showHistory)}
            className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-all flex items-center gap-1 ${showHistory ? 'bg-slate-700 text-white' : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'}`}>
            <ClockIcon className="h-3.5 w-3.5" /> History
          </button>
          <button onClick={() => setShowSpecs(!showSpecs)}
            className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-all flex items-center gap-1 ${showSpecs ? 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white' : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'}`}>
            <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clipRule="evenodd" /></svg>
            Specs
          </button>
        </div>

        <div className="flex items-center gap-3">
          {selectedActions.length > 0 && (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 border border-blue-200 rounded-xl">
              <span className="text-sm font-medium text-blue-700">{selectedActions.length} action{selectedActions.length !== 1 ? 's' : ''} selected</span>
              {selectedActions.some(a => a.destructive) && <ExclamationTriangleIcon className="h-4 w-4 text-red-500" />}
              <button onClick={() => setSelectedActions([])} className="text-xs text-indigo-500 hover:text-blue-700 font-medium ml-1">Clear</button>
            </div>
          )}
          <button onClick={executeActions} disabled={selectedActions.length === 0 || !clusterName.trim() || executing}
            className={`px-5 py-2.5 text-sm font-semibold text-white rounded-lg flex items-center gap-2 transition-all shadow-md ${
              executing ? 'bg-gray-400 cursor-not-allowed' :
              selectedActions.some(a => a.destructive) ? 'bg-gradient-to-r from-red-600 to-red-700 hover:from-red-700 hover:to-red-800 hover:shadow-lg hover:shadow-red-200' :
              'bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-700 hover:to-cyan-700 hover:shadow-lg hover:shadow-blue-200'
            } disabled:opacity-40 disabled:cursor-not-allowed`}>
            {executing ? <><ArrowPathIcon className="h-4 w-4 animate-spin" /> Executing...</> : <><PlayIcon className="h-4 w-4" /> Execute Actions</>}
          </button>
        </div>
      </div>

      {/* History Panel */}
      <HistoryPanel clusterName={clusterName} isOpen={showHistory} onClose={() => setShowHistory(false)} />

      {/* Spec Builder Panel */}
      {showSpecs && (
        <SpecBuilder
          clusterName={clusterName}
          namespace={namespace}
          clusterStatus={clusterStatus}
          onExecute={(results) => { setExecutionResults(results); setShowSpecs(false); }}
          onClose={() => setShowSpecs(false)}
        />
      )}

      {/* Live Execution Panel */}
      {executionResults && (
        <ExecutionPanel
          results={executionResults}
          clusterStatus={clusterStatus}
          onClose={() => setExecutionResults(null)}
          onComplete={() => {
            // Refresh cluster status after actions complete
            if (clusterName) fetchClusterStatus();
          }}
        />
      )}

      {/* Suite list */}
      <div className="space-y-3">
        {filteredSuites.map(suite => (
          <SuiteAccordion key={suite.id} suite={suite} isExpanded={expandedSuites[suite.id]}
            onToggle={() => toggleSuite(suite.id)} clusterStatus={clusterStatus}
            selectedActions={selectedActions} onFeatureToggle={handleFeatureToggle} />
        ))}
        {filteredSuites.length === 0 && (
          <div className="text-center py-12"><p className="text-sm text-gray-400">No feature suites match your filter</p></div>
        )}
      </div>

      {/* Info box */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl px-5 py-4">
        <div className="flex items-start gap-3">
          <InformationCircleIcon className="h-5 w-5 text-blue-500 mt-0.5 flex-shrink-0" />
          <div>
            <h4 className="text-sm font-semibold text-blue-900">How Cluster Actions Work</h4>
            <p className="text-xs text-blue-700 mt-1">
              All features that can be modified on a running cluster. Includes mutable Day1 features and Day2 operations.
              Features are grouped by compatibility suites. Immutable Day1 features (set at creation only) are not shown.
              Use <span className="font-semibold">Specs</span> to run declarative upgrade/apply workflows.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ClusterActions;
