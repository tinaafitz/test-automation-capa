"""
Celery task definitions for the workflow orchestrator.

Each task wraps _run_ansible_task_sync and publishes progress
to Redis pub/sub so the FastAPI server can stream updates to the UI.

Sensitive credentials (AWS keys, OCM secrets) are passed via environment
variables, never serialized into Celery task args or Redis result backend.
"""

import logging
import os
import sys

from celery.exceptions import SoftTimeLimitExceeded

from celery_app import celery_app

_project_root = os.environ.get("AUTOMATION_PATH") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = frozenset({
    "aws_access_key_id", "aws_secret_access_key",
    "ocm_client_id", "ocm_client_secret",
    "ocp_password", "ocp_hub_cluster_password",
})


def _strip_sensitive(extra_vars: dict) -> dict:
    return {k: v for k, v in extra_vars.items() if k.lower() not in _SENSITIVE_KEYS}


_user_vars_cache = None


def _load_user_vars() -> dict:
    global _user_vars_cache
    if _user_vars_cache is not None:
        return _user_vars_cache
    user_vars_path = os.path.join(_project_root, "vars", "user_vars.yml")
    try:
        import yaml
        with open(user_vars_path) as f:
            _user_vars_cache = yaml.safe_load(f) or {}
    except Exception:
        _user_vars_cache = {}
    return _user_vars_cache


_USER_VARS_KEY_MAP = {
    "aws_access_key_id": ["AWS_ACCESS_KEY_ID", "awsAccessKeyId"],
    "aws_secret_access_key": ["AWS_SECRET_ACCESS_KEY", "awsSecretAccessKey"],
    "ocm_client_id": ["OCM_CLIENT_ID", "ocmClientId"],
    "ocm_client_secret": ["OCM_CLIENT_SECRET", "ocmClientSecret"],
    "ocp_password": ["OCP_HUB_CLUSTER_PASSWORD", "password"],
    "ocp_hub_cluster_password": ["OCP_HUB_CLUSTER_PASSWORD", "password"],
}


def _inject_sensitive_from_env(extra_vars: dict) -> dict:
    restored = dict(extra_vars)
    user_vars = _load_user_vars()
    for key in _SENSITIVE_KEYS:
        env_val = os.environ.get(key.upper(), "")
        if env_val:
            restored[key] = env_val
            continue
        for alias in _USER_VARS_KEY_MAP.get(key, []):
            val = user_vars.get(alias, "")
            if val:
                restored[key] = val
                break
    return restored


def _publish_event(execution_id: str, event_type: str, data: dict):
    try:
        from redis_events import publish_step_event
        publish_step_event(execution_id, event_type, data)
    except Exception as e:
        logger.debug(f"Redis publish failed (non-critical): {e}")


@celery_app.task(
    bind=True,
    name="celery_tasks.execute_ansible_step",
    max_retries=3,
    acks_late=True,
    reject_on_worker_lost=True,
)
def execute_ansible_step(
    self,
    execution_id: str,
    step_name: str,
    resource: str,
    task_file: str,
    extra_vars: dict,
    timeout: int,
    retry_config: dict = None,
):
    from workflow_orchestrator import _run_ansible_task_sync

    full_vars = _inject_sensitive_from_env(extra_vars)

    _publish_event(execution_id, "step_started", {
        "step": step_name,
        "resource": resource,
        "celery_task_id": self.request.id,
    })

    try:
        result = _run_ansible_task_sync(
            _project_root, task_file, full_vars, timeout,
            execution_id, step_name,
        )
    except SoftTimeLimitExceeded:
        _publish_event(execution_id, "step_timed_out", {
            "step": step_name,
            "error": f"Celery soft time limit exceeded ({timeout}s)",
        })
        return {
            "success": False,
            "step": step_name,
            "error": f"Timed out after {timeout}s",
        }
    except Exception as exc:
        if retry_config and self.request.retries < retry_config.get("max_attempts", 0):
            interval = retry_config.get("interval", 10)
            backoff = retry_config.get("backoff_rate", 2.0)
            countdown = interval * (backoff ** self.request.retries)
            _publish_event(execution_id, "step_retrying", {
                "step": step_name,
                "attempt": self.request.retries + 1,
                "countdown": countdown,
            })
            raise self.retry(exc=exc, countdown=countdown)

        _publish_event(execution_id, "step_failed", {
            "step": step_name,
            "error": str(exc),
        })
        return {"success": False, "step": step_name, "error": str(exc)}

    event_type = "step_succeeded" if result["success"] else "step_failed"
    _publish_event(execution_id, event_type, {
        "step": step_name,
        "output": result.get("output", "")[-500:],
        "error": result.get("error", ""),
    })

    return {
        "success": result["success"],
        "step": step_name,
        "output": result.get("output", ""),
        "error": result.get("error", ""),
    }
