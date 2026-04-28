"""Tests for Workflow Orchestrator module."""

import asyncio
import os
import sqlite3
import subprocess
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from workflow_orchestrator import (
    StateMachineExecution,
    StepExecution,
    StepStatus,
    ExecutionMode,
    ExecutionStore,
    _execution_store,
    STATE_MACHINES,
    TASK_RESOURCE_MAP,
    list_state_machines,
    get_state_machine_definition,
    get_execution_plan,
    start_execution,
    get_execution,
    get_execution_dict,
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
        assert "InitiateDeletion" in exec_.steps
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
            from workflow_orchestrator import get_execution_mode
            assert get_execution_mode() == ExecutionMode.LOCAL

    def test_aws_mode(self):
        with patch.dict(os.environ, {"ORCHESTRATOR_MODE": "aws"}):
            from workflow_orchestrator import get_execution_mode
            assert get_execution_mode() == ExecutionMode.AWS


class TestExecutionStore:
    def test_persist_and_load(self, tmp_path):
        db_path = str(tmp_path / "test_executions.db")
        store = ExecutionStore(db_path=db_path)
        exec_ = StateMachineExecution("test-persist-1", "rosa-hcp-provision", {"cluster_name": "test"})
        exec_.status = StepStatus.SUCCEEDED
        exec_.completed_at = "2026-04-28T12:00:00"
        store.register(exec_)
        store.persist(exec_)

        store2 = ExecutionStore(db_path=db_path)
        data = store2.get_dict("test-persist-1")
        assert data is not None
        assert data["execution_id"] == "test-persist-1"
        assert data["status"] == "succeeded"

    def test_list_all_combines_live_and_history(self, tmp_path):
        db_path = str(tmp_path / "test_executions.db")
        store = ExecutionStore(db_path=db_path)
        exec1 = StateMachineExecution("test-live", "rosa-hcp-provision", {})
        store.register(exec1)
        exec2 = StateMachineExecution("test-done", "rosa-hcp-delete", {})
        exec2.status = StepStatus.SUCCEEDED
        store.persist(exec2)
        results = store.list_all(limit=10)
        ids = [r["execution_id"] for r in results]
        assert "test-live" in ids
        assert "test-done" in ids

    def test_history_survives_restart(self, tmp_path):
        db_path = str(tmp_path / "test_executions.db")
        store = ExecutionStore(db_path=db_path)
        exec_ = StateMachineExecution("test-restart", "mce-configure", {"key": "val"})
        exec_.status = StepStatus.FAILED
        exec_.error = "something broke"
        store.persist(exec_)
        del store

        store2 = ExecutionStore(db_path=db_path)
        data = store2.get_dict("test-restart")
        assert data is not None
        assert data["status"] == "failed"
        assert data["error"] == "something broke"

    def test_get_returns_none_for_unknown(self, tmp_path):
        db_path = str(tmp_path / "test_executions.db")
        store = ExecutionStore(db_path=db_path)
        assert store.get("nonexistent") is None
        assert store.get_dict("nonexistent") is None

    def test_eviction_caps_at_max(self, tmp_path):
        db_path = str(tmp_path / "test_executions.db")
        store = ExecutionStore(db_path=db_path)
        for i in range(210):
            exec_ = StateMachineExecution(f"test-evict-{i}", "rosa-hcp-provision", {})
            exec_.status = StepStatus.SUCCEEDED
            exec_.created_at = f"2026-01-01T{i:05d}"
            store.persist(exec_)
        with sqlite3.connect(db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM executions").fetchone()[0]
        assert count <= 200


class TestFromDict:
    def test_roundtrip(self):
        exec_ = StateMachineExecution("test-rt", "rosa-hcp-provision", {"cluster_name": "test"})
        exec_.status = StepStatus.FAILED
        exec_.error = "step failed"
        exec_.started_at = "2026-04-28T10:00:00"
        exec_.completed_at = "2026-04-28T10:30:00"
        for step in exec_.steps.values():
            step.status = StepStatus.SUCCEEDED
            step.started_at = "2026-04-28T10:00:00"
            step.completed_at = "2026-04-28T10:01:00"
        data = exec_.to_dict()
        rebuilt = StateMachineExecution.from_dict(data)
        assert rebuilt.execution_id == "test-rt"
        assert rebuilt.state_machine_name == "rosa-hcp-provision"
        assert rebuilt.status == StepStatus.FAILED
        assert rebuilt.input_params == {"cluster_name": "test"}
        assert len(rebuilt.steps) == len(exec_.steps)
        for step in rebuilt.steps.values():
            assert step.status == StepStatus.SUCCEEDED

    def test_from_dict_preserves_step_status(self):
        exec_ = StateMachineExecution("test-ps", "mce-configure", {})
        steps_list = list(exec_.steps.values())
        steps_list[0].status = StepStatus.SUCCEEDED
        steps_list[1].status = StepStatus.SUCCEEDED
        steps_list[2].status = StepStatus.FAILED
        steps_list[2].error = "boom"
        data = exec_.to_dict()
        rebuilt = StateMachineExecution.from_dict(data)
        rebuilt_steps = list(rebuilt.steps.values())
        assert rebuilt_steps[0].status == StepStatus.SUCCEEDED
        assert rebuilt_steps[1].status == StepStatus.SUCCEEDED
        assert rebuilt_steps[2].status == StepStatus.FAILED
        assert rebuilt_steps[2].error == "boom"


class TestResumeExecution:
    @pytest.mark.asyncio
    async def test_resume_resets_failed_steps(self, tmp_path):
        import workflow_orchestrator as wo
        orig_store = wo._execution_store
        wo._execution_store = ExecutionStore(db_path=str(tmp_path / "resume.db"))
        try:
            exec_ = StateMachineExecution("test-resume", "mce-configure", {})
            steps = list(exec_.steps.values())
            steps[0].status = StepStatus.SUCCEEDED
            steps[0].started_at = "2026-04-28T10:00:00"
            steps[0].completed_at = "2026-04-28T10:01:00"
            steps[1].status = StepStatus.FAILED
            steps[1].error = "some error"
            exec_.status = StepStatus.FAILED
            exec_.error = "step failed"
            wo._execution_store.register(exec_)
            wo._execution_store.persist(exec_)

            with patch("workflow_orchestrator._run_local_execution", new=MagicMock(return_value=asyncio.sleep(0))):
                resumed = await wo.resume_execution("test-resume")
            assert resumed is not None
            assert resumed.status == StepStatus.RUNNING
            assert resumed.error is None
            resumed_steps = list(resumed.steps.values())
            assert resumed_steps[0].status == StepStatus.SUCCEEDED
            assert resumed_steps[1].status == StepStatus.PENDING
            assert resumed_steps[1].error is None
        finally:
            wo._execution_store = orig_store

    @pytest.mark.asyncio
    async def test_resume_nonexistent_returns_none(self):
        from workflow_orchestrator import resume_execution
        result = await resume_execution("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_resume_running_returns_none(self, tmp_path):
        import workflow_orchestrator as wo
        orig_store = wo._execution_store
        wo._execution_store = ExecutionStore(db_path=str(tmp_path / "resume_running.db"))
        try:
            exec_ = StateMachineExecution("test-running", "rosa-hcp-provision", {})
            exec_.status = StepStatus.RUNNING
            wo._execution_store.register(exec_)
            wo._execution_store.persist(exec_)
            result = await wo.resume_execution("test-running")
            assert result is None
        finally:
            wo._execution_store = orig_store


class TestRunAnsibleTaskSync:
    def test_missing_task_file(self):
        result = _run_ansible_task_sync("/nonexistent", "nonexistent.yml", {}, 30)
        assert not result["success"]
        assert "not found" in result["error"]

    @patch("subprocess.Popen")
    @patch("playbook_executor.build_playbook_command")
    def test_successful_run(self, mock_build, mock_popen):
        mock_build.return_value = (["ansible-playbook", "test.yml"], os.environ.copy())
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["ok: [localhost]\n", "PLAY RECAP\n"])
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc
        with patch("os.path.exists", return_value=True):
            result = _run_ansible_task_sync("/tmp", "playbooks/test.yml", {"cluster_name": "t"}, 30)
        assert result["success"]

    @patch("subprocess.Popen")
    @patch("playbook_executor.build_playbook_command")
    def test_timeout(self, mock_build, mock_popen):
        mock_build.return_value = (["ansible-playbook", "test.yml"], os.environ.copy())
        mock_proc = MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.wait.side_effect = [subprocess.TimeoutExpired(cmd="test", timeout=30), 0]
        mock_proc.kill = MagicMock()
        mock_popen.return_value = mock_proc
        with patch("os.path.exists", return_value=True):
            result = _run_ansible_task_sync("/tmp", "playbooks/test.yml", {}, 30)
        assert not result["success"]
        assert "timed out" in result["error"].lower() or "timeout" in result["error"].lower()


@pytest.mark.asyncio
class TestAsyncExecution:
    async def test_start_and_get_execution(self):
        with patch("workflow_orchestrator._run_local_execution", new=MagicMock(return_value=asyncio.sleep(0))):
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


class TestOrchestratorRoutes:
    """Test the FastAPI routes (requires test client)."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from workflow_orchestrator_routes import router
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_list_state_machines(self, client):
        resp = client.get("/api/orchestrator/state-machines")
        assert resp.status_code == 200
        data = resp.json()
        assert "state_machines" in data
        assert len(data["state_machines"]) >= 2

    def test_get_state_machine(self, client):
        resp = client.get("/api/orchestrator/state-machines/rosa-hcp-provision")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "rosa-hcp-provision"
        assert "definition" in data

    def test_get_missing_state_machine(self, client):
        resp = client.get("/api/orchestrator/state-machines/nonexistent")
        assert resp.status_code == 404

    def test_plan(self, client):
        resp = client.post("/api/orchestrator/plan", json={
            "state_machine": "rosa-hcp-provision",
            "input_params": {"cluster_name": "test"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["state_machine"] == "rosa-hcp-provision"
        assert len(data["steps"]) > 0

    def test_plan_unknown_machine(self, client):
        resp = client.post("/api/orchestrator/plan", json={
            "state_machine": "nonexistent",
            "input_params": {},
        })
        assert resp.status_code == 400

    def test_execute(self, client):
        with patch("workflow_orchestrator._run_local_execution", new=MagicMock(return_value=asyncio.sleep(0))):
            resp = client.post("/api/orchestrator/execute", json={
                "state_machine": "rosa-hcp-provision",
                "input_params": {"cluster_name": "test"},
            })
            assert resp.status_code == 200
            data = resp.json()
            assert "execution_id" in data

    def test_execute_unknown_machine(self, client):
        resp = client.post("/api/orchestrator/execute", json={
            "state_machine": "nonexistent",
            "input_params": {},
        })
        assert resp.status_code == 400

    def test_list_executions(self, client):
        resp = client.get("/api/orchestrator/executions")
        assert resp.status_code == 200
        data = resp.json()
        assert "executions" in data

    def test_get_missing_execution(self, client):
        resp = client.get("/api/orchestrator/executions/nonexistent")
        assert resp.status_code == 404

    def test_cancel_missing_execution(self, client):
        resp = client.post("/api/orchestrator/executions/nonexistent/cancel")
        assert resp.status_code == 404
