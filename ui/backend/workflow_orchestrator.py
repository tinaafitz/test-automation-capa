"""
Workflow Orchestrator for ROSA HCP Cluster Orchestration

Replaces sequential Ansible provisioning with parallel state machine execution.
Network, IAM roles, and OIDC setup run concurrently, then converge for
ROSAControlPlane creation — cutting provisioning from ~45 min to ~15-20 min.

Uses asyncio for parallel task execution, designed for local and Jenkins CI use.
"""

import asyncio
import io
import json
import logging
import os
import signal
import sqlite3
import subprocess
import threading
import time
import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from agents_service import init_ai_agents
    from shared_state import jobs, ai_agent_sessions
    AGENTS_AVAILABLE = True
except ImportError:
    AGENTS_AVAILABLE = False


class ExecutionMode(str, Enum):
    AWS = "aws"
    LOCAL = "local"
    CELERY = "celery"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


PROVISION_STATE_MACHINE = {
    "Comment": "ROSA HCP Cluster Provisioning with Parallel Resource Setup",
    "StartAt": "PreFlight",
    "States": {
        "PreFlight": {
            "Type": "Task",
            "Comment": "Validate credentials and OCM role",
            "Resource": "preflight_check",
            "TimeoutSeconds": 120,
            "Retry": [{"ErrorEquals": ["RetryableError"], "MaxAttempts": 2, "IntervalSeconds": 10, "BackoffRate": 2.0}],
            "Next": "ParallelResourceSetup",
        },
        "ParallelResourceSetup": {
            "Type": "Parallel",
            "Comment": "Run network, IAM roles, and OIDC setup concurrently",
            "Branches": [
                {
                    "StartAt": "CreateROSANetwork",
                    "States": {
                        "CreateROSANetwork": {
                            "Type": "Task",
                            "Comment": "Create VPC, subnets, IGW, NAT via CloudFormation",
                            "Resource": "create_rosa_network",
                            "TimeoutSeconds": 1800,
                            "Retry": [{"ErrorEquals": ["RetryableError"], "MaxAttempts": 2, "IntervalSeconds": 30, "BackoffRate": 2.0}],
                            "End": True,
                        }
                    },
                },
                {
                    "StartAt": "CreateRosaRoleConfig",
                    "States": {
                        "CreateRosaRoleConfig": {
                            "Type": "Task",
                            "Comment": "Create IAM installer/support/worker roles + OIDC provider",
                            "Resource": "create_rosa_role_config",
                            "TimeoutSeconds": 600,
                            "Retry": [{"ErrorEquals": ["RetryableError"], "MaxAttempts": 2, "IntervalSeconds": 15, "BackoffRate": 2.0}],
                            "End": True,
                        }
                    },
                },
                {
                    "StartAt": "VerifyOIDC",
                    "States": {
                        "VerifyOIDC": {
                            "Type": "Task",
                            "Comment": "Verify OIDC provider is configured",
                            "Resource": "verify_oidc",
                            "TimeoutSeconds": 300,
                            "Retry": [{"ErrorEquals": ["RetryableError"], "MaxAttempts": 3, "IntervalSeconds": 10, "BackoffRate": 2.0}],
                            "End": True,
                        }
                    },
                },
            ],
            "Next": "CreateControlPlane",
        },
        "CreateControlPlane": {
            "Type": "Task",
            "Comment": "Create ROSAControlPlane (depends on network + roles + OIDC)",
            "Resource": "create_control_plane",
            "TimeoutSeconds": 2400,
            "Retry": [{"ErrorEquals": ["RetryableError"], "MaxAttempts": 2, "IntervalSeconds": 30, "BackoffRate": 2.0}],
            "Next": "WaitForClusterReady",
        },
        "WaitForClusterReady": {
            "Type": "Task",
            "Comment": "Poll until ROSAControlPlane status is ready",
            "Resource": "wait_for_cluster_ready",
            "TimeoutSeconds": 2400,
            "Retry": [{"ErrorEquals": ["RetryableError"], "MaxAttempts": 1, "IntervalSeconds": 60}],
            "End": True,
        },
    },
}

DELETE_STATE_MACHINE = {
    "Comment": "ROSA HCP Cluster Deletion with Parallel Cleanup",
    "StartAt": "InitiateDeletion",
    "States": {
        "InitiateDeletion": {
            "Type": "Task",
            "Comment": "Initiate deletion of ROSAControlPlane and cluster resources",
            "Resource": "delete_control_plane",
            "TimeoutSeconds": 300,
            "Next": "WaitForControlPlaneDeleted",
        },
        "WaitForControlPlaneDeleted": {
            "Type": "Task",
            "Comment": "Wait for ROSAControlPlane to be fully removed",
            "Resource": "wait_for_control_plane_deleted",
            "TimeoutSeconds": 1800,
            "Retry": [{"ErrorEquals": ["RetryableError"], "MaxAttempts": 2, "IntervalSeconds": 30}],
            "Next": "ParallelCleanup",
        },
        "ParallelCleanup": {
            "Type": "Parallel",
            "Comment": "Clean up network and IAM resources concurrently",
            "Branches": [
                {
                    "StartAt": "DeleteROSANetwork",
                    "States": {
                        "DeleteROSANetwork": {
                            "Type": "Task",
                            "Comment": "Delete VPC and CloudFormation stack",
                            "Resource": "delete_rosa_network",
                            "TimeoutSeconds": 1800,
                            "Retry": [{"ErrorEquals": ["RetryableError"], "MaxAttempts": 3, "IntervalSeconds": 30, "BackoffRate": 2.0}],
                            "End": True,
                        }
                    },
                },
                {
                    "StartAt": "DeleteRosaRoleConfig",
                    "States": {
                        "DeleteRosaRoleConfig": {
                            "Type": "Task",
                            "Comment": "Delete IAM roles",
                            "Resource": "delete_rosa_role_config",
                            "TimeoutSeconds": 600,
                            "Retry": [{"ErrorEquals": ["RetryableError"], "MaxAttempts": 2, "IntervalSeconds": 15}],
                            "End": True,
                        }
                    },
                },
            ],
            "Next": "VerifyCleanup",
        },
        "VerifyCleanup": {
            "Type": "Task",
            "Comment": "Verify all resources removed, check for orphans",
            "Resource": "verify_cleanup",
            "TimeoutSeconds": 300,
            "End": True,
        },
    },
}

CONFIGURE_STATE_MACHINE = {
    "Comment": "Full MCE CAPI/CAPA Environment Setup",
    "StartAt": "VerifyOCPLogin",
    "States": {
        "VerifyOCPLogin": {
            "Type": "Task",
            "Comment": "Login to OpenShift hub cluster and verify connectivity",
            "Resource": "login_ocp",
            "TimeoutSeconds": 60,
            "Retry": [{"ErrorEquals": ["RetryableError"], "MaxAttempts": 2, "IntervalSeconds": 5, "BackoffRate": 2.0}],
            "Next": "EnableCAPICAPAComponents",
        },
        "EnableCAPICAPAComponents": {
            "Type": "Task",
            "Comment": "Disable Hypershift and enable CAPI/CAPA components in MCE",
            "Resource": "enable_capi_capa",
            "TimeoutSeconds": 300,
            "Retry": [{"ErrorEquals": ["RetryableError"], "MaxAttempts": 2, "IntervalSeconds": 15, "BackoffRate": 2.0}],
            "Next": "WaitForControllers",
        },
        "WaitForControllers": {
            "Type": "Task",
            "Comment": "Wait for capi-controller-manager and capa-controller-manager to be ready",
            "Resource": "wait_for_capi_capa_ready",
            "TimeoutSeconds": 600,
            "Retry": [{"ErrorEquals": ["RetryableError"], "MaxAttempts": 3, "IntervalSeconds": 30, "BackoffRate": 2.0}],
            "Next": "CreateNamespace",
        },
        "CreateNamespace": {
            "Type": "Task",
            "Comment": "Create the CAPI namespace for cluster resources",
            "Resource": "create_namespace",
            "TimeoutSeconds": 60,
            "Next": "ParallelConfigObjects",
        },
        "ParallelConfigObjects": {
            "Type": "Parallel",
            "Comment": "Create credentials, secrets, and identity objects concurrently",
            "Branches": [
                {
                    "StartAt": "CreateAWSCredentials",
                    "States": {
                        "CreateAWSCredentials": {
                            "Type": "Task",
                            "Comment": "Create capa-manager-bootstrap-credentials secret",
                            "Resource": "create_aws_credentials",
                            "TimeoutSeconds": 60,
                            "End": True,
                        }
                    },
                },
                {
                    "StartAt": "CreateROSACredsSecret",
                    "States": {
                        "CreateROSACredsSecret": {
                            "Type": "Task",
                            "Comment": "Create rosa-creds-secret in multicluster-engine namespace",
                            "Resource": "create_rosa_creds_secret",
                            "TimeoutSeconds": 60,
                            "End": True,
                        }
                    },
                },
                {
                    "StartAt": "SetRegistrationConfig",
                    "States": {
                        "SetRegistrationConfig": {
                            "Type": "Task",
                            "Comment": "Set ClusterManager registration config and ClusterRoleBinding",
                            "Resource": "set_registration_config",
                            "TimeoutSeconds": 60,
                            "End": True,
                        }
                    },
                },
            ],
            "Next": "SetAWSIdentityAndRestart",
        },
        "SetAWSIdentityAndRestart": {
            "Type": "Task",
            "Comment": "Set AWSClusterControllerIdentity and restart capa-controller-manager",
            "Resource": "set_aws_identity_restart",
            "TimeoutSeconds": 120,
            "Next": "VerifyEnvironment",
        },
        "VerifyEnvironment": {
            "Type": "Task",
            "Comment": "Validate CAPI/CAPA environment is fully configured and ready",
            "Resource": "validate_capa_environment",
            "TimeoutSeconds": 120,
            "End": True,
        },
    },
}

