# Debug Findings Report Template

Use this format when reporting issues found by `debug-ui-error`.

## Header

```
## Issue: [Brief title]
**Severity**: [Critical | High | Medium | Low]
**Status**: [Running | Stopped | Failed | Degraded]
**Affected Component**: [Backend | Frontend | Container | Network]
```

## Problem Statement

Clear description of what's broken and how it manifests:
- What the user observes
- When it happens
- What endpoints/features are affected

Example:
```
API returns 500 errors on all /api/clusters endpoints.
Started after container restart. Other endpoints respond normally.
```

## Evidence

Raw diagnostic data supporting the finding:

### Container Status
```
CONTAINER ID  IMAGE                             STATUS      PORTS
a1b2c3d4      localhost/test-automation-capa    Up 2 min    3000->3000, 8000->8000
```

### Key Logs
```
[timestamp] ERROR: Connection refused to Redis localhost:6379
[timestamp] ERROR: Failed to initialize orchestrator: Redis unavailable
[timestamp] WARN: Falling back to local mode (expected)
```

### Health Checks
```
API Health: ✅ http://localhost:8000/api/health → 200 OK
Frontend: ✅ http://localhost:3000 → 200 OK
Redis: ❌ redis-cli -p 6379 ping → Connection refused
```

### Resource Usage
```
CONTAINER ID  CPU %   MEM USAGE / LIMIT
a1b2c3d4      0.5%    245MiB / 2GiB
```

## Root Cause

Analysis of why the issue occurred:

```
Redis service not running inside container. The app is designed to 
gracefully degrade to local mode, but this indicates the Docker 
Compose setup (if used) didn't start Redis, or the container image 
is missing Redis installation.
```

## Impact

How this affects the user:

- **Scope**: Affects X feature/endpoint
- **Severity**: Users cannot do Y; workaround is Z
- **Data**: No data loss; state preserved in volumes
- **Performance**: No impact on running operations

Example:
```
Impact: Low. The app correctly falls back to local orchestrator mode.
All features work, just without Redis caching/distributed state.
This is expected for local development. Production should have Redis.
```

## Solution

Step-by-step fix:

### Option 1: Quick Fix (Recommended)
```bash
# Explain what this does
podman exec test-automation-capa redis-server --daemonize yes
# Or restart container with Redis
/stop-ui
/run-ui
```

### Option 2: Detailed Fix
```bash
# Step 1: Identify the issue
podman logs test-automation-capa | grep -i redis

# Step 2: Fix it
podman exec -it test-automation-capa /bin/bash
# Inside container:
apt-get update && apt-get install -y redis-server
redis-server --daemonize yes

# Step 3: Verify
curl http://localhost:8000/api/health
```

## Verification

How to confirm the fix worked:

```bash
# Check that issue is resolved
curl http://localhost:8000/api/health | jq .

# Run a test
/run-ui-tests -k "test_name"

# Or manually verify
# - Open http://localhost:3000
# - Click on feature X
# - Confirm it works
```

## Prevention

How to avoid this in the future:

- Always use `/run-ui` to start (ensures proper setup)
- Check `/debug-ui-error` if anything seems off
- Monitor logs with `podman logs -f test-automation-capa`
- Pin dependency versions in requirements.txt

## References

Links to relevant files/docs:

- Dockerfile: `/Users/tinafitzgerald/acm_dev/ai_dev/test-automation-capa/Dockerfile`
- Backend logs: `podman logs test-automation-capa`
- Health endpoint: `http://localhost:8000/api/health`
- Architecture docs: `ARCHITECTURAL_REVIEW.md`

---

## Example Complete Report

```
## Issue: API returns 503 Service Unavailable

**Severity**: High
**Status**: Failed
**Affected Component**: Backend

### Problem Statement
All API endpoints return 503 Service Unavailable ({"detail":"Service Unavailable"}).
Frontend loads but cannot fetch data. Started after restarting container.

### Evidence

**Container Status:**
```
CONTAINER ID  IMAGE                             STATUS       PORTS
a1b2c3d4      localhost/test-automation-capa    Up 30 sec    3000->3000, 8000->8000
```

**Key Logs:**
```
ERROR: FastAPI failed to import app.py
ModuleNotFoundError: No module named 'minikube_ops'
Traceback: File "/app/ui/backend/app.py", line 42, in <module>
  import minikube_ops
```

**Health Checks:**
```
API Health: ❌ http://localhost:8000/api/health → 503 Service Unavailable
Frontend: ✅ http://localhost:3000 → 200 OK (blank page, can't fetch data)
```

### Root Cause
The Dockerfile was missing `COPY minikube_ops.py /app/minikube_ops.py`.
The backend import fails on startup, causing uvicorn to exit with error.

### Impact
**Scope**: All API endpoints
**Severity**: Users cannot use the app; frontend loads but is non-functional
**Workaround**: Rebuild image with `minikube_ops.py` included

### Solution

**Option 1: Rebuild Image (Recommended)**
```bash
# Update Dockerfile to include minikube_ops.py
# Then rebuild
/stop-ui
podman build -t test-automation-capa /path/to/repo
/run-ui
```

**Option 2: Manual Fix (if already running)**
```bash
# Copy the missing file into running container
podman cp minikube_ops.py test-automation-capa:/app/minikube_ops.py

# Restart the backend
podman exec test-automation-capa pkill -f uvicorn
# (Container will auto-restart uvicorn)

# Wait 5 seconds and verify
sleep 5
curl http://localhost:8000/api/health
```

### Verification
```bash
# Confirm API responds
curl http://localhost:8000/api/health
# Expected: {"status":"healthy","timestamp":"..."}

# Test frontend can fetch data
curl http://localhost:8000/api/clusters
# Expected: 200 OK with cluster list
```

### Prevention
- Always rebuild with `/stop-ui` before `/run-ui` when code changes
- Check `podman logs test-automation-capa` immediately after startup
- Verify health endpoint before assuming the app is ready
```
```
