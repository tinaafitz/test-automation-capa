"""
Agent Orchestration Service for CAPA Automation UI

This service manages Claude Code agent spawning for intelligent automation tasks:
- Explore Agent: Codebase intelligence for investigating failures
- Plan Agent: Smart configuration planning and validation
- General-Purpose Agent: Automated troubleshooting and fixes
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from anthropic import Anthropic
import os


class AgentOrchestrator:
    """
    Manages Claude Code agent spawning and coordination.

    This orchestrator uses the Claude Code Task tool to spawn specialized agents
    that can autonomously explore codebases, plan implementations, and troubleshoot issues.
    """

    def __init__(self):
        """Initialize the agent orchestrator with Claude API client."""
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")

        self.client = Anthropic(api_key=api_key)

        # Track active agent sessions
        self.active_agents: Dict[str, Dict[str, Any]] = {}

    async def spawn_explore_agent(
        self,
        prompt: str,
        thoroughness: str = "medium",
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Spawn an Explore agent to search codebase for patterns and investigate issues.

        The Explore agent is specialized for:
        - Finding provisioning failure patterns in templates/playbooks
        - Searching for similar issues in git history
        - Identifying breaking changes
        - Locating example configurations

        Args:
            prompt: Task description for the agent (e.g., "Find why cluster provision failed")
            thoroughness: Search depth - "quick", "medium", or "very thorough"
            context: Optional context (cluster name, error messages, etc.)

        Returns:
            Dict with agent_id, status, and findings

        Example:
            result = await orchestrator.spawn_explore_agent(
                prompt="Find why ROSA HCP cluster 'demo-01' provisioning failed",
                thoroughness="very thorough",
                context={"cluster_name": "demo-01", "error": "IAM role not found"}
            )
        """
        agent_id = str(uuid.uuid4())

        # Build enriched prompt with context
        enriched_prompt = self._build_explore_prompt(prompt, thoroughness, context)

        # Track agent session
        self.active_agents[agent_id] = {
            "agent_id": agent_id,
            "type": "explore",
            "status": "spawning",
            "prompt": enriched_prompt,
            "thoroughness": thoroughness,
            "started_at": datetime.now().isoformat(),
            "context": context or {}
        }

        try:
            # Spawn agent using Claude Code Task tool
            # Note: In Claude Code CLI, this would use the Task tool directly
            # For API integration, we simulate the agent pattern
            response = await self._execute_agent_task(
                agent_type="explore",
                prompt=enriched_prompt,
                thoroughness=thoroughness
            )

            # Update agent session with results
            self.active_agents[agent_id].update({
                "status": "completed",
                "completed_at": datetime.now().isoformat(),
                "findings": response.get("findings", []),
                "recommendations": response.get("recommendations", []),
                "files_examined": response.get("files_examined", [])
            })

            return self.active_agents[agent_id]

        except Exception as e:
            self.active_agents[agent_id].update({
                "status": "failed",
                "error": str(e),
                "completed_at": datetime.now().isoformat()
            })
            raise

    async def spawn_plan_agent(
        self,
        prompt: str,
        requirements: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Spawn a Plan agent to design cluster configurations and implementation strategies.

        The Plan agent is specialized for:
        - Designing optimal cluster configurations
        - Checking feature compatibility
        - Validating settings against known issues
        - Recommending best practices

        Args:
            prompt: Planning task (e.g., "Design a production ROSA cluster with FIPS mode")
            requirements: Optional dict of requirements (version, region, features, etc.)

        Returns:
            Dict with agent_id, status, and implementation plan

        Example:
            result = await orchestrator.spawn_plan_agent(
                prompt="Plan a production ROSA HCP cluster with FIPS and log forwarding",
                requirements={
                    "openshift_version": "4.14",
                    "region": "us-east-1",
                    "fips": True,
                    "log_forwarding": True
                }
            )
        """
        agent_id = str(uuid.uuid4())

        # Build enriched prompt with requirements
        enriched_prompt = self._build_plan_prompt(prompt, requirements)

        # Track agent session
        self.active_agents[agent_id] = {
            "agent_id": agent_id,
            "type": "plan",
            "status": "spawning",
            "prompt": enriched_prompt,
            "started_at": datetime.now().isoformat(),
            "requirements": requirements or {}
        }

        try:
            # Spawn agent using Claude Code Task tool
            response = await self._execute_agent_task(
                agent_type="plan",
                prompt=enriched_prompt,
                requirements=requirements
            )

            # Update agent session with plan
            self.active_agents[agent_id].update({
                "status": "completed",
                "completed_at": datetime.now().isoformat(),
                "plan": response.get("plan", {}),
                "configuration": response.get("configuration", {}),
                "validation_results": response.get("validation_results", []),
                "warnings": response.get("warnings", [])
            })

            return self.active_agents[agent_id]

        except Exception as e:
            self.active_agents[agent_id].update({
                "status": "failed",
                "error": str(e),
                "completed_at": datetime.now().isoformat()
            })
            raise

    async def spawn_general_agent(
        self,
        prompt: str,
        task_type: str = "troubleshoot",
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Spawn a General-Purpose agent for complex multi-step automation tasks.

        The General-Purpose agent is specialized for:
        - Diagnosing provisioning failures
        - Identifying root causes
        - Generating automated fixes
        - Retrying operations with corrections

        Args:
            prompt: Task description (e.g., "Fix failed cluster provision for demo-01")
            task_type: Type of task - "troubleshoot", "fix", "diagnose", "automate"
            context: Optional context (logs, error messages, cluster state, etc.)

        Returns:
            Dict with agent_id, status, diagnosis, and fix recommendations

        Example:
            result = await orchestrator.spawn_general_agent(
                prompt="Diagnose and fix cluster provision failure for demo-01",
                task_type="fix",
                context={
                    "cluster_name": "demo-01",
                    "error_logs": "...",
                    "playbook": "create_rosa_hcp_cluster.yml"
                }
            )
        """
        agent_id = str(uuid.uuid4())

        # Build enriched prompt with context
        enriched_prompt = self._build_general_prompt(prompt, task_type, context)

        # Track agent session
        self.active_agents[agent_id] = {
            "agent_id": agent_id,
            "type": "general",
            "status": "spawning",
            "prompt": enriched_prompt,
            "task_type": task_type,
            "started_at": datetime.now().isoformat(),
            "context": context or {}
        }

        try:
            # Spawn agent using Claude Code Task tool
            response = await self._execute_agent_task(
                agent_type="general",
                prompt=enriched_prompt,
                task_type=task_type,
                context=context
            )

            # Update agent session with results
            self.active_agents[agent_id].update({
                "status": "completed",
                "completed_at": datetime.now().isoformat(),
                "diagnosis": response.get("diagnosis", ""),
                "root_cause": response.get("root_cause", ""),
                "fix_recommendations": response.get("fix_recommendations", []),
                "automated_fixes": response.get("automated_fixes", []),
                "next_steps": response.get("next_steps", [])
            })

            return self.active_agents[agent_id]

        except Exception as e:
            self.active_agents[agent_id].update({
                "status": "failed",
                "error": str(e),
                "completed_at": datetime.now().isoformat()
            })
            raise

    def get_agent_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the current status of an agent session.

        Args:
            agent_id: UUID of the agent session

        Returns:
            Dict with agent status and results, or None if not found
        """
        return self.active_agents.get(agent_id)

    def list_active_agents(self) -> List[Dict[str, Any]]:
        """
        List all currently active agent sessions.

        Returns:
            List of agent session dicts
        """
        return list(self.active_agents.values())

    # Private helper methods

    def _build_explore_prompt(
        self,
        prompt: str,
        thoroughness: str,
        context: Optional[Dict[str, Any]]
    ) -> str:
        """Build enriched prompt for Explore agent."""
        context_str = ""
        if context:
            context_str = f"\n\nContext:\n{json.dumps(context, indent=2)}"

        return f"""
You are an Explore agent for the CAPA Automation UI codebase.

Task: {prompt}

Thoroughness Level: {thoroughness}
{context_str}

Your objectives:
1. Search the codebase for relevant patterns, configurations, and failures
2. Examine templates, playbooks, and configuration files
3. Investigate git history for similar issues or breaking changes
4. Identify root causes and patterns

Please provide:
- List of files examined
- Key findings from the codebase
- Patterns or issues discovered
- Recommendations for next steps
"""

    def _build_plan_prompt(
        self,
        prompt: str,
        requirements: Optional[Dict[str, Any]]
    ) -> str:
        """Build enriched prompt for Plan agent."""
        requirements_str = ""
        if requirements:
            requirements_str = f"\n\nRequirements:\n{json.dumps(requirements, indent=2)}"

        return f"""
You are a Plan agent for the CAPA Automation UI.

Task: {prompt}
{requirements_str}

Your objectives:
1. Design an optimal cluster configuration
2. Validate compatibility of requested features
3. Check for known issues or conflicts
4. Recommend best practices and settings

Please provide:
- Detailed implementation plan
- Recommended configuration
- Validation results (compatibility checks)
- Warnings or potential issues
- Best practices to follow
"""

    def _build_general_prompt(
        self,
        prompt: str,
        task_type: str,
        context: Optional[Dict[str, Any]]
    ) -> str:
        """Build enriched prompt for General-Purpose agent."""
        context_str = ""
        if context:
            context_str = f"\n\nContext:\n{json.dumps(context, indent=2)}"

        return f"""
You are a General-Purpose agent for the CAPA Automation UI.

Task Type: {task_type}
Task: {prompt}
{context_str}

Your objectives:
1. Diagnose the issue thoroughly
2. Identify the root cause
3. Generate specific fix recommendations
4. Propose automated fixes if possible

Please provide:
- Diagnosis of the issue
- Root cause analysis
- Fix recommendations (step-by-step)
- Automated fixes that can be applied
- Next steps for resolution
"""

    async def _execute_agent_task(
        self,
        agent_type: str,
        prompt: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute an agent task using Claude API.

        Note: In a full Claude Code CLI environment, this would use the Task tool.
        For API integration, we simulate the agent pattern with structured responses.

        Args:
            agent_type: Type of agent (explore, plan, general)
            prompt: Enriched prompt for the agent
            **kwargs: Additional context

        Returns:
            Dict with agent results
        """
        # Build system prompt based on agent type
        system_prompts = {
            "explore": "You are an expert codebase explorer. Analyze code, find patterns, and investigate issues systematically.",
            "plan": "You are an expert software architect. Design robust solutions, validate configurations, and recommend best practices.",
            "general": "You are an expert troubleshooter. Diagnose problems, identify root causes, and generate automated fixes."
        }

        system_prompt = system_prompts.get(agent_type, system_prompts["general"])

        # Call Claude API with structured output format
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-5@20250929",
                max_tokens=4096,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            # Parse response content
            content = response.content[0].text

            # Structure the response based on agent type
            if agent_type == "explore":
                return self._parse_explore_response(content)
            elif agent_type == "plan":
                return self._parse_plan_response(content)
            else:  # general
                return self._parse_general_response(content)

        except Exception as e:
            raise Exception(f"Agent execution failed: {str(e)}")

    def _parse_explore_response(self, content: str) -> Dict[str, Any]:
        """Parse Explore agent response into structured format."""
        return {
            "findings": self._extract_section(content, "findings"),
            "recommendations": self._extract_section(content, "recommendations"),
            "files_examined": self._extract_section(content, "files examined"),
            "raw_output": content
        }

    def _parse_plan_response(self, content: str) -> Dict[str, Any]:
        """Parse Plan agent response into structured format."""
        return {
            "plan": self._extract_section(content, "plan"),
            "configuration": self._extract_section(content, "configuration"),
            "validation_results": self._extract_section(content, "validation"),
            "warnings": self._extract_section(content, "warnings"),
            "raw_output": content
        }

    def _parse_general_response(self, content: str) -> Dict[str, Any]:
        """Parse General-Purpose agent response into structured format."""
        return {
            "diagnosis": self._extract_section(content, "diagnosis"),
            "root_cause": self._extract_section(content, "root cause"),
            "fix_recommendations": self._extract_section(content, "fix recommendations"),
            "automated_fixes": self._extract_section(content, "automated fixes"),
            "next_steps": self._extract_section(content, "next steps"),
            "raw_output": content
        }

    def _extract_section(self, content: str, section_name: str) -> List[str]:
        """Extract a section from agent response content."""
        # Simple extraction - look for section headers and extract bullet points
        lines = content.lower().split('\n')
        section_lines = []
        in_section = False

        for line in lines:
            if section_name.lower() in line and (':' in line or '-' in line):
                in_section = True
                continue

            if in_section:
                if line.strip().startswith(('-', '•', '*', '1.', '2.', '3.')):
                    section_lines.append(line.strip())
                elif line.strip() and not line.strip().startswith(('-', '•', '*')) and len(section_lines) > 0:
                    # End of section
                    break

        return section_lines if section_lines else [content]  # Return full content if no structured section found


# Singleton instance
_agent_orchestrator = None

def get_agent_orchestrator() -> AgentOrchestrator:
    """Get or create the global AgentOrchestrator instance."""
    global _agent_orchestrator
    if _agent_orchestrator is None:
        _agent_orchestrator = AgentOrchestrator()
    return _agent_orchestrator
