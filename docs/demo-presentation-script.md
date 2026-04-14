# CAPA Automation Framework — Demo Script

**URL:** http://localhost:3000/tour
**Navigation:** Arrow keys or click Next/Previous
**Duration:** ~10-12 minutes

---

## Slide 1: CAPA Automation Framework (Welcome)

> "This is the CAPA Automation Framework — an intelligent, end-to-end framework for provisioning, testing, and managing ROSA HCP clusters on Cluster API Provider AWS."

> "It replaces manual, error-prone workflows with automated playbooks, real-time dashboards, and AI-powered remediation."

> "At a high level, it gives you two environments — MCE and Minikube — plus AWS monitoring, GitHub and Jenkins integration, a drag-and-drop workflow builder, AI agents, and built-in notifications with diagnostic summaries."

> "And look at the numbers — 40+ Ansible playbooks, over 2,000 automated tests, a 4-stage AI agent pipeline, and 12+ failure patterns encoded from real incidents."

**[Click Next]**

---

## Slide 2: Key Benefits

> "So why does this framework exist? Every cluster operation — from provisioning to cleanup — is automated, monitored by AI, and improved from run to run."

> "First, full visibility. A single pane of glass — centralized logging, previous task logs always accessible, and real-time status across both environments simultaneously."

> "Second, one-click workflows. 30-second environment setup, run tests in MCE and Minikube at the same time, and Minikube testing transfers to MCE when production-ready."

> "Third, automated diagnostics. Early bug detection before failures cascade, learned knowledge shared across runs, and failure-only notifications — no noise."

> "And fourth, automatic resource cleanup. Orphaned resource remediation that saves real AWS costs, AI agents that learn and improve from every cleanup, and full dependency chain cleanup in the correct order."

**[Click Next]**

---

## Slide 3: Architecture

> "Here's how the pieces fit together. Three layers, built with modern, production-ready technologies."

> "The UI layer is React with Tailwind CSS — five main views: the Dashboard, MCE Environment, Minikube, Workflow Builder, and the AI Assistant."

> "The backend layer is Python with FastAPI and Ansible. It handles the FastAPI server for job management and credentials, the Ansible Runner for 40+ playbooks, the AI Agent Pipeline, and the Notification service for email and Slack with AI summaries."

> "Everything connects through REST APIs and WebSocket for real-time updates. The backend talks to infrastructure through kubectl, the AWS CLI, and boto3."

> "At the bottom, infrastructure — OpenShift Hub with MCE and CAPI/CAPA controllers, ROSA HCP clusters, AWS services like CloudFormation, VPC, IAM, and S3, and Minikube for local dev and PR image testing."

**[Click Next]**

---

## Slide 4: Operational Experience Built Into the Framework

> "This framework was designed to streamline and simplify working with ROSA HCP clusters. Failure patterns, remediation strategies, and confidence thresholds discovered through experience are encoded into the framework."

> "On the left, the manual process — manually configuring credentials and controllers, following multi-step provisioning docs with copy-paste commands, SSH-ing into clusters to diagnose failures, hand-deleting security groups and VPC dependencies in order, and checking the AWS console for quota."

> "On the right, what the framework does — guided setup walks you through configuration step by step, one-click provisioning with YAML preview and validation, AI agents monitor logs and diagnose failures in real time, automated cleanup of SGs, ENIs, and VPC endpoints in the correct order, and on-demand AWS quota and usage dashboards."

> "The numbers speak for themselves: significant time saved per cluster lifecycle, real cost savings by preventing orphaned AWS resources, over 12 failure patterns encoded from real incidents, and 40+ Ansible playbooks automating every manual step."

**[Click Next]**

---

## Slide 5: Claude API & AI Agents

> "The framework uses the Claude API for intelligent diagnosis and a 4-stage AI agent pipeline that runs autonomously during every cluster operation."

> "Stage 1, Monitor — watches live logs in real time and pattern-matches against a known issues database."

