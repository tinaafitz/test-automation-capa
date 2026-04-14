# CAPA CLI Reference

Complete command reference with live output examples from a real environment.

## Quick Reference

| Command | Description |
|---|---|
| `create` | Create a new cluster from profile/spec |
| `upgrade` | Upgrade cluster (CP + MP, auto-sequenced) |
| `apply` | Apply Day2 actions from a spec file |
| `delete` | Delete a cluster |
| `plan` | Show execution plan (dry run) |
| `status` | Show cluster status |
| `specs` | List available profiles |
| `features` | List all features from registry |
| `set` | Set a single feature on a running cluster |
| `validate` | Validate a spec file against the registry |
| `test` | Run test suites |
| `version` | Show CLI, registry, and agent versions |
| `list-clusters` | List all managed ROSA HCP clusters |
| `logs` | Tail sidecar or job logs |
| `history` | Show operation history |
| `watch` | Poll cluster status until ready |
| `completion` | Generate shell completion (bash/zsh) |
| `generate-specs` | Auto-generate feature specs from registry |
| `workflow` | List, show, run, or export workflows |

## Global Flags

```
--verbose, -v    Verbose output (must come before subcommand)
--dry-run        Show plan without executing
```

---

## 1. version

Show CLI, registry, and agent versions.

```
$ ./capa version

CAPA CLI
  CLI version:      1.1.0
  Registry path:    schemas/feature-registry.yml
  Features:         26
  Suites:           9
  Agent framework:  0.2.0
  Python:           3.13.11
  oc                 Client Version: 4.19.22
  ansible-playbook   ansible-playbook [core 2.18.2]
```

## 2. list-clusters

List all managed ROSA HCP clusters.

```
$ ./capa list-clusters

CLUSTER                        NAMESPACE            VERSION      READY    UPGRADING
------------------------------------------------------------------------------------------
  rosa-hcp-1-control-plane     default                           false
  e2e-rosa-hcp                 ns-rosa-hcp          4.21.8       true
  moo-rosa-hcp                 ns-rosa-hcp          4.20.11      true     4.20.11 -> 4.20.17
  upg-rosa-hcp                 ns-rosa-hcp          4.20.11      false
```

## 3. status

Show cluster status including version, readiness, and available upgrades.

```
$ ./capa status --cluster moo-rosa-hcp

Cluster: moo-rosa-hcp
Namespace: ns-rosa-hcp

  Control Plane:
    Version: 4.20.11 -> 4.20.17 (upgrading)
    Ready: true
    Available: ["4.20.12","4.20.13","4.20.14","4.20.15","4.20.16","4.20.17"]

  Machine Pool:
    Version: 4.20.11
    Ready: true
    Replicas: 2
    Available: ["4.20.12","4.20.13","4.20.14","4.20.15","4.20.16","4.20.17"]
```

```
$ ./capa status --cluster e2e-rosa-hcp

Cluster: e2e-rosa-hcp
Namespace: ns-rosa-hcp

  Control Plane:
    Version: 4.21.8
    Ready: true

  Machine Pool:
    Version: 4.21.8
    Ready: true
    Replicas: 2
```

## 4. specs

List available profiles, feature specs, and workflow specs.

```
$ ./capa specs

Available Specs:

  Profiles — Cluster creation presets
    default
      create | availability_zones, instance_type, additional_tags
    ha-production
      create | private_network, availability_zones, instance_type, disk_size
    private-encrypted-custom
      create | instance_type, disk_size, additional_tags
    private-encrypted
      create | private_network, etcd_kms, availability_zones, instance_type

  Features — Individual feature actions
    additional-tags       apply | additional_tags
    audit-logging         apply | audit_logging
    channel-group         apply | channel_group
    cluster-delete        delete | (no features)
    control-plane-upgrade apply | control_plane_upgrade
    default-autoscaling   apply | default_autoscaling
    identity-provider     apply | identity_provider
    image-registry        apply | image_registry
    machine-pool-autoscaling  apply | machine_pool_autoscaling
    machine-pool-upgrade  apply | machine_pool_upgrade
    node-labels           apply | node_labels
    node-taints           apply | node_taints
    parallel-upgrade      apply | parallel_upgrade
    proxy-enabled         apply | proxy_enabled
    security-groups       apply | security_groups
    user-agent            apply | user_agent

  Workflows — Multi-step sequences
    day2-test
      apply | channel_group -> control_plane_upgrade -> machine_pool_upgrade -> channel_group
    full-e2e
    upgrade
    verify-and-configure
```

