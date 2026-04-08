import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  PlayIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';

const mainSidebarItems = [
  { label: 'Dashboard', icon: '\uD83D\uDCCA', src: '/screenshots/at-a-glance-dashboard.png', description: 'Cluster status, task history, Jenkins trends, AWS quota, and GitHub activity at a glance' },
  { label: 'Notifications', icon: '\uD83D\uDD14', src: '/screenshots/main-notifications.png', description: 'Configure email and Slack notifications for cluster provisioning and deletion events' },
  { label: 'Email: Started', icon: '\uD83D\uDCE8', src: '/screenshots/email-started.png', description: 'Email sent when a cluster operation begins — includes cluster name, environment, and timestamp' },
  { label: 'Email: Success', icon: '\u2705', src: '/screenshots/email-success.png', description: 'Email sent on successful completion — includes duration, cluster details, and console link' },
  { label: 'Email: Failed', icon: '\u274C', src: '/screenshots/email-failed.png', description: 'Email sent on failure — includes error details, AI agent diagnostics, and suggested next steps' },
  { label: 'AI Assistant', icon: '\uD83E\uDD16', src: '/screenshots/main-ai-assistant.png', description: 'Chat with Claude about your clusters, logs, and operations — context-aware troubleshooting' },
  { label: 'AWS Usage', icon: '\u2601', src: '/screenshots/mk-aws-usage.png', description: 'Track AWS resource quotas, usage trends, and estimated monthly costs across accounts' },
];

const mceSidebarItems = [
  { label: 'Environments', icon: '\uD83C\uDF10', src: '/screenshots/mce-environments.png', description: 'View and switch between OpenShift Hub environments — see connection status and API endpoints' },
  { label: 'Credentials', icon: '\uD83D\uDD11', src: '/screenshots/mce-credentials.png', description: 'Manage OpenShift credentials needed for connecting to the OpenShift Hub cluster' },
  { label: 'Verify', icon: '\u2714', src: '/screenshots/mce-verify.png', description: 'Run verification checks on CAPI/CAPA controllers and Hypershift components' },
  { label: 'Configure', icon: '\u2699', src: '/screenshots/mce-configure.png', description: 'Set up the MCE environment — install CAPI/CAPA providers and configure cluster settings' },
  { label: 'Provision', icon: '\uD83D\uDE80', src: '/screenshots/mce-provision.png', description: 'Provision a new ROSA HCP cluster with configurable version, region, and instance type' },
  { label: 'ROSA Clusters', icon: '\uD83D\uDCE1', src: '/screenshots/mce-rosa-clusters.png', description: 'Monitor active ROSA HCP clusters — status, version, age, and one-click deletion' },
  { label: 'CAPA Resources', icon: '\uD83D\uDD27', src: '/screenshots/mce-capa-resources.png', description: 'Inspect Kubernetes CAPA resources — ROSAControlPlane, AWSManagedControlPlane, and MachinePool objects' },
  { label: 'Playbooks', icon: '\uD83D\uDCD6', src: '/screenshots/mce-playbooks.png', description: 'Browse and run individual Ansible playbooks for provisioning, testing, and cleanup' },
  { label: 'Workflows', icon: '\u2699\uFE0F', src: '/screenshots/mce-workflow-builder.png', description: 'Build multi-step pipelines by chaining playbooks with drag-and-drop' },
  { label: 'Feature Tests', icon: '\uD83E\uddEA', src: '/screenshots/mce-feature-tests.png', description: 'Run targeted feature test suites against provisioned clusters' },
  { label: 'Terminal', icon: '\uD83D\uDCBB', src: '/screenshots/mce-terminal.png', description: 'Built-in terminal for running kubectl, oc, and aws commands directly in the browser' },
  { label: 'Notifications', icon: '\uD83D\uDD14', src: '/screenshots/mce-notifications.png', description: 'Configure email and Slack notification preferences for this environment' },
  { label: 'Email: Started', icon: '\uD83D\uDCE8', src: '/screenshots/email-started.png', description: 'Email sent when a cluster operation begins — includes cluster name, environment, and timestamp' },
  { label: 'Email: Success', icon: '\u2705', src: '/screenshots/email-success.png', description: 'Email sent on successful completion — includes duration, cluster details, and console link' },
  { label: 'Email: Failed', icon: '\u274C', src: '/screenshots/email-failed.png', description: 'Email sent on failure — includes error details, AI agent diagnostics, and suggested next steps' },
  { label: 'Task Summary', icon: '\uD83D\uDCCB', src: '/screenshots/mce-task-summary.png', description: 'View recent operations with timestamps, status badges, and detailed logs' },
  { label: 'AI Assistant', icon: '\uD83E\uDD16', src: '/screenshots/mce-ai-assistant.png', description: 'Chat with Claude about your MCE environment, clusters, and operations' },
  { label: 'AWS Usage', icon: '\u2601', src: '/screenshots/mce-aws-usage.png', description: 'Track AWS resource quotas, usage trends, and estimated monthly costs' },
];

const mkSidebarItems = [
  { label: 'Clusters', icon: '\uD83C\uDF10', src: '/screenshots/mk-clusters.png', description: 'View and manage local Minikube clusters used for CAPA development and testing' },
  { label: 'Configure', icon: '\u2699', src: '/screenshots/mk-configure.png', description: 'Set up Minikube with CAPI/CAPA providers — configure cluster settings for local dev' },
  { label: 'Custom Image', icon: '\uD83D\uDCE6', src: '/screenshots/mk-custom-image.png', description: 'Build and deploy custom CAPA provider images from open PRs for local testing' },
  { label: 'Provision', icon: '\uD83D\uDE80', src: '/screenshots/mk-provision.png', description: 'Provision a ROSA HCP cluster from Minikube using a custom or default CAPA image' },
  { label: 'ROSA Clusters', icon: '\uD83D\uDCE1', src: '/screenshots/mk-rosa-clusters.png', description: 'Monitor ROSA HCP clusters provisioned from the Minikube environment' },
  { label: 'CAPA Resources', icon: '\uD83D\uDD27', src: '/screenshots/mk-capa-resources.png', description: 'Inspect Kubernetes CAPA resources in the Minikube cluster' },
  { label: 'Playbooks', icon: '\uD83D\uDCD6', src: '/screenshots/mk-playbooks.png', description: 'Browse and run Ansible playbooks tailored for the Minikube environment' },
  { label: 'Terminal', icon: '\uD83D\uDCBB', src: '/screenshots/mk-terminal.png', description: 'Built-in terminal for running commands against the Minikube cluster' },
  { label: 'Notifications', icon: '\uD83D\uDD14', src: '/screenshots/mk-notifications.png', description: 'Configure email and Slack notification preferences for Minikube operations' },
  { label: 'Email: Started', icon: '\uD83D\uDCE8', src: '/screenshots/email-started.png', description: 'Email sent when a cluster operation begins — includes cluster name, environment, and timestamp' },
  { label: 'Email: Success', icon: '\u2705', src: '/screenshots/email-success.png', description: 'Email sent on successful completion — includes duration, cluster details, and console link' },
  { label: 'Email: Failed', icon: '\u274C', src: '/screenshots/email-failed.png', description: 'Email sent on failure — includes error details, AI agent diagnostics, and suggested next steps' },
  { label: 'Task Summary', icon: '\uD83D\uDCCB', src: '/screenshots/mk-task-summary.png', description: 'View recent Minikube operations with timestamps, status badges, and logs' },
  { label: 'AI Assistant', icon: '\uD83E\uDD16', src: '/screenshots/mk-ai-assistant.png', description: 'Chat with Claude about your Minikube environment, clusters, and operations' },
  { label: 'AWS Usage', icon: '\u2601', src: '/screenshots/mk-aws-usage.png', description: 'Track AWS resource quotas, usage trends, and estimated monthly costs' },
];

