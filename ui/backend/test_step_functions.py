"""Tests for Step Functions integration module."""

import asyncio
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from step_functions_integration import (
    StateMachineExecution,
    StepExecution,
    StepStatus,
    ExecutionMode,
    STATE_MACHINES,
    TASK_RESOURCE_MAP,
    list_state_machines,
    get_state_machine_definition,
    get_execution_plan,
    start_execution,
    get_execution,
    list_executions,
    cancel_execution,
    _run_ansible_task_sync,
)


class TestStepExecution:
    def test_initial_state(self):
        step = StepExecution("test_step", "test_resource", timeout=60)
        assert step.name == "test_step"
        assert step.resource == "test_resource"
        assert step.status == StepStatus.PENDING
        assert step.timeout == 60
        assert step.started_at is None
        assert step.completed_at is None

    def test_to_dict(self):
        step = StepExecution("test_step", "test_resource")
        d = step.to_dict()
        assert d["name"] == "test_step"
        assert d["resource"] == "test_resource"
        assert d["status"] == "pending"
        assert d["elapsed_seconds"] is None

    def test_to_dict_with_times(self):
        step = StepExecution("test_step", "test_resource")
        step.started_at = "2026-04-27T10:00:00"
        step.completed_at = "2026-04-27T10:01:30"
        step.status = StepStatus.SUCCEEDED
        d = step.to_dict()
        assert d["elapsed_seconds"] == 90
        assert d["status"] == "succeeded"


class TestStateMachineExecution:
    def test_provision_execution_builds_steps(self):
        exec_ = StateMachineExecution("test-1", "rosa-hcp-provision", {})
        assert "PreFlight" in exec_.steps
        assert "CreateROSANetwork" in exec_.steps
        assert "CreateRosaRoleConfig" in exec_.steps
        assert "VerifyOIDC" in exec_.steps
        assert "CreateControlPlane" in exec_.steps
        assert "WaitForClusterReady" in exec_.steps
        assert len(exec_.parallel_groups) > 0

    def test_delete_execution_builds_steps(self):
        exec_ = StateMachineExecution("test-2", "rosa-hcp-delete", {})
        assert "DeleteControlPlane" in exec_.steps
        assert "WaitForControlPlaneDeleted" in exec_.steps
        assert "DeleteROSANetwork" in exec_.steps
        assert "DeleteRosaRoleConfig" in exec_.steps
        assert "VerifyCleanup" in exec_.steps

    def test_cancel(self):
        exec_ = StateMachineExecution("test-3", "rosa-hcp-provision", {})
        exec_.status = StepStatus.RUNNING
        exec_.cancel()
        assert exec_.status == StepStatus.CANCELLED
        assert exec_.completed_at is not None
        for step in exec_.steps.values():
            assert step.status == StepStatus.CANCELLED

    def test_to_dict(self):
        exec_ = StateMachineExecution("test-4", "rosa-hcp-provision", {"cluster_name": "test"})
        d = exec_.to_dict()
        assert d["execution_id"] == "test-4"
        assert d["state_machine"] == "rosa-hcp-provision"
        assert d["status"] == "pending"
        assert d["input"]["cluster_name"] == "test"
        assert "steps" in d
        assert "parallel_groups" in d

    def test_unknown_state_machine(self):
        exec_ = StateMachineExecution("test-5", "nonexistent", {})
        assert len(exec_.steps) == 0


