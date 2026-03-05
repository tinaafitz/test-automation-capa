# Backend Automation Architecture

A comprehensive technical guide to the asynchronous automation patterns, job execution, and background task management in the CAPA Automation UI backend.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Ansible Job Execution](#ansible-job-execution)
- [Job Management & Polling](#job-management--polling)
- [Real-Time Communication](#real-time-communication)
- [Notification Services](#notification-services)
- [Caching Strategies](#caching-strategies)
- [Frontend Integration](#frontend-integration)
- [Development Guide](#development-guide)

## Overview

The CAPA Automation UI backend uses FastAPI to provide a REST API that orchestrates long-running Ansible playbooks, manages asynchronous jobs, and provides real-time status updates to the frontend.

### Key Components

- **FastAPI Backend** (`ui/backend/app.py`) - Main API server
- **Ansible Integration** - Subprocess management for playbooks
- **Job Queue** - In-memory job tracking (Redis-ready)
- **WebSocket Server** - Real-time job updates
- **Notification Services** - Email and Slack integrations
- **Caching Layer** - Performance optimization for expensive operations

### Technology Stack

- **FastAPI** - Async Python web framework
- **Pydantic** - Data validation and serialization
- **WebSockets** - Real-time bidirectional communication
- **Subprocess** - Ansible playbook execution
- **SQLite** - Persistent storage for test results
- **SMTP/Slack** - Notification delivery

## Architecture

### High-Level System Design

```
┌─────────────────────────────────────────────────────────────┐
│                    React Frontend                            │
│                                                              │
│  User Action (e.g., "Provision Cluster")                   │
│         │                                                    │
└─────────┼────────────────────────────────────────────────────┘
          │
          │ POST /api/ansible/run-playbook
          │ { playbook, extra_vars, description }
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│                  FastAPI Backend                             │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  1. Create Job Entry                               │    │
│  │     job_id = uuid.uuid4()                          │    │
│  │     jobs[job_id] = {                               │    │
│  │       "status": "pending",                         │    │
│  │       "logs": [],                                  │    │
│  │       "progress": 0                                │    │
│  │     }                                              │    │
│  └────────────────┬───────────────────────────────────┘    │
│                   │                                          │
│  ┌────────────────▼───────────────────────────────────┐    │
│  │  2. Launch Background Task                        │    │
│  │     background_tasks.add_task(                     │    │
│  │       run_ansible_playbook,                        │    │
│  │       playbook, config, job_id                     │    │
│  │     )                                              │    │
│  └────────────────┬───────────────────────────────────┘    │
│                   │                                          │
│                   │ Return job_id immediately                │
│                   │ (API response: HTTP 200)                │
└───────────────────┼──────────────────────────────────────────┘
                    │
                    │
  ┌─────────────────▼────────────────────────────┐
  │  Background Worker Thread                    │
  │                                               │
  │  run_ansible_playbook(playbook, config, job) │
  │  ├── jobs[job]["status"] = "running"         │
  │  ├── subprocess.Popen(["ansible-playbook"]) │
  │  ├── Stream stdout line-by-line              │
  │  │   └─> jobs[job]["logs"].append(line)     │
  │  ├── Update progress (30% → 95%)             │
  │  └── Set final status (completed/failed)     │
  │                                               │
  └───────────────┬─────────────────────────────┘
                  │
                  │ Ansible subprocess running
                  │ Logs streaming to job queue
                  │
    ┌─────────────▼──────────────┐
    │  Frontend Polling Loop     │
    │                            │
    │  setInterval(() => {       │
    │    fetch(`/api/jobs/${id}`)│
    │    .then(data => {         │
    │      setStatus(data)       │
    │      setLogs(data.logs)    │
    │    })                      │
    │  }, 1000)  // Poll/1s      │
    │                            │
    └────────────────────────────┘
```

### Request Flow

**1. Initial Request**
```javascript
// Frontend initiates job
POST /api/ansible/run-playbook
{
  "playbook": "playbooks/configure_mce_environment.yml",
  "description": "Configure MCE CAPI/CAPA",
  "extra_vars": {}
}

// Backend responds immediately
HTTP 200 OK
{
  "success": true,
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
}
```

**2. Background Execution**
```python
# FastAPI background task runs Ansible
def run_ansible_playbook(playbook, config, job_id):
    jobs[job_id]["status"] = "running"

    # Execute Ansible with real-time streaming
    process = subprocess.Popen(
        ["ansible-playbook", playbook, "-e", "..."],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1  # Line buffered
    )

    # Stream output line-by-line
    for line in process.stdout:
        jobs[job_id]["logs"].append(line.rstrip())

    returncode = process.wait(timeout=3600)
    jobs[job_id]["status"] = "completed" if returncode == 0 else "failed"
```

**3. Status Polling**
```javascript
// Frontend polls for updates
GET /api/jobs/3fa85f64-5717-4562-b3fc-2c963f66afa6

HTTP 200 OK
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "running",
  "progress": 65,
  "logs": ["TASK [Verify MCE installation]", "ok: [localhost]", ...],
  "created_at": "2026-03-05T10:30:00",
  "message": "Executing ansible playbook"
}
```

## Ansible Job Execution

### Core Execution Function

**Location**: `ui/backend/app.py:289`

```python
def run_ansible_playbook(playbook: str, config: dict, job_id: str):
    """Run ansible playbook asynchronously with real-time log streaming"""
    try:
        # Update job status
        jobs[job_id]["status"] = "running"
        jobs[job_id]["progress"] = 10
        jobs[job_id]["message"] = f"Starting {playbook} execution"

        # Build Ansible command with extra vars
        cmd = [
            "ansible-playbook",
            playbook,
            "-e", f"cluster_name={config['name']}",
            "-e", f"openshift_version={config['version']}",
            "-e", "skip_ansible_runner=true"
        ]

        # Execute with line-buffered output
        process = subprocess.Popen(
            cmd,
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Merge stderr into stdout
            text=True,
            bufsize=1  # Line buffered for real-time streaming
        )

        # Stream output in real-time
        line_count = 0
        for line in process.stdout:
            # Append to job logs immediately (visible in UI)
            jobs[job_id]["logs"].append(line.rstrip())

            # Update progress every 10 lines (30% → 95%)
            line_count += 1
            if line_count % 10 == 0:
                jobs[job_id]["progress"] = min(30 + (line_count // 10), 95)

            # Print to console for debugging
            print(line, end='')
            sys.stdout.flush()

        # Wait for completion (60 min timeout)
        returncode = process.wait(timeout=3600)

        # Set final status
        if returncode == 0:
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["progress"] = 100
        else:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["message"] = f"Failed with exit code {returncode}"

        jobs[job_id]["completed_at"] = datetime.now()

    except subprocess.TimeoutExpired:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["message"] = "Job timed out after 60 minutes"
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["message"] = f"Error: {str(e)}"
```

### Key Features

**1. Real-Time Log Streaming**
- Line-buffered subprocess output (`bufsize=1`)
- Immediate log append to job queue
- Frontend sees logs as they're generated
- No need to wait for job completion

**2. Progress Tracking**
- Initial: 10% (job created)
- Pre-execution: 30% (ansible starting)
- During execution: 30-95% (based on line count)
- Completion: 100% (success) or error state

**3. Timeout Protection**
- 60-minute hard timeout for all jobs
- Prevents hung processes
- Matches Jenkins deletion timeout

**4. Error Handling**
- Captures subprocess exceptions
- Timeout handling
- Exit code checking
- Error messages in job logs

## Job Management & Polling

### Job Storage

**In-Memory Queue** (Production: Use Redis)

```python
# Job structure
jobs: Dict[str, dict] = {}

jobs[job_id] = {
    "id": job_id,
    "description": "Configure MCE CAPI/CAPA",
    "status": "pending | running | completed | failed",
    "progress": 0-100,
    "logs": ["line1", "line2", ...],
    "created_at": datetime,
    "completed_at": datetime | None,
    "message": "Current status message",
    "playbook": "playbooks/configure_mce_environment.yml",
    "extra_vars": {...}
}
```

### API Endpoints

**1. List All Jobs**

```python
@app.get("/api/jobs")
async def list_jobs():
    """Get all jobs (limited to last 100)"""
    job_list = list(jobs.values())
    job_list.sort(key=lambda x: x["created_at"], reverse=True)
    return {
        "success": True,
        "jobs": job_list[:100],
        "count": len(job_list)
    }
```

**2. Get Job Status**

```python
@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get status and metadata for a specific job"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]
```

**3. Get Job Logs**

```python
@app.get("/api/jobs/{job_id}/logs")
async def get_job_logs(job_id: str):
    """Get logs for a specific job"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job_id,
        "logs": jobs[job_id]["logs"],
        "status": jobs[job_id]["status"]
    }
```

**4. Cancel Job**

```python
@app.delete("/api/jobs/{job_id}")
async def cancel_job(job_id: str):
    """Cancel a running job"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    if jobs[job_id]["status"] == "running":
        # Kill the subprocess (implementation needed)
        jobs[job_id]["status"] = "cancelled"
        jobs[job_id]["message"] = "Job cancelled by user"

    return {"success": True, "job_id": job_id}
```

### Frontend Polling Pattern

```javascript
// Continuously poll for job updates
const pollJobStatus = async (jobId) => {
  const maxAttempts = 1800; // 30 minutes max
  let attempts = 0;

  while (attempts < maxAttempts) {
    attempts++;

    // Fetch current status
    const response = await fetch(`/api/jobs/${jobId}`);
    const jobData = await response.json();

    // Fetch logs
    const logsResponse = await fetch(`/api/jobs/${jobId}/logs`);
    const logsData = await logsResponse.json();

    // Update UI every 5 seconds
    if (attempts % 5 === 0) {
      setProvisionResults({
        success: jobData.status !== 'failed',
        output: logsData.logs.join('\n')
      });
    }

    // Check completion
    if (jobData.status === 'completed') {
      setProvisionResults({ success: true, output: logsData.logs.join('\n') });
      return;
    } else if (jobData.status === 'failed') {
      setProvisionResults({ success: false, output: logsData.logs.join('\n') });
      return;
    }

    // Poll every 1 second
    await new Promise(resolve => setTimeout(resolve, 1000));
  }

  throw new Error('Polling timeout after 30 minutes');
};
```

## Real-Time Communication

### WebSocket Support

**Location**: `ui/backend/app.py:921`

```python
@app.websocket("/ws/jobs/{job_id}")
async def websocket_job_updates(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for real-time job updates"""
    await websocket.accept()

    try:
        while True:
            if job_id not in jobs:
                await websocket.send_json({"error": "Job not found"})
                break

            job = jobs[job_id]

            # Send current status
            await websocket.send_json({
                "job_id": job_id,
                "status": job["status"],
                "progress": job["progress"],
                "logs": job["logs"][-10:],  # Last 10 lines
                "message": job.get("message", "")
            })

            # Stop if job completed
            if job["status"] in ["completed", "failed", "cancelled"]:
                break

            # Send updates every 500ms
            await asyncio.sleep(0.5)

    except Exception as e:
        await websocket.send_json({"error": str(e)})
    finally:
        await websocket.close()
```

**Frontend WebSocket Client**

```javascript
// Connect to WebSocket for real-time updates
const ws = new WebSocket(`ws://localhost:8000/ws/jobs/${jobId}`);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  // Update UI in real-time
  setJobStatus(data.status);
  setJobProgress(data.progress);
  setJobLogs(data.logs);
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
  // Fall back to HTTP polling
};
```

## Notification Services

### Slack Notifications

**Service**: `ui/backend/slack_notification_service.py`

```python
class SlackNotificationService:
    def __init__(self):
        self.webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        self.enabled = os.getenv("SLACK_ENABLED", "false").lower() == "true"

    async def send_provision_notification(
        self,
        cluster_name: str,
        status: str,
        details: dict
    ):
        """Send cluster provisioning notification to Slack"""
        if not self.enabled:
            return

        # Build message
        message = {
            "text": f"🚀 ROSA HCP Cluster: {cluster_name}",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{'✅' if status == 'success' else '❌'} {cluster_name}"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Status:* {status}"},
                        {"type": "mrkdwn", "text": f"*Region:* {details.get('region')}"},
                        {"type": "mrkdwn", "text": f"*Version:* {details.get('version')}"}
                    ]
                }
            ]
        }

        # Send to Slack
        async with httpx.AsyncClient() as client:
            await client.post(self.webhook_url, json=message)
```

### Email Notifications

**Service**: `ui/backend/email_notification_service.py`

```python
class EmailNotificationService:
    def __init__(self):
        self.smtp_server = os.getenv("SMTP_SERVER")
        self.smtp_port = int(os.getenv("SMTP_PORT", 587))
        self.from_email = os.getenv("FROM_EMAIL")
        self.enabled = os.getenv("EMAIL_ENABLED", "false").lower() == "true"

    async def send_provision_notification(
        self,
        cluster_name: str,
        status: str,
        details: dict
    ):
        """Send cluster provisioning email notification"""
        if not self.enabled:
            return

        subject = f"ROSA HCP Cluster {status.upper()}: {cluster_name}"

        body = f"""
        Cluster: {cluster_name}
        Status: {status}
        Region: {details.get('region')}
        Version: {details.get('version')}

        View details: {details.get('dashboard_url')}
        """

        # Send email via SMTP
        message = MIMEText(body)
        message["Subject"] = subject
        message["From"] = self.from_email
        message["To"] = ", ".join(self.to_emails)

        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
            server.starttls()
            if self.smtp_username:
                server.login(self.smtp_username, self.smtp_password)
            server.send_message(message)
```

## Caching Strategies

### Performance Optimization

**Problem**: Expensive subprocess calls (OCP status, ROSA CLI, kubectl)
**Solution**: TTL-based caching

```python
# Cache structure
cache = {
    "data": None,          # Cached result
    "timestamp": 0,        # Last update time
    "ttl": 30             # Time-to-live (seconds)
}

# Cache implementation
def get_cached_or_fetch(cache_key, fetch_fn, ttl=30):
    """Get from cache or fetch if expired"""
    cache = caches[cache_key]
    now = time.time()

    # Check if cache is valid
    if cache["data"] is not None and (now - cache["timestamp"]) < cache["ttl"]:
        return cache["data"]

    # Cache miss or expired - fetch new data
    cache["data"] = fetch_fn()
    cache["timestamp"] = now
    return cache["data"]
```

### Cached Operations

**1. Minikube Cluster List** (TTL: 30s)

```python
minikube_clusters_cache = {"data": None, "timestamp": 0, "ttl": 30}

@app.get("/api/minikube/list-clusters")
async def list_minikube_clusters():
    now = time.time()

    # Check cache
    if (minikube_clusters_cache["data"] and
        now - minikube_clusters_cache["timestamp"] < 30):
        return minikube_clusters_cache["data"]

    # Fetch new data
    result = subprocess.run(["minikube", "profile", "list", "-o", "json"],
                          capture_output=True, text=True)
    data = json.loads(result.stdout)

    # Update cache
    minikube_clusters_cache["data"] = data
    minikube_clusters_cache["timestamp"] = now

    return data
```

**2. OCP Connection Status** (TTL: 60s)

```python
ocp_status_cache = {"data": None, "timestamp": 0, "ttl": 60}

@app.get("/api/ocp/connection-status")
async def get_ocp_connection_status():
    # Longer TTL since connection tests are slow
    return get_cached_or_fetch(
        "ocp_status",
        lambda: check_ocp_connection(),
        ttl=60
    )
```

**3. ROSA Status** (TTL: 30s)

```python
rosa_status_cache = {"data": None, "timestamp": 0, "ttl": 30}

@app.get("/api/rosa/status")
async def get_rosa_status():
    return get_cached_or_fetch(
        "rosa_status",
        lambda: check_rosa_cli(),
        ttl=30
    )
```

## Frontend Integration

### Complete Workflow Example

**Scenario**: User provisions a ROSA HCP cluster

**1. User Submits Form**

```javascript
// Frontend: RosaProvisionModal.jsx
const handleSubmit = async (config) => {
  const response = await fetch('/api/ansible/run-playbook', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      playbook: 'playbooks/create_rosa_hcp_cluster.yml',
      description: `Provision ROSA HCP: ${config.clusterName}`,
      extra_vars: config
    })
  });

  const result = await response.json();

  if (result.success) {
    // Start polling
    pollJobStatus(result.job_id);
  }
};
```

**2. Backend Creates Job**

```python
@app.post("/api/ansible/run-playbook")
async def run_ansible_playbook_endpoint(request: dict, background_tasks: BackgroundTasks):
    # Create job
    job_id = str(uuid.uuid4())

    jobs[job_id] = {
        "id": job_id,
        "description": request["description"],
        "status": "pending",
        "progress": 0,
        "logs": [],
        "created_at": datetime.now(),
        "playbook": request["playbook"]
    }

    # Launch background task
    background_tasks.add_task(
        run_ansible_playbook,
        request["playbook"],
        request["extra_vars"],
        job_id
    )

    # Return immediately
    return {"success": True, "job_id": job_id}
