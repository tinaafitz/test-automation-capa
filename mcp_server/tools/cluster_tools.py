"""ROSA HCP cluster listing and status tools."""

import json
import subprocess


def register_tools(mcp):

    @mcp.tool()
    def capa_list_clusters() -> str:
        """List all ROSA HCP clusters with status, region, version, and namespace."""
        try:
            result = subprocess.run(
                ["rosa", "list", "clusters", "-o", "json"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                # Fallback to K8s ROSAControlPlane resources
                return _list_from_k8s()

            clusters = json.loads(result.stdout)
            cluster_list = []
            for c in clusters:
                cluster_list.append({
                    "name": c.get("name", "unknown"),
                    "status": c.get("state", "unknown"),
                    "region": (c.get("region", {}).get("id", "N/A")
                               if isinstance(c.get("region"), dict)
                               else c.get("region", "N/A")),
                    "version": c.get("openshift_version", "N/A"),
                    "created": c.get("creation_timestamp"),
                })
            return json.dumps({"clusters": cluster_list, "count": len(cluster_list)}, indent=2)
        except subprocess.TimeoutExpired:
            return _list_from_k8s()
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def capa_cluster_status(cluster_name: str) -> str:
        """Get detailed status of a specific ROSA HCP cluster including K8s resource conditions.

        Args:
            cluster_name: Name of the ROSA cluster
        """
        result = {}

        # ROSA CLI status
        try:
            proc = subprocess.run(
                ["rosa", "describe", "cluster", "--cluster", cluster_name, "-o", "json"],
                capture_output=True, text=True, timeout=10,
            )
            if proc.returncode == 0:
                rosa_data = json.loads(proc.stdout)
                result["rosa"] = {
                    "name": rosa_data.get("name"),
                    "state": rosa_data.get("state"),
                    "version": rosa_data.get("openshift_version"),
                    "region": (rosa_data.get("region", {}).get("id")
                               if isinstance(rosa_data.get("region"), dict)
                               else rosa_data.get("region")),
                    "api_url": rosa_data.get("api", {}).get("url") if isinstance(rosa_data.get("api"), dict) else None,
                    "console_url": rosa_data.get("console", {}).get("url") if isinstance(rosa_data.get("console"), dict) else None,
                    "created": rosa_data.get("creation_timestamp"),
                }
        except Exception as e:
            result["rosa"] = {"error": str(e)}

        # K8s ROSAControlPlane status
        try:
            proc = subprocess.run(
                ["oc", "get", "rosacontrolplane", cluster_name, "-n", "ns-rosa-hcp", "-o", "json"],
                capture_output=True, text=True, timeout=10,
            )
            if proc.returncode == 0:
                cp = json.loads(proc.stdout)
                conditions = cp.get("status", {}).get("conditions", [])
                result["control_plane"] = {
                    "ready": cp.get("status", {}).get("ready", False),
                    "conditions": [
                        {"type": c["type"], "status": c["status"],
                         "reason": c.get("reason", ""), "message": c.get("message", "")}
                        for c in conditions
                    ],
                }
            else:
                result["control_plane"] = {"error": proc.stderr.strip()}
        except Exception as e:
            result["control_plane"] = {"error": str(e)}

        # K8s ROSANetwork status
        try:
            proc = subprocess.run(
                ["oc", "get", "rosanetwork", f"{cluster_name}-network", "-n", "ns-rosa-hcp", "-o", "json"],
                capture_output=True, text=True, timeout=10,
            )
            if proc.returncode == 0:
                net = json.loads(proc.stdout)
                result["network"] = {
                    "ready": net.get("status", {}).get("ready", False),
                    "stack_status": net.get("status", {}).get("stackStatus", "unknown"),
                    "vpc_id": net.get("status", {}).get("vpcID"),
                }
        except Exception:
            pass

        # MachinePool status
        try:
            proc = subprocess.run(
                ["oc", "get", "machinepool", cluster_name, "-n", "ns-rosa-hcp", "-o", "json"],
                capture_output=True, text=True, timeout=10,
            )
            if proc.returncode == 0:
                mp = json.loads(proc.stdout)
                result["machine_pool"] = {
                    "replicas": mp.get("spec", {}).get("replicas"),
                    "ready_replicas": mp.get("status", {}).get("readyReplicas", 0),
                    "available_replicas": mp.get("status", {}).get("availableReplicas", 0),
                }
        except Exception:
            pass

        return json.dumps(result, indent=2, default=str)


def _list_from_k8s() -> str:
    """Fallback: list clusters from ROSAControlPlane K8s resources."""
    try:
        proc = subprocess.run(
            ["oc", "get", "rosacontrolplane", "--all-namespaces", "-o", "json"],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            return json.dumps({"error": proc.stderr.strip(), "clusters": []})

        data = json.loads(proc.stdout)
        cluster_list = []
        for item in data.get("items", []):
            meta = item.get("metadata", {})
            status = item.get("status", {})
            spec = item.get("spec", {})
            ready = status.get("ready", False)
            deleting = meta.get("deletionTimestamp") is not None

            state = "ready" if ready else "deleting" if deleting else "provisioning"
            cluster_list.append({
                "name": meta.get("name", "unknown"),
                "namespace": meta.get("namespace"),
                "status": state,
                "region": spec.get("region", "N/A"),
                "version": spec.get("version", "N/A"),
            })
        return json.dumps({"clusters": cluster_list, "count": len(cluster_list), "source": "kubernetes"}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e), "clusters": []})
