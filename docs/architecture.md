# CAPA Test Automation Platform -- System Architecture

**Cluster API Provider AWS (CAPA) -- End-to-End Test Automation with AI-Driven Self-Healing**

CAPA Test Automation is a spec-driven platform that automates the full lifecycle of ROSA HCP
clusters on AWS -- from provisioning through configuration, upgrade, and teardown. It combines
declarative cluster specifications, an extensible feature registry, and Ansible-based execution
with an AI agent framework that autonomously detects, diagnoses, and remediates infrastructure
failures in real time, reducing mean time to recovery and eliminating manual intervention.

---

## Quick Reference

```
+-------------------------------+-------------------------------+
|  PLATFORM METRICS             |  AI AGENT METRICS             |
+-------------------------------+-------------------------------+
|  CLI Subcommands ......... 8  |  Error Patterns ......... 12  |
|  Registered Features .... 35  |  Unit Tests ............ 258  |
|  Feature Specs .......... 26  |  Knowledge Base Files .... 3  |
|  Ansible Playbooks ...... 10  |  Domain Plugins ......... 1  |
|  Task Modules ........... 63  |  Agent Classes .......... 4  |
|  Test Suites ............ 10  |  Auto-Fix Capable ...... Yes |
|  Workflow Templates ...... 5  |  Confidence Learning ... Yes |
|  Cluster Profiles ........ 3  |  Dry-Run Support ...... Yes  |
+-------------------------------+-------------------------------+
```

---

## 1. Presentation Layer

Interfaces through which operators, CI systems, and dashboards interact with the platform.

```
+================================================================================+
|                            PRESENTATION LAYER                                  |
|                                                                                |
|  +------------------------+  +------------------------+  +------------------+  |
|  |       CAPA CLI          |  |     Web UI (React)      |  |  Jenkins / CI    |  |
|  |                         |  |                          |  |                  |  |
|  |  capa create            |  |  Cluster Dashboard       |  |  Jenkinsfile     |  |
|  |  capa delete            |  |  Job Monitor             |  |  capa test       |  |
|  |  capa upgrade           |  |  Workflow Designer        |  |  --ai-agent      |  |
|  |  capa apply             |  |  AWS Usage Dashboard     |  |                  |  |
|  |  capa test              |  |  AI Chat Assistant       |  |                  |  |
|  |  capa workflow          |  |  Trigger Manager         |  |                  |  |
|  |  capa trigger           |  |                          |  |                  |  |
|  |  capa minikube          |  |  WebSocket (live logs)   |  |                  |  |
|  +----------+--------------+  +----------+---------------+  +--------+---------+  |
|             |                            |                           |             |
+================================================================================+
              |                            |                           |
              | direct call                | REST + WebSocket          | subprocess
              v                            v                           v
```

---

## 2. Application Layer

Execution engines that interpret user intent, resolve plans, and orchestrate operations.

```
+================================================================================+
|                            APPLICATION LAYER                                   |
|                                                                                |
|  +---------------------------+       +--------------------------------------+  |
|  |    ExecutionEngine         |       |        FastAPI Backend               |  |
|  |    (capa CLI core)         |       |        (ui/backend/app.py)           |  |
|  |                            |       |                                      |  |
|  |  - Plan display            |       |  /api/clusters    CRUD operations    |  |
|  |  - Step-by-step execution  |       |  /api/jobs        Lifecycle mgmt     |  |
|  |  - Dry-run preview         |       |  /api/workflows   Run and export     |  |
|  |  - Failure handling        |       |  /api/triggers    Schedule / hooks   |  |
|  |  - History logging         |       |  /api/agents      AI configuration   |  |
|  |                            |       |  /api/aws/usage   Cost tracking      |  |
|  |  Modes:                    |       |  /api/webhooks    Trigger dispatch   |  |
|  |  - Synchronous (CLI)       |       |                                      |  |
|  |  - Background (triggers)   |       |  Async job execution                 |  |
|  |                            |       |  WebSocket streaming                 |  |
|  +------------+---------------+       |  Trigger scheduler (background)      |  |
|               |                       +------------------+-------------------+  |
|               |                                          |                      |
|               +------------------+-----------------------+                      |
|                                  |                                              |
|                                  v  (both use)                                  |
|  +----------------------------------------------------------------------+      |
|  |                       CORE SERVICES (Shared)                          |      |
|  |                                                                       |      |
|  |  +---------------------+  +--------------------+  +-----------------+ |      |
|  |  |  capa_core.py        |  | playbook_executor  |  | run-test-suite  | |      |
|  |  |                      |  |                    |  |   .py           | |      |
|  |  |  FeatureRegistry     |  | build_command()    |  | Suite runner    | |      |
|  |  |  Spec parser         |  | run_blocking()     |  | Progress report | |      |
|  |  |  Plan resolution     |  | Streaming runner   |  | Multi-format    | |      |
|  |  |  Validation engine   |  | Env-based creds    |  |   output        | |      |
|  |  |                      |  |   (never CLI args) |  | Agent hooks     | |      |
|  |  +----------+-----------+  +---------+----------+  +--------+--------+ |      |
|  +-------------|------------------------|-----------------------|----------+      |
|                |                        |                       |                |
+================================================================================+
                 |                        |                       |
                 | loads                  | executes              | monitors
                 v                        v                       v
```

