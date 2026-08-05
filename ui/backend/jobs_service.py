"""
Jobs service module — FastAPI router for job-related endpoints.

Endpoints moved here from app.py:
  GET    /api/jobs
  DELETE /api/jobs
  GET    /api/jobs/{job_id}
  GET    /api/jobs/{job_id}/logs
  POST   /api/jobs/{job_id}/cancel
  WS     /ws/jobs/{job_id}
  GET    /api/jobs/{job_id}/agent-stats
"""

import asyncio
import json
import sys
from datetime import datetime

from fastapi import APIRouter, HTTPException, WebSocket

from shared_state import jobs, ai_agent_sessions

router = APIRouter()


# ── Helper functions ─────────────────────────────────────────────────────

def normalize_timestamp(value):
    """Normalize various timestamp formats to datetime for comparison"""
    from datetime import datetime

    if value is None:
        return datetime.min

    # Already a datetime object
    if isinstance(value, datetime):
        return value

    # Unix timestamp (float or int)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value)
        except (ValueError, OSError):
            return datetime.min

    # ISO string or other string format
    if isinstance(value, str):
        if not value or value == "0":
            return datetime.min
        try:
            # Try parsing ISO format
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return datetime.min

    return datetime.min


def check_and_timeout_stuck_jobs():
    """Check for stuck jobs and mark them as failed if they've been running too long"""
    TIMEOUT_MINUTES = 90  # Timeout after 90 minutes (allows for long ROSA operations like delete/provision)

    current_time = datetime.now()
    stuck_jobs = []

    for job_id, job in jobs.items():
        # Only check running jobs
        if job.get("status") != "running":
            continue

        # Get job start time
        started_at = job.get("started_at")
        if not started_at:
            # If no started_at, use created_at
            started_at = job.get("created_at")

        if not started_at:
            continue

        # Parse the timestamp
        try:
            if isinstance(started_at, str):
                start_time = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            else:
                start_time = started_at
        except (ValueError, AttributeError):
            continue

        # Check if job has been running for too long
        elapsed_time = (current_time - start_time).total_seconds() / 60  # Convert to minutes

        if elapsed_time > TIMEOUT_MINUTES:
            # Mark job as failed due to timeout
            jobs[job_id]["status"] = "failed"
            jobs[job_id][
                "message"
            ] = f"Job timed out after {int(elapsed_time)} minutes with no progress"
            jobs[job_id]["error"] = f"Job exceeded timeout limit of {TIMEOUT_MINUTES} minutes"
            jobs[job_id]["completed_at"] = datetime.now().isoformat()
            jobs[job_id]["progress"] = 0
            stuck_jobs.append(job_id)

            # Persist agent stats before cleaning up session
            persist_agent_stats_on_completion(job_id)

            print(f"⏱️ Marked job {job_id} as failed due to timeout ({int(elapsed_time)} minutes)")

    return stuck_jobs


def persist_agent_stats_on_completion(job_id: str):
    """Save agent stats to the job record in SQLite when a job completes."""
    try:
        # Get current agent stats
        stats = get_agent_stats(job_id)
        
        # Only persist if agent was enabled and we have meaningful data
        if stats.get("enabled") and job_id in jobs:
            # Store the agent stats in the job record (this auto-persists to SQLite via JobStore)
            jobs[job_id]["agent_stats"] = stats
            
            # Clean up the in-memory agent session since the job is complete
            if job_id in ai_agent_sessions:
                ai_agent_sessions.pop(job_id, None)
                print(f"[AI Agent] Stats persisted and session cleaned up for job {job_id}")
    except Exception as e:
        print(f"[AI Agent] Error persisting stats for job {job_id}: {e}")


def get_agent_stats(job_id: str) -> dict:
    """Get AI agent statistics for a job."""
    session = ai_agent_sessions.get(job_id)
    if not session:
        # Try to get persisted agent stats from the job record if job is not in memory
        if job_id in jobs:
            persisted_stats = jobs[job_id].get("agent_stats")
            if persisted_stats:
                return persisted_stats
        return {"enabled": False}

    monitor = session["monitor"]
    remediation = session["remediation"]

    # Build per-resource event details with full timeline
    events = jobs.get(job_id, {}).get("agent_events", [])
    resource_details = {}
    for event in events:
        rk = event.get("resource_key", "unknown")
        if rk not in resource_details:
            resource_details[rk] = {
                "resource_key": rk,
                "issue_type": event.get("issue_type", ""),
                "diagnosis": event.get("diagnosis", ""),
                "fix_applied": event.get("fix_applied", ""),
                "timeline": [],
            }
        # Update latest diagnosis/fix
        resource_details[rk]["diagnosis"] = event.get("diagnosis", "")
        resource_details[rk]["fix_applied"] = event.get("fix_applied", "")
        # Add to timeline
        resource_details[rk]["timeline"].append({
            "time": event.get("timestamp", ""),
            "action": event.get("fix_applied", ""),
            "detail": event.get("diagnosis", ""),
            "result": event.get("remediation_result", ""),
            "confidence": event.get("confidence", 0),
        })

    # Add resolution status from tracked issues
    for key, tracked in monitor._tracked_issues.items():
        rk = tracked.resource_key
        if rk in resource_details:
            resource_details[rk]["status"] = tracked.state.value
            resource_details[rk]["attempts"] = tracked.attempts

    # Count unique issues (by resource) instead of raw pattern matches
    unique_issues = len(resource_details)
    # Count meaningful interventions (exclude log_and_continue and already-deleted confirmations)
    meaningful_interventions = sum(
        1 for i in remediation.interventions
        if i.get("type") not in ("log_and_continue",)
        and "already deleted" not in i.get("details", {}).get("message", "")
    )

    # Flush learning agent outcomes and apply confidence adjustments
    learning = session.get("learning")
    learning_summary = {}
    if learning:
        try:
            learning_summary = learning.end_of_run_summary()
        except Exception as e:
            print(f"[AI Agent] Learning summary error: {e}")

    return {
        "enabled": True,
        "issues_detected": unique_issues,
        "interventions": meaningful_interventions,
        "total_checks": len(monitor.patterns_detected),
        "resource_details": list(resource_details.values()),
        "learning": learning_summary,
    }


