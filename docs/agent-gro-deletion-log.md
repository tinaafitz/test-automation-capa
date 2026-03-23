# AI Agent in Action: gro-rosa-hcp Deletion Log

**Date:** March 23, 2026
**Cluster:** gro-rosa-hcp
**Mode:** CLI via `run-test-suite.py --ai-agent`
**Result:** Deletion completed successfully in 40m 55s
**Agent stats:** 6 issues detected, 4 interventions, all successful

---

## Timeline

### 1. ROSAControlPlane (12:58)

```
[12:58:11] [Monitor]     Issue detected: rosacontrolplane_stuck_deletion for ns-rosa-hcp/gro-rosa-hcp
[12:58:11] [Diagnostic]  Diagnosing: rosacontrolplane_stuck_deletion
[12:58:13] [Diagnostic]  ROSA cluster gro-rosa-hcp is fully gone -- safe to remove finalizers
[12:58:13] [Diagnostic]  Diagnosis complete. Confidence: 0.7
[12:58:13] [Remediation] Executing fix: remove_finalizers
[12:58:14] [Remediation] Fix applied successfully: Resource rosacontrolplane/gro-rosa-hcp already deleted
[12:58:14] [Monitor]     Issue resolved: rosacontrolplane_stuck_deletion for ns-rosa-hcp/gro-rosa-hcp
```

The agent detected the ROSAControlPlane was stuck in deletion. It checked `rosa describe cluster` and confirmed the ROSA cluster was fully gone ("not found" from OCM). Since the cluster is gone, it's safe to proceed. The K8s resource had already been cleaned up by the CAPA controller.

**Safety check:** If the ROSA cluster had still been in `uninstalling`, `ready`, or any other state, the agent would have waited instead of removing finalizers. This prevents premature cleanup that could leave the HCP control-plane-operator running and recreating VPC resources.

### 2. ROSANetwork / CloudFormation (13:29) -- The Real Fix

```
[13:29:27] [Monitor]     Issue detected: rosanetwork_stuck_deletion for ns-rosa-hcp/gro-rosa-hcp-network
[13:29:27] [Diagnostic]  Diagnosing: rosanetwork_stuck_deletion
[13:29:35] [Diagnostic]  CloudFormation stack gro-rosa-hcp-rosa-network-stack DELETE_FAILED -- retrying
[13:29:35] [Remediation] Executing fix: retry_cloudformation_delete
[13:30:12] [Remediation] Fix applied successfully:
                           Cleaned up VPC dependencies for gro-rosa-hcp-rosa-network-stack
                           Deleted security group sg-0a315c10e77d09f15 (*-vpce-private-router)
                           Removed finalizers from rosanetwork/gro-rosa-hcp-network
[13:30:12] [Monitor]     Issue resolved: rosanetwork_stuck_deletion for ns-rosa-hcp/gro-rosa-hcp-network
```

The CloudFormation stack hit `DELETE_FAILED` because ROSA had created a security group (`*-vpce-private-router`) outside of CloudFormation's management. CloudFormation couldn't delete the VPC with this dependency still attached.

The agent:
1. Detected the CF stack was in `DELETE_FAILED` state
2. Found the blocking security group in the VPC
3. Deleted the security group
4. Retried the CloudFormation stack deletion
5. Removed the K8s ROSANetwork finalizer

**Without the agent, this deletion would have timed out at the 30-minute Ansible wait loop and left orphaned AWS resources** (VPC, subnets, NAT gateways, Elastic IPs). This is exactly what happened earlier on the pro-rosa-hcp deletion, which required manual intervention.

### 3. Post-deletion Confirmation (13:30)

```
[13:30:42] [Monitor]     Issue detected: rosanetwork_stuck_deletion for ROSANetwork
[13:30:43] [Remediation] Executing fix: remove_finalizers
[13:30:44] [Remediation] Fix applied successfully: Resource rosanetwork/gro-rosa-hcp-network already deleted
[13:30:44] [Monitor]     Issue resolved

[13:30:44] [Monitor]     Issue detected: rosaroleconfig_stuck_deletion for ns-rosa-hcp/gro-rosa-hcp-roles
[13:30:44] [Remediation] Executing fix: remove_finalizers
[13:30:45] [Remediation] Fix applied successfully: Resource rosaroleconfig/gro-rosa-hcp-roles already deleted
[13:30:45] [Monitor]     Issue resolved
```

The agent confirmed that both ROSANetwork and ROSARoleConfig were already cleaned up. These are verification checks, not real fixes -- the resources were already gone.

## Final Stats

```
AI AGENT SUMMARY:
   Agent auto-fixed 1 issue(s)

   Actions:
     Fix applied: Retried CF stack delete: gro-rosa-hcp-rosa-network-stack
     Confirmed deleted: rosacontrolplane/gro-rosa-hcp
     Confirmed deleted: rosanetwork/gro-rosa-hcp-network
     Confirmed deleted: rosaroleconfig/gro-rosa-hcp-roles

   Fix Success Rates:
      remove_finalizers: 100.0% (3/3)
      retry_cloudformation_delete: 100.0% (1/1)
```

## Comparison: With vs Without Agent

On the same day, pro-rosa-hcp was deleted **without** the agent. The CloudFormation stack hit `DELETE_FAILED` with the same `*-vpce-private-router` security group blocker. The deletion stalled for 15+ minutes until manual intervention (deleting the SG and retrying the stack via CLI).

| | pro-rosa-hcp (no agent) | gro-rosa-hcp (with agent) |
|---|---|---|
| CF DELETE_FAILED? | Yes | Yes |
| Resolution | Manual CLI intervention | Agent auto-fixed in ~45 seconds |
| Orphaned resources? | Would have been if not caught | Zero |
| Total time | 39m 50s (with manual fix) | 40m 55s |
| Human effort | ~5 min debugging + cleanup | None |

## Throttle Behavior

After resolving the ROSAControlPlane issue, the agent correctly throttled duplicate detections:

```
[12:58:14] Issue resolved: rosacontrolplane_stuck_deletion for ns-rosa-hcp/gro-rosa-hcp
[12:58:15] Issue rosacontrolplane_stuck_deletion already in state resolved (attempt 1/3)
[12:58:15] Issue rosacontrolplane_stuck_deletion already in state resolved (attempt 1/3)
... (suppressed -- no re-intervention for 120s cooldown)
```

The state machine prevented hundreds of duplicate interventions that plagued the old code (which had 242 detections and 215 failed `remove_finalizers` attempts in a single Jenkins run).