class TestStateMachineDefinitions:
    def test_provision_state_machine_exists(self):
        assert "rosa-hcp-provision" in STATE_MACHINES

    def test_delete_state_machine_exists(self):
        assert "rosa-hcp-delete" in STATE_MACHINES

    def test_provision_has_parallel_state(self):
        sm = STATE_MACHINES["rosa-hcp-provision"]
        parallel_found = False
        for state_def in sm["States"].values():
            if state_def.get("Type") == "Parallel":
                parallel_found = True
                assert len(state_def["Branches"]) == 3
        assert parallel_found

    def test_delete_has_parallel_cleanup(self):
        sm = STATE_MACHINES["rosa-hcp-delete"]
        parallel_found = False
        for state_def in sm["States"].values():
            if state_def.get("Type") == "Parallel":
                parallel_found = True
                assert len(state_def["Branches"]) == 2
        assert parallel_found

    def test_all_task_resources_mapped(self):
        for sm in STATE_MACHINES.values():
            for state_def in sm["States"].values():
                if state_def.get("Type") == "Task":
                    resource = state_def.get("Resource", "")
                    assert resource in TASK_RESOURCE_MAP, f"Resource '{resource}' not in TASK_RESOURCE_MAP"
                elif state_def.get("Type") == "Parallel":
                    for branch in state_def.get("Branches", []):
                        for bstate_def in branch.get("States", {}).values():
                            if bstate_def.get("Type") == "Task":
                                resource = bstate_def.get("Resource", "")
                                assert resource in TASK_RESOURCE_MAP, f"Resource '{resource}' not in TASK_RESOURCE_MAP"

    def test_retry_configs_valid(self):
        for sm in STATE_MACHINES.values():
            for state_def in sm["States"].values():
                for retry in state_def.get("Retry", []):
                    assert "ErrorEquals" in retry
                    assert "MaxAttempts" in retry
                    assert retry["MaxAttempts"] >= 1


class TestListStateMachines:
    def test_returns_both(self):
        machines = list_state_machines()
        names = [m["name"] for m in machines]
        assert "rosa-hcp-provision" in names
        assert "rosa-hcp-delete" in names

    def test_has_comment_and_states(self):
        machines = list_state_machines()
        for m in machines:
            assert "comment" in m
            assert "states" in m
            assert len(m["states"]) > 0


class TestGetStateMachineDefinition:
    def test_existing(self):
        defn = get_state_machine_definition("rosa-hcp-provision")
        assert defn is not None
        assert "States" in defn

    def test_missing(self):
        defn = get_state_machine_definition("nonexistent")
        assert defn is None


class TestGetExecutionPlan:
    def test_provision_plan(self):
        plan = get_execution_plan("rosa-hcp-provision", {"cluster_name": "test"})
        assert plan["state_machine"] == "rosa-hcp-provision"
        assert len(plan["steps"]) > 0
        assert plan["estimated_time_parallel_seconds"] < plan["estimated_time_sequential_seconds"]

    def test_parallel_steps_marked(self):
        plan = get_execution_plan("rosa-hcp-provision", {})
        parallel_steps = [s for s in plan["steps"] if s.get("parallel")]
        assert len(parallel_steps) == 3

    def test_unknown_machine(self):
        plan = get_execution_plan("nonexistent", {})
        assert "error" in plan

    def test_plan_has_task_files(self):
        plan = get_execution_plan("rosa-hcp-provision", {})
        for step in plan["steps"]:
            assert "task_file" in step
            assert step["task_file"] != "unknown"


class TestExecutionMode:
    def test_default_is_local(self):
        with patch.dict(os.environ, {}, clear=True):
            from step_functions_integration import get_execution_mode
            assert get_execution_mode() == ExecutionMode.LOCAL

    def test_aws_mode(self):
        with patch.dict(os.environ, {"STEP_FUNCTIONS_MODE": "aws"}):
            from step_functions_integration import get_execution_mode
            assert get_execution_mode() == ExecutionMode.AWS


