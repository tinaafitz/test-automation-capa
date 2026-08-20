# Test Results: `componentRoutes` support for ROSAControlPlane (PR #6183)

## Environment

| | |
|---|---|
| **Hub cluster** | Minikube `route4-cluster` (Kubernetes v1.34.0, podman rootless driver, containerd runtime) |
| **CAPI version** | v1.13.4 (clusterctl) |
| **CAPA image** | `quay.io/tinaafitz/cluster-api-aws-controller-amd64:pr-6183` |
| **CAPA source** | `openshift/cluster-api-provider-aws` branch `pr-6183`, CAPI dependency `v1.13.4` |
| **OCM environment** | Stage |
| **Hosted cluster** | `ttt-route5-cluster` |
| **OCP version** | 4.22.8 (channel: stable) |
| **Region** | us-west-2, Public endpoint, 2 AZs, 4 compute nodes (autoscaled) |

---

## Pre-requisite — Provisioned ROSA HCP cluster using pr-6183 image

Created ROSA HCP cluster `ttt-route5-cluster` via CAPI on Minikube hub using the pr-6183 controller image. Cluster reached `ready` state with control plane and 4 compute nodes available before proceeding to day 2 testing.

- ROSAControlPlane: `ready=true`
- ROSAMachinePool: `ready=true`, replicas=2
- Cluster phase: `Provisioned`
- Console URL (default): `https://console-openshift-console.apps.rosa.<cluster-domain>`

---

## Test Cases

### Test 1 — Set single route (console only)

Patched `name=console`, `hostname=console.ttt-test.example.com`, `tlsSecretRef=my-console-tls`

Controller log:
```
"reconcile componentRoutes"
"updating ingress <ingress-id> componentRoutes on cluster <cluster-id>"
```

OCM result: `Console URL: https://console.ttt-test.example.com`

**Result: PASS ✅**

---

### Test 2 — Remove custom route (revert to default)

Patched `componentRoutes` to empty list

Controller log:
```
"reconcile componentRoutes"
"updating ingress <ingress-id> componentRoutes on cluster <cluster-id>"
```
Controller called `resetComponentRoutes()`, sent empty hostname/tlsSecretRef to OCM for both `console` and `downloads`.

OCM result: `Console URL: https://console-openshift-console.apps.rosa.<cluster-domain>`

**Result: PASS ✅**

---

### Test 3 — Set both routes simultaneously

Patched `name=console`, `hostname=console.ttt-test.example.com`, `tlsSecretRef=my-console-tls` and `name=downloads`, `hostname=downloads.ttt-test.example.com`, `tlsSecretRef=my-downloads-tls`

OCM ingress API (`/api/clusters_mgmt/v1/clusters/.../ingresses`) confirmed:

| Route | Hostname | TLS Secret |
|-------|----------|------------|
| console | `console.ttt-test.example.com` | `my-console-tls` |
| downloads | `downloads.ttt-test.example.com` | `my-downloads-tls` |

**Result: PASS ✅**

---

### Test 4 — Webhook rejects invalid route name

Patched `name=oauth`, `hostname=oauth.ttt-test.example.com`, `tlsSecretRef=my-oauth-tls`

Webhook response:
```
The ROSAControlPlane "ttt-route5-cluster" is invalid:
spec.componentRoutes[0].name: Unsupported value: "oauth": supported values: "console", "downloads"
```

Request rejected before reaching the controller or OCM.

**Result: PASS ✅**

---

### Test 5 — Idempotency

Applied the same `componentRoutes` values twice. On subsequent reconcile loops the controller ran `reconcile componentRoutes` but did not call `updating ingress` — `componentRoutesEqual()` correctly detected no diff and skipped the redundant OCM API call.

| Reconcile loop | `updating ingress` called? |
|----------------|---------------------------|
| 1st (after patch) | Yes |
| 2nd+ (no change) | No |

**Result: PASS ✅**

---

## Notes

- OCM accepts `tlsSecretRef` by name without validating secret existence at admission time — resolution is deferred to the hosted cluster's ingress operator. This is expected behavior consistent with how OpenShift handles ingress customization.
- Webhook correctly rejects both empty `tlsSecretRef` and invalid `name` values.
- TLS secrets were created in `openshift-config` namespace on the hosted cluster using self-signed certs (no custom domain available in test environment).
- The `downloads` route hostname is not surfaced in `rosa describe cluster` output but is confirmed via the OCM ingresses API.

---

## Summary

| Test | Description | Result |
|------|-------------|--------|
| 1 | Set console route | PASS ✅ |
| 2 | Remove route, revert to default | PASS ✅ |
| 3 | Set console + downloads together | PASS ✅ |
| 4 | Webhook rejects invalid name | PASS ✅ |
| 5 | Idempotency — no redundant OCM calls | PASS ✅ |

**Overall result: PASS** — all 5 test cases behaved as expected.
