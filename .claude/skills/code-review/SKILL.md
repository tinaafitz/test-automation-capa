# code-review

Conduct architectural and code quality reviews following 95% confidence threshold standards.

## What this skill does

Performs deep code analysis across multiple dimensions:
- **Architecture** — System design, patterns, coupling, scalability
- **Security** — Threat modeling, authentication, injection risks, data protection
- **Performance** — Algorithmic complexity, database queries, resource usage
- **Testing** — Coverage, isolation, mocking strategy, integration patterns
- **Maintainability** — Readability, naming, SOLID principles, technical debt

Reports findings above 95% confidence threshold only—no plausible or uncertain findings.

---

## Basic Review

```bash
# Review a specific file or directory
/code-review path/to/file.py

# Review multiple files
/code-review ui/backend/ agents/

# Review a specific function/class (provide file and context)
/code-review ui/backend/app.py --focus "get_cluster_list"
```

---

## Architecture Review

```bash
# Review system architecture (broad scope)
/code-review --architecture

# Review service boundaries and coupling
/code-review --boundaries

# Review async/event patterns
/code-review --patterns async-event

# Review state management
/code-review --patterns state-management
```

---

## Security Review

```bash
# Deep threat modeling
/code-review --security --threat-modeling

# Authentication/authorization analysis
/code-review --security --auth

# Input validation and injection prevention
/code-review --security --input-validation

# Secrets and credential handling
/code-review --security --secrets
```

---

## Performance Review

```bash
# Database query patterns
/code-review --performance --queries

# Async and concurrency
/code-review --performance --async

# Resource usage (memory, CPU)
/code-review --performance --resources

# Caching strategy
/code-review --performance --caching
```

---

## Testing Review

```bash
# Test coverage analysis
/code-review --testing --coverage

# Test isolation and mocking
/code-review --testing --isolation

# Integration test patterns
/code-review --testing --integration

# Fixture and setup/teardown
/code-review --testing --fixtures
```

---

## Output Format

All reviews follow the structure:

```
## 🎯 Review Scope
[What was reviewed and why]

## 📊 Executive Summary
[Key findings ranked by severity, 1-3 sentences each]

## ✅ Strengths
[What's done well, patterns worth replicating]

## ⚠️ Findings (95% Confidence)
[Issues verified above confidence threshold]

### [Finding 1]: [Title]
**Severity**: 🔴 Critical | 🟠 High | 🟡 Medium | 🟢 Low
**File**: path/to/file.py:line
**Category**: security | performance | correctness | maintainability
**Verification**: [How this was verified to 95% confidence]

**Problem**:
[What's wrong and why it matters]

**Impact**:
[What breaks, who's affected, when it happens]

**Evidence**:
[Code snippet, logs, or proof]

**Fix**:
[Recommended solution with code example]

---

## 📚 Related Patterns
[Links to ARCHITECTURAL_REVIEW.md patterns and examples]

## 🛡️ Prevention
[How to avoid this pattern in future code]
```

---

## Review Types

### Pull Request Review (Focused)
```bash
# Quick review of a specific changeset
/code-review --pr main...feature-branch

# What changed: Only files modified in this PR
# Scope: Impact analysis, not full architecture
# Time: 5-10 minutes
# Output: Quick findings + verification
```

### Module Review (Broad)
```bash
# Deep dive into a specific component
/code-review --module capa_core

# What changed: All files in the module
# Scope: Architecture, patterns, debt
# Time: 20-30 minutes
# Output: Comprehensive findings with prevention
```

### Full Architecture Review (Comprehensive)
```bash
# System-wide analysis
/code-review --architecture

# What changed: Entire codebase
# Scope: System design, coupling, scalability
# Time: 1-2 hours
# Output: Strategic insights and refactoring roadmap
```

### Security Audit (Threat-focused)
```bash
# Deep threat modeling and vulnerability analysis
/code-review --security --threat-modeling

# What changed: All auth, credential, API paths
# Scope: Attack surface, privilege escalation, data exposure
# Time: 1-2 hours
# Output: Threat model + vulns + mitigations
```

---

## Confidence Threshold

**Only report findings above 95% confidence.**

**95% confidence means:**
- ✅ Verified by static analysis + code reading
- ✅ Can reproduce the issue or show exact failure scenario
- ✅ Impact is clear and measurable
- ✅ Not a style preference or opinion
- ✅ Not a "might be a problem" or "could lead to"

