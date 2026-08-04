"""
MCE Features routes -- FastAPI router for MCE feature inspection endpoints.

Endpoints moved here from app.py:
  GET    /api/mce/features
  GET    /api/mce/yaml
  GET    /api/mce/resources

Also contains:
  _get_mce_features_sync  -- sync helper that shells out to ``oc`` for MCE data
"""

import asyncio
import json
import subprocess
import sys

from fastapi import APIRouter, HTTPException

router = APIRouter()


def _resolve(name: str):
    """Look up *name* via the app module so that unittest.mock.patch on
    ``app.<name>`` takes effect even though the endpoint lives here."""
    app_mod = sys.modules.get("app")
    if app_mod is not None:
        return getattr(app_mod, name)
    return globals()[name]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_mce_features_sync():
    """Get all MCE features and their enablement status (sync)."""
    try:
        # Run oc command to get MCE resource
        result = subprocess.run(
            ["oc", "get", "mce", "-o", "json"], capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Failed to get MCE: {result.stderr}")

        mce_data = json.loads(result.stdout)

        features = []
        mce_info = None

        # Parse MCE components
        if mce_data.get("items") and len(mce_data["items"]) > 0:
            mce = mce_data["items"][0]

            # Extract MCE info separately (not in features list)
            mce_status = mce.get("status", {}).get("phase", "Unknown")
            mce_name = mce.get("metadata", {}).get("name", "multiclusterengine")
            mce_version = mce.get("status", {}).get("currentVersion", "Unknown")

            # Check for CRD availability
            rosa_network_crd_available = False
            rosa_role_config_crd_available = False

            try:
                # Check for ROSANetwork CRD
                crd_check = subprocess.run(
                    ["oc", "get", "crd", "rosanetworks.infrastructure.cluster.x-k8s.io"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                rosa_network_crd_available = crd_check.returncode == 0

                # Check for ROSARoleConfig CRD (might be named differently)
                # Try both possible CRD names
                for crd_name in [
                    "rosaroleconfigs.infrastructure.cluster.x-k8s.io",
                    "rosaroles.infrastructure.cluster.x-k8s.io",
                ]:
                    crd_check = subprocess.run(
                        ["oc", "get", "crd", crd_name], capture_output=True, text=True, timeout=10
                    )
                    if crd_check.returncode == 0:
                        rosa_role_config_crd_available = True
                        break
            except Exception as e:
                # If CRD check fails, assume CRDs not available
                print(f"CRD check failed: {e}")

            ocp_version = ""
            try:
                ocp_result = subprocess.run(
                    ["oc", "get", "clusterversion", "version",
                     "-o", "jsonpath={.status.desired.version}"],
                    capture_output=True, text=True, timeout=10,
                )
                if ocp_result.returncode == 0:
                    ocp_version = ocp_result.stdout.strip()
            except Exception:
                pass

            mce_info = {
                "name": mce_name,
                "version": mce_version,
                "status": mce_status,
                "available": mce_status == "Available",
                "ocpVersion": ocp_version,
                "capabilities": {
                    "rosaNetworkCrd": rosa_network_crd_available,
                    "rosaRoleConfigCrd": rosa_role_config_crd_available,
                },
            }

            components = mce.get("spec", {}).get("overrides", {}).get("components", [])

            # Feature descriptions
            feature_descriptions = {
                "cluster-api": "Core Cluster API for cluster lifecycle management",
                "cluster-api-provider-aws": "AWS infrastructure provider for Cluster API",
                "hypershift": "HyperShift operator for hosted control planes",
                "hypershift-local-hosting": "Local hosting support for HyperShift",
                "managedserviceaccount": "Managed service account addon",
                "managedserviceaccount-preview": "Preview features for managed service accounts",
                "console-mce": "Multicluster Engine console plugin",
                "discovery": "Cluster discovery service",
                "hive": "Hive operator for cluster provisioning",
                "assisted-service": "Assisted installer service",
                "cluster-lifecycle": "Cluster lifecycle management",
                "cluster-manager": "Cluster manager service",
                "clusterproxy-addon": "Cluster proxy addon",
                "search-v2": "Search v2 service for cluster indexing",
            }

            for component in components:
                name = component.get("name", "Unknown")
                enabled = component.get("enabled", False)

                features.append(
                    {
                        "name": name,
                        "enabled": enabled,
                        "description": feature_descriptions.get(name, ""),
                        "version": mce_version if enabled else None,
                    }
                )

        return {"success": True, "features": features, "count": len(features), "mce_info": mce_info}

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Request to OpenShift timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching MCE features: {str(e)}")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/mce/features")
async def get_mce_features():
    """Get all MCE features -- offloads to thread pool."""
    return await asyncio.to_thread(_resolve("_get_mce_features_sync"))


@router.get("/api/mce/yaml")
async def get_mce_yaml():
    """Get the YAML for the MultiClusterEngine resource"""
    try:
        # Fetch the MultiClusterEngine resource YAML
        result = subprocess.run(
            ["oc", "get", "multiclusterengine", "-o", "yaml"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return {
                "success": False,
                "yaml": None,
                "message": f"Error fetching MCE YAML: {result.stderr}",
            }

        return {
            "success": True,
            "yaml": result.stdout,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "yaml": None,
            "message": "Request to OpenShift timed out",
        }
    except Exception as e:
        import traceback

        print(f"\u274c [MCE-YAML] Error: {str(e)}")
        print(traceback.format_exc())
        return {
            "success": False,
            "yaml": None,
            "message": f"Error fetching MCE YAML: {str(e)}",
        }


@router.get("/api/mce/resources")
async def get_mce_resources():
    """Get CAPI/CAPA resources from the MCE environment"""
    try:
        resources = []

        # Define resource types to fetch
        resource_types = [
            # Skip Deployment for now as it's slow and not critical for resource display
            # {
            #     "type": "Deployment",
            #     "namespaces": ["capi-system", "capa-system", "multicluster-engine"],
            # },
            {"type": "AWSClusterControllerIdentity", "namespaces": ["capa-system"]},
            {"type": "ROSACluster", "namespaces": None},  # All namespaces
            {"type": "ROSANetwork", "namespaces": None},  # All namespaces
            {"type": "ROSAControlPlane", "namespaces": None},  # All namespaces
            {"type": "ROSARoleConfig", "namespaces": None},  # All namespaces
        ]

        for resource_config in resource_types:
            resource_type = resource_config["type"]
            namespaces = resource_config["namespaces"]

            try:
                if namespaces:
                    # Fetch from specific namespaces
                    for namespace in namespaces:
                        result = subprocess.run(
                            ["oc", "get", resource_type.lower(), "-n", namespace, "-o", "json"],
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )

                        if result.returncode == 0:
                            data = json.loads(result.stdout)
                            for item in data.get("items", []):
                                metadata = item.get("metadata", {})
                                resource_name = metadata.get("name", "unknown")

                                # Get YAML for this resource
                                yaml_result = subprocess.run(
                                    [
                                        "oc",
                                        "get",
                                        resource_type.lower(),
                                        resource_name,
                                        "-n",
                                        namespace,
                                        "-o",
                                        "yaml",
                                    ],
                                    capture_output=True,
                                    text=True,
                                    timeout=10,
                                )

                                yaml_content = (
                                    yaml_result.stdout if yaml_result.returncode == 0 else None
                                )

                                resources.append(
                                    {
                                        "name": resource_name,
                                        "type": resource_type,
                                        "namespace": metadata.get("namespace", namespace),
                                        "status": "Active",
                                        "yaml": yaml_content,
                                    }
                                )
                else:
                    # Fetch from all namespaces
                    result = subprocess.run(
                        ["oc", "get", resource_type.lower(), "--all-namespaces", "-o", "json"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )

                    if result.returncode == 0:
                        data = json.loads(result.stdout)
                        for item in data.get("items", []):
                            metadata = item.get("metadata", {})
                            resource_name = metadata.get("name", "unknown")
                            resource_namespace = metadata.get("namespace", "default")

                            # Get YAML for this resource
                            yaml_result = subprocess.run(
                                [
                                    "oc",
                                    "get",
                                    resource_type.lower(),
                                    resource_name,
                                    "-n",
                                    resource_namespace,
                                    "-o",
                                    "yaml",
                                ],
                                capture_output=True,
                                text=True,
                                timeout=10,
                            )

                            yaml_content = (
                                yaml_result.stdout if yaml_result.returncode == 0 else None
                            )

                            resources.append(
                                {
                                    "name": resource_name,
                                    "type": resource_type,
                                    "namespace": resource_namespace,
                                    "status": "Active",
                                    "yaml": yaml_content,
                                }
                            )

            except Exception as e:
                # Log but don't fail if one resource type fails
                print(f"Failed to fetch {resource_type}: {str(e)}")
                continue

        return {"success": True, "resources": resources, "count": len(resources)}

    except Exception as e:
        return {
            "success": False,
            "message": f"Error fetching MCE resources: {str(e)}",
            "resources": [],
        }
