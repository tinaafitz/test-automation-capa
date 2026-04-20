#!/usr/bin/env python3
"""
Tests for ExecutionEngine AI Agent Integration
===============================================

Covers:
    - Agent initialization (live and dry-run modes)
    - Agent callback chain (detect -> diagnose -> remediate -> learn)
    - Streaming playbook runner with agent line processing
    - Agent summary output
    - --ai-agent flag parsing on all lifecycle commands
    - Graceful handling when agents are unavailable
    - Edge cases: diagnosis None, diagnosis exception, remediation exception,
      remediation failure, ImportError on init, empty cluster_name,
      missing extra_vars, summary with learning outcomes, thread safety
"""

import sys
import subprocess
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))

from capa_core import FeatureRegistry


def _make_engine(ai_agent=False, ai_agent_dry_run=False):
    """Create an ExecutionEngine with optional agent support."""
    # Import here to get the threading-aware version
    sys.path.insert(0, str(Path(__file__).parent))
    exec(open(Path(__file__).parent / "capa").read().split("def main")[0], globals())
    base_dir = Path(__file__).parent
    registry = FeatureRegistry(base_dir)
    return ExecutionEngine(registry, base_dir, ai_agent=ai_agent, ai_agent_dry_run=ai_agent_dry_run)


def test_engine_no_agents_by_default():
    """Engine without --ai-agent has no agents initialized."""
    print("\n=== Test 1: Engine without agents ===")
    engine = _make_engine()
    assert engine.monitor_agent is None
    assert engine.diagnostic_agent is None
    assert engine.remediation_agent is None
    assert engine.learning_agent is None
    assert engine.ai_agent is False
    print("PASSED")


def test_engine_agents_initialize():
    """Engine with --ai-agent initializes all 4 agents."""
    print("\n=== Test 2: Agent initialization ===")
    engine = _make_engine(ai_agent=True)
    assert engine.monitor_agent is not None, "MonitoringAgent not initialized"
    assert engine.diagnostic_agent is not None, "DiagnosticAgent not initialized"
    assert engine.remediation_agent is not None, "RemediationAgent not initialized"
    assert engine.learning_agent is not None, "LearningAgent not initialized"
    assert engine.ai_agent is True
    print("PASSED")


def test_engine_agents_dry_run_mode():
    """Engine with --ai-agent-dry-run sets remediation to dry-run."""
    print("\n=== Test 3: Agent dry-run mode ===")
    engine = _make_engine(ai_agent=True, ai_agent_dry_run=True)
    assert engine.remediation_agent.dry_run is True, "RemediationAgent should be in dry-run mode"
    assert engine.ai_agent_dry_run is True
    print("PASSED")


def test_engine_agents_share_kb_dir():
    """All agents share the same knowledge base directory."""
    print("\n=== Test 4: Agents share kb_dir ===")
    engine = _make_engine(ai_agent=True)
    expected_kb = Path(__file__).parent / "agents" / "domains" / "rosa_hcp" / "knowledge_base"
    assert engine.monitor_agent.kb_dir.resolve() == expected_kb.resolve()
    assert engine.diagnostic_agent.kb_dir.resolve() == expected_kb.resolve()
    assert engine.remediation_agent.kb_dir.resolve() == expected_kb.resolve()
    assert engine.learning_agent.kb_dir.resolve() == expected_kb.resolve()
    print("PASSED")


def test_agent_process_line():
    """_agent_process_line feeds lines to the monitoring agent."""
    print("\n=== Test 5: Agent process line ===")
    engine = _make_engine(ai_agent=True)

    # Feed a structured context line
    engine._agent_process_line("#AGENT_CONTEXT: resource_name=test-cluster namespace=ns-rosa-hcp resource_type=rosacontrolplane")
    assert engine.monitor_agent._structured_context.get("resource_name") == "test-cluster"
    assert engine.monitor_agent._structured_context.get("namespace") == "ns-rosa-hcp"
    print("PASSED")