## 5. features

List all features from the feature registry.

```
$ ./capa features

Feature Registry:

  Cluster Configuration [Day1]
    private_network         immutable  create         boolean    ROSAControlPlane
    byon                    immutable  create         boolean    ROSAControlPlane (after private_network)
    sts                     immutable  create         boolean    ROSAControlPlane
    availability_zones      immutable  create         select     ROSANetwork
    additional_tags         mutable    create,apply   key_value  ROSAControlPlane

  Security & Authentication [Day1]
    identity_provider       mutable    create,apply   select     ROSAControlPlane
    external_oidc           immutable  create         boolean    ROSAControlPlane
    security_groups         mutable    create,apply   list       ROSAControlPlane
    etcd_kms                immutable  create         string     ROSAControlPlane

  Machine Pool & Auto-Scaling [Day1]
    default_autoscaling     mutable    create,apply   range      ROSAMachinePool
    machine_pool_autoscaling mutable   create,apply   range      ROSAMachinePool
    parallel_upgrade        mutable    create,apply   number     ROSAMachinePool

  Version & Lifecycle [Day2]
    control_plane_upgrade   mutable    apply,upgrade  version    ROSAControlPlane
    machine_pool_upgrade    mutable    apply,upgrade  version    ROSAMachinePool (after control_plane_upgrade)
    channel_group           mutable    create,apply,upgrade select ROSAControlPlane

  Node Configuration [Day1]
    instance_type           immutable  create         select     ROSAMachinePool
    disk_size               immutable  create         number     ROSAMachinePool
    node_taints             mutable    create,apply   key_value  ROSAMachinePool
    node_labels             mutable    create,apply   key_value  ROSAMachinePool

  Network & Connectivity [Day1]
    no_cni                  immutable  create         boolean    ROSAControlPlane
    proxy_enabled           mutable    create,apply   boolean    ROSAControlPlane

  Storage & Registry [Day1]
    image_registry          mutable    create,apply   boolean    ROSAControlPlane

  Domain & User Agent [Day1]
    domain_prefix           immutable  create         string     ROSAControlPlane
    user_agent              mutable    create,apply   string     ROSAControlPlane

  Day2 Operations [Day2]
    cluster_delete          immutable  delete         action
    audit_logging           mutable    apply          select     ROSAControlPlane
```

## 6. create

Create a new cluster from a profile or spec file.

```
$ ./capa --dry-run create --profile default -e name_prefix=demo

============================================================
  Execution Plan: 1 step(s)
============================================================

  Step 1: Create cluster demo-rosa-hcp

DRY RUN — no changes made.
```

**Live example:**
```
$ ./capa create --profile default -e name_prefix=e2e -e version=4.21.8
```

## 7. upgrade

Upgrade a cluster — auto-sequences control plane then machine pool.

```
$ ./capa --dry-run upgrade --cluster moo-rosa-hcp --version 4.20.17

============================================================
  Execution Plan: 2 step(s)
============================================================

  Step 1: Upgrade control plane to 4.20.17
  Step 2: Upgrade machine pool to 4.20.17 (after control_plane_upgrade)

DRY RUN — no changes made.
```

## 8. apply

Apply Day2 actions from a spec file.

```
$ ./capa --dry-run apply -f specs/workflows/day2-test.yml --cluster e2e-rosa-hcp

============================================================
  Execution Plan: 4 step(s)
============================================================

  Step 1: Channel Group = fast
  Step 2: Control Plane Upgrade
  Step 3: Machine Pool Upgrade (after control_plane_upgrade)
  Step 4: Channel Group = stable

DRY RUN — no changes made.
```

## 9. delete

Delete a cluster (with confirmation prompt).

```
$ ./capa --dry-run delete --cluster old-rosa-hcp

Delete cluster 'old-rosa-hcp'? This cannot be undone. [y/N]: n
Cancelled.
```

## 10. plan

Show the execution plan for a spec without executing (always a dry run).

```
$ ./capa plan -f specs/profiles/default.yml -e name_prefix=demo

============================================================
  Execution Plan: 1 step(s)
============================================================

  Step 1: Create cluster demo-rosa-hcp

DRY RUN — no changes made.
```

## 11. set

Set a single feature on a running cluster.

```
$ ./capa --dry-run set channel_group fast -c e2e-rosa-hcp

============================================================
  Execution Plan: 1 step(s)
============================================================

  Step 1: Channel Group = fast

DRY RUN — no changes made.
```

