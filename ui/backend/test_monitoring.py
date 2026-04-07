"""Tests for monitoring module (Sentry integration)."""

from unittest.mock import patch, MagicMock

import pytest


class TestInitSentry:
    @patch("monitoring.sentry_sdk")
    @patch.dict("os.environ", {"SENTRY_DSN": "https://test@sentry.io/123"})
    def test_init_with_dsn(self, mock_sentry):
        from monitoring import init_sentry
        result = init_sentry()
        assert result is True
        mock_sentry.init.assert_called_once()

    @patch("monitoring.sentry_sdk")
    @patch.dict("os.environ", {}, clear=True)
    def test_init_without_dsn(self, mock_sentry):
        # Remove SENTRY_DSN if present
        import os
        os.environ.pop("SENTRY_DSN", None)
        from monitoring import init_sentry
        result = init_sentry()
        assert result is False


class TestCaptureException:
    @patch("monitoring.sentry_sdk")
    def test_capture_without_context(self, mock_sentry):
        from monitoring import capture_exception
        error = Exception("test error")
        capture_exception(error)
        mock_sentry.capture_exception.assert_called_once_with(error)

    @patch("monitoring.sentry_sdk")
    def test_capture_with_context(self, mock_sentry):
        from monitoring import capture_exception
        error = Exception("test error")
        mock_scope = MagicMock()
        mock_sentry.configure_scope.return_value.__enter__ = MagicMock(return_value=mock_scope)
        mock_sentry.configure_scope.return_value.__exit__ = MagicMock(return_value=False)
        capture_exception(error, context={"cluster": {"name": "test"}})
        mock_sentry.capture_exception.assert_called_once_with(error)


class TestCaptureMessage:
    @patch("monitoring.sentry_sdk")
    def test_capture_message_without_context(self, mock_sentry):
        from monitoring import capture_message
        capture_message("test message", level="warning")
        mock_sentry.capture_message.assert_called_once_with("test message", level="warning")

    @patch("monitoring.sentry_sdk")
    def test_capture_message_with_context(self, mock_sentry):
        from monitoring import capture_message
        mock_scope = MagicMock()
        mock_sentry.configure_scope.return_value.__enter__ = MagicMock(return_value=mock_scope)
        mock_sentry.configure_scope.return_value.__exit__ = MagicMock(return_value=False)
        capture_message("test", context={"info": {"key": "val"}})
        mock_sentry.capture_message.assert_called_once()


class TestSetUser:
    @patch("monitoring.sentry_sdk")
    def test_set_user(self, mock_sentry):
        from monitoring import set_user
        set_user("user1", email="test@example.com", username="tester")
        mock_sentry.set_user.assert_called_once_with({
            "id": "user1",
            "email": "test@example.com",
            "username": "tester",
        })


class TestAddBreadcrumb:
    @patch("monitoring.sentry_sdk")
    def test_add_breadcrumb(self, mock_sentry):
        from monitoring import add_breadcrumb
        add_breadcrumb("clicked button", category="ui", level="info")
        mock_sentry.add_breadcrumb.assert_called_once_with(
            message="clicked button", category="ui", level="info", data={}
        )

    @patch("monitoring.sentry_sdk")
    def test_add_breadcrumb_with_data(self, mock_sentry):
        from monitoring import add_breadcrumb
        add_breadcrumb("api call", category="api", data={"url": "/test"})
        mock_sentry.add_breadcrumb.assert_called_once_with(
            message="api call", category="api", level="info", data={"url": "/test"}
        )