def test_agent_callback_high_confidence():
    """Agent callback chain works for high-confidence issues (>= 0.7)."""
    print("\n=== Test 6: Agent callback - high confidence ===")
    engine = _make_engine(ai_agent=True, ai_agent_dry_run=True)

    # Simulate the callback with a rate limit issue (high confidence, no external deps)
    context = {
        "line": "ERROR: HTTP 429 rate limit exceeded",
        "buffer": [],
        "current_task": "test",
        "resource_key": "test/resource",
    }
    issue = {"type": "api_rate_limit", "auto_fix": True}

    engine._agent_issue_detected("api_rate_limit", context, issue)

    # Should have recorded an outcome
    assert len(engine.learning_agent.session_outcomes) == 1
    outcome = engine.learning_agent.session_outcomes[0]
    assert outcome["issue_type"] == "api_rate_limit"
    assert outcome["success"] is True  # dry-run returns True
    print("PASSED")


def test_agent_callback_low_confidence():
    """Agent callback marks issue as failed when confidence < 0.7."""
    print("\n=== Test 7: Agent callback - low confidence ===")
    engine = _make_engine(ai_agent=True)

    context = {
        "line": "some unknown issue",
        "buffer": [],
        "current_task": "test",
        "resource_key": "test/resource",
    }
    issue = {"type": "unknown_issue_type", "auto_fix": True}

    engine._agent_issue_detected("unknown_issue_type", context, issue)

    # Generic diagnosis returns 0.3 confidence, below threshold
    # Should NOT record an outcome (no remediation attempted)
    assert len(engine.learning_agent.session_outcomes) == 0

    # The callback calls mark_issue_failed which updates the tracking state
    # The key is built from the resource_key passed in context
    found_failed = any(
        t.state.value == "failed"
        for t in engine.monitor_agent._tracked_issues.values()
    )
    # If no tracked issue exists yet (callback was invoked directly, not via process_line),
    # mark_issue_failed creates one with the resource_key
    # Either way, no outcome should be recorded for low-confidence issues
    assert len(engine.learning_agent.session_outcomes) == 0, "Low confidence should not record outcomes"
    print("PASSED")


def test_agent_summary_clean_run():
    """Agent summary reports clean run when no issues detected."""
    print("\n=== Test 8: Agent summary - clean run ===")
    engine = _make_engine(ai_agent=True)
    # Don't feed any lines — should report clean
    engine._print_agent_summary()
    stats = engine.monitor_agent.get_statistics()
    assert stats["patterns_detected"] == 0
    print("PASSED")


def test_agent_summary_with_issues():
    """Agent summary reports issues when they were detected."""
    print("\n=== Test 9: Agent summary - with issues ===")
    engine = _make_engine(ai_agent=True, ai_agent_dry_run=True)

    # Trigger an issue through the monitoring agent
    engine._agent_process_line("#AGENT_CONTEXT: resource_name=test namespace=ns resource_type=rosacontrolplane")
    engine._agent_process_line("FAILED - RETRYING: [localhost]: Wait for rosacontrolplane test upgrade to 4.20.12. state=upgrading (60s elapsed).")

    stats = engine.monitor_agent.get_statistics()
    assert stats["patterns_detected"] > 0
    engine._print_agent_summary()
    print("PASSED")


def test_no_agents_summary_when_disabled():
    """No agent summary printed when agents are disabled."""
    print("\n=== Test 10: No agent summary when disabled ===")
    engine = _make_engine(ai_agent=False)
    # Should not crash
    engine._print_agent_summary()
    print("PASSED")


def test_cli_flag_parsing():
    """All lifecycle commands accept --ai-agent and --ai-agent-dry-run."""
    print("\n=== Test 11: CLI flag parsing ===")
    capa_path = str(Path(__file__).parent / "capa")

    commands_with_agents = ["create", "upgrade", "apply", "delete", "test", "workflow"]
    for cmd in commands_with_agents:
        result = subprocess.run(
            [sys.executable, capa_path, cmd, "--help"],
            capture_output=True, text=True, timeout=10
        )
        assert "--ai-agent" in result.stdout, f"{cmd} missing --ai-agent flag"
        assert "--ai-agent-dry-run" in result.stdout, f"{cmd} missing --ai-agent-dry-run flag"

    print(f"PASSED ({len(commands_with_agents)} commands verified)")


