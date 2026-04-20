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
    jobs, _jobs_lock,
    ai_agent_sessions, _sessions_lock,
    clusters,
    rosa_status_cache, ocp_status_cache,
    last_rosa_yaml_path,
)

# Jobs service (router + helper functions)
from jobs_service import router as jobs_router, normalize_timestamp, check_and_timeout_stuck_jobs, get_agent_stats
app.include_router(jobs_router)

# Agents service (router + agent lifecycle helpers)
from agents_service import (
    router as agents_router,
    init_ai_agents,
    _load_agent_kb_file,
    _save_agent_kb_file,
    AI_AGENTS_AVAILABLE as _agents_ai_available,
)
app.include_router(agents_router)



# Notification routes (model, helper, endpoints) — extracted to notification_routes.py
from notification_routes import (
    router as notification_router,
    NotificationSettings,
    send_cluster_notifications,
    slack_service,
    email_service,
)
app.include_router(notification_router)



# Static / reference-data routes — extracted to static_routes.py
from static_routes import (
    router as static_router,
    root,
    health_check,
    get_supported_versions,
    _get_supported_versions_sync,
    get_templates,
    analyze_yaml,
    get_onboarding_tour,
    get_available_diagnostic_checks,
    run_diagnostics,
    get_environment_overview,
    get_user_profile,
    get_build_templates,
    validate_config,
)
app.include_router(static_router)


# User Journey APIs — moved to static_routes.py


# Credential & connection-status routes — extracted to credentials_routes.py
from credentials_routes import (
    router as credentials_router,
    CredentialsUpdate,
    _get_rosa_status_sync,
    _get_ocp_connection_status_sync,
    get_rosa_status,
    get_config_status,
    get_credentials,
    save_credentials,
    get_ocp_connection_status,
    get_aws_credentials_status,
    get_guided_setup_status,
)
app.include_router(credentials_router)


# Provisioning routes (generate-yaml, apply-yaml) — extracted to provisioning_routes.py
from provisioning_routes import (
    router as provisioning_router,
    generate_provisioning_yaml,
    apply_provisioning_yaml,
)
app.include_router(provisioning_router)

# AI chat endpoint — extracted to ai_chat_routes.py
from ai_chat_routes import (
    router as ai_chat_router,
    ai_assistant_chat,
)
app.include_router(ai_chat_router)


# Test suite routes — extracted to test_suite_routes.py
from test_suite_routes import (
    router as test_suite_router,
    test_suite_runs,
    TestSuiteRun,
    list_test_suites,
    run_test_suite,
    get_test_suite_status,
    get_test_suite_history,
)
app.include_router(test_suite_router)

# Workflow & trigger routes — extracted to workflow_routes.py
from workflow_routes import (
    router as workflow_router,
    WORKFLOWS_FILE,
    _normalize_workflow,
    _load_workflows,
    _save_workflows,
    WorkflowSave,
    TriggerCreate,
    _get_trigger_or_404,
    _fire_and_update,
)
app.include_router(workflow_router)

# Re-export trigger_service symbols for backward compat (tests patch via app.*)
import logging as _trigger_logging
_trigger_logger = _trigger_logging.getLogger("trigger_routes")
from trigger_service import (
    TRIGGER_STATE_FILE,
    TRIGGER_MIN_INTERVAL,
    AUTO_DISABLE_THRESHOLD,
    MAX_PAGINATION_LIMIT,
    _trigger_last_fire,
    _active_trigger_runs,
    _load_trigger_state,
    _save_trigger_state,
    _send_trigger_notification,
    _update_trigger_after_run,
    _fire_trigger_workflow,
    check_rate_limit,
    TriggerScheduler,
    _trigger_scheduler,
)


