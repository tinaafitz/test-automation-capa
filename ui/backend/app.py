#!/usr/bin/env python3
"""
ROSA Automation UI Backend
FastAPI-based backend for the ROSA cluster automation interface
"""

from fastapi import FastAPI, HTTPException, WebSocket, BackgroundTasks, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional
import asyncio
import fcntl
import json
import re
import subprocess
import threading
import uuid
from datetime import datetime
import os
import yaml
import sqlite3
import time
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
import minikube_ops
from playbook_executor import build_playbook_command, SENSITIVE_KEYS
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

# Shared mutable state (single source of truth lives in shared_state.py)
from shared_state import (
    jobs, _jobs_lock,
    ai_agent_sessions, _sessions_lock,
    clusters,
    rosa_status_cache, ocp_status_cache,
    last_rosa_yaml_path,
)

# Jobs service (router + helper functions)
from jobs_service import router as jobs_router, normalize_timestamp, check_and_timeout_stuck_jobs, get_agent_stats
app.include_router(jobs_router)

# Agents service (router + agent lifecycle helpers)
from agents_service import (
    router as agents_router,
    init_ai_agents,
    _load_agent_kb_file,
    _save_agent_kb_file,
    AI_AGENTS_AVAILABLE as _agents_ai_available,
)
app.include_router(agents_router)


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


# Notification routes (model, helper, endpoints) — extracted to notification_routes.py
from notification_routes import (
    router as notification_router,
    NotificationSettings,
    send_cluster_notifications,
    slack_service,
    email_service,
)
app.include_router(notification_router)


def run_minikube_init_playbook(
    playbook_path: str,
    cluster_name: str,
    job_id: str,
    custom_capa_image: dict = None,
):
    """Run Minikube CAPI initialization playbook (sync, called via asyncio.to_thread).

    Delegates the actual work to minikube_ops.configure_capi() while managing
    job progress tracking for the UI.
    """
    try:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["progress"] = 10
        jobs[job_id]["message"] = f"Configuring CAPI/CAPA on Minikube cluster '{cluster_name}' using clusterctl"
        jobs[job_id]["logs"] = ["=== ANSIBLE PLAYBOOK OUTPUT ===", ""]

        if custom_capa_image:
            jobs[job_id]["message"] = (
                f"Configuring CAPI/CAPA on Minikube cluster '{cluster_name}' using clusterctl "
                f"with custom image {custom_capa_image['repository']}:{custom_capa_image['tag']}"
            )

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        def on_output(line_text):
            jobs[job_id]["logs"].append(line_text)
            if "TASK" in line_text:
                current_progress = jobs[job_id]["progress"]
                if current_progress < 90:
                    jobs[job_id]["progress"] = min(current_progress + 5, 90)

        result = minikube_ops.configure_capi(
            profile_name=cluster_name,
            project_root=project_root,
            custom_capa_image=custom_capa_image,
            on_output=on_output,
        )

        jobs[job_id]["logs"].append("")
        jobs[job_id]["logs"].append("=== PLAYBOOK COMPLETED ===")
        jobs[job_id]["progress"] = 100

        if result["success"]:
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["message"] = f"CAPI/CAPA initialized successfully on cluster '{cluster_name}'"
        else:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["message"] = f"Failed to initialize CAPI/CAPA: {result['message']}"
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


# Static / reference-data routes — extracted to static_routes.py
from static_routes import (
    router as static_router,
    root,
    health_check,
    get_supported_versions,
    _get_supported_versions_sync,
    get_templates,
    analyze_yaml,
    get_onboarding_tour,
    get_available_diagnostic_checks,
    run_diagnostics,
    get_environment_overview,
    get_user_profile,
    get_build_templates,
    validate_config,
)
app.include_router(static_router)


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
        "success": True,
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

    return {"success": True, "cluster": cluster, "job": job_status}


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

    return {"success": True, "job_id": job_id, "message": "Cluster deletion started"}



# User Journey APIs — moved to static_routes.py


# Credential & connection-status routes — extracted to credentials_routes.py
from credentials_routes import (
    router as credentials_router,
    CredentialsUpdate,
    _get_rosa_status_sync,
    _get_ocp_connection_status_sync,
    get_rosa_status,
    get_config_status,
    get_credentials,
    save_credentials,
    get_ocp_connection_status,
    get_aws_credentials_status,
    get_guided_setup_status,
)
app.include_router(credentials_router)


