"""
Cluster Actions / Feature Action Engine service module -- FastAPI router for
cluster-actions and cluster-specs endpoints.

Endpoints moved here from app.py:
  GET    /api/cluster-actions/features
  GET    /api/cluster-actions/features/{suite_id}
  POST   /api/cluster-actions/execute
  GET    /api/cluster-actions/history
  POST   /api/cluster-actions/provision
  GET    /api/cluster-actions/discover
  GET    /api/cluster-actions/cluster/{cluster_name}/status
  GET    /api/cluster-specs
  GET    /api/cluster-specs/{spec_id}
  POST   /api/cluster-specs/plan
  POST   /api/cluster-specs/execute
  POST   /api/cluster-specs/save

Also contains:
  Feature registry wrappers (_load_feature_registry_full, _load_feature_registry, etc.)
  CLUSTER_FEATURE_REGISTRY, _FEATURE_INDEX -- backward-compat module-level variables
  ClusterActionRequest     -- Pydantic request model
  Action history helpers   -- _load_action_history, _save_action_history, _record_action
  Per-cluster locking      -- _cluster_locks, _get_cluster_lock
  Spec helpers             -- SPECS_DIR, _find_spec_file, _resolve_spec_to_plan
"""

import asyncio
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime
from typing import Dict, Optional

import yaml
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel
from pathlib import Path as _Path

from capa_core import (
    FeatureRegistry as _CoreFeatureRegistry,
    ClusterAutomationSpec as _CoreClusterAutomationSpec,
    validate_feature_value as _core_validate_feature_value,
    validate_cluster_name as _core_validate_cluster_name,
    build_json_merge_patch as _core_build_json_merge_patch,
    resolve_spec_to_plan as _core_resolve_spec_to_plan,
)

router = APIRouter()

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Shared registry instance (auto-refreshes on file change via mtime cache)
_shared_registry = _CoreFeatureRegistry(_Path(_project_root))


def _resolve(name: str):
    """Look up *name* via the app module so that unittest.mock.patch on
    ``app.<name>`` takes effect even though the endpoint lives here."""
    app_mod = sys.modules.get("app")
    if app_mod is not None:
        return getattr(app_mod, name)
    return globals()[name]


# ============================================================================
# Cluster Actions / Feature Action Engine API
# ============================================================================

# Feature registry: delegates to shared capa_core (single source of truth)
# These thin wrappers preserve the existing API surface used throughout this file.

def _load_feature_registry_full():
    """Load the full feature registry YAML (delegates to shared registry)."""
    _shared_registry.refresh()
    return _shared_registry.raw_data


def _load_feature_registry():
    """Load feature registry suites (for backward compat). Returns dict with 'suites' key."""
    _shared_registry.refresh()
    return {"suites": _shared_registry.suites}


def _get_registry():
    """Get the live feature registry (refreshed on file change via mtime cache)."""
    return _load_feature_registry()


def _get_feature_index():
    """Get the live feature index (auto-refreshed via shared registry)."""
    _shared_registry.refresh()
    return _shared_registry.all_features()


# Backward-compat module-level variables (used by tests)
CLUSTER_FEATURE_REGISTRY = _load_feature_registry()
_FEATURE_INDEX = _get_feature_index()


def _validate_cluster_name(name: str) -> Optional[str]:
    return _core_validate_cluster_name(name)


def _validate_feature_value(feature: dict, value) -> Optional[str]:
    return _core_validate_feature_value(feature, value)


@router.get("/api/cluster-actions/features")
async def get_feature_registry():
    """Return the full feature registry organized by suite groupings"""
    return {"success": True, "registry": _resolve("_get_registry")()}


@router.get("/api/cluster-actions/features/{suite_id}")
async def get_suite_features(suite_id: str):
    """Return features for a specific suite"""
    registry = _resolve("_get_registry")()
    for suite in registry["suites"]:
        if suite["id"] == suite_id:
            return {"success": True, "suite": suite}
    raise HTTPException(status_code=404, detail=f"Suite '{suite_id}' not found")


class ClusterActionRequest(BaseModel):
    cluster_name: str
    namespace: str = "ns-rosa-hcp"
    actions: list  # [{feature_id, target_value}]


# --- Action History Persistence ---
ACTION_HISTORY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "vars", "cluster_action_history.json"
)


