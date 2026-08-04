# Instance Profile Leak Investigation — cmb-rosa-hcp

**Date discovered**: 2026-07-29  
**Severity**: Critical (998/1000 AWS account limit reached)  
**Status**: Instance profiles cleaned up. Orphaned cluster + AWS resources pending cleanup. Upstream bug not yet filed.

---

## Summary

During provisioning of the `cmb-rosa-hcp` cluster (4.22.3, stable channel), the ROSA service created **996 orphaned IAM instance profiles** in ~72 minutes. The profiles were never garbage-collected, bringing the AWS account to 998/1000 — 2 away from blocking all future cluster provisioning.

## Timeline

| Time (UTC) | Event |
|---|---|
| 2026-07-28 05:11:52 | cmb IAM roles created (11 roles with `cmb-` prefix) |
| 2026-07-28 05:12:12 | CloudFormation stack `cmb-rosa-hcp-rosa-network-stack` created |
| 2026-07-28 05:15:19 | OCM cluster `cmb-rosa-hcp` created (ID: `2rqupp2710e75t4v623oekdlnjkml5u4`) |
| 2026-07-27 19:17:37 | First `worker-preflight` instance profile created |
| 2026-07-27 20:29:32 | Last `worker-preflight` instance profile created (996 total in ~72 min) |
| 2026-07-29 ~15:00 | Discovered during routine AWS resource check — 998 instance profiles |
| 2026-07-29 ~15:05 | Bulk deleted all 996 orphaned profiles → count back to 2 |

## Root Cause

The cluster got stuck in `waiting` state due to an OIDC token validation failure:

```
InvalidIdentityToken: The web identity token provided could not be validated.
STS AssumeRoleWithWebIdentity failed for operator role:
  cmb-openshift-ingress-operator-cloud-credentials
```

While stuck, the ROSA service's reconciliation loop created a **new `worker-preflight` instance profile on every iteration** — approximately one every 4-5 seconds. Over 72 minutes, this produced 996 empty (no attached roles) instance profiles, all following the naming pattern:

```
rosa-service-managed-staging-<uuid>-cmb-worker-preflight
```

**The ROSA service never cleans up these preflight instance profiles**, whether the provisioning succeeds or fails. This is an upstream bug.

## Evidence

### Instance Profile Pattern

- **Count**: 996
- **All empty**: Zero attached roles on every profile
- **Creation rate**: ~1 every 4.3 seconds
- **Earliest**: `rosa-service-managed-staging-2rqm1k72n3lgejqi0l7uh3vj41kqti04-cmb-worker-preflight` (2026-07-27T19:17:37Z)
- **Latest**: `rosa-service-managed-staging-2rqn3aq3v0nk1a5u89thd3pht9ebe0gb-cmb-worker-preflight` (2026-07-27T20:29:32Z)

### Cluster State at Discovery

- **OCM state**: `waiting` (stuck since 2026-07-28T05:15:19Z)
- **K8s CRs**: All deleted (ROSAControlPlane, Cluster, ROSANetwork — not found in ns-rosa-hcp)
- **OCM cluster**: Still exists with ID `2rqupp2710e75t4v623oekdlnjkml5u4`
- **OIDC**: Managed, endpoint `2rold16drh87dgeo0uurahq2iqouarjr`

### Orphaned AWS Resources (still present)