# user/profile, build/templates, validate — moved to static_routes.py


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


# MCE features routes (get_mce_features, get_mce_yaml) — extracted to mce_features_routes.py


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


# get_mce_resources — extracted to mce_features_routes.py


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

        def camel_to_snake(name):
            special_cases = {'openShift': 'openshift', 'OpenShift': 'openshift'}
            for camel, snake in special_cases.items():
                if camel in name:
                    name = name.replace(camel, snake)
            s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
            return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

        snake_vars = {camel_to_snake(k): v for k, v in extra_vars.items()}

        env = os.environ.copy()
        env["KUBECONFIG"] = job_kubeconfig if job_kubeconfig else os.environ.get("KUBECONFIG", os.path.expanduser("~/.kube/config"))
        env["PYTHONUNBUFFERED"] = "1"

        cmd, env = build_playbook_command(
            playbook_path, extra_vars=snake_vars, verbosity=1, env=env,
        )

        print(f"[Playbook] Running: {' '.join(cmd)}")
        jobs[job_id]["progress"] = 30
        jobs[job_id]["message"] = "Executing ansible playbook"

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

        return {"success": True, "components": components, "timestamp": datetime.now().isoformat()}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get component versions: {str(e)}")


@app.get("/api/capi/cli-versions")
async def get_capi_cli_versions():
    """Get versions of CAPI-related CLI tools (clusterctl, minikube, kubectl)"""
    return await asyncio.to_thread(minikube_ops.get_tool_versions)


@app.get("/api/minikube/list-clusters")
async def list_minikube_clusters():
    """List available Minikube profiles (cached for 30 seconds)"""
    return await asyncio.to_thread(minikube_ops.list_profiles)


@app.get("/api/minikube/current-context")
async def get_current_kubectl_context():
    """Get the current kubectl context (active cluster)"""
    return await asyncio.to_thread(minikube_ops.get_current_context)


@app.get("/api/minikube/active-profile")
async def get_active_minikube_profile():
    """Get information about the active minikube cluster"""
    return await asyncio.to_thread(minikube_ops.get_active_profile)


@app.post("/api/minikube/verify-cluster")
async def verify_minikube_cluster(request: dict):
    """Verify if a Minikube cluster exists and is accessible"""
    cluster_name = request.get("cluster_name", "").strip()
    return await asyncio.to_thread(minikube_ops.verify_cluster, cluster_name)




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
    """Background task to create a minikube cluster (delegates to minikube_ops)."""
    try:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["logs"].append(f"Starting minikube cluster '{cluster_name}'...")
        jobs[job_id]["logs"].append(f"Running: minikube start --profile {cluster_name} --cpus=2 --memory=4096")
        jobs[job_id]["logs"].append("")

        result = minikube_ops.create_profile(
            cluster_name,
            on_output=lambda line: jobs[job_id]["logs"].append(line),
        )

        if result["success"]:
            if result.get("verified"):
                jobs[job_id]["logs"].append("Cluster verified successfully!")
            else:
                jobs[job_id]["logs"].append("Warning: Cluster created but kubectl verification returned an error.")
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["message"] = f"Cluster '{cluster_name}' created successfully"
            jobs[job_id]["completed_at"] = datetime.now()
        else:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["message"] = result["message"]

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

        # Validate name and check prerequisites via minikube_ops
        name_pattern = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
        if not name_pattern.match(cluster_name):
            return {
                "success": False,
                "message": "Invalid cluster name format",
                "suggestion": "Use lowercase letters, numbers, and hyphens only",
            }

        if not minikube_ops.is_minikube_installed():
            return {
                "success": False,
                "message": "Minikube is not installed",
                "suggestion": "Install Minikube first: brew install minikube",
            }

        status = minikube_ops.get_profile_status(cluster_name)
        if status["exists"]:
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

        return await asyncio.to_thread(minikube_ops.delete_profile, cluster_name)

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
    body = await request.json()
    cluster_name = body.get("cluster_name", "").strip()
    namespace = body.get("namespace", "ns-rosa-hcp")
    return await asyncio.to_thread(minikube_ops.get_capi_resources, cluster_name, namespace)


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
            "success": True,
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


