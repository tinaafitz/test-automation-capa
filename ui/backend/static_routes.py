"""
Static / reference-data service module — FastAPI router for lightweight endpoints
that return canned data or perform simple lookups.

Endpoints moved here from app.py:
  GET    /                           — root
  GET    /api/health                 — health check
  GET    /api/versions               — supported OpenShift versions
  GET    /api/templates              — cluster templates
  POST   /api/analyze-yaml           — YAML intent analysis
  GET    /api/onboarding/tour        — onboarding tour steps
  GET    /api/diagnostics/checks     — available diagnostic checks
  POST   /api/diagnostics/run        — run diagnostic checks
  GET    /api/environment/overview   — environment overview
  GET    /api/user/profile           — user profile
  GET    /api/build/templates        — build project templates
  POST   /api/validate               — validate cluster configuration

Also contains:
  _get_supported_versions_sync()    — helper for /api/versions
"""

import asyncio
import os
import subprocess
import sys
from datetime import datetime

import yaml
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


def _resolve(name: str):
    """Look up *name* via the app module so that unittest.mock.patch on
    ``app.<name>`` takes effect even though the endpoint lives here."""
    app_mod = sys.modules.get("app")
    if app_mod is not None:
        return getattr(app_mod, name)
    return globals()[name]


# ============================================================================
# Root & health
# ============================================================================

@router.get("/")
async def root():
    return {"message": "ROSA Automation API", "version": "1.0.0"}


@router.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now()}


# ============================================================================
# Versions
# ============================================================================

@router.get("/api/versions")
async def get_supported_versions(channel_group: str = "stable"):
    """Get supported OpenShift versions — offloads to thread pool."""
    return await asyncio.to_thread(_get_supported_versions_sync, channel_group)


def _get_supported_versions_sync(channel_group: str = "stable"):
    """Get supported OpenShift versions via OCM API with rosa CLI fallback."""
    allowed_groups = {"stable", "fast", "candidate", "eus", "nightly"}
    if channel_group not in allowed_groups:
        channel_group = "stable"

    _FALLBACK = {
        "success": True,
        "versions": ["4.21.0", "4.20.12", "4.20.11", "4.20.10", "4.20.8", "4.19.22", "4.19.21"],
        "default_version": "4.20.12",
        "latest_version": "4.21.0",
    }

    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from agents.ocm_client import get_ocm_client
        ocm = get_ocm_client()
        versions, err = ocm.list_versions(channel_group)

        if err or not versions:
            return _FALLBACK

        return {
            "success": True,
            "versions": versions,
            "default_version": versions[1] if len(versions) > 1 else versions[0],
            "latest_version": versions[0] if versions else "4.21.0",
        }
    except Exception as e:
        print(f"Error fetching ROSA versions: {e}")
        return _FALLBACK


# ============================================================================
# Templates
# ============================================================================

@router.get("/api/templates")
async def get_templates():
    """Get available cluster templates"""
    return {
        "success": True,
        "templates": [
            {
                "id": "rosa-network-basic",
                "name": "ROSA with Network Automation",
                "description": "Basic ROSA HCP cluster with automated VPC/subnet creation",
                "features": ["network_automation"],
                "version": "4.20",
            },
            {
                "id": "rosa-full-automation",
                "name": "ROSA Full Automation",
                "description": "ROSA HCP cluster with network and role automation",
                "features": ["network_automation", "role_automation"],
                "version": "4.20",
            },
        ]
    }


# ============================================================================
# YAML Analysis
# ============================================================================

