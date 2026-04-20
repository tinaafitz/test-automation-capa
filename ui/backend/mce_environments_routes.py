"""
MCE Environment Management service module — FastAPI router for MCE test
environment CRUD, stats, and search endpoints.

Endpoints moved here from app.py:
  GET    /api/mce-environments
  GET    /api/mce-environments/{cluster_name}
  POST   /api/mce-environments
  POST   /api/mce-environments/{cluster_name}/status
  GET    /api/mce-environments/stats/summary
  GET    /api/mce-environments/search/{query}
"""

import os
import re
import sys
import traceback
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from typing import Optional

router = APIRouter()


def _resolve(name: str):
    """Look up *name* via the app module so that unittest.mock.patch on
    ``app.<name>`` takes effect even though the endpoint lives here."""
    app_mod = sys.modules.get("app")
    if app_mod is not None:
        return getattr(app_mod, name)
    return globals()[name]


# ── Endpoints ────────────────────────────────────────────────────────────


@router.get("/api/mce-environments")
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
        traceback.print_exc()
        return {
            "success": False,
            "message": f"Error listing environments: {str(e)}",
            "environments": [],
            "total": 0,
        }


@router.get("/api/mce-environments/{cluster_name}")
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
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error getting environment: {str(e)}")


@router.post("/api/mce-environments")
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
        traceback.print_exc()
        return {"success": False, "message": f"Error saving environment: {str(e)}"}


@router.post("/api/mce-environments/{cluster_name}/status")
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
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error updating status: {str(e)}")


@router.get("/api/mce-environments/stats/summary")
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
        traceback.print_exc()
        return {
            "success": False,
            "message": f"Error getting stats: {str(e)}",
            "stats": {"total": 0, "byPlatform": {}, "byStatus": {}, "recent": []},
        }


@router.get("/api/mce-environments/search/{query}")
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
        traceback.print_exc()
        return {
            "success": False,
            "message": f"Error searching environments: {str(e)}",
            "results": [],
            "total": 0,
        }
