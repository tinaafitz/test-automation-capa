"""
Notification routes module -- FastAPI router for notification-related endpoints.

Endpoints moved here from app.py:
  GET    /api/notification-settings
  POST   /api/notification-settings
  POST   /api/notification-settings/test

Also contains:
  NotificationSettings       -- Pydantic model for notification config
  send_cluster_notifications -- helper to dispatch Slack/Email notifications
"""

import os
import traceback
from typing import List, Optional

import yaml
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from slack_notification_service import SlackNotificationService
from email_notification_service import EmailNotificationService

router = APIRouter()

# ── Module-level service references ────────────────────────────────────
# Populated by _init_services() which app.py calls after creating the
# singleton SlackNotificationService / EmailNotificationService instances.

_slack_service: SlackNotificationService = None  # type: ignore[assignment]
_email_service: EmailNotificationService = None  # type: ignore[assignment]


def _init_services(slack: SlackNotificationService, email: EmailNotificationService):
    """Called once from app.py to inject the shared service singletons."""
    global _slack_service, _email_service
    _slack_service = slack
    _email_service = email


def _get_slack():
    """Return the slack service, falling back to the app module for test patches."""
    import sys
    app_mod = sys.modules.get("app")
    if app_mod is not None:
        return getattr(app_mod, "slack_service", _slack_service)
    return _slack_service


def _get_email():
    """Return the email service, falling back to the app module for test patches."""
    import sys
    app_mod = sys.modules.get("app")
    if app_mod is not None:
        return getattr(app_mod, "email_service", _email_service)
    return _email_service


# ── Pydantic model ─────────────────────────────────────────────────────

class NotificationSettings(BaseModel):
    # Slack settings
    slack_enabled: bool = False
    slack_webhook_url: Optional[str] = ""
    # Email settings
    email_enabled: bool = False
    smtp_server: Optional[str] = ""
    smtp_port: int = 587
    smtp_username: Optional[str] = ""
    smtp_password: Optional[str] = ""
    from_email: Optional[str] = ""
    to_emails: List[str] = []
    use_tls: bool = True
    # Common settings
    app_url: str = "http://localhost:3000"
    notify_on_start: bool = False
    notify_on_complete: bool = True
    notify_on_failure: bool = True
    # Provision notification preferences
    notify_provision_start: bool = False
    notify_provision_success: bool = True
    notify_provision_failure: bool = True
    # Delete notification preferences
    notify_delete_start: bool = False
    notify_delete_success: bool = True
    notify_delete_failure: bool = True


# ── Helper function ────────────────────────────────────────────────────

def send_cluster_notifications(cluster_name: str, region: str, version: str, job_id: str, status: str, error: str = None, operation_type: str = "provision"):
    """
    Send notifications for cluster operations (provision/delete)

    Args:
        cluster_name: Name of the cluster
        region: AWS region
        version: OpenShift version
        job_id: Job ID
        status: 'started', 'completed', or 'failed'
        error: Error message (for failed status)
        operation_type: 'provision' or 'delete'
    """
    try:
        # Load notification settings
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        config_path = os.path.join(project_root, "vars", "notification_config.yml")

        if not os.path.exists(config_path):
            print("Notification config not found, skipping notifications")
            return

        with open(config_path, "r") as f:
            settings = yaml.safe_load(f) or {}

        # Build job data for notifications
        job_data = {
            "cluster_name": cluster_name,
            "region": region,
            "version": version,
            "job_id": job_id,
        }

        if error:
            job_data["error"] = error

        # Check notification preferences based on operation type and status
        should_notify = False

        if operation_type == "provision":
            if status == "started" and settings.get("notify_provision_start", False):
                should_notify = True
            elif status == "completed" and settings.get("notify_provision_success", True):
                should_notify = True
            elif status == "failed" and settings.get("notify_provision_failure", True):
                should_notify = True
        elif operation_type == "delete":
            if status == "started" and settings.get("notify_delete_start", False):
                should_notify = True
            elif status == "completed" and settings.get("notify_delete_success", True):
                should_notify = True
            elif status == "failed" and settings.get("notify_delete_failure", True):
                should_notify = True

        if not should_notify:
            print(f"Notifications disabled for {operation_type} {status}")
            return

        slack_service = _get_slack()
        email_service = _get_email()

        # Send Slack notification
        if settings.get("slack_enabled", False):
            try:
                slack_service.reload_config()  # Reload config to get latest settings
                slack_service.send_provisioning_notification(job_data, status)
                print(f"Slack notification sent for {operation_type} {status}")
            except Exception as e:
                print(f"Failed to send Slack notification: {e}")

        # Send Email notification
        if settings.get("email_enabled", False):
            try:
                email_service.reload_config()  # Reload config to get latest settings
                email_service.send_provisioning_notification(job_data, status)
                print(f"Email notification sent for {operation_type} {status}")
            except Exception as e:
                print(f"Failed to send email notification: {e}")

    except Exception as e:
        print(f"Error in send_cluster_notifications: {e}")


# ── Route handlers ─────────────────────────────────────────────────────

