"""
Workflow Orchestrator for ROSA HCP Cluster Orchestration

Replaces sequential Ansible provisioning with parallel state machine execution.
Network, IAM roles, and OIDC setup run concurrently, then converge for
ROSAControlPlane creation — cutting provisioning from ~45 min to ~15-20 min.

Uses asyncio for parallel task execution, designed for local and Jenkins CI use.
"""

import asyncio
import json
import logging
import os
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
            for eid, data_json in rows:
                self._history[eid] = json.loads(data_json)
            logger.info(f"Loaded {len(self._history)} execution(s) from history")
        except Exception as e:
            logger.warning(f"Failed to load execution history: {e}")

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
            logger.warning(f"Failed to persist execution {execution.execution_id}: {e}")
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

    if mode == ExecutionMode.LOCAL:
        asyncio.create_task(_run_local_execution(execution))
    else:
        asyncio.create_task(_run_aws_execution(execution))

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
    _execution_store.persist(execution)
    return True


async def resume_execution(execution_id: str) -> Optional[StateMachineExecution]:
    """Resume a failed/crashed execution from its last checkpoint."""
    data = _execution_store.get_dict(execution_id)
    if not data:
        return None

    if data.get("status") not in ("failed", "cancelled"):
        return None

    execution = StateMachineExecution.from_dict(data)

    for step in execution.steps.values():
        if step.status in (StepStatus.FAILED, StepStatus.CANCELLED, StepStatus.RUNNING):
            step.status = StepStatus.PENDING
            step.error = None
            step.completed_at = None

    execution.status = StepStatus.RUNNING
    execution.error = None
    execution.completed_at = None

    async with _executions_lock:
        _execution_store.register(execution)

    asyncio.create_task(_run_local_execution(execution))
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


async def _execute_local_task(
    execution: StateMachineExecution, state_name: str, state_def: dict
) -> bool:
    """Execute a single task step locally by running the mapped Ansible task."""
    step = execution.steps.get(state_name)
    if not step:
        return False

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

        pre_event_count = len(jobs.get(execution.execution_id, {}).get("agent_events", [])) if AGENTS_AVAILABLE else 0

        result = await asyncio.to_thread(
            _run_ansible_task_sync, project_root, task_file, extra_vars, step.timeout,
            execution.execution_id, state_name,
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

    except asyncio.TimeoutError:
        step.status = StepStatus.TIMED_OUT
        step.error = f"Timed out after {step.timeout}s"
        step.completed_at = datetime.utcnow().isoformat()
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
        result = await asyncio.to_thread(
            _run_ansible_task_sync, project_root, task_file, extra_vars, step.timeout,
            execution.execution_id, step.name,
        )

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
        sub_execution = await start_execution(
            nested_sm_name, execution.input_params, execution.mode
        )
        step.sub_execution_id = sub_execution.execution_id

        while not execution._cancelled:
            await asyncio.sleep(3)
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
    template_name: "rosa-controlplane-only"
    template_category: "features"
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
        "availability_zone_count": str(az_count),
        "create_rosa_roles": extra_vars.get("create_rosa_roles", "true"),
        "create_rosa_network": extra_vars.get("create_rosa_network", "true"),
        "domain_prefix": name_prefix or derived_cluster_name,
        "cluster_name_prefix": name_prefix or derived_cluster_name,
        "ocp_user": extra_vars.get("OCP_HUB_CLUSTER_USER", ""),
        "ocp_password": extra_vars.get("OCP_HUB_CLUSTER_PASSWORD", ""),
        "api_url": extra_vars.get("OCP_HUB_API_URL", ""),
        "mce_namespace": extra_vars.get("MCE_NAMESPACE", "multicluster-engine"),
        "MCE_NAMESPACE": extra_vars.get("MCE_NAMESPACE", "multicluster-engine"),
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
                                    try:
                                        with agent_lock:
                                            agent_session["monitor"].process_line(line)
                                    except Exception:
                                        pass
                            last_pos = f.tell()
                except Exception:
                    pass
                sidecar_stop.wait(2)

        sidecar_thread = threading.Thread(target=_tail_sidecar, daemon=True)
        sidecar_thread.start()

    try:
        from playbook_executor import build_playbook_command, SENSITIVE_KEYS
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
        )

        output_lines = []
        for line in proc.stdout:
            line_stripped = line.rstrip()
            output_lines.append(line_stripped)
            if agent_session and agent_session.get("monitor"):
                try:
                    with agent_lock:
                        agent_session["monitor"].process_line(line_stripped)
                except Exception:
                    pass

        returncode = proc.wait(timeout=timeout)
        combined_output = "\n".join(output_lines)

        return {
            "success": returncode == 0,
            "output": combined_output[-2000:],
            "error": combined_output[-3000:] if returncode != 0 else "",
        }
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        return {"success": False, "error": f"Timed out after {timeout}s"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        sidecar_stop.set()
        if sidecar_thread is not None:
            sidecar_thread.join(timeout=5)
        if not is_playbook:
            try:
                os.unlink(playbook_path)
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
