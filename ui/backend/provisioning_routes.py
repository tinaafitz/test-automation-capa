"""
Provisioning routes -- FastAPI router for YAML generation and application
for ROSA HCP cluster provisioning.

Endpoints moved here from app.py:
  POST   /api/provisioning/generate-yaml
  POST   /api/provisioning/apply-yaml
"""

import asyncio
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request

from shared_state import jobs
from jobs_service import get_agent_stats
from agents_service import init_ai_agents
from notification_routes import send_cluster_notifications

router = APIRouter()


def _resolve(name: str):
    """Look up *name* via the app module so that unittest.mock.patch on
    ``app.<name>`` takes effect even though the endpoint lives here."""
    app_mod = sys.modules.get("app")
    if app_mod is not None:
        return getattr(app_mod, name)
    return globals()[name]


# MCE features routes (get_mce_features, get_mce_yaml) — extracted to mce_features_routes.py




@router.post("/api/provisioning/generate-yaml")
async def generate_provisioning_yaml(request: Request):
    """Generate provisioning YAML without applying it (preview mode) - Direct Jinja2 rendering"""
    try:
        body = await request.json()
        config = body.get("config", {})

        # Extract configuration
        cluster_name = config.get("clusterName")
        openshift_version = config.get("openShiftVersion", "4.20.10")
        create_rosa_network = config.get("createRosaNetwork", True)
        create_rosa_roles = config.get("createRosaRoleConfig", True)
        vpc_cidr_block = config.get("vpcCidrBlock", "10.0.0.0/16")
        availability_zone_count = config.get("availabilityZoneCount", 1)
        role_prefix = config.get("rolePrefix", cluster_name)
        domain_prefix = config.get("domainPrefix", "")
        channel_group = config.get("channelGroup", "")
        channel = config.get("channel", "")
        aws_region = config.get("awsRegion", "us-west-2")

        # Extract node pool configuration
        node_pool_name = config.get("nodePoolName", "")

        # Extract log forwarding configuration
        enable_log_forwarding = config.get("enableLogForwarding", False)
        log_forward_applications = config.get(
            "logForwardApplications", ["application", "infrastructure"]
        )
        log_forward_cloudwatch_role_arn = config.get("logForwardCloudWatchRoleArn", "")
        log_forward_cloudwatch_log_group = config.get("logForwardCloudWatchLogGroup", "")
        log_forward_s3_bucket = config.get("logForwardS3Bucket", "")
        log_forward_s3_prefix = config.get("logForwardS3Prefix", "")

        # Extract FIPS configuration (OpenShift 4.21+ only)
        enable_fips = config.get("fips", False)
        print(f"🔍 [FIPS] Extracted FIPS value: {enable_fips}")

        # Extract manual configuration (for environments without ROSANetwork/ROSARoleConfig CRDs)
        manual_public_subnet = config.get("manualPublicSubnet", "")
        manual_private_subnet = config.get("manualPrivateSubnet", "")
        manual_vpc_id = config.get("manualVpcId", "")
        manual_installer_role_arn = config.get("manualInstallerRoleArn", "")
        manual_support_role_arn = config.get("manualSupportRoleArn", "")
        manual_worker_role_arn = config.get("manualWorkerRoleArn", "")
        manual_control_plane_operator_role_arn = config.get("manualControlPlaneOperatorRoleArn", "")
        manual_kms_provider_role_arn = config.get("manualKmsProviderRoleArn", "")
        manual_ingress_operator_role_arn = config.get("manualIngressOperatorRoleArn", "")
        manual_image_registry_operator_role_arn = config.get(
            "manualImageRegistryOperatorRoleArn", ""
        )
        manual_storage_operator_role_arn = config.get("manualStorageOperatorRoleArn", "")
        manual_network_operator_role_arn = config.get("manualNetworkOperatorRoleArn", "")
        manual_oidc_config_id = config.get("manualOidcConfigId", "")

        if not cluster_name:
            raise HTTPException(status_code=400, detail="cluster_name is required")

        if not domain_prefix:
            raise HTTPException(status_code=400, detail="domain_prefix is required")

        if len(domain_prefix) > 15:
            raise HTTPException(
                status_code=400, detail="domain_prefix must be 15 characters or less"
            )

        print(f"🔍 [PREVIEW-DIRECT] Rendering templates directly for {cluster_name}")

        project_root = os.environ.get("AUTOMATION_PATH") or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        print(f"🔍 [PREVIEW-DIRECT] project_root: {project_root}")
        print(f"🔍 [PREVIEW-DIRECT] AUTOMATION_PATH env: {os.environ.get('AUTOMATION_PATH')}")

        # Parse version to get major.minor
        version_parts = openshift_version.split(".")
        major_minor = (
            f"{version_parts[0]}.{version_parts[1]}"
            if len(version_parts) >= 2
            else openshift_version
        )

        versions_dir = os.path.join(project_root, "templates", "versions")
        if not os.path.isdir(os.path.join(versions_dir, major_minor)):
            try:
                def _version_sort_key(v):
                    parts = []
                    for segment in v.split("."):
                        digits = "".join(c for c in segment if c.isdigit())
                        parts.append(int(digits) if digits else 0)
                    return parts or [0]

                available = sorted(
                    [d for d in os.listdir(versions_dir) if os.path.isdir(os.path.join(versions_dir, d))],
                    key=_version_sort_key,
                    reverse=True,
                )
                if available:
                    print(f"⚠️  Version dir '{major_minor}' not found, falling back to '{available[0]}'")
                    major_minor = available[0]
                else:
                    raise FileNotFoundError(f"No template version directories in {versions_dir}")
            except OSError as e:
                raise HTTPException(status_code=500, detail=f"Template versions directory error: {e}")

        from jinja2 import Environment, FileSystemLoader
        import re
        from datetime import datetime

        # Custom Jinja2 filters to match Ansible functionality
        def ansible_bool(value):
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ("true", "yes", "1")
            if isinstance(value, (int, float)):
                return bool(value)
            return bool(value)

        def ansible_int(value, default=0):
            try:
                return int(value)
            except (ValueError, TypeError):
                return default

        def regex_replace(value, pattern, replacement):
            """Ansible-compatible regex_replace filter"""
            return re.sub(pattern, replacement, str(value))

        def ansible_lookup(lookup_type, command):
            """Ansible-compatible lookup filter - simplified for preview mode"""
            if lookup_type == "pipe" and "date" in command:
                # Return current UTC timestamp
                return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            return ""

        yaml_contents = []
        yaml_files = []

        # Template variables
        template_vars = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "cluster_name": cluster_name,
            "cluster_name_prefix": cluster_name[:32],  # Truncate to 32 chars for AWS limits
            "rcp_version": openshift_version,
            "aws_account_id": "123456789012",  # Placeholder for preview
            "aws_region": aws_region,
            "capi_namespace": "ns-rosa-hcp",
            "rosa_hcp_namespace": "ns-rosa-hcp",
            "rosa_role_config_name": f"{cluster_name}-roles",
            "rosa_role_prefix": role_prefix,
            "rosa_network_name": f"{cluster_name}-network",
            "network_cidr": vpc_cidr_block,
            "vpc_cidr_block": vpc_cidr_block,
            "availability_zone_count": availability_zone_count,
            "aws_availability_zones": [f"{aws_region}a", f"{aws_region}b", f"{aws_region}c"][
                :availability_zone_count
            ],
            "openshift_version": openshift_version,
            "rosa_creds_secret": "rosa-creds-secret",
            "environment_tag": "test",
            "purpose_tag": "rosa-preview",
            "domain_prefix": domain_prefix if domain_prefix else f"rosa-{cluster_name[:15]}",
            "channel_group": channel_group,
            "channel": channel,
            "cluster_network": {
                "pod_cidr": "10.128.0.0/14",
                "service_cidr": "172.30.0.0/16",
                "machine_cidr": vpc_cidr_block,
            },
            "rosa_network_config": {
                "name": f"{cluster_name}-network",
                "cidr_block": vpc_cidr_block,
                "availability_zones": [f"us-west-2a", f"us-west-2b"][:availability_zone_count],
                "identity_name": "default",
                "enabled": create_rosa_network,
                "tags": {"Environment": "test", "CreatedBy": "automation-ui"},
            },
            "rosa_role_config": {
                "prefix": role_prefix[:4],
                "version": openshift_version,
                "identity_name": "default",
                "enabled": create_rosa_roles,
            },
            "machine_pool": {
                "instance_type": "m5.xlarge",
                "min_replicas": 2,
                "max_replicas": 3,
                "replicas": 2,
                "node_pool_name": node_pool_name,
            },
            # Log forwarding configuration
            "log_forward_enabled": enable_log_forwarding,
            "log_forward_applications": log_forward_applications,
            "log_forward_cloudwatch_role_arn": log_forward_cloudwatch_role_arn,
            "log_forward_cloudwatch_log_group": log_forward_cloudwatch_log_group,
            "log_forward_s3_bucket": log_forward_s3_bucket,
            "log_forward_s3_prefix": log_forward_s3_prefix,
            # FIPS configuration (OpenShift 4.21+ only)
            "fips": enable_fips,
            # Manual configuration (for environments without CRDs)
            "manual_subnets": (
                [manual_public_subnet, manual_private_subnet]
                if manual_public_subnet and manual_private_subnet
                else []
            ),
            "manual_public_subnet": manual_public_subnet,
            "manual_private_subnet": manual_private_subnet,
            "manual_vpc_id": manual_vpc_id,
            "manual_oidc_config_id": manual_oidc_config_id,
            "manual_roles": {
                "installer": manual_installer_role_arn,
                "support": manual_support_role_arn,
                "worker": manual_worker_role_arn,
                "control_plane_operator": manual_control_plane_operator_role_arn,
                "kms_provider": manual_kms_provider_role_arn,
                "ingress_operator": manual_ingress_operator_role_arn,
                "image_registry_operator": manual_image_registry_operator_role_arn,
                "storage_operator": manual_storage_operator_role_arn,
                "network_operator": manual_network_operator_role_arn,
            },
        }

        # Determine which template to use based on automation options
        if create_rosa_network and create_rosa_roles:
            cp_template_name = "rosa-combined-automation.yaml.j2"
            use_combined_template = True
        elif create_rosa_network:
            cp_template_name = "rosa-capi-network-cluster.yaml.j2"
            cp_template_fallback = "rosa-controlplane-only.yaml.j2"
            use_combined_template = True
        elif create_rosa_roles:
            cp_template_name = "rosa-capi-roles-cluster.yaml.j2"
            cp_template_fallback = "rosa-controlplane-only.yaml.j2"
            use_combined_template = True
        else:
            cp_template_name = "rosa-control-plane.yaml.j2"
            cp_template_fallback = "rosa-controlplane-only.yaml.j2"
            use_combined_template = False

        # If NOT using a combined template, render individual resources first
        if not use_combined_template:
            # Render ROSARoleConfig if needed (only for manual mode)
            if create_rosa_roles:
                role_template_path = os.path.join(
                    project_root,
                    f"templates/versions/{major_minor}/features/rosa-role-config.yaml.j2",
                )
                if not os.path.exists(role_template_path):
                    role_template_path = os.path.join(
                        project_root,
                        f"templates/versions/{major_minor}/4.20/features/rosa-role-config.yaml.j2",
                    )
                if not os.path.exists(role_template_path):
                    role_template_path = os.path.join(
                        project_root, f"templates/features/rosa-role-config.yaml.j2"
                    )

                if os.path.exists(role_template_path):
                    env = Environment(loader=FileSystemLoader(os.path.dirname(role_template_path)))
                    env.filters["regex_replace"] = regex_replace
                    env.filters["bool"] = ansible_bool
                    env.filters["int"] = ansible_int
                    env.globals["lookup"] = ansible_lookup
                    template = env.get_template(os.path.basename(role_template_path))
                    rendered = template.render(**template_vars)
                    yaml_contents.append(rendered)
                    yaml_files.append(role_template_path)

            # Render ROSANetwork if needed (only for manual mode)
            if create_rosa_network:
                network_template_path = os.path.join(
                    project_root,
                    f"templates/versions/{major_minor}/features/rosa-network-config.yaml.j2",
                )
                if not os.path.exists(network_template_path):
                    network_template_path = os.path.join(
                        project_root,
                        f"templates/versions/{major_minor}/4.20/features/rosa-network-config.yaml.j2",
                    )
                if not os.path.exists(network_template_path):
                    network_template_path = os.path.join(
                        project_root, f"templates/features/rosa-network-config.yaml.j2"
                    )

                if os.path.exists(network_template_path):
                    env = Environment(
                        loader=FileSystemLoader(os.path.dirname(network_template_path))
                    )
                    env.filters["regex_replace"] = regex_replace
                    env.filters["bool"] = ansible_bool
                    env.filters["int"] = ansible_int
                    env.globals["lookup"] = ansible_lookup
                    template = env.get_template(os.path.basename(network_template_path))
                    rendered = template.render(**template_vars)
                    yaml_contents.append(rendered)
                    yaml_files.append(network_template_path)

        # Render main cluster template (combined or control-plane-only)
        print(f"🔍 [PREVIEW-DIRECT] Template name: {cp_template_name}, major_minor: {major_minor}")
        cp_template_path = os.path.join(
            project_root, f"templates/versions/{major_minor}/features/{cp_template_name}"
        )
        print(f"🔍 [PREVIEW-DIRECT] Try 1: {cp_template_path} -> {os.path.exists(cp_template_path)}")
        if not os.path.exists(cp_template_path):
            # Try version/4.20/features fallback (e.g., 4.19/4.20/features)
            cp_template_path = os.path.join(
                project_root, f"templates/versions/{major_minor}/4.20/features/{cp_template_name}"
            )
            print(f"🔍 [PREVIEW-DIRECT] Try 2: {cp_template_path} -> {os.path.exists(cp_template_path)}")
        if not os.path.exists(cp_template_path):
            cp_template_path = os.path.join(
                project_root, f"templates/versions/{major_minor}/cluster-configs/{cp_template_name}"
            )
            print(f"🔍 [PREVIEW-DIRECT] Try 3: {cp_template_path} -> {os.path.exists(cp_template_path)}")
        if not os.path.exists(cp_template_path):
            cp_template_path = os.path.join(project_root, f"templates/features/{cp_template_name}")
            print(f"🔍 [PREVIEW-DIRECT] Try 4: {cp_template_path} -> {os.path.exists(cp_template_path)}")
        if not os.path.exists(cp_template_path) and 'cp_template_fallback' in locals():
            fb = cp_template_fallback
            cp_template_path = os.path.join(
                project_root, f"templates/versions/{major_minor}/features/{fb}"
            )
            print(f"🔍 [PREVIEW-DIRECT] Try 5 (fallback): {cp_template_path} -> {os.path.exists(cp_template_path)}")

        if os.path.exists(cp_template_path):
            env = Environment(loader=FileSystemLoader(os.path.dirname(cp_template_path)))
            env.filters["regex_replace"] = regex_replace
            env.filters["bool"] = ansible_bool
            env.filters["int"] = ansible_int
            env.globals["lookup"] = ansible_lookup
            template = env.get_template(os.path.basename(cp_template_path))
            rendered = template.render(
                **template_vars,
                rosa_role_config_ref=(
                    template_vars["rosa_role_config_name"] if create_rosa_roles else None
                ),
                rosa_network_ref=(
                    template_vars["rosa_network_name"] if create_rosa_network else None
                ),
            )
            yaml_contents.append(rendered)
            yaml_files.append(cp_template_path)
            print(
                f"✅ [PREVIEW-DIRECT] Rendered template: {cp_template_name} (combined={use_combined_template})"
            )
        else:
            print(f"⚠️  Control plane template not found at {cp_template_path}")

        # Combine all YAML documents
        combined_yaml = "\n---\n".join(yaml_contents)

        print(f"🔍 [PREVIEW-DIRECT] combined_yaml length: {len(combined_yaml)}")
        print(f"🔍 [PREVIEW-DIRECT] yaml_contents count: {len(yaml_contents)}")
        if len(combined_yaml) > 0:
            print(f"🔍 [PREVIEW-DIRECT] First 200 chars: {combined_yaml[:200]}")

        # Determine feature type for filename
        if create_rosa_network and create_rosa_roles:
            feature_type = "network-roles"
            automation_suffix = (
                "full-automation"  # Complete cluster with automated network and roles
            )
        elif create_rosa_network:
            feature_type = "network"
            automation_suffix = "network-automation"  # Complete cluster with automated network
        elif create_rosa_roles:
            feature_type = "roles"
            automation_suffix = "roles-automation"  # Complete cluster with automated roles
        else:
            feature_type = "manual"
            automation_suffix = "manual-config"  # Complete cluster with manual network and roles

        # Create a meaningful file path for the combined YAML
        # Use the pattern: {cluster-name}-complete-{automation-type}.yaml
        combined_filename = f"{cluster_name}-complete-{automation_suffix}.yaml"
        combined_file_path = (
            f"generated-yamls/{datetime.now().strftime('%Y-%m-%d')}/{combined_filename}"
        )

        print(f"✅ [PREVIEW-DIRECT] Generated {len(yaml_contents)} YAML document(s)")
        print(f"📄 [PREVIEW-DIRECT] File will be saved as: {combined_file_path}")

        if not combined_yaml.strip():
            return {
                "success": False,
                "message": f"Template rendering produced no content for {cp_template_name}",
                "yaml_content": "",
            }

        response_data = {
            "success": True,
            "yaml_content": combined_yaml,
            "file_paths": [combined_file_path],  # Single combined file path
            "feature_type": feature_type,
            "cluster_name": cluster_name,
            "message": f"Generated YAML for {len(yaml_contents)} resource(s)",
        }

        print(f"🔍 [PREVIEW-DIRECT] Response success: {response_data['success']}")
        print(f"🔍 [PREVIEW-DIRECT] Response yaml_content length: {len(response_data.get('yaml_content', ''))}")
        print(f"🔍 [PREVIEW-DIRECT] Response keys: {list(response_data.keys())}")

        return response_data

    except Exception as e:
        import traceback

        print(f"❌ [PREVIEW-DIRECT] Error: {str(e)}")
        print(traceback.format_exc())
        return {
            "success": False,
            "message": f"Error generating YAML: {str(e)}",
            "error": traceback.format_exc(),
        }


