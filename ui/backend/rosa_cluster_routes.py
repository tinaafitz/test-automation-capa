"""
ROSA cluster lifecycle routes -- FastAPI router for cluster CRUD operations,
ROSA cluster listing, deletion with agent monitoring, and status queries.

Endpoints moved here from app.py:
  POST   /api/clusters
  GET    /api/clusters/{cluster_id}
  DELETE /api/clusters/{cluster_id}
  GET    /api/rosa/clusters
  DELETE /api/rosa/clusters/{cluster_name}
  GET    /api/clusters                     (list all)
  GET    /api/clusters/{cluster_name}/status

Also contains:
  ClusterConfig                -- Pydantic model for cluster creation
  _wait_for_resource_deletion  -- polling helper with agent monitoring
  _run_deletion_wait_loops     -- multi-resource deletion orchestrator
  _get_rosa_clusters_sync      -- sync helper for ROSA cluster listing
  perform_cluster_deletion     -- background worker for direct-API deletion
"""

import asyncio
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel

from shared_state import jobs, ai_agent_sessions, clusters
from jobs_service import normalize_timestamp, get_agent_stats
from agents_service import init_ai_agents

router = APIRouter()


def _resolve(name: str):
    """Look up *name* via the app module so that unittest.mock.patch on
    ``app.<name>`` takes effect even though the endpoint lives here."""
    app_mod = sys.modules.get("app")
    if app_mod is not None:
        return getattr(app_mod, name)
    return globals()[name]


class ClusterConfig(BaseModel):
    name: str
    version: str = "4.20.0"
    region: str = "us-west-2"
    instance_type: str = "m5.xlarge"
    min_replicas: int = 2
    max_replicas: int = 3
    network_automation: bool = True
    role_automation: bool = False
    availability_zones: List[str] = ["us-west-2a", "us-west-2b"]
    cidr_block: str = "10.0.0.0/16"
    tags: Dict[str, str] = {}

    # Manual network configuration (used when network_automation=False)
    subnets: Optional[List[str]] = None
    vpc_id: Optional[str] = None

    # Manual IAM role configuration (used when role_automation=False)
    installer_role_arn: Optional[str] = None
    support_role_arn: Optional[str] = None
    worker_role_arn: Optional[str] = None
    oidc_id: Optional[str] = None

    # Operator roles
    ingress_arn: Optional[str] = None
    image_registry_arn: Optional[str] = None
    storage_arn: Optional[str] = None
    network_arn: Optional[str] = None
    kube_cloud_controller_arn: Optional[str] = None
    node_pool_management_arn: Optional[str] = None
    control_plane_operator_arn: Optional[str] = None
    kms_provider_arn: Optional[str] = None