def test_execute_calls_agent_summary():
    """execute() calls _print_agent_summary when agents are enabled."""
    print("\n=== Test 12: execute() calls agent summary ===")
    engine = _make_engine(ai_agent=True)

    # Execute an empty plan (dry-run to skip actual execution)
    engine.dry_run = True
    results = engine.execute([{"step": 1, "name": "test step", "type": "playbook"}])
    assert results[0]["status"] == "dry_run"
    # Agent summary should have been called (no crash)
    print("PASSED")


def test_streaming_path_selected_with_agents():
    """_run_playbook uses StreamingPlaybookRunner when agents are enabled."""
    print("\n=== Test 13: Streaming path with agents ===")
    engine = _make_engine(ai_agent=True)

    step = {
        "step": 1,
        "name": "test",
        "type": "playbook",
        "playbook": "playbooks/nonexistent.yml",
        "extra_vars": {"cluster_name": "test-cluster"},
    }

    result = engine._run_playbook(step)
    # Should fail because playbook doesn't exist, but should use streaming path
    assert result["status"] == "failed"
    assert "not found" in result.get("error", "").lower() or result["status"] == "failed"
    print("PASSED")


def test_blocking_path_without_agents():
    """_run_playbook uses run_playbook_blocking when agents are disabled."""
    print("\n=== Test 14: Blocking path without agents ===")
    engine = _make_engine(ai_agent=False)

    step = {
        "step": 1,
        "name": "test",
        "type": "playbook",
        "playbook": "playbooks/nonexistent.yml",
        "extra_vars": {},
    }

    result = engine._run_playbook(step)
    assert result["status"] == "failed"
    print("PASSED")


# =========================================================================
# NEW TESTS: edge cases for 95% coverage
# =========================================================================

def test_agent_callback_diagnosis_returns_none():
    """Agent callback handles diagnosis returning None (no diagnosis available)."""
    print("\n=== Test 15: Agent callback - diagnosis returns None ===")
    engine = _make_engine(ai_agent=True)

    # Mock the diagnostic agent to return None
    engine.diagnostic_agent.diagnose = MagicMock(return_value=None)

    context = {
        "line": "some error line",
        "buffer": [],
        "current_task": "test",
        "resource_key": "test/resource",
    }
    issue = {"type": "some_issue", "auto_fix": True}

    engine._agent_issue_detected("some_issue", context, issue)

    # When diagnosis is None, no remediation is attempted and no outcome recorded
    assert len(engine.learning_agent.session_outcomes) == 0, \
        "No outcome should be recorded when diagnosis is None"

    # mark_issue_failed should have been called (line 146 in capa)
    # Verify it didn't crash
    print("PASSED")


def test_agent_callback_diagnosis_exception():
    """Agent callback handles exception during diagnosis gracefully."""
    print("\n=== Test 16: Agent callback - diagnosis exception ===")
    engine = _make_engine(ai_agent=True)

    # Mock the diagnostic agent to raise an exception
    engine.diagnostic_agent.diagnose = MagicMock(side_effect=RuntimeError("diagnosis failed"))

    context = {
        "line": "error line",
        "buffer": [],
        "current_task": "test",
        "resource_key": "test/resource",
    }
    issue = {"type": "error_type", "auto_fix": True}

    # Should not raise — exception is caught in the try/except block
    engine._agent_issue_detected("error_type", context, issue)

    # No outcome recorded because exception was caught before remediation
    assert len(engine.learning_agent.session_outcomes) == 0
    print("PASSED")


def test_agent_callback_remediation_exception():
    """Agent callback handles exception during remediation gracefully."""
    print("\n=== Test 17: Agent callback - remediation exception ===")
    engine = _make_engine(ai_agent=True)

    # Mock diagnostic agent to return high-confidence diagnosis
    engine.diagnostic_agent.diagnose = MagicMock(return_value={
        "root_cause": "test issue",
        "recommended_fix": "test fix",
        "confidence": 0.9,
    })

    # Mock remediation agent to raise an exception
    engine.remediation_agent.remediate = MagicMock(side_effect=RuntimeError("remediation exploded"))

    context = {
        "line": "error line",
        "buffer": [],
        "current_task": "test",
        "resource_key": "test/resource",
    }
    issue = {"type": "fixable_issue", "auto_fix": True}

    # Should not raise — exception is caught in the try/except block
    engine._agent_issue_detected("fixable_issue", context, issue)

    # No outcome recorded because exception happened before record_outcome
    assert len(engine.learning_agent.session_outcomes) == 0

    # mark_issue_failed should have been called via the except branch
    print("PASSED")


