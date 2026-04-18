"""Tests for the shared playbook executor module."""

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

from playbook_executor import (
    SENSITIVE_KEYS,
    build_playbook_command,
    run_playbook_blocking,
    StreamingPlaybookRunner,
)


class TestSensitiveKeys:
    def test_contains_aws_keys(self):
        assert "aws_access_key_id" in SENSITIVE_KEYS
        assert "aws_secret_access_key" in SENSITIVE_KEYS

    def test_contains_ocm_keys(self):
        assert "ocm_client_id" in SENSITIVE_KEYS
        assert "ocm_client_secret" in SENSITIVE_KEYS

    def test_is_frozenset(self):
        assert isinstance(SENSITIVE_KEYS, frozenset)


class TestBuildPlaybookCommand:
    def test_basic_command(self):
        cmd, env = build_playbook_command("/path/to/playbook.yml")
        assert cmd == ["ansible-playbook", "/path/to/playbook.yml"]
        assert isinstance(env, dict)

    def test_verbosity_flags(self):
        cmd, _ = build_playbook_command("/pb.yml", verbosity=1)
        assert "-v" in cmd

        cmd, _ = build_playbook_command("/pb.yml", verbosity=3)
        assert "-vvv" in cmd

    def test_verbosity_capped_at_4(self):
        cmd, _ = build_playbook_command("/pb.yml", verbosity=10)
        assert "-vvvv" in cmd

    def test_no_verbosity_flag_at_zero(self):
        cmd, _ = build_playbook_command("/pb.yml", verbosity=0)
        assert len(cmd) == 2

    def test_string_extra_vars(self):
        cmd, _ = build_playbook_command("/pb.yml", extra_vars={"key": "value"})
        assert "-e" in cmd
        assert "key=value" in cmd

    def test_bool_extra_vars(self):
        cmd, _ = build_playbook_command("/pb.yml", extra_vars={"flag": True})
        assert "flag=true" in cmd

        cmd, _ = build_playbook_command("/pb.yml", extra_vars={"flag": False})
        assert "flag=false" in cmd

    def test_dict_extra_vars_as_json(self):
        tags = {"env": "test", "team": "qa"}
        cmd, _ = build_playbook_command("/pb.yml", extra_vars={"tags": tags})
        idx = cmd.index("-e")
        arg = cmd[idx + 1]
        assert arg.startswith("tags=")
        parsed = json.loads(arg.split("=", 1)[1])
        assert parsed == tags

    def test_list_extra_vars_as_json(self):
        zones = ["us-east-1a", "us-east-1b"]
        cmd, _ = build_playbook_command("/pb.yml", extra_vars={"zones": zones})
        idx = cmd.index("-e")
        arg = cmd[idx + 1]
        assert arg.startswith("zones=")
        parsed = json.loads(arg.split("=", 1)[1])
        assert parsed == zones

    def test_credentials_go_to_env_not_cmd(self):
        cmd, env = build_playbook_command("/pb.yml", extra_vars={
            "aws_access_key_id": "AKID123",
            "aws_secret_access_key": "secret456",
            "cluster_name": "my-cluster",
        })
        assert "AKID123" not in " ".join(cmd)
        assert "secret456" not in " ".join(cmd)
        assert env["AWS_ACCESS_KEY_ID"] == "AKID123"
        assert env["AWS_SECRET_ACCESS_KEY"] == "secret456"
        assert "cluster_name=my-cluster" in cmd

    def test_ocm_credentials_go_to_env(self):
        cmd, env = build_playbook_command("/pb.yml", extra_vars={
            "ocm_client_id": "ocm-id",
            "ocm_client_secret": "ocm-secret",
        })
        assert "ocm-id" not in " ".join(cmd)
        assert env["OCM_CLIENT_ID"] == "ocm-id"
        assert env["OCM_CLIENT_SECRET"] == "ocm-secret"

    def test_credential_key_case_insensitive(self):
        cmd, env = build_playbook_command("/pb.yml", extra_vars={
            "AWS_ACCESS_KEY_ID": "key123",
        })
        assert "key123" not in " ".join(cmd)
        assert env["AWS_ACCESS_KEY_ID"] == "key123"

    def test_none_value_becomes_empty_string(self):
        cmd, _ = build_playbook_command("/pb.yml", extra_vars={"key": None})
        assert "key=" in cmd

    def test_custom_env_preserved(self):
        custom_env = {"MY_VAR": "hello", "PATH": "/usr/bin"}
        cmd, env = build_playbook_command("/pb.yml", env=custom_env)
        assert env["MY_VAR"] == "hello"

    def test_no_extra_vars(self):
        cmd, _ = build_playbook_command("/pb.yml", extra_vars=None)
        assert cmd == ["ansible-playbook", "/pb.yml"]

    def test_empty_extra_vars(self):
        cmd, _ = build_playbook_command("/pb.yml", extra_vars={})
        assert cmd == ["ansible-playbook", "/pb.yml"]