def _wait_for_resource_deletion(
    resource_type: str, resource_name: str, namespace: str,
    job_id: str, timeout_seconds: int = 1200, poll_interval: int = 10,
):
    """Poll for K8s resource deletion with real-time agent monitoring.

    Unlike Ansible shell tasks (which buffer stdout), this runs directly in Python
    so every poll result is immediately fed to the AI agent for detection.

    Returns True if the resource was deleted, False if timed out.
    """
    import time as _time

    retries = timeout_seconds // poll_interval
    log_prefix = f"[DELETE-WAIT] {resource_type}/{resource_name}"

    def log_and_feed(msg):
        """Log to job, console, and feed to agent."""
        jobs[job_id].setdefault("logs", []).append(msg)
        print(msg)
        agent_session = ai_agent_sessions.get(job_id)
        if agent_session and agent_session.get("monitor"):
            try:
                agent_session["monitor"].process_line(msg)
            except Exception:
                pass

    # Emit agent context so the agent knows which resource we're watching
    context_line = f'#AGENT_CONTEXT: resource_name={resource_name} namespace={namespace} resource_type={resource_type}'
    log_and_feed(context_line)

    for i in range(retries):
        try:
            result = subprocess.run(
                ["oc", "get", resource_type, resource_name, "-n", namespace],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                output = result.stderr + result.stdout
                if any(s in output.lower() for s in ["not found", "notfound", "no resources found"]):
                    msg = f"{resource_type} {resource_name} deleted successfully"
                    log_and_feed(msg)
                    return True
                # Connection error or other failure — warn but keep retrying
                msg = f"WARNING: oc get failed unexpectedly (rc={result.returncode}): {output.strip()}"
                log_and_feed(msg)
            else:
                # Resource still exists
                retries_left = retries - i - 1
                msg = f"FAILED - RETRYING: [localhost]: Wait for {resource_type} {resource_name} deletion to complete ({retries_left} retries left)."
                log_and_feed(msg)
        except subprocess.TimeoutExpired:
            log_and_feed(f"WARNING: oc get timed out for {resource_type}/{resource_name}")
        except Exception as e:
            log_and_feed(f"WARNING: Error checking {resource_type}/{resource_name}: {e}")

        _time.sleep(poll_interval)

    log_and_feed(f"Timed out waiting for {resource_type} {resource_name} deletion after {timeout_seconds}s")
    return False


def _run_deletion_wait_loops(job_id: str, cluster_name: str, namespace: str,
                             delete_network: bool = True, delete_roles: bool = True):
    """Run Python-native wait loops for deletion with real-time agent monitoring.

    Called after the Ansible playbook initiates deletions (with wait_for_deletion=false).
    Runs the same wait sequence as the Ansible task file but in Python so each poll
    is immediately visible to the AI agent.
    """
    import time as _time

    network_name = f"{cluster_name}-network"
    role_config_name = f"{cluster_name}-roles"

    def log_msg(msg):
        jobs[job_id].setdefault("logs", []).append(msg)
        print(f"[DELETE-WAIT] {msg}")

    # Phase 1: Wait for ROSAControlPlane deletion (20 min)
    log_msg(f"Waiting for ROSAControlPlane {cluster_name} deletion...")
    rcp_deleted = _resolve("_wait_for_resource_deletion")(
        "rosacontrolplane", cluster_name, namespace, job_id,
        timeout_seconds=1200, poll_interval=10,
    )
    if rcp_deleted:
        log_msg(f"ROSAControlPlane successfully deleted: {cluster_name}")
    else:
        log_msg(f"ROSAControlPlane {cluster_name} still exists after timeout — failing")
        return False

    # Phase 2: Wait for ROSANetwork and ROSARoleConfig in parallel-ish
    # (Network first since it takes longer, RoleConfig after)
    results = {}

    if delete_network:
        log_msg(f"Waiting for ROSANetwork {network_name} deletion...")
        results["network"] = _resolve("_wait_for_resource_deletion")(
            "rosanetwork", network_name, namespace, job_id,
            timeout_seconds=1800, poll_interval=10,
        )
        if results["network"]:
            log_msg(f"ROSANetwork successfully deleted: {network_name}")
        else:
            log_msg(f"ROSANetwork {network_name} still exists after timeout — failing")
            return False

    if delete_roles:
        log_msg(f"Waiting for ROSARoleConfig {role_config_name} deletion...")
        results["roles"] = _resolve("_wait_for_resource_deletion")(
            "rosaroleconfig", role_config_name, namespace, job_id,
            timeout_seconds=600, poll_interval=10,
        )
        if results["roles"]:
            log_msg(f"ROSARoleConfig successfully deleted: {role_config_name}")
        else:
            log_msg(f"ROSARoleConfig {role_config_name} timed out (non-fatal)")

    return True


@router.post("/api/clusters")
async def create_cluster(config: ClusterConfig, background_tasks: BackgroundTasks):
    """Create a new ROSA cluster"""

    # Generate unique IDs
    cluster_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())

    # Store cluster config
    clusters[cluster_id] = {
        "id": cluster_id,
        "config": config.dict(),
        "job_id": job_id,
        "created_at": datetime.now(),
        "status": "creating",
    }

    # Create job
    jobs[job_id] = {
        "id": job_id,
        "cluster_id": cluster_id,
        "status": "pending",
        "progress": 0,
        "message": "Job queued for execution",
        "started_at": datetime.now(),
        "logs": [],
    }

    # Use the new automated ROSA HCP playbook
    playbook = "playbooks/create_rosa_hcp_automated.yaml"

    # Map frontend config to playbook extra_vars
    extra_vars = {
        "cluster_name": config.name,
        "openshift_version": config.version,
        "aws_region": config.region,
        "create_rosa_roles": config.role_automation,
        "create_rosa_network": config.network_automation,
        "network_cidr": config.cidr_block,
        "availability_zone_count": len(config.availability_zones),
    }

    # Initialize AI agents for provisioning monitoring
    init_ai_agents(job_id)

    # Start background task
    asyncio.create_task(
        _resolve("run_playbook_background")(playbook, extra_vars, job_id, "Create ROSA HCP Cluster")
    )

    return {
        "success": True,
        "cluster_id": cluster_id,
        "job_id": job_id,
        "message": "Cluster creation started",
        "status": "pending",
    }


@router.get("/api/clusters/{cluster_id}")
async def get_cluster(cluster_id: str):
    """Get cluster information"""
    if cluster_id not in clusters:
        raise HTTPException(status_code=404, detail="Cluster not found")

    cluster = clusters[cluster_id]
    job_id = cluster["job_id"]

    # Get job status
    job_status = jobs.get(job_id, {})

    return {"success": True, "cluster": cluster, "job": job_status}


