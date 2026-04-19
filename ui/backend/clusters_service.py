"""
Clusters service module -- FastAPI router for cluster-related endpoints.

Endpoints moved here from app.py:
  POST   /api/clusters                        -- create_cluster
  GET    /api/clusters                        -- list_clusters
  GET    /api/clusters/{cluster_id}           -- get_cluster
  DELETE /api/clusters/{cluster_id}           -- delete_cluster
  GET    /api/clusters/{cluster_name}/status  -- get_cluster_status
  GET    /api/rosa/clusters                   -- get_rosa_clusters
  DELETE /api/rosa/clusters/{cluster_name}    -- delete_rosa_cluster
  GET    /api/rosa/status                     -- get_rosa_status

Heavy helper functions (_get_rosa_clusters_sync, _get_rosa_status_sync,
perform_cluster_deletion, etc.) remain in app.py.  Route handlers here
are thin wrappers that resolve those helpers at call time via the ``app``
module so that ``unittest.mock.patch("app.<name>")`` keeps working.
"""

import asyncio
import json
import sys
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from shared_state import jobs, clusters

router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────────────────

def _resolve(name: str):
    """Look up *name* via the ``app`` module so that unittest.mock.patch on
    ``app.<name>`` takes effect even though the endpoint lives here."""
    app_mod = sys.modules.get("app")
    if app_mod is not None:
        return getattr(app_mod, name)
    return globals()[name]


# ── Cluster CRUD endpoints ──────────────────────────────────────────────

@router.post("/api/clusters")
async def create_cluster(request: Request, background_tasks: BackgroundTasks):
    """Create a new ROSA cluster.

    Accepts a JSON body matching the ClusterConfig Pydantic model defined
    in app.py.  We resolve the model at call time to avoid circular imports.
    """
    _app = sys.modules.get("app")
    ClusterConfig = getattr(_app, "ClusterConfig")
    body = await request.json()
    config = ClusterConfig(**body)

    init_ai_agents = _resolve("init_ai_agents")
    run_playbook_background = _resolve("run_playbook_background")
    _asyncio = _resolve("asyncio")

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
    _asyncio.create_task(
        run_playbook_background(playbook, extra_vars, job_id, "Create ROSA HCP Cluster")
    )

    return {
        "cluster_id": cluster_id,
        "job_id": job_id,
        "message": "Cluster creation started",
        "status": "pending",
    }


@router.get("/api/clusters")
async def list_clusters():
    """List all ROSA HCP clusters with their status"""
    _subprocess = _resolve("subprocess")
    normalize_timestamp = _resolve("normalize_timestamp")

    try:
        result = _subprocess.run(
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

        print(f"\u274c [LIST-CLUSTERS] Error: {str(e)}")
        print(traceback.format_exc())
        return {
            "success": False,
            "clusters": [],
            "message": f"Error listing clusters: {str(e)}",
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

    return {"cluster": cluster, "job": job_status}


@router.delete("/api/clusters/{cluster_id}")
async def delete_cluster(cluster_id: str, background_tasks: BackgroundTasks):
    """Delete a ROSA cluster"""
    if cluster_id not in clusters:
        raise HTTPException(status_code=404, detail="Cluster not found")

    cluster = clusters[cluster_id]
    job_id = str(uuid.uuid4())

    init_ai_agents = _resolve("init_ai_agents")
    run_playbook_background = _resolve("run_playbook_background")
    _asyncio = _resolve("asyncio")

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
    _asyncio.create_task(
        run_playbook_background("playbooks/delete_rosa_hcp_cluster.yml", delete_vars, job_id, "Delete ROSA HCP Cluster")
    )

    return {"job_id": job_id, "message": "Cluster deletion started"}


@router.get("/api/clusters/{cluster_name}/status")
async def get_cluster_status(cluster_name: str):
    """Get detailed status for a specific cluster"""
    _subprocess = _resolve("subprocess")

    try:
        # Get ROSAControlPlane
        result = _subprocess.run(
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
        network_result = _subprocess.run(
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
        role_result = _subprocess.run(
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

        print(f"\u274c [GET-CLUSTER-STATUS] Error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error getting cluster status: {str(e)}")


# ── ROSA endpoints ──────────────────────────────────────────────────────

@router.get("/api/rosa/status")
async def get_rosa_status():
    """Check ROSA CLI authentication status -- offloads to thread pool."""
    _get_rosa_status_sync = _resolve("_get_rosa_status_sync")
    return await asyncio.to_thread(_get_rosa_status_sync)


@router.get("/api/rosa/clusters")
async def get_rosa_clusters(context: str = None):
    """Get actual ROSA HCP clusters -- offloads to thread pool so subprocess calls don't block the event loop."""
    _get_rosa_clusters_sync = _resolve("_get_rosa_clusters_sync")
    return await asyncio.to_thread(_get_rosa_clusters_sync, context)


@router.delete("/api/rosa/clusters/{cluster_name}")
async def delete_rosa_cluster(
    cluster_name: str, request: Request, background_tasks: BackgroundTasks
):
    """Delete a ROSA HCP cluster and all its resources"""
    import time

    init_ai_agents = _resolve("init_ai_agents")
    perform_cluster_deletion = _resolve("perform_cluster_deletion")
    _asyncio = _resolve("asyncio")

    try:
        body = await request.json()
        namespace = body.get("namespace")

        if not namespace:
            return {"success": False, "message": "Namespace is required"}

        print(f"\U0001f5d1\ufe0f [DELETE-CLUSTER] Deleting cluster: {cluster_name} in namespace: {namespace}")

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
        _asyncio.create_task(asyncio.to_thread(perform_cluster_deletion, job_id, cluster_name, namespace))

        # Return immediately
        return {
            "success": True,
            "message": f"Cluster deletion started for {cluster_name}",
            "job_id": job_id,
        }

    except Exception as e:
        import traceback

        print(f"\u274c [DELETE-CLUSTER] Error: {str(e)}")
        print(traceback.format_exc())
        return {
            "success": False,
            "message": f"Error deleting cluster: {str(e)}",
        }
