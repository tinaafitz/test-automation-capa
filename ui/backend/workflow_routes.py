"""
Workflow & trigger service module — FastAPI router for workflow management
and trigger endpoints.

Endpoints moved here from app.py:
  GET    /api/workflows
  GET    /api/workflows/{workflow_id}
  POST   /api/workflows
  PUT    /api/workflows/{workflow_id}
  DELETE /api/workflows/{workflow_id}
  POST   /api/workflows/{workflow_id}/duplicate
  POST   /api/workflows/{workflow_id}/run
  GET    /api/workflows/templates/list
  GET    /api/workflows/yaml
  GET    /api/workflows/{workflow_id}/triggers
  GET    /api/triggers
  POST   /api/triggers
  GET    /api/triggers/metrics
  GET    /api/triggers/{trigger_id}
  DELETE /api/triggers/{trigger_id}
  POST   /api/triggers/{trigger_id}/enable
  POST   /api/triggers/{trigger_id}/disable
  POST   /api/triggers/{trigger_id}/fire
  GET    /api/triggers/{trigger_id}/history
  GET    /api/triggers/history/all
  POST   /api/webhooks/trigger/{trigger_id}
  GET    /api/triggers/scheduler/status

Also contains:
  WORKFLOWS_FILE, _normalize_workflow, _load_workflows, _save_workflows,
  WorkflowSave, TriggerCreate, _get_trigger_or_404, _fire_and_update
"""

import json
import logging as _trigger_logging
import os
import sys
import uuid
from datetime import datetime

import yaml
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from trigger_service import (
    TRIGGER_STATE_FILE,
    TRIGGER_MIN_INTERVAL,
    AUTO_DISABLE_THRESHOLD,
    MAX_PAGINATION_LIMIT,
    _trigger_last_fire,
    _active_trigger_runs,
    _load_trigger_state,
    _save_trigger_state,
    _send_trigger_notification,
    _update_trigger_after_run,
    _fire_trigger_workflow,
    check_rate_limit,
    TriggerScheduler,
    _trigger_scheduler,
)

router = APIRouter()

_trigger_logger = _trigger_logging.getLogger("trigger_routes")

# Project root (same as _project_root in app.py)
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _resolve(name: str):
    """Look up *name* via the app module so that unittest.mock.patch on
    ``app.<name>`` takes effect even though the endpoint lives here."""
    app_mod = sys.modules.get("app")
    if app_mod is not None:
        return getattr(app_mod, name)
    return globals()[name]


# ============================================================================
# Workflow Management API
# ============================================================================

WORKFLOWS_FILE = os.path.join(
    _project_root, "vars", "saved_workflows.json"
)


def _normalize_workflow(wf):
    """Normalize a workflow to canonical snake_case format (migrates old camelCase)."""
    # Top-level fields
    if "globalVars" in wf and "vars" not in wf:
        wf["vars"] = wf.pop("globalVars")
    elif "globalVars" in wf:
        wf.pop("globalVars")
    if "stopOnFailure" in wf and "stop_on_failure" not in wf:
        wf["stop_on_failure"] = wf.pop("stopOnFailure")
    elif "stopOnFailure" in wf:
        wf.pop("stopOnFailure")
    # Step fields
    for step in wf.get("steps", []):
        if "file" in step and "playbook" not in step:
            step["playbook"] = step.pop("file")
        elif "file" in step:
            step.pop("file")
        if "onFailure" in step and "on_failure" not in step:
            step["on_failure"] = step.pop("onFailure")
        elif "onFailure" in step:
            step.pop("onFailure")
        if "extra_vars" in step and "vars" not in step:
            step["vars"] = step.pop("extra_vars")
        elif "extra_vars" in step:
            step.pop("extra_vars")
    return wf


def _load_workflows():
    """Load saved workflows from disk (auto-migrates old camelCase format)."""
    wf_file = _resolve("WORKFLOWS_FILE")
    if not os.path.exists(wf_file):
        return []
    try:
        with open(wf_file, "r") as f:
            workflows = json.load(f)
        return [_normalize_workflow(wf) for wf in workflows]
    except (json.JSONDecodeError, IOError):
        return []


