# 🚨 Problem Report Template

**Make problem reports so clear and actionable that anyone can fix them.**

---

## 🎯 The One-Liner

Start here. If someone reads nothing else, they understand the issue:

```
[Component] is [broken/slow/crashing] when [condition], impact: [what breaks]
```

**Examples:**
```
Backend API is returning 500 errors on /api/clusters after container restart
Frontend is blank when Redis is unavailable, but should gracefully degrade
Tests are timing out waiting for cluster provisioning (30+ minute timeout)
```

---

## 📊 Quick Stats (fill these first)

```
Severity:      🔴 Critical | 🟠 High | 🟡 Medium | 🟢 Low
Status:        ❌ Broken | ⚠️  Degraded | 🔄 Intermittent | ✅ Fixed
Component:     [Backend | Frontend | Container | Network | Tests]
First Seen:    [Date/Time]
Reproducible:  [Always | Sometimes | Rare]
Impact:        [# users/features affected]
```

---

## 🔍 The Problem (in plain English)

Write as if explaining to a teammate over coffee. No jargon unless necessary.

**What happened:**
- What you did
- What you expected
- What actually happened

**Example:**
```
I restarted the container with /run-ui. The backend should start on port 8000.
Instead, it crashed with "ModuleNotFoundError: No module named 'minikube_ops'".
Frontend loads but can't fetch any data (all API calls fail).
```

**When it happens:**
- Every time? Under specific conditions? After X minutes?
- Does restarting help? Does refreshing the page help?
- Reproducible steps (numbered list)

---

## 📸 Show, Don't Tell

Raw evidence that proves the issue exists:

### Container Status
```
CONTAINER ID  IMAGE                 STATUS        PORTS
a1b2c3d4      test-automation-capa  Up 2 min      0.0.0.0:3000->3000
```

### Error Message (full traceback)
```
ERROR: ModuleNotFoundError: No module named 'minikube_ops'
  File "/app/ui/backend/app.py", line 42, in <module>
    import minikube_ops
  File "/usr/local/lib/python3.12/importlib/__init__.py", line 90, in import_module
```

### Health Checks (what's responding, what's not)
```
✅ Frontend:  http://localhost:3000 → 200 OK (blank page)
❌ API:       http://localhost:8000/api/health → 503 Service Unavailable
❌ Redis:     localhost:6379 → Connection refused (expected)
```

### Key Logs (last 20-30 lines, with context)
```
2026-09-28T12:29:45Z ERROR: Backend startup failed
2026-09-28T12:29:45Z ModuleNotFoundError: No module named 'minikube_ops'
2026-09-28T12:29:46Z Uvicorn exited with code 1
```

### Resource Usage (if performance-related)
```
CONTAINER  CPU %   MEM USAGE / LIMIT
capa       5.2%    1.8GB / 2GB  ⚠️  High memory!
```

---

## 🎓 The Why (Root Cause)

Explain what's actually broken, not just what went wrong:

**Root cause:**
```
The Dockerfile is missing COPY minikube_ops.py /app/minikube_ops.py.
When the app tries to import it on startup, Python can't find the module.
The entrypoint fails before uvicorn even starts.
```

