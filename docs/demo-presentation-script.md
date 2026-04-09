# CAPA Automation Framework — Demo Script

**URL:** http://localhost:3000/tour
**Navigation:** Arrow keys or click Next/Previous
**Duration:** ~8-10 minutes

---

## Slide 1: CAPA Automation Framework (Welcome)

> "This is the CAPA Automation Framework — an intelligent, end-to-end framework for provisioning, testing, and managing ROSA HCP clusters on Cluster API Provider AWS."

> "It replaces manual, error-prone workflows with automated playbooks, real-time dashboards, and AI-powered remediation."

> "At a high level, it gives you two environments — MCE and Minikube — plus AWS monitoring, GitHub and Jenkins integration, a drag-and-drop workflow builder, AI agents, and built-in notifications with diagnostic summaries."

**[Click Next]**

---

## Slide 2: Key Benefits

> "So why does this framework exist? Every cluster operation — from provisioning to cleanup — is automated, monitored by AI, and improved from run to run."

> "First, full visibility. One dashboard shows you cluster status, test results, AWS usage, Jenkins trends, and active operations across all environments."

> "Second, one-click workflows. You can chain verify, provision, test, and delete into reusable pipelines that run with a single click."

> "Third, automated diagnostics. No more SSH-ing into clusters to read logs. The AI pipeline detects issues, diagnoses root causes, and remediates failures automatically."

> "And fourth, automatic resource cleanup. The AI agents detect orphaned CloudFormation stacks, clean up security groups and VPC dependencies, and retry deletions — preventing costly orphaned AWS resources."

**[Click Next]**

---

## Slide 3: Architecture

> "Here's how the pieces fit together. Three layers, built with modern, production-ready technologies."

> "The UI layer is React with Tailwind CSS — four main views: the At a Glance Dashboard, MCE Environment, Minikube Environment, and the Workflow Builder."

> "The backend layer is Python with FastAPI and Ansible. It handles job management, credential handling, playbook execution, and the AI agent pipeline."

> "Everything connects through REST APIs and WebSocket for real-time updates. The backend talks to infrastructure through kubectl, the AWS CLI, and boto3."

> "At the bottom, infrastructure — OpenShift Hub clusters, ROSA HCP clusters, AWS services like CloudFormation and VPC, and Minikube for local development."

**[Click Next]**

---

## Slide 4: Operational Experience Built Into the Framework

> "This framework was designed to streamline and simplify working with ROSA HCP clusters. Failure patterns, remediation strategies, and confidence thresholds discovered through experience are encoded into the framework."

> "On the left, you can see what the manual process looked like — manually configuring credentials and controllers, following multi-step provisioning docs, SSH-ing into clusters to diagnose failures, hand-deleting security groups in the right order, and checking the AWS console for usage."

> "On the right, what the framework does now — guided setup walks you through configuration, one-click provisioning with YAML preview, AI agents monitor logs in real time, automated cleanup of dependencies in the correct order, and on-demand AWS quota dashboards."

> "The numbers speak for themselves: significant time saved per cluster lifecycle, cost savings by preventing orphaned AWS resources, over 12 failure patterns encoded from real incidents, and 40+ Ansible playbooks automating manual steps."

**[Click Next]**

---

## Slide 5: Claude API & AI Agents

> "The framework uses the Claude API for intelligent diagnosis and a 4-stage AI agent pipeline that runs autonomously during every cluster operation."

> "Stage 1, Monitor — watches live logs in real time and pattern-matches against a known issues database."

> "Stage 2, Diagnose — determines root cause using pattern matching, and falls back to the Claude API for unknown failures."

> "Stage 3, Remediate — executes targeted fixes. For example, cleaning ENIs, security groups, and retrying CloudFormation deletions."

> "Stage 4, Learn — records outcomes, adjusts confidence scores, and improves future diagnoses over time."

> "There's a strong safety model here. Only known, approved remediations run automatically. Anything Claude suggests requires human approval. Confidence thresholds prevent low-confidence actions, and the learning agent adjusts those scores based on actual success and failure history."

**[Click Next]**

---

## Slide 6: AI Assistant

> "In addition to the agent pipeline, there's a built-in Claude-powered chat assistant right inside the dashboard."

> "It's context-aware — it knows about your active clusters, recent operations, and credential status. You can ask it to debug failures, get guided workflows, or troubleshoot issues without ever leaving the UI."

> "Here's an example — I ask 'Why did my cluster fail to delete?' and it explains the CloudFormation VPC issue, the orphaned security groups, and confirms the AI agent already cleaned it up."

> "Or I can ask about AWS quota usage and get a specific breakdown with recommendations."

**[Click Next]**

---

## Slide 7: Test Coverage & Code Quality

> "The framework has over 2,000 automated tests covering agents, backend, and frontend."

> "252 agent tests at 97% coverage — testing the full pipeline, all 4 stages, confidence scoring, and thresholds."

> "1,090 backend tests at 87% coverage — all 40+ REST API endpoints, credential and job management, WebSocket and async operations."

> "722 frontend tests across 37 test suites at 55% coverage — every UI component, the workflow builder interactions, dashboard and sidebar navigation."

**[Click Next]**

---

## Slide 8: At a Glance Dashboard

> "This is the main dashboard — a unified view of everything. Cluster status, AWS quotas, Jenkins test result trends, GitHub activity, and recent tasks — all in one place."

*[Click through the screenshots to show different views]*

**[Click Next]**

---

## Slide 9: MCE Environment

> "The MCE environment is for full OpenShift Hub testing. From here you manage credentials, verify CAPI and CAPA controllers are running, provision ROSA HCP clusters, and delete them — all with live log streaming and AI agent monitoring."

*[Click through the screenshots to show different views]*

**[Click Next]**

---

## Slide 10: Minikube Environment

> "The Minikube environment is for fast local iteration. You can test custom CAPA provider images from open pull requests without needing a full Hub cluster. It's great for development and quick validation."

*[Click through the screenshots to show different views]*

**[Click Next]**

---

## Slide 11: Workflow Builder in Action

> "The Workflow Builder lets you drag and drop playbooks into multi-step pipelines. You can configure variables per step, set failure policies — stop, skip, or retry — and execute the entire workflow with one click."

> "For example, you could chain verify environment, configure credentials, provision a cluster, run tests, and delete — all as a single automated pipeline."

*[Click through the screenshots to show different views]*

**[Click Next]**

---

## Slide 12: Ready to Explore (Closing)

> "So to recap — one framework, two environments, full lifecycle automation."

> "40+ Ansible playbooks, over 2,000 automated tests, and real cost savings on every orphaned stack the AI agents catch."

> "It handles MCE and Minikube environments, drag-and-drop workflows, a 4-stage AI pipeline, real-time dashboards, a Claude-powered assistant, and live log streaming."

> "Let me show you the live dashboard."

**[Click Start Exploring]**

---

## Tips for Recording

- **Pace:** Pause 1-2 seconds between slides to let the transition animate
- **Screenshots:** On slides 8-11, click through 2-3 screenshots slowly so viewers can see the UI
- **Emphasis:** Slides 4 (Operational Experience) and 5 (AI Agents) are the key differentiators — spend more time here
- **Closing:** After clicking "Start Exploring", briefly navigate the live dashboard to show it's real
