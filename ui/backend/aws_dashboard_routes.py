"""
AWS Dashboard & external-service routes -- FastAPI router for
AWS usage, Jenkins test results, and GitHub repo activity endpoints.

Endpoints moved here from app.py:
  GET    /api/jenkins/test-results-trend
  GET    /api/github/repo-activity
  GET    /api/aws/usage
  GET    /api/aws/usage-trend
  GET    /api/aws/usage-config
  GET    /api/aws/usage/{resource_key}
  GET    /api/aws/resource-details/{resource_type}

Also contains:
  _collect_aws_usage_data     -- sync helper to poll AWS CLI for resource counts
  _get_aws_history_db         -- path to SQLite history DB
  _init_aws_history_db        -- create tables on first import
  _save_aws_usage_snapshot    -- persist a usage snapshot to the DB
  _aws_usage_snapshot_loop    -- hourly background coroutine
"""

import asyncio
import json
import os
import sqlite3 as _sqlite3
import subprocess
import sys
from datetime import datetime

from fastapi import APIRouter, Response


def _get_sqlite3():
    """Return the sqlite3 module, preferring the app module's reference so
    that ``@patch("app.sqlite3")`` in tests takes effect."""
    app_mod = sys.modules.get("app")
    if app_mod is not None and hasattr(app_mod, "sqlite3"):
        return app_mod.sqlite3
    return _sqlite3

router = APIRouter()


def _resolve(name: str):
    """Look up *name* via the app module so that unittest.mock.patch on
    ``app.<name>`` takes effect even though the endpoint lives here."""
    app_mod = sys.modules.get("app")
    if app_mod is not None:
        return getattr(app_mod, name)
    return globals()[name]


# ---------------------------------------------------------------------------
# AWS usage data collection
# ---------------------------------------------------------------------------