**Don't report:**
- ❌ Plausible issues (could happen, but can't verify)
- ❌ Exploratory findings (need more investigation)
- ❌ Style issues (tabs vs spaces, naming conventions)
- ❌ Hypothetical problems (if X then Y, but X won't happen)

---

## Examples

### Example 1: Security Finding (Verified)
```
### O(n²) User Query Loop (N+1 Problem)
**Severity**: 🟠 High
**File**: ui/backend/app.py:234-250
**Category**: performance

**Verification**: Traced code execution with test inputs. Query counter shows:
- get_users() → 1 query
- Loop users (n=100): foreach user → get_user_clusters() → 100 queries
- Total: 1 + 100 = 101 queries for 100 users (✓ Reproduced)

**Problem**:
Inside the loop (line 240), we call get_user_clusters(user_id) for each user.
This executes one database query per user. With 100 users, that's 100 queries.

**Impact**:
- Cluster list page takes 15+ seconds to load
- Database connection pool exhausted (max 10 connections)
- API returns 503 under load (>50 concurrent users)
- Simple fix reduces query count 100x

**Evidence**:
```python
# ❌ WRONG: N+1 queries
users = get_users()  # 1 query
clusters_by_user = {}
for user in users:
    clusters_by_user[user.id] = get_user_clusters(user.id)  # ← 100 queries!
```

**Fix**:
```python
# ✅ CORRECT: Single batch query
users = get_users()  # 1 query
cluster_data = get_all_user_clusters(user_ids=[u.id for u in users])  # 1 query
clusters_by_user = {uid: clusters for uid, clusters in cluster_data}
```

**Prevention**:
- Always load relationships with joins or batch queries, not loops
- Add database query logging during development
- Write performance tests that assert query count
```

### Example 2: Architectural Finding (High Confidence)
```
### Orchestrator Lock Blocks Event Loop (Async Antipattern)
**Severity**: 🔴 Critical
**File**: capa_core.py:256-280
**Category**: correctness + performance

**Verification**:
- Static analysis: Lock held during blocking I/O (minikube_ops call)
- Profiling: Event loop blocked 60+ seconds during cluster fetch
- Logs: Timeout errors after 60 second hang
- Root cause identified: asyncio.to_thread() with no executor limit

**Problem**:
The orchestrator acquires an async lock, then calls a synchronous blocking function
inside the lock. If that function is slow (waiting for API response), it blocks
the entire event loop. Other requests queue up waiting for the lock.

**Impact**:
- Frontend cluster list requests timeout after 60 seconds
- 20-30% request failure rate (intermittent based on network latency)
- Thread pool exhaustion under load (all threads blocked)
- Affects primary user feature (cluster viewing)

**Evidence**:
```python
async def get_cluster_list(cluster_name=None, namespace=None):
    async with orchestrator_lock:  # ← Acquire lock
        result = await asyncio.to_thread(
            minikube_ops.get_capi_resources,  # ← BLOCKS for 50+ seconds!
            cluster_name,
            namespace
        )
        return result

# Logs during hang:
# 2026-09-28T14:35:22Z INFO: Acquiring lock
# [60 seconds of silence...]
# 2026-09-28T14:36:22Z ERROR: Request timeout
```

**Fix**:
```python
async def get_cluster_list(cluster_name=None, namespace=None):
    # Check cache (fast) without holding lock
    cached = await _check_cache(cluster_name, namespace)
    if cached:
        return cached
    
    # Do slow operation OUTSIDE lock with dedicated executor
    executor = ThreadPoolExecutor(max_workers=5)  # Limit threads
    result = await asyncio.get_event_loop().run_in_executor(
        executor,
        minikube_ops.get_capi_resources,
        cluster_name,
        namespace
    )
    
    # Update cache while holding lock (brief)
    async with orchestrator_lock:
        await _update_cache(result)
    
    return result
```

**Prevention**:
- Never hold locks while doing I/O (network, disk, subprocess)
- Use dedicated thread pools for blocking operations
- Add profiling to detect event loop blocking
- Test under simulated slow API conditions (add delays)
```

---

## Severity Levels

- 🔴 **Critical** — System crashes, data loss, security breach, or core feature broken
- 🟠 **High** — Significant performance degradation, scalability issue, or auth flaw
- 🟡 **Medium** — Improves code quality, prevents future bugs, or minor perf issue
- 🟢 **Low** — Nice to have, style improvement, or edge case

---

## Common Review Patterns

### Async/Blocking Review
- Identify blocking calls in async context
- Check event loop starvation patterns
- Verify executor configuration and limits
- Look for lock contention during I/O

### Database Query Review
- Detect N+1 query patterns
- Check for unbounded queries
- Verify index usage
- Look for missing batch operations

### Security Review
- Trace authentication flow (who can access what)
- Check input validation (form data, URLs, APIs)
- Identify credential storage/handling
- Look for SQL injection, XSS, CSRF vulnerabilities
- Check privilege escalation paths

### Test Coverage Review
- Identify untested happy paths
- Check for over-mocking (tests pass, code fails)
- Verify test isolation (cleanup, setup)
- Look for flaky/intermittent tests

---

## Related Documentation

- **Architecture standards:** `/CLAUDE.md` (95% confidence, SOLID, patterns)
- **Pattern library:** `ARCHITECTURAL_REVIEW.md` (cross-project patterns)
- **Threat modeling:** CLAUDE.md → Security Analysis Depth
- **Test patterns:** test-automation-capa/ARCHITECTURAL_REVIEW.md

---

## Pro Tips

1. **Start with architecture** — Understand the system before diving into code
2. **Verify everything** — Don't report plausible issues, verify to 95% confidence
3. **Show evidence** — Include code snippets, logs, reproduction steps
4. **Offer fixes** — Don't just point out problems, show the solution
5. **Context matters** — Understand constraints and trade-offs before judging
6. **Link to patterns** — Reference cross-project patterns for learning
7. **Prevention first** — How to avoid this pattern in future code

---

## Review Workflow

**Step 1: Scope** — Define what's being reviewed and why
**Step 2: Analyze** — Read code, run tests, profile if needed
**Step 3: Verify** — Confirm each finding above 95% confidence
**Step 4: Report** — Write clear, actionable findings
**Step 5: Recommend** — Provide fixes and prevention strategies

---

## File location

`.claude/skills/code-review/SKILL.md`

## Related skills

- `/run-ui-tests` — Verify tests pass for changes
- `/debug-ui-error` — Diagnose if code breaks something
- `/export-ui-logs` — Capture logs during code analysis
