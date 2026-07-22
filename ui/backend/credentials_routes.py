"""
Credentials & connection-status service module — FastAPI router for
credential management and connectivity-check endpoints.

Endpoints moved here from app.py:
  GET    /api/config/status
  GET    /api/credentials
  POST   /api/credentials
  GET    /api/rosa/status
  GET    /api/ocp/connection-status
  GET    /api/aws/credentials-status
  GET    /api/guided-setup/status

Also contains:
  CredentialsUpdate        — Pydantic model
  _get_rosa_status_sync()  — sync helper for ROSA CLI auth check
  _get_ocp_connection_status_sync() — sync helper for OCP Hub login test
"""

import asyncio
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from typing import Dict

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from shared_state import rosa_status_cache, ocp_status_cache

router = APIRouter()


def _resolve(name: str):
    """Look up *name* via the app module so that unittest.mock.patch on
    ``app.<name>`` takes effect even though the endpoint lives here."""
    app_mod = sys.modules.get("app")
    if app_mod is not None:
        return getattr(app_mod, name)
    return globals()[name]


class CredentialsUpdate(BaseModel):
    credentials: Dict[str, str]


# ── Helpers ─────────────────────────────────────────────────────────────


def _get_rosa_status_sync():
    """Check ROSA/OCM authentication status via OCM API with CLI fallback."""
    import time

    current_time = time.time()
    if (
        rosa_status_cache["data"] is not None
        and current_time - rosa_status_cache["timestamp"] < rosa_status_cache["ttl"]
    ):
        return rosa_status_cache["data"]

    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from agents.ocm_client import get_ocm_client
        ocm = get_ocm_client()
        result = ocm.whoami()

        if result and result.get("authenticated"):
            response_data = {
                "success": True,
                "authenticated": True,
                "status": "success",
                "message": result.get("message", "Authenticated"),
                "user_info": result.get("user_info", {}),
                "raw_output": "",
                "command": result.get("source", "ocm_api"),
                "last_checked": datetime.now().isoformat(),
            }
            rosa_status_cache["data"] = response_data
            rosa_status_cache["timestamp"] = current_time
            return response_data
        else:
            return {
                "success": False,
                "authenticated": False,
                "status": "error",
                "message": "OCM authentication failed or credentials not configured",
                "error": "Set OCM_CLIENT_ID and OCM_CLIENT_SECRET environment variables, or run 'rosa login'",
                "fix_command": "rosa login --env staging --use-auth-code",
                "suggestion": "Configure OCM service account credentials or authenticate via ROSA CLI",
                "last_checked": datetime.now().isoformat(),
            }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
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
            "success": False,
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
            "success": False,
            "authenticated": False,
            "status": "error",
            "message": f"Unexpected error checking ROSA status: {str(e)}",
            "error": str(e),
            "fix_command": "rosa whoami",
            "suggestion": "Check your ROSA CLI installation and try again",
            "last_checked": datetime.now().isoformat(),
        }


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
                "success": False,
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
                "success": False,
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
                "success": False,
                "connected": False,
                "status": "missing_api_url",
                "message": "OCP_HUB_API_URL not configured",
                "suggestion": "Configure OCP_HUB_API_URL in vars/user_vars.yml",
                "last_checked": datetime.now().isoformat(),
            }

        if not ocp_user or not ocp_password:
            return {
                "success": False,
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

                # Detect MCE version
                mce_version = ""
                try:
                    mce_result = subprocess.run(
                        ["oc", "get", "mce", "-ojsonpath={.items[0].status.currentVersion}"],
                        capture_output=True, text=True, timeout=10
                    )
                    if mce_result.returncode == 0 and mce_result.stdout.strip():
                        mce_version = mce_result.stdout.strip()
                        cluster_info["mce_version"] = mce_version
                except Exception:
                    pass

                # Save MCE version to the environment record
                if mce_version:
                    try:
                        match = re.search(r"api\.([^.]+)", ocp_api_url)
                        if match:
                            cluster_name = match.group(1)
                            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                            scripts_dir = os.path.join(project_root, "scripts")
                            sys.path.insert(0, scripts_dir)
                            from mce_env_manager import MCEEnvManager
                            manager = MCEEnvManager()
                            env = manager.get_environment(cluster_name)
                            if env:
                                env_cluster = env.get("data", {}).get("cluster", {})
                                env_cluster["mce_version"] = mce_version
                                manager.save_db()
                    except Exception as env_err:
                        print(f"Warning: could not save MCE version to environment: {env_err}")

                response_data = {
                    "success": True,
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
                    "success": True,
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
                "success": False,
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
            "success": False,
            "connected": False,
            "status": "timeout",
            "message": "Connection test timed out after 30 seconds",
            "suggestion": "Check network connectivity and API URL",
            "api_url": ocp_api_url,
            "last_checked": datetime.now().isoformat(),
        }
    except FileNotFoundError:
        return {
            "success": False,
            "connected": False,
            "status": "oc_not_found",
            "message": "OpenShift CLI (oc) not found",
            "suggestion": "Install the OpenShift CLI (oc) command",
            "last_checked": datetime.now().isoformat(),
        }
    except yaml.YAMLError as e:
        return {
            "success": False,
            "connected": False,
            "status": "invalid_yaml",
            "message": f"Invalid YAML format in vars/user_vars.yml: {str(e)}",
            "suggestion": "Fix the YAML syntax errors in vars/user_vars.yml",
            "last_checked": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "success": False,
            "connected": False,
            "status": "error",
            "message": f"Error testing OCP connection: {str(e)}",
            "suggestion": "Check configuration and try again",
            "last_checked": datetime.now().isoformat(),
        }


# ── Endpoints ────────────────────────────────────────────────────────────


@router.get("/api/rosa/status")
async def get_rosa_status():
    """Check ROSA CLI authentication status — offloads to thread pool."""
    return await asyncio.to_thread(_resolve("_get_rosa_status_sync"))


@router.get("/api/config/status")
async def get_config_status():
    """Check if vars/user_vars.yml has been properly configured"""
    try:
        # Path to user_vars.yml relative to the project root
        # Go up from ui/backend/app.py -> ui/backend -> ui -> automation-capi (project root)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        config_path = os.path.join(project_root, "vars", "user_vars.yml")

        if not os.path.exists(config_path):
            return {
                "success": True,
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
            "success": True,
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
            "success": False,
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
            "success": False,
            "configured": False,
            "status": "error",
            "message": f"Error reading configuration: {str(e)}",
            "missing_fields": [],
            "empty_fields": [],
            "suggestion": "Check file permissions and try again",
            "last_checked": datetime.now().isoformat(),
        }


# Credentials management endpoints
@router.get("/api/credentials")
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


@router.post("/api/credentials")
async def save_credentials(update: CredentialsUpdate):
    """Save credentials to vars/user_vars.yml and to the active MCE environment record"""
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

        # Also save credentials to the active MCE environment record
        api_url = update.credentials.get("OCP_HUB_API_URL", config.get("OCP_HUB_API_URL", ""))
        if api_url:
            try:
                match = re.search(r"api\.([^.]+)", api_url)
                if match:
                    cluster_name = match.group(1)
                    scripts_dir = os.path.join(project_root, "scripts")
                    sys.path.insert(0, scripts_dir)
                    from mce_env_manager import MCEEnvManager
                    manager = MCEEnvManager()
                    env = manager.get_environment(cluster_name)
                    if env:
                        manager.update_credentials(cluster_name, update.credentials)
            except Exception as env_err:
                print(f"Warning: could not save credentials to environment record: {env_err}")

        return {"success": True, "message": "Credentials saved successfully"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving credentials: {str(e)}")


@router.get("/api/ocp/connection-status")
async def get_ocp_connection_status():
    """Test OpenShift Hub connection — offloads to thread pool."""
    return await asyncio.to_thread(_resolve("_get_ocp_connection_status_sync"))


@router.get("/api/aws/credentials-status")
async def get_aws_credentials_status():
    """Check AWS credentials validity and provide detailed guidance"""
    try:
        # Path to user_vars.yml
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        config_path = os.path.join(project_root, "vars", "user_vars.yml")

        if not os.path.exists(config_path):
            return {
                "success": False,
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
                "success": False,
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
                try:
                    identity = json.loads(result.stdout)
                    return {
                        "success": True,
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
                        "success": True,
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
                    "success": False,
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
                "success": False,
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
                "success": False,
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
            "success": False,
            "valid": False,
            "status": "invalid_yaml",
            "message": f"Invalid YAML in configuration file: {str(e)}",
            "credentials_configured": False,
            "suggestion": "Fix YAML syntax in vars/user_vars.yml",
            "last_checked": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "success": False,
            "valid": False,
            "status": "error",
            "message": f"Error checking AWS credentials: {str(e)}",
            "credentials_configured": False,
            "suggestion": "Check configuration and try again",
            "last_checked": datetime.now().isoformat(),
        }


@router.get("/api/guided-setup/status")
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
            "success": True,
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
            "success": False,
            "current_step": 1,
            "next_action": "error",
            "all_prerequisites_met": False,
            "error": f"Error checking guided setup status: {str(e)}",
            "last_checked": datetime.now().isoformat(),
        }
