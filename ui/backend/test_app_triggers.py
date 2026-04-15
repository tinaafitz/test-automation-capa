"""
Tests for trigger management API endpoints and scheduler.
"""

import asyncio
import hashlib
import hmac
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient

# Mock modules before app import
sys.modules.setdefault("anthropic", MagicMock())
sys.modules.setdefault("app_extensions", MagicMock())

from app import (
    app, _load_trigger_state, _save_trigger_state, TRIGGER_STATE_FILE,
    _trigger_last_fire, _trigger_scheduler, TriggerScheduler,
    _active_trigger_runs, _send_trigger_notification, _fire_trigger_workflow,
    _update_trigger_after_run, jobs,
)


@pytest.fixture(autouse=True)
def clean_trigger_state(tmp_path):
    """Use a temp file for trigger state and clear rate limits."""
    state_file = str(tmp_path / "trigger_state.json")
    _trigger_last_fire.clear()
    _active_trigger_runs.clear()
    with patch("app.TRIGGER_STATE_FILE", state_file):
        yield state_file


@pytest.fixture
def client(clean_trigger_state):
    """FastAPI test client."""
    with patch("app.TRIGGER_STATE_FILE", clean_trigger_state):
        return TestClient(app)


@pytest.fixture
def sample_trigger(client, clean_trigger_state):
    """Create and return a sample schedule trigger."""
    with patch("app.TRIGGER_STATE_FILE", clean_trigger_state):
        resp = client.post("/api/triggers", json={
            "workflow_name": "test-wf",
            "type": "schedule",
            "trigger_name": "nightly",
            "cron": "0 2 * * *",
        })
        return resp.json()["trigger"]


@pytest.fixture
def webhook_trigger(client, clean_trigger_state):
    """Create and return a sample webhook trigger."""
    with patch("app.TRIGGER_STATE_FILE", clean_trigger_state):
        resp = client.post("/api/triggers", json={
            "workflow_name": "test-wf",
            "type": "webhook",
            "trigger_name": "ci-hook",
        })
        return resp.json()["trigger"]


