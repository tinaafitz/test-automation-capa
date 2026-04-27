"""
ROSA HCP Remediation Agent
===========================

Domain-specific fix methods for ROSA HCP test automation.
Handles finalizer removal, CloudFormation retries, VPC cleanup, and more.
"""

import json
import subprocess
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

from ...remediation_agent import RemediationAgent


class RosaHcpRemediationAgent(RemediationAgent):
    """RemediationAgent with ROSA HCP-specific fix methods."""

    def __init__(self, base_dir: Path, enabled: bool = True, verbose: bool = False, dry_run: bool = False,
                 kb_dir: Path = None):
        if kb_dir is None:
            kb_dir = Path(__file__).parent / "knowledge_base"
        super().__init__(base_dir, enabled, verbose, dry_run, kb_dir=kb_dir)

    def _get_fix_method(self, fix_name: str):
        rosa_methods = {
            "remove_finalizers": self._fix_remove_finalizers,
            "refresh_ocm_token": self._fix_refresh_ocm_token,
            "backoff_and_retry": self._fix_backoff_retry,
            "cleanup_vpc_dependencies": self._fix_cleanup_vpc_dependencies,
            "manual_cloudformation_cleanup": self._fix_cloudformation_manual,
            "retry_cloudformation_delete": self._fix_retry_cloudformation_delete,
            "install_capi_capa": self._fix_install_capi,
            "increase_timeout_and_monitor": self._fix_increase_timeout,
            "create_and_link_ocm_role": self._fix_create_and_link_ocm_role,
            "fix_replica_az_mismatch": self._fix_replica_az_mismatch,
        }
        method = rosa_methods.get(fix_name)
        if method:
            return method
        return super()._get_fix_method(fix_name)

    def _fix_remove_finalizers(self, params: Dict) -> Tuple[bool, str]:
        resource_type = params.get("resource_type")
        resource_name = params.get("resource_name")
        namespace = params.get("namespace", "default")

        self.log(f"Removing finalizers from {resource_type}/{resource_name}", "info")

        try:
            cmd = [
                "oc", "patch", resource_type, resource_name,
                "-n", namespace,
                "--type=merge",
                "-p", '{"metadata":{"finalizers":null}}'
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                return True, f"Successfully removed finalizers from {resource_type}/{resource_name}"
            elif "NotFound" in result.stderr or "not found" in result.stderr.lower():
                return True, f"Resource {resource_type}/{resource_name} already deleted (no finalizer removal needed)"
            else:
                return False, f"Failed to remove finalizers: {result.stderr}"

        except subprocess.TimeoutExpired:
            return False, "Timeout while removing finalizers"
        except Exception as e:
            return False, f"Error removing finalizers: {str(e)}"

    def _fix_refresh_ocm_token(self, params: Dict) -> Tuple[bool, str]:
        self.log("Refreshing OCM token", "info")
        return False, "OCM token refresh requires manual intervention - credentials need to be updated"

    def _fix_create_and_link_ocm_role(self, params: Dict) -> Tuple[bool, str]:
        """Create and link OCM role using boto3 + OCM API."""
        import os
        self.log("Attempting to create/link OCM role", "info")

        ocm_client_id = os.environ.get("OCM_CLIENT_ID", "")
        ocm_client_secret = os.environ.get("OCM_CLIENT_SECRET", "")
        ocm_api_url = os.environ.get("OCM_API_URL", "https://api.stage.openshift.com")
        aws_account_id = os.environ.get("AWS_ACCOUNT_ID", "")

        if not ocm_client_id or not ocm_client_secret:
            if not ocm_client_id:
                try:
                    result = subprocess.run(
                        ["oc", "get", "secret", "rosa-creds-secret", "-n", "multicluster-engine",
                         "-o", "jsonpath={.data.ocmClientID}"],
                        capture_output=True, text=True, timeout=10,
                    )
                    if result.returncode == 0 and result.stdout:
                        import base64
                        ocm_client_id = base64.b64decode(result.stdout).decode()
                        result2 = subprocess.run(
                            ["oc", "get", "secret", "rosa-creds-secret", "-n", "multicluster-engine",
                             "-o", "jsonpath={.data.ocmClientSecret}"],
                            capture_output=True, text=True, timeout=10,
                        )
                        if result2.returncode == 0 and result2.stdout:
                            ocm_client_secret = base64.b64decode(result2.stdout).decode()
                except Exception:
                    pass

        if not ocm_client_id or not ocm_client_secret:
            return False, "OCM credentials not available (set OCM_CLIENT_ID/OCM_CLIENT_SECRET or ensure rosa-creds-secret exists)"

        try:
            from .ocm_role_manager import OcmRoleManager
            mgr = OcmRoleManager(
                ocm_client_id=ocm_client_id,
                ocm_client_secret=ocm_client_secret,
                ocm_api_url=ocm_api_url,
                aws_account_id=aws_account_id,
                dry_run=self.dry_run,
            )
            return mgr.ensure_ocm_role()
        except Exception as e:
            return False, f"OCM role creation failed: {e}"

    def _fix_backoff_retry(self, params: Dict) -> Tuple[bool, str]:
        backoff_seconds = params.get("backoff_seconds", 60)
        max_retries = params.get("max_retries", 3)

        self.log(f"Rate limit detected: recommend {backoff_seconds}s backoff before retry", "info")
        return True, f"Rate limit advisory: wait {backoff_seconds}s before retrying (max {max_retries} retries)"

    def _fix_cleanup_vpc_dependencies(self, params: Dict) -> Tuple[bool, str]:
        vpc_id = params.get("vpc_id")
        cluster_id = params.get("cluster_id")
        region = params.get("region", "us-west-2")

        if not vpc_id:
            return False, "VPC ID is required for cleanup"

        if not cluster_id:
            return False, "Cluster ID is required for cleanup (to prevent deleting resources from other clusters in shared VPCs)"

        self.log(f"Cleaning up VPC dependencies for {vpc_id} in {region}", "info")
        self.log(f"Filtering resources by cluster ID: {cluster_id}", "info")

        outputs = []
        cleanup_count = 0
        sg_cleanup_count = 0

        try:
            self.log("Searching for orphaned ENIs...", "info")
            cmd = [
                "aws", "ec2", "describe-network-interfaces",
                "--region", region,
                "--filters",
                f"Name=vpc-id,Values={vpc_id}",
                f"Name=tag:cluster.x-k8s.io/cluster-name,Values={cluster_id}",
                "--query", "NetworkInterfaces[*].[NetworkInterfaceId,Attachment.AttachmentId,Status,Description]",
                "--output", "text"
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0 and result.stdout.strip():
                enis = result.stdout.strip().split('\n')
                outputs.append(f"Found {len(enis)} ENI(s) in VPC")

                for eni_line in enis:
                    parts = eni_line.split('\t')
                    if len(parts) >= 3:
                        eni_id = parts[0]
                        attachment_id = parts[1] if len(parts) > 1 else None
                        status = parts[2] if len(parts) > 2 else "unknown"
                        description = parts[3] if len(parts) > 3 else ""

                        if "lambda" in description.lower() or "rds" in description.lower():
                            outputs.append(f"  Skipping {eni_id}: {description} (managed service)")
                            continue

                        if attachment_id and attachment_id != "None":
                            detach_cmd = [
                                "aws", "ec2", "detach-network-interface",
                                "--region", region,
                                "--attachment-id", attachment_id,
                                "--force"
                            ]
                            detach_result = subprocess.run(detach_cmd, capture_output=True, text=True, timeout=30)
                            if detach_result.returncode == 0:
                                outputs.append(f"  Detached ENI {eni_id}")
                                time.sleep(2)

                        if status == "available" or attachment_id == "None":
                            delete_cmd = [
                                "aws", "ec2", "delete-network-interface",
                                "--region", region,
                                "--network-interface-id", eni_id
                            ]
                            delete_result = subprocess.run(delete_cmd, capture_output=True, text=True, timeout=30)
                            if delete_result.returncode == 0:
                                outputs.append(f"  Deleted ENI {eni_id}")
                                cleanup_count += 1
                            else:
                                outputs.append(f"  FAILED to delete ENI {eni_id}: {delete_result.stderr}")
            else:
                outputs.append("No orphaned ENIs found")

            self.log("Checking security groups...", "info")

            sg_filters = [
                f"Name=vpc-id,Values={vpc_id}",
                f"Name=tag:red-hat-clustertype,Values={cluster_id}"
            ]

            sg_cmd = [
                "aws", "ec2", "describe-security-groups",
                "--region", region,
                "--filters"
            ] + sg_filters + [
                "--query", "SecurityGroups[?GroupName!='default'].[GroupId,GroupName,Tags]",
                "--output", "json"
            ]

            sg_result = subprocess.run(sg_cmd, capture_output=True, text=True, timeout=30)

            if sg_result.returncode == 0 and sg_result.stdout.strip():
                sgs = json.loads(sg_result.stdout)

                if sgs:
                    outputs.append(f"Found {len(sgs)} security group(s) for cluster {cluster_id}")

                    for sg_data in sgs:
                        sg_id = sg_data[0]
                        sg_name = sg_data[1]

                        delete_sg_cmd = [
                            "aws", "ec2", "delete-security-group",
                            "--region", region,
                            "--group-id", sg_id
                        ]

                        delete_sg_result = subprocess.run(delete_sg_cmd, capture_output=True, text=True, timeout=30)
                        if delete_sg_result.returncode == 0:
                            outputs.append(f"  Deleted security group {sg_id} ({sg_name})")
                            sg_cleanup_count += 1
                        else:
                            error_msg = delete_sg_result.stderr.strip()
                            if "DependencyViolation" in error_msg:
                                outputs.append(f"  SKIPPED security group {sg_id} ({sg_name}) has dependencies, will be cleaned by CloudFormation")
                            else:
                                outputs.append(f"  FAILED to delete security group {sg_id}: {error_msg}")
                else:
                    outputs.append("No security groups found matching criteria")
            else:
                outputs.append("No security groups found")

            summary = f"VPC cleanup completed: {cleanup_count} ENI(s) removed, {sg_cleanup_count} security group(s) deleted"
            full_output = "\n".join(outputs)

            self.log(summary, "success" if cleanup_count > 0 else "info")

            return True, f"{summary}\n\nDetails:\n{full_output}"

        except subprocess.TimeoutExpired:
            return False, "Timeout while cleaning up VPC dependencies"
        except Exception as e:
            return False, f"Error during VPC cleanup: {str(e)}"

    def _fix_cloudformation_manual(self, params: Dict) -> Tuple[bool, str]:
        self.log("CloudFormation issue requires manual cleanup", "warning")

        message = params.get("message", "CloudFormation stack requires manual inspection")
        self.log(f"MANUAL INTERVENTION REQUIRED: {message}", "warning")
        return True, f"Logged for manual review: {message}"

    def _fix_retry_cloudformation_delete(self, params: Dict) -> Tuple[bool, str]:
        stack_name = params.get("stack_name")
        region = params.get("region", "us-west-2")

        if not stack_name:
            return False, "Stack name is required for CloudFormation retry"

        self.log(f"Retrying CloudFormation stack deletion: {stack_name}", "info")

        try:
            status_cmd = [
                "aws", "cloudformation", "describe-stacks",
                "--stack-name", stack_name,
                "--region", region,
                "--query", "Stacks[0].StackStatus",
                "--output", "text"
            ]
            status_result = subprocess.run(status_cmd, capture_output=True, text=True, timeout=10)

            if status_result.returncode != 0:
                if "does not exist" in status_result.stderr:
                    return True, f"CloudFormation stack {stack_name} already deleted"
                return False, f"Failed to check stack status: {status_result.stderr}"

            stack_status = status_result.stdout.strip()

            if stack_status not in ("DELETE_IN_PROGRESS", "DELETE_FAILED"):
                return False, f"Stack {stack_name} in unexpected state: {stack_status}"

            cleanup_details = []
            cleanup_errors = []

            vpc_cmd = [
                "aws", "cloudformation", "list-stack-resources",
                "--stack-name", stack_name,
                "--region", region,
                "--query", "StackResourceSummaries[?ResourceType=='AWS::EC2::VPC'].PhysicalResourceId",
                "--output", "text"
            ]
            vpc_result = subprocess.run(vpc_cmd, capture_output=True, text=True, timeout=10)
            vpc_id = vpc_result.stdout.strip() if vpc_result.returncode == 0 else None

            if vpc_id and vpc_id.startswith("vpc-"):
                self.log(f"Cleaning up VPC {vpc_id} dependencies before retry", "info")

                vpce_cmd = [
                    "aws", "ec2", "describe-vpc-endpoints",
                    "--region", region,
                    "--filters", f"Name=vpc-id,Values={vpc_id}",
                    "--query", "VpcEndpoints[*].VpcEndpointId",
                    "--output", "text"
                ]
                vpce_result = subprocess.run(vpce_cmd, capture_output=True, text=True, timeout=10)
                if vpce_result.returncode == 0 and vpce_result.stdout.strip():
                    vpce_ids = [v for v in vpce_result.stdout.strip().split() if v.startswith("vpce-")]
                    if vpce_ids:
                        self.log(f"Deleting {len(vpce_ids)} VPC endpoint(s)", "info")
                        del_vpce = subprocess.run([
                            "aws", "ec2", "delete-vpc-endpoints",
                            "--region", region,
                            "--vpc-endpoint-ids", *vpce_ids
                        ], capture_output=True, text=True, timeout=60)
                        if del_vpce.returncode == 0:
                            cleanup_details.append(f"Deleted {len(vpce_ids)} VPC endpoint(s)")
                        else:
                            cleanup_errors.append(f"Failed to delete VPC endpoints: {del_vpce.stderr.strip()}")
                        self.log("Waiting 20s for ENIs to release after VPC endpoint deletion", "info")
                        time.sleep(20)

                eni_cmd = [
                    "aws", "ec2", "describe-network-interfaces",
                    "--region", region,
                    "--filters", f"Name=vpc-id,Values={vpc_id}",
                    "--query", "NetworkInterfaces[*].[NetworkInterfaceId,Attachment.AttachmentId,Status]",
                    "--output", "text"
                ]
                eni_result = subprocess.run(eni_cmd, capture_output=True, text=True, timeout=10)
                if eni_result.returncode == 0 and eni_result.stdout.strip():
                    for line in eni_result.stdout.strip().split('\n'):
                        parts = line.split('\t')
                        if len(parts) >= 1:
                            eni_id = parts[0]
                            attachment_id = parts[1] if len(parts) > 1 and parts[1] != "None" else None
                            if attachment_id:
                                detach_r = subprocess.run([
                                    "aws", "ec2", "detach-network-interface",
                                    "--region", region,
                                    "--attachment-id", attachment_id, "--force"
                                ], capture_output=True, text=True, timeout=10)
                                if detach_r.returncode != 0:
                                    cleanup_errors.append(f"Failed to detach ENI {eni_id}: {detach_r.stderr.strip()}")
                                time.sleep(2)
                            del_eni_r = subprocess.run([
                                "aws", "ec2", "delete-network-interface",
                                "--region", region,
                                "--network-interface-id", eni_id
                            ], capture_output=True, text=True, timeout=10)
                            if del_eni_r.returncode == 0:
                                cleanup_details.append(f"Deleted ENI {eni_id}")
                            else:
                                cleanup_errors.append(f"Failed to delete ENI {eni_id}: {del_eni_r.stderr.strip()}")

                sg_cmd = [
                    "aws", "ec2", "describe-security-groups",
                    "--region", region,
                    "--filters", f"Name=vpc-id,Values={vpc_id}",
                    "--query", "SecurityGroups[?GroupName!='default'].[GroupId,GroupName]",
                    "--output", "text"
                ]
                sg_result = subprocess.run(sg_cmd, capture_output=True, text=True, timeout=10)
                if sg_result.returncode == 0 and sg_result.stdout.strip():
                    for line in sg_result.stdout.strip().split('\n'):
                        parts = line.split('\t')
                        if len(parts) >= 1:
                            sg_id = parts[0]
                            sg_name = parts[1] if len(parts) > 1 else "unknown"
                            del_result = subprocess.run([
                                "aws", "ec2", "delete-security-group",
                                "--region", region,
                                "--group-id", sg_id
                            ], capture_output=True, text=True, timeout=10)
                            if del_result.returncode == 0:
                                cleanup_details.append(f"Deleted security group {sg_id} ({sg_name})")
                                self.log(f"Deleted orphaned security group {sg_id} ({sg_name})", "info")
                            else:
                                cleanup_errors.append(f"Failed to delete SG {sg_id}: {del_result.stderr.strip()}")

                subnet_cmd = [
                    "aws", "ec2", "describe-subnets",
                    "--region", region,
                    "--filters", f"Name=vpc-id,Values={vpc_id}",
                    "--query", "Subnets[*].SubnetId",
                    "--output", "text"
                ]
                subnet_result = subprocess.run(subnet_cmd, capture_output=True, text=True, timeout=10)
                if subnet_result.returncode == 0 and subnet_result.stdout.strip():
                    for subnet_id in subnet_result.stdout.strip().split('\t'):
                        del_sub_r = subprocess.run([
                            "aws", "ec2", "delete-subnet",
                            "--region", region,
                            "--subnet-id", subnet_id
                        ], capture_output=True, text=True, timeout=10)
                        if del_sub_r.returncode == 0:
                            cleanup_details.append(f"Deleted subnet {subnet_id}")
                        else:
                            cleanup_errors.append(f"Failed to delete subnet {subnet_id}: {del_sub_r.stderr.strip()}")

                igw_cmd = [
                    "aws", "ec2", "describe-internet-gateways",
                    "--region", region,
                    "--filters", f"Name=attachment.vpc-id,Values={vpc_id}",
                    "--query", "InternetGateways[*].InternetGatewayId",
                    "--output", "text"
                ]
                igw_result = subprocess.run(igw_cmd, capture_output=True, text=True, timeout=10)
                if igw_result.returncode == 0 and igw_result.stdout.strip():
                    for igw_id in igw_result.stdout.strip().split('\t'):
                        subprocess.run([
                            "aws", "ec2", "detach-internet-gateway",
                            "--region", region,
                            "--internet-gateway-id", igw_id,
                            "--vpc-id", vpc_id
                        ], capture_output=True, text=True, timeout=10)
                        del_igw_r = subprocess.run([
                            "aws", "ec2", "delete-internet-gateway",
                            "--region", region,
                            "--internet-gateway-id", igw_id
                        ], capture_output=True, text=True, timeout=10)
                        if del_igw_r.returncode == 0:
                            cleanup_details.append(f"Deleted internet gateway {igw_id}")
                        else:
                            cleanup_errors.append(f"Failed to delete IGW {igw_id}: {del_igw_r.stderr.strip()}")

                if cleanup_details:
                    self.log(f"VPC cleanup: {'; '.join(cleanup_details)}", "info")
                if cleanup_errors:
                    self.log(f"VPC cleanup errors: {'; '.join(cleanup_errors)}", "warning")

            if stack_status == "DELETE_FAILED":
                delete_cmd = [
                    "aws", "cloudformation", "delete-stack",
                    "--stack-name", stack_name,
                    "--region", region
                ]
                delete_result = subprocess.run(delete_cmd, capture_output=True, text=True, timeout=10)

                if delete_result.returncode != 0:
                    return False, f"Failed to retry stack deletion: {delete_result.stderr}"

                time.sleep(5)
                recheck = subprocess.run(status_cmd, capture_output=True, text=True, timeout=10)
                if recheck.returncode == 0 and "DELETE_FAILED" in recheck.stdout:
                    self.log(f"Stack {stack_name} immediately re-entered DELETE_FAILED after retry", "warning")
                    return False, f"Stack {stack_name} re-entered DELETE_FAILED — dependencies may still exist"

            cleanup_summary = f"; {'; '.join(cleanup_details)}" if cleanup_details else ""
            return True, f"Cleaned up VPC dependencies for {stack_name}{cleanup_summary}"

        except subprocess.TimeoutExpired:
            return False, "Timeout during CloudFormation retry"
        except Exception as e:
            return False, f"Error retrying CloudFormation delete: {str(e)}"

    def _fix_install_capi(self, params: Dict) -> Tuple[bool, str]:
        self.log("CAPI/CAPA installation check/fix", "info")

        capi_installed = params.get("capi_installed", False)
        capa_installed = params.get("capa_installed", False)

        if not capi_installed and not capa_installed:
            return False, "CAPI/CAPA not installed - requires manual installation via test suite 10-configure-mce-environment"
        elif not capi_installed:
            return False, "CAPI controller not found - check capi-system namespace"
        elif not capa_installed:
            return False, "CAPA controller not found - check capa-system namespace"

        return True, "CAPI/CAPA installation verified"

    def _fix_increase_timeout(self, params: Dict) -> Tuple[bool, str]:
        suggested_increase = params.get("suggested_timeout_increase", "2x")

        self.log(f"Timeout issue detected - suggest increasing timeout by {suggested_increase}", "warning")
        return True, f"Recommend increasing timeout by {suggested_increase} for this operation"

    def _fix_replica_az_mismatch(self, params: Dict) -> Tuple[bool, str]:
        """Fix replica/AZ mismatch by patching MachinePool and RosaControlPlane replicas to match AZ count."""
        cluster_name = params.get("resource_name") or params.get("cluster_name", "")
        namespace = params.get("namespace", "default")

        if not cluster_name:
            return False, "Cluster name required to fix replica/AZ mismatch"

        self.log(f"Fixing replica/AZ mismatch for {cluster_name}", "info")

        try:
            az_cmd = [
                "oc", "get", "rosacontrolplane", cluster_name, "-n", namespace,
                "-o", "jsonpath={.spec.availabilityZones}",
            ]
            result = subprocess.run(az_cmd, capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                return False, f"Could not read AZ config: {result.stderr}"

            import json as _json
            try:
                az_list = _json.loads(result.stdout)
                az_count = len(az_list)
            except (ValueError, TypeError):
                az_raw = result.stdout.strip().strip("[]")
                az_count = len([a for a in az_raw.split(",") if a.strip()]) if az_raw else 1

            if az_count < 1:
                az_count = 1

            self.log(f"Detected {az_count} AZs, setting replicas accordingly", "info")

            if self.dry_run:
                return True, f"[DRY RUN] Would patch replicas to {az_count} (AZ count) for {cluster_name}"

            rcp_patch = _json.dumps({
                "spec": {
                    "defaultMachinePoolSpec": {
                        "autoscaling": {
                            "minReplicas": az_count,
                            "maxReplicas": az_count * 2,
                        }
                    }
                }
            })
            rcp_cmd = [
                "oc", "patch", "rosacontrolplane", cluster_name, "-n", namespace,
                "--type=merge", "-p", rcp_patch,
            ]
            rcp_result = subprocess.run(rcp_cmd, capture_output=True, text=True, timeout=15)

            mp_patch = _json.dumps({"spec": {"replicas": az_count}})
            mp_cmd = [
                "oc", "patch", "machinepool", cluster_name, "-n", namespace,
                "--type=merge", "-p", mp_patch,
            ]
            mp_result = subprocess.run(mp_cmd, capture_output=True, text=True, timeout=15)

            patched = []
            if rcp_result.returncode == 0:
                patched.append(f"RosaControlPlane minReplicas={az_count}")
            if mp_result.returncode == 0:
                patched.append(f"MachinePool replicas={az_count}")

            if patched:
                return True, f"Fixed replica/AZ mismatch: {', '.join(patched)}"
            return False, f"Patch failed: RCP={rcp_result.stderr}, MP={mp_result.stderr}"

        except subprocess.TimeoutExpired:
            return False, "Timed out patching replicas"
        except Exception as e:
            return False, f"Error fixing replica/AZ mismatch: {e}"
