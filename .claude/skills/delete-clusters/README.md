# delete-clusters

Delete ROSA HCP test clusters safely with proper resource cleanup order.

## What this skill does

Deletes one or more ROSA HCP clusters using the Ansible deletion playbook, which ensures:
- **Correct deletion order**: ROSAControlPlane → ROSANetwork → ROSARoleConfig
- **Proper timeouts**: 20min (ControlPlane), 30min (Network/CloudFormation), 10min (Roles)
- **Safety checks**: Verifies AWS resources are gone before stripping finalizers
- **Force cleanup**: Removes stuck resources after timeouts
- **Full logging**: Emits sidecar logs for real-time progress monitoring

## Usage

### Delete a single cluster by prefix:
```bash
/delete-clusters we5
```

### Delete multiple clusters:
```bash
/delete-clusters we1 we2 we4 we5
```

### Delete with custom namespace:
```bash
/delete-clusters we5 --namespace custom-ns
```

### Delete without waiting (initiate only):
```bash
/delete-clusters we5 --no-wait
```

## Parameters

- **cluster_prefix** (required): Name prefix (e.g. "we5", "qe6"). Full cluster name becomes `{prefix}-rosa-hcp`
- **--namespace**: Custom CAPI namespace (default: `ns-rosa-hcp`)
- **--no-wait**: Initiate deletion without waiting for completion
- **--force-cleanup**: Enable force-cleanup of stuck resources (enabled by default)

## How it works

1. **Validates** cluster names and configuration
2. **Deletes** ROSAControlPlane first (20 min wait)
3. **Deletes** ROSANetwork (30 min wait for CloudFormation)
4. **Deletes** ROSARoleConfig (10 min wait for IAM cleanup)
5. **Force-cleans** any stuck resources (if timeouts occur)
6. **Reports** deletion status and summary

## Logs

Real-time progress is available via sidecar logs:
- `#AGENT_CONTEXT` lines show which resource is being deleted
- `FAILED - RETRYING` lines show wait status
- `CloudFormation stack` lines show CF deletion progress

## Example output

```
======================================
Deleting we5-rosa-hcp...
======================================

#AGENT_CONTEXT: resource_name=we5-rosa-hcp namespace=ns-rosa-hcp resource_type=rosacontrolplane
✓ ROSAControlPlane deletion initiated for we5-rosa-hcp
✓ ROSANetwork deletion initiated for we5-rosa-hcp-network
✓ ROSARoleConfig deletion initiated for we5-rosa-hcp-roles

FAILED - RETRYING: [localhost]: Wait for rosacontrolplane deletion to complete (119 retries left).
FAILED - RETRYING: [localhost]: Wait for cloudformation we5-rosa-hcp-rosa-network-stack deletion...

[After ~60 min total]
✅ DELETION COMPLETE! All resources cleaned up
```

## Safety notes

- CloudFormation stack deletion can be slow (up to 30 min) due to orphaned security groups
- ROSARoleConfig deletion requires IAM role cleanup (typically 5-10 min)
- Force cleanup only targets resources already in `deletionTimestamp` state
- For ROSANetwork, verifies CloudFormation stack is gone before stripping finalizers
- For ROSAControlPlane, verifies OCM cluster is gone before stripping finalizers

## See also

- `provision-clusters` — Create new ROSA HCP clusters
- `run-ui` — Launch the test automation UI to monitor provisioning/deletion
