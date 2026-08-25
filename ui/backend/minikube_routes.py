"""
Minikube & CAPI component routes -- FastAPI router for Minikube cluster
lifecycle management and CAPI/CAPA component version queries.

Endpoints moved here from app.py:
  GET    /api/capi/component-versions
  GET    /api/capi/cli-versions
  GET    /api/minikube/list-clusters
  GET    /api/minikube/current-context
  GET    /api/minikube/active-profile
  POST   /api/minikube/verify-cluster
  POST   /api/minikube/initialize-capi
  POST   /api/minikube/create-cluster
  POST   /api/minikube/delete-cluster
  POST   /api/minikube/execute-command

Also contains:
  run_minikube_init_playbook  -- sync helper for CAPI init job tracking
  _run_minikube_create        -- sync helper for minikube create job tracking
"""

import asyncio
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request

import minikube_ops

router = APIRouter()


def _resolve(name: str):
    """Look up *name* via the app module so that unittest.mock.patch on
    ``app.<name>`` takes effect even though the endpoint lives here.

    The backend may be started either as a module (``uvicorn app:app``,
    registered as ``app``) or as a script (``python app.py``, registered as
    ``__main__``). Check both, then fall back to shared_state (the single
    source of truth for these globals) so ``jobs`` resolves regardless of how
    the process was launched."""
    for mod_name in ("app", "__main__"):
        app_mod = sys.modules.get(mod_name)
        if app_mod is not None and hasattr(app_mod, name):
            return getattr(app_mod, name)
    import shared_state
    if hasattr(shared_state, name):
        return getattr(shared_state, name)
    return globals()[name]


# ---------------------------------------------------------------------------
# Sync helpers (called via asyncio.to_thread)
# ---------------------------------------------------------------------------

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
    jobs = _resolve("jobs")
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


def _run_minikube_create(cluster_name: str, job_id: str):
    """Background task to create a minikube cluster (delegates to minikube_ops)."""
    jobs = _resolve("jobs")
    try:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["logs"].append(f"Starting minikube cluster '{cluster_name}'...")
        jobs[job_id]["logs"].append(f"Running: minikube start --profile {cluster_name} --cpus=2 --memory=4096 --cni=kindnet")
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


# ---------------------------------------------------------------------------
# GET /api/capi/component-versions
# ---------------------------------------------------------------------------