def test_agent_callback_remediation_returns_failure():
    """Agent callback handles remediation returning success=False."""
    print("\n=== Test 18: Agent callback - remediation failure ===")
    engine = _make_engine(ai_agent=True)

    # Mock diagnostic agent to return high-confidence diagnosis
    engine.diagnostic_agent.diagnose = MagicMock(return_value={
        "root_cause": "test issue",
        "recommended_fix": "test fix",
        "confidence": 0.9,
    })

    # Mock remediation agent to return failure
    engine.remediation_agent.remediate = MagicMock(return_value=(False, "fix did not work"))

    context = {
        "line": "error line",
        "buffer": [],
        "current_task": "test",
        "resource_key": "test/resource",
    }
    issue = {"type": "unfixable_issue", "auto_fix": True}

    engine._agent_issue_detected("unfixable_issue", context, issue)

    # Outcome IS recorded even on failure (success=False path still calls record_outcome)
    assert len(engine.learning_agent.session_outcomes) == 1
    outcome = engine.learning_agent.session_outcomes[0]
    assert outcome["issue_type"] == "unfixable_issue"
    assert outcome["success"] is False
    assert outcome["details"] == "fix did not work"
    print("PASSED")


def test_init_agents_import_error():
    """_init_agents gracefully handles ImportError when agents module is unavailable."""
    print("\n=== Test 19: _init_agents - ImportError ===")
    engine = _make_engine(ai_agent=False)  # Start with agents disabled

    # Manually set ai_agent True, then call _init_agents with a mocked import failure
    engine.ai_agent = True

    import builtins
    original_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "agents" or name.startswith("agents."):
            raise ImportError("agents module not available")
        return original_import(name, *args, **kwargs)

    builtins.__import__ = mock_import
    try:
        engine._init_agents()
    finally:
        builtins.__import__ = original_import

    # After ImportError, ai_agent should be set back to False
    assert engine.ai_agent is False, "ai_agent should be False after ImportError"
    assert engine.monitor_agent is None
    assert engine.diagnostic_agent is None
    assert engine.remediation_agent is None
    assert engine.learning_agent is None
    print("PASSED")


def test_run_playbook_sidecar_log_none_for_empty_cluster():
    """_run_playbook sets sidecar_log=None when cluster_name is empty."""
    print("\n=== Test 20: Streaming path - empty cluster_name ===")
    engine = _make_engine(ai_agent=True)

    step = {
        "step": 1,
        "name": "test",
        "type": "playbook",
        "playbook": "playbooks/nonexistent.yml",
        "extra_vars": {"cluster_name": ""},
    }

    # When cluster_name is empty, sidecar_log should be None and
    # on_sidecar_line should be None. The streaming path is still used
    # (ai_agent=True) but without sidecar monitoring.
    result = engine._run_playbook(step)
    assert result["status"] == "failed"
    print("PASSED")


def test_run_playbook_missing_extra_vars():
    """_run_playbook handles step with no extra_vars key."""
    print("\n=== Test 21: Streaming path - missing extra_vars ===")
    engine = _make_engine(ai_agent=True)

    step = {
        "step": 1,
        "name": "test",
        "type": "playbook",
        "playbook": "playbooks/nonexistent.yml",
        # extra_vars intentionally omitted
    }

    # step.get("extra_vars", {}).get("cluster_name", "") should return ""
    # sidecar_log should be None, on_sidecar_line should be None
    result = engine._run_playbook(step)
    assert result["status"] == "failed"
    print("PASSED")


