#!/usr/bin/env python3
"""
ROSA Automation UI Backend
FastAPI-based backend for the ROSA cluster automation interface
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional
import asyncio
import json
import re
import subprocess
import threading
import uuid
from datetime import datetime
import os
import yaml
import sqlite3
import time
from ai_assistant_service import AIAssistantService

# AI Agent Framework (monitoring, diagnostic, remediation)
try:
    import sys

    _project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    from agents import MonitoringAgent, DiagnosticAgent, RemediationAgent, LearningAgent, IssueState

    AI_AGENTS_AVAILABLE = True
    print("AI Agent Framework loaded successfully")
except ImportError as e:
    AI_AGENTS_AVAILABLE = False
    print(f"AI Agent Framework not available: {e}")

from capa_core import (
    resolve_spec_to_plan as _core_resolve_spec_to_plan,
)
import minikube_ops


app = FastAPI(title="ROSA Automation API", version="1.0.0")

# Add production endpoints (health checks, metrics, monitoring)
try:
    from app_extensions import add_production_endpoints

    add_production_endpoints(app)
except ImportError:
    print("⚠️  app_extensions not available - production endpoints not loaded")

# Initialize AI assistant service
ai_service = AIAssistantService()

# CORS middleware for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared mutable state (single source of truth lives in shared_state.py)
from shared_state import (
    jobs,
    _jobs_lock,
    ai_agent_sessions,
    _sessions_lock,
    clusters,
    rosa_status_cache,
    ocp_status_cache,
    last_rosa_yaml_path,
)

# Jobs service
from jobs_service import (
    router as jobs_router,
    normalize_timestamp,
    check_and_timeout_stuck_jobs,
    get_agent_stats,
)

app.include_router(jobs_router)

# Agents service
from agents_service import router as agents_router, init_ai_agents

app.include_router(agents_router)

# Notification routes
from notification_routes import (
    router as notification_router,
    send_cluster_notifications,
    slack_service,
    email_service,
)

app.include_router(notification_router)

# Static / reference-data routes
from static_routes import router as static_router

app.include_router(static_router)

# Credentials routes
from credentials_routes import (
    router as credentials_router,
    _get_rosa_status_sync,
    _get_ocp_connection_status_sync,
    get_rosa_status,
)

app.include_router(credentials_router)

# Provisioning routes
from provisioning_routes import router as provisioning_router

app.include_router(provisioning_router)

# AI chat routes
from ai_chat_routes import router as ai_chat_router

app.include_router(ai_chat_router)

# Test suite routes
from test_suite_routes import router as test_suite_router, test_suite_runs

app.include_router(test_suite_router)

# Workflow & trigger routes
from workflow_routes import (
    router as workflow_router,
    WORKFLOWS_FILE,
    _normalize_workflow,
    _load_workflows,
    _get_trigger_or_404,
    _fire_and_update,
)

app.include_router(workflow_router)

from trigger_service import (
    _trigger_scheduler,
    _load_trigger_state,
    _save_trigger_state,
    check_rate_limit,
)

# Cluster actions & specs routes
from cluster_actions_routes import (
    router as cluster_actions_router,
    _load_feature_registry_full,
    _get_registry,
    _get_feature_index,
    CLUSTER_FEATURE_REGISTRY,
    _FEATURE_INDEX,
    _validate_cluster_name,
    _validate_feature_value,
    _find_feature,
    _build_json_merge_patch,
    ACTION_HISTORY_FILE,
    _load_action_history,
    _save_action_history,
    _record_action,
    _cluster_locks,
    _get_cluster_lock,
    _find_spec_file,
    _resolve_spec_to_plan,
)

app.include_router(cluster_actions_router)

# MCE environment management routes
from mce_environments_routes import router as mce_environments_router

app.include_router(mce_environments_router)

# AWS dashboard routes
from aws_dashboard_routes import (
    router as aws_dashboard_router,
    _collect_aws_usage_data,
    _get_aws_history_db,
    _save_aws_usage_snapshot,
    _aws_usage_snapshot_loop,
)

app.include_router(aws_dashboard_router)

from aws_orphan_report import daily_orphan_report_loop as _daily_orphan_report_loop

# MCE features routes
from mce_features_routes import router as mce_features_router, _get_mce_features_sync

app.include_router(mce_features_router)

# Resource browser routes
from resource_browser_routes import router as resource_browser_router

app.include_router(resource_browser_router)

# Minikube & CAPI component routes
from minikube_routes import (
    router as minikube_router,
    run_minikube_init_playbook,
    _run_minikube_create,
)

app.include_router(minikube_router)

# Ansible execution routes
from ansible_routes import (
    router as ansible_router,
    run_ansible_task_background,
    _run_playbook_in_thread,
    run_playbook_background,
)

app.include_router(ansible_router)

# Workflow orchestration routes
from workflow_orchestrator_routes import router as orchestrator_router

app.include_router(orchestrator_router)

# ROSA cluster lifecycle routes
from rosa_cluster_routes import (
    router as rosa_cluster_router,
    _wait_for_resource_deletion,
    _run_deletion_wait_loops,
    _get_rosa_clusters_sync,
    perform_cluster_deletion,
)

app.include_router(rosa_cluster_router)

from must_gather_routes import router as must_gather_router
app.include_router(must_gather_router)


@app.on_event("startup")
async def start_trigger_scheduler():
    await _trigger_scheduler.start()


@app.on_event("shutdown")
async def stop_trigger_scheduler():
    await _trigger_scheduler.stop()


@app.on_event("startup")
async def configure_thread_pool():
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    loop = asyncio.get_running_loop()
    loop.set_default_executor(ThreadPoolExecutor(max_workers=20))


@app.on_event("startup")
async def start_aws_snapshot_collector():
    asyncio.create_task(_aws_usage_snapshot_loop())


@app.on_event("startup")
async def start_daily_orphan_report():
    asyncio.create_task(_daily_orphan_report_loop())


@app.on_event("startup")
async def check_redis_celery():
    try:
        from celery_app import is_redis_available, get_worker_stats
        from workflow_orchestrator import get_execution_mode, ExecutionMode
        mode = get_execution_mode()
        if is_redis_available():
            print("Redis connected")
            stats = get_worker_stats()
            if stats.get("available"):
                print(f"Celery workers online: {stats['worker_count']}")
            else:
                print("Celery workers not yet available (start with: celery -A celery_app worker)")
        else:
            print("Redis not available (orchestrator will use local mode)")
        if mode == ExecutionMode.CELERY:
            print("Orchestrator mode: celery")
        else:
            print(f"Orchestrator mode: {mode.value}")
    except ImportError:
        print("Celery/Redis packages not installed (orchestrator using local mode)")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
