"""Kubernetes / OpenShift resource query tools."""

import json
import subprocess

ALLOWED_RESOURCE_TYPES = [
    "rosacontrolplane", "rosanetwork", "rosaroleconfig",
    "rosamachinepool", "machinepool", "cluster",
    "namespace", "pods", "events", "secrets",
]


def register_tools(mcp):

    @mcp.tool()
    def capa_k8s_get_resource(
        resource_type: str,
        name: str = "",
        namespace: str = "",
    ) -> str:
        """Query Kubernetes/OpenShift resources. Restricted to CAPI-related resource types.

        Args:
            resource_type: Resource type (rosacontrolplane, rosanetwork, rosaroleconfig,
                rosamachinepool, machinepool, cluster, namespace, pods, events)
            name: Specific resource name (optional — omit to list all)
            namespace: K8s namespace (optional — omit for all namespaces)
        """
        if resource_type not in ALLOWED_RESOURCE_TYPES:
            return json.dumps({
                "error": f"Resource type '{resource_type}' not allowed. Allowed: {', '.join(ALLOWED_RESOURCE_TYPES)}"
            })

        cmd = ["oc", "get", resource_type]
        if name:
            cmd.append(name)
        if namespace:
            cmd.extend(["-n", namespace])
        else:
            cmd.append("--all-namespaces")
        cmd.extend(["-o", "json"])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                return json.dumps({"error": result.stderr.strip()})

            data = json.loads(result.stdout)

            # Summarize items for readability
            if "items" in data:
                items = []
                for item in data["items"]:
                    meta = item.get("metadata", {})
                    status = item.get("status", {})
                    summary = {
                        "name": meta.get("name"),
                        "namespace": meta.get("namespace"),
                        "created": meta.get("creationTimestamp"),
                    }
                    if meta.get("deletionTimestamp"):
                        summary["deleting_since"] = meta["deletionTimestamp"]
                    if "ready" in status:
                        summary["ready"] = status["ready"]
                    if "conditions" in status:
                        summary["conditions"] = [
                            {"type": c["type"], "status": c["status"],
                             "reason": c.get("reason", ""), "message": c.get("message", "")[:200]}
                            for c in status["conditions"]
                        ]
                    if "replicas" in status:
                        summary["replicas"] = status.get("replicas")
                        summary["ready_replicas"] = status.get("readyReplicas")
                    items.append(summary)
                return json.dumps({"count": len(items), "items": items}, indent=2)
            else:
                meta = data.get("metadata", {})
                status = data.get("status", {})
                spec = data.get("spec", {})
                return json.dumps({
                    "name": meta.get("name"),
                    "namespace": meta.get("namespace"),
                    "created": meta.get("creationTimestamp"),
                    "deleting_since": meta.get("deletionTimestamp"),
                    "spec": spec,
                    "status": status,
                }, indent=2, default=str)
        except subprocess.TimeoutExpired:
            return json.dumps({"error": "Timeout querying K8s"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def capa_k8s_events(namespace: str = "ns-rosa-hcp", limit: int = 20) -> str:
        """Get recent Kubernetes events for a namespace, sorted by time.

        Args:
            namespace: K8s namespace (default: ns-rosa-hcp)
            limit: Max events to return (default: 20)
        """
        try:
            result = subprocess.run(
                ["oc", "get", "events", "-n", namespace,
                 "--sort-by=.lastTimestamp", "-o", "json"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                return json.dumps({"error": result.stderr.strip()})

            data = json.loads(result.stdout)
            events = []
            for e in data.get("items", [])[-limit:]:
                events.append({
                    "type": e.get("type"),
                    "reason": e.get("reason"),
                    "message": e.get("message", "")[:300],
                    "object": f"{e.get('involvedObject', {}).get('kind', '')}/{e.get('involvedObject', {}).get('name', '')}",
                    "count": e.get("count"),
                    "last_seen": e.get("lastTimestamp"),
                })
            events.reverse()
            return json.dumps({"namespace": namespace, "count": len(events), "events": events}, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})