UPGRADE_STATE_MACHINE = {
    "Comment": "ROSA HCP Cluster Version Upgrade (Control Plane then Machine Pool)",
    "StartAt": "UpgradeControlPlane",
    "States": {
        "UpgradeControlPlane": {
            "Type": "Task",
            "Comment": "Upgrade ROSAControlPlane to next available version (includes wait)",
            "Resource": "upgrade_control_plane",
            "TimeoutSeconds": 3900,
            "Retry": [{"ErrorEquals": ["RetryableError"], "MaxAttempts": 1, "IntervalSeconds": 30}],
            "Next": "UpgradeMachinePool",
        },
        "UpgradeMachinePool": {
            "Type": "Task",
            "Comment": "Upgrade ROSAMachinePool to match control plane version (includes wait)",
            "Resource": "upgrade_machine_pool",
            "TimeoutSeconds": 3900,
            "Retry": [{"ErrorEquals": ["RetryableError"], "MaxAttempts": 1, "IntervalSeconds": 30}],
            "End": True,
        },
    },
}

FULL_LIFECYCLE_STATE_MACHINE = {
    "Comment": "Full ROSA HCP Lifecycle: Configure → Provision → Delete",
    "StartAt": "Configure",
    "States": {
        "Configure": {
            "Type": "StateMachine",
            "Comment": "Set up MCE CAPI/CAPA environment",
            "Resource": "mce-configure",
            "Next": "Provision",
        },
        "Provision": {
            "Type": "StateMachine",
            "Comment": "Provision ROSA HCP cluster with parallel resource setup",
            "Resource": "rosa-hcp-provision",
            "Next": "Delete",
        },
        "Delete": {
            "Type": "StateMachine",
            "Comment": "Delete ROSA HCP cluster with parallel cleanup",
            "Resource": "rosa-hcp-delete",
            "End": True,
        },
    },
}

PROVISION_AND_DELETE_STATE_MACHINE = {
    "Comment": "Provision then Delete ROSA HCP Cluster (E2E test)",
    "StartAt": "Provision",
    "States": {
        "Provision": {
            "Type": "StateMachine",
            "Comment": "Provision ROSA HCP cluster with parallel resource setup",
            "Resource": "rosa-hcp-provision",
            "Next": "Delete",
        },
        "Delete": {
            "Type": "StateMachine",
            "Comment": "Delete ROSA HCP cluster with parallel cleanup",
            "Resource": "rosa-hcp-delete",
            "End": True,
        },
    },
}

STATE_MACHINES = {
    "rosa-hcp-provision": PROVISION_STATE_MACHINE,
    "rosa-hcp-delete": DELETE_STATE_MACHINE,
    "mce-configure": CONFIGURE_STATE_MACHINE,
    "rosa-hcp-upgrade": UPGRADE_STATE_MACHINE,
    "full-lifecycle": FULL_LIFECYCLE_STATE_MACHINE,
    "provision-and-delete": PROVISION_AND_DELETE_STATE_MACHINE,
}


class StepExecution:
    """Tracks the state of a single step within an execution."""

    def __init__(self, name: str, resource: str, timeout: int = 300):
        self.name = name
        self.resource = resource
        self.status = StepStatus.PENDING
        self.started_at: Optional[str] = None
        self.completed_at: Optional[str] = None
        self.output: Optional[str] = None
        self.error: Optional[str] = None
        self.timeout = timeout
        self.job_id: Optional[str] = None
        self.agent_events: List[dict] = []

    def to_dict(self) -> dict:
        elapsed = None
        if self.started_at:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.completed_at) if self.completed_at else datetime.utcnow()
            elapsed = round((end - start).total_seconds())
        return {
            "name": self.name,
            "resource": self.resource,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_seconds": elapsed,
            "timeout_seconds": self.timeout,
            "output": self.output,
            "error": self.error,
            "job_id": self.job_id,
            "agent_events": self.agent_events,
            "sub_execution_id": getattr(self, 'sub_execution_id', None),
        }


class StateMachineExecution:
    """Tracks a full state machine execution (provision or delete)."""

    def __init__(self, execution_id: str, state_machine_name: str, input_params: dict,
                 mode: ExecutionMode = ExecutionMode.LOCAL):
        self.execution_id = execution_id
        self.state_machine_name = state_machine_name
        self.input_params = input_params
        self.mode = mode
        self.status = StepStatus.PENDING
        self.steps: Dict[str, StepExecution] = {}
        self.parallel_groups: List[List[str]] = []
        self.created_at = datetime.utcnow().isoformat()
        self.started_at: Optional[str] = None
        self.completed_at: Optional[str] = None
        self.error: Optional[str] = None
        self._cancelled = False
        self.agent_session: Optional[dict] = None
        self.agent_events: List[dict] = []

        self._build_steps_from_definition()

    def _build_steps_from_definition(self):
        definition = STATE_MACHINES.get(self.state_machine_name, {})
        states = definition.get("States", {})

        for state_name, state_def in states.items():
            state_type = state_def.get("Type")
            if state_type == "Task":
                timeout = state_def.get("TimeoutSeconds", 300)
                self.steps[state_name] = StepExecution(
                    name=state_name,
                    resource=state_def.get("Resource", state_name),
                    timeout=timeout,
                )
            elif state_type == "StateMachine":
                nested_name = state_def.get("Resource", state_name)
                nested_def = STATE_MACHINES.get(nested_name, {})
                total_timeout = sum(
                    s.get("TimeoutSeconds", 300)
                    for s in nested_def.get("States", {}).values()
                    if s.get("Type") == "Task"
                )
                step = StepExecution(
                    name=state_name,
                    resource=nested_name,
                    timeout=total_timeout or 3600,
                )
                step.sub_execution_id = None
                self.steps[state_name] = step
            elif state_type == "Parallel":
                group = []
                for branch in state_def.get("Branches", []):
                    for bstate_name, bstate_def in branch.get("States", {}).items():
                        if bstate_def.get("Type") == "Task":
                            timeout = bstate_def.get("TimeoutSeconds", 300)
                            self.steps[bstate_name] = StepExecution(
                                name=bstate_name,
                                resource=bstate_def.get("Resource", bstate_name),
                                timeout=timeout,
                            )
                            group.append(bstate_name)
                self.parallel_groups.append(group)

    @classmethod
    def from_dict(cls, data: dict) -> 'StateMachineExecution':
        exec_ = cls.__new__(cls)
        exec_.execution_id = data["execution_id"]
        exec_.state_machine_name = data["state_machine"]
        exec_.input_params = data.get("input", {})
        exec_.mode = ExecutionMode(data.get("mode", "local"))
        exec_.status = StepStatus(data.get("status", "pending"))
        exec_.parallel_groups = data.get("parallel_groups", [])
        exec_.created_at = data.get("created_at", datetime.utcnow().isoformat())
        exec_.started_at = data.get("started_at")
        exec_.completed_at = data.get("completed_at")
        exec_.error = data.get("error")
        exec_._cancelled = False
        exec_.agent_session = None
        exec_.agent_events = data.get("agent_events", [])
        exec_.steps = {}
        for name, step_data in data.get("steps", {}).items():
            step = StepExecution(
                name=step_data["name"],
                resource=step_data.get("resource", ""),
                timeout=step_data.get("timeout_seconds", 300),
            )
            step.status = StepStatus(step_data.get("status", "pending"))
            step.started_at = step_data.get("started_at")
            step.completed_at = step_data.get("completed_at")
            step.output = step_data.get("output")
            step.error = step_data.get("error")
            step.job_id = step_data.get("job_id")
            step.agent_events = step_data.get("agent_events", [])
            step.sub_execution_id = step_data.get("sub_execution_id")
            exec_.steps[name] = step
        return exec_

    def cancel(self):
        self._cancelled = True
        for step in self.steps.values():
            if step.status in (StepStatus.PENDING, StepStatus.RUNNING):
                step.status = StepStatus.CANCELLED
        self.status = StepStatus.CANCELLED
        self.completed_at = datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        elapsed = None
        if self.started_at:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.completed_at) if self.completed_at else datetime.utcnow()
            elapsed = round((end - start).total_seconds())
        return {
            "execution_id": self.execution_id,
            "state_machine": self.state_machine_name,
            "mode": self.mode.value,
            "status": self.status.value,
            "input": self.input_params,
            "steps": {name: step.to_dict() for name, step in self.steps.items()},
            "parallel_groups": self.parallel_groups,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_seconds": elapsed,
            "error": self.error,
            "agent_events": self.agent_events,
            "agent_stats": _get_execution_agent_stats(self),
        }


def _get_execution_agent_stats(execution: 'StateMachineExecution') -> dict:
    """Get AI agent statistics for a workflow execution."""
    session = execution.agent_session
    if not session:
        return {"enabled": False}
    monitor = session.get("monitor")
    remediation = session.get("remediation")
    events = execution.agent_events
    return {
        "enabled": True,
        "issues_detected": len(events),
        "interventions": len([e for e in events if e.get("remediation_result")]),
        "total_patterns_checked": len(getattr(monitor, "patterns_detected", [])) if monitor else 0,
    }


