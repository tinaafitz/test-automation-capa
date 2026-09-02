# Turn a freshly-provisioned ROSA HCP cluster into your own MCE test hub

**Status:** Design / plan only — no code written yet.
**Date:** 2026-09-02
**Repo:** `test-automation-capa`

---

## 1. The goal

Today you have to wait for a shared MCE environment to be free before you can test.
This workflow removes that dependency: **self-serve an MCE hub on demand.**

```
minikube (CAPI/CAPA bootstrap)  ──►  provision a ROSA HCP cluster  ──►  install + configure MCE on it  ──►  your own MCE test hub
        (already works)                    (already works)                    (THE GAP — this doc)
```

Concretely: use your local minikube as the CAPI/CAPA management cluster to provision a
ROSA HCP cluster (exactly what you did this morning), then install MCE on that fresh
cluster and flip it into a CAPI/CAPA management hub — so it becomes your personal MCE
test environment instead of contending for a shared one.

---

## 2. What already exists

The **provisioning half** is complete and working in this repo.

| Capability | Where |
| --- | --- |
| minikube as CAPI/CAPA bootstrap cluster | root `initialize-minikube-capi.yml`, driven by backend `configure_capi()` → `/api/minikube/initialize-capi` (`ui/backend/minikube_routes.py`) |
| clusterctl init + CAPA image load + creds on minikube | `tasks/clusterctl_install_capi.yml` (creates `rosa-creds-secret`, `capa-manager-bootstrap-credentials` on the **minikube** mgmt cluster) |
| Provision a ROSA HCP cluster | `playbooks/create_rosa_hcp_cluster.yml` → `tasks/create_rosa_role_config.yml`, `tasks/create_rosa_network.yml`, control-plane + nodepool waits |
| ROSA CAPA CRs (v1beta2) | `ROSANetwork`, `ROSARoleConfig`, `ROSAControlPlane` (+ `Cluster` / `MachinePool`); refs use `apiGroup` (PR #248) |
| Readiness waits | `tasks/wait_for_rosa_control_plane_ready.yml`, `tasks/wait_for_rosa_network.yml` |
| Front door UI | `ui/frontend/src/pages/MinikubeDashboard.jsx` (localhost:3000/minikube) + `ui/backend/minikube_routes.py` |

The **MCE-configuration half** also exists — but it assumes MCE is *already installed*:

| Capability | Where |
| --- | --- |
| Enable CAPI/CAPA, disable HyperShift on an existing hub | `tasks/enable_capi_capa.yml` (does `oc get mce`, **hard-fails if MCE < 2.8**) |
| Toggle individual MCE components | `tasks/toggle_mce_component.yml`, `tasks/update_multiple_components.yml` |
| Discover MCE name dynamically | `oc get mce -ojsonpath={.items[0].metadata.name}` — do **not** hardcode `multiclusterengine` (PR #252) |
| Component / ACM-version surfacing | `ui/backend/mce_features_routes.py` |
| Create `rosa-creds-secret` (OCM) in `multicluster-engine` | `tasks/create_rosa_creds_secret.yml` |

---

## 3. What's missing (the gap)

**There is no step anywhere in the repo that installs the MCE operator.**

Confirmed: `grep -rln "kind: Subscription|kind: OperatorGroup|kind: MultiClusterEngine"` returns
nothing. Every "MCE" playbook/task today runs against a hub that *already has MCE installed*
(it does `oc get mce` and fails if MCE is absent or < 2.8).

So on a freshly-provisioned ROSA HCP cluster the flow breaks the moment we try to configure MCE —
nothing has installed it, and nothing has put OCM/AWS creds onto the *new* cluster (they only live
on the minikube management cluster today).

The gap is exactly **one new capability**: install MCE (OperatorGroup + Subscription +
`MultiClusterEngine` CR + wait-for-healthy) on the new cluster, wire creds onto it, then chain the
existing `enable_capi_capa.yml`.

---

## 3a. VERIFIED: how the team's 5.0 (pre-GA / RC / dev) MCE is actually sourced

**Confirmed live off the `ci-azure-w36` daily-regression hub (2026-09-02) — this is the real mechanism, not a guess.**

The `latest-5.0` ACM/MCE stream the team currently tests on is a **downstream `acm-d` dev catalog**, NOT the GA `redhat-operators` catalog:

| Operator | CatalogSource (in `openshift-marketplace`) | Image |
| --- | --- | --- |
| MCE | `mce-dev-catalog` | `quay.io:443/acm-d/mce-dev-catalog:latest-5.0` |
| ACM | `acm-dev-catalog` | `quay.io:443/acm-d/acm-dev-catalog:latest-5.0` |

- `sourceType: grpc`, publisher `grpc`. `latest-5.0` is a **moving tag** — it resolved on that hub to MCE CSV **`multicluster-engine.v5.0.0-259`** / MCE CR version **`5.0.0-259`**.
- This maps exactly to the repo's **dormant** `catalog_sources.acmd: "quay.io:443/acm-d"` var in `vars/vars.yml` (defined, never referenced). The scaffolding was built for this path.
- **Install mechanism caveat:** on that hub there are **zero OLM Subscriptions cluster-wide** and no ACM CSV — MCE was installed by the downstream **stolostron/ACM deploy tooling** which creates the `acm-d` CatalogSource and drops the CSV + MCE CR directly (no Subscription object). A plain OLM Subscription against the `acm-d` catalog is the *closest OLM-native equivalent* and should work, but it is NOT byte-for-byte how the regression hub does it.
- **Channels (VERIFIED off the `mce-dev-catalog` packagemanifest on ci-azure-w36):** the acm-d dev catalog **does publish a proper `multicluster-engine` packagemanifest** with per-stream `stable-*` channels — so a plain OLM Subscription against it is fully viable and channel-validatable:
  - `stable-5.0` → `multicluster-engine.v5.0.0-259`  ← **use this for 5.0 / RC**
  - `stable-5.1` → `multicluster-engine.v5.1.0-61`  (this is the **defaultChannel**)
  - `stable-2.8` … `stable-2.17` = older streams
  Pre-GA 5.0 builds use `stable-*` channels (NOT `candidate-*`). Because `defaultChannel` is `stable-5.1`, the Subscription **must set `channel` explicitly** or it silently pulls 5.1. To lock an exact build, set `spec.startingCSV` (e.g. `multicluster-engine.v5.0.0-259`).
- **Prerequisite for the new hub:** `quay.io:443/acm-d` is an **internal/authenticated dev registry**. The freshly-provisioned ROSA HCP cluster will need a **pull secret** for `quay.io:443/acm-d` (and possibly an ICSP/IDMS) before it can pull the catalog image. This is a hard live-test prerequisite.

**Design consequence:** the install task must support a **custom CatalogSource** built from the `acm-d` dev catalog (channel/source parameterized via the existing `catalog_sources` + `acm_repo` vars), pinned to `:latest-5.0` or a specific `:5.0.0-NNN` tag — the GA `stable-2.8`/`redhat-operators` path (below) is kept only as a fallback for GA installs.

---

## 4. Implementation plan

> All paths relative to repo root. **Access to the new hub is via the CAPA-published
> `<cluster_name>-kubeconfig` secret** (found on the minikube mgmt cluster in `capi_namespace`) —
> **not** via `tasks/login_ocp.yml`, because ROSA HCP has no kubeadmin and `login_ocp.yml` is
> hardwired to the pre-existing hub's vars.

### 4.1 Feasibility (verified against the repo)

- **MCE installs on ROSA HCP OpenShift** — ROSA HCP ships OperatorHub with the `redhat-operators`
  CatalogSource in `openshift-marketplace`; MCE subscribes there like any OCP hub.
- **Healthy with HyperShift off + CAPI/CAPA on** — that terminal state is exactly what
  `enable_capi_capa.yml` already drives on the existing hub, so chaining it is consistent with
  tested behavior. A fresh MCE first reconciles `Available` with its default component set, *then*
  the toggle flips it — so the install task must wait for MCE `Available` **before** the toggles run.
- **Creds onto the new hub** — the new hub has none. After login we must create `rosa-creds-secret`
  (OCM) and the AWS bootstrap creds on the new hub in `multicluster-engine`
  (and `ns-rosa-hcp` if that's the CAPI namespace there).

### 4.2 New Ansible tasks

**`tasks/preflight_check_mce_creds.yml`** — runs first. Fails fast if `OCM_CLIENT_ID`,
`OCM_CLIENT_SECRET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` are empty/placeholder.
*This directly prevents the #336-class failure* (empty `OCM_CLIENT_ID` → broken `rosa-creds-secret`).
Mirror the assert/fail + `no_log` style of `tasks/login_ocp.yml`.

**`tasks/get_new_hub_kubeconfig.yml`** — on the minikube context, extract
`oc get secret {{ cluster_name }}-kubeconfig -n {{ capi_namespace }} -o jsonpath='{.data.value}' | base64 -d`,
write to `{{ output_dir }}/{{ cluster_name }}-kubeconfig`, register `new_hub_kubeconfig`, then
`oc --kubeconfig ... whoami` / `get clusterversion` sanity check. (This kubeconfig is the one
unavoidable runtime artifact — analogous to how the repo already writes to `generated-yamls/` /
`output_dir`; keep it out of world-readable / git locations.)

**`tasks/install_mce_operator.yml`** — runs against the new hub (KUBECONFIG already pointed at it).
Supports two source modes via `mce_source_mode` (default `gaCatalog`):

- **`devCatalog`** (the acm-d / 5.0 RC/dev path — see section 3a): first `oc apply` a custom
  `CatalogSource` (`kind: CatalogSource`, `sourceType: grpc`, `image: {{ mce_dev_catalog_image }}`,
  10m registryPoll) named `{{ mce_dev_catalog_name }}` in `openshift-marketplace`, then wait for
  `status.connectionState.lastObservedState == READY`. On timeout it fails with a message that flags
  a **missing `quay.io:443/acm-d` pull secret** (ImagePullBackOff on the catalog pod) as the likely
  cause. The Subscription then points `source: {{ mce_dev_catalog_name }}` with `channel: {{ mce_channel }}`
  set **explicitly** (default channel is `stable-5.1`; for 5.0 use `stable-5.0`) and optional
  `startingCSV: {{ mce_starting_csv }}` to pin an exact build.
- **`gaCatalog`** (default): unchanged GA path below.

1. Discover/validate the MCE channel via
   `oc get packagemanifest multicluster-engine -n openshift-marketplace ...` — fail clearly if
   `mce_channel` isn't offered. Runs in **both** modes: the acm-d dev catalog also publishes a
   `multicluster-engine` packagemanifest, so in `devCatalog` mode this validation runs **after** the
   CatalogSource is READY and is **scoped to the dev catalog** via `-l catalog={{ mce_dev_catalog_name }}`
   (its packagemanifest only appears once the catalog pod is up).
2. Create namespace `multicluster-engine` (idempotent `--dry-run=client -o yaml | oc apply -f -`).
3. Create OperatorGroup (heredoc `oc apply -f -`).
4. Create Subscription (`source=redhat-operators`, `sourceNamespace=openshift-marketplace`,
   `channel={{ mce_channel }}`, `name={{ mce_sub_name }}`, approval `Automatic` by default).
5. Wait for CSV `Succeeded` (retry/until, same style as `clusterctl_install_capi.yml`).
6. Apply the `MultiClusterEngine` CR (`name={{ mce_name }}`).
7. Wait for MCE `status.phase == Available` **and** non-empty `status.currentVersion`.
8. Debug-print the installed version.

### 4.3 New playbook: `playbooks/install_mce_on_provisioned_cluster.yml`

Modeled on `playbooks/configure_mce_environment.yml` (vars_files + `set_fact` env fallbacks +
`include_tasks` chain), pointed at the new hub via the extracted kubeconfig:

1. `vars_files`: `../vars/vars.yml`, `../vars/user_vars.yml`.
2. `set_fact` resolving `cluster_name`, `capi_namespace` (default `ns-rosa-hcp`), `minikube_context`,
   `mce_namespace/channel/catalog_source/name/sub_name`, OCM/AWS creds — via the same
   `lookup('env', ...) | default(VAR, true)` pattern already in `configure_mce_environment.yml`.
3. `preflight_check_mce_creds.yml`.
4. *(optional gate)* `wait_for_rosa_control_plane_ready.yml` on the minikube context
   (guarded by `skip_wait_for_ready`, default false).
5. `get_new_hub_kubeconfig.yml`.
6. `install_mce_operator.yml` — with `environment: { KUBECONFIG: "{{ new_hub_kubeconfig }}" }`.
7. Create creds on the new hub: `create_rosa_creds_secret.yml` (OCM, already targets
   `multicluster-engine`) + inline `oc create secret generic capa-manager-bootstrap-credentials`
   (AWS), all under `KUBECONFIG={{ new_hub_kubeconfig }}`.
8. `enable_capi_capa.yml` under `KUBECONFIG={{ new_hub_kubeconfig }}` — disables HyperShift, enables
   `cluster-api` + `cluster-api-provider-aws`. **Reused unchanged.**
9. Final debug summary (console URL, MCE version, CAPI/CAPA enabled).

> **Design note:** tasks 6–8 must all see the new hub. `enable_capi_capa.yml` uses bare `oc`
> (no `--context`), so setting `KUBECONFIG` at the play/block `environment` level is the correct,
> non-invasive redirect — no edit to the shared task. (Verified `update_multiple_components.yml`
> and `get_mce_component_status.yml` also use bare `oc`.)

### 4.4 Config / vars

Add to `vars/vars.yml` (ACM/MCE section):
- `mce_channel: "stable-2.8"` (satisfies the ≥ 2.8 requirement — a var, not hardcoded)
- `mce_catalog_source: "redhat-operators"`
- `mce_catalog_source_namespace: "openshift-marketplace"`
- `mce_install_plan_approval: "Automatic"`

(`mce_namespace`, `mce_name`, `mce_sub_name` already exist — reuse.)

**devCatalog mode vars** (for the acm-d / 5.0 RC/dev path, section 3a):
- `mce_source_mode: "gaCatalog"` — `gaCatalog | devCatalog`; default keeps the GA behavior.
- `mce_dev_catalog_name: "mce-dev-catalog"` — CatalogSource `metadata.name`.
- `mce_dev_catalog_tag: "latest-5.0"` — moving tag, or pin e.g. `5.0.0-259`.
- `mce_starting_csv: ""` — optional; if set, adds `startingCSV` to the Subscription to lock an exact
  build (e.g. `multicluster-engine.v5.0.0-259`).
- `mce_dev_catalog_image: "{{ catalog_sources[acm_repo].index_image.source }}/mce-dev-catalog:{{ mce_dev_catalog_tag }}"`
  — **derived** from the existing dormant `catalog_sources` / `acm_repo` scaffolding, so setting
  `acm_repo: acmd` yields `quay.io:443/acm-d/mce-dev-catalog:<tag>`. Override directly for a fully
  custom image reference.

For a 5.0 RC/dev run: `mce_source_mode: devCatalog`, `acm_repo: acmd`, `mce_dev_catalog_tag` to
`latest-5.0` (moving) or a pinned `5.0.0-NNN`, and set `mce_channel: stable-5.0` (VERIFIED —
`stable-5.0` → `v5.0.0-259`; the catalog `defaultChannel` is `stable-5.1`, so 5.0 requires setting
this explicitly). Optionally pin `mce_starting_csv: multicluster-engine.v5.0.0-259`. The target
cluster needs a pull secret for `quay.io:443/acm-d`.

Add to `vars/user_vars.yml.example`:
- `MCE_CHANNEL: "stable-2.8"` (optional override)
- Comment: no new-hub username/password needed — access comes from the CAPA
  `<cluster_name>-kubeconfig` secret on the minikube mgmt cluster.

### 4.5 How it chains after provisioning

Runs **after** `playbooks/provision_rosa_hcp_minikube.yml` once ROSAControlPlane is Ready.

> **Prerequisite (one-time setup):** like every playbook in this repo, this one lists
> `../vars/user_vars.yml` in `vars_files`, so that file **must exist** — Ansible errors at
> parse time if it's absent. Create it once from the template and fill in your creds:
> ```bash
> cp vars/user_vars.yml.example vars/user_vars.yml   # then edit in OCM_* / AWS_* / region
> ```
> `vars/user_vars.yml` is gitignored, so your creds are never committed. (This matches the
> convention of all other playbooks in the repo — it is intentionally not made optional here,
> to keep behavior consistent. `vars/vars.yml` now ships empty-string defaults for the
> credential keys so an env-only run reaches the friendly `preflight_check_mce_creds.yml`
> failure instead of an undefined-variable crash — but the `user_vars.yml` file itself must
> still be present.)

```bash
ansible-playbook playbooks/install_mce_on_provisioned_cluster.yml \
  -e cluster_name=<name> \
  -e capi_namespace=ns-rosa-hcp \
  -e minikube_context=<minikube-ctx>
```

New test-suite entry `test-suites/15-install-mce-on-provisioned-cluster.json`
(structure copied from `10-configure-mce-environment.json`): single playbook entry,
`environment: "mce"`, `extra_vars` for `cluster_name` / `capi_namespace` / `minikube_context` /
`mce_channel`, `timeout ~1800`, `stopOnFailure: true`. Run via
`./run-test-suite.py 15-install-mce-on-provisioned-cluster -e cluster_name=...`.

**UI (future, not designed now):** a "Make this my MCE hub" button on `MinikubeDashboard.jsx` →
new endpoint in `ui/backend/provisioning_routes.py` shelling the playbook via `playbook_executor.py`.

### 4.6 Verification (against the new hub)

1. `oc get csv -n multicluster-engine` → MCE CSV `Succeeded`.
2. `oc get mce {{ mce_name }} -o jsonpath='{.status.phase} {.status.currentVersion}'` → `Available`, ≥ 2.8.
3. `cluster-api` + `cluster-api-provider-aws` `enabled: true`; hypershift components `enabled: false`
   (reuse `tasks/get_mce_component_status.yml`).
4. `oc get deploy -n multicluster-engine` → capi/capa controllers Available.
5. `rosa-creds-secret` + AWS secret present in `multicluster-engine`.
6. Optionally re-run `test-suites/05-verify-mce-environment.json` against the new hub.

---

## 4.7 Review-hardening fixes (applied)

Two independent reviews of this workflow surfaced the following issues; all are now fixed:

- **Control-plane wait targeted the wrong cluster (BLOCKER).** The optional
  `wait_for_rosa_control_plane_ready.yml` include (guarded by `skip_wait_for_ready`)
  uses bare, context-less `oc get rosacontrolplane ...`, so it hit whatever kube
  context happened to be active — not the minikube mgmt cluster. Fixed in
  `playbooks/install_mce_on_provisioned_cluster.yml` by adding a
  `kubectl config use-context {{ minikube_context }}` step **immediately before**
  the wait include (same approach as `provision_rosa_hcp_minikube.yml`). The shared
  wait task is left unedited. This context selection runs before the new-hub
  `KUBECONFIG` block, which sets its own `KUBECONFIG` env and therefore overrides
  the active-context selection for all new-hub tasks — no leak.

- **OCM secret logged in plaintext (MAJOR).** The reused
  `tasks/create_rosa_creds_secret.yml` has an internal `debug` task that prints
  `ocm_client_id` / `ocm_client_secret` in plaintext and `oc create secret` shells
  that echo secret values in argv, none with `no_log`. Rather than edit that shared
  task, we set `no_log: true` on the `include_tasks` in the playbook — the include
  and all its inner tasks inherit `no_log`, suppressing the plaintext debug at the
  call site. **Follow-up:** a separate PR should add `no_log` inside the shared task
  itself.

- **Retry budget vs. suite hard-kill (MAJOR).** The runner SIGKILLs each playbook at
  the suite `timeout`. The realistic worst case (control-plane wait 2250s + MCE
  install loops ~3600s gaCatalog / ~4200s devCatalog) far exceeded the old
  `timeout: 1800`, killing healthy-but-slow installs as false failures. Fixed by
  raising `test-suites/15-install-mce-on-provisioned-cluster.json` to
  `timeout: 5400` (90 min), with a `timeout_budget_comment` documenting the sum, and
  by annotating the retry loops in `tasks/install_mce_operator.yml` with their
  per-loop and cumulative budgets so the suite timeout and the loop math are visibly
  reconciled. MCE-Available stays ~30 min max, CSV-Succeeded ~20 min max.

- **devCatalog + default `acm_repo` malformed image (MAJOR).** With the default
  `acm_repo: production`, `catalog_sources.production.index_image.source` is `""`, so
  `mce_dev_catalog_image` renders to `/mce-dev-catalog:<tag>` (empty registry prefix)
  → ImagePullBackOff misdiagnosed as a pull-secret problem. Fixed by an `assert` at
  the start of the devCatalog path in `tasks/install_mce_operator.yml` (gated
  `when: mce_source_mode == 'devCatalog'`) that fails fast if `acm_repo` is not a
  `catalog_sources` key or its `index_image.source` is empty, telling the user to set
  `acm_repo: acmd`.

- **packagemanifest discovery race (MAJOR).** The packagemanifest appears
  seconds-to-minutes after the CatalogSource reports `READY`, so a single no-retry
  query returned empty and tripped channel validation with a bogus "channel not
  available". Fixed by adding `until: mce_available_channels.stdout != ''` with
  `retries: 12`, `delay: 15` (3 min) to the discovery task.

- **Preflight now covers `cluster_name` and `AWS_REGION`.**
  `tasks/preflight_check_mce_creds.yml` previously validated only the four
  credentials. It now also fails fast (with a plain, non-`no_log` message) if
  `cluster_name` is empty (would make the kubeconfig secret name `-kubeconfig` and
  fail late) or `AWS_REGION` is empty (consumed by the AWS bootstrap secret).

## 5. Risks / open questions

1. **Channel/version drift** — `stable-2.8` may not exist / map to < 2.8 in a given catalog.
   *Mitigation:* the install task validates the channel via `packagemanifest` before subscribing.
   **Open:** exact supported channel for the target OCP version.
2. **ROSA-HCP-as-MCE-hub topology** — MCE on ROSA HCP as a *nested* CAPI/CAPA management hub is a
   less-common setup. Whether HyperShift-disabled + CAPI-enabled MCE is fully supported on ROSA HCP
   *specifically* is not verifiable from the repo — stated as an assumption; `enable_capi_capa.yml`
   is our precedent, not a guarantee.
3. **#336-class empty-creds risk** — empty `OCM_CLIENT_ID` silently breaks `rosa-creds-secret` and
   later 403s. *Mitigation:* mandatory `preflight_check_mce_creds.yml`; consider also reusing
   `tasks/preflight_check_ocm_role.yml` against the new hub's creds.
4. **Kubeconfig secret timing/name** — assumes CAPA always emits `<cluster_name>-kubeconfig` in
   `capi_namespace` once ControlPlane is Ready. *Guard:* readiness wait + `whoami` check; fail
   clearly if the secret is absent.
5. **Shared `enable_capi_capa.yml` uses context-less `oc`** — relies on play/block `KUBECONFIG` env
   to redirect. Verified no sub-task hardcodes a context; re-verify on implementation.
6. **Runtime kubeconfig file in `output_dir`** — acceptable artifact; ensure not world-readable and
   in a gitignored location.

---

## 6. Critical files for implementation

- `playbooks/configure_mce_environment.yml` — template for the new playbook's structure
- `tasks/enable_capi_capa.yml` — chained unchanged to make the new hub a CAPI/CAPA hub
- `tasks/clusterctl_install_capi.yml` — secret-creation + wait/retry patterns to mirror
- `tasks/create_rosa_creds_secret.yml` — reused to create `rosa-creds-secret` on the new hub
- `vars/vars.yml` — add `mce_channel` / catalog-source / install-plan vars

---

## 7. Next step

This is design only. Implementation is **not** started. To build it, create the three new tasks +
one playbook + vars above (branch off `main`, PR — never push to main directly), then wire the
test-suite entry, then (later) the UI button.