@router.post("/api/analyze-yaml")
async def analyze_yaml(request: Request):
    """Analyze uploaded YAML to detect network and IAM configuration intent"""
    try:
        body = await request.json()
        yaml_content = body.get("yaml_content")

        if not yaml_content:
            raise HTTPException(status_code=400, detail="No YAML content provided")

        # Parse YAML documents
        documents = list(yaml.safe_load_all(yaml_content))

        # Initialize detection results
        has_rosa_network = False
        has_rosa_role_config = False
        has_manual_subnets = False
        has_manual_roles = False
        has_availability_zones = False

        rosa_control_plane = None

        # Analyze each document
        for doc in documents:
            if not doc:
                continue

            kind = doc.get("kind", "")

            # Check for ROSANetwork resource
            if kind == "ROSANetwork":
                has_rosa_network = True

            # Check for RosaRoleConfig resource
            if kind == "RosaRoleConfig":
                has_rosa_role_config = True

            # Check for ROSAControlPlane with manual configuration
            if kind == "ROSAControlPlane":
                rosa_control_plane = doc
                spec = doc.get("spec", {})

                # Check for manual network config
                if spec.get("subnets"):
                    has_manual_subnets = True
                if spec.get("availabilityZones"):
                    has_availability_zones = True

                # Check for manual IAM roles
                if spec.get("installerRoleARN") or spec.get("rolesRef"):
                    has_manual_roles = True

        # Determine intent
        network_intent = None
        role_intent = None

        if has_rosa_network:
            network_intent = "automated"
        elif has_manual_subnets and has_availability_zones:
            network_intent = "manual"

        if has_rosa_role_config:
            role_intent = "automated"
        elif has_manual_roles:
            role_intent = "manual"

        # Generate user-friendly messages
        messages = []

        if network_intent == "manual":
            messages.append(
                "✓ Detected manual network configuration: You've specified subnets and availability zones. These will be used for your cluster."
            )
        elif network_intent == "automated":
            messages.append(
                "✓ Detected ROSANetwork automation: VPC and subnets will be created automatically using CloudFormation."
            )

        if role_intent == "manual":
            messages.append(
                "✓ Detected manual IAM roles: You've specified custom IAM roles. These will be used for your cluster."
            )
        elif role_intent == "automated":
            messages.append(
                "✓ Detected RosaRoleConfig automation: IAM roles and OIDC provider will be created automatically."
            )

        # Extract configuration values if manual
        config_values = {}
        if rosa_control_plane and network_intent == "manual":
            spec = rosa_control_plane.get("spec", {})
            config_values["subnets"] = spec.get("subnets", [])
            config_values["availability_zones"] = spec.get("availabilityZones", [])

        if rosa_control_plane and role_intent == "manual":
            spec = rosa_control_plane.get("spec", {})
            config_values["installer_role_arn"] = spec.get("installerRoleARN")
            config_values["support_role_arn"] = spec.get("supportRoleARN")
            config_values["worker_role_arn"] = spec.get("workerRoleARN")
            config_values["oidc_id"] = spec.get("oidcID")

            roles_ref = spec.get("rolesRef", {})
            config_values["ingress_arn"] = roles_ref.get("ingressARN")
            config_values["image_registry_arn"] = roles_ref.get("imageRegistryARN")
            config_values["storage_arn"] = roles_ref.get("storageARN")
            config_values["network_arn"] = roles_ref.get("networkARN")
            config_values["kube_cloud_controller_arn"] = roles_ref.get("kubeCloudControllerARN")
            config_values["node_pool_management_arn"] = roles_ref.get("nodePoolManagementARN")
            config_values["control_plane_operator_arn"] = roles_ref.get("controlPlaneOperatorARN")
            config_values["kms_provider_arn"] = roles_ref.get("kmsProviderARN")

        return {
            "success": True,
            "network_intent": network_intent,
            "role_intent": role_intent,
            "messages": messages,
            "config_values": config_values,
            "has_rosa_control_plane": rosa_control_plane is not None,
        }

    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing YAML: {str(e)}")


# ============================================================================
# Onboarding
# ============================================================================

@router.get("/api/onboarding/tour")
async def get_onboarding_tour():
    """Get guided onboarding tour steps"""
    return {
        "success": True,
        "steps": [
            {
                "id": 1,
                "title": "Welcome to ROSA Automation",
                "content": "ROSA (Red Hat OpenShift Service on AWS) lets you run OpenShift clusters on AWS with full automation.",
                "duration": "2 minutes",
                "video_url": None,
            },
            {
                "id": 2,
                "title": "What You'll Need",
                "content": "To get started, you'll need an AWS account and the ROSA CLI installed.",
                "checklist": [
                    {"item": "AWS Account with appropriate permissions", "checked": False},
                    {"item": "ROSA CLI installed and authenticated", "checked": False},
                    {"item": "OpenShift Cluster Manager account", "checked": False},
                ],
            },
            {
                "id": 3,
                "title": "Automation Features",
                "content": "Our automation can handle network setup (VPCs, subnets) and AWS role configuration automatically.",
                "features": [
                    {
                        "name": "ROSANetwork (ACM-21174)",
                        "description": "Automated VPC and subnet creation",
                    },
                    {
                        "name": "ROSARoleConfig (ACM-21162)",
                        "description": "Automated AWS IAM role setup",
                    },
                ],
            },
        ]
    }


