"""
Tests for jobs CRUD endpoints and utility functions (normalize_timestamp, etc.).
"""

import importlib
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module-level mocking
# ---------------------------------------------------------------------------

if "app_extensions" in sys.modules:
    if isinstance(sys.modules["app_extensions"], MagicMock):
        del sys.modules["app_extensions"]

sys.modules.setdefault(
    "app_extensions",
    MagicMock(
        register_health_endpoints=MagicMock(),
        register_monitoring_endpoints=MagicMock(),
    ),
)
sys.modules.setdefault("anthropic", MagicMock())

from fastapi.testclient import TestClient

with patch("subprocess.run", return_value=MagicMock(returncode=1, stdout="", stderr="")):
    with patch("subprocess.Popen"):
        if "app" in sys.modules:
            importlib.reload(sys.modules["app"])
        import app as app_module

client = TestClient(app_module.app)


# =============================================
# normalize_timestamp
# =============================================


class TestNormalizeTimestamp:
    def test_none_returns_min(self):
        result = app_module.normalize_timestamp(None)
        assert result == datetime.min

    def test_datetime_passthrough(self):
        dt = datetime(2026, 4, 7, 12, 0)
        result = app_module.normalize_timestamp(dt)
        assert result == dt

    def test_unix_timestamp_int(self):
        ts = 1712505600  # approx 2024-04-07
        result = app_module.normalize_timestamp(ts)
        assert isinstance(result, datetime)
        assert result.year >= 2024

    def test_unix_timestamp_float(self):
        ts = 1712505600.123
        result = app_module.normalize_timestamp(ts)
        assert isinstance(result, datetime)

    def test_iso_string(self):
        result = app_module.normalize_timestamp("2026-04-07T12:00:00")
        assert result.year == 2026
        assert result.month == 4

    def test_iso_string_with_z(self):
        result = app_module.normalize_timestamp("2026-04-07T12:00:00Z")
        assert result.year == 2026

    def test_empty_string(self):
        result = app_module.normalize_timestamp("")
        assert result == datetime.min

    def test_zero_string(self):
        result = app_module.normalize_timestamp("0")
        assert result == datetime.min

    def test_invalid_string(self):
        result = app_module.normalize_timestamp("not-a-date")
        assert result == datetime.min

    def test_invalid_type(self):
        result = app_module.normalize_timestamp([1, 2, 3])
        assert result == datetime.min


# =============================================
# Jobs CRUD
# =============================================


class TestJobsCRUD:
    def setup_method(self):
        app_module.jobs.clear()

    def teardown_method(self):
        app_module.jobs.clear()

    def test_list_jobs_empty(self):
        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 0
        assert data["jobs"] == []

    def test_list_jobs_with_entries(self):
        app_module.jobs["job-1"] = {
            "id": "job-1",
            "status": "completed",
            "message": "Done",
            "created_at": "2026-04-07T12:00:00",
        }
        app_module.jobs["job-2"] = {
            "id": "job-2",
            "status": "running",
            "message": "In progress",
            "created_at": "2026-04-07T13:00:00",
        }
        resp = client.get("/api/jobs")
        data = resp.json()
        assert data["count"] == 2
        # Newest first
        assert data["jobs"][0]["id"] == "job-2"

    def test_get_job_status(self):
        app_module.jobs["job-1"] = {
            "id": "job-1",
            "status": "running",
            "message": "Working",
        }
        resp = client.get("/api/jobs/job-1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_get_job_not_found(self):
        resp = client.get("/api/jobs/nonexistent")
        assert resp.status_code == 404

    def test_get_job_logs(self):
        app_module.jobs["job-1"] = {
            "id": "job-1",
            "status": "running",
            "logs": ["line 1", "line 2"],
        }
        resp = client.get("/api/jobs/job-1/logs")
        assert resp.status_code == 200
        assert resp.json()["logs"] == ["line 1", "line 2"]

    def test_get_job_logs_not_found(self):
        resp = client.get("/api/jobs/nonexistent/logs")
        assert resp.status_code == 404

    def test_cancel_running_job(self):
        app_module.jobs["job-1"] = {
            "id": "job-1",
            "status": "running",
            "message": "Working",
        }
        resp = client.post("/api/jobs/job-1/cancel")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert app_module.jobs["job-1"]["status"] == "failed"
        assert "cancelled" in app_module.jobs["job-1"]["message"].lower()

    def test_cancel_completed_job_fails(self):
        app_module.jobs["job-1"] = {
            "id": "job-1",
            "status": "completed",
            "message": "Done",
        }
        resp = client.post("/api/jobs/job-1/cancel")
        assert resp.status_code == 400

    def test_cancel_nonexistent_job(self):
        resp = client.post("/api/jobs/nonexistent/cancel")
        assert resp.status_code == 404

    def test_clear_all_jobs(self):
        app_module.jobs["job-1"] = {"id": "job-1", "status": "completed"}
        app_module.jobs["job-2"] = {"id": "job-2", "status": "running"}
        resp = client.delete("/api/jobs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(app_module.jobs) == 0


# =============================================
# check_and_timeout_stuck_jobs
# =============================================


class TestCheckAndTimeoutStuckJobs:
    def setup_method(self):
        app_module.jobs.clear()

    def teardown_method(self):
        app_module.jobs.clear()

    def test_no_jobs(self):
        app_module.check_and_timeout_stuck_jobs()
        assert len(app_module.jobs) == 0

    def test_recent_running_job_not_timed_out(self):
        app_module.jobs["job-1"] = {
            "id": "job-1",
            "status": "running",
            "created_at": datetime.now().isoformat(),
        }
        app_module.check_and_timeout_stuck_jobs()
        assert app_module.jobs["job-1"]["status"] == "running"

    def test_old_running_job_gets_timed_out(self):
        from datetime import timedelta
        old_time = (datetime.now() - timedelta(minutes=100)).isoformat()
        app_module.jobs["job-1"] = {
            "id": "job-1",
            "status": "running",
            "created_at": old_time,
        }
        app_module.check_and_timeout_stuck_jobs()
        assert app_module.jobs["job-1"]["status"] == "failed"
        assert "timed out" in app_module.jobs["job-1"]["message"].lower()

    def test_completed_job_not_affected(self):
        from datetime import timedelta
        old_time = (datetime.now() - timedelta(minutes=100)).isoformat()
        app_module.jobs["job-1"] = {
            "id": "job-1",
            "status": "completed",
            "created_at": old_time,
        }
        app_module.check_and_timeout_stuck_jobs()
        assert app_module.jobs["job-1"]["status"] == "completed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