| Resource | ID/Name |
|---|---|
| CloudFormation stack | `cmb-rosa-hcp-rosa-network-stack` (CREATE_COMPLETE) |
| VPC | `vpc-05dd95a535b21bcd5` (10.0.0.0/16) |
| NAT Gateways | `nat-0d046280d690a5fcf`, `nat-06d780b15955f27f6` |
| Elastic IPs | `eipalloc-0fe60a1588eab1925`, `eipalloc-091bf13097cf59b68` |
| Subnets | `subnet-0974b6e7e3f511721`, `subnet-0f14bb0f4a9948bb8`, `subnet-04d23d284b11e6a69`, `subnet-0246503848fac8f01` |
| IAM Roles (11) | `cmb-HCP-ROSA-Installer-Role`, `cmb-HCP-ROSA-Support-Role`, `cmb-HCP-ROSA-Worker-Role`, `cmb-kube-system-capa-controller-manager`, `cmb-kube-system-control-plane-operator`, `cmb-kube-system-kms-provider`, `cmb-kube-system-kube-controller-manager`, `cmb-openshift-cloud-network-config-controller-cloud-credentials`, `cmb-openshift-cluster-csi-drivers-ebs-cloud-credentials`, `cmb-openshift-image-registry-installer-cloud-credentials`, `cmb-openshift-ingress-operator-cloud-credentials` |
| Instance Profiles | **996 deleted** (2026-07-29) |

### OCM Cluster Details

```
Name:           cmb-rosa-hcp
ID:             2rqupp2710e75t4v623oekdlnjkml5u4
Version:        4.22.3
Channel Group:  stable
Region:         us-west-2
State:          waiting
AWS Account:    471112697682
OIDC:           https://oidc.os1.devshift.org/2rold16drh87dgeo0uurahq2iqouarjr (Managed)
Details Page:   https://console.dev.redhat.com/openshift/details/s/3H7OcNRxWHDwTDXr5C4jepXMwCg
```

## The Bug

The ROSA service (OCM backend) creates a new `rosa-service-managed-staging-<uuid>-<cluster>-worker-preflight` IAM instance profile on **every control plane reconciliation attempt**. These profiles:

1. Are created with unique UUIDs each time (never reused)
2. Have no IAM roles attached (empty)
3. Are never deleted — not on success, not on failure, not on cluster deletion
4. Accumulate silently until the AWS account hits the 1,000 instance profile limit
5. At that point, **all** cluster provisioning in the account fails with `LimitExceeded`

### Impact

- A single stuck cluster can exhaust the entire account's instance profile quota
- No monitoring or alerting exists for this — it's a silent time bomb
- The AWS default limit of 1,000 instance profiles is not adjustable via standard quota increase

## Cleanup Performed

```bash
# Verified all profiles were empty (no attached roles)
aws iam list-instance-profiles \
  --query 'InstanceProfiles[?contains(InstanceProfileName, `cmb-worker-preflight`)].[InstanceProfileName,Roles]' \
  --output json | python3 -c "
import json, sys
data = json.load(sys.stdin)
has_roles = sum(1 for p in data if p[1])
no_roles = sum(1 for p in data if not p[1])
print(f'With roles: {has_roles}, Empty: {no_roles}')
"
# Output: With roles: 0, Empty: 996

# Bulk deleted all 996 orphaned profiles
aws iam list-instance-profiles \
  --query 'InstanceProfiles[?contains(InstanceProfileName, `cmb-worker-preflight`)].InstanceProfileName' \
  --output text | tr '\t' '\n' | xargs -P10 -I{} aws iam delete-instance-profile --instance-profile-name {}

# Result: 998 → 2 instance profiles
```

## Remaining Cleanup TODO

- [ ] Delete OCM cluster: `rosa delete cluster --cluster=2rqupp2710e75t4v623oekdlnjkml5u4`
- [ ] Delete CloudFormation stack: `aws cloudformation delete-stack --stack-name cmb-rosa-hcp-rosa-network-stack`
- [ ] Delete 11 cmb IAM roles (detach policies first)
- [ ] Verify VPC, NAT gateways, EIPs cleaned up after CF stack deletion

## Recommendations

1. **File upstream bug** with ROSA/OCM team — preflight instance profiles must be garbage-collected
2. **Add instance profile monitoring** to our AWS resource usage checks — alert when count exceeds 100
3. **Add detection to the agent knowledge base** — pattern match `LimitExceeded.*instance.profile` (done: `instance_profile_leak` in known_issues.json)
4. **Consider periodic sweep** — cron job to delete `*-worker-preflight` profiles with no attached roles older than 24h
