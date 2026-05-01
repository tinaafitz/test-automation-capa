"""
Ansible execution routes -- FastAPI router for running Ansible tasks, roles,
and playbooks.

Endpoints moved here from app.py:
  POST   /api/ansible/run-task
  POST   /api/ansible/run-role
  POST   /api/ansible/run-playbook

Also contains:
  run_ansible_task_background  -- background worker for task execution
  _run_playbook_in_thread      -- sync helper for playbook streaming
  run_playbook_background      -- async wrapper for _run_playbook_in_thread
"""

import asyncio
import os
import re
import subprocess
import sys
import threading
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, BackgroundTasks

from shared_state import jobs, ai_agent_sessions
from jobs_service import get_agent_stats
from agents_service import init_ai_agents
from playbook_executor import build_playbook_command

router = APIRouter()


def _resolve(name: str):
    """Look up *name* via the app module so that unittest.mock.patch on
    ``app.<name>`` takes effect even though the endpoint lives here."""
    app_mod = sys.modules.get("app")
    if app_mod is not None:
        return getattr(app_mod, name)
    return globals()[name]


def run_ansible_task_background(
    job_id, task_file, playbook_file, description, kube_context, extra_vars, cluster_type
):
    """Background task to run ansible playbook or task"""
    import tempfile
    import yaml

    try:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["progress"] = 10
        jobs[job_id]["message"] = f"{description} in progress..."

        # Use AUTOMATION_PATH environment variable if set, otherwise calculate from file path
        project_root = os.environ.get("AUTOMATION_PATH") or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

        # If playbook_file is provided, run it directly
        if playbook_file:
            playbook_path = os.path.join(project_root, playbook_file)
            if not os.path.exists(playbook_path):
                raise Exception(f"Playbook file not found: {playbook_file}")

            # Run the playbook directly
            cmd = [
                "ansible-playbook",
                playbook_path,
                "-i",
                "localhost,",  # Inline inventory with localhost
                "-e",
                "skip_ansible_runner=true",
                "-e",
                f"AUTOMATION_PATH={project_root}",
                "-vv",  # Very verbose output (shows task results)
            ]

            # Add cluster context if provided
            if kube_context:
                cmd.extend(["-e", f"KUBE_CONTEXT={kube_context}"])

            # Add extra vars if provided (skip empty values so vars_files defaults are used)
            for key, value in extra_vars.items():
                if value != '':
                    cmd.extend(["-e", f"{key}={value}"])

            print(f"Running ansible playbook: {' '.join(cmd)}")

            # Run the command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=project_root,
            )

            # Extract detailed error messages
            detailed_error = ""
            error_summary = ""
            if result.returncode != 0 and result.stdout:
                # First try to find Ansible fail task messages (e.g., "msg": "...")
                fail_match = re.search(
                    r'fatal:.*?FAILED!.*?"msg":\s*"(.+?)"', result.stdout, re.DOTALL
                )
                if fail_match:
                    # Extract the message and unescape it
                    detailed_error = fail_match.group(1).strip()
                    # Unescape newlines
                    detailed_error = detailed_error.replace("\\n", "\n")

                    # Extract a short summary for the UI
                    # Look for the main error heading (lines starting with ❌)
                    summary_match = re.search(r'❌\s*(.+?)(?:\n|$)', detailed_error)
                    if summary_match:
                        error_summary = summary_match.group(1).strip()
                    # If no emoji heading, check for "ROOT CAUSE:" section
                    elif "ROOT CAUSE:" in detailed_error or "🔍 ROOT CAUSE:" in detailed_error:
                        # Extract first bullet point after ROOT CAUSE
                        root_cause_match = re.search(r'(?:ROOT CAUSE:.*?)\n\s*[•\-]\s*(.+?)(?:\n|$)', detailed_error, re.DOTALL)
                        if root_cause_match:
                            error_summary = root_cause_match.group(1).strip()

                    # Fallback: use first line of error message
                    if not error_summary and detailed_error:
                        error_summary = detailed_error.split('\n')[0][:100]

            error_message = (
                detailed_error
                if detailed_error
                else (result.stderr if result.returncode != 0 else "")
            )

            # Use summary for the message field if available, full error in error field
            display_message = error_summary if error_summary else error_message

            # Update job status with timestamp
            completed_time = datetime.now().strftime("%-I:%M:%S %p")  # e.g., "4:39:21 AM"

            if result.returncode == 0:
                jobs[job_id]["status"] = "completed"
                jobs[job_id]["progress"] = 100
                jobs[job_id][
                    "message"
                ] = f"{description} completed and refreshed at {completed_time}"
                jobs[job_id]["completed_at"] = datetime.now().isoformat()
            else:
                jobs[job_id]["status"] = "failed"
                jobs[job_id]["message"] = f"{description} failed: {display_message}"
                jobs[job_id]["error"] = error_message
                jobs[job_id]["completed_at"] = datetime.now().isoformat()

            jobs[job_id]["logs"] = result.stdout.split("\n") + result.stderr.split("\n")
            return

        # Handle task_file - create temporary playbook
        task_path = os.path.join(project_root, task_file)
        if not os.path.exists(task_path):
            raise Exception(f"Task file not found: {task_file}")

        # Create temporary playbook (similar to existing code)
        tasks = []

        # Check if this is an MCE task that needs OCP login
        mce_tasks = [
            "validate-capa-environment",
            "validate-mce",
            "enable_capi_capa",
            "get_capi_capa_status",
            "get_mce_component_status",
        ]
        if any(task in task_file for task in mce_tasks):
            # Add OCP login and variable setup tasks first
            tasks.extend(
                [
                    {
                        "name": "Set OCP credentials",
                        "set_fact": {
                            "ocp_user": "{{ OCP_HUB_CLUSTER_USER }}",
                            "ocp_password": "{{ OCP_HUB_CLUSTER_PASSWORD }}",
                            "api_url": "{{ OCP_HUB_API_URL }}",
                        },
                    },
                    {
                        "name": "Login to OCP",
                        "include_tasks": f"{project_root}/tasks/login_ocp.yml",
                    },
                ]
            )

        # Set AUTOMATION_PATH as a fact
        tasks.append(
            {
                "name": "Set AUTOMATION_PATH",
                "set_fact": {"AUTOMATION_PATH": project_root},
            }
        )

        # Add the main task
        tasks.append({"name": "Include task file", "include_tasks": f"{project_root}/{task_file}"})

        playbook_content = [
            {
                "name": f"Run task: {description}",
                "hosts": "localhost",
                "connection": "local",
                "gather_facts": False,
                "vars": {
                    "AUTOMATION_PATH": project_root,
                    "playbook_dir": project_root,
                },
                "vars_files": [
                    f"{project_root}/vars/vars.yml",
                    f"{project_root}/vars/user_vars.yml",
                ],
                "tasks": tasks,
            }
        ]

        # Write temporary playbook
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False, dir="/tmp") as f:
            yaml.dump(playbook_content, f, default_flow_style=False)
            temp_playbook = f.name

        try:
            # Prepare ansible command
            cmd = [
                "ansible-playbook",
                temp_playbook,
                "-i",
                "localhost,",
                "-e",
                "skip_ansible_runner=true",
                "-e",
                f"AUTOMATION_PATH={project_root}",
                "-e",
                f"playbook_dir={project_root}",
                "-v",
            ]

            # Add cluster context if provided
            if kube_context:
                cmd.extend(["-e", f"KUBE_CONTEXT={kube_context}"])

            # Add extra vars if provided (skip empty values so vars_files defaults are used)
            for key, value in extra_vars.items():
                if value != '':
                    cmd.extend(["-e", f"{key}={value}"])

            print(f"Running ansible task: {' '.join(cmd)}")

            # Set environment variables
            env = os.environ.copy()
            env["ANSIBLE_PLAYBOOK_DIR"] = project_root

            # Run the command with Popen
            process = subprocess.Popen(
                cmd,
                cwd=project_root,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=-1,
            )

            try:
                stdout, stderr = process.communicate(timeout=300)
                result = type(
                    "obj",
                    (object,),
                    {"returncode": process.returncode, "stdout": stdout, "stderr": stderr},
                )()
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                raise
            except BrokenPipeError as e:
                print(f"❌ [ANSIBLE-TASK] Broken pipe error: {str(e)}")
                try:
                    stdout, stderr = process.communicate(timeout=5)
                except:
                    stdout, stderr = "", str(e)
                result = type(
                    "obj",
                    (object,),
                    {"returncode": -1, "stdout": stdout, "stderr": f"Broken pipe error: {stderr}"},
                )()

            # Parse output
            stdout_lines = result.stdout.split("\n") if result.stdout else []
            stderr_lines = result.stderr.split("\n") if result.stderr else []

            # Extract detailed error messages
            detailed_error = ""
            if result.returncode != 0 and result.stdout:
                # First try to find Ansible fail task messages (e.g., "msg": "...")
                fail_match = re.search(
                    r'fatal:.*?FAILED!.*?"msg":\s*"(.+?)"', result.stdout, re.DOTALL
                )
                if fail_match:
                    # Extract the message and unescape it
                    detailed_error = fail_match.group(1).strip()
                    # Unescape newlines
                    detailed_error = detailed_error.replace("\\n", "\n")
                else:
                    # Fall back to [ERROR] pattern
                    error_match = re.search(
                        r"\[ERROR\]:\s*Task failed:\s*(.+?)(?=\nOrigin:|$)",
                        result.stdout,
                        re.DOTALL,
                    )
                    if error_match:
                        detailed_error = error_match.group(1).strip()
                        action_match = re.search(
                            r"Action failed:\s*(.+)", detailed_error, re.DOTALL
                        )
                        if action_match:
                            detailed_error = action_match.group(1).strip()

            error_message = (
                detailed_error
                if detailed_error
                else (result.stderr if result.returncode != 0 else "")
            )

            # Update job status
            completed_time = datetime.now().strftime("%-I:%M:%S %p")

            if result.returncode == 0:
                jobs[job_id]["status"] = "completed"
                jobs[job_id]["progress"] = 100
                jobs[job_id][
                    "message"
                ] = f"{description} completed and refreshed at {completed_time}"
                jobs[job_id]["completed_at"] = datetime.now().isoformat()
            else:
                jobs[job_id]["status"] = "failed"
                jobs[job_id]["message"] = f"{description} failed: {error_message}"
                jobs[job_id]["error"] = error_message
                jobs[job_id]["completed_at"] = datetime.now().isoformat()

            jobs[job_id]["logs"] = stdout_lines + stderr_lines

        finally:
            # Clean up temporary playbook file
            try:
                os.unlink(temp_playbook)
            except OSError:
                pass

    except Exception as e:
        import traceback

        error_msg = str(e)
        print(f"❌ Error running task: {error_msg}")
        print(traceback.format_exc())
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["message"] = f"{description} failed: {error_msg}"
        jobs[job_id]["error"] = error_msg
        jobs[job_id]["completed_at"] = datetime.now().isoformat()