def _collect_aws_usage_data():
    """Collect AWS resource usage counts (sync, can be called from background tasks)"""
    usage_data = {}

    # Instance Profiles
    try:
        result = subprocess.run(
            ["aws", "iam", "list-instance-profiles", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            usage_data["instance_profiles"] = len(data.get("InstanceProfiles", []))
        else:
            usage_data["instance_profiles"] = "error"
    except Exception as e:
        usage_data["instance_profiles"] = "error"

    # CloudFormation Stacks
    try:
        result = subprocess.run(
            ["aws", "cloudformation", "list-stacks", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            # Only count non-deleted stacks
            stacks = [s for s in data.get("StackSummaries", [])
                     if s.get("StackStatus") not in ["DELETE_COMPLETE"]]
            usage_data["cloudformation_stacks"] = len(stacks)
        else:
            usage_data["cloudformation_stacks"] = "error"
    except Exception as e:
        usage_data["cloudformation_stacks"] = "error"

    # NAT Gateways
    try:
        result = subprocess.run(
            ["aws", "ec2", "describe-nat-gateways", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            # Only count available NAT gateways
            nat_gateways = [n for n in data.get("NatGateways", [])
                           if n.get("State") == "available"]
            usage_data["nat_gateways"] = len(nat_gateways)
        else:
            usage_data["nat_gateways"] = "error"
    except Exception as e:
        usage_data["nat_gateways"] = "error"

    # Route53 Hosted Zones
    try:
        result = subprocess.run(
            ["aws", "route53", "list-hosted-zones", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            usage_data["route53_zones"] = len(data.get("HostedZones", []))
        else:
            usage_data["route53_zones"] = "error"
    except Exception as e:
        usage_data["route53_zones"] = "error"

    # IAM Roles
    try:
        result = subprocess.run(
            ["aws", "iam", "list-roles", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            usage_data["iam_roles"] = len(data.get("Roles", []))
        else:
            usage_data["iam_roles"] = "error"
    except Exception as e:
        usage_data["iam_roles"] = "error"

    # VPCs
    try:
        result = subprocess.run(
            ["aws", "ec2", "describe-vpcs", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            usage_data["vpcs"] = len(data.get("Vpcs", []))
        else:
            usage_data["vpcs"] = "error"
    except Exception as e:
        usage_data["vpcs"] = "error"

    # Security Groups
    try:
        result = subprocess.run(
            ["aws", "ec2", "describe-security-groups", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            usage_data["security_groups"] = len(data.get("SecurityGroups", []))
        else:
            usage_data["security_groups"] = "error"
    except Exception as e:
        usage_data["security_groups"] = "error"

    # EC2 Instances
    try:
        result = subprocess.run(
            ["aws", "ec2", "describe-instances", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            # Count running and stopped instances
            instance_count = 0
            for reservation in data.get("Reservations", []):
                instance_count += len(reservation.get("Instances", []))
            usage_data["ec2_instances"] = instance_count
        else:
            usage_data["ec2_instances"] = "error"
    except Exception as e:
        usage_data["ec2_instances"] = "error"

    # EBS Volumes
    try:
        result = subprocess.run(
            ["aws", "ec2", "describe-volumes", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            usage_data["ebs_volumes"] = len(data.get("Volumes", []))
        else:
            usage_data["ebs_volumes"] = "error"
    except Exception as e:
        usage_data["ebs_volumes"] = "error"

    # Load Balancers
    try:
        result = subprocess.run(
            ["aws", "elbv2", "describe-load-balancers", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            usage_data["load_balancers"] = len(data.get("LoadBalancers", []))
        else:
            usage_data["load_balancers"] = "error"
    except Exception as e:
        usage_data["load_balancers"] = "error"

    # S3 Buckets
    try:
        result = subprocess.run(
            ["aws", "s3api", "list-buckets", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            usage_data["s3_buckets"] = len(data.get("Buckets", []))
        else:
            usage_data["s3_buckets"] = "error"
    except Exception as e:
        usage_data["s3_buckets"] = "error"

    return usage_data


# ---------------------------------------------------------------------------
# AWS usage history DB helpers
# ---------------------------------------------------------------------------

def _get_aws_history_db():
    """Get path to AWS usage history database"""
    db_path = os.path.join(os.path.dirname(__file__), "aws_usage_history.db")
    return db_path


def _init_aws_history_db():
    """Initialize the AWS usage history SQLite database"""
    db_path = _get_aws_history_db()
    conn = _get_sqlite3().connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usage_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            resource_key TEXT NOT NULL,
            count INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_timestamp ON usage_snapshots(timestamp)
    """)
    conn.commit()
    conn.close()


# Initialize DB on module load
_init_aws_history_db()


def _save_aws_usage_snapshot(usage_data):
    """Save a usage snapshot to the history database"""
    try:
        db_path = _get_aws_history_db()
        conn = _get_sqlite3().connect(db_path)
        timestamp = datetime.now().isoformat()
        for key, value in usage_data.items():
            if value != "error" and isinstance(value, (int, float)):
                conn.execute(
                    "INSERT INTO usage_snapshots (timestamp, resource_key, count) VALUES (?, ?, ?)",
                    (timestamp, key, int(value))
                )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"\u26a0\ufe0f [AWS HISTORY] Failed to save snapshot: {e}")


async def _aws_usage_snapshot_loop():
    """Background task that collects AWS usage snapshots every hour"""
    await asyncio.sleep(10)  # Wait for app startup
    print("\U0001f504 [AWS TREND] Hourly AWS usage snapshot collector started", flush=True)
    while True:
        try:
            usage_data = await asyncio.to_thread(_resolve("_collect_aws_usage_data"))
            _resolve("_save_aws_usage_snapshot")(usage_data)
            valid_count = sum(1 for v in usage_data.values() if v != "error")
            print(f"\u2705 [AWS TREND] Hourly snapshot saved: {valid_count} resources at {datetime.now().strftime('%H:%M')}", flush=True)
        except Exception as e:
            print(f"\u26a0\ufe0f [AWS TREND] Hourly snapshot failed: {e}", flush=True)
        await asyncio.sleep(3600)  # 1 hour


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/jenkins/test-results-trend")
async def get_jenkins_test_results_trend(response: Response):
    """Get Jenkins test results trend data from CAPI tests job"""
    import requests
    from datetime import datetime
    import urllib3

    # Suppress SSL warnings for self-signed cert
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    try:
        jenkins_base_url = "https://jenkins-csb-rhacm-tests.dno.corp.redhat.com/job/CI-Jobs/job/capi_tests"

        # Fetch recent builds (last 20)
        builds_url = f"{jenkins_base_url}/api/json?tree=builds[number,result,timestamp,duration]{{0,20}}"

        print(f"\U0001f4ca [JENKINS] Fetching test trend data from: {builds_url}")

        # Disable SSL verification for internal Jenkins (self-signed cert)
        response = requests.get(builds_url, timeout=10, verify=False)
        response.raise_for_status()
        data = response.json()

        trend_data = []

        # For each build, fetch test results
        for build in data.get("builds", [])[:20]:
            build_number = build.get("number")
            result = build.get("result")
            timestamp = build.get("timestamp")

            # Skip builds without results (still running)
            if not result:
                continue

            try:
                # Fetch test report for this build
                test_url = f"{jenkins_base_url}/{build_number}/testReport/api/json"
                test_response = requests.get(test_url, timeout=5, verify=False)

                if test_response.status_code == 200:
                    test_data = test_response.json()

                    pass_count = test_data.get("passCount", 0)
                    fail_count = test_data.get("failCount", 0)
                    skip_count = test_data.get("skipCount", 0)
                    total_count = pass_count + fail_count + skip_count

                    trend_data.append({
                        "build": build_number,
                        "result": result,
                        "timestamp": datetime.fromtimestamp(timestamp / 1000).isoformat() if timestamp else None,
                        "passCount": pass_count,
                        "failCount": fail_count,
                        "skipCount": skip_count,
                        "totalCount": total_count,
                        "passRate": round((pass_count / total_count * 100), 1) if total_count > 0 else 0,
                    })
                else:
                    # Build might not have test results
                    print(f"\u26a0\ufe0f  [JENKINS] Build #{build_number} has no test results (status {test_response.status_code})")
            except Exception as e:
                print(f"\u26a0\ufe0f  [JENKINS] Failed to fetch test results for build #{build_number}: {str(e)}")
                continue

        # Sort by build number descending (newest first)
        trend_data.sort(key=lambda x: x["build"], reverse=True)

        print(f"\u2705 [JENKINS] Successfully fetched trend data for {len(trend_data)} builds")

        # Set cache-control headers to prevent caching
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

        return {
            "success": True,
            "trend": trend_data,
            "count": len(trend_data),
        }

    except Exception as e:
        print(f"\u274c [JENKINS] Error fetching test results trend: {str(e)}")
        import traceback
        traceback.print_exc()

        return {
            "success": False,
            "trend": [],
            "count": 0,
            "message": f"Error fetching Jenkins test results: {str(e)}",
        }


@router.get("/api/github/repo-activity")
async def get_github_repo_activity():
    """Get GitHub repository activity stats"""
    import requests
    from datetime import datetime, timedelta

    try:
        # Repositories to monitor
        repos = [
            "stolostron/cluster-api-provider-aws",
            "tinaafitz/test-automation-capa"
        ]

        activity_data = []

        for repo in repos:
            # GitHub API endpoint for repo stats
            api_base = f"https://api.github.com/repos/{repo}"

            # Get repo info
            repo_response = requests.get(api_base, timeout=10)
            if repo_response.status_code != 200:
                print(f"\u26a0\ufe0f  [GITHUB] Failed to fetch {repo}: {repo_response.status_code}")
                # Add repo with placeholder data if rate limited
                activity_data.append({
                    "repo": repo,
                    "name": repo.split("/")[1],
                    "stars": 0,
                    "forks": 0,
                    "open_issues": 0,
                    "open_prs": 0,
                    "merged_prs_7d": "?",
                    "commits_7d": 0,
                    "updated_at": None,
                    "error": "Rate limited" if repo_response.status_code == 403 else f"Error {repo_response.status_code}"
                })
                continue

            repo_data = repo_response.json()

            # Get recent commits (last 7 days)
            since_date = (datetime.now() - timedelta(days=7)).isoformat()
            commits_url = f"{api_base}/commits?since={since_date}&per_page=100"
            commits_response = requests.get(commits_url, timeout=10)
            commits_count = len(commits_response.json()) if commits_response.status_code == 200 else 0

            # Get open PRs
            prs_url = f"{api_base}/pulls?state=open&per_page=100"
            prs_response = requests.get(prs_url, timeout=10)
            open_prs = len(prs_response.json()) if prs_response.status_code == 200 else 0

            # Get merged PRs (last 7 days)
            merged_prs_url = f"{api_base}/pulls?state=closed&per_page=100"
            merged_prs_response = requests.get(merged_prs_url, timeout=10)
            merged_prs_count = 0
            if merged_prs_response.status_code == 200:
                closed_prs = merged_prs_response.json()
                # Filter for merged PRs in last 7 days
                seven_days_ago = datetime.now() - timedelta(days=7)
                for pr in closed_prs:
                    if pr.get("merged_at"):
                        merged_at = datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00"))
                        if merged_at.replace(tzinfo=None) >= seven_days_ago:
                            merged_prs_count += 1

            # Get open issues (excluding PRs)
            issues_url = f"{api_base}/issues?state=open&per_page=100"
            issues_response = requests.get(issues_url, timeout=10)
            all_open = len(issues_response.json()) if issues_response.status_code == 200 else 0
            open_issues = all_open - open_prs  # Issues includes PRs, so subtract

            activity_data.append({
                "repo": repo,
                "name": repo.split("/")[1],
                "stars": repo_data.get("stargazers_count", 0),
                "forks": repo_data.get("forks_count", 0),
                "open_issues": open_issues,
                "open_prs": open_prs,
                "merged_prs_7d": merged_prs_count,
                "commits_7d": commits_count,
                "updated_at": repo_data.get("updated_at"),
            })

        print(f"\u2705 [GITHUB] Successfully fetched activity for {len(activity_data)} repos")

        return {
            "success": True,
            "repos": activity_data,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        print(f"\u274c [GITHUB] Error fetching repo activity: {str(e)}")
        return {
            "success": False,
            "repos": [],
            "message": f"Error fetching GitHub repo activity: {str(e)}",
        }


@router.get("/api/aws/usage")
async def get_aws_usage():
    """Get AWS resource usage counts"""
    try:
        usage_data = _resolve("_collect_aws_usage_data")()

        # Save snapshot to history
        _resolve("_save_aws_usage_snapshot")(usage_data)

        return {
            "success": True,
            "usage": usage_data,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        print(f"\u274c [AWS USAGE] Error fetching AWS usage: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to fetch AWS usage data: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }


@router.get("/api/aws/usage-trend")
async def get_aws_usage_trend(days: int = 30):
    """Get AWS resource usage trend data over time"""
    try:
        db_path = _resolve("_get_aws_history_db")()
        conn = _get_sqlite3().connect(db_path)

        # Get snapshots from the last N days
        cutoff = (datetime.now() - __import__('datetime').timedelta(days=days)).isoformat()
        rows = conn.execute(
            """SELECT timestamp, resource_key, count FROM usage_snapshots
               WHERE timestamp >= ? ORDER BY timestamp ASC""",
            (cutoff,)
        ).fetchall()
        conn.close()

        if not rows:
            return {"success": True, "trend": [], "days": days, "message": "No historical data yet. Refresh the AWS Usage page to start collecting data."}

        # Group by timestamp (each snapshot)
        # Use hourly grouping only when we have enough data (>48 snapshots)
        snapshots = {}
        use_hourly = len(set(r[0] for r in rows)) > 48
        for timestamp, resource_key, count in rows:
            group_key = timestamp[:13] if use_hourly else timestamp
            if group_key not in snapshots:
                snapshots[group_key] = {"timestamp": timestamp, "resources": {}}
            snapshots[group_key]["resources"][resource_key] = count

        # Convert to list sorted by time
        trend = []
        for group_key in sorted(snapshots.keys()):
            snap = snapshots[group_key]
            trend.append({
                "timestamp": snap["timestamp"],
                **snap["resources"]
            })

        # Get unique resource keys
        all_keys = set()
        for snap in trend:
            all_keys.update(k for k in snap.keys() if k != "timestamp")

        return {
            "success": True,
            "trend": trend,
            "resource_keys": sorted(all_keys),
            "days": days,
            "snapshot_count": len(trend)
        }

    except Exception as e:
        print(f"\u274c [AWS TREND] Error fetching trend data: {e}")
        return {
            "success": False,
            "message": f"Failed to fetch trend data: {str(e)}"
        }


@router.get("/api/aws/usage-config")
async def get_aws_config():
    """Get AWS resource configuration with live quotas from AWS API"""
    try:
        from aws_config_service import aws_config_service
        return aws_config_service.get_resource_config_with_quotas()
    except Exception as e:
        print(f"\u274c [AWS CONFIG] Error loading AWS configuration: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to load AWS configuration: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }


@router.get("/api/aws/usage/{resource_key}")
async def get_single_resource_usage(resource_key: str):
    """Refresh count for a single AWS resource type"""
    try:
        count = "error"

        if resource_key == "nat_gateways":
            r = subprocess.run(["aws", "ec2", "describe-nat-gateways", "--output", "json"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                data = json.loads(r.stdout)
                count = len([n for n in data.get("NatGateways", []) if n.get("State") == "available"])
        elif resource_key == "route53_zones":
            r = subprocess.run(["aws", "route53", "list-hosted-zones", "--output", "json"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                count = len(json.loads(r.stdout).get("HostedZones", []))
        elif resource_key == "iam_roles":
            r = subprocess.run(["aws", "iam", "list-roles", "--output", "json"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                count = len(json.loads(r.stdout).get("Roles", []))
        elif resource_key == "vpcs":
            r = subprocess.run(["aws", "ec2", "describe-vpcs", "--output", "json"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                count = len(json.loads(r.stdout).get("Vpcs", []))
        elif resource_key == "security_groups":
            r = subprocess.run(["aws", "ec2", "describe-security-groups", "--output", "json"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                count = len(json.loads(r.stdout).get("SecurityGroups", []))
        elif resource_key == "ec2_instances":
            r = subprocess.run(["aws", "ec2", "describe-instances", "--output", "json"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                data = json.loads(r.stdout)
                count = sum(len(res.get("Instances", [])) for res in data.get("Reservations", []))
        elif resource_key == "ebs_volumes":
            r = subprocess.run(["aws", "ec2", "describe-volumes", "--output", "json"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                count = len(json.loads(r.stdout).get("Volumes", []))
        elif resource_key == "load_balancers":
            r = subprocess.run(["aws", "elbv2", "describe-load-balancers", "--output", "json"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                count = len(json.loads(r.stdout).get("LoadBalancers", []))
        elif resource_key == "s3_buckets":
            r = subprocess.run(["aws", "s3api", "list-buckets", "--output", "json"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                count = len(json.loads(r.stdout).get("Buckets", []))
        elif resource_key == "cloudformation_stacks":
            r = subprocess.run(["aws", "cloudformation", "list-stacks", "--output", "json"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                data = json.loads(r.stdout)
                count = len([s for s in data.get("StackSummaries", []) if s.get("StackStatus") not in ["DELETE_COMPLETE"]])
        elif resource_key == "instance_profiles":
            r = subprocess.run(["aws", "iam", "list-instance-profiles", "--output", "json"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                count = len(json.loads(r.stdout).get("InstanceProfiles", []))
        else:
            return {"success": False, "message": f"Unknown resource type: {resource_key}"}

        return {"success": True, "resource_key": resource_key, "count": count, "timestamp": datetime.now().isoformat()}

    except Exception as e:
        return {"success": False, "message": f"Failed to refresh {resource_key}: {str(e)}"}


@router.get("/api/aws/resource-details/{resource_type}")
async def get_resource_details(resource_type: str):
    """Get detailed information about specific AWS resources including creation time, tags, and metadata"""
    try:
        details = []

        if resource_type == "nat_gateways":
            result = subprocess.run(
                ["aws", "ec2", "describe-nat-gateways", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                nat_gateways = [n for n in data.get("NatGateways", [])
                               if n.get("State") == "available"]

                for nat in nat_gateways:
                    # Get VPC name from tags if available
                    vpc_name = None
                    vpc_id = nat.get("VpcId", "N/A")

                    # Try to get VPC name
                    try:
                        vpc_result = subprocess.run(
                            ["aws", "ec2", "describe-vpcs", "--vpc-ids", vpc_id, "--output", "json"],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if vpc_result.returncode == 0:
                            vpc_data = json.loads(vpc_result.stdout)
                            vpcs = vpc_data.get("Vpcs", [])
                            if vpcs:
                                vpc_tags = {tag["Key"]: tag["Value"] for tag in vpcs[0].get("Tags", [])}
                                vpc_name = vpc_tags.get("Name", vpc_id)
                    except:
                        vpc_name = vpc_id

                    # Extract tags
                    tags = {tag["Key"]: tag["Value"] for tag in nat.get("Tags", [])}

                    details.append({
                        "id": nat.get("NatGatewayId", "N/A"),
                        "name": tags.get("Name", "Unnamed"),
                        "vpc_id": vpc_id,
                        "vpc_name": vpc_name or vpc_id,
                        "subnet_id": nat.get("SubnetId", "N/A"),
                        "state": nat.get("State", "N/A"),
                        "created_at": nat.get("CreateTime", "N/A"),
                        "tags": tags,
                        "public_ip": nat.get("NatGatewayAddresses", [{}])[0].get("PublicIp", "N/A") if nat.get("NatGatewayAddresses") else "N/A"
                    })

        elif resource_type == "route53_zones":
            result = subprocess.run(
                ["aws", "route53", "list-hosted-zones", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for zone in data.get("HostedZones", []):
                    # Get tags for this hosted zone
                    zone_id = zone.get("Id", "").split("/")[-1]
                    tags = {}
                    try:
                        tags_result = subprocess.run(
                            ["aws", "route53", "list-tags-for-resource",
                             "--resource-type", "hostedzone",
                             "--resource-id", zone_id,
                             "--output", "json"],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if tags_result.returncode == 0:
                            tags_data = json.loads(tags_result.stdout)
                            tags = {tag["Key"]: tag["Value"] for tag in tags_data.get("ResourceTagSet", {}).get("Tags", [])}
                    except:
                        pass

                    details.append({
                        "id": zone.get("Id", "N/A"),
                        "name": zone.get("Name", "N/A"),
                        "record_count": zone.get("ResourceRecordSetCount", 0),
                        "private_zone": zone.get("Config", {}).get("PrivateZone", False),
                        "comment": zone.get("Config", {}).get("Comment", ""),
                        "tags": tags
                    })

        elif resource_type == "vpcs":
            result = subprocess.run(
                ["aws", "ec2", "describe-vpcs", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for vpc in data.get("Vpcs", []):
                    tags = {tag["Key"]: tag["Value"] for tag in vpc.get("Tags", [])}
                    details.append({
                        "id": vpc.get("VpcId", "N/A"),
                        "name": tags.get("Name", "Unnamed"),
                        "cidr": vpc.get("CidrBlock", "N/A"),
                        "state": vpc.get("State", "N/A"),
                        "is_default": vpc.get("IsDefault", False),
                        "tags": tags
                    })

        elif resource_type == "ec2_instances":
            result = subprocess.run(
                ["aws", "ec2", "describe-instances", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for reservation in data.get("Reservations", []):
                    for instance in reservation.get("Instances", []):
                        tags = {tag["Key"]: tag["Value"] for tag in instance.get("Tags", [])}
                        details.append({
                            "id": instance.get("InstanceId", "N/A"),
                            "name": tags.get("Name", "Unnamed"),
                            "type": instance.get("InstanceType", "N/A"),
                            "state": instance.get("State", {}).get("Name", "N/A"),
                            "launch_time": instance.get("LaunchTime", "N/A"),
                            "vpc_id": instance.get("VpcId", "N/A"),
                            "subnet_id": instance.get("SubnetId", "N/A"),
                            "private_ip": instance.get("PrivateIpAddress", "N/A"),
                            "public_ip": instance.get("PublicIpAddress", "N/A"),
                            "tags": tags
                        })

        elif resource_type == "ebs_volumes":
            result = subprocess.run(
                ["aws", "ec2", "describe-volumes", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for volume in data.get("Volumes", []):
                    tags = {tag["Key"]: tag["Value"] for tag in volume.get("Tags", [])}

                    # Get attachment info
                    attachments = volume.get("Attachments", [])
                    attached_to = attachments[0].get("InstanceId", "Not attached") if attachments else "Not attached"

                    details.append({
                        "id": volume.get("VolumeId", "N/A"),
                        "name": tags.get("Name", "Unnamed"),
                        "size": f"{volume.get('Size', 0)} GB",
                        "volume_type": volume.get("VolumeType", "N/A"),
                        "state": volume.get("State", "N/A"),
                        "created_at": volume.get("CreateTime", "N/A"),
                        "availability_zone": volume.get("AvailabilityZone", "N/A"),
                        "attached_to": attached_to,
                        "encrypted": volume.get("Encrypted", False),
                        "tags": tags
                    })

        elif resource_type == "instance_profiles":
            result = subprocess.run(
                ["aws", "iam", "list-instance-profiles", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                # Limit to first 100 profiles to prevent timeout
                profiles_to_process = data.get("InstanceProfiles", [])[:100]

                for profile in profiles_to_process:
                    profile_name = profile.get("InstanceProfileName", "")
                    # Skip tag fetching for instance profiles to speed up loading
                    tags = {}

                    # Get associated roles
                    roles = [r.get("RoleName", "") for r in profile.get("Roles", [])]

                    details.append({
                        "id": profile.get("InstanceProfileId", "N/A"),
                        "name": profile_name,
                        "arn": profile.get("Arn", "N/A"),
                        "created_at": profile.get("CreateDate", "N/A"),
                        "path": profile.get("Path", "/"),
                        "roles": roles,
                        "tags": tags
                    })

        elif resource_type == "iam_roles":
            result = subprocess.run(
                ["aws", "iam", "list-roles", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                # Limit to first 100 roles to prevent timeout
                roles_to_process = data.get("Roles", [])[:100]

                for role in roles_to_process:
                    role_name = role.get("RoleName", "")
                    # Skip tag fetching for IAM roles to speed up loading
                    # Tags can be added later if needed
                    tags = {}

                    details.append({
                        "id": role.get("RoleId", "N/A"),
                        "name": role_name,
                        "arn": role.get("Arn", "N/A"),
                        "created_at": role.get("CreateDate", "N/A"),
                        "path": role.get("Path", "/"),
                        "description": role.get("Description", ""),
                        "max_session_duration": role.get("MaxSessionDuration", 3600),
                        "tags": tags
                    })

        elif resource_type == "cloudformation_stacks":
            result = subprocess.run(
                ["aws", "cloudformation", "list-stacks", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                stacks = [s for s in data.get("StackSummaries", [])
                         if s.get("StackStatus") not in ["DELETE_COMPLETE"]]

                for stack in stacks:
                    stack_name = stack.get("StackName", "")
                    # Get detailed stack info including tags
                    try:
                        detail_result = subprocess.run(
                            ["aws", "cloudformation", "describe-stacks", "--stack-name", stack_name, "--output", "json"],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if detail_result.returncode == 0:
                            detail_data = json.loads(detail_result.stdout)
                            if detail_data.get("Stacks"):
                                stack_detail = detail_data["Stacks"][0]
                                tags = {tag["Key"]: tag["Value"] for tag in stack_detail.get("Tags", [])}

                                details.append({
                                    "id": stack.get("StackId", "N/A"),
                                    "name": stack_name,
                                    "status": stack.get("StackStatus", "N/A"),
                                    "created_at": stack.get("CreationTime", "N/A"),
                                    "description": stack_detail.get("Description", ""),
                                    "tags": tags
                                })
                    except:
                        # Fallback if detailed fetch fails
                        details.append({
                            "id": stack.get("StackId", "N/A"),
                            "name": stack_name,
                            "status": stack.get("StackStatus", "N/A"),
                            "created_at": stack.get("CreationTime", "N/A"),
                            "description": "",
                            "tags": {}
                        })

        elif resource_type == "load_balancers":
            # Classic load balancers
            result = subprocess.run(
                ["aws", "elbv2", "describe-load-balancers", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for lb in data.get("LoadBalancers", []):
                    lb_arn = lb.get("LoadBalancerArn", "")
                    tags = {}
                    try:
                        tags_result = subprocess.run(
                            ["aws", "elbv2", "describe-tags", "--resource-arns", lb_arn, "--output", "json"],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if tags_result.returncode == 0:
                            tags_data = json.loads(tags_result.stdout)
                            for desc in tags_data.get("TagDescriptions", []):
                                tags = {tag["Key"]: tag["Value"] for tag in desc.get("Tags", [])}
                    except:
                        pass

                    vpc_id = lb.get("VpcId", "N/A")
                    vpc_name = vpc_id
                    try:
                        vpc_result = subprocess.run(
                            ["aws", "ec2", "describe-vpcs", "--vpc-ids", vpc_id, "--output", "json"],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if vpc_result.returncode == 0:
                            vpc_data = json.loads(vpc_result.stdout)
                            vpcs = vpc_data.get("Vpcs", [])
                            if vpcs:
                                vpc_tags = {tag["Key"]: tag["Value"] for tag in vpcs[0].get("Tags", [])}
                                vpc_name = vpc_tags.get("Name", vpc_id)
                    except:
                        pass

                    details.append({
                        "id": lb.get("LoadBalancerArn", "N/A").split("/")[-1] if "/" in lb.get("LoadBalancerArn", "") else lb.get("LoadBalancerArn", "N/A"),
                        "name": lb.get("LoadBalancerName", "Unnamed"),
                        "type": lb.get("Type", "N/A"),
                        "scheme": lb.get("Scheme", "N/A"),
                        "state": lb.get("State", {}).get("Code", "N/A"),
                        "dns_name": lb.get("DNSName", "N/A"),
                        "vpc_id": vpc_id,
                        "vpc_name": vpc_name,
                        "created_at": lb.get("CreatedTime", "N/A"),
                        "tags": tags
                    })

        elif resource_type == "s3_buckets":
            result = subprocess.run(
                ["aws", "s3api", "list-buckets", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for bucket in data.get("Buckets", []):
                    bucket_name = bucket.get("Name", "")
                    tags = {}
                    try:
                        tags_result = subprocess.run(
                            ["aws", "s3api", "get-bucket-tagging", "--bucket", bucket_name, "--output", "json"],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if tags_result.returncode == 0:
                            tags_data = json.loads(tags_result.stdout)
                            tags = {tag["Key"]: tag["Value"] for tag in tags_data.get("TagSet", [])}
                    except:
                        pass

                    details.append({
                        "id": bucket_name,
                        "name": bucket_name,
                        "created_at": bucket.get("CreationDate", "N/A"),
                        "tags": tags
                    })

        elif resource_type == "security_groups":
            result = subprocess.run(
                ["aws", "ec2", "describe-security-groups", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for sg in data.get("SecurityGroups", []):
                    tags = {tag["Key"]: tag["Value"] for tag in sg.get("Tags", [])}

                    # Count inbound and outbound rules
                    ingress_rules = len(sg.get("IpPermissions", []))
                    egress_rules = len(sg.get("IpPermissionsEgress", []))

                    # Get VPC name if available
                    vpc_id = sg.get("VpcId", "N/A")
                    vpc_name = vpc_id
                    try:
                        vpc_result = subprocess.run(
                            ["aws", "ec2", "describe-vpcs", "--vpc-ids", vpc_id, "--output", "json"],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if vpc_result.returncode == 0:
                            vpc_data = json.loads(vpc_result.stdout)
                            vpcs = vpc_data.get("Vpcs", [])
                            if vpcs:
                                vpc_tags = {tag["Key"]: tag["Value"] for tag in vpcs[0].get("Tags", [])}
                                vpc_name = vpc_tags.get("Name", vpc_id)
                    except:
                        pass

                    details.append({
                        "id": sg.get("GroupId", "N/A"),
                        "name": sg.get("GroupName", "Unnamed"),
                        "description": sg.get("Description", ""),
                        "vpc_id": vpc_id,
                        "vpc_name": vpc_name,
                        "ingress_rules": ingress_rules,
                        "egress_rules": egress_rules,
                        "tags": tags
                    })

        # Sort by creation time (most recent first) if available
        if details and "created_at" in details[0]:
            details.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        elif details and "launch_time" in details[0]:
            details.sort(key=lambda x: x.get("launch_time", ""), reverse=True)

        return {
            "success": True,
            "resource_type": resource_type,
            "count": len(details),
            "details": details,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        print(f"\u274c [AWS RESOURCE DETAILS] Error fetching details for {resource_type}: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to fetch resource details: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }
