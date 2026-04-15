"""
Trigger service: core logic for trigger state management, scheduling, and execution.

Extracted from app.py to keep the main module focused on route handlers.
"""

import asyncio
import fcntl
import hashlib
import json
import logging
import os
import threading
from datetime import datetime
from typing import Dict, Optional

import yaml

logger = logging.getLogger("trigger_service")

# ---------------------------------------------------------------------------
# State file configuration
# ---------------------------------------------------------------------------

TRIGGER_STATE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "vars", "trigger_state.json"
)

# Rate limiting: track last fire time per trigger to prevent abuse
_trigger_last_fire: Dict[str, float] = {}
TRIGGER_MIN_INTERVAL = 60  # seconds
MAX_RUN_HISTORY = 200  # max entries kept in run_history

_trigger_state_lock = threading.Lock()

# Concurrent run prevention: tracks which triggers are currently executing
_active_trigger_runs: Dict[str, str] = {}  # trigger_id -> run_id


# ---------------------------------------------------------------------------
# State I/O (thread-safe with file locking)
# ---------------------------------------------------------------------------

def _load_trigger_state():
    """Load trigger state from vars/trigger_state.json (thread-safe)."""
    if not os.path.exists(TRIGGER_STATE_FILE):
        return {"triggers": [], "run_history": []}
    try:
        with _trigger_state_lock:
            with open(TRIGGER_STATE_FILE, "r") as f:
                fcntl.flock(f, fcntl.LOCK_SH)
                try:
                    return json.load(f)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
    except (json.JSONDecodeError, IOError):
        return {"triggers": [], "run_history": []}