@router.delete("/api/clusters/{cluster_id}")
async def delete_cluster(cluster_id: str, background_tasks: BackgroundTasks):
    """Delete a ROSA cluster"""
    if cluster_id not in clusters:
        raise HTTPException(status_code=404, detail="Cluster not found")

    cluster = clusters[cluster_id]
    job_id = str(uuid.uuid4())

    # Create deletion job
    jobs[job_id] = {
        "id": job_id,
        "cluster_id": cluster_id,
        "status": "pending",
        "progress": 0,
        "message": "Cluster deletion queued",
        "started_at": datetime.now(),
        "logs": [],
    }

    # Start deletion task
    delete_vars = {
        "cluster_name": cluster["config"].get("name", ""),
        "capi_namespace": cluster["config"].get("capi_namespace", "ns-rosa-hcp"),
    }
    init_ai_agents(job_id)
    asyncio.create_task(
        _resolve("run_playbook_background")("playbooks/delete_rosa_hcp_cluster.yml", delete_vars, job_id, "Delete ROSA HCP Cluster")
    )

    return {"success": True, "job_id": job_id, "message": "Cluster deletion started"}


@router.get("/api/rosa/clusters")
async def get_rosa_clusters(context: str = None):
    """Get actual ROSA HCP clusters — offloads to thread pool so subprocess calls don't block the event loop."""
    return await asyncio.to_thread(_resolve("_get_rosa_clusters_sync"), context)