class TestTriggerCRUD:
    """Tests for trigger CRUD endpoints."""

    def test_list_empty(self, client):
        resp = client.get("/api/triggers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["triggers"] == []
        assert data["count"] == 0

    def test_create_schedule_trigger(self, client):
        resp = client.post("/api/triggers", json={
            "workflow_name": "full-e2e",
            "type": "schedule",
            "cron": "0 2 * * *",
            "timezone": "UTC",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        trigger = data["trigger"]
        assert trigger["trigger_id"].startswith("trg-")
        assert trigger["workflow_name"] == "full-e2e"
        assert trigger["type"] == "schedule"
        assert trigger["cron"] == "0 2 * * *"
        assert trigger["enabled"] is True

    def test_create_webhook_trigger(self, client):
        resp = client.post("/api/triggers", json={
            "workflow_name": "full-e2e",
            "type": "webhook",
            "trigger_name": "github-push",
        })
        assert resp.status_code == 200
        trigger = resp.json()["trigger"]
        assert trigger["type"] == "webhook"
        assert trigger["trigger_name"] == "github-push"

    def test_create_webhook_with_secret(self, client):
        with patch.dict(os.environ, {"MY_SECRET": "test-secret-value"}):
            resp = client.post("/api/triggers", json={
                "workflow_name": "full-e2e",
                "type": "webhook",
                "secret_env": "MY_SECRET",
            })
        trigger = resp.json()["trigger"]
        assert trigger["secret_env"] == "MY_SECRET"
        expected_hash = hashlib.sha256(b"test-secret-value").hexdigest()
        assert trigger["webhook_secret_hash"] == expected_hash

    def test_create_invalid_type(self, client):
        resp = client.post("/api/triggers", json={
            "workflow_name": "test",
            "type": "invalid",
        })
        assert resp.status_code == 400

    def test_create_schedule_missing_cron(self, client):
        resp = client.post("/api/triggers", json={
            "workflow_name": "test",
            "type": "schedule",
        })
        assert resp.status_code == 400

    def test_create_schedule_invalid_cron(self, client):
        resp = client.post("/api/triggers", json={
            "workflow_name": "test",
            "type": "schedule",
            "cron": "bad cron",
        })
        assert resp.status_code == 400

    def test_get_trigger(self, client, sample_trigger):
        tid = sample_trigger["trigger_id"]
        resp = client.get(f"/api/triggers/{tid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["trigger"]["trigger_id"] == tid
        assert "history" in data

    def test_get_trigger_not_found(self, client):
        resp = client.get("/api/triggers/trg-nonexistent")
        assert resp.status_code == 404

    def test_delete_trigger(self, client, sample_trigger):
        tid = sample_trigger["trigger_id"]
        resp = client.delete(f"/api/triggers/{tid}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == tid

        # Verify gone
        resp2 = client.get(f"/api/triggers/{tid}")
        assert resp2.status_code == 404

    def test_delete_not_found(self, client):
        resp = client.delete("/api/triggers/trg-nonexistent")
        assert resp.status_code == 404

    def test_list_after_create(self, client, sample_trigger):
        resp = client.get("/api/triggers")
        assert resp.json()["count"] == 1
        assert resp.json()["triggers"][0]["trigger_id"] == sample_trigger["trigger_id"]


class TestTriggerEnableDisable:
    """Tests for enable/disable endpoints."""

    def test_enable(self, client, sample_trigger):
        tid = sample_trigger["trigger_id"]
        # Disable first
        client.post(f"/api/triggers/{tid}/disable")
        resp = client.get(f"/api/triggers/{tid}")
        assert resp.json()["trigger"]["enabled"] is False

        # Enable
        resp = client.post(f"/api/triggers/{tid}/enable")
        assert resp.status_code == 200
        assert resp.json()["trigger"]["enabled"] is True

    def test_disable(self, client, sample_trigger):
        tid = sample_trigger["trigger_id"]
        resp = client.post(f"/api/triggers/{tid}/disable")
        assert resp.status_code == 200
        assert resp.json()["trigger"]["enabled"] is False

    def test_enable_not_found(self, client):
        resp = client.post("/api/triggers/trg-nonexistent/enable")
        assert resp.status_code == 404

    def test_disable_not_found(self, client):
        resp = client.post("/api/triggers/trg-nonexistent/disable")
        assert resp.status_code == 404

    def test_enable_resets_consecutive_failures(self, client, clean_trigger_state):
        # Create a trigger with failures
        with patch("app.TRIGGER_STATE_FILE", clean_trigger_state):
            resp = client.post("/api/triggers", json={
                "workflow_name": "test",
                "type": "schedule",
                "cron": "0 2 * * *",
            })
            tid = resp.json()["trigger"]["trigger_id"]

            # Manually set consecutive_failures
            state = _load_trigger_state()
            state["triggers"][0]["consecutive_failures"] = 4
            _save_trigger_state(state)

            # Enable should reset
            resp = client.post(f"/api/triggers/{tid}/enable")
            assert resp.json()["trigger"]["consecutive_failures"] == 0


class TestTriggerHistory:
    """Tests for trigger history endpoints."""

    def test_trigger_history_empty(self, client, sample_trigger):
        tid = sample_trigger["trigger_id"]
        resp = client.get(f"/api/triggers/{tid}/history")
        assert resp.status_code == 200
        assert resp.json()["history"] == []

    def test_all_history_empty(self, client):
        resp = client.get("/api/triggers/history/all")
        assert resp.status_code == 200
        assert resp.json()["history"] == []

    def test_trigger_history_not_found(self, client):
        resp = client.get("/api/triggers/trg-nonexistent/history")
        assert resp.status_code == 404


class TestWorkflowTriggers:
    """Tests for workflow-specific trigger endpoints."""

    def test_get_workflow_triggers(self, client, sample_trigger):
        resp = client.get(f"/api/workflows/{sample_trigger['workflow_name']}/triggers")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1
        assert resp.json()["triggers"][0]["trigger_id"] == sample_trigger["trigger_id"]

    def test_get_workflow_triggers_empty(self, client):
        resp = client.get("/api/workflows/nonexistent/triggers")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


class TestWebhookEndpoint:
    """Tests for the webhook trigger endpoint."""

    def test_webhook_not_found(self, client):
        resp = client.post("/api/webhooks/trigger/trg-nonexistent", content=b"{}")
        assert resp.status_code == 404

    def test_webhook_disabled_returns_404(self, client, webhook_trigger):
        tid = webhook_trigger["trigger_id"]
        client.post(f"/api/triggers/{tid}/disable")
        resp = client.post(f"/api/webhooks/trigger/{tid}", content=b"{}")
        assert resp.status_code == 404

    def test_webhook_schedule_type_returns_404(self, client, sample_trigger):
        """Schedule triggers should not be fireable via webhook endpoint."""
        tid = sample_trigger["trigger_id"]
        resp = client.post(f"/api/webhooks/trigger/{tid}", content=b"{}")
        assert resp.status_code == 404

    def test_webhook_fires_workflow(self, client, webhook_trigger):
        tid = webhook_trigger["trigger_id"]
        resp = client.post(f"/api/webhooks/trigger/{tid}", content=b'{"ref": "main"}')
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["workflow"] == "test-wf"

    def test_webhook_rate_limited(self, client, webhook_trigger):
        tid = webhook_trigger["trigger_id"]
        # First request succeeds
        resp1 = client.post(f"/api/webhooks/trigger/{tid}", content=b"{}")
        assert resp1.status_code == 200

        # Second request within 60s is rate limited
        resp2 = client.post(f"/api/webhooks/trigger/{tid}", content=b"{}")
        assert resp2.status_code == 429

    def test_webhook_invalid_signature(self, client, clean_trigger_state):
        """Webhook with secret configured should reject invalid signatures."""
        with patch.dict(os.environ, {"TEST_SECRET": "my-secret"}):
            with patch("app.TRIGGER_STATE_FILE", clean_trigger_state):
                resp = client.post("/api/triggers", json={
                    "workflow_name": "test-wf",
                    "type": "webhook",
                    "secret_env": "TEST_SECRET",
                })
                tid = resp.json()["trigger"]["trigger_id"]

                # Send with wrong signature
                resp = client.post(
                    f"/api/webhooks/trigger/{tid}",
                    content=b'{"test": true}',
                    headers={"X-Hub-Signature-256": "sha256=wrong"},
                )
                assert resp.status_code == 403

    def test_webhook_valid_signature(self, client, clean_trigger_state):
        """Webhook with correct HMAC signature should succeed."""
        secret = "my-secret"
        with patch.dict(os.environ, {"TEST_SECRET": secret}):
            with patch("app.TRIGGER_STATE_FILE", clean_trigger_state):
                resp = client.post("/api/triggers", json={
                    "workflow_name": "test-wf",
                    "type": "webhook",
                    "secret_env": "TEST_SECRET",
                })
                tid = resp.json()["trigger"]["trigger_id"]

                body = b'{"test": true}'
                sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
                resp = client.post(
                    f"/api/webhooks/trigger/{tid}",
                    content=body,
                    headers={"X-Hub-Signature-256": sig},
                )
                assert resp.status_code == 200


class TestFireTrigger:
    """Tests for the manual fire endpoint."""

    def test_fire_trigger(self, client, sample_trigger):
        tid = sample_trigger["trigger_id"]
        resp = client.post(f"/api/triggers/{tid}/fire")
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["workflow"] == "test-wf"

    def test_fire_not_found(self, client):
        resp = client.post("/api/triggers/trg-nonexistent/fire")
        assert resp.status_code == 404

    def test_fire_rate_limited(self, client, sample_trigger):
        tid = sample_trigger["trigger_id"]
        resp1 = client.post(f"/api/triggers/{tid}/fire")
        assert resp1.status_code == 200
        resp2 = client.post(f"/api/triggers/{tid}/fire")
        assert resp2.status_code == 429


class TestSchedulerStatus:
    """Tests for the scheduler status endpoint."""

    def test_scheduler_status(self, client):
        resp = client.get("/api/triggers/scheduler/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "running" in data
        assert "croniter_available" in data
        assert "active_schedule_triggers" in data
        assert "upcoming" in data

    def test_scheduler_status_with_trigger(self, client, sample_trigger):
        resp = client.get("/api/triggers/scheduler/status")
        data = resp.json()
        assert data["active_schedule_triggers"] == 1
        assert len(data["upcoming"]) == 1
        assert data["upcoming"][0]["trigger_id"] == sample_trigger["trigger_id"]
        assert data["upcoming"][0]["cron"] == "0 2 * * *"


class TestCreateTriggerNextRun:
    """Tests for next_run_at computation on create and enable."""

    def test_create_schedule_sets_next_run(self, client):
        resp = client.post("/api/triggers", json={
            "workflow_name": "test-wf",
            "type": "schedule",
            "cron": "0 2 * * *",
        })
        trigger = resp.json()["trigger"]
        assert trigger["next_run_at"] is not None

    def test_enable_recomputes_next_run(self, client, sample_trigger):
        tid = sample_trigger["trigger_id"]
        client.post(f"/api/triggers/{tid}/disable")
        resp = client.post(f"/api/triggers/{tid}/enable")
        trigger = resp.json()["trigger"]
        assert trigger.get("next_run_at") is not None


class TestTriggerSchedulerUnit:
    """Unit tests for the TriggerScheduler class."""

    def test_scheduler_init(self):
        scheduler = TriggerScheduler()
        assert scheduler._running is False
        assert scheduler._task is None
        assert scheduler._check_interval == 30

    @pytest.mark.asyncio
    async def test_scheduler_start_stop(self):
        scheduler = TriggerScheduler()
        # Patch the loop to not actually run
        with patch.object(scheduler, "_loop", new_callable=AsyncMock):
            await scheduler.start()
            assert scheduler._running is True
            assert scheduler._task is not None
            await scheduler.stop()
            assert scheduler._running is False

    @pytest.mark.asyncio
    async def test_tick_fires_matching_trigger(self, tmp_path):
        """Scheduler tick should fire a trigger whose cron matches the current minute."""
        from croniter import croniter

        scheduler = TriggerScheduler()
        now_utc = datetime.now(timezone.utc)
        # Build a cron that matches the current UTC minute
        current_cron = f"{now_utc.minute} {now_utc.hour} * * *"

        state_file = str(tmp_path / "trigger_state.json")
        trigger_data = {
            "triggers": [{
                "trigger_id": "trg-test123",
                "workflow_name": "test-wf",
                "type": "schedule",
                "trigger_name": "test-sched",
                "enabled": True,
                "cron": current_cron,
                "timezone": "UTC",
                "consecutive_failures": 0,
                "vars_override": {},
            }],
            "run_history": [],
        }
        with open(state_file, "w") as f:
            json.dump(trigger_data, f)

        with patch("app.TRIGGER_STATE_FILE", state_file):
            with patch.object(scheduler, "_fire", new_callable=AsyncMock) as mock_fire:
                await scheduler._tick(croniter)
                mock_fire.assert_called_once()
                fired_trigger = mock_fire.call_args[0][0]
                assert fired_trigger["trigger_id"] == "trg-test123"

    @pytest.mark.asyncio
    async def test_tick_skips_disabled_trigger(self, tmp_path):
        """Scheduler should skip disabled triggers."""
        from croniter import croniter

        scheduler = TriggerScheduler()
        now = datetime.now()
        current_cron = f"{now.minute} {now.hour} * * *"

        state_file = str(tmp_path / "trigger_state.json")
        trigger_data = {
            "triggers": [{
                "trigger_id": "trg-disabled",
                "workflow_name": "test-wf",
                "type": "schedule",
                "trigger_name": "disabled-sched",
                "enabled": False,
                "cron": current_cron,
                "timezone": "UTC",
            }],
            "run_history": [],
        }
        with open(state_file, "w") as f:
            json.dump(trigger_data, f)

        with patch("app.TRIGGER_STATE_FILE", state_file):
            with patch.object(scheduler, "_fire", new_callable=AsyncMock) as mock_fire:
                await scheduler._tick(croniter)
                mock_fire.assert_not_called()

    @pytest.mark.asyncio
    async def test_tick_skips_webhook_trigger(self, tmp_path):
        """Scheduler should skip webhook triggers."""
        from croniter import croniter

        scheduler = TriggerScheduler()
        state_file = str(tmp_path / "trigger_state.json")
        trigger_data = {
            "triggers": [{
                "trigger_id": "trg-webhook",
                "workflow_name": "test-wf",
                "type": "webhook",
                "trigger_name": "hook",
                "enabled": True,
            }],
            "run_history": [],
        }
        with open(state_file, "w") as f:
            json.dump(trigger_data, f)

        with patch("app.TRIGGER_STATE_FILE", state_file):
            with patch.object(scheduler, "_fire", new_callable=AsyncMock) as mock_fire:
                await scheduler._tick(croniter)
                mock_fire.assert_not_called()

    @pytest.mark.asyncio
    async def test_tick_no_double_fire(self, tmp_path):
        """Scheduler should not fire the same trigger twice in the same minute."""
        from croniter import croniter

        scheduler = TriggerScheduler()
        now_utc = datetime.now(timezone.utc)
        current_cron = f"{now_utc.minute} {now_utc.hour} * * *"

        state_file = str(tmp_path / "trigger_state.json")
        trigger_data = {
            "triggers": [{
                "trigger_id": "trg-once",
                "workflow_name": "test-wf",
                "type": "schedule",
                "trigger_name": "once",
                "enabled": True,
                "cron": current_cron,
                "timezone": "UTC",
            }],
            "run_history": [],
        }
        with open(state_file, "w") as f:
            json.dump(trigger_data, f)

        with patch("app.TRIGGER_STATE_FILE", state_file):
            with patch.object(scheduler, "_fire", new_callable=AsyncMock) as mock_fire:
                await scheduler._tick(croniter)
                await scheduler._tick(croniter)  # second tick same minute
                assert mock_fire.call_count == 1

    def test_delete_clears_scheduler_cache(self, client, sample_trigger):
        """Deleting a trigger should clear the scheduler's _last_check."""
        tid = sample_trigger["trigger_id"]
        _trigger_scheduler._last_check[tid] = "2026-04-14 02:00"
        client.delete(f"/api/triggers/{tid}")
        assert tid not in _trigger_scheduler._last_check


class TestConcurrentRunPrevention:
    """Tests for concurrent trigger run prevention."""

    @pytest.mark.asyncio
    async def test_concurrent_run_skipped(self):
        """A trigger already running should return skipped status."""
        trigger = {
            "trigger_id": "trg-concurrent",
            "workflow_name": "test-wf",
            "type": "schedule",
            "workflow_source": "yaml",
        }
        # Simulate an active run
        _active_trigger_runs["trg-concurrent"] = "trun-existing"
        try:
            success, record = await _fire_trigger_workflow(trigger)
            assert success is False
            assert record["status"] == "skipped"
            assert "Already running" in record.get("error", "")
        finally:
            _active_trigger_runs.pop("trg-concurrent", None)

    @pytest.mark.asyncio
    async def test_active_run_cleared_after_completion(self):
        """Active run should be cleaned up even if workflow not found."""
        trigger = {
            "trigger_id": "trg-cleanup",
            "workflow_name": "nonexistent-workflow",
            "type": "schedule",
            "workflow_source": "yaml",
        }
        assert "trg-cleanup" not in _active_trigger_runs
        with patch("app._send_trigger_notification"):
            success, record = await _fire_trigger_workflow(trigger)
        assert success is False
        assert record["status"] == "failed"
        assert "trg-cleanup" not in _active_trigger_runs

    def test_scheduler_status_shows_active_runs(self, client):
        """Scheduler status should include active_runs."""
        resp = client.get("/api/triggers/scheduler/status")
        data = resp.json()
        assert "active_runs" in data


class TestCronValidation:
    """Tests for improved cron validation using croniter."""

    def test_valid_cron_accepted(self, client):
        resp = client.post("/api/triggers", json={
            "workflow_name": "test-wf",
            "type": "schedule",
            "cron": "*/5 * * * *",
        })
        assert resp.status_code == 200

    def test_invalid_cron_rejected(self, client):
        resp = client.post("/api/triggers", json={
            "workflow_name": "test-wf",
            "type": "schedule",
            "cron": "invalid cron expression here",
        })
        assert resp.status_code == 400

    def test_cron_with_ranges(self, client):
        resp = client.post("/api/triggers", json={
            "workflow_name": "test-wf",
            "type": "schedule",
            "cron": "0 9 * * 1-5",
        })
        assert resp.status_code == 200
        trigger = resp.json()["trigger"]
        assert trigger["cron"] == "0 9 * * 1-5"


class TestTriggerNotifications:
    """Tests for trigger notification integration."""

    def test_notification_called_on_failure(self):
        """Notification should be sent when notify_trigger_failure is True."""
        trigger = {"trigger_id": "trg-n1", "trigger_name": "test", "workflow_name": "wf"}
        run_record = {"run_id": "r1", "steps_completed": 1, "steps_total": 3}
        config = {
            "slack_enabled": True,
            "notify_trigger_failure": True,
        }
        with patch("builtins.open", MagicMock()):
            with patch("os.path.exists", return_value=True):
                with patch("yaml.safe_load", return_value=config):
                    with patch("app.slack_service") as mock_slack:
                        _send_trigger_notification(trigger, run_record, False)
                        mock_slack.reload_config.assert_called_once()
                        mock_slack.send_provisioning_notification.assert_called_once()

    def test_notification_skipped_on_success_by_default(self):
        """By default, success notifications are not sent."""
        trigger = {"trigger_id": "trg-n2", "trigger_name": "test", "workflow_name": "wf"}
        run_record = {"run_id": "r2", "steps_completed": 3, "steps_total": 3}
        config = {
            "slack_enabled": True,
            "notify_trigger_success": False,  # default
            "notify_trigger_failure": True,
        }
        with patch("builtins.open", MagicMock()):
            with patch("os.path.exists", return_value=True):
                with patch("yaml.safe_load", return_value=config):
                    with patch("app.slack_service") as mock_slack:
                        _send_trigger_notification(trigger, run_record, True)
                        mock_slack.send_provisioning_notification.assert_not_called()

    def test_notification_sent_on_success_when_enabled(self):
        """Success notification sent when notify_trigger_success is True."""
        trigger = {"trigger_id": "trg-n3", "trigger_name": "test", "workflow_name": "wf"}
        run_record = {"run_id": "r3", "steps_completed": 3, "steps_total": 3}
        config = {
            "slack_enabled": True,
            "notify_trigger_success": True,
        }
        with patch("builtins.open", MagicMock()):
            with patch("os.path.exists", return_value=True):
                with patch("yaml.safe_load", return_value=config):
                    with patch("app.slack_service") as mock_slack:
                        _send_trigger_notification(trigger, run_record, True)
                        mock_slack.reload_config.assert_called_once()
                        mock_slack.send_provisioning_notification.assert_called_once()

    def test_notification_no_config_file(self):
        """No crash when notification config doesn't exist."""
        trigger = {"trigger_id": "trg-n4", "trigger_name": "test", "workflow_name": "wf"}
        run_record = {"run_id": "r4", "steps_completed": 0, "steps_total": 1}
        with patch("os.path.exists", return_value=False):
            # Should not raise
            _send_trigger_notification(trigger, run_record, False)


class TestUpdateTriggerAfterRun:
    """Tests for the shared _update_trigger_after_run helper."""

    def test_updates_state_on_success(self, clean_trigger_state):
        with patch("app.TRIGGER_STATE_FILE", clean_trigger_state):
            state = {"triggers": [{
                "trigger_id": "trg-upd1", "type": "schedule", "cron": "0 2 * * *",
                "run_count": 0, "consecutive_failures": 2,
            }], "run_history": []}
            _save_trigger_state(state)
            run_record = {"run_id": "r1", "started_at": "2026-04-15T00:00:00", "status": "completed"}
            _update_trigger_after_run("trg-upd1", True, run_record)
            updated = _load_trigger_state()
            t = updated["triggers"][0]
            assert t["consecutive_failures"] == 0
            assert t["run_count"] == 1
            assert t["last_run_status"] == "completed"
            assert t.get("next_run_at") is not None

    def test_increments_failures_and_auto_disables(self, clean_trigger_state):
        with patch("app.TRIGGER_STATE_FILE", clean_trigger_state):
            state = {"triggers": [{
                "trigger_id": "trg-upd2", "type": "webhook",
                "run_count": 4, "consecutive_failures": 4, "enabled": True,
            }], "run_history": []}
            _save_trigger_state(state)
            run_record = {"run_id": "r2", "started_at": "2026-04-15T00:00:00", "status": "failed"}
            _update_trigger_after_run("trg-upd2", False, run_record)
            updated = _load_trigger_state()
            t = updated["triggers"][0]
            assert t["consecutive_failures"] == 5
            assert t["enabled"] is False
            assert len(updated["run_history"]) == 1


class TestJobInitialization:
    """Tests that _fire_trigger_workflow properly initializes jobs before running playbooks."""

    @pytest.mark.asyncio
    async def test_job_initialized_before_playbook_run(self, clean_trigger_state):
        """The job entry must exist in jobs dict before _run_playbook_in_thread is called."""
        trigger = {
            "trigger_id": "trg-jobinit",
            "workflow_name": "test-wf",
            "type": "schedule",
        }
        captured_job_ids = []

        def mock_run_playbook(playbook, extra_vars, job_id, description):
            # Verify job was initialized
            assert job_id in jobs, f"jobs[{job_id}] not initialized before _run_playbook_in_thread"
            assert jobs[job_id]["status"] == "running" or jobs[job_id]["status"] == "pending"
            captured_job_ids.append(job_id)
            jobs[job_id]["status"] = "completed"

        # Create a saved workflow so it can be found
        mock_workflows = [{"name": "test-wf", "steps": [
            {"playbook": "playbooks/test.yml", "name": "Test Step", "on_failure": "stop"},
        ], "vars": {}}]

        with patch("app.TRIGGER_STATE_FILE", clean_trigger_state):
            with patch("app._load_workflows", return_value=mock_workflows):
                with patch("app._run_playbook_in_thread", side_effect=mock_run_playbook):
                    with patch("app._send_trigger_notification"):
                        success, record = await _fire_trigger_workflow(trigger)
                        assert success is True
                        assert record["status"] == "completed"
                        assert record["steps_completed"] == 1
                        assert len(captured_job_ids) == 1

    @pytest.mark.asyncio
    async def test_job_uses_asyncio_to_thread(self, clean_trigger_state):
        """_fire_trigger_workflow should use asyncio.to_thread to avoid blocking."""
        trigger = {
            "trigger_id": "trg-async",
            "workflow_name": "test-wf",
            "type": "schedule",
        }
        mock_workflows = [{"name": "test-wf", "steps": [
            {"playbook": "playbooks/test.yml", "name": "Step 1"},
        ], "vars": {}}]

        with patch("app.TRIGGER_STATE_FILE", clean_trigger_state):
            with patch("app._load_workflows", return_value=mock_workflows):
                with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
                    with patch("app._send_trigger_notification"):
                        mock_to_thread.return_value = None
                        success, record = await _fire_trigger_workflow(trigger)
                        mock_to_thread.assert_called_once()
                        # First arg should be _run_playbook_in_thread
                        from app import _run_playbook_in_thread
                        assert mock_to_thread.call_args[0][0] is _run_playbook_in_thread


class TestInputValidation:
    """Tests for workflow_name and trigger_name input validation."""

    def test_empty_workflow_name_rejected(self, client):
        resp = client.post("/api/triggers", json={
            "workflow_name": "",
            "type": "schedule",
            "cron": "0 2 * * *",
        })
        assert resp.status_code == 400

    def test_long_workflow_name_rejected(self, client):
        resp = client.post("/api/triggers", json={
            "workflow_name": "a" * 129,
            "type": "schedule",
            "cron": "0 2 * * *",
        })
        assert resp.status_code == 400

    def test_invalid_chars_in_workflow_name(self, client):
        resp = client.post("/api/triggers", json={
            "workflow_name": "my workflow; rm -rf /",
            "type": "schedule",
            "cron": "0 2 * * *",
        })
        assert resp.status_code == 400

    def test_valid_workflow_name_accepted(self, client):
        resp = client.post("/api/triggers", json={
            "workflow_name": "full-e2e.v2_test",
            "type": "schedule",
            "cron": "0 2 * * *",
        })
        assert resp.status_code == 200

    def test_invalid_trigger_name_rejected(self, client):
        resp = client.post("/api/triggers", json={
            "workflow_name": "test-wf",
            "type": "schedule",
            "cron": "0 2 * * *",
            "trigger_name": "bad name with spaces",
        })
        assert resp.status_code == 400


class TestWorkflowSourceDetection:
    """Tests for correct workflow_source detection."""

    @pytest.mark.asyncio
    async def test_finds_saved_workflow(self, clean_trigger_state):
        """Should find saved workflow and set wf_type to 'saved'."""
        trigger = {
            "trigger_id": "trg-saved",
            "workflow_name": "my-saved-wf",
            "type": "schedule",
        }
        mock_workflows = [{"name": "my-saved-wf", "steps": [], "vars": {}}]

        with patch("app.TRIGGER_STATE_FILE", clean_trigger_state):
            with patch("app._load_workflows", return_value=mock_workflows):
                with patch("app._send_trigger_notification"):
                    success, record = await _fire_trigger_workflow(trigger)
                    assert record["status"] == "completed"
                    assert record["steps_completed"] == 0
                    assert record["steps_total"] == 0


class TestSchedulerPruning:
    """Tests that scheduler prunes stale _last_check entries."""

    @pytest.mark.asyncio
    async def test_prunes_stale_last_check(self, tmp_path):
        """Scheduler tick should remove _last_check entries for deleted triggers."""
        from croniter import croniter

        scheduler = TriggerScheduler()
        scheduler._last_check["trg-deleted"] = "2026-04-14 02:00"
        scheduler._last_check["trg-exists"] = "2026-04-14 02:00"

        state_file = str(tmp_path / "trigger_state.json")
        trigger_data = {
            "triggers": [{"trigger_id": "trg-exists", "type": "webhook", "enabled": True}],
            "run_history": [],
        }
        with open(state_file, "w") as f:
            json.dump(trigger_data, f)

        with patch("app.TRIGGER_STATE_FILE", state_file):
            await scheduler._tick(croniter)

        assert "trg-deleted" not in scheduler._last_check
        assert "trg-exists" in scheduler._last_check
