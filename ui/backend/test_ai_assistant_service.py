"""Tests for AIAssistantService."""

from unittest.mock import patch, MagicMock, AsyncMock

import pytest

# Mock anthropic before importing the service
import sys
mock_anthropic = MagicMock()
sys.modules["anthropic"] = mock_anthropic

from ai_assistant_service import AIAssistantService


@pytest.fixture
def ai_svc():
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        svc = AIAssistantService()
        svc.client = MagicMock()
        return svc


class TestAIAssistantChat:
    @pytest.mark.asyncio
    async def test_chat_success(self, ai_svc):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="You have 1 cluster: test-cluster")]
        ai_svc.client.messages.create.return_value = mock_response

        result = await ai_svc.chat(
            message="What clusters are running?",
            context={"clusters": [{"name": "test-cluster", "namespace": "ns", "status": "ready"}]},
        )
        assert "response" in result
        assert "suggestions" in result
        assert "test-cluster" in result["response"]

    @pytest.mark.asyncio
    async def test_chat_error(self, ai_svc):
        ai_svc.client.messages.create.side_effect = Exception("API error")

        result = await ai_svc.chat(
            message="test",
            context={},
        )
        assert "error" in result["response"].lower()

    @pytest.mark.asyncio
    async def test_chat_with_history(self, ai_svc):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Here's the info")]
        ai_svc.client.messages.create.return_value = mock_response

        result = await ai_svc.chat(
            message="More details",
            context={},
            history=[
                {"role": "user", "content": "What clusters?"},
                {"role": "assistant", "content": "You have 1 cluster"},
            ],
        )
        assert "response" in result
        # Should include history in messages
        call_args = ai_svc.client.messages.create.call_args
        messages = call_args.kwargs.get("messages", [])
        assert len(messages) == 3  # 2 history + 1 current

    @pytest.mark.asyncio
    async def test_chat_no_clusters(self, ai_svc):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="No clusters running")]
        ai_svc.client.messages.create.return_value = mock_response

        result = await ai_svc.chat(
            message="What clusters?",
            context={"clusters": []},
        )
        assert "response" in result


class TestBuildContextSummary:
    def test_with_clusters(self, ai_svc):
        context = {
            "clusters": [
                {"name": "c1", "namespace": "ns1", "status": "ready"},
                {"name": "c2", "namespace": "ns2", "status": "installing"},
            ]
        }
        summary = ai_svc._build_context_summary(context)
        assert "c1" in summary
        assert "c2" in summary
        assert "Active clusters: 2" in summary

    def test_no_clusters(self, ai_svc):
        summary = ai_svc._build_context_summary({"clusters": []})
        assert "No active clusters" in summary

    def test_with_job_logs(self, ai_svc):
        context = {
            "clusters": [],
            "job_logs": [
                {"job_id": "j1", "status": "failed", "cluster_name": "c1", "logs": "error line\n"}
            ],
        }
        summary = ai_svc._build_context_summary(context)
        assert "j1" in summary
        assert "error line" in summary

    def test_with_resource_status(self, ai_svc):
        context = {
            "clusters": [],
            "resource_status": {"ROSANetwork": "ready"},
        }
        summary = ai_svc._build_context_summary(context)
        assert "ROSANetwork" in summary


class TestExtractSuggestions:
    def test_cluster_suggestions(self, ai_svc):
        context = {"clusters": [{"name": "test-c"}]}
        suggestions = ai_svc._extract_suggestions("Here are your clusters running", context)
        assert len(suggestions) > 0

    def test_provision_suggestion(self, ai_svc):
        suggestions = ai_svc._extract_suggestions("You can provision a new cluster", {})
        assert any("provision" in s.lower() for s in suggestions)

    def test_error_suggestion(self, ai_svc):
        suggestions = ai_svc._extract_suggestions("The cluster failed with error", {})
        assert any("error" in s.lower() or "troubleshoot" in s.lower() for s in suggestions)

    def test_max_three_suggestions(self, ai_svc):
        suggestions = ai_svc._extract_suggestions(
            "cluster failed with error, provision delete status health",
            {"clusters": [{"name": "c1"}]},
        )
        assert len(suggestions) <= 3
