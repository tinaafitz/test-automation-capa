"""
AI Assistant chat service module — FastAPI router for the AI chat endpoint.

Endpoints moved here from app.py:
  POST   /api/ai-assistant/chat

Dependencies resolved at runtime via _resolve():
  ai_service          — AIAssistantService instance
  jobs                — shared mutable job dict
  normalize_timestamp — timestamp normalisation helper
"""

import os
import sys

from fastapi import APIRouter, Request

router = APIRouter()


def _resolve(name: str):
    """Look up *name* via the app module so that unittest.mock.patch on
    ``app.<name>`` takes effect even though the endpoint lives here."""
    app_mod = sys.modules.get("app")
    if app_mod is not None:
        return getattr(app_mod, name)
    return globals()[name]


@router.post("/api/ai-assistant/chat")
async def ai_assistant_chat(request: Request):
    """AI Assistant chat endpoint - provides AI-powered analysis of cluster issues using Claude"""
    try:
        body = await request.json()
        message = body.get("message", "")
        context = body.get("context", {})
        history = body.get("history", [])
        clusters_data = context.get("clusters", [])

        import logging

        logger = logging.getLogger("uvicorn")
        logger.info(f"🔍 [AI ASSISTANT] Message: {message}")
        logger.info(f"🔍 [AI ASSISTANT] Clusters data received: {clusters_data}")

        # Ensure clusters_data is a list
        if not isinstance(clusters_data, list):
            clusters_data = []

        # Enrich context with actual job logs for failed/error clusters
        enriched_context = {"clusters": clusters_data, "job_logs": [], "resource_status": {}}

        # Find failed or error clusters and get their job logs
        failed_clusters = [
            c
            for c in clusters_data
            if c.get("status") in ["failed", "error", "provisioning-failed"]
        ]

        jobs = _resolve("jobs")
        ai_service = _resolve("ai_service")
        normalize_timestamp = _resolve("normalize_timestamp")

        for cluster in failed_clusters:
            cluster_name = cluster.get("name", "unknown")

            # Search jobs dictionary for provisioning jobs for this cluster
            for job_id, job_data in jobs.items():
                yaml_file = job_data.get("yaml_file", "")
                description = job_data.get("description", "")

                # Check if this job is for the failed cluster
                if (
                    cluster_name.lower() in yaml_file.lower()
                    or cluster_name.lower() in description.lower()
                ):
                    log_content = "\n".join(job_data.get("logs", []))

                    enriched_context["job_logs"].append(
                        {
                            "job_id": job_id,
                            "cluster_name": cluster_name,
                            "status": job_data.get("status", "unknown"),
                            "logs": log_content,
                            "yaml_file": yaml_file,
                            "created_at": job_data.get("created_at", ""),
                        }
                    )

        # Use AI service if ANTHROPIC_API_KEY is set
        if os.environ.get("ANTHROPIC_API_KEY"):
            try:
                ai_response = await ai_service.chat(message, enriched_context, history)
                response_text = ai_response.get("response", "")

                logger.info(f"🤖 [AI-ASSISTANT] AI Response: {response_text[:200]}...")

                # Post-process: If user asked about clusters and AI didn't include names, fix it
                if "what clusters" in message.lower() or "clusters are running" in message.lower():
                    logger.info(
                        f"🔍 [AI-ASSISTANT] Cluster query detected. Clusters data: {[c.get('name') for c in clusters_data]}"
                    )
                    has_cluster_names = any(
                        c.get("name", "") in response_text for c in clusters_data
                    )
                    logger.info(
                        f"🔍 [AI-ASSISTANT] Response contains cluster names: {has_cluster_names}"
                    )

                    if clusters_data and not has_cluster_names:
                        # AI didn't include cluster names, build proper response
                        logger.info(
                            "🔧 [AI-ASSISTANT] AI response missing cluster names, fixing..."
                        )
                        cluster_list = "\n".join(
                            [
                                f"  - {c.get('name', 'unknown')} (namespace: {c.get('namespace', 'unknown')}, status: {c.get('status', 'unknown')})"
                                for c in clusters_data
                            ]
                        )
                        response_text = (
                            f"You have {len(clusters_data)} cluster(s):\n\n{cluster_list}"
                        )
                        logger.info(f"✅ [AI-ASSISTANT] Fixed response: {response_text}")

                return {
                    "success": True,
                    "response": response_text,
                    "suggestions": ai_response.get("suggestions", []),
                }
            except Exception as ai_error:
                logger.error(
                    f"⚠️ [AI-ASSISTANT] Claude API error: {str(ai_error)}, falling back to simple responses"
                )
                logger.error(f"⚠️ [AI-ASSISTANT] Error traceback: ", exc_info=True)
                # Fall through to simple responses below

        # Fallback: Simple rule-based responses if no API key or AI service fails
        response = ""
        suggestions = []
        message_lower = message.lower()

        # Handle cluster-related questions
        if (
            "what clusters" in message_lower
            or "list clusters" in message_lower
            or "show clusters" in message_lower
        ):
            if clusters_data:
                response = f"Currently, you have {len(clusters_data)} cluster(s):\n\n"

                # Categorize clusters by status
                ready_clusters = [c for c in clusters_data if c.get("status") == "ready"]
                provisioning_clusters = [
                    c for c in clusters_data if c.get("status") == "provisioning"
                ]
                failed_clusters = [
                    c
                    for c in clusters_data
                    if c.get("status") in ["failed", "error", "provisioning-failed"]
                ]
                uninstalling_clusters = [
                    c for c in clusters_data if c.get("status") == "uninstalling"
                ]
                other_clusters = [
                    c
                    for c in clusters_data
                    if c.get("status")
                    not in [
                        "ready",
                        "provisioning",
                        "failed",
                        "error",
                        "provisioning-failed",
                        "uninstalling",
                    ]
                ]

                if ready_clusters:
                    response += f"**✅ Ready ({len(ready_clusters)}):**\n"
                    for cluster in ready_clusters:
                        name = cluster.get("name", "unknown")
                        region = cluster.get("region", "unknown")
                        version = cluster.get("version", "N/A")
                        response += f"• **{name}** - Region: {region}, Version: {version}\n"
                    response += "\n"

                if provisioning_clusters:
                    response += f"**⏳ Provisioning ({len(provisioning_clusters)}):**\n"
                    for cluster in provisioning_clusters:
                        name = cluster.get("name", "unknown")
                        progress = cluster.get("progress", 0)
                        response += f"• **{name}** - {progress}% complete\n"
                    response += "\n"

                if failed_clusters:
                    response += f"**❌ Failed ({len(failed_clusters)}):**\n"
                    for cluster in failed_clusters:
                        name = cluster.get("name", "unknown")
                        status = cluster.get("status", "unknown")
                        response += f"• **{name}** - Status: {status}\n"
                    response += "\n"

                if uninstalling_clusters:
                    response += f"**🗑️ Uninstalling ({len(uninstalling_clusters)}):**\n"
                    for cluster in uninstalling_clusters:
                        name = cluster.get("name", "unknown")
                        namespace = cluster.get("namespace", "unknown")
                        region = cluster.get("region", "unknown")
                        response += f"• **{name}** (namespace: {namespace}, region: {region})\n"
                    response += "\n"

                if other_clusters:
                    response += f"**ℹ️ Other Status ({len(other_clusters)}):**\n"
                    for cluster in other_clusters:
                        name = cluster.get("name", "unknown")
                        status = cluster.get("status", "unknown")
                        response += f"• **{name}** - Status: {status}\n"
                    response += "\n"

                # Set suggestions based on cluster states
                if failed_clusters:
                    suggestions = ["Troubleshoot failed cluster", "Show me the logs"]
                elif uninstalling_clusters:
                    first_cluster_name = uninstalling_clusters[0].get("name", "unknown")
                    suggestions = [f"Tell me more about {first_cluster_name}", "Show me the logs"]
                elif provisioning_clusters:
                    # Add suggestion to check on the provisioning cluster
                    first_cluster_name = provisioning_clusters[0].get("name", "unknown")
                    suggestions = [
                        f"Tell me about {first_cluster_name}",
                        "Check environment status",
                    ]
                else:
                    suggestions = ["Provision new cluster", "What is ROSA HCP?"]
            else:
                response = "You don't have any clusters running at the moment. Would you like to provision one?"
                suggestions = ["How to provision cluster?", "What is ROSA HCP?"]

        # Handle "tell me more about" or "tell me about" cluster requests
        elif ("tell me" in message_lower or "about" in message_lower) and any(
            c.get("name", "").lower() in message_lower for c in clusters_data
        ):
            # Find the cluster being asked about
            target_cluster = None
            for cluster in clusters_data:
                cluster_name = cluster.get("name", "")
                if cluster_name and cluster_name.lower() in message_lower:
                    target_cluster = cluster
                    break

            if target_cluster:
                name = target_cluster.get("name", "unknown")
                status = target_cluster.get("status", "unknown")
                namespace = target_cluster.get("namespace", "unknown")
                region = target_cluster.get("region", "unknown")
                version = target_cluster.get("version", "N/A")
                created = target_cluster.get("created", "N/A")
                domain_prefix = target_cluster.get("domain_prefix", "N/A")
                progress = target_cluster.get("progress", 0)

                response = f"""## 🔍 Detailed Information: **{name}**

### 📊 Current Status
**State:** {status.upper()}"""

                if status == "uninstalling":
                    response += f"""

Your cluster **{name}** is being deleted right now. Here's what I know about it:

**Quick Info:**
• Running in the `{namespace}` namespace
• Located in {region}
• Was running OpenShift version {version}
• Created on {created}

**What's happening behind the scenes:**
Right now, the system is busy tearing everything down:
- Shutting down the OpenShift control plane
- Cleaning up all the AWS resources (EC2 instances, load balancers, etc.)
- Removing the networking setup (VPCs, subnets, security groups)
- Tidying up IAM roles and policies

**Want to check on the progress?**
Pop open the Terminal section and try these commands:
```
oc get rosacontrolplane -n {namespace}
oc describe rosacontrolplane {name} -n {namespace}
oc get events -n {namespace} --sort-by='.lastTimestamp'
```

**How long will this take?**
Usually about 10-20 minutes. Grab a coffee and it should be done when you get back! ☕"""

                elif status == "provisioning":
                    response += f"""
**Progress:** {progress}% complete

### ℹ️ Cluster Details
• **Namespace:** `{namespace}`
• **Region:** {region}
• **OpenShift Version:** {version}
• **Domain Prefix:** {domain_prefix}
• **Created:** {created}

### 🚀 Provisioning Stages
The cluster is being created. Typical stages:
1. **Network Setup** ({progress < 25 and '🔄 Current' or '✅ Complete'}) - Creating VPC, subnets, security groups
2. **IAM Configuration** ({25 <= progress < 50 and '🔄 Current' or progress >= 50 and '✅ Complete' or '⏳ Pending'}) - Setting up IAM roles and policies
3. **Control Plane** ({50 <= progress < 75 and '🔄 Current' or progress >= 75 and '✅ Complete' or '⏳ Pending'}) - Launching OpenShift control plane
4. **Node Provisioning** ({progress >= 75 and '🔄 Current' or '⏳ Pending'}) - Creating worker nodes

### 🔍 How to Monitor
```
oc get rosacontrolplane -n {namespace} -o yaml
oc describe rosacontrolplane {name} -n {namespace}
```

### ⏱️ Expected Timeline
Cluster provisioning typically takes 30-45 minutes to complete."""

                elif status == "ready":
                    response += f"""

### ℹ️ Cluster Details
• **Namespace:** `{namespace}`
• **Region:** {region}
• **OpenShift Version:** {version}
• **Domain Prefix:** {domain_prefix}
• **Created:** {created}

### ✅ Cluster is Ready!
Your ROSA HCP cluster is fully provisioned and operational.

### 🔗 Access Information
You can access the cluster using:
```
oc get rosacontrolplane {name} -n {namespace} -o yaml
```

Look for the `oidcEndpointURL` and API server URL in the status section.

### 🛠️ Next Steps
• Configure node pools for workloads
• Set up application deployments
• Configure monitoring and logging
• Implement backup strategies"""

                else:
                    response += f"""

### ℹ️ Cluster Details
• **Namespace:** `{namespace}`
• **Region:** {region}
• **OpenShift Version:** {version}
• **Domain Prefix:** {domain_prefix}
• **Created:** {created}
• **Current Status:** {status}

### 🔍 Diagnostic Commands
```
oc get rosacontrolplane {name} -n {namespace}
oc describe rosacontrolplane {name} -n {namespace}
oc get events -n {namespace} --sort-by='.lastTimestamp'
```"""

                suggestions = ["Show me the logs", "What clusters are running?"]

        # Handle log requests
        elif "show" in message_lower and "log" in message_lower:
            # Find the most recent job related to any cluster
            recent_jobs = []
            for job_id, job_data in sorted(
                jobs.items(),
                key=lambda x: normalize_timestamp(x[1].get("created_at")),
                reverse=True,
            )[:10]:
                yaml_file = job_data.get("yaml_file", "")
                description = job_data.get("description", "")
                log_lines = job_data.get("logs", [])

                # Check if this job is related to the user's clusters
                for cluster in clusters_data:
                    cluster_name = cluster.get("name", "")
                    if cluster_name and (
                        cluster_name.lower() in yaml_file.lower()
                        or cluster_name.lower() in description.lower()
                    ):
                        recent_jobs.append(
                            {
                                "job_id": job_id,
                                "cluster_name": cluster_name,
                                "description": description,
                                "status": job_data.get("status", "unknown"),
                                "logs": (
                                    "\n".join(log_lines[-20:]) if log_lines else "No logs available"
                                ),
                                "created_at": job_data.get("created_at", ""),
                            }
                        )
                        break

            if recent_jobs:
                latest_job = recent_jobs[0]
                response = f"""**Logs for {latest_job['cluster_name']}**

**Job ID:** {latest_job['job_id']}
**Description:** {latest_job['description']}
**Status:** {latest_job['status']}
**Created:** {latest_job['created_at']}

**Recent Log Output:**
```
{latest_job['logs']}
```

You can view more details in the Task Detail section below."""
                suggestions = [
                    f"Tell me more about {latest_job['cluster_name']}",
                    "What clusters are running?",
                ]
            else:
                response = "I couldn't find any recent logs for your clusters. Logs will appear here when cluster operations (provisioning, deletion, etc.) are running."
                suggestions = ["What clusters are running?", "Provision new cluster"]

        # Handle provisioning questions
        elif (
            "provision" in message_lower
            or "create cluster" in message_lower
            or "how to" in message_lower
        ):
            response = """To provision a ROSA HCP cluster:

1. Click the "Provision" button in the Configuration section
2. Fill in the cluster details:
   - Cluster name
   - OpenShift version
   - Region
   - Instance type and replicas

3. Choose automation features:
   - Network automation (automatic VPC/subnet creation)
   - Role automation (automatic IAM role creation)

4. Review the generated YAML and click "Apply"

The cluster will be provisioned automatically!"""
            suggestions = ["What is network automation?", "What clusters are running?"]

        # Handle troubleshooting
        elif (
            "troubleshoot" in message_lower
            or "failed" in message_lower
            or "error" in message_lower
            or "problem" in message_lower
        ):
            # Check for failed clusters in the context
            failed_clusters = [
                c
                for c in clusters_data
                if c.get("status") in ["failed", "error", "provisioning-failed"]
            ]
            provisioning_clusters = [c for c in clusters_data if c.get("status") == "provisioning"]

            if failed_clusters:
                response = f"I found {len(failed_clusters)} failed cluster(s):\n\n"
                for cluster in failed_clusters:
                    name = cluster.get("name", "unknown")
                    status = cluster.get("status", "unknown")
                    namespace = cluster.get("namespace", "unknown")
                    response += f"**{name}** (Status: {status})\n"
                    response += f"Namespace: {namespace}\n\n"
                    response += "**Troubleshooting steps for this cluster:**\n"
                    response += f"1. Check rosa-creds-secret in namespace '{namespace}'\n"
                    response += f"2. View ROSANetwork status: `oc get rosanetwork -n {namespace}`\n"
                    response += (
                        f"3. View ROSARoleConfig status: `oc get rosaroleconfig -n {namespace}`\n"
                    )
                    response += f"4. Check ROSAControlPlane events: `oc describe rosacontrolplane -n {namespace}`\n"
                    response += f"5. View detailed logs in Recent Operations section\n\n"

                suggestions = ["What clusters are running?", "How to provision cluster?"]
            elif provisioning_clusters:
                response = (
                    f"I see {len(provisioning_clusters)} cluster(s) currently provisioning:\n\n"
                )
                for cluster in provisioning_clusters:
                    name = cluster.get("name", "unknown")
                    progress = cluster.get("progress", 0)
                    response += f"**{name}** - {progress}% complete\n\n"
                response += "Provisioning clusters are still in progress. If a cluster has been stuck for a long time:\n\n"
                response += "1. Check Recent Operations for detailed progress logs\n"
                response += (
                    "2. Verify ROSANetwork is Ready (network creation can take 5-10 minutes)\n"
                )
                response += (
                    "3. Verify ROSARoleConfig is Ready (role creation can take 2-3 minutes)\n"
                )
                response += "4. Check that rosa-creds-secret exists in the cluster namespace\n"
                suggestions = ["What clusters are running?", "Provision new cluster"]
            else:
                response = """I don't see any failed clusters in your environment.

If you're experiencing issues:

1. **Check cluster status**: View the CAPI-Managed ROSA HCP Clusters table
2. **View Recent Operations**: Check the Recent Operations section for error logs
3. **Common issues**:
   - Missing rosa-creds-secret → Verify it exists in both multicluster-engine and cluster namespace
   - Network not ready → ROSANetwork resource may still be provisioning
   - Role creation failed → Check AWS credentials and IAM permissions

4. **Refresh status**: Click the Refresh button to update cluster information"""
                suggestions = ["What clusters are running?", "How to provision cluster?"]

        # Handle ROSA/CAPI concept questions
        elif "what is rosa" in message_lower or "explain rosa" in message_lower:
            response = """ROSA (Red Hat OpenShift Service on AWS) is a fully-managed OpenShift service on AWS.

**ROSA HCP (Hosted Control Planes):**
- Control plane runs in Red Hat's AWS account
- You only pay for worker nodes
- Faster provisioning and scaling
- Lower cost than classic ROSA

**CAPI Integration:**
- This UI uses Cluster API (CAPI) to manage ROSA clusters
- Provides declarative cluster management via Kubernetes CRDs
- Enables GitOps-style cluster lifecycle management"""
            suggestions = ["How to provision cluster?", "What is network automation?"]

        elif "what is capi" in message_lower or "cluster api" in message_lower:
            response = """CAPI (Cluster API) is a Kubernetes project to bring declarative, Kubernetes-style APIs to cluster creation, configuration, and management.

**In this UI:**
- Manage ROSA HCP clusters using Kubernetes Custom Resources
- Automate networking (VPC, subnets) with ROSANetwork
- Automate IAM roles with ROSARoleConfig
- Full cluster lifecycle management

**Benefits:**
- GitOps-friendly workflow
- Declarative configuration
- Automated infrastructure provisioning"""
            suggestions = ["How to provision cluster?", "What clusters are running?"]

        elif "network automation" in message_lower or "rosanetwork" in message_lower:
            response = """Network Automation automatically creates AWS VPC and subnets for your ROSA cluster.

**What it does:**
- Creates VPC with specified CIDR block
- Creates public and private subnets across multiple AZs
- Sets up Internet Gateway and NAT Gateways
- Configures route tables

**Benefits:**
- No manual AWS console work
- Consistent network configuration
- Proper multi-AZ setup automatically

Enable it during provisioning by checking "Network Automation (ROSANetwork)"."""
            suggestions = ["What is role automation?", "How to provision cluster?"]

        elif "role automation" in message_lower or "rosaroleconfig" in message_lower:
            response = """Role Automation automatically creates required AWS IAM roles for your ROSA cluster.

**What it creates:**
- Account roles (installer, support, worker, control-plane)
- Operator roles (for AWS service integration)
- OIDC provider configuration

**Benefits:**
- No manual AWS IAM console work
- Correct permissions automatically
- Proper trust policies configured

Enable it during provisioning by checking "Role Automation (ROSARoleConfig)"."""
            suggestions = ["What is network automation?", "How to provision cluster?"]

        # Handle environment status questions
        elif (
            "environment status" in message_lower
            or "check environment" in message_lower
            or "environment ready" in message_lower
        ):
            # Check MCE/CAPI status
            response = "**Environment Status:**\n\n"
            response += "I can help you check:\n"
            response += (
                "• **CAPI/CAPA Configuration** - Click 'Verify' in the Configuration section\n"
            )
            response += (
                "• **Cluster Resources** - View ROSA HCP Clusters table for all cluster statuses\n"
            )
            response += "• **Recent Operations** - Check Task Summary for recent activity\n\n"
            response += "**Quick Actions:**\n"
            response += "• Verify environment is configured\n"
            response += "• View cluster status details\n"
            response += "• Check provisioning progress\n"
            suggestions = [
                "What clusters are running?",
                "Verify environment",
                "Provision new cluster",
            ]

        # Handle status/monitoring questions
        elif (
            "status" in message_lower or "monitoring" in message_lower or "how is" in message_lower
        ):
            if clusters_data:
                response = "Here's the current status of your clusters:\n\n"
                for cluster in clusters_data:
                    name = cluster.get("name", "unknown")
                    status = cluster.get("status", "unknown")
                    progress = cluster.get("progress")
                    response += f"• **{name}**: {status}"
                    if progress:
                        response += f" ({progress}% complete)"
                    response += "\n"
                response += (
                    "\nYou can see detailed status in the CAPI-Managed ROSA HCP Clusters table."
                )
                suggestions = ["Troubleshoot failed cluster", "Provision new cluster"]
            else:
                response = "You don't have any clusters to monitor yet. Provision a cluster to get started!"
                suggestions = ["How to provision cluster?"]

        # Handle specific cluster queries
        else:
            # Check if user is asking about a specific cluster
            cluster_match = None
            for cluster in clusters_data:
                cluster_name = cluster.get("name", "").lower()
                if cluster_name and cluster_name in message_lower:
                    cluster_match = cluster
                    break

            if cluster_match:
                name = cluster_match.get("name", "unknown")
                status = cluster_match.get("status", "unknown")
                namespace = cluster_match.get("namespace", "unknown")
                progress = cluster_match.get("progress")
                region = cluster_match.get("region", "N/A")
                version = cluster_match.get("version", "N/A")
                created = cluster_match.get("created", "N/A")

                response = f"## Cluster: **{name}**\n\n"
                response += f"**Status:** {status}"
                if progress:
                    response += f" ({progress}% complete)"
                response += f"\n\n"

                response += f"**Details:**\n"
                response += f"• **Namespace:** {namespace}\n"
                response += f"• **Region:** {region}\n"
                response += f"• **OpenShift Version:** {version}\n"
                response += f"• **Created:** {created}\n\n"

                if status == "provisioning":
                    response += "**Provisioning in progress...**\n\n"
                    response += "The cluster is being created. This typically takes:\n"
                    response += "• ROSANetwork: 5-10 minutes\n"
                    response += "• ROSARoleConfig: 2-3 minutes\n"
                    response += "• Control Plane: 10-15 minutes\n\n"
                    response += f"Check the Task Detail section for real-time progress logs."
                    suggestions = ["What clusters are running?", "How to troubleshoot?"]

                elif status in ["failed", "error", "provisioning-failed"]:
                    response += "**⚠️ This cluster has failed**\n\n"
                    response += "**Troubleshooting steps:**\n"
                    response += f"1. View logs in Task Detail section\n"
                    response += f"2. Check `oc describe rosacontrolplane {name} -n {namespace}`\n"
                    response += f"3. Verify rosa-creds-secret exists in {namespace}\n"
                    response += f"4. Check ROSANetwork and ROSARoleConfig status\n"
                    suggestions = ["Troubleshoot failed cluster", "Provision new cluster"]

                elif status == "ready":
                    response += "**✅ Cluster is ready to use!**\n\n"
                    response += f"You can access it via the OpenShift console or CLI."
                    suggestions = ["Provision new cluster", "What is ROSA HCP?"]
                else:
                    suggestions = ["What clusters are running?", "Provision new cluster"]

            # Default fallback
            else:
                response = """I can help you with:

• **Cluster Management**: Provision, list, monitor, and troubleshoot clusters
• **ROSA/CAPI Concepts**: Explain ROSA HCP, CAPI, network automation, role automation
• **Troubleshooting**: Help diagnose and fix cluster issues

What would you like to know?"""
                suggestions = [
                    "What clusters are running?",
                    "How to provision cluster?",
                    "What is ROSA HCP?",
                    "Troubleshoot failed cluster",
                ]

        return {"success": True, "response": response, "suggestions": suggestions}

    except Exception as e:
        import traceback

        print(f"❌ [AI-ASSISTANT] Error: {str(e)}")
        print(traceback.format_exc())
        return {
            "success": False,
            "response": "Sorry, I encountered an error processing your request. Please try again.",
            "suggestions": [],
        }
