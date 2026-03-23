# AI Agent Deletion Remediation

## Overview

The AI agent monitors ROSA HCP cluster deletions in real-time and automatically remediates issues that would otherwise leave orphaned AWS resources or stall the deletion pipeline. It reads Ansible playbook output line-by-line and feeds it through a detection-diagnosis-remediation pipeline. In the web UI it runs as a sidecar thread alongside the Ansible subprocess; in Jenkins/CLI mode it processes each line inline as part of `run-test-suite.py`.

## Execution Modes

The agent runs in two modes:

| Mode | How it starts | Flag |
|------|---------------|------|
| **Web UI** | Backend starts a sidecar thread alongside the Ansible subprocess | Automatic when deletion is triggered from UI |
| **CLI / Jenkins** | `run-test-suite.py` processes each stdout line through the monitoring agent | `--ai-agent` flag (added to Jenkinsfile provision + delete stages) |

In both modes, the agent reads the same Ansible output and uses the same pipeline:
```
Sidecar reads line -> MonitoringAgent detects issue -> DiagnosticAgent diagnoses
-> if confidence >= 0.7 -> RemediationAgent fixes it
```

## The Problems

### 1. CloudFormation DELETE_FAILED (ROSANetwork)

ROSA creates security groups (e.g., `*-vpce-private-router`) and VPC endpoints **outside** of CloudFormation's management. When CloudFormation tries to delete the VPC, it fails:

```
VPC has dependencies -> CloudFormation DELETE_FAILED -> ROSANetwork stuck with finalizer -> orphaned resources
```

### 2. CloudFormation DELETE_IN_PROGRESS with stuck VPC dependencies

Even during `DELETE_IN_PROGRESS`, the stack can get stuck if ROSA-created VPC endpoints and security groups aren't being cleaned up. The agent checks for blocking dependencies and only intervenes when resources are no longer transitioning.

### 3. ROSAControlPlane premature finalizer removal

Removing ROSAControlPlane finalizers before the ROSA cluster is fully gone causes the HCP control-plane-operator to keep running and recreate VPC resources, which then blocks the subsequent ROSANetwork/CloudFormation deletion.

## How the Agent Fixes It

### Detection

The monitoring agent watches Ansible retry loop output for `FAILED - RETRYING` patterns (defined in `agents/knowledge_base/known_issues.json`). Structured context markers (`#AGENT_CONTEXT`) emitted by the Ansible playbook provide the resource name and namespace.

### Diagnosis

#### ROSANetwork

The diagnostic agent checks the CloudFormation stack status:

| CF Stack Status | VPC Dependencies | Agent Action | Confidence |
|----------------|-----------------|--------------|------------|
| `DELETE_IN_PROGRESS` | None or still transitioning | Wait, no intervention | 0.5 |
| `DELETE_IN_PROGRESS` | Stuck blockers (SGs, endpoints) | Clean VPC deps, retry CF delete | 0.95 |
| `DELETE_FAILED` | — | Clean VPC deps, retry CF delete | 0.95 |
| `GONE` | — | Remove K8s finalizer | 0.9+ |

#### ROSAControlPlane

The diagnostic agent checks the ROSA cluster status via `rosa describe cluster`:

| ROSA Cluster Status | Agent Action | Confidence |
|--------------------|--------------|------------|
| `gone` (not found) | Remove K8s finalizer | 0.9+ |
| `uninstalling` | Wait — ROSA is still working | 0.5 |
| `ready` / `installing` / `error` / `unknown` | Wait — do NOT remove finalizers | 0.5 |

Only `gone` triggers finalizer removal. All other states wait. This prevents premature cleanup that would leave the HCP control-plane-operator running and recreating VPC resources.

### Remediation