## 12. validate

Validate a spec file against the feature registry.

```
$ ./capa validate specs/features/channel-group.yml

Validating: specs/features/channel-group.yml
  Kind: ClusterAutomationSpec
  Action: apply
  Features: 0, Actions: 1

  1 warning(s):
    Warning: No cluster specified — will need --cluster at runtime

  Valid spec (with warnings).
```

## 13. test

Run test suites or list available suites.

```
$ ./capa test --list

Available Test Suites:

  00-test-variable-passing
    Name: Test Variable Passing
    Description: Simple test to verify command-line variable passing works correctly

  05-verify-mce-environment
    Name: Verify MCE Environment
    Description: Validate MCE/CAPI/CAPA environment configuration before provisioning

  10-configure-mce-environment
    Name: Configure MCE Environment
    Description: Set up MCE environment for CAPI/CAPA cluster provisioning

  20-rosa-hcp-provision
    Name: Provision ROSA HCP Cluster
    Description: Provision a ROSA HCP cluster using CAPA

  25-rosa-hcp-upgrade-control-plane
    Name: Upgrade ROSA HCP Control Plane
    Description: Upgrade a ROSA HCP cluster control plane to the next available version

  26-rosa-hcp-upgrade-machine-pool
    Name: Upgrade ROSA HCP Machine Pool
    Description: Upgrade a ROSA HCP cluster machine pool to the next available version

  30-rosa-hcp-delete
    Name: Delete ROSA HCP Cluster
    Description: Delete a ROSA HCP cluster and its CAPA automation resources

  40-enable-capi-disable-hypershift
    Name: Enable CAPI/CAPA, Disable Hypershift

  41-disable-capi-enable-hypershift
    Name: Disable CAPI/CAPA, Enable Hypershift
```

**Run a test suite:**
```
$ ./capa test 20-rosa-hcp-provision --ai-agent -VVV
```

## 14. history

Show operation history for a cluster.

```
$ ./capa history --cluster moo-rosa-hcp

Operation history for moo-rosa-hcp:

  TIMESTAMP              CLUSTER                   FEATURE                      STATUS       VALUE
  ----------------------------------------------------------------------------------------------------
  2026-04-13T14:18:35    moo-rosa-hcp              control_plane_upgrade        running      4.20.11
  2026-04-13T16:15:41    moo-rosa-hcp              control_plane_upgrade        running      4.20.11
  2026-04-13T16:30:34    moo-rosa-hcp              machine_pool_upgrade         running      4.20.11
```

## 15. logs

Tail sidecar or job logs for a cluster.

```
$ ./capa logs --cluster moo-rosa-hcp

Recent operations for moo-rosa-hcp:

  2026-04-13T14:18:35  running  control_plane_upgrade  Playbook: playbooks/upgrade_rosa_control_plane.yml
  2026-04-13T16:15:41  running  control_plane_upgrade  Playbook: playbooks/upgrade_rosa_control_plane.yml
  2026-04-13T16:30:34  running  machine_pool_upgrade   Playbook: playbooks/upgrade_rosa_machine_pool.yml
```

## 16. watch

Poll cluster status until ready. Prints every poll interval.

```
$ ./capa watch --cluster moo-rosa-hcp --interval 15

Watching cluster: moo-rosa-hcp
  Namespace: ns-rosa-hcp
  Interval: 15s, Timeout: 7200s
  Press Ctrl+C to stop

  18:39:04  CP: true  MP: true  Version: 4.20.11 upgrading -> 4.20.17  (0s) *
  18:39:19  CP: true  MP: true  Version: 4.20.11 upgrading -> 4.20.17  (15s)
  18:39:35  CP: true  MP: true  Version: 4.20.11 upgrading -> 4.20.17  (31s)
  ...

Cluster moo-rosa-hcp is ready! (v4.20.17, 1234s)
```

## 17. completion

Generate shell completion for bash or zsh.

```
$ ./capa completion bash

# CAPA CLI bash completion
# Add to ~/.bashrc: eval "$(./capa completion bash)"
_capa_complete() {
    local cur prev commands
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    commands="create upgrade apply delete plan status specs features set validate test ..."
    ...
}
complete -F _capa_complete capa
complete -F _capa_complete ./capa
```

**Install:** `eval "$(./capa completion bash)"` or `./capa completion bash >> ~/.bashrc`

## 18. generate-specs

Auto-generate feature spec files from the registry.

