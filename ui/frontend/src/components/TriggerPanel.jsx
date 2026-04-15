import React, { useState, useEffect, useCallback } from 'react';
import {
  ClockIcon,
  BoltIcon,
  PlusIcon,
  TrashIcon,
  PlayIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  XCircleIcon,
  ChevronDownIcon,
  ChevronRightIcon,
} from '@heroicons/react/24/outline';
import { buildApiUrl } from '../config/api';

const CRON_PRESETS = [
  { label: 'Every hour', cron: '0 * * * *' },
  { label: 'Every 6 hours', cron: '0 */6 * * *' },
  { label: 'Daily at 2 AM', cron: '0 2 * * *' },
  { label: 'Daily at midnight', cron: '0 0 * * *' },
  { label: 'Weekdays at 9 AM', cron: '0 9 * * 1-5' },
  { label: 'Weekly (Sun midnight)', cron: '0 0 * * 0' },
];

const TIMEZONE_OPTIONS = [
  'UTC',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'Europe/London',
  'Europe/Berlin',
  'Asia/Tokyo',
];

const cronToHuman = (cron) => {
  if (!cron) return '';
  const preset = CRON_PRESETS.find((p) => p.cron === cron);
  if (preset) return preset.label;
  return cron;
};

const TriggerPanel = ({ workflowName }) => {
  const [triggers, setTriggers] = useState([]);
  const [schedulerStatus, setSchedulerStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [history, setHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);

  // Create form state
  const [newType, setNewType] = useState('schedule');
  const [newCron, setNewCron] = useState('0 2 * * *');
  const [newTimezone, setNewTimezone] = useState('UTC');
  const [newName, setNewName] = useState('');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');

  const fetchTriggers = useCallback(async () => {
    if (!workflowName) return;
    setLoading(true);
    try {
      const resp = await fetch(buildApiUrl(`/api/workflows/${encodeURIComponent(workflowName)}/triggers`));
      const data = await resp.json();
      setTriggers(data.triggers || []);
    } catch {
      setTriggers([]);
    } finally {
      setLoading(false);
    }
  }, [workflowName]);

  const fetchSchedulerStatus = useCallback(async () => {
    try {
      const resp = await fetch(buildApiUrl('/api/triggers/scheduler/status'));
      const data = await resp.json();
      setSchedulerStatus(data);
    } catch {
      setSchedulerStatus(null);
    }
  }, []);

  const fetchHistory = useCallback(async () => {
    try {
      const resp = await fetch(buildApiUrl('/api/triggers/history/all'));
      const data = await resp.json();
      const filtered = (data.history || [])
        .filter((h) => h.workflow_name === workflowName)
        .slice(-10)
        .reverse();
      setHistory(filtered);
    } catch {
      setHistory([]);
    }
  }, [workflowName]);

  useEffect(() => {
    if (expanded && workflowName) {
      fetchTriggers();
      fetchSchedulerStatus();
    }
  }, [expanded, workflowName, fetchTriggers, fetchSchedulerStatus]);

  const createTrigger = async () => {
    setCreating(true);
    setError('');
    try {
      const body = {
        workflow_name: workflowName,
        type: newType,
        trigger_name: newName || `${newType}-${workflowName}`,
      };
      if (newType === 'schedule') {
        body.cron = newCron;
        body.timezone = newTimezone;
      }
      const resp = await fetch(buildApiUrl('/api/triggers'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const data = await resp.json();
        setError(data.detail || 'Failed to create trigger');
        return;
      }
      setShowCreateForm(false);
      setNewName('');
      fetchTriggers();
      fetchSchedulerStatus();
    } catch (e) {
      setError(e.message);
    } finally {
      setCreating(false);
    }
  };

  const deleteTrigger = async (triggerId) => {
    try {
      await fetch(buildApiUrl(`/api/triggers/${triggerId}`), { method: 'DELETE' });
      fetchTriggers();
      fetchSchedulerStatus();
    } catch { /* ignore */ }
  };

  const toggleTrigger = async (triggerId, enable) => {
    try {
      await fetch(buildApiUrl(`/api/triggers/${triggerId}/${enable ? 'enable' : 'disable'}`), { method: 'POST' });
      fetchTriggers();
    } catch { /* ignore */ }
  };

  const fireTrigger = async (triggerId) => {
    try {
      const resp = await fetch(buildApiUrl(`/api/triggers/${triggerId}/fire`), { method: 'POST' });
      if (resp.status === 429) {
        setError('Rate limited - wait 60s between fires');
        setTimeout(() => setError(''), 3000);
        return;
      }
      fetchTriggers();
      fetchHistory();
    } catch { /* ignore */ }
  };

  const scheduleCount = triggers.filter((t) => t.type === 'schedule').length;
  const webhookCount = triggers.filter((t) => t.type === 'webhook').length;

  return (
    <div className="border-t border-gray-100">
      {/* Collapsed header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-5 py-2 hover:bg-gray-50 transition-colors text-left"
      >
        <div className="flex items-center gap-2">
          {expanded ? (
            <ChevronDownIcon className="h-4 w-4 text-gray-400" />
          ) : (
            <ChevronRightIcon className="h-4 w-4 text-gray-400" />
          )}
          <ClockIcon className="h-4 w-4 text-indigo-500" />
          <span className="text-sm font-medium text-gray-700">Triggers</span>
          {triggers.length > 0 && !expanded && (
            <span className="text-[10px] px-1.5 py-0.5 bg-indigo-100 text-indigo-700 rounded-full font-bold">
              {triggers.length}
            </span>
          )}
        </div>
        {schedulerStatus && !expanded && (
          <div className="flex items-center gap-1.5">
            <div className={`w-1.5 h-1.5 rounded-full ${schedulerStatus.running ? 'bg-green-400' : 'bg-gray-300'}`} />
            <span className="text-[10px] text-gray-400">
              {schedulerStatus.running ? 'Scheduler active' : 'Scheduler stopped'}
            </span>
          </div>
        )}
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="px-5 pb-4 space-y-3">
          {/* Scheduler status bar */}
          <div className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2">
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${schedulerStatus?.running ? 'bg-green-400 animate-pulse' : 'bg-gray-300'}`} />
              <span className="text-xs text-gray-600">
                {schedulerStatus?.running ? 'Scheduler running' : 'Scheduler stopped'}
              </span>
              {schedulerStatus?.croniter_available === false && (
                <span className="text-[10px] px-1.5 py-0.5 bg-amber-100 text-amber-700 rounded">
                  croniter not installed
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-gray-400">
                {scheduleCount} schedule{scheduleCount !== 1 ? 's' : ''} | {webhookCount} webhook{webhookCount !== 1 ? 's' : ''}
              </span>
              <button
                onClick={() => { fetchTriggers(); fetchSchedulerStatus(); }}
                className="p-1 hover:bg-gray-200 rounded transition-colors"
                title="Refresh"
              >
                <ArrowPathIcon className="h-3.5 w-3.5 text-gray-400" />
              </button>
            </div>
          </div>

          {/* Trigger list */}
          {loading ? (
            <div className="text-center py-4">
              <ArrowPathIcon className="h-5 w-5 text-gray-400 animate-spin mx-auto" />
            </div>
          ) : triggers.length === 0 ? (
            <div className="text-center py-4 text-xs text-gray-400">
              No triggers configured for this workflow.
            </div>
          ) : (
            <div className="space-y-2">
              {triggers.map((trigger) => (
                <div
                  key={trigger.trigger_id}
                  className={`flex items-center justify-between bg-white border rounded-lg px-3 py-2.5 ${
                    trigger.enabled ? 'border-gray-200' : 'border-gray-100 opacity-60'
                  }`}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    {trigger.type === 'schedule' ? (
                      <ClockIcon className="h-4 w-4 text-blue-500 flex-shrink-0" />
                    ) : (
                      <BoltIcon className="h-4 w-4 text-amber-500 flex-shrink-0" />
                    )}
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-gray-800 truncate">
                        {trigger.trigger_name || trigger.trigger_id}
                      </div>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold ${
                          trigger.type === 'schedule'
                            ? 'bg-blue-50 text-blue-600'
                            : 'bg-amber-50 text-amber-600'
                        }`}>
                          {trigger.type}
                        </span>
                        {trigger.cron && (
                          <span className="text-[10px] text-gray-400 font-mono" title={trigger.cron}>
                            {cronToHuman(trigger.cron)}
                          </span>
                        )}
                        {trigger.next_run_at && trigger.enabled && (
                          <span className="text-[10px] text-gray-400">
                            Next: {new Date(trigger.next_run_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                          </span>
                        )}
                        {trigger.last_run_status && (
                          <span className={`text-[10px] flex items-center gap-0.5 ${
                            trigger.last_run_status === 'completed' ? 'text-green-600' : 'text-red-500'
                          }`}>
                            {trigger.last_run_status === 'completed' ? (
                              <CheckCircleIcon className="h-3 w-3" />
                            ) : (
                              <XCircleIcon className="h-3 w-3" />
                            )}
                            {trigger.last_run_status}
                          </span>
                        )}
                        {trigger.consecutive_failures > 0 && (
                          <span className="text-[10px] text-red-400">
                            {trigger.consecutive_failures} fail{trigger.consecutive_failures !== 1 ? 's' : ''}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-1 flex-shrink-0">
                    {/* Enable/disable toggle */}
                    <button
                      onClick={() => toggleTrigger(trigger.trigger_id, !trigger.enabled)}
                      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                        trigger.enabled ? 'bg-indigo-500' : 'bg-gray-300'
                      }`}
                      title={trigger.enabled ? 'Disable' : 'Enable'}
                    >
                      <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${
                        trigger.enabled ? 'translate-x-4' : 'translate-x-0.5'
                      }`} />
                    </button>
                    {/* Fire manually */}
                    <button
                      onClick={() => fireTrigger(trigger.trigger_id)}
                      className="p-1 text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 rounded transition-colors"
                      title="Fire now"
                    >
                      <PlayIcon className="h-3.5 w-3.5" />
                    </button>
                    {/* Delete */}
                    <button
                      onClick={() => deleteTrigger(trigger.trigger_id)}
                      className="p-1 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded transition-colors"
                      title="Delete trigger"
                    >
                      <TrashIcon className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Error message */}
          {error && (
            <div className="text-xs text-red-500 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          {/* Create form */}
          {showCreateForm ? (
            <div className="bg-gray-50 rounded-lg p-3 space-y-2.5 border border-gray-200">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-700 uppercase tracking-wider">New Trigger</span>
                <button
                  onClick={() => { setShowCreateForm(false); setError(''); }}
                  className="text-xs text-gray-400 hover:text-gray-600"
                >
                  Cancel
                </button>
              </div>

              {/* Type selector */}
              <div className="flex gap-2">
                <button
                  onClick={() => setNewType('schedule')}
                  className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg border transition-all ${
                    newType === 'schedule'
                      ? 'bg-blue-50 border-blue-300 text-blue-700'
                      : 'bg-white border-gray-200 text-gray-500 hover:border-gray-300'
                  }`}
                >
                  <ClockIcon className="h-3.5 w-3.5" />
                  Schedule
                </button>
                <button
                  onClick={() => setNewType('webhook')}
                  className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg border transition-all ${
                    newType === 'webhook'
                      ? 'bg-amber-50 border-amber-300 text-amber-700'
                      : 'bg-white border-gray-200 text-gray-500 hover:border-gray-300'
                  }`}
                >
                  <BoltIcon className="h-3.5 w-3.5" />
                  Webhook
                </button>
              </div>

              {/* Name */}
              <div>
                <label className="block text-[11px] font-medium text-gray-600 mb-1">Name</label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder={`e.g., nightly-${workflowName || 'run'}`}
                  className="w-full text-sm border border-gray-200 rounded-lg px-2.5 py-1.5 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 bg-white"
                />
              </div>

              {/* Schedule-specific fields */}
              {newType === 'schedule' && (
                <>
                  <div>
                    <label className="block text-[11px] font-medium text-gray-600 mb-1">Cron Expression</label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={newCron}
                        onChange={(e) => setNewCron(e.target.value)}
                        placeholder="0 2 * * *"
                        className="flex-1 text-sm border border-gray-200 rounded-lg px-2.5 py-1.5 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 bg-white font-mono"
                      />
                    </div>
                    {/* Presets */}
                    <div className="flex flex-wrap gap-1 mt-1.5">
                      {CRON_PRESETS.map((preset) => (
                        <button
                          key={preset.cron}
                          onClick={() => setNewCron(preset.cron)}
                          className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${
                            newCron === preset.cron
                              ? 'bg-indigo-50 border-indigo-300 text-indigo-700'
                              : 'bg-white border-gray-200 text-gray-500 hover:border-gray-300'
                          }`}
                        >
                          {preset.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <label className="block text-[11px] font-medium text-gray-600 mb-1">Timezone</label>
                    <select
                      value={newTimezone}
                      onChange={(e) => setNewTimezone(e.target.value)}
                      className="w-full text-sm border border-gray-200 rounded-lg px-2.5 py-1.5 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 bg-white"
                    >
                      {TIMEZONE_OPTIONS.map((tz) => (
                        <option key={tz} value={tz}>{tz}</option>
                      ))}
                    </select>
                  </div>
                </>
              )}

              {/* Webhook info */}
              {newType === 'webhook' && (
                <div className="text-xs text-gray-500 bg-white border border-gray-200 rounded-lg px-3 py-2">
                  <p>After creation, use the webhook URL to trigger this workflow:</p>
                  <code className="block mt-1 text-[10px] text-indigo-600 bg-indigo-50 px-2 py-1 rounded font-mono break-all">
                    POST /api/webhooks/trigger/&lt;trigger_id&gt;
                  </code>
                </div>
              )}

              {/* Create button */}
              <button
                onClick={createTrigger}
                disabled={creating || !workflowName || (newType === 'schedule' && !newCron)}
                className="w-full px-3 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-1.5"
              >
                {creating ? (
                  <ArrowPathIcon className="h-4 w-4 animate-spin" />
                ) : (
                  <PlusIcon className="h-4 w-4" />
                )}
                {creating ? 'Creating...' : 'Create Trigger'}
              </button>
            </div>
          ) : (
            <button
              onClick={() => { setShowCreateForm(true); setError(''); }}
              disabled={!workflowName}
              className="w-full flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium text-indigo-600 bg-indigo-50 border border-indigo-200 rounded-lg hover:bg-indigo-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <PlusIcon className="h-3.5 w-3.5" />
              Add Trigger
            </button>
          )}

          {/* History toggle */}
          <button
            onClick={() => { setShowHistory(!showHistory); if (!showHistory) fetchHistory(); }}
            className="text-xs text-gray-400 hover:text-gray-600 transition-colors flex items-center gap-1"
          >
            {showHistory ? <ChevronDownIcon className="h-3 w-3" /> : <ChevronRightIcon className="h-3 w-3" />}
            Recent runs ({history.length})
          </button>

          {showHistory && history.length > 0 && (
            <div className="space-y-1">
              {history.map((run) => (
                <div
                  key={run.run_id}
                  className="flex items-center justify-between bg-white border border-gray-100 rounded px-2.5 py-1.5 text-[11px]"
                >
                  <div className="flex items-center gap-2">
                    {run.status === 'completed' ? (
                      <CheckCircleIcon className="h-3.5 w-3.5 text-green-500" />
                    ) : (
                      <XCircleIcon className="h-3.5 w-3.5 text-red-400" />
                    )}
                    <span className="text-gray-600">{run.triggered_by}</span>
                    <span className="text-gray-400">
                      {run.steps_completed}/{run.steps_total} steps
                    </span>
                  </div>
                  <span className="text-gray-400">
                    {new Date(run.started_at).toLocaleString(undefined, {
                      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
                    })}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default TriggerPanel;