---

## 3. Configuration and Schema Layer

Declarative definitions that drive all platform behavior -- no hardcoded logic.

```
+================================================================================+
|                      CONFIGURATION AND SCHEMA LAYER                            |
|                                                                                |
|  +------------------------+  +------------------------+  +------------------+  |
|  |   Feature Registry      |  |   Specs and Profiles    |  |   Test Suites    |  |
|  |   (schemas/)             |  |   (specs/)              |  |   (test-suites/) |  |
|  |                          |  |                          |  |                  |  |
|  |  feature-registry.yml    |  |  profiles/               |  |  10-configure    |  |
|  |  - 35 registered         |  |    default.yml           |  |  20-provision    |  |
|  |    features              |  |    ha-production.yml     |  |  25-upgrade-cp   |  |
|  |  - Variable mappings     |  |    private-encrypted     |  |  26-upgrade-mp   |  |
|  |  - Dependency graph      |  |                          |  |  30-delete       |  |
|  |  - Execution sequences   |  |  features/               |  |  40-enable-capi  |  |
|  |                          |  |    26 feature specs      |  |  41-disable-capi |  |
|  |  version-compat.yml      |  |                          |  |                  |  |
|  |  feature-matrix.yml      |  |  workflows/              |  |                  |  |
|  |                          |  |    5 workflow templates   |  |                  |  |
|  +------------------------+  +------------------------+  +------------------+  |
|                                                                                |
+================================================================================+
                                       |
                                       | ansible-playbook
                                       v
```

---

## 4. Ansible Execution Layer

Playbooks and task modules that interact with OpenShift, ROSA, and AWS infrastructure.

```
+================================================================================+
|                          ANSIBLE EXECUTION LAYER                               |
|                                                                                |
|  +----------------------+  +----------------------+  +----------------------+  |
|  |  Lifecycle            |  |  Configuration        |  |  Upgrades             |  |
|  |                       |  |                        |  |                       |  |
|  |  create_rosa_hcp      |  |  configure_mce         |  |  upgrade_control      |  |
|  |  delete_rosa_hcp      |  |  verify_capi           |  |    _plane             |  |
|  |  provision_minikube   |  |  enable_capi           |  |  upgrade_machine      |  |
|  +----------+------------+  +------------------------+  |    _pool              |  |
|             |                                            +----------------------+  |
|             | streams output                                                      |
|             v                                                                     |
|  +----------------------------------------------------------------------+        |
|  |  Task Modules (tasks/) -- 63 reusable modules                         |        |
|  |                                                                       |        |
|  |  - create_rosa_network.yml         - delete_rosa_hcp_resources.yml    |        |
|  |  - create_rosa_role_config.yml     - wait_for_rosa_control_plane.yml  |        |
|  |  - login_ocp.yml                   - update_capa_controller_*.yml     |        |
|  |                                                                       |        |
|  |  Instrumentation:                                                     |        |
|  |  - Emits #AGENT_CONTEXT markers for real-time AI monitoring           |        |
|  |  - Emits FAILED - RETRYING lines for pattern detection                |        |
|  +----------------------------------------------------------------------+        |
|                                                                                   |
+================================================================================+
                                       |
                                       | stdout + sidecar logs
                                       v
```

---

## 5. AI Agent Framework -- Self-Healing Pipeline

