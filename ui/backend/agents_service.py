"""
Agents service module — FastAPI router for AI agent dashboard endpoints
and agent lifecycle helpers.

Endpoints moved here from app.py:
  GET    /api/agents/dashboard
  GET    /api/agents/remediation-metrics
  GET    /api/agents/confidence
  GET    /api/agents/knowledge-base
  GET    /api/agents/roi
  POST   /api/agents/pending-learnings/{index}/approve
  POST   /api/agents/pending-learnings/{index}/reject

Also contains:
  init_ai_agents()       — initialise the four-agent pipeline for a job
  _load_agent_kb_file()  — read JSON from the knowledge-base directory
  _save_agent_kb_file()  — write JSON to the knowledge-base directory
"""

import fcntl
import json
import os
import sys
from datetime import datetime

from fastapi import APIRouter, HTTPException

from shared_state import jobs, ai_agent_sessions

# ── Agent class imports (with graceful fallback) ────────────────────────
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

try:
    from agents import MonitoringAgent, DiagnosticAgent, RemediationAgent, LearningAgent, IssueState
    AI_AGENTS_AVAILABLE = True
except ImportError:
    AI_AGENTS_AVAILABLE = False
    MonitoringAgent = DiagnosticAgent = RemediationAgent = LearningAgent = IssueState = None

router = APIRouter()


# ── Agent lifecycle ─────────────────────────────────────────────────────

def _get_app_module():
    """Return the live ``app`` module so that test monkey-patches
    (e.g. ``app_module.AI_AGENTS_AVAILABLE = False`` or
    ``@patch("app.MonitoringAgent")``) are respected at call time.
    Falls back to this module's own globals when ``app`` has not been
    imported yet.
    """
    return sys.modules.get("app")


def init_ai_agents(job_id: str, dry_run: bool = False, operation_type: str = ""):
    """Initialize AI agent framework for a job.  Returns dict of agents or None.

    Reads ``AI_AGENTS_AVAILABLE`` and the four agent classes from the
    ``app`` module at call time so that unit-test patches such as
    ``app_module.AI_AGENTS_AVAILABLE = False`` are honoured.
    """
    _app = _get_app_module()

    # Check AI_AGENTS_AVAILABLE from app module first (tests patch it there),
    # falling back to our own module-level flag.
    if _app is not None:
        if not getattr(_app, "AI_AGENTS_AVAILABLE", AI_AGENTS_AVAILABLE):
            return None
    elif not AI_AGENTS_AVAILABLE:
        return None

    try:
        from pathlib import Path
        base_dir = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

        # Resolve agent classes from ``app`` module (tests patch them there).
        _Mon = getattr(_app, "MonitoringAgent", MonitoringAgent) if _app else MonitoringAgent
        _Diag = getattr(_app, "DiagnosticAgent", DiagnosticAgent) if _app else DiagnosticAgent
        _Rem = getattr(_app, "RemediationAgent", RemediationAgent) if _app else RemediationAgent
        _Learn = getattr(_app, "LearningAgent", LearningAgent) if _app else LearningAgent

        monitor = _Mon(base_dir=base_dir)
        diagnostic = _Diag(base_dir=base_dir)
        remediation = _Rem(base_dir=base_dir, dry_run=dry_run)
        learning = _Learn(base_dir=base_dir)

        def on_issue_detected(issue_type, context, issue):
            import time as _time
            resource_key = context.get("resource_key", "")
            remediation_msg = ""
            _start = _time.time()
            try:
                diagnosis = diagnostic.diagnose(issue_type, context)
            except Exception as e:
                monitor.mark_issue_failed(issue_type, resource_key)
                if job_id in jobs:
                    jobs[job_id].setdefault("logs", []).append(
                        f"\U0001f916 Agent diagnosis error for {issue_type} ({resource_key}): {e}"
                    )
                return
            if diagnosis and diagnosis.get("confidence", 0) >= 0.7:
                try:
                    success, message = remediation.remediate(diagnosis)
                except Exception as e:
                    success, message = False, f"Remediation error: {e}"
                remediation_msg = message
                _duration = _time.time() - _start
                try:
                    learning.record_outcome(
                        issue_type=issue_type,
                        diagnosis=diagnosis,
                        fix_applied=diagnosis.get("recommended_fix", ""),
                        success=success,
                        resource_key=resource_key,
                        details=message,
                        duration_seconds=_duration,
                        operation_type=operation_type,
                    )
                except Exception:
                    pass
                if success:
                    monitor.mark_issue_resolved(issue_type, resource_key)
                else:
                    monitor.mark_issue_failed(issue_type, resource_key)
                if job_id in jobs:
                    action_icon = "\u2705" if success else "\u26a0\ufe0f"
                    jobs[job_id].setdefault("logs", []).append(
                        f"\U0001f916 Agent detected: {issue_type} ({resource_key})"
                    )
                    jobs[job_id]["logs"].append(
                        f"   {action_icon} {message}"
                    )
            elif diagnosis:
                # Low confidence — reset tracked issue to DETECTED so agent
                # can re-evaluate on next retry (e.g., CloudFormation stack
                # transitions from DELETE_IN_PROGRESS to DELETE_FAILED)
                tracked = monitor.reset_to_detected(issue_type, resource_key)
                if tracked:
                    low_conf_count = getattr(tracked, '_low_conf_count', 0) + 1
                    tracked._low_conf_count = low_conf_count
                    should_log = (low_conf_count == 1 or low_conf_count % 5 == 0)
                else:
                    should_log = True
                if should_log and job_id in jobs:
                    root_cause = diagnosis.get("root_cause", "")
                    jobs[job_id].setdefault("logs", []).append(
                        f"\U0001f916 Agent checked: {issue_type} ({resource_key}) \u2014 {root_cause}"
                    )
            # Store agent events for the stats API
            if job_id in jobs:
                jobs[job_id].setdefault("agent_events", [])
                jobs[job_id]["agent_events"].append({
                    "type": "issue_detected",
                    "issue_type": issue_type,
                    "resource_key": resource_key,
                    "diagnosis": diagnosis.get("root_cause", "") if diagnosis else "",
                    "fix_applied": diagnosis.get("recommended_fix", "") if diagnosis else "",
                    "remediation_result": remediation_msg,
                    "confidence": diagnosis.get("confidence", 0) if diagnosis else 0,
                    "timestamp": datetime.now().isoformat(),
                })

        monitor.set_issue_callback(on_issue_detected)

        session = {
            "monitor": monitor,
            "diagnostic": diagnostic,
            "remediation": remediation,
            "learning": learning,
        }
        ai_agent_sessions[job_id] = session
        print(f"[AI Agent] Initialized for job {job_id} (dry_run={dry_run})")
        return session
    except Exception as e:
        print(f"[AI Agent] Failed to initialize: {e}")
        return None