def _save_workflows(workflows):
    """Persist workflows to disk"""
    wf_file = _resolve("WORKFLOWS_FILE")
    os.makedirs(os.path.dirname(wf_file), exist_ok=True)
    with open(wf_file, "w") as f:
        json.dump(workflows, f, indent=2, default=str)


class WorkflowSave(BaseModel):
    name: str
    description: str = ""
    stop_on_failure: bool = True
    vars: dict = {}
    steps: list = []
    # Backward compat: accept old camelCase fields
    stopOnFailure: bool = None
    globalVars: dict = None


@router.get("/api/workflows")
async def list_workflows():
    """List all saved workflows"""
    workflows = _resolve("_load_workflows")()
    # Return summary info (strip globalVars values for security)
    summaries = []
    for wf in workflows:
        wf_vars = wf.get("vars", {})
        summaries.append({
            "id": wf.get("id"),
            "name": wf.get("name"),
            "description": wf.get("description", ""),
            "stepCount": len(wf.get("steps", [])),
            "stepNames": [s.get("name", "") for s in wf.get("steps", [])],
            "hasGlobalVars": len(wf_vars) > 0,
            "globalVarKeys": list(wf_vars.keys()),
            "stop_on_failure": wf.get("stop_on_failure", True),
            "savedAt": wf.get("savedAt"),
            "lastRunAt": wf.get("lastRunAt"),
        })
    return {"success": True, "workflows": summaries, "count": len(summaries)}


@router.get("/api/workflows/{workflow_id}")
async def get_workflow(workflow_id: str):
    """Get a single workflow by ID (includes full details)"""
    workflows = _resolve("_load_workflows")()
    wf = next((w for w in workflows if w.get("id") == workflow_id), None)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"success": True, "workflow": wf}


@router.post("/api/workflows")
async def save_workflow(workflow: WorkflowSave):
    """Save a new workflow or update existing one with same name"""
    workflows = _resolve("_load_workflows")()

    # Check for existing workflow with same name
    existing_idx = next((i for i, w in enumerate(workflows) if w.get("name") == workflow.name), None)

    # Resolve backward-compat fields: prefer new snake_case, fall back to old camelCase
    resolved_stop = workflow.stop_on_failure if workflow.stopOnFailure is None else workflow.stopOnFailure
    resolved_vars = workflow.vars if workflow.globalVars is None else workflow.globalVars
    wf_data = {
        "id": workflows[existing_idx]["id"] if existing_idx is not None else f"wf-{uuid.uuid4().hex[:12]}",
        "name": workflow.name,
        "description": workflow.description,
        "stop_on_failure": resolved_stop,
        "vars": resolved_vars,
        "steps": workflow.steps,
        "savedAt": datetime.now().isoformat(),
    }
    _normalize_workflow(wf_data)

    if existing_idx is not None:
        # Preserve lastRunAt from existing
        wf_data["lastRunAt"] = workflows[existing_idx].get("lastRunAt")
        workflows[existing_idx] = wf_data
    else:
        workflows.append(wf_data)

    _save_workflows(workflows)
    return {"success": True, "workflow": wf_data, "updated": existing_idx is not None}


