"""
Resource browser routes — FastAPI router for resource browsing and command execution.

Endpoints moved here from app.py:
  POST /api/ocp/execute-command                              (execute OCP command)
  POST /api/minikube/get-active-resources                    (get active CAPI resources)
  POST /api/minikube/get-resource-detail                     (get resource YAML detail)
  POST /api/ocp/get-resource-detail                          (get OCP resource YAML detail)
  GET  /api/rosa/last-yaml-path                              (last used YAML path)
  POST /api/rosa/save-yaml-path                              (save YAML path)
  GET  /api/provisioning/log-forwarding-config/{cluster_name} (log forwarding config)
"""

import asyncio
import os
import re
import subprocess
import sys
from datetime import datetime

from fastapi import APIRouter, Request

import minikube_ops

router = APIRouter()


def _resolve(name: str):
    """Look up *name* in the ``app`` module at call time.

    This keeps tests working: they patch ``app.last_rosa_yaml_path``, etc.,
    and this function reads the patched value instead of a stale
    import-time reference.
    """
    _app = sys.modules.get("app")
    if _app is None:
        raise RuntimeError("app module not loaded")
    return getattr(_app, name)


# ── OCP command execution ─────────────────────────────────────────────


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


# ── Active resources ──────────────────────────────────────────────────


# Re-use the same get-active-resources and get-resource-detail endpoints for Minikube
# since they work with kubectl and are provider-agnostic
@router.post("/api/minikube/get-active-resources")
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


# ── Resource detail ───────────────────────────────────────────────────


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


# ── YAML path & log forwarding ───────────────────────────────────────


@router.get("/api/rosa/last-yaml-path")
async def get_last_rosa_yaml_path():
    """Get the last used YAML file path for ROSA HCP provisioning"""
    last_rosa_yaml_path = _resolve("last_rosa_yaml_path")
    return {
        "success": True,
        "path": last_rosa_yaml_path.get("path"),
    }


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
