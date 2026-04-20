"""
Test-suite routes — FastAPI router for test-suite management endpoints.

Endpoints moved here from app.py:
  GET  /api/test-suites/list            (list available test suites)
  POST /api/test-suites/run             (run a test suite)
  GET  /api/test-suites/status/{run_id} (get test suite run status)
  GET  /api/test-suites/history         (get test suite run history)

Also contains:
  test_suite_runs   -- dict storing test suite execution history
  TestSuiteRun      -- Pydantic model for run requests
"""

import asyncio
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime
from typing import Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

router = APIRouter()


def _resolve(name: str):
    """Look up *name* in the ``app`` module at call time.

    This keeps tests working: they patch ``app.<symbol>``, and this
    function reads the patched value instead of a stale import-time
    reference.
    """
    _app = sys.modules.get("app")
    if _app is None:
        raise RuntimeError("app module not loaded")
    return getattr(_app, name)


# ── Shared state ──────────────────────────────────────────────────────

test_suite_runs: Dict[str, dict] = {}  # Store test suite execution history


# ── Pydantic models ──────────────────────────────────────────────────

class TestSuiteRun(BaseModel):
    suite_name: str
    extra_vars: dict = {}


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/api/test-suites/list")
async def list_test_suites():
    """List all available test suites"""
    try:
        project_root = os.environ.get("AUTOMATION_PATH") or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        test_suites_dir = os.path.join(project_root, "test-suites")

        if not os.path.exists(test_suites_dir):
            return {"success": True, "suites": [], "message": "No test suites directory found"}

        suites = []
        # Sort filenames to maintain numbered order (01-, 02-, 03-, etc.)
        for filename in sorted(os.listdir(test_suites_dir)):
            if filename.endswith(".json"):
                filepath = os.path.join(test_suites_dir, filename)
                with open(filepath, "r") as f:
                    suite_config = json.load(f)
                    suites.append({"id": filename.replace(".json", ""), "config": suite_config})

        return {"success": True, "suites": suites, "count": len(suites)}

    except Exception as e:
        return {"success": False, "message": f"Error listing test suites: {str(e)}", "suites": []}


