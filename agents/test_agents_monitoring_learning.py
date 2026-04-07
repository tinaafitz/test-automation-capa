#!/usr/bin/env python3
"""
Extended tests for MonitoringAgent, LearningAgent, and BaseAgent.
"""

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.monitoring_agent import MonitoringAgent, IssueState, TrackedIssue
from agents.learning_agent import LearningAgent
from agents.base_agent import BaseAgent


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory with knowledge base."""
    kb_dir = tmp_path / "agents" / "knowledge_base"
    kb_dir.mkdir(parents=True)

    known_issues = {
        "version": "1.0.0",
        "patterns": [
            {
                "type": "rosanetwork_stuck_deletion",
                "pattern": "FAILED - RETRYING.*(?:rosanetwork|ROSANetwork).*(?:delet|still exists)",
                "severity": "high",
                "auto_fix": True,
            },
            {
                "type": "rosacontrolplane_stuck_deletion",
                "pattern": "FAILED - RETRYING.*(?:rosacontrolplane|ROSAControlPlane).*(?:delet|still exists)",
                "severity": "high",
                "auto_fix": True,
            },
            {
                "type": "rosaroleconfig_stuck_deletion",
                "pattern": "FAILED - RETRYING.*(?:rosaroleconfig|ROSARoleConfig).*(?:delet|still exists)",
                "severity": "high",
                "auto_fix": True,
            },
            {
                "type": "cloudformation_deletion_failure",
                "pattern": "CloudFormation stack DELETE_FAILED:.*",
                "severity": "high",
                "auto_fix": True,
            },
            {
                "type": "ocm_auth_failure",
                "pattern": ".*(ocm|openshift cluster manager).*(401|403|unauthorized).*",
                "severity": "medium",
                "auto_fix": True,
            },
            {
                "type": "capi_not_installed",
                "pattern": ".*(capi|cluster.*api).*(not found|does not exist).*",
                "severity": "high",
                "auto_fix": False,
            },
            {
                "type": "api_rate_limit",
                "pattern": "^(?!.*(?:Pattern matched|Issue detected)).*(?:HTTP.*429|rate.limit.exceed).*",
                "severity": "low",
                "auto_fix": True,
            },
            {
                "type": "repeated_timeouts",
                "pattern": "^(?!.*(?:Pattern matched|Issue detected)).*(?:timed?.out|timeout.*exceeded).*",
                "severity": "medium",
                "auto_fix": False,
            },
        ],
    }
    with open(kb_dir / "known_issues.json", "w") as f:
        json.dump(known_issues, f)

    return tmp_path


@pytest.fixture
def monitor(tmp_project):
    return MonitoringAgent(tmp_project, enabled=True, verbose=False)


@pytest.fixture
def learner(tmp_project):
    return LearningAgent(tmp_project, enabled=True, verbose=False)


# ---------------------------------------------------------------------------
# MonitoringAgent tests
# ---------------------------------------------------------------------------

class TestMonitoringDetectIssue:
    def test_detect_rosanetwork_stuck(self, monitor):
        line = "FAILED - RETRYING: ROSANetwork my-net still exists after deletion"
        issue = monitor._detect_issue(line)
        assert issue is not None
        assert issue["type"] == "rosanetwork_stuck_deletion"

    def test_detect_rosacontrolplane_stuck(self, monitor):
        line = "FAILED - RETRYING: ROSAControlPlane my-cp deletion stuck"
        issue = monitor._detect_issue(line)
        assert issue is not None
        assert issue["type"] == "rosacontrolplane_stuck_deletion"

    def test_detect_rosaroleconfig_stuck(self, monitor):
        line = "FAILED - RETRYING: ROSARoleConfig my-rc still exists"
        issue = monitor._detect_issue(line)
        assert issue is not None
        assert issue["type"] == "rosaroleconfig_stuck_deletion"

    def test_detect_cloudformation_failure(self, monitor):
        line = "CloudFormation stack DELETE_FAILED: my-stack"
        issue = monitor._detect_issue(line)
        assert issue is not None
        assert issue["type"] == "cloudformation_deletion_failure"

    def test_detect_ocm_auth(self, monitor):
        line = "ocm API returned 401 unauthorized"
        issue = monitor._detect_issue(line)
        assert issue is not None
        assert issue["type"] == "ocm_auth_failure"

    def test_detect_rate_limit(self, monitor):
        line = "HTTP 429 rate limit exceeded for API call"
        issue = monitor._detect_issue(line)
        assert issue is not None
        assert issue["type"] == "api_rate_limit"

    def test_no_match(self, monitor):
        line = "Everything is fine"
        issue = monitor._detect_issue(line)
        assert issue is None


class TestMonitoringStatistics:
    def test_empty_stats(self, monitor):
        stats = monitor.get_statistics()
        assert stats["patterns_detected"] == 0
        assert stats["interventions_performed"] == 0
        assert stats["tracked_issues"] == {}

    def test_stats_after_detection(self, monitor):
        monitor.patterns_detected.append({"type": "test"})
        monitor.current_task = "Test task"
        stats = monitor.get_statistics()
        assert stats["patterns_detected"] == 1
        assert stats["current_task"] == "Test task"


class TestMonitoringReset:
    def test_reset_clears_state(self, monitor):
        monitor.line_buffer.append("test")
        monitor.patterns_detected.append({"type": "test"})
        monitor.current_task = "task"
        monitor.waiting_for_resource = "ROSANetwork"
        monitor._tracked_issues["test:key"] = TrackedIssue("test", "key", {})
        monitor._structured_context["resource_name"] = "test"

        monitor.reset()

        assert len(monitor.line_buffer) == 0
        assert len(monitor.patterns_detected) == 0
        assert monitor.current_task is None
        assert monitor.waiting_for_resource is None
        assert len(monitor._tracked_issues) == 0
        assert len(monitor._structured_context) == 0


class TestMonitoringProcessLine:
    def test_disabled(self, tmp_project):
        agent = MonitoringAgent(tmp_project, enabled=False)
        assert agent.process_line("anything") is False

    def test_updates_task_context(self, monitor):
        monitor.process_line("TASK [Wait for ROSANetwork deletion]")
        assert monitor.current_task == "Wait for ROSANetwork deletion"

    def test_updates_waiting_for(self, monitor):
        monitor.process_line("Waiting for ROSANetwork to be deleted")
        assert monitor.waiting_for_resource == "ROSANetwork"

    def test_waiting_for_controlplane(self, monitor):
        monitor.process_line("waiting for ROSAControlPlane deletion")
        assert monitor.waiting_for_resource == "ROSAControlPlane"

    def test_waiting_for_roleconfig(self, monitor):
        monitor.process_line("Waiting for ROSARoleConfig to finish")
        assert monitor.waiting_for_resource == "ROSARoleConfig"

    def test_triggers_callback(self, monitor):
        callback = MagicMock()
        monitor.set_issue_callback(callback)
        line = "CloudFormation stack DELETE_FAILED: my-stack"
        monitor.process_line(line)
        callback.assert_called_once()

    def test_no_callback_without_auto_fix(self, monitor):
        callback = MagicMock()
        monitor.set_issue_callback(callback)
        # capi_not_installed has auto_fix=False
        line = "capi controller not found in cluster"
        monitor.process_line(line)
        callback.assert_not_called()

    def test_buffer_limit(self, monitor):
        for i in range(60):
            monitor.process_line(f"line {i}")
        assert len(monitor.line_buffer) == 50


class TestMonitoringStructuredContext:
    def test_parse_agent_context(self, monitor):
        line = '#AGENT_CONTEXT: resource_name=my-net namespace=my-ns resource_type=rosanetwork'
        monitor._parse_structured_context(line)
        assert monitor._structured_context["resource_name"] == "my-net"
        assert monitor._structured_context["namespace"] == "my-ns"

    def test_context_in_ansible_debug(self, monitor):
        line = '"msg": "#AGENT_CONTEXT: resource_name=test namespace=ns"'
        monitor._parse_structured_context(line)
        assert monitor._structured_context["resource_name"] == "test"


class TestMonitoringIssueStateMachine:
    def test_mark_resolved(self, monitor):
        tracked = TrackedIssue("test", "key", {})
        monitor._tracked_issues["test:key"] = tracked
        monitor.mark_issue_resolved("test", "key")
        assert tracked.state == IssueState.RESOLVED

    def test_mark_failed(self, monitor):
        tracked = TrackedIssue("test", "key", {})
        monitor._tracked_issues["test:key"] = tracked
        monitor.mark_issue_failed("test", "key")
        assert tracked.state == IssueState.FAILED

    def test_build_resource_key_from_context(self, monitor):
        monitor._structured_context = {"resource_name": "my-res", "namespace": "my-ns"}
        key = monitor._build_resource_key()
        assert key == "my-ns/my-res"

    def test_build_resource_key_fallback(self, monitor):
        monitor.waiting_for_resource = "ROSANetwork"
        key = monitor._build_resource_key()
        assert key == "ROSANetwork"


class TestTrackedIssue:
    def test_can_retry_failed(self):
        t = TrackedIssue("test", "key", {})
        t.state = IssueState.FAILED
        t.attempts = 1
        assert t.can_retry() is True

    def test_cannot_retry_max_attempts(self):
        t = TrackedIssue("test", "key", {})
        t.state = IssueState.FAILED
        t.attempts = 3
        assert t.can_retry() is False

    def test_should_intervene_detected(self):
        t = TrackedIssue("test", "key", {})
        assert t.should_intervene() is True

    def test_should_not_intervene_diagnosing(self):
        t = TrackedIssue("test", "key", {})
        t.state = IssueState.DIAGNOSING
        assert t.should_intervene() is False

    def test_should_intervene_resolved_after_cooldown(self):
        t = TrackedIssue("test", "key", {})
        t.state = IssueState.RESOLVED
        t.attempts = 1
        t.last_updated = time.time() - 130  # past 120s cooldown
        assert t.should_intervene() is True

    def test_should_not_intervene_resolved_within_cooldown(self):
        t = TrackedIssue("test", "key", {})
        t.state = IssueState.RESOLVED
        t.attempts = 1
        t.last_updated = time.time()
        assert t.should_intervene() is False


# ---------------------------------------------------------------------------
# LearningAgent tests
# ---------------------------------------------------------------------------

class TestLearningRecordOutcome:
    def test_record_success(self, learner):
        learner.record_outcome(
            issue_type="test_issue",
            diagnosis={"confidence": 0.9, "root_cause": "testing"},
            fix_applied="remove_finalizers",
            success=True,
            resource_key="ns/res",
        )
        assert len(learner.session_outcomes) == 1
        assert learner.session_outcomes[0]["success"] is True

    def test_record_failure(self, learner):
        learner.record_outcome(
            issue_type="test_issue",
            diagnosis={"confidence": 0.5},
            fix_applied="remove_finalizers",
            success=False,
        )
        assert learner.session_outcomes[0]["success"] is False

    def test_disabled(self, tmp_project):
        agent = LearningAgent(tmp_project, enabled=False)
        agent.record_outcome("t", {}, "f", True)
        assert len(agent.session_outcomes) == 0


class TestLearningEndOfRunSummary:
    def test_empty_session(self, learner):
        summary = learner.end_of_run_summary()
        assert summary["adjustments"] == []

    def test_summary_with_outcomes(self, learner):
        for _ in range(4):
            learner.record_outcome("test_issue", {"confidence": 0.9}, "fix_a", True)
        summary = learner.end_of_run_summary()
        assert summary["session_outcomes"] == 4
        assert "test_issue:fix_a" in summary["fix_stats"]

    def test_persists_outcomes(self, learner):
        learner.record_outcome("test_issue", {"confidence": 0.9}, "fix_a", True)
        learner.end_of_run_summary()
        # Session should be cleared after persist
        assert len(learner.session_outcomes) == 0
        # File should exist
        assert learner.outcomes_file.exists()
        with open(learner.outcomes_file) as f:
            data = json.load(f)
        assert len(data) == 1


class TestLearningConfidenceAdjustments:
    def test_boost_on_consecutive_successes(self, learner):
        outcomes = [
            {"issue_type": "t", "success": True, "timestamp": f"2026-01-0{i}"}
            for i in range(1, 6)
        ]
        adjustments = learner._calculate_confidence_adjustments(outcomes)
        assert len(adjustments) == 1
        assert adjustments[0]["action"] == "boost"
        assert adjustments[0]["delta"] == 0.05

    def test_reduce_on_consecutive_failures(self, learner):
        outcomes = [
            {"issue_type": "t", "success": False, "timestamp": f"2026-01-0{i}"}
            for i in range(1, 4)
        ]
        adjustments = learner._calculate_confidence_adjustments(outcomes)
        assert len(adjustments) == 1
        assert adjustments[0]["action"] == "reduce"
        assert adjustments[0]["delta"] == -0.1

    def test_no_change_on_mixed(self, learner):
        outcomes = [
            {"issue_type": "t", "success": True, "timestamp": "2026-01-01"},
            {"issue_type": "t", "success": False, "timestamp": "2026-01-02"},
            {"issue_type": "t", "success": True, "timestamp": "2026-01-03"},
        ]
        adjustments = learner._calculate_confidence_adjustments(outcomes)
        assert len(adjustments) == 0


class TestLearningApplyConfidenceAdjustments:
    def test_applies_adjustment(self, learner):
        adjustments = [{"issue_type": "ocm_auth_failure", "action": "boost", "delta": 0.05, "reason": "test"}]
        learner._apply_confidence_adjustments(adjustments)
        with open(learner.kb_dir / "known_issues.json") as f:
            ki = json.load(f)
        for p in ki["patterns"]:
            if p["type"] == "ocm_auth_failure":
                assert "learned_confidence" in p
                break

    def test_respects_bounds(self, learner):
        # Set existing learned_confidence to 0.3
        ki_file = learner.kb_dir / "known_issues.json"
        with open(ki_file) as f:
            ki = json.load(f)
        for p in ki["patterns"]:
            if p["type"] == "ocm_auth_failure":
                p["learned_confidence"] = 0.3
        with open(ki_file, "w") as f:
            json.dump(ki, f)

        adjustments = [{"issue_type": "ocm_auth_failure", "action": "reduce", "delta": -0.1, "reason": "test"}]
        learner._apply_confidence_adjustments(adjustments)
        with open(ki_file) as f:
            ki = json.load(f)
        for p in ki["patterns"]:
            if p["type"] == "ocm_auth_failure":
                assert p["learned_confidence"] >= 0.3


class TestLearningOutcomesCap:
    def test_caps_at_500(self, learner):
        # Pre-populate with 498 outcomes
        existing = [{"issue_type": "old", "success": True, "timestamp": f"2026-01-{i:04d}"} for i in range(498)]
        with open(learner.outcomes_file, "w") as f:
            json.dump(existing, f)

        for i in range(10):
            learner.record_outcome("new", {}, "fix", True)
        learner._append_outcomes()

        with open(learner.outcomes_file) as f:
            data = json.load(f)
        assert len(data) == 500


class TestLearningSuggestNewPattern:
    def test_creates_pending(self, learner):
        learner.suggest_new_pattern(
            log_line="some error line",
            diagnosis={"issue_type": "new_issue", "severity": "high", "root_cause": "test", "confidence": 0.8, "evidence": [], "recommended_fix": "fix"},
            fix_applied="fix",
            success=True,
        )
        assert learner.pending_file.exists()
        with open(learner.pending_file) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["status"] == "pending_review"
        assert data[0]["suggested_pattern"]["auto_fix"] is False


class TestLearningStats:
    def test_empty_stats(self, learner):
        stats = learner.get_learning_stats()
        assert stats["total_outcomes"] == 0

    def test_stats_with_data(self, learner):
        outcomes = [
            {"issue_type": "a", "recommended_fix": "fix1", "success": True, "timestamp": "t1"},
            {"issue_type": "a", "recommended_fix": "fix1", "success": False, "timestamp": "t2"},
        ]
        with open(learner.outcomes_file, "w") as f:
            json.dump(outcomes, f)
        stats = learner.get_learning_stats()
        assert stats["total_outcomes"] == 2
        assert "fix1" in stats["fix_stats"]
        assert stats["fix_stats"]["fix1"]["success_rate"] == "50%"


# ---------------------------------------------------------------------------
# BaseAgent tests
# ---------------------------------------------------------------------------

class TestBaseAgent:
    def test_match_pattern(self, tmp_project):
        agent = BaseAgent("Test", tmp_project)
        patterns = [{"type": "test", "pattern": "error.*fatal"}]
        assert agent.match_pattern("error is fatal", patterns) is not None
        assert agent.match_pattern("all good", patterns) is None

    def test_should_intervene(self, tmp_project):
        agent = BaseAgent("Test", tmp_project, enabled=True)
        assert agent.should_intervene({"auto_fix": True}) is True
        assert agent.should_intervene({"auto_fix": False}) is False
        assert agent.should_intervene({}) is False

    def test_should_not_intervene_disabled(self, tmp_project):
        agent = BaseAgent("Test", tmp_project, enabled=False)
        assert agent.should_intervene({"auto_fix": True}) is False

    def test_record_intervention(self, tmp_project):
        agent = BaseAgent("Test", tmp_project)
        agent.record_intervention("test_fix", {"key": "val"})
        assert len(agent.interventions) == 1
        assert agent.interventions[0]["type"] == "test_fix"

    def test_update_and_get_context(self, tmp_project):
        agent = BaseAgent("Test", tmp_project)
        agent.update_context("key", "value")
        assert agent.get_context("key") == "value"
        assert agent.get_context("missing", "default") == "default"

    def test_load_knowledge_missing_file(self, tmp_project):
        agent = BaseAgent("Test", tmp_project)
        result = agent._load_knowledge("nonexistent.json")
        assert result == {}