**Why it matters:**
- Is this a code bug? Configuration issue? Missing dependency? Timing problem?
- Did something change recently? (Code commit, dependency update, environment?)
- Is this a known limitation? (Expected behavior you're documenting?)

---

## 💥 The Impact

**Users can't do:**
- ❌ Access the UI (blank page)
- ❌ Fetch cluster data via API
- ✅ Still can: View static frontend files

**Data risk:**
- ✅ No data loss (volumes preserved)
- ✅ No state corruption
- ⚠️  Long-running tests interrupted

**How long broken:**
- Started: 2026-09-28 12:29:45Z
- Duration: ~5 minutes before fix
- Blast radius: All users/jobs affected

---

## ✅ The Fix (multiple options, ranked)

### 🥇 Quick Fix (2 minutes, recommended)
```bash
# Restart container—usually clears transient issues
/stop-ui
/run-ui

# Verify
curl http://localhost:8000/api/health
```

**Why this works:** Fresh start, clean state, re-initializes all services.

---

### 🥈 Better Fix (5 minutes, durable)
```bash
# Step 1: Update the Dockerfile
# Add this line after line 71:
COPY minikube_ops.py /app/minikube_ops.py

# Step 2: Rebuild the image
podman build -t test-automation-capa .

# Step 3: Restart with new image
/stop-ui
/run-ui

# Step 4: Verify
curl http://localhost:8000/api/health
```

**Why this works:** Fixes the root cause in the build, not just the symptom.

---

### 🥉 Nuclear Option (if all else fails)
```bash
# Stop everything
/stop-ui

# Remove image and rebuild from scratch
podman rmi test-automation-capa:latest
podman build -t test-automation-capa .

# Start fresh
/run-ui
```

**Why:** Clears all cached layers, forces full rebuild, eliminates stale state.

---

## 🧪 Verification Checklist

**Before declaring "fixed":**

- [ ] Container started without errors
- [ ] `podman ps` shows container as "Up"
- [ ] `curl http://localhost:8000/api/health` returns 200 with `{"status":"healthy"}`
- [ ] Frontend loads at http://localhost:3000 (not blank)
- [ ] Can click around UI without console errors
- [ ] Test suite passes: `/run-ui-tests`
- [ ] No warnings in logs except Redis (expected)

**If still broken after fix:**
- Run `/debug-ui-error` and capture full diagnostics
- Check: Did you stop the old container before starting new one?
- Check: Is port 3000/8000 still in use by old process?

---

## 🛡️ How to Avoid This Next Time

**Prevention strategies:**

1. **Always rebuild after code changes**
   ```bash
   /stop-ui
   podman build -t test-automation-capa .
   /run-ui
   ```

2. **Check logs immediately after startup**
   ```bash
   podman logs test-automation-capa | head -50
   # Look for: ERROR, ModuleNotFoundError, ImportError, Traceback
   ```

3. **Verify health before assuming it works**
   ```bash
   curl http://localhost:8000/api/health
   # Must return 200 OK with {"status":"healthy"}
   ```

4. **Use this checklist in CI/CD**
   - Build succeeds? ✓
   - Container starts? ✓
   - Health check passes? ✓
   - All tests pass? ✓

---

## 📎 References & Context

- **Dockerfile:** `/Users/tinafitzgerald/acm_dev/ai_dev/test-automation-capa/Dockerfile` (line 71)
- **Backend entry:** `/app/ui/backend/app.py` (line 42)
- **Health endpoint:** `http://localhost:8000/api/health`
- **Related issues:** Similar to previous `app.py` import failures (see git log)
- **Documentation:** `ARCHITECTURAL_REVIEW.md` for system overview

---

## 🎬 Example: Complete Problem Report

```
## 🚨 Backend API Returns 503 Service Unavailable

**Severity:** 🔴 Critical
**Status:** ❌ Broken
**Component:** Backend
**First Seen:** 2026-09-28 12:29:45Z
**Reproducible:** Always (every startup)
**Impact:** Entire API down, affects 100% of users

---

### 🔍 The Problem

I ran `/run-ui` to start the application. The frontend loaded (http://localhost:3000)
but all API calls failed with 503 Service Unavailable. No data could be fetched.

**Reproducible steps:**
1. Run `/stop-ui` (if running)
2. Run `/run-ui`
3. Check health: `curl http://localhost:8000/api/health`
4. Observe: 503 error returned

---

### 📊 Evidence

**Container Status:**
```
CONTAINER ID  IMAGE                             STATUS       PORTS
a1b2c3d4      localhost/test-automation-capa    Up 30 sec    0.0.0.0:3000->3000, 0.0.0.0:8000->8000
```

**Health Check:**
```bash
$ curl http://localhost:8000/api/health
HTTP/1.1 503 Service Unavailable
{"detail":"Service Unavailable"}
```

**Logs (via /debug-ui-error):**
```
2026-09-28T12:29:42Z CAPA Test Automation - Starting
2026-09-28T12:29:45Z Starting backend on :8000...
2026-09-28T12:29:46Z ERROR: Failed to import app
2026-09-28T12:29:46Z ModuleNotFoundError: No module named 'minikube_ops'
2026-09-28T12:29:46Z   File "/app/ui/backend/app.py", line 42, in <module>
2026-09-28T12:29:46Z     import minikube_ops
```

**Frontend Status:**
```bash
$ curl http://localhost:3000
HTTP/1.1 200 OK
(returns blank HTML - API calls all fail)
```

---

### 🎓 Root Cause

The Dockerfile is missing a critical COPY instruction. The file `minikube_ops.py`
exists in the repo root but was never copied into the container image.

When FastAPI starts, `resource_browser_routes.py` tries to `import minikube_ops`
on line 25. Python can't find it (not in /app or PYTHONPATH), so the import fails.
The app crashes before uvicorn even listens on port 8000.

This happened because the Dockerfile was written without that file in mind.

---

### 💥 Impact

**Users can't:**
- ❌ Access any API endpoints
- ❌ Fetch cluster list, configurations, resources
- ❌ Create or manage clusters
- ✅ View static UI (but it's non-functional without API)

**Duration:** From container start until fix applied (~5 min)
**Blast radius:** All users/all features

---

### ✅ The Fix

**Recommended (2 min):**
```bash
/stop-ui
/run-ui
```
Usually works if it's a transient issue. Didn't work here (root cause is code).

**Better (5 min):**
```bash
# Step 1: Edit Dockerfile, add after line 71:
COPY minikube_ops.py /app/minikube_ops.py

# Step 2: Rebuild
podman build -t test-automation-capa .

# Step 3: Restart
/stop-ui
/run-ui

# Step 4: Verify
curl http://localhost:8000/api/health
# Expected: {"status":"healthy",...}
```

---

### 🧪 Verification

After applying fix:
- [x] Container starts without ERROR in logs
- [x] `curl http://localhost:8000/api/health` → 200 OK
- [x] Frontend loads and API calls work
- [x] Tests pass: `/run-ui-tests`

---

### 🛡️ Prevention

- Check Dockerfile whenever adding new Python files to the repo
- Always rebuild image after code changes: `podman build -t test-automation-capa .`
- Verify health immediately after startup: `curl http://localhost:8000/api/health`
- Monitor startup logs for import errors (most common failure mode)

---

### 📎 Files

- **Dockerfile:** Line 71 (missing COPY)
- **Backend:** `/app/ui/backend/app.py` (import on line 42)
- **Resource routes:** `/app/ui/backend/resource_browser_routes.py` (import on line 25)
- **Health endpoint:** `http://localhost:8000/api/health`
```
```

---

## 💡 Pro Tips for Amazing Reports

1. **Use emoji liberally** — Makes scanning fast (red 🔴 = critical, green ✅ = fixed)

2. **Show, don't tell** — Raw logs > "I saw an error"

3. **Give options** — Quick fix, better fix, nuclear option (ranked by time/durability)

4. **Make verification a checklist** — Copy-paste ready, boxes to check off

5. **Explain the why** — Not just "this is broken" but "here's why it's broken"

6. **Help future you** — Add prevention section so you don't repeat the same mistake

7. **One example per report** — One real, complete example is better than generic instructions

8. **Use markdown formatting** — Headers, code blocks, bold, italics (makes it readable)

9. **Link to sources** — File paths, line numbers, URLs (readers can drill down)

10. **End with confidence** — "This fix is durable and prevents recurrence" vs "might work"