@router.get("/api/notification-settings")
async def get_notification_settings():
    """
    Get current notification settings
    """
    try:
        slack_service = _get_slack()
        email_service = _get_email()

        # Reload config to get latest settings
        slack_service.reload_config()
        email_service.reload_config()
        config = slack_service.config  # Both services read from same file

        return {
            "success": True,
            "settings": {
                # Slack settings
                "slack_enabled": config.get("slack_enabled", False),
                "slack_webhook_url": config.get("slack_webhook_url", ""),
                # Email settings
                "email_enabled": config.get("email_enabled", False),
                "smtp_server": config.get("smtp_server", ""),
                "smtp_port": config.get("smtp_port", 587),
                "smtp_username": config.get("smtp_username", ""),
                "smtp_password": config.get("smtp_password", ""),
                "from_email": config.get("from_email", ""),
                "to_emails": config.get("to_emails", []),
                "use_tls": config.get("use_tls", True),
                # Common settings
                "app_url": config.get("app_url", "http://localhost:3000"),
                "notify_on_start": config.get("notify_on_start", False),
                "notify_on_complete": config.get("notify_on_complete", True),
                "notify_on_failure": config.get("notify_on_failure", True),
                # Provision notification preferences
                "notify_provision_start": config.get("notify_provision_start", False),
                "notify_provision_success": config.get("notify_provision_success", True),
                "notify_provision_failure": config.get("notify_provision_failure", True),
                # Delete notification preferences
                "notify_delete_start": config.get("notify_delete_start", False),
                "notify_delete_success": config.get("notify_delete_success", True),
                "notify_delete_failure": config.get("notify_delete_failure", True),
            },
        }
    except Exception as e:
        print(f"[GET-NOTIFICATION-SETTINGS] Error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=500, detail=f"Error getting notification settings: {str(e)}"
        )


@router.post("/api/notification-settings")
async def update_notification_settings(settings: NotificationSettings):
    """
    Update notification settings
    """
    try:
        # Get path to notification config file (go up to automation-capi root)
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "vars",
            "notification_config.yml",
        )

        # Update configuration file
        config_data = {
            # Slack settings
            "slack_enabled": settings.slack_enabled,
            "slack_webhook_url": settings.slack_webhook_url or "",
            # Email settings
            "email_enabled": settings.email_enabled,
            "smtp_server": settings.smtp_server or "",
            "smtp_port": settings.smtp_port,
            "smtp_username": settings.smtp_username or "",
            "smtp_password": settings.smtp_password or "",
            "from_email": settings.from_email or "",
            "to_emails": settings.to_emails or [],
            "use_tls": settings.use_tls,
            # Common settings
            "app_url": settings.app_url,
            "notify_on_start": settings.notify_on_start,
            "notify_on_complete": settings.notify_on_complete,
            "notify_on_failure": settings.notify_on_failure,
            # Provision notification preferences
            "notify_provision_start": settings.notify_provision_start,
            "notify_provision_success": settings.notify_provision_success,
            "notify_provision_failure": settings.notify_provision_failure,
            # Delete notification preferences
            "notify_delete_start": settings.notify_delete_start,
            "notify_delete_success": settings.notify_delete_success,
            "notify_delete_failure": settings.notify_delete_failure,
        }

        with open(config_path, "w") as f:
            yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

        slack_service = _get_slack()
        email_service = _get_email()

        # Reload service configurations
        slack_service.reload_config()
        email_service.reload_config()

        return {
            "success": True,
            "message": "Notification settings updated successfully",
            "settings": config_data,
        }
    except Exception as e:
        print(f"[UPDATE-NOTIFICATION-SETTINGS] Error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=500, detail=f"Error updating notification settings: {str(e)}"
        )


@router.post("/api/notification-settings/test")
async def test_notification_settings(request: Request):
    """
    Test Slack and/or Email notification connections with current form settings
    """
    try:
        # Get test settings from request body (if provided)
        try:
            test_settings = await request.json()
        except:
            test_settings = {}

        # If settings provided in request, use those; otherwise reload from file
        if test_settings:
            # Test with provided settings (from form)
            results = []
            overall_success = True

            # Test Slack if enabled in form
            if test_settings.get("slack_enabled", False):
                # Temporarily create slack service with test settings
                from slack_notification_service import SlackNotificationService

                test_slack = SlackNotificationService()
                test_slack.webhook_url = test_settings.get("slack_webhook_url", "")
                test_slack.config = test_settings
                slack_result = test_slack.test_connection()
                results.append(f"Slack: {slack_result['message']}")
                if not slack_result["success"]:
                    overall_success = False

            # Test Email if enabled in form
            if test_settings.get("email_enabled", False):
                # Temporarily create email service with test settings
                from email_notification_service import EmailNotificationService

                test_email = EmailNotificationService()
                test_email.smtp_server = test_settings.get("smtp_server", "")
                test_email.smtp_port = test_settings.get("smtp_port", 587)
                test_email.smtp_username = test_settings.get("smtp_username", "")
                test_email.smtp_password = test_settings.get("smtp_password", "")
                test_email.from_email = test_settings.get("from_email", "")
                test_email.to_emails = test_settings.get("to_emails", [])
                test_email.use_tls = test_settings.get("use_tls", True)
                test_email.config = test_settings
                email_result = test_email.test_connection()
                results.append(f"Email: {email_result['message']}")
                if not email_result["success"]:
                    overall_success = False
        else:
            slack_service = _get_slack()
            email_service = _get_email()

            # Test with saved configuration
            slack_service.reload_config()
            email_service.reload_config()

            results = []
            overall_success = True

            # Test Slack if enabled
            if slack_service.config.get("slack_enabled", False):
                slack_result = slack_service.test_connection()
                results.append(f"Slack: {slack_result['message']}")
                if not slack_result["success"]:
                    overall_success = False

            # Test Email if enabled
            if email_service.config.get("email_enabled", False):
                email_result = email_service.test_connection()
                results.append(f"Email: {email_result['message']}")
                if not email_result["success"]:
                    overall_success = False

        # If neither is enabled
        if not results:
            return {"success": False, "message": "No notification services are enabled"}

        # Return combined results
        return {"success": overall_success, "message": " | ".join(results)}
    except Exception as e:
        print(f"[TEST-NOTIFICATION-SETTINGS] Error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=500, detail=f"Error testing notification settings: {str(e)}"
        )