def _get_rosa_clusters_sync(context: str = None):
    """Get actual ROSA HCP clusters (sync — runs in thread pool to avoid blocking event loop)."""
    # No CAPI filtering — show all ROSA HCP clusters from rosa CLI
    capi_cluster_names = None

    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from agents.ocm_client import get_ocm_client
        ocm = get_ocm_client()
        rosa_clusters, err = ocm.list_clusters()

        if not err and rosa_clusters:
            cluster_list = []
            for cluster in rosa_clusters:
                cluster_name = cluster.get("name", "unknown")
                if capi_cluster_names is not None and cluster_name not in capi_cluster_names:
                    continue
                state = cluster.get("status", "unknown")
                cluster_list.append({
                    "name": cluster_name,
                    "status": "ready" if state == "ready" else state,
                    "region": cluster.get("region", "N/A"),
                    "created": cluster.get("created"),
                    "version": cluster.get("version", "N/A"),
                    "namespace": "ns-rosa-hcp",
                    "progress": 100 if state == "ready" else 50 if state == "installing" else 0,
                })

            return {
                "success": True,
                "clusters": cluster_list,
                "count": len(cluster_list),
                "filtered_by_context": context,
            }

        # Fallback: Fetch ROSAControlPlane resources from all namespaces
        result = subprocess.run(
            ["oc", "get", "rosacontrolplane", "--all-namespaces", "-o", "json"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return {
                "success": False,
                "clusters": [],
                "message": f"Error fetching ROSA clusters: {result.stderr}",
            }

        data = json.loads(result.stdout)
        cluster_list = []

        for item in data.get("items", []):
            metadata = item.get("metadata", {})
            spec = item.get("spec", {})
            status = item.get("status", {})

            # Determine cluster status
            ready = status.get("ready", False)
            conditions = status.get("conditions", [])
            deletion_timestamp = metadata.get("deletionTimestamp")

            # Check if cluster is being deleted
            is_deleting = deletion_timestamp is not None
            is_uninstalling = False
            has_error = False
            error_message = None
            error_reason = None

            # Check conditions for uninstalling or error state
            for condition in conditions:
                if condition.get("type") in [
                    "Ready",
                    "ROSAControlPlaneReady",
                    "RosaControlPlaneReady",
                ]:
                    reason = condition.get("reason", "").lower()
                    message = condition.get("message", "")

                    # Check if uninstalling
                    if (
                        reason == "uninstalling"
                        or "uninstalling" in message.lower()
                        or "deleting" in message.lower()
                    ):
                        is_uninstalling = True
                        break

                    # Check for actual errors (but not during deletion or normal provisioning)
                    if condition.get("status") == "False" and not is_deleting:
                        # These reasons indicate normal provisioning states, not errors
                        provisioning_reasons = [
                            "installing",
                            "validating",
                            "provisioning",
                            "waiting",
                            "creating",
                            "notpaused",
                        ]
                        # Only mark as error if reason is NOT a normal provisioning state
                        if reason not in provisioning_reasons:
                            has_error = True
                            error_message = message  # Store the full error message
                            error_reason = condition.get("reason", "Unknown")

            # Determine status string
            if is_deleting or is_uninstalling:
                cluster_status = "uninstalling"
            elif ready:
                cluster_status = "ready"
            elif has_error:
                cluster_status = "failed"
            else:
                cluster_status = "provisioning"

            # Calculate progress for provisioning clusters
            progress = 0
            if cluster_status == "provisioning":
                # Base progress on conditions that are ready
                progress_stages = {
                    "InfrastructureReady": 20,
                    "NetworkReady": 40,
                    "ControlPlaneReady": 60,
                    "ROSAControlPlaneReady": 60,
                    "RosaControlPlaneReady": 60,
                    "Ready": 100,
                }

                # Check which conditions are true
                for condition in conditions:
                    condition_type = condition.get("type", "")
                    condition_status = condition.get("status", "")

                    if condition_status == "True" and condition_type in progress_stages:
                        stage_progress = progress_stages[condition_type]
                        if stage_progress > progress:
                            progress = stage_progress

                # If no conditions are set yet, estimate based on creation time
                if progress == 0:
                    from datetime import datetime, timezone

                    try:
                        created_str = metadata.get("creationTimestamp", "")
                        if created_str:
                            created_time = datetime.fromisoformat(
                                created_str.replace("Z", "+00:00")
                            )
                            elapsed = (datetime.now(timezone.utc) - created_time).total_seconds()
                            # Estimate 5-10 minutes for initial provisioning, cap at 15%
                            progress = min(15, int((elapsed / 60) * 2.5))
                    except:
                        progress = 10  # Default starting progress
            elif cluster_status == "ready":
                progress = 100
            elif cluster_status == "failed":
                progress = 0

            # Extract cluster information
            cluster_info = {
                "name": metadata.get("name", "unknown"),
                "status": cluster_status,
                "region": spec.get("region", "N/A"),
                "created": metadata.get("creationTimestamp"),
                "domain_prefix": spec.get("domainPrefix", "N/A"),
                "version": spec.get("version", "N/A"),
                "namespace": metadata.get("namespace", "default"),
                "progress": progress,
                "error_message": error_message,
                "error_reason": error_reason,
            }

            # Only include clusters that are in 'ready' state (fully provisioned ROSA HCP clusters)
            if cluster_status == "ready":
                cluster_list.append(cluster_info)

        # Sort by creation time (newest first)
        cluster_list.sort(key=lambda x: normalize_timestamp(x.get("created")), reverse=True)

        return {
            "success": True,
            "clusters": cluster_list,
            "count": len(cluster_list),
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "clusters": [],
            "message": "Request to OpenShift timed out",
        }
    except Exception as e:
        import traceback

        print(f"❌ [ROSA-CLUSTERS] Error: {str(e)}")
        print(traceback.format_exc())
        return {
            "success": False,
            "clusters": [],
            "message": f"Error fetching ROSA clusters: {str(e)}",
        }


def perform_cluster_deletion(job_id: str, cluster_name: str, namespace: str):
    """Background task to perform actual cluster deletion (sync, called via asyncio.to_thread)"""
    import time as _time

    deleted_resources = []
    errors = []

    def log_delete(msg):
        """Write to stdout, logs array, and feed to AI agent monitor."""
        jobs[job_id]["stdout"] += msg + "\n"
        jobs[job_id].setdefault("logs", []).append(msg)
        print(f"[DELETE-CLUSTER] {msg}")
        # Feed to AI agent for real-time issue detection
        agent_session = ai_agent_sessions.get(job_id)
        if agent_session and agent_session.get("monitor"):
            try:
                agent_session["monitor"].process_line(msg)
            except Exception:
                pass

    try:
        jobs[job_id]["progress"] = 5
        jobs[job_id]["message"] = f"Deleting cluster {cluster_name}..."

        # Step 1: Delete Cluster and ROSAControlPlane together
        try:
            log_delete(f"🗑️ Deleting cluster/{cluster_name} and rosacontrolplane/{cluster_name}")
            log_delete(f"ℹ️  This triggers cascading deletion of all dependent resources")

            # Feed agent context for deletion monitoring
            agent_session = ai_agent_sessions.get(job_id)
            if agent_session and agent_session.get("monitor"):
                try:
                    agent_session["monitor"].process_line(
                        f"#AGENT_CONTEXT: resource_name={cluster_name} namespace={namespace} resource_type=rosacontrolplane"
                    )
                except Exception:
                    pass

            result = subprocess.run(
                [
                    "oc",
                    "delete",
                    "-n",
                    namespace,
                    f"cluster/{cluster_name}",
                    f"rosacontrolplane/{cluster_name}",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            jobs[job_id]["progress"] = 15

            if result.returncode == 0:
                deleted_resources.append(f"cluster/{cluster_name}")
                deleted_resources.append(f"rosacontrolplane/{cluster_name}")
                log_delete(f"✅ Deletion initiated for cluster/{cluster_name} and rosacontrolplane/{cluster_name}")
                log_delete(f"✅ Kubernetes will cascade delete MachinePools automatically")

                # Step 2: Wait for the cluster to be fully deleted
                log_delete(f"⏳ Waiting for cluster deletion to complete...")
                jobs[job_id]["message"] = "Waiting for cluster deletion..."

                max_wait_time = 1200
                check_interval = 10
                elapsed_time = 0

                while elapsed_time < max_wait_time:
                    _time.sleep(check_interval)
                    elapsed_time += check_interval

                    # Update progress (15% to 70% during wait)
                    jobs[job_id]["progress"] = min(15 + int(elapsed_time / max_wait_time * 55), 70)

                    check_result = subprocess.run(
                        ["oc", "get", "cluster", cluster_name, "-n", namespace],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )

                    if check_result.returncode != 0 and "not found" in check_result.stderr.lower():
                        log_delete(f"✅ cluster/{cluster_name} successfully deleted after {elapsed_time}s")
                        log_delete(f"✅ ROSA cluster has been removed from AWS/OCM")
                        break
                    else:
                        status_line = f"⏳ Still waiting for cluster deletion... ({elapsed_time}s elapsed)"
                        # Feed every check to the agent (detects stuck deletions)
                        log_delete(status_line) if elapsed_time % 60 == 0 else None
                        # Always feed agent even if not logging to UI
                        agent_session = ai_agent_sessions.get(job_id)
                        if agent_session and agent_session.get("monitor"):
                            try:
                                status_output = check_result.stdout.strip()
                                agent_session["monitor"].process_line(
                                    f"FAILED - RETRYING: cluster/{cluster_name} deletion still pending ({elapsed_time}s) {status_output}"
                                )
                            except Exception:
                                pass

                if elapsed_time >= max_wait_time:
                    errors.append(
                        f"Timeout waiting for cluster/{cluster_name} to delete after {max_wait_time}s"
                    )
                    log_delete(f"⚠️ Timeout waiting for deletion after {max_wait_time}s, but deletion may still complete in background")
            else:
                if "not found" not in result.stderr.lower():
                    errors.append(f"Failed to delete resources: {result.stderr}")
                    log_delete(f"❌ Error deleting resources: {result.stderr}")

        except subprocess.TimeoutExpired:
            errors.append(f"Timeout deleting cluster and rosacontrolplane")
            log_delete(f"❌ Timeout deleting cluster/{cluster_name} and rosacontrolplane/{cluster_name}")
        except Exception as e:
            errors.append(f"Error deleting cluster and rosacontrolplane: {str(e)}")
            log_delete(f"❌ Error: {str(e)}")

        # Step 3: Clean up remaining ROSA resources
        jobs[job_id]["progress"] = 75
        jobs[job_id]["message"] = "Cleaning up remaining resources..."
        log_delete(f"")
        log_delete(f"🧹 Checking for remaining resources to clean up...")

        cleanup_resources = [
            ("rosanetwork", f"{cluster_name}-network"),
            ("rosaroleconfig", f"{cluster_name}-roles"),
            ("rosamachinepool", cluster_name),
            ("rosacluster", cluster_name),
        ]

        # Resources that need wait loops so the agent can detect and fix issues
        # (e.g., CloudFormation DELETE_FAILED blocking ROSANetwork deletion)
        wait_timeouts = {
            "rosanetwork": 1800,    # 30 minutes — CloudFormation stack deletion
            "rosaroleconfig": 600,  # 10 minutes — IAM role cleanup
        }

        # Phase 1: Initiate deletion for all resources
        resources_to_wait = []
        for i, (resource_type, resource_name) in enumerate(cleanup_resources):
            try:
                check_result = subprocess.run(
                    ["oc", "get", resource_type, resource_name, "-n", namespace],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if check_result.returncode == 0:
                    log_delete(f"🧹 Cleaning up {resource_type}/{resource_name}")

                    # Feed agent context for this resource
                    agent_session = ai_agent_sessions.get(job_id)
                    if agent_session and agent_session.get("monitor"):
                        try:
                            agent_session["monitor"].process_line(
                                f"#AGENT_CONTEXT: resource_name={resource_name} namespace={namespace} resource_type={resource_type}"
                            )
                        except Exception:
                            pass

                    result = subprocess.run(
                        [
                            "oc",
                            "delete",
                            resource_type,
                            resource_name,
                            "-n",
                            namespace,
                            "--ignore-not-found=true",
                            "--wait=false",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )

                    if result.returncode == 0:
                        deleted_resources.append(f"{resource_type}/{resource_name}")
                        log_delete(f"✅ Deletion initiated for {resource_type}/{resource_name}")
                        # Track resources that need wait loops
                        if resource_type in wait_timeouts:
                            resources_to_wait.append((resource_type, resource_name))
                    else:
                        log_delete(f"⚠️ Failed to delete {resource_type}/{resource_name}: {result.stderr}")
                else:
                    log_delete(f"✅ {resource_type}/{resource_name} already deleted (cascade)")

            except Exception as e:
                log_delete(f"⚠️ Error cleaning up {resource_type}/{resource_name}: {str(e)}")

        # Phase 2: Wait for critical resources with agent monitoring
        # This allows the agent to detect DELETE_FAILED CloudFormation stacks
        # and trigger VPC dependency cleanup (orphaned security groups, ENIs, etc.)
        for resource_type, resource_name in resources_to_wait:
            max_wait = wait_timeouts[resource_type]
            check_interval = 15
            elapsed = 0

            log_delete(f"")
            log_delete(f"⏳ Waiting for {resource_type}/{resource_name} deletion...")
            jobs[job_id]["message"] = f"Waiting for {resource_type}/{resource_name} deletion..."

            # Feed agent context so it knows which resource we're monitoring
            agent_session = ai_agent_sessions.get(job_id)
            if agent_session and agent_session.get("monitor"):
                try:
                    agent_session["monitor"].process_line(
                        f"#AGENT_CONTEXT: resource_name={resource_name} namespace={namespace} resource_type={resource_type}"
                    )
                except Exception:
                    pass

            while elapsed < max_wait:
                _time.sleep(check_interval)
                elapsed += check_interval

                check_result = subprocess.run(
                    ["oc", "get", resource_type, resource_name, "-n", namespace],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if check_result.returncode != 0:
                    # Resource is gone
                    log_delete(f"✅ {resource_type}/{resource_name} successfully deleted after {elapsed}s")
                    break

                # Resource still exists — feed status to agent for issue detection
                status_output = check_result.stdout.strip()
                status_line = f"FAILED - RETRYING: {resource_type}/{resource_name} deletion still pending ({elapsed}s) {status_output}"

                # Log to UI every 60s, but always feed to agent
                if elapsed % 60 == 0:
                    log_delete(f"⏳ Still waiting for {resource_type}/{resource_name} deletion... ({elapsed}s elapsed)")

                agent_session = ai_agent_sessions.get(job_id)
                if agent_session and agent_session.get("monitor"):
                    try:
                        agent_session["monitor"].process_line(status_line)
                    except Exception:
                        pass

                # Update progress within this wait phase
                base_progress = 80
                progress_range = 15  # 80-95% for wait phase
                wait_progress = min(int(elapsed / max_wait * progress_range), progress_range)
                jobs[job_id]["progress"] = base_progress + wait_progress

            else:
                # Timeout — resource still exists
                log_delete(f"⚠️ {resource_type}/{resource_name} still exists after {max_wait}s timeout")
                errors.append(f"{resource_type}/{resource_name} deletion timed out after {max_wait}s")

            # Post-deletion CloudFormation verification for ROSANetwork
            # The K8s resource may be gone but the CF stack could be DELETE_FAILED
            # with orphaned VPC/SGs costing ~$139/mo
            if resource_type == "rosanetwork":
                stack_name = f"{cluster_name}-rosa-network-stack"
                region = "us-west-2"
                log_delete(f"🔍 Verifying CloudFormation stack {stack_name} cleanup...")
                try:
                    import boto3
                    cf_client = boto3.client(
                        "cloudformation",
                        region_name=region,
                        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", ""),
                        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
                    )
                    try:
                        response = cf_client.describe_stacks(StackName=stack_name)
                        cf_status = response["Stacks"][0]["StackStatus"]
                        if cf_status == "DELETE_COMPLETE":
                            log_delete(f"✅ CloudFormation stack {stack_name} confirmed deleted")
                        elif cf_status == "DELETE_FAILED":
                            log_delete(f"⚠️ CloudFormation stack DELETE_FAILED: {stack_name} — orphaned AWS resources detected")
                            log_delete(f"CloudFormation stack DELETE_FAILED: {stack_name}")
                            # Feed to agent for remediation
                            agent_session = ai_agent_sessions.get(job_id)
                            if agent_session and agent_session.get("monitor"):
                                try:
                                    agent_session["monitor"].process_line(
                                        f"CloudFormation stack DELETE_FAILED: {stack_name}"
                                    )
                                except Exception:
                                    pass
                            errors.append(f"CloudFormation stack {stack_name} DELETE_FAILED — manual cleanup may be needed")
                        elif cf_status == "DELETE_IN_PROGRESS":
                            log_delete(f"⏳ CloudFormation stack {stack_name} still deleting ({cf_status})")
                        else:
                            log_delete(f"ℹ️ CloudFormation stack {stack_name} status: {cf_status}")
                    except cf_client.exceptions.ClientError as e:
                        if "does not exist" in str(e):
                            log_delete(f"✅ CloudFormation stack {stack_name} confirmed deleted")
                        else:
                            log_delete(f"⚠️ CloudFormation check failed: {e}")
                except ImportError:
                    log_delete(f"⚠️ boto3 not available — cannot verify CloudFormation cleanup")
                    log_delete(f"   Check manually: aws cloudformation describe-stacks --stack-name {stack_name}")
                except Exception as e:
                    log_delete(f"⚠️ CloudFormation verification error: {e}")

        # Final status
        jobs[job_id]["progress"] = 100
        jobs[job_id]["agent_stats"] = get_agent_stats(job_id)

        # Log agent summary if agents were active
        agent_stats = jobs[job_id]["agent_stats"]
        if agent_stats.get("enabled"):
            log_delete(f"")
            log_delete(f"🤖 AI Agent Summary:")
            log_delete(f"   Issues detected: {agent_stats.get('issues_detected', 0)}")
            log_delete(f"   Interventions: {agent_stats.get('interventions', 0)}")
            if agent_stats.get('interventions', 0) > 0:
                log_delete(f"   ✅ Agent auto-fixed {agent_stats['interventions']} issue(s) during deletion")

        if deleted_resources:
            message = (
                f"✅ Successfully deleted cluster {cluster_name}\n\nDeleted resources:\n"
                + "\n".join(f"  - {r}" for r in deleted_resources)
            )
            if errors:
                message += f"\n\n⚠️ Warnings:\n" + "\n".join(f"  - {e}" for e in errors)

            jobs[job_id]["status"] = "completed"
            jobs[job_id]["return_code"] = 0
            log_delete(f"")
            log_delete(message)
            jobs[job_id]["message"] = f"✅ Cluster {cluster_name} deleted"
            jobs[job_id]["completed_at"] = datetime.now().isoformat()
        else:
            message = f"❌ Failed to delete cluster {cluster_name}"
            if errors:
                message += f"\n\nErrors:\n" + "\n".join(f"  - {e}" for e in errors)

            jobs[job_id]["status"] = "failed"
            jobs[job_id]["return_code"] = 1
            log_delete(message)
            jobs[job_id]["message"] = f"❌ Failed to delete {cluster_name}"
            jobs[job_id]["completed_at"] = datetime.now().isoformat()

    except Exception as e:
        import traceback

        print(f"❌ [DELETE-CLUSTER] Error: {str(e)}")
        print(traceback.format_exc())
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["return_code"] = 1
        jobs[job_id]["stderr"] += f"❌ Error: {str(e)}\n{traceback.format_exc()}"
        jobs[job_id].setdefault("logs", []).append(f"❌ Error: {str(e)}")
        jobs[job_id]["progress"] = 100
        jobs[job_id]["message"] = f"❌ Error deleting {cluster_name}"
        jobs[job_id]["completed_at"] = datetime.now().isoformat()


@router.delete("/api/rosa/clusters/{cluster_name}")
async def delete_rosa_cluster(
    cluster_name: str, request: Request, background_tasks: BackgroundTasks
):
    """Delete a ROSA HCP cluster and all its resources"""
    import time
    import asyncio

    try:
        body = await request.json()
        namespace = body.get("namespace")

        if not namespace:
            return {"success": False, "message": "Namespace is required"}

        print(f"🗑️ [DELETE-CLUSTER] Deleting cluster: {cluster_name} in namespace: {namespace}")

        # Create job entry immediately
        job_id = f"delete-cluster-{cluster_name}-{int(time.time())}"
        jobs[job_id] = {
            "id": job_id,
            "description": f"Delete ROSA HCP Cluster: {cluster_name}",
            "status": "running",
            "progress": 0,
            "message": f"Deleting cluster {cluster_name}...",
            "created_at": datetime.now(),
            "task_file": None,
            "playbook_file": None,
            "stdout": "",
            "stderr": "",
            "logs": [],
            "return_code": None,
        }

        # Initialize AI agents for deletion monitoring
        init_ai_agents(job_id)

        # Start deletion in background (use asyncio.to_thread to avoid blocking event loop)
        asyncio.create_task(asyncio.to_thread(_resolve("perform_cluster_deletion"), job_id, cluster_name, namespace))

        # Return immediately
        return {
            "success": True,
            "message": f"Cluster deletion started for {cluster_name}",
            "job_id": job_id,
        }

    except Exception as e:
        import traceback

        print(f"❌ [DELETE-CLUSTER] Error: {str(e)}")
        print(traceback.format_exc())
        return {
            "success": False,
            "message": f"Error deleting cluster: {str(e)}",
        }


@router.get("/api/clusters")
async def list_clusters():
    """List all ROSA HCP clusters with their status"""
    try:
        result = subprocess.run(
            ["kubectl", "get", "rosacontrolplane", "-n", "ns-rosa-hcp", "-o", "json"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return {
                "success": False,
                "clusters": [],
                "message": f"Error fetching clusters: {result.stderr}",
            }

        data = json.loads(result.stdout)

        cluster_list = []
        for item in data.get("items", []):
            metadata = item.get("metadata", {})
            spec = item.get("spec", {})
            status = item.get("status", {})

            # Determine overall status
            ready = status.get("ready", False)
            conditions = status.get("conditions", [])

            # Check if resource is being deleted
            is_deleting = metadata.get("deletionTimestamp") is not None

            # Get error message if any
            error_message = None
            for condition in conditions:
                if condition.get("type") == "Ready" and condition.get("status") == "False":
                    error_message = condition.get("message", "Unknown error")

            # Calculate progress percentage
            progress = 0
            if ready:
                progress = 100
            else:
                # Check sub-resources
                network_ready = any(
                    c.get("type") == "ROSANetworkReady" and c.get("status") == "True"
                    for c in conditions
                )
                role_ready = any(
                    c.get("type") == "ROSARoleConfigReady" and c.get("status") == "True"
                    for c in conditions
                )
                cp_valid = any(
                    c.get("type") == "ROSAControlPlaneValid" and c.get("status") == "True"
                    for c in conditions
                )

                if cp_valid:
                    progress += 25
                if role_ready:
                    progress += 25
                if network_ready:
                    progress += 25
                if ready:
                    progress += 25

            region = spec.get("region", "N/A")
            cluster_info = {
                "name": metadata.get("name"),
                "namespace": metadata.get("namespace", "ns-rosa-hcp"),
                "created_at": metadata.get("creationTimestamp"),
                "domain_prefix": spec.get("domainPrefix", "N/A"),
                "version": spec.get("version", "N/A"),
                "region": region,
                "ready": ready,
                "progress": progress,
                "status": (
                    "deleting"
                    if is_deleting
                    else ("ready" if ready else ("failed" if error_message else "provisioning"))
                ),
                "error_message": error_message,
                "console_url": status.get("consoleURL"),
                "api_url": (
                    f"https://api.{spec.get('domainPrefix', 'unknown')}.{region}.openshiftapps.com"
                    if spec.get("domainPrefix")
                    else None
                ),
            }

            cluster_list.append(cluster_info)

        # Sort by creation time (newest first)
        cluster_list.sort(key=lambda x: normalize_timestamp(x.get("created_at")), reverse=True)

        return {
            "success": True,
            "clusters": cluster_list,
            "count": len(cluster_list),
        }

    except Exception as e:
        import traceback

        print(f"❌ [LIST-CLUSTERS] Error: {str(e)}")
        print(traceback.format_exc())
        return {
            "success": False,
            "clusters": [],
            "message": f"Error listing clusters: {str(e)}",
        }


@router.get("/api/clusters/{cluster_name}/status")
async def get_cluster_status(cluster_name: str):
    """Get detailed status for a specific cluster"""
    try:
        # Get ROSAControlPlane
        result = subprocess.run(
            ["kubectl", "get", "rosacontrolplane", cluster_name, "-n", "ns-rosa-hcp", "-o", "json"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            raise HTTPException(status_code=404, detail=f"Cluster {cluster_name} not found")

        cp_data = json.loads(result.stdout)

        # Get ROSANetwork if it exists
        network_data = None
        network_result = subprocess.run(
            [
                "kubectl",
                "get",
                "rosanetwork",
                f"{cluster_name}-network",
                "-n",
                "ns-rosa-hcp",
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if network_result.returncode == 0:
            network_data = json.loads(network_result.stdout)

        # Get ROSARoleConfig if it exists
        role_data = None
        role_result = subprocess.run(
            [
                "kubectl",
                "get",
                "rosaroleconfig",
                f"{cluster_name}-roles",
                "-n",
                "ns-rosa-hcp",
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if role_result.returncode == 0:
            role_data = json.loads(role_result.stdout)

        return {
            "success": True,
            "control_plane": cp_data,
            "network": network_data,
            "roles": role_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback

        print(f"❌ [GET-CLUSTER-STATUS] Error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error getting cluster status: {str(e)}")
