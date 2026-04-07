"""Tests for health check functions."""

import asyncio
from unittest.mock import patch, MagicMock

import pytest

from health import check_system_health, check_readiness, check_liveness, get_metrics


@pytest.fixture
def run_async():
    """Helper to run async functions in tests."""
    def _run(coro):
        return asyncio.get_event_loop().run_until_complete(coro)
    return _run


class TestCheckSystemHealth:
    @patch("health.subprocess.run")
    @patch("health.os.path.exists", return_value=True)
    def test_all_healthy(self, mock_exists, mock_run, run_async):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="rosa 1.2.3\nansible [core 2.15]"
        )
        result = run_async(check_system_health())
        assert result["status"] in ("healthy", "degraded")
        assert "checks" in result
        assert "timestamp" in result

    @patch("health.subprocess.run")
    @patch("health.os.path.exists", return_value=True)
    def test_rosa_missing(self, mock_exists, mock_run, run_async):
        def side_effect(cmd, **kwargs):
            if cmd[0] == "rosa":
                raise FileNotFoundError("rosa not found")
            return MagicMock(returncode=0, stdout="ansible [core 2.15]")

        mock_run.side_effect = side_effect
        result = run_async(check_system_health())
        assert result["checks"]["rosa_cli"]["status"] == "warning"

    @patch("health.subprocess.run")
    @patch("health.os.path.exists", return_value=True)
    def test_ansible_missing(self, mock_exists, mock_run, run_async):
        def side_effect(cmd, **kwargs):
            if cmd[0] == "ansible":
                raise FileNotFoundError("ansible not found")
            return MagicMock(returncode=0, stdout="rosa 1.2.3")

        mock_run.side_effect = side_effect
        result = run_async(check_system_health())
        assert result["checks"]["ansible"]["status"] == "unhealthy"
        assert result["status"] in ("degraded", "unhealthy")

    @patch("health.subprocess.run")
    @patch("health.os.path.exists", return_value=False)
    def test_config_missing(self, mock_exists, mock_run, run_async):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok")
        result = run_async(check_system_health())
        assert result["checks"]["config_file"]["status"] == "warning"

    @patch("health.subprocess.run")
    @patch("health.os.path.exists", return_value=True)
    def test_rosa_timeout(self, mock_exists, mock_run, run_async):
        import subprocess

        def side_effect(cmd, **kwargs):
            if cmd[0] == "rosa":
                raise subprocess.TimeoutExpired(cmd="rosa", timeout=5)
            return MagicMock(returncode=0, stdout="ansible [core 2.15]")

        mock_run.side_effect = side_effect
        result = run_async(check_system_health())
        assert result["checks"]["rosa_cli"]["status"] == "warning"


class TestCheckReadiness:
    @patch("health.subprocess.run")
    @patch("health.os.path.exists", return_value=True)
    def test_ready(self, mock_exists, mock_run, run_async):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok")
        result = run_async(check_readiness())
        assert result["ready"] is True

    @patch("health.subprocess.run")
    @patch("health.os.path.exists", return_value=True)
    def test_not_ready_ansible_missing(self, mock_exists, mock_run, run_async):
        mock_run.side_effect = FileNotFoundError("ansible")
        result = run_async(check_readiness())
        assert result["ready"] is False

    @patch("health.subprocess.run")
    @patch("health.os.path.exists", return_value=False)
    def test_not_ready_config_missing(self, mock_exists, mock_run, run_async):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok")
        result = run_async(check_readiness())
        assert result["ready"] is False


class TestCheckLiveness:
    def test_alive(self, run_async):
        result = run_async(check_liveness())
        assert result["alive"] is True
        assert "timestamp" in result


class TestGetMetrics:
    def test_metrics_success(self, run_async):
        mock_psutil = MagicMock()
        mock_process = MagicMock()
        mock_process.cpu_percent.return_value = 5.0
        mock_process.memory_info.return_value = MagicMock(rss=100 * 1024 * 1024)
        mock_process.num_threads.return_value = 4
        mock_process.open_files.return_value = []
        mock_psutil.Process.return_value = mock_process
        mock_psutil.cpu_percent.return_value = 10.0
        mock_psutil.virtual_memory.return_value = MagicMock(percent=50.0)
        mock_psutil.disk_usage.return_value = MagicMock(percent=30.0)

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            result = run_async(get_metrics())
        assert "process" in result
        assert "system" in result
        assert result["process"]["threads"] == 4

    def test_metrics_error(self, run_async):
        mock_psutil = MagicMock()
        mock_psutil.Process.side_effect = Exception("no psutil")
        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            result = run_async(get_metrics())
        assert "error" in result