_EXEC_DB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "vars",
)
_EXEC_DB_PATH = os.path.join(_EXEC_DB_DIR, "executions.db")
_EXEC_SCHEMA = """
CREATE TABLE IF NOT EXISTS executions (
    execution_id TEXT PRIMARY KEY,
    data         TEXT NOT NULL,
    created      TEXT NOT NULL,
    updated      TEXT NOT NULL
);
"""
_MAX_HISTORY = 200


class ExecutionStore:
    """Persists completed workflow executions to SQLite for post-mortem analysis."""

    def __init__(self, db_path: str = _EXEC_DB_PATH):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._live: Dict[str, StateMachineExecution] = {}
        self._history: Dict[str, dict] = {}
        self._init_db()
        self._load_history()

    def _init_db(self):
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(_EXEC_SCHEMA)
            conn.commit()

    def _load_history(self):
        try:
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute(
                    "SELECT execution_id, data FROM executions ORDER BY created DESC LIMIT ?",
                    (_MAX_HISTORY,),
                ).fetchall()
            zombies = 0
            for eid, data_json in rows:
                data = json.loads(data_json)
                if data.get("status") == "running":
                    data["status"] = "failed"
                    data["error"] = "Backend restarted during execution"
                    for step in data.get("steps", {}).values():
                        if step.get("status") == "running":
                            step["status"] = "failed"
                            step["error"] = "Backend restarted during execution"
                    self._persist_dict(eid, data)
                    zombies += 1
                self._history[eid] = data
            if zombies:
                logger.warning(f"Marked {zombies} zombie execution(s) as failed")
            logger.info(f"Loaded {len(self._history)} execution(s) from history")
        except Exception as e:
            logger.warning(f"Failed to load execution history: {e}")

    def _persist_dict(self, execution_id: str, data: dict):
        now = datetime.now().isoformat()
        try:
            data_json = json.dumps(data)
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO executions (execution_id, data, created, updated) "
                    "VALUES (?, ?, COALESCE((SELECT created FROM executions WHERE execution_id = ?), ?), ?)",
                    (execution_id, data_json, execution_id, now, now),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to persist execution {execution_id}: {e}")

    def register(self, execution: StateMachineExecution):
        self._live[execution.execution_id] = execution

    def get(self, execution_id: str) -> Optional[StateMachineExecution]:
        return self._live.get(execution_id)

    def get_dict(self, execution_id: str) -> Optional[dict]:
        live = self._live.get(execution_id)
        if live:
            return live.to_dict()
        return self._history.get(execution_id)

    def persist(self, execution: StateMachineExecution):
        data = execution.to_dict()
        self._history[execution.execution_id] = data
        now = datetime.now().isoformat()
        try:
            data_json = json.dumps(data)
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO executions (execution_id, data, created, updated) "
                    "VALUES (?, ?, COALESCE((SELECT created FROM executions WHERE execution_id = ?), ?), ?)",
                    (execution.execution_id, data_json, execution.execution_id, now, now),
                )
                conn.commit()
        except Exception as e:
            logger.error(
                f"Failed to persist execution {execution.execution_id}: {e} "
                f"— step state may be lost on restart"
            )
        self._evict_old()

    def _evict_old(self):
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "DELETE FROM executions WHERE execution_id NOT IN "
                    "(SELECT execution_id FROM executions ORDER BY created DESC LIMIT ?)",
                    (_MAX_HISTORY,),
                )
                conn.commit()
            while len(self._history) > _MAX_HISTORY:
                oldest = min(self._history, key=lambda k: self._history[k].get("created_at", ""))
                del self._history[oldest]
        except Exception:
            pass

    def list_all(self, limit: int = 20) -> List[dict]:
        combined: Dict[str, dict] = {}
        for eid, data in self._history.items():
            combined[eid] = data
        for eid, execution in self._live.items():
            combined[eid] = execution.to_dict()
        sorted_execs = sorted(combined.values(), key=lambda e: e.get("created_at", ""), reverse=True)
        return sorted_execs[:limit]


_execution_store = ExecutionStore()
_executions_lock = asyncio.Lock()
_active_subprocesses: dict[str, subprocess.Popen] = {}
_background_tasks: set[asyncio.Task] = set()

TASK_RESOURCE_MAP = {
    "preflight_check": "tasks/preflight_check_ocm_role.yml",
    "create_rosa_network": "tasks/create_rosa_network.yml",
    "create_rosa_role_config": "tasks/create_rosa_role_config.yml",
    "verify_oidc": "tasks/wait_for_rosa_roles.yml",
    "create_control_plane": "playbooks/create_rosa_hcp_automated.yaml",
    "wait_for_cluster_ready": "tasks/wait_for_rosa_control_plane_ready.yml",
    "delete_control_plane": "tasks/sf_delete_control_plane.yml",
    "wait_for_control_plane_deleted": "tasks/sf_wait_control_plane_deleted.yml",
    "delete_rosa_network": "tasks/sf_delete_rosa_network.yml",
    "delete_rosa_role_config": "tasks/sf_delete_rosa_role_config.yml",
    "verify_cleanup": "tasks/sf_verify_deletion_complete.yml",
    "login_ocp": "tasks/login_ocp.yml",
    "enable_capi_capa": "tasks/enable_capi_capa.yml",
    "wait_for_capi_capa_ready": "tasks/wait-for-capi-capa-ready.yml",
    "create_namespace": "tasks/create_namespace.yml",
    "create_aws_credentials": "tasks/create_capa_manager_bootstrap_credentials.yml",
    "create_rosa_creds_secret": "tasks/create_rosa_creds_secret.yml",
    "set_registration_config": "tasks/set_registration_configuration.yml",
    "set_aws_identity_restart": "tasks/set_aws_identity.yml",
    "validate_capa_environment": "tasks/validate-capa-environment.yml",
    "upgrade_control_plane": "playbooks/upgrade_rosa_control_plane.yml",
    "upgrade_machine_pool": "playbooks/upgrade_rosa_machine_pool.yml",
}


def get_execution_mode() -> ExecutionMode:
    mode = os.environ.get("ORCHESTRATOR_MODE", "local").lower()
    if mode == "aws":
        return ExecutionMode.AWS
    if mode == "celery":
        return ExecutionMode.CELERY
    return ExecutionMode.LOCAL


def list_state_machines() -> List[dict]:
    return [
        {
            "name": name,
            "comment": defn.get("Comment", ""),
            "states": list(defn.get("States", {}).keys()),
        }
        for name, defn in STATE_MACHINES.items()
    ]


async def start_execution(
    state_machine_name: str,
    input_params: dict,
    mode: Optional[ExecutionMode] = None,
) -> StateMachineExecution:
    if state_machine_name not in STATE_MACHINES:
        raise ValueError(f"Unknown state machine: {state_machine_name}")

    if mode is None:
        mode = get_execution_mode()

    execution_id = f"sf-{uuid.uuid4().hex[:12]}"
    execution = StateMachineExecution(execution_id, state_machine_name, input_params, mode)

    async with _executions_lock:
        _execution_store.register(execution)

    if mode == ExecutionMode.CELERY:
        task = asyncio.create_task(_run_celery_execution(execution))
    elif mode == ExecutionMode.LOCAL:
        task = asyncio.create_task(_run_local_execution(execution))
    else:
        task = asyncio.create_task(_run_aws_execution(execution))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return execution


async def get_execution(execution_id: str) -> Optional[StateMachineExecution]:
    return _execution_store.get(execution_id)


async def get_execution_dict(execution_id: str) -> Optional[dict]:
    return _execution_store.get_dict(execution_id)


async def list_executions(limit: int = 20) -> List[dict]:
    return _execution_store.list_all(limit)


async def cancel_execution(execution_id: str) -> bool:
    execution = _execution_store.get(execution_id)
    if not execution:
        return False
    execution.cancel()
    for key in list(_active_subprocesses.keys()):
        if key.startswith(f"{execution_id}:"):
            proc = _active_subprocesses.pop(key, None)
            if proc and proc.poll() is None:
                logger.warning(f"Killing subprocess for cancelled execution {key} (pid={proc.pid})")
                _kill_process_tree(proc)
    _execution_store.persist(execution)
    return True