# ── Knowledge-base file I/O ─────────────────────────────────────────────

def _load_agent_kb_file(filename: str):
    """Load a JSON file from the agent knowledge base directory."""
    kb_path = os.path.join(_project_root, "agents", "knowledge_base", filename)
    if os.path.exists(kb_path):
        with open(kb_path, "r") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                return json.load(f)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    return []


def _save_agent_kb_file(filename: str, data):
    """Save a JSON file to the agent knowledge base directory."""
    kb_path = os.path.join(_project_root, "agents", "knowledge_base", filename)
    os.makedirs(os.path.dirname(kb_path), exist_ok=True)
    with open(kb_path, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            json.dump(data, f, indent=2)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


# ── Endpoints ───────────────────────────────────────────────────────────

@router.get("/api/agents/dashboard")
async def get_agent_dashboard(since: str = "", operation_type: str = ""):
    """Aggregated agent overview: status, pipeline activity, state distribution."""
    # Agent statuses from active sessions
    agent_statuses = {
        "monitor": {"status": "idle", "last_active": None},
        "diagnostic": {"status": "idle", "last_active": None},
        "remediation": {"status": "idle", "last_active": None},
        "learning": {"status": "idle", "last_active": None},
    }
    for jid, session in ai_agent_sessions.items():
        if jid in jobs and jobs[jid].get("status") == "running":
            for agent_name in agent_statuses:
                if session.get(agent_name):
                    agent_statuses[agent_name]["status"] = "active"

    # Collect pipeline activity from all jobs (newest first, max 50)
    all_events = []
    for jid, job in jobs.items():
        for event in job.get("agent_events", []):
            evt = dict(event)
            evt["job_id"] = jid
            # Determine state from tracked issues if available
            session = ai_agent_sessions.get(jid)
            if session and session.get("monitor"):
                tracking_key = f"{event.get('issue_type', '')}:{event.get('resource_key', '')}"
                tracked = session["monitor"]._tracked_issues.get(tracking_key)
                if tracked:
                    evt["state"] = tracked.state.value
            all_events.append(evt)
    all_events.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    pipeline_activity = all_events[:50]

    # State distribution from outcomes
    outcomes = _load_agent_kb_file("remediation_outcomes.json")
    if since:
        outcomes = [o for o in outcomes if o.get("timestamp", "") >= since]
    if operation_type:
        outcomes = [o for o in outcomes if o.get("operation_type", "") == operation_type]
    state_dist = {"detected": 0, "diagnosing": 0, "remediating": 0, "resolved": 0, "failed": 0}
    for o in outcomes:
        if o.get("success"):
            state_dist["resolved"] += 1
        else:
            state_dist["failed"] += 1
    # Add live tracked issues
    for jid, session in ai_agent_sessions.items():
        monitor = session.get("monitor")
        if monitor:
            for tracked in monitor._tracked_issues.values():
                state = tracked.state.value
                if state in state_dist:
                    state_dist[state] += 1

    return {
        "success": True,
        "timestamp": datetime.now().isoformat(),
        "overview": {
            "agent_statuses": agent_statuses,
            "active_sessions": sum(1 for j in ai_agent_sessions if j in jobs and jobs[j].get("status") == "running"),
            "total_sessions": len(ai_agent_sessions),
        },
        "pipeline_activity": pipeline_activity,
        "state_distribution": state_dist,
    }


@router.get("/api/agents/remediation-metrics")
async def get_agent_remediation_metrics(since: str = "", operation_type: str = ""):
    """Remediation totals, success rate, per-type breakdown, and trend."""
    outcomes = _load_agent_kb_file("remediation_outcomes.json")

    if since:
        outcomes = [o for o in outcomes if o.get("timestamp", "") >= since]
    if operation_type:
        outcomes = [o for o in outcomes if o.get("operation_type", "") == operation_type]

    total_success = sum(1 for o in outcomes if o.get("success"))
    total_failed = sum(1 for o in outcomes if not o.get("success"))
    total = len(outcomes)

    # Per issue type
    by_type = {}
    for o in outcomes:
        it = o.get("issue_type", "unknown")
        if it not in by_type:
            by_type[it] = {"total": 0, "success": 0, "failed": 0, "earliest": "", "latest": ""}
        by_type[it]["total"] += 1
        if o.get("success"):
            by_type[it]["success"] += 1
        else:
            by_type[it]["failed"] += 1
        ts = o.get("timestamp", "")
        if ts and (not by_type[it]["earliest"] or ts < by_type[it]["earliest"]):
            by_type[it]["earliest"] = ts
        if ts > by_type[it]["latest"]:
            by_type[it]["latest"] = ts
    for stats in by_type.values():
        stats["rate"] = round(stats["success"] / stats["total"] * 100, 1) if stats["total"] else 0

    # Average duration
    durations = [o["duration_seconds"] for o in outcomes if "duration_seconds" in o]
    avg_duration = round(sum(durations) / len(durations), 2) if durations else None

    # Daily trend
    daily = {}
    for o in outcomes:
        day = o.get("timestamp", "")[:10]
        if day not in daily:
            daily[day] = {"date": day, "resolved": 0, "failed": 0, "total": 0}
        daily[day]["total"] += 1
        if o.get("success"):
            daily[day]["resolved"] += 1
        else:
            daily[day]["failed"] += 1
    trend = sorted(daily.values(), key=lambda d: d["date"])

    timestamps = [o.get("timestamp", "") for o in outcomes if o.get("timestamp")]
    earliest = min(timestamps) if timestamps else None
    latest = max(timestamps) if timestamps else None

    return {
        "success": True,
        "metrics": {
            "total_detected": total,
            "total_remediated": total_success,
            "total_failed": total_failed,
            "success_rate": round(total_success / total * 100, 1) if total else 0,
            "avg_duration_seconds": avg_duration,
            "by_issue_type": by_type,
            "trend": trend,
            "earliest_event": earliest,
            "latest_event": latest,
        },
    }


@router.get("/api/agents/confidence")
async def get_agent_confidence():
    """Per-pattern confidence scores, streaks, and pending learnings."""
    known_issues = _load_agent_kb_file("known_issues.json")
    outcomes = _load_agent_kb_file("remediation_outcomes.json")
    pending = _load_agent_kb_file("pending_learnings.json")

    # Build streak data from outcomes
    streaks = {}
    for o in outcomes:
        it = o.get("issue_type", "unknown")
        if it not in streaks:
            streaks[it] = {"consecutive_successes": 0, "consecutive_failures": 0, "_last": None}
        if o.get("success"):
            if streaks[it]["_last"] == "success":
                streaks[it]["consecutive_successes"] += 1
            else:
                streaks[it]["consecutive_successes"] = 1
                streaks[it]["consecutive_failures"] = 0
            streaks[it]["_last"] = "success"
        else:
            if streaks[it]["_last"] == "failure":
                streaks[it]["consecutive_failures"] += 1
            else:
                streaks[it]["consecutive_failures"] = 1
                streaks[it]["consecutive_successes"] = 0
            streaks[it]["_last"] = "failure"

    patterns = []
    issues_list = known_issues if isinstance(known_issues, list) else known_issues.get("patterns", known_issues.get("issues", []))
    for issue in issues_list:
        it = issue.get("type", "")
        streak = streaks.get(it, {})
        patterns.append({
            "type": it,
            "description": issue.get("description", ""),
            "severity": issue.get("severity", "medium"),
            "auto_fix": issue.get("auto_fix", False),
            "learned_confidence": issue.get("learned_confidence"),
            "last_adjusted": issue.get("last_adjusted"),
            "adjustment_reason": issue.get("adjustment_reason"),
            "consecutive_successes": streak.get("consecutive_successes", 0),
            "consecutive_failures": streak.get("consecutive_failures", 0),
        })

    return {
        "success": True,
        "patterns": patterns,
        "pending_learnings": pending if isinstance(pending, list) else [],
        "pending_count": len(pending) if isinstance(pending, list) else 0,
    }


@router.get("/api/agents/knowledge-base")
async def get_agent_knowledge_base():
    """Knowledge base health: pattern counts, triggers, coverage gaps."""
    known_issues = _load_agent_kb_file("known_issues.json")
    outcomes = _load_agent_kb_file("remediation_outcomes.json")

    issues_list = known_issues if isinstance(known_issues, list) else known_issues.get("patterns", known_issues.get("issues", []))

    # Count triggers per pattern type from outcomes
    trigger_counts = {}
    for o in outcomes:
        it = o.get("issue_type", "unknown")
        trigger_counts[it] = trigger_counts.get(it, 0) + 1

    auto_fix_enabled = sum(1 for i in issues_list if i.get("auto_fix"))
    auto_fix_disabled = len(issues_list) - auto_fix_enabled

    # Severity breakdown
    by_severity = {}
    for i in issues_list:
        sev = i.get("severity", "medium")
        by_severity[sev] = by_severity.get(sev, 0) + 1

    # Per-type stats from outcomes
    type_stats = {}
    for o in outcomes:
        it = o.get("issue_type", "unknown")
        ts = o.get("timestamp", "")
        if it not in type_stats:
            type_stats[it] = {"first_seen": ts, "last_seen": ts, "success": 0, "failed": 0}
        if ts and ts < type_stats[it]["first_seen"]:
            type_stats[it]["first_seen"] = ts
        if ts and ts > type_stats[it]["last_seen"]:
            type_stats[it]["last_seen"] = ts
        if o.get("success"):
            type_stats[it]["success"] += 1
        else:
            type_stats[it]["failed"] += 1

    # Most and least triggered
    pattern_triggers = []
    for i in issues_list:
        it = i.get("type", "")
        stats = type_stats.get(it, {})
        pattern_triggers.append({
            "type": it,
            "count": trigger_counts.get(it, 0),
            "first_seen": stats.get("first_seen"),
            "last_seen": stats.get("last_seen"),
            "success": stats.get("success", 0),
            "failed": stats.get("failed", 0),
            "success_rate": round(stats["success"] / (stats["success"] + stats["failed"]) * 100, 1) if stats.get("success", 0) + stats.get("failed", 0) > 0 else None,
        })
    pattern_triggers.sort(key=lambda p: p["count"], reverse=True)

    # Coverage gaps -- patterns never triggered
    never_triggered = [p["type"] for p in pattern_triggers if p["count"] == 0]

    return {
        "success": True,
        "health": {
            "total_patterns": len(issues_list),
            "auto_fix_enabled": auto_fix_enabled,
            "auto_fix_disabled": auto_fix_disabled,
            "by_severity": by_severity,
            "most_triggered": pattern_triggers[:5],
            "least_triggered": pattern_triggers[-5:] if len(pattern_triggers) > 5 else pattern_triggers,
            "never_triggered": never_triggered,
            "total_outcomes": len(outcomes),
        },
    }


# ROI constants
_ROI_MANUAL_FIX_MINUTES = {
    "retry_cloudformation_delete": 45,
    "cleanup_vpc_dependencies": 60,
    "remove_finalizers": 15,
    "manual_cloudformation_cleanup": 30,
    "default": 30,
}
_ROI_ORPHAN_COST_MONTHLY = 139  # USD per orphaned cluster


@router.get("/api/agents/roi")
async def get_agent_roi(operation_type: str = ""):
    """ROI: clusters saved, time saved, cost avoided."""
    outcomes = _load_agent_kb_file("remediation_outcomes.json")
    if operation_type:
        outcomes = [o for o in outcomes if o.get("operation_type", "") == operation_type]

    successful = [o for o in outcomes if o.get("success")]
    # Unique resources saved
    saved_resources = set(o.get("resource_key", "") for o in successful)
    clusters_saved = len(saved_resources)

    # Time saved
    total_manual_minutes = 0
    for o in successful:
        fix = o.get("recommended_fix", "default")
        total_manual_minutes += _ROI_MANUAL_FIX_MINUTES.get(fix, _ROI_MANUAL_FIX_MINUTES["default"])

    # Agent time
    agent_durations = [o["duration_seconds"] for o in successful if "duration_seconds" in o]
    avg_agent_seconds = round(sum(agent_durations) / len(agent_durations), 1) if agent_durations else None

    # Cost avoided (only CF-related fixes)
    cost_fixes = {"retry_cloudformation_delete", "cleanup_vpc_dependencies", "manual_cloudformation_cleanup"}
    cost_resources = set(
        o.get("resource_key", "") for o in successful
        if o.get("recommended_fix", "") in cost_fixes
    )
    total_cost_avoided = len(cost_resources) * _ROI_ORPHAN_COST_MONTHLY

    # Monthly trend
    monthly = {}
    for o in successful:
        month = o.get("timestamp", "")[:7]
        if month not in monthly:
            monthly[month] = {"month": month, "cost_avoided": 0, "clusters_saved": set(), "interventions": 0}
        monthly[month]["interventions"] += 1
        rk = o.get("resource_key", "")
        if o.get("recommended_fix", "") in cost_fixes:
            monthly[month]["clusters_saved"].add(rk)
    cost_trend = []
    for m in sorted(monthly.keys()):
        entry = monthly[m]
        cost_trend.append({
            "month": entry["month"],
            "cost_avoided": len(entry["clusters_saved"]) * _ROI_ORPHAN_COST_MONTHLY,
            "clusters_saved": len(entry["clusters_saved"]),
            "interventions": entry["interventions"],
        })

    return {
        "success": True,
        "roi": {
            "clusters_saved": clusters_saved,
            "total_interventions": len(successful),
            "total_manual_minutes_saved": total_manual_minutes,
            "total_cost_avoided_usd": total_cost_avoided,
            "avg_agent_fix_seconds": avg_agent_seconds,
            "cost_trend": cost_trend,
        },
    }


@router.post("/api/agents/pending-learnings/{index}/approve")
async def approve_pending_learning(index: int):
    """Approve a pending learning -- adds pattern to known_issues with auto_fix=false."""
    pending = _load_agent_kb_file("pending_learnings.json")
    if not isinstance(pending, list) or index >= len(pending):
        raise HTTPException(status_code=404, detail="Pending learning not found")

    entry = pending.pop(index)
    _save_agent_kb_file("pending_learnings.json", pending)

    # Add to known_issues with auto_fix disabled (safety)
    known_issues = _load_agent_kb_file("known_issues.json")
    issues_list = known_issues if isinstance(known_issues, list) else known_issues.get("patterns", known_issues.get("issues", []))
    new_pattern = entry.get("suggested_pattern", {})
    new_pattern["auto_fix"] = False
    new_pattern["learned_confidence"] = entry.get("diagnosis_details", {}).get("confidence", 0.5)
    new_pattern["last_adjusted"] = datetime.now().isoformat()
    new_pattern["adjustment_reason"] = "Approved from pending learnings"
    issues_list.append(new_pattern)
    if isinstance(known_issues, list):
        _save_agent_kb_file("known_issues.json", issues_list)
    else:
        key = "patterns" if "patterns" in known_issues else "issues"
        known_issues[key] = issues_list
        _save_agent_kb_file("known_issues.json", known_issues)

    return {"success": True, "message": f"Pattern '{new_pattern.get('type', '')}' approved and added to knowledge base"}


@router.post("/api/agents/pending-learnings/{index}/reject")
async def reject_pending_learning(index: int):
    """Reject a pending learning -- removes it from the pending list."""
    pending = _load_agent_kb_file("pending_learnings.json")
    if not isinstance(pending, list) or index >= len(pending):
        raise HTTPException(status_code=404, detail="Pending learning not found")

    entry = pending.pop(index)
    _save_agent_kb_file("pending_learnings.json", pending)

    return {"success": True, "message": f"Pending learning rejected and removed"}
