"""
Shared minikube operations module.

Used by both the CAPA CLI (./capa) and the UI backend (app.py).
All functions are synchronous (subprocess-based). The backend wraps
them with asyncio.to_thread() for async use.
"""

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import yaml
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Profile list cache (shared across callers within the same process)
# ---------------------------------------------------------------------------
_cache_lock = threading.Lock()
_profile_cache: Dict[str, Any] = {
    "data": None,
    "timestamp": 0.0,
    "ttl": 30,
}


def invalidate_cache():
    """Force the next list_profiles() call to fetch fresh data."""
    with _cache_lock:
        _profile_cache["timestamp"] = 0.0


# ---------------------------------------------------------------------------
# Installation check
# ---------------------------------------------------------------------------
def is_minikube_installed() -> bool:
    """Return True if the minikube binary is available."""
    try:
        result = subprocess.run(
            ["minikube", "version"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return False


# ---------------------------------------------------------------------------
# Profile lifecycle
# ---------------------------------------------------------------------------
def _update_cache(result: Dict[str, Any]) -> Dict[str, Any]:
    """Thread-safe cache update. Returns the result for convenience."""
    with _cache_lock:
        _profile_cache["data"] = result
        _profile_cache["timestamp"] = time.time()
    return result


def list_profiles(*, use_cache: bool = True) -> Dict[str, Any]:
    """List minikube profiles. Returns dict with clusters, minikube_installed, message."""
    with _cache_lock:
        cache_age = time.time() - _profile_cache["timestamp"]
        if use_cache and _profile_cache["data"] is not None and cache_age < _profile_cache["ttl"]:
            return _profile_cache["data"]

    try:
        if not is_minikube_installed():
            return _update_cache({
                "clusters": [],
                "minikube_installed": False,
                "message": "Minikube is not installed",
                "suggestion": "Install Minikube first: brew install minikube",
            })

        list_result = subprocess.run(
            ["minikube", "profile", "list", "-o", "json"],
            capture_output=True, text=True, timeout=30,
        )

        if list_result.returncode != 0:
            return _update_cache({
                "clusters": [],
                "minikube_installed": True,
                "message": "No Minikube clusters found",
                "suggestion": "Create a cluster with: minikube start --profile <cluster-name>",
            })

        try:
            profiles_data = json.loads(list_result.stdout)
            clusters = []
            if "valid" in profiles_data:
                for profile in profiles_data["valid"]:
                    clusters.append(profile["Name"])

            return _update_cache({
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
            })

        except json.JSONDecodeError:
            return _update_cache({
                "clusters": [],
                "minikube_installed": True,
                "message": "Failed to parse minikube profile list",
                "suggestion": "Check minikube installation",
            })

    except Exception as e:
        return _update_cache({
            "clusters": [],
            "minikube_installed": False,
            "message": f"Error listing Minikube clusters: {str(e)}",
            "suggestion": "Check Minikube installation and permissions",
        })


def get_profile_status(profile_name: str) -> Dict[str, Any]:
    """Get detailed status for a minikube profile."""
    try:
        result = subprocess.run(
            ["minikube", "status", "-p", profile_name, "-o", "json"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return {
                "exists": False,
                "status": None,
                "message": f"Profile '{profile_name}' does not exist",
            }

        status_data = json.loads(result.stdout)
        return {
            "exists": True,
            "status": status_data,
            "host": status_data.get("Host", "Unknown"),
            "kubelet": status_data.get("Kubelet", "Unknown"),
            "apiserver": status_data.get("APIServer", "Unknown"),
            "kubeconfig": status_data.get("Kubeconfig", "Unknown"),
            "driver": status_data.get("Driver", "Unknown"),
            "is_running": status_data.get("Host", "") == "Running",
            "message": f"Profile '{profile_name}' status: {status_data.get('Host', 'Unknown')}",
        }
    except json.JSONDecodeError:
        return {"exists": False, "status": None, "message": "Failed to parse minikube status"}
    except subprocess.TimeoutExpired:
        return {"exists": False, "status": None, "message": "Minikube status command timed out"}
    except Exception as e:
        return {"exists": False, "status": None, "message": f"Error: {str(e)}"}


_POD_NETWORK_FIX_DS = """
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: pod-network-fix
  namespace: kube-system
  labels:
    app: pod-network-fix
spec:
  selector:
    matchLabels:
      app: pod-network-fix
  template:
    metadata:
      labels:
        app: pod-network-fix
    spec:
      hostNetwork: true
      hostPID: true
      tolerations:
        - operator: Exists
          effect: NoSchedule
      initContainers:
        - name: fix-iptables
          image: busybox:1.28
          command:
            - /bin/sh
            - -c
            - |
              iptables -C FORWARD -s 10.244.0.0/16 -j ACCEPT 2>/dev/null || iptables -I FORWARD 1 -s 10.244.0.0/16 -j ACCEPT
              iptables -C FORWARD -d 10.244.0.0/16 -j ACCEPT 2>/dev/null || iptables -I FORWARD 2 -d 10.244.0.0/16 -j ACCEPT
              iptables -t nat -C POSTROUTING -s 10.244.0.0/16 ! -d 10.244.0.0/16 -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -s 10.244.0.0/16 ! -d 10.244.0.0/16 -j MASQUERADE
              sysctl -w net.ipv4.ip_forward=1
          securityContext:
            privileged: true
          volumeMounts:
            - name: xtables-lock
              mountPath: /run/xtables.lock
      containers:
        - name: pause
          image: registry.k8s.io/pause:3.9
          resources:
            requests:
              cpu: "1m"
              memory: "2Mi"
            limits:
              cpu: "10m"
              memory: "10Mi"
      volumes:
        - name: xtables-lock
          hostPath:
            path: /run/xtables.lock
            type: FileOrCreate
"""


def _apply_pod_network_fix(profile_name: str, on_output=None) -> None:
    """Apply iptables FORWARD accept rules for pod CIDR via a privileged DaemonSet.

    Needed because kube-proxy sets FORWARD chain policy to DROP on podman rootless
    minikube, which blocks pod-to-pod and pod-to-service traffic even with kindnet.
    """
    if on_output:
        on_output("Applying pod network fix (iptables FORWARD rules)...")
    try:
        result = subprocess.run(
            ["kubectl", "apply", "--context", profile_name, "-f", "-"],
            input=_POD_NETWORK_FIX_DS,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if on_output:
            if result.stdout:
                on_output(result.stdout.strip())
            if result.returncode != 0 and result.stderr:
                on_output(f"Warning: pod-network-fix: {result.stderr.strip()}")
    except Exception as e:
        if on_output:
            on_output(f"Warning: could not apply pod-network-fix DaemonSet: {e}")


def create_profile(profile_name: str, cpus: int = 2, memory: int = 4096,
                   on_output=None) -> Dict[str, Any]:
    """Create a minikube profile. Streams output via on_output callback if provided."""
    name_pattern = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
    if not name_pattern.match(profile_name):
        return {
            "success": False,
            "message": "Invalid cluster name format",
            "suggestion": "Use lowercase letters, numbers, and hyphens only",
        }

    if not is_minikube_installed():
        return {
            "success": False,
            "message": "Minikube is not installed",
            "suggestion": "Install Minikube first: brew install minikube",
        }

    # Check if already exists
    status = get_profile_status(profile_name)
    if status["exists"]:
        return {
            "success": False,
            "message": f"Cluster '{profile_name}' already exists",
            "suggestion": "Choose a different name or delete the existing cluster",
        }

    try:
        process = subprocess.Popen(
            ["minikube", "start", "--profile", profile_name,
             f"--cpus={cpus}", f"--memory={memory}", "--cni=kindnet"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        for line in iter(process.stdout.readline, ''):
            line_text = line.rstrip()
            if line_text and on_output:
                on_output(line_text)

        process.wait(timeout=300)

        if process.returncode != 0:
            invalidate_cache()
            return {
                "success": False,
                "message": f"Failed to create cluster '{profile_name}'",
            }

        # Fix pod networking: kindnet uses ptp CNI with ipMasq=true, but kube-proxy sets
        # FORWARD chain policy to DROP. We need to ACCEPT pod CIDR traffic explicitly.
        # Also add a masquerade rule for pod egress. These are idempotent (checked before insert).
        _apply_pod_network_fix(profile_name, on_output)

        # Verify
        kubectl_test = subprocess.run(
            ["kubectl", "cluster-info", "--context", profile_name],
            capture_output=True, text=True, timeout=30,
        )

        invalidate_cache()
        return {
            "success": True,
            "message": f"Cluster '{profile_name}' created successfully",
            "verified": kubectl_test.returncode == 0,
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Cluster creation timed out after 5 minutes"}
    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)}"}


def delete_profile(profile_name: str) -> Dict[str, Any]:
    """Delete a minikube profile."""
    try:
        result = subprocess.run(
            ["minikube", "delete", "--profile", profile_name],
            capture_output=True, text=True, timeout=120,
        )

        invalidate_cache()

        if result.returncode == 0:
            return {
                "success": True,
                "message": f"Cluster '{profile_name}' deleted successfully",
                "output": result.stdout,
            }
        else:
            return {
                "success": False,
                "message": f"Failed to delete cluster: {result.stderr}",
            }

    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Cluster deletion timed out"}
    except Exception as e:
        return {"success": False, "message": f"Error deleting cluster: {str(e)}"}


# ---------------------------------------------------------------------------
# kubectl context
# ---------------------------------------------------------------------------
def get_current_context() -> Dict[str, Any]:
    """Get the current kubectl context."""
    try:
        result = subprocess.run(
            ["kubectl", "config", "current-context"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return {"success": False, "current_context": None, "message": "No current kubectl context set"}

        return {
            "success": True,
            "current_context": result.stdout.strip(),
            "message": f"Current context: {result.stdout.strip()}",
        }
    except Exception as e:
        return {"success": False, "current_context": None, "message": f"Error: {str(e)}"}


def switch_context(profile_name: str) -> Dict[str, Any]:
    """Switch kubectl context to the given profile."""
    try:
        result = subprocess.run(
            ["kubectl", "config", "use-context", profile_name],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return {"success": False, "message": f"Failed to switch context to '{profile_name}': {result.stderr}"}

        return {"success": True, "message": f"Switched to context '{profile_name}'"}
    except Exception as e:
        return {"success": False, "message": f"Error switching context: {str(e)}"}


# ---------------------------------------------------------------------------
# Active profile discovery
# ---------------------------------------------------------------------------
def get_active_profile() -> Dict[str, Any]:
    """Find the first running minikube profile."""
    try:
        profile_result = subprocess.run(
            ["minikube", "profile", "list", "-o", "json"],
            capture_output=True, text=True, timeout=10,
        )

        if profile_result.returncode != 0:
            return {"success": False, "profile": None, "message": "No minikube profiles found"}

        profiles_data = json.loads(profile_result.stdout)

        for profile_info in profiles_data.get("valid", []):
            name = profile_info.get("Name", "")
            status_result = subprocess.run(
                ["minikube", "status", "-p", name, "-o", "json"],
                capture_output=True, text=True, timeout=10,
            )

            if status_result.returncode == 0:
                status_data = json.loads(status_result.stdout)
                if status_data.get("Host") == "Running":
                    api_url = _get_api_url(name)
                    return {
                        "success": True,
                        "profile": {"name": name, "status": "Running", "api_url": api_url},
                        "message": f"Active minikube profile: {name}",
                    }

        return {"success": False, "profile": None, "message": "No running minikube cluster found"}

    except Exception as e:
        return {"success": False, "profile": None, "message": f"Error: {str(e)}"}


def _get_api_url(profile_name: str) -> str:
    """Extract the K8s API URL from kubectl cluster-info."""
    try:
        result = subprocess.run(
            ["kubectl", "cluster-info", "--context", profile_name],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'Kubernetes control plane' in line or 'Kubernetes master' in line:
                    parts = line.split('at')
                    if len(parts) > 1:
                        # Strip ANSI escape codes
                        url = re.sub(r'\x1b\[[0-9;]*m', '', parts[1].strip())
                        return url
    except Exception:
        logger.debug("Failed to get API URL for %s", profile_name, exc_info=True)
    return ""


# ---------------------------------------------------------------------------
# Cluster verification
# ---------------------------------------------------------------------------
def verify_cluster(cluster_name: str) -> Dict[str, Any]:
    """Verify a minikube cluster exists, is running, and kubectl can reach it.

    Returns a detailed dict with exists, accessible, cluster_info, and components.
    """
    if not cluster_name:
        return {
            "exists": False, "accessible": False,
            "message": "Cluster name is required",
            "suggestion": "Please provide a valid Minikube profile name",
        }

    if not is_minikube_installed():
        return {
            "exists": False, "accessible": False,
            "message": "Minikube is not installed",
            "suggestion": "Install Minikube first: brew install minikube",
            "cluster_name": cluster_name,
        }

    status = get_profile_status(cluster_name)
    if not status["exists"]:
        return {
            "exists": False, "accessible": False,
            "message": f"Minikube cluster '{cluster_name}' does not exist",
            "suggestion": f"Create the cluster with: minikube start --profile {cluster_name}",
            "cluster_name": cluster_name,
        }

    if not status.get("is_running", False):
        return {
            "exists": True, "accessible": False,
            "message": f"Minikube cluster '{cluster_name}' exists but is not running",
            "suggestion": f"Start the cluster with: minikube start --profile {cluster_name}",
            "cluster_name": cluster_name,
        }

    # Test kubectl access
    kubectl_test = subprocess.run(
        ["kubectl", "cluster-info", "--context", cluster_name],
        capture_output=True, text=True, timeout=30,
    )

    if kubectl_test.returncode != 0:
        return {
            "exists": True, "accessible": False,
            "message": f"Minikube cluster '{cluster_name}' is running but kubectl access failed",
            "suggestion": f"Try: minikube delete --profile {cluster_name} && minikube start --profile {cluster_name}",
            "cluster_name": cluster_name,
            "error_details": kubectl_test.stderr,
        }

    # Gather cluster info
    cluster_info = _build_cluster_info(cluster_name, status)
    components = _check_components(cluster_name)
    cluster_info["components"] = components

    return {
        "exists": True,
        "accessible": True,
        "message": f"Minikube cluster '{cluster_name}' is running and accessible",
        "cluster_name": cluster_name,
        "context_name": cluster_name,
        "cluster_info": cluster_info,
        "install_method": "clusterctl",
        "suggestion": "You can use this cluster for testing. Update your vars/user_vars.yml with the cluster details.",
    }


def _build_cluster_info(cluster_name: str, status: Dict) -> Dict[str, Any]:
    """Build the cluster_info dict with version, driver, timestamps."""
    version = _get_k8s_version(cluster_name)
    driver = status.get("driver", "N/A")

    info = {
        "name": cluster_name,
        "namespace": "ns-rosa-hcp",
        "status": "Running",
        "driver": driver,
        "kubernetesVersion": version,
        "version": version,
    }

    timestamps = _get_component_timestamps(cluster_name)
    if timestamps:
        info["component_timestamps"] = timestamps

    return info


def _get_k8s_version(context: str) -> str:
    """Get the K8s server version from kubectl."""
    try:
        result = subprocess.run(
            ["kubectl", "version", "-o", "json", "--context", context],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data.get("serverVersion", {}).get("gitVersion", "v1.32.0")
    except Exception:
        logger.debug("Failed to get K8s version for %s", context, exc_info=True)
    return "v1.32.0"


def _get_component_timestamps(context: str) -> Dict[str, str]:
    """Fetch creation timestamps for key CAPI/CAPA components."""
    timestamps = {}
    checks = [
        ("namespace", ["kubectl", "get", "namespace", "ns-rosa-hcp", "-ojson", "--context", context]),
        ("cert-manager", ["kubectl", "get", "deployment", "cert-manager", "-n", "cert-manager", "-ojson", "--context", context]),
        ("capi-controller", ["kubectl", "get", "deployment", "capi-controller-manager", "-n", "capi-system", "-ojson", "--context", context]),
        ("capa-controller", ["kubectl", "get", "deployment", "capa-controller-manager", "-n", "capa-system", "-ojson", "--context", context]),
        ("rosa-crd", ["kubectl", "get", "crd", "rosacontrolplanes.controlplane.cluster.x-k8s.io", "-ojson", "--context", context]),
    ]

    for label, cmd in checks:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                ts = data.get("metadata", {}).get("creationTimestamp", "")
                if ts:
                    timestamps[label] = ts
        except Exception:
            logger.debug("Failed to get timestamp for %s", label, exc_info=True)

    return timestamps


def _check_components(context: str) -> Dict[str, Any]:
    """Check CAPI/CAPA component readiness (AWS creds, OCM secret)."""
    components = {"checks_passed": 0, "warnings": 0, "failed": 0, "details": []}

    secret_checks = [
        {
            "name": "AWS Credentials",
            "cmd": ["kubectl", "get", "secret", "capa-manager-bootstrap-credentials",
                    "-n", "capa-system", "--context", context],
            "ok_msg": "AWS credentials secret found",
            "fail_msg": "AWS credentials secret not found in capa-system namespace",
            "fail_level": "warning",
        },
        {
            "name": "OCM Client Secret",
            "cmd": ["kubectl", "get", "secret", "rosa-creds-secret",
                    "-n", "ns-rosa-hcp", "--context", context],
            "ok_msg": "ROSA credentials secret found",
            "fail_msg": "ROSA credentials secret not found in ns-rosa-hcp namespace",
            "fail_level": "failed",
        },
    ]

    for check in secret_checks:
        try:
            result = subprocess.run(check["cmd"], capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                components["checks_passed"] += 1
                components["details"].append(
                    {"name": check["name"], "status": "configured", "message": check["ok_msg"]}
                )
            else:
                if check["fail_level"] == "warning":
                    components["warnings"] += 1
                    status = "not_configured"
                else:
                    components["failed"] += 1
                    status = "missing"
                components["details"].append(
                    {"name": check["name"], "status": status, "message": check["fail_msg"]}
                )
        except Exception:
            logger.debug("Error checking %s", check["name"], exc_info=True)
            components["failed"] += 1
            components["details"].append(
                {"name": check["name"], "status": "error", "message": f"Error checking {check['name']}"}
            )

    return components


# ---------------------------------------------------------------------------
# Tool versions
# ---------------------------------------------------------------------------
def _get_tool_version(cmd: List[str], parse_json: Optional[str] = None,
                      regex: Optional[str] = None,
                      fallback_cmd: Optional[List[str]] = None) -> Dict[str, Any]:
    """Probe a CLI tool for its version. Returns {"installed": bool, "version": str|None}."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            if parse_json:
                data = json.loads(result.stdout)
                for key in parse_json.split("."):
                    data = data.get(key, {})
                return {"installed": True, "version": data or result.stdout.strip()}
            return {"installed": True, "version": result.stdout.strip()}
        if fallback_cmd:
            result2 = subprocess.run(fallback_cmd, capture_output=True, text=True, timeout=10)
            if result2.returncode == 0:
                if regex:
                    match = re.search(regex, result2.stdout)
                    version = match.group(1) if match else result2.stdout.strip()
                else:
                    version = result2.stdout.strip()
                return {"installed": True, "version": version}
        return {"installed": False, "version": None}
    except (FileNotFoundError, Exception):
        return {"installed": False, "version": None}


def get_tool_versions() -> Dict[str, Any]:
    """Get versions of CAPI-related CLI tools (clusterctl, minikube, kubectl, podman)."""
    tools = {
        "clusterctl": _get_tool_version(
            ["clusterctl", "version", "-o", "short"],
            fallback_cmd=["clusterctl", "version"],
            regex=r'GitVersion:"([^"]+)"',
        ),
        "minikube": _get_tool_version(["minikube", "version", "--short"]),
        "kubectl": _get_tool_version(
            ["kubectl", "version", "--client", "-o", "json"],
            parse_json="clientVersion.gitVersion",
        ),
        "podman": _get_tool_version(
            ["podman", "version", "--format", "{{.Client.Version}}"],
        ),
    }
    return {"tools": tools, "timestamp": datetime.now().isoformat()}


# ---------------------------------------------------------------------------
# CAPI resources
# ---------------------------------------------------------------------------
def _calculate_age(creation_timestamp: str) -> str:
    """Convert a K8s creationTimestamp to a human-readable age string."""
    try:
        created = datetime.fromisoformat(creation_timestamp.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - created
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
        logger.debug("Failed to calculate age from timestamp", exc_info=True)
        return "unknown"


def _determine_resource_status(kind: str, status: Dict) -> str:
    """Determine the status string for a K8s resource based on its kind."""
    if kind == "ROSAControlPlane":
        if status.get("ready") is True or status.get("ready") == "true":
            return "Ready"
        conditions = status.get("conditions", [])
        for condition in conditions:
            if condition.get("status") == "True" and condition.get("type") in ["Ready", "ROSAControlPlaneReady"]:
                return "Ready"
        return "Provisioning"
    elif kind in ("ROSANetwork", "RosaRoleConfig"):
        if status.get("ready") is True or status.get("ready") == "true":
            return "Ready"
        return "Provisioning"
    elif kind == "Cluster":
        return "Ready" if status.get("phase") == "Provisioned" else status.get("phase", "Active")
    elif kind in ("MachinePool", "RosaMachinePool", "MachineDeployment", "Machine"):
        return status.get("phase", "Active")
    else:
        return "Active"


def get_capi_resources(context: str, namespace: str = "ns-rosa-hcp") -> Dict[str, Any]:
    """Fetch all CAPI/ROSA resources from a cluster in one bulk kubectl call."""
    if not context:
        return {"success": False, "message": "Cluster context is required", "resources": []}

    resources = []

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
            ["kubectl", "get", ",".join(resource_types), "-n", namespace,
             "--context", context, "-o", "json"],
            capture_output=True, text=True, timeout=30,
        )

        if result.returncode == 0:
            data = json.loads(result.stdout)
            for item in data.get("items", []):
                metadata = item.get("metadata", {})
                spec = item.get("spec", {})
                status = item.get("status", {})
                kind = item.get("kind", "unknown")

                resources.append({
                    "type": kind,
                    "name": metadata.get("name", "unknown"),
                    "namespace": namespace,
                    "version": spec.get("version", ""),
                    "status": _determine_resource_status(kind, status),
                    "age": _calculate_age(metadata.get("creationTimestamp", "")),
                })
    except subprocess.TimeoutExpired:
        logger.debug("Timed out fetching CAPI resources from %s", context)
    except Exception:
        logger.debug("Failed to fetch CAPI resources from %s", context, exc_info=True)

    # Namespace resource
    try:
        result = subprocess.run(
            ["kubectl", "get", "namespace", namespace, "--context", context, "-o", "json"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            metadata = data.get("metadata", {})
            phase = data.get("status", {}).get("phase", "Active")
            resources.append({
                "type": "Namespace",
                "name": metadata.get("name", "unknown"),
                "namespace": metadata.get("name", "unknown"),
                "version": "",
                "status": phase,
                "age": _calculate_age(metadata.get("creationTimestamp", "")),
            })
    except Exception:
        logger.debug("Failed to fetch namespace %s from %s", namespace, context, exc_info=True)

    # AWSClusterControllerIdentity (cluster-scoped)
    try:
        result = subprocess.run(
            ["kubectl", "get", "awsclustercontrolleridentity",
             "--context", context, "-o", "json"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            for item in data.get("items", []):
                metadata = item.get("metadata", {})
                resources.append({
                    "type": "AWSClusterControllerIdentity",
                    "name": metadata.get("name", "unknown"),
                    "namespace": "(cluster-scoped)",
                    "version": "",
                    "status": "Active",
                    "age": _calculate_age(metadata.get("creationTimestamp", "")),
                })
    except Exception:
        logger.debug("Failed to fetch AWSClusterControllerIdentity from %s", context, exc_info=True)

    return {"success": True, "resources": resources, "count": len(resources)}


# ---------------------------------------------------------------------------
# CAPI configuration (clusterctl install)
# ---------------------------------------------------------------------------

# GitHub "tree" URL: https://github.com/<owner>/<repo>/tree/<branch>/<subpath>
# NOTE: <branch> may itself contain slashes (e.g. feat/rosaeng-8275-...), so we
# capture everything after /tree/ and strip the known CRD subpath to recover it.
_GITHUB_TREE_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/tree/(?P<rest>.+)$"
)

# The playbook globs {SOURCE_PATH}/config/crd/bases/*.yaml, so the URL's CRD
# subpath is always this. Stripping it from <rest> yields the full branch name.
_CRD_SUBPATH = "config/crd/bases"


def _resolve_crd_source_path(crd_location: str, on_output=None) -> Optional[str]:
    """Resolve a CRD location to a local filesystem path.

    If crd_location is a GitHub /tree/<branch>/config/crd/bases URL, shallow-clone
    the repo at that branch into a temp dir and return the repo root (the playbook
    globs ``{path}/config/crd/bases/*.yaml``). If it is already a local path,
    return it as-is. Returns None if it cannot be resolved.

    Branch names may contain slashes, so we strip the known CRD subpath rather
    than assume the branch is a single path segment.

    The caller is responsible for cleaning up the returned temp clone.
    """
    if not crd_location:
        return None

    crd_location = crd_location.strip()

    # Already a local path.
    if not crd_location.startswith(("http://", "https://")):
        return crd_location if os.path.exists(crd_location) else None

    m = _GITHUB_TREE_RE.match(crd_location.rstrip("/"))
    if not m:
        if on_output:
            on_output(f"Warning: unsupported CRD URL (expected a GitHub /tree/ URL): {crd_location}")
        return None

    owner, repo, rest = m.group("owner"), m.group("repo"), m.group("rest")
    # rest = "<branch>/config/crd/bases" (or just "<branch>"); strip the subpath.
    branch = rest
    if branch.endswith("/" + _CRD_SUBPATH):
        branch = branch[: -(len(_CRD_SUBPATH) + 1)]
    elif "/" + _CRD_SUBPATH + "/" in branch:
        branch = branch.split("/" + _CRD_SUBPATH + "/", 1)[0]
    if not branch:
        if on_output:
            on_output(f"Warning: could not parse branch from CRD URL: {crd_location}")
        return None

    clone_url = f"https://github.com/{owner}/{repo}.git"
    tmp_dir = tempfile.mkdtemp(prefix="capa-crd-")
    if on_output:
        on_output(f"Cloning CRDs from {owner}/{repo}@{branch} ...")
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", branch, clone_url, tmp_dir],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            if on_output:
                on_output(f"Warning: CRD clone failed: {result.stderr.strip()}")
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return None
        if on_output:
            on_output(f"✓ CRDs cloned to {tmp_dir}")
        return tmp_dir
    except Exception as e:
        if on_output:
            on_output(f"Warning: could not clone CRDs: {e}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None


def configure_capi(profile_name: str, project_root: str,
                   custom_capa_image: Optional[Dict] = None,
                   on_output=None) -> Dict[str, Any]:
    """Install CAPI/CAPA on a minikube profile via ansible-playbook.

    Args:
        profile_name: Minikube profile name
        project_root: Path to the project root (for finding playbook + credentials)
        custom_capa_image: Optional dict with repository, tag, sourcePath
        on_output: Optional callback for streaming output lines
    """
    # Run the top-level playbook, NOT tasks/clusterctl_install_capi.yml directly:
    # the latter is a task file (no play header) and `ansible-playbook` rejects it
    # with "'shell' is not a valid attribute for a Play". The root playbook
    # include_tasks it with a proper play (hosts, vars_files).
    playbook_path = os.path.join(project_root, "initialize-minikube-capi.yml")
    if not os.path.exists(playbook_path):
        return {
            "success": False,
            "message": f"Initialization playbook not found at: {playbook_path}",
            "suggestion": "Ensure initialize-minikube-capi.yml exists at the project root",
        }

    # Switch context first
    ctx = switch_context(profile_name)
    if not ctx["success"]:
        return ctx

    # Load credentials
    credentials = _load_credentials(project_root)

    # Build environment
    env = os.environ.copy()
    env["MINIKUBE_PROFILE"] = profile_name
    env["KUBECONFIG"] = os.path.expanduser("~/.kube/config")
    env["CAPI_INSTALL_METHOD"] = "clusterctl"
    if credentials:
        env.update(credentials)

    # Track a temp CRD clone so we can clean it up after the run.
    crd_clone_dir = None

    if custom_capa_image:
        repository = (custom_capa_image.get("repository") or "").strip()
        tag = (custom_capa_image.get("tag") or "").strip()
        env["CUSTOM_CAPA_IMAGE"] = "true"
        env["CUSTOM_CAPA_IMAGE_REPO"] = repository
        env["CUSTOM_CAPA_IMAGE_TAG"] = tag

        # Resolve the CRD location. The UI sends `crdLocation` (a GitHub /tree/
        # URL); older callers may pass a local `sourcePath`. Either resolves to a
        # local dir the playbook globs as {path}/config/crd/bases/*.yaml.
        crd_location = custom_capa_image.get("crdLocation") or custom_capa_image.get("sourcePath") or ""
        source_path = _resolve_crd_source_path(crd_location, on_output=on_output) or ""
        env["CUSTOM_CAPA_SOURCE_PATH"] = source_path
        # If we cloned it (URL case), remember it for cleanup.
        if source_path and source_path != crd_location.strip():
            crd_clone_dir = source_path

        # Pre-load the custom image into Minikube so the controller pod doesn't
        # hit ImagePullBackOff when the registry is unreachable from inside the VM.
        full_image = f"{repository}:{tag}"
        if on_output:
            on_output(f"Loading custom image into Minikube (this may take a minute): {full_image}")
        try:
            load_result = subprocess.run(
                ["minikube", "image", "load", full_image, "-p", profile_name],
                capture_output=True, text=True, timeout=300,
            )
            if on_output:
                if load_result.returncode == 0:
                    on_output(f"✓ Image loaded into Minikube: {full_image}")
                else:
                    on_output(f"Warning: image load failed (will try pull from registry): {load_result.stderr.strip()}")
        except Exception as e:
            if on_output:
                on_output(f"Warning: could not pre-load image: {e}")

    # Build command — credentials are already in env, no need to expose on CLI.
    # The root playbook reads cluster_name/install_method as extra-vars.
    cmd = [
        "ansible-playbook", playbook_path, "-vv",
        "-e", f"cluster_name={profile_name}",
        "-e", "install_method=clusterctl",
    ]

    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, env=env,
        )

        for line in iter(process.stdout.readline, ''):
            line_text = line.rstrip()
            if line_text and on_output:
                on_output(line_text)

        process.wait(timeout=600)

        if process.returncode == 0:
            return {"success": True, "message": f"CAPI/CAPA configured on '{profile_name}'"}
        else:
            return {"success": False, "message": f"Playbook failed with exit code {process.returncode}"}

    except subprocess.TimeoutExpired:
        return {"success": False, "message": "CAPI configuration timed out after 10 minutes"}
    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)}"}
    finally:
        if crd_clone_dir:
            shutil.rmtree(crd_clone_dir, ignore_errors=True)


def _load_credentials(project_root: str) -> Dict[str, str]:
    """Load AWS/OCM credentials from vars/user_vars.yml."""
    config_path = os.path.join(project_root, "vars", "user_vars.yml")
    if not os.path.exists(config_path):
        return {}
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f) or {}
        return {
            "AWS_ACCESS_KEY_ID": config.get("AWS_ACCESS_KEY_ID", ""),
            "AWS_SECRET_ACCESS_KEY": config.get("AWS_SECRET_ACCESS_KEY", ""),
            "AWS_REGION": config.get("AWS_REGION", "us-west-2"),
            "OCM_CLIENT_ID": config.get("OCM_CLIENT_ID", ""),
            "OCM_CLIENT_SECRET": config.get("OCM_CLIENT_SECRET", ""),
        }
    except Exception:
        logger.debug("Failed to load credentials from %s", config_path, exc_info=True)
        return {}
