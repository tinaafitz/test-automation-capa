import React from 'react';
import {
  ArrowPathIcon,
  CheckCircleIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline';

// ============================================================================
// "Make this my MCE hub" progress helpers
//
// Pure log-parsing helpers + small presentational components (phase list,
// minimap, live colorized terminal) used by RosaHcpClustersSection.jsx for the
// long-running MCE-hub install flow. Extracted here to keep the section file
// focused; patterns mirror WorkflowBuilder's StepOutputPanel / SortableStep /
// step minimap (colorized terminal, status colors, dot strip).
// ============================================================================

// The 5 fixed phase rows shown in the progress card. `match` is the list of
// real `TASK [...]` name substrings (from the merged playbook) that advance the
// phase to "running". Phases are ordered; deriving them from the log is a pure
// function, so no backend change is needed.
export const MCE_HUB_PHASES = [
  {
    key: 'preflight',
    label: 'Preflight (creds, control plane)',
    match: ['Preflight', 'Wait for ROSA control plane'],
  },
  {
    key: 'install',
    label: 'Install MCE operator',
    match: ['Get the new hub kubeconfig', 'Install the MCE operator'],
  },
  {
    key: 'configure',
    label: 'Configure MCE (secrets)',
    match: ['rosa-creds-secret', 'AWS bootstrap'],
  },
  {
    key: 'enable',
    label: 'Enable CAPI / CAPA',
    match: ['Enable CAPI/CAPA', 'Enable CAPI', 'Enable CAPA'],
  },
  {
    key: 'verify',
    label: 'Verify hub ready',
    match: ['Console:', 'MCE version:'],
  },
];

// Given the full log text (joined lines) and whether the job is still running /
// failed, derive a status ('pending' | 'running' | 'completed' | 'failed') for
// each of the 5 phases. The furthest-reached phase is the "current" one.
export function derivePhases(logText, { isRunning, isFailed, isDone } = {}) {
  const text = logText || '';
  // Index of the furthest phase whose task marker has appeared in the log.
  let reached = -1;
  MCE_HUB_PHASES.forEach((phase, i) => {
    if (phase.match.some((m) => text.includes(m))) {
      reached = Math.max(reached, i);
    }
  });

  return MCE_HUB_PHASES.map((phase, i) => {
    let status;
    if (isDone && !isFailed) {
      status = 'completed';
    } else if (i < reached) {
      status = 'completed';
    } else if (i === reached) {
      if (isFailed) status = 'failed';
      else if (isRunning) status = 'running';
      else status = 'completed';
    } else {
      status = 'pending';
    }
    return { ...phase, status };
  });
}

// Parse the print-only success summary from the playbook log. The playbook
// emits a debug block with lines like:
//   Console:  https://console-openshift-console.apps...
//   MCE version:  2.9.0 (5.0.0-259)
//   CAPI/CAPA:  enabled
// There are no machine-readable return facts, so we scrape these from the log.
export function parseHubSuccess(logText) {
  const text = logText || '';
  // Same-line-anchored grabs (multiline `m` flag) so a match on one line can't
  // greedily span a newline and steal a token from the next line.
  const grab = (re) => {
    const m = text.match(re);
    return m ? m[1].trim() : null;
  };
  // Console must look like a URL (http/https); reject non-URL tokens.
  const rawConsole = grab(/^.*Console:\s*(\S+)/m);
  const consoleUrl = rawConsole && /^https?:\/\//i.test(rawConsole) ? rawConsole : null;
  const mceVersion = grab(/^.*MCE version:\s*(.+)$/m);
  const capiCapaLine = grab(/^.*CAPI\/CAPA:\s*(.+)$/m);
  const capiCapaEnabled = capiCapaLine
    ? /enabled/i.test(capiCapaLine)
    : /CAPI\/CAPA.*enabled/i.test(text);
  return { consoleUrl, mceVersion, capiCapaEnabled };
}

// Phase status color map (mirrors WorkflowBuilder SortableStep minimap colors).
const PHASE_DOT_COLORS = {
  pending: 'bg-gray-300',
  running: 'bg-blue-500 animate-pulse ring-2 ring-blue-200',
  completed: 'bg-emerald-500',
  failed: 'bg-red-500',
};

const PHASE_TEXT_COLORS = {
  pending: 'text-gray-400',
  running: 'text-blue-700 font-medium',
  completed: 'text-emerald-700',
  failed: 'text-red-700 font-medium',
};

// Vertical phase list with a per-phase status icon.
export const HubPhaseList = ({ phases }) => (
  <div className="space-y-1.5">
    {phases.map((phase) => (
      <div key={phase.key} className="flex items-center gap-2 text-sm">
        {phase.status === 'completed' ? (
          <CheckCircleIcon className="h-4 w-4 text-emerald-600 flex-shrink-0" />
        ) : phase.status === 'failed' ? (
          <XCircleIcon className="h-4 w-4 text-red-600 flex-shrink-0" />
        ) : phase.status === 'running' ? (
          <ArrowPathIcon className="h-4 w-4 text-blue-600 animate-spin flex-shrink-0" />
        ) : (
          <span className="inline-block w-4 h-4 flex-shrink-0 flex items-center justify-center">
            <span className="w-2 h-2 rounded-full bg-gray-300" />
          </span>
        )}
        <span className={PHASE_TEXT_COLORS[phase.status] || PHASE_TEXT_COLORS.pending}>
          {phase.label}
        </span>
        {phase.status === 'running' && (
          <span className="text-xs text-blue-500">running…</span>
        )}
      </div>
    ))}
  </div>
);

// Horizontal dot-and-connector minimap (mirrors WorkflowBuilder step minimap).
export const HubPhaseMinimap = ({ phases }) => {
  const completed = phases.filter((p) => p.status === 'completed').length;
  return (
    <div className="flex items-center gap-1.5">
      {phases.map((phase, i) => (
        <div key={phase.key} className="flex items-center gap-1.5">
          <div
            className={`w-2.5 h-2.5 rounded-full ${PHASE_DOT_COLORS[phase.status] || PHASE_DOT_COLORS.pending} transition-all duration-300`}
            title={`${phase.label} (${phase.status})`}
          />
          {i < phases.length - 1 && (
            <div
              className={`w-3 h-px ${
                phase.status === 'completed'
                  ? 'bg-emerald-300'
                  : phase.status === 'running'
                    ? 'bg-blue-300'
                    : 'bg-gray-200'
              }`}
            />
          )}
        </div>
      ))}
      <span className="text-[10px] text-gray-400 ml-2 font-medium">
        {completed}/{phases.length}
      </span>
    </div>
  );
};

// Live colorized terminal (mirrors WorkflowBuilder StepOutputPanel). Auto-scrolls
// to the bottom while running and renders a blinking cursor.
export const HubLogTerminal = ({ logs, isRunning }) => {
  const outputRef = React.useRef(null);

  React.useEffect(() => {
    if (outputRef.current && isRunning) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [logs, isRunning]);

  const lines = (logs || '').split('\n');

  return (
    <div
      ref={outputRef}
      className="bg-gray-900 text-gray-100 rounded p-4 max-h-96 overflow-y-auto font-mono text-sm leading-relaxed"
    >
      {lines.map((line, i) => (
        <div
          key={i}
          className={
            line.includes('TASK [') ? 'text-cyan-400 mt-1' :
            line.includes('ok:') ? 'text-green-400' :
            line.includes('changed:') ? 'text-yellow-400' :
            line.includes('fatal:') || line.includes('FAILED') ? 'text-red-400 font-bold' :
            line.includes('PLAY RECAP') ? 'text-cyan-300 mt-2 font-bold' :
            line.includes('skipping:') ? 'text-gray-500' :
            'text-gray-300'
          }
        >
          {line}
        </div>
      ))}
      {isRunning && <div className="text-blue-400 animate-pulse mt-1">▋</div>}
    </div>
  );
};
