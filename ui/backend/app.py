#!/usr/bin/env python3
"""
ROSA Automation UI Backend
FastAPI-based backend for the ROSA cluster automation interface
"""

from fastapi import FastAPI, HTTPException, WebSocket, BackgroundTasks, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional
import asyncio
import json
import re
import subprocess
import uuid
from datetime import datetime
import os
import yaml
import sqlite3
import time
from slack_notification_service import SlackNotificationService
from email_notification_service import EmailNotificationService
from ai_assistant_service import AIAssistantService

# AI Agent Framework (monitoring, diagnostic, remediation)
try:
    import sys
    _project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    from agents import MonitoringAgent, DiagnosticAgent, RemediationAgent, LearningAgent, IssueState
    AI_AGENTS_AVAILABLE = True
    print("AI Agent Framework loaded successfully")
except ImportError as e:
    AI_AGENTS_AVAILABLE = False
    print(f"AI Agent Framework not available: {e}")

from capa_core import (
    FeatureRegistry as _CoreFeatureRegistry,
    ClusterAutomationSpec as _CoreClusterAutomationSpec,
    validate_feature_value as _core_validate_feature_value,
    validate_cluster_name as _core_validate_cluster_name,
    build_json_merge_patch as _core_build_json_merge_patch,
    resolve_spec_to_plan as _core_resolve_spec_to_plan,
)
from pathlib import Path as _Path

# Shared registry instance (auto-refreshes on file change via mtime cache)
_shared_registry = _CoreFeatureRegistry(_Path(_project_root))

app = FastAPI(title="ROSA Automation API", version="1.0.0")

# Add production endpoints (health checks, metrics, monitoring)
try:
    from app_extensions import add_production_endpoints

    add_production_endpoints(app)
except ImportError:
    print("⚠️  app_extensions not available - production endpoints not loaded")

# Initialize notification services
slack_service = SlackNotificationService()
email_service = EmailNotificationService()

# Initialize AI assistant service
ai_service = AIAssistantService()

# CORS middleware for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for demo (use Redis/DB in production)
jobs: Dict[str, dict] = {}

# AI Agent instances per job (keyed by job_id)
ai_agent_sessions: Dict[str, dict] = {}


def init_ai_agents(job_id: str, dry_run: bool = False) -> Optional[dict]:
    """Initialize AI agent framework for a job. Returns dict of agents or None."""
    if not AI_AGENTS_AVAILABLE:
        return None

    try:
        from pathlib import Path
        base_dir = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

        monitor = MonitoringAgent(base_dir=base_dir)
        diagnostic = DiagnosticAgent(base_dir=base_dir)
        remediation = RemediationAgent(base_dir=base_dir, dry_run=dry_run)
        learning = LearningAgent(base_dir=base_dir)

        def on_issue_detected(issue_type, context, issue):
            resource_key = context.get("resource_key", "")
            remediation_msg = ""
            try:
                diagnosis = diagnostic.diagnose(issue_type, context)
            except Exception as e:
                monitor.mark_issue_failed(issue_type, resource_key)
                if job_id in jobs:
                    jobs[job_id].setdefault("logs", []).append(
                        f"🤖 Agent diagnosis error for {issue_type} ({resource_key}): {e}"
                    )
                return
            if diagnosis and diagnosis.get("confidence", 0) >= 0.7:
                success, message = remediation.remediate(diagnosis)
                remediation_msg = message
                # Record outcome for learning agent
                learning.record_outcome(
                    issue_type=issue_type,
                    diagnosis=diagnosis,
                    fix_applied=diagnosis.get("recommended_fix", ""),
                    success=success,
                    resource_key=resource_key,
                    details=message,
                )
                if success:
                    monitor.mark_issue_resolved(issue_type, resource_key)
                else:
                    monitor.mark_issue_failed(issue_type, resource_key)
                # Log agent action to job logs so users can see it
                if job_id in jobs:
                    action_icon = "✅" if success else "⚠️"
                    jobs[job_id].setdefault("logs", []).append(
                        f"🤖 Agent detected: {issue_type} ({resource_key})"
                    )
                    jobs[job_id]["logs"].append(
                        f"   {action_icon} {message}"
                    )
            elif diagnosis:
                # Low confidence — reset tracked issue to DETECTED so agent
                # can re-evaluate on next retry (e.g., CloudFormation stack
                # transitions from DELETE_IN_PROGRESS to DELETE_FAILED)
                tracking_key = f"{issue_type}:{resource_key}"
                tracked = monitor._tracked_issues.get(tracking_key)
                if tracked:
                    tracked.state = IssueState.DETECTED
                    # Don't count low-confidence checks as real attempts,
                    # but keep attempts >= 1 so the 60s throttle stays active
                    if tracked.attempts > 1:
                        tracked.attempts -= 1
                    # Only log every 5th low-confidence check to reduce noise
                    low_conf_count = getattr(tracked, '_low_conf_count', 0) + 1
                    tracked._low_conf_count = low_conf_count
                    should_log = (low_conf_count == 1 or low_conf_count % 5 == 0)
                else:
                    should_log = True
                if should_log and job_id in jobs:
                    root_cause = diagnosis.get("root_cause", "")
                    jobs[job_id].setdefault("logs", []).append(
                        f"🤖 Agent checked: {issue_type} ({resource_key}) — {root_cause}"
                    )
            # Store agent events for the stats API
            if job_id in jobs:
                jobs[job_id].setdefault("agent_events", [])
                jobs[job_id]["agent_events"].append({
                    "type": "issue_detected",
                    "issue_type": issue_type,
                    "resource_key": resource_key,
                    "diagnosis": diagnosis.get("root_cause", "") if diagnosis else "",
                    "fix_applied": diagnosis.get("recommended_fix", "") if diagnosis else "",
                    "remediation_result": remediation_msg,
                    "confidence": diagnosis.get("confidence", 0) if diagnosis else 0,
                    "timestamp": datetime.now().isoformat(),
                })

        monitor.set_issue_callback(on_issue_detected)

        session = {
            "monitor": monitor,
            "diagnostic": diagnostic,
            "remediation": remediation,
            "learning": learning,
        }
        ai_agent_sessions[job_id] = session
        print(f"[AI Agent] Initialized for job {job_id} (dry_run={dry_run})")
        return session
    except Exception as e:
        print(f"[AI Agent] Failed to initialize: {e}")
        return None


def get_agent_stats(job_id: str) -> dict:
    """Get AI agent statistics for a job."""
    session = ai_agent_sessions.get(job_id)
    if not session:
        return {"enabled": False}

    monitor = session["monitor"]
    remediation = session["remediation"]

    # Build per-resource event details with full timeline
    events = jobs.get(job_id, {}).get("agent_events", [])
    resource_details = {}
    for event in events:
        rk = event.get("resource_key", "unknown")
        if rk not in resource_details:
            resource_details[rk] = {
                "resource_key": rk,
                "issue_type": event.get("issue_type", ""),
                "diagnosis": event.get("diagnosis", ""),
                "fix_applied": event.get("fix_applied", ""),
                "timeline": [],
            }
        # Update latest diagnosis/fix
        resource_details[rk]["diagnosis"] = event.get("diagnosis", "")
        resource_details[rk]["fix_applied"] = event.get("fix_applied", "")
        # Add to timeline
        resource_details[rk]["timeline"].append({
            "time": event.get("timestamp", ""),
            "action": event.get("fix_applied", ""),
            "detail": event.get("diagnosis", ""),
            "result": event.get("remediation_result", ""),
            "confidence": event.get("confidence", 0),
        })

    # Add resolution status from tracked issues
    for key, tracked in monitor._tracked_issues.items():
        rk = tracked.resource_key
        if rk in resource_details:
            resource_details[rk]["status"] = tracked.state.value
            resource_details[rk]["attempts"] = tracked.attempts

    # Count unique issues (by resource) instead of raw pattern matches
    unique_issues = len(resource_details)
    # Count meaningful interventions (exclude log_and_continue and already-deleted confirmations)
    meaningful_interventions = sum(
        1 for i in remediation.interventions
        if i.get("type") not in ("log_and_continue",)
        and "already deleted" not in i.get("details", {}).get("message", "")
    )

    # Flush learning agent outcomes and apply confidence adjustments
    learning = session.get("learning")
    learning_summary = {}
    if learning:
        try:
            learning_summary = learning.end_of_run_summary()
        except Exception as e:
            print(f"[AI Agent] Learning summary error: {e}")

    return {
        "enabled": True,
        "issues_detected": unique_issues,
        "interventions": meaningful_interventions,
        "total_checks": len(monitor.patterns_detected),
        "resource_details": list(resource_details.values()),
        "learning": learning_summary,
    }

# Cache for expensive operations (TTL: 30 seconds)
minikube_clusters_cache = {
    "data": None,
    "timestamp": 0,
    "ttl": 30  # seconds
}
clusters: Dict[str, dict] = {}

# Simple cache for ROSA status to avoid repeated subprocess calls
rosa_status_cache = {"data": None, "timestamp": 0, "ttl": 30}  # Cache for 30 seconds

# Simple cache for OCP connection status to avoid repeated subprocess calls
ocp_status_cache = {
    "data": None,
    "timestamp": 0,
    "ttl": 60,  # Cache for 60 seconds (longer since connection tests are slower)
}

# Store last used YAML file path for ROSA HCP provisioning
last_rosa_yaml_path = {"path": None}


# Pydantic models
class ClusterConfig(BaseModel):
    name: str
    version: str = "4.20.0"
    region: str = "us-west-2"
    instance_type: str = "m5.xlarge"
    min_replicas: int = 2
    max_replicas: int = 3
    network_automation: bool = True
    role_automation: bool = False
    availability_zones: List[str] = ["us-west-2a", "us-west-2b"]
    cidr_block: str = "10.0.0.0/16"
    tags: Dict[str, str] = {}

    # Manual network configuration (used when network_automation=False)
    subnets: Optional[List[str]] = None
    vpc_id: Optional[str] = None

    # Manual IAM role configuration (used when role_automation=False)
    installer_role_arn: Optional[str] = None
    support_role_arn: Optional[str] = None
    worker_role_arn: Optional[str] = None
    oidc_id: Optional[str] = None

    # Operator roles
    ingress_arn: Optional[str] = None
    image_registry_arn: Optional[str] = None
    storage_arn: Optional[str] = None
    network_arn: Optional[str] = None
    kube_cloud_controller_arn: Optional[str] = None
    node_pool_management_arn: Optional[str] = None
    control_plane_operator_arn: Optional[str] = None
    kms_provider_arn: Optional[str] = None


class JobStatus(BaseModel):
    id: str
    status: str  # pending, running, completed, failed
    progress: int  # 0-100
    message: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    logs: List[str] = []


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


# Helper functions
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


def run_minikube_init_playbook(
    playbook_path: str,
    cluster_name: str,
    job_id: str,
    custom_capa_image: dict = None,
):
    """Run Minikube CAPI initialization playbook (sync, called via asyncio.to_thread)"""
    try:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["progress"] = 10
        jobs[job_id][
            "message"
        ] = f"Configuring CAPI/CAPA on Minikube cluster '{cluster_name}' using clusterctl"

        # Get project root
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        # Load credentials from user_vars.yml
        config_path = os.path.join(project_root, "vars", "user_vars.yml")
        credentials = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as file:
                    config = yaml.safe_load(file) or {}
                    credentials = {
                        "AWS_ACCESS_KEY_ID": config.get("AWS_ACCESS_KEY_ID", ""),
                        "AWS_SECRET_ACCESS_KEY": config.get("AWS_SECRET_ACCESS_KEY", ""),
                        "AWS_REGION": config.get("AWS_REGION", "us-west-2"),
                        "OCM_CLIENT_ID": config.get("OCM_CLIENT_ID", ""),
                        "OCM_CLIENT_SECRET": config.get("OCM_CLIENT_SECRET", ""),
                    }
            except Exception as e:
                print(f"Warning: Failed to load credentials: {e}")

        # Switch kubectl context to the Minikube cluster BEFORE running playbook
        try:
            context_switch = subprocess.run(
                ["kubectl", "config", "use-context", cluster_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if context_switch.returncode != 0:
                jobs[job_id]["status"] = "failed"
                jobs[job_id]["message"] = f"Failed to switch kubectl context to '{cluster_name}'"
                jobs[job_id]["logs"].append(f"ERROR: {context_switch.stderr}")
                return
        except Exception as e:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["message"] = f"Failed to switch kubectl context: {str(e)}"
            return

        # Prepare environment with Minikube profile
        env = os.environ.copy()
        env["MINIKUBE_PROFILE"] = cluster_name
        env["KUBECONFIG"] = os.path.expanduser("~/.kube/config")
        env["CAPI_INSTALL_METHOD"] = "clusterctl"

        # Add AWS credentials to environment
        if credentials:
            env.update(credentials)

        # Add custom CAPA image environment variables if provided
        if custom_capa_image:
            env["CUSTOM_CAPA_IMAGE"] = "true"
            env["CUSTOM_CAPA_IMAGE_REPO"] = custom_capa_image.get("repository", "")
            env["CUSTOM_CAPA_IMAGE_TAG"] = custom_capa_image.get("tag", "")
            env["CUSTOM_CAPA_SOURCE_PATH"] = custom_capa_image.get("sourcePath", "")
            jobs[job_id][
                "message"
            ] = f"Configuring CAPI/CAPA on Minikube cluster '{cluster_name}' using clusterctl with custom image {custom_capa_image['repository']}:{custom_capa_image['tag']}"

        # Build ansible-playbook command with AWS credentials as extra vars
        cmd = ["ansible-playbook", playbook_path, "-vv"]

        # Add AWS credentials as Ansible extra vars
        if credentials:
            for key, value in credentials.items():
                cmd.extend(["-e", f"{key}={value}"])

        # Initialize logs list
        jobs[job_id]["logs"] = ["=== ANSIBLE PLAYBOOK OUTPUT ===", ""]

        # Run the initialization playbook with real-time output streaming
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=project_root,
            env=env,
            text=True,
            bufsize=1,
        )

        # Read stdout line by line for real-time streaming
        for line in process.stdout:
            line_text = line.rstrip()
            jobs[job_id]["logs"].append(line_text)

            # Update progress based on log content
            if "TASK" in line_text:
                current_progress = jobs[job_id]["progress"]
                if current_progress < 90:
                    jobs[job_id]["progress"] = min(current_progress + 5, 90)

        # Capture any remaining stderr
        stderr_output = process.stderr.read()
        if stderr_output:
            for line in stderr_output.strip().split("\n"):
                jobs[job_id]["logs"].append(f"[STDERR] {line}")

        returncode = process.wait(timeout=600)

        jobs[job_id]["logs"].append("")
        jobs[job_id]["logs"].append("=== PLAYBOOK COMPLETED ===")
        jobs[job_id]["progress"] = 100

        if returncode == 0:
            jobs[job_id]["status"] = "completed"
            jobs[job_id][
                "message"
            ] = f"✅ CAPI/CAPA initialized successfully on cluster '{cluster_name}'"
            jobs[job_id]["completed_at"] = datetime.now()
        else:
            jobs[job_id]["status"] = "failed"
            jobs[job_id][
                "message"
            ] = f"❌ Failed to initialize CAPI/CAPA on cluster '{cluster_name}'"
            jobs[job_id]["completed_at"] = datetime.now()

    except subprocess.TimeoutExpired:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["message"] = "Initialization timed out after 10 minutes"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["completed_at"] = datetime.now()
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["message"] = f"Error: {str(e)}"
        jobs[job_id]["logs"].append(f"ERROR: {str(e)}")
        jobs[job_id]["progress"] = 100
        jobs[job_id]["completed_at"] = datetime.now()


def _wait_for_resource_deletion(
    resource_type: str, resource_name: str, namespace: str,
    job_id: str, timeout_seconds: int = 1200, poll_interval: int = 10,
):
    """Poll for K8s resource deletion with real-time agent monitoring.

    Unlike Ansible shell tasks (which buffer stdout), this runs directly in Python
    so every poll result is immediately fed to the AI agent for detection.

    Returns True if the resource was deleted, False if timed out.
    """
    import time as _time

    retries = timeout_seconds // poll_interval
    log_prefix = f"[DELETE-WAIT] {resource_type}/{resource_name}"

    def log_and_feed(msg):
        """Log to job, console, and feed to agent."""
        jobs[job_id].setdefault("logs", []).append(msg)
        print(msg)
        agent_session = ai_agent_sessions.get(job_id)
        if agent_session and agent_session.get("monitor"):
            try:
                agent_session["monitor"].process_line(msg)
            except Exception:
                pass

    # Emit agent context so the agent knows which resource we're watching
    context_line = f'#AGENT_CONTEXT: resource_name={resource_name} namespace={namespace} resource_type={resource_type}'
    log_and_feed(context_line)

    for i in range(retries):
        try:
            result = subprocess.run(
                ["oc", "get", resource_type, resource_name, "-n", namespace],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                output = result.stderr + result.stdout
                if any(s in output.lower() for s in ["not found", "notfound", "no resources found"]):
                    msg = f"{resource_type} {resource_name} deleted successfully"
                    log_and_feed(msg)
                    return True
                # Connection error or other failure — warn but keep retrying
                msg = f"WARNING: oc get failed unexpectedly (rc={result.returncode}): {output.strip()}"
                log_and_feed(msg)
            else:
                # Resource still exists
                retries_left = retries - i - 1
                msg = f"FAILED - RETRYING: [localhost]: Wait for {resource_type} {resource_name} deletion to complete ({retries_left} retries left)."
                log_and_feed(msg)
        except subprocess.TimeoutExpired:
            log_and_feed(f"WARNING: oc get timed out for {resource_type}/{resource_name}")
        except Exception as e:
            log_and_feed(f"WARNING: Error checking {resource_type}/{resource_name}: {e}")

        _time.sleep(poll_interval)

    log_and_feed(f"Timed out waiting for {resource_type} {resource_name} deletion after {timeout_seconds}s")
    return False


def _run_deletion_wait_loops(job_id: str, cluster_name: str, namespace: str,
                             delete_network: bool = True, delete_roles: bool = True):
    """Run Python-native wait loops for deletion with real-time agent monitoring.

    Called after the Ansible playbook initiates deletions (with wait_for_deletion=false).
    Runs the same wait sequence as the Ansible task file but in Python so each poll
    is immediately visible to the AI agent.
    """
    import time as _time

    network_name = f"{cluster_name}-network"
    role_config_name = f"{cluster_name}-roles"

    def log_msg(msg):
        jobs[job_id].setdefault("logs", []).append(msg)
        print(f"[DELETE-WAIT] {msg}")

    # Phase 1: Wait for ROSAControlPlane deletion (20 min)
    log_msg(f"Waiting for ROSAControlPlane {cluster_name} deletion...")
    rcp_deleted = _wait_for_resource_deletion(
        "rosacontrolplane", cluster_name, namespace, job_id,
        timeout_seconds=1200, poll_interval=10,
    )
    if rcp_deleted:
        log_msg(f"ROSAControlPlane successfully deleted: {cluster_name}")
    else:
        log_msg(f"ROSAControlPlane {cluster_name} still exists after timeout — failing")
        return False

    # Phase 2: Wait for ROSANetwork and ROSARoleConfig in parallel-ish
    # (Network first since it takes longer, RoleConfig after)
    results = {}

    if delete_network:
        log_msg(f"Waiting for ROSANetwork {network_name} deletion...")
        results["network"] = _wait_for_resource_deletion(
            "rosanetwork", network_name, namespace, job_id,
            timeout_seconds=1800, poll_interval=10,
        )
        if results["network"]:
            log_msg(f"ROSANetwork successfully deleted: {network_name}")
        else:
            log_msg(f"ROSANetwork {network_name} still exists after timeout — failing")
            return False

    if delete_roles:
        log_msg(f"Waiting for ROSARoleConfig {role_config_name} deletion...")
        results["roles"] = _wait_for_resource_deletion(
            "rosaroleconfig", role_config_name, namespace, job_id,
            timeout_seconds=600, poll_interval=10,
        )
        if results["roles"]:
            log_msg(f"ROSARoleConfig successfully deleted: {role_config_name}")
        else:
            log_msg(f"ROSARoleConfig {role_config_name} timed out (non-fatal)")

    return True


# run_ansible_playbook() removed — consolidated into _run_playbook_in_thread()


# API Routes
@app.get("/")
async def root():
    return {"message": "ROSA Automation API", "version": "1.0.0"}


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now()}


@app.get("/api/versions")
async def get_supported_versions():
    """Get supported OpenShift versions — offloads to thread pool."""
    return await asyncio.to_thread(_get_supported_versions_sync)


def _get_supported_versions_sync():
    """Get supported OpenShift versions by calling rosa list versions (sync)."""
    try:
        # Call rosa list versions to get the actual available versions
        result = subprocess.run(
            ["rosa", "list", "versions", "--channel-group", "stable"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            # Fallback to hardcoded versions if rosa command fails
            return {
                "versions": [
                    "4.21.0",
                    "4.20.12",
                    "4.20.11",
                    "4.20.10",
                    "4.20.8",
                    "4.19.22",
                    "4.19.21",
                ],
                "default_version": "4.20.12",
                "latest_version": "4.21.0",
            }

        # Parse the output to extract version numbers
        versions = []
        for line in result.stdout.split("\n"):
            # Skip header and empty lines
            if line.strip() and not line.startswith("VERSION") and not line.startswith("WARN"):
                parts = line.split()
                if parts and parts[0]:
                    version = parts[0]
                    # Validate it's a version string (x.y.z format)
                    if len(version.split(".")) == 3 and all(
                        p.isdigit() for p in version.split(".")
                    ):
                        versions.append(version)

        if not versions:
            # Fallback if parsing failed
            return {
                "versions": [
                    "4.21.0",
                    "4.20.12",
                    "4.20.11",
                    "4.20.10",
                    "4.20.8",
                    "4.19.22",
                    "4.19.21",
                ],
                "default_version": "4.20.12",
                "latest_version": "4.21.0",
            }

        # Return the versions with the latest as default
        return {
            "versions": versions,
            "default_version": (
                versions[1] if len(versions) > 1 else versions[0]
            ),  # Second version is usually latest stable
            "latest_version": versions[0] if versions else "4.21.0",
        }

    except Exception as e:
        print(f"Error fetching ROSA versions: {e}")
        # Fallback to hardcoded versions
        return {
            "versions": ["4.21.0", "4.20.12", "4.20.11", "4.20.10", "4.20.8", "4.19.22", "4.19.21"],
            "default_version": "4.20.12",
            "latest_version": "4.21.0",
        }


@app.get("/api/templates")
async def get_templates():
    """Get available cluster templates"""
    return {
        "templates": [
            {
                "id": "rosa-network-basic",
                "name": "ROSA with Network Automation",
                "description": "Basic ROSA HCP cluster with automated VPC/subnet creation",
                "features": ["network_automation"],
                "version": "4.20",
            },
            {
                "id": "rosa-full-automation",
                "name": "ROSA Full Automation",
                "description": "ROSA HCP cluster with network and role automation",
                "features": ["network_automation", "role_automation"],
                "version": "4.20",
            },
        ]
    }


@app.post("/api/analyze-yaml")
async def analyze_yaml(request: Request):
    """Analyze uploaded YAML to detect network and IAM configuration intent"""
    try:
        body = await request.json()
        yaml_content = body.get("yaml_content")

        if not yaml_content:
            raise HTTPException(status_code=400, detail="No YAML content provided")

        # Parse YAML documents
        documents = list(yaml.safe_load_all(yaml_content))

        # Initialize detection results
        has_rosa_network = False
        has_rosa_role_config = False
        has_manual_subnets = False
        has_manual_roles = False
        has_availability_zones = False

        rosa_control_plane = None

        # Analyze each document
        for doc in documents:
            if not doc:
                continue

            kind = doc.get("kind", "")

            # Check for ROSANetwork resource
            if kind == "ROSANetwork":
                has_rosa_network = True

            # Check for RosaRoleConfig resource
            if kind == "RosaRoleConfig":
                has_rosa_role_config = True

            # Check for ROSAControlPlane with manual configuration
            if kind == "ROSAControlPlane":
                rosa_control_plane = doc
                spec = doc.get("spec", {})

                # Check for manual network config
                if spec.get("subnets"):
                    has_manual_subnets = True
                if spec.get("availabilityZones"):
                    has_availability_zones = True

                # Check for manual IAM roles
                if spec.get("installerRoleARN") or spec.get("rolesRef"):
                    has_manual_roles = True

        # Determine intent
        network_intent = None
        role_intent = None

        if has_rosa_network:
            network_intent = "automated"
        elif has_manual_subnets and has_availability_zones:
            network_intent = "manual"

        if has_rosa_role_config:
            role_intent = "automated"
        elif has_manual_roles:
            role_intent = "manual"

        # Generate user-friendly messages
        messages = []

        if network_intent == "manual":
            messages.append(
                "✓ Detected manual network configuration: You've specified subnets and availability zones. These will be used for your cluster."
            )
        elif network_intent == "automated":
            messages.append(
                "✓ Detected ROSANetwork automation: VPC and subnets will be created automatically using CloudFormation."
            )

        if role_intent == "manual":
            messages.append(
                "✓ Detected manual IAM roles: You've specified custom IAM roles. These will be used for your cluster."
            )
        elif role_intent == "automated":
            messages.append(
                "✓ Detected RosaRoleConfig automation: IAM roles and OIDC provider will be created automatically."
            )

        # Extract configuration values if manual
        config_values = {}
        if rosa_control_plane and network_intent == "manual":
            spec = rosa_control_plane.get("spec", {})
            config_values["subnets"] = spec.get("subnets", [])
            config_values["availability_zones"] = spec.get("availabilityZones", [])

        if rosa_control_plane and role_intent == "manual":
            spec = rosa_control_plane.get("spec", {})
            config_values["installer_role_arn"] = spec.get("installerRoleARN")
            config_values["support_role_arn"] = spec.get("supportRoleARN")
            config_values["worker_role_arn"] = spec.get("workerRoleARN")
            config_values["oidc_id"] = spec.get("oidcID")

            roles_ref = spec.get("rolesRef", {})
            config_values["ingress_arn"] = roles_ref.get("ingressARN")
            config_values["image_registry_arn"] = roles_ref.get("imageRegistryARN")
            config_values["storage_arn"] = roles_ref.get("storageARN")
            config_values["network_arn"] = roles_ref.get("networkARN")
            config_values["kube_cloud_controller_arn"] = roles_ref.get("kubeCloudControllerARN")
            config_values["node_pool_management_arn"] = roles_ref.get("nodePoolManagementARN")
            config_values["control_plane_operator_arn"] = roles_ref.get("controlPlaneOperatorARN")
            config_values["kms_provider_arn"] = roles_ref.get("kmsProviderARN")

        return {
            "network_intent": network_intent,
            "role_intent": role_intent,
            "messages": messages,
            "config_values": config_values,
            "has_rosa_control_plane": rosa_control_plane is not None,
        }

    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing YAML: {str(e)}")


@app.post("/api/clusters")
async def create_cluster(config: ClusterConfig, background_tasks: BackgroundTasks):
    """Create a new ROSA cluster"""

    # Generate unique IDs
    cluster_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())

    # Store cluster config
    clusters[cluster_id] = {
        "id": cluster_id,
        "config": config.dict(),
        "job_id": job_id,
        "created_at": datetime.now(),
        "status": "creating",
    }

    # Create job
    jobs[job_id] = {
        "id": job_id,
        "cluster_id": cluster_id,
        "status": "pending",
        "progress": 0,
        "message": "Job queued for execution",
        "started_at": datetime.now(),
        "logs": [],
    }

    # Use the new automated ROSA HCP playbook
    playbook = "playbooks/create_rosa_hcp_automated.yaml"

    # Map frontend config to playbook extra_vars
    extra_vars = {
        "cluster_name": config.name,
        "openshift_version": config.version,
        "aws_region": config.region,
        "create_rosa_roles": config.role_automation,
        "create_rosa_network": config.network_automation,
        "network_cidr": config.cidr_block,
        "availability_zone_count": len(config.availability_zones),
    }

    # Initialize AI agents for provisioning monitoring
    init_ai_agents(job_id)

    # Start background task
    asyncio.create_task(
        run_playbook_background(playbook, extra_vars, job_id, "Create ROSA HCP Cluster")
    )

    return {
        "cluster_id": cluster_id,
        "job_id": job_id,
        "message": "Cluster creation started",
        "status": "pending",
    }


@app.get("/api/clusters/{cluster_id}")
async def get_cluster(cluster_id: str):
    """Get cluster information"""
    if cluster_id not in clusters:
        raise HTTPException(status_code=404, detail="Cluster not found")

    cluster = clusters[cluster_id]
    job_id = cluster["job_id"]

    # Get job status
    job_status = jobs.get(job_id, {})

    return {"cluster": cluster, "job": job_status}


@app.delete("/api/clusters/{cluster_id}")
async def delete_cluster(cluster_id: str, background_tasks: BackgroundTasks):
    """Delete a ROSA cluster"""
    if cluster_id not in clusters:
        raise HTTPException(status_code=404, detail="Cluster not found")

    cluster = clusters[cluster_id]
    job_id = str(uuid.uuid4())

    # Create deletion job
    jobs[job_id] = {
        "id": job_id,
        "cluster_id": cluster_id,
        "status": "pending",
        "progress": 0,
        "message": "Cluster deletion queued",
        "started_at": datetime.now(),
        "logs": [],
    }

    # Start deletion task
    delete_vars = {
        "cluster_name": cluster["config"].get("name", ""),
        "capi_namespace": cluster["config"].get("capi_namespace", "ns-rosa-hcp"),
    }
    init_ai_agents(job_id)
    asyncio.create_task(
        run_playbook_background("playbooks/delete_rosa_hcp_cluster.yml", delete_vars, job_id, "Delete ROSA HCP Cluster")
    )

    return {"job_id": job_id, "message": "Cluster deletion started"}


def normalize_timestamp(value):
    """Normalize various timestamp formats to datetime for comparison"""
    from datetime import datetime

    if value is None:
        return datetime.min

    # Already a datetime object
    if isinstance(value, datetime):
        return value

    # Unix timestamp (float or int)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value)
        except (ValueError, OSError):
            return datetime.min

    # ISO string or other string format
    if isinstance(value, str):
        if not value or value == "0":
            return datetime.min
        try:
            # Try parsing ISO format
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return datetime.min

    return datetime.min


@app.get("/api/jobs")
async def list_jobs():
    """List all jobs"""
    try:
        # Check for and timeout stuck jobs before returning the list
        check_and_timeout_stuck_jobs()

        # Return all jobs sorted by creation time (newest first)
        job_list = []
        for job_id, job in jobs.items():
            job_data = {**job, "id": job_id}
            job_list.append(job_data)

        # Sort by created_at timestamp (newest first)
        # Use normalize_timestamp to handle different timestamp formats
        job_list.sort(key=lambda x: normalize_timestamp(x.get("created_at")), reverse=True)

        return {"success": True, "jobs": job_list, "count": len(job_list)}
    except Exception as e:
        print(f"❌ Error in list_jobs: {str(e)}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e), "jobs": [], "count": 0}


@app.delete("/api/jobs")
async def clear_all_jobs():
    """Clear all jobs from history"""
    global jobs
    jobs.clear()
    return {"success": True, "message": "All jobs cleared", "count": 0}


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get job status"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    return jobs[job_id]


@app.get("/api/jobs/{job_id}/logs")
async def get_job_logs(job_id: str):
    """Get job logs"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    return {"logs": jobs[job_id].get("logs", [])}


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a running job"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]

    # Only allow canceling jobs that are currently running
    if job.get("status") != "running":
        raise HTTPException(
            status_code=400, detail=f"Cannot cancel job with status: {job.get('status')}"
        )

    # Mark job as cancelled
    jobs[job_id]["status"] = "failed"
    jobs[job_id]["message"] = "Job cancelled by user"
    jobs[job_id]["error"] = "Job was manually cancelled"
    jobs[job_id]["completed_at"] = datetime.now().isoformat()
    jobs[job_id]["progress"] = 0

    return {"success": True, "message": "Job cancelled successfully", "job_id": job_id}


def check_and_timeout_stuck_jobs():
    """Check for stuck jobs and mark them as failed if they've been running too long"""
    TIMEOUT_MINUTES = 90  # Timeout after 90 minutes (allows for long ROSA operations like delete/provision)

    current_time = datetime.now()
    stuck_jobs = []

    for job_id, job in jobs.items():
        # Only check running jobs
        if job.get("status") != "running":
            continue

        # Get job start time
        started_at = job.get("started_at")
        if not started_at:
            # If no started_at, use created_at
            started_at = job.get("created_at")

        if not started_at:
            continue

        # Parse the timestamp
        try:
            if isinstance(started_at, str):
                start_time = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            else:
                start_time = started_at
        except (ValueError, AttributeError):
            continue

        # Check if job has been running for too long
        elapsed_time = (current_time - start_time).total_seconds() / 60  # Convert to minutes

        if elapsed_time > TIMEOUT_MINUTES:
            # Mark job as failed due to timeout
            jobs[job_id]["status"] = "failed"
            jobs[job_id][
                "message"
            ] = f"Job timed out after {int(elapsed_time)} minutes with no progress"
            jobs[job_id]["error"] = f"Job exceeded timeout limit of {TIMEOUT_MINUTES} minutes"
            jobs[job_id]["completed_at"] = datetime.now().isoformat()
            jobs[job_id]["progress"] = 0
            stuck_jobs.append(job_id)

            print(f"⏱️ Marked job {job_id} as failed due to timeout ({int(elapsed_time)} minutes)")

    return stuck_jobs


@app.websocket("/ws/jobs/{job_id}")
async def websocket_job_updates(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for real-time job updates"""
    await websocket.accept()

    if job_id not in jobs:
        await websocket.close(code=1003, reason="Job not found")
        return

    try:
        last_progress = -1
        while True:
            job = jobs.get(job_id, {})
            current_progress = job.get("progress", 0)

            # Send update if progress changed
            if current_progress != last_progress:
                update = {
                    "job_id": job_id,
                    "status": job.get("status", "unknown"),
                    "progress": current_progress,
                    "message": job.get("message", ""),
                    "timestamp": datetime.now().isoformat(),
                }
                # Include AI agent stats if available
                agent_stats = get_agent_stats(job_id)
                if agent_stats.get("enabled"):
                    update["agent_stats"] = agent_stats
                await websocket.send_json(update)
                last_progress = current_progress

            # Close connection if job completed
            if job.get("status") in ["completed", "failed"]:
                break

            await asyncio.sleep(2)  # Update every 2 seconds

    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await websocket.close()


# AI Agent Stats API
@app.get("/api/jobs/{job_id}/agent-stats")
async def get_job_agent_stats(job_id: str):
    """Get AI agent statistics for a specific job"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    stats = get_agent_stats(job_id)
    # Also include any stored agent events
    events = jobs[job_id].get("agent_events", [])
    return {"success": True, "agent_stats": stats, "agent_events": events}


# Notification Settings APIs
@app.get("/api/notification-settings")
async def get_notification_settings():
    """
    Get current notification settings
    """
    try:
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
        import traceback

        print(f"❌ [GET-NOTIFICATION-SETTINGS] Error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=500, detail=f"Error getting notification settings: {str(e)}"
        )


@app.post("/api/notification-settings")
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

        # Reload service configurations
        slack_service.reload_config()
        email_service.reload_config()

        return {
            "success": True,
            "message": "Notification settings updated successfully",
            "settings": config_data,
        }
    except Exception as e:
        import traceback

        print(f"❌ [UPDATE-NOTIFICATION-SETTINGS] Error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=500, detail=f"Error updating notification settings: {str(e)}"
        )


@app.post("/api/notification-settings/test")
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
        import traceback

        print(f"❌ [TEST-NOTIFICATION-SETTINGS] Error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=500, detail=f"Error testing notification settings: {str(e)}"
        )


# User Journey APIs
@app.get("/api/onboarding/tour")
async def get_onboarding_tour():
    """Get guided onboarding tour steps"""
    return {
        "steps": [
            {
                "id": 1,
                "title": "Welcome to ROSA Automation",
                "content": "ROSA (Red Hat OpenShift Service on AWS) lets you run OpenShift clusters on AWS with full automation.",
                "duration": "2 minutes",
                "video_url": None,
            },
            {
                "id": 2,
                "title": "What You'll Need",
                "content": "To get started, you'll need an AWS account and the ROSA CLI installed.",
                "checklist": [
                    {"item": "AWS Account with appropriate permissions", "checked": False},
                    {"item": "ROSA CLI installed and authenticated", "checked": False},
                    {"item": "OpenShift Cluster Manager account", "checked": False},
                ],
            },
            {
                "id": 3,
                "title": "Automation Features",
                "content": "Our automation can handle network setup (VPCs, subnets) and AWS role configuration automatically.",
                "features": [
                    {
                        "name": "ROSANetwork (ACM-21174)",
                        "description": "Automated VPC and subnet creation",
                    },
                    {
                        "name": "ROSARoleConfig (ACM-21162)",
                        "description": "Automated AWS IAM role setup",
                    },
                ],
            },
        ]
    }


@app.get("/api/diagnostics/checks")
async def get_available_diagnostic_checks():
    """Get list of available diagnostic checks"""
    return {
        "checks": [
            {
                "id": "aws_credentials",
                "name": "AWS Credentials",
                "description": "Verify AWS CLI configuration",
            },
            {
                "id": "rosa_auth",
                "name": "ROSA Authentication",
                "description": "Check ROSA CLI login status",
            },
            {
                "id": "openshift_version",
                "name": "OpenShift Version Support",
                "description": "Verify supported versions",
            },
            {
                "id": "network_connectivity",
                "name": "Network Connectivity",
                "description": "Test AWS API connectivity",
            },
            {
                "id": "permissions",
                "name": "IAM Permissions",
                "description": "Verify required AWS permissions",
            },
        ]
    }


@app.post("/api/diagnostics/run")
async def run_diagnostics(request: dict):
    """Run diagnostic checks"""
    checks_to_run = request.get("checks", [])

    # Run actual diagnostic checks
    results = []
    for check_id in checks_to_run:
        if check_id == "aws_credentials":
            # Mock AWS check for now
            results.append(
                {
                    "check": "aws_credentials",
                    "name": "AWS Credentials",
                    "status": "pass",
                    "message": "✅ AWS credentials are valid",
                    "details": "Account: 123456789012, Region: us-west-2",
                }
            )
        elif check_id == "rosa_auth":
            # Get actual ROSA status
            rosa_status = await get_rosa_status()
            if rosa_status["authenticated"]:
                user_display = rosa_status.get("user_info", {}).get("aws_account_id", "Unknown")
                results.append(
                    {
                        "check": "rosa_auth",
                        "name": "ROSA Authentication",
                        "status": "pass",
                        "message": f"✅ ROSA CLI authenticated",
                        "details": f"Account: {user_display}",
                        "raw_output": rosa_status.get("raw_output", ""),
                    }
                )
            else:
                results.append(
                    {
                        "check": "rosa_auth",
                        "name": "ROSA Authentication",
                        "status": "fail",
                        "message": f"❌ {rosa_status['message']}",
                        "fix": rosa_status.get(
                            "suggestion",
                            "Run 'rosa login --env staging --use-auth-code' to authenticate",
                        ),
                        "command": rosa_status.get(
                            "fix_command", "rosa login --env staging --use-auth-code"
                        ),
                        "error": rosa_status.get("error", ""),
                    }
                )
        elif check_id == "openshift_version":
            results.append(
                {
                    "check": "openshift_version",
                    "name": "OpenShift Version Support",
                    "status": "pass",
                    "message": "✅ OpenShift 4.20 is supported",
                    "details": "Available versions: 4.18, 4.19, 4.20",
                }
            )

    return {"results": results}


@app.get("/api/environment/overview")
async def get_environment_overview():
    """Get comprehensive environment overview"""
    return {
        "aws": {
            "account_id": "123456789012",
            "region": "us-west-2",
            "credentials_status": "valid",
            "last_verified": datetime.now().isoformat(),
        },
        "rosa": {
            "authenticated": True,
            "organization": "Red Hat",
            "subscription_status": "active",
            "console_url": "https://console.redhat.com/openshift",
        },
        "clusters": [
            {
                "name": "tfitzger-rosa-hcp-capi-test",
                "status": "error",
                "version": "4.18.9",
                "region": "us-west-2",
                "node_count": 0,
                "created": "2025-08-11T00:00:00Z",
                "error_message": "Cluster provisioning failed - check AWS permissions",
                "upgrade_available": "4.20.0",
                "automation_used": False,
            }
        ],
        "automation_status": {
            "network_automation_available": True,
            "role_automation_available": True,
            "templates_count": 2,
            "could_have_prevented_issues": True,
        },
        "recommendations": [
            "🚨 Your cluster 'tfitzger-rosa-hcp-capi-test' is in error state - run diagnostics",
            "⬆️ Consider upgrading from OpenShift 4.18.9 to 4.20.0 for better stability",
            "🔧 Use ROSANetwork automation to prevent networking issues in future clusters",
            "📋 Review our troubleshooting guide for cluster error resolution",
        ],
        "alerts": [
            {
                "type": "error",
                "message": "1 cluster in error state requires attention",
                "action": "Run diagnostics",
                "severity": "high",
            },
            {
                "type": "info",
                "message": "Automation features available to improve reliability",
                "action": "Learn about automation",
                "severity": "medium",
            },
        ],
    }


@app.get("/api/rosa/status")
async def get_rosa_status():
    """Check ROSA CLI authentication status — offloads to thread pool."""
    return await asyncio.to_thread(_get_rosa_status_sync)


def _get_rosa_status_sync():
    """Check ROSA CLI authentication status (sync)."""
    import time

    # Check if we have cached data that's still valid
    current_time = time.time()
    if (
        rosa_status_cache["data"] is not None
        and current_time - rosa_status_cache["timestamp"] < rosa_status_cache["ttl"]
    ):
        return rosa_status_cache["data"]

    try:
        # Use synchronous subprocess with very short timeout for better reliability
        result = subprocess.run(
            ["rosa", "whoami"], capture_output=True, text=True, timeout=5  # Very short timeout
        )

        if result.returncode == 0:
            # Parse rosa whoami output
            output_lines = result.stdout.split("\n")
            user_info = {}

            for line in output_lines:
                if ":" in line:
                    key, value = line.split(":", 1)
                    user_info[key.strip().lower().replace(" ", "_")] = value.strip()

            response_data = {
                "authenticated": True,
                "status": "success",
                "message": "ROSA CLI is authenticated and ready",
                "user_info": user_info,
                "raw_output": result.stdout,
                "command": "rosa whoami",
                "last_checked": datetime.now().isoformat(),
            }

            # Cache the successful response
            rosa_status_cache["data"] = response_data
            rosa_status_cache["timestamp"] = current_time

            return response_data
        else:
            # Parse error to provide helpful guidance
            error_msg = result.stderr if result.stderr else "Unknown error"

            if "not logged in" in error_msg.lower() or "authentication" in error_msg.lower():
                fix_command = "rosa login --env staging --use-auth-code"
                suggestion = "Run 'rosa login --env staging --use-auth-code' to authenticate with the ROSA staging environment"
            elif "command not found" in error_msg.lower():
                fix_command = "Install ROSA CLI"
                suggestion = (
                    "Install the ROSA CLI from https://console.redhat.com/openshift/downloads"
                )
            else:
                fix_command = "rosa whoami"
                suggestion = "Check your ROSA CLI installation and network connectivity"

            return {
                "authenticated": False,
                "status": "error",
                "message": f"ROSA CLI authentication failed: {error_msg}",
                "error": error_msg,
                "fix_command": fix_command,
                "suggestion": suggestion,
                "last_checked": datetime.now().isoformat(),
            }

    except subprocess.TimeoutExpired:
        return {
            "authenticated": False,
            "status": "timeout",
            "message": "ROSA CLI command timed out after 5 seconds",
            "error": "Command execution timed out",
            "fix_command": "rosa whoami",
            "suggestion": "Check your network connectivity and try again",
            "last_checked": datetime.now().isoformat(),
        }
    except FileNotFoundError:
        return {
            "authenticated": False,
            "status": "not_installed",
            "message": "ROSA CLI is not installed",
            "error": "ROSA CLI not found in PATH",
            "fix_command": "Install ROSA CLI",
            "suggestion": "Install the ROSA CLI from https://console.redhat.com/openshift/downloads",
            "last_checked": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "authenticated": False,
            "status": "error",
            "message": f"Unexpected error checking ROSA status: {str(e)}",
            "error": str(e),
            "fix_command": "rosa whoami",
            "suggestion": "Check your ROSA CLI installation and try again",
            "last_checked": datetime.now().isoformat(),
        }


@app.get("/api/config/status")
async def get_config_status():
    """Check if vars/user_vars.yml has been properly configured"""
    try:
        # Path to user_vars.yml relative to the project root
        # Go up from ui/backend/app.py -> ui/backend -> ui -> automation-capi (project root)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        config_path = os.path.join(project_root, "vars", "user_vars.yml")

        if not os.path.exists(config_path):
            return {
                "configured": False,
                "status": "missing",
                "message": "vars/user_vars.yml file not found",
                "missing_fields": [],
                "empty_fields": [],
                "suggestion": "Create vars/user_vars.yml from the template",
                "last_checked": datetime.now().isoformat(),
            }

        # Read and parse the YAML file
        with open(config_path, "r") as file:
            config = yaml.safe_load(file) or {}

        # Required fields that must be configured
        required_fields = {
            "OCP_HUB_API_URL": "OpenShift Hub API URL",
            "OCP_HUB_CLUSTER_USER": "OpenShift Hub Username",
            "OCP_HUB_CLUSTER_PASSWORD": "OpenShift Hub Password",
            "AWS_REGION": "AWS Region",
            "AWS_ACCESS_KEY_ID": "AWS Access Key ID",
            "AWS_SECRET_ACCESS_KEY": "AWS Secret Access Key",
            "OCM_CLIENT_ID": "OpenShift Cluster Manager Client ID",
            "OCM_CLIENT_SECRET": "OpenShift Cluster Manager Client Secret",
        }

        # Check which fields are missing or empty
        missing_fields = []
        empty_fields = []
        configured_fields = []

        for field, description in required_fields.items():
            if field not in config:
                missing_fields.append({"field": field, "description": description})
            elif not config[field] or str(config[field]).strip() == "":
                empty_fields.append({"field": field, "description": description})
            else:
                configured_fields.append({"field": field, "description": description})

        # Determine overall status
        total_required = len(required_fields)
        total_configured = len(configured_fields)

        if total_configured == total_required:
            status = "fully_configured"
            message = "All required credentials are configured"
        elif total_configured > 0:
            status = "partially_configured"
            message = f"{total_configured}/{total_required} credentials configured"
        else:
            status = "not_configured"
            message = "No credentials have been configured"

        return {
            "configured": total_configured == total_required,
            "status": status,
            "message": message,
            "total_required": total_required,
            "total_configured": total_configured,
            "configured_fields": configured_fields,
            "missing_fields": missing_fields,
            "empty_fields": empty_fields,
            "suggestion": "Configure the missing credentials in vars/user_vars.yml",
            "config_file_path": "vars/user_vars.yml",
            "last_checked": datetime.now().isoformat(),
        }

    except yaml.YAMLError as e:
        return {
            "configured": False,
            "status": "invalid_yaml",
            "message": f"Invalid YAML format in vars/user_vars.yml: {str(e)}",
            "missing_fields": [],
            "empty_fields": [],
            "suggestion": "Fix the YAML syntax errors in vars/user_vars.yml",
            "last_checked": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "configured": False,
            "status": "error",
            "message": f"Error reading configuration: {str(e)}",
            "missing_fields": [],
            "empty_fields": [],
            "suggestion": "Check file permissions and try again",
            "last_checked": datetime.now().isoformat(),
        }


# Credentials management endpoints
@app.get("/api/credentials")
async def get_credentials():
    """Get current credentials from vars/user_vars.yml"""
    try:
        # Path to user_vars.yml
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        config_path = os.path.join(project_root, "vars", "user_vars.yml")

        if not os.path.exists(config_path):
            return {
                "success": False,
                "message": "vars/user_vars.yml file not found",
                "credentials": {},
            }

        # Read and parse the YAML file
        with open(config_path, "r") as file:
            config = yaml.safe_load(file) or {}

        # Return only the credential fields we care about
        credentials = {
            "OCP_HUB_API_URL": config.get("OCP_HUB_API_URL", ""),
            "OCP_HUB_CLUSTER_USER": config.get("OCP_HUB_CLUSTER_USER", ""),
            "OCP_HUB_CLUSTER_PASSWORD": config.get("OCP_HUB_CLUSTER_PASSWORD", ""),
            "AWS_REGION": config.get("AWS_REGION", ""),
            "AWS_ACCESS_KEY_ID": config.get("AWS_ACCESS_KEY_ID", ""),
            "AWS_SECRET_ACCESS_KEY": config.get("AWS_SECRET_ACCESS_KEY", ""),
            "OCM_CLIENT_ID": config.get("OCM_CLIENT_ID", ""),
            "OCM_CLIENT_SECRET": config.get("OCM_CLIENT_SECRET", ""),
            # Minikube cluster selection fields
            "clusterName": config.get("clusterName", ""),
            "apiPort": config.get("apiPort", ""),
        }

        return {"success": True, "credentials": credentials}

    except Exception as e:
        return {
            "success": False,
            "message": f"Error reading credentials: {str(e)}",
            "credentials": {},
        }


class CredentialsUpdate(BaseModel):
    credentials: Dict[str, str]


@app.post("/api/credentials")
async def save_credentials(update: CredentialsUpdate):
    """Save credentials to vars/user_vars.yml"""
    try:
        # Path to user_vars.yml
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        config_path = os.path.join(project_root, "vars", "user_vars.yml")

        # Read existing config or create new one
        if os.path.exists(config_path):
            with open(config_path, "r") as file:
                config = yaml.safe_load(file) or {}
        else:
            config = {}

        # Update with new credentials
        for key, value in update.credentials.items():
            config[key] = value

        # Write back to file with proper formatting
        with open(config_path, "w") as file:
            yaml.dump(config, file, default_flow_style=False, sort_keys=False)

        return {"success": True, "message": "Credentials saved successfully"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving credentials: {str(e)}")


@app.get("/api/ocp/connection-status")
async def get_ocp_connection_status():
    """Test OpenShift Hub connection — offloads to thread pool."""
    return await asyncio.to_thread(_get_ocp_connection_status_sync)


def _get_ocp_connection_status_sync():
    """Test OpenShift Hub connection using OCP_HUB variables from user_vars.yml (sync)."""
    import time

    # Check if we have cached data that's still valid
    current_time = time.time()
    if (
        ocp_status_cache["data"] is not None
        and current_time - ocp_status_cache["timestamp"] < ocp_status_cache["ttl"]
    ):
        return ocp_status_cache["data"]

    try:
        # Path to user_vars.yml
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        config_path = os.path.join(project_root, "vars", "user_vars.yml")

        if not os.path.exists(config_path):
            return {
                "connected": False,
                "status": "config_missing",
                "message": "vars/user_vars.yml file not found",
                "suggestion": "Create and configure vars/user_vars.yml with OCP Hub credentials",
                "last_checked": datetime.now().isoformat(),
            }

        # Read and parse the YAML file
        with open(config_path, "r") as file:
            config = yaml.safe_load(file) or {}

        # Check if OCP Hub variables are configured
        ocp_api_url = config.get("OCP_HUB_API_URL", "").strip()
        ocp_user = config.get("OCP_HUB_CLUSTER_USER", "").strip()
        ocp_password = config.get("OCP_HUB_CLUSTER_PASSWORD", "").strip()

        # Check for placeholder values
        placeholder_values = [
            "your-username",
            "your-password",
            "https://api.your-cluster.example.com:6443",
            "api.your-cluster.example.com",
        ]

        is_placeholder = (
            ocp_user in placeholder_values
            or ocp_password in placeholder_values
            or ocp_api_url in placeholder_values
            or "your-cluster.example.com" in ocp_api_url
        )

        if is_placeholder:
            return {
                "connected": False,
                "status": "placeholder_credentials",
                "message": "⚠️ OCP Hub credentials contain placeholder values",
                "suggestion": (
                    "❌ CREDENTIAL CONFIGURATION REQUIRED\n\n"
                    "Your vars/user_vars.yml file contains placeholder values:\n"
                    f"  • OCP_HUB_CLUSTER_USER: {ocp_user}\n"
                    f"  • OCP_HUB_API_URL: {ocp_api_url}\n\n"
                    "✅ REQUIRED STEPS:\n"
                    "1. Open vars/user_vars.yml\n"
                    "2. Replace placeholder values with your actual OpenShift Hub credentials\n"
                    "3. Get credentials from your OpenShift console → Copy login command\n"
                    "4. Save the file and refresh this page\n\n"
                    "📝 Note: This file is in .gitignore and will not be committed."
                ),
                "detected_values": {
                    "username": ocp_user,
                    "api_url": ocp_api_url,
                },
                "last_checked": datetime.now().isoformat(),
            }

        if not ocp_api_url:
            return {
                "connected": False,
                "status": "missing_api_url",
                "message": "OCP_HUB_API_URL not configured",
                "suggestion": "Configure OCP_HUB_API_URL in vars/user_vars.yml",
                "last_checked": datetime.now().isoformat(),
            }

        if not ocp_user or not ocp_password:
            return {
                "connected": False,
                "status": "missing_credentials",
                "message": "OCP Hub username or password not configured",
                "suggestion": "Configure OCP_HUB_CLUSTER_USER and OCP_HUB_CLUSTER_PASSWORD in vars/user_vars.yml",
                "configured_url": ocp_api_url,
                "last_checked": datetime.now().isoformat(),
            }

        # Test the connection using oc login
        login_cmd = [
            "oc",
            "login",
            ocp_api_url,
            "--username",
            ocp_user,
            "--password",
            ocp_password,
            "--insecure-skip-tls-verify=true",
        ]

        # Run oc login command
        result = subprocess.run(login_cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            # Login successful, now get cluster info
            try:
                # Get cluster version
                version_result = subprocess.run(
                    ["oc", "version", "--short"], capture_output=True, text=True, timeout=10
                )

                # Get current user context
                whoami_result = subprocess.run(
                    ["oc", "whoami"], capture_output=True, text=True, timeout=10
                )

                # Get cluster info
                cluster_result = subprocess.run(
                    ["oc", "cluster-info"], capture_output=True, text=True, timeout=10
                )

                cluster_info = {}
                if version_result.returncode == 0:
                    cluster_info["version"] = version_result.stdout.strip()
                if whoami_result.returncode == 0:
                    cluster_info["current_user"] = whoami_result.stdout.strip()
                if cluster_result.returncode == 0:
                    cluster_info["cluster_info"] = cluster_result.stdout.strip()

                response_data = {
                    "connected": True,
                    "status": "connected",
                    "message": "Successfully connected to OpenShift Hub cluster",
                    "api_url": ocp_api_url,
                    "username": ocp_user,
                    "cluster_info": cluster_info,
                    "connection_test_output": result.stdout.strip(),
                    "last_checked": datetime.now().isoformat(),
                }

                # Cache the successful response
                ocp_status_cache["data"] = response_data
                ocp_status_cache["timestamp"] = current_time

                return response_data

            except subprocess.TimeoutExpired:
                return {
                    "connected": True,
                    "status": "connected_limited",
                    "message": "Connected to OpenShift, but cluster info retrieval timed out",
                    "api_url": ocp_api_url,
                    "username": ocp_user,
                    "last_checked": datetime.now().isoformat(),
                }

        else:
            # Login failed
            error_msg = result.stderr.strip() if result.stderr else result.stdout.strip()

            if (
                "unauthorized" in error_msg.lower()
                or "invalid username or password" in error_msg.lower()
                or "401" in error_msg
                or "login failed" in error_msg.lower()
            ):
                status = "invalid_credentials"
                message = "❌ Authentication Failed (401 Unauthorized)"
                suggestion = (
                    "❌ AUTHENTICATION FAILED\n\n"
                    "Login to OpenShift Hub cluster failed with 401 Unauthorized.\n\n"
                    f"Cluster: {ocp_api_url}\n"
                    f"Username: {ocp_user}\n\n"
                    "⚠️  POSSIBLE CAUSES:\n\n"
                    "1. ❌ Incorrect Password\n"
                    "   - The password in vars/user_vars.yml may be wrong or outdated\n"
                    "   - Passwords may have been rotated by your cluster administrator\n\n"
                    "2. ❌ Account Disabled/Expired\n"
                    "   - The user account may be disabled or expired\n"
                    "   - Contact your cluster administrator to verify account status\n\n"
                    "3. ❌ Wrong Username\n"
                    "   - The username may be incorrect\n"
                    "   - Verify the username is correct for this cluster\n\n"
                    "✅ REQUIRED ACTIONS:\n\n"
                    "1. Get fresh credentials from your OpenShift cluster:\n"
                    f"   - Log in to OpenShift Console: {ocp_api_url.replace(':6443', '')}\n"
                    "   - Click on your username in the top right\n"
                    "   - Select 'Copy login command'\n"
                    "   - Click 'Display Token'\n"
                    "   - Copy the login command to get current credentials\n\n"
                    "2. Update vars/user_vars.yml with the correct credentials:\n"
                    f'   OCP_HUB_API_URL: "{ocp_api_url}"\n'
                    '   OCP_HUB_CLUSTER_USER: "your-correct-username"\n'
                    '   OCP_HUB_CLUSTER_PASSWORD: "your-correct-password"\n\n'
                    "3. Save the file and refresh this page to retry\n\n"
                    f"📝 Original Error: {error_msg}"
                )
            elif (
                "network" in error_msg.lower()
                or "connection" in error_msg.lower()
                or "timeout" in error_msg.lower()
            ):
                status = "connection_failed"
                message = "Network connection failed"
                suggestion = "Check your network connection and OCP_HUB_API_URL"
            elif "certificate" in error_msg.lower() or "tls" in error_msg.lower():
                status = "tls_error"
                message = "TLS/Certificate error"
                suggestion = "Check the API URL or certificate configuration"
            else:
                status = "login_failed"
                message = f"Login failed: {error_msg}"
                suggestion = "Check your OCP Hub configuration and network connectivity"

            response_data = {
                "connected": False,
                "status": status,
                "message": message,
                "suggestion": suggestion,
                "api_url": ocp_api_url,
                "username": ocp_user,
                "error_details": error_msg,
                "last_checked": datetime.now().isoformat(),
            }

            # Clear cache on failure - don't cache failed login attempts
            ocp_status_cache["data"] = None
            ocp_status_cache["timestamp"] = 0

            return response_data

    except subprocess.TimeoutExpired:
        # Get API URL from config even if timeout occurred
        try:
            project_root = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            config_path = os.path.join(project_root, "vars", "user_vars.yml")
            if os.path.exists(config_path):
                with open(config_path, "r") as file:
                    config = yaml.safe_load(file) or {}
                ocp_api_url = config.get("OCP_HUB_API_URL", "").strip()
            else:
                ocp_api_url = None
        except:
            ocp_api_url = None

        return {
            "connected": False,
            "status": "timeout",
            "message": "Connection test timed out after 30 seconds",
            "suggestion": "Check network connectivity and API URL",
            "api_url": ocp_api_url,
            "last_checked": datetime.now().isoformat(),
        }
    except FileNotFoundError:
        return {
            "connected": False,
            "status": "oc_not_found",
            "message": "OpenShift CLI (oc) not found",
            "suggestion": "Install the OpenShift CLI (oc) command",
            "last_checked": datetime.now().isoformat(),
        }
    except yaml.YAMLError as e:
        return {
            "connected": False,
            "status": "invalid_yaml",
            "message": f"Invalid YAML format in vars/user_vars.yml: {str(e)}",
            "suggestion": "Fix the YAML syntax errors in vars/user_vars.yml",
            "last_checked": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "connected": False,
            "status": "error",
            "message": f"Error testing OCP connection: {str(e)}",
            "suggestion": "Check configuration and try again",
            "last_checked": datetime.now().isoformat(),
        }


@app.get("/api/aws/credentials-status")
async def get_aws_credentials_status():
    """Check AWS credentials validity and provide detailed guidance"""
    try:
        # Path to user_vars.yml
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        config_path = os.path.join(project_root, "vars", "user_vars.yml")

        if not os.path.exists(config_path):
            return {
                "valid": False,
                "status": "config_missing",
                "message": "Configuration file not found",
                "credentials_configured": False,
                "suggestion": "Create vars/user_vars.yml and configure AWS credentials",
                "setup_guide": "Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in vars/user_vars.yml",
                "last_checked": datetime.now().isoformat(),
            }

        # Read configuration
        with open(config_path, "r") as file:
            config = yaml.safe_load(file) or {}

        aws_access_key = config.get("AWS_ACCESS_KEY_ID", "").strip()
        aws_secret_key = config.get("AWS_SECRET_ACCESS_KEY", "").strip()
        aws_region = config.get("AWS_REGION", "us-west-2").strip()

        # Check if credentials are configured
        if not aws_access_key or not aws_secret_key:
            return {
                "valid": False,
                "status": "empty_credentials",
                "message": "AWS credentials not configured",
                "credentials_configured": False,
                "aws_region": aws_region if aws_region else "us-west-2",
                "suggestion": "Configure AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in vars/user_vars.yml",
                "setup_guide": "1. Get AWS credentials from AWS Console → IAM → Users → Your User → Security Credentials\n2. Add to vars/user_vars.yml:\nAWS_ACCESS_KEY_ID: your_access_key\nAWS_SECRET_ACCESS_KEY: your_secret_key",
                "last_checked": datetime.now().isoformat(),
            }

        # Test AWS credentials by calling AWS STS get-caller-identity
        try:
            test_cmd = ["aws", "sts", "get-caller-identity", "--region", aws_region]

            # Set environment variables for the test
            env = os.environ.copy()
            env["AWS_ACCESS_KEY_ID"] = aws_access_key
            env["AWS_SECRET_ACCESS_KEY"] = aws_secret_key
            env["AWS_DEFAULT_REGION"] = aws_region

            result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=15, env=env)

            if result.returncode == 0:
                # Parse the response to get account info
                import json

                try:
                    identity = json.loads(result.stdout)
                    return {
                        "valid": True,
                        "status": "valid",
                        "message": "AWS credentials are valid and working",
                        "credentials_configured": True,
                        "aws_region": aws_region,
                        "account_info": {
                            "account_id": identity.get("Account", "Unknown"),
                            "user_arn": identity.get("Arn", "Unknown"),
                            "user_id": identity.get("UserId", "Unknown"),
                        },
                        "last_checked": datetime.now().isoformat(),
                    }
                except json.JSONDecodeError:
                    return {
                        "valid": True,
                        "status": "valid_no_details",
                        "message": "AWS credentials are valid",
                        "credentials_configured": True,
                        "aws_region": aws_region,
                        "last_checked": datetime.now().isoformat(),
                    }
            else:
                # Credentials are invalid
                error_msg = result.stderr.strip()

                if "InvalidUserID.NotFound" in error_msg or "does not exist" in error_msg:
                    status = "invalid_user"
                    message = "AWS Access Key ID not found"
                    suggestion = "Verify your AWS_ACCESS_KEY_ID is correct"
                elif "SignatureDoesNotMatch" in error_msg or "invalid" in error_msg.lower():
                    status = "invalid_secret"
                    message = "AWS Secret Access Key is invalid"
                    suggestion = "Verify your AWS_SECRET_ACCESS_KEY is correct"
                elif "credentials" in error_msg.lower():
                    status = "invalid_credentials"
                    message = "AWS credentials are invalid"
                    suggestion = "Check both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY"
                else:
                    status = "aws_error"
                    message = f"AWS API error: {error_msg}"
                    suggestion = "Check your AWS credentials and network connectivity"

                return {
                    "valid": False,
                    "status": status,
                    "message": message,
                    "credentials_configured": True,
                    "aws_region": aws_region,
                    "suggestion": suggestion,
                    "troubleshooting": "1. Verify credentials in AWS Console\n2. Check IAM user has required permissions\n3. Ensure credentials are active",
                    "error_details": error_msg,
                    "last_checked": datetime.now().isoformat(),
                }

        except subprocess.TimeoutExpired:
            return {
                "valid": False,
                "status": "timeout",
                "message": "AWS credential validation timed out",
                "credentials_configured": True,
                "aws_region": aws_region,
                "suggestion": "Check your network connectivity to AWS",
                "last_checked": datetime.now().isoformat(),
            }
        except FileNotFoundError:
            return {
                "valid": False,
                "status": "aws_cli_missing",
                "message": "AWS CLI not found",
                "credentials_configured": True,
                "aws_region": aws_region,
                "suggestion": "Install AWS CLI: 'pip install awscli' or 'brew install awscli'",
                "last_checked": datetime.now().isoformat(),
            }

    except yaml.YAMLError as e:
        return {
            "valid": False,
            "status": "invalid_yaml",
            "message": f"Invalid YAML in configuration file: {str(e)}",
            "credentials_configured": False,
            "suggestion": "Fix YAML syntax in vars/user_vars.yml",
            "last_checked": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "valid": False,
            "status": "error",
            "message": f"Error checking AWS credentials: {str(e)}",
            "credentials_configured": False,
            "suggestion": "Check configuration and try again",
            "last_checked": datetime.now().isoformat(),
        }


@app.get("/api/guided-setup/status")
async def get_guided_setup_status():
    """Get comprehensive guided setup status for sequential onboarding"""
    try:
        # Get all prerequisite statuses
        rosa_status = await get_rosa_status()
        config_status = await get_config_status()
        aws_status = await get_aws_credentials_status()
        ocp_status = await get_ocp_connection_status()

        # Determine current step and next actions
        current_step = 1
        next_action = "rosa_login"
        all_prerequisites_met = True

        if not rosa_status["authenticated"]:
            current_step = 1
            next_action = "rosa_login"
            all_prerequisites_met = False
        elif config_status.get("is_new_user", False) or not config_status["configured"]:
            current_step = 2
            next_action = "configure_vars"
            all_prerequisites_met = False
        elif not aws_status["credentials_configured"] or not aws_status["valid"]:
            current_step = 3
            next_action = "aws_credentials"
            all_prerequisites_met = False
        elif not ocp_status["connected"]:
            current_step = 4
            next_action = "ocp_connection"
            all_prerequisites_met = False
            # Check if user has chosen Kind cluster alternative
            # For now, Step 5 is only reachable when OCP connection is successful
            # TODO: Add Kind cluster preference tracking
        else:
            current_step = 5
            next_action = "ready"

        return {
            "current_step": current_step,
            "next_action": next_action,
            "all_prerequisites_met": all_prerequisites_met,
            "steps": {
                1: {
                    "name": "ROSA Staging Authentication",
                    "status": (
                        "completed"
                        if rosa_status["authenticated"]
                        else "current" if current_step == 1 else "pending"
                    ),
                    "required": True,
                    "data": rosa_status,
                },
                2: {
                    "name": "Configuration Setup",
                    "status": (
                        "completed"
                        if config_status["configured"]
                        else "current" if current_step == 2 else "pending"
                    ),
                    "required": True,
                    "data": config_status,
                },
                3: {
                    "name": "AWS Credentials",
                    "status": (
                        "completed"
                        if aws_status["valid"]
                        else "current" if current_step == 3 else "pending"
                    ),
                    "required": True,
                    "data": aws_status,
                },
                4: {
                    "name": "OpenShift Hub Connection",
                    "status": (
                        "completed"
                        if ocp_status["connected"]
                        else "current" if current_step == 4 else "pending"
                    ),
                    "required": True,  # Required until user chooses Kind alternative
                    "description": "Connect to OpenShift Hub or choose Kind cluster for testing",
                    "data": ocp_status,
                },
                5: {
                    "name": "Ready for Automation",
                    "status": "completed" if all_prerequisites_met else "pending",
                    "required": False,
                    "description": "All prerequisites met - ready to create and manage ROSA clusters",
                    "data": {
                        "cluster_connection_ready": ocp_status["connected"],
                        "automation_enabled": all_prerequisites_met,
                    },
                },
            },
            "last_checked": datetime.now().isoformat(),
        }

    except Exception as e:
        return {
            "current_step": 1,
            "next_action": "error",
            "all_prerequisites_met": False,
            "error": f"Error checking guided setup status: {str(e)}",
            "last_checked": datetime.now().isoformat(),
        }


@app.get("/api/user/profile")
async def get_user_profile():
    """Get user profile and permissions"""
    return {
        "identity": {
            "username": "user@example.com",
            "account_id": "123456789012",
            "organization": "My Organization",
            "last_login": datetime.now().isoformat(),
        },
        "permissions": {
            "cluster_create": True,
            "cluster_delete": True,
            "network_manage": True,
            "role_manage": False,
            "admin_access": False,
        },
        "quotas": {
            "clusters": {"used": 2, "limit": 10},
            "vcpus": {"used": 12, "limit": 100},
            "storage": {"used": "500GB", "limit": "5TB"},
        },
        "recent_activity": [
            {"action": "Created cluster 'test-cluster'", "timestamp": "2024-01-16T10:00:00Z"},
            {"action": "Updated automation settings", "timestamp": "2024-01-15T15:30:00Z"},
            {"action": "Ran environment diagnostics", "timestamp": "2024-01-15T09:15:00Z"},
        ],
    }


@app.get("/api/build/templates")
async def get_build_templates():
    """Get project templates for building"""
    return {
        "templates": [
            {
                "id": "development",
                "name": "Development Environment",
                "description": "Perfect for development and testing with cost optimization",
                "icon": "🧪",
                "specs": {
                    "instance_type": "m5.large",
                    "min_nodes": 1,
                    "max_nodes": 3,
                    "features": ["network_automation"],
                },
                "estimated_cost": "$200-400/month",
            },
            {
                "id": "production",
                "name": "Production Application",
                "description": "High availability setup for production workloads",
                "icon": "🚀",
                "specs": {
                    "instance_type": "m5.xlarge",
                    "min_nodes": 3,
                    "max_nodes": 10,
                    "features": ["network_automation", "role_automation"],
                },
                "estimated_cost": "$800-2000/month",
            },
            {
                "id": "learning",
                "name": "Learning & Testing",
                "description": "Minimal setup for learning OpenShift",
                "icon": "📚",
                "specs": {
                    "instance_type": "m5.large",
                    "min_nodes": 1,
                    "max_nodes": 2,
                    "features": ["network_automation"],
                },
                "estimated_cost": "$150-250/month",
            },
        ]
    }


@app.post("/api/validate")
async def validate_config(config: ClusterConfig):
    """Validate cluster configuration"""
    errors = []
    warnings = []

    # Basic validation
    if not config.name.replace("-", "").isalnum():
        errors.append("Cluster name must contain only alphanumeric characters and hyphens")

    if len(config.name) > 15:
        warnings.append("Cluster name longer than 15 characters may cause issues")

    if config.min_replicas > config.max_replicas:
        errors.append("Min replicas cannot be greater than max replicas")

    # Version validation
    if not config.version.startswith("4.20"):
        warnings.append("Only OpenShift 4.20 is fully supported by this automation")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def run_ansible_task_background(
    job_id, task_file, playbook_file, description, kube_context, extra_vars, cluster_type
):
    """Background task to run ansible playbook or task"""
    import tempfile

    try:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["progress"] = 10
        jobs[job_id]["message"] = f"{description} in progress..."

        # Use AUTOMATION_PATH environment variable if set, otherwise calculate from file path
        project_root = os.environ.get("AUTOMATION_PATH") or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

        # If playbook_file is provided, run it directly
        if playbook_file:
            playbook_path = os.path.join(project_root, playbook_file)
            if not os.path.exists(playbook_path):
                raise Exception(f"Playbook file not found: {playbook_file}")

            # Run the playbook directly
            cmd = [
                "ansible-playbook",
                playbook_path,
                "-i",
                "localhost,",  # Inline inventory with localhost
                "-e",
                "skip_ansible_runner=true",
                "-e",
                f"AUTOMATION_PATH={project_root}",
                "-vv",  # Very verbose output (shows task results)
            ]

            # Add cluster context if provided
            if kube_context:
                cmd.extend(["-e", f"KUBE_CONTEXT={kube_context}"])

            # Add extra vars if provided
            for key, value in extra_vars.items():
                cmd.extend(["-e", f"{key}={value}"])

            print(f"Running ansible playbook: {' '.join(cmd)}")

            # Run the command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=project_root,
            )

            # Extract detailed error messages
            detailed_error = ""
            error_summary = ""
            if result.returncode != 0 and result.stdout:
                import re

                # First try to find Ansible fail task messages (e.g., "msg": "...")
                fail_match = re.search(
                    r'fatal:.*?FAILED!.*?"msg":\s*"(.+?)"', result.stdout, re.DOTALL
                )
                if fail_match:
                    # Extract the message and unescape it
                    detailed_error = fail_match.group(1).strip()
                    # Unescape newlines
                    detailed_error = detailed_error.replace("\\n", "\n")

                    # Extract a short summary for the UI
                    # Look for the main error heading (lines starting with ❌)
                    summary_match = re.search(r'❌\s*(.+?)(?:\n|$)', detailed_error)
                    if summary_match:
                        error_summary = summary_match.group(1).strip()
                    # If no emoji heading, check for "ROOT CAUSE:" section
                    elif "ROOT CAUSE:" in detailed_error or "🔍 ROOT CAUSE:" in detailed_error:
                        # Extract first bullet point after ROOT CAUSE
                        root_cause_match = re.search(r'(?:ROOT CAUSE:.*?)\n\s*[•\-]\s*(.+?)(?:\n|$)', detailed_error, re.DOTALL)
                        if root_cause_match:
                            error_summary = root_cause_match.group(1).strip()

                    # Fallback: use first line of error message
                    if not error_summary and detailed_error:
                        error_summary = detailed_error.split('\n')[0][:100]

            error_message = (
                detailed_error
                if detailed_error
                else (result.stderr if result.returncode != 0 else "")
            )

            # Use summary for the message field if available, full error in error field
            display_message = error_summary if error_summary else error_message

            # Update job status with timestamp
            completed_time = datetime.now().strftime("%-I:%M:%S %p")  # e.g., "4:39:21 AM"

            if result.returncode == 0:
                jobs[job_id]["status"] = "completed"
                jobs[job_id]["progress"] = 100
                jobs[job_id][
                    "message"
                ] = f"{description} completed and refreshed at {completed_time}"
                jobs[job_id]["completed_at"] = datetime.now().isoformat()
            else:
                jobs[job_id]["status"] = "failed"
                jobs[job_id]["message"] = f"{description} failed: {display_message}"
                jobs[job_id]["error"] = error_message
                jobs[job_id]["completed_at"] = datetime.now().isoformat()

            jobs[job_id]["logs"] = result.stdout.split("\n") + result.stderr.split("\n")
            return

        # Handle task_file - create temporary playbook
        task_path = os.path.join(project_root, task_file)
        if not os.path.exists(task_path):
            raise Exception(f"Task file not found: {task_file}")

        # Create temporary playbook (similar to existing code)
        tasks = []

        # Check if this is an MCE task that needs OCP login
        mce_tasks = [
            "validate-capa-environment",
            "validate-mce",
            "enable_capi_capa",
            "get_capi_capa_status",
            "get_mce_component_status",
        ]
        if any(task in task_file for task in mce_tasks):
            # Add OCP login and variable setup tasks first
            tasks.extend(
                [
                    {
                        "name": "Set OCP credentials",
                        "set_fact": {
                            "ocp_user": "{{ OCP_HUB_CLUSTER_USER }}",
                            "ocp_password": "{{ OCP_HUB_CLUSTER_PASSWORD }}",
                            "api_url": "{{ OCP_HUB_API_URL }}",
                        },
                    },
                    {
                        "name": "Login to OCP",
                        "include_tasks": f"{project_root}/tasks/login_ocp.yml",
                    },
                ]
            )

        # Set AUTOMATION_PATH as a fact
        tasks.append(
            {
                "name": "Set AUTOMATION_PATH",
                "set_fact": {"AUTOMATION_PATH": project_root},
            }
        )

        # Add the main task
        tasks.append({"name": "Include task file", "include_tasks": f"{project_root}/{task_file}"})

        playbook_content = [
            {
                "name": f"Run task: {description}",
                "hosts": "localhost",
                "connection": "local",
                "gather_facts": False,
                "vars": {
                    "AUTOMATION_PATH": project_root,
                    "playbook_dir": project_root,
                },
                "vars_files": [
                    f"{project_root}/vars/vars.yml",
                    f"{project_root}/vars/user_vars.yml",
                ],
                "tasks": tasks,
            }
        ]

        # Write temporary playbook
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False, dir="/tmp") as f:
            yaml.dump(playbook_content, f, default_flow_style=False)
            temp_playbook = f.name

        try:
            # Prepare ansible command
            cmd = [
                "ansible-playbook",
                temp_playbook,
                "-i",
                "localhost,",
                "-e",
                "skip_ansible_runner=true",
                "-e",
                f"AUTOMATION_PATH={project_root}",
                "-e",
                f"playbook_dir={project_root}",
                "-v",
            ]

            # Add cluster context if provided
            if kube_context:
                cmd.extend(["-e", f"KUBE_CONTEXT={kube_context}"])

            # Add extra vars if provided
            for key, value in extra_vars.items():
                cmd.extend(["-e", f"{key}={value}"])

            print(f"Running ansible task: {' '.join(cmd)}")

            # Set environment variables
            import os as os_module

            env = os_module.environ.copy()
            env["ANSIBLE_PLAYBOOK_DIR"] = project_root

            # Run the command with Popen
            process = subprocess.Popen(
                cmd,
                cwd=project_root,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=-1,
            )

            try:
                stdout, stderr = process.communicate(timeout=300)
                result = type(
                    "obj",
                    (object,),
                    {"returncode": process.returncode, "stdout": stdout, "stderr": stderr},
                )()
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                raise
            except BrokenPipeError as e:
                print(f"❌ [ANSIBLE-TASK] Broken pipe error: {str(e)}")
                try:
                    stdout, stderr = process.communicate(timeout=5)
                except:
                    stdout, stderr = "", str(e)
                result = type(
                    "obj",
                    (object,),
                    {"returncode": -1, "stdout": stdout, "stderr": f"Broken pipe error: {stderr}"},
                )()

            # Parse output
            stdout_lines = result.stdout.split("\n") if result.stdout else []
            stderr_lines = result.stderr.split("\n") if result.stderr else []

            # Extract detailed error messages
            detailed_error = ""
            if result.returncode != 0 and result.stdout:
                import re

                # First try to find Ansible fail task messages (e.g., "msg": "...")
                fail_match = re.search(
                    r'fatal:.*?FAILED!.*?"msg":\s*"(.+?)"', result.stdout, re.DOTALL
                )
                if fail_match:
                    # Extract the message and unescape it
                    detailed_error = fail_match.group(1).strip()
                    # Unescape newlines
                    detailed_error = detailed_error.replace("\\n", "\n")
                else:
                    # Fall back to [ERROR] pattern
                    error_match = re.search(
                        r"\[ERROR\]:\s*Task failed:\s*(.+?)(?=\nOrigin:|$)",
                        result.stdout,
                        re.DOTALL,
                    )
                    if error_match:
                        detailed_error = error_match.group(1).strip()
                        action_match = re.search(
                            r"Action failed:\s*(.+)", detailed_error, re.DOTALL
                        )
                        if action_match:
                            detailed_error = action_match.group(1).strip()

            error_message = (
                detailed_error
                if detailed_error
                else (result.stderr if result.returncode != 0 else "")
            )

            # Update job status
            completed_time = datetime.now().strftime("%-I:%M:%S %p")

            if result.returncode == 0:
                jobs[job_id]["status"] = "completed"
                jobs[job_id]["progress"] = 100
                jobs[job_id][
                    "message"
                ] = f"{description} completed and refreshed at {completed_time}"
                jobs[job_id]["completed_at"] = datetime.now().isoformat()
            else:
                jobs[job_id]["status"] = "failed"
                jobs[job_id]["message"] = f"{description} failed: {error_message}"
                jobs[job_id]["error"] = error_message
                jobs[job_id]["completed_at"] = datetime.now().isoformat()

            jobs[job_id]["logs"] = stdout_lines + stderr_lines

        finally:
            # Clean up temporary playbook file
            try:
                os.unlink(temp_playbook)
            except OSError:
                pass

    except Exception as e:
        import traceback

        error_msg = str(e)
        print(f"❌ Error running task: {error_msg}")
        print(traceback.format_exc())
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["message"] = f"{description} failed: {error_msg}"
        jobs[job_id]["error"] = error_msg
        jobs[job_id]["completed_at"] = datetime.now().isoformat()


@app.post("/api/ansible/run-task")
async def run_ansible_task(request: dict, background_tasks: BackgroundTasks):
    """Run a specific ansible task or playbook"""
    import tempfile
    import uuid

    try:
        task_file = request.get("task_file")
        playbook_file = request.get("playbook_file")
        description = request.get("description", "Running ansible task")
        kube_context = request.get("kube_context")  # Optional cluster context
        extra_vars = request.get("extra_vars", {})  # Optional extra variables
        cluster_type = request.get("cluster_type", "mce")  # mce or minikube

        if not task_file and not playbook_file:
            raise HTTPException(
                status_code=400, detail="Either task_file or playbook_file is required"
            )

        # Create a job entry for tracking
        job_id = str(uuid.uuid4())
        jobs[job_id] = {
            "id": job_id,
            "status": "running",
            "progress": 0,
            "message": f"Starting {description}...",
            "description": description,
            "task_file": task_file or playbook_file,
            "yaml_file": task_file or playbook_file,
            "created_at": datetime.now().isoformat(),
            "started_at": datetime.now().isoformat(),
            "logs": [],
        }

        # Run task in background (use asyncio.to_thread to avoid blocking event loop)
        asyncio.create_task(asyncio.to_thread(
            run_ansible_task_background,
            job_id,
            task_file,
            playbook_file,
            description,
            kube_context,
            extra_vars,
            cluster_type,
        ))

        return {
            "success": True,
            "job_id": job_id,
            "message": f"{description} started",
            "status": "running",
        }
    except Exception as e:
        import traceback

        error_msg = f"Error starting task: {str(e)}"
        print(error_msg)
        print(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=error_msg)


@app.get("/api/mce/features")
async def get_mce_features():
    """Get all MCE features — offloads to thread pool."""
    return await asyncio.to_thread(_get_mce_features_sync)


def _get_mce_features_sync():
    """Get all MCE features and their enablement status (sync)."""
    try:
        # Run oc command to get MCE resource
        result = subprocess.run(
            ["oc", "get", "mce", "-o", "json"], capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Failed to get MCE: {result.stderr}")

        import json

        mce_data = json.loads(result.stdout)

        features = []
        mce_info = None

        # Parse MCE components
        if mce_data.get("items") and len(mce_data["items"]) > 0:
            mce = mce_data["items"][0]

            # Extract MCE info separately (not in features list)
            mce_status = mce.get("status", {}).get("phase", "Unknown")
            mce_name = mce.get("metadata", {}).get("name", "multiclusterengine")
            mce_version = mce.get("status", {}).get("currentVersion", "Unknown")

            # Check for CRD availability
            rosa_network_crd_available = False
            rosa_role_config_crd_available = False

            try:
                # Check for ROSANetwork CRD
                crd_check = subprocess.run(
                    ["oc", "get", "crd", "rosanetworks.infrastructure.cluster.x-k8s.io"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                rosa_network_crd_available = crd_check.returncode == 0

                # Check for ROSARoleConfig CRD (might be named differently)
                # Try both possible CRD names
                for crd_name in [
                    "rosaroleconfigs.infrastructure.cluster.x-k8s.io",
                    "rosaroles.infrastructure.cluster.x-k8s.io",
                ]:
                    crd_check = subprocess.run(
                        ["oc", "get", "crd", crd_name], capture_output=True, text=True, timeout=10
                    )
                    if crd_check.returncode == 0:
                        rosa_role_config_crd_available = True
                        break
            except Exception as e:
                # If CRD check fails, assume CRDs not available
                print(f"CRD check failed: {e}")

            mce_info = {
                "name": mce_name,
                "version": mce_version,
                "status": mce_status,
                "available": mce_status == "Available",
                "capabilities": {
                    "rosaNetworkCrd": rosa_network_crd_available,
                    "rosaRoleConfigCrd": rosa_role_config_crd_available,
                },
            }

            components = mce.get("spec", {}).get("overrides", {}).get("components", [])

            # Feature descriptions
            feature_descriptions = {
                "cluster-api": "Core Cluster API for cluster lifecycle management",
                "cluster-api-provider-aws": "AWS infrastructure provider for Cluster API",
                "hypershift": "HyperShift operator for hosted control planes",
                "hypershift-local-hosting": "Local hosting support for HyperShift",
                "managedserviceaccount": "Managed service account addon",
                "managedserviceaccount-preview": "Preview features for managed service accounts",
                "console-mce": "Multicluster Engine console plugin",
                "discovery": "Cluster discovery service",
                "hive": "Hive operator for cluster provisioning",
                "assisted-service": "Assisted installer service",
                "cluster-lifecycle": "Cluster lifecycle management",
                "cluster-manager": "Cluster manager service",
                "clusterproxy-addon": "Cluster proxy addon",
                "search-v2": "Search v2 service for cluster indexing",
            }

            for component in components:
                name = component.get("name", "Unknown")
                enabled = component.get("enabled", False)

                features.append(
                    {
                        "name": name,
                        "enabled": enabled,
                        "description": feature_descriptions.get(name, ""),
                        "version": mce_version if enabled else None,
                    }
                )

        return {"features": features, "count": len(features), "mce_info": mce_info}

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Request to OpenShift timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching MCE features: {str(e)}")


@app.get("/api/mce/yaml")
async def get_mce_yaml():
    """Get the YAML for the MultiClusterEngine resource"""
    try:
        # Fetch the MultiClusterEngine resource YAML
        result = subprocess.run(
            ["oc", "get", "multiclusterengine", "-o", "yaml"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return {
                "success": False,
                "yaml": None,
                "message": f"Error fetching MCE YAML: {result.stderr}",
            }

        return {
            "success": True,
            "yaml": result.stdout,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "yaml": None,
            "message": "Request to OpenShift timed out",
        }
    except Exception as e:
        import traceback

        print(f"❌ [MCE-YAML] Error: {str(e)}")
        print(traceback.format_exc())
        return {
            "success": False,
            "yaml": None,
            "message": f"Error fetching MCE YAML: {str(e)}",
        }


@app.get("/api/rosa/clusters")
async def get_rosa_clusters(context: str = None):
    """Get actual ROSA HCP clusters — offloads to thread pool so subprocess calls don't block the event loop."""
    return await asyncio.to_thread(_get_rosa_clusters_sync, context)


def _get_rosa_clusters_sync(context: str = None):
    """Get actual ROSA HCP clusters (sync — runs in thread pool to avoid blocking event loop)."""
    import json

    # No CAPI filtering — show all ROSA HCP clusters from rosa CLI
    capi_cluster_names = None

    try:
        # Try to get actual ROSA clusters using rosa CLI with short timeout
        result = subprocess.run(
            ["rosa", "list", "clusters", "-o", "json"],
            capture_output=True,
            text=True,
            timeout=5,  # Short timeout - rosa CLI can hang without credentials
        )

        if result.returncode == 0:
            # Successfully got clusters from rosa CLI
            try:
                rosa_clusters = json.loads(result.stdout)
                clusters = []

                for cluster in rosa_clusters:
                    cluster_name = cluster.get("name", "unknown")

                    # Only include clusters that exist as CAPI resources on this hub
                    if capi_cluster_names is not None and cluster_name not in capi_cluster_names:
                        continue

                    # Extract cluster information from rosa CLI output
                    cluster_info = {
                        "name": cluster_name,
                        "status": "ready" if cluster.get("state") == "ready" else cluster.get("state", "unknown"),
                        "region": cluster.get("region", {}).get("id", "N/A") if isinstance(cluster.get("region"), dict) else cluster.get("region", "N/A"),
                        "created": cluster.get("creation_timestamp"),
                        "version": cluster.get("openshift_version", "N/A"),
                        "namespace": "ns-rosa-hcp",  # CAPI clusters are in ns-rosa-hcp
                        "progress": 100 if cluster.get("state") == "ready" else 50 if cluster.get("state") == "installing" else 0,
                    }

                    clusters.append(cluster_info)

                return {
                    "success": True,
                    "clusters": clusters,
                    "count": len(clusters),
                    "filtered_by_context": context,
                }
            except json.JSONDecodeError:
                # Fall through to RosaControlPlane method
                pass

        # Fallback: Fetch ROSAControlPlane resources from all namespaces
        result = subprocess.run(
            ["oc", "get", "rosacontrolplane", "--all-namespaces", "-o", "json"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return {
                "success": False,
                "clusters": [],
                "message": f"Error fetching ROSA clusters: {result.stderr}",
            }

        data = json.loads(result.stdout)
        clusters = []

        for item in data.get("items", []):
            metadata = item.get("metadata", {})
            spec = item.get("spec", {})
            status = item.get("status", {})

            # Determine cluster status
            ready = status.get("ready", False)
            conditions = status.get("conditions", [])
            deletion_timestamp = metadata.get("deletionTimestamp")

            # Check if cluster is being deleted
            is_deleting = deletion_timestamp is not None
            is_uninstalling = False
            has_error = False
            error_message = None
            error_reason = None

            # Check conditions for uninstalling or error state
            for condition in conditions:
                if condition.get("type") in [
                    "Ready",
                    "ROSAControlPlaneReady",
                    "RosaControlPlaneReady",
                ]:
                    reason = condition.get("reason", "").lower()
                    message = condition.get("message", "")

                    # Check if uninstalling
                    if (
                        reason == "uninstalling"
                        or "uninstalling" in message.lower()
                        or "deleting" in message.lower()
                    ):
                        is_uninstalling = True
                        break

                    # Check for actual errors (but not during deletion or normal provisioning)
                    if condition.get("status") == "False" and not is_deleting:
                        # These reasons indicate normal provisioning states, not errors
                        provisioning_reasons = [
                            "installing",
                            "validating",
                            "provisioning",
                            "waiting",
                            "creating",
                            "notpaused",
                        ]
                        # Only mark as error if reason is NOT a normal provisioning state
                        if reason not in provisioning_reasons:
                            has_error = True
                            error_message = message  # Store the full error message
                            error_reason = condition.get("reason", "Unknown")

            # Determine status string
            if is_deleting or is_uninstalling:
                cluster_status = "uninstalling"
            elif ready:
                cluster_status = "ready"
            elif has_error:
                cluster_status = "failed"
            else:
                cluster_status = "provisioning"

            # Calculate progress for provisioning clusters
            progress = 0
            if cluster_status == "provisioning":
                # Base progress on conditions that are ready
                progress_stages = {
                    "InfrastructureReady": 20,
                    "NetworkReady": 40,
                    "ControlPlaneReady": 60,
                    "ROSAControlPlaneReady": 60,
                    "RosaControlPlaneReady": 60,
                    "Ready": 100,
                }

                # Check which conditions are true
                for condition in conditions:
                    condition_type = condition.get("type", "")
                    condition_status = condition.get("status", "")

                    if condition_status == "True" and condition_type in progress_stages:
                        stage_progress = progress_stages[condition_type]
                        if stage_progress > progress:
                            progress = stage_progress

                # If no conditions are set yet, estimate based on creation time
                if progress == 0:
                    from datetime import datetime, timezone

                    try:
                        created_str = metadata.get("creationTimestamp", "")
                        if created_str:
                            created_time = datetime.fromisoformat(
                                created_str.replace("Z", "+00:00")
                            )
                            elapsed = (datetime.now(timezone.utc) - created_time).total_seconds()
                            # Estimate 5-10 minutes for initial provisioning, cap at 15%
                            progress = min(15, int((elapsed / 60) * 2.5))
                    except:
                        progress = 10  # Default starting progress
            elif cluster_status == "ready":
                progress = 100
            elif cluster_status == "failed":
                progress = 0

            # Extract cluster information
            cluster_info = {
                "name": metadata.get("name", "unknown"),
                "status": cluster_status,
                "region": spec.get("region", "N/A"),
                "created": metadata.get("creationTimestamp"),
                "domain_prefix": spec.get("domainPrefix", "N/A"),
                "version": spec.get("version", "N/A"),
                "namespace": metadata.get("namespace", "default"),
                "progress": progress,
                "error_message": error_message,
                "error_reason": error_reason,
            }

            # Only include clusters that are in 'ready' state (fully provisioned ROSA HCP clusters)
            if cluster_status == "ready":
                clusters.append(cluster_info)

        # Sort by creation time (newest first)
        clusters.sort(key=lambda x: normalize_timestamp(x.get("created")), reverse=True)

        return {
            "success": True,
            "clusters": clusters,
            "count": len(clusters),
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "clusters": [],
            "message": "Request to OpenShift timed out",
        }
    except Exception as e:
        import traceback

        print(f"❌ [ROSA-CLUSTERS] Error: {str(e)}")
        print(traceback.format_exc())
        return {
            "success": False,
            "clusters": [],
            "message": f"Error fetching ROSA clusters: {str(e)}",
        }


def perform_cluster_deletion(job_id: str, cluster_name: str, namespace: str):
    """Background task to perform actual cluster deletion (sync, called via asyncio.to_thread)"""
    import time as _time

    deleted_resources = []
    errors = []

    def log_delete(msg):
        """Write to stdout, logs array, and feed to AI agent monitor."""
        jobs[job_id]["stdout"] += msg + "\n"
        jobs[job_id].setdefault("logs", []).append(msg)
        print(f"[DELETE-CLUSTER] {msg}")
        # Feed to AI agent for real-time issue detection
        agent_session = ai_agent_sessions.get(job_id)
        if agent_session and agent_session.get("monitor"):
            try:
                agent_session["monitor"].process_line(msg)
            except Exception:
                pass

    try:
        jobs[job_id]["progress"] = 5
        jobs[job_id]["message"] = f"Deleting cluster {cluster_name}..."

        # Step 1: Delete Cluster and ROSAControlPlane together
        try:
            log_delete(f"🗑️ Deleting cluster/{cluster_name} and rosacontrolplane/{cluster_name}")
            log_delete(f"ℹ️  This triggers cascading deletion of all dependent resources")

            # Feed agent context for deletion monitoring
            agent_session = ai_agent_sessions.get(job_id)
            if agent_session and agent_session.get("monitor"):
                try:
                    agent_session["monitor"].process_line(
                        f"#AGENT_CONTEXT: resource_name={cluster_name} namespace={namespace} resource_type=rosacontrolplane"
                    )
                except Exception:
                    pass

            result = subprocess.run(
                [
                    "oc",
                    "delete",
                    "-n",
                    namespace,
                    f"cluster/{cluster_name}",
                    f"rosacontrolplane/{cluster_name}",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            jobs[job_id]["progress"] = 15

            if result.returncode == 0:
                deleted_resources.append(f"cluster/{cluster_name}")
                deleted_resources.append(f"rosacontrolplane/{cluster_name}")
                log_delete(f"✅ Deletion initiated for cluster/{cluster_name} and rosacontrolplane/{cluster_name}")
                log_delete(f"✅ Kubernetes will cascade delete MachinePools automatically")

                # Step 2: Wait for the cluster to be fully deleted
                log_delete(f"⏳ Waiting for cluster deletion to complete...")
                jobs[job_id]["message"] = "Waiting for cluster deletion..."

                max_wait_time = 1200
                check_interval = 10
                elapsed_time = 0

                while elapsed_time < max_wait_time:
                    _time.sleep(check_interval)
                    elapsed_time += check_interval

                    # Update progress (15% to 70% during wait)
                    jobs[job_id]["progress"] = min(15 + int(elapsed_time / max_wait_time * 55), 70)

                    check_result = subprocess.run(
                        ["oc", "get", "cluster", cluster_name, "-n", namespace],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )

                    if check_result.returncode != 0 and "not found" in check_result.stderr.lower():
                        log_delete(f"✅ cluster/{cluster_name} successfully deleted after {elapsed_time}s")
                        log_delete(f"✅ ROSA cluster has been removed from AWS/OCM")
                        break
                    else:
                        status_line = f"⏳ Still waiting for cluster deletion... ({elapsed_time}s elapsed)"
                        # Feed every check to the agent (detects stuck deletions)
                        log_delete(status_line) if elapsed_time % 60 == 0 else None
                        # Always feed agent even if not logging to UI
                        agent_session = ai_agent_sessions.get(job_id)
                        if agent_session and agent_session.get("monitor"):
                            try:
                                status_output = check_result.stdout.strip()
                                agent_session["monitor"].process_line(
                                    f"FAILED - RETRYING: cluster/{cluster_name} deletion still pending ({elapsed_time}s) {status_output}"
                                )
                            except Exception:
                                pass

                if elapsed_time >= max_wait_time:
                    errors.append(
                        f"Timeout waiting for cluster/{cluster_name} to delete after {max_wait_time}s"
                    )
                    log_delete(f"⚠️ Timeout waiting for deletion after {max_wait_time}s, but deletion may still complete in background")
            else:
                if "not found" not in result.stderr.lower():
                    errors.append(f"Failed to delete resources: {result.stderr}")
                    log_delete(f"❌ Error deleting resources: {result.stderr}")

        except subprocess.TimeoutExpired:
            errors.append(f"Timeout deleting cluster and rosacontrolplane")
            log_delete(f"❌ Timeout deleting cluster/{cluster_name} and rosacontrolplane/{cluster_name}")
        except Exception as e:
            errors.append(f"Error deleting cluster and rosacontrolplane: {str(e)}")
            log_delete(f"❌ Error: {str(e)}")

        # Step 3: Clean up remaining ROSA resources
        jobs[job_id]["progress"] = 75
        jobs[job_id]["message"] = "Cleaning up remaining resources..."
        log_delete(f"")
        log_delete(f"🧹 Checking for remaining resources to clean up...")

        cleanup_resources = [
            ("rosanetwork", f"{cluster_name}-network"),
            ("rosaroleconfig", f"{cluster_name}-roles"),
            ("rosamachinepool", cluster_name),
            ("rosacluster", cluster_name),
        ]

        # Resources that need wait loops so the agent can detect and fix issues
        # (e.g., CloudFormation DELETE_FAILED blocking ROSANetwork deletion)
        wait_timeouts = {
            "rosanetwork": 1800,    # 30 minutes — CloudFormation stack deletion
            "rosaroleconfig": 600,  # 10 minutes — IAM role cleanup
        }

        # Phase 1: Initiate deletion for all resources
        resources_to_wait = []
        for i, (resource_type, resource_name) in enumerate(cleanup_resources):
            try:
                check_result = subprocess.run(
                    ["oc", "get", resource_type, resource_name, "-n", namespace],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if check_result.returncode == 0:
                    log_delete(f"🧹 Cleaning up {resource_type}/{resource_name}")

                    # Feed agent context for this resource
                    agent_session = ai_agent_sessions.get(job_id)
                    if agent_session and agent_session.get("monitor"):
                        try:
                            agent_session["monitor"].process_line(
                                f"#AGENT_CONTEXT: resource_name={resource_name} namespace={namespace} resource_type={resource_type}"
                            )
                        except Exception:
                            pass

                    result = subprocess.run(
                        [
                            "oc",
                            "delete",
                            resource_type,
                            resource_name,
                            "-n",
                            namespace,
                            "--ignore-not-found=true",
                            "--wait=false",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )

                    if result.returncode == 0:
                        deleted_resources.append(f"{resource_type}/{resource_name}")
                        log_delete(f"✅ Deletion initiated for {resource_type}/{resource_name}")
                        # Track resources that need wait loops
                        if resource_type in wait_timeouts:
                            resources_to_wait.append((resource_type, resource_name))
                    else:
                        log_delete(f"⚠️ Failed to delete {resource_type}/{resource_name}: {result.stderr}")
                else:
                    log_delete(f"✅ {resource_type}/{resource_name} already deleted (cascade)")

            except Exception as e:
                log_delete(f"⚠️ Error cleaning up {resource_type}/{resource_name}: {str(e)}")

        # Phase 2: Wait for critical resources with agent monitoring
        # This allows the agent to detect DELETE_FAILED CloudFormation stacks
        # and trigger VPC dependency cleanup (orphaned security groups, ENIs, etc.)
        for resource_type, resource_name in resources_to_wait:
            max_wait = wait_timeouts[resource_type]
            check_interval = 15
            elapsed = 0

            log_delete(f"")
            log_delete(f"⏳ Waiting for {resource_type}/{resource_name} deletion...")
            jobs[job_id]["message"] = f"Waiting for {resource_type}/{resource_name} deletion..."

            # Feed agent context so it knows which resource we're monitoring
            agent_session = ai_agent_sessions.get(job_id)
            if agent_session and agent_session.get("monitor"):
                try:
                    agent_session["monitor"].process_line(
                        f"#AGENT_CONTEXT: resource_name={resource_name} namespace={namespace} resource_type={resource_type}"
                    )
                except Exception:
                    pass

            while elapsed < max_wait:
                _time.sleep(check_interval)
                elapsed += check_interval

                check_result = subprocess.run(
                    ["oc", "get", resource_type, resource_name, "-n", namespace],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if check_result.returncode != 0:
                    # Resource is gone
                    log_delete(f"✅ {resource_type}/{resource_name} successfully deleted after {elapsed}s")
                    break

                # Resource still exists — feed status to agent for issue detection
                status_output = check_result.stdout.strip()
                status_line = f"FAILED - RETRYING: {resource_type}/{resource_name} deletion still pending ({elapsed}s) {status_output}"

                # Log to UI every 60s, but always feed to agent
                if elapsed % 60 == 0:
                    log_delete(f"⏳ Still waiting for {resource_type}/{resource_name} deletion... ({elapsed}s elapsed)")

                agent_session = ai_agent_sessions.get(job_id)
                if agent_session and agent_session.get("monitor"):
                    try:
                        agent_session["monitor"].process_line(status_line)
                    except Exception:
                        pass

                # Update progress within this wait phase
                base_progress = 80
                progress_range = 15  # 80-95% for wait phase
                wait_progress = min(int(elapsed / max_wait * progress_range), progress_range)
                jobs[job_id]["progress"] = base_progress + wait_progress

            else:
                # Timeout — resource still exists
                log_delete(f"⚠️ {resource_type}/{resource_name} still exists after {max_wait}s timeout")
                errors.append(f"{resource_type}/{resource_name} deletion timed out after {max_wait}s")

            # Post-deletion CloudFormation verification for ROSANetwork
            # The K8s resource may be gone but the CF stack could be DELETE_FAILED
            # with orphaned VPC/SGs costing ~$139/mo
            if resource_type == "rosanetwork":
                stack_name = f"{cluster_name}-rosa-network-stack"
                region = "us-west-2"
                log_delete(f"🔍 Verifying CloudFormation stack {stack_name} cleanup...")
                try:
                    import boto3
                    cf_client = boto3.client(
                        "cloudformation",
                        region_name=region,
                        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", ""),
                        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
                    )
                    try:
                        response = cf_client.describe_stacks(StackName=stack_name)
                        cf_status = response["Stacks"][0]["StackStatus"]
                        if cf_status == "DELETE_COMPLETE":
                            log_delete(f"✅ CloudFormation stack {stack_name} confirmed deleted")
                        elif cf_status == "DELETE_FAILED":
                            log_delete(f"⚠️ CloudFormation stack DELETE_FAILED: {stack_name} — orphaned AWS resources detected")
                            log_delete(f"CloudFormation stack DELETE_FAILED: {stack_name}")
                            # Feed to agent for remediation
                            agent_session = ai_agent_sessions.get(job_id)
                            if agent_session and agent_session.get("monitor"):
                                try:
                                    agent_session["monitor"].process_line(
                                        f"CloudFormation stack DELETE_FAILED: {stack_name}"
                                    )
                                except Exception:
                                    pass
                            errors.append(f"CloudFormation stack {stack_name} DELETE_FAILED — manual cleanup may be needed")
                        elif cf_status == "DELETE_IN_PROGRESS":
                            log_delete(f"⏳ CloudFormation stack {stack_name} still deleting ({cf_status})")
                        else:
                            log_delete(f"ℹ️ CloudFormation stack {stack_name} status: {cf_status}")
                    except cf_client.exceptions.ClientError as e:
                        if "does not exist" in str(e):
                            log_delete(f"✅ CloudFormation stack {stack_name} confirmed deleted")
                        else:
                            log_delete(f"⚠️ CloudFormation check failed: {e}")
                except ImportError:
                    log_delete(f"⚠️ boto3 not available — cannot verify CloudFormation cleanup")
                    log_delete(f"   Check manually: aws cloudformation describe-stacks --stack-name {stack_name}")
                except Exception as e:
                    log_delete(f"⚠️ CloudFormation verification error: {e}")

        # Final status
        jobs[job_id]["progress"] = 100
        jobs[job_id]["agent_stats"] = get_agent_stats(job_id)

        # Log agent summary if agents were active
        agent_stats = jobs[job_id]["agent_stats"]
        if agent_stats.get("enabled"):
            log_delete(f"")
            log_delete(f"🤖 AI Agent Summary:")
            log_delete(f"   Issues detected: {agent_stats.get('issues_detected', 0)}")
            log_delete(f"   Interventions: {agent_stats.get('interventions', 0)}")
            if agent_stats.get('interventions', 0) > 0:
                log_delete(f"   ✅ Agent auto-fixed {agent_stats['interventions']} issue(s) during deletion")

        if deleted_resources:
            message = (
                f"✅ Successfully deleted cluster {cluster_name}\n\nDeleted resources:\n"
                + "\n".join(f"  - {r}" for r in deleted_resources)
            )
            if errors:
                message += f"\n\n⚠️ Warnings:\n" + "\n".join(f"  - {e}" for e in errors)

            jobs[job_id]["status"] = "completed"
            jobs[job_id]["return_code"] = 0
            log_delete(f"")
            log_delete(message)
            jobs[job_id]["message"] = f"✅ Cluster {cluster_name} deleted"
            jobs[job_id]["completed_at"] = datetime.now().isoformat()
        else:
            message = f"❌ Failed to delete cluster {cluster_name}"
            if errors:
                message += f"\n\nErrors:\n" + "\n".join(f"  - {e}" for e in errors)

            jobs[job_id]["status"] = "failed"
            jobs[job_id]["return_code"] = 1
            log_delete(message)
            jobs[job_id]["message"] = f"❌ Failed to delete {cluster_name}"
            jobs[job_id]["completed_at"] = datetime.now().isoformat()

    except Exception as e:
        import traceback

        print(f"❌ [DELETE-CLUSTER] Error: {str(e)}")
        print(traceback.format_exc())
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["return_code"] = 1
        jobs[job_id]["stderr"] += f"❌ Error: {str(e)}\n{traceback.format_exc()}"
        jobs[job_id].setdefault("logs", []).append(f"❌ Error: {str(e)}")
        jobs[job_id]["progress"] = 100
        jobs[job_id]["message"] = f"❌ Error deleting {cluster_name}"
        jobs[job_id]["completed_at"] = datetime.now().isoformat()


@app.delete("/api/rosa/clusters/{cluster_name}")
async def delete_rosa_cluster(
    cluster_name: str, request: Request, background_tasks: BackgroundTasks
):
    """Delete a ROSA HCP cluster and all its resources"""
    import time
    import asyncio

    try:
        body = await request.json()
        namespace = body.get("namespace")

        if not namespace:
            return {"success": False, "message": "Namespace is required"}

        print(f"🗑️ [DELETE-CLUSTER] Deleting cluster: {cluster_name} in namespace: {namespace}")

        # Create job entry immediately
        job_id = f"delete-cluster-{cluster_name}-{int(time.time())}"
        jobs[job_id] = {
            "id": job_id,
            "description": f"Delete ROSA HCP Cluster: {cluster_name}",
            "status": "running",
            "progress": 0,
            "message": f"Deleting cluster {cluster_name}...",
            "created_at": datetime.now(),
            "task_file": None,
            "playbook_file": None,
            "stdout": "",
            "stderr": "",
            "logs": [],
            "return_code": None,
        }

        # Initialize AI agents for deletion monitoring
        init_ai_agents(job_id)

        # Start deletion in background (use asyncio.to_thread to avoid blocking event loop)
        asyncio.create_task(asyncio.to_thread(perform_cluster_deletion, job_id, cluster_name, namespace))

        # Return immediately
        return {
            "success": True,
            "message": f"Cluster deletion started for {cluster_name}",
            "job_id": job_id,
        }

    except Exception as e:
        import traceback

        print(f"❌ [DELETE-CLUSTER] Error: {str(e)}")
        print(traceback.format_exc())
        return {
            "success": False,
            "message": f"Error deleting cluster: {str(e)}",
        }


@app.get("/api/mce/resources")
async def get_mce_resources():
    """Get CAPI/CAPA resources from the MCE environment"""
    try:
        resources = []

        # Define resource types to fetch
        resource_types = [
            # Skip Deployment for now as it's slow and not critical for resource display
            # {
            #     "type": "Deployment",
            #     "namespaces": ["capi-system", "capa-system", "multicluster-engine"],
            # },
            {"type": "AWSClusterControllerIdentity", "namespaces": ["capa-system"]},
            {"type": "ROSACluster", "namespaces": None},  # All namespaces
            {"type": "ROSANetwork", "namespaces": None},  # All namespaces
            {"type": "ROSAControlPlane", "namespaces": None},  # All namespaces
            {"type": "ROSARoleConfig", "namespaces": None},  # All namespaces
        ]

        for resource_config in resource_types:
            resource_type = resource_config["type"]
            namespaces = resource_config["namespaces"]

            try:
                if namespaces:
                    # Fetch from specific namespaces
                    for namespace in namespaces:
                        result = subprocess.run(
                            ["oc", "get", resource_type.lower(), "-n", namespace, "-o", "json"],
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )

                        if result.returncode == 0:
                            import json

                            data = json.loads(result.stdout)
                            for item in data.get("items", []):
                                metadata = item.get("metadata", {})
                                resource_name = metadata.get("name", "unknown")

                                # Get YAML for this resource
                                yaml_result = subprocess.run(
                                    [
                                        "oc",
                                        "get",
                                        resource_type.lower(),
                                        resource_name,
                                        "-n",
                                        namespace,
                                        "-o",
                                        "yaml",
                                    ],
                                    capture_output=True,
                                    text=True,
                                    timeout=10,
                                )

                                yaml_content = (
                                    yaml_result.stdout if yaml_result.returncode == 0 else None
                                )

                                resources.append(
                                    {
                                        "name": resource_name,
                                        "type": resource_type,
                                        "namespace": metadata.get("namespace", namespace),
                                        "status": "Active",
                                        "yaml": yaml_content,
                                    }
                                )
                else:
                    # Fetch from all namespaces
                    result = subprocess.run(
                        ["oc", "get", resource_type.lower(), "--all-namespaces", "-o", "json"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )

                    if result.returncode == 0:
                        import json

                        data = json.loads(result.stdout)
                        for item in data.get("items", []):
                            metadata = item.get("metadata", {})
                            resource_name = metadata.get("name", "unknown")
                            resource_namespace = metadata.get("namespace", "default")

                            # Get YAML for this resource
                            yaml_result = subprocess.run(
                                [
                                    "oc",
                                    "get",
                                    resource_type.lower(),
                                    resource_name,
                                    "-n",
                                    resource_namespace,
                                    "-o",
                                    "yaml",
                                ],
                                capture_output=True,
                                text=True,
                                timeout=10,
                            )

                            yaml_content = (
                                yaml_result.stdout if yaml_result.returncode == 0 else None
                            )

                            resources.append(
                                {
                                    "name": resource_name,
                                    "type": resource_type,
                                    "namespace": resource_namespace,
                                    "status": "Active",
                                    "yaml": yaml_content,
                                }
                            )

            except Exception as e:
                # Log but don't fail if one resource type fails
                print(f"Failed to fetch {resource_type}: {str(e)}")
                continue

        return {"success": True, "resources": resources, "count": len(resources)}

    except Exception as e:
        return {
            "success": False,
            "message": f"Error fetching MCE resources: {str(e)}",
            "resources": [],
        }


@app.post("/api/ansible/run-role")
async def run_ansible_role(request: dict):
    """Run a specific ansible role"""
    try:
        role_name = request.get("role_name")
        description = request.get("description", "Running ansible role")
        extra_vars = request.get("extra_vars", {})

        if not role_name:
            raise HTTPException(status_code=400, detail="role_name is required")

        # Check if role exists
        # Use AUTOMATION_PATH environment variable if set, otherwise calculate from file path
        project_root = os.environ.get("AUTOMATION_PATH") or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        role_path = os.path.join(project_root, "roles", role_name)
        if not os.path.exists(role_path):
            raise HTTPException(status_code=404, detail=f"Role not found: {role_name}")

        # Create a temporary playbook to run the role
        import tempfile
        import yaml

        # Add OCP login and variable setup tasks first for MCE roles
        tasks = []
        mce_roles = ["configure-capa-environment"]
        if role_name in mce_roles:
            tasks.extend(
                [
                    {
                        "name": "Set OCP credentials",
                        "set_fact": {
                            "ocp_user": "{{ OCP_HUB_CLUSTER_USER }}",
                            "ocp_password": "{{ OCP_HUB_CLUSTER_PASSWORD }}",
                            "api_url": "{{ OCP_HUB_API_URL }}",
                        },
                    },
                    {
                        "name": "Login to OCP",
                        "include_tasks": f"{project_root}/tasks/login_ocp.yml",
                    },
                ]
            )

        # Set AUTOMATION_PATH as a fact to ensure it's available to all included tasks
        tasks.append(
            {
                "name": "Set AUTOMATION_PATH",
                "set_fact": {"AUTOMATION_PATH": project_root},
            }
        )

        # Add the main role task
        tasks.append(
            {
                "name": f"Configure the MCE CAPI/CAPA environment",
                "include_role": {"name": role_name},
                "vars": {
                    "ocm_client_id": "{{ OCM_CLIENT_ID }}",
                    "ocm_client_secret": "{{ OCM_CLIENT_SECRET }}",
                },
            }
        )

        playbook_content = {
            "name": f"Run {role_name} role",
            "hosts": "localhost",
            "connection": "local",
            "gather_facts": False,
            "vars": {
                "AUTOMATION_PATH": project_root,
                "playbook_dir": project_root,
            },
            "vars_files": [f"{project_root}/vars/vars.yml", f"{project_root}/vars/user_vars.yml"],
            "tasks": tasks,
        }

        # Write temporary playbook
        # Use AUTOMATION_PATH environment variable if set, otherwise calculate from file path
        project_root = os.environ.get("AUTOMATION_PATH") or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        # Write temp file to /tmp since project_root might be read-only
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False, dir="/tmp") as f:
            yaml.dump([playbook_content], f, default_flow_style=False)
            temp_playbook = f.name

        try:
            # Prepare ansible command
            cmd = [
                "ansible-playbook",
                temp_playbook,
                "-i",
                "localhost,",  # Inline inventory with localhost
                "-e",
                "skip_ansible_runner=true",
                "-e",
                f"AUTOMATION_PATH={project_root}",
                "-e",
                f"playbook_dir={project_root}",
                "-v",  # Verbose output
            ]

            # Add extra vars if provided
            for key, value in extra_vars.items():
                cmd.extend(["-e", f"{key}={value}"])

            print(f"Running ansible role: {' '.join(cmd)}")

            # Set environment variables for Ansible
            import os as os_module

            env = os_module.environ.copy()
            env["ANSIBLE_ROLES_PATH"] = f"{project_root}/roles"
            env["ANSIBLE_PLAYBOOK_DIR"] = project_root

            # Run the command
            result = subprocess.run(
                cmd,
                cwd=project_root,
                env=env,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minutes timeout for roles
            )

            # Parse the output
            stdout_lines = result.stdout.split("\n") if result.stdout else []
            stderr_lines = result.stderr.split("\n") if result.stderr else []

            print(f"Ansible role completed with return code: {result.returncode}")
            print(f"STDOUT: {result.stdout}")
            if result.stderr:
                print(f"STDERR: {result.stderr}")

            return {
                "success": result.returncode == 0,
                "return_code": result.returncode,
                "output": result.stdout,
                "error": result.stderr,
                "message": (
                    "Role completed successfully" if result.returncode == 0 else "Role failed"
                ),
                "role_name": role_name,
                "description": description,
                "stdout_lines": stdout_lines,
                "stderr_lines": stderr_lines,
            }

        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_playbook)
            except OSError:
                pass

    except subprocess.TimeoutExpired as e:
        error_msg = f"Role {role_name} timed out after 10 minutes"
        print(error_msg)
        # Try to get partial output from timeout exception
        partial_output = getattr(e, "stdout", "") or ""
        partial_error = getattr(e, "stderr", "") or ""
        return {
            "success": False,
            "error": error_msg,
            "message": "Role timed out",
            "role_name": role_name,
            "description": description,
            "output": partial_output,
            "return_code": -1,
        }
    except Exception as e:
        error_msg = f"Error running role {role_name}: {str(e)}"
        print(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


def _run_playbook_in_thread(playbook: str, extra_vars: dict, job_id: str, description: str):
    """Run ansible playbook in a thread (called via asyncio.to_thread to avoid blocking event loop)"""
    import re
    import threading

    try:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["progress"] = 10
        jobs[job_id]["message"] = f"Starting playbook: {playbook}"

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        playbook_path = os.path.join(project_root, playbook)

        # For deletion and provisioning playbooks, start a sidecar file tailer for real-time
        # agent monitoring. Ansible shell wait loops buffer stdout, but they also write to a
        # sidecar log file via tee. This thread tails that file and feeds lines to the agent.
        is_deletion = "delete" in playbook.lower()
        is_provisioning = "create" in playbook.lower() or "provision" in playbook.lower()
        use_sidecar = is_deletion or is_provisioning
        sidecar_stop = threading.Event()
        sidecar_thread = None
        agent_lock = threading.Lock()  # Guard process_line from concurrent sidecar + stdout access

        if use_sidecar:
            cluster_name = extra_vars.get("cluster_name", extra_vars.get("clusterName", extra_vars.get("name_prefix", "")))
            if cluster_name and not cluster_name.endswith("-rosa-hcp") and is_provisioning:
                sidecar_cluster = f"{cluster_name}-rosa-hcp"
            else:
                sidecar_cluster = cluster_name
            sidecar_logfile = f"/tmp/{'deletion' if is_deletion else 'provision'}-agent-{sidecar_cluster}.log"

            def _tail_sidecar():
                """Tail the sidecar log file and feed lines to the AI agent in real-time."""
                import time as _sidecar_time
                last_pos = 0
                while not sidecar_stop.is_set():
                    try:
                        if os.path.exists(sidecar_logfile):
                            with open(sidecar_logfile, 'r') as f:
                                f.seek(last_pos)
                                new_lines = f.readlines()
                                if new_lines:
                                    for line in new_lines:
                                        line = line.strip()
                                        if line:
                                            # Feed to agent (lock prevents race with main stdout loop)
                                            agent_session = ai_agent_sessions.get(job_id)
                                            if agent_session and agent_session.get("monitor"):
                                                try:
                                                    with agent_lock:
                                                        agent_session["monitor"].process_line(line)
                                                except Exception:
                                                    pass
                                            # Also add to job logs so UI sees it in real-time
                                            jobs[job_id]["logs"].append(f"[AGENT-SIDECAR] {line}")
                                            print(f"[SIDECAR] {line}")
                                last_pos = f.tell()
                    except Exception:
                        pass
                    _sidecar_time.sleep(2)  # Poll every 2 seconds

            sidecar_thread = threading.Thread(target=_tail_sidecar, daemon=True)
            sidecar_thread.start()

        # If a cluster_context is provided (e.g. Minikube), create an isolated
        # kubeconfig copy for this job so we don't stomp on the global context.
        # This prevents context bleeding between concurrent jobs.
        cluster_context = extra_vars.get("cluster_context", "")
        job_kubeconfig = None

        if cluster_context:
            import shutil
            import tempfile
            try:
                src_kubeconfig = os.environ.get("KUBECONFIG", os.path.expanduser("~/.kube/config"))
                job_kubeconfig = os.path.join(tempfile.gettempdir(), f"kubeconfig-{job_id}")
                shutil.copy2(src_kubeconfig, job_kubeconfig)

                # Switch context in the isolated copy only
                ctx_result = subprocess.run(
                    ["kubectl", "config", "use-context", cluster_context],
                    capture_output=True, text=True, timeout=10,
                    env={**os.environ, "KUBECONFIG": job_kubeconfig},
                )
                if ctx_result.returncode == 0:
                    jobs[job_id]["logs"].append(f"Using isolated kubeconfig for context: {cluster_context}")
                    print(f"[Playbook] Isolated kubeconfig for context: {cluster_context}")
                    # Tell the playbook to skip OCP login since we're using kubectl context
                    extra_vars["skip_ocp_login"] = "true"
                else:
                    jobs[job_id]["status"] = "failed"
                    jobs[job_id]["message"] = f"Failed to switch kubectl context to '{cluster_context}'"
                    jobs[job_id]["logs"].append(f"ERROR: {ctx_result.stderr}")
                    os.remove(job_kubeconfig)
                    return
            except Exception as e:
                jobs[job_id]["status"] = "failed"
                jobs[job_id]["message"] = f"Failed to set up isolated kubeconfig: {str(e)}"
                if job_kubeconfig and os.path.exists(job_kubeconfig):
                    os.remove(job_kubeconfig)
                return

        cmd = ["ansible-playbook", playbook_path, "-v"]

        def camel_to_snake(name):
            special_cases = {'openShift': 'openshift', 'OpenShift': 'openshift'}
            for camel, snake in special_cases.items():
                if camel in name:
                    name = name.replace(camel, snake)
            s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
            return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

        for key, value in extra_vars.items():
            snake_key = camel_to_snake(key)
            str_value = str(value).strip() if value is not None else ""
            cmd.extend(["-e", f"{snake_key}={str_value}"])

        print(f"[Playbook] Running: {' '.join(cmd)}")
        jobs[job_id]["progress"] = 30
        jobs[job_id]["message"] = "Executing ansible playbook"

        env = os.environ.copy()
        # Use the isolated kubeconfig if we created one, otherwise default
        env["KUBECONFIG"] = job_kubeconfig if job_kubeconfig else os.environ.get("KUBECONFIG", os.path.expanduser("~/.kube/config"))
        env["PYTHONUNBUFFERED"] = "1"

        process = subprocess.Popen(
            cmd, cwd=project_root,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, env=env,
        )

        import time as _time
        line_count = 0
        for line in process.stdout:
            line_stripped = line.rstrip()
            jobs[job_id]["logs"].append(line_stripped)

            # AI Agent: Process each line for real-time issue detection
            agent_session = ai_agent_sessions.get(job_id)
            if agent_session and agent_session.get("monitor"):
                try:
                    with agent_lock:
                        agent_session["monitor"].process_line(line_stripped)
                except Exception:
                    pass

            line_count += 1
            if line_count % 10 == 0:
                jobs[job_id]["progress"] = min(30 + (line_count // 10), 95)

            print(line_stripped)

            # Yield the GIL periodically so the event loop can process requests
            if line_count % 5 == 0:
                _time.sleep(0.001)

        returncode = process.wait(timeout=5400)
        print(f"[Playbook] Completed with return code: {returncode}")

        if returncode == 0:
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["progress"] = 100
            jobs[job_id]["return_code"] = 0
            jobs[job_id]["message"] = "Playbook completed successfully"
        else:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["progress"] = 100
            jobs[job_id]["return_code"] = returncode
            jobs[job_id]["message"] = f"Playbook failed with return code {returncode}"

        jobs[job_id]["agent_stats"] = get_agent_stats(job_id)
        jobs[job_id]["completed_at"] = datetime.now().isoformat()

    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["return_code"] = 1
        jobs[job_id]["message"] = "Playbook timed out after 90 minutes"
        jobs[job_id]["logs"].append("ERROR: Process timed out after 90 minutes")
        jobs[job_id]["agent_stats"] = get_agent_stats(job_id)
        jobs[job_id]["completed_at"] = datetime.now().isoformat()
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["return_code"] = 1
        jobs[job_id]["message"] = f"Error: {str(e)}"
        jobs[job_id]["logs"].append(f"ERROR: {str(e)}")
        jobs[job_id]["agent_stats"] = get_agent_stats(job_id)
        jobs[job_id]["completed_at"] = datetime.now().isoformat()
    finally:
        # Stop the sidecar tailer thread
        if sidecar_stop is not None:
            sidecar_stop.set()
        if sidecar_thread is not None:
            sidecar_thread.join(timeout=5)
        # Clean up isolated kubeconfig
        if job_kubeconfig and os.path.exists(job_kubeconfig):
            try:
                os.remove(job_kubeconfig)
            except Exception:
                pass


async def run_playbook_background(playbook: str, extra_vars: dict, job_id: str, description: str):
    """Wrapper that runs the playbook in a thread so the event loop stays free."""
    await asyncio.to_thread(_run_playbook_in_thread, playbook, extra_vars, job_id, description)


@app.post("/api/ansible/run-playbook")
async def run_ansible_playbook_endpoint(request: dict, background_tasks: BackgroundTasks):
    """Run an existing ansible playbook asynchronously"""
    try:
        playbook = request.get("playbook")
        description = request.get("description", "Running ansible playbook")
        extra_vars = request.get("extra_vars", {})

        if not playbook:
            raise HTTPException(status_code=400, detail="playbook is required")

        # Ensure the playbook file exists
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        playbook_path = os.path.join(project_root, playbook)
        if not os.path.exists(playbook_path):
            raise HTTPException(status_code=404, detail=f"Playbook not found: {playbook}")

        # Generate job ID
        job_id = str(uuid.uuid4())

        # Create job
        jobs[job_id] = {
            "id": job_id,
            "status": "pending",
            "progress": 0,
            "message": f"Queued: {description}",
            "logs": [],
            "created_at": datetime.now(),
            "playbook": playbook,
            "description": description,
        }

        # Initialize AI agents for playbook monitoring
        init_ai_agents(job_id)

        # Run playbook as async task (not background_tasks which blocks the event loop)
        asyncio.create_task(
            run_playbook_background(playbook, extra_vars, job_id, description)
        )

        return {
            "success": True,
            "job_id": job_id,
            "status": "pending",
            "message": f"Playbook {playbook} queued for execution",
            "playbook": playbook,
            "description": description,
        }

    except Exception as e:
        error_msg = f"Error queuing playbook {playbook}: {str(e)}"
        print(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


# ===========================
# Minikube API Endpoints
# ===========================


@app.get("/api/capi/component-versions")
async def get_capi_component_versions(cluster_name: str = None, environment: str = None):
    """Get CAPI component versions from the cluster

    Args:
        cluster_name: Optional cluster name (for Minikube context)
        environment: Optional environment type ('mce' or 'minikube')
    """
    try:
        components = []

        # Determine which CLI to use
        if environment == "minikube" or cluster_name:
            # Use kubectl for Minikube
            cli_cmd = ["kubectl"]
            if cluster_name:
                cli_cmd.extend(["--context", cluster_name])
        else:
            # Use oc for OpenShift/MCE (default)
            cli_cmd = ["oc"]

        # Get cert-manager version
        try:
            cert_manager_result = subprocess.run(
                cli_cmd
                + [
                    "get",
                    "deployment",
                    "cert-manager",
                    "-n",
                    "cert-manager",
                    "-o",
                    "jsonpath={.spec.template.spec.containers[0].image}",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if cert_manager_result.returncode == 0:
                image = cert_manager_result.stdout.strip()
                version = image.split(":")[-1] if ":" in image else "unknown"

                # Fetch YAML for cert-manager deployment
                yaml_result = subprocess.run(
                    cli_cmd
                    + ["get", "deployment", "cert-manager", "-n", "cert-manager", "-o", "yaml"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                yaml_content = yaml_result.stdout if yaml_result.returncode == 0 else ""

                components.append(
                    {
                        "name": "Cert Manager",
                        "version": version,
                        "enabled": True,
                        "yaml": yaml_content,
                        "type": "Deployment",
                        "namespace": "cert-manager",
                    }
                )
        except Exception as e:
            print(f"Failed to get cert-manager version: {e}")
            components.append({"name": "Cert Manager", "version": "unknown", "enabled": False})

        # Get CAPI controller version
        try:
            capi_result = subprocess.run(
                cli_cmd
                + [
                    "get",
                    "deployment",
                    "capi-controller-manager",
                    "-n",
                    "capi-system",
                    "-o",
                    "jsonpath={.spec.template.spec.containers[?(@.name=='manager')].image}",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if capi_result.returncode == 0:
                image = capi_result.stdout.strip()
                version = image.split(":")[-1] if ":" in image else "unknown"

                # Fetch YAML for CAPI controller deployment
                yaml_result = subprocess.run(
                    cli_cmd
                    + [
                        "get",
                        "deployment",
                        "capi-controller-manager",
                        "-n",
                        "capi-system",
                        "-o",
                        "yaml",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                yaml_content = yaml_result.stdout if yaml_result.returncode == 0 else ""

                components.append(
                    {
                        "name": "CAPI Controller",
                        "version": version,
                        "enabled": True,
                        "yaml": yaml_content,
                        "type": "Deployment",
                        "namespace": "capi-system",
                    }
                )
        except Exception as e:
            print(f"Failed to get CAPI controller version: {e}")
            components.append({"name": "CAPI Controller", "version": "unknown", "enabled": False})

        # Get CAPA controller version
        try:
            capa_result = subprocess.run(
                cli_cmd
                + [
                    "get",
                    "deployment",
                    "capa-controller-manager",
                    "-n",
                    "capa-system",
                    "-o",
                    "jsonpath={.spec.template.spec.containers[?(@.name=='manager')].image}",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if capa_result.returncode == 0:
                image = capa_result.stdout.strip()
                # Extract version/tag from image
                if ":" in image:
                    repo = image.split(":")[0]
                    tag = image.split(":")[-1]
                    # Check if it's a custom image
                    if "quay.io/melserng" in image or "dev" in tag or "pr" in tag.lower():
                        # Show repo shortname + tag for custom images
                        repo_name = repo.split("/")[-1] if "/" in repo else repo
                        version = f"{tag} (custom: {repo_name})"
                    else:
                        version = tag
                else:
                    version = "unknown"

                # Fetch YAML for CAPA controller deployment
                yaml_result = subprocess.run(
                    cli_cmd
                    + [
                        "get",
                        "deployment",
                        "capa-controller-manager",
                        "-n",
                        "capa-system",
                        "-o",
                        "yaml",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                yaml_content = yaml_result.stdout if yaml_result.returncode == 0 else ""

                components.append(
                    {
                        "name": "CAPA Controller",
                        "version": version,
                        "enabled": True,
                        "yaml": yaml_content,
                        "type": "Deployment",
                        "namespace": "capa-system",
                    }
                )
        except Exception as e:
            print(f"Failed to get CAPA controller version: {e}")
            components.append({"name": "CAPA Controller", "version": "unknown", "enabled": False})

        # Get ROSA CRD version
        try:
            rosa_crd_result = subprocess.run(
                cli_cmd
                + [
                    "get",
                    "crd",
                    "rosacontrolplanes.controlplane.cluster.x-k8s.io",
                    "-o",
                    "jsonpath={.metadata.annotations.controller-gen\\.kubebuilder\\.io/version}",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if rosa_crd_result.returncode == 0:
                version = rosa_crd_result.stdout.strip() or "unknown"

                # Fetch YAML for ROSA CRD
                yaml_result = subprocess.run(
                    cli_cmd
                    + [
                        "get",
                        "crd",
                        "rosacontrolplanes.controlplane.cluster.x-k8s.io",
                        "-o",
                        "yaml",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                yaml_content = yaml_result.stdout if yaml_result.returncode == 0 else ""

                components.append(
                    {
                        "name": "ROSA CRD",
                        "version": version,
                        "enabled": True,
                        "yaml": yaml_content,
                        "type": "CustomResourceDefinition",
                        "namespace": "cluster-scoped",
                    }
                )
        except Exception as e:
            print(f"Failed to get ROSA CRD version: {e}")
            components.append({"name": "ROSA CRD", "version": "unknown", "enabled": False})

        return {"components": components, "timestamp": datetime.now().isoformat()}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get component versions: {str(e)}")


@app.get("/api/capi/cli-versions")
async def get_capi_cli_versions():
    """Get versions of CAPI-related CLI tools (clusterctl, minikube, kubectl)"""
    tools = {}

    # clusterctl version
    try:
        result = subprocess.run(
            ["clusterctl", "version", "-o", "short"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            tools["clusterctl"] = {"installed": True, "version": version}
        else:
            # Try without -o short (older versions)
            result2 = subprocess.run(
                ["clusterctl", "version"],
                capture_output=True, text=True, timeout=10,
            )
            if result2.returncode == 0:
                import re
                match = re.search(r'GitVersion:"([^"]+)"', result2.stdout)
                version = match.group(1) if match else result2.stdout.strip()
                tools["clusterctl"] = {"installed": True, "version": version}
            else:
                tools["clusterctl"] = {"installed": False, "version": None}
    except FileNotFoundError:
        tools["clusterctl"] = {"installed": False, "version": None}
    except Exception as e:
        tools["clusterctl"] = {"installed": False, "version": None, "error": str(e)}

    # minikube version
    try:
        result = subprocess.run(
            ["minikube", "version", "--short"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            tools["minikube"] = {"installed": True, "version": result.stdout.strip()}
        else:
            tools["minikube"] = {"installed": False, "version": None}
    except FileNotFoundError:
        tools["minikube"] = {"installed": False, "version": None}
    except Exception:
        tools["minikube"] = {"installed": False, "version": None}

    # kubectl version
    try:
        result = subprocess.run(
            ["kubectl", "version", "--client", "-o", "json"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            version_data = json.loads(result.stdout)
            version = version_data.get("clientVersion", {}).get("gitVersion", "unknown")
            tools["kubectl"] = {"installed": True, "version": version}
        else:
            tools["kubectl"] = {"installed": False, "version": None}
    except FileNotFoundError:
        tools["kubectl"] = {"installed": False, "version": None}
    except Exception:
        tools["kubectl"] = {"installed": False, "version": None}

    # podman version
    try:
        result = subprocess.run(
            ["podman", "version", "--format", "{{.Client.Version}}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            tools["podman"] = {"installed": True, "version": result.stdout.strip()}
        else:
            tools["podman"] = {"installed": False, "version": None}
    except FileNotFoundError:
        tools["podman"] = {"installed": False, "version": None}
    except Exception:
        tools["podman"] = {"installed": False, "version": None}

    return {"tools": tools, "timestamp": datetime.now().isoformat()}


@app.get("/api/minikube/list-clusters")
async def list_minikube_clusters():
    """List available Minikube profiles (cached for 30 seconds)"""
    global minikube_clusters_cache

    # Check cache first
    current_time = time.time()
    cache_age = current_time - minikube_clusters_cache["timestamp"]

    if minikube_clusters_cache["data"] is not None and cache_age < minikube_clusters_cache["ttl"]:
        print(f"[CACHE HIT] Returning cached Minikube clusters (age: {cache_age:.1f}s)")
        return minikube_clusters_cache["data"]

    print(f"[CACHE MISS] Fetching fresh Minikube clusters (cache age: {cache_age:.1f}s)")

    try:
        # Check if Minikube is installed
        minikube_check = subprocess.run(
            ["minikube", "version"], capture_output=True, text=True, timeout=30
        )

        if minikube_check.returncode != 0:
            result = {
                "clusters": [],
                "minikube_installed": False,
                "message": "Minikube is not installed",
                "suggestion": "Install Minikube first: brew install minikube",
            }
            minikube_clusters_cache["data"] = result
            minikube_clusters_cache["timestamp"] = current_time
            return result

        # List Minikube profiles
        list_result = subprocess.run(
            ["minikube", "profile", "list", "-o", "json"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if list_result.returncode != 0:
            result = {
                "clusters": [],
                "minikube_installed": True,
                "message": "No Minikube clusters found",
                "suggestion": "Create a cluster with: minikube start --profile <cluster-name>",
            }
            minikube_clusters_cache["data"] = result
            minikube_clusters_cache["timestamp"] = current_time
            return result

        try:
            profiles_data = json.loads(list_result.stdout)
            clusters = []

            if "valid" in profiles_data:
                for profile in profiles_data["valid"]:
                    clusters.append(profile["Name"])

            result = {
                "clusters": clusters,
                "minikube_installed": True,
                "message": (
                    f"Found {len(clusters)} Minikube cluster(s)"
                    if clusters
                    else "No Minikube clusters found"
                ),
                "suggestion": (
                    "Create a cluster with: minikube start --profile <cluster-name>"
                    if not clusters
                    else None
                ),
            }
            minikube_clusters_cache["data"] = result
            minikube_clusters_cache["timestamp"] = current_time
            print(f"[CACHE UPDATE] Cached {len(clusters)} Minikube clusters")
            return result
        except json.JSONDecodeError:
            result = {
                "clusters": [],
                "minikube_installed": True,
                "message": "Failed to parse minikube profile list",
                "suggestion": "Check minikube installation",
            }
            minikube_clusters_cache["data"] = result
            minikube_clusters_cache["timestamp"] = current_time
            return result

    except Exception as e:
        result = {
            "clusters": [],
            "minikube_installed": False,
            "message": f"Error listing Minikube clusters: {str(e)}",
            "suggestion": "Check Minikube installation and permissions",
        }
        minikube_clusters_cache["data"] = result
        minikube_clusters_cache["timestamp"] = current_time
        return result


@app.get("/api/minikube/current-context")
async def get_current_kubectl_context():
    """Get the current kubectl context (active cluster)"""
    try:
        # Get current context
        context_result = subprocess.run(
            ["kubectl", "config", "current-context"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if context_result.returncode != 0:
            return {
                "success": False,
                "current_context": None,
                "message": "No current kubectl context set",
            }

        current_context = context_result.stdout.strip()

        return {
            "success": True,
            "current_context": current_context,
            "message": f"Current context: {current_context}",
        }

    except Exception as e:
        return {
            "success": False,
            "current_context": None,
            "message": f"Error getting current context: {str(e)}",
        }


@app.get("/api/minikube/active-profile")
async def get_active_minikube_profile():
    """Get information about the active minikube cluster"""
    try:
        # Get list of minikube profiles
        profile_result = subprocess.run(
            ["minikube", "profile", "list", "-o", "json"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if profile_result.returncode != 0:
            return {
                "success": False,
                "profile": None,
                "message": "No minikube profiles found",
            }

        import json
        profiles_data = json.loads(profile_result.stdout)

        # Find the active profile (valid and running)
        active_profile = None
        for profile_info in profiles_data.get("valid", []):
            profile_name = profile_info.get("Name", "")

            # Get detailed status for this profile
            status_result = subprocess.run(
                ["minikube", "status", "-p", profile_name, "-o", "json"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if status_result.returncode == 0:
                status_data = json.loads(status_result.stdout)
                host_status = status_data.get("Host", "")

                if host_status == "Running":
                    # Get cluster info
                    cluster_info_result = subprocess.run(
                        ["kubectl", "cluster-info", "--context", profile_name],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )

                    api_url = ""
                    if cluster_info_result.returncode == 0:
                        # Extract API server URL from cluster-info output
                        for line in cluster_info_result.stdout.split('\n'):
                            if 'Kubernetes control plane' in line or 'Kubernetes master' in line:
                                # Extract URL from line like: "Kubernetes control plane is running at https://192.168.49.2:8443"
                                parts = line.split('at')
                                if len(parts) > 1:
                                    api_url = parts[1].strip()
                                    break

                    active_profile = {
                        "name": profile_name,
                        "status": host_status,
                        "api_url": api_url,
                    }
                    break

        if active_profile:
            return {
                "success": True,
                "profile": active_profile,
                "message": f"Active minikube profile: {active_profile['name']}",
            }
        else:
            return {
                "success": False,
                "profile": None,
                "message": "No running minikube cluster found",
            }

    except Exception as e:
        return {
            "success": False,
            "profile": None,
            "message": f"Error getting active minikube profile: {str(e)}",
        }


@app.post("/api/minikube/verify-cluster")
async def verify_minikube_cluster(request: dict):
    """Verify if a Minikube cluster exists and is accessible"""
    cluster_name = request.get("cluster_name", "").strip()

    if not cluster_name:
        return {
            "exists": False,
            "accessible": False,
            "message": "Cluster name is required",
            "suggestion": "Please provide a valid Minikube profile name",
        }

    try:
        # Check if Minikube is installed
        minikube_check = subprocess.run(
            ["minikube", "version"], capture_output=True, text=True, timeout=30
        )

        if minikube_check.returncode != 0:
            return {
                "exists": False,
                "accessible": False,
                "message": "Minikube is not installed",
                "suggestion": "Install Minikube first: brew install minikube",
                "cluster_name": cluster_name,
            }

        # Check if profile exists
        status_result = subprocess.run(
            ["minikube", "status", "-p", cluster_name, "-o", "json"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if status_result.returncode != 0:
            return {
                "exists": False,
                "accessible": False,
                "message": f"Minikube cluster '{cluster_name}' does not exist",
                "suggestion": f"Create the cluster with: minikube start --profile {cluster_name}",
                "cluster_name": cluster_name,
            }

        # Parse status to check if running
        import json

        try:
            status_data = json.loads(status_result.stdout)
            is_running = status_data.get("Host", "") == "Running"

            if not is_running:
                return {
                    "exists": True,
                    "accessible": False,
                    "message": f"Minikube cluster '{cluster_name}' exists but is not running",
                    "suggestion": f"Start the cluster with: minikube start --profile {cluster_name}",
                    "cluster_name": cluster_name,
                }

            # Test kubectl access
            context_name = cluster_name
            kubectl_test = subprocess.run(
                ["kubectl", "cluster-info", "--context", context_name],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if kubectl_test.returncode == 0:
                # Get cluster version using JSON output
                version_result = subprocess.run(
                    ["kubectl", "version", "-o", "json", "--context", context_name],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                # Extract server version from JSON
                version = "v1.32.0"  # Default fallback
                if version_result.returncode == 0:
                    try:
                        import json as json_module

                        version_data = json_module.loads(version_result.stdout)
                        version = version_data.get("serverVersion", {}).get("gitVersion", "v1.32.0")
                    except:
                        version = "v1.32.0"

                # Get driver from minikube status
                driver = status_data.get("Driver", "N/A")

                cluster_info = {
                    "name": cluster_name,
                    "namespace": "ns-rosa-hcp",  # Default namespace for ROSA HCP resources
                    "status": "Running",  # Capitalized to match Minikube convention
                    "driver": driver,
                    "kubernetesVersion": version,
                    "version": version,  # Keep for backward compatibility
                }

                # Fetch creationTimestamp for key components
                component_timestamps = {}

                # Get namespace timestamp (for Minikube Cluster)
                namespace_timestamp = subprocess.run(
                    [
                        "kubectl",
                        "get",
                        "namespace",
                        "ns-rosa-hcp",
                        "-ojson",
                        "--context",
                        context_name,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if namespace_timestamp.returncode == 0:
                    try:
                        import json

                        ns_data = json.loads(namespace_timestamp.stdout)
                        component_timestamps["namespace"] = ns_data.get("metadata", {}).get(
                            "creationTimestamp", ""
                        )
                    except:
                        pass

                # Get cert-manager deployment timestamp
                cert_manager_timestamp = subprocess.run(
                    [
                        "kubectl",
                        "get",
                        "deployment",
                        "cert-manager",
                        "-n",
                        "cert-manager",
                        "-ojson",
                        "--context",
                        context_name,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if cert_manager_timestamp.returncode == 0:
                    try:
                        import json

                        cm_data = json.loads(cert_manager_timestamp.stdout)
                        component_timestamps["cert-manager"] = cm_data.get("metadata", {}).get(
                            "creationTimestamp", ""
                        )
                    except:
                        pass

                # Get CAPI controller timestamp
                capi_timestamp = subprocess.run(
                    [
                        "kubectl",
                        "get",
                        "deployment",
                        "capi-controller-manager",
                        "-n",
                        "capi-system",
                        "-ojson",
                        "--context",
                        context_name,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if capi_timestamp.returncode == 0:
                    try:
                        import json

                        capi_data = json.loads(capi_timestamp.stdout)
                        component_timestamps["capi-controller"] = capi_data.get("metadata", {}).get(
                            "creationTimestamp", ""
                        )
                    except:
                        pass

                # Get CAPA controller timestamp
                capa_timestamp = subprocess.run(
                    [
                        "kubectl",
                        "get",
                        "deployment",
                        "capa-controller-manager",
                        "-n",
                        "capa-system",
                        "-ojson",
                        "--context",
                        context_name,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if capa_timestamp.returncode == 0:
                    try:
                        import json

                        capa_data = json.loads(capa_timestamp.stdout)
                        component_timestamps["capa-controller"] = capa_data.get("metadata", {}).get(
                            "creationTimestamp", ""
                        )
                    except:
                        pass

                # Get ROSA CRD timestamp
                rosa_crd_timestamp = subprocess.run(
                    [
                        "kubectl",
                        "get",
                        "crd",
                        "rosacontrolplanes.controlplane.cluster.x-k8s.io",
                        "-ojson",
                        "--context",
                        context_name,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if rosa_crd_timestamp.returncode == 0:
                    try:
                        import json

                        crd_data = json.loads(rosa_crd_timestamp.stdout)
                        component_timestamps["rosa-crd"] = crd_data.get("metadata", {}).get(
                            "creationTimestamp", ""
                        )
                    except:
                        pass

                cluster_info["component_timestamps"] = component_timestamps

                # Check for CAPI/CAPA components
                components = {"checks_passed": 0, "warnings": 0, "failed": 0, "details": []}

                # Check AWS credentials secret
                aws_creds_check = subprocess.run(
                    [
                        "kubectl",
                        "get",
                        "secret",
                        "capa-manager-bootstrap-credentials",
                        "-n",
                        "capa-system",
                        "--context",
                        context_name,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if aws_creds_check.returncode == 0:
                    components["checks_passed"] += 1
                    components["details"].append(
                        {
                            "name": "AWS Credentials",
                            "status": "configured",
                            "message": "AWS credentials secret found",
                        }
                    )
                else:
                    components["warnings"] += 1
                    components["details"].append(
                        {
                            "name": "AWS Credentials",
                            "status": "not_configured",
                            "message": "AWS credentials secret not found in capa-system namespace",
                        }
                    )

                # Check OCM Client Secret
                ocm_secret_check = subprocess.run(
                    [
                        "kubectl",
                        "get",
                        "secret",
                        "rosa-creds-secret",
                        "-n",
                        "ns-rosa-hcp",
                        "--context",
                        context_name,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if ocm_secret_check.returncode == 0:
                    components["checks_passed"] += 1
                    components["details"].append(
                        {
                            "name": "OCM Client Secret",
                            "status": "configured",
                            "message": "ROSA credentials secret found",
                        }
                    )
                else:
                    components["failed"] += 1
                    components["details"].append(
                        {
                            "name": "OCM Client Secret",
                            "status": "missing",
                            "message": "ROSA credentials secret not found in ns-rosa-hcp namespace",
                        }
                    )

                cluster_info["components"] = components
                install_method = "clusterctl"

                return {
                    "exists": True,
                    "accessible": True,
                    "message": f"Minikube cluster '{cluster_name}' is running and accessible",
                    "cluster_name": cluster_name,
                    "context_name": context_name,
                    "cluster_info": cluster_info,
                    "install_method": install_method,
                    "suggestion": f"You can use this cluster for testing. Update your vars/user_vars.yml with the cluster details.",
                }
            else:
                return {
                    "exists": True,
                    "accessible": False,
                    "message": f"Minikube cluster '{cluster_name}' is running but kubectl access failed",
                    "suggestion": f"Try: minikube delete --profile {cluster_name} && minikube start --profile {cluster_name}",
                    "cluster_name": cluster_name,
                    "error_details": kubectl_test.stderr,
                }

        except json.JSONDecodeError:
            return {
                "exists": False,
                "accessible": False,
                "message": "Failed to parse minikube status",
                "suggestion": "Check minikube installation",
                "cluster_name": cluster_name,
            }

    except subprocess.TimeoutExpired:
        return {
            "exists": False,
            "accessible": False,
            "message": "Minikube command timed out",
            "suggestion": "Check Minikube installation and system performance",
            "cluster_name": cluster_name,
        }
    except Exception as e:
        return {
            "exists": False,
            "accessible": False,
            "message": f"Error checking Minikube cluster: {str(e)}",
            "suggestion": "Check Minikube installation and permissions",
            "cluster_name": cluster_name,
        }


@app.post("/api/minikube/initialize-capi")
async def initialize_minikube_capi(request: Request, background_tasks: BackgroundTasks):
    """Initialize Minikube cluster with CAPI/CAPA support"""
    try:
        body = await request.json()
        cluster_name = body.get("cluster_name", "").strip()
        install_method = body.get("install_method", "clusterctl").strip().lower()
        custom_capa_image = body.get("custom_capa_image", None)

        if not cluster_name:
            return {
                "success": False,
                "message": "Cluster name is required",
            }

        # Validate install method
        if install_method != "clusterctl":
            return {
                "success": False,
                "message": f"Invalid install method: {install_method}. Must be 'clusterctl'",
            }

        # Validate custom image config if provided
        if custom_capa_image:
            if not isinstance(custom_capa_image, dict):
                return {
                    "success": False,
                    "message": "custom_capa_image must be an object with repository and tag",
                }
            if not custom_capa_image.get("repository") or not custom_capa_image.get("tag"):
                return {
                    "success": False,
                    "message": "custom_capa_image requires both repository and tag",
                }

        # Determine which task file to use
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        playbook_path = os.path.join(project_root, "tasks", "clusterctl_install_capi.yml")

        if not os.path.exists(playbook_path):
            return {
                "success": False,
                "message": f"Initialization playbook not found at: {playbook_path}",
                "suggestion": "Ensure clusterctl installation task file exists",
            }

        # Generate unique job ID
        job_id = str(uuid.uuid4())
        # Build description with custom image info
        action = "Reconfigure" if custom_capa_image else "Configure"
        description = f"{action} CAPI/CAPA on Minikube: {cluster_name} (clusterctl)"
        if custom_capa_image:
            description += (
                f" [Custom Image: {custom_capa_image['repository']}:{custom_capa_image['tag']}]"
            )

        # Create job entry
        jobs[job_id] = {
            "id": job_id,
            "status": "pending",
            "progress": 0,
            "message": f"{action}ing CAPI/CAPA on Minikube cluster '{cluster_name}' using clusterctl",
            "started_at": datetime.now(),
            "logs": [],
            "environment": "minikube",
            "description": description,
            "custom_capa_image": custom_capa_image,
        }

        # Run configuration in background (use asyncio.to_thread to avoid blocking event loop)
        asyncio.create_task(asyncio.to_thread(
            run_minikube_init_playbook,
            playbook_path,
            cluster_name,
            job_id,
            custom_capa_image,
        ))

        return {
            "success": True,
            "job_id": job_id,
            "message": f"CAPI/CAPA configuration started for cluster '{cluster_name}' using clusterctl",
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Error starting initialization: {str(e)}",
            "suggestion": "Check the playbook and cluster configuration",
        }


def _run_minikube_create(cluster_name: str, job_id: str):
    """Background task to create a minikube cluster"""
    try:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["logs"].append(f"Starting minikube cluster '{cluster_name}'...")
        jobs[job_id]["logs"].append(f"Running: minikube start --profile {cluster_name} --cpus=2 --memory=4096")
        jobs[job_id]["logs"].append("")

        # Run minikube start with real-time output capture
        process = subprocess.Popen(
            ["minikube", "start", "--profile", cluster_name, "--cpus=2", "--memory=4096"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        for line in iter(process.stdout.readline, ''):
            line_text = line.rstrip()
            if line_text:
                jobs[job_id]["logs"].append(line_text)

        process.wait(timeout=300)

        if process.returncode != 0:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["message"] = f"Failed to create cluster '{cluster_name}'"
            jobs[job_id]["logs"].append("")
            jobs[job_id]["logs"].append(f"Process exited with code {process.returncode}")
            # Clear cache so UI refreshes
            minikube_clusters_cache["timestamp"] = 0
            return

        jobs[job_id]["logs"].append("")
        jobs[job_id]["logs"].append("Verifying cluster...")

        # Verify the cluster
        kubectl_test = subprocess.run(
            ["kubectl", "cluster-info", "--context", cluster_name],
            capture_output=True, text=True, timeout=30,
        )

        if kubectl_test.returncode == 0:
            jobs[job_id]["logs"].append("Cluster verified successfully!")
        else:
            jobs[job_id]["logs"].append("Warning: Cluster created but kubectl verification returned an error. It may need a moment to initialize.")

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["message"] = f"Cluster '{cluster_name}' created successfully"
        jobs[job_id]["completed_at"] = datetime.now()
        # Clear cache so cluster list refreshes
        minikube_clusters_cache["timestamp"] = 0

    except subprocess.TimeoutExpired:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["message"] = "Cluster creation timed out after 5 minutes"
        jobs[job_id]["logs"].append("ERROR: Timed out waiting for minikube start")
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["message"] = f"Error: {str(e)}"
        jobs[job_id]["logs"].append(f"ERROR: {str(e)}")


@app.post("/api/minikube/create-cluster")
async def create_minikube_cluster(request: Request, background_tasks: BackgroundTasks):
    """Create a new Minikube cluster (async with job tracking)"""
    try:
        body = await request.json()
        cluster_name = body.get("cluster_name", "").strip()

        if not cluster_name:
            return {
                "success": False,
                "message": "Cluster name is required",
                "suggestion": "Provide a valid cluster name",
            }

        # Validate cluster name
        import re

        name_pattern = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
        if not name_pattern.match(cluster_name):
            return {
                "success": False,
                "message": "Invalid cluster name format",
                "suggestion": "Use lowercase letters, numbers, and hyphens only",
            }

        # Check if Minikube is installed
        minikube_check = subprocess.run(
            ["minikube", "version"], capture_output=True, text=True, timeout=30
        )

        if minikube_check.returncode != 0:
            return {
                "success": False,
                "message": "Minikube is not installed",
                "suggestion": "Install Minikube first: brew install minikube",
            }

        # Check if cluster already exists
        status_result = subprocess.run(
            ["minikube", "status", "-p", cluster_name], capture_output=True, text=True, timeout=30
        )

        if status_result.returncode == 0:
            return {
                "success": False,
                "message": f"Cluster '{cluster_name}' already exists",
                "suggestion": "Choose a different name or delete the existing cluster",
            }

        # Create job for tracking
        job_id = str(uuid.uuid4())
        jobs[job_id] = {
            "id": job_id,
            "type": "minikube-create",
            "cluster_name": cluster_name,
            "status": "pending",
            "message": f"Creating cluster '{cluster_name}'...",
            "created_at": datetime.now(),
            "logs": [],
        }

        # Start creation in background (use asyncio.to_thread to avoid blocking event loop)
        asyncio.create_task(asyncio.to_thread(_run_minikube_create, cluster_name, job_id))

        return {
            "success": True,
            "job_id": job_id,
            "message": f"Cluster '{cluster_name}' creation started",
            "cluster_name": cluster_name,
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Error creating Minikube cluster: {str(e)}",
            "suggestion": "Check Minikube installation and Podman daemon status",
        }


@app.post("/api/minikube/delete-cluster")
async def delete_minikube_cluster(request: Request):
    """Delete a Minikube cluster"""
    try:
        body = await request.json()
        cluster_name = body.get("cluster_name", "").strip()

        if not cluster_name:
            return {
                "success": False,
                "message": "Cluster name is required",
            }

        # Delete the cluster (minikube delete will handle non-existent clusters)
        delete_result = subprocess.run(
            ["minikube", "delete", "--profile", cluster_name],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if delete_result.returncode == 0:
            # Clear cache to force refresh
            minikube_clusters_cache["timestamp"] = 0

            return {
                "success": True,
                "message": f"Cluster '{cluster_name}' deleted successfully",
                "output": delete_result.stdout,
            }
        else:
            return {
                "success": False,
                "message": f"Failed to delete cluster: {delete_result.stderr}",
            }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "message": "Cluster deletion timed out",
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error deleting Minikube cluster: {str(e)}",
        }


@app.post("/api/minikube/execute-command")
async def execute_minikube_command(request: Request):
    """Execute a kubectl command in the context of a Minikube cluster"""
    try:
        body = await request.json()
        cluster_name = body.get("cluster_name", "").strip()
        command = body.get("command", "").strip()

        if not cluster_name:
            return {
                "success": False,
                "error": "Cluster name is required",
                "output": "",
            }

        if not command:
            return {
                "success": False,
                "error": "Command is required",
                "output": "",
            }

        # Security check: block dangerous commands
        dangerous_patterns = [
            r"\brm\s+-rf\s+/",
            r"\bmkfs\b",
            r"\bdd\b.*of=/dev",
            r"\bshutdown\b",
            r"\breboot\b",
            r"\bkillall\b",
            r":\(\)",
        ]

        import re

        for pattern in dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return {
                    "success": False,
                    "error": "This command is not allowed for security reasons",
                    "output": "",
                }

        # Use bash login shell with alias expansion
        user_shell = os.environ.get("SHELL", "/bin/bash")

        wrapper_command = f"""
            # Source profile files silently
            [ -f ~/.profile ] && source ~/.profile 2>/dev/null
            [ -f ~/.bashrc ] && source ~/.bashrc 2>/dev/null
            [ -f ~/.bash_profile ] && source ~/.bash_profile 2>/dev/null
            # Enable alias expansion
            shopt -s expand_aliases 2>/dev/null || true
            # Set kubectl context
            export KUBECONFIG=~/.kube/config
            # Run the actual command
            {command}
        """

        result = subprocess.run(
            [user_shell, "-c", wrapper_command],
            capture_output=True,
            text=True,
            timeout=60,
        )

        return {
            "success": result.returncode == 0,
            "output": result.stdout if result.stdout else result.stderr,
            "exit_code": result.returncode,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Command execution timed out (60s limit)",
            "output": "",
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Error executing command: {str(e)}",
            "output": "",
        }


@app.post("/api/ocp/execute-command")
async def execute_ocp_command(request: Request):
    """Execute a command in the context of the OpenShift/MCE cluster"""
    try:
        body = await request.json()
        command = body.get("command", "").strip()

        if not command:
            return {
                "success": False,
                "error": "Command is required",
                "output": "",
            }

        # Security check: block dangerous commands
        dangerous_patterns = [
            r"\brm\s+-rf\s+/",
            r"\bmkfs\b",
            r"\bdd\b.*of=/dev",
            r"\bshutdown\b",
            r"\breboot\b",
            r"\bkillall\b",
            r":\(\)",
        ]

        import re

        for pattern in dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return {
                    "success": False,
                    "error": "This command is not allowed for security reasons",
                    "output": "",
                }

        # Use bash login shell with alias expansion
        user_shell = os.environ.get("SHELL", "/bin/bash")

        # Get project root (automation-capi directory)
        project_root = os.environ.get("AUTOMATION_PATH") or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

        wrapper_command = f"""
            # Source profile files silently
            [ -f ~/.profile ] && source ~/.profile 2>/dev/null
            [ -f ~/.bashrc ] && source ~/.bashrc 2>/dev/null
            [ -f ~/.bash_profile ] && source ~/.bash_profile 2>/dev/null
            # Enable alias expansion
            shopt -s expand_aliases 2>/dev/null || true
            # Change to automation-capi project directory
            cd "{project_root}"
            # Run the actual command (oc commands use current cluster context)
            {command}
        """

        result = subprocess.run(
            [user_shell, "-c", wrapper_command],
            capture_output=True,
            text=True,
            timeout=60,
        )

        return {
            "success": result.returncode == 0,
            "output": result.stdout if result.stdout else result.stderr,
            "exit_code": result.returncode,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Command execution timed out (60s limit)",
            "output": "",
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Error executing command: {str(e)}",
            "output": "",
        }


# Re-use the same get-active-resources and get-resource-detail endpoints for Minikube
# since they work with kubectl and are provider-agnostic
@app.post("/api/minikube/get-active-resources")
async def get_minikube_active_resources(request: Request):
    """Get active CAPI/ROSA resources from the Minikube cluster"""
    # This endpoint is identical to Kind's version, just uses Minikube context
    body = await request.json()
    cluster_name = body.get("cluster_name", "").strip()

    # For Minikube, the context name is just the cluster name (not "kind-{name}")
    # So we temporarily modify the request to work with the shared logic
    modified_request = {
        "cluster_name": cluster_name,
        "namespace": body.get("namespace", "ns-rosa-hcp"),
    }

    # Call the shared implementation (we'll extract it to a helper function)
    return await _get_active_resources_impl(cluster_name, body.get("namespace", "ns-rosa-hcp"))


async def _get_active_resources_impl(cluster_name: str, namespace: str = "ns-rosa-hcp"):
    """
    Optimized implementation for getting active resources.
    Uses a single kubectl command to fetch all CAPI/CAPA resources at once,
    dramatically reducing API round trips from 17+ to 1.
    """
    try:
        if not cluster_name:
            return {"success": False, "message": "Cluster name is required", "resources": []}

        resources = []

        def calculate_age(creation_timestamp):
            from datetime import datetime, timezone

            try:
                created = datetime.fromisoformat(creation_timestamp.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                delta = now - created

                days = delta.days
                hours, remainder = divmod(delta.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)

                if days > 0:
                    return f"{days}d{hours}h"
                elif hours > 0:
                    return f"{hours}h{minutes}m"
                elif minutes > 0:
                    return f"{minutes}m{seconds}s"
                else:
                    return f"{seconds}s"
            except Exception:
                return "unknown"

        # OPTIMIZED: Fetch all CAPI/CAPA resources in one command
        # This replaces 17+ sequential kubectl calls with a single command
        # Skips: secrets, awsmanagedmachinepool, machinedeployment, machine, awsmachine (low-level resources)
        resource_types = [
            "rosacontrolplane",
            "rosanetwork",
            "rosaroleconfig",
            "rosamachinepool",
            "clusters.cluster.x-k8s.io",
            "machinepool",
        ]

        try:
            result = subprocess.run(
                ["kubectl", "get", ",".join(resource_types), "-n", namespace, "--context", cluster_name, "-o", "json"],
                capture_output=True,
                text=True,
                timeout=30,  # Increased timeout for bulk fetch
            )

            if result.returncode == 0:
                import json as json_module
                data = json_module.loads(result.stdout)

                for item in data.get("items", []):
                    metadata = item.get("metadata", {})
                    spec = item.get("spec", {})
                    status = item.get("status", {})
                    kind = item.get("kind", "unknown")

                    # Determine resource status based on kind
                    resource_status = "Unknown"
                    if kind == "ROSAControlPlane":
                        # Check for ready status
                        if status.get("ready") == True or status.get("ready") == "true":
                            resource_status = "Ready"
                        else:
                            conditions = status.get("conditions", [])
                            for condition in conditions:
                                if condition.get("status") == "True" and condition.get("type") in ["Ready", "ROSAControlPlaneReady"]:
                                    resource_status = "Ready"
                                    break
                            if resource_status != "Ready":
                                resource_status = "Provisioning"
                    elif kind in ["ROSANetwork", "RosaRoleConfig"]:
                        if status.get("ready") == True or status.get("ready") == "true":
                            resource_status = "Ready"
                        else:
                            resource_status = "Provisioning"
                    elif kind == "Cluster":
                        resource_status = "Ready" if status.get("phase") == "Provisioned" else status.get("phase", "Active")
                    elif kind in ["MachinePool", "RosaMachinePool", "MachineDeployment", "Machine"]:
                        resource_status = status.get("phase", "Active")
                    else:
                        resource_status = "Active"

                    resources.append({
                        "type": kind,
                        "name": metadata.get("name", "unknown"),
                        "namespace": namespace,
                        "version": spec.get("version", ""),
                        "status": resource_status,
                        "age": calculate_age(metadata.get("creationTimestamp", "")),
                    })
        except subprocess.TimeoutExpired:
            print(f"Timeout fetching resources for {cluster_name}")
        except Exception as e:
            print(f"Error fetching resources: {str(e)}")

        # Fetch ns-rosa-hcp namespace
        try:
            result = subprocess.run(
                ["kubectl", "get", "namespace", namespace, "--context", cluster_name, "-o", "json"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                import json as json_module

                data = json_module.loads(result.stdout)
                metadata = data.get("metadata", {})
                status = data.get("status", {})
                phase = status.get("phase", "Active")

                # Fetch YAML for namespace
                yaml_result = subprocess.run(
                    [
                        "kubectl",
                        "get",
                        "namespace",
                        namespace,
                        "--context",
                        cluster_name,
                        "-o",
                        "yaml",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                yaml_content = yaml_result.stdout if yaml_result.returncode == 0 else ""

                resources.append(
                    {
                        "type": "Namespace",
                        "name": metadata.get("name", "unknown"),
                        "namespace": metadata.get(
                            "name", "unknown"
                        ),  # Namespace resource shows its own name
                        "version": "",
                        "status": phase,
                        "age": calculate_age(metadata.get("creationTimestamp", "")),
                        "yaml": yaml_content,
                    }
                )
        except Exception:
            pass

        # Fetch AWSClusterControllerIdentity (infrastructure resource)
        try:
            result = subprocess.run(
                [
                    "kubectl",
                    "get",
                    "awsclustercontrolleridentity",
                    "--context",
                    cluster_name,
                    "-o",
                    "json",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                import json as json_module

                data = json_module.loads(result.stdout)
                for item in data.get("items", []):
                    metadata = item.get("metadata", {})
                    identity_name = metadata.get("name", "unknown")

                    # Fetch YAML for this identity
                    yaml_result = subprocess.run(
                        [
                            "kubectl",
                            "get",
                            "awsclustercontrolleridentity",
                            identity_name,
                            "--context",
                            cluster_name,
                            "-o",
                            "yaml",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    yaml_content = yaml_result.stdout if yaml_result.returncode == 0 else ""

                    resources.append(
                        {
                            "type": "AWSClusterControllerIdentity",
                            "name": identity_name,
                            "namespace": metadata.get(
                                "namespace", "default"
                            ),  # Cluster-scoped resource
                            "version": "",
                            "status": "Configured",
                            "age": calculate_age(metadata.get("creationTimestamp", "")),
                            "yaml": yaml_content,
                        }
                    )
        except Exception:
            pass

        # Fetch secrets only for the requested namespace to avoid duplicates
        # when multiple namespaces are fetched in parallel
        secret_fetches = []
        if namespace == "capa-system":
            secret_fetches = [
                ("rosa-creds-secret", "capa-system", "Secret (ROSA Creds)"),
                ("capa-manager-bootstrap-credentials", "capa-system", "Secret (AWS Creds)"),
            ]
        elif namespace != "default":
            # For other namespaces (e.g. ns-rosa-hcp), only fetch rosa-creds-secret in that namespace
            secret_fetches = [
                ("rosa-creds-secret", namespace, "Secret (ROSA Creds)"),
            ]

        for secret_name, secret_ns, secret_type in secret_fetches:
            try:
                result = subprocess.run(
                    ["kubectl", "get", "secret", secret_name, "-n", secret_ns,
                     "--context", cluster_name, "-o", "json"],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    import json as json_module
                    data = json_module.loads(result.stdout)
                    metadata = data.get("metadata", {})
                    resources.append({
                        "type": secret_type,
                        "name": metadata.get("name", "unknown"),
                        "namespace": secret_ns,
                        "version": "",
                        "status": "Configured",
                        "age": calculate_age(metadata.get("creationTimestamp", "")),
                    })
            except Exception:
                pass

        # Fetch CAPI Clusters
        try:
            result = subprocess.run(
                [
                    "kubectl",
                    "get",
                    "clusters.cluster.x-k8s.io",
                    "-n",
                    namespace,
                    "--context",
                    cluster_name,
                    "-o",
                    "json",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                import json as json_module

                data = json_module.loads(result.stdout)
                for item in data.get("items", []):
                    metadata = item.get("metadata", {})
                    spec = item.get("spec", {})
                    status = item.get("status", {})
                    cluster_name_item = metadata.get("name", "unknown")

                    # Fetch YAML for this cluster
                    yaml_result = subprocess.run(
                        [
                            "kubectl",
                            "get",
                            "clusters.cluster.x-k8s.io",
                            cluster_name_item,
                            "-n",
                            namespace,
                            "--context",
                            cluster_name,
                            "-o",
                            "yaml",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    yaml_content = yaml_result.stdout if yaml_result.returncode == 0 else ""

                    resources.append(
                        {
                            "type": "CAPI Clusters",
                            "name": cluster_name_item,
                            "namespace": namespace,
                            "version": spec.get("topology", {}).get("version", "v1.5.3"),
                            "status": (
                                "Ready"
                                if status.get("phase") == "Provisioned"
                                else status.get("phase", "Active")
                            ),
                            "age": calculate_age(metadata.get("creationTimestamp", "")),
                            "yaml": yaml_content,
                        }
                    )
        except Exception:
            pass

        # Fetch ROSACluster
        try:
            result = subprocess.run(
                [
                    "kubectl",
                    "get",
                    "rosacluster",
                    "-n",
                    namespace,
                    "--context",
                    cluster_name,
                    "-o",
                    "json",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                import json as json_module

                data = json_module.loads(result.stdout)
                for item in data.get("items", []):
                    metadata = item.get("metadata", {})
                    spec = item.get("spec", {})
                    status = item.get("status", {})
                    rosa_cluster_name = metadata.get("name", "unknown")

                    # Check for ready status - could be in status.ready field or in conditions
                    is_ready = False

                    # First check if there's a direct ready field
                    if status.get("ready") == True or status.get("ready") == "true":
                        is_ready = True
                    else:
                        # Check conditions for various ready condition types
                        conditions = status.get("conditions", [])
                        for condition in conditions:
                            condition_type = condition.get("type", "")
                            # Check for various possible ready condition types
                            if condition.get("status") == "True" and (
                                condition_type == "Ready"
                                or condition_type == "ROSAClusterReady"
                                or condition_type == "RosaClusterReady"
                            ):
                                is_ready = True
                                break

                    # Fetch YAML for this ROSA cluster
                    yaml_result = subprocess.run(
                        [
                            "kubectl",
                            "get",
                            "rosacluster",
                            rosa_cluster_name,
                            "-n",
                            namespace,
                            "--context",
                            cluster_name,
                            "-o",
                            "yaml",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    yaml_content = yaml_result.stdout if yaml_result.returncode == 0 else ""

                    resources.append(
                        {
                            "type": "ROSACluster",
                            "name": rosa_cluster_name,
                            "namespace": namespace,
                            "version": spec.get("version", "v4.20"),
                            "status": "Ready" if is_ready else "Provisioning",
                            "age": calculate_age(metadata.get("creationTimestamp", "")),
                            "yaml": yaml_content,
                        }
                    )
        except Exception:
            pass

        # Fetch RosaControlPlane
        try:
            result = subprocess.run(
                [
                    "kubectl",
                    "get",
                    "rosacontrolplane",
                    "-n",
                    namespace,
                    "--context",
                    cluster_name,
                    "-o",
                    "json",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                import json as json_module

                data = json_module.loads(result.stdout)
                for item in data.get("items", []):
                    metadata = item.get("metadata", {})
                    spec = item.get("spec", {})
                    status = item.get("status", {})
                    rcp_name = metadata.get("name", "unknown")

                    # Check for ready status - could be in status.ready field or in conditions
                    is_ready = False

                    # First check if there's a direct ready field
                    if status.get("ready") == True or status.get("ready") == "true":
                        is_ready = True
                    else:
                        # Check conditions for various ready condition types
                        conditions = status.get("conditions", [])
                        for condition in conditions:
                            condition_type = condition.get("type", "")
                            # Check for various possible ready condition types
                            if condition.get("status") == "True" and (
                                condition_type == "Ready"
                                or condition_type == "ROSAControlPlaneReady"
                                or condition_type == "RosaControlPlaneReady"
                            ):
                                is_ready = True
                                break

                    # Fetch YAML for this RosaControlPlane
                    yaml_result = subprocess.run(
                        [
                            "kubectl",
                            "get",
                            "rosacontrolplane",
                            rcp_name,
                            "-n",
                            namespace,
                            "--context",
                            cluster_name,
                            "-o",
                            "yaml",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    yaml_content = yaml_result.stdout if yaml_result.returncode == 0 else ""

                    resources.append(
                        {
                            "type": "RosaControlPlane",
                            "name": rcp_name,
                            "namespace": metadata.get("namespace", namespace),
                            "version": spec.get("version", "v4.20"),
                            "status": "Ready" if is_ready else "Provisioning",
                            "age": calculate_age(metadata.get("creationTimestamp", "")),
                            "yaml": yaml_content,
                        }
                    )
        except Exception:
            pass

        # Fetch RosaNetwork
        try:
            result = subprocess.run(
                [
                    "kubectl",
                    "get",
                    "rosanetwork",
                    "-n",
                    namespace,
                    "--context",
                    cluster_name,
                    "-o",
                    "json",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                import json as json_module

                data = json_module.loads(result.stdout)
                for item in data.get("items", []):
                    metadata = item.get("metadata", {})
                    spec = item.get("spec", {})
                    status = item.get("status", {})
                    network_name = metadata.get("name", "unknown")

                    # Check conditions for RosaNetwork ready state
                    # Could be ROSANetworkReady, RosaNetworkReady, or just Ready
                    is_ready = False
                    conditions = status.get("conditions", [])
                    for condition in conditions:
                        condition_type = condition.get("type", "")
                        # Check for various possible ready condition types
                        if condition.get("status") == "True" and (
                            condition_type == "ROSANetworkReady"
                            or condition_type == "RosaNetworkReady"
                            or condition_type == "Ready"
                        ):
                            is_ready = True
                            break

                    # Fetch YAML for this RosaNetwork
                    yaml_result = subprocess.run(
                        [
                            "kubectl",
                            "get",
                            "rosanetwork",
                            network_name,
                            "-n",
                            namespace,
                            "--context",
                            cluster_name,
                            "-o",
                            "yaml",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    yaml_content = yaml_result.stdout if yaml_result.returncode == 0 else ""

                    resources.append(
                        {
                            "type": "RosaNetwork",
                            "name": network_name,
                            "namespace": metadata.get("namespace", namespace),
                            "version": spec.get("version", "v4.20"),
                            "status": "Ready" if is_ready else "Configuring",
                            "age": calculate_age(metadata.get("creationTimestamp", "")),
                            "yaml": yaml_content,
                        }
                    )
        except Exception:
            pass

        # Fetch RosaRoleConfig
        try:
            result = subprocess.run(
                [
                    "kubectl",
                    "get",
                    "rosaroleconfig",
                    "-n",
                    namespace,
                    "--context",
                    cluster_name,
                    "-o",
                    "json",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                import json as json_module

                data = json_module.loads(result.stdout)
                for item in data.get("items", []):
                    metadata = item.get("metadata", {})
                    spec = item.get("spec", {})
                    status = item.get("status", {})
                    role_config_name = metadata.get("name", "unknown")

                    # Check conditions for RosaRoleConfig ready state
                    # Could be ROSARoleConfigReady, RosaRoleConfigReady, or just Ready
                    is_ready = False
                    conditions = status.get("conditions", [])
                    for condition in conditions:
                        condition_type = condition.get("type", "")
                        # Check for various possible ready condition types
                        if condition.get("status") == "True" and (
                            condition_type == "ROSARoleConfigReady"
                            or condition_type == "RosaRoleConfigReady"
                            or condition_type == "Ready"
                        ):
                            is_ready = True
                            break

                    # Fetch YAML for this RosaRoleConfig
                    yaml_result = subprocess.run(
                        [
                            "kubectl",
                            "get",
                            "rosaroleconfig",
                            role_config_name,
                            "-n",
                            namespace,
                            "--context",
                            cluster_name,
                            "-o",
                            "yaml",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    yaml_content = yaml_result.stdout if yaml_result.returncode == 0 else ""

                    resources.append(
                        {
                            "type": "RosaRoleConfig",
                            "name": role_config_name,
                            "namespace": metadata.get("namespace", namespace),
                            "version": spec.get("version", "v4.20"),
                            "status": "Ready" if is_ready else "Configuring",
                            "age": calculate_age(metadata.get("creationTimestamp", "")),
                            "yaml": yaml_content,
                        }
                    )
        except Exception:
            pass

        return {
            "success": True,
            "resources": resources,
            "message": f"Found {len(resources)} active resource(s)",
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Error fetching active resources: {str(e)}",
            "resources": [],
        }


@app.post("/api/minikube/get-resource-detail")
async def get_minikube_resource_detail(request: Request):
    """Get full YAML details of a specific resource from the Minikube cluster"""
    try:
        body = await request.json()
        cluster_name = body.get("cluster_name", "").strip()
        resource_type = body.get("resource_type", "").strip()
        resource_name = body.get("resource_name", "").strip()
        namespace = body.get("namespace", "ns-rosa-hcp").strip()

        if not cluster_name or not resource_type or not resource_name:
            return {
                "success": False,
                "message": "cluster_name, resource_type, and resource_name are required",
                "data": None,
            }

        # For Minikube, context name is just the cluster name (no "kind-" prefix)
        context_name = cluster_name

        # Map friendly resource types to kubectl resource types
        resource_type_map = {
            "CAPI Clusters": "clusters.cluster.x-k8s.io",
            "ROSACluster": "rosacluster",
            "RosaControlPlane": "rosacontrolplane",
            "RosaNetwork": "rosanetwork",
            "RosaRoleConfig": "rosaroleconfig",
            "AWSClusterControllerIdentity": "awsclustercontrolleridentity",
            "Secret (ROSA Creds)": "secret",
            "Secret (AWS Creds)": "secret",
        }

        kubectl_resource_type = resource_type_map.get(resource_type, resource_type.lower())

        # For secrets, extract the actual secret name from the display name
        # e.g., "rosa-creds-secret (capa-system)" -> "rosa-creds-secret"
        if kubectl_resource_type == "secret" and "(" in resource_name:
            # Extract name and namespace from display format
            actual_name = resource_name.split("(")[0].strip()
            # Extract namespace from parentheses if present
            if "(" in resource_name and ")" in resource_name:
                ns_from_name = resource_name.split("(")[1].split(")")[0].strip()
                namespace = ns_from_name
            resource_name = actual_name

        # Fetch the resource details in YAML format
        try:
            # For cluster-scoped resources (like AWSClusterControllerIdentity), don't use namespace
            if kubectl_resource_type == "awsclustercontrolleridentity":
                result = subprocess.run(
                    [
                        "kubectl",
                        "get",
                        kubectl_resource_type,
                        resource_name,
                        "--context",
                        context_name,
                        "-o",
                        "yaml",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            else:
                result = subprocess.run(
                    [
                        "kubectl",
                        "get",
                        kubectl_resource_type,
                        resource_name,
                        "-n",
                        namespace,
                        "--context",
                        context_name,
                        "-o",
                        "yaml",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

            if result.returncode == 0:
                return {
                    "success": True,
                    "data": result.stdout,
                    "resource_type": resource_type,
                    "resource_name": resource_name,
                    "namespace": namespace,
                    "message": f"Successfully fetched {resource_type} '{resource_name}'",
                }
            else:
                return {
                    "success": False,
                    "message": f"Failed to fetch resource: {result.stderr}",
                    "data": None,
                }

        except subprocess.TimeoutExpired:
            return {"success": False, "message": "Request timed out", "data": None}

    except Exception as e:
        return {
            "success": False,
            "message": f"Error fetching resource detail: {str(e)}",
            "data": None,
        }


@app.post("/api/ocp/get-resource-detail")
async def get_ocp_resource_detail(request: Request):
    """Get full YAML details of a specific resource from the OCP/MCE cluster"""
    try:
        body = await request.json()
        resource_type = body.get("resource_type", "").strip()
        resource_name = body.get("resource_name", "").strip()
        namespace = body.get("namespace", "").strip()

        if not resource_type or not resource_name:
            return {
                "success": False,
                "message": "resource_type and resource_name are required",
                "data": None,
            }

        # Map friendly resource types to oc/kubectl resource types
        resource_type_map = {
            "Deployment": "deployment",
            "ClusterManager": "clustermanager",
            "ClusterRoleBinding": "clusterrolebinding",
            "Secret": "secret",
            "AWSClusterControllerIdentity": "awsclustercontrolleridentity",
            "Namespace": "namespace",
            # CAPI resources
            "Cluster": "cluster",
            "ROSACluster": "rosacluster",
            "ROSAControlPlane": "rosacontrolplane",
            "ROSANetwork": "rosanetwork",
            "ROSARoleConfig": "rosaroleconfig",
            "ManagedCluster": "managedcluster",
            "MachinePool": "machinepool",
            "ROSAMachinePool": "rosamachinepool",
        }

        oc_resource_type = resource_type_map.get(resource_type, resource_type.lower())

        # Fetch the resource details in YAML format using oc
        try:
            # For cluster-scoped resources, don't use namespace
            cluster_scoped_resources = [
                "clusterrolebinding",
                "awsclustercontrolleridentity",
                "namespace",
                "clustermanager",
                "managedcluster",  # ACM ManagedCluster is cluster-scoped
            ]

            if oc_resource_type in cluster_scoped_resources:
                result = subprocess.run(
                    [
                        "oc",
                        "get",
                        oc_resource_type,
                        resource_name,
                        "-o",
                        "yaml",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            else:
                # Namespace-scoped resources
                if not namespace:
                    return {
                        "success": False,
                        "message": f"Namespace is required for resource type '{resource_type}'",
                        "data": None,
                    }
                result = subprocess.run(
                    [
                        "oc",
                        "get",
                        oc_resource_type,
                        resource_name,
                        "-n",
                        namespace,
                        "-o",
                        "yaml",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

            if result.returncode == 0:
                return {
                    "success": True,
                    "data": result.stdout,
                    "resource_type": resource_type,
                    "resource_name": resource_name,
                    "namespace": namespace,
                    "message": f"Successfully fetched {resource_type} '{resource_name}'",
                }
            else:
                return {
                    "success": False,
                    "message": f"Failed to fetch resource: {result.stderr}",
                    "data": None,
                }

        except subprocess.TimeoutExpired:
            return {"success": False, "message": "Request timed out", "data": None}

    except Exception as e:
        return {
            "success": False,
            "message": f"Error fetching resource detail: {str(e)}",
            "data": None,
        }


@app.get("/api/rosa/last-yaml-path")
async def get_last_rosa_yaml_path():
    """Get the last used YAML file path for ROSA HCP provisioning"""
    return {
        "success": True,
        "path": last_rosa_yaml_path.get("path"),
    }


@app.post("/api/rosa/save-yaml-path")
async def save_rosa_yaml_path(request: Request):
    """Save the YAML file path used for ROSA HCP provisioning"""
    try:
        body = await request.json()
        path = body.get("path")

        if path:
            last_rosa_yaml_path["path"] = path
            return {
                "success": True,
                "message": f"Saved YAML path: {path}",
                "path": path,
            }
        else:
            return {
                "success": False,
                "message": "No path provided",
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error saving YAML path: {str(e)}",
        }


@app.get("/api/provisioning/log-forwarding-config/{cluster_name}")
async def get_log_forwarding_config(cluster_name: str):
    """Get log forwarding configuration for a cluster if it exists"""
    try:
        project_root = os.environ.get("AUTOMATION_PATH") or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

        # Check for config file
        config_file = os.path.join(project_root, f"log-forwarding-config-{cluster_name}.yml")

        if not os.path.exists(config_file):
            return {
                "success": False,
                "found": False,
                "message": f"No log forwarding config found for {cluster_name}",
            }

        # Read and parse the config file
        import yaml

        with open(config_file, "r") as f:
            config_data = yaml.safe_load(f)

        # Extract values
        return {
            "success": True,
            "found": True,
            "cluster_name": cluster_name,
            "cloudwatch_log_group_name": config_data.get("cloudwatch_log_group_name", ""),
            "cloudwatch_log_role_arn": config_data.get("cloudwatch_log_role_arn", ""),
            "s3_log_bucket_name": config_data.get("s3_log_bucket_name", ""),
            "s3_log_bucket_prefix": config_data.get("s3_log_bucket_prefix", ""),
            "message": f"Found log forwarding config for {cluster_name}",
        }
    except Exception as e:
        return {"success": False, "found": False, "message": f"Error reading config: {str(e)}"}


@app.post("/api/provisioning/generate-yaml")
async def generate_provisioning_yaml(request: Request):
    """Generate provisioning YAML without applying it (preview mode) - Direct Jinja2 rendering"""
    try:
        body = await request.json()
        config = body.get("config", {})

        # Extract configuration
        cluster_name = config.get("clusterName")
        openshift_version = config.get("openShiftVersion", "4.20.10")
        create_rosa_network = config.get("createRosaNetwork", True)
        create_rosa_roles = config.get("createRosaRoleConfig", True)
        vpc_cidr_block = config.get("vpcCidrBlock", "10.0.0.0/16")
        availability_zone_count = config.get("availabilityZoneCount", 1)
        role_prefix = config.get("rolePrefix", cluster_name)
        domain_prefix = config.get("domainPrefix", "")
        channel_group = config.get("channelGroup", "")
        channel = config.get("channel", "")
        aws_region = config.get("awsRegion", "us-west-2")

        # Extract node pool configuration
        node_pool_name = config.get("nodePoolName", "")

        # Extract log forwarding configuration
        enable_log_forwarding = config.get("enableLogForwarding", False)
        log_forward_applications = config.get(
            "logForwardApplications", ["application", "infrastructure"]
        )
        log_forward_cloudwatch_role_arn = config.get("logForwardCloudWatchRoleArn", "")
        log_forward_cloudwatch_log_group = config.get("logForwardCloudWatchLogGroup", "")
        log_forward_s3_bucket = config.get("logForwardS3Bucket", "")
        log_forward_s3_prefix = config.get("logForwardS3Prefix", "")

        # Extract FIPS configuration (OpenShift 4.21+ only)
        enable_fips = config.get("fips", False)
        print(f"🔍 [FIPS] Extracted FIPS value: {enable_fips}")

        # Extract manual configuration (for environments without ROSANetwork/ROSARoleConfig CRDs)
        manual_public_subnet = config.get("manualPublicSubnet", "")
        manual_private_subnet = config.get("manualPrivateSubnet", "")
        manual_vpc_id = config.get("manualVpcId", "")
        manual_installer_role_arn = config.get("manualInstallerRoleArn", "")
        manual_support_role_arn = config.get("manualSupportRoleArn", "")
        manual_worker_role_arn = config.get("manualWorkerRoleArn", "")
        manual_control_plane_operator_role_arn = config.get("manualControlPlaneOperatorRoleArn", "")
        manual_kms_provider_role_arn = config.get("manualKmsProviderRoleArn", "")
        manual_ingress_operator_role_arn = config.get("manualIngressOperatorRoleArn", "")
        manual_image_registry_operator_role_arn = config.get(
            "manualImageRegistryOperatorRoleArn", ""
        )
        manual_storage_operator_role_arn = config.get("manualStorageOperatorRoleArn", "")
        manual_network_operator_role_arn = config.get("manualNetworkOperatorRoleArn", "")
        manual_oidc_config_id = config.get("manualOidcConfigId", "")

        if not cluster_name:
            raise HTTPException(status_code=400, detail="cluster_name is required")

        if not domain_prefix:
            raise HTTPException(status_code=400, detail="domain_prefix is required")

        if len(domain_prefix) > 15:
            raise HTTPException(
                status_code=400, detail="domain_prefix must be 15 characters or less"
            )

        print(f"🔍 [PREVIEW-DIRECT] Rendering templates directly for {cluster_name}")

        project_root = os.environ.get("AUTOMATION_PATH") or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        print(f"🔍 [PREVIEW-DIRECT] project_root: {project_root}")
        print(f"🔍 [PREVIEW-DIRECT] AUTOMATION_PATH env: {os.environ.get('AUTOMATION_PATH')}")

        # Parse version to get major.minor
        version_parts = openshift_version.split(".")
        major_minor = (
            f"{version_parts[0]}.{version_parts[1]}"
            if len(version_parts) >= 2
            else openshift_version
        )

        from jinja2 import Environment, FileSystemLoader, select_autoescape
        import re
        from datetime import datetime

        # Custom Jinja2 filters to match Ansible functionality
        def regex_replace(value, pattern, replacement):
            """Ansible-compatible regex_replace filter"""
            return re.sub(pattern, replacement, str(value))

        def ansible_lookup(lookup_type, command):
            """Ansible-compatible lookup filter - simplified for preview mode"""
            if lookup_type == "pipe" and "date" in command:
                # Return current UTC timestamp
                return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            return ""

        yaml_contents = []
        yaml_files = []

        # Template variables
        template_vars = {
            "cluster_name": cluster_name,
            "cluster_name_prefix": cluster_name[:32],  # Truncate to 32 chars for AWS limits
            "rcp_version": openshift_version,
            "aws_account_id": "123456789012",  # Placeholder for preview
            "aws_region": aws_region,
            "capi_namespace": "ns-rosa-hcp",
            "rosa_role_config_name": f"{cluster_name}-roles",
            "rosa_role_prefix": role_prefix,
            "rosa_network_name": f"{cluster_name}-network",
            "network_cidr": vpc_cidr_block,
            "vpc_cidr_block": vpc_cidr_block,
            "availability_zone_count": availability_zone_count,
            "aws_availability_zones": [f"{aws_region}a", f"{aws_region}b", f"{aws_region}c"][
                :availability_zone_count
            ],
            "openshift_version": openshift_version,
            "rosa_creds_secret": "rosa-creds-secret",
            "environment_tag": "test",
            "purpose_tag": "rosa-preview",
            "domain_prefix": domain_prefix if domain_prefix else f"rosa-{cluster_name[:15]}",
            "channel_group": channel_group,
            "channel": channel,
            "cluster_network": {
                "pod_cidr": "10.128.0.0/14",
                "service_cidr": "172.30.0.0/16",
                "machine_cidr": vpc_cidr_block,
            },
            "rosa_network_config": {
                "name": f"{cluster_name}-network",
                "cidr_block": vpc_cidr_block,
                "availability_zones": [f"us-west-2a", f"us-west-2b"][:availability_zone_count],
                "identity_name": "default",
                "enabled": create_rosa_network,
                "tags": {"Environment": "test", "CreatedBy": "automation-ui"},
            },
            "rosa_role_config": {
                "prefix": role_prefix[:4],
                "version": openshift_version,
                "identity_name": "default",
                "enabled": create_rosa_roles,
            },
            "machine_pool": {
                "instance_type": "m5.xlarge",
                "min_replicas": 2,
                "max_replicas": 3,
                "replicas": 2,
                "node_pool_name": node_pool_name,
            },
            # Log forwarding configuration
            "log_forward_enabled": enable_log_forwarding,
            "log_forward_applications": log_forward_applications,
            "log_forward_cloudwatch_role_arn": log_forward_cloudwatch_role_arn,
            "log_forward_cloudwatch_log_group": log_forward_cloudwatch_log_group,
            "log_forward_s3_bucket": log_forward_s3_bucket,
            "log_forward_s3_prefix": log_forward_s3_prefix,
            # FIPS configuration (OpenShift 4.21+ only)
            "fips": enable_fips,
            # Manual configuration (for environments without CRDs)
            "manual_subnets": (
                [manual_public_subnet, manual_private_subnet]
                if manual_public_subnet and manual_private_subnet
                else []
            ),
            "manual_public_subnet": manual_public_subnet,
            "manual_private_subnet": manual_private_subnet,
            "manual_vpc_id": manual_vpc_id,
            "manual_oidc_config_id": manual_oidc_config_id,
            "manual_roles": {
                "installer": manual_installer_role_arn,
                "support": manual_support_role_arn,
                "worker": manual_worker_role_arn,
                "control_plane_operator": manual_control_plane_operator_role_arn,
                "kms_provider": manual_kms_provider_role_arn,
                "ingress_operator": manual_ingress_operator_role_arn,
                "image_registry_operator": manual_image_registry_operator_role_arn,
                "storage_operator": manual_storage_operator_role_arn,
                "network_operator": manual_network_operator_role_arn,
            },
        }

        # Determine which template to use based on automation options
        if create_rosa_network and create_rosa_roles:
            # Use combined template that includes everything (ROSARoleConfig, ROSANetwork, and all cluster resources)
            cp_template_name = "rosa-combined-automation.yaml.j2"
            use_combined_template = True
        elif create_rosa_network:
            cp_template_name = "rosa-capi-network-cluster.yaml.j2"
            use_combined_template = True  # Network template also includes ROSANetwork
        elif create_rosa_roles:
            cp_template_name = "rosa-capi-roles-cluster.yaml.j2"
            use_combined_template = True  # Roles template also includes ROSARoleConfig
        else:
            cp_template_name = "rosa-control-plane.yaml.j2"
            use_combined_template = False

        # If NOT using a combined template, render individual resources first
        if not use_combined_template:
            # Render ROSARoleConfig if needed (only for manual mode)
            if create_rosa_roles:
                role_template_path = os.path.join(
                    project_root,
                    f"templates/versions/{major_minor}/features/rosa-role-config.yaml.j2",
                )
                if not os.path.exists(role_template_path):
                    role_template_path = os.path.join(
                        project_root,
                        f"templates/versions/{major_minor}/4.20/features/rosa-role-config.yaml.j2",
                    )
                if not os.path.exists(role_template_path):
                    role_template_path = os.path.join(
                        project_root, f"templates/features/rosa-role-config.yaml.j2"
                    )

                if os.path.exists(role_template_path):
                    env = Environment(loader=FileSystemLoader(os.path.dirname(role_template_path)))
                    env.filters["regex_replace"] = regex_replace
                    env.globals["lookup"] = ansible_lookup
                    template = env.get_template(os.path.basename(role_template_path))
                    rendered = template.render(**template_vars)
                    yaml_contents.append(rendered)
                    yaml_files.append(role_template_path)

            # Render ROSANetwork if needed (only for manual mode)
            if create_rosa_network:
                network_template_path = os.path.join(
                    project_root,
                    f"templates/versions/{major_minor}/features/rosa-network-config.yaml.j2",
                )
                if not os.path.exists(network_template_path):
                    network_template_path = os.path.join(
                        project_root,
                        f"templates/versions/{major_minor}/4.20/features/rosa-network-config.yaml.j2",
                    )
                if not os.path.exists(network_template_path):
                    network_template_path = os.path.join(
                        project_root, f"templates/features/rosa-network-config.yaml.j2"
                    )

                if os.path.exists(network_template_path):
                    env = Environment(
                        loader=FileSystemLoader(os.path.dirname(network_template_path))
                    )
                    env.filters["regex_replace"] = regex_replace
                    env.globals["lookup"] = ansible_lookup
                    template = env.get_template(os.path.basename(network_template_path))
                    rendered = template.render(**template_vars)
                    yaml_contents.append(rendered)
                    yaml_files.append(network_template_path)

        # Render main cluster template (combined or control-plane-only)
        print(f"🔍 [PREVIEW-DIRECT] Template name: {cp_template_name}, major_minor: {major_minor}")
        cp_template_path = os.path.join(
            project_root, f"templates/versions/{major_minor}/features/{cp_template_name}"
        )
        print(f"🔍 [PREVIEW-DIRECT] Try 1: {cp_template_path} -> {os.path.exists(cp_template_path)}")
        if not os.path.exists(cp_template_path):
            # Try version/4.20/features fallback (e.g., 4.19/4.20/features)
            cp_template_path = os.path.join(
                project_root, f"templates/versions/{major_minor}/4.20/features/{cp_template_name}"
            )
            print(f"🔍 [PREVIEW-DIRECT] Try 2: {cp_template_path} -> {os.path.exists(cp_template_path)}")
        if not os.path.exists(cp_template_path):
            cp_template_path = os.path.join(
                project_root, f"templates/versions/{major_minor}/cluster-configs/{cp_template_name}"
            )
            print(f"🔍 [PREVIEW-DIRECT] Try 3: {cp_template_path} -> {os.path.exists(cp_template_path)}")
        if not os.path.exists(cp_template_path):
            cp_template_path = os.path.join(project_root, f"templates/features/{cp_template_name}")
            print(f"🔍 [PREVIEW-DIRECT] Try 4: {cp_template_path} -> {os.path.exists(cp_template_path)}")

        if os.path.exists(cp_template_path):
            env = Environment(loader=FileSystemLoader(os.path.dirname(cp_template_path)))
            env.filters["regex_replace"] = regex_replace
            env.globals["lookup"] = ansible_lookup
            template = env.get_template(os.path.basename(cp_template_path))
            rendered = template.render(
                **template_vars,
                rosa_role_config_ref=(
                    template_vars["rosa_role_config_name"] if create_rosa_roles else None
                ),
                rosa_network_ref=(
                    template_vars["rosa_network_name"] if create_rosa_network else None
                ),
            )
            yaml_contents.append(rendered)
            yaml_files.append(cp_template_path)
            print(
                f"✅ [PREVIEW-DIRECT] Rendered template: {cp_template_name} (combined={use_combined_template})"
            )
        else:
            print(f"⚠️  Control plane template not found at {cp_template_path}")

        # Combine all YAML documents
        combined_yaml = "\n---\n".join(yaml_contents)

        print(f"🔍 [PREVIEW-DIRECT] combined_yaml length: {len(combined_yaml)}")
        print(f"🔍 [PREVIEW-DIRECT] yaml_contents count: {len(yaml_contents)}")
        if len(combined_yaml) > 0:
            print(f"🔍 [PREVIEW-DIRECT] First 200 chars: {combined_yaml[:200]}")

        # Determine feature type for filename
        if create_rosa_network and create_rosa_roles:
            feature_type = "network-roles"
            automation_suffix = (
                "full-automation"  # Complete cluster with automated network and roles
            )
        elif create_rosa_network:
            feature_type = "network"
            automation_suffix = "network-automation"  # Complete cluster with automated network
        elif create_rosa_roles:
            feature_type = "roles"
            automation_suffix = "roles-automation"  # Complete cluster with automated roles
        else:
            feature_type = "manual"
            automation_suffix = "manual-config"  # Complete cluster with manual network and roles

        # Create a meaningful file path for the combined YAML
        # Use the pattern: {cluster-name}-complete-{automation-type}.yaml
        combined_filename = f"{cluster_name}-complete-{automation_suffix}.yaml"
        combined_file_path = (
            f"generated-yamls/{datetime.now().strftime('%Y-%m-%d')}/{combined_filename}"
        )

        print(f"✅ [PREVIEW-DIRECT] Generated {len(yaml_contents)} YAML document(s)")
        print(f"📄 [PREVIEW-DIRECT] File will be saved as: {combined_file_path}")

        response_data = {
            "success": True,
            "yaml_content": combined_yaml,
            "file_paths": [combined_file_path],  # Single combined file path
            "feature_type": feature_type,
            "cluster_name": cluster_name,
            "message": f"Generated YAML for {len(yaml_contents)} resource(s)",
        }

        print(f"🔍 [PREVIEW-DIRECT] Response success: {response_data['success']}")
        print(f"🔍 [PREVIEW-DIRECT] Response yaml_content length: {len(response_data.get('yaml_content', ''))}")
        print(f"🔍 [PREVIEW-DIRECT] Response keys: {list(response_data.keys())}")

        return response_data

    except Exception as e:
        import traceback

        print(f"❌ [PREVIEW-DIRECT] Error: {str(e)}")
        print(traceback.format_exc())
        return {
            "success": False,
            "message": f"Error generating YAML: {str(e)}",
            "error": traceback.format_exc(),
        }


@app.post("/api/provisioning/apply-yaml")
async def apply_provisioning_yaml(request: Request, background_tasks: BackgroundTasks):
    """Save and apply user-edited provisioning YAML"""
    try:
        body = await request.json()
        yaml_content = body.get("yaml_content")
        cluster_name = body.get("cluster_name")
        feature_type = body.get("feature_type", "manual")
        cluster_context = body.get(
            "cluster_context"
        )  # Optional: Minikube cluster name or kubeconfig context

        if not yaml_content or not cluster_name:
            raise HTTPException(
                status_code=400, detail="yaml_content and cluster_name are required"
            )

        project_root = os.environ.get("AUTOMATION_PATH") or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

        # Create dated directory: generated-yamls/YYYY-MM-DD/
        from datetime import date

        today = date.today().strftime("%Y-%m-%d")
        saved_yamls_dir = os.path.join(project_root, "generated-yamls", today)
        os.makedirs(saved_yamls_dir, exist_ok=True)

        # Save to dated directory with feature type naming
        saved_yaml_filename = f"{cluster_name}-{feature_type}.yaml"
        saved_yaml_path = os.path.join(saved_yamls_dir, saved_yaml_filename)

        with open(saved_yaml_path, "w") as f:
            f.write(yaml_content)

        print(f"💾 [APPLY] Saved edited YAML to: {saved_yaml_path}")

        # Also copy to ~/output for Ansible compatibility
        output_dir = os.path.expanduser("~/output")
        os.makedirs(output_dir, exist_ok=True)
        output_yaml_path = os.path.join(output_dir, f"{cluster_name}-combined.yaml")

        with open(output_yaml_path, "w") as f:
            f.write(yaml_content)

        # Generate job ID
        job_id = str(uuid.uuid4())

        # Create job
        jobs[job_id] = {
            "id": job_id,
            "status": "pending",
            "progress": 0,
            "message": "Queued: Applying provisioning YAML",
            "logs": [],
            "created_at": datetime.now(),
            "yaml_file": saved_yaml_path,
            "description": f"Apply ROSA provisioning YAML for {cluster_name}",
        }

        # Initialize AI agents for provisioning monitoring
        agents = init_ai_agents(job_id)

        # Run application in background
        async def apply_yaml_background():
            try:
                jobs[job_id]["status"] = "running"
                jobs[job_id]["progress"] = 10
                jobs[job_id]["message"] = "Parsing YAML resources"

                # Split multi-document YAML by ---
                import yaml
                import time
                import json
                import asyncio

                yaml_documents = list(yaml.safe_load_all(yaml_content))

                jobs[job_id]["progress"] = 20
                jobs[job_id]["message"] = f"Found {len(yaml_documents)} resource(s) to apply"
                jobs[job_id]["logs"].append(f"📄 Parsed {len(yaml_documents)} YAML document(s)")

                # Extract cluster information from YAML for notifications
                region = "N/A"
                version = "N/A"
                for doc in yaml_documents:
                    if doc and doc.get("kind") == "RosaControlPlane":
                        spec = doc.get("spec", {})
                        region = spec.get("region", "N/A")
                        version = spec.get("version", "N/A")
                        break

                # Send "started" notification
                send_cluster_notifications(
                    cluster_name=cluster_name,
                    region=region,
                    version=version,
                    job_id=job_id,
                    status="started",
                    operation_type="provision"
                )

                # For Minikube, use Ansible playbook for async execution
                if cluster_context:
                    # Filter out ManagedCluster resources (MCE/ACM-specific, not available on minikube)
                    mce_kinds = {"ManagedCluster"}
                    filtered_docs = [doc for doc in yaml_documents if doc and doc.get("kind") not in mce_kinds]
                    skipped = len(yaml_documents) - len(filtered_docs)
                    if skipped > 0:
                        jobs[job_id]["logs"].append(f"⏭️  Skipped {skipped} MCE-specific resource(s) (ManagedCluster) - not applicable to Minikube")
                        # Re-save the filtered YAML
                        filtered_yaml = "\n---\n".join(yaml.dump(doc, default_flow_style=False) for doc in filtered_docs)
                        with open(saved_yaml_path, "w") as f:
                            f.write(filtered_yaml)

                    jobs[job_id]["logs"].append(f"\n🎯 Provisioning to Minikube cluster: {cluster_context} via Ansible playbook")
                    jobs[job_id]["progress"] = 30
                    jobs[job_id]["message"] = "Running Ansible playbook for Minikube provisioning"

                    # Use the provision_rosa_hcp_minikube playbook
                    playbook_path = os.path.join(project_root, "playbooks", "provision_rosa_hcp_minikube.yml")

                    extra_vars = {
                        "cluster_name": cluster_name,
                        "minikube_context": cluster_context,
                        "yaml_file": saved_yaml_path,
                        "target_namespace": "ns-rosa-hcp"
                    }

                    jobs[job_id]["logs"].append(f"\n📋 Playbook: {playbook_path}")
                    jobs[job_id]["logs"].append(f"📦 Variables: {json.dumps(extra_vars, indent=2)}")

                    # Run ansible-playbook command
                    ansible_cmd = [
                        "ansible-playbook",
                        playbook_path,
                        "-e", json.dumps(extra_vars)
                    ]

                    result = await asyncio.to_thread(
                        subprocess.run,
                        ansible_cmd,
                        cwd=project_root,
                        capture_output=True,
                        text=True,
                        timeout=300  # 5 minute timeout for playbook itself
                    )

                    jobs[job_id]["logs"].append(f"\n{result.stdout}")
                    if result.stderr:
                        jobs[job_id]["logs"].append(f"\n⚠️ Warnings:\n{result.stderr}")

                    if result.returncode != 0:
                        jobs[job_id]["status"] = "failed"
                        jobs[job_id]["message"] = f"❌ Playbook failed with exit code {result.returncode}"
                        jobs[job_id]["error"] = result.stderr or result.stdout

                        send_cluster_notifications(
                            cluster_name=cluster_name,
                            region=region,
                            version=version,
                            job_id=job_id,
                            status="failed",
                            error=result.stderr or result.stdout,
                            operation_type="provision"
                        )
                        return

                    # Resources applied successfully - now poll until cluster is ready
                    jobs[job_id]["progress"] = 40
                    jobs[job_id]["message"] = "✅ Resources applied - monitoring cluster provisioning..."
                    jobs[job_id]["logs"].append(f"\n✅ Resources applied successfully! Now monitoring cluster status...")
                    jobs[job_id]["logs"].append(f"⏳ Polling RosaControlPlane status (this typically takes 15-20 minutes)...\n")

                    max_wait_time = 3600  # 60 minutes
                    poll_interval = 15  # Check every 15 seconds
                    start_time = time.time()
                    last_log_time = 0

                    while (time.time() - start_time) < max_wait_time:
                        try:
                            # Check RosaControlPlane status
                            check_cmd = [
                                "kubectl", "--context", cluster_context,
                                "get", "rosacontrolplane", cluster_name,
                                "-n", "ns-rosa-hcp", "-o", "json"
                            ]
                            check_result = await asyncio.to_thread(
                                subprocess.run,
                                check_cmd, capture_output=True, text=True, timeout=30
                            )

                            if check_result.returncode == 0:
                                rcp_data = json.loads(check_result.stdout)
                                status_obj = rcp_data.get("status", {})
                                ready = status_obj.get("ready", False)
                                conditions = status_obj.get("conditions", [])

                                # Find the ROSAControlPlaneReady condition
                                rcp_reason = "Unknown"
                                rcp_message = ""
                                for cond in conditions:
                                    if cond.get("type") == "ROSAControlPlaneReady":
                                        rcp_reason = cond.get("reason", "Unknown")
                                        rcp_message = cond.get("message", "")
                                        break

                                elapsed = time.time() - start_time
                                elapsed_min = int(elapsed // 60)
                                elapsed_sec = int(elapsed % 60)

                                # AI Agent: Feed status to monitoring agent
                                if agents and agents.get("monitor"):
                                    try:
                                        status_line = f"#AGENT_CONTEXT: resource_name={cluster_name} namespace=ns-rosa-hcp resource_type=rosacontrolplane"
                                        agents["monitor"].process_line(status_line)
                                        status_line = f"RosaControlPlane {cluster_name}: ready={ready} reason={rcp_reason} message={rcp_message}"
                                        agents["monitor"].process_line(status_line)
                                    except Exception as agent_err:
                                        print(f"[AI Agent] Warning: {agent_err}")

                                if ready:
                                    jobs[job_id]["status"] = "completed"
                                    jobs[job_id]["progress"] = 100
                                    jobs[job_id]["message"] = f"✅ Cluster {cluster_name} provisioned successfully!"
                                    jobs[job_id]["logs"].append(f"\n✅ Cluster {cluster_name} is READY! ({elapsed_min}m {elapsed_sec}s)")
                                    jobs[job_id]["agent_stats"] = get_agent_stats(job_id)

                                    send_cluster_notifications(
                                        cluster_name=cluster_name,
                                        region=region,
                                        version=version,
                                        job_id=job_id,
                                        status="completed",
                                        operation_type="provision"
                                    )
                                    return

                                elif rcp_reason in ["ReconciliationError", "ProvisioningFailed", "Failed"]:
                                    jobs[job_id]["status"] = "failed"
                                    jobs[job_id]["progress"] = 100
                                    jobs[job_id]["message"] = f"❌ Cluster {cluster_name} provisioning failed: {rcp_reason}"
                                    jobs[job_id]["logs"].append(f"\n❌ Provisioning failed: {rcp_reason}")
                                    if rcp_message:
                                        jobs[job_id]["logs"].append(f"   {rcp_message}")
                                    jobs[job_id]["agent_stats"] = get_agent_stats(job_id)

                                    send_cluster_notifications(
                                        cluster_name=cluster_name,
                                        region=region,
                                        version=version,
                                        job_id=job_id,
                                        status="failed",
                                        error=f"{rcp_reason}: {rcp_message}",
                                        operation_type="provision"
                                    )
                                    return

                                else:
                                    # Still provisioning - update progress (40-90%)
                                    progress = min(90, 40 + int((elapsed / max_wait_time) * 50))
                                    jobs[job_id]["progress"] = progress
                                    jobs[job_id]["message"] = f"⏳ Provisioning... ({rcp_reason}) - {elapsed_min}m {elapsed_sec}s"

                                    # Log every 30 seconds
                                    if time.time() - last_log_time >= 30:
                                        jobs[job_id]["logs"].append(f"   [{elapsed_min}m {elapsed_sec}s] Status: {rcp_reason}")
                                        if rcp_message:
                                            jobs[job_id]["logs"].append(f"             {rcp_message}")
                                        last_log_time = time.time()

                        except Exception as poll_error:
                            jobs[job_id]["logs"].append(f"⚠️ Poll error: {str(poll_error)}")

                        await asyncio.sleep(poll_interval)

                    # Timeout
                    jobs[job_id]["status"] = "failed"
                    jobs[job_id]["progress"] = 100
                    jobs[job_id]["message"] = f"❌ Provisioning timed out after 60 minutes"
                    jobs[job_id]["logs"].append(f"\n❌ Timeout: Cluster did not reach ready state within 60 minutes")

                    send_cluster_notifications(
                        cluster_name=cluster_name,
                        region=region,
                        version=version,
                        job_id=job_id,
                        status="failed",
                        error="Provisioning timed out after 60 minutes",
                        operation_type="provision"
                    )
                    return

                    apply_cmd = [
                        "kubectl",
                        "--context",
                        cluster_context,
                        "apply",
                        "-f",
                        saved_yaml_path,
                    ]

                    result = subprocess.run(
                        apply_cmd,
                        cwd=project_root,
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )

                    jobs[job_id]["logs"].append(f"\n{result.stdout}")
                    if result.stderr:
                        jobs[job_id]["logs"].append(f"\n⚠️ Warnings/Errors:\n{result.stderr}")

                    if result.returncode == 0 or "created" in result.stdout or "configured" in result.stdout:
                        jobs[job_id]["progress"] = 50
                        jobs[job_id]["message"] = "✅ Resources applied, waiting for cluster to be ready..."
                        jobs[job_id]["logs"].append(f"\n✅ All resources applied successfully!")

                        # Wait for cluster to be ready (for Minikube/ROSA provisioning)
                        jobs[job_id]["logs"].append(f"\n⏳ Monitoring cluster provisioning status...")

                        max_wait_time = 3600  # 60 minutes max wait
                        poll_interval = 10  # Check every 10 seconds
                        start_time = time.time()

                        while (time.time() - start_time) < max_wait_time:
                            # Get cluster name from YAML
                            try:
                                # Check for Cluster resource status
                                check_cluster_cmd = [
                                    "kubectl",
                                    "--context",
                                    cluster_context,
                                    "get",
                                    "cluster",
                                    "-n", "ns-rosa-hcp",
                                    "-o", "json"
                                ]

                                cluster_result = subprocess.run(
                                    check_cluster_cmd,
                                    capture_output=True,
                                    text=True,
                                    timeout=30
                                )

                                if cluster_result.returncode == 0:
                                    clusters_data = json.loads(cluster_result.stdout)

                                    if clusters_data.get("items"):
                                        cluster = clusters_data["items"][0]  # Get first cluster
                                        found_cluster_name = cluster["metadata"]["name"]
                                        phase = cluster.get("status", {}).get("phase", "Unknown")

                                        # Check RosaControlPlane ready status
                                        check_rcp_cmd = [
                                            "kubectl",
                                            "--context",
                                            cluster_context,
                                            "get",
                                            "rosacontrolplane",
                                            found_cluster_name,
                                            "-n", "ns-rosa-hcp",
                                            "-o", "jsonpath={.status.ready}"
                                        ]

                                        rcp_result = subprocess.run(
                                            check_rcp_cmd,
                                            capture_output=True,
                                            text=True,
                                            timeout=30
                                        )

                                        rcp_ready = rcp_result.stdout.strip().lower() == "true"

                                        # Update progress based on phase
                                        if phase == "Provisioned" and rcp_ready:
                                            jobs[job_id]["status"] = "completed"
                                            jobs[job_id]["progress"] = 100
                                            jobs[job_id]["message"] = f"✅ Cluster {found_cluster_name} is ready!"
                                            jobs[job_id]["logs"].append(f"\n✅ Cluster {found_cluster_name} provisioned successfully!")
                                            jobs[job_id]["logs"].append(f"   Phase: {phase}")
                                            jobs[job_id]["logs"].append(f"   RosaControlPlane Ready: {rcp_ready}")
                                            return
                                        elif phase == "Failed":
                                            jobs[job_id]["status"] = "failed"
                                            jobs[job_id]["progress"] = 100
                                            jobs[job_id]["message"] = f"❌ Cluster {found_cluster_name} provisioning failed"
                                            jobs[job_id]["logs"].append(f"\n❌ Cluster {found_cluster_name} entered Failed state")
                                            return
                                        else:
                                            # Update progress incrementally (50-90%)
                                            elapsed = time.time() - start_time
                                            progress = min(90, 50 + int((elapsed / max_wait_time) * 40))
                                            jobs[job_id]["progress"] = progress
                                            jobs[job_id]["message"] = f"⏳ Cluster {cluster_name} provisioning... (Phase: {phase}, RCP Ready: {rcp_ready})"

                                            # Log status update every 60 seconds
                                            if int(elapsed) % 60 == 0:
                                                jobs[job_id]["logs"].append(f"   [{int(elapsed//60)}m] Phase: {phase}, RCP Ready: {rcp_ready}")

                            except Exception as status_error:
                                jobs[job_id]["logs"].append(f"⚠️  Error checking cluster status: {str(status_error)}")

                            await asyncio.sleep(poll_interval)

                        # Timeout reached
                        jobs[job_id]["status"] = "failed"
                        jobs[job_id]["progress"] = 100
                        jobs[job_id]["message"] = "❌ Cluster provisioning timed out after 60 minutes"
                        jobs[job_id]["logs"].append(f"\n❌ Timeout: Cluster did not reach ready state within 60 minutes")
                        return
                    else:
                        jobs[job_id]["status"] = "failed"
                        jobs[job_id]["progress"] = 100
                        jobs[job_id]["message"] = f"❌ Failed to apply resources"
                        jobs[job_id]["logs"].append(f"\n❌ ERROR: {result.stderr}")
                        return

                # Apply each resource using oc apply
                progress_increment = 70 / max(len(yaml_documents), 1)
                current_progress = 20

                for idx, doc in enumerate(yaml_documents, 1):
                    if not doc:  # Skip empty documents
                        continue

                    kind = doc.get("kind", "Unknown")
                    name = doc.get("metadata", {}).get("name", "Unknown")

                    # Skip ManagedCluster when applying to Minikube (no ACM/MCE CRDs)
                    if cluster_context and kind == "ManagedCluster":
                        jobs[job_id]["logs"].append(
                            f"\n[{idx}/{len(yaml_documents)}] Skipping {kind}/{name} (ACM/MCE-only resource, not available on Minikube)"
                        )
                        continue

                    jobs[job_id]["logs"].append(
                        f"\n[{idx}/{len(yaml_documents)}] Applying {kind}/{name}..."
                    )

                    # Save individual document to temp file
                    import tempfile

                    with tempfile.NamedTemporaryFile(
                        mode="w", suffix=".yaml", delete=False
                    ) as temp_file:
                        yaml.dump(doc, temp_file)
                        temp_path = temp_file.name

                    try:
                        # Build kubectl/oc command with optional context
                        if cluster_context:
                            # Use kubectl with --context for Minikube or other non-OpenShift clusters
                            apply_cmd = [
                                "kubectl",
                                "--context",
                                cluster_context,
                                "apply",
                                "-f",
                                temp_path,
                            ]
                        else:
                            # Default to oc for OpenShift clusters
                            apply_cmd = ["oc", "apply", "-f", temp_path]

                        result = subprocess.run(
                            apply_cmd,
                            cwd=project_root,
                            capture_output=True,
                            text=True,
                            timeout=120,
                        )

                        if result.returncode == 0:
                            jobs[job_id]["logs"].append(f"✅ {result.stdout.strip()}")

                            # If we just created a Namespace or ManagedCluster, copy rosa-creds-secret to it
                            # ManagedCluster is often the first resource and triggers namespace creation
                            if kind in ["Namespace", "ManagedCluster"]:
                                # Get the namespace name from the resource
                                namespace_name = doc.get("metadata", {}).get(
                                    "namespace", name if kind == "Namespace" else None
                                )

                                if namespace_name:
                                    jobs[job_id]["logs"].append(
                                        f"\n🔐 Checking for rosa-creds-secret to copy to {namespace_name}..."
                                    )

                                    try:
                                        # Build kubectl/oc commands with optional context
                                        if cluster_context:
                                            kubectl_cmd = "kubectl --context " + cluster_context
                                        else:
                                            kubectl_cmd = "oc"

                                        # Check if rosa-creds-secret exists in multicluster-engine namespace
                                        check_secret = subprocess.run(
                                            [kubectl_cmd.split()[0]]
                                            + (kubectl_cmd.split()[1:] if cluster_context else [])
                                            + [
                                                "get",
                                                "secret",
                                                "rosa-creds-secret",
                                                "-n",
                                                "multicluster-engine",
                                            ],
                                            capture_output=True,
                                            text=True,
                                            timeout=10,
                                        )

                                        if check_secret.returncode == 0:
                                            # Secret exists, copy it to the new namespace
                                            copy_cmd = f"""
{kubectl_cmd} get secret rosa-creds-secret -n multicluster-engine -o yaml | \
sed 's/namespace: multicluster-engine/namespace: {namespace_name}/' | \
sed '/resourceVersion:/d' | \
sed '/uid:/d' | \
sed '/creationTimestamp:/d' | \
{kubectl_cmd} apply -f -
"""
                                            copy_result = subprocess.run(
                                                ["bash", "-c", copy_cmd],
                                                capture_output=True,
                                                text=True,
                                                timeout=30,
                                            )

                                            if copy_result.returncode == 0:
                                                jobs[job_id]["logs"].append(
                                                    f"✅ rosa-creds-secret copied to {namespace_name}"
                                                )
                                            else:
                                                jobs[job_id]["logs"].append(
                                                    f"⚠️  Failed to copy rosa-creds-secret: {copy_result.stderr.strip()}"
                                                )
                                        else:
                                            jobs[job_id]["logs"].append(
                                                f"⚠️  rosa-creds-secret not found in multicluster-engine namespace - skipping copy"
                                            )

                                    except Exception as secret_error:
                                        jobs[job_id]["logs"].append(
                                            f"⚠️  Error copying secret: {str(secret_error)}"
                                        )
                        else:
                            jobs[job_id]["logs"].append(f"❌ Failed: {result.stderr.strip()}")
                            raise Exception(f"Failed to apply {kind}/{name}: {result.stderr}")

                    finally:
                        os.unlink(temp_path)

                    current_progress += progress_increment
                    jobs[job_id]["progress"] = int(current_progress)

                jobs[job_id]["status"] = "completed"
                jobs[job_id]["progress"] = 100
                jobs[job_id]["message"] = f"Successfully applied {len(yaml_documents)} resource(s)"
                jobs[job_id]["logs"].append(f"\n✅ All resources applied successfully!")
                jobs[job_id]["completed_at"] = datetime.now()
                jobs[job_id]["return_code"] = 0

            except Exception as e:
                jobs[job_id]["status"] = "failed"
                jobs[job_id]["message"] = f"Error applying YAML: {str(e)}"
                jobs[job_id]["logs"].append(f"\n❌ ERROR: {str(e)}")
                jobs[job_id]["completed_at"] = datetime.now()
                jobs[job_id]["return_code"] = 1

        # Start background task using asyncio.create_task so blocking calls
        # don't freeze the event loop
        import asyncio
        asyncio.create_task(apply_yaml_background())

        return {
            "job_id": job_id,
            "status": "pending",
            "message": "YAML queued for application",
            "saved_path": saved_yaml_path,
        }

    except Exception as e:
        import traceback

        error_msg = f"Error applying YAML: {str(e)}"
        print(f"❌ [APPLY] {error_msg}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_msg)


@app.get("/api/clusters")
async def list_clusters():
    """List all ROSA HCP clusters with their status"""
    try:
        result = subprocess.run(
            ["kubectl", "get", "rosacontrolplane", "-n", "ns-rosa-hcp", "-o", "json"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return {
                "success": False,
                "clusters": [],
                "message": f"Error fetching clusters: {result.stderr}",
            }

        import json

        data = json.loads(result.stdout)

        clusters = []
        for item in data.get("items", []):
            metadata = item.get("metadata", {})
            spec = item.get("spec", {})
            status = item.get("status", {})

            # Determine overall status
            ready = status.get("ready", False)
            conditions = status.get("conditions", [])

            # Check if resource is being deleted
            is_deleting = metadata.get("deletionTimestamp") is not None

            # Get error message if any
            error_message = None
            for condition in conditions:
                if condition.get("type") == "Ready" and condition.get("status") == "False":
                    error_message = condition.get("message", "Unknown error")

            # Calculate progress percentage
            progress = 0
            if ready:
                progress = 100
            else:
                # Check sub-resources
                network_ready = any(
                    c.get("type") == "ROSANetworkReady" and c.get("status") == "True"
                    for c in conditions
                )
                role_ready = any(
                    c.get("type") == "ROSARoleConfigReady" and c.get("status") == "True"
                    for c in conditions
                )
                cp_valid = any(
                    c.get("type") == "ROSAControlPlaneValid" and c.get("status") == "True"
                    for c in conditions
                )

                if cp_valid:
                    progress += 25
                if role_ready:
                    progress += 25
                if network_ready:
                    progress += 25
                if ready:
                    progress += 25

            region = spec.get("region", "N/A")
            cluster_info = {
                "name": metadata.get("name"),
                "namespace": metadata.get("namespace", "ns-rosa-hcp"),
                "created_at": metadata.get("creationTimestamp"),
                "domain_prefix": spec.get("domainPrefix", "N/A"),
                "version": spec.get("version", "N/A"),
                "region": region,
                "ready": ready,
                "progress": progress,
                "status": (
                    "deleting"
                    if is_deleting
                    else ("ready" if ready else ("failed" if error_message else "provisioning"))
                ),
                "error_message": error_message,
                "console_url": status.get("consoleURL"),
                "api_url": (
                    f"https://api.{spec.get('domainPrefix', 'unknown')}.{region}.openshiftapps.com"
                    if spec.get("domainPrefix")
                    else None
                ),
            }

            clusters.append(cluster_info)

        # Sort by creation time (newest first)
        clusters.sort(key=lambda x: normalize_timestamp(x.get("created_at")), reverse=True)

        return {
            "success": True,
            "clusters": clusters,
            "count": len(clusters),
        }

    except Exception as e:
        import traceback

        print(f"❌ [LIST-CLUSTERS] Error: {str(e)}")
        print(traceback.format_exc())
        return {
            "success": False,
            "clusters": [],
            "message": f"Error listing clusters: {str(e)}",
        }


@app.get("/api/clusters/{cluster_name}/status")
async def get_cluster_status(cluster_name: str):
    """Get detailed status for a specific cluster"""
    try:
        # Get ROSAControlPlane
        result = subprocess.run(
            ["kubectl", "get", "rosacontrolplane", cluster_name, "-n", "ns-rosa-hcp", "-o", "json"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            raise HTTPException(status_code=404, detail=f"Cluster {cluster_name} not found")

        import json

        cp_data = json.loads(result.stdout)

        # Get ROSANetwork if it exists
        network_data = None
        network_result = subprocess.run(
            [
                "kubectl",
                "get",
                "rosanetwork",
                f"{cluster_name}-network",
                "-n",
                "ns-rosa-hcp",
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if network_result.returncode == 0:
            network_data = json.loads(network_result.stdout)

        # Get ROSARoleConfig if it exists
        role_data = None
        role_result = subprocess.run(
            [
                "kubectl",
                "get",
                "rosaroleconfig",
                f"{cluster_name}-roles",
                "-n",
                "ns-rosa-hcp",
                "-o",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if role_result.returncode == 0:
            role_data = json.loads(role_result.stdout)

        return {
            "success": True,
            "control_plane": cp_data,
            "network": network_data,
            "roles": role_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback

        print(f"❌ [GET-CLUSTER-STATUS] Error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error getting cluster status: {str(e)}")


@app.post("/api/ai-assistant/chat")
async def ai_assistant_chat(request: Request):
    """AI Assistant chat endpoint - provides AI-powered analysis of cluster issues using Claude"""
    try:
        body = await request.json()
        message = body.get("message", "")
        context = body.get("context", {})
        history = body.get("history", [])
        clusters_data = context.get("clusters", [])

        import logging

        logger = logging.getLogger("uvicorn")
        logger.info(f"🔍 [AI ASSISTANT] Message: {message}")
        logger.info(f"🔍 [AI ASSISTANT] Clusters data received: {clusters_data}")

        # Ensure clusters_data is a list
        if not isinstance(clusters_data, list):
            clusters_data = []

        # Enrich context with actual job logs for failed/error clusters
        enriched_context = {"clusters": clusters_data, "job_logs": [], "resource_status": {}}

        # Find failed or error clusters and get their job logs
        failed_clusters = [
            c
            for c in clusters_data
            if c.get("status") in ["failed", "error", "provisioning-failed"]
        ]

        for cluster in failed_clusters:
            cluster_name = cluster.get("name", "unknown")

            # Search jobs dictionary for provisioning jobs for this cluster
            for job_id, job_data in jobs.items():
                yaml_file = job_data.get("yaml_file", "")
                description = job_data.get("description", "")

                # Check if this job is for the failed cluster
                if (
                    cluster_name.lower() in yaml_file.lower()
                    or cluster_name.lower() in description.lower()
                ):
                    log_content = "\n".join(job_data.get("logs", []))

                    enriched_context["job_logs"].append(
                        {
                            "job_id": job_id,
                            "cluster_name": cluster_name,
                            "status": job_data.get("status", "unknown"),
                            "logs": log_content,
                            "yaml_file": yaml_file,
                            "created_at": job_data.get("created_at", ""),
                        }
                    )

        # Use AI service if ANTHROPIC_API_KEY is set
        if os.environ.get("ANTHROPIC_API_KEY"):
            try:
                ai_response = await ai_service.chat(message, enriched_context, history)
                response_text = ai_response.get("response", "")

                logger.info(f"🤖 [AI-ASSISTANT] AI Response: {response_text[:200]}...")

                # Post-process: If user asked about clusters and AI didn't include names, fix it
                if "what clusters" in message.lower() or "clusters are running" in message.lower():
                    logger.info(
                        f"🔍 [AI-ASSISTANT] Cluster query detected. Clusters data: {[c.get('name') for c in clusters_data]}"
                    )
                    has_cluster_names = any(
                        c.get("name", "") in response_text for c in clusters_data
                    )
                    logger.info(
                        f"🔍 [AI-ASSISTANT] Response contains cluster names: {has_cluster_names}"
                    )

                    if clusters_data and not has_cluster_names:
                        # AI didn't include cluster names, build proper response
                        logger.info(
                            "🔧 [AI-ASSISTANT] AI response missing cluster names, fixing..."
                        )
                        cluster_list = "\n".join(
                            [
                                f"  - {c.get('name', 'unknown')} (namespace: {c.get('namespace', 'unknown')}, status: {c.get('status', 'unknown')})"
                                for c in clusters_data
                            ]
                        )
                        response_text = (
                            f"You have {len(clusters_data)} cluster(s):\n\n{cluster_list}"
                        )
                        logger.info(f"✅ [AI-ASSISTANT] Fixed response: {response_text}")

                return {
                    "response": response_text,
                    "suggestions": ai_response.get("suggestions", []),
                }
            except Exception as ai_error:
                logger.error(
                    f"⚠️ [AI-ASSISTANT] Claude API error: {str(ai_error)}, falling back to simple responses"
                )
                logger.error(f"⚠️ [AI-ASSISTANT] Error traceback: ", exc_info=True)
                # Fall through to simple responses below

        # Fallback: Simple rule-based responses if no API key or AI service fails
        response = ""
        suggestions = []
        message_lower = message.lower()

        # Handle cluster-related questions
        if (
            "what clusters" in message_lower
            or "list clusters" in message_lower
            or "show clusters" in message_lower
        ):
            if clusters_data:
                response = f"Currently, you have {len(clusters_data)} cluster(s):\n\n"

                # Categorize clusters by status
                ready_clusters = [c for c in clusters_data if c.get("status") == "ready"]
                provisioning_clusters = [
                    c for c in clusters_data if c.get("status") == "provisioning"
                ]
                failed_clusters = [
                    c
                    for c in clusters_data
                    if c.get("status") in ["failed", "error", "provisioning-failed"]
                ]
                uninstalling_clusters = [
                    c for c in clusters_data if c.get("status") == "uninstalling"
                ]
                other_clusters = [
                    c
                    for c in clusters_data
                    if c.get("status")
                    not in [
                        "ready",
                        "provisioning",
                        "failed",
                        "error",
                        "provisioning-failed",
                        "uninstalling",
                    ]
                ]

                if ready_clusters:
                    response += f"**✅ Ready ({len(ready_clusters)}):**\n"
                    for cluster in ready_clusters:
                        name = cluster.get("name", "unknown")
                        region = cluster.get("region", "unknown")
                        version = cluster.get("version", "N/A")
                        response += f"• **{name}** - Region: {region}, Version: {version}\n"
                    response += "\n"

                if provisioning_clusters:
                    response += f"**⏳ Provisioning ({len(provisioning_clusters)}):**\n"
                    for cluster in provisioning_clusters:
                        name = cluster.get("name", "unknown")
                        progress = cluster.get("progress", 0)
                        response += f"• **{name}** - {progress}% complete\n"
                    response += "\n"

                if failed_clusters:
                    response += f"**❌ Failed ({len(failed_clusters)}):**\n"
                    for cluster in failed_clusters:
                        name = cluster.get("name", "unknown")
                        status = cluster.get("status", "unknown")
                        response += f"• **{name}** - Status: {status}\n"
                    response += "\n"

                if uninstalling_clusters:
                    response += f"**🗑️ Uninstalling ({len(uninstalling_clusters)}):**\n"
                    for cluster in uninstalling_clusters:
                        name = cluster.get("name", "unknown")
                        namespace = cluster.get("namespace", "unknown")
                        region = cluster.get("region", "unknown")
                        response += f"• **{name}** (namespace: {namespace}, region: {region})\n"
                    response += "\n"

                if other_clusters:
                    response += f"**ℹ️ Other Status ({len(other_clusters)}):**\n"
                    for cluster in other_clusters:
                        name = cluster.get("name", "unknown")
                        status = cluster.get("status", "unknown")
                        response += f"• **{name}** - Status: {status}\n"
                    response += "\n"

                # Set suggestions based on cluster states
                if failed_clusters:
                    suggestions = ["Troubleshoot failed cluster", "Show me the logs"]
                elif uninstalling_clusters:
                    first_cluster_name = uninstalling_clusters[0].get("name", "unknown")
                    suggestions = [f"Tell me more about {first_cluster_name}", "Show me the logs"]
                elif provisioning_clusters:
                    # Add suggestion to check on the provisioning cluster
                    first_cluster_name = provisioning_clusters[0].get("name", "unknown")
                    suggestions = [
                        f"Tell me about {first_cluster_name}",
                        "Check environment status",
                    ]
                else:
                    suggestions = ["Provision new cluster", "What is ROSA HCP?"]
            else:
                response = "You don't have any clusters running at the moment. Would you like to provision one?"
                suggestions = ["How to provision cluster?", "What is ROSA HCP?"]

        # Handle "tell me more about" or "tell me about" cluster requests
        elif ("tell me" in message_lower or "about" in message_lower) and any(
            c.get("name", "").lower() in message_lower for c in clusters_data
        ):
            # Find the cluster being asked about
            target_cluster = None
            for cluster in clusters_data:
                cluster_name = cluster.get("name", "")
                if cluster_name and cluster_name.lower() in message_lower:
                    target_cluster = cluster
                    break

            if target_cluster:
                name = target_cluster.get("name", "unknown")
                status = target_cluster.get("status", "unknown")
                namespace = target_cluster.get("namespace", "unknown")
                region = target_cluster.get("region", "unknown")
                version = target_cluster.get("version", "N/A")
                created = target_cluster.get("created", "N/A")
                domain_prefix = target_cluster.get("domain_prefix", "N/A")
                progress = target_cluster.get("progress", 0)

                response = f"""## 🔍 Detailed Information: **{name}**

### 📊 Current Status
**State:** {status.upper()}"""

                if status == "uninstalling":
                    response += f"""

Your cluster **{name}** is being deleted right now. Here's what I know about it:

**Quick Info:**
• Running in the `{namespace}` namespace
• Located in {region}
• Was running OpenShift version {version}
• Created on {created}

**What's happening behind the scenes:**
Right now, the system is busy tearing everything down:
- Shutting down the OpenShift control plane
- Cleaning up all the AWS resources (EC2 instances, load balancers, etc.)
- Removing the networking setup (VPCs, subnets, security groups)
- Tidying up IAM roles and policies

**Want to check on the progress?**
Pop open the Terminal section and try these commands:
```
oc get rosacontrolplane -n {namespace}
oc describe rosacontrolplane {name} -n {namespace}
oc get events -n {namespace} --sort-by='.lastTimestamp'
```

**How long will this take?**
Usually about 10-20 minutes. Grab a coffee and it should be done when you get back! ☕"""

                elif status == "provisioning":
                    response += f"""
**Progress:** {progress}% complete

### ℹ️ Cluster Details
• **Namespace:** `{namespace}`
• **Region:** {region}
• **OpenShift Version:** {version}
• **Domain Prefix:** {domain_prefix}
• **Created:** {created}

### 🚀 Provisioning Stages
The cluster is being created. Typical stages:
1. **Network Setup** ({progress < 25 and '🔄 Current' or '✅ Complete'}) - Creating VPC, subnets, security groups
2. **IAM Configuration** ({25 <= progress < 50 and '🔄 Current' or progress >= 50 and '✅ Complete' or '⏳ Pending'}) - Setting up IAM roles and policies
3. **Control Plane** ({50 <= progress < 75 and '🔄 Current' or progress >= 75 and '✅ Complete' or '⏳ Pending'}) - Launching OpenShift control plane
4. **Node Provisioning** ({progress >= 75 and '🔄 Current' or '⏳ Pending'}) - Creating worker nodes

### 🔍 How to Monitor
```
oc get rosacontrolplane -n {namespace} -o yaml
oc describe rosacontrolplane {name} -n {namespace}
```

### ⏱️ Expected Timeline
Cluster provisioning typically takes 30-45 minutes to complete."""

                elif status == "ready":
                    response += f"""

### ℹ️ Cluster Details
• **Namespace:** `{namespace}`
• **Region:** {region}
• **OpenShift Version:** {version}
• **Domain Prefix:** {domain_prefix}
• **Created:** {created}

### ✅ Cluster is Ready!
Your ROSA HCP cluster is fully provisioned and operational.

### 🔗 Access Information
You can access the cluster using:
```
oc get rosacontrolplane {name} -n {namespace} -o yaml
```

Look for the `oidcEndpointURL` and API server URL in the status section.

### 🛠️ Next Steps
• Configure node pools for workloads
• Set up application deployments
• Configure monitoring and logging
• Implement backup strategies"""

                else:
                    response += f"""

### ℹ️ Cluster Details
• **Namespace:** `{namespace}`
• **Region:** {region}
• **OpenShift Version:** {version}
• **Domain Prefix:** {domain_prefix}
• **Created:** {created}
• **Current Status:** {status}

### 🔍 Diagnostic Commands
```
oc get rosacontrolplane {name} -n {namespace}
oc describe rosacontrolplane {name} -n {namespace}
oc get events -n {namespace} --sort-by='.lastTimestamp'
```"""

                suggestions = ["Show me the logs", "What clusters are running?"]

        # Handle log requests
        elif "show" in message_lower and "log" in message_lower:
            # Find the most recent job related to any cluster
            recent_jobs = []
            for job_id, job_data in sorted(
                jobs.items(),
                key=lambda x: normalize_timestamp(x[1].get("created_at")),
                reverse=True,
            )[:10]:
                yaml_file = job_data.get("yaml_file", "")
                description = job_data.get("description", "")
                log_lines = job_data.get("logs", [])

                # Check if this job is related to the user's clusters
                for cluster in clusters_data:
                    cluster_name = cluster.get("name", "")
                    if cluster_name and (
                        cluster_name.lower() in yaml_file.lower()
                        or cluster_name.lower() in description.lower()
                    ):
                        recent_jobs.append(
                            {
                                "job_id": job_id,
                                "cluster_name": cluster_name,
                                "description": description,
                                "status": job_data.get("status", "unknown"),
                                "logs": (
                                    "\n".join(log_lines[-20:]) if log_lines else "No logs available"
                                ),
                                "created_at": job_data.get("created_at", ""),
                            }
                        )
                        break

            if recent_jobs:
                latest_job = recent_jobs[0]
                response = f"""**Logs for {latest_job['cluster_name']}**

**Job ID:** {latest_job['job_id']}
**Description:** {latest_job['description']}
**Status:** {latest_job['status']}
**Created:** {latest_job['created_at']}

**Recent Log Output:**
```
{latest_job['logs']}
```

You can view more details in the Task Detail section below."""
                suggestions = [
                    f"Tell me more about {latest_job['cluster_name']}",
                    "What clusters are running?",
                ]
            else:
                response = "I couldn't find any recent logs for your clusters. Logs will appear here when cluster operations (provisioning, deletion, etc.) are running."
                suggestions = ["What clusters are running?", "Provision new cluster"]

        # Handle provisioning questions
        elif (
            "provision" in message_lower
            or "create cluster" in message_lower
            or "how to" in message_lower
        ):
            response = """To provision a ROSA HCP cluster:

1. Click the "Provision" button in the Configuration section
2. Fill in the cluster details:
   - Cluster name
   - OpenShift version
   - Region
   - Instance type and replicas

3. Choose automation features:
   - Network automation (automatic VPC/subnet creation)
   - Role automation (automatic IAM role creation)

4. Review the generated YAML and click "Apply"

The cluster will be provisioned automatically!"""
            suggestions = ["What is network automation?", "What clusters are running?"]

        # Handle troubleshooting
        elif (
            "troubleshoot" in message_lower
            or "failed" in message_lower
            or "error" in message_lower
            or "problem" in message_lower
        ):
            # Check for failed clusters in the context
            failed_clusters = [
                c
                for c in clusters_data
                if c.get("status") in ["failed", "error", "provisioning-failed"]
            ]
            provisioning_clusters = [c for c in clusters_data if c.get("status") == "provisioning"]

            if failed_clusters:
                response = f"I found {len(failed_clusters)} failed cluster(s):\n\n"
                for cluster in failed_clusters:
                    name = cluster.get("name", "unknown")
                    status = cluster.get("status", "unknown")
                    namespace = cluster.get("namespace", "unknown")
                    response += f"**{name}** (Status: {status})\n"
                    response += f"Namespace: {namespace}\n\n"
                    response += "**Troubleshooting steps for this cluster:**\n"
                    response += f"1. Check rosa-creds-secret in namespace '{namespace}'\n"
                    response += f"2. View ROSANetwork status: `oc get rosanetwork -n {namespace}`\n"
                    response += (
                        f"3. View ROSARoleConfig status: `oc get rosaroleconfig -n {namespace}`\n"
                    )
                    response += f"4. Check ROSAControlPlane events: `oc describe rosacontrolplane -n {namespace}`\n"
                    response += f"5. View detailed logs in Recent Operations section\n\n"

                suggestions = ["What clusters are running?", "How to provision cluster?"]
            elif provisioning_clusters:
                response = (
                    f"I see {len(provisioning_clusters)} cluster(s) currently provisioning:\n\n"
                )
                for cluster in provisioning_clusters:
                    name = cluster.get("name", "unknown")
                    progress = cluster.get("progress", 0)
                    response += f"**{name}** - {progress}% complete\n\n"
                response += "Provisioning clusters are still in progress. If a cluster has been stuck for a long time:\n\n"
                response += "1. Check Recent Operations for detailed progress logs\n"
                response += (
                    "2. Verify ROSANetwork is Ready (network creation can take 5-10 minutes)\n"
                )
                response += (
                    "3. Verify ROSARoleConfig is Ready (role creation can take 2-3 minutes)\n"
                )
                response += "4. Check that rosa-creds-secret exists in the cluster namespace\n"
                suggestions = ["What clusters are running?", "Provision new cluster"]
            else:
                response = """I don't see any failed clusters in your environment.

If you're experiencing issues:

1. **Check cluster status**: View the CAPI-Managed ROSA HCP Clusters table
2. **View Recent Operations**: Check the Recent Operations section for error logs
3. **Common issues**:
   - Missing rosa-creds-secret → Verify it exists in both multicluster-engine and cluster namespace
   - Network not ready → ROSANetwork resource may still be provisioning
   - Role creation failed → Check AWS credentials and IAM permissions

4. **Refresh status**: Click the Refresh button to update cluster information"""
                suggestions = ["What clusters are running?", "How to provision cluster?"]

        # Handle ROSA/CAPI concept questions
        elif "what is rosa" in message_lower or "explain rosa" in message_lower:
            response = """ROSA (Red Hat OpenShift Service on AWS) is a fully-managed OpenShift service on AWS.

**ROSA HCP (Hosted Control Planes):**
- Control plane runs in Red Hat's AWS account
- You only pay for worker nodes
- Faster provisioning and scaling
- Lower cost than classic ROSA

**CAPI Integration:**
- This UI uses Cluster API (CAPI) to manage ROSA clusters
- Provides declarative cluster management via Kubernetes CRDs
- Enables GitOps-style cluster lifecycle management"""
            suggestions = ["How to provision cluster?", "What is network automation?"]

        elif "what is capi" in message_lower or "cluster api" in message_lower:
            response = """CAPI (Cluster API) is a Kubernetes project to bring declarative, Kubernetes-style APIs to cluster creation, configuration, and management.

**In this UI:**
- Manage ROSA HCP clusters using Kubernetes Custom Resources
- Automate networking (VPC, subnets) with ROSANetwork
- Automate IAM roles with ROSARoleConfig
- Full cluster lifecycle management

**Benefits:**
- GitOps-friendly workflow
- Declarative configuration
- Automated infrastructure provisioning"""
            suggestions = ["How to provision cluster?", "What clusters are running?"]

        elif "network automation" in message_lower or "rosanetwork" in message_lower:
            response = """Network Automation automatically creates AWS VPC and subnets for your ROSA cluster.

**What it does:**
- Creates VPC with specified CIDR block
- Creates public and private subnets across multiple AZs
- Sets up Internet Gateway and NAT Gateways
- Configures route tables

**Benefits:**
- No manual AWS console work
- Consistent network configuration
- Proper multi-AZ setup automatically

Enable it during provisioning by checking "Network Automation (ROSANetwork)"."""
            suggestions = ["What is role automation?", "How to provision cluster?"]

        elif "role automation" in message_lower or "rosaroleconfig" in message_lower:
            response = """Role Automation automatically creates required AWS IAM roles for your ROSA cluster.

**What it creates:**
- Account roles (installer, support, worker, control-plane)
- Operator roles (for AWS service integration)
- OIDC provider configuration

**Benefits:**
- No manual AWS IAM console work
- Correct permissions automatically
- Proper trust policies configured

Enable it during provisioning by checking "Role Automation (ROSARoleConfig)"."""
            suggestions = ["What is network automation?", "How to provision cluster?"]

        # Handle environment status questions
        elif (
            "environment status" in message_lower
            or "check environment" in message_lower
            or "environment ready" in message_lower
        ):
            # Check MCE/CAPI status
            response = "**Environment Status:**\n\n"
            response += "I can help you check:\n"
            response += (
                "• **CAPI/CAPA Configuration** - Click 'Verify' in the Configuration section\n"
            )
            response += (
                "• **Cluster Resources** - View ROSA HCP Clusters table for all cluster statuses\n"
            )
            response += "• **Recent Operations** - Check Task Summary for recent activity\n\n"
            response += "**Quick Actions:**\n"
            response += "• Verify environment is configured\n"
            response += "• View cluster status details\n"
            response += "• Check provisioning progress\n"
            suggestions = [
                "What clusters are running?",
                "Verify environment",
                "Provision new cluster",
            ]

        # Handle status/monitoring questions
        elif (
            "status" in message_lower or "monitoring" in message_lower or "how is" in message_lower
        ):
            if clusters_data:
                response = "Here's the current status of your clusters:\n\n"
                for cluster in clusters_data:
                    name = cluster.get("name", "unknown")
                    status = cluster.get("status", "unknown")
                    progress = cluster.get("progress")
                    response += f"• **{name}**: {status}"
                    if progress:
                        response += f" ({progress}% complete)"
                    response += "\n"
                response += (
                    "\nYou can see detailed status in the CAPI-Managed ROSA HCP Clusters table."
                )
                suggestions = ["Troubleshoot failed cluster", "Provision new cluster"]
            else:
                response = "You don't have any clusters to monitor yet. Provision a cluster to get started!"
                suggestions = ["How to provision cluster?"]

        # Handle specific cluster queries
        else:
            # Check if user is asking about a specific cluster
            cluster_match = None
            for cluster in clusters_data:
                cluster_name = cluster.get("name", "").lower()
                if cluster_name and cluster_name in message_lower:
                    cluster_match = cluster
                    break

            if cluster_match:
                name = cluster_match.get("name", "unknown")
                status = cluster_match.get("status", "unknown")
                namespace = cluster_match.get("namespace", "unknown")
                progress = cluster_match.get("progress")
                region = cluster_match.get("region", "N/A")
                version = cluster_match.get("version", "N/A")
                created = cluster_match.get("created", "N/A")

                response = f"## Cluster: **{name}**\n\n"
                response += f"**Status:** {status}"
                if progress:
                    response += f" ({progress}% complete)"
                response += f"\n\n"

                response += f"**Details:**\n"
                response += f"• **Namespace:** {namespace}\n"
                response += f"• **Region:** {region}\n"
                response += f"• **OpenShift Version:** {version}\n"
                response += f"• **Created:** {created}\n\n"

                if status == "provisioning":
                    response += "**Provisioning in progress...**\n\n"
                    response += "The cluster is being created. This typically takes:\n"
                    response += "• ROSANetwork: 5-10 minutes\n"
                    response += "• ROSARoleConfig: 2-3 minutes\n"
                    response += "• Control Plane: 10-15 minutes\n\n"
                    response += f"Check the Task Detail section for real-time progress logs."
                    suggestions = ["What clusters are running?", "How to troubleshoot?"]

                elif status in ["failed", "error", "provisioning-failed"]:
                    response += "**⚠️ This cluster has failed**\n\n"
                    response += "**Troubleshooting steps:**\n"
                    response += f"1. View logs in Task Detail section\n"
                    response += f"2. Check `oc describe rosacontrolplane {name} -n {namespace}`\n"
                    response += f"3. Verify rosa-creds-secret exists in {namespace}\n"
                    response += f"4. Check ROSANetwork and ROSARoleConfig status\n"
                    suggestions = ["Troubleshoot failed cluster", "Provision new cluster"]

                elif status == "ready":
                    response += "**✅ Cluster is ready to use!**\n\n"
                    response += f"You can access it via the OpenShift console or CLI."
                    suggestions = ["Provision new cluster", "What is ROSA HCP?"]
                else:
                    suggestions = ["What clusters are running?", "Provision new cluster"]

            # Default fallback
            else:
                response = """I can help you with:

• **Cluster Management**: Provision, list, monitor, and troubleshoot clusters
• **ROSA/CAPI Concepts**: Explain ROSA HCP, CAPI, network automation, role automation
• **Troubleshooting**: Help diagnose and fix cluster issues

What would you like to know?"""
                suggestions = [
                    "What clusters are running?",
                    "How to provision cluster?",
                    "What is ROSA HCP?",
                    "Troubleshoot failed cluster",
                ]

        return {"response": response, "suggestions": suggestions}

    except Exception as e:
        import traceback

        print(f"❌ [AI-ASSISTANT] Error: {str(e)}")
        print(traceback.format_exc())
        return {
            "response": "Sorry, I encountered an error processing your request. Please try again.",
            "suggestions": [],
        }


# Test Suite Management
test_suite_runs: Dict[str, dict] = {}  # Store test suite execution history


class TestSuiteRun(BaseModel):
    suite_name: str
    extra_vars: dict = {}


@app.get("/api/test-suites/list")
async def list_test_suites():
    """List all available test suites"""
    try:
        project_root = os.environ.get("AUTOMATION_PATH") or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        test_suites_dir = os.path.join(project_root, "test-suites")

        if not os.path.exists(test_suites_dir):
            return {"success": True, "suites": [], "message": "No test suites directory found"}

        suites = []
        # Sort filenames to maintain numbered order (01-, 02-, 03-, etc.)
        for filename in sorted(os.listdir(test_suites_dir)):
            if filename.endswith(".json"):
                filepath = os.path.join(test_suites_dir, filename)
                with open(filepath, "r") as f:
                    suite_config = json.load(f)
                    suites.append({"id": filename.replace(".json", ""), "config": suite_config})

        return {"success": True, "suites": suites, "count": len(suites)}

    except Exception as e:
        return {"success": False, "message": f"Error listing test suites: {str(e)}", "suites": []}


@app.post("/api/test-suites/run")
async def run_test_suite(run_config: TestSuiteRun, background_tasks: BackgroundTasks):
    """Run a test suite"""
    try:
        project_root = os.environ.get("AUTOMATION_PATH") or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

        # Load suite configuration
        suite_file = os.path.join(project_root, "test-suites", f"{run_config.suite_name}.json")

        if not os.path.exists(suite_file):
            raise HTTPException(
                status_code=404, detail=f"Test suite '{run_config.suite_name}' not found"
            )

        with open(suite_file, "r") as f:
            suite_config = json.load(f)

        # Generate job ID (use jobs system for Task Summary integration)
        job_id = str(uuid.uuid4())

        # Initialize job in jobs system (will appear in Task Summary)
        jobs[job_id] = {
            "id": job_id,
            "type": "test-suite",
            "suite_name": run_config.suite_name,
            "suite_title": f"⚡ PLAYBOOK TESTING: {suite_config.get('name', run_config.suite_name)}",
            "description": suite_config.get("description", "Running automated playbook"),
            "status": "pending",
            "progress": 0,
            "message": f"🧪 Queued for execution",
            "started_at": datetime.now(),
            "completed_at": None,
            "playbook_results": [],
            "total_playbooks": len(suite_config.get("playbooks", [])),
            "completed_playbooks": 0,
            "failed_playbooks": 0,
            "logs": [],
            "environment": "mce",
        }

        # Run test suite in background
        def run_test_suite_background():
            try:
                job_data = jobs[job_id]
                job_data["status"] = "running"
                job_data["message"] = f"⚡ PLAYBOOK TESTING: Running {suite_config['name']}"
                job_data["logs"].append(f"🚀 ⚡ PLAYBOOK TESTING: {suite_config['name']}")
                job_data["logs"].append(f"📋 Description: {suite_config.get('description', 'N/A')}")
                job_data["logs"].append(f"📦 Total playbooks: {job_data['total_playbooks']}")
                job_data["logs"].append("")

                playbooks = suite_config.get("playbooks", [])
                stop_on_failure = suite_config.get("stopOnFailure", False)

                for idx, playbook_config in enumerate(playbooks, 1):
                    playbook_display_name = playbook_config["name"]
                    playbook_file = playbook_config.get("file", playbook_config["name"])
                    timeout = playbook_config.get("timeout", 600)
                    required = playbook_config.get("required", True)

                    job_data["progress"] = int((idx - 1) / len(playbooks) * 100)
                    job_data["message"] = (
                        f"Running playbook {idx}/{len(playbooks)}: {playbook_display_name}"
                    )
                    job_data["logs"].append(
                        f"\n[{idx}/{len(playbooks)}] Running: {playbook_display_name}"
                    )
                    job_data["logs"].append(f"📄 {playbook_config.get('description', '')}")
                    job_data["logs"].append(f"📁 File: {playbook_file}")
                    job_data["logs"].append(f"⏱️  Timeout: {timeout}s")

                    playbook_start = datetime.now()
                    playbook_result = {
                        "playbook": playbook_display_name,
                        "description": playbook_config.get("description"),
                        "status": "running",
                        "started_at": playbook_start,
                        "completed_at": None,
                        "duration": None,
                        "exit_code": None,
                        "output": "",
                        "error": "",
                    }

                    try:
                        # Run playbook using ansible-playbook directly to pass extra_vars
                        playbook_path = os.path.join(project_root, playbook_file)

                        if not os.path.exists(playbook_path):
                            raise Exception(f"Playbook not found: {playbook_path}")

                        # Execute playbook with environment variables
                        env = os.environ.copy()

                        # Set AUTOMATION_PATH to project root
                        env["AUTOMATION_PATH"] = project_root

                        # Try to read credentials from vars/user_vars.yml if not in environment
                        try:
                            import yaml

                            user_vars_path = os.path.join(project_root, "vars", "user_vars.yml")
                            if os.path.exists(user_vars_path):
                                with open(user_vars_path, "r") as f:
                                    user_vars = yaml.safe_load(f) or {}
                                    if "OCP_HUB_CLUSTER_USER" not in env or not env.get(
                                        "OCP_HUB_CLUSTER_USER"
                                    ):
                                        env["OCP_HUB_CLUSTER_USER"] = user_vars.get(
                                            "OCP_HUB_CLUSTER_USER", ""
                                        )
                                    if "OCP_HUB_CLUSTER_PASSWORD" not in env or not env.get(
                                        "OCP_HUB_CLUSTER_PASSWORD"
                                    ):
                                        env["OCP_HUB_CLUSTER_PASSWORD"] = user_vars.get(
                                            "OCP_HUB_CLUSTER_PASSWORD", ""
                                        )
                                    if "OCP_HUB_API_URL" not in env or not env.get(
                                        "OCP_HUB_API_URL"
                                    ):
                                        env["OCP_HUB_API_URL"] = user_vars.get(
                                            "OCP_HUB_API_URL", ""
                                        )
                        except Exception as e:
                            print(f"Warning: Could not read user_vars.yml: {e}")

                        # Build ansible-playbook command
                        cmd = [
                            "ansible-playbook",
                            "-i",
                            "localhost,",
                            "--connection=local",
                            playbook_file,
                            "-e",
                            "skip_ansible_runner=true",
                            "-e",
                            f"ocp_user={env.get('OCP_HUB_CLUSTER_USER', '')}",
                            "-e",
                            f"ocp_password={env.get('OCP_HUB_CLUSTER_PASSWORD', '')}",
                            "-e",
                            f"api_url={env.get('OCP_HUB_API_URL', '')}",
                            "-e",
                            f"mce_namespace=multicluster-engine",
                            "-e",
                            f"AUTOMATION_PATH={project_root}",
                        ]

                        # Add extra vars from provisioning modal if provided
                        if run_config.extra_vars:
                            for key, value in run_config.extra_vars.items():
                                # Convert boolean values to lowercase strings for ansible
                                if isinstance(value, bool):
                                    value = str(value).lower()
                                cmd.extend(["-e", f"{key}={value}"])

                        result = subprocess.run(
                            cmd,
                            cwd=project_root,
                            capture_output=True,
                            text=True,
                            timeout=timeout,
                            env=env,
                        )

                        playbook_end = datetime.now()
                        duration = (playbook_end - playbook_start).total_seconds()

                        playbook_result.update(
                            {
                                "status": "passed" if result.returncode == 0 else "failed",
                                "completed_at": playbook_end,
                                "duration": duration,
                                "exit_code": result.returncode,
                                "output": result.stdout,
                                "error": result.stderr,
                            }
                        )

                        if result.returncode == 0:
                            job_data["logs"].append(f"✅ PASSED ({duration:.1f}s)")
                            job_data["completed_playbooks"] += 1
                        else:
                            job_data["logs"].append(f"❌ FAILED ({duration:.1f}s)")
                            job_data["logs"].append(f"Error: {result.stderr[:200]}")
                            job_data["failed_playbooks"] += 1

                            if required and stop_on_failure:
                                job_data["logs"].append(
                                    f"\n⚠️  Stopping test suite due to required playbook failure"
                                )
                                job_data["playbook_results"].append(playbook_result)
                                break

                    except subprocess.TimeoutExpired:
                        playbook_result.update(
                            {
                                "status": "timeout",
                                "completed_at": datetime.now(),
                                "duration": timeout,
                                "error": f"Playbook timed out after {timeout}s",
                            }
                        )
                        job_data["logs"].append(f"⏱️  TIMEOUT after {timeout}s")
                        job_data["failed_playbooks"] += 1

                        if required and stop_on_failure:
                            job_data["logs"].append(f"\n⚠️  Stopping test suite due to timeout")
                            job_data["playbook_results"].append(playbook_result)
                            break

                    except Exception as e:
                        playbook_result.update(
                            {"status": "error", "completed_at": datetime.now(), "error": str(e)}
                        )
                        job_data["logs"].append(f"💥 ERROR: {str(e)}")
                        job_data["failed_playbooks"] += 1

                        if required and stop_on_failure:
                            job_data["logs"].append(f"\n⚠️  Stopping test suite due to error")
                            job_data["playbook_results"].append(playbook_result)
                            break

                    job_data["playbook_results"].append(playbook_result)

                # Finalize run
                job_data["completed_at"] = datetime.now()
                job_data["progress"] = 100

                total_duration = (job_data["completed_at"] - job_data["started_at"]).total_seconds()

                if job_data["failed_playbooks"] == 0:
                    job_data["status"] = "completed"
                    job_data["message"] = (
                        f"⚡ PLAYBOOK TESTING: Playbook passed! ({total_duration:.1f}s)"
                    )
                    job_data["logs"].append(f"\n✅ ⚡ PLAYBOOK TESTING COMPLETE: Playbook passed!")
                else:
                    job_data["status"] = "failed"
                    job_data["message"] = (
                        f"⚡ PLAYBOOK TESTING: Playbook failed ({total_duration:.1f}s)"
                    )
                    job_data["logs"].append(f"\n❌ ⚡ PLAYBOOK TESTING COMPLETE: Playbook failed")

                job_data["logs"].append(f"\n📊 Summary:")
                job_data["logs"].append(f"   Total: {job_data['total_playbooks']}")
                job_data["logs"].append(f"   Passed: {job_data['completed_playbooks']}")
                job_data["logs"].append(f"   Failed: {job_data['failed_playbooks']}")
                job_data["logs"].append(f"   Duration: {total_duration:.1f}s")

            except Exception as e:
                import traceback

                job_data["status"] = "error"
                job_data["message"] = f"Test suite error: {str(e)}"
                job_data["logs"].append(f"\n💥 Fatal error: {str(e)}")
                job_data["logs"].append(traceback.format_exc())
                job_data["completed_at"] = datetime.now()

        # Start background task (use asyncio.to_thread to avoid blocking event loop)
        asyncio.create_task(asyncio.to_thread(run_test_suite_background))

        return {
            "success": True,
            "job_id": job_id,
            "run_id": job_id,  # Keep for backwards compatibility
            "message": f"⚡ PLAYBOOK TESTING: {suite_config['name']} started",
            "suite_name": suite_config["name"],
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback

        print(f"❌ Error starting test suite: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error starting test suite: {str(e)}")


@app.get("/api/test-suites/status/{run_id}")
async def get_test_suite_status(run_id: str):
    """Get status of a running or completed test suite"""
    try:
        if run_id not in test_suite_runs:
            raise HTTPException(status_code=404, detail=f"Test suite run '{run_id}' not found")

        run_data = test_suite_runs[run_id]

        return {"success": True, "run": run_data}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting test suite status: {str(e)}")


@app.get("/api/test-suites/history")
async def get_test_suite_history():
    """Get history of all test suite runs"""
    try:
        # Sort by started_at descending (newest first)
        sorted_runs = sorted(
            test_suite_runs.values(), key=lambda x: x.get("started_at", datetime.min), reverse=True
        )

        return {"success": True, "runs": sorted_runs, "count": len(sorted_runs)}

    except Exception as e:
        return {
            "success": False,
            "message": f"Error getting test suite history: {str(e)}",
            "runs": [],
        }


# ============================================================================
# Workflow Management API
# ============================================================================

WORKFLOWS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "vars", "saved_workflows.json"
)


def _load_workflows():
    """Load saved workflows from disk"""
    if not os.path.exists(WORKFLOWS_FILE):
        return []
    try:
        with open(WORKFLOWS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_workflows(workflows):
    """Persist workflows to disk"""
    os.makedirs(os.path.dirname(WORKFLOWS_FILE), exist_ok=True)
    with open(WORKFLOWS_FILE, "w") as f:
        json.dump(workflows, f, indent=2, default=str)


class WorkflowSave(BaseModel):
    name: str
    description: str = ""
    stopOnFailure: bool = True
    globalVars: dict = {}
    steps: list = []


@app.get("/api/workflows")
async def list_workflows():
    """List all saved workflows"""
    workflows = _load_workflows()
    # Return summary info (strip globalVars values for security)
    summaries = []
    for wf in workflows:
        summaries.append({
            "id": wf.get("id"),
            "name": wf.get("name"),
            "description": wf.get("description", ""),
            "stepCount": len(wf.get("steps", [])),
            "stepNames": [s.get("name", "") for s in wf.get("steps", [])],
            "hasGlobalVars": len(wf.get("globalVars", {})) > 0,
            "globalVarKeys": list(wf.get("globalVars", {}).keys()),
            "stopOnFailure": wf.get("stopOnFailure", True),
            "savedAt": wf.get("savedAt"),
            "lastRunAt": wf.get("lastRunAt"),
        })
    return {"success": True, "workflows": summaries, "count": len(summaries)}


@app.get("/api/workflows/{workflow_id}")
async def get_workflow(workflow_id: str):
    """Get a single workflow by ID (includes full details)"""
    workflows = _load_workflows()
    wf = next((w for w in workflows if w.get("id") == workflow_id), None)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"success": True, "workflow": wf}


@app.post("/api/workflows")
async def save_workflow(workflow: WorkflowSave):
    """Save a new workflow or update existing one with same name"""
    workflows = _load_workflows()

    # Check for existing workflow with same name
    existing_idx = next((i for i, w in enumerate(workflows) if w.get("name") == workflow.name), None)

    wf_data = {
        "id": workflows[existing_idx]["id"] if existing_idx is not None else f"wf-{uuid.uuid4().hex[:12]}",
        "name": workflow.name,
        "description": workflow.description,
        "stopOnFailure": workflow.stopOnFailure,
        "globalVars": workflow.globalVars,
        "steps": workflow.steps,
        "savedAt": datetime.now().isoformat(),
    }

    if existing_idx is not None:
        # Preserve lastRunAt from existing
        wf_data["lastRunAt"] = workflows[existing_idx].get("lastRunAt")
        workflows[existing_idx] = wf_data
    else:
        workflows.append(wf_data)

    _save_workflows(workflows)
    return {"success": True, "workflow": wf_data, "updated": existing_idx is not None}


@app.put("/api/workflows/{workflow_id}")
async def update_workflow(workflow_id: str, workflow: WorkflowSave):
    """Update an existing workflow by ID"""
    workflows = _load_workflows()
    idx = next((i for i, w in enumerate(workflows) if w.get("id") == workflow_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflows[idx].update({
        "name": workflow.name,
        "description": workflow.description,
        "stopOnFailure": workflow.stopOnFailure,
        "globalVars": workflow.globalVars,
        "steps": workflow.steps,
        "savedAt": datetime.now().isoformat(),
    })

    _save_workflows(workflows)
    return {"success": True, "workflow": workflows[idx]}


@app.delete("/api/workflows/{workflow_id}")
async def delete_workflow(workflow_id: str):
    """Delete a saved workflow"""
    workflows = _load_workflows()
    updated = [w for w in workflows if w.get("id") != workflow_id]
    if len(updated) == len(workflows):
        raise HTTPException(status_code=404, detail="Workflow not found")
    _save_workflows(updated)
    return {"success": True, "deleted": workflow_id}


@app.post("/api/workflows/{workflow_id}/duplicate")
async def duplicate_workflow(workflow_id: str):
    """Duplicate an existing workflow with a new name"""
    workflows = _load_workflows()
    source = next((w for w in workflows if w.get("id") == workflow_id), None)
    if not source:
        raise HTTPException(status_code=404, detail="Workflow not found")

    new_wf = {
        **source,
        "id": f"wf-{uuid.uuid4().hex[:12]}",
        "name": f"{source['name']} (copy)",
        "savedAt": datetime.now().isoformat(),
        "lastRunAt": None,
    }
    workflows.append(new_wf)
    _save_workflows(workflows)
    return {"success": True, "workflow": new_wf}


@app.post("/api/workflows/{workflow_id}/run")
async def mark_workflow_run(workflow_id: str):
    """Record that a workflow was run (updates lastRunAt)"""
    workflows = _load_workflows()
    idx = next((i for i, w in enumerate(workflows) if w.get("id") == workflow_id), None)
    if idx is not None:
        workflows[idx]["lastRunAt"] = datetime.now().isoformat()
        _save_workflows(workflows)
    return {"success": True}


@app.get("/api/workflows/templates/list")
async def list_workflow_templates():
    """Return built-in workflow templates"""
    templates = [
        {
            "id": "tpl-full-e2e",
            "name": "Full E2E (Provision + Delete)",
            "description": "Complete end-to-end test: validate environment, provision a ROSA HCP cluster, verify it, then delete and clean up.",
            "icon": "rocket",
            "steps": [
                {"name": "Validate CAPA Environment", "file": "playbooks/validate-capa-environment.yml", "onFailure": "stop", "timeout": 120, "extra_vars": {}},
                {"name": "Provision ROSA HCP Cluster", "file": "playbooks/provision_rosa_hcp_cluster.yml", "onFailure": "stop", "timeout": 2400, "extra_vars": {}},
                {"name": "Verify ROSA HCP Cluster", "file": "playbooks/verify_rosa_hcp_cluster.yml", "onFailure": "skip", "timeout": 600, "extra_vars": {}},
                {"name": "Delete ROSA HCP Cluster", "file": "playbooks/delete_rosa_hcp_cluster.yml", "onFailure": "stop", "timeout": 2400, "extra_vars": {}},
            ],
            "globalVars": {},
            "stopOnFailure": True,
        },
        {
            "id": "tpl-provision-only",
            "name": "Provision Only",
            "description": "Validate the environment and provision a ROSA HCP cluster.",
            "icon": "server",
            "steps": [
                {"name": "Validate CAPA Environment", "file": "playbooks/validate-capa-environment.yml", "onFailure": "stop", "timeout": 120, "extra_vars": {}},
                {"name": "Provision ROSA HCP Cluster", "file": "playbooks/provision_rosa_hcp_cluster.yml", "onFailure": "stop", "timeout": 2400, "extra_vars": {}},
            ],
            "globalVars": {},
            "stopOnFailure": True,
        },
        {
            "id": "tpl-delete-cleanup",
            "name": "Delete + Cleanup",
            "description": "Delete a ROSA HCP cluster and clean up any orphaned AWS resources.",
            "icon": "trash",
            "steps": [
                {"name": "Delete ROSA HCP Cluster", "file": "playbooks/delete_rosa_hcp_cluster.yml", "onFailure": "skip", "timeout": 2400, "extra_vars": {}},
            ],
            "globalVars": {},
            "stopOnFailure": False,
        },
        {
            "id": "tpl-validate-env",
            "name": "Validate Environment",
            "description": "Run all validation checks to ensure your CAPA environment is properly configured.",
            "icon": "check",
            "steps": [
                {"name": "Validate CAPA Environment", "file": "playbooks/validate-capa-environment.yml", "onFailure": "stop", "timeout": 120, "extra_vars": {"soft_verify": "true"}},
            ],
            "globalVars": {},
            "stopOnFailure": True,
        },
    ]
    return {"success": True, "templates": templates}


# ============================================================================
# Cluster Actions / Feature Action Engine API
# ============================================================================

# Feature registry: delegates to shared capa_core (single source of truth)
# These thin wrappers preserve the existing API surface used throughout this file.

def _load_feature_registry_full():
    """Load the full feature registry YAML (delegates to shared registry)."""
    _shared_registry.refresh()
    return _shared_registry.raw_data


def _load_feature_registry():
    """Load feature registry suites (for backward compat). Returns dict with 'suites' key."""
    _shared_registry.refresh()
    return {"suites": _shared_registry.suites}


def _get_registry():
    """Get the live feature registry (refreshed on file change via mtime cache)."""
    return _load_feature_registry()


def _get_feature_index():
    """Get the live feature index (auto-refreshed via shared registry)."""
    _shared_registry.refresh()
    return _shared_registry.all_features()


# Backward-compat module-level variables (used by tests)
CLUSTER_FEATURE_REGISTRY = _load_feature_registry()
_FEATURE_INDEX = _get_feature_index()


def _validate_cluster_name(name: str) -> Optional[str]:
    return _core_validate_cluster_name(name)


def _validate_feature_value(feature: dict, value) -> Optional[str]:
    return _core_validate_feature_value(feature, value)


@app.get("/api/cluster-actions/features")
async def get_feature_registry():
    """Return the full feature registry organized by suite groupings"""
    return {"success": True, "registry": _get_registry()}


@app.get("/api/cluster-actions/features/{suite_id}")
async def get_suite_features(suite_id: str):
    """Return features for a specific suite"""
    registry = _get_registry()
    for suite in registry["suites"]:
        if suite["id"] == suite_id:
            return {"success": True, "suite": suite}
    raise HTTPException(status_code=404, detail=f"Suite '{suite_id}' not found")


class ClusterActionRequest(BaseModel):
    cluster_name: str
    namespace: str = "ns-rosa-hcp"
    actions: list  # [{feature_id, target_value}]


# --- Action History Persistence ---
ACTION_HISTORY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "vars", "cluster_action_history.json"
)


def _load_action_history():
    if not os.path.exists(ACTION_HISTORY_FILE):
        return []
    try:
        with open(ACTION_HISTORY_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save_action_history(history):
    os.makedirs(os.path.dirname(ACTION_HISTORY_FILE), exist_ok=True)
    # Cap at 200 entries
    with open(ACTION_HISTORY_FILE, "w") as f:
        json.dump(history[-200:], f, indent=2, default=str)


def _record_action(cluster_name, namespace, feature_id, feature_name, target_value, status, job_id=None, message=""):
    history = _load_action_history()
    history.append({
        "id": str(uuid.uuid4())[:8],
        "cluster_name": cluster_name,
        "namespace": namespace,
        "feature_id": feature_id,
        "feature_name": feature_name,
        "target_value": target_value,
        "status": status,
        "job_id": job_id,
        "message": message,
        "timestamp": datetime.now().isoformat(),
    })
    _save_action_history(history)


def _find_feature(feature_id):
    """Look up a feature in the registry by ID (O(1) index lookup, auto-refreshed)."""
    return _get_feature_index().get(feature_id)


def _build_json_merge_patch(k8s_field: str, value) -> dict:
    return _core_build_json_merge_patch(k8s_field, value)


# Per-cluster lock to prevent concurrent operations on the same cluster
_cluster_locks: Dict[str, asyncio.Lock] = {}
_CLUSTER_LOCKS_MAX = 100


def _get_cluster_lock(cluster_name: str) -> asyncio.Lock:
    """Get or create an asyncio.Lock for a cluster (prevents concurrent operations)."""
    if cluster_name not in _cluster_locks:
        # Evict unlocked entries if we've exceeded the max
        if len(_cluster_locks) >= _CLUSTER_LOCKS_MAX:
            stale = [k for k, v in _cluster_locks.items() if not v.locked()]
            for k in stale:
                del _cluster_locks[k]
        _cluster_locks[cluster_name] = asyncio.Lock()
    return _cluster_locks[cluster_name]



# Per-cluster lock to prevent concurrent operations on the same cluster
_cluster_locks: Dict[str, asyncio.Lock] = {}


def _get_cluster_lock(cluster_name: str) -> asyncio.Lock:
    """Get or create an asyncio.Lock for a cluster (prevents concurrent operations)."""
    if cluster_name not in _cluster_locks:
        _cluster_locks[cluster_name] = asyncio.Lock()
    return _cluster_locks[cluster_name]


@app.post("/api/cluster-actions/execute")
async def execute_cluster_actions(request: ClusterActionRequest):
    """
    Execute a batch of feature actions on a cluster.
    Playbook-backed actions are run via the job system with live polling.
    K8s patch actions are executed directly via oc patch.
    Uses per-cluster locking to prevent concurrent conflicting operations.
    """
    # Validate cluster name
    name_err = _validate_cluster_name(request.cluster_name)
    if name_err:
        raise HTTPException(status_code=400, detail=name_err)

    lock = _get_cluster_lock(request.cluster_name)
    if lock.locked():
        raise HTTPException(status_code=409, detail=f"Cluster '{request.cluster_name}' has an operation in progress. Please wait.")

    async with lock:
        return await _execute_cluster_actions_locked(request)


async def _execute_cluster_actions_locked(request: ClusterActionRequest):
    """Inner execution logic, called while holding the per-cluster lock."""
    results = []

    for action in request.actions:
        feature_id = action.get("feature_id")
        target_value = action.get("target_value")
        feature = _find_feature(feature_id)

        if not feature:
            results.append({"feature_id": feature_id, "status": "error", "message": f"Unknown feature: {feature_id}"})
            continue

        if not feature.get("mutable"):
            results.append({"feature_id": feature_id, "status": "error", "message": f"Feature '{feature['name']}' is immutable (set at creation time only)"})
            continue

        # Validate target_value against feature type
        if target_value is not None:
            val_err = _validate_feature_value(feature, target_value)
            if val_err:
                results.append({"feature_id": feature_id, "status": "error", "message": val_err})
                continue

        # If feature has a playbook, run it through the job system
        if feature.get("playbook"):
            extra_vars = {
                "cluster_name": request.cluster_name,
                "capi_namespace": request.namespace,
            }
            if target_value is not None:
                if feature_id in ("control_plane_upgrade", "machine_pool_upgrade"):
                    extra_vars["requested_version"] = str(target_value)

            try:
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                playbook_path = os.path.join(project_root, feature["playbook"])
                if not os.path.exists(playbook_path):
                    results.append({"feature_id": feature_id, "status": "error", "message": f"Playbook not found: {feature['playbook']}"})
                    continue

                job_id = str(uuid.uuid4())
                description = f"[ClusterAction] {feature['name']} on {request.cluster_name}"

                # Create job in the job system
                jobs[job_id] = {
                    "id": job_id,
                    "status": "pending",
                    "progress": 0,
                    "message": f"Queued: {description}",
                    "logs": [],
                    "created_at": datetime.now(),
                    "playbook": feature["playbook"],
                    "description": description,
                }

                init_ai_agents(job_id)

                # Launch the playbook asynchronously
                asyncio.create_task(
                    run_playbook_background(feature["playbook"], extra_vars, job_id, description)
                )

                results.append({
                    "feature_id": feature_id,
                    "status": "running",
                    "job_id": job_id,
                    "playbook": feature["playbook"],
                    "message": f"Started {feature['name']}",
                    "target_value": target_value,
                    "current_value": extra_vars.get("current_version", ""),
                    "wait_timeout": feature.get("wait_timeout", 600),
                    "wait_resource": feature.get("wait_resource"),
                    "wait_field": feature.get("wait_field"),
                    "wait_value": feature.get("wait_value"),
                })

                _record_action(request.cluster_name, request.namespace, feature_id,
                               feature["name"], target_value, "running", job_id, f"Playbook: {feature['playbook']}")

            except Exception as e:
                results.append({"feature_id": feature_id, "status": "error", "message": str(e)})
                _record_action(request.cluster_name, request.namespace, feature_id,
                               feature["name"], target_value, "error", message=str(e))
        else:
            # K8s patch action — execute via oc patch
            resource = feature.get("resource", "")
            field = feature.get("k8s_field", "")
            patch_status = "queued"
            patch_message = ""

            if resource and field:
                try:
                    patch_obj = _build_json_merge_patch(field, target_value)
                    patch_json = json.dumps(patch_obj)
                    resource_name = resource.lower()

                    cmd = [
                        "oc", "patch", resource_name, request.cluster_name,
                        "-n", request.namespace,
                        "--type=merge", "-p", patch_json,
                    ]

                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                    if result.returncode == 0:
                        patch_status = "completed"
                        patch_message = f"Patched {resource} {field} = {target_value}"
                    else:
                        patch_status = "error"
                        patch_message = result.stderr.strip() or "Patch failed"

                except subprocess.TimeoutExpired:
                    patch_status = "error"
                    patch_message = "Timeout executing oc patch"
                except Exception as e:
                    patch_status = "error"
                    patch_message = str(e)
            else:
                patch_message = f"No resource/field defined for {feature_id}"

            results.append({
                "feature_id": feature_id,
                "status": patch_status,
                "message": patch_message,
                "resource": resource,
                "field": field,
                "target_value": target_value,
            })

            _record_action(request.cluster_name, request.namespace, feature_id,
                           feature["name"], target_value, patch_status, message=patch_message)

    return {
        "success": True,
        "cluster_name": request.cluster_name,
        "namespace": request.namespace,
        "action_count": len(results),
        "results": results,
    }


@app.get("/api/cluster-actions/history")
async def get_action_history(cluster_name: str = ""):
    """Get action history, optionally filtered by cluster name"""
    history = _load_action_history()
    if cluster_name:
        history = [h for h in history if h.get("cluster_name") == cluster_name]
    # Return most recent first
    return {"success": True, "history": list(reversed(history)), "count": len(history)}


@app.post("/api/cluster-actions/provision")
async def provision_cluster_with_features(request: dict, background_tasks: BackgroundTasks):
    """
    Provision a new ROSA HCP cluster with Day1 features pre-configured.
    Translates selected features into extra_vars for the provision playbook.
    """
    cluster_name = request.get("cluster_name", "")
    name_prefix = request.get("name_prefix", "")
    namespace = request.get("namespace", "ns-rosa-hcp")
    features = request.get("features", {})  # {feature_id: target_value}

    if not cluster_name and not name_prefix:
        raise HTTPException(status_code=400, detail="cluster_name or name_prefix required")

    # Validate cluster name format if provided
    if cluster_name:
        name_err = _validate_cluster_name(cluster_name)
        if name_err:
            raise HTTPException(status_code=400, detail=name_err)

    # Build extra_vars from selected features
    extra_vars = {
        "capi_namespace": namespace,
    }
    if name_prefix:
        extra_vars["name_prefix"] = name_prefix
    if cluster_name:
        extra_vars["cluster_name"] = cluster_name

    # Map features to provision playbook extra_vars using registry var_map
    registry_data = _load_feature_registry_full()
    var_map = registry_data.get("var_map", {})

    for feature_id, target_value in features.items():
        var_name = var_map.get(feature_id, feature_id)
        if target_value is not None:
            extra_vars[var_name] = target_value

    # Use the provision playbook
    playbook = "playbooks/create_rosa_hcp_cluster.yml"
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    playbook_path = os.path.join(project_root, playbook)

    if not os.path.exists(playbook_path):
        raise HTTPException(status_code=404, detail=f"Playbook not found: {playbook}")

    job_id = str(uuid.uuid4())
    effective_name = cluster_name or f"{name_prefix}-rosa-hcp"
    description = f"[ClusterAction] Provision {effective_name}"

    jobs[job_id] = {
        "id": job_id,
        "status": "pending",
        "progress": 0,
        "message": f"Queued: {description}",
        "logs": [],
        "created_at": datetime.now(),
        "playbook": playbook,
        "description": description,
    }

    init_ai_agents(job_id)
    asyncio.create_task(run_playbook_background(playbook, extra_vars, job_id, description))

    _record_action(effective_name, namespace, "provision",
                   "Provision New Cluster", json.dumps(features), "running", job_id,
                   f"Features: {', '.join(features.keys()) if features else 'defaults'}")

    return {
        "success": True,
        "job_id": job_id,
        "cluster_name": effective_name,
        "namespace": namespace,
        "features_applied": list(features.keys()),
        "extra_vars_count": len(extra_vars),
    }


@app.get("/api/cluster-actions/discover")
async def discover_clusters(namespace: str = ""):
    """
    Discover all ROSAControlPlane clusters across namespaces (or in a specific namespace).
    Returns a list of clusters with basic status info.
    """
    clusters = []
    try:
        cmd = ["oc", "get", "rosacontrolplane", "-o", "json"]
        if namespace:
            cmd.extend(["-n", namespace])
        else:
            cmd.append("--all-namespaces")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            for item in data.get("items", []):
                meta = item.get("metadata", {})
                spec = item.get("spec", {})
                status = item.get("status", {})
                clusters.append({
                    "name": meta.get("name", "unknown"),
                    "namespace": meta.get("namespace", ""),
                    "version": spec.get("version", ""),
                    "ready": status.get("ready", False),
                    "channel_group": spec.get("channelGroup", "stable"),
                    "available_upgrades": status.get("availableUpgrades", []),
                    "domain_prefix": spec.get("domainPrefix", ""),
                    "endpoint_access": spec.get("endpointAccess", "public"),
                    "created": meta.get("creationTimestamp", ""),
                })
        else:
            return {"success": False, "clusters": [], "error": result.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"success": False, "clusters": [], "error": "Timeout querying clusters"}
    except Exception as e:
        return {"success": False, "clusters": [], "error": str(e)}

    return {"success": True, "clusters": clusters, "count": len(clusters)}


@app.get("/api/cluster-actions/cluster/{cluster_name}/status")
async def get_cluster_feature_status(cluster_name: str, namespace: str = "ns-rosa-hcp"):
    """
    Get current feature values for a cluster by reading K8s resources.
    Returns the live state of all features.
    """
    status = {}
    try:
        # Get ROSAControlPlane
        result = subprocess.run(
            ["oc", "get", "rosacontrolplane", cluster_name, "-n", namespace, "-o", "json"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            cp = json.loads(result.stdout)
            spec = cp.get("spec", {})
            cp_status = cp.get("status", {})
            status["cluster_found"] = True
            status["version"] = spec.get("version", "unknown")
            status["ready"] = cp_status.get("ready", False)
            status["available_upgrades"] = cp_status.get("availableUpgrades", [])
            status["endpoint_access"] = spec.get("endpointAccess", "public")
            status["channel_group"] = spec.get("channelGroup", "stable")
            status["domain_prefix"] = spec.get("domainPrefix", "")
            status["etcd_kms"] = bool(spec.get("etcdEncryptionKMSARN"))
            status["additional_tags"] = spec.get("additionalTags", {})
        else:
            status["cluster_found"] = False
            status["error"] = result.stderr.strip()

        # Get ROSAMachinePool
        result2 = subprocess.run(
            ["oc", "get", "rosamachinepool", "-n", namespace, "-l", f"cluster.x-k8s.io/cluster-name={cluster_name}", "-o", "json"],
            capture_output=True, text=True, timeout=15
        )
        if result2.returncode == 0:
            pools = json.loads(result2.stdout)
            pool_items = pools.get("items", [])
            status["machine_pools"] = []
            for pool in pool_items:
                pool_spec = pool.get("spec", {})
                pool_status = pool.get("status", {})
                status["machine_pools"].append({
                    "name": pool.get("metadata", {}).get("name", "unknown"),
                    "version": pool_spec.get("version", ""),
                    "instance_type": pool_spec.get("instanceType", ""),
                    "replicas": pool_spec.get("replicas"),
                    "autoscaling": pool_spec.get("autoscaling"),
                    "ready": pool_status.get("ready", False),
                    "available_upgrades": pool_status.get("availableUpgrades", []),
                })

    except subprocess.TimeoutExpired:
        status["cluster_found"] = False
        status["error"] = "Timeout querying cluster"
    except Exception as e:
        status["cluster_found"] = False
        status["error"] = str(e)

    return {"success": True, "cluster_name": cluster_name, "namespace": namespace, "status": status}


# ============================================================================
# ClusterAutomationSpec API - Declarative cluster lifecycle
# ============================================================================

SPECS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "specs"
)

def _resolve_spec_to_plan(spec_data: dict) -> list:
    """Resolve a ClusterAutomationSpec into an execution plan (delegates to capa_core)."""
    spec = _CoreClusterAutomationSpec(spec_data)
    return _core_resolve_spec_to_plan(_shared_registry, spec)


@app.get("/api/cluster-specs")
async def list_cluster_specs():
    """List available ClusterAutomationSpec specs by category."""
    specs = []
    if os.path.isdir(SPECS_DIR):
        for root, dirs, files in os.walk(SPECS_DIR):
            category = os.path.basename(root) if root != SPECS_DIR else "uncategorized"
            for fname in sorted(files):
                if not (fname.endswith(".yml") or fname.endswith(".yaml")):
                    continue
                try:
                    with open(os.path.join(root, fname)) as f:
                        data = yaml.safe_load(f)
                    spec_section = data.get("spec", {})
                    specs.append({
                        "id": os.path.splitext(fname)[0],
                        "name": data.get("metadata", {}).get("name", fname),
                        "action": spec_section.get("action", ""),
                        "features": list(spec_section.get("features", {}).keys()),
                        "version": spec_section.get("version", ""),
                        "region": spec_section.get("region", ""),
                        "category": category,
                    })
                except Exception:
                    continue
    return {"success": True, "specs": specs}


def _find_spec_file(spec_id: str) -> str:
    """Search specs/ subdirectories for a spec by ID."""
    for root, dirs, files in os.walk(SPECS_DIR):
        for ext in (".yml", ".yaml"):
            candidate = os.path.join(root, f"{spec_id}{ext}")
            if os.path.exists(candidate):
                return candidate
    return ""


@app.get("/api/cluster-specs/{spec_id}")
async def get_cluster_spec(spec_id: str):
    """Get a specific ClusterAutomationSpec by ID."""
    spec_path = _find_spec_file(spec_id)
    if not spec_path:
        return {"success": False, "error": f"Spec not found: {spec_id}"}
    try:
        with open(spec_path) as f:
            data = yaml.safe_load(f)
        return {"success": True, "spec": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/cluster-specs/plan")
async def plan_cluster_spec(request: Request):
    """Resolve a ClusterAutomationSpec into an execution plan (dry run)."""
    body = await request.json()
    spec_data = body.get("spec")

    # If spec_id provided, load from file
    if not spec_data and body.get("spec_id"):
        spec_path = _find_spec_file(body["spec_id"])
        if spec_path:
            with open(spec_path) as f:
                spec_data = yaml.safe_load(f)

    if not spec_data:
        return {"success": False, "error": "No spec provided"}

    # Apply overrides
    overrides = body.get("overrides", {})
    for k, v in overrides.items():
        if k in ("cluster", "namespace", "version", "region", "channel", "name_prefix", "action"):
            spec_data.setdefault("spec", {})[k] = v

    try:
        plan = _resolve_spec_to_plan(spec_data)
        return {"success": True, "plan": plan, "step_count": len(plan)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/cluster-specs/execute")
async def execute_cluster_spec(request: Request):
    """Execute a ClusterAutomationSpec — resolves to plan and runs each step."""
    body = await request.json()
    spec_data = body.get("spec")

    if not spec_data and body.get("spec_id"):
        spec_path = _find_spec_file(body["spec_id"])
        if spec_path:
            with open(spec_path) as f:
                spec_data = yaml.safe_load(f)

    if not spec_data:
        return {"success": False, "error": "No spec provided"}

    overrides = body.get("overrides", {})
    for k, v in overrides.items():
        if k in ("cluster", "namespace", "version", "region", "channel", "name_prefix", "action"):
            spec_data.setdefault("spec", {})[k] = v

    try:
        plan = _resolve_spec_to_plan(spec_data)
    except Exception as e:
        return {"success": False, "error": str(e)}

    # Execute each step through the existing job system
    results = []
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    for step in plan:
        if step["type"] == "playbook":
            playbook_path = os.path.join(project_root, step["playbook"])
            if not os.path.exists(playbook_path):
                results.append({"step": step["step"], "name": step["name"],
                                "status": "error", "message": f"Playbook not found: {step['playbook']}"})
                continue

            job_id = str(uuid.uuid4())
            description = f"[Spec] {step['name']}"
            jobs[job_id] = {
                "id": job_id, "status": "pending", "progress": 0,
                "message": f"Queued: {description}", "logs": [],
                "created_at": datetime.now(), "playbook": step["playbook"],
                "description": description,
            }
            init_ai_agents(job_id)
            asyncio.create_task(
                run_playbook_background(step["playbook"], step.get("extra_vars", {}), job_id, description)
            )
            results.append({
                "step": step["step"], "name": step["name"],
                "status": "running", "job_id": job_id,
                "feature": step.get("feature", ""),
                "depends_on": step.get("depends_on"),
                "playbook": step["playbook"],
            })

        elif step["type"] == "patch":
            resource = step.get("resource", "").lower()
            field = step.get("k8s_field", "")
            value = step.get("value")
            cluster = step.get("cluster", "")
            namespace = step.get("namespace", "ns-rosa-hcp")

            patch_obj = _build_json_merge_patch(field, value)
            cmd = ["oc", "patch", resource, cluster, "-n", namespace,
                   "--type=merge", "-p", json.dumps(patch_obj)]

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                if result.returncode == 0:
                    results.append({"step": step["step"], "name": step["name"],
                                    "status": "completed", "feature": step.get("feature", "")})
                else:
                    results.append({"step": step["step"], "name": step["name"],
                                    "status": "error", "message": result.stderr.strip(),
                                    "feature": step.get("feature", "")})
            except Exception as e:
                results.append({"step": step["step"], "name": step["name"],
                                "status": "error", "message": str(e),
                                "feature": step.get("feature", "")})

    return {
        "success": True,
        "spec_name": spec_data.get("metadata", {}).get("name", ""),
        "action": spec_data.get("spec", {}).get("action", ""),
        "step_count": len(plan),
        "results": results,
    }


@app.post("/api/cluster-specs/save")
async def save_cluster_spec(request: Request):
    """Save a ClusterAutomationSpec to the specs directory."""
    body = await request.json()
    spec_data = body.get("spec")
    spec_id = body.get("id", "")

    if not spec_data or not spec_id:
        return {"success": False, "error": "spec and id required"}

    # Sanitize filename
    safe_id = "".join(c for c in spec_id if c.isalnum() or c in "-_").strip()
    if not safe_id:
        return {"success": False, "error": "Invalid spec id"}

    # Determine category subdirectory based on action
    action = spec_data.get("spec", {}).get("action", "apply")
    category = body.get("category", "")
    if not category:
        category = "profiles" if action == "create" else "features"
    save_dir = os.path.join(SPECS_DIR, category)
    os.makedirs(save_dir, exist_ok=True)
    spec_path = os.path.join(save_dir, f"{safe_id}.yml")

    try:
        with open(spec_path, "w") as f:
            yaml.dump(spec_data, f, default_flow_style=False, sort_keys=False)
        return {"success": True, "id": safe_id, "path": spec_path}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# MCE Environment Management API
# ============================================================================


@app.get("/api/mce-environments")
async def list_mce_environments(platform: Optional[str] = None, status: Optional[str] = None):
    """
    List all saved MCE test environments with optional filtering.

    Query Parameters:
        platform: Filter by platform (e.g., "IBM Power", "AWS-ARM")
        status: Filter by test status (pass, fail, blocked, in_progress, unknown)
    """
    try:
        import sys

        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "scripts")
        sys.path.insert(0, scripts_dir)

        from mce_env_manager import MCEEnvManager

        manager = MCEEnvManager()
        envs = manager.list_environments(platform_filter=platform, status_filter=status)

        # Format for frontend
        formatted_envs = []
        for env in envs:
            data = env.get("data", {})
            cluster_data = data.get("cluster", {})
            notification = data.get("notification", {})

            formatted_envs.append(
                {
                    "clusterName": env.get("cluster_name"),
                    "platform": env.get("platform"),
                    "status": env.get("status"),
                    "notes": env.get("notes", ""),
                    "addedDate": env.get("added_date"),
                    "lastAccessed": env.get("last_accessed"),
                    "ocpVersion": cluster_data.get("ocp_version"),
                    "mceVersion": cluster_data.get("mce_version"),
                    "acmVersion": cluster_data.get("acm_version"),
                    "clusterStatus": cluster_data.get("status"),
                    "password": cluster_data.get("password"),
                    "consoleUrl": cluster_data.get("console_url"),
                    "jira": notification.get("jira"),
                    "polarion": notification.get("polarion"),
                    "totalFailures": notification.get("total_failures", 0),
                    "components": notification.get("components", {}),
                }
            )

        return {"success": True, "environments": formatted_envs, "total": len(formatted_envs)}

    except Exception as e:
        print(f"❌ Error listing MCE environments: {str(e)}")
        import traceback

        traceback.print_exc()
        return {
            "success": False,
            "message": f"Error listing environments: {str(e)}",
            "environments": [],
            "total": 0,
        }


@app.get("/api/mce-environments/{cluster_name}")
async def get_mce_environment(cluster_name: str):
    """
    Get detailed information for a specific MCE environment.
    """
    try:
        import sys

        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "scripts")
        sys.path.insert(0, scripts_dir)

        from mce_env_manager import MCEEnvManager

        manager = MCEEnvManager()
        env = manager.get_environment(cluster_name)

        if not env:
            raise HTTPException(status_code=404, detail=f"Environment {cluster_name} not found")

        data = env.get("data", {})
        cluster_data = data.get("cluster", {})
        notification = data.get("notification", {})
        platform = env.get("platform", "")

        # Build API URL based on platform
        if "IBM" in platform or "Power" in platform:
            api_url = f"https://api.{cluster_name}.rdr-ppcloud.sandbox.cis.ibm.net:6443"
        elif "ARM" in platform or "AWS" in platform:
            api_url = f"https://api.{cluster_name}.dev09.red-chesterfield.com:6443"
        else:
            api_url = f"https://api.{cluster_name}:6443"

        return {
            "success": True,
            "environment": {
                "clusterName": env.get("cluster_name"),
                "platform": platform,
                "status": env.get("status"),
                "notes": env.get("notes", ""),
                "addedDate": env.get("added_date"),
                "lastAccessed": env.get("last_accessed"),
                "ocpVersion": cluster_data.get("ocp_version"),
                "mceVersion": cluster_data.get("mce_version"),
                "acmVersion": cluster_data.get("acm_version"),
                "clusterStatus": cluster_data.get("status"),
                "password": cluster_data.get("password"),
                "consoleUrl": cluster_data.get("console_url"),
                "apiUrl": api_url,
                "jira": notification.get("jira"),
                "polarion": notification.get("polarion"),
                "title": notification.get("title"),
                "totalFailures": notification.get("total_failures", 0),
                "components": notification.get("components", {}),
                "loginCommand": f"oc login {api_url} -u kubeadmin -p {cluster_data.get('password')} --insecure-skip-tls-verify",
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error getting MCE environment: {str(e)}")
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error getting environment: {str(e)}")


@app.post("/api/mce-environments")
async def save_mce_environment(request: Request):
    """
    Save current MCE environment connection details for future use.

    Request body:
    {
        "clusterName": "qe6-vmware-ibm",
        "apiUrl": "https://api.qe6-vmware-ibm.install.dev09.red-chesterfield.com:6443",
        "username": "kubeadmin",
        "password": "xxxxx",
        "platform": "VMware",
        "ocpVersion": "4.20.11",
        "mceVersion": "2.11.0-239",
        "acmVersion": "2.16.0-xxx",
        "consoleUrl": "https://console-openshift-console.apps.qe6-vmware-ibm..."
    }
    """
    try:
        import sys
        from datetime import datetime

        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "scripts")
        sys.path.insert(0, scripts_dir)

        from mce_env_manager import MCEEnvManager

        data = await request.json()

        # Extract cluster name from API URL if not provided
        cluster_name = data.get("clusterName")
        if not cluster_name:
            api_url = data.get("apiUrl", "")
            # Extract from URL like https://api.qe6-vmware-ibm.install.dev09.red-chesterfield.com:6443
            import re

            match = re.search(r"api\.([^.]+)", api_url)
            if match:
                cluster_name = match.group(1)
            else:
                return {"success": False, "message": "Could not determine cluster name"}

        # Build environment data structure matching MCEEnvManager expectations
        env_data = {
            "cluster": {
                "platform": data.get("platform", "Unknown"),
                "hub_cluster": cluster_name,
                "ocp_version": data.get("ocpVersion", ""),
                "mce_version": data.get("mceVersion", ""),
                "acm_version": data.get("acmVersion", ""),
                "status": "Running",
                "password": data.get("password", ""),
                "console_url": data.get("consoleUrl", ""),
                "api_url": data.get("apiUrl", ""),
                "username": data.get("username", "kubeadmin"),
            },
            "notification": {
                "title": f"MCE Environment - {cluster_name}",
                "mce_version": data.get("mceVersion", ""),
                "acm_version": data.get("acmVersion", ""),
                "hub_cluster": cluster_name,
                "jira": data.get("jira", ""),
                "polarion": data.get("polarion", ""),
            },
        }

        manager = MCEEnvManager()

        # Check if environment already exists
        existing = manager.get_environment(cluster_name)
        if existing:
            # Update last_accessed time
            manager.update_last_accessed(cluster_name)
            message = f"Environment {cluster_name} already exists - updated last accessed time"
        else:
            # Add new environment
            manager.add_environment(env_data)
            message = f"Environment {cluster_name} saved successfully"

        return {"success": True, "message": message, "clusterName": cluster_name}

    except Exception as e:
        print(f"❌ Error saving MCE environment: {str(e)}")
        import traceback

        traceback.print_exc()
        return {"success": False, "message": f"Error saving environment: {str(e)}"}


@app.post("/api/mce-environments/{cluster_name}/status")
async def update_mce_environment_status(cluster_name: str, request: Request):
    """
    Update the test status for an MCE environment.

    Body:
        status: Test status (pass, fail, blocked, in_progress, unknown)
        notes: Optional notes about the test result
    """
    try:
        import sys

        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "scripts")
        sys.path.insert(0, scripts_dir)

        from mce_env_manager import MCEEnvManager

        body = await request.json()
        status = body.get("status")
        notes = body.get("notes")

        if status not in ["pass", "fail", "blocked", "in_progress", "unknown"]:
            raise HTTPException(status_code=400, detail="Invalid status value")

        manager = MCEEnvManager()
        success = manager.update_status(cluster_name, status, notes)

        if not success:
            raise HTTPException(status_code=404, detail=f"Environment {cluster_name} not found")

        return {"success": True, "message": f"Updated {cluster_name} to status: {status}"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error updating MCE environment status: {str(e)}")
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error updating status: {str(e)}")


@app.get("/api/mce-environments/stats/summary")
async def get_mce_environment_stats():
    """
    Get statistics about MCE test environments.
    """
    try:
        import sys

        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "scripts")
        sys.path.insert(0, scripts_dir)

        from mce_env_manager import MCEEnvManager

        manager = MCEEnvManager()
        stats = manager.get_stats()

        return {
            "success": True,
            "stats": {
                "total": stats.get("total", 0),
                "byPlatform": stats.get("by_platform", {}),
                "byStatus": stats.get("by_status", {}),
                "recent": [
                    {
                        "clusterName": env.get("cluster_name"),
                        "platform": env.get("platform"),
                        "status": env.get("status"),
                        "lastAccessed": env.get("last_accessed"),
                    }
                    for env in stats.get("recent", [])
                ],
            },
        }

    except Exception as e:
        print(f"❌ Error getting MCE environment stats: {str(e)}")
        import traceback

        traceback.print_exc()
        return {
            "success": False,
            "message": f"Error getting stats: {str(e)}",
            "stats": {"total": 0, "byPlatform": {}, "byStatus": {}, "recent": []},
        }


@app.get("/api/mce-environments/search/{query}")
async def search_mce_environments(query: str):
    """
    Search MCE environments by cluster name, platform, Jira, Polarion, or notes.
    """
    try:
        import sys

        scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "scripts")
        sys.path.insert(0, scripts_dir)

        from mce_env_manager import MCEEnvManager

        manager = MCEEnvManager()
        results = manager.search_environments(query)

        # Format for frontend
        formatted_results = []
        for env in results:
            data = env.get("data", {})
            cluster_data = data.get("cluster", {})
            notification = data.get("notification", {})

            formatted_results.append(
                {
                    "clusterName": env.get("cluster_name"),
                    "platform": env.get("platform"),
                    "status": env.get("status"),
                    "notes": env.get("notes", ""),
                    "lastAccessed": env.get("last_accessed"),
                    "jira": notification.get("jira"),
                    "polarion": notification.get("polarion"),
                    "totalFailures": notification.get("total_failures", 0),
                }
            )

        return {
            "success": True,
            "results": formatted_results,
            "total": len(formatted_results),
            "query": query,
        }

    except Exception as e:
        print(f"❌ Error searching MCE environments: {str(e)}")
        import traceback

        traceback.print_exc()
        return {
            "success": False,
            "message": f"Error searching environments: {str(e)}",
            "results": [],
            "total": 0,
        }


@app.get("/api/jenkins/test-results-trend")
async def get_jenkins_test_results_trend(response: Response):
    """Get Jenkins test results trend data from CAPI tests job"""
    import requests
    from datetime import datetime
    import urllib3

    # Suppress SSL warnings for self-signed cert
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    try:
        jenkins_base_url = "https://jenkins-csb-rhacm-tests.dno.corp.redhat.com/job/CI-Jobs/job/capi_tests"

        # Fetch recent builds (last 20)
        builds_url = f"{jenkins_base_url}/api/json?tree=builds[number,result,timestamp,duration]{{0,20}}"

        print(f"📊 [JENKINS] Fetching test trend data from: {builds_url}")

        # Disable SSL verification for internal Jenkins (self-signed cert)
        response = requests.get(builds_url, timeout=10, verify=False)
        response.raise_for_status()
        data = response.json()

        trend_data = []

        # For each build, fetch test results
        for build in data.get("builds", [])[:20]:
            build_number = build.get("number")
            result = build.get("result")
            timestamp = build.get("timestamp")

            # Skip builds without results (still running)
            if not result:
                continue

            try:
                # Fetch test report for this build
                test_url = f"{jenkins_base_url}/{build_number}/testReport/api/json"
                test_response = requests.get(test_url, timeout=5, verify=False)

                if test_response.status_code == 200:
                    test_data = test_response.json()

                    pass_count = test_data.get("passCount", 0)
                    fail_count = test_data.get("failCount", 0)
                    skip_count = test_data.get("skipCount", 0)
                    total_count = pass_count + fail_count + skip_count

                    trend_data.append({
                        "build": build_number,
                        "result": result,
                        "timestamp": datetime.fromtimestamp(timestamp / 1000).isoformat() if timestamp else None,
                        "passCount": pass_count,
                        "failCount": fail_count,
                        "skipCount": skip_count,
                        "totalCount": total_count,
                        "passRate": round((pass_count / total_count * 100), 1) if total_count > 0 else 0,
                    })
                else:
                    # Build might not have test results
                    print(f"⚠️  [JENKINS] Build #{build_number} has no test results (status {test_response.status_code})")
            except Exception as e:
                print(f"⚠️  [JENKINS] Failed to fetch test results for build #{build_number}: {str(e)}")
                continue

        # Sort by build number descending (newest first)
        trend_data.sort(key=lambda x: x["build"], reverse=True)

        print(f"✅ [JENKINS] Successfully fetched trend data for {len(trend_data)} builds")

        # Set cache-control headers to prevent caching
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

        return {
            "success": True,
            "trend": trend_data,
            "count": len(trend_data),
        }

    except Exception as e:
        print(f"❌ [JENKINS] Error fetching test results trend: {str(e)}")
        import traceback
        traceback.print_exc()

        return {
            "success": False,
            "trend": [],
            "count": 0,
            "message": f"Error fetching Jenkins test results: {str(e)}",
        }


@app.get("/api/github/repo-activity")
async def get_github_repo_activity():
    """Get GitHub repository activity stats"""
    import requests
    from datetime import datetime, timedelta

    try:
        # Repositories to monitor
        repos = [
            "stolostron/cluster-api-provider-aws",
            "tinaafitz/test-automation-capa"
        ]

        activity_data = []

        for repo in repos:
            # GitHub API endpoint for repo stats
            api_base = f"https://api.github.com/repos/{repo}"

            # Get repo info
            repo_response = requests.get(api_base, timeout=10)
            if repo_response.status_code != 200:
                print(f"⚠️  [GITHUB] Failed to fetch {repo}: {repo_response.status_code}")
                # Add repo with placeholder data if rate limited
                activity_data.append({
                    "repo": repo,
                    "name": repo.split("/")[1],
                    "stars": 0,
                    "forks": 0,
                    "open_issues": 0,
                    "open_prs": 0,
                    "merged_prs_7d": "?",
                    "commits_7d": 0,
                    "updated_at": None,
                    "error": "Rate limited" if repo_response.status_code == 403 else f"Error {repo_response.status_code}"
                })
                continue

            repo_data = repo_response.json()

            # Get recent commits (last 7 days)
            since_date = (datetime.now() - timedelta(days=7)).isoformat()
            commits_url = f"{api_base}/commits?since={since_date}&per_page=100"
            commits_response = requests.get(commits_url, timeout=10)
            commits_count = len(commits_response.json()) if commits_response.status_code == 200 else 0

            # Get open PRs
            prs_url = f"{api_base}/pulls?state=open&per_page=100"
            prs_response = requests.get(prs_url, timeout=10)
            open_prs = len(prs_response.json()) if prs_response.status_code == 200 else 0

            # Get merged PRs (last 7 days)
            merged_prs_url = f"{api_base}/pulls?state=closed&per_page=100"
            merged_prs_response = requests.get(merged_prs_url, timeout=10)
            merged_prs_count = 0
            if merged_prs_response.status_code == 200:
                closed_prs = merged_prs_response.json()
                # Filter for merged PRs in last 7 days
                seven_days_ago = datetime.now() - timedelta(days=7)
                for pr in closed_prs:
                    if pr.get("merged_at"):
                        merged_at = datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00"))
                        if merged_at.replace(tzinfo=None) >= seven_days_ago:
                            merged_prs_count += 1

            # Get open issues (excluding PRs)
            issues_url = f"{api_base}/issues?state=open&per_page=100"
            issues_response = requests.get(issues_url, timeout=10)
            all_open = len(issues_response.json()) if issues_response.status_code == 200 else 0
            open_issues = all_open - open_prs  # Issues includes PRs, so subtract

            activity_data.append({
                "repo": repo,
                "name": repo.split("/")[1],
                "stars": repo_data.get("stargazers_count", 0),
                "forks": repo_data.get("forks_count", 0),
                "open_issues": open_issues,
                "open_prs": open_prs,
                "merged_prs_7d": merged_prs_count,
                "commits_7d": commits_count,
                "updated_at": repo_data.get("updated_at"),
            })

        print(f"✅ [GITHUB] Successfully fetched activity for {len(activity_data)} repos")

        return {
            "success": True,
            "repos": activity_data,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        print(f"❌ [GITHUB] Error fetching repo activity: {str(e)}")
        return {
            "success": False,
            "repos": [],
            "message": f"Error fetching GitHub repo activity: {str(e)}",
        }


def _collect_aws_usage_data():
    """Collect AWS resource usage counts (sync, can be called from background tasks)"""
    usage_data = {}

    # Instance Profiles
    try:
        result = subprocess.run(
            ["aws", "iam", "list-instance-profiles", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            usage_data["instance_profiles"] = len(data.get("InstanceProfiles", []))
        else:
            usage_data["instance_profiles"] = "error"
    except Exception as e:
        usage_data["instance_profiles"] = "error"

    # CloudFormation Stacks
    try:
        result = subprocess.run(
            ["aws", "cloudformation", "list-stacks", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            # Only count non-deleted stacks
            stacks = [s for s in data.get("StackSummaries", [])
                     if s.get("StackStatus") not in ["DELETE_COMPLETE"]]
            usage_data["cloudformation_stacks"] = len(stacks)
        else:
            usage_data["cloudformation_stacks"] = "error"
    except Exception as e:
        usage_data["cloudformation_stacks"] = "error"

    # NAT Gateways
    try:
        result = subprocess.run(
            ["aws", "ec2", "describe-nat-gateways", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            # Only count available NAT gateways
            nat_gateways = [n for n in data.get("NatGateways", [])
                           if n.get("State") == "available"]
            usage_data["nat_gateways"] = len(nat_gateways)
        else:
            usage_data["nat_gateways"] = "error"
    except Exception as e:
        usage_data["nat_gateways"] = "error"

    # Route53 Hosted Zones
    try:
        result = subprocess.run(
            ["aws", "route53", "list-hosted-zones", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            usage_data["route53_zones"] = len(data.get("HostedZones", []))
        else:
            usage_data["route53_zones"] = "error"
    except Exception as e:
        usage_data["route53_zones"] = "error"

    # IAM Roles
    try:
        result = subprocess.run(
            ["aws", "iam", "list-roles", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            usage_data["iam_roles"] = len(data.get("Roles", []))
        else:
            usage_data["iam_roles"] = "error"
    except Exception as e:
        usage_data["iam_roles"] = "error"

    # VPCs
    try:
        result = subprocess.run(
            ["aws", "ec2", "describe-vpcs", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            usage_data["vpcs"] = len(data.get("Vpcs", []))
        else:
            usage_data["vpcs"] = "error"
    except Exception as e:
        usage_data["vpcs"] = "error"

    # Security Groups
    try:
        result = subprocess.run(
            ["aws", "ec2", "describe-security-groups", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            usage_data["security_groups"] = len(data.get("SecurityGroups", []))
        else:
            usage_data["security_groups"] = "error"
    except Exception as e:
        usage_data["security_groups"] = "error"

    # EC2 Instances
    try:
        result = subprocess.run(
            ["aws", "ec2", "describe-instances", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            # Count running and stopped instances
            instance_count = 0
            for reservation in data.get("Reservations", []):
                instance_count += len(reservation.get("Instances", []))
            usage_data["ec2_instances"] = instance_count
        else:
            usage_data["ec2_instances"] = "error"
    except Exception as e:
        usage_data["ec2_instances"] = "error"

    # EBS Volumes
    try:
        result = subprocess.run(
            ["aws", "ec2", "describe-volumes", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            usage_data["ebs_volumes"] = len(data.get("Volumes", []))
        else:
            usage_data["ebs_volumes"] = "error"
    except Exception as e:
        usage_data["ebs_volumes"] = "error"

    # Load Balancers
    try:
        result = subprocess.run(
            ["aws", "elbv2", "describe-load-balancers", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            usage_data["load_balancers"] = len(data.get("LoadBalancers", []))
        else:
            usage_data["load_balancers"] = "error"
    except Exception as e:
        usage_data["load_balancers"] = "error"

    # S3 Buckets
    try:
        result = subprocess.run(
            ["aws", "s3api", "list-buckets", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            usage_data["s3_buckets"] = len(data.get("Buckets", []))
        else:
            usage_data["s3_buckets"] = "error"
    except Exception as e:
        usage_data["s3_buckets"] = "error"

    return usage_data


@app.get("/api/aws/usage")
async def get_aws_usage():
    """Get AWS resource usage counts"""
    try:
        usage_data = _collect_aws_usage_data()

        # Save snapshot to history
        _save_aws_usage_snapshot(usage_data)

        return {
            "success": True,
            "usage": usage_data,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        print(f"❌ [AWS USAGE] Error fetching AWS usage: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to fetch AWS usage data: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }


def _get_aws_history_db():
    """Get path to AWS usage history database"""
    db_path = os.path.join(os.path.dirname(__file__), "aws_usage_history.db")
    return db_path


def _init_aws_history_db():
    """Initialize the AWS usage history SQLite database"""
    db_path = _get_aws_history_db()
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usage_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            resource_key TEXT NOT NULL,
            count INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_timestamp ON usage_snapshots(timestamp)
    """)
    conn.commit()
    conn.close()


# Initialize DB on module load
_init_aws_history_db()


async def _aws_usage_snapshot_loop():
    """Background task that collects AWS usage snapshots every hour"""
    await asyncio.sleep(10)  # Wait for app startup
    print("🔄 [AWS TREND] Hourly AWS usage snapshot collector started", flush=True)
    while True:
        try:
            usage_data = await asyncio.to_thread(_collect_aws_usage_data)
            _save_aws_usage_snapshot(usage_data)
            valid_count = sum(1 for v in usage_data.values() if v != "error")
            print(f"✅ [AWS TREND] Hourly snapshot saved: {valid_count} resources at {datetime.now().strftime('%H:%M')}", flush=True)
        except Exception as e:
            print(f"⚠️ [AWS TREND] Hourly snapshot failed: {e}", flush=True)
        await asyncio.sleep(3600)  # 1 hour


@app.on_event("startup")
async def start_aws_snapshot_collector():
    asyncio.create_task(_aws_usage_snapshot_loop())


def _save_aws_usage_snapshot(usage_data):
    """Save a usage snapshot to the history database"""
    try:
        db_path = _get_aws_history_db()
        conn = sqlite3.connect(db_path)
        timestamp = datetime.now().isoformat()
        for key, value in usage_data.items():
            if value != "error" and isinstance(value, (int, float)):
                conn.execute(
                    "INSERT INTO usage_snapshots (timestamp, resource_key, count) VALUES (?, ?, ?)",
                    (timestamp, key, int(value))
                )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ [AWS HISTORY] Failed to save snapshot: {e}")


@app.get("/api/aws/usage-trend")
async def get_aws_usage_trend(days: int = 30):
    """Get AWS resource usage trend data over time"""
    try:
        db_path = _get_aws_history_db()
        conn = sqlite3.connect(db_path)

        # Get snapshots from the last N days
        cutoff = (datetime.now() - __import__('datetime').timedelta(days=days)).isoformat()
        rows = conn.execute(
            """SELECT timestamp, resource_key, count FROM usage_snapshots
               WHERE timestamp >= ? ORDER BY timestamp ASC""",
            (cutoff,)
        ).fetchall()
        conn.close()

        if not rows:
            return {"success": True, "trend": [], "days": days, "message": "No historical data yet. Refresh the AWS Usage page to start collecting data."}

        # Group by timestamp (each snapshot)
        # Use hourly grouping only when we have enough data (>48 snapshots)
        snapshots = {}
        use_hourly = len(set(r[0] for r in rows)) > 48
        for timestamp, resource_key, count in rows:
            group_key = timestamp[:13] if use_hourly else timestamp
            if group_key not in snapshots:
                snapshots[group_key] = {"timestamp": timestamp, "resources": {}}
            snapshots[group_key]["resources"][resource_key] = count

        # Convert to list sorted by time
        trend = []
        for group_key in sorted(snapshots.keys()):
            snap = snapshots[group_key]
            trend.append({
                "timestamp": snap["timestamp"],
                **snap["resources"]
            })

        # Get unique resource keys
        all_keys = set()
        for snap in trend:
            all_keys.update(k for k in snap.keys() if k != "timestamp")

        return {
            "success": True,
            "trend": trend,
            "resource_keys": sorted(all_keys),
            "days": days,
            "snapshot_count": len(trend)
        }

    except Exception as e:
        print(f"❌ [AWS TREND] Error fetching trend data: {e}")
        return {
            "success": False,
            "message": f"Failed to fetch trend data: {str(e)}"
        }


@app.get("/api/aws/usage-config")
async def get_aws_config():
    """Get AWS resource configuration with live quotas from AWS API"""
    try:
        from aws_config_service import aws_config_service
        return aws_config_service.get_resource_config_with_quotas()
    except Exception as e:
        print(f"❌ [AWS CONFIG] Error loading AWS configuration: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to load AWS configuration: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }


@app.get("/api/aws/usage/{resource_key}")
async def get_single_resource_usage(resource_key: str):
    """Refresh count for a single AWS resource type"""
    try:
        count = "error"

        if resource_key == "nat_gateways":
            r = subprocess.run(["aws", "ec2", "describe-nat-gateways", "--output", "json"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                data = json.loads(r.stdout)
                count = len([n for n in data.get("NatGateways", []) if n.get("State") == "available"])
        elif resource_key == "route53_zones":
            r = subprocess.run(["aws", "route53", "list-hosted-zones", "--output", "json"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                count = len(json.loads(r.stdout).get("HostedZones", []))
        elif resource_key == "iam_roles":
            r = subprocess.run(["aws", "iam", "list-roles", "--output", "json"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                count = len(json.loads(r.stdout).get("Roles", []))
        elif resource_key == "vpcs":
            r = subprocess.run(["aws", "ec2", "describe-vpcs", "--output", "json"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                count = len(json.loads(r.stdout).get("Vpcs", []))
        elif resource_key == "security_groups":
            r = subprocess.run(["aws", "ec2", "describe-security-groups", "--output", "json"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                count = len(json.loads(r.stdout).get("SecurityGroups", []))
        elif resource_key == "ec2_instances":
            r = subprocess.run(["aws", "ec2", "describe-instances", "--output", "json"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                data = json.loads(r.stdout)
                count = sum(len(res.get("Instances", [])) for res in data.get("Reservations", []))
        elif resource_key == "ebs_volumes":
            r = subprocess.run(["aws", "ec2", "describe-volumes", "--output", "json"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                count = len(json.loads(r.stdout).get("Volumes", []))
        elif resource_key == "load_balancers":
            r = subprocess.run(["aws", "elbv2", "describe-load-balancers", "--output", "json"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                count = len(json.loads(r.stdout).get("LoadBalancers", []))
        elif resource_key == "s3_buckets":
            r = subprocess.run(["aws", "s3api", "list-buckets", "--output", "json"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                count = len(json.loads(r.stdout).get("Buckets", []))
        elif resource_key == "cloudformation_stacks":
            r = subprocess.run(["aws", "cloudformation", "list-stacks", "--output", "json"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                data = json.loads(r.stdout)
                count = len([s for s in data.get("StackSummaries", []) if s.get("StackStatus") not in ["DELETE_COMPLETE"]])
        elif resource_key == "instance_profiles":
            r = subprocess.run(["aws", "iam", "list-instance-profiles", "--output", "json"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                count = len(json.loads(r.stdout).get("InstanceProfiles", []))
        else:
            return {"success": False, "message": f"Unknown resource type: {resource_key}"}

        return {"success": True, "resource_key": resource_key, "count": count, "timestamp": datetime.now().isoformat()}

    except Exception as e:
        return {"success": False, "message": f"Failed to refresh {resource_key}: {str(e)}"}


@app.get("/api/aws/resource-details/{resource_type}")
async def get_resource_details(resource_type: str):
    """Get detailed information about specific AWS resources including creation time, tags, and metadata"""
    try:
        details = []

        if resource_type == "nat_gateways":
            result = subprocess.run(
                ["aws", "ec2", "describe-nat-gateways", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                nat_gateways = [n for n in data.get("NatGateways", [])
                               if n.get("State") == "available"]

                for nat in nat_gateways:
                    # Get VPC name from tags if available
                    vpc_name = None
                    vpc_id = nat.get("VpcId", "N/A")

                    # Try to get VPC name
                    try:
                        vpc_result = subprocess.run(
                            ["aws", "ec2", "describe-vpcs", "--vpc-ids", vpc_id, "--output", "json"],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if vpc_result.returncode == 0:
                            vpc_data = json.loads(vpc_result.stdout)
                            vpcs = vpc_data.get("Vpcs", [])
                            if vpcs:
                                vpc_tags = {tag["Key"]: tag["Value"] for tag in vpcs[0].get("Tags", [])}
                                vpc_name = vpc_tags.get("Name", vpc_id)
                    except:
                        vpc_name = vpc_id

                    # Extract tags
                    tags = {tag["Key"]: tag["Value"] for tag in nat.get("Tags", [])}

                    details.append({
                        "id": nat.get("NatGatewayId", "N/A"),
                        "name": tags.get("Name", "Unnamed"),
                        "vpc_id": vpc_id,
                        "vpc_name": vpc_name or vpc_id,
                        "subnet_id": nat.get("SubnetId", "N/A"),
                        "state": nat.get("State", "N/A"),
                        "created_at": nat.get("CreateTime", "N/A"),
                        "tags": tags,
                        "public_ip": nat.get("NatGatewayAddresses", [{}])[0].get("PublicIp", "N/A") if nat.get("NatGatewayAddresses") else "N/A"
                    })

        elif resource_type == "route53_zones":
            result = subprocess.run(
                ["aws", "route53", "list-hosted-zones", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for zone in data.get("HostedZones", []):
                    # Get tags for this hosted zone
                    zone_id = zone.get("Id", "").split("/")[-1]
                    tags = {}
                    try:
                        tags_result = subprocess.run(
                            ["aws", "route53", "list-tags-for-resource",
                             "--resource-type", "hostedzone",
                             "--resource-id", zone_id,
                             "--output", "json"],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if tags_result.returncode == 0:
                            tags_data = json.loads(tags_result.stdout)
                            tags = {tag["Key"]: tag["Value"] for tag in tags_data.get("ResourceTagSet", {}).get("Tags", [])}
                    except:
                        pass

                    details.append({
                        "id": zone.get("Id", "N/A"),
                        "name": zone.get("Name", "N/A"),
                        "record_count": zone.get("ResourceRecordSetCount", 0),
                        "private_zone": zone.get("Config", {}).get("PrivateZone", False),
                        "comment": zone.get("Config", {}).get("Comment", ""),
                        "tags": tags
                    })

        elif resource_type == "vpcs":
            result = subprocess.run(
                ["aws", "ec2", "describe-vpcs", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for vpc in data.get("Vpcs", []):
                    tags = {tag["Key"]: tag["Value"] for tag in vpc.get("Tags", [])}
                    details.append({
                        "id": vpc.get("VpcId", "N/A"),
                        "name": tags.get("Name", "Unnamed"),
                        "cidr": vpc.get("CidrBlock", "N/A"),
                        "state": vpc.get("State", "N/A"),
                        "is_default": vpc.get("IsDefault", False),
                        "tags": tags
                    })

        elif resource_type == "ec2_instances":
            result = subprocess.run(
                ["aws", "ec2", "describe-instances", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for reservation in data.get("Reservations", []):
                    for instance in reservation.get("Instances", []):
                        tags = {tag["Key"]: tag["Value"] for tag in instance.get("Tags", [])}
                        details.append({
                            "id": instance.get("InstanceId", "N/A"),
                            "name": tags.get("Name", "Unnamed"),
                            "type": instance.get("InstanceType", "N/A"),
                            "state": instance.get("State", {}).get("Name", "N/A"),
                            "launch_time": instance.get("LaunchTime", "N/A"),
                            "vpc_id": instance.get("VpcId", "N/A"),
                            "subnet_id": instance.get("SubnetId", "N/A"),
                            "private_ip": instance.get("PrivateIpAddress", "N/A"),
                            "public_ip": instance.get("PublicIpAddress", "N/A"),
                            "tags": tags
                        })

        elif resource_type == "ebs_volumes":
            result = subprocess.run(
                ["aws", "ec2", "describe-volumes", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for volume in data.get("Volumes", []):
                    tags = {tag["Key"]: tag["Value"] for tag in volume.get("Tags", [])}

                    # Get attachment info
                    attachments = volume.get("Attachments", [])
                    attached_to = attachments[0].get("InstanceId", "Not attached") if attachments else "Not attached"

                    details.append({
                        "id": volume.get("VolumeId", "N/A"),
                        "name": tags.get("Name", "Unnamed"),
                        "size": f"{volume.get('Size', 0)} GB",
                        "volume_type": volume.get("VolumeType", "N/A"),
                        "state": volume.get("State", "N/A"),
                        "created_at": volume.get("CreateTime", "N/A"),
                        "availability_zone": volume.get("AvailabilityZone", "N/A"),
                        "attached_to": attached_to,
                        "encrypted": volume.get("Encrypted", False),
                        "tags": tags
                    })

        elif resource_type == "instance_profiles":
            result = subprocess.run(
                ["aws", "iam", "list-instance-profiles", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                # Limit to first 100 profiles to prevent timeout
                profiles_to_process = data.get("InstanceProfiles", [])[:100]

                for profile in profiles_to_process:
                    profile_name = profile.get("InstanceProfileName", "")
                    # Skip tag fetching for instance profiles to speed up loading
                    tags = {}

                    # Get associated roles
                    roles = [r.get("RoleName", "") for r in profile.get("Roles", [])]

                    details.append({
                        "id": profile.get("InstanceProfileId", "N/A"),
                        "name": profile_name,
                        "arn": profile.get("Arn", "N/A"),
                        "created_at": profile.get("CreateDate", "N/A"),
                        "path": profile.get("Path", "/"),
                        "roles": roles,
                        "tags": tags
                    })

        elif resource_type == "iam_roles":
            result = subprocess.run(
                ["aws", "iam", "list-roles", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                # Limit to first 100 roles to prevent timeout
                roles_to_process = data.get("Roles", [])[:100]

                for role in roles_to_process:
                    role_name = role.get("RoleName", "")
                    # Skip tag fetching for IAM roles to speed up loading
                    # Tags can be added later if needed
                    tags = {}

                    details.append({
                        "id": role.get("RoleId", "N/A"),
                        "name": role_name,
                        "arn": role.get("Arn", "N/A"),
                        "created_at": role.get("CreateDate", "N/A"),
                        "path": role.get("Path", "/"),
                        "description": role.get("Description", ""),
                        "max_session_duration": role.get("MaxSessionDuration", 3600),
                        "tags": tags
                    })

        elif resource_type == "cloudformation_stacks":
            result = subprocess.run(
                ["aws", "cloudformation", "list-stacks", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                stacks = [s for s in data.get("StackSummaries", [])
                         if s.get("StackStatus") not in ["DELETE_COMPLETE"]]

                for stack in stacks:
                    stack_name = stack.get("StackName", "")
                    # Get detailed stack info including tags
                    try:
                        detail_result = subprocess.run(
                            ["aws", "cloudformation", "describe-stacks", "--stack-name", stack_name, "--output", "json"],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if detail_result.returncode == 0:
                            detail_data = json.loads(detail_result.stdout)
                            if detail_data.get("Stacks"):
                                stack_detail = detail_data["Stacks"][0]
                                tags = {tag["Key"]: tag["Value"] for tag in stack_detail.get("Tags", [])}

                                details.append({
                                    "id": stack.get("StackId", "N/A"),
                                    "name": stack_name,
                                    "status": stack.get("StackStatus", "N/A"),
                                    "created_at": stack.get("CreationTime", "N/A"),
                                    "description": stack_detail.get("Description", ""),
                                    "tags": tags
                                })
                    except:
                        # Fallback if detailed fetch fails
                        details.append({
                            "id": stack.get("StackId", "N/A"),
                            "name": stack_name,
                            "status": stack.get("StackStatus", "N/A"),
                            "created_at": stack.get("CreationTime", "N/A"),
                            "description": "",
                            "tags": {}
                        })

        elif resource_type == "load_balancers":
            # Classic load balancers
            result = subprocess.run(
                ["aws", "elbv2", "describe-load-balancers", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for lb in data.get("LoadBalancers", []):
                    lb_arn = lb.get("LoadBalancerArn", "")
                    tags = {}
                    try:
                        tags_result = subprocess.run(
                            ["aws", "elbv2", "describe-tags", "--resource-arns", lb_arn, "--output", "json"],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if tags_result.returncode == 0:
                            tags_data = json.loads(tags_result.stdout)
                            for desc in tags_data.get("TagDescriptions", []):
                                tags = {tag["Key"]: tag["Value"] for tag in desc.get("Tags", [])}
                    except:
                        pass

                    vpc_id = lb.get("VpcId", "N/A")
                    vpc_name = vpc_id
                    try:
                        vpc_result = subprocess.run(
                            ["aws", "ec2", "describe-vpcs", "--vpc-ids", vpc_id, "--output", "json"],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if vpc_result.returncode == 0:
                            vpc_data = json.loads(vpc_result.stdout)
                            vpcs = vpc_data.get("Vpcs", [])
                            if vpcs:
                                vpc_tags = {tag["Key"]: tag["Value"] for tag in vpcs[0].get("Tags", [])}
                                vpc_name = vpc_tags.get("Name", vpc_id)
                    except:
                        pass

                    details.append({
                        "id": lb.get("LoadBalancerArn", "N/A").split("/")[-1] if "/" in lb.get("LoadBalancerArn", "") else lb.get("LoadBalancerArn", "N/A"),
                        "name": lb.get("LoadBalancerName", "Unnamed"),
                        "type": lb.get("Type", "N/A"),
                        "scheme": lb.get("Scheme", "N/A"),
                        "state": lb.get("State", {}).get("Code", "N/A"),
                        "dns_name": lb.get("DNSName", "N/A"),
                        "vpc_id": vpc_id,
                        "vpc_name": vpc_name,
                        "created_at": lb.get("CreatedTime", "N/A"),
                        "tags": tags
                    })

        elif resource_type == "s3_buckets":
            result = subprocess.run(
                ["aws", "s3api", "list-buckets", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for bucket in data.get("Buckets", []):
                    bucket_name = bucket.get("Name", "")
                    tags = {}
                    try:
                        tags_result = subprocess.run(
                            ["aws", "s3api", "get-bucket-tagging", "--bucket", bucket_name, "--output", "json"],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if tags_result.returncode == 0:
                            tags_data = json.loads(tags_result.stdout)
                            tags = {tag["Key"]: tag["Value"] for tag in tags_data.get("TagSet", [])}
                    except:
                        pass

                    details.append({
                        "id": bucket_name,
                        "name": bucket_name,
                        "created_at": bucket.get("CreationDate", "N/A"),
                        "tags": tags
                    })

        elif resource_type == "security_groups":
            result = subprocess.run(
                ["aws", "ec2", "describe-security-groups", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for sg in data.get("SecurityGroups", []):
                    tags = {tag["Key"]: tag["Value"] for tag in sg.get("Tags", [])}

                    # Count inbound and outbound rules
                    ingress_rules = len(sg.get("IpPermissions", []))
                    egress_rules = len(sg.get("IpPermissionsEgress", []))

                    # Get VPC name if available
                    vpc_id = sg.get("VpcId", "N/A")
                    vpc_name = vpc_id
                    try:
                        vpc_result = subprocess.run(
                            ["aws", "ec2", "describe-vpcs", "--vpc-ids", vpc_id, "--output", "json"],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if vpc_result.returncode == 0:
                            vpc_data = json.loads(vpc_result.stdout)
                            vpcs = vpc_data.get("Vpcs", [])
                            if vpcs:
                                vpc_tags = {tag["Key"]: tag["Value"] for tag in vpcs[0].get("Tags", [])}
                                vpc_name = vpc_tags.get("Name", vpc_id)
                    except:
                        pass

                    details.append({
                        "id": sg.get("GroupId", "N/A"),
                        "name": sg.get("GroupName", "Unnamed"),
                        "description": sg.get("Description", ""),
                        "vpc_id": vpc_id,
                        "vpc_name": vpc_name,
                        "ingress_rules": ingress_rules,
                        "egress_rules": egress_rules,
                        "tags": tags
                    })

        # Sort by creation time (most recent first) if available
        if details and "created_at" in details[0]:
            details.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        elif details and "launch_time" in details[0]:
            details.sort(key=lambda x: x.get("launch_time", ""), reverse=True)

        return {
            "success": True,
            "resource_type": resource_type,
            "count": len(details),
            "details": details,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        print(f"❌ [AWS RESOURCE DETAILS] Error fetching details for {resource_type}: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to fetch resource details: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
