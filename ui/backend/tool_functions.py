"""
Tool functions for the UI chat assistant.
Async wrappers around the same logic used by the MCP server tools.
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict

PROJECT_ROOT = Path(__file__).parent.parent.parent
KB_DIR = PROJECT_ROOT / "agents" / "knowledge_base"

ALLOWED_K8S_RESOURCE_TYPES = [
    "rosacontrolplane", "rosanetwork", "rosaroleconfig",
    "rosamachinepool", "machinepool", "cluster",
    "namespace", "pods", "events", "secrets",
]

VALID_ISSUE_TYPES = [
    "rosanetwork_stuck_deletion",
    "rosacontrolplane_stuck_deletion",
    "rosaroleconfig_stuck_deletion",
    "cloudformation_deletion_failure",
    "ocm_auth_failure",
    "capi_not_installed",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_cmd(cmd, timeout=30):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _aws_cmd(args, timeout=30):
    try:
        result = _run_cmd(["aws"] + args + ["--output", "json"], timeout)
        if result.returncode != 0:
            return None, result.stderr.strip()
        return json.loads(result.stdout), None
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except Exception as e:
        return None, str(e)


# ---------------------------------------------------------------------------
# Sync tool implementations (run via asyncio.to_thread)
# ---------------------------------------------------------------------------

def _list_clusters_sync():
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from agents.ocm_client import get_ocm_client
        ocm = get_ocm_client()
        clusters, err = ocm.list_clusters()
        if err:
            return _list_from_k8s()
        return json.dumps({"clusters": clusters, "count": len(clusters)}, indent=2)
    except Exception as e:
        return _list_from_k8s()


def _list_from_k8s():
    try:
        proc = _run_cmd(
            ["oc", "get", "rosacontrolplane", "--all-namespaces", "-o", "json"], timeout=30
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


def _cluster_status_sync(cluster_name):
    result = {}

    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from agents.ocm_client import get_ocm_client
        ocm = get_ocm_client()
        rosa_data, err = ocm.describe_cluster(cluster_name)
        if rosa_data:
            result["rosa"] = rosa_data
    except Exception as e:
        result["rosa"] = {"error": str(e)}

    try:
        proc = _run_cmd(
            ["oc", "get", "rosacontrolplane", cluster_name, "-n", "ns-rosa-hcp", "-o", "json"], timeout=10
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

    try:
        proc = _run_cmd(
            ["oc", "get", "rosanetwork", f"{cluster_name}-network", "-n", "ns-rosa-hcp", "-o", "json"], timeout=10
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

    try:
        proc = _run_cmd(
            ["oc", "get", "machinepool", cluster_name, "-n", "ns-rosa-hcp", "-o", "json"], timeout=10
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


def _aws_resource_usage_sync():
    usage = {}
    checks = [
        ("vpcs", ["ec2", "describe-vpcs"], lambda d: len(d.get("Vpcs", []))),
        ("nat_gateways", ["ec2", "describe-nat-gateways"], lambda d: len([n for n in d.get("NatGateways", []) if n.get("State") == "available"])),
        ("security_groups", ["ec2", "describe-security-groups"], lambda d: len(d.get("SecurityGroups", []))),
        ("ec2_instances", ["ec2", "describe-instances"], lambda d: sum(len(r.get("Instances", [])) for r in d.get("Reservations", []))),
        ("ebs_volumes", ["ec2", "describe-volumes"], lambda d: len(d.get("Volumes", []))),
        ("load_balancers", ["elbv2", "describe-load-balancers"], lambda d: len(d.get("LoadBalancers", []))),
        ("cloudformation_stacks", ["cloudformation", "list-stacks"], lambda d: len([s for s in d.get("StackSummaries", []) if s.get("StackStatus") != "DELETE_COMPLETE"])),
        ("iam_roles", ["iam", "list-roles"], lambda d: len(d.get("Roles", []))),
        ("instance_profiles", ["iam", "list-instance-profiles"], lambda d: len(d.get("InstanceProfiles", []))),
        ("route53_zones", ["route53", "list-hosted-zones"], lambda d: len(d.get("HostedZones", []))),
        ("s3_buckets", ["s3api", "list-buckets"], lambda d: len(d.get("Buckets", []))),
    ]
    for name, cmd, extractor in checks:
        data, err = _aws_cmd(cmd)
        usage[name] = extractor(data) if data else f"error: {err}"
    return json.dumps(usage, indent=2)


def _cloudformation_stack_status_sync(stack_name, region="us-west-2"):
    data, err = _aws_cmd(
        ["cloudformation", "describe-stacks", "--stack-name", stack_name, "--region", region]
    )
    if err:
        return json.dumps({"error": err})

    stacks = data.get("Stacks", [])
    if not stacks:
        return json.dumps({"error": f"Stack '{stack_name}' not found"})

    stack = stacks[0]
    result = {
        "stack_name": stack.get("StackName"),
        "status": stack.get("StackStatus"),
        "status_reason": stack.get("StackStatusReason"),
        "created": stack.get("CreationTime"),
        "updated": stack.get("LastUpdatedTime"),
    }

    outputs = {}
    for o in stack.get("Outputs", []):
        outputs[o.get("OutputKey", "")] = o.get("OutputValue", "")
    if outputs:
        result["outputs"] = outputs

    if stack.get("StackStatus") == "DELETE_FAILED":
        events_data, _ = _aws_cmd([
            "cloudformation", "describe-stack-events",
            "--stack-name", stack_name, "--region", region
        ])
        if events_data:
            failed_events = [
                {"resource": e.get("LogicalResourceId"), "status": e.get("ResourceStatus"),
                 "reason": e.get("ResourceStatusReason")}
                for e in events_data.get("StackEvents", [])
                if "FAILED" in e.get("ResourceStatus", "")
            ]
            if failed_events:
                result["failed_resources"] = failed_events[:10]

    return json.dumps(result, indent=2, default=str)


def _aws_resource_details_sync(resource_type, region="us-west-2"):
    commands = {
        "vpcs": (["ec2", "describe-vpcs", "--region", region], "Vpcs"),
        "nat_gateways": (["ec2", "describe-nat-gateways", "--region", region], "NatGateways"),
        "security_groups": (["ec2", "describe-security-groups", "--region", region], "SecurityGroups"),
        "ec2_instances": (["ec2", "describe-instances", "--region", region], None),
        "cloudformation_stacks": (["cloudformation", "list-stacks", "--region", region], "StackSummaries"),
        "load_balancers": (["elbv2", "describe-load-balancers", "--region", region], "LoadBalancers"),
        "ebs_volumes": (["ec2", "describe-volumes", "--region", region], "Volumes"),
    }

    if resource_type not in commands:
        return json.dumps({"error": f"Unknown resource_type '{resource_type}'. Valid: {', '.join(commands.keys())}"})

    cmd, key = commands[resource_type]
    data, err = _aws_cmd(cmd)
    if err:
        return json.dumps({"error": err})

    if resource_type == "ec2_instances":
        instances = []
        for r in data.get("Reservations", []):
            for i in r.get("Instances", []):
                name_tag = next((t["Value"] for t in i.get("Tags", []) if t["Key"] == "Name"), "")
                instances.append({
                    "id": i.get("InstanceId"),
                    "name": name_tag,
                    "type": i.get("InstanceType"),
                    "state": i.get("State", {}).get("Name"),
                    "launch_time": i.get("LaunchTime"),
                })
        return json.dumps({"instances": instances, "count": len(instances)}, indent=2, default=str)

    if resource_type == "cloudformation_stacks":
        stacks = [s for s in data.get(key, []) if s.get("StackStatus") != "DELETE_COMPLETE"]
        summary = [{
            "name": s.get("StackName"),
            "status": s.get("StackStatus"),
            "created": s.get("CreationTime"),
            "updated": s.get("LastUpdatedTime"),
        } for s in stacks]
        return json.dumps({"stacks": summary, "count": len(summary)}, indent=2, default=str)

    items = data.get(key, [])
    return json.dumps({"count": len(items), resource_type: items}, indent=2, default=str)


def _k8s_get_resource_sync(resource_type, name="", namespace=""):
    if resource_type not in ALLOWED_K8S_RESOURCE_TYPES:
        return json.dumps({
            "error": f"Resource type '{resource_type}' not allowed. Allowed: {', '.join(ALLOWED_K8S_RESOURCE_TYPES)}"
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
        result = _run_cmd(cmd, timeout=15)
        if result.returncode != 0:
            return json.dumps({"error": result.stderr.strip()})

        data = json.loads(result.stdout)

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


def _k8s_events_sync(namespace="ns-rosa-hcp", limit=20):
    try:
        result = _run_cmd(
            ["oc", "get", "events", "-n", namespace,
             "--sort-by=.lastTimestamp", "-o", "json"],
            timeout=15,
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


def _search_known_issues_sync(query="", issue_type=""):
    try:
        with open(KB_DIR / "known_issues.json") as f:
            data = json.load(f)
    except Exception as e:
        return json.dumps({"error": f"Failed to load knowledge base: {e}"})

    patterns = data.get("patterns", []) if isinstance(data, dict) else data
    results = []
    for issue in patterns:
        if issue_type and issue.get("type") != issue_type:
            continue
        if query:
            searchable = json.dumps(issue).lower()
            if query.lower() not in searchable:
                continue
        results.append(issue)

    return json.dumps({"matches": results, "count": len(results), "total_known_issues": len(patterns)}, indent=2)


def _remediation_history_sync(issue_type="", limit=20):
    try:
        with open(KB_DIR / "remediation_outcomes.json") as f:
            outcomes = json.load(f)
    except Exception as e:
        return json.dumps({"error": f"Failed to load remediation outcomes: {e}"})

    if issue_type:
        outcomes = [o for o in outcomes if o.get("issue_type") == issue_type]

    total = len(outcomes)
    successes = sum(1 for o in outcomes if o.get("success"))
    failures = total - successes

    recent = outcomes[-limit:] if limit else outcomes
    recent.reverse()

    return json.dumps({
        "total_outcomes": total,
        "successes": successes,
        "failures": failures,
        "success_rate": f"{(successes / total * 100):.1f}%" if total else "N/A",
        "recent": recent,
    }, indent=2, default=str)


def _learning_stats_sync():
    stats = {}
    try:
        with open(KB_DIR / "remediation_outcomes.json") as f:
            outcomes = json.load(f)

        by_fix = {}
        for o in outcomes:
            fix = o.get("recommended_fix", "unknown")
            by_fix.setdefault(fix, {"total": 0, "successes": 0})
            by_fix[fix]["total"] += 1
            if o.get("success"):
                by_fix[fix]["successes"] += 1

        for fix, data in by_fix.items():
            data["success_rate"] = f"{(data['successes'] / data['total'] * 100):.1f}%" if data["total"] else "N/A"

        stats["by_fix_type"] = by_fix
        stats["total_outcomes"] = len(outcomes)
    except Exception as e:
        stats["outcomes_error"] = str(e)

    try:
        pending_path = KB_DIR / "pending_learnings.json"
        if pending_path.exists():
            with open(pending_path) as f:
                pending = json.load(f)
            stats["pending_review"] = len(pending)
            stats["pending_patterns"] = pending
        else:
            stats["pending_review"] = 0
    except Exception:
        stats["pending_review"] = 0

    return json.dumps(stats, indent=2, default=str)


def _diagnose_issue_sync(issue_type, resource_name, namespace="ns-rosa-hcp"):
    if issue_type not in VALID_ISSUE_TYPES:
        return json.dumps({
            "error": f"Unknown issue_type '{issue_type}'. Valid: {', '.join(VALID_ISSUE_TYPES)}"
        })

    try:
        from agents.diagnostic_agent import DiagnosticAgent

        agent = DiagnosticAgent(base_dir=PROJECT_ROOT)
        context = {
            "resource_name": resource_name,
            "namespace": namespace,
            "buffer": [],
        }
        diagnosis = agent.diagnose(issue_type, context)
        return json.dumps(diagnosis, indent=2, default=str)
    except ImportError as e:
        return json.dumps({"error": f"Could not import agent framework: {e}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Async wrappers
# ---------------------------------------------------------------------------

async def list_clusters():
    return await asyncio.to_thread(_list_clusters_sync)

async def cluster_status(cluster_name: str):
    return await asyncio.to_thread(_cluster_status_sync, cluster_name)

async def aws_resource_usage():
    return await asyncio.to_thread(_aws_resource_usage_sync)

async def cloudformation_stack_status(stack_name: str, region: str = "us-west-2"):
    return await asyncio.to_thread(_cloudformation_stack_status_sync, stack_name, region)

async def aws_resource_details(resource_type: str, region: str = "us-west-2"):
    return await asyncio.to_thread(_aws_resource_details_sync, resource_type, region)

async def k8s_get_resource(resource_type: str, name: str = "", namespace: str = ""):
    return await asyncio.to_thread(_k8s_get_resource_sync, resource_type, name, namespace)

async def k8s_events(namespace: str = "ns-rosa-hcp", limit: int = 20):
    return await asyncio.to_thread(_k8s_events_sync, namespace, limit)

async def search_known_issues(query: str = "", issue_type: str = ""):
    return await asyncio.to_thread(_search_known_issues_sync, query, issue_type)

async def remediation_history(issue_type: str = "", limit: int = 20):
    return await asyncio.to_thread(_remediation_history_sync, issue_type, limit)

async def learning_stats():
    return await asyncio.to_thread(_learning_stats_sync)

async def diagnose_issue(issue_type: str, resource_name: str, namespace: str = "ns-rosa-hcp"):
    return await asyncio.to_thread(_diagnose_issue_sync, issue_type, resource_name, namespace)


# ---------------------------------------------------------------------------
# Tool dispatch map
# ---------------------------------------------------------------------------

TOOL_DISPATCH: Dict[str, Callable] = {
    "capa_list_clusters": list_clusters,
    "capa_cluster_status": cluster_status,
    "capa_aws_resource_usage": aws_resource_usage,
    "capa_cloudformation_stack_status": cloudformation_stack_status,
    "capa_aws_resource_details": aws_resource_details,
    "capa_k8s_get_resource": k8s_get_resource,
    "capa_k8s_events": k8s_events,
    "capa_search_known_issues": search_known_issues,
    "capa_remediation_history": remediation_history,
    "capa_learning_stats": learning_stats,
    "capa_diagnose_issue": diagnose_issue,
}


# ---------------------------------------------------------------------------
# Claude API tool definitions
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "name": "capa_list_clusters",
        "description": "List all ROSA HCP clusters with status, region, version, and namespace.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "capa_cluster_status",
        "description": "Get detailed status of a specific ROSA HCP cluster including K8s resource conditions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cluster_name": {
                    "type": "string",
                    "description": "Name of the ROSA cluster",
                },
            },
            "required": ["cluster_name"],
        },
    },
    {
        "name": "capa_aws_resource_usage",
        "description": "Get counts of all AWS resources: VPCs, NAT gateways, CloudFormation stacks, security groups, IAM roles, EC2 instances, EBS volumes, Route53 zones, S3 buckets, load balancers, and instance profiles.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "capa_cloudformation_stack_status",
        "description": "Get detailed status of a specific CloudFormation stack.",
        "input_schema": {
            "type": "object",
            "properties": {
                "stack_name": {
                    "type": "string",
                    "description": "CloudFormation stack name",
                },
                "region": {
                    "type": "string",
                    "description": "AWS region (default: us-west-2)",
                },
            },
            "required": ["stack_name"],
        },
    },
    {
        "name": "capa_aws_resource_details",
        "description": "Get detailed information about a specific type of AWS resource.",
        "input_schema": {
            "type": "object",
            "properties": {
                "resource_type": {
                    "type": "string",
                    "description": "One of: vpcs, nat_gateways, security_groups, ec2_instances, cloudformation_stacks, load_balancers, ebs_volumes",
                },
                "region": {
                    "type": "string",
                    "description": "AWS region (default: us-west-2)",
                },
            },
            "required": ["resource_type"],
        },
    },
    {
        "name": "capa_k8s_get_resource",
        "description": "Query Kubernetes/OpenShift resources. Restricted to CAPI-related resource types.",
        "input_schema": {
            "type": "object",
            "properties": {
                "resource_type": {
                    "type": "string",
                    "description": "Resource type: rosacontrolplane, rosanetwork, rosaroleconfig, rosamachinepool, machinepool, cluster, namespace, pods, events, secrets",
                },
                "name": {
                    "type": "string",
                    "description": "Specific resource name (optional - omit to list all)",
                },
                "namespace": {
                    "type": "string",
                    "description": "K8s namespace (optional - omit for all namespaces)",
                },
            },
            "required": ["resource_type"],
        },
    },
    {
        "name": "capa_k8s_events",
        "description": "Get recent Kubernetes events for a namespace, sorted by time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "K8s namespace (default: ns-rosa-hcp)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max events to return (default: 20)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "capa_search_known_issues",
        "description": "Search the CAPA knowledge base for known cluster issues and their remediation strategies.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free-text search across issue descriptions, symptoms, and causes",
                },
                "issue_type": {
                    "type": "string",
                    "description": "Filter by exact issue type (e.g., 'cloudformation_deletion_failure')",
                },
            },
            "required": [],
        },
    },
    {
        "name": "capa_remediation_history",
        "description": "View past remediation outcomes - what fixes were tried, whether they succeeded, and details.",
        "input_schema": {
            "type": "object",
            "properties": {
                "issue_type": {
                    "type": "string",
                    "description": "Filter by issue type (optional)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default: 20)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "capa_learning_stats",
        "description": "Get AI agent learning statistics - success rates by fix type, confidence trends, and pending patterns awaiting human review.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "capa_diagnose_issue",
        "description": "Run the CAPA diagnostic pipeline for a specific cluster issue. Returns root cause analysis, confidence score, evidence, and recommended fix.",
        "input_schema": {
            "type": "object",
            "properties": {
                "issue_type": {
                    "type": "string",
                    "description": "One of: rosanetwork_stuck_deletion, rosacontrolplane_stuck_deletion, rosaroleconfig_stuck_deletion, cloudformation_deletion_failure, ocm_auth_failure, capi_not_installed",
                },
                "resource_name": {
                    "type": "string",
                    "description": "K8s resource name (e.g., 'moo-rosa-hcp-network')",
                },
                "namespace": {
                    "type": "string",
                    "description": "K8s namespace (default: ns-rosa-hcp)",
                },
            },
            "required": ["issue_type", "resource_name"],
        },
    },
]