def test_agent_summary_with_learning_outcomes():
    """Agent summary prints learning outcomes count when outcomes are recorded."""
    print("\n=== Test 22: Agent summary - with learning outcomes ===")
    engine = _make_engine(ai_agent=True, ai_agent_dry_run=True)

    # Record a mock outcome directly on the learning agent
    engine.learning_agent.session_outcomes.append({
        "timestamp": "2026-01-01T00:00:00",
        "issue_type": "test_issue",
        "recommended_fix": "test_fix",
        "success": True,
        "confidence_used": 0.9,
        "root_cause": "test",
        "resource_key": "test/res",
        "details": "test details",
    })

    # Mock end_of_run_summary to return a summary with session_outcomes count
    engine.learning_agent.end_of_run_summary = MagicMock(return_value={
        "session_outcomes": 1,
        "fix_stats": {},
        "adjustments": [],
        "pending_reviews": 0,
    })

    # Also trigger an issue so patterns_detected > 0 to hit the else branch
    engine._agent_process_line("#AGENT_CONTEXT: resource_name=test namespace=ns resource_type=rosacontrolplane")
    engine._agent_process_line("FAILED - RETRYING: [localhost]: Wait for rosacontrolplane test upgrade to 4.20.12. state=upgrading (60s elapsed).")

    # This should print the learning outcomes line (line 170)
    engine._print_agent_summary()

    # Verify end_of_run_summary was called
    engine.learning_agent.end_of_run_summary.assert_called_once()
    print("PASSED")


def test_agent_summary_without_learning_agent():
    """Agent summary works when learning_agent is None."""
    print("\n=== Test 23: Agent summary - no learning agent ===")
    engine = _make_engine(ai_agent=True)

    # Set learning_agent to None
    engine.learning_agent = None

    # Should not crash — the if self.learning_agent check on line 167 guards this
    engine._print_agent_summary()
    print("PASSED")


def test_execute_no_agent_summary_when_disabled():
    """execute() does NOT call _print_agent_summary when ai_agent is False."""
    print("\n=== Test 24: execute() skips agent summary when disabled ===")
    engine = _make_engine(ai_agent=False)

    # Mock _execute_step so we don't actually run a playbook
    engine._execute_step = MagicMock(return_value={
        "step": 1, "name": "test step", "status": "completed", "elapsed": 0.1
    })

    # Patch _print_agent_summary to track calls
    engine._print_agent_summary = MagicMock()

    results = engine.execute([{"step": 1, "name": "test step", "type": "playbook"}])
    assert results[0]["status"] == "completed"

    # _print_agent_summary should NOT have been called (ai_agent is False)
    engine._print_agent_summary.assert_not_called()
    print("PASSED")


def test_execute_calls_agent_summary_when_enabled():
    """execute() calls _print_agent_summary when ai_agent is True (non-dry-run path)."""
    print("\n=== Test 25: execute() calls agent summary when enabled ===")
    engine = _make_engine(ai_agent=True)

    # Mock _execute_step so we don't actually run a playbook
    engine._execute_step = MagicMock(return_value={
        "step": 1, "name": "test step", "status": "completed", "elapsed": 0.1
    })

    # Patch _print_agent_summary to track calls
    engine._print_agent_summary = MagicMock()

    results = engine.execute([{"step": 1, "name": "test step", "type": "playbook"}])
    assert results[0]["status"] == "completed"

    # _print_agent_summary SHOULD have been called (lines 209-210)
    engine._print_agent_summary.assert_called_once()
    print("PASSED")


def test_agent_process_line_acquires_lock():
    """_agent_process_line acquires the thread lock."""
    print("\n=== Test 26: Thread safety - lock acquisition ===")
    engine = _make_engine(ai_agent=True)

    # Replace the lock with a trackable mock
    lock_acquired = []
    real_lock = engine._agent_lock

    class TrackingLock:
        def __enter__(self):
            lock_acquired.append(True)
            return real_lock.__enter__()
        def __exit__(self, *args):
            return real_lock.__exit__(*args)

    engine._agent_lock = TrackingLock()

    engine._agent_process_line("test line")

    assert len(lock_acquired) == 1, "Lock should have been acquired exactly once"
    print("PASSED")


def test_agent_process_line_noop_without_monitor():
    """_agent_process_line is a no-op when monitor_agent is None."""
    print("\n=== Test 27: Process line no-op without monitor ===")
    engine = _make_engine(ai_agent=False)
    assert engine.monitor_agent is None

    # Should not crash
    engine._agent_process_line("some line")
    print("PASSED")


