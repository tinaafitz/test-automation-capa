"""
Shared mutable state for the ROSA Automation UI Backend.

All global dicts and their locks live here so that app.py and service
modules (jobs_service, etc.) operate on the *same* objects.
"""

import threading
from typing import Dict

# ── Job tracking ─────────────────────────────────────────────────────────
jobs: Dict[str, dict] = {}
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