@router.post("/api/ansible/run-task")
async def run_ansible_task(request: dict, background_tasks: BackgroundTasks):
    """Run a specific ansible task or playbook"""
    try:
        task_file = request.get("task_file")
        playbook_file = request.get("playbook_file")
        description = request.get("description", "Running ansible task")
        kube_context = request.get("kube_context")  # Optional cluster context
        extra_vars = request.get("extra_vars", {})  # Optional extra variables
        cluster_type = request.get("cluster_type", "mce")  # mce or minikube

        if not task_file and not playbook_file:
            raise HTTPException(
                status_code=400, detail="Either task_file or playbook_file is required"
            )

        # Create a job entry for tracking
        job_id = str(uuid.uuid4())
        jobs[job_id] = {
            "id": job_id,
            "status": "running",
            "progress": 0,
            "message": f"Starting {description}...",
            "description": description,
            "task_file": task_file or playbook_file,
            "yaml_file": task_file or playbook_file,
            "created_at": datetime.now().isoformat(),
            "started_at": datetime.now().isoformat(),
            "logs": [],
        }

        # Run task in background (use asyncio.to_thread to avoid blocking event loop)
        asyncio.create_task(asyncio.to_thread(
            _resolve("run_ansible_task_background"),
            job_id,
            task_file,
            playbook_file,
            description,
            kube_context,
            extra_vars,
            cluster_type,
        ))

        return {
            "success": True,
            "job_id": job_id,
            "message": f"{description} started",
            "status": "running",
        }
    except Exception as e:
        import traceback

        error_msg = f"Error starting task: {str(e)}"
        print(error_msg)
        print(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/api/ansible/run-role")
async def run_ansible_role(request: dict):
    """Run a specific ansible role"""
    try:
        import tempfile
        import yaml

        role_name = request.get("role_name")
        description = request.get("description", "Running ansible role")
        extra_vars = request.get("extra_vars", {})

        if not role_name:
            raise HTTPException(status_code=400, detail="role_name is required")

        # Check if role exists
        # Use AUTOMATION_PATH environment variable if set, otherwise calculate from file path
        project_root = os.environ.get("AUTOMATION_PATH") or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        role_path = os.path.join(project_root, "roles", role_name)
        if not os.path.exists(role_path):
            raise HTTPException(status_code=404, detail=f"Role not found: {role_name}")

        # Create a temporary playbook to run the role
        # Add OCP login and variable setup tasks first for MCE roles
        tasks = []
        mce_roles = ["configure-capa-environment"]
        if role_name in mce_roles:
            tasks.extend(
                [
                    {
                        "name": "Set OCP credentials",
                        "set_fact": {
                            "ocp_user": "{{ OCP_HUB_CLUSTER_USER }}",
                            "ocp_password": "{{ OCP_HUB_CLUSTER_PASSWORD }}",
                            "api_url": "{{ OCP_HUB_API_URL }}",
                        },
                    },
                    {
                        "name": "Login to OCP",
                        "include_tasks": f"{project_root}/tasks/login_ocp.yml",
                    },
                ]
            )

        # Set AUTOMATION_PATH as a fact to ensure it's available to all included tasks
        tasks.append(
            {
                "name": "Set AUTOMATION_PATH",
                "set_fact": {"AUTOMATION_PATH": project_root},
            }
        )

        # Add the main role task
        tasks.append(
            {
                "name": f"Configure the MCE CAPI/CAPA environment",
                "include_role": {"name": role_name},
                "vars": {
                    "ocm_client_id": "{{ OCM_CLIENT_ID }}",
                    "ocm_client_secret": "{{ OCM_CLIENT_SECRET }}",
                },
            }
        )

        playbook_content = {
            "name": f"Run {role_name} role",
            "hosts": "localhost",
            "connection": "local",
            "gather_facts": False,
            "vars": {
                "AUTOMATION_PATH": project_root,
                "playbook_dir": project_root,
            },
            "vars_files": [f"{project_root}/vars/vars.yml", f"{project_root}/vars/user_vars.yml"],
            "tasks": tasks,
        }

        # Write temporary playbook
        # Use AUTOMATION_PATH environment variable if set, otherwise calculate from file path
        project_root = os.environ.get("AUTOMATION_PATH") or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        # Write temp file to /tmp since project_root might be read-only
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False, dir="/tmp") as f:
            yaml.dump([playbook_content], f, default_flow_style=False)
            temp_playbook = f.name

        try:
            # Prepare ansible command
            cmd = [
                "ansible-playbook",
                temp_playbook,
                "-i",
                "localhost,",  # Inline inventory with localhost
                "-e",
                "skip_ansible_runner=true",
                "-e",
                f"AUTOMATION_PATH={project_root}",
                "-e",
                f"playbook_dir={project_root}",
                "-v",  # Verbose output
            ]

            # Add extra vars if provided (skip empty values so vars_files defaults are used)
            for key, value in extra_vars.items():
                if value != '':
                    cmd.extend(["-e", f"{key}={value}"])

            print(f"Running ansible role: {' '.join(cmd)}")

            # Set environment variables for Ansible
            env = os.environ.copy()
            env["ANSIBLE_ROLES_PATH"] = f"{project_root}/roles"
            env["ANSIBLE_PLAYBOOK_DIR"] = project_root

            # Run the command
            result = subprocess.run(
                cmd,
                cwd=project_root,
                env=env,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minutes timeout for roles
            )

            # Parse the output
            stdout_lines = result.stdout.split("\n") if result.stdout else []
            stderr_lines = result.stderr.split("\n") if result.stderr else []

            print(f"Ansible role completed with return code: {result.returncode}")
            print(f"STDOUT: {result.stdout}")
            if result.stderr:
                print(f"STDERR: {result.stderr}")

            return {
                "success": result.returncode == 0,
                "return_code": result.returncode,
                "output": result.stdout,
                "error": result.stderr,
                "message": (
                    "Role completed successfully" if result.returncode == 0 else "Role failed"
                ),
                "role_name": role_name,
                "description": description,
                "stdout_lines": stdout_lines,
                "stderr_lines": stderr_lines,
            }

        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_playbook)
            except OSError:
                pass

    except subprocess.TimeoutExpired as e:
        error_msg = f"Role {role_name} timed out after 10 minutes"
        print(error_msg)
        # Try to get partial output from timeout exception
        partial_output = getattr(e, "stdout", "") or ""
        partial_error = getattr(e, "stderr", "") or ""
        return {
            "success": False,
            "error": error_msg,
            "message": "Role timed out",
            "role_name": role_name,
            "description": description,
            "output": partial_output,
            "return_code": -1,
        }
    except Exception as e:
        error_msg = f"Error running role {role_name}: {str(e)}"
        print(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


def _run_playbook_in_thread(playbook: str, extra_vars: dict, job_id: str, description: str):
    """Run ansible playbook in a thread (called via asyncio.to_thread to avoid blocking event loop)"""
    try:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["progress"] = 10
        jobs[job_id]["message"] = f"Starting playbook: {playbook}"

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        playbook_path = os.path.join(project_root, playbook)

        # For deletion and provisioning playbooks, start a sidecar file tailer for real-time
        # agent monitoring. Ansible shell wait loops buffer stdout, but they also write to a
        # sidecar log file via tee. This thread tails that file and feeds lines to the agent.
        is_deletion = "delete" in playbook.lower()
        is_provisioning = "create" in playbook.lower() or "provision" in playbook.lower()
        use_sidecar = is_deletion or is_provisioning
        sidecar_stop = threading.Event()
        sidecar_thread = None
        agent_lock = threading.Lock()  # Guard process_line from concurrent sidecar + stdout access

        if use_sidecar:
            cluster_name = extra_vars.get("cluster_name", extra_vars.get("clusterName", extra_vars.get("name_prefix", "")))
            if cluster_name and not cluster_name.endswith("-rosa-hcp") and is_provisioning:
                sidecar_cluster = f"{cluster_name}-rosa-hcp"
            else:
                sidecar_cluster = cluster_name
            sidecar_logfile = f"/tmp/{'deletion' if is_deletion else 'provision'}-agent-{sidecar_cluster}.log"

            def _tail_sidecar():
                """Tail the sidecar log file and feed lines to the AI agent in real-time."""
                import time as _sidecar_time
                last_pos = 0
                while not sidecar_stop.is_set():
                    try:
                        if os.path.exists(sidecar_logfile):
                            with open(sidecar_logfile, 'r') as f:
                                f.seek(last_pos)
                                new_lines = f.readlines()
                                if new_lines:
                                    for line in new_lines:
                                        line = line.strip()
                                        if line:
                                            # Feed to agent (lock prevents race with main stdout loop)
                                            agent_session = ai_agent_sessions.get(job_id)
                                            if agent_session and agent_session.get("monitor"):
                                                try:
                                                    with agent_lock:
                                                        agent_session["monitor"].process_line(line)
                                                except Exception:
                                                    pass
                                            # Also add to job logs so UI sees it in real-time
                                            jobs[job_id]["logs"].append(f"[AGENT-SIDECAR] {line}")
                                            print(f"[SIDECAR] {line}")
                                last_pos = f.tell()
                    except Exception:
                        pass
                    _sidecar_time.sleep(2)  # Poll every 2 seconds

            sidecar_thread = threading.Thread(target=_tail_sidecar, daemon=True)
            sidecar_thread.start()

        # If a cluster_context is provided (e.g. Minikube), create an isolated
        # kubeconfig copy for this job so we don't stomp on the global context.
        # This prevents context bleeding between concurrent jobs.
        cluster_context = extra_vars.get("cluster_context", "")
        job_kubeconfig = None

        if cluster_context:
            import shutil
            import tempfile
            try:
                src_kubeconfig = os.environ.get("KUBECONFIG", os.path.expanduser("~/.kube/config"))
                job_kubeconfig = os.path.join(tempfile.gettempdir(), f"kubeconfig-{job_id}")
                shutil.copy2(src_kubeconfig, job_kubeconfig)

                # Switch context in the isolated copy only
                ctx_result = subprocess.run(
                    ["kubectl", "config", "use-context", cluster_context],
                    capture_output=True, text=True, timeout=10,
                    env={**os.environ, "KUBECONFIG": job_kubeconfig},
                )
                if ctx_result.returncode == 0:
                    jobs[job_id]["logs"].append(f"Using isolated kubeconfig for context: {cluster_context}")
                    print(f"[Playbook] Isolated kubeconfig for context: {cluster_context}")
                    # Tell the playbook to skip OCP login since we're using kubectl context
                    extra_vars["skip_ocp_login"] = "true"
                else:
                    jobs[job_id]["status"] = "failed"
                    jobs[job_id]["message"] = f"Failed to switch kubectl context to '{cluster_context}'"
                    jobs[job_id]["logs"].append(f"ERROR: {ctx_result.stderr}")
                    os.remove(job_kubeconfig)
                    return
            except Exception as e:
                jobs[job_id]["status"] = "failed"
                jobs[job_id]["message"] = f"Failed to set up isolated kubeconfig: {str(e)}"
                if job_kubeconfig and os.path.exists(job_kubeconfig):
                    os.remove(job_kubeconfig)
                return

        def camel_to_snake(name):
            special_cases = {'openShift': 'openshift', 'OpenShift': 'openshift'}
            for camel, snake in special_cases.items():
                if camel in name:
                    name = name.replace(camel, snake)
            s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
            return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

        snake_vars = {camel_to_snake(k): v for k, v in extra_vars.items()}

        env = os.environ.copy()
        env["KUBECONFIG"] = job_kubeconfig if job_kubeconfig else os.environ.get("KUBECONFIG", os.path.expanduser("~/.kube/config"))
        env["PYTHONUNBUFFERED"] = "1"

        cmd, env = build_playbook_command(
            playbook_path, extra_vars=snake_vars, verbosity=1, env=env,
        )

        print(f"[Playbook] Running: {' '.join(cmd)}")
        jobs[job_id]["progress"] = 30
        jobs[job_id]["message"] = "Executing ansible playbook"

        process = subprocess.Popen(
            cmd, cwd=project_root,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, env=env,
        )

        import time as _time
        line_count = 0
        for line in process.stdout:
            line_stripped = line.rstrip()
            jobs[job_id]["logs"].append(line_stripped)

            # AI Agent: Process each line for real-time issue detection
            agent_session = ai_agent_sessions.get(job_id)
            if agent_session and agent_session.get("monitor"):
                try:
                    with agent_lock:
                        agent_session["monitor"].process_line(line_stripped)
                except Exception:
                    pass

            line_count += 1
            if line_count % 10 == 0:
                jobs[job_id]["progress"] = min(30 + (line_count // 10), 95)

            print(line_stripped)

            # Yield the GIL periodically so the event loop can process requests
            if line_count % 5 == 0:
                _time.sleep(0.001)

        returncode = process.wait(timeout=5400)
        print(f"[Playbook] Completed with return code: {returncode}")

        if returncode == 0:
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["progress"] = 100
            jobs[job_id]["return_code"] = 0
            jobs[job_id]["message"] = "Playbook completed successfully"
        else:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["progress"] = 100
            jobs[job_id]["return_code"] = returncode
            jobs[job_id]["message"] = f"Playbook failed with return code {returncode}"

        jobs[job_id]["agent_stats"] = get_agent_stats(job_id)
        jobs[job_id]["completed_at"] = datetime.now().isoformat()

    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["return_code"] = 1
        jobs[job_id]["message"] = "Playbook timed out after 90 minutes"
        jobs[job_id]["logs"].append("ERROR: Process timed out after 90 minutes")
        jobs[job_id]["agent_stats"] = get_agent_stats(job_id)
        jobs[job_id]["completed_at"] = datetime.now().isoformat()
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["return_code"] = 1
        jobs[job_id]["message"] = f"Error: {str(e)}"
        jobs[job_id]["logs"].append(f"ERROR: {str(e)}")
        jobs[job_id]["agent_stats"] = get_agent_stats(job_id)
        jobs[job_id]["completed_at"] = datetime.now().isoformat()
    finally:
        # Stop the sidecar tailer thread
        if sidecar_stop is not None:
            sidecar_stop.set()
        if sidecar_thread is not None:
            sidecar_thread.join(timeout=5)
        # Clean up isolated kubeconfig
        if job_kubeconfig and os.path.exists(job_kubeconfig):
            try:
                os.remove(job_kubeconfig)
            except Exception:
                pass


async def run_playbook_background(playbook: str, extra_vars: dict, job_id: str, description: str):
    """Wrapper that runs the playbook in a thread so the event loop stays free."""
    await asyncio.to_thread(_resolve("_run_playbook_in_thread"), playbook, extra_vars, job_id, description)


@router.post("/api/ansible/run-playbook")
async def run_ansible_playbook_endpoint(request: dict, background_tasks: BackgroundTasks):
    """Run an existing ansible playbook asynchronously"""
    try:
        playbook = request.get("playbook")
        description = request.get("description", "Running ansible playbook")
        extra_vars = request.get("extra_vars", {})

        if not playbook:
            raise HTTPException(status_code=400, detail="playbook is required")

        # Ensure the playbook file exists
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        playbook_path = os.path.join(project_root, playbook)
        if not os.path.exists(playbook_path):
            raise HTTPException(status_code=404, detail=f"Playbook not found: {playbook}")

        # Generate job ID
        job_id = str(uuid.uuid4())

        # Create job
        jobs[job_id] = {
            "id": job_id,
            "status": "pending",
            "progress": 0,
            "message": f"Queued: {description}",
            "logs": [],
            "created_at": datetime.now(),
            "playbook": playbook,
            "description": description,
        }

        # Initialize AI agents for playbook monitoring
        init_ai_agents(job_id)

        # Run playbook as async task (not background_tasks which blocks the event loop)
        asyncio.create_task(
            _resolve("run_playbook_background")(playbook, extra_vars, job_id, description)
        )

        return {
            "success": True,
            "job_id": job_id,
            "status": "pending",
            "message": f"Playbook {playbook} queued for execution",
            "playbook": playbook,
            "description": description,
        }

    except Exception as e:
        error_msg = f"Error queuing playbook {playbook}: {str(e)}"
        print(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)
