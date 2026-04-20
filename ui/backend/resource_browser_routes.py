"""
Resource Browser routes -- FastAPI router for kubectl/oc resource
browsing, command execution, and YAML path management.

Endpoints moved here from app.py:
  POST   /api/ocp/execute-command
  POST   /api/minikube/get-active-resources
  POST   /api/minikube/get-resource-detail
  POST   /api/ocp/get-resource-detail
  GET    /api/rosa/last-yaml-path
  POST   /api/rosa/save-yaml-path
  GET    /api/provisioning/log-forwarding-config/{cluster_name}

"""

import asyncio
import os
import re
import subprocess
import sys

import yaml
from fastapi import APIRouter, Request

import minikube_ops

router = APIRouter()


def _resolve(name: str):
    """Look up *name* via the app module so that unittest.mock.patch on
    ``app.<name>`` takes effect even though the endpoint lives here."""
    app_mod = sys.modules.get("app")
    if app_mod is not None:
        return getattr(app_mod, name)
    return globals()[name]


# ---------------------------------------------------------------------------
# POST /api/ocp/execute-command
# ---------------------------------------------------------------------------

@router.post("/api/ocp/execute-command")
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


# ---------------------------------------------------------------------------
# POST /api/minikube/get-active-resources
# ---------------------------------------------------------------------------

@router.post("/api/minikube/get-active-resources")
async def get_minikube_active_resources(request: Request):
    """Get active CAPI/ROSA resources from the Minikube cluster"""
    body = await request.json()
    cluster_name = body.get("cluster_name", "").strip()
    namespace = body.get("namespace", "ns-rosa-hcp")
    return await asyncio.to_thread(minikube_ops.get_capi_resources, cluster_name, namespace)


# ---------------------------------------------------------------------------
# POST /api/minikube/get-resource-detail
# ---------------------------------------------------------------------------

@router.post("/api/minikube/get-resource-detail")
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


# ---------------------------------------------------------------------------
# POST /api/ocp/get-resource-detail
# ---------------------------------------------------------------------------

@router.post("/api/ocp/get-resource-detail")
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


# ---------------------------------------------------------------------------
# GET /api/rosa/last-yaml-path
# ---------------------------------------------------------------------------

@router.get("/api/rosa/last-yaml-path")
async def get_last_rosa_yaml_path():
    """Get the last used YAML file path for ROSA HCP provisioning"""
    last_rosa_yaml_path = _resolve("last_rosa_yaml_path")
    return {
        "success": True,
        "path": last_rosa_yaml_path.get("path"),
    }


# ---------------------------------------------------------------------------
# POST /api/rosa/save-yaml-path
# ---------------------------------------------------------------------------

@router.post("/api/rosa/save-yaml-path")
async def save_rosa_yaml_path(request: Request):
    """Save the YAML file path used for ROSA HCP provisioning"""
    try:
        body = await request.json()
        path = body.get("path")

        last_rosa_yaml_path = _resolve("last_rosa_yaml_path")
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


# ---------------------------------------------------------------------------
# GET /api/provisioning/log-forwarding-config/{cluster_name}
# ---------------------------------------------------------------------------

@router.get("/api/provisioning/log-forwarding-config/{cluster_name}")
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
