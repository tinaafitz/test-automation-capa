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
  { label: 'Email Alerts', indent: true, icon: '\uD83D\uDCE8', description: 'Automated email notifications for cluster lifecycle events — started, success, and failure', content: (
    <div className="flex gap-3 h-full items-start justify-center">
      <div className="flex flex-col items-center gap-1 flex-1">
        <span className="text-xs font-semibold text-gray-500">Started</span>
        <img src="/screenshots/email-started.png" alt="Email: Started" className="rounded-lg border border-gray-200 shadow-sm w-full object-contain" style={{maxHeight: '500px'}} />
      </div>
      <div className="flex flex-col items-center gap-1 flex-1">
        <span className="text-xs font-semibold text-gray-500">Success</span>
        <img src="/screenshots/email-success.png" alt="Email: Success" className="rounded-lg border border-gray-200 shadow-sm w-full object-contain" style={{maxHeight: '500px'}} />
      </div>
      <div className="flex flex-col items-center gap-1 flex-1">
        <span className="text-xs font-semibold text-gray-500">Failed</span>
        <img src="/screenshots/email-failed.png" alt="Email: Failed" className="rounded-lg border border-gray-200 shadow-sm w-full object-contain" style={{maxHeight: '500px'}} />
      </div>
    </div>
  )},
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
  { label: 'Email Alerts', indent: true, icon: '\uD83D\uDCE8', description: 'Automated email notifications for cluster lifecycle events — started, success, and failure', content: (
    <div className="flex gap-3 h-full items-start justify-center">
      <div className="flex flex-col items-center gap-1 flex-1">
        <span className="text-xs font-semibold text-gray-500">Started</span>
        <img src="/screenshots/email-started.png" alt="Email: Started" className="rounded-lg border border-gray-200 shadow-sm w-full object-contain" style={{maxHeight: '500px'}} />
      </div>
      <div className="flex flex-col items-center gap-1 flex-1">
        <span className="text-xs font-semibold text-gray-500">Success</span>
        <img src="/screenshots/email-success.png" alt="Email: Success" className="rounded-lg border border-gray-200 shadow-sm w-full object-contain" style={{maxHeight: '500px'}} />
      </div>
      <div className="flex flex-col items-center gap-1 flex-1">
        <span className="text-xs font-semibold text-gray-500">Failed</span>
        <img src="/screenshots/email-failed.png" alt="Email: Failed" className="rounded-lg border border-gray-200 shadow-sm w-full object-contain" style={{maxHeight: '500px'}} />
      </div>
    </div>
  )},
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
  { label: 'Email Alerts', indent: true, icon: '\uD83D\uDCE8', description: 'Automated email notifications for cluster lifecycle events — started, success, and failure', content: (
    <div className="flex gap-3 h-full items-start justify-center">
      <div className="flex flex-col items-center gap-1 flex-1">
        <span className="text-xs font-semibold text-gray-500">Started</span>
        <img src="/screenshots/email-started.png" alt="Email: Started" className="rounded-lg border border-gray-200 shadow-sm w-full object-contain" style={{maxHeight: '500px'}} />
      </div>
      <div className="flex flex-col items-center gap-1 flex-1">
        <span className="text-xs font-semibold text-gray-500">Success</span>
        <img src="/screenshots/email-success.png" alt="Email: Success" className="rounded-lg border border-gray-200 shadow-sm w-full object-contain" style={{maxHeight: '500px'}} />
      </div>
      <div className="flex flex-col items-center gap-1 flex-1">
        <span className="text-xs font-semibold text-gray-500">Failed</span>
        <img src="/screenshots/email-failed.png" alt="Email: Failed" className="rounded-lg border border-gray-200 shadow-sm w-full object-contain" style={{maxHeight: '500px'}} />
      </div>
    </div>
  )},
  { label: 'Task Summary', icon: '\uD83D\uDCCB', src: '/screenshots/mk-task-summary.png', description: 'View recent Minikube operations with timestamps, status badges, and logs' },
  { label: 'AI Assistant', icon: '\uD83E\uDD16', src: '/screenshots/mk-ai-assistant.png', description: 'Chat with Claude about your Minikube environment, clusters, and operations' },
  { label: 'AWS Usage', icon: '\u2601', src: '/screenshots/mk-aws-usage.png', description: 'Track AWS resource quotas, usage trends, and estimated monthly costs' },
];