@router.post("/api/provisioning/apply-yaml")
async def apply_provisioning_yaml(request: Request, background_tasks: BackgroundTasks):
    """Save and apply user-edited provisioning YAML"""
    try:
        body = await request.json()
        yaml_content = body.get("yaml_content")
        cluster_name = body.get("cluster_name")
        feature_type = body.get("feature_type", "manual")
        cluster_context = body.get(
            "cluster_context"
        )  # Optional: Minikube cluster name or kubeconfig context

        if not yaml_content or not cluster_name:
            raise HTTPException(
                status_code=400, detail="yaml_content and cluster_name are required"
            )

        project_root = os.environ.get("AUTOMATION_PATH") or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

        # Create dated directory: generated-yamls/YYYY-MM-DD/
        from datetime import date

        today = date.today().strftime("%Y-%m-%d")
        saved_yamls_dir = os.path.join(project_root, "generated-yamls", today)
        os.makedirs(saved_yamls_dir, exist_ok=True)

        # Save to dated directory with feature type naming
        saved_yaml_filename = f"{cluster_name}-{feature_type}.yaml"
        saved_yaml_path = os.path.join(saved_yamls_dir, saved_yaml_filename)

        with open(saved_yaml_path, "w") as f:
            f.write(yaml_content)

        print(f"💾 [APPLY] Saved edited YAML to: {saved_yaml_path}")

        # Also copy to ~/output for Ansible compatibility
        output_dir = os.path.expanduser("~/output")
        os.makedirs(output_dir, exist_ok=True)
        output_yaml_path = os.path.join(output_dir, f"{cluster_name}-combined.yaml")

        with open(output_yaml_path, "w") as f:
            f.write(yaml_content)

        # Generate job ID
        job_id = str(uuid.uuid4())

        # Create job
        jobs[job_id] = {
            "id": job_id,
            "status": "pending",
            "progress": 0,
            "message": "Queued: Applying provisioning YAML",
            "logs": [],
            "created_at": datetime.now(),
            "yaml_file": saved_yaml_path,
            "description": f"Apply ROSA provisioning YAML for {cluster_name}",
        }

        # Initialize AI agents for provisioning monitoring
        agents = init_ai_agents(job_id)

        # Run application in background
        async def apply_yaml_background():
            try:
                jobs[job_id]["status"] = "running"
                jobs[job_id]["progress"] = 10
                jobs[job_id]["message"] = "Parsing YAML resources"

                # Split multi-document YAML by ---
                import yaml
                import time
                import json
                import asyncio

                yaml_documents = list(yaml.safe_load_all(yaml_content))

                jobs[job_id]["progress"] = 20
                jobs[job_id]["message"] = f"Found {len(yaml_documents)} resource(s) to apply"
                jobs[job_id]["logs"].append(f"📄 Parsed {len(yaml_documents)} YAML document(s)")

                # Extract cluster information from YAML for notifications
                region = "N/A"
                version = "N/A"
                for doc in yaml_documents:
                    if doc and doc.get("kind") == "RosaControlPlane":
                        spec = doc.get("spec", {})
                        region = spec.get("region", "N/A")
                        version = spec.get("version", "N/A")
                        break

                # Send "started" notification
                send_cluster_notifications(
                    cluster_name=cluster_name,
                    region=region,
                    version=version,
                    job_id=job_id,
                    status="started",
                    operation_type="provision"
                )

                # For Minikube, use Ansible playbook for async execution
                if cluster_context:
                    # Filter out ManagedCluster resources (MCE/ACM-specific, not available on minikube)
                    mce_kinds = {"ManagedCluster"}
                    filtered_docs = [doc for doc in yaml_documents if doc and doc.get("kind") not in mce_kinds]
                    skipped = len(yaml_documents) - len(filtered_docs)
                    if skipped > 0:
                        jobs[job_id]["logs"].append(f"⏭️  Skipped {skipped} MCE-specific resource(s) (ManagedCluster) - not applicable to Minikube")
                        # Re-save the filtered YAML
                        filtered_yaml = "\n---\n".join(yaml.dump(doc, default_flow_style=False) for doc in filtered_docs)
                        with open(saved_yaml_path, "w") as f:
                            f.write(filtered_yaml)

                    jobs[job_id]["logs"].append(f"\n🎯 Provisioning to Minikube cluster: {cluster_context} via Ansible playbook")
                    jobs[job_id]["progress"] = 30
                    jobs[job_id]["message"] = "Running Ansible playbook for Minikube provisioning"

                    # Use the provision_rosa_hcp_minikube playbook
                    playbook_path = os.path.join(project_root, "playbooks", "provision_rosa_hcp_minikube.yml")

                    extra_vars = {
                        "cluster_name": cluster_name,
                        "minikube_context": cluster_context,
                        "yaml_file": saved_yaml_path,
                        "target_namespace": "ns-rosa-hcp"
                    }

                    jobs[job_id]["logs"].append(f"\n📋 Playbook: {playbook_path}")
                    jobs[job_id]["logs"].append(f"📦 Variables: {json.dumps(extra_vars, indent=2)}")

                    # Run ansible-playbook command
                    ansible_cmd = [
                        "ansible-playbook",
                        playbook_path,
                        "-e", json.dumps(extra_vars)
                    ]

                    result = await asyncio.to_thread(
                        subprocess.run,
                        ansible_cmd,
                        cwd=project_root,
                        capture_output=True,
                        text=True,
                        timeout=300  # 5 minute timeout for playbook itself
                    )

                    jobs[job_id]["logs"].append(f"\n{result.stdout}")
                    if result.stderr:
                        jobs[job_id]["logs"].append(f"\n⚠️ Warnings:\n{result.stderr}")

                    if result.returncode != 0:
                        jobs[job_id]["status"] = "failed"
                        jobs[job_id]["message"] = f"❌ Playbook failed with exit code {result.returncode}"
                        jobs[job_id]["error"] = result.stderr or result.stdout

                        send_cluster_notifications(
                            cluster_name=cluster_name,
                            region=region,
                            version=version,
                            job_id=job_id,
                            status="failed",
                            error=result.stderr or result.stdout,
                            operation_type="provision"
                        )
                        return

                    # Resources applied successfully - now poll until cluster is ready
                    jobs[job_id]["progress"] = 40
                    jobs[job_id]["message"] = "✅ Resources applied - monitoring cluster provisioning..."
                    jobs[job_id]["logs"].append(f"\n✅ Resources applied successfully! Now monitoring cluster status...")
                    jobs[job_id]["logs"].append(f"⏳ Polling RosaControlPlane status (this typically takes 15-20 minutes)...\n")

                    max_wait_time = 3600  # 60 minutes
                    poll_interval = 15  # Check every 15 seconds
                    start_time = time.time()
                    last_log_time = 0

                    while (time.time() - start_time) < max_wait_time:
                        try:
                            # Check RosaControlPlane status
                            check_cmd = [
                                "kubectl", "--context", cluster_context,
                                "get", "rosacontrolplane", cluster_name,
                                "-n", "ns-rosa-hcp", "-o", "json"
                            ]
                            check_result = await asyncio.to_thread(
                                subprocess.run,
                                check_cmd, capture_output=True, text=True, timeout=30
                            )

                            if check_result.returncode == 0:
                                rcp_data = json.loads(check_result.stdout)
                                status_obj = rcp_data.get("status", {})
                                ready = status_obj.get("ready", False)
                                conditions = status_obj.get("conditions", [])

                                # Find the ROSAControlPlaneReady condition
                                rcp_reason = "Unknown"
                                rcp_message = ""
                                for cond in conditions:
                                    if cond.get("type") == "ROSAControlPlaneReady":
                                        rcp_reason = cond.get("reason", "Unknown")
                                        rcp_message = cond.get("message", "")
                                        break

                                elapsed = time.time() - start_time
                                elapsed_min = int(elapsed // 60)
                                elapsed_sec = int(elapsed % 60)

                                # AI Agent: Feed status to monitoring agent
                                if agents and agents.get("monitor"):
                                    try:
                                        status_line = f"#AGENT_CONTEXT: resource_name={cluster_name} namespace=ns-rosa-hcp resource_type=rosacontrolplane"
                                        agents["monitor"].process_line(status_line)
                                        status_line = f"RosaControlPlane {cluster_name}: ready={ready} reason={rcp_reason} message={rcp_message}"
                                        agents["monitor"].process_line(status_line)
                                    except Exception as agent_err:
                                        print(f"[AI Agent] Warning: {agent_err}")

                                if ready:
                                    jobs[job_id]["status"] = "completed"
                                    jobs[job_id]["progress"] = 100
                                    jobs[job_id]["message"] = f"✅ Cluster {cluster_name} provisioned successfully!"
                                    jobs[job_id]["logs"].append(f"\n✅ Cluster {cluster_name} is READY! ({elapsed_min}m {elapsed_sec}s)")
                                    jobs[job_id]["agent_stats"] = get_agent_stats(job_id)

                                    send_cluster_notifications(
                                        cluster_name=cluster_name,
                                        region=region,
                                        version=version,
                                        job_id=job_id,
                                        status="completed",
                                        operation_type="provision"
                                    )
                                    return

                                elif rcp_reason in ["ReconciliationError", "ProvisioningFailed", "Failed"]:
                                    jobs[job_id]["status"] = "failed"
                                    jobs[job_id]["progress"] = 100
                                    jobs[job_id]["message"] = f"❌ Cluster {cluster_name} provisioning failed: {rcp_reason}"
                                    jobs[job_id]["logs"].append(f"\n❌ Provisioning failed: {rcp_reason}")
                                    if rcp_message:
                                        jobs[job_id]["logs"].append(f"   {rcp_message}")
                                    jobs[job_id]["agent_stats"] = get_agent_stats(job_id)

                                    send_cluster_notifications(
                                        cluster_name=cluster_name,
                                        region=region,
                                        version=version,
                                        job_id=job_id,
                                        status="failed",
                                        error=f"{rcp_reason}: {rcp_message}",
                                        operation_type="provision"
                                    )
                                    return

                                else:
                                    # Still provisioning - update progress (40-90%)
                                    progress = min(90, 40 + int((elapsed / max_wait_time) * 50))
                                    jobs[job_id]["progress"] = progress
                                    jobs[job_id]["message"] = f"⏳ Provisioning... ({rcp_reason}) - {elapsed_min}m {elapsed_sec}s"

                                    # Log every 30 seconds
                                    if time.time() - last_log_time >= 30:
                                        jobs[job_id]["logs"].append(f"   [{elapsed_min}m {elapsed_sec}s] Status: {rcp_reason}")
                                        if rcp_message:
                                            jobs[job_id]["logs"].append(f"             {rcp_message}")
                                        last_log_time = time.time()

                        except Exception as poll_error:
                            jobs[job_id]["logs"].append(f"⚠️ Poll error: {str(poll_error)}")

                        await asyncio.sleep(poll_interval)

                    # Timeout
                    jobs[job_id]["status"] = "failed"
                    jobs[job_id]["progress"] = 100
                    jobs[job_id]["message"] = f"❌ Provisioning timed out after 60 minutes"
                    jobs[job_id]["logs"].append(f"\n❌ Timeout: Cluster did not reach ready state within 60 minutes")

                    send_cluster_notifications(
                        cluster_name=cluster_name,
                        region=region,
                        version=version,
                        job_id=job_id,
                        status="failed",
                        error="Provisioning timed out after 60 minutes",
                        operation_type="provision"
                    )
                    return

                    apply_cmd = [
                        "kubectl",
                        "--context",
                        cluster_context,
                        "apply",
                        "-f",
                        saved_yaml_path,
                    ]

                    result = subprocess.run(
                        apply_cmd,
                        cwd=project_root,
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )

                    jobs[job_id]["logs"].append(f"\n{result.stdout}")
                    if result.stderr:
                        jobs[job_id]["logs"].append(f"\n⚠️ Warnings/Errors:\n{result.stderr}")

                    if result.returncode == 0 or "created" in result.stdout or "configured" in result.stdout:
                        jobs[job_id]["progress"] = 50
                        jobs[job_id]["message"] = "✅ Resources applied, waiting for cluster to be ready..."
                        jobs[job_id]["logs"].append(f"\n✅ All resources applied successfully!")

                        # Wait for cluster to be ready (for Minikube/ROSA provisioning)
                        jobs[job_id]["logs"].append(f"\n⏳ Monitoring cluster provisioning status...")

                        max_wait_time = 3600  # 60 minutes max wait
                        poll_interval = 10  # Check every 10 seconds
                        start_time = time.time()

                        while (time.time() - start_time) < max_wait_time:
                            # Get cluster name from YAML
                            try:
                                # Check for Cluster resource status
                                check_cluster_cmd = [
                                    "kubectl",
                                    "--context",
                                    cluster_context,
                                    "get",
                                    "cluster",
                                    "-n", "ns-rosa-hcp",
                                    "-o", "json"
                                ]

                                cluster_result = subprocess.run(
                                    check_cluster_cmd,
                                    capture_output=True,
                                    text=True,
                                    timeout=30
                                )

                                if cluster_result.returncode == 0:
                                    clusters_data = json.loads(cluster_result.stdout)

                                    if clusters_data.get("items"):
                                        cluster = clusters_data["items"][0]  # Get first cluster
                                        found_cluster_name = cluster["metadata"]["name"]
                                        phase = cluster.get("status", {}).get("phase", "Unknown")

                                        # Check RosaControlPlane ready status
                                        check_rcp_cmd = [
                                            "kubectl",
                                            "--context",
                                            cluster_context,
                                            "get",
                                            "rosacontrolplane",
                                            found_cluster_name,
                                            "-n", "ns-rosa-hcp",
                                            "-o", "jsonpath={.status.ready}"
                                        ]

                                        rcp_result = subprocess.run(
                                            check_rcp_cmd,
                                            capture_output=True,
                                            text=True,
                                            timeout=30
                                        )

                                        rcp_ready = rcp_result.stdout.strip().lower() == "true"

                                        # Update progress based on phase
                                        if phase == "Provisioned" and rcp_ready:
                                            jobs[job_id]["status"] = "completed"
                                            jobs[job_id]["progress"] = 100
                                            jobs[job_id]["message"] = f"✅ Cluster {found_cluster_name} is ready!"
                                            jobs[job_id]["logs"].append(f"\n✅ Cluster {found_cluster_name} provisioned successfully!")
                                            jobs[job_id]["logs"].append(f"   Phase: {phase}")
                                            jobs[job_id]["logs"].append(f"   RosaControlPlane Ready: {rcp_ready}")
                                            return
                                        elif phase == "Failed":
                                            jobs[job_id]["status"] = "failed"
                                            jobs[job_id]["progress"] = 100
                                            jobs[job_id]["message"] = f"❌ Cluster {found_cluster_name} provisioning failed"
                                            jobs[job_id]["logs"].append(f"\n❌ Cluster {found_cluster_name} entered Failed state")
                                            return
                                        else:
                                            # Update progress incrementally (50-90%)
                                            elapsed = time.time() - start_time
                                            progress = min(90, 50 + int((elapsed / max_wait_time) * 40))
                                            jobs[job_id]["progress"] = progress
                                            jobs[job_id]["message"] = f"⏳ Cluster {cluster_name} provisioning... (Phase: {phase}, RCP Ready: {rcp_ready})"

                                            # Log status update every 60 seconds
                                            if int(elapsed) % 60 == 0:
                                                jobs[job_id]["logs"].append(f"   [{int(elapsed//60)}m] Phase: {phase}, RCP Ready: {rcp_ready}")

                            except Exception as status_error:
                                jobs[job_id]["logs"].append(f"⚠️  Error checking cluster status: {str(status_error)}")

                            await asyncio.sleep(poll_interval)

                        # Timeout reached
                        jobs[job_id]["status"] = "failed"
                        jobs[job_id]["progress"] = 100
                        jobs[job_id]["message"] = "❌ Cluster provisioning timed out after 60 minutes"
                        jobs[job_id]["logs"].append(f"\n❌ Timeout: Cluster did not reach ready state within 60 minutes")
                        return
                    else:
                        jobs[job_id]["status"] = "failed"
                        jobs[job_id]["progress"] = 100
                        jobs[job_id]["message"] = f"❌ Failed to apply resources"
                        jobs[job_id]["logs"].append(f"\n❌ ERROR: {result.stderr}")
                        return

                # Apply each resource using oc apply
                progress_increment = 70 / max(len(yaml_documents), 1)
                current_progress = 20

                for idx, doc in enumerate(yaml_documents, 1):
                    if not doc:  # Skip empty documents
                        continue

                    kind = doc.get("kind", "Unknown")
                    name = doc.get("metadata", {}).get("name", "Unknown")

                    # Skip ManagedCluster when applying to Minikube (no ACM/MCE CRDs)
                    if cluster_context and kind == "ManagedCluster":
                        jobs[job_id]["logs"].append(
                            f"\n[{idx}/{len(yaml_documents)}] Skipping {kind}/{name} (ACM/MCE-only resource, not available on Minikube)"
                        )
                        continue

                    jobs[job_id]["logs"].append(
                        f"\n[{idx}/{len(yaml_documents)}] Applying {kind}/{name}..."
                    )

                    # Save individual document to temp file
                    import tempfile

                    with tempfile.NamedTemporaryFile(
                        mode="w", suffix=".yaml", delete=False
                    ) as temp_file:
                        yaml.dump(doc, temp_file)
                        temp_path = temp_file.name

                    try:
                        # Build kubectl/oc command with optional context
                        if cluster_context:
                            # Use kubectl with --context for Minikube or other non-OpenShift clusters
                            apply_cmd = [
                                "kubectl",
                                "--context",
                                cluster_context,
                                "apply",
                                "-f",
                                temp_path,
                            ]
                        else:
                            # Default to oc for OpenShift clusters
                            apply_cmd = ["oc", "apply", "-f", temp_path]

                        result = subprocess.run(
                            apply_cmd,
                            cwd=project_root,
                            capture_output=True,
                            text=True,
                            timeout=120,
                        )

                        if result.returncode == 0:
                            jobs[job_id]["logs"].append(f"✅ {result.stdout.strip()}")

                            # If we just created a Namespace or ManagedCluster, copy rosa-creds-secret to it
                            # ManagedCluster is often the first resource and triggers namespace creation
                            if kind in ["Namespace", "ManagedCluster"]:
                                # Get the namespace name from the resource
                                namespace_name = doc.get("metadata", {}).get(
                                    "namespace", name if kind == "Namespace" else None
                                )

                                if namespace_name:
                                    jobs[job_id]["logs"].append(
                                        f"\n🔐 Checking for rosa-creds-secret to copy to {namespace_name}..."
                                    )

                                    try:
                                        # Build kubectl/oc commands with optional context
                                        if cluster_context:
                                            kubectl_cmd = "kubectl --context " + cluster_context
                                        else:
                                            kubectl_cmd = "oc"

                                        # Check if rosa-creds-secret exists in multicluster-engine namespace
                                        check_secret = subprocess.run(
                                            [kubectl_cmd.split()[0]]
                                            + (kubectl_cmd.split()[1:] if cluster_context else [])
                                            + [
                                                "get",
                                                "secret",
                                                "rosa-creds-secret",
                                                "-n",
                                                "multicluster-engine",
                                            ],
                                            capture_output=True,
                                            text=True,
                                            timeout=10,
                                        )

                                        if check_secret.returncode == 0:
                                            # Secret exists, copy it to the new namespace
                                            copy_cmd = f"""
{kubectl_cmd} get secret rosa-creds-secret -n multicluster-engine -o yaml | \
sed 's/namespace: multicluster-engine/namespace: {namespace_name}/' | \
sed '/resourceVersion:/d' | \
sed '/uid:/d' | \
sed '/creationTimestamp:/d' | \
{kubectl_cmd} apply -f -
"""
                                            copy_result = subprocess.run(
                                                ["bash", "-c", copy_cmd],
                                                capture_output=True,
                                                text=True,
                                                timeout=30,
                                            )

                                            if copy_result.returncode == 0:
                                                jobs[job_id]["logs"].append(
                                                    f"✅ rosa-creds-secret copied to {namespace_name}"
                                                )
                                            else:
                                                jobs[job_id]["logs"].append(
                                                    f"⚠️  Failed to copy rosa-creds-secret: {copy_result.stderr.strip()}"
                                                )
                                        else:
                                            jobs[job_id]["logs"].append(
                                                f"⚠️  rosa-creds-secret not found in multicluster-engine namespace - skipping copy"
                                            )

                                    except Exception as secret_error:
                                        jobs[job_id]["logs"].append(
                                            f"⚠️  Error copying secret: {str(secret_error)}"
                                        )
                        else:
                            jobs[job_id]["logs"].append(f"❌ Failed: {result.stderr.strip()}")
                            raise Exception(f"Failed to apply {kind}/{name}: {result.stderr}")

                    finally:
                        os.unlink(temp_path)

                    current_progress += progress_increment
                    jobs[job_id]["progress"] = int(current_progress)

                jobs[job_id]["status"] = "completed"
                jobs[job_id]["progress"] = 100
                jobs[job_id]["message"] = f"Successfully applied {len(yaml_documents)} resource(s)"
                jobs[job_id]["logs"].append(f"\n✅ All resources applied successfully!")
                jobs[job_id]["completed_at"] = datetime.now()
                jobs[job_id]["return_code"] = 0

            except Exception as e:
                jobs[job_id]["status"] = "failed"
                jobs[job_id]["message"] = f"Error applying YAML: {str(e)}"
                jobs[job_id]["logs"].append(f"\n❌ ERROR: {str(e)}")
                jobs[job_id]["completed_at"] = datetime.now()
                jobs[job_id]["return_code"] = 1

        # Start background task using asyncio.create_task so blocking calls
        # don't freeze the event loop
        import asyncio
        asyncio.create_task(apply_yaml_background())

        return {
            "success": True,
            "job_id": job_id,
            "status": "pending",
            "message": "YAML queued for application",
            "saved_path": saved_yaml_path,
        }

    except Exception as e:
        import traceback

        error_msg = f"Error applying YAML: {str(e)}"
        print(f"❌ [APPLY] {error_msg}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_msg)