def _check_k8s_resource_exists(resource_type: str, name: str, namespace: str) -> bool:
    """Check whether a K8s resource exists. Returns False on any error."""
    try:
        result = subprocess.run(
            ["oc", "get", resource_type, name, "-n", namespace,
             "--no-headers", "--ignore-not-found"],
            capture_output=True, text=True, timeout=15,
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


_PROVISION_STEP_RESOURCE_CHECKS = {
    "CreateROSANetwork": ("rosanetwork", "rosa_network_name"),
    "CreateRosaRoleConfig": ("rosaroleconfig", "rosa_role_config_name"),
    "VerifyOIDC": ("rosaroleconfig", "rosa_role_config_name"),
}

_DELETE_STEP_RESOURCE_CHECKS = {
    "DeleteROSANetwork": ("rosanetwork", "rosa_network_name"),
    "DeleteRosaRoleConfig": ("rosaroleconfig", "rosa_role_config_name"),
}


def _validate_succeeded_steps(execution: StateMachineExecution) -> None:
    """Reset steps marked SUCCEEDED whose K8s resource state contradicts completion."""
    namespace = execution.input_params.get("capi_namespace", "ns-rosa-hcp")

    is_provision = execution.state_machine_name in ("rosa-hcp-provision",)
    is_delete = execution.state_machine_name in ("rosa-hcp-delete",)

    if is_provision:
        for step_name, (resource_type, param_key) in _PROVISION_STEP_RESOURCE_CHECKS.items():
            step = execution.steps.get(step_name)
            if not step or step.status != StepStatus.SUCCEEDED:
                continue
            resource_name = execution.input_params.get(param_key, "")
            if not resource_name:
                continue
            if not _check_k8s_resource_exists(resource_type, resource_name, namespace):
                logger.warning(
                    f"Resurrection guard: step '{step_name}' was SUCCEEDED but "
                    f"{resource_type}/{resource_name} not found in {namespace}"
                    " — resetting to PENDING"
                )
                step.status = StepStatus.PENDING
                step.error = None
                step.completed_at = None

    if is_delete:
        for step_name, (resource_type, param_key) in _DELETE_STEP_RESOURCE_CHECKS.items():
            step = execution.steps.get(step_name)
            if not step or step.status != StepStatus.SUCCEEDED:
                continue
            resource_name = execution.input_params.get(param_key, "")
            if not resource_name:
                continue
            if _check_k8s_resource_exists(resource_type, resource_name, namespace):
                logger.warning(
                    f"Resurrection guard: step '{step_name}' was SUCCEEDED but "
                    f"{resource_type}/{resource_name} still exists in {namespace}"
                    " — resetting to PENDING"
                )
                step.status = StepStatus.PENDING
                step.error = None
                step.completed_at = None


async def resume_execution(execution_id: str) -> Optional[StateMachineExecution]:
    """Resume a failed/crashed execution from its last checkpoint."""
    data = _execution_store.get_dict(execution_id)
    if not data:
        return None

    if data.get("status") not in ("failed", "cancelled"):
        return None

    execution = StateMachineExecution.from_dict(data)

    for step in execution.steps.values():
        if step.status in (StepStatus.FAILED, StepStatus.CANCELLED, StepStatus.RUNNING,
                           StepStatus.TIMED_OUT):
            step.status = StepStatus.PENDING
            step.error = None
            step.completed_at = None

    _validate_succeeded_steps(execution)

    execution.status = StepStatus.RUNNING
    execution.error = None
    execution.completed_at = None

    async with _executions_lock:
        _execution_store.register(execution)

    task = asyncio.create_task(_run_local_execution(execution))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return execution


async def _run_local_execution(execution: StateMachineExecution):
    """Execute workflow locally using asyncio for parallelism."""
    execution.status = StepStatus.RUNNING
    execution.started_at = datetime.utcnow().isoformat()

    if AGENTS_AVAILABLE:
        try:
            jobs[execution.execution_id] = {
                "id": execution.execution_id,
                "status": "running",
                "logs": [],
                "agent_events": [],
                "created_at": execution.created_at,
            }
            execution.agent_session = init_ai_agents(execution.execution_id)
            logger.info(f"AI agents initialized for execution {execution.execution_id}")
        except Exception as e:
            logger.warning(f"Failed to initialize AI agents: {e}")

    definition = STATE_MACHINES.get(execution.state_machine_name, {})
    states = definition.get("States", {})
    current_state = definition.get("StartAt")

    try:
        while current_state and not execution._cancelled:
            state_def = states.get(current_state)
            if not state_def:
                raise RuntimeError(f"State '{current_state}' not found in definition")

            step = execution.steps.get(current_state)
            if step and step.status == StepStatus.SUCCEEDED:
                logger.info(f"Skipping completed step '{current_state}'")
                if state_def.get("End"):
                    break
                current_state = state_def.get("Next")
                continue

            state_type = state_def.get("Type")

            if state_type == "Task":
                success = await _execute_local_task(execution, current_state, state_def)
                if not success:
                    execution.status = StepStatus.FAILED
                    execution.error = f"Step '{current_state}' failed"
                    execution.completed_at = datetime.utcnow().isoformat()
                    return

            elif state_type == "StateMachine":
                success = await _execute_nested_state_machine(execution, current_state, state_def)
                if not success:
                    execution.status = StepStatus.FAILED
                    execution.error = f"Nested state machine '{current_state}' failed"
                    execution.completed_at = datetime.utcnow().isoformat()
                    return

            elif state_type == "Parallel":
                success = await _execute_local_parallel(execution, current_state, state_def)
                if not success:
                    execution.status = StepStatus.FAILED
                    execution.error = f"Parallel group '{current_state}' had failures"
                    execution.completed_at = datetime.utcnow().isoformat()
                    return

            _execution_store.persist(execution)

            if state_def.get("End"):
                break
            current_state = state_def.get("Next")

        if execution._cancelled:
            return

        execution.status = StepStatus.SUCCEEDED
        execution.completed_at = datetime.utcnow().isoformat()
        logger.info(f"Execution {execution.execution_id} completed successfully")

    except Exception as e:
        execution.status = StepStatus.FAILED
        execution.error = str(e)
        execution.completed_at = datetime.utcnow().isoformat()
        logger.error(f"Execution {execution.execution_id} failed: {e}")
    finally:
        _finalize_agents(execution)
        _execution_store.persist(execution)


async def _run_celery_execution(execution: StateMachineExecution):
    """Execute workflow via Celery distributed task queue."""
    from celery_tasks import execute_ansible_step
    from redis_events import publish_step_event

    execution.status = StepStatus.RUNNING
    execution.started_at = datetime.utcnow().isoformat()

    definition = STATE_MACHINES.get(execution.state_machine_name, {})
    states = definition.get("States", {})
    current_state = definition.get("StartAt")

    try:
        while current_state and not execution._cancelled:
            state_def = states.get(current_state)
            if not state_def:
                raise RuntimeError(f"State '{current_state}' not found in definition")

            step = execution.steps.get(current_state)
            if step and step.status == StepStatus.SUCCEEDED:
                logger.info(f"[celery] Skipping completed step '{current_state}'")
                if state_def.get("End"):
                    break
                current_state = state_def.get("Next")
                continue

            state_type = state_def.get("Type")

            if state_type == "Task":
                success = await _execute_celery_task(execution, current_state, state_def)
                if not success:
                    execution.status = StepStatus.FAILED
                    execution.error = f"Step '{current_state}' failed"
                    execution.completed_at = datetime.utcnow().isoformat()
                    return

            elif state_type == "StateMachine":
                success = await _execute_nested_state_machine(execution, current_state, state_def)
                if not success:
                    execution.status = StepStatus.FAILED
                    execution.error = f"Nested state machine '{current_state}' failed"
                    execution.completed_at = datetime.utcnow().isoformat()
                    return

            elif state_type == "Parallel":
                success = await _execute_celery_parallel(execution, current_state, state_def)
                if not success:
                    execution.status = StepStatus.FAILED
                    execution.error = f"Parallel group '{current_state}' had failures"
                    execution.completed_at = datetime.utcnow().isoformat()
                    return

            _execution_store.persist(execution)

            if state_def.get("End"):
                break
            current_state = state_def.get("Next")

        if execution._cancelled:
            return

        execution.status = StepStatus.SUCCEEDED
        execution.completed_at = datetime.utcnow().isoformat()
        logger.info(f"[celery] Execution {execution.execution_id} completed successfully")

    except Exception as e:
        execution.status = StepStatus.FAILED
        execution.error = str(e)
        execution.completed_at = datetime.utcnow().isoformat()
        logger.error(f"[celery] Execution {execution.execution_id} failed: {e}")
    finally:
        _finalize_agents(execution)
        _execution_store.persist(execution)


async def _execute_celery_task(
    execution: StateMachineExecution, state_name: str, state_def: dict
) -> bool:
    """Dispatch a single task step to a Celery worker and poll for completion."""
    from celery_tasks import execute_ansible_step

    step = execution.steps.get(state_name)
    if not step:
        return False

    if step.status == StepStatus.SUCCEEDED:
        return True

    step.status = StepStatus.RUNNING
    step.started_at = datetime.utcnow().isoformat()

    resource = state_def.get("Resource", state_name)
    task_file = TASK_RESOURCE_MAP.get(resource)
    if not task_file:
        step.status = StepStatus.FAILED
        step.error = f"No task file mapped for resource '{resource}'"
        step.completed_at = datetime.utcnow().isoformat()
        return False

    from celery_tasks import _strip_sensitive

    extra_vars = {**execution.input_params}
    _TEMPLATE_OVERRIDE_TASKS = {"create_rosa_role_config", "create_rosa_network"}
    if resource in _TEMPLATE_OVERRIDE_TASKS:
        extra_vars.pop("template_name", None)
        extra_vars.pop("template_category", None)

    safe_vars = _strip_sensitive(extra_vars)

    retry_config = None
    if state_def.get("Retry"):
        rc = state_def["Retry"][0]
        retry_config = {
            "max_attempts": rc.get("MaxAttempts", 0),
            "interval": rc.get("IntervalSeconds", 10),
            "backoff_rate": rc.get("BackoffRate", 2.0),
        }

    try:
        async_result = execute_ansible_step.apply_async(
            kwargs={
                "execution_id": execution.execution_id,
                "step_name": state_name,
                "resource": resource,
                "task_file": task_file,
                "extra_vars": safe_vars,
                "timeout": step.timeout,
                "retry_config": retry_config,
            },
            soft_time_limit=step.timeout,
            time_limit=step.timeout + 60,
        )
        step.job_id = async_result.id

        while not execution._cancelled:
            await asyncio.sleep(3)
            if async_result.ready():
                break

        if execution._cancelled:
            try:
                async_result.revoke(terminate=True)
            except Exception:
                pass
            step.status = StepStatus.CANCELLED
            step.completed_at = datetime.utcnow().isoformat()
            return False

        try:
            result = async_result.result
        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = f"Failed to retrieve task result: {e}"
            step.completed_at = datetime.utcnow().isoformat()
            return False

        step.completed_at = datetime.utcnow().isoformat()

        if isinstance(result, dict) and result.get("success"):
            step.status = StepStatus.SUCCEEDED
            step.output = result.get("output", "")
            return True
        else:
            step.status = StepStatus.FAILED
            step.error = result.get("error", "Task failed") if isinstance(result, dict) else str(result)
            return False

    except Exception as e:
        step.status = StepStatus.FAILED
        step.error = str(e)
        step.completed_at = datetime.utcnow().isoformat()
        return False


async def _execute_celery_parallel(
    execution: StateMachineExecution, state_name: str, state_def: dict
) -> bool:
    """Dispatch parallel branches to Celery workers using celery.group."""
    from celery import group as celery_group
    from celery_tasks import execute_ansible_step

    branches = state_def.get("Branches", [])

    all_done = all(
        (step := execution.steps.get(b.get("StartAt"))) is not None
        and step.status == StepStatus.SUCCEEDED
        for b in branches if b.get("StartAt")
    )
    if all_done and branches:
        return True

    tasks = []
    step_names = []
    for branch in branches:
        branch_start = branch.get("StartAt")
        branch_states = branch.get("States", {})
        if not branch_start or branch_start not in branch_states:
            continue

        task_def = branch_states[branch_start]
        resource = task_def.get("Resource", branch_start)
        task_file = TASK_RESOURCE_MAP.get(resource)
        if not task_file:
            continue

        step = execution.steps.get(branch_start)
        if step and step.status == StepStatus.SUCCEEDED:
            continue

        if step:
            step.status = StepStatus.RUNNING
            step.started_at = datetime.utcnow().isoformat()

        from celery_tasks import _strip_sensitive

        extra_vars = {**execution.input_params}
        _TEMPLATE_OVERRIDE_TASKS = {"create_rosa_role_config", "create_rosa_network"}
        if resource in _TEMPLATE_OVERRIDE_TASKS:
            extra_vars.pop("template_name", None)
            extra_vars.pop("template_category", None)

        safe_vars = _strip_sensitive(extra_vars)

        retry_config = None
        if task_def.get("Retry"):
            rc = task_def["Retry"][0]
            retry_config = {
                "max_attempts": rc.get("MaxAttempts", 0),
                "interval": rc.get("IntervalSeconds", 10),
                "backoff_rate": rc.get("BackoffRate", 2.0),
            }

        timeout = task_def.get("TimeoutSeconds", 300)
        tasks.append(execute_ansible_step.s(
            execution_id=execution.execution_id,
            step_name=branch_start,
            resource=resource,
            task_file=task_file,
            extra_vars=safe_vars,
            timeout=timeout,
            retry_config=retry_config,
        ))
        step_names.append(branch_start)

    if not tasks:
        return True

    job = celery_group(tasks)
    group_result = job.apply_async()

    while not execution._cancelled:
        await asyncio.sleep(3)
        if group_result.ready():
            break

    if execution._cancelled:
        for child in group_result.children or []:
            child.revoke(terminate=True)
        return False

    all_ok = True
    for i, child_result in enumerate(group_result.results):
        step_name = step_names[i] if i < len(step_names) else None
        step = execution.steps.get(step_name) if step_name else None

        try:
            result = child_result.result
            if step:
                step.completed_at = datetime.utcnow().isoformat()
                if isinstance(result, dict) and result.get("success"):
                    step.status = StepStatus.SUCCEEDED
                    step.output = result.get("output", "")
                else:
                    step.status = StepStatus.FAILED
                    step.error = result.get("error", "Task failed") if isinstance(result, dict) else str(result)
                    all_ok = False
        except Exception as e:
            if step:
                step.status = StepStatus.FAILED
                step.error = str(e)
                step.completed_at = datetime.utcnow().isoformat()
            all_ok = False

    return all_ok


def _finalize_agents(execution: StateMachineExecution):
    """Collect agent events and run learning summary."""
    if not AGENTS_AVAILABLE:
        return
    try:
        if execution.execution_id in jobs:
            execution.agent_events = jobs[execution.execution_id].get("agent_events", [])
        if execution.agent_session and execution.agent_session.get("learning"):
            execution.agent_session["learning"].end_of_run_summary()
    except Exception as e:
        logger.warning(f"Agent finalization error: {e}")


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """Kill a subprocess and its entire process group, with verification."""
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(pgid, signal.SIGKILL)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.error(
                    f"Process {proc.pid} (pgid={pgid}) survived SIGKILL"
                )
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
            proc.wait(timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            pass

    if proc.poll() is None:
        logger.error(
            f"Zombie process {proc.pid} still running after kill attempts"
        )


def _kill_active_subprocess(execution_id: str, step_name: str) -> None:
    """Kill a subprocess left behind after an async timeout.

    Also closes proc.stdout to unblock any thread stuck on os.read()
    or readline() — the asyncio.wait_for timeout cannot interrupt a
    blocked OS-level read in a thread, so closing the FD is the only
    way to free the thread.
    """
    proc_key = f"{execution_id}:{step_name}"
    proc = _active_subprocesses.pop(proc_key, None)
    if proc:
        if proc.poll() is None:
            logger.warning(f"Killing zombie subprocess for {proc_key} (pid={proc.pid})")
            _kill_process_tree(proc)
        # Close stdout pipe to unblock any thread doing os.read()/readline()
        try:
            if proc.stdout and not proc.stdout.closed:
                proc.stdout.close()
        except Exception:
            pass


async def _execute_local_task(
    execution: StateMachineExecution, state_name: str, state_def: dict
) -> bool:
    """Execute a single task step locally by running the mapped Ansible task."""
    step = execution.steps.get(state_name)
    if not step:
        return False

    if step.status == StepStatus.SUCCEEDED:
        logger.info(f"Skipping completed task '{state_name}'")
        return True

    step.status = StepStatus.RUNNING
    step.started_at = datetime.utcnow().isoformat()

    resource = state_def.get("Resource", state_name)
    task_file = TASK_RESOURCE_MAP.get(resource)

    if not task_file:
        step.status = StepStatus.FAILED
        step.error = f"No task file mapped for resource '{resource}'"
        step.completed_at = datetime.utcnow().isoformat()
        return False

    try:
        project_root = os.environ.get("AUTOMATION_PATH") or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

        job_id = str(uuid.uuid4())
        step.job_id = job_id

        extra_vars = {**execution.input_params}

        # Tasks that resolve their own templates must not inherit the
        # orchestrator's default template_name/template_category, because
        # Ansible -e vars override set_fact inside the task file.
        _TEMPLATE_OVERRIDE_TASKS = {
            "create_rosa_role_config", "create_rosa_network",
        }
        if resource in _TEMPLATE_OVERRIDE_TASKS:
            extra_vars.pop("template_name", None)
            extra_vars.pop("template_category", None)

        pre_event_count = len(jobs.get(execution.execution_id, {}).get("agent_events", [])) if AGENTS_AVAILABLE else 0

        result = await asyncio.wait_for(
            asyncio.to_thread(
                _run_ansible_task_sync, project_root, task_file, extra_vars, step.timeout,
                execution.execution_id, state_name,
            ),
            timeout=step.timeout + 30,
        )

        step.completed_at = datetime.utcnow().isoformat()

        if AGENTS_AVAILABLE:
            all_events = jobs.get(execution.execution_id, {}).get("agent_events", [])
            new_events = all_events[pre_event_count:]
            for evt in new_events:
                evt["step_name"] = state_name
            step.agent_events.extend(new_events)

        if result["success"]:
            step.status = StepStatus.SUCCEEDED
            step.output = result.get("output", "")
            return True
        else:
            retry_config = state_def.get("Retry", [])
            retried = await _handle_retry(execution, step, state_def, extra_vars, project_root)
            if retried:
                return True
            step.status = StepStatus.FAILED
            step.error = result.get("error", "Task failed")
            return False

    except (asyncio.TimeoutError, TimeoutError):
        step.status = StepStatus.TIMED_OUT
        step.error = f"Timed out after {step.timeout}s"
        step.completed_at = datetime.utcnow().isoformat()
        _kill_active_subprocess(execution.execution_id, state_name)
        return False
    except Exception as e:
        step.status = StepStatus.FAILED
        step.error = str(e)
        step.completed_at = datetime.utcnow().isoformat()
        return False


async def _handle_retry(
    execution: StateMachineExecution, step: StepExecution,
    state_def: dict, extra_vars: dict, project_root: str,
) -> bool:
    retry_configs = state_def.get("Retry", [])
    if not retry_configs:
        return False

    config = retry_configs[0]
    max_attempts = config.get("MaxAttempts", 0)
    interval = config.get("IntervalSeconds", 5)
    backoff = config.get("BackoffRate", 1.0)

    resource = state_def.get("Resource", "")
    task_file = TASK_RESOURCE_MAP.get(resource, "")

    for attempt in range(max_attempts):
        if execution._cancelled:
            return False

        wait_time = interval * (backoff ** attempt)
        logger.info(f"Retry {attempt + 1}/{max_attempts} for {step.name} in {wait_time}s")
        await asyncio.sleep(wait_time)

        step.status = StepStatus.RUNNING
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    _run_ansible_task_sync, project_root, task_file, extra_vars, step.timeout,
                    execution.execution_id, step.name,
                ),
                timeout=step.timeout + 30,
            )
        except (asyncio.TimeoutError, TimeoutError):
            step.status = StepStatus.TIMED_OUT
            step.error = f"Retry {attempt + 1} timed out after {step.timeout}s"
            step.completed_at = datetime.utcnow().isoformat()
            _kill_active_subprocess(execution.execution_id, step.name)
            return False

        if result["success"]:
            step.status = StepStatus.SUCCEEDED
            step.output = result.get("output", "")
            step.completed_at = datetime.utcnow().isoformat()
            return True

    return False