```
$ ./capa generate-specs

Generated: 0 specs, skipped: 16 (already exist)
  Use --force to overwrite existing specs
```

## 19. workflow

Manage and run workflows — works with both UI-saved workflows and YAML workflow files.

### workflow list

```
$ ./capa workflow list

Saved Workflows (saved_workflows.json):

  verify_and_configure  (2 steps)  saved: 2026-04-13T10:28
    1. Verify MCE Environment
    2. Configure MCE Environment
  verify_configure_provision  (3 steps)  saved: 2026-04-13T10:29
    1. Verify MCE Environment
    2. Configure MCE Environment
    3. Provision ROSA HCP Cluster

YAML Workflows (specs/workflows/):

  full-e2e  (4 steps)  Complete end-to-end test - validate, provision, verify, then delete
    1. Validate CAPA Environment
    2. Provision ROSA HCP Cluster
    3. Verify ROSA HCP Cluster
    4. Delete ROSA HCP Cluster
  verify-and-configure  (2 steps)  Validate the CAPA environment and configure MCE for cluster provisioning
    1. Verify MCE Environment
    2. Configure MCE Environment
```

### workflow show

```
$ ./capa workflow show verify_configure_provision

Workflow: verify_configure_provision
  ID: wf-d9dc4f951afa
  Stop on failure: True

  Steps:
    1. Verify MCE Environment
       playbook: playbooks/verify_capi_environment.yaml
       on_failure: stop
    2. Configure MCE Environment
       playbook: playbooks/configure_mce_environment.yml
       on_failure: stop
    3. Provision ROSA HCP Cluster
       playbook: playbooks/create_rosa_hcp_cluster.yml
       on_failure: stop
       extra_vars: {
         "name_prefix": "lop",
         "openshift_version": "4.20.10",
         "create_rosa_network": true,
         "create_rosa_role_config": true,
         "vpc_cidr_block": "10.0.0.0/16",
         "availability_zone_count": 1,
         "aws_region": "us-west-2",
         "channel_group": "stable",
         "capi_namespace": "ns-rosa-hcp"
       }
```

### workflow run (dry run)

```
$ ./capa --dry-run workflow run verify_configure_provision

============================================================
  Workflow: verify_configure_provision (3 steps)
============================================================

  Step 1: Verify MCE Environment
  Step 2: Configure MCE Environment
  Step 3: Provision ROSA HCP Cluster

DRY RUN — no changes made.
```

### workflow run with overrides

```
$ ./capa workflow run verify_configure_provision -e name_prefix=ci1 -e openshift_version=4.21.8
```

### workflow export

Convert a UI-saved workflow to a YAML file.

```
$ ./capa workflow export verify_and_configure

Exported YAML:

apiVersion: capa-automation/v1
kind: Workflow
metadata:
  name: verify_and_configure
  description: ''
spec:
  vars: {}
  steps:
  - name: Verify MCE Environment
    playbook: playbooks/verify_capi_environment.yaml
    on_failure: stop
    timeout: 600
  - name: Configure MCE Environment
    playbook: playbooks/configure_mce_environment.yml
    on_failure: stop
    timeout: 600

Save to: specs/workflows/verify_and_configure.yml
Write file? [y/N]:
```

---

## YAML Workflow Format

Workflows can be defined as YAML files in `specs/workflows/` using a format similar to GitHub Actions:

```yaml
apiVersion: capa-automation/v1
kind: Workflow
metadata:
  name: full-e2e
  description: Complete end-to-end test
spec:
  vars:
    MCE_NAMESPACE: multicluster-engine
  steps:
    - name: Validate CAPA Environment
      playbook: playbooks/validate-capa-environment.yml
      on_failure: stop
      timeout: 120
      vars:
        soft_verify: "true"

    - name: Provision ROSA HCP Cluster
      playbook: playbooks/create_rosa_hcp_cluster.yml
      on_failure: stop
      timeout: 2400

    - name: Delete ROSA HCP Cluster
      playbook: playbooks/delete_rosa_hcp_cluster.yml
      on_failure: skip
      timeout: 2400
```

### Workflow fields

| Field | Description |
|---|---|
| `spec.vars` | Global variables shared across all steps |
| `steps[].name` | Step display name |
| `steps[].playbook` | Ansible playbook path |
| `steps[].on_failure` | `stop` (default), `skip`, or `retry` |
| `steps[].timeout` | Timeout in seconds (default: 600) |
| `steps[].vars` | Per-step variables (override globals) |
