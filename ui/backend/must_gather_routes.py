"""
Must-Gather diagnostics route -- FastAPI router that collects a comprehensive
cluster diagnostic bundle across ROSA/OCM, CAPI resources, controllers,
K8s events, AWS state, and agent history.

Endpoints:
  GET /api/clusters/{cluster_name}/must-gather[?download=true]
"""

import asyncio
import json
import logging
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, Response

router = APIRouter()
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_cmd(args: List[str], timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, capture_output=True, text=True, timeout=timeout
    )


def _safe_json(stdout: str) -> Optional[dict]:
    try:
        return json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Section collectors (all synchronous)
# ---------------------------------------------------------------------------

def _collect_rosa_ocm_state(cluster_name: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "state": None, "version": None, "region": None,
        "error_code": None, "error_message": None, "created": None,
        "install_logs": None, "uninstall_logs": None,
    }
    try:
        proc = _run_cmd(["rosa", "describe", "cluster", "--cluster", cluster_name, "-o", "json"], timeout=30)
        if proc.returncode == 0:
            data = _safe_json(proc.stdout) or {}
            status = data.get("status", {})
            result["state"] = status.get("state")
            result["version"] = (data.get("version", {}) or {}).get("id")
            result["region"] = (data.get("region", {}) or {}).get("id")
            result["error_code"] = status.get("provision_error_code")
            result["error_message"] = status.get("provision_error_message")
            result["created"] = data.get("creation_timestamp")
        else:
            result["error_message"] = proc.stderr.strip()
    except Exception as exc:
        result["error_message"] = str(exc)

    try:
        proc = _run_cmd(["rosa", "logs", "install", "-c", cluster_name, "--tail", "50"], timeout=30)
        result["install_logs"] = proc.stdout.strip() if proc.returncode == 0 else None
    except Exception:
        pass

    try:
        proc = _run_cmd(["rosa", "logs", "uninstall", "-c", cluster_name, "--tail", "50"], timeout=30)
        result["uninstall_logs"] = proc.stdout.strip() if proc.returncode == 0 else None
    except Exception:
        pass

    return result


_CAPI_RESOURCE_TYPES = [
    ("rosacontrolplane", "{cluster}"),
    ("rosanetwork", "{cluster}-network"),
    ("rosaroleconfig", "{cluster}-roles"),
    ("rosamachinepool", "{cluster}"),
    ("machinepool", "{cluster}"),
    ("cluster.cluster.x-k8s.io", "{cluster}"),
]


def _collect_capi_resources(cluster_name: str, namespace: str) -> Dict[str, Any]:
    resources = []
    is_deleting = False

    for res_type, name_tpl in _CAPI_RESOURCE_TYPES:
        name = name_tpl.format(cluster=cluster_name)
        entry: Dict[str, Any] = {
            "type": res_type, "name": name, "exists": False,
            "ready": None, "conditions": [], "deletionTimestamp": None,
            "finalizers": [], "creationTimestamp": None,
        }
        try:
            proc = _run_cmd(["oc", "get", res_type, name, "-n", namespace, "-o", "json"])
            if proc.returncode == 0:
                data = _safe_json(proc.stdout) or {}
                meta = data.get("metadata", {})
                status = data.get("status", {})
                entry["exists"] = True
                entry["creationTimestamp"] = meta.get("creationTimestamp")
                entry["deletionTimestamp"] = meta.get("deletionTimestamp")
                entry["finalizers"] = meta.get("finalizers", [])

                # Ready from status.ready or conditions
                if "ready" in status:
                    entry["ready"] = status["ready"]
                else:
                    conditions = status.get("conditions", [])
                    for c in conditions:
                        if c.get("type") == "Ready":
                            entry["ready"] = c.get("status") == "True"
                            break

                entry["conditions"] = [
                    {"type": c.get("type"), "status": c.get("status"),
                     "reason": c.get("reason"), "message": c.get("message")}
                    for c in status.get("conditions", [])
                ]

                if entry["deletionTimestamp"]:
                    is_deleting = True
        except Exception as exc:
            entry["error"] = str(exc)

        resources.append(entry)

    return {"resources": resources, "is_deleting": is_deleting}


