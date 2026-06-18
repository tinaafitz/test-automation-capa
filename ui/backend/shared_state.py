"""
Shared mutable state for the ROSA Automation UI Backend.

All global dicts and their locks live here so that app.py and service
modules (jobs_service, etc.) operate on the *same* objects.
"""

import threading
from typing import Dict

from job_store import JobStore

# ── Job tracking (SQLite-backed, dict-like interface) ────────────────────
jobs = JobStore()
_jobs_lock = threading.Lock()

# ── AI Agent sessions (keyed by job_id) ──────────────────────────────────
ai_agent_sessions: Dict[str, dict] = {}
_sessions_lock = threading.Lock()

# ── Cluster tracking ─────────────────────────────────────────────────────
clusters: Dict[str, dict] = {}

# ── ROSA / OCP caches ────────────────────────────────────────────────────
rosa_status_cache = {"data": None, "timestamp": 0, "ttl": 30}
ocp_status_cache = {
    "data": None,
    "timestamp": 0,
    "ttl": 60,
}

# ── Last used YAML path for ROSA HCP provisioning ───────────────────────
last_rosa_yaml_path = {"path": None}

# ── Redis client (lazy init, optional) ──────────────────────────────
_redis_client = None


def get_redis_client():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import os
        import redis
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        _redis_client = redis.Redis.from_url(url, socket_connect_timeout=2, decode_responses=True)
        _redis_client.ping()
        return _redis_client
    except Exception:
        return None
