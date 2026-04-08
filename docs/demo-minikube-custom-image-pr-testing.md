# Demo: Minikube Environment - Testing PRs with Custom CAPA Images

**Topic:** Using a local Minikube cluster to test CAPA pull requests by deploying a custom controller image, applying updated CRDs, and provisioning a real ROSA HCP cluster - all from the UI

**Target audience:** Team, management, stakeholders

**Runtime:** 3-4 minutes

---

## The Hook (15 seconds)

> "When someone opens a CAPA pull request - say, adding log forwarding support or fixing a CloudFormation bug - how do you test it before merging? You used to need a full MCE environment. Now you can spin up a Minikube cluster on your laptop, point it at the PR's container image, and provision a real ROSA HCP cluster in AWS - all from the UI."

---

## The Problem (45-60 seconds)

> "Here's what testing a CAPA PR used to look like:"

1. Wait for CI to build the PR image (or build it yourself locally)
2. Get access to an MCE test environment - shared, often busy, sometimes broken
3. Manually patch the CAPA controller deployment with the PR image
4. Apply any updated CRDs from the PR branch by hand
5. Set up RBAC for any new resource types the PR introduces
6. Provision a cluster and hope you patched everything correctly
7. If something's wrong, debug whether it's your PR, the environment, or your patching

> "The turnaround time to test a single PR was hours. And if the shared environment was in use or broken, you were blocked entirely."

---

## The Demo (2-3 minutes)

### Step 1: Switch to the Minikube Dashboard

In the sidebar, click the **Minikube** tab. The dashboard switches to a purple theme - visually distinct from the blue MCE dashboard.

> "The Minikube dashboard is a separate environment. Your own local cluster - no contention with the team."

### Step 2: Create or Select a Minikube Cluster

In the **Environments** section, either select an existing cluster or click **"+ Add"** to create a new one:

- Enter a cluster name (e.g., `sat-minikube-test`)
- Click **"Add Cluster"** - the cluster appears with a "Creating..." status

> "One click to create a fresh Minikube cluster with CAPI/CAPA pre-configured."

### Step 3: Set Custom CAPA Image

Click **"Set Custom CAPA Image"** in the sidebar. This is the key section for PR testing.

Check **"Use Custom CAPA Image"** - three fields appear with a purple left border:

| Field | Example | What it does |
|-------|---------|-------------|
| **Image Repository** | `quay.io/username/cluster-api-aws-controller` | The container image built from the PR |
| **Image Tag** | `pr-5786` | The PR number or branch tag |
| **CRD Location (URL)** | `https://github.com/serngawy/cluster-api-provider-aws/tree/logforward/api/v1beta2` | GitHub URL to updated CRD definitions from the PR branch |

> "Three fields. The image repo and tag from the PR's CI build, and optionally the CRD location if the PR changes any API types."

Click **"Apply Changes"**.

### Step 4: Watch the Configuration Run

The playbook executes with live output streaming:

1. Generates AWS credentials
2. Initializes clusterctl with ROSA support
3. Waits for CAPI and CAPA controllers to be ready
4. **Applies updated CRDs** from the PR branch (if CRD location provided)
5. **Creates RBAC** for any new resource types (e.g., NodeadmConfig)
6. **Patches the CAPA controller deployment** with the custom image
7. Waits for the controller to restart with the new image
8. **Verifies** the running image matches what was specified

> "It handles everything - CRDs, RBAC, image patching, rollout verification. The output shows exactly what image the controller is running."

The output will show:
```
Custom CAPA Image Configuration:
  Repository: quay.io/username/cluster-api-aws-controller
  Tag: pr-5786

CAPA controller patched with custom image
Image: quay.io/username/cluster-api-aws-controller:pr-5786

CAPA controller running with image: quay.io/username/cluster-api-aws-controller:pr-5786
```

### Step 5: Provision a Cluster with the PR Image

Click **"Provision"** in the sidebar. The same provisioning form from the MCE dashboard appears, but now it's running against your Minikube cluster with the custom CAPA image.

- Fill in cluster name, version, region
- Click **"Preview & Provision"** - review the YAML
- Click **"Provision Now"**

> "This provisions a real ROSA HCP cluster in AWS - using the controller code from the PR. Same form, same YAML preview, same live monitoring. The only difference is it's running on your local Minikube with the custom image."

### Step 6: Verify the PR Works

Once provisioned, the cluster appears in the **ROSA HCP Clusters** table. You can:

- See it's running with the correct version
- Delete it to test the deletion path (also using the PR's controller code)
- Check the AI agent stats for any issues during provisioning/deletion

> "End-to-end PR validation: provision, verify, delete - all with the PR's code, all from the UI, all on your own local environment."

---

## Why Minikube? (if asked)

| | MCE Environment | Minikube |
|--|----------------|----------|
| **Setup time** | Request access, wait for availability | `minikube start` - 2 minutes |
| **Contention** | Shared with team | Your own isolated cluster |
| **Custom images** | Requires cluster-admin on shared env | Full control |
| **Cost** | Runs on expensive OCP cluster | Runs on your laptop |
| **CAPA version** | Tied to MCE release | Any image, any branch, any PR |

> "Minikube gives you a zero-contention, zero-cost environment to test any CAPA change before it hits the team."

---

## What the Playbook Does Behind the Scenes (if asked)

When you apply a custom image, the automation:

1. **`clusterctl init --infrastructure aws`** - installs CAPI + CAPA with ROSA support enabled (`EXP_ROSA=true`)
2. **Applies CRDs** from the PR branch - handles new/changed API types
3. **Creates RBAC** - adds ClusterRole and ClusterRoleBinding for new resource types (e.g., `nodeadmconfigs`) so the controller has permissions
4. **`kubectl set image`** - patches the `capa-controller-manager` deployment in `capa-system` namespace
5. **`kubectl rollout status`** - waits for the new pod to be running
6. **Verifies** - reads back the deployment's container image to confirm the patch took effect

---

## The Kicker (15 seconds)

> "Before: wait for a shared environment, manually patch, hope you got the RBAC right. Now: three fields, click Apply, provision a cluster. A developer can validate their CAPA PR end-to-end in the time it used to take just to get access to a test environment."

---

## Recording Tips

- **Show the sidebar switch** from MCE (blue) to Minikube (purple) - the visual theme change makes it clear these are different environments
- **Pause on the three custom image fields** - this is the money shot for the PR testing story
- **Show the playbook output** confirming the custom image is running - the "CAPA controller running with image: ..." line is the proof
- **If you have a real PR image available**, use it for the demo with a real tag like `pr-5786` - more convincing than placeholder text
- For a quick recording, you can show: sidebar switch + custom image form + Apply + configuration output (2-3 min). Skip the actual provisioning since it takes 17 min
- Target runtime: **3-4 minutes**