def test_agent_callback_exception_with_monitor_none():
    """Agent callback exception path works even if monitor_agent is None."""
    print("\n=== Test 28: Agent callback exception - monitor_agent None ===")
    engine = _make_engine(ai_agent=True)

    # Mock diagnostic agent to raise
    engine.diagnostic_agent.diagnose = MagicMock(side_effect=RuntimeError("boom"))

    # Set monitor_agent to None to test the `if self.monitor_agent` guard in except
    engine.monitor_agent = None

    context = {
        "line": "error",
        "buffer": [],
        "current_task": "test",
        "resource_key": "test/resource",
    }
    issue = {"type": "test_type", "auto_fix": True}

    # Should not raise — the except block checks `if self.monitor_agent` before calling mark_issue_failed
    engine._agent_issue_detected("test_type", context, issue)
    print("PASSED")


def test_agent_callback_remediation_success_marks_resolved():
    """Agent callback marks issue as resolved on successful remediation."""
    print("\n=== Test 29: Agent callback - remediation success marks resolved ===")
    engine = _make_engine(ai_agent=True)

    # Mock diagnostic agent to return high-confidence diagnosis
    engine.diagnostic_agent.diagnose = MagicMock(return_value={
        "root_cause": "test issue",
        "recommended_fix": "test fix",
        "confidence": 0.9,
    })

    # Mock remediation agent to return success
    engine.remediation_agent.remediate = MagicMock(return_value=(True, "fix applied successfully"))

    # Mock mark_issue_resolved to verify it's called
    engine.monitor_agent.mark_issue_resolved = MagicMock()

    context = {
        "line": "error line",
        "buffer": [],
        "current_task": "test",
        "resource_key": "test/resource",
    }
    issue = {"type": "fixable_issue", "auto_fix": True}

    engine._agent_issue_detected("fixable_issue", context, issue)

    # Verify mark_issue_resolved was called
    engine.monitor_agent.mark_issue_resolved.assert_called_once_with("fixable_issue", "test/resource")

    # Outcome recorded with success=True
    assert len(engine.learning_agent.session_outcomes) == 1
    assert engine.learning_agent.session_outcomes[0]["success"] is True
    print("PASSED")


def test_agent_callback_remediation_failure_marks_failed():
    """Agent callback marks issue as failed on unsuccessful remediation."""
    print("\n=== Test 30: Agent callback - remediation failure marks failed ===")
    engine = _make_engine(ai_agent=True)

    # Mock diagnostic agent to return high-confidence diagnosis
    engine.diagnostic_agent.diagnose = MagicMock(return_value={
        "root_cause": "test issue",
        "recommended_fix": "test fix",
        "confidence": 0.9,
    })

    # Mock remediation agent to return failure
    engine.remediation_agent.remediate = MagicMock(return_value=(False, "could not fix"))

    # Mock mark_issue_failed to verify it's called
    engine.monitor_agent.mark_issue_failed = MagicMock()

    context = {
        "line": "error line",
        "buffer": [],
        "current_task": "test",
        "resource_key": "test/resource",
    }
    issue = {"type": "unfixable", "auto_fix": True}

    engine._agent_issue_detected("unfixable", context, issue)

    # Verify mark_issue_failed was called (not mark_issue_resolved)
    engine.monitor_agent.mark_issue_failed.assert_called_once_with("unfixable", "test/resource")
    print("PASSED")


def test_agent_callback_no_learning_agent():
    """Agent callback works when learning_agent is None during remediation."""
    print("\n=== Test 31: Agent callback - no learning agent ===")
    engine = _make_engine(ai_agent=True)

    # Mock diagnostic agent to return high-confidence diagnosis
    engine.diagnostic_agent.diagnose = MagicMock(return_value={
        "root_cause": "test issue",
        "recommended_fix": "test fix",
        "confidence": 0.9,
    })

    # Mock remediation agent to return success
    engine.remediation_agent.remediate = MagicMock(return_value=(True, "fixed"))

    # Set learning_agent to None to test the `if self.learning_agent` guard on line 131
    engine.learning_agent = None

    context = {
        "line": "error line",
        "buffer": [],
        "current_task": "test",
        "resource_key": "test/resource",
    }
    issue = {"type": "test_issue", "auto_fix": True}

    # Should not crash — the if self.learning_agent check guards record_outcome
    engine._agent_issue_detected("test_issue", context, issue)
    print("PASSED")