# ============================================================================
# Diagnostics
# ============================================================================

@router.get("/api/diagnostics/checks")
async def get_available_diagnostic_checks():
    """Get list of available diagnostic checks"""
    return {
        "success": True,
        "checks": [
            {
                "id": "aws_credentials",
                "name": "AWS Credentials",
                "description": "Verify AWS CLI configuration",
            },
            {
                "id": "rosa_auth",
                "name": "ROSA Authentication",
                "description": "Check ROSA CLI login status",
            },
            {
                "id": "openshift_version",
                "name": "OpenShift Version Support",
                "description": "Verify supported versions",
            },
            {
                "id": "network_connectivity",
                "name": "Network Connectivity",
                "description": "Test AWS API connectivity",
            },
            {
                "id": "permissions",
                "name": "IAM Permissions",
                "description": "Verify required AWS permissions",
            },
        ]
    }


@router.post("/api/diagnostics/run")
async def run_diagnostics(request: dict):
    """Run diagnostic checks"""
    checks_to_run = request.get("checks", [])

    # Run actual diagnostic checks
    results = []
    for check_id in checks_to_run:
        if check_id == "aws_credentials":
            # Mock AWS check for now
            results.append(
                {
                    "check": "aws_credentials",
                    "name": "AWS Credentials",
                    "status": "pass",
                    "message": "✅ AWS credentials are valid",
                    "details": "Account: 123456789012, Region: us-west-2",
                }
            )
        elif check_id == "rosa_auth":
            # Get actual ROSA status
            get_rosa_status = _resolve("get_rosa_status")
            rosa_status = await get_rosa_status()
            if rosa_status["authenticated"]:
                user_display = rosa_status.get("user_info", {}).get("aws_account_id", "Unknown")
                results.append(
                    {
                        "check": "rosa_auth",
                        "name": "ROSA Authentication",
                        "status": "pass",
                        "message": f"✅ ROSA CLI authenticated",
                        "details": f"Account: {user_display}",
                        "raw_output": rosa_status.get("raw_output", ""),
                    }
                )
            else:
                results.append(
                    {
                        "check": "rosa_auth",
                        "name": "ROSA Authentication",
                        "status": "fail",
                        "message": f"❌ {rosa_status['message']}",
                        "fix": rosa_status.get(
                            "suggestion",
                            "Run 'rosa login --env staging --use-auth-code' to authenticate",
                        ),
                        "command": rosa_status.get(
                            "fix_command", "rosa login --env staging --use-auth-code"
                        ),
                        "error": rosa_status.get("error", ""),
                    }
                )
        elif check_id == "openshift_version":
            results.append(
                {
                    "check": "openshift_version",
                    "name": "OpenShift Version Support",
                    "status": "pass",
                    "message": "✅ OpenShift 4.20 is supported",
                    "details": "Available versions: 4.18, 4.19, 4.20",
                }
            )

    return {"success": True, "results": results}


# ============================================================================
# Environment overview
# ============================================================================

