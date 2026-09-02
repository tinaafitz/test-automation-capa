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
  ArrowDownTrayIcon,
  ArrowUpTrayIcon,
  MagnifyingGlassIcon,
  BookmarkIcon,
  RocketLaunchIcon,
  ServerIcon,
  ShieldCheckIcon,
  XMarkIcon,
  StarIcon,
  EllipsisVerticalIcon,
} from '@heroicons/react/24/outline';
import { BookmarkIcon as BookmarkSolidIcon } from '@heroicons/react/24/solid';
import { buildApiUrl } from '../config/api';
import { useRecentOperationsContext } from '../store/AppContext';
import TriggerPanel from './TriggerPanel';

// ============================================================================
// Draggable Playbook Card (in the palette)
// ============================================================================
const categoryColors = {
  Validation: { bg: 'bg-teal-50', border: 'border-teal-200', text: 'text-teal-700', dot: 'bg-teal-400' },
  Configuration: { bg: 'bg-violet-50', border: 'border-violet-200', text: 'text-violet-700', dot: 'bg-violet-400' },
  Provisioning: { bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-700', dot: 'bg-blue-400' },
  Cleanup: { bg: 'bg-orange-50', border: 'border-orange-200', text: 'text-orange-700', dot: 'bg-orange-400' },
  Other: { bg: 'bg-gray-50', border: 'border-gray-200', text: 'text-gray-700', dot: 'bg-gray-400' },
};

const PlaybookPaletteItem = ({ suite, onAdd, category }) => {
  const colors = categoryColors[category] || categoryColors.Other;
  return (
    <div
      className={`flex items-center gap-2.5 px-3 py-2.5 bg-white border ${colors.border} rounded-xl cursor-grab hover:shadow-md hover:-translate-y-0.5 transition-all duration-200 group`}
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData('application/json', JSON.stringify(suite));
        e.dataTransfer.effectAllowed = 'copy';
      }}
      title={`${suite.name}\n${suite.description || ''}`}
    >
      <div className={`w-1.5 h-8 rounded-full ${colors.dot} flex-shrink-0`} />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-gray-900 line-clamp-2 leading-snug">{suite.name}</div>
        <div className="text-xs text-gray-500 line-clamp-2">{suite.description}</div>
      </div>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onAdd(suite);
        }}
        className="flex-shrink-0 p-1.5 text-gray-300 hover:text-white hover:bg-indigo-500 rounded-lg transition-all duration-200 opacity-0 group-hover:opacity-100"
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
const stepCategoryColors = {
  Validation: { accent: 'bg-teal-400', badge: 'bg-teal-100 text-teal-700' },
  Configuration: { accent: 'bg-violet-400', badge: 'bg-violet-100 text-violet-700' },
  Provisioning: { accent: 'bg-blue-400', badge: 'bg-blue-100 text-blue-700' },
  Cleanup: { accent: 'bg-orange-400', badge: 'bg-orange-100 text-orange-700' },
  Other: { accent: 'bg-gray-400', badge: 'bg-gray-100 text-gray-700' },
};

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

  const statusStyles = {
    pending: { card: 'border-gray-200 bg-white shadow-sm hover:shadow-md', accent: 'bg-gray-400', iconBg: 'bg-gray-50', iconText: 'text-gray-600' },
    running: { card: 'border-blue-400 bg-gradient-to-r from-blue-50 to-white ring-2 ring-blue-100 shadow-md shadow-blue-100/50', accent: 'bg-blue-500', iconBg: 'bg-blue-100', iconText: 'text-blue-600' },
    completed: { card: 'border-emerald-400 bg-gradient-to-r from-emerald-50 to-white shadow-sm hover:shadow-md', accent: 'bg-emerald-500', iconBg: 'bg-emerald-100', iconText: 'text-emerald-600' },
    failed: { card: 'border-red-400 bg-gradient-to-r from-red-50 to-white shadow-sm hover:shadow-md', accent: 'bg-red-500', iconBg: 'bg-red-100', iconText: 'text-red-600' },
    skipped: { card: 'border-amber-300 bg-gradient-to-r from-amber-50 to-white shadow-sm hover:shadow-md', accent: 'bg-amber-400', iconBg: 'bg-amber-100', iconText: 'text-amber-600' },
  };

  const st = statusStyles[step.status] || statusStyles.pending;

  const statusIcons = {
    pending: (
      <div className={`w-7 h-7 rounded-full ${st.iconBg} flex items-center justify-center text-xs font-bold ${st.iconText} flex-shrink-0 border border-gray-200`}>
        {index + 1}
      </div>
    ),
    running: (
      <div className="w-7 h-7 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0 border-2 border-blue-400 ring-2 ring-blue-200 animate-pulse">
        <ArrowPathIcon className="h-4 w-4 text-blue-600 animate-spin" />
      </div>
    ),
    completed: (
      <div className="w-7 h-7 rounded-full bg-emerald-100 flex items-center justify-center flex-shrink-0 border border-emerald-300">
        <CheckCircleIcon className="h-4 w-4 text-emerald-600" />
      </div>
    ),
    failed: (
      <div className="w-7 h-7 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0 border border-red-300">
        <XCircleIcon className="h-4 w-4 text-red-600" />
      </div>
    ),
    skipped: (
      <div className="w-7 h-7 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0 border border-amber-300">
        <ClockIcon className="h-4 w-4 text-amber-600" />
      </div>
    ),
  };

  const formatDuration = (start, end) => {
    const secs = Math.round(((end || Date.now()) - start) / 1000);
    if (secs < 60) return `${secs}s`;
    return `${Math.floor(secs / 60)}m ${secs % 60}s`;
  };

  return (
    <div ref={setNodeRef} style={style}>
      {/* Connector */}
      {index > 0 && (
        <div className="flex flex-col items-center py-1">
          <div className={`w-0.5 h-3 ${step.status === 'running' ? 'bg-blue-400' : step.status === 'completed' ? 'bg-emerald-400' : 'bg-gray-300'} rounded-full`} />
          <ArrowDownIcon className={`h-4 w-4 -mt-0.5 ${step.status === 'running' ? 'text-blue-500' : step.status === 'completed' ? 'text-emerald-500' : 'text-gray-400'}`} />
        </div>
      )}

      {/* Step card */}
      <div className={`rounded-lg border-2 ${st.card} transition-all duration-300 overflow-hidden`}>
        {/* Color accent bar — uses category color when pending, status color when running/completed/failed */}
        <div className={`h-0.5 ${step.status === 'pending' ? (stepCategoryColors[step.category]?.accent || st.accent) : st.accent} transition-all duration-500`} />

        {/* Animated progress bar for running steps */}
        {step.status === 'running' && (
          <div className="h-0.5 bg-blue-100 overflow-hidden">
            <div className="h-full bg-gradient-to-r from-blue-400 via-blue-500 to-blue-400 animate-[shimmer_1.5s_ease-in-out_infinite]"
              style={{ width: '40%', animation: 'shimmer 3s ease-in-out infinite' }}
            />
            <style>{`@keyframes shimmer { 0% { transform: translateX(-100%); } 100% { transform: translateX(350%); } }`}</style>

          </div>
        )}

        <div className="flex items-center gap-2.5 px-3.5 py-2.5">
          {/* Drag handle */}
          <div
            {...attributes}
            {...listeners}
            className="cursor-grab active:cursor-grabbing text-gray-300 hover:text-gray-500 flex-shrink-0 transition-colors"
            title="Drag to reorder"
          >
            <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
              <path d="M7 2a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM13 2a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM7 8a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM13 8a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM7 14a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM13 14a2 2 0 1 0 0 4 2 2 0 0 0 0-4z" />
            </svg>
          </div>

          {/* Status icon */}
          {statusIcons[step.status]}

          {/* Step info — single line, name only */}
          <div className="flex-1 min-w-0 flex items-center gap-2">
            <span className="text-sm font-semibold text-gray-900 truncate">{step.name}</span>
            {step.startedAt && (
              <span className={`flex-shrink-0 font-mono px-1.5 py-0.5 rounded text-[10px] ${
                step.status === 'running' ? 'bg-blue-100 text-blue-700' :
                step.status === 'completed' ? 'bg-emerald-100 text-emerald-700' :
                step.status === 'failed' ? 'bg-red-100 text-red-700' :
                'bg-gray-100 text-gray-600'
              }`}>
                {formatDuration(step.startedAt, step.completedAt)}
                {step.status === 'running' && '...'}
              </span>
            )}
          </div>

          {/* Step badges */}
          <div className="flex items-center gap-1.5 flex-shrink-0">
            {step.category && (
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-wider ${stepCategoryColors[step.category]?.badge || 'bg-gray-100 text-gray-700'}`}>
                {step.category}
              </span>
            )}
            {step.on_failure === 'skip' && (
              <span className="text-[10px] px-2 py-0.5 bg-amber-100 text-amber-700 rounded-full font-semibold uppercase tracking-wider">Skip on fail</span>
            )}
            {step.on_failure === 'retry' && (
              <span className="text-[10px] px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full font-semibold uppercase tracking-wider">Retry</span>
            )}
            {step.required && (
              <span className="text-[10px] px-2 py-0.5 bg-purple-100 text-purple-700 rounded-full font-semibold uppercase tracking-wider">Required</span>
            )}
            {step.condition && (
              <span className="text-[10px] px-2 py-0.5 bg-yellow-100 text-yellow-700 rounded-full font-semibold uppercase tracking-wider">if: {step.condition}</span>
            )}
          </div>

          {/* Config toggle */}
          <button
            onClick={() => onToggleConfig(step.id)}
            className="relative p-1 text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-md transition-all flex-shrink-0"
            title="Configure step"
          >
            <Cog6ToothIcon className="h-3.5 w-3.5" />
            {Object.keys(step.vars || {}).length > 0 && (
              <span className="absolute -top-1 -right-1 w-4 h-4 bg-indigo-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center">
                {Object.keys(step.vars).length}
              </span>
            )}
          </button>

          {/* Output toggle (when logs exist) */}
          {(step.logs || []).length > 0 && (
            <button
              onClick={() => onToggleOutput(step.id)}
              className={`p-1 rounded-md transition-all flex-shrink-0 ${
                isOutputActive ? 'text-indigo-600 bg-indigo-100 ring-2 ring-indigo-200' : 'text-gray-400 hover:text-indigo-600 hover:bg-indigo-50'
              }`}
              title={isOutputActive ? 'Hide output' : 'Show output'}
            >
              <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M2 4.75A.75.75 0 012.75 4h14.5a.75.75 0 010 1.5H2.75A.75.75 0 012 4.75zm0 10.5a.75.75 0 01.75-.75h7.5a.75.75 0 010 1.5h-7.5a.75.75 0 01-.75-.75zM2 10a.75.75 0 01.75-.75h14.5a.75.75 0 010 1.5H2.75A.75.75 0 012 10z" clipRule="evenodd" />
              </svg>
            </button>
          )}

          {/* Remove button */}
          <button
            onClick={() => onRemove(step.id)}
            className="p-1 text-gray-300 hover:text-red-600 hover:bg-red-50 rounded-md transition-all flex-shrink-0"
            title="Remove step"
          >
            <TrashIcon className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Expanded config panel */}
        {step.showConfig && (
          <div className="border-t border-gray-100 px-4 py-4 bg-gradient-to-b from-slate-50/50 to-white space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">On Failure</label>
                <select
                  value={step.on_failure}
                  onChange={(e) => onUpdateStep(step.id, { on_failure: e.target.value })}
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
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Condition (if)</label>
              <select
                value={step.condition || ''}
                onChange={(e) => onUpdateStep(step.id, { condition: e.target.value || undefined })}
                className="w-full text-sm border border-gray-300 rounded-md px-2 py-1.5 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="">Always run (default)</option>
                <option value="always">always — run even after failures</option>
                <option value="success">success — only if all prior steps passed</option>
                <option value="failure">failure — only if a prior step failed</option>
              </select>
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
                    const updated = { ...(step.vars || {}), '': '' };
                    // Use a unique placeholder key
                    const key = `new_var_${Object.keys(step.vars || {}).length}`;
                    updated[key] = '';
                    onUpdateStep(step.id, { vars: updated });
                  }}
                  className="text-xs text-blue-600 hover:text-blue-800 font-medium flex items-center gap-1"
                >
                  <PlusIcon className="h-3 w-3" />
                  Add variable
                </button>
              </div>
              {Object.keys(step.vars || {}).length > 0 ? (
                <div className="space-y-1.5">
                  {Object.entries(step.vars || {}).map(([key, val]) => (
                    <div key={key} className="flex items-center gap-2">
                      <input
                        type="text"
                        defaultValue={key}
                        placeholder="key"
                        onBlur={(e) => {
                          const newKey = e.target.value.trim();
                          if (newKey && newKey !== key) {
                            const vars = { ...step.vars };
                            const value = vars[key];
                            delete vars[key];
                            vars[newKey] = value;
                            onUpdateStep(step.id, { vars: vars });
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
                          const vars = { ...step.vars };
                          // Try to parse booleans and numbers
                          let parsed = e.target.value;
                          if (parsed === 'true') parsed = true;
                          else if (parsed === 'false') parsed = false;
                          else if (parsed !== '' && !isNaN(parsed) && !isNaN(parseFloat(parsed))) parsed = parseFloat(parsed);
                          vars[key] = parsed;
                          onUpdateStep(step.id, { vars: vars });
                        }}
                        className="flex-1 text-xs font-mono border border-gray-300 rounded px-2 py-1 focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                      />
                      <button
                        onClick={() => {
                          const vars = { ...step.vars };
                          delete vars[key];
                          onUpdateStep(step.id, { vars: vars });
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

  // Saved workflows & library
  const [savedWorkflows, setSavedWorkflows] = useState([]);
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [saveDescription, setSaveDescription] = useState('');
  const [workflowTemplates, setWorkflowTemplates] = useState([]);
  const [yamlWorkflows, setYamlWorkflows] = useState([]);
  const [librarySearch, setLibrarySearch] = useState('');
  const [libraryTab, setLibraryTab] = useState('saved'); // 'saved' | 'templates' | 'yaml'
  const [activeWorkflowId, setActiveWorkflowId] = useState(null);
  const [showOverwriteConfirm, setShowOverwriteConfirm] = useState(false);
  const [contextMenuId, setContextMenuId] = useState(null);
  const [paletteTab, setPaletteTab] = useState('playbooks'); // 'playbooks' | 'workflows'
  const fileInputRef = useRef(null);

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
    loadWorkflowTemplates();
    loadYamlWorkflows();
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

  const sortedPlaybooks = [...filteredPlaybooks].sort((a, b) =>
    (a.name || '').localeCompare(b.name || '')
  );

  // ---- Add step to workflow ----
  const addStep = useCallback((suite) => {
    const playbook = suite.playbooks?.[0] || {};
    const newStep = {
      id: `step-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      name: suite.name,
      description: suite.description || '',
      playbook: playbook.file || playbook.playbook || '',
      suiteName: suite.name,
      category: categorizePlaybook(suite),
      required: playbook.required !== undefined ? playbook.required : false,
      on_failure: 'stop',
      timeout: playbook.timeout || 600,
      vars: playbook.vars || playbook.extra_vars || {},
      status: 'pending',
      showConfig: Object.keys(playbook.vars || playbook.extra_vars || {}).length > 0,
    };
    setWorkflowSteps((prev) => [...prev, newStep]);
  }, [categorizePlaybook]);

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

  // ---- Save / Load workflows (backend-backed) ----
  const loadSavedWorkflows = async () => {
    try {
      const res = await fetch(buildApiUrl('/api/workflows'));
      if (res.ok) {
        const data = await res.json();
        setSavedWorkflows(data.workflows || []);
      }
    } catch (e) {
      console.error('Failed to load workflows:', e);
      // Fallback to localStorage
      try {
        const saved = localStorage.getItem('capa-workflows');
        if (saved) setSavedWorkflows(JSON.parse(saved));
      } catch (err) { /* ignore */ }
    }
  };

  const loadWorkflowTemplates = async () => {
    try {
      const res = await fetch(buildApiUrl('/api/workflows/templates/list'));
      if (res.ok) {
        const data = await res.json();
        setWorkflowTemplates(data.templates || []);
      }
    } catch (e) {
      console.error('Failed to load templates:', e);
    }
  };

  const loadYamlWorkflows = async () => {
    try {
      const res = await fetch(buildApiUrl('/api/workflows/yaml'));
      if (res.ok) {
        const data = await res.json();
        setYamlWorkflows(data.workflows || []);
      }
    } catch (e) {
      console.error('Failed to load YAML workflows:', e);
    }
  };

  const saveWorkflow = async () => {
    if (!workflowName.trim() || workflowSteps.length === 0) return;

    // Check for existing workflow with same name
    const existing = savedWorkflows.find((w) => w.name === workflowName && w.id !== activeWorkflowId);
    if (existing && !showOverwriteConfirm) {
      setShowOverwriteConfirm(true);
      return;
    }

    try {
      const res = await fetch(buildApiUrl('/api/workflows'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: workflowName,
          description: saveDescription,
          stop_on_failure: stopOnFailure,
          vars: globalVars,
          steps: workflowSteps.map(({ id, showConfig, status, logs, agentStats, startedAt, completedAt, ...rest }) => rest),
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setActiveWorkflowId(data.workflow.id);
        await loadSavedWorkflows();
      }
    } catch (e) {
      console.error('Failed to save workflow:', e);
    }

    setShowSaveDialog(false);
    setShowOverwriteConfirm(false);
    setSaveDescription('');
  };

  // Normalize a workflow object to the canonical format (handles both old camelCase and new snake_case)
  const normalizeWorkflow = (wf) => ({
    ...wf,
    stop_on_failure: wf.stop_on_failure ?? wf.stopOnFailure ?? true,
    vars: wf.vars || wf.globalVars || {},
    steps: (wf.steps || []).map((s) => ({
      ...s,
      playbook: s.playbook || s.file || '',
      on_failure: s.on_failure || s.onFailure || 'stop',
      vars: s.vars || s.extra_vars || {},
    })),
  });

  const loadWorkflow = async (workflow) => {
    // If it's a template or YAML workflow, load directly from data (no backend fetch needed)
    if (workflow.id?.startsWith('tpl-') || workflow.id?.startsWith('yaml-')) {
      const wf = normalizeWorkflow(workflow);
      setWorkflowName(wf.name);
      setStopOnFailure(wf.stop_on_failure);
      setGlobalVars(wf.vars);
      setWorkflowSteps(
        wf.steps.map((step, i) => ({
          ...step,
          id: `step-${Date.now()}-${i}`,
          status: 'pending',
          showConfig: false,
        }))
      );
      setActiveWorkflowId(null);
      setPaletteTab('playbooks');
      return;
    }

    // Fetch full workflow from backend
    try {
      const res = await fetch(buildApiUrl(`/api/workflows/${workflow.id}`));
      if (res.ok) {
        const data = await res.json();
        const wf = normalizeWorkflow(data.workflow);
        setWorkflowName(wf.name);
        setStopOnFailure(wf.stop_on_failure);
        setGlobalVars(wf.vars);
        setSaveDescription(wf.description || '');
        setWorkflowSteps(
          wf.steps.map((step, i) => ({
            ...step,
            id: `step-${Date.now()}-${i}`,
            status: 'pending',
            showConfig: false,
          }))
        );
        setActiveWorkflowId(wf.id);
      }
    } catch (e) {
      console.error('Failed to load workflow:', e);
    }
    setPaletteTab('playbooks');
  };

  const deleteWorkflow = async (workflowId) => {
    try {
      await fetch(buildApiUrl(`/api/workflows/${workflowId}`), { method: 'DELETE' });
      await loadSavedWorkflows();
      if (activeWorkflowId === workflowId) setActiveWorkflowId(null);
    } catch (e) {
      console.error('Failed to delete workflow:', e);
    }
  };

  const duplicateWorkflow = async (workflowId) => {
    try {
      await fetch(buildApiUrl(`/api/workflows/${workflowId}/duplicate`), { method: 'POST' });
      await loadSavedWorkflows();
    } catch (e) {
      console.error('Failed to duplicate workflow:', e);
    }
    setContextMenuId(null);
  };

  const exportWorkflow = async (workflow) => {
    let wfData;
    if (workflow.steps) {
      wfData = workflow;
    } else {
      try {
        const res = await fetch(buildApiUrl(`/api/workflows/${workflow.id}`));
        if (!res.ok) return;
        const data = await res.json();
        wfData = data.workflow;
      } catch (e) { return; }
    }

    const exportData = {
      name: wfData.name,
      description: wfData.description || '',
      stopOnFailure: wfData.stopOnFailure,
      globalVars: wfData.globalVars || {},
      steps: (wfData.steps || []).map(({ id, showConfig, status, logs, agentStats, startedAt, completedAt, ...rest }) => rest),
      exportedAt: new Date().toISOString(),
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `workflow-${wfData.name.replace(/[^a-z0-9]/gi, '-').toLowerCase()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    setContextMenuId(null);
  };

  const importWorkflow = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = async (e) => {
      try {
        const data = JSON.parse(e.target.result);
        if (!data.name || !data.steps?.length) {
          alert('Invalid workflow file: must contain name and steps');
          return;
        }

        // Save imported workflow to backend
        await fetch(buildApiUrl('/api/workflows'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: data.name,
            description: data.description || `Imported on ${new Date().toLocaleDateString()}`,
            stopOnFailure: data.stopOnFailure ?? true,
            globalVars: data.globalVars || {},
            steps: data.steps,
          }),
        });
        await loadSavedWorkflows();
      } catch (err) {
        alert('Failed to import workflow: invalid JSON file');
      }
    };
    reader.readAsText(file);
    // Reset input so same file can be imported again
    event.target.value = '';
  };

  // ---- Run workflow ----
  const runWorkflow = async () => {
    if (workflowSteps.length === 0 || isRunning) return;

    setIsRunning(true);
    // Reset all steps to pending, clear logs
    setWorkflowSteps((prev) => prev.map((s) => ({ ...s, status: 'pending', logs: [] })));
    setActiveOutputStepId(null);

    // Mark workflow as run on backend
    if (activeWorkflowId) {
      fetch(buildApiUrl(`/api/workflows/${activeWorkflowId}/run`), { method: 'POST' }).catch(() => {});
    }

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
        const mergedVars = { ...globalVars, ...(step.vars || {}) };
        if (step.name.toLowerCase().includes('verify')) {
          mergedVars.soft_verify = 'true';
        }

        // Run the playbook via API
        const response = await fetch(buildApiUrl('/api/ansible/run-playbook'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            playbook: step.playbook,
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
          if (step.on_failure === 'retry') {
            // Retry once
            setWorkflowSteps((prev) =>
              prev.map((s, idx) => idx === i ? { ...s, status: 'running' } : s)
            );
            updateRecentOperationStatus(stepOpId, '⏳ Retrying...');
            const retryResponse = await fetch(buildApiUrl('/api/ansible/run-playbook'), {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                playbook: step.playbook,
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
          } else if (step.on_failure === 'stop' || (step.required && stopOnFailure)) {
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
      // Incremental log cursor: only fetch lines after what we've already seen.
      let logCursor = 0;
      let accumulatedLogs = [];
      const interval = setInterval(async () => {
        try {
          const [statusResponse, logsResponse, agentResponse] = await Promise.all([
            fetch(buildApiUrl(`/api/jobs/${jobId}`)),
            fetch(buildApiUrl(`/api/jobs/${jobId}/logs?since=${logCursor}`)),
            fetch(buildApiUrl(`/api/jobs/${jobId}/agent-stats`)).catch(() => null),
          ]);

          // Update logs and agent stats on the step
          const agentStats = agentResponse?.ok ? await agentResponse.json().catch(() => null) : null;

          if (logsResponse.ok) {
            const logsData = await logsResponse.json();
            // Backend echoes the `since` it applied; if it fell back to 0 (e.g.
            // job log was reset), start our accumulator over to stay in sync.
            if ((logsData.since ?? logCursor) === 0) {
              accumulatedLogs = [];
            }
            const newLines = (logsData.logs || []).filter(l => l.trim());
            if (newLines.length > 0) {
              accumulatedLogs = accumulatedLogs.concat(newLines);
            }
            if (typeof logsData.total === 'number') {
              logCursor = logsData.total;
            }
            if (stepId) {
              setWorkflowSteps((prev) =>
                prev.map((s) => s.id === stepId ? {
                  ...s,
                  ...(accumulatedLogs.length > 0 ? { logs: accumulatedLogs } : {}),
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
    setActiveWorkflowId(null);
    setSaveDescription('');
    localStorage.removeItem('capa-workflow-last-run');
  };

  // ---- Computed stats for status bar ----
  const completedSteps = workflowSteps.filter(s => s.status === 'completed').length;
  const failedSteps = workflowSteps.filter(s => s.status === 'failed').length;
  const runningSteps = workflowSteps.filter(s => s.status === 'running').length;
  const skippedSteps = workflowSteps.filter(s => s.status === 'skipped').length;
  const hasRunResults = completedSteps + failedSteps + skippedSteps > 0;
  const progressPercent = workflowSteps.length > 0
    ? Math.round(((completedSteps + failedSteps + skippedSteps) / workflowSteps.length) * 100)
    : 0;

  // ============================================================================
  // Render
  // ============================================================================
  return (
    <div className="flex gap-5 h-[calc(100vh-180px)] overflow-hidden">
      {/* ---- Left: Tabbed Palette (Playbooks / Workflows) ---- */}
      <div className="w-80 flex-shrink-0 flex flex-col rounded-2xl border border-gray-200 shadow-sm overflow-hidden bg-white">
        {/* Tab header */}
        <div className="bg-gradient-to-br from-slate-800 to-slate-900 px-2 pt-3 pb-0">
          <div className="flex">
            <button
              onClick={() => setPaletteTab('playbooks')}
              className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium rounded-t-xl transition-all ${
                paletteTab === 'playbooks'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <PlusIcon className="h-4 w-4" />
              Playbooks
            </button>
            <button
              onClick={() => { setPaletteTab('workflows'); loadSavedWorkflows(); }}
              className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium rounded-t-xl transition-all ${
                paletteTab === 'workflows'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <BookmarkIcon className="h-4 w-4" />
              Workflows
              {savedWorkflows.length > 0 && paletteTab !== 'workflows' && (
                <span className="text-[10px] px-1.5 py-0.5 bg-indigo-500 text-white rounded-full font-bold min-w-[18px] text-center">
                  {savedWorkflows.length}
                </span>
              )}
            </button>
          </div>
        </div>

        {/* ---- Playbooks Tab Content ---- */}
        {paletteTab === 'playbooks' && (
          <>
            {/* Search */}
            <div className="px-3 py-2.5 border-b border-gray-100">
              <div className="relative">
                <MagnifyingGlassIcon className="h-4 w-4 text-gray-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Search playbooks..."
                  value={paletteSearch}
                  onChange={(e) => setPaletteSearch(e.target.value)}
                  className="w-full text-sm border border-gray-200 rounded-lg pl-8 pr-3 py-1.5 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 bg-gray-50"
                />
              </div>
            </div>

            {/* Category filter */}
            <div className="px-3 py-2 border-b border-gray-100 flex flex-wrap gap-1">
              {['all', 'Validation', 'Configuration', 'Provisioning', 'Cleanup', 'Other'].map((cat) => {
                const catColor = categoryColors[cat] || {};
                const count = cat === 'all'
                  ? filteredPlaybooks.length
                  : availablePlaybooks.filter(s => categorizePlaybook(s) === cat).length;
                return (
                  <button
                    key={cat}
                    onClick={() => setPaletteCategory(cat)}
                    className={`text-xs px-2.5 py-1 rounded-lg transition-all duration-200 font-medium ${
                      paletteCategory === cat
                        ? cat === 'all'
                          ? 'bg-indigo-100 text-indigo-700 shadow-sm'
                          : `${catColor.bg || 'bg-indigo-100'} ${catColor.text || 'text-indigo-700'} shadow-sm`
                        : 'bg-gray-50 text-gray-500 hover:bg-gray-100 hover:text-gray-700'
                    }`}
                  >
                    {cat === 'all' ? `All (${count})` : `${cat} (${count})`}
                  </button>
                );
              })}
            </div>

            {/* Playbook list */}
            <div className="flex-1 overflow-y-auto px-3 py-2.5">
              {loading ? (
                <div className="text-center py-12">
                  <div className="w-10 h-10 mx-auto rounded-xl bg-indigo-100 flex items-center justify-center mb-3">
                    <ArrowPathIcon className="h-5 w-5 text-indigo-500 animate-spin" />
                  </div>
                  <p className="text-xs text-gray-500">Loading...</p>
                </div>
              ) : sortedPlaybooks.length === 0 ? (
                <div className="text-center py-8">
                  <p className="text-xs text-gray-400">No playbooks found</p>
                </div>
              ) : paletteCategory === 'all' ? (
                <div className="space-y-3">
                  {['Validation', 'Configuration', 'Provisioning', 'Cleanup', 'Other'].map((cat) => {
                    const items = sortedPlaybooks.filter(s => categorizePlaybook(s) === cat);
                    if (items.length === 0) return null;
                    const colors = categoryColors[cat];
                    return (
                      <div key={cat}>
                        <div className={`text-[10px] font-bold uppercase tracking-wider ${colors.text} mb-1.5 px-1 flex items-center gap-1.5`}>
                          <div className={`w-2 h-2 rounded-full ${colors.dot}`} />
                          {cat} ({items.length})
                        </div>
                        <div className="space-y-1.5">
                          {items.map((suite) => (
                            <PlaybookPaletteItem
                              key={suite.name}
                              suite={suite}
                              onAdd={addStep}
                              category={cat}
                            />
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="space-y-1.5">
                  {sortedPlaybooks.map((suite) => (
                    <PlaybookPaletteItem
                      key={suite.name}
                      suite={suite}
                      onAdd={addStep}
                      category={categorizePlaybook(suite)}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Palette footer */}
            <div className="px-3 py-2 border-t border-gray-100 bg-gray-50">
              <p className="text-[10px] text-gray-400 text-center">{sortedPlaybooks.length} playbooks available</p>
            </div>
          </>
        )}

        {/* ---- Workflows Tab Content ---- */}
        {paletteTab === 'workflows' && (
          <>
            {/* Search */}
            <div className="px-3 py-2.5 border-b border-gray-100">
              <div className="relative">
                <MagnifyingGlassIcon className="h-4 w-4 text-gray-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Search workflows..."
                  value={librarySearch}
                  onChange={(e) => setLibrarySearch(e.target.value)}
                  className="w-full text-sm border border-gray-200 rounded-lg pl-8 pr-3 py-1.5 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 bg-gray-50"
                />
              </div>
            </div>

            {/* Sub-tabs: Saved / Templates */}
            <div className="px-3 py-2 border-b border-gray-100 flex gap-1">
              <button
                onClick={() => setLibraryTab('saved')}
                className={`text-xs px-2.5 py-1 rounded-lg transition-all duration-200 font-medium flex items-center gap-1 ${
                  libraryTab === 'saved'
                    ? 'bg-indigo-100 text-indigo-700 shadow-sm'
                    : 'bg-gray-50 text-gray-500 hover:bg-gray-100'
                }`}
              >
                Saved
                {savedWorkflows.length > 0 && (
                  <span className="text-[10px] px-1 py-0 bg-indigo-200 text-indigo-700 rounded-full font-bold">
                    {savedWorkflows.length}
                  </span>
                )}
              </button>
              <button
                onClick={() => setLibraryTab('templates')}
                className={`text-xs px-2.5 py-1 rounded-lg transition-all duration-200 font-medium flex items-center gap-1 ${
                  libraryTab === 'templates'
                    ? 'bg-purple-100 text-purple-700 shadow-sm'
                    : 'bg-gray-50 text-gray-500 hover:bg-gray-100'
                }`}
              >
                Templates
                <span className="text-[10px] px-1 py-0 bg-purple-100 text-purple-600 rounded-full font-bold">
                  {workflowTemplates.length}
                </span>
              </button>
              {yamlWorkflows.length > 0 && (
                <button
                  onClick={() => setLibraryTab('yaml')}
                  className={`text-xs px-2.5 py-1 rounded-lg transition-all duration-200 font-medium flex items-center gap-1 ${
                    libraryTab === 'yaml'
                      ? 'bg-green-100 text-green-700 shadow-sm'
                      : 'bg-gray-50 text-gray-500 hover:bg-gray-100'
                  }`}
                >
                  YAML
                  <span className="text-[10px] px-1 py-0 bg-green-100 text-green-600 rounded-full font-bold">
                    {yamlWorkflows.length}
                  </span>
                </button>
              )}
            </div>

            {/* Workflow list */}
            <div className="flex-1 overflow-y-auto px-3 py-2.5">
              {libraryTab === 'saved' && (
                <>
                  {savedWorkflows.length === 0 ? (
                    <div className="text-center py-8">
                      <BookmarkIcon className="h-8 w-8 text-gray-300 mx-auto mb-2" />
                      <p className="text-xs text-gray-400 mb-1">No saved workflows yet</p>
                      <p className="text-[10px] text-gray-300">Build a workflow and click Save</p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {savedWorkflows
                        .filter((wf) => !librarySearch || wf.name.toLowerCase().includes(librarySearch.toLowerCase()) || (wf.description || '').toLowerCase().includes(librarySearch.toLowerCase()))
                        .map((wf) => (
                        <div
                          key={wf.id}
                          className={`group relative bg-white border rounded-xl p-3 hover:shadow-md transition-all cursor-pointer ${
                            activeWorkflowId === wf.id ? 'border-indigo-400 ring-2 ring-indigo-100' : 'border-gray-200 hover:border-indigo-300'
                          }`}
                          onClick={() => loadWorkflow(wf)}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-1.5">
                                <h4 className="text-sm font-semibold text-gray-900 truncate">{wf.name}</h4>
                                {activeWorkflowId === wf.id && (
                                  <span className="text-[9px] px-1 py-0 bg-indigo-100 text-indigo-600 rounded font-bold uppercase">Active</span>
                                )}
                              </div>
                              {wf.description && (
                                <p className="text-[11px] text-gray-400 mt-0.5 truncate">{wf.description}</p>
                              )}
                              <div className="flex items-center gap-2 mt-1.5">
                                <span className="text-[10px] text-gray-400">{wf.stepCount} steps</span>
                                {wf.hasGlobalVars && (
                                  <span className="text-[10px] text-gray-400">{wf.globalVarKeys?.length} vars</span>
                                )}
                              </div>
                              {/* Step name pills with category colors */}
                              <div className="flex flex-wrap gap-1 mt-1.5">
                                {(wf.stepNames || []).map((name, i) => {
                                  const nameLower = (name || '').toLowerCase();
                                  let cat = 'Other';
                                  if (nameLower.includes('verify') || nameLower.includes('validation') || nameLower.includes('test')) cat = 'Validation';
                                  else if (nameLower.includes('configure') || nameLower.includes('enable') || nameLower.includes('disable')) cat = 'Configuration';
                                  else if (nameLower.includes('provision') || nameLower.includes('create') || nameLower.includes('add') || nameLower.includes('upgrade')) cat = 'Provisioning';
                                  else if (nameLower.includes('delete') || nameLower.includes('cleanup')) cat = 'Cleanup';
                                  const colors = categoryColors[cat] || categoryColors.Other;
                                  return (
                                    <span key={i} className={`text-[10px] px-1.5 py-0.5 ${colors.bg} ${colors.text} rounded border ${colors.border} truncate max-w-[140px]`}>
                                      {i + 1}. {name}
                                    </span>
                                  );
                                })}
                              </div>
                            </div>

                            {/* Actions */}
                            <div className="relative flex-shrink-0" onClick={(e) => e.stopPropagation()}>
                              <button
                                onClick={() => setContextMenuId(contextMenuId === wf.id ? null : wf.id)}
                                className="p-1 text-gray-400 hover:text-gray-600 rounded transition-colors"
                              >
                                <EllipsisVerticalIcon className="h-4 w-4" />
                              </button>
                              {contextMenuId === wf.id && (
                                <div className="absolute right-0 top-6 bg-white border border-gray-200 rounded-lg shadow-lg py-1 w-32 z-10">
                                  <button
                                    onClick={() => duplicateWorkflow(wf.id)}
                                    className="w-full text-left px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                                  >
                                    <DocumentDuplicateIcon className="h-3.5 w-3.5" />
                                    Duplicate
                                  </button>
                                  <button
                                    onClick={() => exportWorkflow(wf)}
                                    className="w-full text-left px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                                  >
                                    <ArrowDownTrayIcon className="h-3.5 w-3.5" />
                                    Export
                                  </button>
                                  <div className="border-t border-gray-100 my-0.5" />
                                  <button
                                    onClick={() => { deleteWorkflow(wf.id); setContextMenuId(null); }}
                                    className="w-full text-left px-3 py-1.5 text-xs text-red-600 hover:bg-red-50 flex items-center gap-2"
                                  >
                                    <TrashIcon className="h-3.5 w-3.5" />
                                    Delete
                                  </button>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}

              {libraryTab === 'templates' && (
                <div className="space-y-2">
                  {workflowTemplates
                    .filter((tpl) => !librarySearch || tpl.name.toLowerCase().includes(librarySearch.toLowerCase()))
                    .map((tpl) => {
                    const iconMap = {
                      rocket: <RocketLaunchIcon className="h-4 w-4" />,
                      server: <ServerIcon className="h-4 w-4" />,
                      trash: <TrashIcon className="h-4 w-4" />,
                      check: <ShieldCheckIcon className="h-4 w-4" />,
                    };
                    const colorMap = {
                      rocket: 'from-blue-500 to-indigo-600',
                      server: 'from-emerald-500 to-teal-600',
                      trash: 'from-orange-500 to-red-500',
                      check: 'from-green-500 to-emerald-600',
                    };
                    return (
                      <div
                        key={tpl.id}
                        className="group bg-white border border-gray-200 rounded-xl p-3 hover:shadow-md hover:border-purple-300 transition-all cursor-pointer"
                        onClick={() => loadWorkflow(tpl)}
                      >
                        <div className="flex items-start gap-2.5">
                          <div className={`w-8 h-8 rounded-lg bg-gradient-to-br ${colorMap[tpl.icon] || 'from-gray-400 to-gray-600'} flex items-center justify-center text-white flex-shrink-0`}>
                            {iconMap[tpl.icon] || <StarIcon className="h-4 w-4" />}
                          </div>
                          <div className="flex-1 min-w-0">
                            <h4 className="text-sm font-semibold text-gray-900 truncate">{tpl.name}</h4>
                            <p className="text-[11px] text-gray-400 mt-0.5 line-clamp-2">{tpl.description}</p>
                            <div className="flex items-center gap-2 mt-1.5">
                              <span className="text-[10px] text-gray-400">
                                {tpl.steps.length} step{tpl.steps.length !== 1 ? 's' : ''}
                              </span>
                              <span className="text-[10px] px-1.5 py-0 bg-purple-50 text-purple-500 rounded font-semibold">
                                Template
                              </span>
                            </div>
                            {/* Step preview pills */}
                            <div className="flex flex-wrap gap-1 mt-1.5">
                              {(tpl.steps || []).map((s, i) => {
                                const nameLower = (s.name || '').toLowerCase();
                                let cat = 'Other';
                                if (nameLower.includes('verify') || nameLower.includes('validation') || nameLower.includes('test')) cat = 'Validation';
                                else if (nameLower.includes('configure') || nameLower.includes('enable') || nameLower.includes('disable')) cat = 'Configuration';
                                else if (nameLower.includes('provision') || nameLower.includes('create') || nameLower.includes('add') || nameLower.includes('upgrade')) cat = 'Provisioning';
                                else if (nameLower.includes('delete') || nameLower.includes('cleanup')) cat = 'Cleanup';
                                const colors = categoryColors[cat] || categoryColors.Other;
                                return (
                                  <span key={i} className={`text-[10px] px-1.5 py-0.5 ${colors.bg} ${colors.text} rounded border ${colors.border} truncate max-w-[140px]`}>
                                    {i + 1}. {s.name}
                                  </span>
                                );
                              })}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {libraryTab === 'yaml' && (
                <div className="space-y-2">
                  {yamlWorkflows
                    .filter((wf) => !librarySearch || wf.name.toLowerCase().includes(librarySearch.toLowerCase()) || (wf.description || '').toLowerCase().includes(librarySearch.toLowerCase()))
                    .map((wf) => (
                    <div
                      key={wf.id}
                      className="group bg-white border border-gray-200 rounded-xl p-3 hover:shadow-md hover:border-green-300 transition-all cursor-pointer"
                      onClick={() => loadWorkflow(wf)}
                    >
                      <div className="flex items-start gap-2.5">
                        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-green-500 to-emerald-600 flex items-center justify-center text-white flex-shrink-0">
                          <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                            <path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clipRule="evenodd" />
                          </svg>
                        </div>
                        <div className="flex-1 min-w-0">
                          <h4 className="text-sm font-semibold text-gray-900 truncate">{wf.name}</h4>
                          {wf.description && (
                            <p className="text-[11px] text-gray-400 mt-0.5 line-clamp-2">{wf.description}</p>
                          )}
                          <div className="flex items-center gap-2 mt-1.5">
                            <span className="text-[10px] text-gray-400">
                              {wf.stepCount} step{wf.stepCount !== 1 ? 's' : ''}
                            </span>
                            <span className="text-[10px] px-1.5 py-0 bg-green-50 text-green-600 rounded font-semibold">
                              YAML
                            </span>
                          </div>
                          <div className="flex flex-wrap gap-1 mt-1.5">
                            {(wf.stepNames || []).map((name, i) => {
                              const nameLower = (name || '').toLowerCase();
                              let cat = 'Other';
                              if (nameLower.includes('verify') || nameLower.includes('validation') || nameLower.includes('test')) cat = 'Validation';
                              else if (nameLower.includes('configure') || nameLower.includes('enable') || nameLower.includes('disable')) cat = 'Configuration';
                              else if (nameLower.includes('provision') || nameLower.includes('create') || nameLower.includes('add') || nameLower.includes('upgrade')) cat = 'Provisioning';
                              else if (nameLower.includes('delete') || nameLower.includes('cleanup')) cat = 'Cleanup';
                              const colors = categoryColors[cat] || categoryColors.Other;
                              return (
                                <span key={i} className={`text-[10px] px-1.5 py-0.5 ${colors.bg} ${colors.text} rounded border ${colors.border} truncate max-w-[140px]`}>
                                  {i + 1}. {name}
                                </span>
                              );
                            })}
                          </div>
                          <div className="mt-1">
                            <span className="text-[9px] text-gray-300 font-mono">{wf.source}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Workflows tab footer */}
            <div className="px-3 py-2 border-t border-gray-100 bg-gray-50">
              <button
                onClick={() => fileInputRef.current?.click()}
                className="w-full text-[11px] text-gray-400 hover:text-indigo-600 flex items-center justify-center gap-1 transition-colors"
              >
                <ArrowUpTrayIcon className="h-3.5 w-3.5" />
                Import from file
              </button>
            </div>
          </>
        )}
      </div>

      {/* ---- Center: Workflow Canvas ---- */}
      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        {/* Toolbar - glass effect */}
        <div className="flex items-center justify-between px-5 py-3 bg-white/95 backdrop-blur-sm rounded-t-2xl border border-gray-200 border-b-0 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center flex-shrink-0">
              <svg className="h-5 w-5 text-white" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M3 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clipRule="evenodd" />
              </svg>
            </div>
            <div>
              <input
                type="text"
                value={workflowName}
                onChange={(e) => setWorkflowName(e.target.value)}
                className="text-lg font-bold text-gray-900 border-0 border-b-2 border-transparent hover:border-indigo-300 focus:border-indigo-500 focus:ring-0 bg-transparent px-0 py-0 transition-colors w-64"
                placeholder="Workflow name..."
              />
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-xs text-gray-400">
                  {workflowSteps.length} step{workflowSteps.length !== 1 ? 's' : ''}
                </span>
                {workflowSteps.length > 0 && (() => {
                  const totalSecs = workflowSteps.reduce((sum, s) => sum + (s.timeout || 600), 0);
                  const mins = Math.round(totalSecs / 60);
                  return (
                    <>
                      <span className="text-xs text-gray-300">|</span>
                      <span className="text-xs text-gray-400 flex items-center gap-1">
                        <ClockIcon className="h-3 w-3" />
                        ~{mins} min est.
                      </span>
                    </>
                  );
                })()}
                {activeWorkflowId && (
                  <>
                    <span className="text-xs text-gray-300">|</span>
                    <span className="text-xs text-indigo-500 flex items-center gap-1">
                      <BookmarkSolidIcon className="h-3 w-3" />
                      Saved
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Stop on failure toggle */}
            <label className="flex items-center gap-2 text-sm text-gray-500 mr-1 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={stopOnFailure}
                onChange={(e) => setStopOnFailure(e.target.checked)}
                className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded"
              />
              Stop on failure
            </label>

            <div className="w-px h-6 bg-gray-200 mx-1" />

            {/* Save */}
            <button
              onClick={() => {
                setSaveDescription(saveDescription || '');
                setShowSaveDialog(true);
                setShowOverwriteConfirm(false);
              }}
              disabled={workflowSteps.length === 0}
              className="px-3 py-1.5 text-sm font-medium text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 hover:border-gray-300 disabled:opacity-40 disabled:cursor-not-allowed transition-all flex items-center gap-1.5"
            >
              <BookmarkIcon className="h-4 w-4" />
              Save
            </button>

            {/* Export (when workflow is saved) */}
            {activeWorkflowId && (
              <button
                onClick={() => exportWorkflow({ id: activeWorkflowId, name: workflowName })}
                className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-all"
                title="Export workflow"
              >
                <ArrowDownTrayIcon className="h-4 w-4" />
              </button>
            )}

            {/* Hidden file input for import */}
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              onChange={importWorkflow}
              className="hidden"
            />

            <div className="w-px h-6 bg-gray-200 mx-1" />

            {/* Clear */}
            <button
              onClick={clearWorkflow}
              disabled={workflowSteps.length === 0 || isRunning}
              className="px-3 py-1.5 text-sm font-medium text-red-500 bg-white border border-red-200 rounded-lg hover:bg-red-50 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
            >
              Clear
            </button>

            {/* Run */}
            <button
              onClick={runWorkflow}
              disabled={workflowSteps.length === 0 || isRunning}
              className={`px-5 py-2.5 text-sm font-semibold text-white rounded-lg flex items-center gap-2 transition-all duration-200 ${
                isRunning
                  ? 'bg-gradient-to-r from-gray-400 to-gray-500 cursor-not-allowed shadow-sm'
                  : 'bg-gradient-to-r from-indigo-600 to-blue-600 shadow-md hover:from-indigo-700 hover:to-blue-700 hover:shadow-lg hover:shadow-indigo-300/50'
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

        {/* Step Progress Minimap */}
        {workflowSteps.length > 0 && (
          <div className="bg-white border-x border-gray-200 px-5 py-2 border-b border-gray-100">
            <div className="flex items-center gap-1.5">
              {workflowSteps.map((step, i) => {
                const colors = {
                  pending: 'bg-gray-300',
                  running: 'bg-blue-500 animate-pulse ring-2 ring-blue-200',
                  completed: 'bg-emerald-500',
                  failed: 'bg-red-500',
                  skipped: 'bg-amber-400',
                };
                return (
                  <div key={step.id} className="flex items-center gap-1.5">
                    <div
                      className={`w-2.5 h-2.5 rounded-full ${colors[step.status] || colors.pending} transition-all duration-300`}
                      title={`Step ${i + 1}: ${step.name} (${step.status})`}
                    />
                    {i < workflowSteps.length - 1 && (
                      <div className={`w-3 h-px ${
                        step.status === 'completed' ? 'bg-emerald-300' :
                        step.status === 'running' ? 'bg-blue-300' :
                        'bg-gray-200'
                      }`} />
                    )}
                  </div>
                );
              })}
              <span className="text-[10px] text-gray-400 ml-2 font-medium">
                {workflowSteps.filter(s => s.status === 'completed').length}/{workflowSteps.length}
              </span>
            </div>
          </div>
        )}

        {/* Global Variables Panel */}
        <div className="bg-white border-x border-gray-200">
          <button
            onClick={() => setShowGlobalVars(!showGlobalVars)}
            className="w-full flex items-center justify-between px-5 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
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

              {/* Common variable presets (credentials come from Credentials page / user_vars.yml automatically) */}
              {Object.keys(globalVars).length === 0 && (
                <div className="flex flex-wrap gap-1.5 py-1">
                  {[
                    { key: 'name_prefix', label: 'name_prefix' },
                    { key: 'MCE_NAMESPACE', label: 'MCE Namespace' },
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

        {/* Trigger Panel */}
        <div className="mx-0 border-x border-gray-200 bg-white">
          <TriggerPanel workflowName={workflowName} />
        </div>

        {/* Status summary bar (shows when workflow has run results) */}
        {hasRunResults && (
          <div className="mx-0 border-x border-gray-200 bg-white px-5 py-2.5">
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-3">
                {completedSteps > 0 && (
                  <span className="flex items-center gap-1 text-xs font-medium text-emerald-700">
                    <CheckCircleIcon className="h-3.5 w-3.5" />
                    {completedSteps} passed
                  </span>
                )}
                {failedSteps > 0 && (
                  <span className="flex items-center gap-1 text-xs font-medium text-red-600">
                    <XCircleIcon className="h-3.5 w-3.5" />
                    {failedSteps} failed
                  </span>
                )}
                {skippedSteps > 0 && (
                  <span className="flex items-center gap-1 text-xs font-medium text-amber-600">
                    <ClockIcon className="h-3.5 w-3.5" />
                    {skippedSteps} skipped
                  </span>
                )}
                {runningSteps > 0 && (
                  <span className="flex items-center gap-1 text-xs font-medium text-blue-600">
                    <ArrowPathIcon className="h-3.5 w-3.5 animate-spin" />
                    {runningSteps} running
                  </span>
                )}
              </div>
              <span className="text-xs text-gray-400 font-mono">{progressPercent}%</span>
            </div>
            {/* Progress bar */}
            <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden flex">
              {completedSteps > 0 && (
                <div
                  className="h-full bg-gradient-to-r from-emerald-400 to-emerald-500 transition-all duration-500"
                  style={{ width: `${(completedSteps / workflowSteps.length) * 100}%` }}
                />
              )}
              {failedSteps > 0 && (
                <div
                  className="h-full bg-gradient-to-r from-red-400 to-red-500 transition-all duration-500"
                  style={{ width: `${(failedSteps / workflowSteps.length) * 100}%` }}
                />
              )}
              {skippedSteps > 0 && (
                <div
                  className="h-full bg-gradient-to-r from-amber-300 to-amber-400 transition-all duration-500"
                  style={{ width: `${(skippedSteps / workflowSteps.length) * 100}%` }}
                />
              )}
              {runningSteps > 0 && (
                <div
                  className="h-full bg-gradient-to-r from-blue-400 to-blue-500 animate-pulse transition-all duration-500"
                  style={{ width: `${(runningSteps / workflowSteps.length) * 100}%` }}
                />
              )}
            </div>
          </div>
        )}

        {/* Canvas */}
        <div
          className="flex-1 border border-gray-200 rounded-b-2xl overflow-y-auto p-6 transition-all duration-300"
          style={{
            background: 'linear-gradient(135deg, #f8fafc 0%, #f1f5f9 50%, #eff3f8 100%)',
            backgroundImage: workflowSteps.length === 0
              ? 'radial-gradient(circle at 1px 1px, #e2e8f0 1px, transparent 0)'
              : 'none',
            backgroundSize: '24px 24px',
          }}
          onDrop={handleCanvasDrop}
          onDragOver={handleCanvasDragOver}
          onDragLeave={handleCanvasDragLeave}
        >
          {workflowSteps.length === 0 ? (
            <div className="h-full flex items-center justify-center">
              <div className="text-center">
                <div className="w-24 h-24 mx-auto mb-6 rounded-2xl bg-gradient-to-br from-indigo-50 via-indigo-100 to-purple-100 flex items-center justify-center shadow-md border border-indigo-200/50">
                  <PlusIcon className="h-12 w-12 text-indigo-500" />
                </div>
                <h3 className="text-xl font-semibold text-gray-800 mb-2">Build your workflow</h3>
                <p className="text-sm text-gray-500 max-w-sm mx-auto mb-6">
                  Drag playbooks from the palette, or start with a common workflow below.
                </p>
                <div className="flex gap-3 justify-center flex-wrap">
                  <button
                    onClick={() => { setPaletteTab('workflows'); setLibraryTab('templates'); loadSavedWorkflows(); loadWorkflowTemplates(); }}
                    className="px-4 py-2 text-sm font-medium text-indigo-600 bg-indigo-50 border border-indigo-200 rounded-xl hover:bg-indigo-100 hover:shadow-sm transition-all inline-flex items-center gap-2"
                  >
                    <RocketLaunchIcon className="h-4 w-4" />
                    Start from a template
                  </button>
                  <button
                    onClick={() => {
                      const verify = availablePlaybooks.find(s => (s.name || '').toLowerCase().includes('verify'));
                      const configure = availablePlaybooks.find(s => (s.name || '').toLowerCase().includes('configure'));
                      const provision = availablePlaybooks.find(s => (s.name || '').toLowerCase().includes('provision'));
                      if (verify) addStep(verify);
                      if (configure) addStep(configure);
                      if (provision) addStep(provision);
                    }}
                    className="px-4 py-2 text-sm font-medium text-gray-600 bg-white border border-gray-200 rounded-xl hover:bg-gray-50 hover:shadow-sm transition-all inline-flex items-center gap-2"
                  >
                    <ShieldCheckIcon className="h-4 w-4" />
                    Quick start: Verify + Configure + Provision
                  </button>
                </div>
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
            <div className="mt-3 bg-white rounded-2xl border border-gray-200 shadow-lg overflow-hidden">
              <div className="flex items-center justify-between px-5 py-2.5 bg-gradient-to-r from-slate-800 to-slate-900">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-slate-300">Output:</span>
                  <span className="text-sm text-white font-medium">{activeStep.name}</span>
                  {activeStep.status === 'running' && (
                    <ArrowPathIcon className="h-4 w-4 text-blue-400 animate-spin" />
                  )}
                  {activeStep.status === 'completed' && (
                    <CheckCircleIcon className="h-4 w-4 text-emerald-400" />
                  )}
                  {activeStep.status === 'failed' && (
                    <XCircleIcon className="h-4 w-4 text-red-400" />
                  )}
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-slate-400 font-mono">{activeStep.logs.length} lines</span>
                  <button
                    onClick={() => setActiveOutputStepId(null)}
                    className="p-1 text-slate-400 hover:text-white transition-colors"
                    title="Close output"
                  >
                    <XMarkIcon className="h-4 w-4" />
                  </button>
                </div>
              </div>
              <StepOutputPanel logs={activeStep.logs} status={activeStep.status} agentStats={activeStep.agentStats} />
            </div>
          );
        })()}
      </div>

      {/* Enhanced Save dialog */}
      {showSaveDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => { setShowSaveDialog(false); setShowOverwriteConfirm(false); }}>
          <div className="bg-white rounded-xl shadow-2xl w-[440px] overflow-hidden" onClick={(e) => e.stopPropagation()}>
            <div className="bg-gradient-to-r from-indigo-600 to-blue-600 px-6 py-4">
              <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                <BookmarkIcon className="h-5 w-5" />
                Save Workflow
              </h3>
              <p className="text-indigo-200 text-sm mt-0.5">
                {workflowSteps.length} step{workflowSteps.length !== 1 ? 's' : ''} will be saved
              </p>
            </div>

            <div className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Workflow Name</label>
                <input
                  type="text"
                  value={workflowName}
                  onChange={(e) => setWorkflowName(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2.5 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                  placeholder="e.g., Full E2E Test Suite"
                  autoFocus
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Description <span className="text-gray-400 font-normal">(optional)</span></label>
                <textarea
                  value={saveDescription}
                  onChange={(e) => setSaveDescription(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm resize-none"
                  rows={2}
                  placeholder="What does this workflow do?"
                />
              </div>

              {/* Step preview */}
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Steps Preview</p>
                <div className="space-y-1">
                  {workflowSteps.slice(0, 5).map((step, i) => (
                    <div key={i} className="flex items-center gap-2 text-sm text-gray-700">
                      <span className="w-5 h-5 flex items-center justify-center rounded-full bg-indigo-100 text-indigo-700 text-xs font-semibold flex-shrink-0">
                        {i + 1}
                      </span>
                      <span className="truncate">{step.name}</span>
                    </div>
                  ))}
                  {workflowSteps.length > 5 && (
                    <p className="text-xs text-gray-400 pl-7">+{workflowSteps.length - 5} more steps</p>
                  )}
                </div>
              </div>

              {/* Overwrite warning */}
              {showOverwriteConfirm && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex items-start gap-2">
                  <span className="text-amber-500 text-lg leading-none mt-0.5">!</span>
                  <div>
                    <p className="text-sm font-medium text-amber-800">A workflow named &quot;{workflowName}&quot; already exists.</p>
                    <p className="text-xs text-amber-600 mt-0.5">Click Save again to overwrite it.</p>
                  </div>
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2 px-6 py-4 bg-gray-50 border-t border-gray-100">
              <button
                onClick={() => { setShowSaveDialog(false); setShowOverwriteConfirm(false); }}
                className="px-4 py-2 text-sm text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={saveWorkflow}
                disabled={!workflowName.trim()}
                className={`px-5 py-2 text-sm text-white rounded-lg transition-colors flex items-center gap-2 ${
                  showOverwriteConfirm
                    ? 'bg-amber-600 hover:bg-amber-700'
                    : 'bg-indigo-600 hover:bg-indigo-700'
                } disabled:opacity-50`}
              >
                <BookmarkIcon className="h-4 w-4" />
                {showOverwriteConfirm ? 'Overwrite' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};

export default WorkflowBuilder;