This is the platform's core differentiator: a four-stage autonomous pipeline that monitors
live Ansible output, detects known failure patterns, diagnoses root cause with confidence
scoring, and executes verified remediations -- all without human intervention. A learning
agent continuously refines detection accuracy based on observed outcomes.

```
+================================================================================+
|                                                                                |
|              AI AGENT FRAMEWORK -- SELF-HEALING PIPELINE                       |
|                                                                                |
|  VALUE: Autonomous failure recovery | Reduced MTTR | Continuous learning       |
|                                                                                |
|  +------------------------------------------------------------------+         |
|  |                                                                    |         |
|  |                    GENERIC FRAMEWORK (agents/)                     |         |
|  |                                                                    |         |
|  |    +-------------+     +---------------+     +-----------------+   |         |
|  |    |  Monitoring  | --> |  Diagnostic    | --> |  Remediation    |   |         |
|  |    |  Agent       |     |  Agent         |     |  Agent          |   |         |
|  |    |              |     |                |     |                 |   |         |
|  |    | - Stream     |     | - Root cause   |     | - Fix execution|   |         |
|  |    |   processing |     |   analysis     |     | - Dry-run mode |   |         |
|  |    | - State      |     | - Confidence   |     | - Success rate |   |         |
|  |    |   machine    |     |   scoring      |     |   tracking     |   |         |
|  |    | - Throttling |     | - Generic      |     |                |   |         |
|  |    | - Dedup      |     |   fallback     |     |                |   |         |
|  |    +-------------+     +---------------+     +--------+--------+   |         |
|  |                                                       |            |         |
|  |                                                       v            |         |
|  |                                              +-----------------+   |         |
|  |                                              |  Learning Agent  |   |         |
|  |                                              |                  |   |         |
|  |                                              | - Outcome track  |   |         |
|  |                                              | - Confidence +/- |   |         |
|  |                                              | - Pattern suggest|   |         |
|  |                                              +-----------------+   |         |
|  |                                                                    |         |
|  +------------------------------------------------------------------+         |
|       |                                                                        |
|       | subclass + override hooks                                              |
|       v                                                                        |
|  +------------------------------------------------------------------+         |
|  |                                                                    |         |
|  |    DOMAIN PLUGIN: ROSA HCP (agents/domains/rosa_hcp/)              |         |
|  |                                                                    |         |
|  |  +------------------+ +-------------------+ +-------------------+  |         |
|  |  | RosaHcp           | | RosaHcp            | | RosaHcp           |  |         |
|  |  |  MonitoringAgent  | |  DiagnosticAgent   | |  RemediationAgent |  |         |
|  |  |                   | |                     | |                   |  |         |
|  |  | - ROSANetwork     | | - CloudFormation   | | - Finalizer       |  |         |
|  |  |   resource detect | |   status check     | |   removal         |  |         |
|  |  | - Control plane   | | - ROSA cluster     | | - CF stack retry  |  |         |
|  |  |   state tracking  | |   health check     | | - VPC cleanup     |  |         |
|  |  | - Stale-issue     | | - VPC dependency   | | - Security group  |  |         |
|  |  |   filtering       | |   analysis         | |   remediation     |  |         |
|  |  |                   | | - CAPI/CAPA health | |                   |  |         |
|  |  +------------------+ +-------------------+ +-------------------+  |         |
|  |                                                                    |         |
|  |  +--------------------------------------------------------------+  |         |
|  |  |  Knowledge Base (knowledge_base/)                              |  |         |
|  |  |                                                                |  |         |
|  |  |  known_issues.json       12 error patterns with adaptive      |  |         |
|  |  |                          confidence scoring                   |  |         |
|  |  |  fix_strategies.json     Operator runbooks and remediation    |  |         |
|  |  |                          procedures                           |  |         |
|  |  |  remediation_outcomes    Historical results for continuous    |  |         |
|  |  |    .json                 learning (capped at 500 entries)     |  |         |
|  |  +--------------------------------------------------------------+  |         |
|  |                                                                    |         |
|  +------------------------------------------------------------------+         |
|                                                                                |
|  +------------------------------------------------------------------+         |
|  |                                                                    |         |
|  |    DOMAIN PLUGIN: [Extensible] (agents/domains/your_domain/)       |         |
|  |                                                                    |         |
|  |    Override hooks:                                                  |         |
|  |    - _diagnose_issue()                                              |         |
|  |    - _get_fix_method()                                              |         |
|  |    - _should_skip_stale_issue()                                     |         |
|  |    - _extract_waiting_for_resource()                                |         |
|  |                                                                    |         |
|  |    Provide: Domain-specific known_issues.json                       |         |
|  |    Reuse:   MonitoringAgent state machine, LearningAgent loop       |         |
|  |                                                                    |         |
|  +------------------------------------------------------------------+         |
|                                                                                |
+================================================================================+
                                       |
                                       | oc / rosa / aws CLI
                                       v
```