const ScreenshotSidebarViewer = ({ items, title, gradient }) => {
  const [activeIdx, setActiveIdx] = useState(0);
  const item = items[activeIdx];
  return (
    <div className="flex gap-4 w-full" style={{height: 'calc(100vh - 240px)', maxHeight: '700px'}}>
      {/* Sidebar */}
      <div className="w-48 flex-shrink-0 rounded-xl overflow-hidden border border-gray-200 shadow-sm flex flex-col" style={{backgroundColor: '#f8fafc'}}>
        <div className="px-4 py-3 text-white font-bold text-sm" style={{background: gradient}}>
          {title}
        </div>
        <div className="flex-1 overflow-y-auto py-1" onWheel={(e) => e.stopPropagation()}>
          {items.map((s, i) => (
            <button
              key={s.label}
              onClick={(e) => { e.stopPropagation(); setActiveIdx(i); }}
              className="w-full text-left px-3 py-2 text-xs flex items-center gap-2 transition-all"
              style={i === activeIdx
                ? { backgroundColor: '#eff6ff', borderLeft: '3px solid #3b82f6', color: '#1d4ed8', fontWeight: 600 }
                : { borderLeft: '3px solid transparent', color: '#64748b' }
              }
              onMouseEnter={(e) => { if (i !== activeIdx) e.currentTarget.style.backgroundColor = '#f1f5f9'; }}
              onMouseLeave={(e) => { if (i !== activeIdx) e.currentTarget.style.backgroundColor = 'transparent'; }}
            >
              <span className="text-base">{s.icon}</span>
              <span>{s.label}</span>
            </button>
          ))}
        </div>
      </div>
      {/* Screenshot + description */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex-1 rounded-xl overflow-hidden border border-gray-200 shadow-md">
          <img src={item.src} alt={item.label} className="w-full h-full object-contain object-left-top" style={{backgroundColor: '#f8fafc'}} />
        </div>
        {item.description && (
          <p className="text-base text-gray-700 text-center mt-3 px-4">{item.description}</p>
        )}
      </div>
    </div>
  );
};

const MCEScreenshotViewer = () => (
  <ScreenshotSidebarViewer items={mceSidebarItems} title="MCE Environment" gradient="linear-gradient(135deg, #527fff 0%, #3b82f6 100%)" />
);

const MinikubeScreenshotViewer = () => (
  <ScreenshotSidebarViewer items={mkSidebarItems} title="Minikube Environment" gradient="linear-gradient(135deg, #7c3aed 0%, #a855f7 100%)" />
);

const MainScreenshotViewer = () => (
  <ScreenshotSidebarViewer items={mainSidebarItems} title="CAPA Automation" gradient="linear-gradient(135deg, #4b5563 0%, #6b7280 100%)" />
);

const workflowScreenshots = [
  { src: '/screenshots/mce-wf-empty.png', label: '1. Empty Canvas', description: 'Browse playbooks by category in the left palette and drag them onto the canvas' },
  { src: '/screenshots/mce-wf-one-step.png', label: '2. Add First Step', description: 'Drag a Verify MCE Environment playbook as the first step' },
  { src: '/screenshots/mce-wf-two-steps.png', label: '3. Chain Steps', description: 'Add a Configure step after Verify to build a sequential pipeline' },
  { src: '/screenshots/mce-wf-configure-vars.png', label: '4. Configure Variables', description: 'Expand a step to set per-step variables like name_prefix, region, and OpenShift version' },
  { src: '/screenshots/mce-wf-three-steps.png', label: '5. Complete Pipeline', description: 'Three-step workflow: Verify, Configure, then Provision — ready to run' },
  { src: '/screenshots/mce-wf-ready.png', label: '6. Ready to Run', description: 'Click Run Workflow to execute all steps sequentially' },
  { src: '/screenshots/mce-wf-running-verify.png', label: '7. Step 1 Running', description: 'Verify step executes with live Ansible output streaming below' },
  { src: '/screenshots/mce-wf-running-configure.png', label: '8. Step 2 Running', description: 'Configure step runs after Verify completes — creating credentials, secrets, and AWSClusterControllerIdentity' },
  { src: '/screenshots/mce-wf-running-provision.png', label: '9. Step 3 Running', description: 'Provisioning step kicks off — applying cluster YAML and monitoring progress' },
  { src: '/screenshots/mce-wf-complete.png', label: '10. Workflow Complete', description: 'All three steps completed successfully — cluster is fully provisioned and running' },
];

const ScreenshotCarousel = () => {
  const [activeIdx, setActiveIdx] = useState(0);
  const shot = workflowScreenshots[activeIdx];
  return (
    <div className="max-w-5xl mx-auto space-y-4">
      {/* Main image */}
      <div className="relative rounded-xl overflow-hidden shadow-xl border border-gray-200">
        <img src={shot.src} alt={shot.label} className="w-full h-auto" />
        {/* Left arrow */}
        <button
          onClick={(e) => { e.stopPropagation(); setActiveIdx((activeIdx - 1 + workflowScreenshots.length) % workflowScreenshots.length); }}
          className="absolute left-3 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full flex items-center justify-center text-white text-xl font-bold transition-opacity hover:opacity-100"
          style={{backgroundColor: 'rgba(35,47,62,0.7)', opacity: 0.6}}
        >
          &#x2039;
        </button>
        {/* Right arrow */}
        <button
          onClick={(e) => { e.stopPropagation(); setActiveIdx((activeIdx + 1) % workflowScreenshots.length); }}
          className="absolute right-3 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full flex items-center justify-center text-white text-xl font-bold transition-opacity hover:opacity-100"
          style={{backgroundColor: 'rgba(35,47,62,0.7)', opacity: 0.6}}
        >
          &#x203a;
        </button>
      </div>
      {/* Label */}
      <div className="text-center">
        <div className="text-lg font-bold text-gray-900">{shot.label}</div>
        <div className="text-sm text-gray-500">{shot.description}</div>
      </div>
      {/* Thumbnails */}
      <div className="flex justify-center gap-3">
        {workflowScreenshots.map((s, i) => (
          <button
            key={s.label}
            onClick={(e) => { e.stopPropagation(); setActiveIdx(i); }}
            className={`rounded-lg overflow-hidden border-2 transition-all ${i === activeIdx ? 'border-blue-500 shadow-md scale-105' : 'border-gray-200 opacity-60 hover:opacity-100'}`}
            style={{width: '120px'}}
          >
            <img src={s.src} alt={s.label} className="w-full h-auto" />
          </button>
        ))}
      </div>
    </div>
  );
};

const slides = [
  // Slide 1: Intro
  {
    id: 'intro',
    title: 'CAPA Automation Framework',
    subtitle: null,
    content: (
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Hero banner */}
        <div className="rounded-2xl p-8 text-center text-white" style={{background: 'linear-gradient(135deg, #232f3e 0%, #37475a 40%, #527fff 100%)'}}>
          <p className="text-2xl leading-relaxed font-light">
            An intelligent end-to-end framework for{' '}
            <span className="font-bold" style={{color: '#ff9900'}}>provisioning</span>,{' '}
            <span className="font-bold" style={{color: '#44b700'}}>testing</span>, and{' '}
            <span className="font-bold" style={{color: '#00d4ff'}}>managing</span>{' '}
            ROSA HCP clusters on Cluster API Provider AWS.
          </p>
          <p className="text-base mt-4 opacity-80">
            Replacing manual, error-prone workflows with automated playbooks, real-time dashboards,
            and AI-powered remediation.
          </p>
        </div>

        {/* Keyboard hint */}
        <div className="text-center">
          <span className="text-xs text-gray-400">Use <kbd className="px-1.5 py-0.5 rounded border border-gray-300 bg-gray-100 text-gray-500 font-mono text-xs">&#x2190;</kbd> <kbd className="px-1.5 py-0.5 rounded border border-gray-300 bg-gray-100 text-gray-500 font-mono text-xs">&#x2192;</kbd> arrow keys to navigate &middot; <kbd className="px-1.5 py-0.5 rounded border border-gray-300 bg-gray-100 text-gray-500 font-mono text-xs">Esc</kbd> to exit</span>
        </div>

        {/* Feature cards */}
        <div className="grid grid-cols-3 gap-5">
          <div className="rounded-xl p-5 border-l-4 shadow-sm" style={{borderColor: '#527fff', backgroundColor: '#f0f4ff'}}>
            <div className="flex items-center gap-2 text-2xl font-bold mb-2" style={{color: '#527fff'}}><span>&#x1F5A5;</span> MCE + Minikube</div>
            <p className="text-sm text-gray-600">Two environments &mdash; MCE for full OpenShift Hub testing, Minikube for fast local dev</p>
          </div>
          <div className="rounded-xl p-5 border-l-4 shadow-sm" style={{borderColor: '#ff9900', backgroundColor: '#fff8ee'}}>
            <div className="flex items-center gap-2 text-2xl font-bold mb-2" style={{color: '#ff9900'}}><span>&#x2601;</span> AWS Monitoring</div>
            <p className="text-sm text-gray-600">Track quota, usage trends, and resource costs across accounts in real time</p>
          </div>
          <div className="rounded-xl p-5 border-l-4 shadow-sm" style={{borderColor: '#1a8f53', backgroundColor: '#f0faf4'}}>
            <div className="flex items-center gap-2 text-2xl font-bold mb-2" style={{color: '#1a8f53'}}><span>&#x1F4C8;</span> GitHub + Jenkins</div>
            <p className="text-sm text-gray-600">View repo activity, pull request status, and test result trends at a glance</p>
          </div>
          <div className="rounded-xl p-5 border-l-4 shadow-sm" style={{borderColor: '#d13212', backgroundColor: '#fef5f2'}}>
            <div className="flex items-center gap-2 text-2xl font-bold mb-2" style={{color: '#d13212'}}><span>&#x2699;</span> Workflow Builder</div>
            <p className="text-sm text-gray-600">Drag-and-drop multi-step pipelines &mdash; chain verify, provision, test, and delete</p>
          </div>
          <div className="rounded-xl p-5 border-l-4 shadow-sm" style={{borderColor: '#8b5cf6', backgroundColor: '#f5f0ff'}}>
            <div className="flex items-center gap-2 text-2xl font-bold mb-2" style={{color: '#8b5cf6'}}><span>&#x1F916;</span> AI Agents</div>
            <p className="text-sm text-gray-600">Monitor, diagnose, remediate, and learn from failures &mdash; automatically</p>
          </div>
          <div className="rounded-xl p-5 border-l-4 shadow-sm" style={{borderColor: '#232f3e', backgroundColor: '#f4f5f7'}}>
            <div className="flex items-center gap-2 text-2xl font-bold mb-2" style={{color: '#232f3e'}}><span>&#x1F514;</span> Notifications</div>
            <p className="text-sm text-gray-600">Email and Slack alerts on provision, deletion, and failure events &mdash; with AI diagnostic summaries</p>
          </div>
        </div>
      </div>
    ),
  },

  // Slide 2: Problems It Solves
  {
    id: 'problems',
    title: 'Key Benefits',
    subtitle: 'How the framework saves time, reduces manual work, and prevents orphaned AWS resources',
    content: (
      <div className="max-w-3xl mx-auto space-y-5">
        <div className="rounded-xl p-5 text-center text-white mb-2" style={{background: 'linear-gradient(135deg, #232f3e 0%, #527fff 100%)'}}>
          <p className="text-xl font-semibold">
            Every cluster operation &mdash; from provisioning to cleanup &mdash; is automated, monitored by AI, and improved from run to run.
          </p>
        </div>
        <div className="flex items-start gap-6 py-5 border-b border-gray-200">
          <div className="w-14 h-14 rounded-xl flex items-center justify-center flex-shrink-0 text-2xl" style={{backgroundColor: '#fff8ee'}}>&#x1F4CA;</div>
          <div>
            <h3 className="text-xl font-bold text-gray-900">Full Visibility</h3>
            <p className="text-base text-gray-600 mt-1">
              A single pane of glass for cluster status, test results, AWS resource usage,
              Jenkins trends, and active operations across all environments.
            </p>
          </div>
        </div>
        <div className="flex items-start gap-6 py-5 border-b border-gray-200">
          <div className="w-14 h-14 rounded-xl flex items-center justify-center flex-shrink-0 text-2xl" style={{backgroundColor: '#f5f0ff'}}>&#x26A1;</div>
          <div>
            <h3 className="text-xl font-bold text-gray-900">One-Click Workflows</h3>
            <p className="text-base text-gray-600 mt-1">
              Build reusable, multi-step pipelines with drag-and-drop. Chain verify, provision,
              test, and delete into automated workflows that run with a single click.
            </p>
          </div>
        </div>
        <div className="flex items-start gap-6 py-5 border-b border-gray-200">
          <div className="w-14 h-14 rounded-xl flex items-center justify-center flex-shrink-0 text-2xl" style={{backgroundColor: '#f0f4ff'}}>&#x1F916;</div>
          <div>
            <h3 className="text-xl font-bold text-gray-900">Automated Diagnostics</h3>
            <p className="text-base text-gray-600 mt-1">
              No more SSH-ing into clusters and reading logs. The AI pipeline detects issues,
              diagnoses root causes, and remediates failures automatically.
            </p>
          </div>
        </div>
        <div className="flex items-start gap-6 py-5">
          <div className="w-14 h-14 rounded-xl flex items-center justify-center flex-shrink-0 text-2xl" style={{backgroundColor: '#f0faf4'}}>&#x1F9F9;</div>
          <div>
            <h3 className="text-xl font-bold text-gray-900">Automatic Resource Cleanup</h3>
            <p className="text-base text-gray-600 mt-1">
              AI agents detect orphaned CloudFormation stacks, clean up security groups and VPC
              dependencies, and retry deletions &mdash; saving ~$139/month per stack.
            </p>
          </div>
        </div>
      </div>
    ),
  },

  // Slide: Architecture
  {
    id: 'architecture',
    title: 'Architecture',
    subtitle: 'Three layers working together to automate the full cluster lifecycle',
    content: (
      <div className="max-w-5xl mx-auto space-y-5">
        {/* Description */}
        <p className="text-center text-sm text-gray-500">
          Built with modern, production-ready technologies &mdash; each layer is independently testable and connects through well-defined APIs.
        </p>

        {/* Top layer - UI */}
        <div className="rounded-xl p-5 shadow-md" style={{background: 'linear-gradient(135deg, #527fff 0%, #3b5ee6 100%)'}}>
          <div className="flex items-center gap-2 mb-3">
            <h3 className="text-sm font-bold uppercase tracking-wider text-white opacity-90">UI Layer</h3>
            <span className="text-xs font-mono ml-auto text-white opacity-60">React + Tailwind CSS</span>
          </div>
          <div className="grid grid-cols-4 gap-3">
            {['At a Glance Dashboard', 'MCE Environment', 'Minikube Environment', 'Workflow Builder'].map((item) => (
              <div key={item} className="rounded-lg p-3 text-center text-sm font-medium shadow-sm" style={{color: '#527fff', backgroundColor: 'rgba(255,255,255,0.95)'}}>
                {item}
              </div>
            ))}
          </div>
        </div>

        {/* Arrow down */}
        <div className="flex flex-col items-center gap-1">
          <div className="w-0.5 h-3" style={{backgroundColor: '#cbd5e1'}}></div>
          <div className="flex items-center gap-2">
            <div className="h-0.5 w-8" style={{backgroundColor: '#cbd5e1'}}></div>
            <span className="text-xs font-mono px-3 py-1 rounded-full font-semibold" style={{color: '#475569', backgroundColor: '#e2e8f0'}}>REST API + WebSocket</span>
            <div className="h-0.5 w-8" style={{backgroundColor: '#cbd5e1'}}></div>
          </div>
          <div style={{width: 0, height: 0, borderLeft: '6px solid transparent', borderRight: '6px solid transparent', borderTop: '8px solid #cbd5e1'}}></div>
        </div>

        {/* Middle layer - Backend */}
        <div className="rounded-xl p-5 shadow-md" style={{background: 'linear-gradient(135deg, #ff9900 0%, #e88a00 100%)'}}>
          <div className="flex items-center gap-2 mb-3">
            <h3 className="text-sm font-bold uppercase tracking-wider text-white opacity-90">Backend Layer</h3>
            <span className="text-xs font-mono ml-auto text-white opacity-60">Python + FastAPI + Ansible</span>
          </div>
          <div className="grid grid-cols-3 gap-3">
            {[
              { name: 'FastAPI Server', desc: 'Job management, credential handling' },
              { name: 'Ansible Runner', desc: 'Playbook execution engine' },
              { name: 'AI Agent Pipeline', desc: 'Monitor > Diagnose > Remediate > Learn' },
            ].map((item) => (
              <div key={item.name} className="rounded-lg p-3 shadow-sm" style={{backgroundColor: 'rgba(255,255,255,0.95)'}}>
                <div className="text-sm font-medium" style={{color: '#232f3e'}}>{item.name}</div>
                <div className="text-xs mt-1" style={{color: '#b45309'}}>{item.desc}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Arrow down */}
        <div className="flex flex-col items-center gap-1">
          <div className="w-0.5 h-3" style={{backgroundColor: '#cbd5e1'}}></div>
          <div className="flex items-center gap-2">
            <div className="h-0.5 w-8" style={{backgroundColor: '#cbd5e1'}}></div>
            <span className="text-xs font-mono px-3 py-1 rounded-full font-semibold" style={{color: '#475569', backgroundColor: '#e2e8f0'}}>kubectl + aws CLI + boto3</span>
            <div className="h-0.5 w-8" style={{backgroundColor: '#cbd5e1'}}></div>
          </div>
          <div style={{width: 0, height: 0, borderLeft: '6px solid transparent', borderRight: '6px solid transparent', borderTop: '8px solid #cbd5e1'}}></div>
        </div>

        {/* Bottom layer - Infrastructure */}
        <div className="rounded-xl p-5 shadow-md" style={{background: 'linear-gradient(135deg, #232f3e 0%, #37475a 100%)'}}>
          <div className="flex items-center gap-2 mb-3">
            <h3 className="text-sm font-bold uppercase tracking-wider text-white opacity-90">Infrastructure</h3>
            <span className="text-xs font-mono ml-auto text-white opacity-60">AWS + OpenShift + Minikube</span>
          </div>
          <div className="grid grid-cols-4 gap-3">
            {['OpenShift Hub Cluster', 'ROSA HCP Clusters', 'AWS (CF, VPC, IAM)', 'Minikube (local dev)'].map((item) => (
              <div key={item} className="rounded-lg p-3 text-center text-sm font-medium shadow-sm" style={{color: '#232f3e', backgroundColor: 'rgba(255,255,255,0.95)'}}>
                {item}
              </div>
            ))}
          </div>
        </div>
      </div>
    ),
  },

  // Slide: Operational Experience
  {
    id: 'operational-experience',
    title: 'Operational Experience Built Into the Framework',
    subtitle: 'Built from real operational knowledge — not theory, not templates',
    content: (
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Hero statement */}
        <div className="rounded-2xl p-6 text-white" style={{background: 'linear-gradient(135deg, #232f3e 0%, #37475a 40%, #527fff 100%)'}}>
          <p className="text-base font-light leading-relaxed opacity-95">
            This framework was designed and built from hands-on experience &mdash; the feature set, dashboard layouts, sidebar groupings, and workflow design were all shaped to streamline and simplify working with ROSA HCP clusters. Failure patterns, remediation strategies, and confidence thresholds were discovered through real debugging and encoded into the framework &mdash; replacing hours of manual investigation and repetitive cleanup with automated detection and resolution, refined through iterative building and testing.
          </p>
        </div>

        {/* Before / After comparison */}
        <div className="grid grid-cols-2 gap-5">
          <div className="rounded-xl p-5 border-2" style={{borderColor: '#d13212', backgroundColor: '#fef5f2'}}>
            <div className="flex items-center gap-2 mb-3">
              <span className="text-xl">&#x1F6D1;</span>
              <span className="text-lg font-bold" style={{color: '#d13212'}}>Before &mdash; Manual Process</span>
            </div>
            <div className="space-y-2 text-sm text-gray-700">
              <div className="flex items-start gap-2">
                <span style={{color: '#d13212'}}>&#x2717;</span>
                <span>SSH into clusters to read logs and diagnose failures</span>
              </div>
              <div className="flex items-start gap-2">
                <span style={{color: '#d13212'}}>&#x2717;</span>
                <span>Manually identify orphaned CloudFormation stacks</span>
              </div>
              <div className="flex items-start gap-2">
                <span style={{color: '#d13212'}}>&#x2717;</span>
                <span>Hand-delete security groups, ENIs, and VPC dependencies in order</span>
              </div>
              <div className="flex items-start gap-2">
                <span style={{color: '#d13212'}}>&#x2717;</span>
                <span>Run provision, test, and delete steps one at a time</span>
              </div>
              <div className="flex items-start gap-2">
                <span style={{color: '#d13212'}}>&#x2717;</span>
                <span>Check AWS console for quota and resource usage</span>
              </div>
            </div>
          </div>
          <div className="rounded-xl p-5 border-2" style={{borderColor: '#1a8f53', backgroundColor: '#f0faf4'}}>
            <div className="flex items-center gap-2 mb-3">
              <span className="text-xl">&#x1F680;</span>
              <span className="text-lg font-bold" style={{color: '#1a8f53'}}>After &mdash; Automated Framework</span>
            </div>
            <div className="space-y-2 text-sm text-gray-700">
              <div className="flex items-start gap-2">
                <span style={{color: '#1a8f53'}}>&#x2713;</span>
                <span>AI agents monitor logs and diagnose failures in real time</span>
              </div>
              <div className="flex items-start gap-2">
                <span style={{color: '#1a8f53'}}>&#x2713;</span>
                <span>Automatic detection of orphaned stacks and failed deletions</span>
              </div>
              <div className="flex items-start gap-2">
                <span style={{color: '#1a8f53'}}>&#x2713;</span>
                <span>Automated cleanup of SGs, ENIs, VPC endpoints in correct order</span>
              </div>
              <div className="flex items-start gap-2">
                <span style={{color: '#1a8f53'}}>&#x2713;</span>
                <span>One-click workflows chain entire lifecycle together</span>
              </div>
              <div className="flex items-start gap-2">
                <span style={{color: '#1a8f53'}}>&#x2713;</span>
                <span>Live AWS quota and usage dashboard with cost tracking</span>
              </div>
            </div>
          </div>
        </div>

        {/* Metrics */}
        <div className="grid grid-cols-4 gap-4">
          <div className="rounded-xl p-4 text-center border-2" style={{borderColor: '#527fff', backgroundColor: '#f0f4ff'}}>
            <div className="text-2xl font-bold" style={{color: '#527fff'}}>~2 hrs</div>
            <div className="text-xs text-gray-600 mt-1">Manual debugging saved per failed deletion</div>
          </div>
          <div className="rounded-xl p-4 text-center border-2" style={{borderColor: '#ff9900', backgroundColor: '#fff8ee'}}>
            <div className="text-2xl font-bold" style={{color: '#ff9900'}}>~$139/mo</div>
            <div className="text-xs text-gray-600 mt-1">Saved per orphaned stack cleaned up</div>
          </div>
          <div className="rounded-xl p-4 text-center border-2" style={{borderColor: '#1a8f53', backgroundColor: '#f0faf4'}}>
            <div className="text-2xl font-bold" style={{color: '#1a8f53'}}>12+</div>
            <div className="text-xs text-gray-600 mt-1">Failure patterns encoded from real incidents</div>
          </div>
          <div className="rounded-xl p-4 text-center border-2" style={{borderColor: '#8b5cf6', backgroundColor: '#f5f0ff'}}>
            <div className="text-2xl font-bold" style={{color: '#8b5cf6'}}>40+</div>
            <div className="text-xs text-gray-600 mt-1">Ansible playbooks automating manual steps</div>
          </div>
        </div>
      </div>
    ),
  },

  // Slide: Claude API & AI Agents
  {
    id: 'ai-agents',
    title: 'Claude API & AI Agents',
    subtitle: null,
    content: (
      <div className="max-w-5xl mx-auto space-y-8">
        {/* Claude API banner */}
        <div className="rounded-2xl p-6 text-center text-white" style={{background: 'linear-gradient(135deg, #da7756 0%, #c4593a 50%, #232f3e 100%)'}}>
          <p className="text-xl font-light leading-relaxed">
            The framework uses the <span className="font-bold">Claude API</span> for intelligent diagnosis
            and a <span className="font-bold">4-stage AI agent pipeline</span> that runs autonomously during
            every cluster operation.
          </p>
        </div>

        {/* Pipeline flow */}
        <div className="flex items-stretch gap-3">
          <div className="flex-1 rounded-xl p-5 text-center border-2" style={{borderColor: '#527fff', backgroundColor: '#f0f4ff'}}>
            <div className="text-3xl mb-2">1</div>
            <div className="text-lg font-bold mb-1" style={{color: '#527fff'}}>Monitor</div>
            <p className="text-xs text-gray-600">Watches live logs in real time, pattern-matches against known issues database</p>
          </div>
          <div className="flex items-center text-gray-300 text-2xl font-bold">&#x2192;</div>
          <div className="flex-1 rounded-xl p-5 text-center border-2" style={{borderColor: '#ff9900', backgroundColor: '#fff8ee'}}>
            <div className="text-3xl mb-2">2</div>
            <div className="text-lg font-bold mb-1" style={{color: '#ff9900'}}>Diagnose</div>
            <p className="text-xs text-gray-600">Determines root cause using pattern matching + Claude API for unknown failures</p>
          </div>
          <div className="flex items-center text-gray-300 text-2xl font-bold">&#x2192;</div>
          <div className="flex-1 rounded-xl p-5 text-center border-2" style={{borderColor: '#1a8f53', backgroundColor: '#f0faf4'}}>
            <div className="text-3xl mb-2">3</div>
            <div className="text-lg font-bold mb-1" style={{color: '#1a8f53'}}>Remediate</div>
            <p className="text-xs text-gray-600">Executes targeted fixes &mdash; cleans ENIs, security groups, retries CF deletions</p>
          </div>
          <div className="flex items-center text-gray-300 text-2xl font-bold">&#x2192;</div>
          <div className="flex-1 rounded-xl p-5 text-center border-2" style={{borderColor: '#8b5cf6', backgroundColor: '#f5f0ff'}}>
            <div className="text-3xl mb-2">4</div>
            <div className="text-lg font-bold mb-1" style={{color: '#8b5cf6'}}>Learn</div>
            <p className="text-xs text-gray-600">Records outcomes, adjusts confidence scores, improves future diagnoses</p>
          </div>
        </div>

        {/* Details row */}
        <div className="grid grid-cols-2 gap-5">
          <div className="rounded-xl p-5 border border-gray-200 shadow-sm">
            <h3 className="text-lg font-bold text-gray-900 mb-3">Claude API Integration</h3>
            <div className="space-y-2 text-sm text-gray-600">
              <div className="flex items-start gap-2">
                <span className="font-bold" style={{color: '#da7756'}}>&#x2022;</span>
                <span>Analyzes unknown failure patterns that aren't in the knowledge base</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="font-bold" style={{color: '#da7756'}}>&#x2022;</span>
                <span>Suggests new remediation strategies with confidence scoring</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="font-bold" style={{color: '#da7756'}}>&#x2022;</span>
                <span>Powers the AI Assistant chat for interactive troubleshooting</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="font-bold" style={{color: '#da7756'}}>&#x2022;</span>
                <span>New patterns saved to pending_learnings.json for human review</span>
              </div>
            </div>
          </div>
          <div className="rounded-xl p-5 border border-gray-200 shadow-sm">
            <h3 className="text-lg font-bold text-gray-900 mb-3">Safety Model</h3>
            <div className="space-y-2 text-sm text-gray-600">
              <div className="flex items-start gap-2">
                <span className="font-bold" style={{color: '#1a8f53'}}>&#x2022;</span>
                <span>Only known, approved remediations run automatically</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="font-bold" style={{color: '#1a8f53'}}>&#x2022;</span>
                <span>Claude-suggested fixes require human approval before activation</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="font-bold" style={{color: '#1a8f53'}}>&#x2022;</span>
                <span>Confidence thresholds prevent low-confidence actions (min 0.7)</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="font-bold" style={{color: '#1a8f53'}}>&#x2022;</span>
                <span>Learning agent auto-adjusts confidence based on success/failure history</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    ),
  },

  // Slide 4: AI Assistant
  {
    id: 'ai-assistant',
    title: 'AI Assistant',
    subtitle: 'A built-in Claude-powered chat that understands your clusters, logs, and operations — ask it anything without leaving the dashboard',
    content: (
      <div className="max-w-5xl mx-auto space-y-5">
        {/* Features - 4 compact cards */}
        <div className="grid grid-cols-4 gap-4">
          <div className="rounded-xl p-4 border-2 shadow-sm" style={{borderColor: '#8b5cf6', backgroundColor: '#f5f0ff'}}>
            <div className="text-lg font-bold mb-1" style={{color: '#8b5cf6'}}>Context-Aware</div>
            <p className="text-xs text-gray-600">
              Knows your active clusters, recent operations, and credential status automatically.
            </p>
          </div>
          <div className="rounded-xl p-4 border-2 shadow-sm" style={{borderColor: '#527fff', backgroundColor: '#f0f4ff'}}>
            <div className="text-lg font-bold mb-1" style={{color: '#527fff'}}>Debug Failures</div>
            <p className="text-xs text-gray-600">
              Ask why a cluster failed, what an error means, or how to fix it. Analyzes logs and suggests solutions.
            </p>
          </div>
          <div className="rounded-xl p-4 border-2 shadow-sm" style={{borderColor: '#ff9900', backgroundColor: '#fff8ee'}}>
            <div className="text-lg font-bold mb-1" style={{color: '#ff9900'}}>Guided Workflows</div>
            <p className="text-xs text-gray-600">
              Step-by-step guidance on credentials, environments, test suites, and custom workflows.
            </p>
          </div>
          <div className="rounded-xl p-4 border-2 shadow-sm" style={{borderColor: '#1a8f53', backgroundColor: '#f0faf4'}}>
            <div className="text-lg font-bold mb-1" style={{color: '#1a8f53'}}>Zero Context Switching</div>
            <p className="text-xs text-gray-600">
              Built into the UI &mdash; chat alongside your dashboards, logs, and cluster views.
            </p>
          </div>
        </div>

        {/* Example conversation mockup */}
        <div className="rounded-xl border border-gray-200 shadow-md overflow-hidden">
          <div className="px-4 py-2 text-sm font-semibold text-white flex items-center gap-2" style={{backgroundColor: '#232f3e'}}>
            <span style={{color: '#8b5cf6'}}>&#x2B24;</span> AI Assistant
          </div>
          <div className="p-4 space-y-3" style={{backgroundColor: '#fafafa'}}>
            {/* Conversation 1 */}
            <div className="flex justify-end">
              <div className="rounded-lg px-4 py-2 text-sm max-w-md text-white" style={{backgroundColor: '#527fff'}}>
                Why did my e2e-rosa-hcp cluster fail to delete?
              </div>
            </div>
            <div className="flex justify-start">
              <div className="rounded-lg px-4 py-2 text-sm max-w-lg bg-white border border-gray-200 text-gray-700">
                The deletion failed because CloudFormation couldn't delete the VPC stack.
                ROSA created security groups outside of CloudFormation (e.g. *-vpce-private-router)
                that blocked VPC deletion. The AI agent has already cleaned up these resources
                and retried the stack deletion successfully.
              </div>
            </div>
            <div className="border-t border-gray-200 my-1"></div>
            {/* Conversation 2 */}
            <div className="flex justify-end">
              <div className="rounded-lg px-4 py-2 text-sm max-w-md text-white" style={{backgroundColor: '#527fff'}}>
                What&apos;s the current AWS quota usage for my account?
              </div>
            </div>
            <div className="flex justify-start">
              <div className="rounded-lg px-4 py-2 text-sm max-w-lg bg-white border border-gray-200 text-gray-700">
                Your account is using 14 of 20 VPCs (70%), 3 of 5 Elastic IPs (60%), and 28 of 50 EC2 instances (56%).
                You have room for 2 more ROSA HCP clusters before hitting VPC limits.
              </div>
            </div>
          </div>
        </div>
      </div>
    ),
  },

  // Slide: Test Coverage & Code Quality
  {
    id: 'test-coverage',
    title: 'Test Coverage & Code Quality',
    subtitle: 'Over 1,000 automated tests across agents, backend, and frontend',
    content: (
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Test coverage */}
        <div className="rounded-2xl p-5 text-center text-white" style={{background: 'linear-gradient(135deg, #1a8f53 0%, #15803d 50%, #232f3e 100%)'}}>
          <p className="text-4xl font-bold mb-1">1,030 Automated Tests</p>
          <p className="text-base font-light opacity-90">
            Covering agents, backend API, and React components
          </p>
        </div>

        {/* Coverage breakdown */}
        <div className="grid grid-cols-3 gap-5">
          <div className="rounded-xl p-5 border-2 text-center" style={{borderColor: '#8b5cf6', backgroundColor: '#f5f0ff'}}>
            <div className="text-3xl font-bold mb-1" style={{color: '#8b5cf6'}}>197</div>
            <div className="text-sm font-semibold text-gray-900">Agent Tests</div>
            <div className="text-xs text-gray-500 mt-1">~90% coverage</div>
            <div className="mt-2 w-full bg-gray-200 rounded-full h-2">
              <div className="h-2 rounded-full" style={{width: '90%', backgroundColor: '#8b5cf6'}}></div>
            </div>
          </div>
          <div className="rounded-xl p-5 border-2 text-center" style={{borderColor: '#ff9900', backgroundColor: '#fff8ee'}}>
            <div className="text-3xl font-bold mb-1" style={{color: '#ff9900'}}>540</div>
            <div className="text-sm font-semibold text-gray-900">Backend Tests</div>
            <div className="text-xs text-gray-500 mt-1">~74% coverage</div>
            <div className="mt-2 w-full bg-gray-200 rounded-full h-2">
              <div className="h-2 rounded-full" style={{width: '74%', backgroundColor: '#ff9900'}}></div>
            </div>
          </div>
          <div className="rounded-xl p-5 border-2 text-center" style={{borderColor: '#527fff', backgroundColor: '#f0f4ff'}}>
            <div className="text-3xl font-bold mb-1" style={{color: '#527fff'}}>293</div>
            <div className="text-sm font-semibold text-gray-900">Frontend Tests</div>
            <div className="text-xs text-gray-500 mt-1">37 test suites</div>
            <div className="mt-2 w-full bg-gray-200 rounded-full h-2">
              <div className="h-2 rounded-full" style={{width: '45%', backgroundColor: '#527fff'}}></div>
            </div>
          </div>
        </div>

        {/* What's tested */}
        <div className="rounded-xl p-5 border border-gray-200 shadow-sm">
          <div className="text-sm font-bold text-gray-900 mb-3">What&apos;s Covered</div>
          <div className="grid grid-cols-3 gap-3">
            <div className="flex items-center gap-2 text-xs text-gray-600">
              <span style={{color: '#8b5cf6'}}>&#x2713;</span> Agent pipeline end-to-end flows
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-600">
              <span style={{color: '#8b5cf6'}}>&#x2713;</span> All 4 agent stages + learning
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-600">
              <span style={{color: '#8b5cf6'}}>&#x2713;</span> Confidence scoring + thresholds
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-600">
              <span style={{color: '#ff9900'}}>&#x2713;</span> All 40+ REST API endpoints
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-600">
              <span style={{color: '#ff9900'}}>&#x2713;</span> Credential + job management
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-600">
              <span style={{color: '#ff9900'}}>&#x2713;</span> WebSocket + async operations
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-600">
              <span style={{color: '#527fff'}}>&#x2713;</span> Every UI component + page
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-600">
              <span style={{color: '#527fff'}}>&#x2713;</span> Workflow builder interactions
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-600">
              <span style={{color: '#527fff'}}>&#x2713;</span> Dashboard + sidebar navigation
            </div>
          </div>
        </div>
      </div>
    ),
  },

  // Slide: At a Glance Dashboard
  {
    id: 'at-a-glance',
    title: 'At a Glance Dashboard',
    subtitle: 'Clusters, tasks, Jenkins trends, AWS quotas, and GitHub activity — all in one place',
    content: (
      <div className="space-y-4">
        <div className="flex items-center justify-center gap-6 text-xs text-gray-500">
          <span className="flex items-center gap-1"><span style={{color: '#527fff'}}>&#x25CF;</span> Cluster Status</span>
          <span className="flex items-center gap-1"><span style={{color: '#ff9900'}}>&#x25CF;</span> AWS Quota</span>
          <span className="flex items-center gap-1"><span style={{color: '#1a8f53'}}>&#x25CF;</span> Jenkins Trends</span>
          <span className="flex items-center gap-1"><span style={{color: '#8b5cf6'}}>&#x25CF;</span> GitHub Activity</span>
          <span className="flex items-center gap-1"><span style={{color: '#d13212'}}>&#x25CF;</span> Recent Tasks</span>
        </div>
        <MainScreenshotViewer />
      </div>
    ),
  },

  // Slide: MCE Environment Tour
  {
    id: 'mce-tour',
    title: 'MCE Environment',
    subtitle: 'Credentials, controller verification, provisioning, and deletion on a full OpenShift Hub',
    content: (
      <div className="space-y-4">
        <div className="flex items-center justify-center gap-6 text-xs text-gray-500">
          <span className="flex items-center gap-1"><span style={{color: '#ff9900'}}>&#x25CF;</span> Credentials</span>
          <span className="flex items-center gap-1"><span style={{color: '#1a8f53'}}>&#x25CF;</span> Verify Controllers</span>
          <span className="flex items-center gap-1"><span style={{color: '#527fff'}}>&#x25CF;</span> Provision</span>
          <span className="flex items-center gap-1"><span style={{color: '#d13212'}}>&#x25CF;</span> Delete</span>
          <span className="flex items-center gap-1"><span style={{color: '#8b5cf6'}}>&#x25CF;</span> AI Agents</span>
        </div>
        <MCEScreenshotViewer />
      </div>
    ),
  },

  // Slide: Minikube Environment Tour
  {
    id: 'minikube-tour',
    title: 'Minikube Environment',
    subtitle: 'Test custom CAPA provider images from open PRs — fast local iteration without a full Hub',
    content: (
      <div className="space-y-4">
        <div className="flex items-center justify-center gap-6 text-xs text-gray-500">
          <span className="flex items-center gap-1"><span style={{color: '#527fff'}}>&#x25CF;</span> Start Minikube</span>
          <span className="flex items-center gap-1"><span style={{color: '#ff9900'}}>&#x25CF;</span> Custom Images</span>
          <span className="flex items-center gap-1"><span style={{color: '#1a8f53'}}>&#x25CF;</span> PR Testing</span>
          <span className="flex items-center gap-1"><span style={{color: '#8b5cf6'}}>&#x25CF;</span> Local Dev</span>
        </div>
        <MinikubeScreenshotViewer />
      </div>
    ),
  },

  // Slide: Workflow Builder Screenshots
  {
    id: 'workflow-screenshots',
    title: 'Workflow Builder in Action',
    subtitle: 'Drag-and-drop playbooks into multi-step pipelines — configure, chain, and execute with one click',
    content: (
      <div className="space-y-4">
        <div className="flex items-center justify-center gap-6 text-xs text-gray-500">
          <span className="flex items-center gap-1"><span style={{color: '#527fff'}}>&#x25CF;</span> Drag &amp; Drop</span>
          <span className="flex items-center gap-1"><span style={{color: '#ff9900'}}>&#x25CF;</span> Configure Variables</span>
          <span className="flex items-center gap-1"><span style={{color: '#1a8f53'}}>&#x25CF;</span> Set Failure Policy</span>
          <span className="flex items-center gap-1"><span style={{color: '#8b5cf6'}}>&#x25CF;</span> One-Click Execute</span>
        </div>
        <ScreenshotCarousel />
      </div>
    ),
  },

  // Slide: Closing
  {
    id: 'closing',
    title: 'Ready to Explore',
    subtitle: null,
    darkSlide: true,
    content: (
      <div className="max-w-4xl mx-auto space-y-8">
        {/* Tagline */}
        <div className="text-center">
          <p className="text-2xl font-light leading-relaxed text-gray-300">
            One framework. Two environments. Full lifecycle automation.
          </p>
          <p className="text-base mt-3 text-gray-500">
            From provisioning to deletion, from failure detection to automated cleanup &mdash; built to save time and prevent costly mistakes.
          </p>
        </div>

        {/* Key takeaways */}
        <div className="grid grid-cols-3 gap-5">
          <div className="rounded-xl p-5 text-center border" style={{borderColor: '#3b4f6a', backgroundColor: 'rgba(82, 127, 255, 0.1)'}}>
            <div className="text-3xl font-bold mb-2" style={{color: '#527fff'}}>40+</div>
            <div className="text-sm font-semibold text-gray-300">Ansible Playbooks</div>
            <div className="text-xs text-gray-500 mt-1">Automating every manual step</div>
          </div>
          <div className="rounded-xl p-5 text-center border" style={{borderColor: '#2d5a3e', backgroundColor: 'rgba(26, 143, 83, 0.1)'}}>
            <div className="text-3xl font-bold mb-2" style={{color: '#1a8f53'}}>1,030</div>
            <div className="text-sm font-semibold text-gray-300">Automated Tests</div>
            <div className="text-xs text-gray-500 mt-1">Agents, backend, and frontend</div>
          </div>
          <div className="rounded-xl p-5 text-center border" style={{borderColor: '#5a4020', backgroundColor: 'rgba(255, 153, 0, 0.1)'}}>
            <div className="text-3xl font-bold mb-2" style={{color: '#ff9900'}}>~$139/mo</div>
            <div className="text-sm font-semibold text-gray-300">Saved Per Cleanup</div>
            <div className="text-xs text-gray-500 mt-1">Orphaned AWS resources caught automatically</div>
          </div>
        </div>

        {/* Capabilities summary */}
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center gap-3 rounded-lg p-3" style={{backgroundColor: 'rgba(255,255,255,0.05)'}}>
            <span className="text-lg" style={{color: '#527fff'}}>&#x2713;</span>
            <span className="text-sm text-gray-400">MCE + Minikube environments with credential management</span>
          </div>
          <div className="flex items-center gap-3 rounded-lg p-3" style={{backgroundColor: 'rgba(255,255,255,0.05)'}}>
            <span className="text-lg" style={{color: '#527fff'}}>&#x2713;</span>
            <span className="text-sm text-gray-400">Drag-and-drop workflow builder with one-click execution</span>
          </div>
          <div className="flex items-center gap-3 rounded-lg p-3" style={{backgroundColor: 'rgba(255,255,255,0.05)'}}>
            <span className="text-lg" style={{color: '#527fff'}}>&#x2713;</span>
            <span className="text-sm text-gray-400">4-stage AI pipeline: Monitor, Diagnose, Remediate, Learn</span>
          </div>
          <div className="flex items-center gap-3 rounded-lg p-3" style={{backgroundColor: 'rgba(255,255,255,0.05)'}}>
            <span className="text-lg" style={{color: '#527fff'}}>&#x2713;</span>
            <span className="text-sm text-gray-400">Real-time dashboards with AWS quota and cost tracking</span>
          </div>
          <div className="flex items-center gap-3 rounded-lg p-3" style={{backgroundColor: 'rgba(255,255,255,0.05)'}}>
            <span className="text-lg" style={{color: '#527fff'}}>&#x2713;</span>
            <span className="text-sm text-gray-400">Claude-powered AI assistant for interactive troubleshooting</span>
          </div>
          <div className="flex items-center gap-3 rounded-lg p-3" style={{backgroundColor: 'rgba(255,255,255,0.05)'}}>
            <span className="text-lg" style={{color: '#527fff'}}>&#x2713;</span>
            <span className="text-sm text-gray-400">Live log streaming with Ansible syntax highlighting</span>
          </div>
        </div>

        {/* CTA */}
        <div className="text-center pt-2">
          <p className="text-sm text-gray-500">Click <span className="font-semibold text-gray-400">Start Exploring</span> below to jump into the dashboard</p>
        </div>
      </div>
    ),
    showStartDemo: true,
  },
];

