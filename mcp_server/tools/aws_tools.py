"""AWS resource usage and detail tools."""

import json
import subprocess


def _aws_cmd(args, timeout=30):
    """Run an AWS CLI command and return parsed JSON or error string."""
    try:
        result = subprocess.run(
            ["aws"] + args + ["--output", "json"],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            return None, result.stderr.strip()
        return json.loads(result.stdout), None
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except Exception as e:
        return None, str(e)


def register_tools(mcp):

    @mcp.tool()
    def capa_aws_resource_usage() -> str:
        """Get counts of all AWS resources: VPCs, NAT gateways, CloudFormation stacks,
        security groups, IAM roles, EC2 instances, EBS volumes, Route53 zones,
        S3 buckets, load balancers, and instance profiles."""
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

    @mcp.tool()
    def capa_cloudformation_stack_status(stack_name: str, region: str = "us-west-2") -> str:
        """Get detailed status of a specific CloudFormation stack.

        Args:
            stack_name: CloudFormation stack name
            region: AWS region (default: us-west-2)
        """
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

        # Get outputs (VPC ID, subnet IDs, etc.)
        outputs = {}
        for o in stack.get("Outputs", []):
            outputs[o.get("OutputKey", "")] = o.get("OutputValue", "")
        if outputs:
            result["outputs"] = outputs

        # If DELETE_FAILED, get the blocking resources
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

    @mcp.tool()
    def capa_aws_resource_details(resource_type: str, region: str = "us-west-2") -> str:
        """Get detailed information about a specific type of AWS resource.

        Args:
            resource_type: One of: vpcs, nat_gateways, security_groups, ec2_instances,
                cloudformation_stacks, load_balancers, ebs_volumes
            region: AWS region (default: us-west-2)
        """
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
