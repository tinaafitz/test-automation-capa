# Kubernetes Sidecars

## What is a Sidecar?

A sidecar is a secondary container that runs alongside the main application container in the same Pod. They share the same network namespace (localhost), storage volumes, and lifecycle.

## Common Use Cases

- **Logging/monitoring** — a Fluentd or Filebeat sidecar ships logs from the main container to a central system
- **Service mesh proxies** — Envoy in Istio/Linkerd intercepts all traffic for mTLS, retries, circuit breaking
- **Secret management** — Vault Agent sidecar injects and rotates secrets
- **Config reloading** — watches for ConfigMap changes and signals the main container

## How They Work

```yaml
spec:
  containers:
  - name: app           # Main container
    image: my-app:v1
  - name: log-shipper   # Sidecar
    image: fluentd
    volumeMounts:
    - name: logs
      mountPath: /var/log/app
```

Both containers share the `logs` volume. The app writes logs, the sidecar reads and ships them — neither knows about the other's internals.

## Native Sidecar Support (K8s 1.28+)

Before 1.28, sidecars were just regular containers — they had no guaranteed ordering, and during Pod shutdown a sidecar might die before the main container finished. Kubernetes 1.28 introduced **native sidecar containers** via `initContainers` with `restartPolicy: Always`:

```yaml
initContainers:
- name: log-shipper
  image: fluentd
  restartPolicy: Always   # This makes it a native sidecar
```

This guarantees the sidecar starts **before** the main container and stops **after** it — solving the lifecycle ordering problem.

## Sidecar Pattern in This Project

In this project, our "sidecar" borrows the Kubernetes concept but uses threads instead of containers. When you trigger a cluster operation (provisioning or deletion) from the UI:

1. **The backend starts the Ansible playbook** as a subprocess (e.g., `delete_rosa_hcp_cluster.yml`)
2. **A sidecar thread starts simultaneously** — it reads the playbook's stdout line by line in real-time
3. **Each line gets fed to `MonitoringAgent.process_line()`** which pattern-matches against known issues in `agents/knowledge_base/known_issues.json`

### The Agent Pipeline

When the sidecar spots a known pattern (like a RETRYING line for a stuck resource):

```
Sidecar reads line -> MonitoringAgent detects issue -> DiagnosticAgent diagnoses
-> if confidence >= 0.7 -> RemediationAgent fixes it
```

The state machine for each tracked issue is: **DETECTED -> DIAGNOSING -> REMEDIATING -> RESOLVED/FAILED**

### What You'll See in the Logs

Lines prefixed with `[SIDECAR]` are the raw Ansible output being captured. For example:

```
[SIDECAR] FAILED - RETRYING: Wait for rosacontrolplane hat-rosa-test deletion to complete (116 retries left)
```

The agent sees that RETRYING pattern, checks how long the resource has been stuck, and if it exceeds a threshold, triggers diagnosis. The diagnostic agent checks the actual ROSA cluster status (via `rosa describe cluster`) before recommending any remediation — preventing premature cleanup of resources that are still actively being deleted.