def _collect_controller_health() -> Dict[str, Any]:
    result = {}
    for label, deploy_name in [
        ("capa_controller", "capa-controller-manager"),
        ("capi_controller", "capi-controller-manager"),
    ]:
        info: Dict[str, Any] = {
            "ready_replicas": 0, "desired_replicas": 0, "available": False,
        }
        try:
            proc = _run_cmd([
                "oc", "get", "deployment", deploy_name,
                "-n", "multicluster-engine", "-o", "json",
            ])
            if proc.returncode == 0:
                data = _safe_json(proc.stdout) or {}
                spec = data.get("spec", {})
                status = data.get("status", {})
                info["desired_replicas"] = spec.get("replicas", 0)
                info["ready_replicas"] = status.get("readyReplicas", 0)
                info["available"] = info["ready_replicas"] >= info["desired_replicas"] > 0
        except Exception as exc:
            info["error"] = str(exc)
        result[label] = info

    return result


def _collect_controller_logs(cluster_name: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {"capa_errors": [], "capi_errors": []}
    pattern = re.compile(r"error|fail|warn", re.IGNORECASE)

    for key, deploy in [
        ("capa_errors", "capa-controller-manager"),
        ("capi_errors", "capi-controller-manager"),
    ]:
        try:
            proc = _run_cmd([
                "oc", "logs", f"deployment/{deploy}",
                "-n", "multicluster-engine", "--tail=200",
            ], timeout=30)
            if proc.returncode == 0:
                matching = [
                    line for line in proc.stdout.splitlines()
                    if pattern.search(line) and cluster_name in line
                ]
                result[key] = matching[-50:]
        except Exception:
            pass

    return result


def _collect_k8s_events(namespace: str) -> Dict[str, Any]:
    events: List[Dict[str, Any]] = []
    try:
        proc = _run_cmd([
            "oc", "get", "events", "-n", namespace,
            "--sort-by=.lastTimestamp", "-o", "json",
        ], timeout=30)
        if proc.returncode == 0:
            data = _safe_json(proc.stdout) or {}
            for ev in (data.get("items") or [])[-30:]:
                msg = (ev.get("message") or "")[:300]
                obj = ev.get("involvedObject", {})
                events.append({
                    "type": ev.get("type"),
                    "reason": ev.get("reason"),
                    "message": msg,
                    "object": f"{obj.get('kind', '')}/{obj.get('name', '')}",
                    "count": ev.get("count"),
                    "lastTimestamp": ev.get("lastTimestamp"),
                })
    except Exception:
        pass

    return {"events": events, "count": len(events)}


def _collect_aws_resources(cluster_name: str) -> Dict[str, Any]:
    stack_name = f"{cluster_name}-rosa-network-stack"
    region = "us-west-2"
    cf: Dict[str, Any] = {
        "stack_name": stack_name, "status": None,
        "status_reason": None, "failed_resources": [],
    }
    vpc: Dict[str, Any] = {"vpc_id": None, "cidr": None}

    try:
        proc = _run_cmd([
            "aws", "cloudformation", "describe-stacks",
            "--stack-name", stack_name, "--region", region, "--output", "json",
        ], timeout=30)
        if proc.returncode == 0:
            data = _safe_json(proc.stdout) or {}
            stacks = data.get("Stacks", [])
            if stacks:
                stack = stacks[0]
                cf["status"] = stack.get("StackStatus")
                cf["status_reason"] = stack.get("StackStatusReason")

                if cf["status"] == "DELETE_FAILED":
                    try:
                        ev_proc = _run_cmd([
                            "aws", "cloudformation", "describe-stack-events",
                            "--stack-name", stack_name, "--region", region,
                            "--output", "json",
                        ], timeout=30)
                        if ev_proc.returncode == 0:
                            ev_data = _safe_json(ev_proc.stdout) or {}
                            cf["failed_resources"] = [
                                {
                                    "logical_id": e.get("LogicalResourceId"),
                                    "status": e.get("ResourceStatus"),
                                    "reason": e.get("ResourceStatusReason"),
                                }
                                for e in ev_data.get("StackEvents", [])
                                if "FAILED" in (e.get("ResourceStatus") or "")
                            ]
                    except Exception:
                        pass

                # Extract VPC from stack outputs or resources
                for output in stack.get("Outputs", []):
                    if "VPC" in (output.get("OutputKey") or "").upper():
                        vpc["vpc_id"] = output.get("OutputValue")
                        break
    except Exception:
        pass

    if vpc["vpc_id"]:
        try:
            proc = _run_cmd([
                "aws", "ec2", "describe-vpcs", "--vpc-ids", vpc["vpc_id"],
                "--region", region, "--output", "json",
            ])
            if proc.returncode == 0:
                vpcs = (_safe_json(proc.stdout) or {}).get("Vpcs", [])
                if vpcs:
                    vpc["cidr"] = vpcs[0].get("CidrBlock")
        except Exception:
            pass

    return {"cloudformation": cf, "vpc": vpc}


def _collect_agent_history(cluster_name: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "remediation_outcomes": [],
        "provision_sidecar": None,
        "deletion_sidecar": None,
    }

    outcomes_path = PROJECT_ROOT / "agents" / "knowledge_base" / "remediation_outcomes.json"
    try:
        if outcomes_path.exists():
            data = json.loads(outcomes_path.read_text())
            result["remediation_outcomes"] = [
                o for o in (data if isinstance(data, list) else [])
                if cluster_name in str(o.get("cluster_name", ""))
            ]
    except Exception:
        pass

    for label, prefix in [
        ("provision_sidecar", "provision-agent"),
        ("deletion_sidecar", "deletion-agent"),
    ]:
        log_path = Path(f"/tmp/{prefix}-{cluster_name}.log")
        try:
            if log_path.exists():
                lines = log_path.read_text().splitlines()
                result[label] = "\n".join(lines[-50:])
        except Exception:
            pass

    return result


def _collect_deletion_analysis(
    cluster_name: str,
    namespace: str,
    capi_resources: Dict[str, Any],
) -> Dict[str, Any]:
    region = "us-west-2"
    result: Dict[str, Any] = {
        "finalizers": [],
        "ocm_state": None,
        "vpc_dependencies": {},
        "stuck_timeline": [],
    }

    # Finalizer analysis from already-collected CAPI resources
    for res in capi_resources.get("resources", []):
        if res.get("deletionTimestamp") and res.get("finalizers"):
            result["finalizers"].append({
                "type": res["type"],
                "name": res["name"],
                "finalizers": res["finalizers"],
                "deletionTimestamp": res["deletionTimestamp"],
            })

    # OCM state
    try:
        proc = _run_cmd(["rosa", "describe", "cluster", "--cluster", cluster_name, "-o", "json"], timeout=30)
        if proc.returncode == 0:
            data = _safe_json(proc.stdout) or {}
            result["ocm_state"] = (data.get("status", {}) or {}).get("state", "unknown")
        else:
            stderr = proc.stderr.strip().lower()
            if "not found" in stderr or "does not exist" in stderr:
                result["ocm_state"] = "gone"
            else:
                result["ocm_state"] = "unknown"
    except Exception:
        result["ocm_state"] = "unknown"

    # VPC dependencies -- try to get VPC ID from rosanetwork resource
    vpc_id = None
    try:
        proc = _run_cmd([
            "oc", "get", "rosanetwork", f"{cluster_name}-network",
            "-n", namespace, "-o", "json",
        ])
        if proc.returncode == 0:
            data = _safe_json(proc.stdout) or {}
            vpc_id = (data.get("status", {}) or {}).get("vpcID")
    except Exception:
        pass

    if vpc_id:
        deps: Dict[str, Any] = {}
        try:
            proc = _run_cmd([
                "aws", "ec2", "describe-vpc-endpoints",
                "--filters", f"Name=vpc-id,Values={vpc_id}",
                "--region", region,
                "--query", "VpcEndpoints[].{Id:VpcEndpointId,State:State}",
                "--output", "json",
            ])
            if proc.returncode == 0:
                deps["vpc_endpoints"] = _safe_json(proc.stdout) or []
        except Exception:
            pass

        try:
            proc = _run_cmd([
                "aws", "ec2", "describe-network-interfaces",
                "--filters", f"Name=vpc-id,Values={vpc_id}",
                "--region", region,
                "--query", "NetworkInterfaces[].{Id:NetworkInterfaceId,Status:Status,Description:Description}",
                "--output", "json",
            ])
            if proc.returncode == 0:
                deps["network_interfaces"] = _safe_json(proc.stdout) or []
        except Exception:
            pass

        try:
            proc = _run_cmd([
                "aws", "ec2", "describe-security-groups",
                "--filters", f"Name=vpc-id,Values={vpc_id}",
                "--region", region,
                "--query", "SecurityGroups[?GroupName!='default'].{Id:GroupId,Name:GroupName}",
                "--output", "json",
            ])
            if proc.returncode == 0:
                deps["security_groups"] = _safe_json(proc.stdout) or []
        except Exception:
            pass

        result["vpc_dependencies"] = deps

    # Stuck timeline
    thresholds = {
        "rosacontrolplane": 20 * 60,
        "rosanetwork": 30 * 60,
        "rosaroleconfig": 10 * 60,
    }
    now = datetime.now(timezone.utc)
    for res in capi_resources.get("resources", []):
        ts = res.get("deletionTimestamp")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            elapsed = int((now - dt).total_seconds())
            threshold = thresholds.get(res["type"])
            result["stuck_timeline"].append({
                "type": res["type"],
                "name": res["name"],
                "elapsed_seconds": elapsed,
                "threshold_seconds": threshold,
                "stuck": threshold is not None and elapsed > threshold,
            })
        except Exception:
            pass

    return result


def _collect_node_status(cluster_name: str, namespace: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "replicas": 0, "ready_replicas": 0, "available_replicas": 0,
    }
    try:
        proc = _run_cmd([
            "oc", "get", "rosamachinepool", cluster_name,
            "-n", namespace, "-o", "json",
        ])
        if proc.returncode == 0:
            status = (_safe_json(proc.stdout) or {}).get("status", {})
            result["replicas"] = status.get("replicas", 0)
            result["ready_replicas"] = status.get("readyReplicas", 0)
            result["available_replicas"] = status.get("availableReplicas", 0)
    except Exception:
        pass

    return result


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def _collect_must_gather(cluster_name: str, namespace: str = "ns-rosa-hcp") -> Dict[str, Any]:
    sections: Dict[str, Any] = {}

    collectors = [
        ("rosa_ocm_state", lambda: _collect_rosa_ocm_state(cluster_name)),
        ("capi_resources", lambda: _collect_capi_resources(cluster_name, namespace)),
        ("controller_health", lambda: _collect_controller_health()),
        ("controller_logs", lambda: _collect_controller_logs(cluster_name)),
        ("k8s_events", lambda: _collect_k8s_events(namespace)),
        ("aws_resources", lambda: _collect_aws_resources(cluster_name)),
        ("agent_history", lambda: _collect_agent_history(cluster_name)),
        ("node_status", lambda: _collect_node_status(cluster_name, namespace)),
    ]

    for name, fn in collectors:
        try:
            sections[name] = fn()
        except Exception as exc:
            sections[name] = {"error": str(exc)}

    # Determine is_deleting from CAPI resources
    capi = sections.get("capi_resources", {})
    is_deleting = capi.get("is_deleting", False) if isinstance(capi, dict) else False

    # Deletion analysis only when deleting
    if is_deleting:
        try:
            sections["deletion_analysis"] = _collect_deletion_analysis(
                cluster_name, namespace, capi
            )
        except Exception as exc:
            sections["deletion_analysis"] = {"error": str(exc)}
    else:
        sections["deletion_analysis"] = None

    return {
        "cluster_name": cluster_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "namespace": namespace,
        "is_deleting": is_deleting,
        "sections": sections,
    }


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("/api/clusters/{cluster_name}/must-gather")
async def must_gather(
    cluster_name: str,
    download: bool = Query(False),
):
    bundle = await asyncio.to_thread(_collect_must_gather, cluster_name)

    if download:
        payload = json.dumps(bundle, indent=2, default=str)
        filename = f"must-gather-{cluster_name}-{bundle['generated_at'][:19].replace(':', '-')}.json"
        return Response(
            content=payload,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return bundle
