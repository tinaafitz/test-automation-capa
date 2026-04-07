"""Tests for EmailNotificationService."""

from unittest.mock import patch, MagicMock

import pytest

from email_notification_service import EmailNotificationService


class TestEmailLoadConfig:
    def test_default_config(self):
        svc = EmailNotificationService()
        defaults = svc._default_config()
        assert defaults["email_enabled"] is False
        assert defaults["smtp_port"] == 587

    def test_reload_config(self):
        svc = EmailNotificationService()
        svc.config = {"smtp_server": "new.server.com", "smtp_port": 465,
                      "smtp_username": "", "smtp_password": "",
                      "from_email": "", "to_emails": [], "use_tls": False}
        svc.reload_config()
        # After reload, should re-read from file (which won't exist, so defaults)


class TestEmailSendNotification:
    def test_disabled(self):
        svc = EmailNotificationService()
        svc.config = {"email_enabled": False, "smtp_server": ""}
        result = svc.send_provisioning_notification({"cluster_name": "test"}, "started")
        assert result is False

    def test_no_recipients(self):
        svc = EmailNotificationService()
        svc.config = {"email_enabled": True, "smtp_server": "smtp.test.com"}
        svc.smtp_server = "smtp.test.com"
        svc.to_emails = []
        result = svc.send_provisioning_notification({"cluster_name": "test"}, "started")
        assert result is False

    @patch("email_notification_service.smtplib.SMTP")
    def test_send_started(self, mock_smtp):
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        svc = EmailNotificationService()
        svc.config = {"email_enabled": True}
        svc.smtp_server = "smtp.test.com"
        svc.smtp_port = 587
        svc.smtp_username = "user"
        svc.smtp_password = "pass"
        svc.from_email = "from@test.com"
        svc.to_emails = ["to@test.com"]
        svc.use_tls = True
        result = svc.send_provisioning_notification(
            {"cluster_name": "test", "region": "us-west-2", "version": "4.14", "job_id": "j1"},
            "started",
        )
        assert result is True
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once()
        mock_server.sendmail.assert_called_once()

    @patch("email_notification_service.smtplib.SMTP")
    def test_send_completed(self, mock_smtp):
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        svc = EmailNotificationService()
        svc.config = {"email_enabled": True}
        svc.smtp_server = "smtp.test.com"
        svc.smtp_port = 587
        svc.smtp_username = ""
        svc.smtp_password = ""
        svc.from_email = "from@test.com"
        svc.to_emails = ["to@test.com"]
        svc.use_tls = False
        result = svc.send_provisioning_notification(
            {"cluster_name": "test", "region": "us-west-2", "version": "4.14", "job_id": "j1"},
            "completed",
        )
        assert result is True

    @patch("email_notification_service.smtplib.SMTP")
    def test_send_failed(self, mock_smtp):
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        svc = EmailNotificationService()
        svc.config = {"email_enabled": True}
        svc.smtp_server = "smtp.test.com"
        svc.smtp_port = 587
        svc.smtp_username = ""
        svc.smtp_password = ""
        svc.from_email = "from@test.com"
        svc.to_emails = ["to@test.com"]
        svc.use_tls = True
        result = svc.send_provisioning_notification(
            {"cluster_name": "test", "region": "us-west-2", "error": "boom", "job_id": "j1"},
            "failed",
        )
        assert result is True


class TestEmailBuildContent:
    def test_build_success_email(self):
        svc = EmailNotificationService()
        subject, html, text = svc._build_success_email("my-cluster", "us-west-2", "4.14", "j1")
        assert "my-cluster" in subject
        assert "my-cluster" in html
        assert "my-cluster" in text

    def test_build_failure_email(self):
        svc = EmailNotificationService()
        subject, html, text = svc._build_failure_email("c", "r", {"error": "oops"}, "j1")
        assert "Failed" in subject
        assert "oops" in html

    def test_build_failure_email_truncates_long_error(self):
        svc = EmailNotificationService()
        long_error = "x" * 600
        subject, html, text = svc._build_failure_email("c", "r", {"error": long_error}, "j1")
        assert "..." in html

    def test_build_failure_email_escapes_html(self):
        svc = EmailNotificationService()
        subject, html, text = svc._build_failure_email("c", "r", {"error": "<script>alert(1)</script>"}, "j1")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_build_started_email(self):
        svc = EmailNotificationService()
        subject, html, text = svc._build_started_email("c", "r", "4.14", "j1")
        assert "Started" in subject

    def test_build_generic_email(self):
        svc = EmailNotificationService()
        subject, html, text = svc._build_generic_email("c", "custom", {})
        assert "Update" in subject


class TestEmailSendEmail:
    @patch("email_notification_service.smtplib.SMTP")
    def test_smtp_error(self, mock_smtp):
        mock_smtp.side_effect = Exception("connection refused")
        svc = EmailNotificationService()
        svc.smtp_server = "smtp.test.com"
        svc.smtp_port = 587
        svc.from_email = "from@test.com"
        svc.to_emails = ["to@test.com"]
        svc.use_tls = True
        result = svc._send_email("Subject", "<html></html>", "text")
        assert result is False

    @patch("email_notification_service.smtplib.SMTP")
    def test_no_tls(self, mock_smtp):
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        svc = EmailNotificationService()
        svc.smtp_server = "smtp.test.com"
        svc.smtp_port = 25
        svc.smtp_username = ""
        svc.smtp_password = ""
        svc.from_email = "from@test.com"
        svc.to_emails = ["to@test.com"]
        svc.use_tls = False
        result = svc._send_email("Subject", "<html></html>", "text")
        assert result is True
        mock_server.starttls.assert_not_called()


class TestEmailTestConnection:
    def test_no_smtp_server(self):
        svc = EmailNotificationService()
        svc.smtp_server = ""
        result = svc.test_connection()
        assert result["success"] is False

    def test_no_recipients(self):
        svc = EmailNotificationService()
        svc.smtp_server = "smtp.test.com"
        svc.to_emails = []
        result = svc.test_connection()
        assert result["success"] is False

    @patch("email_notification_service.smtplib.SMTP")
    def test_connection_success(self, mock_smtp):
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        svc = EmailNotificationService()
        svc.smtp_server = "smtp.test.com"
        svc.smtp_port = 587
        svc.smtp_username = "user"
        svc.smtp_password = "pass"
        svc.from_email = "from@test.com"
        svc.to_emails = ["to@test.com"]
        svc.use_tls = True
        result = svc.test_connection()
        assert result["success"] is True

    @patch("email_notification_service.smtplib.SMTP")
    def test_connection_failure(self, mock_smtp):
        mock_smtp.side_effect = Exception("refused")
        svc = EmailNotificationService()
        svc.smtp_server = "smtp.test.com"
        svc.smtp_port = 587
        svc.from_email = "from@test.com"
        svc.to_emails = ["to@test.com"]
        svc.use_tls = True
        result = svc.test_connection()
        assert result["success"] is False