**CloudFormation retry** (`_fix_retry_cloudformation_delete`):
1. Gets VPC ID from the CloudFormation stack
2. Deletes VPC endpoints first (they create `ela-attach` ENIs that can't be manually detached)
3. Waits ~20s for ENIs to release after endpoint deletion
4. Deletes orphaned ENIs (detach + delete)
5. Deletes non-default security groups (the ROSA-created ones)
6. Deletes orphaned subnets
7. Detaches/deletes internet gateways
8. Retries the CloudFormation stack deletion
9. Verifies stack transitioned to `DELETE_IN_PROGRESS`

**Finalizer removal** (`_fix_remove_finalizers`):
If a K8s resource is stuck after its backing resource is gone, the agent patches out the finalizer directly. For ROSANetwork this only happens after the CF stack is `GONE`. For ROSAControlPlane, only after `rosa describe cluster` returns "not found".

## Agent Summary in the UI

The frontend shows an agent summary after deletion completes:

- **Real fixes** (e.g., cleaned VPC endpoints, retried CF delete) — shown as "Agent auto-fixed N issue(s)"
- **Confirmations** (resource was already deleted) — shown as "Confirmed deleted" not "Removed finalizers"
- **Monitoring only** (no intervention needed) — shown as "Agent monitored N resource(s) — all deleted cleanly"

Intervention counting uses the correct dict keys from `record_intervention()`: `type` and `details.message` (not `action` and `result`).

To avoid a race condition where the frontend fetches stats before the last remediation finishes, the UI re-fetches agent stats with a 2-second delay when job completion is detected.

## Time Impact

The agent does **not** speed up successful deletions. Normal deletion timing:

| Phase | Duration |
|-------|----------|
| ROSAControlPlane deprovisioning | ~15 min |
| CloudFormation stack deletion | ~5-10 min |
| ROSARoleConfig IAM cleanup | ~2-5 min |
| **Total (successful)** | **~25-30 min** |

### When CloudFormation Fails

| Scenario | Without Agent | With Agent |
|----------|---------------|------------|
| CF hits `DELETE_FAILED` | Wait loop runs full 30 min, times out, `failed=1`, resources orphaned | Agent detects within ~60-120s, cleans deps, retries CF (~5-10 min extra), completes successfully |
| Post-deletion cleanup | Manual: 30+ min per batch of orphaned stacks | None needed - zero orphaned resources |
| Re-run required? | Yes, and it will fail the same way | No - deletion completes cleanly |

**The value is reliability, not speed.** The agent turns a failing deletion with orphaned resources into a successful deletion with zero cleanup needed.

## State Machine

Per-resource lifecycle:

```
DETECTED --> DIAGNOSING --> REMEDIATING --> RESOLVED
    ^            |                            |
    |            v                            v (after 120s cooldown)
    +-- (low confidence,                  DIAGNOSING (re-intervention)
         reset to DETECTED)                   |
                                              v
                                         RESOLVED (finalizer removed)
```

- Max 3 attempts per issue per resource
- 60s throttle between checks for DETECTED state
- 120s cooldown before re-intervention from RESOLVED state
- Low-confidence diagnoses (e.g., `DELETE_IN_PROGRESS`, cluster still `uninstalling`) reset to DETECTED for re-evaluation

## Timeout Chain

All timeout layers are aligned (inner < outer):

```
Ansible resource waits (RCP 20m + Network 30m + RoleConfig 10m + final checks)
  < Frontend polling (80 min)
    < Backend stuck-job checker (90 min)
      < Jenkins timeout (90 min)
```

## AWS Cleanup Order

When manually cleaning orphaned resources, delete in this order:

1. **VPC Endpoints** first - they create `ela-attach` ENIs that can't be manually detached
2. **Wait ~15-30s** for ENIs to release
3. **ENIs** - only deletable after endpoints are gone
4. **Security Groups** - only deletable after ENIs referencing them are gone
5. **Retry stack deletion** - CloudFormation handles remaining resources

If K8s ROSANetwork resource still exists, the CAPA controller will recreate VPC endpoints. Delete the K8s resource first.

## Key Files

| File | Role |
|------|------|
| `agents/monitoring_agent.py` | Pattern detection, per-resource state machine |
| `agents/diagnostic_agent.py` | CF stack status, ROSA cluster status, VPC dependency checking |
| `agents/remediation_agent.py` | VPC cleanup, CF retry, finalizer removal |
| `agents/base_agent.py` | Intervention recording (`record_intervention`) |
| `agents/knowledge_base/known_issues.json` | Pattern definitions (single source of truth) |
| `run-test-suite.py` | CLI/Jenkins sidecar (`--ai-agent` flag) |
| `ui/backend/app.py` | Web UI sidecar thread, agent stats API |
| `ui/frontend/.../RosaHcpClustersSection.jsx` | Agent summary display |
| `tasks/delete_rosa_hcp_resources.yml` | Ansible wait loops with `#AGENT_CONTEXT` markers |
| `Jenkinsfile` | CI pipeline with `--ai-agent` enabled |