class TestRunPlaybookBlocking:
    def test_playbook_not_found(self):
        result = run_playbook_blocking("/nonexistent/playbook.yml")
        assert result["success"] is False
        assert "not found" in result["error"]
        assert result["elapsed"] == 0

    @patch("playbook_executor.subprocess.run")
    @patch("playbook_executor.os.path.exists", return_value=True)
    def test_successful_run(self, mock_exists, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        result = run_playbook_blocking("/pb.yml")
        assert result["success"] is True
        assert result["returncode"] == 0
        assert result["elapsed"] > 0

    @patch("playbook_executor.subprocess.run")
    @patch("playbook_executor.os.path.exists", return_value=True)
    def test_failed_run(self, mock_exists, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="task failed")
        result = run_playbook_blocking("/pb.yml")
        assert result["success"] is False
        assert result["returncode"] == 1
        assert "task failed" in result["error"]

    @patch("playbook_executor.subprocess.run")
    @patch("playbook_executor.os.path.exists", return_value=True)
    def test_timeout(self, mock_exists, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=10)
        result = run_playbook_blocking("/pb.yml", timeout=10)
        assert result["success"] is False
        assert "Timeout" in result["error"]

    @patch("playbook_executor.subprocess.run")
    @patch("playbook_executor.os.path.exists", return_value=True)
    def test_passes_extra_vars(self, mock_exists, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        run_playbook_blocking("/pb.yml", extra_vars={"key": "val"})
        cmd = mock_run.call_args[0][0]
        assert "-e" in cmd
        assert "key=val" in cmd

    @patch("playbook_executor.subprocess.run")
    @patch("playbook_executor.os.path.exists", return_value=True)
    def test_passes_cwd(self, mock_exists, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        run_playbook_blocking("/pb.yml", cwd="/my/dir")
        assert mock_run.call_args[1]["cwd"] == "/my/dir"

    @patch("playbook_executor.subprocess.run")
    @patch("playbook_executor.os.path.exists", return_value=True)
    def test_credentials_not_in_command(self, mock_exists, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        run_playbook_blocking("/pb.yml", extra_vars={
            "aws_secret_access_key": "TOPSECRET",
            "cluster_name": "test",
        })
        cmd = mock_run.call_args[0][0]
        assert "TOPSECRET" not in " ".join(cmd)
        env = mock_run.call_args[1]["env"]
        assert env["AWS_SECRET_ACCESS_KEY"] == "TOPSECRET"


class TestStreamingPlaybookRunner:
    @patch("playbook_executor.os.path.exists", return_value=False)
    def test_playbook_not_found(self, mock_exists):
        runner = StreamingPlaybookRunner("/nonexistent.yml")
        result = runner.run()
        assert result["success"] is False
        assert "not found" in result["error"]

    @patch("playbook_executor.subprocess.Popen")
    @patch("playbook_executor.os.path.exists", return_value=True)
    def test_successful_streaming(self, mock_exists, mock_popen):
        process = MagicMock()
        process.stdout = iter(["line1\n", "line2\n"])
        process.wait.return_value = 0
        mock_popen.return_value = process

        lines_received = []
        runner = StreamingPlaybookRunner(
            "/pb.yml", on_line=lambda l: lines_received.append(l),
        )
        result = runner.run()

        assert result["success"] is True
        assert result["returncode"] == 0
        assert len(result["output_lines"]) == 2
        assert lines_received == ["line1", "line2"]

    @patch("playbook_executor.subprocess.Popen")
    @patch("playbook_executor.os.path.exists", return_value=True)
    def test_failed_streaming(self, mock_exists, mock_popen):
        process = MagicMock()
        process.stdout = iter(["error output\n"])
        process.wait.return_value = 1
        mock_popen.return_value = process

        runner = StreamingPlaybookRunner("/pb.yml")
        result = runner.run()

        assert result["success"] is False
        assert result["returncode"] == 1

    @patch("playbook_executor.subprocess.Popen")
    @patch("playbook_executor.os.path.exists", return_value=True)
    def test_timeout_kills_process(self, mock_exists, mock_popen):
        process = MagicMock()
        process.stdout = iter([])
        process.wait.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=1)
        mock_popen.return_value = process

        runner = StreamingPlaybookRunner("/pb.yml", timeout=1)
        result = runner.run()

        assert result["success"] is False
        assert "timed out" in result["error"].lower()
        process.kill.assert_called_once()

    @patch("playbook_executor.subprocess.Popen")
    @patch("playbook_executor.os.path.exists", return_value=True)
    def test_credentials_in_env_not_cmd(self, mock_exists, mock_popen):
        process = MagicMock()
        process.stdout = iter([])
        process.wait.return_value = 0
        mock_popen.return_value = process

        runner = StreamingPlaybookRunner(
            "/pb.yml",
            extra_vars={"aws_access_key_id": "KEY", "name": "test"},
        )
        runner.run()

        call_kwargs = mock_popen.call_args
        cmd = call_kwargs[0][0]
        env = call_kwargs[1]["env"]

        assert "KEY" not in " ".join(cmd)
        assert env["AWS_ACCESS_KEY_ID"] == "KEY"
        assert "name=test" in cmd

    @patch("playbook_executor.subprocess.Popen")
    @patch("playbook_executor.os.path.exists", return_value=True)
    def test_sidecar_thread_starts_and_stops(self, mock_exists, mock_popen):
        process = MagicMock()
        process.stdout = iter(["done\n"])
        process.wait.return_value = 0
        mock_popen.return_value = process

        sidecar_lines = []
        runner = StreamingPlaybookRunner(
            "/pb.yml",
            sidecar_logfile="/tmp/test-sidecar.log",
            on_sidecar_line=lambda l: sidecar_lines.append(l),
        )

        result = runner.run()
        assert result["success"] is True
        assert runner._sidecar_stop.is_set()

    @patch("playbook_executor.subprocess.Popen")
    @patch("playbook_executor.os.path.exists", return_value=True)
    def test_exception_during_run(self, mock_exists, mock_popen):
        mock_popen.side_effect = OSError("permission denied")

        runner = StreamingPlaybookRunner("/pb.yml")
        result = runner.run()

        assert result["success"] is False
        assert "permission denied" in result["error"]

    def test_extra_vars_passed_to_command(self):
        runner = StreamingPlaybookRunner(
            "/pb.yml", extra_vars={"key": "val", "flag": True},
        )
        assert "-e" in runner.cmd
        assert "key=val" in runner.cmd
        assert "flag=true" in runner.cmd
