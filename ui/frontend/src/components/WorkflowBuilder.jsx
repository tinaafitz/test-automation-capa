/* eslint-disable no-unused-vars */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragOverlay,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import {
  PlayIcon,
  TrashIcon,
  PlusIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  XCircleIcon,
  ClockIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  Cog6ToothIcon,
  ArrowDownIcon,
  DocumentDuplicateIcon,
  FolderOpenIcon,
} from '@heroicons/react/24/outline';
import { buildApiUrl } from '../config/api';
import { useRecentOperationsContext } from '../store/AppContext';

// ============================================================================
// Draggable Playbook Card (in the palette)
// ============================================================================
const PlaybookPaletteItem = ({ suite, onAdd }) => {
  return (
    <div
      className="flex items-center justify-between px-3 py-2 bg-white border border-gray-200 rounded-lg cursor-grab hover:border-blue-400 hover:shadow-sm transition-all group"
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData('application/json', JSON.stringify(suite));
        e.dataTransfer.effectAllowed = 'copy';
      }}
    >
      <div className="flex-1 min-w-0 mr-2">
        <div className="text-sm font-medium text-gray-900 truncate">{suite.name}</div>
        <div className="text-xs text-gray-500 truncate">{suite.description}</div>
      </div>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onAdd(suite);
        }}
        className="flex-shrink-0 p-1 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded transition-colors opacity-0 group-hover:opacity-100"
        title="Add to workflow"
      >
        <PlusIcon className="h-4 w-4" />
      </button>
    </div>
  );
};

