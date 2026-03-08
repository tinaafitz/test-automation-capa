"""
Quick Fix Service
Provides executable quick fix commands for common ROSA/CAPI issues
"""

import subprocess
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class QuickFixService:
    """Service for executing quick fix commands"""

    def __init__(self):
        self.commands = {
            "force_cleanup_rosanetwork": self._force_cleanup_rosanetwork,
            "remove_finalizers": self._remove_finalizers,
            "restart_capi_controller": self._restart_capi_controller,
            "check_aws_cloudformation": self._check_aws_cloudformation,
            "force_delete_cluster": self._force_delete_cluster,
        }

    async def execute_command(
        self, command: str, parameters: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a quick fix command

        Args:
            command: The command identifier
            parameters: Command-specific parameters
            context: Current page and recent operations context

        Returns:
            Dict with success status, output, and error if applicable
        """
        logger.info(f"Executing quick fix command: {command} with parameters: {parameters}")

        if command not in self.commands:
            return {
                "success": False,
                "error": f"Unknown command: {command}",
                "output": "",
            }

        try:
            result = await self.commands[command](parameters, context)
            logger.info(f"Command {command} completed successfully")
            return {"success": True, "output": result, "error": None}
        except Exception as e:
            logger.error(f"Command {command} failed: {str(e)}")
            return {"success": False, "error": str(e), "output": ""}

    async def _force_cleanup_rosanetwork(
        self, parameters: Dict[str, Any], context: Dict[str, Any]
    ) -> str:
        """
        Force cleanup stuck ROSANetwork by removing finalizers

        Parameters:
            - cluster_name: Name of the cluster
            - namespace: Namespace (default: ns-rosa-hcp)
        """
        cluster_name = parameters.get("cluster_name")
        namespace = parameters.get("namespace", "ns-rosa-hcp")

        if not cluster_name:
            raise ValueError("cluster_name is required")

        # Remove finalizers from ROSANetwork
        cmd = [
            "oc",
            "patch",
            "rosanetwork",
            cluster_name,
            "-n",
            namespace,
            "--type=json",
            "-p=[{\"op\": \"remove\", \"path\": \"/metadata/finalizers\"}]",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            raise Exception(f"Failed to remove finalizers: {result.stderr}")

        return f"Successfully removed finalizers from ROSANetwork '{cluster_name}'"

    async def _remove_finalizers(
        self, parameters: Dict[str, Any], context: Dict[str, Any]
    ) -> str:
        """
        Remove finalizers from a specific resource

        Parameters:
            - resource_type: Type of resource (e.g., rosanetwork, rosacontrolplane)
            - resource_name: Name of the resource
            - namespace: Namespace
        """
        resource_type = parameters.get("resource_type")
        resource_name = parameters.get("resource_name")
        namespace = parameters.get("namespace", "ns-rosa-hcp")

        if not resource_type or not resource_name:
            raise ValueError("resource_type and resource_name are required")

        cmd = [
            "oc",
            "patch",
            resource_type,
            resource_name,
            "-n",
            namespace,
            "--type=json",
            "-p=[{\"op\": \"remove\", \"path\": \"/metadata/finalizers\"}]",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            raise Exception(f"Failed to remove finalizers: {result.stderr}")

        return f"Successfully removed finalizers from {resource_type} '{resource_name}'"

    async def _restart_capi_controller(
        self, parameters: Dict[str, Any], context: Dict[str, Any]
    ) -> str:
        """
        Restart the CAPI controller pod

        Parameters:
            - namespace: Namespace where CAPI controller is running (default: multicluster-engine)
        """
        namespace = parameters.get("namespace", "multicluster-engine")

        # Delete CAPI controller pod to force restart
        cmd = [
            "oc",
            "delete",
            "pod",
            "-n",
            namespace,
            "-l",
            "control-plane=capi-controller-manager",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            raise Exception(f"Failed to restart controller: {result.stderr}")

        return f"Successfully restarted CAPI controller in namespace '{namespace}'"

    async def _check_aws_cloudformation(
        self, parameters: Dict[str, Any], context: Dict[str, Any]
    ) -> str:
        """
        Check AWS CloudFormation stack status

        Parameters:
            - stack_name: CloudFormation stack name
            - region: AWS region (default: us-west-2)
        """
        stack_name = parameters.get("stack_name")
        region = parameters.get("region", "us-west-2")

        if not stack_name:
            raise ValueError("stack_name is required")

        cmd = [
            "aws",
            "cloudformation",
            "describe-stacks",
            "--stack-name",
            stack_name,
            "--region",
            region,
            "--query",
            "Stacks[0].[StackStatus,StackStatusReason]",
            "--output",
            "text",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            raise Exception(f"Failed to check CloudFormation stack: {result.stderr}")

        return f"CloudFormation stack '{stack_name}' status:\n{result.stdout}"

    async def _force_delete_cluster(
        self, parameters: Dict[str, Any], context: Dict[str, Any]
    ) -> str:
        """
        Force delete a cluster by removing all finalizers from all resources

        Parameters:
            - cluster_name: Name of the cluster
            - namespace: Namespace (default: ns-rosa-hcp)
        """
        cluster_name = parameters.get("cluster_name")
        namespace = parameters.get("namespace", "ns-rosa-hcp")

        if not cluster_name:
            raise ValueError("cluster_name is required")

        outputs = []

        # Remove finalizers from all related resources
        resources = [
            ("cluster", cluster_name),
            ("rosacontrolplane", cluster_name),
            ("rosanetwork", cluster_name),
            ("awscluster", cluster_name),
        ]

        for resource_type, resource_name in resources:
            cmd = [
                "oc",
                "patch",
                resource_type,
                resource_name,
                "-n",
                namespace,
                "--type=json",
                "-p=[{\"op\": \"remove\", \"path\": \"/metadata/finalizers\"}]",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                outputs.append(f"✓ Removed finalizers from {resource_type}")
            else:
                outputs.append(
                    f"✗ Failed to remove finalizers from {resource_type}: {result.stderr}"
                )

        return "\n".join(outputs)