# AI chat endpoint — extracted to ai_chat_routes.py
from ai_chat_routes import (
    router as ai_chat_router,
    ai_assistant_chat,
)
app.include_router(ai_chat_router)


# Test suite routes — extracted to test_suite_routes.py
from test_suite_routes import (
    router as test_suite_router,
    test_suite_runs,
    TestSuiteRun,
    list_test_suites,
    run_test_suite,
    get_test_suite_status,
    get_test_suite_history,
)
app.include_router(test_suite_router)

# Workflow & trigger routes — extracted to workflow_routes.py
from workflow_routes import (
    router as workflow_router,
    WORKFLOWS_FILE,
    _normalize_workflow,
    _load_workflows,
    _save_workflows,
    WorkflowSave,
    TriggerCreate,
    _get_trigger_or_404,
    _fire_and_update,
)
app.include_router(workflow_router)

# Re-export trigger_service symbols for backward compat (tests patch via app.*)
import logging as _trigger_logging
_trigger_logger = _trigger_logging.getLogger("trigger_routes")
from trigger_service import (
    TRIGGER_STATE_FILE,
    TRIGGER_MIN_INTERVAL,
    AUTO_DISABLE_THRESHOLD,
    MAX_PAGINATION_LIMIT,
    _trigger_last_fire,
    _active_trigger_runs,
    _load_trigger_state,
    _save_trigger_state,
    _send_trigger_notification,
    _update_trigger_after_run,
    _fire_trigger_workflow,
    check_rate_limit,
    TriggerScheduler,
    _trigger_scheduler,
)


# Cluster actions & specs routes — extracted to cluster_actions_routes.py
from cluster_actions_routes import (
    router as cluster_actions_router,
    _load_feature_registry_full,
    _load_feature_registry,
    _get_registry,
    _get_feature_index,
    CLUSTER_FEATURE_REGISTRY,
    _FEATURE_INDEX,
    _validate_cluster_name,
    _validate_feature_value,
    _find_feature,
    _build_json_merge_patch,
    ClusterActionRequest,
    ACTION_HISTORY_FILE,
    _load_action_history,
    _save_action_history,
    _record_action,
    _cluster_locks,
    _CLUSTER_LOCKS_MAX,
    _get_cluster_lock,
    SPECS_DIR,
    _find_spec_file,
    _resolve_spec_to_plan,
    execute_cluster_actions,
    get_action_history,
    provision_cluster_with_features,
    discover_clusters,
    get_cluster_feature_status,
    list_cluster_specs,
    get_cluster_spec,
    plan_cluster_spec,
    execute_cluster_spec,
    save_cluster_spec,
    get_feature_registry,
    get_suite_features,
)
app.include_router(cluster_actions_router)

# MCE environment management routes — extracted to mce_environments_routes.py
from mce_environments_routes import (
    router as mce_environments_router,
    list_mce_environments,
    get_mce_environment,
    save_mce_environment,
    update_mce_environment_status,
    get_mce_environment_stats,
    search_mce_environments,
)
app.include_router(mce_environments_router)


# AWS dashboard routes (Jenkins, GitHub, AWS usage) — extracted to aws_dashboard_routes.py
from aws_dashboard_routes import (
    router as aws_dashboard_router,
    _collect_aws_usage_data,
    _get_aws_history_db,
    _init_aws_history_db,
    _save_aws_usage_snapshot,
    _aws_usage_snapshot_loop,
    get_jenkins_test_results_trend,
    get_github_repo_activity,
    get_aws_usage,
    get_aws_usage_trend,
    get_aws_config,
    get_single_resource_usage,
    get_resource_details,
)
app.include_router(aws_dashboard_router)

# MCE features routes (get_mce_features, get_mce_yaml, get_mce_resources) — extracted to mce_features_routes.py
from mce_features_routes import (
    router as mce_features_router,
    _get_mce_features_sync,
    get_mce_features,
    get_mce_yaml,
    get_mce_resources,
)
app.include_router(mce_features_router)


@app.on_event("startup")
async def start_trigger_scheduler():
    await _trigger_scheduler.start()


@app.on_event("shutdown")
async def stop_trigger_scheduler():
    await _trigger_scheduler.stop()


@app.on_event("startup")
async def start_aws_snapshot_collector():
    asyncio.create_task(_aws_usage_snapshot_loop())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