// ============================================================================
// Sortable Workflow Step
// ============================================================================
const SortableStep = ({ step, index, totalSteps, onRemove, onToggleConfig, onUpdateStep, isOutputActive, onToggleOutput }) => {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: step.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const statusColors = {
    pending: 'border-gray-200 bg-white',
    running: 'border-blue-400 bg-blue-50 ring-2 ring-blue-200',
    completed: 'border-green-400 bg-green-50',
    failed: 'border-red-400 bg-red-50',
    skipped: 'border-yellow-400 bg-yellow-50',
  };

  const statusIcons = {
    pending: <div className="w-6 h-6 rounded-full border-2 border-gray-300 flex items-center justify-center text-xs font-bold text-gray-400">{index + 1}</div>,
    running: <ArrowPathIcon className="h-6 w-6 text-blue-600 animate-spin" />,
    completed: <CheckCircleIcon className="h-6 w-6 text-green-600" />,
    failed: <XCircleIcon className="h-6 w-6 text-red-600" />,
    skipped: <ClockIcon className="h-6 w-6 text-yellow-600" />,
  };

  return (
    <div ref={setNodeRef} style={style}>
      {/* Connector arrow */}
      {index > 0 && (
        <div className="flex justify-center py-1">
          <ArrowDownIcon className="h-4 w-4 text-gray-400" />
        </div>
      )}

      {/* Step card */}
      <div className={`rounded-lg border-2 ${statusColors[step.status]} transition-all`}>
        <div className="flex items-center gap-3 px-4 py-3">
          {/* Drag handle */}
          <div
            {...attributes}
            {...listeners}
            className="cursor-grab active:cursor-grabbing text-gray-400 hover:text-gray-600 flex-shrink-0"
            title="Drag to reorder"
          >
            <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path d="M7 2a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM13 2a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM7 8a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM13 8a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM7 14a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM13 14a2 2 0 1 0 0 4 2 2 0 0 0 0-4z" />
            </svg>
          </div>

          {/* Status icon */}
          {statusIcons[step.status]}

          {/* Step info */}
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold text-gray-900 truncate">{step.name}</div>
            <div className="text-xs text-gray-500 truncate">
              {step.description}
              {step.startedAt && (
                <span className="ml-2 text-gray-400">
                  {step.completedAt
                    ? (() => {
                        const secs = Math.round((step.completedAt - step.startedAt) / 1000);
                        return secs < 60 ? `${secs}s` : `${Math.floor(secs / 60)}m ${secs % 60}s`;
                      })()
                    : step.status === 'running'
                    ? (() => {
                        const secs = Math.round((Date.now() - step.startedAt) / 1000);
                        return secs < 60 ? `${secs}s...` : `${Math.floor(secs / 60)}m ${secs % 60}s...`;
                      })()
                    : null}
                </span>
              )}
            </div>
          </div>

          {/* Step badges */}
          <div className="flex items-center gap-2 flex-shrink-0">
            {step.onFailure === 'skip' && (
              <span className="text-xs px-2 py-0.5 bg-yellow-100 text-yellow-700 rounded-full font-medium">Skip on fail</span>
            )}
          </div>

          {/* Config toggle */}
          <button
            onClick={() => onToggleConfig(step.id)}
            className="relative p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded transition-colors flex-shrink-0"
            title="Configure step"
          >
            <Cog6ToothIcon className="h-4 w-4" />
            {Object.keys(step.extra_vars || {}).length > 0 && (
              <span className="absolute -top-1 -right-1 w-4 h-4 bg-blue-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center">
                {Object.keys(step.extra_vars).length}
              </span>
            )}
          </button>

          {/* Output toggle (when logs exist) */}
          {(step.logs || []).length > 0 && (
            <button
              onClick={() => onToggleOutput(step.id)}
              className={`p-1.5 rounded transition-colors flex-shrink-0 ${
                isOutputActive ? 'text-blue-600 bg-blue-100' : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100'
              }`}
              title={isOutputActive ? 'Hide output' : 'Show output'}
            >
              <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M2 4.75A.75.75 0 012.75 4h14.5a.75.75 0 010 1.5H2.75A.75.75 0 012 4.75zm0 10.5a.75.75 0 01.75-.75h7.5a.75.75 0 010 1.5h-7.5a.75.75 0 01-.75-.75zM2 10a.75.75 0 01.75-.75h14.5a.75.75 0 010 1.5H2.75A.75.75 0 012 10z" clipRule="evenodd" />
              </svg>
            </button>
          )}

          {/* Remove button */}
          <button
            onClick={() => onRemove(step.id)}
            className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors flex-shrink-0"
            title="Remove step"
          >
            <TrashIcon className="h-4 w-4" />
          </button>
        </div>

        {/* Expanded config panel */}
        {step.showConfig && (
          <div className="border-t border-gray-200 px-4 py-3 bg-gray-50 rounded-b-lg space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">On Failure</label>
                <select
                  value={step.onFailure}
                  onChange={(e) => onUpdateStep(step.id, { onFailure: e.target.value })}
                  className="w-full text-sm border border-gray-300 rounded-md px-2 py-1.5 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="stop">Stop workflow</option>
                  <option value="skip">Skip and continue</option>
                  <option value="retry">Retry once</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Timeout (seconds)</label>
                <input
                  type="number"
                  value={step.timeout}
                  onChange={(e) => onUpdateStep(step.id, { timeout: parseInt(e.target.value) || 600 })}
                  className="w-full text-sm border border-gray-300 rounded-md px-2 py-1.5 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
            </div>
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={step.required}
                  onChange={(e) => onUpdateStep(step.id, { required: e.target.checked })}
                  className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                />
                <span className="text-sm text-gray-700">Required step</span>
              </label>
            </div>
            {/* Extra vars - editable */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-xs font-medium text-gray-700">Variables</label>
                <button
                  onClick={() => {
                    const updated = { ...(step.extra_vars || {}), '': '' };
                    // Use a unique placeholder key
                    const key = `new_var_${Object.keys(step.extra_vars || {}).length}`;
                    updated[key] = '';
                    onUpdateStep(step.id, { extra_vars: updated });
                  }}
                  className="text-xs text-blue-600 hover:text-blue-800 font-medium flex items-center gap-1"
                >
                  <PlusIcon className="h-3 w-3" />
                  Add variable
                </button>
              </div>
              {Object.keys(step.extra_vars || {}).length > 0 ? (
                <div className="space-y-1.5">
                  {Object.entries(step.extra_vars || {}).map(([key, val]) => (
                    <div key={key} className="flex items-center gap-2">
                      <input
                        type="text"
                        defaultValue={key}
                        placeholder="key"
                        onBlur={(e) => {
                          const newKey = e.target.value.trim();
                          if (newKey && newKey !== key) {
                            const vars = { ...step.extra_vars };
                            const value = vars[key];
                            delete vars[key];
                            vars[newKey] = value;
                            onUpdateStep(step.id, { extra_vars: vars });
                          }
                        }}
                        className="flex-1 text-xs font-mono border border-gray-300 rounded px-2 py-1 focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                      />
                      <span className="text-gray-400 text-xs">=</span>
                      <input
                        type="text"
                        value={typeof val === 'object' ? JSON.stringify(val) : String(val)}
                        placeholder="value"
                        onChange={(e) => {
                          const vars = { ...step.extra_vars };
                          // Try to parse booleans and numbers
                          let parsed = e.target.value;
                          if (parsed === 'true') parsed = true;
                          else if (parsed === 'false') parsed = false;
                          else if (parsed !== '' && !isNaN(parsed) && !isNaN(parseFloat(parsed))) parsed = parseFloat(parsed);
                          vars[key] = parsed;
                          onUpdateStep(step.id, { extra_vars: vars });
                        }}
                        className="flex-1 text-xs font-mono border border-gray-300 rounded px-2 py-1 focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                      />
                      <button
                        onClick={() => {
                          const vars = { ...step.extra_vars };
                          delete vars[key];
                          onUpdateStep(step.id, { extra_vars: vars });
                        }}
                        className="p-0.5 text-gray-400 hover:text-red-500 transition-colors"
                        title="Remove variable"
                      >
                        <XCircleIcon className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-gray-400 italic">
                  No step-specific variables — uses{' '}
                  <span className="text-blue-500 font-medium">Workflow Variables</span> only
                </p>
              )}
            </div>
            {/* Close config button */}
            <button
              onClick={() => onToggleConfig(step.id)}
              className="w-full text-xs text-gray-500 hover:text-gray-700 hover:bg-gray-100 py-1.5 rounded transition-colors text-center"
            >
              Close
            </button>
          </div>
        )}

      </div>
    </div>
  );
};

// ============================================================================
// Step Output Panel (live log viewer)
// ============================================================================
const StepOutputPanel = ({ logs, status, agentStats }) => {
  const outputRef = useRef(null);
  const [copied, setCopied] = useState(false);

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (outputRef.current && status === 'running') {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [logs, status]);

  const handleCopy = () => {
    navigator.clipboard.writeText(logs.join('\n')).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const stats = agentStats;
  const hasAgent = stats?.enabled;
  const issuesDetected = stats?.issues_detected || 0;
  const interventions = stats?.interventions || 0;
  const totalChecks = stats?.total_checks || 0;

  return (
    <div className="border-t border-gray-200">
      {/* AI Agent summary header */}
      {hasAgent && (issuesDetected > 0 || interventions > 0 || totalChecks > 0) && (
        <div className={`px-3 py-2 text-xs flex items-center gap-4 ${
          interventions > 0
            ? 'bg-yellow-50 border-b border-yellow-200'
            : 'bg-gray-50 border-b border-gray-200'
        }`}>
          <span className="font-semibold text-gray-700">
            {issuesDetected > 0 ? '\uD83E\uDD16' : '\uD83D\uDEE1\uFE0F'} AI Agent{status === 'running' ? ': Monitoring' : ': Summary'}
          </span>
          <span className="text-gray-600">Issues: {issuesDetected}</span>
          <span className="text-gray-600">Fixes: {interventions}</span>
          {totalChecks > 0 && (
            <span className="text-gray-500">({totalChecks} checks)</span>
          )}
          {interventions > 0 && (
            <span className="text-green-700 font-medium">
              Auto-fixed {interventions} issue(s)
            </span>
          )}
        </div>
      )}
      <div className="relative">
        {logs.length > 0 && (
          <button
            onClick={handleCopy}
            className="absolute top-2 right-2 z-10 px-2 py-1 text-xs rounded bg-gray-700 hover:bg-gray-600 text-gray-300 hover:text-white transition-colors"
            title="Copy output"
          >
            {copied ? 'Copied!' : 'Copy'}
          </button>
        )}
        <div
          ref={outputRef}
          className="bg-gray-900 text-gray-100 rounded-b-lg p-3 max-h-80 overflow-y-auto font-mono text-xs leading-relaxed"
        >
        {logs.map((line, i) => (
          <div
            key={i}
            className={
              line.includes('TASK [') ? 'text-cyan-400 mt-1' :
              line.includes('ok:') ? 'text-green-400' :
              line.includes('changed:') ? 'text-yellow-400' :
              line.includes('fatal:') || line.includes('FAILED') ? 'text-red-400 font-bold' :
              line.includes('PLAY RECAP') ? 'text-cyan-300 mt-2 font-bold' :
              line.includes('skipping:') ? 'text-gray-500' :
              line.includes('\uD83E\uDD16') || line.includes('Agent') ? 'text-yellow-300 font-medium' :
              'text-gray-300'
            }
          >
            {line}
          </div>
        ))}
        {status === 'running' && (
          <div className="text-blue-400 animate-pulse mt-1">▋</div>
        )}
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// Main WorkflowBuilder Component
// ============================================================================
const WorkflowBuilder = () => {
  const [availablePlaybooks, setAvailablePlaybooks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [paletteSearch, setPaletteSearch] = useState('');
  const [paletteCategory, setPaletteCategory] = useState('all');

  // Workflow state
  const [workflowName, setWorkflowName] = useState('My Workflow');
  const [workflowSteps, setWorkflowSteps] = useState([]);
  const [stopOnFailure, setStopOnFailure] = useState(true);
  const [isRunning, setIsRunning] = useState(false);
  const [runJobId, setRunJobId] = useState(null);

  // Global workflow variables (shared across all steps, like Jenkins environment block)
  const [globalVars, setGlobalVars] = useState({});
  const [showGlobalVars, setShowGlobalVars] = useState(false);

  // Output panel — which step's logs to show
  const [activeOutputStepId, setActiveOutputStepId] = useState(null);

  // Saved workflows
  const [savedWorkflows, setSavedWorkflows] = useState([]);
  const [showSavedList, setShowSavedList] = useState(false);
  const [showSaveDialog, setShowSaveDialog] = useState(false);

  // Recent operations (task logging)
  const recentOps = useRecentOperationsContext();
  const { addToRecent, updateRecentOperationStatus } = recentOps;

  // Drag state
  const [activeId, setActiveId] = useState(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  // ---- Restore last run results from localStorage ----
  useEffect(() => {
    try {
      const saved = localStorage.getItem('capa-workflow-last-run');
      if (saved) {
        const data = JSON.parse(saved);
        if (data.workflowSteps?.length > 0) {
          setWorkflowName(data.workflowName || 'My Workflow');
          setWorkflowSteps(data.workflowSteps);
          setGlobalVars(data.globalVars || {});
          setStopOnFailure(data.stopOnFailure ?? true);
          if (data.activeOutputStepId) setActiveOutputStepId(data.activeOutputStepId);
        }
      }
    } catch (e) {
      console.error('Failed to restore last run:', e);
    }
  }, []);

  // ---- Persist workflow results to localStorage when steps change ----
  const initialLoadDone = useRef(false);
  useEffect(() => {
    // Skip the first render cycle so we don't overwrite stored data with empty initial state
    if (!initialLoadDone.current) {
      initialLoadDone.current = true;
      return;
    }
    if (workflowSteps.length > 0) {
      try {
        localStorage.setItem('capa-workflow-last-run', JSON.stringify({
          workflowName,
          workflowSteps,
          globalVars,
          stopOnFailure,
          activeOutputStepId,
        }));
      } catch (e) {
        console.error('Failed to persist workflow results:', e);
      }
    }
  }, [workflowSteps, workflowName, activeOutputStepId, globalVars, stopOnFailure]);

  // ---- Fetch available playbooks ----
  useEffect(() => {
    fetchPlaybooks();
    loadSavedWorkflows();
  }, []);

  const fetchPlaybooks = async () => {
    setLoading(true);
    try {
      const response = await fetch(buildApiUrl('/api/test-suites/list'));
      if (response.ok) {
        const data = await response.json();
        // API returns {suites: [{id, config: {name, description, playbooks, ...}}]}
        const suites = (data.suites || []).map((s) => ({
          id: s.id,
          ...s.config,
        }));
        setAvailablePlaybooks(suites);
      }
    } catch (error) {
      console.error('Failed to fetch playbooks:', error);
    } finally {
      setLoading(false);
    }
  };

  // ---- Categorize playbooks ----
  const categorizePlaybook = (suite) => {
    const name = (suite.name || '').toLowerCase();
    const tags = (suite.tags || []).map(t => t.toLowerCase());
    if (name.includes('verify') || name.includes('validation') || tags.includes('validation')) return 'Validation';
    if (name.includes('configure') || name.includes('enable') || name.includes('disable') || tags.includes('configuration')) return 'Configuration';
    if (name.includes('provision') || name.includes('create') || tags.includes('provisioning')) return 'Provisioning';
    if (name.includes('delete') || name.includes('cleanup') || tags.includes('cleanup')) return 'Cleanup';
    return 'Other';
  };

  const filteredPlaybooks = availablePlaybooks.filter((suite) => {
    const matchesSearch = !paletteSearch ||
      (suite.name || '').toLowerCase().includes(paletteSearch.toLowerCase()) ||
      (suite.description || '').toLowerCase().includes(paletteSearch.toLowerCase());
    const matchesCategory = paletteCategory === 'all' || categorizePlaybook(suite) === paletteCategory;
    return matchesSearch && matchesCategory;
  });

  const groupedPlaybooks = filteredPlaybooks.reduce((groups, suite) => {
    const cat = categorizePlaybook(suite);
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(suite);
    return groups;
  }, {});

  // ---- Add step to workflow ----
  const addStep = useCallback((suite) => {
    const playbook = suite.playbooks?.[0] || {};
    const newStep = {
      id: `step-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      name: suite.name,
      description: suite.description || '',
      file: playbook.file || '',
      suiteName: suite.name,
      required: playbook.required !== undefined ? playbook.required : false,
      onFailure: 'stop',
      timeout: playbook.timeout || 600,
      extra_vars: playbook.extra_vars || playbook.vars || {},
      status: 'pending',
      showConfig: Object.keys(playbook.extra_vars || playbook.vars || {}).length > 0,
    };
    setWorkflowSteps((prev) => [...prev, newStep]);
  }, []);

  // ---- Remove step ----
  const removeStep = useCallback((stepId) => {
    setWorkflowSteps((prev) => prev.filter((s) => s.id !== stepId));
  }, []);

  // ---- Toggle config panel ----
  const toggleConfig = useCallback((stepId) => {
    setWorkflowSteps((prev) =>
      prev.map((s) => s.id === stepId ? { ...s, showConfig: !s.showConfig } : s)
    );
  }, []);

  // ---- Update step ----
  const updateStep = useCallback((stepId, updates) => {
    setWorkflowSteps((prev) =>
      prev.map((s) => s.id === stepId ? { ...s, ...updates } : s)
    );
  }, []);

  // ---- Drag handlers ----
  const handleDragStart = (event) => {
    setActiveId(event.active.id);
  };

  const handleDragEnd = (event) => {
    setActiveId(null);
    const { active, over } = event;
    if (active.id !== over?.id) {
      setWorkflowSteps((items) => {
        const oldIndex = items.findIndex((i) => i.id === active.id);
        const newIndex = items.findIndex((i) => i.id === over.id);
        return arrayMove(items, oldIndex, newIndex);
      });
    }
  };

  // ---- Drop zone for palette items ----
  const handleCanvasDrop = (e) => {
    e.preventDefault();
    e.currentTarget.classList.remove('ring-2', 'ring-blue-400', 'bg-blue-50');
    try {
      const data = e.dataTransfer.getData('application/json');
      if (data) {
        const suite = JSON.parse(data);
        addStep(suite);
      }
    } catch (err) {
      // Not a palette drag
    }
  };

  const handleCanvasDragOver = (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
    e.currentTarget.classList.add('ring-2', 'ring-blue-400', 'bg-blue-50');
  };

  const handleCanvasDragLeave = (e) => {
    e.currentTarget.classList.remove('ring-2', 'ring-blue-400', 'bg-blue-50');
  };

  // ---- Save / Load workflows ----
  const loadSavedWorkflows = () => {
    try {
      const saved = localStorage.getItem('capa-workflows');
      if (saved) setSavedWorkflows(JSON.parse(saved));
    } catch (e) {
      console.error('Failed to load workflows:', e);
    }
  };

  const saveWorkflow = () => {
    if (!workflowName.trim() || workflowSteps.length === 0) return;

    const workflow = {
      id: `wf-${Date.now()}`,
      name: workflowName,
      stopOnFailure,
      globalVars,
      steps: workflowSteps.map(({ id, showConfig, status, ...rest }) => rest),
      savedAt: new Date().toISOString(),
    };

    const existing = savedWorkflows.filter((w) => w.name !== workflowName);
    const updated = [...existing, workflow];
    setSavedWorkflows(updated);
    localStorage.setItem('capa-workflows', JSON.stringify(updated));
    setShowSaveDialog(false);
  };

  const loadWorkflow = (workflow) => {
    setWorkflowName(workflow.name);
    setStopOnFailure(workflow.stopOnFailure ?? true);
    setGlobalVars(workflow.globalVars || {});
    setWorkflowSteps(
      workflow.steps.map((step, i) => ({
        ...step,
        id: `step-${Date.now()}-${i}`,
        status: 'pending',
        showConfig: false,
      }))
    );
    setShowSavedList(false);
  };

  const deleteWorkflow = (workflowId) => {
    const updated = savedWorkflows.filter((w) => w.id !== workflowId);
    setSavedWorkflows(updated);
    localStorage.setItem('capa-workflows', JSON.stringify(updated));
  };

  // ---- Run workflow ----
  const runWorkflow = async () => {
    if (workflowSteps.length === 0 || isRunning) return;

    setIsRunning(true);
    // Reset all steps to pending, clear logs
    setWorkflowSteps((prev) => prev.map((s) => ({ ...s, status: 'pending', logs: [] })));
    setActiveOutputStepId(null);

    // Log workflow start to Recent Tasks
    const workflowOpId = `workflow-${Date.now()}`;
    addToRecent({
      id: workflowOpId,
      title: `📋 Workflow: ${workflowName}`,
      color: 'bg-indigo-600',
      status: `⏳ Running (0/${workflowSteps.length} steps)`,
      environment: 'mce',
    });

    let completedCount = 0;
    let failedCount = 0;

    for (let i = 0; i < workflowSteps.length; i++) {
      const step = workflowSteps[i];
      const stepOpId = `${workflowOpId}-step-${i}`;

      // Mark current step as running and auto-show its output
      setWorkflowSteps((prev) =>
        prev.map((s, idx) => idx === i ? { ...s, status: 'running', startedAt: Date.now(), completedAt: null } : s)
      );
      setActiveOutputStepId(step.id);

      // Log step start
      addToRecent({
        id: stepOpId,
        title: `  ↳ Step ${i + 1}: ${step.name}`,
        color: 'bg-blue-600',
        status: '⏳ Running...',
        environment: 'mce',
      });

      // Update workflow progress
      updateRecentOperationStatus(
        workflowOpId,
        `⏳ Running step ${i + 1}/${workflowSteps.length}: ${step.name}`
      );

      try {
        // Merge global vars with step-specific vars (step vars override globals)
        // Auto-add soft_verify for verify playbooks so informational "not configured" doesn't fail the workflow
        const mergedVars = { ...globalVars, ...(step.extra_vars || {}) };
        if (step.name.toLowerCase().includes('verify')) {
          mergedVars.soft_verify = 'true';
        }

        // Run the playbook via API
        const response = await fetch(buildApiUrl('/api/ansible/run-playbook'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            playbook: step.file,
            description: `[Workflow: ${workflowName}] ${step.name}`,
            extra_vars: mergedVars,
          }),
        });

        if (!response.ok) {
          throw new Error(`Failed to start: ${response.statusText}`);
        }

        const result = await response.json();
        const jobId = result.job_id;
        setRunJobId(jobId);

        // Poll for completion
        const success = await pollJobCompletion(jobId, step.id);

        setWorkflowSteps((prev) =>
          prev.map((s, idx) => idx === i ? { ...s, status: success ? 'completed' : 'failed', completedAt: Date.now() } : s)
        );

        // Fetch final logs from the API for the task summary
        let stepOutput = '';
        try {
          const finalLogsRes = await fetch(buildApiUrl(`/api/jobs/${jobId}/logs`));
          if (finalLogsRes.ok) {
            const finalLogsData = await finalLogsRes.json();
            stepOutput = (finalLogsData.logs || []).join('\n');
          }
        } catch (e) { /* ignore */ }

        if (success) {
          completedCount++;
          updateRecentOperationStatus(stepOpId, '✅ Completed', stepOutput);
        } else {
          failedCount++;
          updateRecentOperationStatus(stepOpId, '❌ Failed', stepOutput);
        }

        if (!success) {
          if (step.onFailure === 'retry') {
            // Retry once
            setWorkflowSteps((prev) =>
              prev.map((s, idx) => idx === i ? { ...s, status: 'running' } : s)
            );
            updateRecentOperationStatus(stepOpId, '⏳ Retrying...');
            const retryResponse = await fetch(buildApiUrl('/api/ansible/run-playbook'), {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                playbook: step.file,
                description: `[Workflow: ${workflowName}] ${step.name} (retry)`,
                extra_vars: mergedVars,
              }),
            });
            if (retryResponse.ok) {
              const retryResult = await retryResponse.json();
              const retrySuccess = await pollJobCompletion(retryResult.job_id, step.id);
              setWorkflowSteps((prev) =>
                prev.map((s, idx) => idx === i ? { ...s, status: retrySuccess ? 'completed' : 'failed' } : s)
              );
              // Fetch retry logs
              let retryOutput = '';
              try {
                const retryLogsRes = await fetch(buildApiUrl(`/api/jobs/${retryResult.job_id}/logs`));
                if (retryLogsRes.ok) {
                  const retryLogsData = await retryLogsRes.json();
                  retryOutput = (retryLogsData.logs || []).join('\n');
                }
              } catch (e) { /* ignore */ }

              if (retrySuccess) {
                failedCount--;
                completedCount++;
                updateRecentOperationStatus(stepOpId, '✅ Completed (retry)', retryOutput);
              } else {
                updateRecentOperationStatus(stepOpId, '❌ Failed (after retry)', retryOutput);
                if (step.required && stopOnFailure) {
                  // Mark remaining as skipped
                  for (let j = i + 1; j < workflowSteps.length; j++) {
                    addToRecent({
                      id: `${workflowOpId}-step-${j}`,
                      title: `  ↳ Step ${j + 1}: ${workflowSteps[j].name}`,
                      color: 'bg-yellow-600',
                      status: '⚠️ Skipped',
                      environment: 'mce',
                    });
                  }
                  setWorkflowSteps((prev) =>
                    prev.map((s, idx) => idx > i ? { ...s, status: 'skipped' } : s)
                  );
                  break;
                }
              }
            }
          } else if (step.onFailure === 'stop' || (step.required && stopOnFailure)) {
            // Mark remaining as skipped
            for (let j = i + 1; j < workflowSteps.length; j++) {
              addToRecent({
                id: `${workflowOpId}-step-${j}`,
                title: `  ↳ Step ${j + 1}: ${workflowSteps[j].name}`,
                color: 'bg-yellow-600',
                status: '⚠️ Skipped',
                environment: 'mce',
              });
            }
            setWorkflowSteps((prev) =>
              prev.map((s, idx) => idx > i ? { ...s, status: 'skipped' } : s)
            );
            break;
          }
          // 'skip' just continues to next step
        }
      } catch (error) {
        console.error(`Step ${step.name} failed:`, error);
        failedCount++;
        setWorkflowSteps((prev) =>
          prev.map((s, idx) => idx === i ? { ...s, status: 'failed' } : s)
        );
        updateRecentOperationStatus(stepOpId, `❌ Error: ${error.message}`);

        if (step.required && stopOnFailure) {
          for (let j = i + 1; j < workflowSteps.length; j++) {
            addToRecent({
              id: `${workflowOpId}-step-${j}`,
              title: `  ↳ Step ${j + 1}: ${workflowSteps[j].name}`,
              color: 'bg-yellow-600',
              status: '⚠️ Skipped',
              environment: 'mce',
            });
          }
          setWorkflowSteps((prev) =>
            prev.map((s, idx) => idx > i ? { ...s, status: 'skipped' } : s)
          );
          break;
        }
      }
    }

    // Update workflow final status
    const skippedCount = workflowSteps.length - completedCount - failedCount;
    if (failedCount === 0) {
      updateRecentOperationStatus(
        workflowOpId,
        `✅ Completed (${completedCount}/${workflowSteps.length} steps)`
      );
    } else {
      updateRecentOperationStatus(
        workflowOpId,
        `❌ ${failedCount} failed, ${completedCount} passed${skippedCount > 0 ? `, ${skippedCount} skipped` : ''}`
      );
    }

    setIsRunning(false);
    setRunJobId(null);
  };

  const pollJobCompletion = (jobId, stepId) => {
    return new Promise((resolve) => {
      const interval = setInterval(async () => {
        try {
          const [statusResponse, logsResponse, agentResponse] = await Promise.all([
            fetch(buildApiUrl(`/api/jobs/${jobId}`)),
            fetch(buildApiUrl(`/api/jobs/${jobId}/logs`)),
            fetch(buildApiUrl(`/api/jobs/${jobId}/agent-stats`)).catch(() => null),
          ]);

          // Update logs and agent stats on the step
          const agentStats = agentResponse?.ok ? await agentResponse.json().catch(() => null) : null;

          if (logsResponse.ok) {
            const logsData = await logsResponse.json();
            const logLines = (logsData.logs || []).filter(l => l.trim());
            if (stepId) {
              setWorkflowSteps((prev) =>
                prev.map((s) => s.id === stepId ? {
                  ...s,
                  ...(logLines.length > 0 ? { logs: logLines } : {}),
                  ...(agentStats?.agent_stats ? { agentStats: agentStats.agent_stats } : {}),
                } : s)
              );
            }
          }

          if (statusResponse.ok) {
            const job = await statusResponse.json();
            if (job.status === 'completed') {
              clearInterval(interval);
              resolve(true);
            } else if (job.status === 'failed') {
              clearInterval(interval);
              resolve(false);
            }
          } else if (statusResponse.status === 404) {
            // Job was cleaned up — process already finished
            clearInterval(interval);
            resolve(true);
          }
        } catch (e) {
          // Keep polling
        }
      }, 3000);

      // Safety timeout (90 min)
      setTimeout(() => {
        clearInterval(interval);
        resolve(false);
      }, 90 * 60 * 1000);
    });
  };

  // ---- Clear workflow ----
  const clearWorkflow = () => {
    setWorkflowSteps([]);
    setWorkflowName('My Workflow');
    setStopOnFailure(true);
    setGlobalVars({});
    setActiveOutputStepId(null);
    localStorage.removeItem('capa-workflow-last-run');
  };

  // ============================================================================
  // Render
  // ============================================================================
  return (
    <div className="flex gap-6 h-[calc(100vh-180px)] overflow-hidden">
      {/* ---- Left: Playbook Palette ---- */}
      <div className="w-72 flex-shrink-0 flex flex-col bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
          <h3 className="text-sm font-semibold text-gray-900">Playbooks</h3>
          <p className="text-xs text-gray-500 mt-0.5">Drag to add to workflow</p>
        </div>

        {/* Search */}
        <div className="px-3 py-2 border-b border-gray-100">
          <input
            type="text"
            placeholder="Search playbooks..."
            value={paletteSearch}
            onChange={(e) => setPaletteSearch(e.target.value)}
            className="w-full text-sm border border-gray-300 rounded-md px-2.5 py-1.5 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>

        {/* Category filter */}
        <div className="px-3 py-2 border-b border-gray-100 flex flex-wrap gap-1">
          {['all', 'Validation', 'Configuration', 'Provisioning', 'Cleanup', 'Other'].map((cat) => (
            <button
              key={cat}
              onClick={() => setPaletteCategory(cat)}
              className={`text-xs px-2 py-1 rounded-full transition-colors ${
                paletteCategory === cat
                  ? 'bg-blue-100 text-blue-700 font-medium'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {cat === 'all' ? 'All' : cat}
            </button>
          ))}
        </div>

        {/* Playbook list */}
        <div className="flex-1 overflow-y-auto px-3 py-2 space-y-3">
          {loading ? (
            <div className="text-center py-8">
              <ArrowPathIcon className="h-6 w-6 text-gray-400 mx-auto animate-spin" />
              <p className="text-xs text-gray-500 mt-2">Loading...</p>
            </div>
          ) : Object.keys(groupedPlaybooks).length === 0 ? (
            <p className="text-xs text-gray-500 text-center py-4">No playbooks found</p>
          ) : (
            Object.entries(groupedPlaybooks).map(([category, suites]) => (
              <div key={category}>
                <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">
                  {category} ({suites.length})
                </h4>
                <div className="space-y-1.5">
                  {suites.map((suite) => (
                    <PlaybookPaletteItem
                      key={suite.name}
                      suite={suite}
                      onAdd={addStep}
                    />
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* ---- Center: Workflow Canvas ---- */}
      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        {/* Toolbar */}
        <div className="flex items-center justify-between px-4 py-3 bg-white rounded-t-lg border border-gray-200 border-b-0">
          <div className="flex items-center gap-3">
            <input
              type="text"
              value={workflowName}
              onChange={(e) => setWorkflowName(e.target.value)}
              className="text-lg font-bold text-gray-900 border-0 border-b-2 border-transparent hover:border-gray-300 focus:border-blue-500 focus:ring-0 bg-transparent px-1 py-0.5 transition-colors"
              placeholder="Workflow name..."
            />
            <span className="text-xs text-gray-400">
              {workflowSteps.length} step{workflowSteps.length !== 1 ? 's' : ''}
            </span>
          </div>

          <div className="flex items-center gap-2">
            {/* Stop on failure toggle */}
            <label className="flex items-center gap-2 text-sm text-gray-600 mr-2">
              <input
                type="checkbox"
                checked={stopOnFailure}
                onChange={(e) => setStopOnFailure(e.target.checked)}
                className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
              />
              Stop on failure
            </label>

            {/* Save */}
            <button
              onClick={() => setShowSaveDialog(true)}
              disabled={workflowSteps.length === 0}
              className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Save
            </button>

            {/* Load */}
            <button
              onClick={() => setShowSavedList(!showSavedList)}
              className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors flex items-center gap-1.5"
            >
              <FolderOpenIcon className="h-4 w-4" />
              Load
            </button>

            {/* Clear */}
            <button
              onClick={clearWorkflow}
              disabled={workflowSteps.length === 0 || isRunning}
              className="px-3 py-1.5 text-sm font-medium text-red-600 bg-white border border-red-200 rounded-md hover:bg-red-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Clear
            </button>

            {/* Run */}
            <button
              onClick={runWorkflow}
              disabled={workflowSteps.length === 0 || isRunning}
              className={`px-4 py-1.5 text-sm font-medium text-white rounded-md flex items-center gap-2 transition-colors ${
                isRunning
                  ? 'bg-gray-400 cursor-not-allowed'
                  : 'bg-blue-600 hover:bg-blue-700'
              }`}
            >
              {isRunning ? (
                <>
                  <ArrowPathIcon className="h-4 w-4 animate-spin" />
                  Running...
                </>
              ) : (
                <>
                  <PlayIcon className="h-4 w-4" />
                  Run Workflow
                </>
              )}
            </button>
          </div>
        </div>

        {/* Saved workflows dropdown */}
        {showSavedList && (
          <div className="mx-0 bg-white border-x border-gray-200 shadow-inner">
            <div className="px-4 py-2 border-b border-gray-100">
              <h4 className="text-sm font-semibold text-gray-700">Saved Workflows</h4>
            </div>
            {savedWorkflows.length === 0 ? (
              <p className="px-4 py-3 text-sm text-gray-500">No saved workflows yet</p>
            ) : (
              <div className="max-h-48 overflow-y-auto">
                {savedWorkflows.map((wf) => (
                  <div
                    key={wf.id}
                    className="flex items-center justify-between px-4 py-2 hover:bg-gray-50 transition-colors"
                  >
                    <button
                      onClick={() => loadWorkflow(wf)}
                      className="flex-1 text-left"
                    >
                      <div className="text-sm font-medium text-gray-900">{wf.name}</div>
                      <div className="text-xs text-gray-500">
                        {wf.steps.length} steps - saved {new Date(wf.savedAt).toLocaleDateString()}
                      </div>
                    </button>
                    <button
                      onClick={() => deleteWorkflow(wf.id)}
                      className="p-1 text-gray-400 hover:text-red-600 transition-colors"
                    >
                      <TrashIcon className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Global Variables Panel */}
        <div className="bg-white border-x border-gray-200">
          <button
            onClick={() => setShowGlobalVars(!showGlobalVars)}
            className="w-full flex items-center justify-between px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
          >
            <div className="flex items-center gap-2">
              {showGlobalVars ? <ChevronDownIcon className="h-4 w-4" /> : <ChevronRightIcon className="h-4 w-4" />}
              <span>Workflow Variables</span>
              {Object.keys(globalVars).length > 0 && (
                <span className="text-xs px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded-full">
                  {Object.keys(globalVars).length}
                </span>
              )}
            </div>
            <span className="text-xs text-gray-400">Shared across all steps</span>
          </button>

          {showGlobalVars && (
            <div className="px-4 pb-3 border-t border-gray-100 space-y-2">
              <div className="flex items-center justify-between pt-2">
                <p className="text-xs text-gray-500">Set once, passed to every step. Step-level vars override these.</p>
                <button
                  onClick={() => {
                    const key = `var_${Object.keys(globalVars).length}`;
                    setGlobalVars((prev) => ({ ...prev, [key]: '' }));
                  }}
                  className="text-xs text-blue-600 hover:text-blue-800 font-medium flex items-center gap-1"
                >
                  <PlusIcon className="h-3 w-3" />
                  Add variable
                </button>
              </div>

              {/* Common variable presets */}
              {Object.keys(globalVars).length === 0 && (
                <div className="flex flex-wrap gap-1.5 py-1">
                  <button
                    onClick={() => setGlobalVars({
                      name_prefix: '',
                      OCP_HUB_API_URL: '',
                      OCP_HUB_CLUSTER_USER: '',
                      OCP_HUB_CLUSTER_PASSWORD: '',
                      MCE_NAMESPACE: 'multicluster-engine',
                      AWS_ACCESS_KEY_ID: '',
                      AWS_SECRET_ACCESS_KEY: '',
                      AWS_ACCOUNT_ID: '',
                      OCM_CLIENT_ID: '',
                      OCM_CLIENT_SECRET: '',
                    })}
                    className="text-xs px-2.5 py-1 bg-blue-100 text-blue-700 hover:bg-blue-200 rounded-md transition-colors border border-blue-200 font-medium"
                  >
                    + Add All Credentials
                  </button>
                  {[
                    { key: 'name_prefix', label: 'name_prefix' },
                    { key: 'OCP_HUB_API_URL', label: 'OCP API URL' },
                    { key: 'OCP_HUB_CLUSTER_USER', label: 'OCP User' },
                    { key: 'OCP_HUB_CLUSTER_PASSWORD', label: 'OCP Password' },
                    { key: 'MCE_NAMESPACE', label: 'MCE Namespace' },
                    { key: 'AWS_ACCESS_KEY_ID', label: 'AWS Key ID' },
                    { key: 'AWS_SECRET_ACCESS_KEY', label: 'AWS Secret' },
                    { key: 'AWS_ACCOUNT_ID', label: 'AWS Account ID' },
                    { key: 'OCM_CLIENT_ID', label: 'OCM Client ID' },
                    { key: 'OCM_CLIENT_SECRET', label: 'OCM Client Secret' },
                  ].map((preset) => (
                    <button
                      key={preset.key}
                      onClick={() => setGlobalVars((prev) => ({ ...prev, [preset.key]: '' }))}
                      className="text-xs px-2 py-1 bg-gray-100 text-gray-600 hover:bg-blue-50 hover:text-blue-700 rounded-md transition-colors border border-gray-200"
                    >
                      + {preset.label}
                    </button>
                  ))}
                </div>
              )}

              {Object.keys(globalVars).length > 0 && (
                <div className="space-y-1.5">
                  {Object.entries(globalVars).map(([key, val]) => (
                    <div key={key} className="flex items-center gap-2">
                      <input
                        type="text"
                        defaultValue={key}
                        placeholder="key"
                        onBlur={(e) => {
                          const newKey = e.target.value.trim();
                          if (newKey && newKey !== key) {
                            setGlobalVars((prev) => {
                              const updated = { ...prev };
                              const value = updated[key];
                              delete updated[key];
                              updated[newKey] = value;
                              return updated;
                            });
                          }
                        }}
                        className="flex-1 text-xs font-mono border border-gray-300 rounded px-2 py-1.5 focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                      />
                      <span className="text-gray-400 text-xs">=</span>
                      <input
                        type={key.toLowerCase().includes('password') || key.toLowerCase().includes('secret') || key.toLowerCase().includes('access_key') ? 'password' : 'text'}
                        value={String(val)}
                        placeholder="value"
                        onChange={(e) => {
                          setGlobalVars((prev) => ({ ...prev, [key]: e.target.value }));
                        }}
                        className="flex-1 text-xs font-mono border border-gray-300 rounded px-2 py-1.5 focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                      />
                      <button
                        onClick={() => {
                          setGlobalVars((prev) => {
                            const updated = { ...prev };
                            delete updated[key];
                            return updated;
                          });
                        }}
                        className="p-0.5 text-gray-400 hover:text-red-500 transition-colors"
                      >
                        <XCircleIcon className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Canvas */}
        <div
          className="flex-1 bg-gray-50 border border-gray-200 rounded-b-lg overflow-y-auto p-6 transition-all"
          onDrop={handleCanvasDrop}
          onDragOver={handleCanvasDragOver}
          onDragLeave={handleCanvasDragLeave}
        >
          {workflowSteps.length === 0 ? (
            <div className="h-full flex items-center justify-center">
              <div className="text-center">
                <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gray-100 flex items-center justify-center">
                  <PlusIcon className="h-8 w-8 text-gray-400" />
                </div>
                <h3 className="text-lg font-medium text-gray-600 mb-1">Build your workflow</h3>
                <p className="text-sm text-gray-500 max-w-sm">
                  Drag playbooks from the palette on the left, or click the + button to add steps to your workflow.
                </p>
              </div>
            </div>
          ) : (
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragStart={handleDragStart}
              onDragEnd={handleDragEnd}
            >
              <SortableContext
                items={workflowSteps.map((s) => s.id)}
                strategy={verticalListSortingStrategy}
              >
                <div className="max-w-2xl mx-auto space-y-0">
                  {workflowSteps.map((step, index) => (
                    <SortableStep
                      key={step.id}
                      step={step}
                      index={index}
                      totalSteps={workflowSteps.length}
                      onRemove={removeStep}
                      onToggleConfig={toggleConfig}
                      onUpdateStep={updateStep}
                      isOutputActive={activeOutputStepId === step.id}
                      onToggleOutput={(id) => setActiveOutputStepId(activeOutputStepId === id ? null : id)}
                    />
                  ))}
                </div>
              </SortableContext>
            </DndContext>
          )}
        </div>

        {/* Output Panel — below the canvas */}
        {activeOutputStepId && (() => {
          const activeStep = workflowSteps.find(s => s.id === activeOutputStepId);
          if (!activeStep || !(activeStep.logs || []).length) return null;
          return (
            <div className="mt-3 bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2 bg-gray-50 border-b border-gray-200">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-gray-700">Output:</span>
                  <span className="text-sm text-gray-600">{activeStep.name}</span>
                  {activeStep.status === 'running' && (
                    <ArrowPathIcon className="h-4 w-4 text-blue-500 animate-spin" />
                  )}
                  {activeStep.status === 'completed' && (
                    <CheckCircleIcon className="h-4 w-4 text-green-500" />
                  )}
                  {activeStep.status === 'failed' && (
                    <XCircleIcon className="h-4 w-4 text-red-500" />
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-400">{activeStep.logs.length} lines</span>
                  <button
                    onClick={() => setActiveOutputStepId(null)}
                    className="p-1 text-gray-400 hover:text-gray-600 transition-colors"
                    title="Close output"
                  >
                    <XCircleIcon className="h-4 w-4" />
                  </button>
                </div>
              </div>
              <StepOutputPanel logs={activeStep.logs} status={activeStep.status} agentStats={activeStep.agentStats} />
            </div>
          );
        })()}
      </div>

      {/* Save dialog */}
      {showSaveDialog && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 w-96">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Save Workflow</h3>
            <input
              type="text"
              value={workflowName}
              onChange={(e) => setWorkflowName(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 mb-4 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="Workflow name..."
              autoFocus
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowSaveDialog(false)}
                className="px-4 py-2 text-sm text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={saveWorkflow}
                disabled={!workflowName.trim()}
                className="px-4 py-2 text-sm text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default WorkflowBuilder;