async def _execute_local_parallel(
    execution: StateMachineExecution, state_name: str, state_def: dict
) -> bool:
    """Execute parallel branches concurrently using asyncio.gather."""
    branches = state_def.get("Branches", [])

    all_done = all(
        (step := execution.steps.get(b.get("StartAt"))) is not None
        and step.status == StepStatus.SUCCEEDED
        for b in branches if b.get("StartAt")
    )
    if all_done and branches:
        logger.info(f"Skipping completed parallel group '{state_name}'")
        return True

    tasks = []
    for branch in branches:
        branch_start = branch.get("StartAt")
        branch_states = branch.get("States", {})
        if branch_start and branch_start in branch_states:
            task_def = branch_states[branch_start]
            tasks.append(_execute_local_task(execution, branch_start, task_def))

    if not tasks:
        return True

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_ok = True
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"Parallel branch exception: {r}")
            all_ok = False
        elif not r:
            all_ok = False

    return all_ok


async def _execute_nested_state_machine(
    execution: StateMachineExecution, state_name: str, state_def: dict
) -> bool:
    """Execute a nested state machine as a sub-execution."""
    step = execution.steps.get(state_name)
    if not step:
        return False

    step.status = StepStatus.RUNNING
    step.started_at = datetime.utcnow().isoformat()

    nested_sm_name = state_def.get("Resource", "")
    if nested_sm_name not in STATE_MACHINES:
        step.status = StepStatus.FAILED
        step.error = f"Unknown state machine: {nested_sm_name}"
        step.completed_at = datetime.utcnow().isoformat()
        return False

    try:
        sub_execution = None
        prior_sub_id = getattr(step, "sub_execution_id", None)
        if prior_sub_id:
            prior_data = _execution_store.get_dict(prior_sub_id)
            if prior_data and prior_data.get("status") == "succeeded":
                logger.info(
                    f"Sub-execution {prior_sub_id} already succeeded for "
                    f"nested state machine '{nested_sm_name}' — skipping"
                )
                step.status = StepStatus.SUCCEEDED
                step.completed_at = datetime.utcnow().isoformat()
                return True

            sub_execution = await resume_execution(prior_sub_id)
            if sub_execution:
                logger.info(
                    f"Resumed prior sub-execution {prior_sub_id} for nested "
                    f"state machine '{nested_sm_name}'"
                )

        if not sub_execution:
            sub_execution = await start_execution(
                nested_sm_name, execution.input_params, execution.mode
            )
            step.sub_execution_id = sub_execution.execution_id

        poll_start = time.time()
        while not execution._cancelled:
            await asyncio.sleep(3)
            if time.time() - poll_start > step.timeout:
                await cancel_execution(sub_execution.execution_id)
                step.status = StepStatus.TIMED_OUT
                step.error = f"Nested state machine '{nested_sm_name}' timed out after {step.timeout}s"
                step.completed_at = datetime.utcnow().isoformat()
                return False
            sub = await get_execution(sub_execution.execution_id)
            if not sub:
                break
            if sub.status == StepStatus.SUCCEEDED:
                step.status = StepStatus.SUCCEEDED
                step.completed_at = datetime.utcnow().isoformat()
                step.agent_events.extend(sub.agent_events)
                return True
            elif sub.status in (StepStatus.FAILED, StepStatus.TIMED_OUT, StepStatus.CANCELLED):
                step.status = sub.status
                step.error = sub.error or f"Nested state machine '{nested_sm_name}' {sub.status.value}"
                step.completed_at = datetime.utcnow().isoformat()
                step.agent_events.extend(sub.agent_events)
                return False

        step.status = StepStatus.CANCELLED
        step.completed_at = datetime.utcnow().isoformat()
        return False

    except Exception as e:
        step.status = StepStatus.FAILED
        step.error = str(e)
        step.completed_at = datetime.utcnow().isoformat()
        return False