# Cluster actions & specs routes — extracted to cluster_actions_routes.py
from cluster_actions_routes import (
    router as cluster_actions_router,
    _load_feature_registry_full,
    _load_feature_registry,
    _get_registry,
    _get_feature_index,
    CLUSTER_FEATURE_REGISTRY,
    _FEATURE_INDEX,
    _validate_cluster_name,
    _validate_feature_value,
    _find_feature,
    _build_json_merge_patch,
    ClusterActionRequest,
    ACTION_HISTORY_FILE,
    _load_action_history,
    _save_action_history,
    _record_action,
    _cluster_locks,
    _CLUSTER_LOCKS_MAX,
    _get_cluster_lock,
    SPECS_DIR,
    _find_spec_file,
    _resolve_spec_to_plan,
    execute_cluster_actions,
    get_action_history,
    provision_cluster_with_features,
    discover_clusters,
    get_cluster_feature_status,
    list_cluster_specs,
    get_cluster_spec,
    plan_cluster_spec,
    execute_cluster_spec,
    save_cluster_spec,
    get_feature_registry,
    get_suite_features,
)
app.include_router(cluster_actions_router)

# MCE environment management routes — extracted to mce_environments_routes.py
from mce_environments_routes import (
    router as mce_environments_router,
    list_mce_environments,
    get_mce_environment,
    save_mce_environment,
    update_mce_environment_status,
    get_mce_environment_stats,
    search_mce_environments,
)
app.include_router(mce_environments_router)


# AWS dashboard routes (Jenkins, GitHub, AWS usage) — extracted to aws_dashboard_routes.py
from aws_dashboard_routes import (
    router as aws_dashboard_router,
    _collect_aws_usage_data,
    _get_aws_history_db,
    _init_aws_history_db,
    _save_aws_usage_snapshot,
    _aws_usage_snapshot_loop,
    get_jenkins_test_results_trend,
    get_github_repo_activity,
    get_aws_usage,
    get_aws_usage_trend,
    get_aws_config,
    get_single_resource_usage,
    get_resource_details,
)
app.include_router(aws_dashboard_router)

# MCE features routes (get_mce_features, get_mce_yaml, get_mce_resources) — extracted to mce_features_routes.py
from mce_features_routes import (
    router as mce_features_router,
    _get_mce_features_sync,
    get_mce_features,
    get_mce_yaml,
    get_mce_resources,
)
app.include_router(mce_features_router)

# Resource browser routes (kubectl/oc resource browsing, YAML paths) — extracted to resource_browser_routes.py
from resource_browser_routes import (
    router as resource_browser_router,
    execute_ocp_command,
    get_minikube_active_resources,
    get_minikube_resource_detail,
    get_ocp_resource_detail,
    get_last_rosa_yaml_path,
    save_rosa_yaml_path,
    get_log_forwarding_config,
)
app.include_router(resource_browser_router)

# Minikube & CAPI component routes — extracted to minikube_routes.py
from minikube_routes import (
    router as minikube_router,
    run_minikube_init_playbook,
    _run_minikube_create,
    get_capi_component_versions,
    get_capi_cli_versions,
    list_minikube_clusters,
    get_current_kubectl_context,
    get_active_minikube_profile,
    verify_minikube_cluster,
    initialize_minikube_capi,
    create_minikube_cluster,
    delete_minikube_cluster,
    execute_minikube_command,
)
app.include_router(minikube_router)

# Ansible execution routes (run-task, run-role, run-playbook) — extracted to ansible_routes.py
from ansible_routes import (
    router as ansible_router,
    run_ansible_task_background,
    run_ansible_task,
    run_ansible_role,
    _run_playbook_in_thread,
    run_playbook_background,
    run_ansible_playbook_endpoint,
)
app.include_router(ansible_router)

# ROSA cluster lifecycle routes — extracted to rosa_cluster_routes.py
from rosa_cluster_routes import (
    router as rosa_cluster_router,
    ClusterConfig,
    _wait_for_resource_deletion,
    _run_deletion_wait_loops,
    create_cluster,
    get_cluster,
    delete_cluster,
    get_rosa_clusters,
    _get_rosa_clusters_sync,
    perform_cluster_deletion,
    delete_rosa_cluster,
    list_clusters,
    get_cluster_status,
)
app.include_router(rosa_cluster_router)


@app.on_event("startup")
async def start_trigger_scheduler():
    await _trigger_scheduler.start()


@app.on_event("shutdown")
async def stop_trigger_scheduler():
    await _trigger_scheduler.stop()


@app.on_event("startup")
async def start_aws_snapshot_collector():
    asyncio.create_task(_aws_usage_snapshot_loop())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