@router.post("/api/test-suites/run")
async def run_test_suite(run_config: TestSuiteRun, background_tasks: BackgroundTasks):
    """Run a test suite"""
    try:
        project_root = os.environ.get("AUTOMATION_PATH") or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

        # Load suite configuration
        suite_file = os.path.join(project_root, "test-suites", f"{run_config.suite_name}.json")

        if not os.path.exists(suite_file):
            raise HTTPException(
                status_code=404, detail=f"Test suite '{run_config.suite_name}' not found"
            )

        with open(suite_file, "r") as f:
            suite_config = json.load(f)

        # Generate job ID (use jobs system for Task Summary integration)
        job_id = str(uuid.uuid4())

        jobs = _resolve("jobs")

        # Initialize job in jobs system (will appear in Task Summary)
        jobs[job_id] = {
            "id": job_id,
            "type": "test-suite",
            "suite_name": run_config.suite_name,
            "suite_title": f"⚡ PLAYBOOK TESTING: {suite_config.get('name', run_config.suite_name)}",
            "description": suite_config.get("description", "Running automated playbook"),
            "status": "pending",
            "progress": 0,
            "message": f"🧪 Queued for execution",
            "started_at": datetime.now(),
            "completed_at": None,
            "playbook_results": [],
            "total_playbooks": len(suite_config.get("playbooks", [])),
            "completed_playbooks": 0,
            "failed_playbooks": 0,
            "logs": [],
            "environment": "mce",
        }

        # Run test suite in background
        def run_test_suite_background():
            try:
                job_data = jobs[job_id]
                job_data["status"] = "running"
                job_data["message"] = f"⚡ PLAYBOOK TESTING: Running {suite_config['name']}"
                job_data["logs"].append(f"🚀 ⚡ PLAYBOOK TESTING: {suite_config['name']}")
                job_data["logs"].append(f"📋 Description: {suite_config.get('description', 'N/A')}")
                job_data["logs"].append(f"📦 Total playbooks: {job_data['total_playbooks']}")
                job_data["logs"].append("")

                playbooks = suite_config.get("playbooks", [])
                stop_on_failure = suite_config.get("stopOnFailure", False)

                for idx, playbook_config in enumerate(playbooks, 1):
                    playbook_display_name = playbook_config["name"]
                    playbook_file = playbook_config.get("file", playbook_config["name"])
                    timeout = playbook_config.get("timeout", 600)
                    required = playbook_config.get("required", True)

                    job_data["progress"] = int((idx - 1) / len(playbooks) * 100)
                    job_data["message"] = (
                        f"Running playbook {idx}/{len(playbooks)}: {playbook_display_name}"
                    )
                    job_data["logs"].append(
                        f"\n[{idx}/{len(playbooks)}] Running: {playbook_display_name}"
                    )
                    job_data["logs"].append(f"📄 {playbook_config.get('description', '')}")
                    job_data["logs"].append(f"📁 File: {playbook_file}")
                    job_data["logs"].append(f"⏱️  Timeout: {timeout}s")

                    playbook_start = datetime.now()
                    playbook_result = {
                        "playbook": playbook_display_name,
                        "description": playbook_config.get("description"),
                        "status": "running",
                        "started_at": playbook_start,
                        "completed_at": None,
                        "duration": None,
                        "exit_code": None,
                        "output": "",
                        "error": "",
                    }

                    try:
                        # Run playbook using ansible-playbook directly to pass extra_vars
                        playbook_path = os.path.join(project_root, playbook_file)

                        if not os.path.exists(playbook_path):
                            raise Exception(f"Playbook not found: {playbook_path}")

                        # Execute playbook with environment variables
                        env = os.environ.copy()

                        # Set AUTOMATION_PATH to project root
                        env["AUTOMATION_PATH"] = project_root

                        # Try to read credentials from vars/user_vars.yml if not in environment
                        try:
                            import yaml

                            user_vars_path = os.path.join(project_root, "vars", "user_vars.yml")
                            if os.path.exists(user_vars_path):
                                with open(user_vars_path, "r") as f:
                                    user_vars = yaml.safe_load(f) or {}
                                    if "OCP_HUB_CLUSTER_USER" not in env or not env.get(
                                        "OCP_HUB_CLUSTER_USER"
                                    ):
                                        env["OCP_HUB_CLUSTER_USER"] = user_vars.get(
                                            "OCP_HUB_CLUSTER_USER", ""
                                        )
                                    if "OCP_HUB_CLUSTER_PASSWORD" not in env or not env.get(
                                        "OCP_HUB_CLUSTER_PASSWORD"
                                    ):
                                        env["OCP_HUB_CLUSTER_PASSWORD"] = user_vars.get(
                                            "OCP_HUB_CLUSTER_PASSWORD", ""
                                        )
                                    if "OCP_HUB_API_URL" not in env or not env.get(
                                        "OCP_HUB_API_URL"
                                    ):
                                        env["OCP_HUB_API_URL"] = user_vars.get(
                                            "OCP_HUB_API_URL", ""
                                        )
                        except Exception as e:
                            print(f"Warning: Could not read user_vars.yml: {e}")

                        # Build ansible-playbook command
                        cmd = [
                            "ansible-playbook",
                            "-i",
                            "localhost,",
                            "--connection=local",
                            playbook_file,
                            "-e",
                            "skip_ansible_runner=true",
                            "-e",
                            f"ocp_user={env.get('OCP_HUB_CLUSTER_USER', '')}",
                            "-e",
                            f"ocp_password={env.get('OCP_HUB_CLUSTER_PASSWORD', '')}",
                            "-e",
                            f"api_url={env.get('OCP_HUB_API_URL', '')}",
                            "-e",
                            f"mce_namespace=multicluster-engine",
                            "-e",
                            f"AUTOMATION_PATH={project_root}",
                        ]

                        # Add extra vars from provisioning modal if provided
                        if run_config.extra_vars:
                            for key, value in run_config.extra_vars.items():
                                # Convert boolean values to lowercase strings for ansible
                                if isinstance(value, bool):
                                    value = str(value).lower()
                                cmd.extend(["-e", f"{key}={value}"])

                        result = subprocess.run(
                            cmd,
                            cwd=project_root,
                            capture_output=True,
                            text=True,
                            timeout=timeout,
                            env=env,
                        )

                        playbook_end = datetime.now()
                        duration = (playbook_end - playbook_start).total_seconds()

                        playbook_result.update(
                            {
                                "status": "passed" if result.returncode == 0 else "failed",
                                "completed_at": playbook_end,
                                "duration": duration,
                                "exit_code": result.returncode,
                                "output": result.stdout,
                                "error": result.stderr,
                            }
                        )

                        if result.returncode == 0:
                            job_data["logs"].append(f"✅ PASSED ({duration:.1f}s)")
                            job_data["completed_playbooks"] += 1
                        else:
                            job_data["logs"].append(f"❌ FAILED ({duration:.1f}s)")
                            job_data["logs"].append(f"Error: {result.stderr[:200]}")
                            job_data["failed_playbooks"] += 1

                            if required and stop_on_failure:
                                job_data["logs"].append(
                                    f"\n⚠️  Stopping test suite due to required playbook failure"
                                )
                                job_data["playbook_results"].append(playbook_result)
                                break

                    except subprocess.TimeoutExpired:
                        playbook_result.update(
                            {
                                "status": "timeout",
                                "completed_at": datetime.now(),
                                "duration": timeout,
                                "error": f"Playbook timed out after {timeout}s",
                            }
                        )
                        job_data["logs"].append(f"⏱️  TIMEOUT after {timeout}s")
                        job_data["failed_playbooks"] += 1

                        if required and stop_on_failure:
                            job_data["logs"].append(f"\n⚠️  Stopping test suite due to timeout")
                            job_data["playbook_results"].append(playbook_result)
                            break

                    except Exception as e:
                        playbook_result.update(
                            {"status": "error", "completed_at": datetime.now(), "error": str(e)}
                        )
                        job_data["logs"].append(f"💥 ERROR: {str(e)}")
                        job_data["failed_playbooks"] += 1

                        if required and stop_on_failure:
                            job_data["logs"].append(f"\n⚠️  Stopping test suite due to error")
                            job_data["playbook_results"].append(playbook_result)
                            break

                    job_data["playbook_results"].append(playbook_result)

                # Finalize run
                job_data["completed_at"] = datetime.now()
                job_data["progress"] = 100

                total_duration = (job_data["completed_at"] - job_data["started_at"]).total_seconds()

                if job_data["failed_playbooks"] == 0:
                    job_data["status"] = "completed"
                    job_data["message"] = (
                        f"⚡ PLAYBOOK TESTING: Playbook passed! ({total_duration:.1f}s)"
                    )
                    job_data["logs"].append(f"\n✅ ⚡ PLAYBOOK TESTING COMPLETE: Playbook passed!")
                else:
                    job_data["status"] = "failed"
                    job_data["message"] = (
                        f"⚡ PLAYBOOK TESTING: Playbook failed ({total_duration:.1f}s)"
                    )
                    job_data["logs"].append(f"\n❌ ⚡ PLAYBOOK TESTING COMPLETE: Playbook failed")

                job_data["logs"].append(f"\n📊 Summary:")
                job_data["logs"].append(f"   Total: {job_data['total_playbooks']}")
                job_data["logs"].append(f"   Passed: {job_data['completed_playbooks']}")
                job_data["logs"].append(f"   Failed: {job_data['failed_playbooks']}")
                job_data["logs"].append(f"   Duration: {total_duration:.1f}s")

            except Exception as e:
                import traceback

                job_data["status"] = "error"
                job_data["message"] = f"Test suite error: {str(e)}"
                job_data["logs"].append(f"\n💥 Fatal error: {str(e)}")
                job_data["logs"].append(traceback.format_exc())
                job_data["completed_at"] = datetime.now()

        # Start background task (use asyncio.to_thread to avoid blocking event loop)
        asyncio.create_task(asyncio.to_thread(run_test_suite_background))

        return {
            "success": True,
            "job_id": job_id,
            "run_id": job_id,  # Keep for backwards compatibility
            "message": f"⚡ PLAYBOOK TESTING: {suite_config['name']} started",
            "suite_name": suite_config["name"],
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback

        print(f"❌ Error starting test suite: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error starting test suite: {str(e)}")


@router.get("/api/test-suites/status/{run_id}")
async def get_test_suite_status(run_id: str):
    """Get status of a running or completed test suite"""
    try:
        if run_id not in test_suite_runs:
            raise HTTPException(status_code=404, detail=f"Test suite run '{run_id}' not found")

        run_data = test_suite_runs[run_id]

        return {"success": True, "run": run_data}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting test suite status: {str(e)}")


@router.get("/api/test-suites/history")
async def get_test_suite_history():
    """Get history of all test suite runs"""
    try:
        # Sort by started_at descending (newest first)
        sorted_runs = sorted(
            test_suite_runs.values(), key=lambda x: x.get("started_at", datetime.min), reverse=True
        )

        return {"success": True, "runs": sorted_runs, "count": len(sorted_runs)}

    except Exception as e:
        return {
            "success": False,
            "message": f"Error getting test suite history: {str(e)}",
            "runs": [],
        }