_TASK_TEMPLATE_MAP = {
    "create_rosa_role_config": ("rosa-role-config", "features"),
    "create_rosa_network": ("rosa-network-config", "features"),
}


def _resolve_template_name(task_file: str) -> str:
    for key, (name, _) in _TASK_TEMPLATE_MAP.items():
        if key in task_file:
            return name
    return "rosa-controlplane-only"


def _resolve_template_category(task_file: str) -> str:
    for key, (_, cat) in _TASK_TEMPLATE_MAP.items():
        if key in task_file:
            return cat
    return "features"


def _run_ansible_task_sync(
    project_root: str, task_file: str, extra_vars: dict, timeout: int,
    execution_id: str = None, step_name: str = None,
) -> dict:
    """Run an Ansible playbook or task file using playbook_executor.

    For playbook files (playbooks/*.yml): runs directly.
    For task files (tasks/*.yml): wraps in a temporary playbook first.
    Credentials are passed via environment variables, not command line.
    """
    import sys
    sys.path.insert(0, project_root)

    file_path = os.path.join(project_root, task_file)
    if not os.path.exists(file_path):
        return {"success": False, "error": f"File not found: {task_file}"}

    is_playbook = task_file.startswith("playbooks/")

    if is_playbook:
        playbook_path = file_path
    else:
        import tempfile
        venv_bin = os.path.join(project_root, "ui", "backend", "venv", "bin")
        name_prefix = extra_vars.get("name_prefix", "")
        cluster_name = f"{name_prefix}-rosa-hcp" if name_prefix else extra_vars.get("cluster_name", "test-cluster")
        az_count = int(extra_vars.get("availability_zone_count", "1"))
        region = extra_vars.get("aws_region", "us-west-2")
        az_suffixes = ["a", "b", "c"]
        az_list = [f"{region}{az_suffixes[i]}" for i in range(min(az_count, 3))]
        az_list_yaml = "[" + ", ".join(f'"{az}"' for az in az_list) + "]"
        playbook_content = f"""---
- hosts: localhost
  connection: local
  gather_facts: true
  vars:
    ansible_python_interpreter: {venv_bin}/python
    cluster_name: "{cluster_name}"
    name_prefix: "{name_prefix}"
    capi_namespace: "{extra_vars.get('capi_namespace', 'ns-rosa-hcp')}"
    openshift_version: "{extra_vars.get('openshift_version', '4.20.10')}"
    aws_region: "{region}"
    rosa_role_prefix: "{cluster_name}"
    rosa_role_config_name: "{cluster_name}-roles"
    rosa_network_name: "{cluster_name}-network"
    rosa_network_config_name: "{cluster_name}-network"
    network_cidr: "{extra_vars.get('network_cidr', '10.0.0.0/16')}"
    availability_zone_count: {az_count}
    availability_zones_list: {az_list_yaml}
    create_rosa_roles: {extra_vars.get('create_rosa_roles', 'true')}
    create_rosa_network: {extra_vars.get('create_rosa_network', 'true')}
    rcp_version: "{extra_vars.get('openshift_version', '4.20.10')}"
    template_name: "{_resolve_template_name(task_file)}"
    template_category: "{_resolve_template_category(task_file)}"
    channel: ""
    channel_group: ""
    fips: false
    manual_subnets: []
    cluster_description: ""
    domain_prefix: "{name_prefix}"
    cluster_name_prefix: "{name_prefix}"
    machine_pool: {{}}
    environment_tag: "test"
    purpose_tag: "orchestrator-testing"
    log_forward_enabled: false
    rosa_creds_secret: "rosa-creds-secret"
    cluster_network:
      machine_cidr: "10.0.0.0/16"
      pod_cidr: "10.128.0.0/14"
      service_cidr: "172.30.0.0/16"
    aws_account_id: "{{{{ lookup('pipe', 'aws sts get-caller-identity --query Account --output text 2>/dev/null || echo unknown') }}}}"
  environment:
    PATH: "{venv_bin}:{{{{ ansible_env.PATH }}}}"
    VIRTUAL_ENV: "{os.path.join(project_root, 'ui', 'backend', 'venv')}"
  vars_files:
    - {project_root}/vars/vars.yml
    - {project_root}/vars/user_vars.yml
  tasks:
    - include_tasks: {file_path}
"""
        playbooks_dir = os.path.join(project_root, "playbooks")
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False, dir=playbooks_dir)
        tmp.write(playbook_content)
        tmp.close()
        playbook_path = tmp.name

    name_prefix = extra_vars.get("name_prefix", "")
    derived_cluster_name = f"{name_prefix}-rosa-hcp" if name_prefix else extra_vars.get("cluster_name", "test-cluster")
    region = extra_vars.get("aws_region", "us-west-2")
    az_count = int(extra_vars.get("availability_zone_count", "1"))
    az_suffixes = ["a", "b", "c"]
    az_list = [f"{region}{az_suffixes[i]}" for i in range(min(az_count, 3))]

    merged_vars = {
        "skip_ansible_runner": "true",
        "AUTOMATION_PATH": project_root,
        "automation_path": project_root,
        "cluster_name": derived_cluster_name,
        "capi_namespace": extra_vars.get("capi_namespace", "ns-rosa-hcp"),
        "openshift_version": extra_vars.get("openshift_version", "4.20.10"),
        "rcp_version": extra_vars.get("openshift_version", "4.20.10"),
        "aws_region": region,
        "rosa_role_prefix": derived_cluster_name,
        "rosa_role_config_name": f"{derived_cluster_name}-roles",
        "rosa_network_name": f"{derived_cluster_name}-network",
        "rosa_network_config_name": f"{derived_cluster_name}-network",
        "network_cidr": extra_vars.get("network_cidr", "10.0.0.0/16"),
        "availability_zone_count": az_count,
        "create_rosa_roles": extra_vars.get("create_rosa_roles", "true"),
        "create_rosa_network": extra_vars.get("create_rosa_network", "true"),
        "domain_prefix": name_prefix or derived_cluster_name,
        "cluster_name_prefix": name_prefix or derived_cluster_name,
        "ocp_user": extra_vars.get("OCP_HUB_CLUSTER_USER", ""),
        "ocp_password": extra_vars.get("OCP_HUB_CLUSTER_PASSWORD", ""),
        "api_url": extra_vars.get("OCP_HUB_API_URL", ""),
        "mce_namespace": extra_vars.get("MCE_NAMESPACE", "multicluster-engine"),
        "MCE_NAMESPACE": extra_vars.get("MCE_NAMESPACE", "multicluster-engine"),
        "template_name": _resolve_template_name(task_file),
        "template_category": _resolve_template_category(task_file),
        "channel": "",
        "channel_group": "",
        "fips": False,
        "cluster_description": "",
        "rosa_creds_secret": "rosa-creds-secret",
        "environment_tag": "test",
        "purpose_tag": "orchestrator-testing",
        "log_forward_enabled": False,
        "log_forward_cloudwatch_role_arn": "",
        "log_forward_cloudwatch_log_group": "",
        "log_forward_s3_bucket": "",
        "log_forward_s3_prefix": "",
        "availability_zones_list": az_list,
        "machine_pool": {},
        "manual_subnets": [],
        "cluster_network": {
            "machine_cidr": "10.0.0.0/16",
            "pod_cidr": "10.128.0.0/14",
            "service_cidr": "172.30.0.0/16",
        },
        **{k: v for k, v in extra_vars.items() if v is not None and v != ""},
    }

    try:
        import subprocess as _sp
        aws_account = _sp.run(
            ["aws", "sts", "get-caller-identity", "--query", "Account", "--output", "text"],
            capture_output=True, text=True, timeout=10, env=os.environ.copy()
        )
        if aws_account.returncode == 0 and aws_account.stdout.strip():
            merged_vars["aws_account_id"] = aws_account.stdout.strip()
    except Exception:
        pass

    try:
        oc_ctx = _sp.run(
            ["oc", "config", "current-context"],
            capture_output=True, text=True, timeout=10
        )
        if oc_ctx.returncode == 0 and oc_ctx.stdout.strip():
            merged_vars["ocp_context"] = oc_ctx.stdout.strip()
    except Exception:
        pass

    agent_session = ai_agent_sessions.get(execution_id) if (AGENTS_AVAILABLE and execution_id) else None
    agent_lock = threading.Lock()
    agent_seen_lines: set[str] = set()

    is_deletion = "delete" in task_file.lower()
    is_provisioning = "create" in task_file.lower() or "provision" in task_file.lower()
    use_sidecar = (is_deletion or is_provisioning) and agent_session
    sidecar_stop = threading.Event()
    sidecar_thread = None

    if use_sidecar:
        cluster_name_for_sidecar = merged_vars.get("cluster_name", "unknown")
        sidecar_logfile = f"/tmp/{'deletion' if is_deletion else 'provision'}-agent-{cluster_name_for_sidecar}.log"

        def _tail_sidecar():
            last_pos = 0
            while not sidecar_stop.is_set():
                try:
                    if os.path.exists(sidecar_logfile):
                        with open(sidecar_logfile, 'r') as f:
                            f.seek(last_pos)
                            for line in f:
                                line = line.strip()
                                if line and agent_session.get("monitor"):
                                    with agent_lock:
                                        if line not in agent_seen_lines:
                                            agent_seen_lines.add(line)
                                            try:
                                                agent_session["monitor"].process_line(line)
                                            except Exception:
                                                pass
                            last_pos = f.tell()
                except Exception:
                    pass
                sidecar_stop.wait(2)

        sidecar_thread = threading.Thread(target=_tail_sidecar, daemon=True)
        sidecar_thread.start()

    vars_file_path = None
    proc_key = f"{execution_id}:{step_name}" if execution_id else f"anon:{id(task_file)}"
    try:
        import tempfile as _tmpmod
        from playbook_executor import build_playbook_command, SENSITIVE_KEYS

        if is_playbook:
            # For full playbooks, write vars to a JSON file and use @file
            # syntax. This preserves dicts/lists/booleans that -e mangles.
            env = os.environ.copy()
            cmd = ["ansible-playbook", playbook_path, "-v", "-i", "localhost,"]

            # Separate credentials into env vars (not on command line)
            file_vars = {}
            for k, v in merged_vars.items():
                if str(k).lower() in SENSITIVE_KEYS:
                    env[str(k).upper()] = str(v).strip() if v is not None else ""
                    # Also pass via -e so the playbook can use them as Ansible vars
                    cmd.extend(["-e", f"{k}={v}"])
                else:
                    file_vars[k] = v

            vars_tmp = _tmpmod.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False,
                prefix="orchestrator_vars_",
            )
            json.dump(file_vars, vars_tmp, default=str)
            vars_tmp.close()
            vars_file_path = vars_tmp.name
            cmd.extend(["-e", f"@{vars_file_path}"])
        else:
            # For task wrappers, keep existing -e approach (vars are in
            # the generated playbook's vars: block already)
            cmd, env = build_playbook_command(playbook_path, merged_vars, verbosity=1)
            cmd.extend(["-i", "localhost,"])
            for k, v in merged_vars.items():
                if str(k).lower() in SENSITIVE_KEYS and v:
                    cmd.extend(["-e", f"{k}={v}"])

        env["PYTHONUNBUFFERED"] = "1"

        proc = subprocess.Popen(
            cmd, cwd=project_root,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, env=env,
            start_new_session=True,
        )
        _active_subprocesses[proc_key] = proc

        cpu_samples: list[dict] = []
        cpu_stop = threading.Event()

        def _sample_cpu():
            try:
                import psutil
            except ImportError:
                return
            if not isinstance(proc.pid, int):
                return
            backend_proc = psutil.Process()
            backend_proc.cpu_percent()
            try:
                child_proc = psutil.Process(proc.pid)
                child_proc.cpu_percent()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                child_proc = None
            while not cpu_stop.wait(10):
                sample = {"t": time.time(), "backend": backend_proc.cpu_percent()}
                try:
                    if child_proc and child_proc.is_running():
                        kids = child_proc.children(recursive=True)
                        sample["subprocess"] = child_proc.cpu_percent()
                        sample["child_tree"] = sum(c.cpu_percent() for c in kids)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                cpu_samples.append(sample)

        cpu_thread = threading.Thread(target=_sample_cpu, daemon=True)
        cpu_thread.start()

        output_lines = []
        deadline = time.time() + timeout

        # Read stdout using raw os.read() with select() to prevent the
        # thread from blocking indefinitely.  The previous approach used
        # select() + proc.stdout.readline(), but readline() is a *buffered*
        # read that blocks waiting for a full line even after select()
        # reports data available — it can hang when a grandchild holds the
        # pipe open and writes partial data (or no newlines).
        #
        # os.read() returns immediately with whatever raw bytes are
        # available (no newline requirement), so select() + os.read()
        # is a truly non-blocking combination.  We split lines manually.
        import select as _select

        try:
            stdout_fd = proc.stdout.fileno()
            use_raw_read = True
        except (AttributeError, io.UnsupportedOperation):
            use_raw_read = False

        _PIPE_GRACE_SECS = 10  # seconds to drain after process exits
        _proc_exit_time: float | None = None
        _raw_buf = ""

        def _feed_agent(line_stripped: str):
            if agent_session and agent_session.get("monitor"):
                with agent_lock:
                    if line_stripped not in agent_seen_lines:
                        agent_seen_lines.add(line_stripped)
                        try:
                            agent_session["monitor"].process_line(line_stripped)
                        except Exception:
                            pass

        if use_raw_read:
            while True:
                if time.time() > deadline:
                    _kill_process_tree(proc)
                    return {"success": False, "error": f"Timed out after {timeout}s"}

                # Detect process exit and enforce grace period
                if proc.poll() is not None:
                    if _proc_exit_time is None:
                        _proc_exit_time = time.time()
                    elif (time.time() - _proc_exit_time) > _PIPE_GRACE_SECS:
                        logger.warning(
                            f"[{step_name}] Pipe still open {_PIPE_GRACE_SECS}s "
                            f"after process exit (pid={proc.pid}). "
                            f"Killing process group and closing pipe."
                        )
                        try:
                            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                        except (ProcessLookupError, PermissionError, OSError):
                            pass
                        break

                ready, _, _ = _select.select([stdout_fd], [], [], 1.0)
                if not ready:
                    continue

                # os.read() returns immediately with available bytes —
                # never blocks waiting for a newline like readline() does.
                try:
                    chunk = os.read(stdout_fd, 65536)
                except OSError:
                    break
                if not chunk:
                    # True EOF — all writers have closed the pipe
                    break

                _raw_buf += chunk.decode("utf-8", errors="replace")
                while "\n" in _raw_buf:
                    line_text, _raw_buf = _raw_buf.split("\n", 1)
                    line_stripped = line_text.rstrip()
                    output_lines.append(line_stripped)
                    _feed_agent(line_stripped)
        else:
            # Fallback for platforms where fileno() is unavailable.
            # Uses a watchdog thread to force-close the pipe if the
            # process exits but the pipe stays open.
            _watchdog_stop = threading.Event()

            def _pipe_watchdog():
                """Close proc.stdout if process dies but pipe stays open."""
                while not _watchdog_stop.wait(2):
                    if proc.poll() is not None:
                        # Process exited — give a grace period to drain
                        _watchdog_stop.wait(_PIPE_GRACE_SECS)
                        if not _watchdog_stop.is_set():
                            logger.warning(
                                f"[{step_name}] Watchdog: force-closing "
                                f"stdout pipe (pid={proc.pid})"
                            )
                            try:
                                proc.stdout.close()
                            except Exception:
                                pass
                        return

            wd_thread = threading.Thread(target=_pipe_watchdog, daemon=True)
            wd_thread.start()
            try:
                for line in proc.stdout:
                    if time.time() > deadline:
                        _kill_process_tree(proc)
                        return {"success": False, "error": f"Timed out after {timeout}s"}
                    line_stripped = line.rstrip()
                    output_lines.append(line_stripped)
                    _feed_agent(line_stripped)
            except ValueError:
                # Pipe was closed by watchdog — expected
                logger.info(f"[{step_name}] stdout closed by watchdog, exiting read loop")
            finally:
                _watchdog_stop.set()
                wd_thread.join(timeout=3)

        # Flush any trailing partial line
        if _raw_buf.strip():
            output_lines.append(_raw_buf.strip())

        # Ensure pipe FD is closed to prevent leaked descriptors
        try:
            proc.stdout.close()
        except Exception:
            pass

        returncode = proc.wait(timeout=10)
        combined_output = "\n".join(output_lines)

        cpu_stop.set()
        cpu_thread.join(timeout=3)
        if cpu_samples:
            backend_avg = sum(s.get("backend", 0) for s in cpu_samples) / len(cpu_samples)
            sub_avg = sum(s.get("subprocess", 0) for s in cpu_samples) / len(cpu_samples)
            tree_avg = sum(s.get("child_tree", 0) for s in cpu_samples) / len(cpu_samples)
            backend_peak = max(s.get("backend", 0) for s in cpu_samples)
            sub_peak = max(s.get("subprocess", 0) for s in cpu_samples)
            tree_peak = max(s.get("child_tree", 0) for s in cpu_samples)
            logger.info(
                f"[CPU] step={step_name} samples={len(cpu_samples)} "
                f"backend_avg={backend_avg:.1f}% peak={backend_peak:.1f}% | "
                f"ansible_avg={sub_avg:.1f}% peak={sub_peak:.1f}% | "
                f"child_tree_avg={tree_avg:.1f}% peak={tree_peak:.1f}%"
            )

        return {
            "success": returncode == 0,
            "output": combined_output[-2000:],
            "error": combined_output[-3000:] if returncode != 0 else "",
        }
    except subprocess.TimeoutExpired:
        _kill_process_tree(proc)
        cpu_stop.set()
        return {"success": False, "error": f"Timed out after {timeout}s"}
    except Exception as e:
        cpu_stop.set()
        return {"success": False, "error": str(e)}
    finally:
        cpu_stop.set()
        _active_subprocesses.pop(proc_key, None)
        sidecar_stop.set()
        if sidecar_thread is not None:
            sidecar_thread.join(timeout=5)
        if not is_playbook:
            try:
                os.unlink(playbook_path)
            except OSError:
                pass
        if vars_file_path:
            try:
                os.unlink(vars_file_path)
            except OSError:
                pass