def _load_action_history():
    if not os.path.exists(ACTION_HISTORY_FILE):
        return []
    try:
        with open(ACTION_HISTORY_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save_action_history(history):
    os.makedirs(os.path.dirname(ACTION_HISTORY_FILE), exist_ok=True)
    # Cap at 200 entries
    with open(ACTION_HISTORY_FILE, "w") as f:
        json.dump(history[-200:], f, indent=2, default=str)


def _record_action(cluster_name, namespace, feature_id, feature_name, target_value, status, job_id=None, message=""):
    history = _load_action_history()
    history.append({
        "id": str(uuid.uuid4())[:8],
        "cluster_name": cluster_name,
        "namespace": namespace,
        "feature_id": feature_id,
        "feature_name": feature_name,
        "target_value": target_value,
        "status": status,
        "job_id": job_id,
        "message": message,
        "timestamp": datetime.now().isoformat(),
    })
    _save_action_history(history)


def _find_feature(feature_id):
    """Look up a feature in the registry by ID (O(1) index lookup, auto-refreshed)."""
    return _get_feature_index().get(feature_id)


def _build_json_merge_patch(k8s_field: str, value) -> dict:
    return _core_build_json_merge_patch(k8s_field, value)


# Per-cluster lock to prevent concurrent operations on the same cluster
_cluster_locks: Dict[str, asyncio.Lock] = {}
_CLUSTER_LOCKS_MAX = 100


def _get_cluster_lock(cluster_name: str) -> asyncio.Lock:
    """Get or create an asyncio.Lock for a cluster (prevents concurrent operations)."""
    if cluster_name not in _cluster_locks:
        # Evict unlocked entries if we've exceeded the max
        if len(_cluster_locks) >= _CLUSTER_LOCKS_MAX:
            stale = [k for k, v in _cluster_locks.items() if not v.locked()]
            for k in stale:
                del _cluster_locks[k]
        _cluster_locks[cluster_name] = asyncio.Lock()
    return _cluster_locks[cluster_name]


@router.post("/api/cluster-actions/execute")
async def execute_cluster_actions(request: ClusterActionRequest):
    """
    Execute a batch of feature actions on a cluster.
    Playbook-backed actions are run via the job system with live polling.
    K8s patch actions are executed directly via oc patch.
    Uses per-cluster locking to prevent concurrent conflicting operations.
    """
    # Validate cluster name
    name_err = _validate_cluster_name(request.cluster_name)
    if name_err:
        raise HTTPException(status_code=400, detail=name_err)

    lock = _get_cluster_lock(request.cluster_name)
    if lock.locked():
        raise HTTPException(status_code=409, detail=f"Cluster '{request.cluster_name}' has an operation in progress. Please wait.")

    async with lock:
        return await _execute_cluster_actions_locked(request)


async def _execute_cluster_actions_locked(request: ClusterActionRequest):
    """Inner execution logic, called while holding the per-cluster lock."""
    from shared_state import jobs
    from agents_service import init_ai_agents

    results = []

    for action in request.actions:
        feature_id = action.get("feature_id")
        target_value = action.get("target_value")
        feature = _resolve("_find_feature")(feature_id)

        if not feature:
            results.append({"feature_id": feature_id, "status": "error", "message": f"Unknown feature: {feature_id}"})
            continue

        if not feature.get("mutable"):
            results.append({"feature_id": feature_id, "status": "error", "message": f"Feature '{feature['name']}' is immutable (set at creation time only)"})
            continue

        # Validate target_value against feature type
        if target_value is not None:
            val_err = _resolve("_validate_feature_value")(feature, target_value)
            if val_err:
                results.append({"feature_id": feature_id, "status": "error", "message": val_err})
                continue

        # If feature has a playbook, run it through the job system
        if feature.get("playbook"):
            extra_vars = {
                "cluster_name": request.cluster_name,
                "capi_namespace": request.namespace,
            }
            if target_value is not None:
                if feature_id in ("control_plane_upgrade", "machine_pool_upgrade"):
                    extra_vars["requested_version"] = str(target_value)

            try:
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                playbook_path = os.path.join(project_root, feature["playbook"])
                if not os.path.exists(playbook_path):
                    results.append({"feature_id": feature_id, "status": "error", "message": f"Playbook not found: {feature['playbook']}"})
                    continue

                job_id = str(uuid.uuid4())
                description = f"[ClusterAction] {feature['name']} on {request.cluster_name}"

                # Create job in the job system
                jobs[job_id] = {
                    "id": job_id,
                    "status": "pending",
                    "progress": 0,
                    "message": f"Queued: {description}",
                    "logs": [],
                    "created_at": datetime.now(),
                    "playbook": feature["playbook"],
                    "description": description,
                }

                init_ai_agents(job_id)

                # Launch the playbook asynchronously
                app_mod = sys.modules.get("app")
                run_playbook_bg = getattr(app_mod, "run_playbook_background")
                asyncio.create_task(
                    run_playbook_bg(feature["playbook"], extra_vars, job_id, description)
                )

                results.append({
                    "feature_id": feature_id,
                    "status": "running",
                    "job_id": job_id,
                    "playbook": feature["playbook"],
                    "message": f"Started {feature['name']}",
                    "target_value": target_value,
                    "current_value": extra_vars.get("current_version", ""),
                    "wait_timeout": feature.get("wait_timeout", 600),
                    "wait_resource": feature.get("wait_resource"),
                    "wait_field": feature.get("wait_field"),
                    "wait_value": feature.get("wait_value"),
                })

                _resolve("_record_action")(request.cluster_name, request.namespace, feature_id,
                               feature["name"], target_value, "running", job_id, f"Playbook: {feature['playbook']}")

            except Exception as e:
                results.append({"feature_id": feature_id, "status": "error", "message": str(e)})
                _resolve("_record_action")(request.cluster_name, request.namespace, feature_id,
                               feature["name"], target_value, "error", message=str(e))
        else:
            # K8s patch action — execute via oc patch
            resource = feature.get("resource", "")
            field = feature.get("k8s_field", "")
            patch_status = "queued"
            patch_message = ""

            if resource and field:
                try:
                    patch_obj = _resolve("_build_json_merge_patch")(field, target_value)
                    patch_json = json.dumps(patch_obj)
                    resource_name = resource.lower()

                    cmd = [
                        "oc", "patch", resource_name, request.cluster_name,
                        "-n", request.namespace,
                        "--type=merge", "-p", patch_json,
                    ]

                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                    if result.returncode == 0:
                        patch_status = "completed"
                        patch_message = f"Patched {resource} {field} = {target_value}"
                    else:
                        patch_status = "error"
                        patch_message = result.stderr.strip() or "Patch failed"

                except subprocess.TimeoutExpired:
                    patch_status = "error"
                    patch_message = "Timeout executing oc patch"
                except Exception as e:
                    patch_status = "error"
                    patch_message = str(e)
            else:
                patch_message = f"No resource/field defined for {feature_id}"

            results.append({
                "feature_id": feature_id,
                "status": patch_status,
                "message": patch_message,
                "resource": resource,
                "field": field,
                "target_value": target_value,
            })

            _resolve("_record_action")(request.cluster_name, request.namespace, feature_id,
                           feature["name"], target_value, patch_status, message=patch_message)

    return {
        "success": True,
        "cluster_name": request.cluster_name,
        "namespace": request.namespace,
        "action_count": len(results),
        "results": results,
    }


@router.get("/api/cluster-actions/history")
async def get_action_history(cluster_name: str = ""):
    """Get action history, optionally filtered by cluster name"""
    history = _resolve("_load_action_history")()
    if cluster_name:
        history = [h for h in history if h.get("cluster_name") == cluster_name]
    # Return most recent first
    return {"success": True, "history": list(reversed(history)), "count": len(history)}


@router.post("/api/cluster-actions/provision")
async def provision_cluster_with_features(request: dict, background_tasks: BackgroundTasks):
    """
    Provision a new ROSA HCP cluster with Day1 features pre-configured.
    Translates selected features into extra_vars for the provision playbook.
    """
    from shared_state import jobs
    from agents_service import init_ai_agents

    cluster_name = request.get("cluster_name", "")
    name_prefix = request.get("name_prefix", "")
    namespace = request.get("namespace", "ns-rosa-hcp")
    features = request.get("features", {})  # {feature_id: target_value}

    if not cluster_name and not name_prefix:
        raise HTTPException(status_code=400, detail="cluster_name or name_prefix required")

    # Validate cluster name format if provided
    if cluster_name:
        name_err = _resolve("_validate_cluster_name")(cluster_name)
        if name_err:
            raise HTTPException(status_code=400, detail=name_err)

    # Build extra_vars from selected features
    extra_vars = {
        "capi_namespace": namespace,
    }
    if name_prefix:
        extra_vars["name_prefix"] = name_prefix
    if cluster_name:
        extra_vars["cluster_name"] = cluster_name

    # Map features to provision playbook extra_vars using registry var_map
    registry_data = _resolve("_load_feature_registry_full")()
    var_map = registry_data.get("var_map", {})

    for feature_id, target_value in features.items():
        var_name = var_map.get(feature_id, feature_id)
        if target_value is not None:
            extra_vars[var_name] = target_value

    # Use the provision playbook
    playbook = "playbooks/create_rosa_hcp_cluster.yml"
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    playbook_path = os.path.join(project_root, playbook)

    if not os.path.exists(playbook_path):
        raise HTTPException(status_code=404, detail=f"Playbook not found: {playbook}")

    job_id = str(uuid.uuid4())
    effective_name = cluster_name or f"{name_prefix}-rosa-hcp"
    description = f"[ClusterAction] Provision {effective_name}"

    jobs[job_id] = {
        "id": job_id,
        "status": "pending",
        "progress": 0,
        "message": f"Queued: {description}",
        "logs": [],
        "created_at": datetime.now(),
        "playbook": playbook,
        "description": description,
    }

    init_ai_agents(job_id)
    app_mod = sys.modules.get("app")
    run_playbook_bg = getattr(app_mod, "run_playbook_background")
    asyncio.create_task(run_playbook_bg(playbook, extra_vars, job_id, description))

    _resolve("_record_action")(effective_name, namespace, "provision",
                   "Provision New Cluster", json.dumps(features), "running", job_id,
                   f"Features: {', '.join(features.keys()) if features else 'defaults'}")

    return {
        "success": True,
        "job_id": job_id,
        "cluster_name": effective_name,
        "namespace": namespace,
        "features_applied": list(features.keys()),
        "extra_vars_count": len(extra_vars),
    }


@router.get("/api/cluster-actions/discover")
async def discover_clusters(namespace: str = ""):
    """
    Discover all ROSAControlPlane clusters across namespaces (or in a specific namespace).
    Returns a list of clusters with basic status info.
    """
    clusters = []
    try:
        cmd = ["oc", "get", "rosacontrolplane", "-o", "json"]
        if namespace:
            cmd.extend(["-n", namespace])
        else:
            cmd.append("--all-namespaces")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            for item in data.get("items", []):
                meta = item.get("metadata", {})
                spec = item.get("spec", {})
                status = item.get("status", {})
                clusters.append({
                    "name": meta.get("name", "unknown"),
                    "namespace": meta.get("namespace", ""),
                    "version": spec.get("version", ""),
                    "ready": status.get("ready", False),
                    "channel_group": spec.get("channelGroup", "stable"),
                    "available_upgrades": status.get("availableUpgrades", []),
                    "domain_prefix": spec.get("domainPrefix", ""),
                    "endpoint_access": spec.get("endpointAccess", "public"),
                    "created": meta.get("creationTimestamp", ""),
                })
        else:
            return {"success": False, "clusters": [], "error": result.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"success": False, "clusters": [], "error": "Timeout querying clusters"}
    except Exception as e:
        return {"success": False, "clusters": [], "error": str(e)}

    return {"success": True, "clusters": clusters, "count": len(clusters)}


@router.get("/api/cluster-actions/cluster/{cluster_name}/status")
async def get_cluster_feature_status(cluster_name: str, namespace: str = "ns-rosa-hcp"):
    """
    Get current feature values for a cluster by reading K8s resources.
    Returns the live state of all features.
    """
    status = {}
    try:
        # Get ROSAControlPlane
        result = subprocess.run(
            ["oc", "get", "rosacontrolplane", cluster_name, "-n", namespace, "-o", "json"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            cp = json.loads(result.stdout)
            spec = cp.get("spec", {})
            cp_status = cp.get("status", {})
            status["cluster_found"] = True
            status["version"] = spec.get("version", "unknown")
            status["ready"] = cp_status.get("ready", False)
            status["available_upgrades"] = cp_status.get("availableUpgrades", [])
            status["endpoint_access"] = spec.get("endpointAccess", "public")
            status["channel_group"] = spec.get("channelGroup", "stable")
            status["domain_prefix"] = spec.get("domainPrefix", "")
            status["etcd_kms"] = bool(spec.get("etcdEncryptionKMSARN"))
            status["additional_tags"] = spec.get("additionalTags", {})
        else:
            status["cluster_found"] = False
            status["error"] = result.stderr.strip()

        # Get ROSAMachinePool
        result2 = subprocess.run(
            ["oc", "get", "rosamachinepool", "-n", namespace, "-l", f"cluster.x-k8s.io/cluster-name={cluster_name}", "-o", "json"],
            capture_output=True, text=True, timeout=15
        )
        if result2.returncode == 0:
            pools = json.loads(result2.stdout)
            pool_items = pools.get("items", [])
            status["machine_pools"] = []
            for pool in pool_items:
                pool_spec = pool.get("spec", {})
                pool_status = pool.get("status", {})
                status["machine_pools"].append({
                    "name": pool.get("metadata", {}).get("name", "unknown"),
                    "version": pool_spec.get("version", ""),
                    "instance_type": pool_spec.get("instanceType", ""),
                    "replicas": pool_spec.get("replicas"),
                    "autoscaling": pool_spec.get("autoscaling"),
                    "ready": pool_status.get("ready", False),
                    "available_upgrades": pool_status.get("availableUpgrades", []),
                })

    except subprocess.TimeoutExpired:
        status["cluster_found"] = False
        status["error"] = "Timeout querying cluster"
    except Exception as e:
        status["cluster_found"] = False
        status["error"] = str(e)

    return {"success": True, "cluster_name": cluster_name, "namespace": namespace, "status": status}


# ============================================================================
# ClusterAutomationSpec API - Declarative cluster lifecycle
# ============================================================================

SPECS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "specs"
)

def _resolve_spec_to_plan(spec_data: dict) -> list:
    """Resolve a ClusterAutomationSpec into an execution plan (delegates to capa_core)."""
    spec = _CoreClusterAutomationSpec(spec_data)
    return _core_resolve_spec_to_plan(_shared_registry, spec)


@router.get("/api/cluster-specs")
async def list_cluster_specs():
    """List available ClusterAutomationSpec specs by category."""
    specs = []
    if os.path.isdir(SPECS_DIR):
        for root, dirs, files in os.walk(SPECS_DIR):
            category = os.path.basename(root) if root != SPECS_DIR else "uncategorized"
            for fname in sorted(files):
                if not (fname.endswith(".yml") or fname.endswith(".yaml")):
                    continue
                try:
                    with open(os.path.join(root, fname)) as f:
                        data = yaml.safe_load(f)
                    spec_section = data.get("spec", {})
                    specs.append({
                        "id": os.path.splitext(fname)[0],
                        "name": data.get("metadata", {}).get("name", fname),
                        "action": spec_section.get("action", ""),
                        "features": list(spec_section.get("features", {}).keys()),
                        "version": spec_section.get("version", ""),
                        "region": spec_section.get("region", ""),
                        "category": category,
                    })
                except Exception:
                    continue
    return {"success": True, "specs": specs}


def _find_spec_file(spec_id: str) -> str:
    """Search specs/ subdirectories for a spec by ID."""
    for root, dirs, files in os.walk(SPECS_DIR):
        for ext in (".yml", ".yaml"):
            candidate = os.path.join(root, f"{spec_id}{ext}")
            if os.path.exists(candidate):
                return candidate
    return ""


@router.get("/api/cluster-specs/{spec_id}")
async def get_cluster_spec(spec_id: str):
    """Get a specific ClusterAutomationSpec by ID."""
    spec_path = _resolve("_find_spec_file")(spec_id)
    if not spec_path:
        return {"success": False, "error": f"Spec not found: {spec_id}"}
    try:
        with open(spec_path) as f:
            data = yaml.safe_load(f)
        return {"success": True, "spec": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/cluster-specs/plan")
async def plan_cluster_spec(request: Request):
    """Resolve a ClusterAutomationSpec into an execution plan (dry run)."""
    body = await request.json()
    spec_data = body.get("spec")

    # If spec_id provided, load from file
    if not spec_data and body.get("spec_id"):
        spec_path = _resolve("_find_spec_file")(body["spec_id"])
        if spec_path:
            with open(spec_path) as f:
                spec_data = yaml.safe_load(f)

    if not spec_data:
        return {"success": False, "error": "No spec provided"}

    # Apply overrides
    overrides = body.get("overrides", {})
    for k, v in overrides.items():
        if k in ("cluster", "namespace", "version", "region", "channel", "name_prefix", "action"):
            spec_data.setdefault("spec", {})[k] = v

    try:
        plan = _resolve("_resolve_spec_to_plan")(spec_data)
        return {"success": True, "plan": plan, "step_count": len(plan)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/cluster-specs/execute")
async def execute_cluster_spec(request: Request):
    """Execute a ClusterAutomationSpec — resolves to plan and runs each step."""
    from shared_state import jobs
    from agents_service import init_ai_agents

    body = await request.json()
    spec_data = body.get("spec")

    if not spec_data and body.get("spec_id"):
        spec_path = _resolve("_find_spec_file")(body["spec_id"])
        if spec_path:
            with open(spec_path) as f:
                spec_data = yaml.safe_load(f)

    if not spec_data:
        return {"success": False, "error": "No spec provided"}

    overrides = body.get("overrides", {})
    for k, v in overrides.items():
        if k in ("cluster", "namespace", "version", "region", "channel", "name_prefix", "action"):
            spec_data.setdefault("spec", {})[k] = v

    try:
        plan = _resolve("_resolve_spec_to_plan")(spec_data)
    except Exception as e:
        return {"success": False, "error": str(e)}

    # Execute each step through the existing job system
    results = []
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    for step in plan:
        if step["type"] == "playbook":
            playbook_path = os.path.join(project_root, step["playbook"])
            if not os.path.exists(playbook_path):
                results.append({"step": step["step"], "name": step["name"],
                                "status": "error", "message": f"Playbook not found: {step['playbook']}"})
                continue

            job_id = str(uuid.uuid4())
            description = f"[Spec] {step['name']}"
            jobs[job_id] = {
                "id": job_id, "status": "pending", "progress": 0,
                "message": f"Queued: {description}", "logs": [],
                "created_at": datetime.now(), "playbook": step["playbook"],
                "description": description,
            }
            init_ai_agents(job_id)
            app_mod = sys.modules.get("app")
            run_playbook_bg = getattr(app_mod, "run_playbook_background")
            asyncio.create_task(
                run_playbook_bg(step["playbook"], step.get("extra_vars", {}), job_id, description)
            )
            results.append({
                "step": step["step"], "name": step["name"],
                "status": "running", "job_id": job_id,
                "feature": step.get("feature", ""),
                "depends_on": step.get("depends_on"),
                "playbook": step["playbook"],
            })

        elif step["type"] == "patch":
            resource = step.get("resource", "").lower()
            field = step.get("k8s_field", "")
            value = step.get("value")
            cluster = step.get("cluster", "")
            namespace = step.get("namespace", "ns-rosa-hcp")

            patch_obj = _resolve("_build_json_merge_patch")(field, value)
            cmd = ["oc", "patch", resource, cluster, "-n", namespace,
                   "--type=merge", "-p", json.dumps(patch_obj)]

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                if result.returncode == 0:
                    results.append({"step": step["step"], "name": step["name"],
                                    "status": "completed", "feature": step.get("feature", "")})
                else:
                    results.append({"step": step["step"], "name": step["name"],
                                    "status": "error", "message": result.stderr.strip(),
                                    "feature": step.get("feature", "")})
            except Exception as e:
                results.append({"step": step["step"], "name": step["name"],
                                "status": "error", "message": str(e),
                                "feature": step.get("feature", "")})

    return {
        "success": True,
        "spec_name": spec_data.get("metadata", {}).get("name", ""),
        "action": spec_data.get("spec", {}).get("action", ""),
        "step_count": len(plan),
        "results": results,
    }


@router.post("/api/cluster-specs/save")
async def save_cluster_spec(request: Request):
    """Save a ClusterAutomationSpec to the specs directory."""
    body = await request.json()
    spec_data = body.get("spec")
    spec_id = body.get("id", "")

    if not spec_data or not spec_id:
        return {"success": False, "error": "spec and id required"}

    # Sanitize filename
    safe_id = "".join(c for c in spec_id if c.isalnum() or c in "-_").strip()
    if not safe_id:
        return {"success": False, "error": "Invalid spec id"}

    # Determine category subdirectory based on action
    action = spec_data.get("spec", {}).get("action", "apply")
    category = body.get("category", "")
    if not category:
        category = "profiles" if action == "create" else "features"
    save_dir = os.path.join(SPECS_DIR, category)
    os.makedirs(save_dir, exist_ok=True)
    spec_path = os.path.join(save_dir, f"{safe_id}.yml")

    try:
        with open(spec_path, "w") as f:
            yaml.dump(spec_data, f, default_flow_style=False, sort_keys=False)
        return {"success": True, "id": safe_id, "path": spec_path}
    except Exception as e:
        return {"success": False, "error": str(e)}