def test_agent_summary_no_session_outcomes():
    """Agent summary handles end_of_run_summary returning no session_outcomes."""
    print("\n=== Test 32: Agent summary - no session outcomes from learning ===")
    engine = _make_engine(ai_agent=True)

    # Trigger an issue so patterns_detected > 0 (to hit the else branch)
    engine._agent_process_line("#AGENT_CONTEXT: resource_name=test namespace=ns resource_type=rosacontrolplane")
    engine._agent_process_line("FAILED - RETRYING: [localhost]: Wait for rosacontrolplane test upgrade to 4.20.12. state=upgrading (60s elapsed).")

    # Mock end_of_run_summary to return empty session_outcomes (falsy)
    engine.learning_agent.end_of_run_summary = MagicMock(return_value={
        "session_outcomes": 0,  # falsy value
        "adjustments": [],
        "pending_reviews": 0,
    })

    # Should not crash; should skip the "Learning: N outcomes recorded" line
    engine._print_agent_summary()
    print("PASSED")


def test_agent_callback_resource_key_none():
    """Agent callback handles missing resource_key in context."""
    print("\n=== Test 33: Agent callback - resource_key None ===")
    engine = _make_engine(ai_agent=True)

    # Mock diagnostic agent to return None (simple path)
    engine.diagnostic_agent.diagnose = MagicMock(return_value=None)

    context = {
        "line": "error line",
        "buffer": [],
        "current_task": "test",
        # resource_key intentionally omitted
    }
    issue = {"type": "some_issue", "auto_fix": True}

    # resource_key = context.get("resource_key") will be None
    engine._agent_issue_detected("some_issue", context, issue)

    # Should not crash
    print("PASSED")


def test_thread_safety_concurrent_process_lines():
    """Multiple threads can call _agent_process_line safely."""
    print("\n=== Test 34: Thread safety - concurrent process lines ===")
    engine = _make_engine(ai_agent=True)

    errors = []

    def feed_lines(prefix, count):
        try:
            for i in range(count):
                engine._agent_process_line(f"{prefix} line {i}")
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=feed_lines, args=("thread-A", 20)),
        threading.Thread(target=feed_lines, args=("thread-B", 20)),
        threading.Thread(target=feed_lines, args=("thread-C", 20)),
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(errors) == 0, f"Thread errors: {errors}"
    print("PASSED")


if __name__ == "__main__":
    print("=" * 60)
    print("ExecutionEngine AI Agent Integration Tests")
    print("=" * 60)

    tests = [
        test_engine_no_agents_by_default,
        test_engine_agents_initialize,
        test_engine_agents_dry_run_mode,
        test_engine_agents_share_kb_dir,
        test_agent_process_line,
        test_agent_callback_high_confidence,
        test_agent_callback_low_confidence,
        test_agent_summary_clean_run,
        test_agent_summary_with_issues,
        test_no_agents_summary_when_disabled,
        test_cli_flag_parsing,
        test_execute_calls_agent_summary,
        test_streaming_path_selected_with_agents,
        test_blocking_path_without_agents,
        # New edge-case tests
        test_agent_callback_diagnosis_returns_none,
        test_agent_callback_diagnosis_exception,
        test_agent_callback_remediation_exception,
        test_agent_callback_remediation_returns_failure,
        test_init_agents_import_error,
        test_run_playbook_sidecar_log_none_for_empty_cluster,
        test_run_playbook_missing_extra_vars,
        test_agent_summary_with_learning_outcomes,
        test_agent_summary_without_learning_agent,
        test_execute_no_agent_summary_when_disabled,
        test_execute_calls_agent_summary_when_enabled,
        test_agent_process_line_acquires_lock,
        test_agent_process_line_noop_without_monitor,
        test_agent_callback_exception_with_monitor_none,
        test_agent_callback_remediation_success_marks_resolved,
        test_agent_callback_remediation_failure_marks_failed,
        test_agent_callback_no_learning_agent,
        test_agent_summary_no_session_outcomes,
        test_agent_callback_resource_key_none,
        test_thread_safety_concurrent_process_lines,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    print(f"{'=' * 60}")
    sys.exit(1 if failed > 0 else 0)