async def _run_aws_execution(execution: StateMachineExecution):
    """Run via real AWS Step Functions (optional). Requires boto3 and deployed state machine."""
    try:
        import boto3

        sfn = boto3.client("stepfunctions", region_name=execution.input_params.get("aws_region", "us-west-2"))

        state_machine_arn = os.environ.get("ORCHESTRATOR_ARN", "")
        if not state_machine_arn:
            raise RuntimeError("ORCHESTRATOR_ARN environment variable not set")

        execution.status = StepStatus.RUNNING
        execution.started_at = datetime.utcnow().isoformat()

        response = sfn.start_execution(
            stateMachineArn=state_machine_arn,
            name=execution.execution_id,
            input=json.dumps(execution.input_params),
        )

        aws_execution_arn = response["executionArn"]

        while not execution._cancelled:
            await asyncio.sleep(10)
            desc = sfn.describe_execution(executionArn=aws_execution_arn)
            aws_status = desc["status"]

            history = sfn.get_execution_history(
                executionArn=aws_execution_arn,
                reverseOrder=True,
                maxResults=100,
            )
            _sync_aws_history_to_steps(execution, history.get("events", []))

            if aws_status == "SUCCEEDED":
                execution.status = StepStatus.SUCCEEDED
                execution.completed_at = datetime.utcnow().isoformat()
                return
            elif aws_status == "FAILED":
                execution.status = StepStatus.FAILED
                execution.error = desc.get("error", "Execution failed in AWS")
                execution.completed_at = datetime.utcnow().isoformat()
                return
            elif aws_status == "TIMED_OUT":
                execution.status = StepStatus.TIMED_OUT
                execution.completed_at = datetime.utcnow().isoformat()
                return
            elif aws_status == "ABORTED":
                execution.status = StepStatus.CANCELLED
                execution.completed_at = datetime.utcnow().isoformat()
                return

    except ImportError:
        execution.status = StepStatus.FAILED
        execution.error = "boto3 not installed — cannot use AWS mode"
        execution.completed_at = datetime.utcnow().isoformat()
    except Exception as e:
        execution.status = StepStatus.FAILED
        execution.error = str(e)
        execution.completed_at = datetime.utcnow().isoformat()
        logger.error(f"AWS execution failed: {e}")


