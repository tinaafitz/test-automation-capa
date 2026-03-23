# AI Agent for CLI and Jenkins

## Overview

The AI agent monitors ROSA HCP cluster operations in real-time and automatically remediates issues that would otherwise leave orphaned AWS resources or stall the pipeline. In CLI and Jenkins mode, `run-test-suite.py` processes each Ansible output line inline through the agent pipeline:

```
Ansible stdout line -> MonitoringAgent detects issue -> DiagnosticAgent diagnoses
-> if confidence >= 0.7 -> RemediationAgent fixes it
```

## Enabling the Agent

### CLI

```bash
./run-test-suite.py 30-rosa-hcp-delete --format junit -vvv --ai-agent \
  -e name_prefix=my-cluster
```

Use `--ai-agent-dry-run` to see what the agent would do without actually making changes.

### Jenkins

The `--ai-agent` flag is passed in the Jenkinsfile for both provision and delete stages:

```groovy
./run-test-suite.py 30-rosa-hcp-delete --format junit -vvv --ai-agent \
  -e name_prefix="${NAME_PREFIX}" ...
```

The Jenkins delete timeout is set to 90 minutes to allow time for agent remediation.

## What the Agent Monitors

The agent watches for `FAILED - RETRYING` lines in Ansible output, matching patterns defined in `agents/knowledge_base/known_issues.json`:

| Issue Type | Trigger | Auto-fix |
|-----------|---------|----------|
| `rosacontrolplane_stuck_deletion` | RETRYING on ROSAControlPlane deletion | Yes |
| `rosanetwork_stuck_deletion` | RETRYING on ROSANetwork deletion | Yes |
| `rosaroleconfig_stuck_deletion` | RETRYING on ROSARoleConfig deletion | Yes |
| `api_rate_limit` | HTTP 429 / throttling errors | Yes (backoff) |
| `cloudformation_deletion_failure` | CF delete/rollback failure | No (logged) |
| `networking_configuration_error` | Subnet/VPC not found | No (logged) |

## How It Fixes Deletions

### ROSAControlPlane

The agent checks the ROSA cluster status via `rosa describe cluster`:

| ROSA Status | Agent Action |
|------------|--------------|
| `gone` (not found) | Safe to remove finalizers |
| `uninstalling` | Wait -- ROSA is still working |
| `ready` / `installing` / `error` | Wait -- do NOT remove finalizers |

Only `gone` triggers finalizer removal. Removing finalizers while the cluster is still `uninstalling` would leave the HCP control-plane-operator running, which recreates VPC resources and blocks CloudFormation deletion downstream.

### ROSANetwork / CloudFormation

The agent checks the CloudFormation stack status:

| CF Status | Agent Action |
|----------|--------------|
| `DELETE_IN_PROGRESS` (no stuck deps) | Wait |
| `DELETE_IN_PROGRESS` (stuck VPC deps) | Clean deps, retry CF delete |
| `DELETE_FAILED` | Clean deps, retry CF delete |
| `GONE` | Remove K8s finalizer |

**CloudFormation retry** cleans up in this order:
1. Delete VPC endpoints (they create ENIs that can't be manually detached)
2. Wait ~20s for ENIs to release
3. Delete orphaned ENIs
4. Delete non-default security groups (e.g., `*-vpce-private-router`)
5. Delete orphaned subnets
6. Detach/delete internet gateways
7. Retry CloudFormation stack deletion

### ROSARoleConfig

Standard finalizer removal when the resource is stuck. IAM roles are cleaned up by the CAPA controller.

## Agent Output

During execution, agent activity appears inline with Ansible output:

```
FAILED - RETRYING: [localhost]: Wait for ROSANetwork deletion to complete (58 retries left)
[13:29:27] [Monitor]     Issue detected: rosanetwork_stuck_deletion
[13:29:35] [Diagnostic]  CloudFormation stack DELETE_FAILED -- retrying
[13:29:35] [Remediation] Executing fix: retry_cloudformation_delete
[13:30:12] [Remediation] Fix applied successfully:
                           Cleaned up VPC dependencies
                           Deleted security group sg-0a315c10e77d09f15 (*-vpce-private-router)
[13:30:12] [Monitor]     Issue resolved
```

### End-of-Run Summary

After the test suite completes, the agent prints a summary:

**When the agent fixed something:**
```
AI AGENT SUMMARY:
   Agent auto-fixed 1 issue(s)

   Actions:
     ✓ Retried CF stack delete: my-cluster-rosa-network-stack
     ✓ Confirmed deleted: rosacontrolplane/my-cluster
     ✓ Confirmed deleted: rosaroleconfig/my-cluster-roles

   Fix Success Rates:
      remove_finalizers: 100.0% (2/2)
      retry_cloudformation_delete: 100.0% (1/1)
```

**When the agent monitored but no fixes were needed:**
```
AI AGENT SUMMARY:
   Agent monitored 3 resource(s) — all deleted cleanly
```

**Clean run with no issues:**
```
AI AGENT SUMMARY:
   No issues detected — clean run
```

With `-vvv` verbosity, tracked issue states are also printed:

```
   Tracked Issues:
     rosacontrolplane_stuck_deletion:ns-rosa-hcp/my-cluster: resolved (1 attempt(s))
     rosanetwork_stuck_deletion:ns-rosa-hcp/my-cluster-network: resolved (1 attempt(s))
```

## Structured Context

Ansible playbooks emit `#AGENT_CONTEXT` markers so the agent knows which resource it's operating on:

```yaml
- name: Emit agent context for ROSANetwork deletion wait
  shell: |
    echo "#AGENT_CONTEXT: resource_name={{ network_name }} namespace={{ namespace }} resource_type=rosanetwork"
```

This gives the agent the correct resource name and namespace instead of having to parse it from task names (which is unreliable).

## State Machine

Each resource gets its own tracked issue with this lifecycle:

```
DETECTED --> DIAGNOSING --> REMEDIATING --> RESOLVED
    ^            |                            |
    |            v                            v (after 120s cooldown)
    +-- (low confidence,                  DIAGNOSING (re-intervention)
         reset to DETECTED)                   |
                                              v
                                         RESOLVED
```

- Max 3 attempts per issue per resource
- 60s throttle between rechecks
- 120s cooldown before re-intervention from RESOLVED state
- Low-confidence diagnoses (cluster still `uninstalling`, CF still `DELETE_IN_PROGRESS`) do not trigger remediation

## Timeout Chain

```
Ansible resource waits (RCP 20m + Network 30m + RoleConfig 10m)
  < Ansible fallback timeout (40 min)
    < Jenkins timeout (90 min)
```

## Key Files

| File | Role |
|------|------|
| `run-test-suite.py` | Agent initialization, line processing, summary output |
| `agents/monitoring_agent.py` | Pattern detection, per-resource state machine |
| `agents/diagnostic_agent.py` | CF stack status, ROSA cluster status, VPC dependency checks |
| `agents/remediation_agent.py` | VPC cleanup, CF retry, finalizer removal |
| `agents/knowledge_base/known_issues.json` | Pattern definitions |
| `tasks/delete_rosa_hcp_resources.yml` | Ansible wait loops with `#AGENT_CONTEXT` markers |
| `Jenkinsfile` | CI pipeline with `--ai-agent` enabled, 90 min timeout |