@router.get("/api/capi/component-versions")
async def get_capi_component_versions(cluster_name: str = None, environment: str = None):
    """Get CAPI component versions from the cluster

    Args:
        cluster_name: Optional cluster name (for Minikube context)
        environment: Optional environment type ('mce' or 'minikube')
    """
    def _extract_version(image):
        if not image:
            return "unknown"
        if "@sha256:" in image:
            sha = image.split("@sha256:")[-1][:12]
            repo = image.split("@")[0]
            repo_name = repo.split("/")[-1] if "/" in repo else repo
            return f"{repo_name} ({sha})"
        if ":" in image:
            return image.split(":")[-1]
        return "unknown"

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

        # Get CAPI controller version (try capi-system first, then multicluster-engine for MCE)
        try:
            capi_found = False
            for capi_ns in ["capi-system", "multicluster-engine"]:
                capi_result = subprocess.run(
                    cli_cmd
                    + [
                        "get",
                        "deployment",
                        "capi-controller-manager",
                        "-n",
                        capi_ns,
                        "-o",
                        "jsonpath={.spec.template.spec.containers[?(@.name=='manager')].image}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if capi_result.returncode == 0 and capi_result.stdout.strip():
                    image = capi_result.stdout.strip()
                    version = _extract_version(image)

                    yaml_result = subprocess.run(
                        cli_cmd
                        + [
                            "get",
                            "deployment",
                            "capi-controller-manager",
                            "-n",
                            capi_ns,
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
                            "namespace": capi_ns,
                        }
                    )
                    capi_found = True
                    break
            if not capi_found:
                components.append({"name": "CAPI Controller", "version": "unknown", "enabled": False})
        except Exception as e:
            print(f"Failed to get CAPI controller version: {e}")
            components.append({"name": "CAPI Controller", "version": "unknown", "enabled": False})

        # Get CAPA controller version (try capa-system first, then multicluster-engine for MCE)
        try:
            capa_found = False
            for capa_ns in ["capa-system", "multicluster-engine"]:
                capa_result = subprocess.run(
                    cli_cmd
                    + [
                        "get",
                        "deployment",
                        "capa-controller-manager",
                        "-n",
                        capa_ns,
                        "-o",
                        "jsonpath={.spec.template.spec.containers[?(@.name=='manager')].image}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if capa_result.returncode == 0 and capa_result.stdout.strip():
                    image = capa_result.stdout.strip()
                    version = _extract_version(image)
                    if "quay.io/melserng" in image:
                        repo = image.split("@")[0] if "@" in image else image.rsplit(":", 1)[0]
                        repo_name = repo.split("/")[-1] if "/" in repo else repo
                        version = f"{version} (custom: {repo_name})"

                    yaml_result = subprocess.run(
                        cli_cmd
                        + [
                            "get",
                            "deployment",
                            "capa-controller-manager",
                            "-n",
                            capa_ns,
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
                            "namespace": capa_ns,
                        }
                    )
                    capa_found = True
                    break
            if not capa_found:
                components.append({"name": "CAPA Controller", "version": "unknown", "enabled": False})
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


# ---------------------------------------------------------------------------
# GET /api/capi/cli-versions
# ---------------------------------------------------------------------------

@router.get("/api/capi/cli-versions")
async def get_capi_cli_versions():
    """Get versions of CAPI-related CLI tools (clusterctl, minikube, kubectl)"""
    return await asyncio.to_thread(minikube_ops.get_tool_versions)


# ---------------------------------------------------------------------------
# GET /api/minikube/list-clusters
# ---------------------------------------------------------------------------

@router.get("/api/minikube/list-clusters")
async def list_minikube_clusters():
    """List available Minikube profiles (cached for 30 seconds)"""
    return await asyncio.to_thread(minikube_ops.list_profiles)


# ---------------------------------------------------------------------------
# GET /api/minikube/current-context
# ---------------------------------------------------------------------------

@router.get("/api/minikube/current-context")
async def get_current_kubectl_context():
    """Get the current kubectl context (active cluster)"""
    return await asyncio.to_thread(minikube_ops.get_current_context)


# ---------------------------------------------------------------------------
# GET /api/minikube/active-profile
# ---------------------------------------------------------------------------

@router.get("/api/minikube/active-profile")
async def get_active_minikube_profile():
    """Get information about the active minikube cluster"""
    return await asyncio.to_thread(minikube_ops.get_active_profile)


# ---------------------------------------------------------------------------
# POST /api/minikube/verify-cluster
# ---------------------------------------------------------------------------

@router.post("/api/minikube/verify-cluster")
async def verify_minikube_cluster(request: dict):
    """Verify if a Minikube cluster exists and is accessible"""
    cluster_name = request.get("cluster_name", "").strip()
    return await asyncio.to_thread(minikube_ops.verify_cluster, cluster_name)


# ---------------------------------------------------------------------------
# POST /api/minikube/initialize-capi
# ---------------------------------------------------------------------------

@router.post("/api/minikube/initialize-capi")
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

        jobs = _resolve("jobs")

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
            _resolve("run_minikube_init_playbook"),
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


# ---------------------------------------------------------------------------
# POST /api/minikube/create-cluster
# ---------------------------------------------------------------------------

@router.post("/api/minikube/create-cluster")
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

        jobs = _resolve("jobs")

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
        asyncio.create_task(asyncio.to_thread(_resolve("_run_minikube_create"), cluster_name, job_id))

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


# ---------------------------------------------------------------------------
# POST /api/minikube/delete-cluster
# ---------------------------------------------------------------------------

@router.post("/api/minikube/delete-cluster")
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


# ---------------------------------------------------------------------------
# POST /api/minikube/execute-command
# ---------------------------------------------------------------------------

@router.post("/api/minikube/execute-command")
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