# ── Endpoints ────────────────────────────────────────────────────────────

def _resolve(name: str):
    """Look up *name* via the app module so that unittest.mock.patch on
    ``app.<name>`` takes effect even though the endpoint lives here."""
    app_mod = sys.modules.get("app")
    if app_mod is not None:
        return getattr(app_mod, name)
    # Fallback to local module scope (e.g. when running standalone)
    return globals()[name]


@router.get("/api/jobs")
async def list_jobs():
    """List all jobs"""
    try:
        # Check for and timeout stuck jobs before returning the list
        _resolve("check_and_timeout_stuck_jobs")()

        # Return all jobs sorted by creation time (newest first)
        job_list = []
        for job_id, job in jobs.items():
            job_data = {**job, "id": job_id}
            job_list.append(job_data)

        # Sort by created_at timestamp (newest first)
        # Use normalize_timestamp to handle different timestamp formats
        job_list.sort(key=lambda x: normalize_timestamp(x.get("created_at")), reverse=True)

        return {"success": True, "jobs": job_list, "count": len(job_list)}
    except Exception as e:
        print(f"❌ Error in list_jobs: {str(e)}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e), "jobs": [], "count": 0}


@router.delete("/api/jobs")
async def clear_all_jobs():
    """Clear all jobs from history"""
    jobs.clear()
    return {"success": True, "message": "All jobs cleared", "count": 0}


@router.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get job status"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    return jobs[job_id]


@router.get("/api/jobs/{job_id}/logs")
async def get_job_logs(job_id: str):
    """Get job logs"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    return {"success": True, "logs": jobs[job_id].get("logs", [])}


@router.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a running job"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]

    # Only allow canceling jobs that are currently running
    if job.get("status") != "running":
        raise HTTPException(
            status_code=400, detail=f"Cannot cancel job with status: {job.get('status')}"
        )

    # Kill the subprocess immediately — don't wait for next stdout line
    from ansible_routes import kill_job_subprocess

    killed = kill_job_subprocess(job_id)

    # Mark job as cancelled
    jobs[job_id]["status"] = "failed"
    jobs[job_id]["message"] = "Job cancelled by user"
    jobs[job_id]["error"] = "Job was manually cancelled"
    jobs[job_id]["completed_at"] = datetime.now().isoformat()
    jobs[job_id]["progress"] = 0

    # Persist agent stats before cleaning up session
    persist_agent_stats_on_completion(job_id)

    return {
        "success": True,
        "message": "Job cancelled successfully",
        "job_id": job_id,
        "process_killed": killed,
    }


@router.websocket("/ws/jobs/{job_id}")
async def websocket_job_updates(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for real-time job updates"""
    await websocket.accept()

    if job_id not in jobs:
        await websocket.close(code=1003, reason="Job not found")
        return

    try:
        last_progress = -1
        while True:
            job = jobs.get(job_id, {})
            current_progress = job.get("progress", 0)

            # Send update if progress changed
            if current_progress != last_progress:
                update = {
                    "job_id": job_id,
                    "status": job.get("status", "unknown"),
                    "progress": current_progress,
                    "message": job.get("message", ""),
                    "timestamp": datetime.now().isoformat(),
                }
                # Include AI agent stats if available
                agent_stats = get_agent_stats(job_id)
                if agent_stats.get("enabled"):
                    update["agent_stats"] = agent_stats
                await websocket.send_json(update)
                last_progress = current_progress

            # Close connection if job completed
            if job.get("status") in ["completed", "failed"]:
                break

            await asyncio.sleep(2)  # Update every 2 seconds

    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await websocket.close()


# AI Agent Stats API
@router.get("/api/jobs/{job_id}/agent-stats")
async def get_job_agent_stats(job_id: str):
    """Get AI agent statistics for a specific job"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    stats = get_agent_stats(job_id)
    # Also include any stored agent events
    events = jobs[job_id].get("agent_events", [])
    return {"success": True, "agent_stats": stats, "agent_events": events}
