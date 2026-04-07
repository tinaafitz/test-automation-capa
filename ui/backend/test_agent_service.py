"""Tests for AgentOrchestrator service."""

import sys
from unittest.mock import patch, MagicMock

import pytest

# Mock anthropic before importing — use a fresh mock each import
if "anthropic" not in sys.modules or isinstance(sys.modules["anthropic"], MagicMock):
    sys.modules["anthropic"] = MagicMock()

from agent_service import AgentOrchestrator, get_agent_orchestrator


class TestAgentOrchestratorInit:
    def test_init_with_key(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            orch = AgentOrchestrator()
            assert orch.active_agents == {}

    def test_init_without_key(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                AgentOrchestrator()


class TestBuildPrompts:
    @pytest.fixture
    def orch(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            return AgentOrchestrator()

    def test_build_explore_prompt(self, orch):
        prompt = orch._build_explore_prompt("find errors", "medium", {"cluster": "c1"})
        assert "find errors" in prompt
        assert "medium" in prompt.lower()
        assert "c1" in prompt

    def test_build_explore_prompt_no_context(self, orch):
        prompt = orch._build_explore_prompt("find errors", "quick", None)
        assert "find errors" in prompt

    def test_build_plan_prompt(self, orch):
        prompt = orch._build_plan_prompt("design cluster", {"version": "4.14"})
        assert "design cluster" in prompt
        assert "4.14" in prompt

    def test_build_plan_prompt_no_requirements(self, orch):
        prompt = orch._build_plan_prompt("design cluster", None)
        assert "design cluster" in prompt

    def test_build_general_prompt(self, orch):
        prompt = orch._build_general_prompt("fix issue", "troubleshoot", {"error": "timeout"})
        assert "fix issue" in prompt
        assert "troubleshoot" in prompt.lower()

    def test_build_general_prompt_no_context(self, orch):
        prompt = orch._build_general_prompt("fix issue", "diagnose", None)
        assert "fix issue" in prompt


class TestParseResponses:
    @pytest.fixture
    def orch(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            return AgentOrchestrator()

    def test_parse_explore_response(self, orch):
        content = "## Findings:\n- Found pattern A\n- Found pattern B\n## Recommendations:\n- Fix it"
        result = orch._parse_explore_response(content)
        assert "findings" in result
        assert "recommendations" in result

    def test_parse_plan_response(self, orch):
        content = "## Plan:\n- Step 1\n## Configuration:\n- setting=val"
        result = orch._parse_plan_response(content)
        assert "plan" in result
        assert "configuration" in result

    def test_parse_general_response(self, orch):
        content = "## Diagnosis:\n- Root cause found\n## Root cause:\n- Missing IAM"
        result = orch._parse_general_response(content)
        assert "diagnosis" in result
        assert "root_cause" in result

    def test_extract_section_not_found(self, orch):
        content = "Just some text without sections"
        result = orch._extract_section(content, "findings")
        assert len(result) == 1  # Returns full content


class TestAgentStatus:
    @pytest.fixture
    def orch(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            return AgentOrchestrator()

    def test_get_agent_status_not_found(self, orch):
        assert orch.get_agent_status("nonexistent") is None

    def test_list_active_agents_empty(self, orch):
        assert orch.list_active_agents() == []

    def test_list_active_agents_with_agents(self, orch):
        orch.active_agents["a1"] = {"agent_id": "a1", "type": "explore"}
        orch.active_agents["a2"] = {"agent_id": "a2", "type": "plan"}
        agents = orch.list_active_agents()
        assert len(agents) == 2


class TestSpawnAgents:
    def _make_orch(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            orch = AgentOrchestrator()
            # Replace client with a fresh mock to avoid side_effect leaking between tests
            orch.client = MagicMock()
            return orch

    @pytest.mark.asyncio
    async def test_spawn_explore_success(self):
        orch = self._make_orch()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="## Findings:\n- Found issue\n## Recommendations:\n- Fix it")]
        orch.client.messages.create.return_value = mock_response

        result = await orch.spawn_explore_agent("find errors", "quick")
        assert result["status"] == "completed"
        assert result["type"] == "explore"

    @pytest.mark.asyncio
    async def test_spawn_explore_failure(self):
        orch = self._make_orch()
        orch.client.messages.create.side_effect = Exception("API error")
        with pytest.raises(Exception, match="API error"):
            await orch.spawn_explore_agent("find errors", "quick")

    @pytest.mark.asyncio
    async def test_spawn_plan_success(self):
        orch = self._make_orch()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="## Plan:\n- Step 1")]
        orch.client.messages.create.return_value = mock_response

        result = await orch.spawn_plan_agent("design cluster")
        assert result["status"] == "completed"
        assert result["type"] == "plan"

    @pytest.mark.asyncio
    async def test_spawn_general_success(self):
        orch = self._make_orch()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="## Diagnosis:\n- Root cause")]
        orch.client.messages.create.return_value = mock_response

        result = await orch.spawn_general_agent("fix issue", "troubleshoot")
        assert result["status"] == "completed"
        assert result["type"] == "general"


class TestGetAgentOrchestrator:
    def test_singleton(self):
        import agent_service
        agent_service._agent_orchestrator = None
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            orch1 = get_agent_orchestrator()
            orch2 = get_agent_orchestrator()
            assert orch1 is orch2
        agent_service._agent_orchestrator = None  # Reset for other tests