```

**3. Frontend Polls for Updates**

```javascript
const pollJobStatus = async (jobId) => {
  while (true) {
    // Get status
    const statusRes = await fetch(`/api/jobs/${jobId}`);
    const statusData = await statusRes.json();

    // Get logs
    const logsRes = await fetch(`/api/jobs/${jobId}/logs`);
    const logsData = await logsRes.json();

    // Update UI
    setProvisionResults({
      status: statusData.status,
      progress: statusData.progress,
      output: logsData.logs.join('\n')
    });

    // Check completion
    if (statusData.status === 'completed') {
      showSuccessNotification();
      break;
    } else if (statusData.status === 'failed') {
      showErrorNotification();
      break;
    }

    // Wait 1 second
    await new Promise(r => setTimeout(r, 1000));
  }
};
```

**4. Background Worker Executes**

```python
# Background task running Ansible
def run_ansible_playbook(playbook, config, job_id):
    jobs[job_id]["status"] = "running"

    # Run ansible-playbook with real-time streaming
    process = subprocess.Popen([...])

    for line in process.stdout:
        jobs[job_id]["logs"].append(line)
        # Frontend sees this immediately on next poll

    jobs[job_id]["status"] = "completed"
```

## Development Guide

### Adding a New Ansible Endpoint

**1. Create Pydantic Model**

```python
class MyTaskConfig(BaseModel):
    param1: str
    param2: int = 10
    optional_param: Optional[str] = None