const slideTransitionStyle = `
  @keyframes slideFadeIn {
    from { opacity: 0; transform: translateY(12px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .slide-animate {
    animation: slideFadeIn 0.4s ease-out;
  }
`;

const PresentationMode = () => {
  const navigate = useNavigate();
  const [currentSlide, setCurrentSlide] = useState(0);

  const goNext = useCallback(() => {
    if (currentSlide < slides.length - 1) {
      setCurrentSlide(currentSlide + 1);
    }
  }, [currentSlide]);

  const goPrev = useCallback(() => {
    if (currentSlide > 0) {
      setCurrentSlide(currentSlide - 1);
    }
  }, [currentSlide]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'ArrowRight' || e.key === ' ') {
        e.preventDefault();
        goNext();
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        goPrev();
      } else if (e.key === 'Escape') {
        navigate('/');
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [goNext, goPrev, navigate]);

  const slide = slides[currentSlide];

  return (
    <div className={`h-screen w-screen flex flex-col overflow-hidden transition-colors duration-500 ${slide.darkSlide ? 'bg-gray-900' : 'bg-white'}`}>
      <style>{slideTransitionStyle}</style>
      {/* Top bar */}
      <div className="flex flex-col flex-shrink-0">
        <div className="flex items-center justify-between px-6 py-3 bg-gradient-to-r from-gray-900 to-gray-800 text-white">
          <div className="flex items-center gap-3">
            <span className="text-sm font-mono opacity-70">CAPA Framework</span>
            <span className="text-xs opacity-40">|</span>
            <span className="text-sm opacity-50">{slide.title}</span>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm opacity-70">
              {currentSlide + 1} / {slides.length}
            </span>
            <button
              onClick={() => navigate('/')}
              className="p-1.5 hover:bg-gray-700 rounded transition-colors"
              title="Exit presentation (Esc)"
            >
              <XMarkIcon className="h-5 w-5" />
            </button>
          </div>
        </div>
        {/* Progress bar */}
        <div className="w-full h-1 bg-gray-200">
          <div
            className="h-1 transition-all duration-500 ease-out"
            style={{
              width: `${((currentSlide + 1) / slides.length) * 100}%`,
              background: 'linear-gradient(90deg, #527fff 0%, #8b5cf6 100%)',
            }}
          />
        </div>
      </div>

      {/* Slide content */}
      <div className="flex-1 flex flex-col items-center justify-start px-12 py-4 overflow-y-auto">
        <div key={slide.id} className="w-full max-w-6xl slide-animate">
          {/* Title */}
          <div className="text-center mb-4">
            <h1 className={`font-bold tracking-tight ${slide.darkSlide ? 'text-6xl text-white' : 'text-4xl text-gray-900'}`}>{slide.title}</h1>
            {slide.subtitle && (
              <p className={`text-lg mt-2 ${slide.darkSlide ? 'text-gray-400' : 'text-gray-500'}`}>{slide.subtitle}</p>
            )}
          </div>

          {/* Content */}
          <div className="mt-2">
            {slide.content}
          </div>

        </div>
      </div>

      {/* Navigation bar */}
      <div className={`flex items-center justify-between px-6 py-4 border-t flex-shrink-0 transition-colors duration-500 ${slide.darkSlide ? 'bg-gray-800 border-gray-700' : 'bg-gray-50 border-gray-200'}`}>
        <button
          onClick={goPrev}
          disabled={currentSlide === 0}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
            currentSlide === 0
              ? `${slide.darkSlide ? 'text-gray-600' : 'text-gray-300'} cursor-not-allowed`
              : `${slide.darkSlide ? 'text-gray-300 hover:bg-gray-700' : 'text-gray-700 hover:bg-gray-200'}`
          }`}
        >
          <ChevronLeftIcon className="h-5 w-5" />
          Previous
        </button>

        {/* Slide indicators */}
        <div className="flex items-center gap-1.5">
          {slides.map((s, i) => (
            <button
              key={s.id}
              onClick={() => setCurrentSlide(i)}
              className="h-1.5 rounded-full transition-all duration-300"
              style={{
                width: i === currentSlide ? '24px' : '8px',
                backgroundColor: i === currentSlide ? '#527fff' : i < currentSlide ? '#93a3b8' : '#d1d5db',
              }}
              title={s.title}
            />
          ))}
        </div>

        <button
          onClick={currentSlide === slides.length - 1 ? () => navigate('/') : goNext}
          className={`flex items-center gap-2 rounded-lg font-medium transition-all ${
            currentSlide === slides.length - 1
              ? 'px-6 py-2.5 text-lg bg-blue-500 text-white hover:bg-blue-400 shadow-lg shadow-blue-500/30'
              : `px-4 py-2 ${slide.darkSlide ? 'text-gray-300 hover:bg-gray-700' : 'text-gray-700 hover:bg-gray-200'}`
          }`}
        >
          {currentSlide === slides.length - 1 ? 'Start Exploring' : 'Next'}
          <ChevronRightIcon className="h-5 w-5" />
        </button>
      </div>
    </div>
  );
};

export default PresentationMode;