def _sync_aws_history_to_steps(execution: StateMachineExecution, events: list):
    """Map AWS execution history events to our step tracking."""
    for event in events:
        event_type = event.get("type", "")
        details = event.get("stateEnteredEventDetails") or event.get("stateExitedEventDetails") or {}
        state_name = details.get("name", "")
        step = execution.steps.get(state_name)
        if not step:
            continue

        if "Entered" in event_type and step.status == StepStatus.PENDING:
            step.status = StepStatus.RUNNING
            step.started_at = event["timestamp"].isoformat() if hasattr(event.get("timestamp"), "isoformat") else str(event.get("timestamp"))
        elif "Succeeded" in event_type:
            step.status = StepStatus.SUCCEEDED
            step.completed_at = event["timestamp"].isoformat() if hasattr(event.get("timestamp"), "isoformat") else str(event.get("timestamp"))
        elif "Failed" in event_type:
            step.status = StepStatus.FAILED
            fail_details = event.get("executionFailedEventDetails", {})
            step.error = fail_details.get("cause", "Step failed")
            step.completed_at = event["timestamp"].isoformat() if hasattr(event.get("timestamp"), "isoformat") else str(event.get("timestamp"))


def get_state_machine_definition(name: str) -> Optional[dict]:
    return STATE_MACHINES.get(name)


def get_execution_plan(state_machine_name: str, input_params: dict) -> dict:
    """Dry-run: show what would execute without actually running."""
    definition = STATE_MACHINES.get(state_machine_name)
    if not definition:
        return {"error": f"Unknown state machine: {state_machine_name}"}

    plan = {
        "state_machine": state_machine_name,
        "comment": definition.get("Comment", ""),
        "mode": get_execution_mode().value,
        "input": input_params,
        "steps": [],
        "parallel_groups": [],
        "estimated_time_sequential_seconds": 0,
        "estimated_time_parallel_seconds": 0,
    }

    sequential_total = 0
    parallel_total = 0

    states = definition.get("States", {})
    for state_name, state_def in states.items():
        if state_def.get("Type") == "Task":
            timeout = state_def.get("TimeoutSeconds", 300)
            task_file = TASK_RESOURCE_MAP.get(state_def.get("Resource", ""), "unknown")
            plan["steps"].append({
                "name": state_name,
                "resource": state_def.get("Resource", state_name),
                "task_file": task_file,
                "timeout_seconds": timeout,
                "retry": state_def.get("Retry", []),
                "parallel": False,
            })
            sequential_total += timeout
            parallel_total += timeout
        elif state_def.get("Type") == "StateMachine":
            nested_name = state_def.get("Resource", state_name)
            nested_plan = get_execution_plan(nested_name, input_params)
            nested_seq = nested_plan.get("estimated_time_sequential_seconds", 0)
            nested_par = nested_plan.get("estimated_time_parallel_seconds", 0)
            plan["steps"].append({
                "name": state_name,
                "resource": nested_name,
                "task_file": f"state-machine:{nested_name}",
                "timeout_seconds": nested_seq,
                "retry": [],
                "parallel": False,
                "nested": True,
                "nested_steps": nested_plan.get("steps", []),
            })
            sequential_total += nested_seq
            parallel_total += nested_par
        elif state_def.get("Type") == "Parallel":
            group = []
            branch_max = 0
            for branch in state_def.get("Branches", []):
                for bname, bdef in branch.get("States", {}).items():
                    if bdef.get("Type") == "Task":
                        timeout = bdef.get("TimeoutSeconds", 300)
                        task_file = TASK_RESOURCE_MAP.get(bdef.get("Resource", ""), "unknown")
                        plan["steps"].append({
                            "name": bname,
                            "resource": bdef.get("Resource", bname),
                            "task_file": task_file,
                            "timeout_seconds": timeout,
                            "retry": bdef.get("Retry", []),
                            "parallel": True,
                            "parallel_group": state_name,
                        })
                        sequential_total += timeout
                        branch_max = max(branch_max, timeout)
                        group.append(bname)
            parallel_total += branch_max
            plan["parallel_groups"].append({"name": state_name, "steps": group})

    plan["estimated_time_sequential_seconds"] = sequential_total
    plan["estimated_time_parallel_seconds"] = parallel_total

    return plan
