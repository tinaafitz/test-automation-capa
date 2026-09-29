# 🚨 Sample Problem Report: Frontend Timeout on Cluster List

---

## 🎯 The One-Liner

Frontend hangs for 60+ seconds when loading cluster list, eventually timeout. API is responding normally but something in the orchestrator is blocking.

---

## 📊 Quick Stats

```
Severity:      🟠 High
Status:        ⚠️  Intermittent
Component:     Frontend + Backend (Orchestrator)
First Seen:    2026-09-28 14:35:22Z
Reproducible:  Sometimes (happens 2-3 times out of 10)
Impact:        5-10 users affected, cluster list unusable
```

---

## 🔍 The Problem

**What I did:**
1. Started the UI with `/run-ui`
2. Navigated to the cluster list page
3. Clicked the "Load Clusters" button

**What I expected:**
- Page shows cluster list in <2 seconds
- Smooth, responsive UI

**What actually happened:**
- Button went unresponsive
- Loading spinner appeared
- Page hung for 60+ seconds
- Finally timed out with: `Failed to load clusters: Request timeout`
- Had to refresh and try again (sometimes works, sometimes doesn't)

**When it happens:**
- Happens randomly, not every time
- Seems to happen more often after the app has been running for 15+ minutes
- No pattern to which user/cluster triggers it
- Works fine if I wait 10 minutes and try again

---

## 📸 Show, Don't Tell

### Browser Console Error
```
[error] Uncaught (in promise) TypeError: Failed to fetch
  at fetchClusters (app.js:1234)
  at onClick (ClusterList.jsx:45)
  at HTMLButtonElement.onclick (index.html:1)

Stack:
  fetchClusters @ app.js:1234
  _callee$ @ app.js:1245
  tryCatch @ runtime.js:63
  invoke @ runtime.js:298
  Promise.then @ app.js:1237
  __awaiter @ app.js:1235
  fetchClusters @ app.js:1200
```

### Network Tab
```
Request:  GET http://localhost:8000/api/clusters
Status:   Pending (never completes)
Time:     60000ms (request timeout)
Response: (empty)

Next 5 requests:
  GET /api/health         → 200 OK (10ms)
  GET /api/config         → 200 OK (12ms)
  GET /api/versions       → 200 OK (8ms)
  GET /api/clusters       → HANG (60000ms timeout)
  GET /api/clusters       → HANG (60000ms timeout) [user retried]
```

### API Health Check (from `/debug-ui-error`)
```bash
$ curl http://localhost:8000/api/health
{"status":"healthy","timestamp":"2026-09-28T18:36:44.050699"}

✅ API responding, so it's not a general backend issue
```

### Backend Logs (when it happens)
```
2026-09-28T14:35:22Z INFO: GET /api/clusters
2026-09-28T14:35:22Z DEBUG: Orchestrator processing cluster list request
2026-09-28T14:35:22Z DEBUG: Acquiring lock on cluster cache
2026-09-28T14:35:23Z [STUCK HERE - no more logs]
[60 seconds of silence]
2026-09-28T14:36:23Z WARN: Request timeout, cancelling operation
2026-09-28T14:36:23Z ERROR: Cluster list fetch timed out after 60s
```

### Container Resource Usage (during hang)
```
CONTAINER  CPU %   MEM USAGE / LIMIT   PIDS
capa       95%     1.2GB / 2GB         47 ⚠️  Very high CPU!

Process list during hang:
python    12234   95.0% 1.2GB  (uvicorn worker spinning?)
```

### Code: The Orchestrator Lock (suspected culprit)
```python
# In capa_core.py, around line 256:

async def get_cluster_list(cluster_name=None, namespace=None):
    async with orchestrator_lock:  # ← SUSPICIOUS: Lock acquisition
        cached = await _check_cache(cluster_name, namespace)
        if cached:
            return cached
        
        # This is where it gets stuck (line 260-280)
        result = await asyncio.to_thread(
            minikube_ops.get_capi_resources,  # Blocking call!
            cluster_name,
            namespace
        )
        
        await _update_cache(result)
        return result
```

---

## 🎓 Root Cause

**The problem:** The orchestrator is blocking on a lock while calling a synchronous function inside an async context.

**Why it happens:**
1. Frontend requests `/api/clusters`
2. Backend acquires `orchestrator_lock` (async lock)
3. Then calls `minikube_ops.get_capi_resources()` — this is **synchronous and blocking**
4. If Kubernetes API is slow (or that's the test-automation pod doesn't have permission), the thread blocks
5. Other requests queue up waiting for the lock
6. After 60s, the request times out

**Why it's intermittent:**
- Depends on Kubernetes API response time
- Depends on network latency to the cluster
- Depends on how many concurrent requests pile up

**Why it happens after 15+ minutes:**
- Thread pool might be exhausted (all threads blocked)
- Or the lock holder is doing a slow operation

---

## 💥 Impact

**Users can't:**
- ❌ View cluster list (primary feature)
- ❌ Get cluster details, status, or configuration
- ⚠️  Can still view static UI (sidebar, navigation)
- ✅ Health check endpoint works fine
- ✅ Create new clusters (that endpoint is faster)

**Performance:**
- Normal response time: 100-200ms
- During hang: 60,000ms (60 seconds)
- 300x slower than normal

**How many users:**
- ~5-10 users out of 100 report this
- Happens randomly, 20-30% of requests fail
- Not correlated to specific clusters or regions

**How long:**
- Request appears to hang indefinitely (60s timeout)
- User has to refresh and retry
- 2-3 attempts usually succeeds
- No data loss, just poor UX

---

## ✅ The Fix

### 🥇 Quick Workaround (0 minutes, temporary)
```bash
# Refresh the page and try again
# 80% of the time it works on the second try

# Or wait 5-10 minutes and try again
# (lets the thread pool recover)
```

**Why:** Doesn't fix the root cause, but buys time.

---

### 🥈 Better Fix (15 minutes, semi-durable)
```bash
# Increase asyncio timeout (gives slow operations more time)
# Edit: ui/backend/app.py, around line 45

# Change from:
ORCHESTRATOR_TIMEOUT = 60  # seconds

# To:
ORCHESTRATOR_TIMEOUT = 120  # seconds (gives more breathing room)

# Then rebuild and restart:
/stop-ui
podman build -t test-automation-capa .
/run-ui
```

**Why:** Reduces false timeouts if the API is just slow. But doesn't fix the root cause (blocking calls in async context).

---

### 🥉 Proper Fix (30 minutes, durable)
```bash
# Convert minikube_ops.get_capi_resources to async
# This requires creating an async wrapper that doesn't block the event loop

# Step 1: Create new async version in common/async_minikube_ops.py
cat > common/async_minikube_ops.py << 'EOF'
import asyncio
from concurrent.futures import ThreadPoolExecutor
import minikube_ops

_executor = ThreadPoolExecutor(max_workers=10)  # Dedicated thread pool

async def get_capi_resources_async(cluster_name, namespace):
    """Non-blocking async wrapper for minikube_ops"""
    return await asyncio.get_event_loop().run_in_executor(
        _executor,
        minikube_ops.get_capi_resources,
        cluster_name,
        namespace
    )
EOF

# Step 2: Update capa_core.py to use the async version
# Change:
#   result = await asyncio.to_thread(minikube_ops.get_capi_resources, ...)
# To:
#   result = await async_minikube_ops.get_capi_resources_async(...)

# Step 3: Rebuild and restart
/stop-ui
podman build -t test-automation-capa .
/run-ui

# Step 4: Verify the fix works
# Try loading cluster list 10 times—should be consistent
```

**Why this works:**
- Uses dedicated thread pool (doesn't starve other operations)
- Doesn't block the async event loop
- Prevents lock contention
- Other requests can proceed while one is slow

---

### 🚀 Nuclear Option (1 hour, comprehensive)
If the above fix doesn't work, investigate deeper:

```bash
# Profile where the time is actually spent
podman exec test-automation-capa python -m cProfile -s cumtime /app/app.py &
# Then trigger a cluster list request
curl http://localhost:8000/api/clusters

# Look at which function calls are taking the most time
# Could be:
# - Kubernetes API is very slow (50s)
# - Network latency (20s)
# - Orchestrator doing O(n²) work (15s)

# Once you identify the bottleneck, optimize that specifically
```

---

## 🧪 Verification Checklist

After applying the fix:

- [ ] Restart UI: `/stop-ui && /run-ui`
- [ ] Open browser, navigate to cluster list
- [ ] Click "Load Clusters" button
- [ ] Observe: Page loads in <2 seconds (not 60s)
- [ ] **Repeat 10 times**: Click load clusters 10 times, all should succeed
- [ ] **Wait 20 minutes**: Let app run, then try again, should still be fast
- [ ] Check logs: No timeout errors in `/debug-ui-error`
- [ ] Health check still works: `curl http://localhost:8000/api/health`
- [ ] Run tests: `/run-ui-tests` all pass

**Success criteria:**
- 100% of requests complete in <2 seconds (not 60s timeout)
- No lock contention errors in logs
- Other endpoints still responsive

**If still hanging:**
- Might be Kubernetes API itself is slow (not the app)
- Check: Does `/api/health` still respond quickly? If yes, it's the cluster fetch
- Run profiling (see Nuclear Option above)

---

## 🛡️ How to Avoid This Next Time

### 1. **Never block in async contexts**
```python
# ❌ WRONG: This blocks the event loop
async def get_clusters():
    result = minikube_ops.get_capi_resources()  # Blocking!
    return result

# ✅ CORRECT: Use run_in_executor for blocking calls
async def get_clusters():
    result = await asyncio.get_event_loop().run_in_executor(
        None,
        minikube_ops.get_capi_resources
    )
    return result
```

### 2. **Set appropriate timeouts**
```python
# Wrap long operations with timeouts
try:
    result = await asyncio.wait_for(
        get_cluster_list(),
        timeout=30  # seconds
    )
except asyncio.TimeoutError:
    return {"error": "Cluster fetch timed out, try again"}
```

### 3. **Avoid locks in hot paths**
```python
# Don't hold locks while doing I/O
# Get the lock, copy the data, release the lock quickly
async with orchestrator_lock:
    cached = await _check_cache()
    
# Do the slow operation outside the lock
if not cached:
    result = await get_from_api()
```

### 4. **Monitor performance in tests**
```bash
# Add performance tests that catch regressions
pytest -v --durations=10  # Shows slowest 10 tests
# If cluster list fetch test takes >5 seconds, that's a regression
```

### 5. **Add logging at lock acquisition**
```python
logger.debug(f"Acquiring lock, queue_size={len(waiters)}")
async with orchestrator_lock:
    logger.debug("Lock acquired, processing")
logger.debug("Lock released")

# This lets you see if locks are being held too long
```

---

## 📎 References & Context

- **Code location:** `capa_core.py` line 256 (orchestrator lock)
- **Blocking call:** `minikube_ops.get_capi_resources()` (should be async)
- **Frontend:** `ui/frontend/src/components/ClusterList.jsx` line 45
- **API endpoint:** `http://localhost:8000/api/clusters`
- **Timeout setting:** `app.py` line 45 (ORCHESTRATOR_TIMEOUT = 60)
- **Architecture doc:** `ARCHITECTURAL_REVIEW.md` → "Execution Bottleneck" section
- **Related issue:** Similar pattern with PlaybookExecutor (also blocking in async)
- **Test case:** `ui/backend/test_app_extended.py` → `test_cluster_list_timeout`

---

## 💡 Key Takeaways

**What went wrong:** Synchronous blocking call inside async context, causing lock contention and timeouts.

**Why it's hard to debug:** Works fine most of the time (only fails under load or slow API conditions). Intermittent issues are the hardest to track down.

**The real lesson:** Async is contagious—if you mix blocking and async code, you get the worst of both worlds (complexity of async + blocking delays).

**Prevention:** Use profiling, add performance tests, never hold locks during I/O, and convert blocking library calls to async versions.
