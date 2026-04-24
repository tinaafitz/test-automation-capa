"""Diagnostic tools that reuse the CAPA agent framework."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

VALID_ISSUE_TYPES = [
    "rosanetwork_stuck_deletion",
    "rosacontrolplane_stuck_deletion",
    "rosaroleconfig_stuck_deletion",
    "cloudformation_deletion_failure",
    "ocm_auth_failure",
    "capi_not_installed",
]


def register_tools(mcp):

    @mcp.tool()
    def capa_diagnose_issue(
        issue_type: str,
        resource_name: str,
        namespace: str = "ns-rosa-hcp",
    ) -> str:
        """Run the CAPA diagnostic pipeline for a specific cluster issue.
        Returns root cause analysis, confidence score, evidence, and recommended fix.

        Args:
            issue_type: One of: rosanetwork_stuck_deletion,
                rosacontrolplane_stuck_deletion, rosaroleconfig_stuck_deletion,
                cloudformation_deletion_failure, ocm_auth_failure, capi_not_installed
            resource_name: K8s resource name (e.g., 'moo-rosa-hcp-network')
            namespace: K8s namespace (default: ns-rosa-hcp)
        """
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