```

**2. Create API Endpoint**

```python
@app.post("/api/ansible/run-my-task")
async def run_my_task(config: MyTaskConfig, background_tasks: BackgroundTasks):
    # Create job
    job_id = str(uuid.uuid4())

    jobs[job_id] = {
        "id": job_id,
        "description": "My Custom Task",
        "status": "pending",
        "logs": [],
        "created_at": datetime.now()
    }

    # Launch background task
    background_tasks.add_task(
        run_ansible_playbook,
        "playbooks/my_custom_task.yml",
        config.dict(),
        job_id
    )

    return {"success": True, "job_id": job_id}
```

**3. Frontend Integration**

```javascript
// Call endpoint
const response = await fetch('/api/ansible/run-my-task', {
  method: 'POST',
  body: JSON.stringify({ param1: "value", param2: 20 })
});

const { job_id } = await response.json();

// Poll for results
pollJobStatus(job_id);
```

### Adding Caching

```python
# Create cache
my_cache = {"data": None, "timestamp": 0, "ttl": 60}

@app.get("/api/my-expensive-operation")
async def my_operation():
    now = time.time()

    # Check cache
    if my_cache["data"] and now - my_cache["timestamp"] < my_cache["ttl"]:
        return my_cache["data"]

    # Expensive operation
    result = expensive_subprocess_call()

    # Update cache
    my_cache["data"] = result
    my_cache["timestamp"] = now

    return result
```

### Testing

**Unit Test Example**

```python
from fastapi.testclient import TestClient

def test_run_playbook_endpoint():
    client = TestClient(app)

    response = client.post("/api/ansible/run-playbook", json={
        "playbook": "test.yml",
        "description": "Test",
        "extra_vars": {}
    })

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "job_id" in data
```

**Integration Test**

```python
async def test_full_workflow():
    # Start job
    response = await client.post("/api/ansible/run-playbook", ...)
    job_id = response.json()["job_id"]

    # Wait for completion
    for _ in range(60):
        status = await client.get(f"/api/jobs/{job_id}")
        if status.json()["status"] in ["completed", "failed"]:
            break
        await asyncio.sleep(1)

    # Verify result
    assert status.json()["status"] == "completed"
```

---

**Document Version:** 1.0
**Last Updated:** 2026-03-05
**Maintained By:** CAPA Automation Team