@router.put("/api/workflows/{workflow_id}")
async def update_workflow(workflow_id: str, workflow: WorkflowSave):
    """Update an existing workflow by ID"""
    workflows = _resolve("_load_workflows")()
    idx = next((i for i, w in enumerate(workflows) if w.get("id") == workflow_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    resolved_stop = workflow.stop_on_failure if workflow.stopOnFailure is None else workflow.stopOnFailure
    resolved_vars = workflow.vars if workflow.globalVars is None else workflow.globalVars
    update_data = {
        "name": workflow.name,
        "description": workflow.description,
        "stop_on_failure": resolved_stop,
        "vars": resolved_vars,
        "steps": workflow.steps,
        "savedAt": datetime.now().isoformat(),
    }
    _normalize_workflow(update_data)
    workflows[idx].update(update_data)

    _save_workflows(workflows)
    return {"success": True, "workflow": workflows[idx]}


@router.delete("/api/workflows/{workflow_id}")
async def delete_workflow(workflow_id: str):
    """Delete a saved workflow"""
    workflows = _resolve("_load_workflows")()
    updated = [w for w in workflows if w.get("id") != workflow_id]
    if len(updated) == len(workflows):
        raise HTTPException(status_code=404, detail="Workflow not found")
    _save_workflows(updated)
    return {"success": True, "deleted": workflow_id}


@router.post("/api/workflows/{workflow_id}/duplicate")
async def duplicate_workflow(workflow_id: str):
    """Duplicate an existing workflow with a new name"""
    workflows = _resolve("_load_workflows")()
    source = next((w for w in workflows if w.get("id") == workflow_id), None)
    if not source:
        raise HTTPException(status_code=404, detail="Workflow not found")

    new_wf = {
        **source,
        "id": f"wf-{uuid.uuid4().hex[:12]}",
        "name": f"{source['name']} (copy)",
        "savedAt": datetime.now().isoformat(),
        "lastRunAt": None,
    }
    workflows.append(new_wf)
    _save_workflows(workflows)
    return {"success": True, "workflow": new_wf}


@router.post("/api/workflows/{workflow_id}/run")
async def mark_workflow_run(workflow_id: str):
    """Record that a workflow was run (updates lastRunAt)"""
    workflows = _resolve("_load_workflows")()
    idx = next((i for i, w in enumerate(workflows) if w.get("id") == workflow_id), None)
    if idx is not None:
        workflows[idx]["lastRunAt"] = datetime.now().isoformat()
        _save_workflows(workflows)
    return {"success": True}


@router.get("/api/workflows/templates/list")
async def list_workflow_templates():
    """Return built-in workflow templates"""
    templates = [
        {
            "id": "tpl-full-e2e",
            "name": "Full E2E (Provision + Delete)",
            "description": "Complete end-to-end test: validate environment, provision a ROSA HCP cluster, verify it, then delete and clean up.",
            "icon": "rocket",
            "steps": [
                {"name": "Validate CAPA Environment", "playbook": "playbooks/validate-capa-environment.yml", "on_failure": "stop", "timeout": 120, "vars": {}},
                {"name": "Provision ROSA HCP Cluster", "playbook": "playbooks/provision_rosa_hcp_cluster.yml", "on_failure": "stop", "timeout": 2400, "vars": {}},
                {"name": "Verify ROSA HCP Cluster", "playbook": "playbooks/verify_rosa_hcp_cluster.yml", "on_failure": "skip", "timeout": 600, "vars": {}},
                {"name": "Delete ROSA HCP Cluster", "playbook": "playbooks/delete_rosa_hcp_cluster.yml", "on_failure": "stop", "timeout": 2400, "vars": {}},
            ],
            "vars": {},
            "stop_on_failure": True,
        },
        {
            "id": "tpl-provision-only",
            "name": "Provision Only",
            "description": "Validate the environment and provision a ROSA HCP cluster.",
            "icon": "server",
            "steps": [
                {"name": "Validate CAPA Environment", "playbook": "playbooks/validate-capa-environment.yml", "on_failure": "stop", "timeout": 120, "vars": {}},
                {"name": "Provision ROSA HCP Cluster", "playbook": "playbooks/provision_rosa_hcp_cluster.yml", "on_failure": "stop", "timeout": 2400, "vars": {}},
            ],
            "vars": {},
            "stop_on_failure": True,
        },
        {
            "id": "tpl-delete-cleanup",
            "name": "Delete + Cleanup",
            "description": "Delete a ROSA HCP cluster and clean up any orphaned AWS resources.",
            "icon": "trash",
            "steps": [
                {"name": "Delete ROSA HCP Cluster", "playbook": "playbooks/delete_rosa_hcp_cluster.yml", "on_failure": "skip", "timeout": 2400, "vars": {}},
            ],
            "vars": {},
            "stop_on_failure": False,
        },
        {
            "id": "tpl-validate-env",
            "name": "Validate Environment",
            "description": "Run all validation checks to ensure your CAPA environment is properly configured.",
            "icon": "check",
            "steps": [
                {"name": "Validate CAPA Environment", "playbook": "playbooks/validate-capa-environment.yml", "on_failure": "stop", "timeout": 120, "vars": {"soft_verify": "true"}},
            ],
            "vars": {},
            "stop_on_failure": True,
        },
    ]
    return {"success": True, "templates": templates}


@router.get("/api/workflows/yaml")
async def list_yaml_workflows():
    """Return YAML workflow files from specs/workflows/."""
    import yaml as _yaml
    wf_dir = os.path.join(_project_root, "specs", "workflows")
    results = []
    if not os.path.isdir(wf_dir):
        return {"success": True, "workflows": []}
    for fname in sorted(os.listdir(wf_dir)):
        if not fname.endswith(".yml"):
            continue
        fpath = os.path.join(wf_dir, fname)
        try:
            with open(fpath) as f:
                data = _yaml.safe_load(f)
            if not data or data.get("kind") != "Workflow":
                continue
            meta = data.get("metadata", {})
            spec = data.get("spec", {})
            steps = spec.get("steps", [])
            wf_vars = spec.get("vars", {})
            results.append({
                "id": f"yaml-{fname.replace('.yml', '')}",
                "name": meta.get("name", fname.replace(".yml", "")),
                "description": meta.get("description", ""),
                "source": f"specs/workflows/{fname}",
                "stepCount": len(steps),
                "stepNames": [s.get("name", "") for s in steps],
                "vars": wf_vars,
                "hasGlobalVars": len(wf_vars) > 0,
                "globalVarKeys": list(wf_vars.keys()),
                "stop_on_failure": True,
                "steps": [
                    {
                        "name": s.get("name", ""),
                        "playbook": s.get("playbook", ""),
                        "on_failure": s.get("on_failure", "stop"),
                        "timeout": s.get("timeout", 600),
                        "vars": s.get("vars", {}),
                        **({"condition": s["if"]} if s.get("if") else {}),
                    }
                    for s in steps
                ],
            })
        except Exception:
            continue
    return {"success": True, "workflows": results}


# ============================================================================
# Trigger Management API
# ============================================================================


def _get_trigger_or_404(state: dict, trigger_id: str) -> dict:
    """Look up a trigger by ID or raise 404. Eliminates repeated lookup pattern."""
    trigger = next((t for t in state.get("triggers", []) if t.get("trigger_id") == trigger_id), None)
    if not trigger:
        raise HTTPException(404, "Trigger not found")
    return trigger


class TriggerCreate(BaseModel):
    workflow_name: str
    type: str  # "schedule" or "webhook"
    trigger_name: str = ""
    cron: str = ""
    timezone: str = "UTC"
    secret_env: str = ""
    vars_override: dict = {}
    enabled: bool = True


@router.get("/api/triggers")
async def list_triggers(offset: int = 0, limit: int = 100):
    """List all configured triggers with pagination."""
    limit = min(limit, MAX_PAGINATION_LIMIT)
    state = _resolve("_load_trigger_state")()
    all_triggers = state.get("triggers", [])
    total = len(all_triggers)
    page = all_triggers[offset:offset + limit]
    return {"success": True, "triggers": page, "count": len(page), "total": total, "offset": offset, "limit": limit}


@router.post("/api/triggers")
async def create_trigger(trigger: TriggerCreate):
    """Create a new trigger."""
    import hashlib

    state = _resolve("_load_trigger_state")()

    # Validate input lengths and characters
    import re as _re
    if not trigger.workflow_name or len(trigger.workflow_name) > 128:
        raise HTTPException(400, "workflow_name must be 1-128 characters")
    if not _re.match(r'^[a-zA-Z0-9][a-zA-Z0-9._-]*$', trigger.workflow_name):
        raise HTTPException(400, "workflow_name contains invalid characters (use alphanumeric, dots, hyphens, underscores)")
    if trigger.trigger_name and len(trigger.trigger_name) > 128:
        raise HTTPException(400, "trigger_name must be at most 128 characters")
    if trigger.trigger_name and not _re.match(r'^[a-zA-Z0-9][a-zA-Z0-9._-]*$', trigger.trigger_name):
        raise HTTPException(400, "trigger_name contains invalid characters")

    # Validate type
    if trigger.type not in ("schedule", "webhook"):
        raise HTTPException(400, "type must be 'schedule' or 'webhook'")

    # Validate cron for schedule triggers
    if trigger.type == "schedule":
        if not trigger.cron:
            raise HTTPException(400, "cron is required for schedule triggers")
        try:
            from croniter import croniter
            croniter(trigger.cron)  # validates the expression
        except (ValueError, KeyError) as e:
            raise HTTPException(400, f"Invalid cron expression: {trigger.cron} ({e})")
        except ImportError:
            # Fallback: basic 5-part check if croniter not available
            parts = trigger.cron.strip().split()
            if len(parts) != 5:
                raise HTTPException(400, f"Invalid cron expression: {trigger.cron}")

    # Validate workflow exists
    wf_found = False
    workflows = _resolve("_load_workflows")()
    if any(w.get("name") == trigger.workflow_name for w in workflows):
        wf_found = True
    if not wf_found:
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        wf_dir = os.path.join(repo_root, "specs", "workflows")
        if os.path.isdir(wf_dir):
            for fname in os.listdir(wf_dir):
                if not fname.endswith(".yml"):
                    continue
                try:
                    with open(os.path.join(wf_dir, fname)) as f:
                        data = yaml.safe_load(f)
                    if data and data.get("kind") == "Workflow":
                        name = data.get("metadata", {}).get("name", fname.replace(".yml", ""))
                        if name == trigger.workflow_name:
                            wf_found = True
                            break
                except (yaml.YAMLError, IOError):
                    continue
    if not wf_found:
        raise HTTPException(400, f"Workflow not found: {trigger.workflow_name}")

    trigger_id = f"trg-{hashlib.sha256(os.urandom(16)).hexdigest()[:16]}"
    trigger_data = {
        "trigger_id": trigger_id,
        "workflow_name": trigger.workflow_name,
        "workflow_source": "yaml",  # determined at fire time
        "type": trigger.type,
        "trigger_name": trigger.trigger_name or f"{trigger.type}-{trigger.workflow_name}",
        "enabled": trigger.enabled,
        "created_at": datetime.now().isoformat(),
        "last_run_at": None,
        "last_run_status": None,
        "next_run_at": None,
        "run_count": 0,
        "consecutive_failures": 0,
        "vars_override": trigger.vars_override,
    }

    if trigger.type == "schedule":
        trigger_data["cron"] = trigger.cron
        trigger_data["timezone"] = trigger.timezone
        # Compute next_run_at
        try:
            from croniter import croniter
            next_t = croniter(trigger.cron, datetime.now()).get_next(datetime)
            trigger_data["next_run_at"] = next_t.isoformat()
        except Exception:
            pass

    if trigger.type == "webhook":
        if trigger.secret_env:
            trigger_data["secret_env"] = trigger.secret_env
            secret_val = os.environ.get(trigger.secret_env, "")
            if secret_val:
                trigger_data["webhook_secret_hash"] = hashlib.sha256(secret_val.encode()).hexdigest()
            else:
                trigger_data["webhook_secret_hash"] = None
        else:
            trigger_data["secret_env"] = None
            trigger_data["webhook_secret_hash"] = None

    state.setdefault("triggers", []).append(trigger_data)
    _resolve("_save_trigger_state")(state)
    _trigger_logger.info("Trigger created", extra={"trigger_id": trigger_id, "type": trigger.type, "workflow": trigger.workflow_name})
    return {"success": True, "trigger": trigger_data}


@router.get("/api/triggers/metrics")
async def trigger_metrics():
    """Return aggregate trigger metrics: counts, success rate, avg execution time."""
    state = _resolve("_load_trigger_state")()
    triggers = state.get("triggers", [])
    history = state.get("run_history", [])
    total_runs = len(history)
    completed = sum(1 for h in history if h.get("status") == "completed")
    failed = sum(1 for h in history if h.get("status") == "failed")
    skipped = sum(1 for h in history if h.get("status") == "skipped")
    success_rate = round(completed / total_runs * 100, 1) if total_runs > 0 else 0.0
    durations = []
    for h in history:
        started = h.get("started_at")
        completed_at = h.get("completed_at")
        if started and completed_at:
            try:
                start_dt = datetime.fromisoformat(started)
                end_dt = datetime.fromisoformat(completed_at)
                durations.append((end_dt - start_dt).total_seconds())
            except (ValueError, TypeError):
                pass
    avg_duration = round(sum(durations) / len(durations), 1) if durations else 0.0
    return {
        "success": True,
        "total_triggers": len(triggers),
        "enabled_triggers": sum(1 for t in triggers if t.get("enabled", True)),
        "disabled_triggers": sum(1 for t in triggers if not t.get("enabled", True)),
        "schedule_triggers": sum(1 for t in triggers if t.get("type") == "schedule"),
        "webhook_triggers": sum(1 for t in triggers if t.get("type") == "webhook"),
        "total_runs": total_runs,
        "completed_runs": completed,
        "failed_runs": failed,
        "skipped_runs": skipped,
        "success_rate_pct": success_rate,
        "avg_duration_seconds": avg_duration,
    }


@router.get("/api/triggers/{trigger_id}")
async def get_trigger(trigger_id: str):
    """Get a single trigger by ID."""
    state = _resolve("_load_trigger_state")()
    trigger = _get_trigger_or_404(state, trigger_id)

    # Include recent history
    history = [h for h in state.get("run_history", []) if h.get("trigger_id") == trigger_id][-10:]
    return {"success": True, "trigger": trigger, "history": history}


@router.delete("/api/triggers/{trigger_id}")
async def delete_trigger(trigger_id: str):
    """Delete a trigger."""
    state = _resolve("_load_trigger_state")()
    _get_trigger_or_404(state, trigger_id)
    state["triggers"] = [t for t in state.get("triggers", []) if t.get("trigger_id") != trigger_id]
    _resolve("_save_trigger_state")(state)
    _trigger_scheduler._last_check.pop(trigger_id, None)
    _trigger_logger.info("Trigger deleted", extra={"trigger_id": trigger_id})
    return {"success": True, "deleted": trigger_id}


@router.post("/api/triggers/{trigger_id}/enable")
async def enable_trigger(trigger_id: str):
    """Enable a trigger."""
    state = _resolve("_load_trigger_state")()
    trigger = _get_trigger_or_404(state, trigger_id)
    trigger["enabled"] = True
    trigger["consecutive_failures"] = 0
    # Recompute next_run_at for schedule triggers
    if trigger.get("type") == "schedule" and trigger.get("cron"):
        try:
            from croniter import croniter
            next_t = croniter(trigger["cron"], datetime.now()).get_next(datetime)
            trigger["next_run_at"] = next_t.isoformat()
        except Exception:
            pass
    _resolve("_save_trigger_state")(state)
    _trigger_scheduler._last_check.pop(trigger_id, None)
    return {"success": True, "trigger": trigger}


@router.post("/api/triggers/{trigger_id}/disable")
async def disable_trigger(trigger_id: str):
    """Disable a trigger."""
    state = _resolve("_load_trigger_state")()
    trigger = _get_trigger_or_404(state, trigger_id)
    trigger["enabled"] = False
    _resolve("_save_trigger_state")(state)
    return {"success": True, "trigger": trigger}


async def _fire_and_update(trigger, background_tasks: BackgroundTasks):
    """Shared helper: enqueue trigger workflow execution as a background task."""
    trigger_id = trigger["trigger_id"]

    async def _run():
        success, run_record = await _fire_trigger_workflow(trigger, trigger.get("vars_override", {}))
        _update_trigger_after_run(trigger_id, success, run_record)

    background_tasks.add_task(_run)


@router.post("/api/triggers/{trigger_id}/fire")
async def fire_trigger(trigger_id: str, background_tasks: BackgroundTasks):
    """Manually fire a trigger from the UI."""
    state = _resolve("_load_trigger_state")()
    trigger = _get_trigger_or_404(state, trigger_id)

    # Atomic rate limit check
    remaining = _resolve("check_rate_limit")(trigger_id)
    if remaining is not None:
        _trigger_logger.warning("Trigger rate limited", extra={"trigger_id": trigger_id, "retry_after": remaining})
        return JSONResponse(
            status_code=429,
            content={"detail": f"Rate limited. Try again in {remaining}s"},
            headers={"Retry-After": str(remaining)},
        )

    _trigger_logger.info("Trigger fired", extra={"trigger_id": trigger_id, "workflow": trigger["workflow_name"], "source": "manual"})
    await _fire_and_update(trigger, background_tasks)
    return {"success": True, "message": f"Trigger {trigger_id} fired", "workflow": trigger["workflow_name"]}


@router.get("/api/triggers/{trigger_id}/history")
async def get_trigger_history(trigger_id: str, limit: int = 20, offset: int = 0):
    """Get run history for a specific trigger with pagination."""
    limit = min(limit, MAX_PAGINATION_LIMIT)
    state = _resolve("_load_trigger_state")()
    _get_trigger_or_404(state, trigger_id)
    all_history = [h for h in state.get("run_history", []) if h.get("trigger_id") == trigger_id]
    total = len(all_history)
    page = all_history[offset:offset + limit]
    return {"success": True, "history": page, "count": len(page), "total": total, "offset": offset, "limit": limit}


@router.get("/api/triggers/history/all")
async def get_all_trigger_history(limit: int = 50, offset: int = 0):
    """Get all trigger run history with pagination."""
    limit = min(limit, MAX_PAGINATION_LIMIT)
    state = _resolve("_load_trigger_state")()
    all_history = state.get("run_history", [])
    total = len(all_history)
    page = all_history[offset:offset + limit]
    return {"success": True, "history": page, "count": len(page), "total": total, "offset": offset, "limit": limit}


@router.get("/api/workflows/{workflow_id}/triggers")
async def get_workflow_triggers(workflow_id: str):
    """Get triggers associated with a specific workflow."""
    state = _resolve("_load_trigger_state")()
    # workflow_id could be a name or an actual ID
    triggers = [
        t for t in state.get("triggers", [])
        if t.get("workflow_name") == workflow_id
    ]
    return {"success": True, "triggers": triggers, "count": len(triggers)}


# Webhook endpoint
@router.post("/api/webhooks/trigger/{trigger_id}")
async def webhook_trigger(trigger_id: str, request: Request, background_tasks: BackgroundTasks):
    """Receive a webhook and fire the associated workflow."""
    import hashlib
    import hmac as _hmac

    state = _resolve("_load_trigger_state")()
    trigger = next((t for t in state.get("triggers", []) if t.get("trigger_id") == trigger_id), None)

    # Return generic 404 to prevent trigger enumeration
    if not trigger or trigger.get("type") != "webhook" or not trigger.get("enabled"):
        raise HTTPException(404, "Not found")

    # Atomic rate limit check
    remaining = _resolve("check_rate_limit")(trigger_id)
    if remaining is not None:
        _trigger_logger.warning("Webhook rate limited", extra={"trigger_id": trigger_id, "retry_after": remaining})
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limited"},
            headers={"Retry-After": str(remaining)},
        )

    body = await request.body()

    # Validate HMAC secret if configured
    if trigger.get("webhook_secret_hash"):
        secret_env = trigger.get("secret_env", "")
        secret = os.environ.get(secret_env, "") if secret_env else ""
        if not secret:
            raise HTTPException(500, "Webhook secret not configured in environment")
        signature = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + _hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not _hmac.compare_digest(signature, expected):
            raise HTTPException(403, "Invalid signature")

    _trigger_logger.info("Webhook trigger fired", extra={"trigger_id": trigger_id, "workflow": trigger["workflow_name"], "source": "webhook"})
    await _fire_and_update(trigger, background_tasks)
    return {"success": True, "message": "Webhook received", "workflow": trigger["workflow_name"]}


@router.get("/api/triggers/scheduler/status")
async def scheduler_status():
    """Return the trigger scheduler status and upcoming schedule trigger runs."""
    try:
        from croniter import croniter
        croniter_available = True
    except ImportError:
        croniter_available = False

    state = _resolve("_load_trigger_state")()
    schedule_triggers = [
        t for t in state.get("triggers", [])
        if t.get("type") == "schedule" and t.get("enabled", True)
    ]

    upcoming = []
    if croniter_available:
        for t in schedule_triggers:
            cron_expr = t.get("cron", "")
            if not cron_expr:
                continue
            try:
                cron = croniter(cron_expr, datetime.now())
                next_run = cron.get_next(datetime)
                upcoming.append({
                    "trigger_id": t["trigger_id"],
                    "trigger_name": t.get("trigger_name", ""),
                    "workflow_name": t.get("workflow_name", ""),
                    "cron": cron_expr,
                    "timezone": t.get("timezone", "UTC"),
                    "next_run_at": next_run.isoformat(),
                })
            except (ValueError, KeyError):
                continue

    upcoming.sort(key=lambda x: x.get("next_run_at", ""))

    return {
        "success": True,
        "running": _trigger_scheduler._running,
        "croniter_available": croniter_available,
        "check_interval": _trigger_scheduler._check_interval,
        "active_schedule_triggers": len(schedule_triggers),
        "active_runs": dict(_active_trigger_runs),
        "upcoming": upcoming,
    }