def _save_trigger_state(state):
    """Persist trigger state (thread-safe with file locking)."""
    os.makedirs(os.path.dirname(TRIGGER_STATE_FILE), exist_ok=True)
    if len(state.get("run_history", [])) > MAX_RUN_HISTORY:
        state["run_history"] = state["run_history"][-MAX_RUN_HISTORY:]
    with _trigger_state_lock:
        with open(TRIGGER_STATE_FILE, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                json.dump(state, f, indent=2, default=str)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

def _send_trigger_notification(trigger, run_record, success):
    """Send Slack/email notification for a trigger run result."""
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        config_path = os.path.join(project_root, "vars", "notification_config.yml")
        if not os.path.exists(config_path):
            return
        with open(config_path, "r") as f:
            settings = yaml.safe_load(f) or {}

        status = "completed" if success else "failed"

        # Only notify on failure by default, or on completion if configured
        notify_trigger_success = settings.get("notify_trigger_success", False)
        notify_trigger_failure = settings.get("notify_trigger_failure", True)
        if success and not notify_trigger_success:
            return
        if not success and not notify_trigger_failure:
            return

        job_data = {
            "cluster_name": f"[Trigger] {trigger.get('trigger_name', trigger['trigger_id'])}",
            "region": f"Workflow: {trigger.get('workflow_name', 'unknown')}",
            "version": f"{run_record.get('steps_completed', 0)}/{run_record.get('steps_total', 0)} steps",
            "job_id": run_record.get("run_id", ""),
        }
        if not success:
            job_data["error"] = f"Trigger workflow failed ({run_record.get('steps_completed', 0)}/{run_record.get('steps_total', 0)} steps completed)"

        if settings.get("slack_enabled", False):
            try:
                from app import slack_service
                slack_service.reload_config()
                slack_service.send_provisioning_notification(job_data, status)
                logger.info("Slack notification sent", extra={"trigger_id": trigger['trigger_id'], "status": status})
            except Exception as e:
                logger.warning("Slack notification failed", extra={"error": str(e)})

        if settings.get("email_enabled", False):
            try:
                from app import email_service
                email_service.reload_config()
                email_service.send_provisioning_notification(job_data, status)
                logger.info("Email notification sent", extra={"trigger_id": trigger['trigger_id'], "status": status})
            except Exception as e:
                logger.warning("Email notification failed", extra={"error": str(e)})
    except Exception as e:
        logger.error("Notification error", extra={"error": str(e)})


# ---------------------------------------------------------------------------
# Post-run state update
# ---------------------------------------------------------------------------

def _update_trigger_after_run(trigger_id, success, run_record):
    """Shared helper: update trigger state after a run (avoids duplication across fire/webhook/scheduler)."""
    st = _load_trigger_state()
    t = next((x for x in st.get("triggers", []) if x.get("trigger_id") == trigger_id), None)
    if t:
        t["last_run_at"] = run_record.get("started_at")
        t["last_run_status"] = run_record.get("status")
        t["run_count"] = t.get("run_count", 0) + 1
        if success:
            t["consecutive_failures"] = 0
        else:
            t["consecutive_failures"] = t.get("consecutive_failures", 0) + 1
            if t["consecutive_failures"] >= 5:
                t["enabled"] = False
                logger.warning("Trigger auto-disabled after 5 consecutive failures", extra={"trigger_id": trigger_id})
        # Update next_run_at for schedule triggers
        if t.get("type") == "schedule" and t.get("cron"):
            try:
                from croniter import croniter as _cron
                next_t = _cron(t["cron"], datetime.now()).get_next(datetime)
                t["next_run_at"] = next_t.isoformat()
            except Exception:
                pass
    st.setdefault("run_history", []).append(run_record)
    _save_trigger_state(st)


# ---------------------------------------------------------------------------
# Workflow execution
# ---------------------------------------------------------------------------

async def _fire_trigger_workflow(trigger, vars_override=None):
    """Execute a trigger's workflow via the playbook runner. Returns (success, run_record)."""
    from app import jobs, _load_workflows, _run_playbook_in_thread

    workflow_name = trigger["workflow_name"]
    trigger_id = trigger["trigger_id"]
    run_id = f"trun-{hashlib.sha256(os.urandom(16)).hexdigest()[:8]}"

    # Concurrent run prevention
    if trigger_id in _active_trigger_runs:
        active_run = _active_trigger_runs[trigger_id]
        logger.info("Skipping trigger — already running", extra={"trigger_id": trigger_id, "active_run": active_run})
        return False, {
            "trigger_id": trigger_id, "run_id": run_id,
            "workflow_name": workflow_name, "started_at": datetime.now().isoformat(),
            "completed_at": datetime.now().isoformat(),
            "status": "skipped", "steps_completed": 0, "steps_total": 0,
            "triggered_by": trigger["type"], "error": f"Already running ({active_run})",
        }

    _active_trigger_runs[trigger_id] = run_id
    started_at = datetime.now().isoformat()

    try:
        # Find the workflow — try saved workflows first, then YAML
        wf = None
        wf_type = None

        workflows = _load_workflows()
        wf = next((w for w in workflows if w.get("name") == workflow_name), None)
        if wf:
            wf_type = "saved"

        if not wf:
            repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            wf_dir = os.path.join(repo_root, "specs", "workflows")
            if os.path.isdir(wf_dir):
                for fname in os.listdir(wf_dir):
                    if not fname.endswith(".yml"):
                        continue
                    fpath = os.path.join(wf_dir, fname)
                    try:
                        with open(fpath) as f:
                            data = yaml.safe_load(f)
                        if data and data.get("kind") == "Workflow":
                            name = data.get("metadata", {}).get("name", fname.replace(".yml", ""))
                            if name == workflow_name:
                                wf = data
                                wf_type = "yaml"
                                break
                    except (yaml.YAMLError, IOError):
                        continue

        if not wf:
            run_record = {
                "trigger_id": trigger_id, "run_id": run_id,
                "workflow_name": workflow_name, "started_at": started_at,
                "completed_at": datetime.now().isoformat(),
                "status": "failed", "steps_completed": 0, "steps_total": 0,
                "triggered_by": trigger["type"], "error": "Workflow not found",
            }
            _send_trigger_notification(trigger, run_record, False)
            return False, run_record

        # Extract steps
        if wf_type == "yaml":
            global_vars = wf.get("spec", {}).get("vars", {})
            raw_steps = wf.get("spec", {}).get("steps", [])
        else:
            global_vars = wf.get("vars", wf.get("globalVars", {}))
            raw_steps = wf.get("steps", [])

        # Execute steps sequentially
        steps_completed = 0
        steps_total = len(raw_steps)
        step_results = []

        for i, step in enumerate(raw_steps):
            step_vars = step.get("vars", step.get("extra_vars", {}))
            merged_vars = {**global_vars, **step_vars}
            if vars_override:
                merged_vars.update(vars_override)

            playbook = step.get("playbook", step.get("file", ""))
            step_name = step.get("name", f"Step {i+1}")

            # Check condition
            step_if = step.get("if")
            if step_if:
                if step_if == "always":
                    pass  # always run
                elif step_if == "failure":
                    if not any(r.get("status") == "failed" for r in step_results):
                        step_results.append({"step": i, "status": "skipped"})
                        continue
                elif step_if == "success":
                    if not all(r.get("status") == "completed" for r in step_results):
                        step_results.append({"step": i, "status": "skipped"})
                        continue

            # Run the playbook — initialize job entry first, then run in thread
            job_id = f"trigger-{run_id}-step-{i}"
            jobs[job_id] = {
                "id": job_id,
                "status": "pending",
                "progress": 0,
                "message": f"Trigger step: {step_name}",
                "started_at": datetime.now(),
                "logs": [],
            }
            try:
                await asyncio.to_thread(
                    _run_playbook_in_thread, playbook, merged_vars,
                    job_id, f"[Trigger: {trigger_id}] {step_name}"
                )
                # Check result
                job_info = jobs.get(job_id, {})
                if job_info.get("status") == "completed":
                    steps_completed += 1
                    step_results.append({"step": i, "status": "completed"})
                else:
                    step_results.append({"step": i, "status": "failed"})
                    on_failure = step.get("on_failure", step.get("onFailure", "stop"))
                    if on_failure == "stop":
                        break
            except Exception as e:
                step_results.append({"step": i, "status": "failed", "error": str(e)})
                on_failure = step.get("on_failure", step.get("onFailure", "stop"))
                if on_failure == "stop":
                    break

        completed_at = datetime.now().isoformat()
        success = steps_completed == steps_total

        run_record = {
            "trigger_id": trigger_id, "run_id": run_id,
            "workflow_name": workflow_name, "started_at": started_at,
            "completed_at": completed_at,
            "status": "completed" if success else "failed",
            "steps_completed": steps_completed, "steps_total": steps_total,
            "triggered_by": trigger["type"],
        }
        _send_trigger_notification(trigger, run_record, success)
        return success, run_record
    finally:
        _active_trigger_runs.pop(trigger_id, None)


# ---------------------------------------------------------------------------
# Trigger Scheduler — in-process asyncio cron loop using croniter
# ---------------------------------------------------------------------------

class TriggerScheduler:
    """Lightweight in-process scheduler that fires schedule triggers at their cron times."""

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._check_interval = 30  # seconds between cron checks
        self._last_check: Dict[str, str] = {}  # trigger_id -> last fired minute ISO

    async def start(self):
        """Start the scheduler loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Scheduler started")

    async def stop(self):
        """Stop the scheduler loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Scheduler stopped")

    async def _loop(self):
        """Main scheduler loop — checks every _check_interval seconds."""
        try:
            from croniter import croniter
        except ImportError:
            logger.warning("croniter not installed — scheduler disabled")
            return

        while self._running:
            try:
                await self._tick(croniter)
            except Exception as e:
                logger.error("Error in scheduler tick", extra={"error": str(e)})
            await asyncio.sleep(self._check_interval)

    async def _tick(self, croniter_cls):
        """Single scheduler tick — check all schedule triggers."""
        from datetime import timezone as _tz
        from zoneinfo import ZoneInfo

        now_utc = datetime.now(_tz.utc)
        state = _load_trigger_state()
        triggers = state.get("triggers", [])

        # Prune _last_check for triggers that no longer exist
        active_ids = {t["trigger_id"] for t in triggers}
        stale_keys = [k for k in self._last_check if k not in active_ids]
        for k in stale_keys:
            del self._last_check[k]

        for trigger in triggers:
            if trigger.get("type") != "schedule":
                continue
            if not trigger.get("enabled", True):
                continue
            cron_expr = trigger.get("cron", "")
            if not cron_expr:
                continue

            trigger_id = trigger["trigger_id"]
            tz_name = trigger.get("timezone", "UTC")

            try:
                tz = ZoneInfo(tz_name)
            except (KeyError, Exception):
                tz = ZoneInfo("UTC")

            now_local = now_utc.astimezone(tz)

            # Build a minute-resolution key to prevent double-firing
            minute_key = now_local.strftime("%Y-%m-%d %H:%M")
            if self._last_check.get(trigger_id) == minute_key:
                continue

            # Check if this cron expression matches the current minute
            try:
                import datetime as _dt_mod
                cron = croniter_cls(cron_expr, now_local - _dt_mod.timedelta(minutes=1))
                next_fire = cron.get_next(datetime)
                # If next_fire falls in the current minute window, fire
                if next_fire.strftime("%Y-%m-%d %H:%M") == minute_key:
                    self._last_check[trigger_id] = minute_key
                    logger.info("Firing scheduled trigger", extra={
                        "trigger_id": trigger_id,
                        "trigger_name": trigger.get("trigger_name", ""),
                        "workflow_name": trigger.get("workflow_name", ""),
                    })
                    asyncio.create_task(self._fire(trigger))
            except (ValueError, KeyError) as e:
                logger.warning("Bad cron expression", extra={"trigger_id": trigger_id, "error": str(e)})

    async def _fire(self, trigger):
        """Fire a single trigger and update state."""
        trigger_id = trigger["trigger_id"]
        try:
            success, run_record = await _fire_trigger_workflow(
                trigger, trigger.get("vars_override", {})
            )
            _update_trigger_after_run(trigger_id, success, run_record)
            if success:
                logger.info("Trigger completed successfully", extra={"trigger_id": trigger_id})
            else:
                logger.warning("Trigger failed", extra={"trigger_id": trigger_id})
        except Exception as e:
            logger.error("Error firing trigger", extra={"trigger_id": trigger_id, "error": str(e)})


# Global scheduler instance
_trigger_scheduler = TriggerScheduler()