---

## 6. External Systems Layer

Cloud infrastructure and managed services that the platform provisions, configures, and monitors.

```
+================================================================================+
|                          EXTERNAL SYSTEMS LAYER                                |
|                                                                                |
|  +------------------------+  +------------------------+  +------------------+  |
|  |  OpenShift Hub Cluster  |  |  ROSA / OCM             |  |  AWS              |  |
|  |                          |  |                          |  |                  |  |
|  |  Kubernetes API (oc)    |  |  Cluster management     |  |  CloudFormation  |  |
|  |  CAPI/CAPA controllers  |  |  HCP provisioning       |  |  VPC / Subnets   |  |
|  |  MCE operator           |  |  OIDC configuration     |  |  IAM Roles       |  |
|  |  Custom resources:      |  |  Machine pool mgmt      |  |  Security Groups |  |
|  |  - ROSANetwork          |  |                          |  |  Route53         |  |
|  |  - ROSAControlPlane     |  |                          |  |  EC2 / ENI       |  |
|  |  - ROSARoleConfig       |  |                          |  |  NAT Gateways    |  |
|  +------------------------+  +------------------------+  +------------------+  |
|                                                                                |
+================================================================================+
```

---

## Data Flows

### Spec-Driven Cluster Lifecycle

The platform uses a declarative model: operators define desired state in YAML specs, and the
engine resolves those specs into an ordered execution plan based on the feature registry's
dependency graph.

```
                   DECLARATIVE SPEC-DRIVEN EXECUTION
    ====================================================================

    Spec YAML -----> FeatureRegistry -----> Plan Resolution -----> Steps
                      (var mapping)          (ordered deps)

                                                                     |
                                                    +----------------+--------+
                                                    |                         |
                                                    v                         v
                                            Ansible Playbook           oc patch (K8s)
                                                    |
                                                    v
                                          AI Agent Pipeline
                                            (if --ai-agent)
                                                    |
                                  +-----------------+-----------------+
                                  |                 |                 |
                                  v                 v                 v
                              DETECT           DIAGNOSE          REMEDIATE
                          (pattern match)   (root cause)      (auto-fix)
                                  |                 |                 |
                                  +-----------------+-----------------+
                                                    |
                                                    v
                                             LEARN + ADJUST
                                         (confidence scoring)
```

### Trigger-Driven Automation

Scheduled jobs, webhooks, and manual triggers feed into a unified workflow engine that
chains multi-step operations with configurable failure policies.

```
                   TRIGGER-DRIVEN WORKFLOW EXECUTION
    ====================================================================

    Schedule (cron) ----+
                        |
    Webhook (POST)  ----+----> TriggerScheduler ----> Workflow ----> Plan ----> Execute
                        |       (background)           (YAML)
    Manual fire     ----+


    Workflow step chaining with failure policies:

    step 1 (playbook) ----> step 2 (playbook) ----> step 3 (test suite)
         |                       |                        |
    on_failure: stop        on_failure: skip         on_failure: continue
```

---

## Key Architectural Decisions

| Decision | Rationale |
|---|---|
| Spec-driven, not imperative | Operators declare intent; the engine resolves execution order |
| Environment-based credentials | Secrets never appear in CLI arguments or logs |
| Plugin-based AI agents | New domains extend the framework without modifying core logic |
| Confidence-scored remediation | Automated fixes improve over time; low-confidence actions run in dry-run mode |
| Knowledge base with learning loop | Outcomes feed back to adjust pattern confidence, enabling continuous improvement |
| Ansible as execution substrate | Leverages existing Red Hat ecosystem tooling and operator expertise |
| Feature registry as single source of truth | One YAML file governs CLI, UI, CI, and test suites |

---

*CAPA Test Automation Platform -- Red Hat Advanced Cluster Management*
