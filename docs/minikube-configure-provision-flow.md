# Minikube Configure + Provision Flow

This document describes the complete steps to configure CAPI/CAPA on a Minikube cluster and provision a ROSA HCP cluster from it.

## Prerequisites

Four credentials are required:

| Credential | Purpose |
|---|---|
| `AWS_ACCESS_KEY_ID` | AWS IAM access key |
| `AWS_SECRET_ACCESS_KEY` | AWS IAM secret key |
| `AWS_REGION` | AWS region (e.g. `us-west-2`) |
| `OCM_CLIENT_ID` | OCM service account client ID |
| `OCM_CLIENT_SECRET` | OCM service account client secret |

Tools required: `clusterctl`, `clusterawsadm`, `kubectl`, `minikube`

---

## Phase 1: Configure CAPI/CAPA

Task file: `tasks/clusterctl_install_capi.yml`

### 1. Encode AWS credentials

```bash
clusterawsadm bootstrap credentials encode-as-profile
```

**Environment variables:**
- `AWS_REGION`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`

This outputs a base64-encoded credentials profile used by `clusterctl init`.

> **Note:** This project does NOT use `clusterawsadm bootstrap iam create-cloudformation-stack` (from the [upstream quickstart guide](https://cluster-api-aws.sigs.k8s.io/quick-start)). IAM role creation is handled by the `ROSARoleConfig` CRD during provisioning instead.

### 2. Initialize clusterctl

```bash
clusterctl init --infrastructure aws
```

**Environment variables:**
- `KUBECONFIG` (defaults to `~/.kube/config`)
- `AWS_REGION`
- `EXP_ROSA=true` — enables ROSA HCP support (experimental feature gate)
- `EXP_MACHINE_POOL=true` — enables MachinePool support
- `CLUSTER_TOPOLOGY=true` — enables ClusterClass/topology support
- `AWS_B64ENCODED_CREDENTIALS` — output from step 1

This installs:
- CAPI core controller in `capi-system`
- CAPA (AWS) infrastructure provider in `capa-system`
- `AWSClusterControllerIdentity/default` — cluster-scoped resource that allows CAPA to use AWS credentials

### 3. Wait for CAPI controller

```bash
kubectl wait --for=condition=Available --timeout=300s \
  deployment/capi-controller-manager -n capi-system
```

Retries 10 times with 30s delay between attempts.

### 4. Wait for CAPA controller

```bash
kubectl wait --for=condition=Available --timeout=300s \
  deployment/capa-controller-manager -n capa-system