const ScreenshotSidebarViewer = ({ items, title, gradient }) => {
  const [activeIdx, setActiveIdx] = useState(0);
  const item = items[activeIdx];
  return (
    <div className="flex gap-4 w-full" style={{height: 'calc(100vh - 200px)', maxHeight: '800px'}}>
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
              <span className="text-base" style={s.indent ? {marginLeft: '24px'} : undefined}>{s.icon}</span>
              <span style={s.indent ? {fontSize: '0.65rem'} : undefined}>{s.label}</span>
            </button>
          ))}
        </div>
      </div>
      {/* Screenshot + description */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex-1 rounded-xl overflow-hidden border border-gray-200 shadow-md">
          {item.content ? (
            <div className="w-full h-full overflow-auto p-4" style={{backgroundColor: '#f8fafc'}}>
              {item.content}
            </div>
          ) : (
            <img src={item.src} alt={item.label} className="w-full h-full object-contain object-left-top" style={{backgroundColor: '#f8fafc'}} />
          )}
        </div>
        {item.description && (
          <p className="text-xs text-gray-500 text-center mt-2 px-4">{item.description}</p>
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

const deletionScreenshots = [
  { src: '/screenshots/mce-delete-clusters.png', label: '1. ROSA HCP Clusters', description: 'Three clusters running — lol-rosa-hcp is Ready and targeted for deletion' },
  { src: '/screenshots/mce-delete-confirm.png', label: '2. Confirm Deletion', description: 'Safety confirmation — "This action cannot be undone and will remove all associated resources"' },
  { src: '/screenshots/mce-delete-started.png', label: '3. Deletion Started', description: 'AI Agent activates in Monitoring mode — playbook begins deleting cluster resources' },
  { src: '/screenshots/mce-delete-agent-monitoring.png', label: '4. Agent Monitoring', description: 'Agent tracks ROSAControlPlane deletion — status: Uninstalling, CAPA controller managing deletion' },
  { src: '/screenshots/mce-delete-agent-network.png', label: '5. Network Cleanup', description: 'Cluster removed from list — agent now monitoring ROSANetwork and CloudFormation stack deletion' },
  { src: '/screenshots/mce-delete-complete.png', label: '6. Deletion Complete', description: 'Agent summary: 3 resources monitored, 3 issues auto-fixed — VPC deps cleaned, finalizers removed' },
  { src: '/screenshots/mce-delete-agent-detail.png', label: '7. Agent Detail', description: 'Full timeline — ROSAControlPlane monitored, ROSANetwork SGs cleaned, CloudFormation stack resolved' },
];

const ScreenshotCarousel = ({ screenshots = workflowScreenshots }) => {
  const [activeIdx, setActiveIdx] = useState(0);
  const shot = screenshots[activeIdx];
  return (
    <div className="max-w-5xl mx-auto space-y-4">
      {/* Main image */}
      <div className="relative rounded-xl overflow-hidden shadow-xl border border-gray-200">
        <img src={shot.src} alt={shot.label} className="w-full h-auto" />
        {/* Left arrow */}
        <button
          onClick={(e) => { e.stopPropagation(); setActiveIdx((activeIdx - 1 + screenshots.length) % screenshots.length); }}
          className="absolute left-3 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full flex items-center justify-center text-white text-xl font-bold transition-opacity hover:opacity-100"
          style={{backgroundColor: 'rgba(35,47,62,0.7)', opacity: 0.6}}
        >
          &#x2039;
        </button>
        {/* Right arrow */}
        <button
          onClick={(e) => { e.stopPropagation(); setActiveIdx((activeIdx + 1) % screenshots.length); }}
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
        {screenshots.map((s, i) => (
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
    subtitle: 'ROSA HCP on Cluster API Provider AWS',
    content: (
      <div className="max-w-5xl mx-auto space-y-5">
        {/* Hero banner */}
        <div className="rounded-2xl p-8 text-center text-white" style={{background: 'linear-gradient(135deg, #232f3e 0%, #37475a 40%, #527fff 100%)'}}>
          <p className="text-3xl leading-relaxed font-light">
            An intelligent end-to-end framework for{' '}
            <span className="font-extrabold text-4xl" style={{color: '#ff9900'}}>provisioning</span>,{' '}
            <span className="font-extrabold text-4xl" style={{color: '#44b700'}}>testing</span>, and{' '}
            <span className="font-extrabold text-4xl" style={{color: '#00d4ff'}}>managing</span>{' '}
            ROSA HCP clusters.
          </p>
          <p className="text-base mt-4 opacity-80">
            Replacing manual, error-prone workflows with automated playbooks, real-time dashboards,
            and AI-powered remediation.
          </p>
        </div>

        {/* Feature cards */}
        <div className="grid grid-cols-3 gap-4">
          <div className="rounded-xl p-5 border-l-4 shadow-sm" style={{borderColor: '#527fff', backgroundColor: '#f0f4ff'}}>
            <div className="flex items-center gap-3 mb-2">
              <div className="w-9 h-9 rounded-lg flex items-center justify-center text-white text-sm font-bold" style={{backgroundColor: '#527fff'}}>&#x25A6;</div>
              <span className="text-lg font-bold" style={{color: '#527fff'}}>MCE + Minikube</span>
            </div>
            <p className="text-sm text-gray-600">Two environments &mdash; MCE for full OpenShift Hub testing, Minikube for fast local dev</p>
          </div>
          <div className="rounded-xl p-5 border-l-4 shadow-sm" style={{borderColor: '#ff9900', backgroundColor: '#fff8ee'}}>
            <div className="flex items-center gap-3 mb-2">
              <div className="w-9 h-9 rounded-lg flex items-center justify-center text-white text-sm font-bold" style={{backgroundColor: '#ff9900'}}>&#x2601;</div>
              <span className="text-lg font-bold" style={{color: '#ff9900'}}>AWS Monitoring</span>
            </div>
            <p className="text-sm text-gray-600">Track quota, usage trends, and resource costs across accounts on-demand</p>
          </div>
          <div className="rounded-xl p-5 border-l-4 shadow-sm" style={{borderColor: '#1a8f53', backgroundColor: '#f0faf4'}}>
            <div className="flex items-center gap-3 mb-2">
              <div className="w-9 h-9 rounded-lg flex items-center justify-center text-white text-sm font-bold" style={{backgroundColor: '#1a8f53'}}>&#x2191;</div>
              <span className="text-lg font-bold" style={{color: '#1a8f53'}}>GitHub + Jenkins</span>
            </div>
            <p className="text-sm text-gray-600">View repo activity, pull request status, and test result trends at a glance</p>
          </div>
          <div className="rounded-xl p-5 border-l-4 shadow-sm" style={{borderColor: '#0ea5e9', backgroundColor: '#f0f9ff'}}>
            <div className="flex items-center gap-3 mb-2">
              <div className="w-9 h-9 rounded-lg flex items-center justify-center text-white text-sm font-bold" style={{backgroundColor: '#0ea5e9'}}>&#x2B82;</div>
              <span className="text-lg font-bold" style={{color: '#0ea5e9'}}>Workflow Builder</span>
            </div>
            <p className="text-sm text-gray-600">Drag-and-drop multi-step pipelines &mdash; chain verify, provision, test, and delete</p>
          </div>
          <div className="rounded-xl p-5 border-l-4 shadow-sm" style={{borderColor: '#8b5cf6', backgroundColor: '#f5f0ff'}}>
            <div className="flex items-center gap-3 mb-2">
              <div className="w-9 h-9 rounded-lg flex items-center justify-center text-white text-sm font-bold" style={{backgroundColor: '#8b5cf6'}}>&#x2B23;</div>
              <span className="text-lg font-bold" style={{color: '#8b5cf6'}}>AI Agents</span>
            </div>
            <p className="text-sm text-gray-600">Monitor, diagnose, remediate, and learn from failures &mdash; automatically</p>
          </div>
          <div className="rounded-xl p-5 border-l-4 shadow-sm" style={{borderColor: '#232f3e', backgroundColor: '#f4f5f7'}}>
            <div className="flex items-center gap-3 mb-2">
              <div className="w-9 h-9 rounded-lg flex items-center justify-center text-white text-sm font-bold" style={{backgroundColor: '#232f3e'}}>&#x2709;</div>
              <span className="text-lg font-bold" style={{color: '#232f3e'}}>Notifications</span>
            </div>
            <p className="text-sm text-gray-600">Email and Slack alerts on provision, deletion, and failure events &mdash; with AI diagnostic summaries</p>
          </div>
        </div>

        {/* Bottom stat bar */}
        <div className="flex items-center justify-center gap-8 py-3 rounded-xl" style={{backgroundColor: '#f8fafc', border: '1px solid #e2e8f0'}}>
          <div className="text-center">
            <span className="text-lg font-bold" style={{color: '#527fff'}}>40+</span>
            <span className="text-xs text-gray-500 ml-1.5">Ansible Playbooks</span>
          </div>
          <div className="w-px h-6" style={{backgroundColor: '#e2e8f0'}}></div>
          <div className="text-center">
            <span className="text-lg font-bold" style={{color: '#1a8f53'}}>2,064</span>
            <span className="text-xs text-gray-500 ml-1.5">Automated Tests</span>
          </div>
          <div className="w-px h-6" style={{backgroundColor: '#e2e8f0'}}></div>
          <div className="text-center">
            <span className="text-lg font-bold" style={{color: '#8b5cf6'}}>4-Stage</span>
            <span className="text-xs text-gray-500 ml-1.5">AI Agent Pipeline</span>
          </div>
          <div className="w-px h-6" style={{backgroundColor: '#e2e8f0'}}></div>
          <div className="text-center">
            <span className="text-lg font-bold" style={{color: '#ff9900'}}>12+</span>
            <span className="text-xs text-gray-500 ml-1.5">Failure Patterns Encoded</span>
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
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="rounded-xl p-4 text-center text-white" style={{background: 'linear-gradient(135deg, #232f3e 0%, #527fff 100%)'}}>
          <p className="text-lg font-semibold">
            Every cluster operation &mdash; from provisioning to cleanup &mdash; is automated, monitored by AI, and improved from run to run.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-5">
          <div className="rounded-xl p-5 border-l-4 shadow-sm" style={{borderColor: '#527fff', backgroundColor: '#f0f4ff'}}>
            <div className="flex items-center gap-3 mb-2">
              <div className="w-9 h-9 rounded-lg flex items-center justify-center text-white text-sm font-bold" style={{backgroundColor: '#527fff'}}>&#x25A6;</div>
              <h3 className="text-base font-bold text-gray-900">Full Visibility</h3>
            </div>
            <p className="text-sm text-gray-600 mb-2">
              Single pane of glass for cluster status, test results, AWS usage, and Jenkins trends.
            </p>
            <ul className="text-xs text-gray-500 space-y-1 ml-1">
              <li className="flex items-start gap-1.5"><span style={{color: '#527fff'}}>&#x25B8;</span> Centralized logging across all operations</li>
              <li className="flex items-start gap-1.5"><span style={{color: '#527fff'}}>&#x25B8;</span> Previous task logs always accessible</li>
              <li className="flex items-start gap-1.5"><span style={{color: '#527fff'}}>&#x25B8;</span> Real-time status across both environments simultaneously</li>
            </ul>
          </div>

          <div className="rounded-xl p-5 border-l-4 shadow-sm" style={{borderColor: '#0ea5e9', backgroundColor: '#f0f9ff'}}>
            <div className="flex items-center gap-3 mb-2">
              <div className="w-9 h-9 rounded-lg flex items-center justify-center text-white text-sm font-bold" style={{backgroundColor: '#0ea5e9'}}>&#x2B82;</div>
              <h3 className="text-base font-bold text-gray-900">One-Click Workflows</h3>
            </div>
            <p className="text-sm text-gray-600 mb-2">
              Drag-and-drop pipelines that chain verify, provision, test, and delete.
            </p>
            <ul className="text-xs text-gray-500 space-y-1 ml-1">
              <li className="flex items-start gap-1.5"><span style={{color: '#0ea5e9'}}>&#x25B8;</span> 30-second environment setup</li>
              <li className="flex items-start gap-1.5"><span style={{color: '#0ea5e9'}}>&#x25B8;</span> Run tests in MCE and Minikube at the same time</li>
              <li className="flex items-start gap-1.5"><span style={{color: '#0ea5e9'}}>&#x25B8;</span> Minikube testing transfers to MCE when production-ready</li>
            </ul>
          </div>

          <div className="rounded-xl p-5 border-l-4 shadow-sm" style={{borderColor: '#8b5cf6', backgroundColor: '#f5f0ff'}}>
            <div className="flex items-center gap-3 mb-2">
              <div className="w-9 h-9 rounded-lg flex items-center justify-center text-white text-sm font-bold" style={{backgroundColor: '#8b5cf6'}}>&#x2B23;</div>
              <h3 className="text-base font-bold text-gray-900">Automated Diagnostics</h3>
            </div>
            <p className="text-sm text-gray-600 mb-2">
              AI pipeline detects issues, diagnoses root causes, and remediates automatically.
            </p>
            <ul className="text-xs text-gray-500 space-y-1 ml-1">
              <li className="flex items-start gap-1.5"><span style={{color: '#8b5cf6'}}>&#x25B8;</span> Early bug detection before failures cascade</li>
              <li className="flex items-start gap-1.5"><span style={{color: '#8b5cf6'}}>&#x25B8;</span> Learned knowledge shared across runs</li>
              <li className="flex items-start gap-1.5"><span style={{color: '#8b5cf6'}}>&#x25B8;</span> Failure-only notifications &mdash; no noise</li>
            </ul>
          </div>

          <div className="rounded-xl p-5 border-l-4 shadow-sm" style={{borderColor: '#1a8f53', backgroundColor: '#f0faf4'}}>
            <div className="flex items-center gap-3 mb-2">
              <div className="w-9 h-9 rounded-lg flex items-center justify-center text-white text-sm font-bold" style={{backgroundColor: '#1a8f53'}}>&#x2714;</div>
              <h3 className="text-base font-bold text-gray-900">Automatic Resource Cleanup</h3>
            </div>
            <p className="text-sm text-gray-600 mb-2">
              AI agents detect orphaned stacks, clean up VPC dependencies, and retry deletions.
            </p>
            <ul className="text-xs text-gray-500 space-y-1 ml-1">
              <li className="flex items-start gap-1.5"><span style={{color: '#1a8f53'}}>&#x25B8;</span> Orphaned resource remediation saves real AWS costs</li>
              <li className="flex items-start gap-1.5"><span style={{color: '#1a8f53'}}>&#x25B8;</span> AI agents learn and improve from every cleanup</li>
              <li className="flex items-start gap-1.5"><span style={{color: '#1a8f53'}}>&#x25B8;</span> Full dependency chain cleanup in the correct order</li>
            </ul>
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
      <div className="max-w-5xl mx-auto space-y-4">
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
          <div className="grid grid-cols-5 gap-3">
            {[
              { icon: '\u25A6', name: 'Dashboard', desc: 'Unified status view' },
              { icon: '\u2756', name: 'MCE Environment', desc: 'Full Hub testing' },
              { icon: '\u25B6', name: 'Minikube', desc: 'Fast local dev' },
              { icon: '\u2B82', name: 'Workflow Builder', desc: 'Drag-and-drop pipelines' },
              { icon: '\u2B50', name: 'AI Assistant', desc: 'Context-aware chat' },
            ].map((item) => (
              <div key={item.name} className="rounded-lg p-3 text-center shadow-sm border" style={{backgroundColor: 'rgba(255,255,255,0.97)', borderColor: 'rgba(82,127,255,0.2)'}}>
                <div className="text-xl mb-1 font-bold" style={{color: '#527fff'}}>{item.icon}</div>
                <div className="text-xs font-semibold" style={{color: '#3b5ee6'}}>{item.name}</div>
                <div className="text-xs mt-0.5" style={{color: '#6b7280'}}>{item.desc}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Arrow down */}
        <div className="flex flex-col items-center gap-0.5">
          <div className="w-0.5 h-2" style={{backgroundColor: '#94a3b8'}}></div>
          <div className="flex items-center gap-2">
            <div className="h-0.5 w-10" style={{backgroundColor: '#94a3b8'}}></div>
            <span className="text-xs font-mono px-3 py-1 rounded-full font-semibold" style={{color: '#334155', backgroundColor: '#e2e8f0'}}>REST API + WebSocket</span>
            <div className="h-0.5 w-10" style={{backgroundColor: '#94a3b8'}}></div>
          </div>
          <div style={{width: 0, height: 0, borderLeft: '6px solid transparent', borderRight: '6px solid transparent', borderTop: '8px solid #94a3b8'}}></div>
        </div>

        {/* Middle layer - Backend */}
        <div className="rounded-xl p-5 shadow-md" style={{background: 'linear-gradient(135deg, #ff9900 0%, #e88a00 100%)'}}>
          <div className="flex items-center gap-2 mb-3">
            <h3 className="text-sm font-bold uppercase tracking-wider text-white opacity-90">Backend Layer</h3>
            <span className="text-xs font-mono ml-auto text-white opacity-60">Python + FastAPI + Ansible</span>
          </div>
          <div className="grid grid-cols-4 gap-3">
            {[
              { icon: '\u26A1', name: 'FastAPI Server', desc: 'Job mgmt, credentials, WebSocket' },
              { icon: '\u25B7', name: 'Ansible Runner', desc: '40+ playbooks, async execution' },
              { icon: '\u2B23', name: 'AI Agent Pipeline', desc: 'Monitor \u2192 Diagnose \u2192 Remediate \u2192 Learn' },
              { icon: '\u2709', name: 'Notifications', desc: 'Email + Slack with AI summaries' },
            ].map((item) => (
              <div key={item.name} className="rounded-lg p-3 text-center shadow-sm border" style={{backgroundColor: 'rgba(255,255,255,0.97)', borderColor: 'rgba(255,153,0,0.2)'}}>
                <div className="text-xl mb-1 font-bold" style={{color: '#e88a00'}}>{item.icon}</div>
                <div className="text-xs font-semibold" style={{color: '#232f3e'}}>{item.name}</div>
                <div className="text-xs mt-0.5" style={{color: '#b45309'}}>{item.desc}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Arrow down */}
        <div className="flex flex-col items-center gap-0.5">
          <div className="w-0.5 h-2" style={{backgroundColor: '#94a3b8'}}></div>
          <div className="flex items-center gap-2">
            <div className="h-0.5 w-10" style={{backgroundColor: '#94a3b8'}}></div>
            <span className="text-xs font-mono px-3 py-1 rounded-full font-semibold" style={{color: '#334155', backgroundColor: '#e2e8f0'}}>kubectl + aws CLI + boto3</span>
            <div className="h-0.5 w-10" style={{backgroundColor: '#94a3b8'}}></div>
          </div>
          <div style={{width: 0, height: 0, borderLeft: '6px solid transparent', borderRight: '6px solid transparent', borderTop: '8px solid #94a3b8'}}></div>
        </div>

        {/* Bottom layer - Infrastructure */}
        <div className="rounded-xl p-5 shadow-md" style={{background: 'linear-gradient(135deg, #232f3e 0%, #37475a 100%)'}}>
          <div className="flex items-center gap-2 mb-3">
            <h3 className="text-sm font-bold uppercase tracking-wider text-white opacity-90">Infrastructure</h3>
            <span className="text-xs font-mono ml-auto text-white opacity-60">AWS + OpenShift + Minikube</span>
          </div>
          <div className="grid grid-cols-4 gap-3">
            {[
              { icon: '\u2B22', name: 'OpenShift Hub', desc: 'MCE + CAPI/CAPA controllers' },
              { icon: '\u2B24', name: 'ROSA HCP Clusters', desc: 'Managed control planes on AWS' },
              { icon: '\u2B21', name: 'AWS Services', desc: 'CloudFormation, VPC, IAM, S3' },
              { icon: '\u25C6', name: 'Minikube', desc: 'Local dev + PR image testing' },
            ].map((item) => (
              <div key={item.name} className="rounded-lg p-3 text-center shadow-sm border" style={{backgroundColor: 'rgba(255,255,255,0.97)', borderColor: 'rgba(255,255,255,0.3)'}}>
                <div className="text-xl mb-1 font-bold" style={{color: '#94a3b8'}}>{item.icon}</div>
                <div className="text-xs font-semibold" style={{color: '#232f3e'}}>{item.name}</div>
                <div className="text-xs mt-0.5" style={{color: '#64748b'}}>{item.desc}</div>
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
    subtitle: ' ',
    content: (
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Hero statement */}
        <div className="rounded-2xl p-6 text-white" style={{background: 'linear-gradient(135deg, #232f3e 0%, #37475a 40%, #527fff 100%)'}}>
          <p className="text-base font-light leading-relaxed opacity-95">
            This framework was designed to streamline and simplify working with ROSA HCP clusters. Failure patterns, remediation strategies, and confidence thresholds discovered through experience are encoded into the framework &mdash; replacing hours of manual error prone tasks, investigations and repetitive cleanup with automated detection and resolution, refined through iterative building and testing.
          </p>
        </div>

        {/* Before / After comparison */}
        <div className="grid grid-cols-11 gap-0 items-stretch">
          {/* Before card */}
          <div className="col-span-5 rounded-xl p-6 border-2 shadow-sm" style={{borderColor: '#d13212', backgroundColor: '#fef5f2'}}>
            <div className="flex items-center gap-2 mb-4">
              <span className="text-2xl">&#x1F6D1;</span>
              <span className="text-xl font-bold" style={{color: '#d13212'}}>Before &mdash; Manual Process</span>
            </div>
            <div className="space-y-3 text-base text-gray-700">
              <div className="flex items-start gap-2.5">
                <span className="font-bold mt-0.5" style={{color: '#d13212'}}>&#x2717;</span>
                <span>Manually configure credentials, CAPI controllers, and AWS roles</span>
              </div>
              <div className="flex items-start gap-2.5">
                <span className="font-bold mt-0.5" style={{color: '#d13212'}}>&#x2717;</span>
                <span>Follow multi-step provisioning docs with copy-paste commands</span>
              </div>
              <div className="flex items-start gap-2.5">
                <span className="font-bold mt-0.5" style={{color: '#d13212'}}>&#x2717;</span>
                <span>SSH into clusters to read logs and diagnose failures</span>
              </div>
              <div className="flex items-start gap-2.5">
                <span className="font-bold mt-0.5" style={{color: '#d13212'}}>&#x2717;</span>
                <span>Hand-delete security groups, ENIs, and VPC dependencies in order</span>
              </div>
              <div className="flex items-start gap-2.5">
                <span className="font-bold mt-0.5" style={{color: '#d13212'}}>&#x2717;</span>
                <span>Check AWS console for quota and resource usage</span>
              </div>
            </div>
          </div>

          {/* Arrow divider */}
          <div className="col-span-1 flex flex-col items-center justify-center">
            <div className="rounded-full w-10 h-10 flex items-center justify-center shadow-md" style={{background: 'linear-gradient(135deg, #232f3e 0%, #527fff 100%)'}}>
              <span className="text-white text-lg font-bold">&#x2192;</span>
            </div>
          </div>

          {/* After card */}
          <div className="col-span-5 rounded-xl p-6 border-2 shadow-sm" style={{borderColor: '#1a8f53', backgroundColor: '#f0faf4'}}>
            <div className="flex items-center gap-2 mb-4">
              <span className="text-2xl">&#x1F680;</span>
              <span className="text-xl font-bold" style={{color: '#1a8f53'}}>After &mdash; Automated Framework</span>
            </div>
            <div className="space-y-3 text-base text-gray-700">
              <div className="flex items-start gap-2.5">
                <span className="font-bold mt-0.5" style={{color: '#1a8f53'}}>&#x2713;</span>
                <span>Guided setup walks through configuration step by step</span>
              </div>
              <div className="flex items-start gap-2.5">
                <span className="font-bold mt-0.5" style={{color: '#1a8f53'}}>&#x2713;</span>
                <span>One-click provisioning with YAML preview and validation</span>
              </div>
              <div className="flex items-start gap-2.5">
                <span className="font-bold mt-0.5" style={{color: '#1a8f53'}}>&#x2713;</span>
                <span>AI agents monitor logs and diagnose failures in real time</span>
              </div>
              <div className="flex items-start gap-2.5">
                <span className="font-bold mt-0.5" style={{color: '#1a8f53'}}>&#x2713;</span>
                <span>Automated cleanup of SGs, ENIs, VPC endpoints in correct order</span>
              </div>
              <div className="flex items-start gap-2.5">
                <span className="font-bold mt-0.5" style={{color: '#1a8f53'}}>&#x2713;</span>
                <span>On-demand AWS quota and usage dashboard with cost tracking</span>
              </div>
            </div>
          </div>
        </div>

        {/* Metrics */}
        <div className="grid grid-cols-4 gap-4">
          <div className="rounded-xl p-5 text-center shadow-md" style={{background: 'linear-gradient(135deg, #527fff 0%, #3b5ee6 100%)'}}>
            <div className="text-3xl font-bold text-white">Time</div>
            <div className="text-xs text-white mt-1 opacity-80">Saved per cluster lifecycle vs manual steps</div>
          </div>
          <div className="rounded-xl p-5 text-center shadow-md" style={{background: 'linear-gradient(135deg, #ff9900 0%, #e88a00 100%)'}}>
            <div className="text-3xl font-bold text-white">$$$</div>
            <div className="text-xs text-white mt-1 opacity-80">Saved by preventing orphaned AWS resources</div>
          </div>
          <div className="rounded-xl p-5 text-center shadow-md" style={{background: 'linear-gradient(135deg, #1a8f53 0%, #15794a 100%)'}}>
            <div className="text-3xl font-bold text-white">12+</div>
            <div className="text-xs text-white mt-1 opacity-80">Failure patterns encoded from real incidents</div>
          </div>
          <div className="rounded-xl p-5 text-center shadow-md" style={{background: 'linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)'}}>
            <div className="text-3xl font-bold text-white">40+</div>
            <div className="text-xs text-white mt-1 opacity-80">Ansible playbooks automating manual steps</div>
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
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Claude API banner */}
        <div className="rounded-2xl p-5 text-center text-white" style={{background: 'linear-gradient(135deg, #da7756 0%, #c4593a 50%, #232f3e 100%)'}}>
          <p className="text-lg font-light leading-relaxed">
            The framework uses the <span className="font-bold">Claude API</span> for intelligent diagnosis
            and a <span className="font-bold">4-stage AI agent pipeline</span> that runs autonomously during
            every cluster operation.
          </p>
        </div>

        {/* Pipeline flow with connecting line */}
        <div className="relative">
          {/* Connecting line behind the cards */}
          <div className="absolute top-1/2 left-0 right-0 h-1 -translate-y-1/2 rounded-full" style={{background: 'linear-gradient(90deg, #527fff 0%, #ff9900 33%, #1a8f53 66%, #8b5cf6 100%)', zIndex: 0}}></div>
          <div className="relative flex items-stretch gap-4" style={{zIndex: 1}}>
            <div className="flex-1 rounded-xl p-5 text-center shadow-lg" style={{background: 'linear-gradient(135deg, #527fff 0%, #3b5ee6 100%)'}}>
              <div className="text-3xl font-bold text-white opacity-40 mb-1">1</div>
              <div className="text-lg font-bold text-white mb-2">Monitor</div>
              <p className="text-xs text-white opacity-80">Watches live logs in real time, pattern-matches against known issues database</p>
            </div>
            <div className="flex-1 rounded-xl p-5 text-center shadow-lg" style={{background: 'linear-gradient(135deg, #ff9900 0%, #e88a00 100%)'}}>
              <div className="text-3xl font-bold text-white opacity-40 mb-1">2</div>
              <div className="text-lg font-bold text-white mb-2">Diagnose</div>
              <p className="text-xs text-white opacity-80">Determines root cause using pattern matching + Claude API for unknown failures</p>
            </div>
            <div className="flex-1 rounded-xl p-5 text-center shadow-lg" style={{background: 'linear-gradient(135deg, #1a8f53 0%, #15794a 100%)'}}>
              <div className="text-3xl font-bold text-white opacity-40 mb-1">3</div>
              <div className="text-lg font-bold text-white mb-2">Remediate</div>
              <p className="text-xs text-white opacity-80">Executes targeted fixes &mdash; cleans ENIs, security groups, retries CF deletions</p>
            </div>
            <div className="flex-1 rounded-xl p-5 text-center shadow-lg" style={{background: 'linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)'}}>
              <div className="text-3xl font-bold text-white opacity-40 mb-1">4</div>
              <div className="text-lg font-bold text-white mb-2">Learn</div>
              <p className="text-xs text-white opacity-80">Records outcomes, adjusts confidence scores, improves future diagnoses</p>
            </div>
          </div>
        </div>

        {/* Details row */}
        <div className="grid grid-cols-2 gap-5">
          <div className="rounded-xl p-6 border-l-4 shadow-sm" style={{borderColor: '#da7756', backgroundColor: '#fef5f2'}}>
            <div className="flex items-center gap-3 mb-4">
              <div className="w-9 h-9 rounded-lg flex items-center justify-center text-white text-sm font-bold" style={{backgroundColor: '#da7756'}}>&#x2B23;</div>
              <h3 className="text-lg font-bold text-gray-900">Claude API Integration</h3>
            </div>
            <div className="space-y-3 text-sm text-gray-700">
              <div className="flex items-start gap-2.5">
                <span className="font-bold mt-0.5" style={{color: '#da7756'}}>&#x25B8;</span>
                <span>Analyzes unknown failure patterns that aren&apos;t in the knowledge base</span>
              </div>
              <div className="flex items-start gap-2.5">
                <span className="font-bold mt-0.5" style={{color: '#da7756'}}>&#x25B8;</span>
                <span>Suggests new remediation strategies with confidence scoring</span>
              </div>
              <div className="flex items-start gap-2.5">
                <span className="font-bold mt-0.5" style={{color: '#da7756'}}>&#x25B8;</span>
                <span>Powers the AI Assistant chat for interactive troubleshooting</span>
              </div>
              <div className="flex items-start gap-2.5">
                <span className="font-bold mt-0.5" style={{color: '#da7756'}}>&#x25B8;</span>
                <span>New patterns saved to pending_learnings.json for human review</span>
              </div>
            </div>
          </div>
          <div className="rounded-xl p-6 border-l-4 shadow-sm" style={{borderColor: '#1a8f53', backgroundColor: '#f0faf4'}}>
            <div className="flex items-center gap-3 mb-4">
              <div className="w-9 h-9 rounded-lg flex items-center justify-center text-white text-sm font-bold" style={{backgroundColor: '#1a8f53'}}>&#x2714;</div>
              <h3 className="text-lg font-bold text-gray-900">Safety Model</h3>
            </div>
            <div className="space-y-3 text-sm text-gray-700">
              <div className="flex items-start gap-2.5">
                <span className="font-bold mt-0.5" style={{color: '#1a8f53'}}>&#x25B8;</span>
                <span>Only known, approved remediations run automatically</span>
              </div>
              <div className="flex items-start gap-2.5">
                <span className="font-bold mt-0.5" style={{color: '#1a8f53'}}>&#x25B8;</span>
                <span>Claude-suggested fixes require human approval before activation</span>
              </div>
              <div className="flex items-start gap-2.5">
                <span className="font-bold mt-0.5" style={{color: '#1a8f53'}}>&#x25B8;</span>
                <span>Confidence thresholds prevent low-confidence actions (min 0.7)</span>
              </div>
              <div className="flex items-start gap-2.5">
                <span className="font-bold mt-0.5" style={{color: '#1a8f53'}}>&#x25B8;</span>
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
          <div className="px-4 py-2.5 text-sm font-semibold text-white flex items-center gap-2" style={{backgroundColor: '#232f3e'}}>
            <span style={{color: '#8b5cf6'}}>&#x2B24;</span> AI Assistant
          </div>
          <div className="p-5 space-y-4" style={{backgroundColor: '#fafafa'}}>
            {/* Conversation 1 */}
            <div className="flex justify-end">
              <div className="rounded-xl px-4 py-2.5 text-sm max-w-md text-white shadow-sm" style={{backgroundColor: '#527fff'}}>
                Why did my e2e-rosa-hcp cluster fail to delete?
              </div>
            </div>
            <div className="flex justify-start">
              <div className="rounded-xl px-4 py-3 text-sm max-w-lg bg-white border border-gray-200 text-gray-700 shadow-sm">
                The deletion failed because CloudFormation couldn&apos;t delete the VPC stack.
                ROSA created security groups outside of CloudFormation (e.g. *-vpce-private-router)
                that blocked VPC deletion. The AI agent has already cleaned up these resources
                and retried the stack deletion successfully.
              </div>
            </div>
            <div className="border-t border-gray-100 my-1"></div>
            {/* Conversation 2 */}
            <div className="flex justify-end">
              <div className="rounded-xl px-4 py-2.5 text-sm max-w-md text-white shadow-sm" style={{backgroundColor: '#527fff'}}>
                What&apos;s the current AWS quota usage for my account?
              </div>
            </div>
            <div className="flex justify-start">
              <div className="rounded-xl px-4 py-3 text-sm max-w-lg bg-white border border-gray-200 text-gray-700 shadow-sm">
                Your account is using 14 of 20 VPCs (70%), 3 of 5 Elastic IPs (60%), and 28 of 50 EC2 instances (56%).
                You have room for 2 more ROSA HCP clusters before hitting VPC limits.
              </div>
            </div>
            <div className="border-t border-gray-100 my-1"></div>
            {/* Conversation 3 */}
            <div className="flex justify-end">
              <div className="rounded-xl px-4 py-2.5 text-sm max-w-md text-white shadow-sm" style={{backgroundColor: '#527fff'}}>
                How do I provision a cluster with a custom CAPA image?
              </div>
            </div>
            <div className="flex justify-start">
              <div className="rounded-xl px-4 py-3 text-sm max-w-lg bg-white border border-gray-200 text-gray-700 shadow-sm">
                Use the Minikube environment &mdash; go to Custom Image, enter the PR number or image URL,
                and click Apply. The framework will patch the CAPA controller deployment with your image
                and you can provision a cluster to test your changes locally.
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
    subtitle: 'Over 2,000 automated tests across agents, backend, and frontend',
    content: (
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Test coverage */}
        <div className="rounded-2xl p-5 text-center text-white" style={{background: 'linear-gradient(135deg, #1a8f53 0%, #15803d 50%, #232f3e 100%)'}}>
          <p className="text-4xl font-bold mb-1">2,064 Automated Tests</p>
          <p className="text-base font-light opacity-90">
            Covering agents, backend API, and React components
          </p>
        </div>

        {/* Coverage breakdown */}
        <div className="grid grid-cols-3 gap-5">
          <div className="rounded-xl p-5 text-center shadow-lg" style={{background: 'linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)'}}>
            <div className="text-4xl font-bold text-white mb-1">252</div>
            <div className="text-sm font-semibold text-white">Agent Tests</div>
            <div className="mt-3 w-full rounded-full h-3 relative" style={{backgroundColor: 'rgba(255,255,255,0.25)'}}>
              <div className="h-3 rounded-full" style={{width: '97%', backgroundColor: 'rgba(255,255,255,0.9)'}}></div>
              <span className="absolute right-2 top-0 text-xs font-bold leading-3" style={{color: '#7c3aed'}}>97%</span>
            </div>
          </div>
          <div className="rounded-xl p-5 text-center shadow-lg" style={{background: 'linear-gradient(135deg, #ff9900 0%, #e88a00 100%)'}}>
            <div className="text-4xl font-bold text-white mb-1">1,090</div>
            <div className="text-sm font-semibold text-white">Backend Tests</div>
            <div className="mt-3 w-full rounded-full h-3 relative" style={{backgroundColor: 'rgba(255,255,255,0.25)'}}>
              <div className="h-3 rounded-full" style={{width: '87%', backgroundColor: 'rgba(255,255,255,0.9)'}}></div>
              <span className="absolute right-2 top-0 text-xs font-bold leading-3" style={{color: '#e88a00'}}>87%</span>
            </div>
          </div>
          <div className="rounded-xl p-5 text-center shadow-lg" style={{background: 'linear-gradient(135deg, #527fff 0%, #3b5ee6 100%)'}}>
            <div className="text-4xl font-bold text-white mb-1">722</div>
            <div className="text-sm font-semibold text-white">Frontend Tests</div>
            <div className="text-xs text-white opacity-70 mt-0.5">37 test suites</div>
            <div className="mt-2 w-full rounded-full h-3 relative" style={{backgroundColor: 'rgba(255,255,255,0.25)'}}>
              <div className="h-3 rounded-full" style={{width: '55%', backgroundColor: 'rgba(255,255,255,0.9)'}}></div>
              <span className="absolute right-2 top-0 text-xs font-bold leading-3" style={{color: '#3b5ee6'}}>55%</span>
            </div>
          </div>
        </div>

        {/* What's tested - color-coded columns */}
        <div className="grid grid-cols-3 gap-4">
          <div className="rounded-xl p-5 border-l-4 shadow-sm" style={{borderColor: '#8b5cf6', backgroundColor: '#f5f0ff'}}>
            <div className="text-sm font-bold text-gray-900 mb-3">Agent Coverage</div>
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <span className="font-bold" style={{color: '#8b5cf6'}}>&#x25B8;</span> Pipeline end-to-end flows
              </div>
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <span className="font-bold" style={{color: '#8b5cf6'}}>&#x25B8;</span> All 4 stages + learning
              </div>
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <span className="font-bold" style={{color: '#8b5cf6'}}>&#x25B8;</span> Confidence scoring + thresholds
              </div>
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <span className="font-bold" style={{color: '#8b5cf6'}}>&#x25B8;</span> Known issues pattern matching
              </div>
            </div>
          </div>
          <div className="rounded-xl p-5 border-l-4 shadow-sm" style={{borderColor: '#ff9900', backgroundColor: '#fff8ee'}}>
            <div className="text-sm font-bold text-gray-900 mb-3">Backend Coverage</div>
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <span className="font-bold" style={{color: '#ff9900'}}>&#x25B8;</span> All 40+ REST API endpoints
              </div>
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <span className="font-bold" style={{color: '#ff9900'}}>&#x25B8;</span> Credential + job management
              </div>
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <span className="font-bold" style={{color: '#ff9900'}}>&#x25B8;</span> WebSocket + async operations
              </div>
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <span className="font-bold" style={{color: '#ff9900'}}>&#x25B8;</span> Notification + email services
              </div>
            </div>
          </div>
          <div className="rounded-xl p-5 border-l-4 shadow-sm" style={{borderColor: '#527fff', backgroundColor: '#f0f4ff'}}>
            <div className="text-sm font-bold text-gray-900 mb-3">Frontend Coverage</div>
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <span className="font-bold" style={{color: '#527fff'}}>&#x25B8;</span> Every UI component + page
              </div>
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <span className="font-bold" style={{color: '#527fff'}}>&#x25B8;</span> Workflow builder interactions
              </div>
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <span className="font-bold" style={{color: '#527fff'}}>&#x25B8;</span> Dashboard + sidebar navigation
              </div>
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <span className="font-bold" style={{color: '#527fff'}}>&#x25B8;</span> Presentation mode + tour
              </div>
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

  // Slide: Deletion with AI Agent
  {
    id: 'deletion-agent',
    title: 'Cluster Deletion with AI Agent Remediation',
    subtitle: 'One-click deletion with autonomous monitoring, diagnosis, and cleanup of orphaned AWS resources',
    content: (
      <div className="space-y-4">
        <div className="flex items-center justify-center gap-6 text-xs text-gray-500">
          <span className="flex items-center gap-1"><span style={{color: '#d13212'}}>&#x25CF;</span> Delete Cluster</span>
          <span className="flex items-center gap-1"><span style={{color: '#ff9900'}}>&#x25CF;</span> Agent Monitors</span>
          <span className="flex items-center gap-1"><span style={{color: '#8b5cf6'}}>&#x25CF;</span> Auto-Remediate</span>
          <span className="flex items-center gap-1"><span style={{color: '#1a8f53'}}>&#x25CF;</span> Cleanup Complete</span>
        </div>
        <ScreenshotCarousel screenshots={deletionScreenshots} />
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
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Tagline */}
        <div className="text-center">
          <p className="text-3xl font-light leading-relaxed text-gray-200">
            One framework. Two environments. Full lifecycle automation.
          </p>
          <p className="text-base mt-3 text-gray-500">
            From provisioning to deletion, from failure detection to automated cleanup &mdash; built to save time and prevent costly mistakes.
          </p>
        </div>

        {/* Key takeaways - solid gradient boxes */}
        <div className="grid grid-cols-3 gap-5">
          <div className="rounded-xl p-6 text-center shadow-lg" style={{background: 'linear-gradient(135deg, #527fff 0%, #3b5ee6 100%)'}}>
            <div className="text-4xl font-bold text-white mb-1">40+</div>
            <div className="text-sm font-semibold text-white">Ansible Playbooks</div>
            <div className="text-xs text-white mt-1 opacity-70">Automating every manual step</div>
          </div>
          <div className="rounded-xl p-6 text-center shadow-lg" style={{background: 'linear-gradient(135deg, #1a8f53 0%, #15794a 100%)'}}>
            <div className="text-4xl font-bold text-white mb-1">2,064</div>
            <div className="text-sm font-semibold text-white">Automated Tests</div>
            <div className="text-xs text-white mt-1 opacity-70">Agents, backend, and frontend</div>
          </div>
          <div className="rounded-xl p-6 text-center shadow-lg" style={{background: 'linear-gradient(135deg, #ff9900 0%, #e88a00 100%)'}}>
            <div className="text-4xl font-bold text-white mb-1">$$$</div>
            <div className="text-sm font-semibold text-white">Cost Savings</div>
            <div className="text-xs text-white mt-1 opacity-70">Orphaned AWS resources caught automatically</div>
          </div>
        </div>

        {/* Capabilities summary - bigger cards */}
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center gap-3 rounded-xl p-4" style={{backgroundColor: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.1)'}}>
            <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0" style={{backgroundColor: 'rgba(82,127,255,0.2)'}}>
              <span className="text-sm font-bold" style={{color: '#527fff'}}>&#x2713;</span>
            </div>
            <span className="text-sm text-gray-300">MCE + Minikube environments with credential management</span>
          </div>
          <div className="flex items-center gap-3 rounded-xl p-4" style={{backgroundColor: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.1)'}}>
            <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0" style={{backgroundColor: 'rgba(14,165,233,0.2)'}}>
              <span className="text-sm font-bold" style={{color: '#0ea5e9'}}>&#x2713;</span>
            </div>
            <span className="text-sm text-gray-300">Drag-and-drop workflow builder with one-click execution</span>
          </div>
          <div className="flex items-center gap-3 rounded-xl p-4" style={{backgroundColor: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.1)'}}>
            <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0" style={{backgroundColor: 'rgba(139,92,246,0.2)'}}>
              <span className="text-sm font-bold" style={{color: '#8b5cf6'}}>&#x2713;</span>
            </div>
            <span className="text-sm text-gray-300">4-stage AI pipeline: Monitor, Diagnose, Remediate, Learn</span>
          </div>
          <div className="flex items-center gap-3 rounded-xl p-4" style={{backgroundColor: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.1)'}}>
            <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0" style={{backgroundColor: 'rgba(255,153,0,0.2)'}}>
              <span className="text-sm font-bold" style={{color: '#ff9900'}}>&#x2713;</span>
            </div>
            <span className="text-sm text-gray-300">On-demand dashboards with AWS quota and cost tracking</span>
          </div>
          <div className="flex items-center gap-3 rounded-xl p-4" style={{backgroundColor: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.1)'}}>
            <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0" style={{backgroundColor: 'rgba(218,119,86,0.2)'}}>
              <span className="text-sm font-bold" style={{color: '#da7756'}}>&#x2713;</span>
            </div>
            <span className="text-sm text-gray-300">Claude-powered AI assistant for interactive troubleshooting</span>
          </div>
          <div className="flex items-center gap-3 rounded-xl p-4" style={{backgroundColor: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.1)'}}>
            <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0" style={{backgroundColor: 'rgba(26,143,83,0.2)'}}>
              <span className="text-sm font-bold" style={{color: '#1a8f53'}}>&#x2713;</span>
            </div>
            <span className="text-sm text-gray-300">Live log streaming with Ansible syntax highlighting</span>
          </div>
        </div>

        {/* Bold closing statement */}
        <div className="text-center pt-2">
          <p className="text-xl font-semibold text-gray-300">
            Let me show you the live dashboard &#x2192;
          </p>
          <p className="text-xs text-gray-500 mt-2">Click <span className="font-semibold text-gray-400">Start Exploring</span> below</p>
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