class TestRunAnsibleTaskSync:
    def test_missing_task_file(self):
        result = _run_ansible_task_sync("/nonexistent", "nonexistent.yml", {}, 30)
        assert not result["success"]
        assert "not found" in result["error"]

    @patch("subprocess.run")
    @patch("playbook_executor.build_playbook_command")
    def test_successful_run(self, mock_build, mock_run):
        mock_build.return_value = (["ansible-playbook", "test.yml"], os.environ.copy())
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        with patch("os.path.exists", return_value=True):
            result = _run_ansible_task_sync("/tmp", "playbooks/test.yml", {"cluster_name": "t"}, 30)
        assert result["success"]

    @patch("subprocess.run")
    @patch("playbook_executor.build_playbook_command")
    def test_timeout(self, mock_build, mock_run):
        import subprocess
        mock_build.return_value = (["ansible-playbook", "test.yml"], os.environ.copy())
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=30)
        with patch("os.path.exists", return_value=True):
            result = _run_ansible_task_sync("/tmp", "playbooks/test.yml", {}, 30)
        assert not result["success"]
        assert "timed out" in result["error"].lower() or "timeout" in result["error"].lower()


@pytest.mark.asyncio
class TestAsyncExecution:
    async def test_start_and_get_execution(self):
        with patch("step_functions_integration._run_local_execution", new=MagicMock(return_value=asyncio.sleep(0))):
            exec_ = await start_execution("rosa-hcp-provision", {"cluster_name": "test"}, ExecutionMode.LOCAL)
            assert exec_.execution_id.startswith("sf-")
            assert exec_.state_machine_name == "rosa-hcp-provision"

            fetched = await get_execution(exec_.execution_id)
            assert fetched is not None
            assert fetched.execution_id == exec_.execution_id

    async def test_list_executions(self):
        execs = await list_executions()
        assert isinstance(execs, list)

    async def test_cancel_nonexistent(self):
        result = await cancel_execution("nonexistent-id")
        assert result is False

    async def test_start_unknown_machine(self):
        with pytest.raises(ValueError, match="Unknown state machine"):
            await start_execution("nonexistent", {})


class TestStepFunctionsRoutes:
    """Test the FastAPI routes (requires test client)."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from step_functions_routes import router
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_list_state_machines(self, client):
        resp = client.get("/api/stepfunctions/state-machines")
        assert resp.status_code == 200
        data = resp.json()
        assert "state_machines" in data
        assert len(data["state_machines"]) >= 2

    def test_get_state_machine(self, client):
        resp = client.get("/api/stepfunctions/state-machines/rosa-hcp-provision")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "rosa-hcp-provision"
        assert "definition" in data

    def test_get_missing_state_machine(self, client):
        resp = client.get("/api/stepfunctions/state-machines/nonexistent")
        assert resp.status_code == 404

    def test_plan(self, client):
        resp = client.post("/api/stepfunctions/plan", json={
            "state_machine": "rosa-hcp-provision",
            "input_params": {"cluster_name": "test"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["state_machine"] == "rosa-hcp-provision"
        assert len(data["steps"]) > 0

    def test_plan_unknown_machine(self, client):
        resp = client.post("/api/stepfunctions/plan", json={
            "state_machine": "nonexistent",
            "input_params": {},
        })
        assert resp.status_code == 400

    def test_execute(self, client):
        with patch("step_functions_integration._run_local_execution", new=MagicMock(return_value=asyncio.sleep(0))):
            resp = client.post("/api/stepfunctions/execute", json={
                "state_machine": "rosa-hcp-provision",
                "input_params": {"cluster_name": "test"},
            })
            assert resp.status_code == 200
            data = resp.json()
            assert "execution_id" in data

    def test_execute_unknown_machine(self, client):
        resp = client.post("/api/stepfunctions/execute", json={
            "state_machine": "nonexistent",
            "input_params": {},
        })
        assert resp.status_code == 400

    def test_list_executions(self, client):
        resp = client.get("/api/stepfunctions/executions")
        assert resp.status_code == 200
        data = resp.json()
        assert "executions" in data

    def test_get_missing_execution(self, client):
        resp = client.get("/api/stepfunctions/executions/nonexistent")
        assert resp.status_code == 404

    def test_cancel_missing_execution(self, client):
        resp = client.post("/api/stepfunctions/executions/nonexistent/cancel")
        assert resp.status_code == 404