@router.get("/api/environment/overview")
async def get_environment_overview():
    """Get comprehensive environment overview"""
    return {
        "success": True,
        "aws": {
            "account_id": "123456789012",
            "region": "us-west-2",
            "credentials_status": "valid",
            "last_verified": datetime.now().isoformat(),
        },
        "rosa": {
            "authenticated": True,
            "organization": "Red Hat",
            "subscription_status": "active",
            "console_url": "https://console.redhat.com/openshift",
        },
        "clusters": [
            {
                "name": "tfitzger-rosa-hcp-capi-test",
                "status": "error",
                "version": "4.18.9",
                "region": "us-west-2",
                "node_count": 0,
                "created": "2025-08-11T00:00:00Z",
                "error_message": "Cluster provisioning failed - check AWS permissions",
                "upgrade_available": "4.20.0",
                "automation_used": False,
            }
        ],
        "automation_status": {
            "network_automation_available": True,
            "role_automation_available": True,
            "templates_count": 2,
            "could_have_prevented_issues": True,
        },
        "recommendations": [
            "🚨 Your cluster 'tfitzger-rosa-hcp-capi-test' is in error state - run diagnostics",
            "⬆️ Consider upgrading from OpenShift 4.18.9 to 4.20.0 for better stability",
            "🔧 Use ROSANetwork automation to prevent networking issues in future clusters",
            "📋 Review our troubleshooting guide for cluster error resolution",
        ],
        "alerts": [
            {
                "type": "error",
                "message": "1 cluster in error state requires attention",
                "action": "Run diagnostics",
                "severity": "high",
            },
            {
                "type": "info",
                "message": "Automation features available to improve reliability",
                "action": "Learn about automation",
                "severity": "medium",
            },
        ],
    }


# ============================================================================
# User profile
# ============================================================================

@router.get("/api/user/profile")
async def get_user_profile():
    """Get user profile and permissions"""
    return {
        "success": True,
        "identity": {
            "username": "user@example.com",
            "account_id": "123456789012",
            "organization": "My Organization",
            "last_login": datetime.now().isoformat(),
        },
        "permissions": {
            "cluster_create": True,
            "cluster_delete": True,
            "network_manage": True,
            "role_manage": False,
            "admin_access": False,
        },
        "quotas": {
            "clusters": {"used": 2, "limit": 10},
            "vcpus": {"used": 12, "limit": 100},
            "storage": {"used": "500GB", "limit": "5TB"},
        },
        "recent_activity": [
            {"action": "Created cluster 'test-cluster'", "timestamp": "2024-01-16T10:00:00Z"},
            {"action": "Updated automation settings", "timestamp": "2024-01-15T15:30:00Z"},
            {"action": "Ran environment diagnostics", "timestamp": "2024-01-15T09:15:00Z"},
        ],
    }


# ============================================================================
# Build templates
# ============================================================================

@router.get("/api/build/templates")
async def get_build_templates():
    """Get project templates for building"""
    return {
        "success": True,
        "templates": [
            {
                "id": "development",
                "name": "Development Environment",
                "description": "Perfect for development and testing with cost optimization",
                "icon": "🧪",
                "specs": {
                    "instance_type": "m5.large",
                    "min_nodes": 1,
                    "max_nodes": 3,
                    "features": ["network_automation"],
                },
                "estimated_cost": "$200-400/month",
            },
            {
                "id": "production",
                "name": "Production Application",
                "description": "High availability setup for production workloads",
                "icon": "🚀",
                "specs": {
                    "instance_type": "m5.xlarge",
                    "min_nodes": 3,
                    "max_nodes": 10,
                    "features": ["network_automation", "role_automation"],
                },
                "estimated_cost": "$800-2000/month",
            },
            {
                "id": "learning",
                "name": "Learning & Testing",
                "description": "Minimal setup for learning OpenShift",
                "icon": "📚",
                "specs": {
                    "instance_type": "m5.large",
                    "min_nodes": 1,
                    "max_nodes": 2,
                    "features": ["network_automation"],
                },
                "estimated_cost": "$150-250/month",
            },
        ]
    }


# ============================================================================
# Validation
# ============================================================================

@router.post("/api/validate")
async def validate_config(request: Request):
    """Validate cluster configuration"""
    body = await request.json()

    # Extract fields matching ClusterConfig schema
    name = body.get("name", "")
    version = body.get("version", "4.20.0")
    min_replicas = body.get("min_replicas", 2)
    max_replicas = body.get("max_replicas", 3)

    errors = []
    warnings = []

    # Basic validation
    if not name.replace("-", "").isalnum():
        errors.append("Cluster name must contain only alphanumeric characters and hyphens")

    if len(name) > 15:
        warnings.append("Cluster name longer than 15 characters may cause issues")

    if min_replicas > max_replicas:
        errors.append("Min replicas cannot be greater than max replicas")

    # Version validation
    if not version.startswith("4.20"):
        warnings.append("Only OpenShift 4.20 is fully supported by this automation")

    return {"success": True, "valid": len(errors) == 0, "errors": errors, "warnings": warnings}
