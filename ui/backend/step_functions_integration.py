"""
AWS Step Functions Integration for ROSA HCP Cluster Orchestration

Replaces sequential Ansible provisioning with parallel state machine execution.
Network, IAM roles, and OIDC setup run concurrently, then converge for
ROSAControlPlane creation — cutting provisioning from ~45 min to ~15-20 min.

Supports two modes:
  - AWS mode: real Step Functions execution via boto3
  - Local mode: simulates parallel execution using asyncio (for dev/testing)
"""

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


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
            "TimeoutSeconds": 300,
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
    "StartAt": "DeleteControlPlane",
    "States": {
        "DeleteControlPlane": {
            "Type": "Task",
            "Comment": "Delete ROSAControlPlane resource",
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

STATE_MACHINES = {
    "rosa-hcp-provision": PROVISION_STATE_MACHINE,
    "rosa-hcp-delete": DELETE_STATE_MACHINE,
    "mce-configure": CONFIGURE_STATE_MACHINE,
    "rosa-hcp-upgrade": UPGRADE_STATE_MACHINE,
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

        self._build_steps_from_definition()

    def _build_steps_from_definition(self):
        definition = STATE_MACHINES.get(self.state_machine_name, {})
        states = definition.get("States", {})

        for state_name, state_def in states.items():
            if state_def.get("Type") == "Task":
                timeout = state_def.get("TimeoutSeconds", 300)
                self.steps[state_name] = StepExecution(
                    name=state_name,
                    resource=state_def.get("Resource", state_name),
                    timeout=timeout,
                )
            elif state_def.get("Type") == "Parallel":
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
        }


# In-memory execution store (keyed by execution_id)
_executions: Dict[str, StateMachineExecution] = {}
_executions_lock = asyncio.Lock()

TASK_RESOURCE_MAP = {
    "preflight_check": "tasks/preflight_check_ocm_role.yml",
    "create_rosa_network": "tasks/create_rosa_network.yml",
    "create_rosa_role_config": "tasks/create_rosa_role_config.yml",
    "verify_oidc": "tasks/wait_for_rosa_roles.yml",
    "create_control_plane": "tasks/create_rosa_control_plane_versioned.yml",
    "wait_for_cluster_ready": "tasks/wait_for_rosa_control_plane_ready.yml",
    "delete_control_plane": "tasks/delete_rosa_control_plane.yml",
    "wait_for_control_plane_deleted": "tasks/wait_for_rosa_control_plane_deleted.yml",
    "delete_rosa_network": "tasks/delete_rosa_network.yml",
    "delete_rosa_role_config": "tasks/delete_rosa_role_config.yml",
    "verify_cleanup": "tasks/verify_deletion_complete.yml",
    "login_ocp": "tasks/login_ocp.yml",
    "enable_capi_capa": "tasks/enable_capi_capa.yml",
    "wait_for_capi_capa_ready": "tasks/wait-for-capi-capa-ready.yml",
    "create_namespace": "tasks/create_output_folder.yml",
    "create_aws_credentials": "tasks/create_capa_manager_bootstrap_credentials.yml",
    "create_rosa_creds_secret": "tasks/create_rosa_creds_secret.yml",
    "set_registration_config": "tasks/set_registration_configuration.yml",
    "set_aws_identity_restart": "tasks/set_aws_identity.yml",
    "validate_capa_environment": "tasks/validate-capa-environment.yml",
    "upgrade_control_plane": "playbooks/upgrade_rosa_control_plane.yml",
    "upgrade_machine_pool": "playbooks/upgrade_rosa_machine_pool.yml",
}


def get_execution_mode() -> ExecutionMode:
    mode = os.environ.get("STEP_FUNCTIONS_MODE", "local").lower()
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
        _executions[execution_id] = execution

    if mode == ExecutionMode.LOCAL:
        asyncio.create_task(_run_local_execution(execution))
    else:
        asyncio.create_task(_run_aws_execution(execution))

    return execution


async def get_execution(execution_id: str) -> Optional[StateMachineExecution]:
    return _executions.get(execution_id)


async def list_executions(limit: int = 20) -> List[dict]:
    execs = sorted(_executions.values(), key=lambda e: e.created_at, reverse=True)
    return [e.to_dict() for e in execs[:limit]]


async def cancel_execution(execution_id: str) -> bool:
    execution = _executions.get(execution_id)
    if not execution:
        return False
    execution.cancel()
    return True


async def _run_local_execution(execution: StateMachineExecution):
    """Simulate Step Functions execution locally using asyncio for parallelism."""
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

            state_type = state_def.get("Type")

            if state_type == "Task":
                success = await _execute_local_task(execution, current_state, state_def)
                if not success:
                    execution.status = StepStatus.FAILED
                    execution.error = f"Step '{current_state}' failed"
                    execution.completed_at = datetime.utcnow().isoformat()
                    return

            elif state_type == "Parallel":
                success = await _execute_local_parallel(execution, current_state, state_def)
                if not success:
                    execution.status = StepStatus.FAILED
                    execution.error = f"Parallel group '{current_state}' had failures"
                    execution.completed_at = datetime.utcnow().isoformat()
                    return

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

        result = await asyncio.to_thread(
            _run_ansible_task_sync, project_root, task_file, extra_vars, step.timeout
        )

        step.completed_at = datetime.utcnow().isoformat()

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
            _run_ansible_task_sync, project_root, task_file, extra_vars, step.timeout
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


def _run_ansible_task_sync(
    project_root: str, task_file: str, extra_vars: dict, timeout: int
) -> dict:
    """Synchronously run an Ansible task file and return the result."""
    import subprocess

    task_path = os.path.join(project_root, task_file)
    if not os.path.exists(task_path):
        return {"success": False, "error": f"Task file not found: {task_file}"}

    playbook_content = f"""---
- hosts: localhost
  connection: local
  gather_facts: false
  tasks:
    - name: Run {task_file}
      include_tasks: {task_path}
"""

    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False, dir=project_root) as f:
        f.write(playbook_content)
        tmp_playbook = f.name

    try:
        cmd = ["ansible-playbook", tmp_playbook, "-v"]

        for k, v in extra_vars.items():
            if v is not None and v != "":
                cmd.extend(["-e", f"{k}={v}"])

        env = os.environ.copy()
        env["ANSIBLE_STDOUT_CALLBACK"] = "yaml"
        env.setdefault("ANSIBLE_HOST_KEY_CHECKING", "False")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=project_root,
            env=env,
        )

        return {
            "success": result.returncode == 0,
            "output": result.stdout[-2000:] if result.stdout else "",
            "error": result.stderr[-1000:] if result.stderr and result.returncode != 0 else "",
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Ansible task timed out after {timeout}s"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        try:
            os.unlink(tmp_playbook)
        except OSError:
            pass


async def _run_aws_execution(execution: StateMachineExecution):
    """Run via real AWS Step Functions. Requires boto3 and deployed state machine."""
    try:
        import boto3

        sfn = boto3.client("stepfunctions", region_name=execution.input_params.get("aws_region", "us-west-2"))

        state_machine_arn = os.environ.get("STEP_FUNCTIONS_ARN", "")
        if not state_machine_arn:
            raise RuntimeError("STEP_FUNCTIONS_ARN environment variable not set")

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
    """Map AWS Step Functions history events to our step tracking."""
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