```

Retries 10 times with 30s delay between attempts.

### 5. (Custom image only) Apply updated CRDs

Only runs when `CUSTOM_CAPA_IMAGE=true` and `CUSTOM_CAPA_SOURCE_PATH` is set.

```bash
for crd in <CUSTOM_CAPA_SOURCE_PATH>/config/crd/bases/*.yaml; do
  kubectl apply -f "$crd"
done
```

### 6. (Custom image only) Create NodeadmConfig RBAC

Required by newer CAPA builds that include NodeadmConfig resources.

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: nodeadmconfig-access
rules:
- apiGroups: ["bootstrap.cluster.x-k8s.io"]
  resources:
    - nodeadmconfigs
    - nodeadmconfigs/status
    - nodeadmconfigtemplates
    - nodeadmconfigtemplates/status
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: nodeadmconfig-access-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: nodeadmconfig-access
subjects:
- kind: ServiceAccount
  name: capa-controller-manager
  namespace: capa-system
```

### 7. (Custom image only) Patch CAPA deployment

```bash
kubectl set image deployment/capa-controller-manager \
  manager=<CUSTOM_CAPA_IMAGE_REPO>:<CUSTOM_CAPA_IMAGE_TAG> \
  -n capa-system
```

### 8. (Custom image only) Wait for rollout and verify

```bash
kubectl rollout status deployment/capa-controller-manager -n capa-system --timeout=300s

kubectl get deployment capa-controller-manager -n capa-system \
  -o jsonpath='{.spec.template.spec.containers[0].image}'
```

### 9. Create namespace

```bash
kubectl create namespace ns-rosa-hcp --dry-run=client -o yaml | kubectl apply -f -
```

### 10. Create AWS credentials secret

```bash
kubectl create secret generic capa-manager-bootstrap-credentials \
  --from-literal=AWS_ACCESS_KEY_ID="<AWS_ACCESS_KEY_ID>" \
  --from-literal=AWS_SECRET_ACCESS_KEY="<AWS_SECRET_ACCESS_KEY>" \
  --from-literal=AWS_REGION="<AWS_REGION>" \
  -n capa-system \
  --dry-run=client -o yaml | kubectl apply -f -
```

### 11. Create ROSA credentials secret (capa-system)

```bash
kubectl create secret generic rosa-creds-secret \
  --from-literal=ocmClientID="<OCM_CLIENT_ID>" \
  --from-literal=ocmClientSecret="<OCM_CLIENT_SECRET>" \
  --from-literal=ocmApiUrl="https://api.stage.openshift.com" \
  -n capa-system \
  --dry-run=client -o yaml | kubectl apply -f -
```

### 12. Create ROSA credentials secret (ns-rosa-hcp)

```bash
kubectl create secret generic rosa-creds-secret \
  --from-literal=ocmClientID="<OCM_CLIENT_ID>" \
  --from-literal=ocmClientSecret="<OCM_CLIENT_SECRET>" \
  --from-literal=ocmApiUrl="https://api.stage.openshift.com" \
  -n ns-rosa-hcp \
  --dry-run=client -o yaml | kubectl apply -f -
```

### 13. Verify installation

```bash
kubectl get deploy -n capi-system
kubectl get deploy -n capa-system
kubectl get ns ns-rosa-hcp
```

---

## Phase 2: Provision a ROSA HCP Cluster

Playbook: `playbooks/provision_rosa_hcp_minikube.yml`

### 1. Switch to Minikube context

```bash
kubectl config use-context <minikube_context>
```

### 2. Create namespace

```bash
kubectl --context <minikube_context> create namespace ns-rosa-hcp \
  --dry-run=client -o yaml | kubectl --context <minikube_context> apply -f -
```

### 3. Apply cluster YAML

```bash
kubectl --context <minikube_context> apply -f <yaml_file>
```

The generated YAML contains these Kubernetes resources:

| Resource | Kind | Purpose |
|---|---|---|
| Cluster | `cluster.x-k8s.io/v1beta1` | CAPI Cluster object, ties everything together |
| ROSACluster | `infrastructure.cluster.x-k8s.io/v1beta2` | Infrastructure reference (empty spec) |
| ROSANetwork | `infrastructure.cluster.x-k8s.io/v1beta2` | Creates VPC, subnets, IGW via CloudFormation |
| ROSARoleConfig | `infrastructure.cluster.x-k8s.io/v1beta2` | Creates IAM roles (installer, support, worker, control plane operator) |
| ROSAControlPlane | `controlplane.cluster.x-k8s.io/v1beta2` | ROSA HCP control plane definition |
| MachinePool | `cluster.x-k8s.io/v1beta1` | Worker node pool wrapper |
| ROSAMachinePool | `infrastructure.cluster.x-k8s.io/v1beta2` | ROSA-specific machine pool config |

> **Note:** `ManagedCluster` resources (MCE/ACM-specific) are automatically filtered out for Minikube provisioning.

Both `ROSANetwork` and `ROSARoleConfig` reference `AWSClusterControllerIdentity/default` via `identityRef` — this was created automatically by `clusterctl init` in Phase 1.

### 4. Wait for RosaControlPlane

```bash
kubectl --context <minikube_context> get rosacontrolplane <cluster_name> \
  -n ns-rosa-hcp -o json
```

Retries 10 times with 2s delay. The cluster typically takes 15-20 minutes to fully provision.

### Provisioning stages

1. IAM roles creation (`ROSARoleConfig`)
2. Network resources via CloudFormation (`ROSANetwork`)
3. Control plane provisioning
4. Worker node provisioning

---

## Differences from MCE Environment

| Aspect | Minikube | MCE |
|---|---|---|
| CAPI/CAPA installation | `clusterctl init` | Multicluster Engine operator |
| AWSClusterControllerIdentity | Created automatically by `clusterctl init` | Created explicitly via `tasks/set_aws_identity.yml` |
| IAM role creation | `ROSARoleConfig` CRD | `ROSARoleConfig` CRD |
| `clusterawsadm bootstrap iam` | Not used (ROSARoleConfig handles it) | Not used (ROSARoleConfig handles it) |
| ManagedCluster resource | Filtered out (not available on Minikube) | Included (ACM/MCE manages it) |
| Custom CAPA image support | Yes (patch deployment after init) | No (uses MCE-managed provider) |
| kubectl vs oc | `kubectl` | `oc` |
