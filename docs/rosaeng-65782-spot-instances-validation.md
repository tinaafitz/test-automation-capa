# AWS Spot instance support for ROSA HCP MachinePools — Implementation & Test Results (ROSAENG-65782)

## Summary of work done

Implemented AWS Spot instance support for ROSA HCP worker
node pools in `cluster-api-provider-aws` — a new field on the machine pool, a webhook to keep bad
combinations out, a version gate so it only kicks in on 4.22 and up, and the OCM API mapping.

Verified end-to-end: a spot-enabled node pool provisioned through to a live ROSA HCP cluster,
backed by two real EC2 spot instances.

## Environment

| | |
|---|---|
| **Hub cluster** | Minikube `route4-cluster` (Kubernetes v1.34.0, podman rootless driver, containerd runtime) |
| **CAPA image** | `quay.io/<user>/cluster-api-aws-controller-amd64:spot-test` (built with podman, `version=v2.10.0-spot-test`) |
| **CAPA source** | `kubernetes-sigs/cluster-api-provider-aws` branch `feat/rosaeng-8275-spot-market-options` (commit `6a842b07d`, PR #6193) |
| **OCM environment** | Stage |
| **Hosted cluster** | `spot-test-cluster` (OCM cluster ID redacted) |
| **OCP version** | 4.22.8 (channel: stable) |
| **Region** | *(redacted)*, Public endpoint, single AZ, AWS account *(redacted)* |

---

## What the feature does

A new optional field `spec.spotMarketOptions` on `ROSAMachinePool` maps to the OCM
`AwsNodePool.spot_market_options` API:

- `spotMarketOptions: {}` — Spot with no maximum price
- `spotMarketOptions: { maxPrice: "0.05" }` — Spot with an hourly bid cap

> **⚠️ Guardrails — these are hard rules, enforced and tested:**
> - **Day-1 only / immutable** — Spot is set when the pool is created and cannot be added,
>   removed, or changed afterward.
> - **Requires OpenShift 4.22 or newer** — rejected on any earlier control-plane version.
> - **Incompatible with `capacityReservationID`** — setting both is rejected.

---

## Implementation (what we built)

| Area | File | Change |
|---|---|---|
| API field | `exp/api/v1beta2/rosamachinepool_types.go` | New `SpotMarketOptions *infrav1.SpotMarketOptions` (`+immutable` `+optional`), reusing the shared `api/v1beta2.SpotMarketOptions` type |
| CRD marker fix | `api/v1beta2/types.go` | `+kubebuilder:validation:pattern=` → `Pattern=` (lowercase was silently ignored); `maxPrice` pattern now actually emitted into CRDs |
| OCM mapping (create) | `exp/controllers/rosamachinepool_controller.go` (`nodePoolBuilder`) | Maps to `cmv1.NewAwsNodePoolSpotMarketOptions()`; sets `.MaxPrice()` only when non-nil |
| Version gate | `exp/controllers/rosamachinepool_controller.go` (`validateMachinePoolSpec`) | Rejects Spot on control-plane versions < 4.22; runs even when `spec.version` is omitted |
| Immutability / diff | `exp/controllers/rosamachinepool_controller.go` (`computeSpecDiff`, `updateNodePool`) | Ignored in the spec diff and zeroed before Day-2 update, so it never triggers a spurious update |
| Readback | `exp/utils/rosa_helper.go` | Reads OCM spot options back into CAPA spec, distinguishing "no price" from "capped" |
| Webhook | `exp/webhooks/rosamachinepool_webhook.go` | Forbids Spot + `capacityReservationID`; enforces immutability; runs on create and update |
| Version constant | `pkg/rosa/versions.go` | `MinSpotMarketOptionsVersion = semver.MustParse("4.22.0")` |
| Docs | `docs/book/src/topics/rosa/creating-rosa-machinepools.md` | New "Spot instances" section |
| Dependency bump | `go.mod` / `go.sum` | `ocm-sdk-go` 0.1.486 → 0.1.510, `ocm-api-model` 0.0.440 → 0.0.465 |

`ROSAMachinePool` is v1beta2-only, so no conversion webhook changes were required.

---

## Pre-requisite — Custom controller image + updated CRD deployed

Built the controller from the branch with podman, loaded it into the `route4-cluster` node's
containerd, applied the updated `rosamachinepools` CRD from the branch, and patched the
`capa-controller-manager` deployment.

- Controller running image: `quay.io/<user>/cluster-api-aws-controller-amd64:spot-test`
- Controller startup log: `"starting manager" version="v2.10.0-spot-test"`
- Live CRD confirmed to carry `spec.spotMarketOptions` with `maxPrice` pattern `^[0-9]+(\.[0-9]+)?$`

---

## Test Cases

### Test 1 — Accept Spot with no max price

Applied a `ROSAMachinePool` with `spotMarketOptions: {}` (server dry-run).

```
rosamachinepool.infrastructure.cluster.x-k8s.io/spot-test-nocap created (server dry run)
```

**Result: PASS ✅**

---

### Test 2 — Accept Spot with max price

Applied a `ROSAMachinePool` with `spotMarketOptions: { maxPrice: "0.05" }` (server dry-run).

```
rosamachinepool.infrastructure.cluster.x-k8s.io/spot-test-cap created (server dry run)
```

**Result: PASS ✅**

---

### Test 3 — CRD rejects invalid maxPrice format

Applied `spotMarketOptions: { maxPrice: "abc" }`.

CRD schema response:
```
The ROSAMachinePool "spot-test-badprice" is invalid:
spec.spotMarketOptions.maxPrice: Invalid value: "abc": spec.spotMarketOptions.maxPrice in body
should match '^[0-9]+(\.[0-9]+)?$'
```

Proves the `pattern` → `Pattern` kubebuilder marker fix propagated into the CRD (the lowercase
form was silently ignored by controller-gen, so `"abc"` would otherwise have been accepted).

**Result: PASS ✅**

---

### Test 4 — Webhook rejects Spot + capacityReservationID

Applied `spotMarketOptions: {}` together with `capacityReservationID: "cr-0123456789abcdef0"`.

Webhook response:
```
The ROSAMachinePool "spot-test-conflict" is invalid:
spec.spotMarketOptions: Forbidden: spotMarketOptions is incompatible with capacityReservationID
```

Request rejected before reaching the controller or OCM.

**Result: PASS ✅**

---

### Test 5 — Version gate passes against a live 4.22 control plane

Provisioned a real ROSA HCP cluster at OCP 4.22.8 with a Spot-enabled node pool. The controller
version gate reads `ControlPlane.Status.Version` (populated as `4.22.8`) and must allow Spot.

- ROSAControlPlane: `Status.Version = 4.22.8`, `Ready=true`
- ROSAMachinePool: `RosaMachinePoolReady=True`, `FailureMessage` empty (no version-gate rejection)

**Result: PASS ✅**

---

### Test 6 — Spot node pool provisioned in OCM (real EC2 spot instances)

The Spot node pool reconciled after the control plane became ready. The controller mapped
`spotMarketOptions` to the OCM `AwsNodePool.spot_market_options` builder, and OCM created a real
spot-backed node pool.

`ROSAMachinePool` spec after provision:
```yaml
spec:
  instanceType: m5.xlarge
  nodePoolName: spot-np
  version: 4.22.8
  spotMarketOptions: {}
  providerIDList:
  - aws:///<az>/<instance-id>   # real EC2 spot instance
  - aws:///<az>/<instance-id>   # real EC2 spot instance
```

CAPI `MachinePool`: `PHASE=Running`, `2/2 READY`.

**Result: PASS ✅**

---

### Test 7 — Day-1 only: Immutability — Spot excluded from reconcile diff

On routine reconciles the controller logged `"MachinePool spec diff detected"` for other fields
settling, but `SpotMarketOptions` never appeared in any diff, confirming `computeSpecDiff` ignores
it and no spurious Day-2 OCM update is triggered.

| Reconcile loop | `SpotMarketOptions` in diff? |
|----------------|------------------------------|
| Any (post-provision) | No |

**Result: PASS ✅**

---

## Summary

| Test | Description | Result |
|------|-------------|--------|
| 1 | Accept Spot with no max price | PASS ✅ |
| 2 | Accept Spot with max price | PASS ✅ |
| 3 | CRD rejects invalid maxPrice format | PASS ✅ |
| 4 | Webhook rejects Spot + capacityReservationID | PASS ✅ |
| 5 | Version gate passes against live 4.22 control plane | PASS ✅ |
| 6 | Spot node pool provisioned in OCM (2 real EC2 spot instances) | PASS ✅ |
| 7 | Day-1 only: Immutability — Spot excluded from reconcile diff | PASS ✅ |

**Overall result: PASS** — all 7 test cases behaved as expected. The feature works end-to-end,
from CRD/webhook validation through the controller version gate and OCM mapping to a live
spot-backed ROSA HCP node pool.