> "Stage 2, Diagnose — determines root cause using pattern matching, and falls back to the Claude API for unknown failures."

> "Stage 3, Remediate — executes targeted fixes. For example, cleaning ENIs, security groups, and retrying CloudFormation deletions."

> "Stage 4, Learn — records outcomes, adjusts confidence scores, and improves future diagnoses over time."

> "There's a strong safety model here. Only known, approved remediations run automatically. Anything Claude suggests requires human approval. Confidence thresholds prevent low-confidence actions — minimum 0.7 — and the learning agent auto-adjusts confidence based on actual success and failure history."

**[Click Next]**

---

## Slide 6: AI Assistant

> "In addition to the agent pipeline, there's a built-in Claude-powered chat assistant right inside the dashboard."

> "It's context-aware — it knows about your active clusters, recent operations, and credential status. You can ask it to debug failures, get guided workflows, or troubleshoot issues without ever leaving the UI."

> "Here are three examples — I ask 'Why did my cluster fail to delete?' and it explains the CloudFormation VPC issue, the orphaned security groups, and confirms the AI agent already cleaned it up."

> "Or I can ask about AWS quota usage and get a specific breakdown with recommendations."

> "And I can ask 'How do I provision a cluster with a custom CAPA image?' and it walks me through the Minikube environment workflow."

**[Click Next]**

---

## Slide 7: Test Coverage & Code Quality

> "The framework has over 2,000 automated tests covering agents, backend, and frontend."

> "252 agent tests at 97% coverage — testing the full pipeline, all 4 stages, confidence scoring, thresholds, and known issues pattern matching."

> "1,090 backend tests at 87% coverage — all 40+ REST API endpoints, credential and job management, WebSocket and async operations, and notification services."

> "722 frontend tests across 37 test suites at 55% coverage — every UI component and page, workflow builder interactions, dashboard and sidebar navigation, and the presentation mode."

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

> "Here I'm walking through a real workflow — starting with an empty canvas, adding Verify, Configure, and Provision steps, configuring per-step variables, and then running the entire pipeline. You can see the live output streaming as each step completes."

> "At the end, all three steps are green — the cluster is fully provisioned and running."

*[Click through the 10-step carousel]*

**[Click Next]**

---

## Slide 12: Cluster Deletion with AI Agent Remediation

> "Now let's see the other side — deleting a cluster with the AI agent watching."

> "I click delete on lol-rosa-hcp, confirm the deletion, and the playbook starts running with the AI agent in Monitoring mode."

> "The agent tracks the ROSAControlPlane as it uninstalls, monitors the ROSANetwork and CloudFormation stack deletion, and when it detects issues — orphaned security groups blocking the VPC stack — it automatically cleans up the dependencies."

> "At the end, the agent summary shows 3 resources monitored, 3 issues auto-fixed. You can expand the detail view to see the full timeline — every check, every fix, every status transition."

> "This is what used to take hours of manual debugging and cleanup."

*[Click through the 7-step carousel]*

**[Click Next]**

---

## Slide 13: Ready to Explore (Closing)

> "So to recap — one framework, two environments, full lifecycle automation."

> "40+ Ansible playbooks, over 2,000 automated tests, and real cost savings on every orphaned stack the AI agents catch."

> "It handles MCE and Minikube environments, drag-and-drop workflows, a 4-stage AI pipeline, on-demand dashboards, a Claude-powered assistant, and live log streaming."

> "Let me show you the live dashboard."

**[Click Start Exploring]**

---

## Tips for Recording

- **Pace:** Pause 1-2 seconds between slides to let the transition animate
- **Screenshots:** On slides 8-10, click through 2-3 screenshots slowly so viewers can see the UI
- **Carousels:** On slides 11-12, click through all steps in the carousel — these tell the full story
- **Emphasis:** Slides 4 (Operational Experience), 5 (AI Agents), and 12 (Deletion with Agent) are the key differentiators — spend more time here
- **Closing:** After clicking "Start Exploring", briefly navigate the live dashboard to show it's real
