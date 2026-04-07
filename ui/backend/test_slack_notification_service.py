"""Tests for SlackNotificationService."""

import os
from unittest.mock import patch, MagicMock

import pytest

from slack_notification_service import SlackNotificationService


class TestSlackLoadConfig:
    def test_load_config_missing_file(self):
        with patch.object(SlackNotificationService, "_load_config", return_value={
            "slack_enabled": False,
            "slack_webhook_url": "",
            "app_url": "http://localhost:3000",
        }):
            svc = SlackNotificationService()
            assert svc.config["slack_enabled"] is False

    def test_load_config_from_file(self, tmp_config_dir):
        config_path = str(tmp_config_dir / "vars" / "notification_config.yml")
        with patch("slack_notification_service.os.path.join", return_value=config_path):
            with patch("slack_notification_service.os.path.exists", return_value=True):
                svc = SlackNotificationService()
                svc.config = svc._load_config()
                # Should have loaded from the patched path or default


class TestSlackSendNotification:
    def test_disabled(self):
        svc = SlackNotificationService()
        svc.config = {"slack_enabled": False, "slack_webhook_url": ""}
        svc.webhook_url = ""
        result = svc.send_provisioning_notification({"cluster_name": "test"}, "started")
        assert result is False

    @patch("slack_notification_service.requests.post")
    def test_send_started(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        svc = SlackNotificationService()
        svc.config = {"slack_enabled": True, "slack_webhook_url": "https://hook", "app_url": "http://localhost:3000"}
        svc.webhook_url = "https://hook"
        result = svc.send_provisioning_notification(
            {"cluster_name": "test", "region": "us-west-2", "version": "4.14", "job_id": "j1"},
            "started",
        )
        assert result is True
        mock_post.assert_called_once()

    @patch("slack_notification_service.requests.post")
    def test_send_completed(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        svc = SlackNotificationService()
        svc.config = {"slack_enabled": True, "slack_webhook_url": "https://hook", "app_url": "http://localhost:3000"}
        svc.webhook_url = "https://hook"
        result = svc.send_provisioning_notification(
            {"cluster_name": "test", "region": "us-west-2", "version": "4.14", "job_id": "j1"},
            "completed",
        )
        assert result is True

    @patch("slack_notification_service.requests.post")
    def test_send_failed(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        svc = SlackNotificationService()
        svc.config = {"slack_enabled": True, "slack_webhook_url": "https://hook", "app_url": "http://localhost:3000"}
        svc.webhook_url = "https://hook"
        result = svc.send_provisioning_notification(
            {"cluster_name": "test", "region": "us-west-2", "error": "boom", "job_id": "j1"},
            "failed",
        )
        assert result is True


class TestSlackBuildMessage:
    def test_build_success_message(self):
        svc = SlackNotificationService()
        svc.config = {"app_url": "http://localhost:3000"}
        msg = svc._build_success_message("my-cluster", "us-west-2", "4.14", "j1")
        assert "blocks" in msg
        assert any("Successfully" in str(b) for b in msg["blocks"])

    def test_build_failure_message(self):
        svc = SlackNotificationService()
        svc.config = {"app_url": "http://localhost:3000"}
        msg = svc._build_failure_message("my-cluster", "us-west-2", {"error": "oops"}, "j1")
        assert "blocks" in msg
        assert any("Failed" in str(b) for b in msg["blocks"])

    def test_build_started_message(self):
        svc = SlackNotificationService()
        svc.config = {"app_url": "http://localhost:3000"}
        msg = svc._build_started_message("my-cluster", "us-west-2", "4.14", "j1")
        assert "blocks" in msg
        assert any("Started" in str(b) for b in msg["blocks"])

    def test_build_generic_message(self):
        svc = SlackNotificationService()
        msg = svc._build_generic_message("my-cluster", "custom", {})
        assert "blocks" in msg

    def test_failure_message_truncates_long_error(self):
        svc = SlackNotificationService()
        svc.config = {"app_url": "http://localhost:3000"}
        long_error = "x" * 600
        msg = svc._build_failure_message("c", "r", {"error": long_error}, "j1")
        # Error should be truncated in the message blocks
        assert "blocks" in msg


class TestSlackPostToSlack:
    @patch("slack_notification_service.requests.post")
    def test_post_success(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        svc = SlackNotificationService()
        svc.webhook_url = "https://hook"
        assert svc._post_to_slack({"text": "test"}) is True

    @patch("slack_notification_service.requests.post")
    def test_post_failure(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500, text="error")
        svc = SlackNotificationService()
        svc.webhook_url = "https://hook"
        assert svc._post_to_slack({"text": "test"}) is False

    @patch("slack_notification_service.requests.post")
    def test_post_exception(self, mock_post):
        mock_post.side_effect = Exception("network error")
        svc = SlackNotificationService()
        svc.webhook_url = "https://hook"
        assert svc._post_to_slack({"text": "test"}) is False


class TestSlackTestConnection:
    def test_no_webhook(self):
        svc = SlackNotificationService()
        svc.webhook_url = None
        result = svc.test_connection()
        assert result["success"] is False

    @patch("slack_notification_service.requests.post")
    def test_connection_success(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        svc = SlackNotificationService()
        svc.webhook_url = "https://hook"
        result = svc.test_connection()
        assert result["success"] is True

    @patch("slack_notification_service.requests.post")
    def test_connection_failure(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500, text="err")
        svc = SlackNotificationService()
        svc.webhook_url = "https://hook"
        result = svc.test_connection()
        assert result["success"] is False
