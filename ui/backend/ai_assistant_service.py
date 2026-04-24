"""
AI Assistant Service for ROSA Cluster Management
Integrates with Claude API to provide intelligent assistance with tool use
"""

import json
import os
import anthropic
from typing import List, Dict, Any

from tool_functions import TOOL_DEFINITIONS, TOOL_DISPATCH

MAX_TOOL_CALLS = 5


class AIAssistantService:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

        self.system_prompt = """You are an AI assistant specialized in Red Hat OpenShift Service on AWS (ROSA) and Cluster API (CAPI) operations.

You have access to tools that let you query live cluster data, AWS resources, Kubernetes resources, and a knowledge base of known issues. USE THESE TOOLS to answer questions with real, current data rather than relying solely on context provided in the message.

When a user asks about clusters, resources, or issues:
1. Call the appropriate tool(s) to get live data
2. Interpret the results and present them clearly
3. Offer relevant follow-up suggestions

Your capabilities via tools:
- List and inspect ROSA HCP clusters (capa_list_clusters, capa_cluster_status)
- Query AWS resource usage and details (capa_aws_resource_usage, capa_aws_resource_details)
- Check CloudFormation stack status (capa_cloudformation_stack_status)
- Query Kubernetes resources and events (capa_k8s_get_resource, capa_k8s_events)
- Search known issues and remediation history (capa_search_known_issues, capa_remediation_history)
- View AI agent learning statistics (capa_learning_stats)
- Run diagnostics on cluster issues (capa_diagnose_issue)

When analyzing failed clusters:
1. Read the actual job logs provided in the context
2. Identify the specific error (credentials, network timeout, AWS API error, IAM permissions, etc.)
3. Provide the exact fix for that specific error
4. Use tools to gather additional context (e.g., check CF stack status, search known issues)

Be specific, cite actual data from tool results, and give actionable recommendations."""

    async def chat(
        self, message: str, context: Dict[str, Any], history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Process a chat message with cluster context and tool use.

        Args:
            message: User's message
            context: Current cluster state and environment info
            history: Previous conversation messages

        Returns:
            Response with assistant message and optional suggestions
        """
        context_summary = self._build_context_summary(context)

        messages = []
        if history:
            for msg in history[-5:]:
                messages.append({"role": msg.get("role"), "content": msg.get("content")})

        user_prompt = f"{context_summary}\n\nUser question: {message}"
        messages.append({"role": "user", "content": user_prompt})

        try:
            tool_call_count = 0

            while True:
                response = self.client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=4096,
                    system=self.system_prompt,
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                )

                if response.stop_reason == "tool_use":
                    messages.append({"role": "assistant", "content": response.content})

                    tool_results = []
                    for block in response.content:
                        if block.type == "tool_use":
                            tool_call_count += 1
                            if tool_call_count > MAX_TOOL_CALLS:
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": json.dumps({"error": "Tool call limit reached"}),
                                    "is_error": True,
                                })
                                continue

                            result = await self._execute_tool(block.name, block.input)
                            print(f"🔧 Tool call: {block.name}({block.input}) -> {len(result)} chars")
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result,
                            })

                    messages.append({"role": "user", "content": tool_results})

                    if tool_call_count > MAX_TOOL_CALLS:
                        break
                else:
                    break

            text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text

            suggestions = self._extract_suggestions(text, context)
            return {"response": text, "suggestions": suggestions}

        except Exception as e:
            return {
                "response": f"I encountered an error: {str(e)}. Please try again or contact support.",
                "suggestions": [],
            }

    async def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        func = TOOL_DISPATCH.get(tool_name)
        if not func:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        try:
            return await func(**tool_input)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _build_context_summary(self, context: Dict[str, Any]) -> str:
        """Build a summary of the current cluster context"""
        summary_parts = ["Current cluster context:"]

        clusters = context.get("clusters", [])
        print(f"🔍 DEBUG: Clusters from context: {clusters}")  # DEBUG
        if clusters:
            summary_parts.append(f"\nActive clusters: {len(clusters)}")
            for cluster in clusters[:5]:  # First 5 clusters
                status = cluster.get("status", "unknown")
                name = cluster.get("name", "unnamed")
                namespace = cluster.get("namespace", "unknown")
                print(
                    f"🔍 DEBUG: Processing cluster - name: {name}, namespace: {namespace}, status: {status}"
                )  # DEBUG
                summary_parts.append(f"  - {name} (namespace: {namespace}): {status}")
        else:
            summary_parts.append("\nNo active clusters")
            print("🔍 DEBUG: No clusters found in context")  # DEBUG

        # Add job logs if available (for failed clusters)
        job_logs = context.get("job_logs", [])
        if job_logs:
            summary_parts.append("\n\nRecent provisioning job logs:")
            for log_entry in job_logs[:3]:  # Last 3 jobs
                job_id = log_entry.get("job_id", "unknown")
                status = log_entry.get("status", "unknown")
                cluster_name = log_entry.get("cluster_name", "unknown")
                logs = log_entry.get("logs", "")

                summary_parts.append(
                    f"\nJob {job_id} for cluster '{cluster_name}' - Status: {status}"
                )
                if logs:
                    # Include last 20 lines of logs for context
                    log_lines = logs.split("\n")[-20:]
                    summary_parts.append("Log excerpt:")
                    summary_parts.append("\n".join(log_lines))

        # Add resource status if available
        resource_status = context.get("resource_status", {})
        if resource_status:
            summary_parts.append("\n\nCluster Resource Status:")
            for resource_type, resources in resource_status.items():
                summary_parts.append(f"\n{resource_type}:")
                summary_parts.append(resources)

        return "\n".join(summary_parts)

    def _extract_suggestions(self, message: str, context: Dict[str, Any]) -> List[str]:
        """Extract actionable suggestions from the response"""
        suggestions = []

        clusters = context.get("clusters", [])

        # If we just listed clusters, offer to provide more details
        if clusters and ("cluster" in message.lower() or "running" in message.lower()):
            suggestions.append("What is the cluster name?")
            if len(clusters) > 0:
                cluster_name = clusters[0].get("name", "cluster")
                suggestions.append(f"Tell me more about {cluster_name}")
            suggestions.append("Provision new cluster")

        # Common patterns that should become clickable actions
        if "provision" in message.lower():
            suggestions.append("How do I provision a new cluster?")

        if "delete" in message.lower() or "remove" in message.lower():
            suggestions.append("How do I safely delete a cluster?")

        if "status" in message.lower() or "health" in message.lower():
            suggestions.append("Check cluster health status")

        if "error" in message.lower() or "fail" in message.lower():
            suggestions.append("Show me cluster error logs")
            suggestions.append("Troubleshoot failed cluster")

        # If showing cluster details, ask if they want to do something with it
        if any(c.get("name", "") in message for c in clusters):
            suggestions.append("What can I do with this cluster?")

        return suggestions[:3]  # Max 3 suggestions


# FastAPI endpoint integration example
"""
Add to app.py:

from ai_assistant_service import AIAssistantService

ai_service = AIAssistantService()

@app.post("/api/ai-assistant/chat")
async def ai_assistant_chat(request: dict):
    '''AI assistant chat endpoint'''
    try:
        message = request.get("message")
        context = request.get("context", {})
        history = request.get("history", [])

        response = await ai_service.chat(message, context, history)
        return response
    except Exception as e:
        return {"error": str(e)}, 500
"""
