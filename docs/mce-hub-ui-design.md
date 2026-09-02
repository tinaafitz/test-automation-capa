# UI Design: "Make this my MCE hub" (Install MCE on a provisioned ROSA HCP cluster)

Design spec for the UI on top of the PR #261 backend workflow. Hand-off doc for a
frontend engineer. Desktop-first, information-dense, matches existing conventions.

> **Ground-truth verified against merged main (PR #261, merge commit `46ed4ab`).** The two
> workflow files DO exist on `origin/main` — the design was drafted against a stale local
> checkout, now reconciled. The corrections below OVERRIDE any conflicting assumption later in
> this doc (notably the `mce_source_mode` radio and `stable-5.0` default in §3b, which are NOT
> backed by the suite contract). Every "reuse this" citation still points at present UI code.
>
> **Confirmed suite 15 contract** (`test-suites/15-install-mce-on-provisioned-cluster.json`):
> - `playbook: playbooks/install_mce_on_provisioned_cluster.yml`, `test_case_id: RHACM4K-61722`, `timeout: 7200`.
> - Real `extra_vars` (ONLY these four): `cluster_name` (""), `capi_namespace` ("ns-rosa-hcp"),
>   `minikube_context` ("minikube"), `mce_channel` ("stable-2.8"). **There is NO `mce_source_mode`
>   in the suite** — it's a playbook-level var (gaCatalog default). For a first UI cut, expose the
>   four suite vars; treat GA-vs-dev-catalog + `stable-5.0` as a later enhancement, and keep the
>   acm-d pull-secret guardrail (§5) conditional on the user choosing a `stable-5.x` channel.
> - **Success outputs are PRINT-ONLY** (a `debug` summary at playbook.yml:129-141: `Console:`,
>   `MCE version:`, `CAPI/CAPA: enabled`). No machine-readable registered return facts → the
>   success card (§3d) MUST parse these from the log stream. Console URL comes from
>   `oc ... whoami --show-console` (playbook.yml:122-124); MCE version from `mce_current_version`.
> - **Real task names for log→phase mapping (§3c)** — top-level tasks are:
>   "Preflight - validate OCM and AWS credentials" → "Wait for ROSA control plane to be ready" →
>   "Get the new hub kubeconfig" → "Install the MCE operator on the new hub" →
>   "Create rosa-creds-secret (OCM) on the new hub" / "Create AWS bootstrap credentials secret" →
>   "Enable CAPI/CAPA and disable HyperShift on the new hub". Map these substrings to phase rows.
> - Default `mce_channel` is **`stable-2.8`** (GA), NOT `stable-5.0`. Prefill the field with the
>   suite default and let the user change it.

---

## 1. UX Overview

- **Mental model: cluster-centric.** The unit of work is a single provisioned ROSA HCP
  cluster row. "Make this my MCE hub" is a *per-row action on that cluster*, not a global
  page-level button. This mirrors how Delete already works today (per-row trash icon +
  confirm panel in `RosaHcpClustersSection.jsx:688-696`, `:705-736`).
- **Primary navigation:** existing sidebar. The action lives inside the **ROSA HCP Clusters**
  section of the **Minikube dashboard** (`MinikubeDashboard.jsx:1899-1900`,
  `<RosaHcpClustersSection theme="minikube" />`). No new route.
- **Guardrails before commitment.** This is a 30-110 min (timeout 7200s) irreversible-ish
  operation. Two hard gates surface *before* launch: (a) cluster readiness (only offer on a
  `Ready` ROSAControlPlane), and (b) a creds/pull-secret preflight. Never let the user start
  a doomed 30+ min run.
- **Long-run-first progress design.** Because this is long, the design treats live-log tail +
  phase indicators + cancel as first-class, reusing the proven abortable long-poll loop that
  Delete already uses (`RosaHcpClustersSection.jsx:295-405`) and the incremental `?since=`
  cursor from WorkflowBuilder (`WorkflowBuilder.jsx:1189-1223`).
- **One in-flight hub build at a time.** Like the delete flow, a running "make hub" job binds
  the section (disable other rows' hub buttons while one is running); resume-on-remount so a
  refresh doesn't orphan the run (`RosaHcpClustersSection.jsx:436-534`).

---

## 2. Per-cluster action states

The hub button reads each cluster row and renders one of these states. Cluster readiness comes
from the row's `status` field already fetched by `fetchClusters()`
(`RosaHcpClustersSection.jsx:127-141`; ROSAControlPlane rows with `status`, `version`, `age`).

| State | Condition | Control | Behavior |
|---|---|---|---|
| **Eligible** | `cluster.status === 'ready'` (ROSAControlPlane Ready) AND not already a hub AND no hub-build running | Solid "Make this my MCE hub" button | Opens pre-run config panel |
| **Not ready** | `status === 'provisioning'` / anything != ready | Button disabled + tooltip "Cluster must be Ready" | Reuse status-dot logic `:668-673` |
| **Preflight-blocked** | Eligible, but creds/pull-secret check failed | Button enabled but pre-run panel shows a blocking warning; Launch disabled | See §5 |
| **Running** | A hub-build job is in flight for this cluster | Button → "Building hub… (12m)" spinner; other rows' buttons disabled | Live progress panel (§3), Cancel available |
| **Succeeded** | Job completed | Row shows an "MCE hub" badge + version; button → "Open console" link | Success card (§3) |
| **Failed** | Job failed/cancelled | Row shows failed badge; button → "Retry" | Error card + copyable logs, reuse `:895-914` |
| **Already a hub** | Row detected as MCE-enabled | Badge "MCE hub • CAPI/CAPA" + "Open console"; hide "Make hub" | Idempotent — re-run allowed via kebab |

**Readiness read.** Add a small helper `isClusterReady(cluster)` → `cluster.status === 'ready'`.
This is the ONLY gate that enables the button; the deeper creds check happens in the pre-run
panel (§5), not on the row, so we don't block the whole row on an async check.

---

## 3. Interaction flow / wireframe

### 3a. The row (add one action to the existing table)

Insert into the actions cell that currently holds only the delete icon
(`RosaHcpClustersSection.jsx:688-696`):

```
ROSA HCP Clusters                                              [ ⟳ Refresh ]
┌──────────────┬───────────┬──────┬──────────┬─────────┬──────────────┬───────────────────────────┐
│ Name         │ Status    │ Type │ Created  │ Version │ Provider     │ Actions                   │
├──────────────┼───────────┼──────┼──────────┼─────────┼──────────────┼───────────────────────────┤
│ my-hcp-01    │ ● ready   │ ROSA │ 02 Sep   │ 4.19    │ AWS (usw2)   │ [★ Make this my MCE hub] 🗑│
│ my-hcp-02    │ ● prov…   │ ROSA │ 02 Sep   │ 4.19    │ AWS (usw2)   │ [★ Make hub] (disabled)  🗑│  ← tooltip: must be Ready
│ hub-alpha    │ ● ready   │ ROSA │ 01 Sep   │ 4.19    │ AWS (usw2)   │ [MCE hub • CAPI/CAPA ✓] 🗑 │  ← already a hub, badge + Open console
└──────────────┴───────────┴──────┴──────────┴─────────┴──────────────┴───────────────────────────┘
```

- Button: purple, matches `theme="minikube"` colors already computed in `getThemeColors()`
  (`RosaHcpClustersSection.jsx:36-60`, `buttonBg`/`buttonBgHover`). Icon: `StarIcon` (or
  `RocketLaunchIcon`, both already imported project-wide via heroicons).
- Disabled state reuses the same disabled treatment as the Refresh button (`:613-618`).

### 3b. Pre-run config + preflight panel (inline, not a modal library)

Follow the existing inline-panel convention — the delete confirm renders as an inline card
below the table (`RosaHcpClustersSection.jsx:705-736`), NOT a portal Dialog. Do the same here:
a single `clusterPendingHub` state object (mirror of `clusterPendingDeletion` at `:77`, `:210-212`)
drives an inline card.

```
┌─ Make "my-hcp-01" your MCE test hub ──────────────────────────────────────────┐
│ ★  This installs + configures MultiCluster Engine and enables CAPI/CAPA.       │
│    Estimated 30–110 min. You can cancel, but a partial install may need cleanup.│
│                                                                                 │
│  PREFLIGHT                                                                       │
│   ✓ OCM credentials present          ✓ AWS credentials present                  │
│   ⚠ acm-d pull secret NOT found  — required for devCatalog / stable-5.0 (§5)    │
│                                                                                 │
│  CONFIGURATION                                                                   │
│   Cluster name       [ my-hcp-01              ]  (prefilled from row, read-only-ish)
│   CAPI namespace     [ ns-rosa-hcp            ]  (default)                       │
│   Minikube context   [ sat-minikube-test  ▾  ]  (prefilled from credentials)    │
│   MCE source         (•) GA catalog   ( ) Dev catalog (acm-d)                    │
│   MCE channel        [ stable-5.0         ▾  ]  (shown when Dev catalog chosen)  │
│                                                                                 │
│  ⚠ Dev catalog / stable-5.0 requires the acm-d pull secret. Fix before launch.  │
│                                                                                 │
│                        [ Cancel ]   [ ★ Launch hub build ]  ← disabled if blocked│
└─────────────────────────────────────────────────────────────────────────────┘
```

Field → `extra_vars` mapping (confirm keys against merged suite 15):

| Field | extra_var | Source of default |
|---|---|---|
| Cluster name | `cluster_name` | `cluster.name` from the row |
| CAPI namespace | `capi_namespace` | default `ns-rosa-hcp` (matches delete flow default `:267`) |
| Minikube context | `minikube_context` | from `/api/credentials` → `minikubeCluster`/`clusterName` (same fetch used at `:107-109`, `:256-258`) |
| MCE source | `mce_source_mode` | radio: `gaCatalog` (default) / `devCatalog` |
| MCE channel | `mce_channel` | select, shown only for devCatalog; default `stable-5.0` for RC/dev |

- **Source ↔ channel coupling:** when `mce_source_mode = gaCatalog`, hide the channel select and
  the acm-d warning. When `devCatalog`, reveal channel + the acm-d pull-secret guardrail.
- Launch button disabled while any preflight item is ✗ (creds) or while devCatalog is selected
  and the acm-d pull secret is missing.

### 3c. Long-running progress view (the important one)

On Launch, POST to `/api/ansible/run-playbook` and enter the running state. Reuse the delete
flow's abortable poll loop wholesale (`RosaHcpClustersSection.jsx:295-405`) but with a longer
`maxAttempts` (7200s timeout → budget ~130 min) and phase parsing. Render an inline results card
modeled on the deletion results card (`:739-914`).

```
┌─ Building MCE hub on "my-hcp-01"… ───────────────────  ⏱ 00:42:17   [ ⛔ Cancel ]┐
│  Phases                                                                          │
│   ✓ Preflight (creds, pull secret)        ▸ 00:31                                │
│   ✓ Install MCE operator                  ▸ 06:12                                │
│   ⟳ Configure MCE (MultiClusterEngine CR) ▸ running…    ← blue pulse             │
│   ○ Enable CAPI / CAPA                                                           │
│   ○ Verify hub ready                                                             │
│                                                                                 │
│  [ ●───────●───────◍───────○───────○ ]  3/5   ← minimap, reuse WorkflowBuilder   │
│                                             step-dot minimap (:1846-1879)        │
│                                                                                 │
│  Playbook Output                                             [ 📋 Copy ]         │
│  ┌───────────────────────────────────────────────────────────────────────────┐ │
│  │ TASK [Install MCE operator] ***                          (cyan)            │ │
│  │ ok: [localhost]                                          (green)           │ │
│  │ changed: [localhost] => subscription created            (yellow)          │ │
│  │ ▋  ← live cursor while running                                             │ │
│  └───────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

- **Live log tail:** reuse the dark terminal panel + auto-scroll + line colorization from
  `StepOutputPanel` (`WorkflowBuilder.jsx:425-511`) — it already colorizes `TASK [`, `ok:`,
  `changed:`, `fatal:/FAILED`, `PLAY RECAP`, `skipping:` and renders the blinking `▋` cursor
  while running. Fetch incrementally with `/api/jobs/{id}/logs?since=<cursor>` and the
  `logsData.total` cursor bookkeeping (`WorkflowBuilder.jsx:1189-1223`) so a 100-min log
  doesn't re-transfer every poll. Poll interval 3s (same as WorkflowBuilder `:1242`).
- **Phase indicators:** derive phases from `TASK [...]` markers in the log stream (cheap,
  no backend change) — map known task-name substrings ("Install MCE", "Configure MCE",
  "Enable CAPI", "Enable CAPA", "Verify") to the 5 phase rows. Phase status styling reuses the
  `SortableStep` status color map (pending/running/completed/failed) at `WorkflowBuilder.jsx:119-155`.
- **Minimap:** the dot-and-connector strip at `WorkflowBuilder.jsx:1846-1879` maps 1:1 to phases.
- **Cancel:** reuse the Abort button + `POST /api/jobs/{id}/cancel` + `AbortController.abort()`
  exactly as the delete flow does (`RosaHcpClustersSection.jsx:751-767`; cancel endpoint
  `jobs_service.py:292-314`). Label it "Cancel hub build" and warn that a partial MCE install
  may require manual cleanup.
- **Resume on remount:** copy the running-job discovery pattern (`RosaHcpClustersSection.jsx:436-534`)
  but match on `description.includes('Make MCE hub')` instead of `'Delete ROSA HCP'`, so a
  browser refresh mid-build re-attaches to the live job.

### 3d. Success state

```
┌─ ✅ MCE hub ready on "my-hcp-01" ────────────────────────────────────────────┐
│  MCE version: 2.9.0 (5.0.0-259)      CAPI ✓ enabled     CAPA ✓ enabled         │
│  Console:  https://console-openshift-console.apps.my-hcp-01…  [ ↗ Open ] [📋]  │
│  Duration: 47m 12s                                                             │
│  ▸ View full playbook output                                                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

- On success: set an "MCE hub" badge on the row, flip the row's action to "Open console",
  and call `fetchClusters()` to refresh (same post-success refresh the delete flow does at
  `:349`, `:511`).
- Console URL / MCE version / CAPI-CAPA flags come from the playbook's final output (parse from
  logs, or from suite 15's registered return facts if PR #261 exposes them — confirm). If not
  machine-readable, fall back to showing the console link only when parseable and always keep
  "View full playbook output".

---

## 4. Component mapping (reuse vs. new)

| Concern | Reuse | Source (file:line) |
|---|---|---|
| Per-row action button + disabled style | Refresh/Delete button patterns | `RosaHcpClustersSection.jsx:611-621`, `:688-696` |
| Row status dot (ready/provisioning) | status-dot span | `RosaHcpClustersSection.jsx:668-673` |
| Theme colors (minikube purple) | `getThemeColors()` | `RosaHcpClustersSection.jsx:36-62` |
| Pre-run inline confirm/config card | delete confirm card + `clusterPendingDeletion` state | `RosaHcpClustersSection.jsx:77`, `:210-212`, `:705-736` |
| Job launch POST + response `{success, job_id}` | delete launch | `RosaHcpClustersSection.jsx:273-291`; endpoint `ansible_routes.py:930-977` |
| Abortable long-poll loop (status+logs) | delete poll loop, `AbortController` | `RosaHcpClustersSection.jsx:225-227`, `:295-405` |
| Incremental log cursor `?since=` | WorkflowBuilder `pollJobCompletion` | `WorkflowBuilder.jsx:1189-1223` |
| Live colorized log terminal + auto-scroll + `▋` | `StepOutputPanel` | `WorkflowBuilder.jsx:425-511` |
| Phase status colors | `SortableStep` statusStyles/icons | `WorkflowBuilder.jsx:119-155` |
| Phase minimap dots+connectors | step minimap | `WorkflowBuilder.jsx:1846-1879` |
| Cancel button + `/cancel` | delete Abort button | `RosaHcpClustersSection.jsx:751-767`; `jobs_service.py:292-314` |
| Resume-on-remount for running job | delete resume effect | `RosaHcpClustersSection.jsx:436-534` |
| Results card (running/success/fail) + copy | deletion results card | `RosaHcpClustersSection.jsx:739-914` |
| Task Summary logging | `addToRecent` / `updateRecentOperationStatus` | `RosaHcpClustersSection.jsx:33`, `:241-249` |
| Credentials read (context default) | `/api/credentials` fetch | `RosaHcpClustersSection.jsx:107-109`, `:256-258` |

**New (small):**
- `isClusterReady(cluster)` helper + hub-state derivation per row.
- Pre-run config form (5 fields) with source↔channel coupling — plain inputs matching the
  existing form styling in `WorkflowBuilder` config panel (`:284-330`).
- Phase-derivation from `TASK [...]` log lines (pure function; no backend change).
- Preflight fetch (see §5) — thin call, ideally a dedicated endpoint if PR #261 added one.

### Concrete insertion points

1. **Row button** — in the actions `<td>` at `RosaHcpClustersSection.jsx:688-696`, add the
   "Make this my MCE hub" button *before* the delete `<button>`, gated on `isClusterReady` and
   hub state.
2. **State** — alongside the deletion state block (`RosaHcpClustersSection.jsx:73-83`), add
   `clusterPendingHub`, `hubResults`, `isBuildingHub`, `activeHubJobId` (ref), and a
   `hubAbortController` ref — 1:1 with the existing deletion equivalents.
3. **Handlers** — add `handleMakeHub(cluster)` (opens config card), `executeMakeHub(cluster, cfg)`
   (launch + poll), modeled on `handleDeleteCluster` (`:210-212`) / `executeDeleteCluster`
   (`:215-426`).
4. **Pre-run card** — render below the table next to the delete confirm card, gated on
   `clusterPendingHub` (mirror of `:705-736`).
5. **Results card** — render below, gated on `hubResults` (mirror of `:739-914`), swapping the
   delete-specific agent panel for the phase list + minimap.
6. **Mount is unchanged** — the section already renders at `MinikubeDashboard.jsx:1899-1900`.

**Launch payload (confirm keys with merged suite 15):**
```jsonc
POST /api/ansible/run-playbook
{
  "playbook": "playbooks/install_mce_on_provisioned_cluster.yml",
  "description": "Make MCE hub: my-hcp-01",   // "Make MCE hub" prefix drives resume-match
  "extra_vars": {
    "cluster_name": "my-hcp-01",
    "capi_namespace": "ns-rosa-hcp",
    "minikube_context": "sat-minikube-test",
    "mce_source_mode": "gaCatalog",           // or "devCatalog"
    "mce_channel": "stable-5.0"               // only when devCatalog
  }
}
```
> Alternative: `POST /api/test-suites/run {suite_name: "15-install-mce-on-provisioned-cluster"}`
> (`test_suite_routes.py:77`). Prefer the direct playbook POST for per-cluster extra_vars — the
> suite path doesn't cleanly pass per-row `cluster_name`/context. The generic WorkflowBuilder
> can already run suite 15, but with no purpose-built UX; this design is the purpose-built path.

### Illustrative snippet — the key control (row button)

```jsx
// Inside the actions <td>, before the existing delete button (RosaHcpClustersSection.jsx:688)
const ready = cluster.status === 'ready';
const isHub = cluster.mceHub;                 // derive from row detection
const buildingThis = isBuildingHub && activeHubJobId.current === cluster.name;

{isHub ? (
  <a href={cluster.consoleUrl} target="_blank" rel="noreferrer"
     className="inline-flex items-center gap-1 text-sm font-medium text-purple-700">
    <StarIcon className="h-4 w-4" /> MCE hub • CAPI/CAPA ✓
  </a>
) : (
  <button
    onClick={() => setClusterPendingHub(cluster)}
    disabled={!ready || isBuildingHub}
    title={!ready ? 'Cluster must be Ready' : 'Install + configure MCE and enable CAPI/CAPA'}
    className="inline-flex items-center gap-1.5 px-3 py-1.5 mr-3 text-sm font-medium text-white rounded disabled:opacity-50"
    style={ready && !isBuildingHub ? { backgroundColor: colors.buttonBg } : {}}
  >
    {buildingThis
      ? (<><ArrowPathIcon className="h-4 w-4 animate-spin" /> Building hub…</>)
      : (<><StarIcon className="h-4 w-4" /> Make this my MCE hub</>)}
  </button>
)}
```

---

## 5. UX guardrails: creds preflight + acm-d pull secret

Both are **pre-launch blockers** — surfaced in the pre-run panel (§3b) so the user never starts
a 30-110 min run that the playbook would hard-fail fast anyway.

- **Creds preflight (OCM + AWS).** The merged playbook hard-fails fast via a preflight when
  `OCM_CLIENT_ID`/`OCM_CLIENT_SECRET` or AWS creds are empty/placeholder. Do the equivalent
  check in the UI *before* enabling Launch. Preferred: a dedicated preflight endpoint from
  PR #261 (confirm) returning `{ocm: ok, aws: ok, pullSecret: present}`. If none exists, fall
  back to `/api/credentials` (already used in this file at `:107`, `:144`, `:256`) to verify the
  values are non-empty/non-placeholder. Render as the two ✓/✗ rows in the panel; if either is ✗,
  disable Launch and link to the Credentials/Environments section
  (`MinikubeDashboard.jsx:1912-1952`, `MCEEnvironmentSelector`).
- **acm-d pull secret (dev / RC builds).** For `mce_source_mode = devCatalog` or
  `mce_channel = stable-5.0`, the acm-d pull secret is a prerequisite (dev catalog
  `quay.io:443/acm-d/mce-dev-catalog`). Show the ⚠ line only in that branch and disable Launch
  until it's confirmed present. This prevents the classic "operator install stalls pulling from
  acm-d" failure ~10 min into an otherwise-good run. For `gaCatalog`, hide this entirely — GA
  redhat-operators needs no acm-d secret.

**Copy for the blocked state:** "Dev catalog / stable-5.0 requires the acm-d pull secret on the
target cluster. Add it (or switch to GA catalog) before launching — the install will otherwise
stall pulling the dev catalog image." Keep the exact channel/registry jargon; the audience is
the CAPA team.

---

## Open questions for the implementing engineer (confirm against merged PR #261)
1. Exact merged names: `playbooks/install_mce_on_provisioned_cluster.yml` and
   `test-suites/15-install-mce-on-provisioned-cluster.json` (neither present on current `main`).
2. Exact `extra_vars` keys and whether `mce_source_mode`/`mce_channel` are the real names.
3. Does the playbook register machine-readable return facts (console URL, MCE version,
   CAPI/CAPA enabled) for the success card, or must the UI parse them from logs?
4. Is there a dedicated preflight/creds-check endpoint, or should the UI reuse `/api/credentials`?
5. Confirm the `TASK [...]` names for the 5 phases so log→phase mapping is exact.
