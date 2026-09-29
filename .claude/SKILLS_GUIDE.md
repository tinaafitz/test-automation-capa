# 🛠️ test-automation-capa Skills Guide

Complete reference for all available Claude Code skills for the test-automation-capa project.

---

## Quick Start

All skills work from **any directory**—they auto-detect the repo path.

```bash
/run-ui              # Start the app
/stop-ui             # Stop the app
/run-ui-tests        # Run tests
/debug-ui-error      # Troubleshoot issues
/export-ui-logs      # Save logs to file
/code-review         # Conduct code review (95% confidence threshold)
```

---

## 🚀 Lifecycle Skills

### `/run-ui` — Start the Application

**What it does:**
- Starts podman machine (if needed)
- Builds image (skips if already built)
- Launches container with all services
- Opens ports 3000 (frontend), 8000 (API), 6379 (Redis)
- Mounts kubeconfig, vars, generated-yamls (if available)

**Usage:**
```bash
/run-ui
```

**Expected output:**
```
✅ Container started: test-automation-capa
✅ Frontend: http://localhost:3000
✅ API: http://localhost:8000
✅ API Health: {"status":"healthy",...}
```

**When to use:**
- Starting your day / beginning work session
- After stopping with `/stop-ui`
- After code changes (rebuilds automatically if needed)

**Related:**
- `/stop-ui` — Stop the app
- `/export-ui-logs` — Save logs before stopping

**File location:** `.claude/skills/run-ui/SKILL.md`

---

### `/stop-ui` — Stop the Application

**What it does:**
- Gracefully stops running container
- Removes container (frees resources)
- **Preserves data volume** for next startup
- Idempotent (safe to run multiple times)

**Usage:**
```bash
/stop-ui
```

**Expected output:**
```
✅ Container stopped successfully
✅ Data volume preserved for next startup
```

**When to use:**
- End of day / before shutdown
- Before rebuilding image
- Before restarting with different config
- If container is stuck/not responding

**Safe to run:**
- Container already stopped? No error
- Container in crash loop? Stops it anyway
- Multiple times in a row? No harm

**Related:**
- `/run-ui` — Start the app
- `/export-ui-logs` — Save logs before stopping

**File location:** `.claude/skills/stop-ui/SKILL.md`

---

## 🧪 Testing Skills

### `/run-ui-tests` — Run the Test Suite

**What it does:**
- Executes pytest against all tests
- Bypasses entrypoint (goes straight to pytest)
- Supports filtering by test name, file, or marker
- Reports pass/fail results and coverage
- Runs in ephemeral container (cleaned up after)

**Basic usage:**
```bash
/run-ui-tests
```

Runs all tests, shows output.

**Run specific test file:**
```bash
podman run --rm \
  --entrypoint bash \
  test-automation-capa:latest \
  -c "cd /app && pytest -v ui/backend/test_app.py"
```

**Run tests matching pattern:**
```bash
podman run --rm \
  --entrypoint bash \
  test-automation-capa:latest \
  -c "cd /app && pytest -v -k rosa"
```

**Run with coverage report:**
```bash
podman run --rm \
  --entrypoint bash \
  test-automation-capa:latest \
  -c "cd /app && pytest -v --cov --cov-report=term-missing"
```

**Options:**
- `-v` — Verbose output
- `-q` — Quiet output
- `--cov` — Calculate coverage
- `--cov-report=html` — HTML coverage report
- `-k PATTERN` — Filter by test name
- `-m MARKER` — Filter by marker (e.g., `unit`, `integration`)
- `--tb=short` — Shorter tracebacks
- `-x` — Stop on first failure
- `-s` — Show print statements

**When to use:**
- After code changes (verify nothing broke)
- Before commits (ensure quality gate)
- After `/run-ui` (validate app works)
- Debugging a specific test failure

**Expected output:**
```
collected 47 items

ui/backend/test_app.py::test_health_check PASSED
ui/backend/test_app.py::test_api_clusters PASSED
agents/test_agents.py::test_monitoring_agent PASSED
...
=============== 47 passed in 12.34s ===============
```

**If tests fail:**
1. Check error message and traceback
2. Run single failing test with `-s` to see prints
3. Run with `--tb=long` for full traceback
4. Use `/debug-ui-error` to check app state
5. Run `/export-ui-logs` to save logs for analysis

**Related:**
- `/run-ui` — Start the app first
- `/debug-ui-error` — If tests fail, debug the app
- `/export-ui-logs` — Save test output to file

**File location:** `.claude/skills/run-ui-tests/SKILL.md`

---

## 🔍 Debugging Skills

### `/debug-ui-error` — Troubleshoot Issues

**What it does:**
- Streams container logs (all output or filtered)
- Shows health check status (all endpoints)
- Displays resource usage (CPU, memory)
- Lists running processes
- Helps diagnose common problems

**Common diagnoses:**
```bash
# Show all logs
podman logs -f test-automation-capa

# Show errors only
podman logs test-automation-capa 2>&1 | grep -i error

# Show last 50 lines
podman logs --tail 50 test-automation-capa

# Show logs with timestamps
podman logs -t test-automation-capa

# Check health
curl http://localhost:8000/api/health | jq .

# Check resource usage
podman stats test-automation-capa

# Interactive shell (for deeper debugging)
podman exec -it test-automation-capa /bin/bash
```

**When to use:**
- Container won't start
- API returning 503 or error
- Frontend is blank or non-responsive
- Something's using lots of CPU/memory
- Need to understand what's happening

**How to report findings:**
Use the **PROBLEM_REPORT_TEMPLATE.md** for structured, actionable reports.

See **SAMPLE_PROBLEM_REPORT.md** for a complete example.

**Related:**
- `/export-ui-logs` — Save diagnostic output to file
- `/run-ui-tests` — If you suspect test issues
- `PROBLEM_REPORT_TEMPLATE.md` — How to report issues clearly

**File location:** `.claude/skills/debug-ui-error/SKILL.md`

---

### `/export-ui-logs` — Export Logs to File

**What it does:**
- Captures all container logs to timestamped file
- Supports filtering (errors only, last N lines, time range)
- Creates diagnostic bundle (logs + health + stats + processes)
- Saves to `/tmp/` with timestamps (no overwrites)
- Uses standard `podman logs` commands

**Basic export (all logs):**
```bash
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
podman logs -t test-automation-capa > /tmp/test-automation-capa_$TIMESTAMP.log
```

**Export errors only:**
```bash
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
podman logs test-automation-capa 2>&1 | grep -i error > /tmp/errors_$TIMESTAMP.log
```

**Create full diagnostic bundle:**
```bash
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="/tmp/capa_diagnostics_$TIMESTAMP"
mkdir -p "$OUTPUT_DIR"

podman logs -t test-automation-capa > "$OUTPUT_DIR/container.log"
podman ps --all > "$OUTPUT_DIR/container_status.txt"
curl -s http://localhost:8000/api/health | jq . > "$OUTPUT_DIR/health_check.json"
podman stats --no-stream test-automation-capa > "$OUTPUT_DIR/resource_stats.txt"
podman exec test-automation-capa ps aux > "$OUTPUT_DIR/processes.txt"

echo "Bundle ready: $OUTPUT_DIR"
```

**Common use cases:**
- Before restarting, save current logs
- Send logs to colleague for debugging
- Archive logs for later analysis
- Attach logs to bug report

**When to use:**
- After reproducing a problem
- Before restarting container
- When sharing issues with others
- For post-mortem analysis

**Output locations:**
- Single file: `/tmp/test-automation-capa_20260928_133142.log`
- Bundle: `/tmp/capa_diagnostics_20260928_133142/`

**Related:**
- `/debug-ui-error` — View logs interactively first
- `PROBLEM_REPORT_TEMPLATE.md` — Include logs in structured reports

**File location:** `.claude/skills/export-ui-logs/SKILL.md`

---

## 🔍 Code Review Skill

### `/code-review` — Architectural Code Analysis

**What it does:**
- Conducts deep code analysis across multiple dimensions
- Reviews architecture, security, performance, testing, maintainability
- Reports findings above 95% confidence threshold only
- Provides verified findings with reproduction steps, impact, and fixes
- Supports PR reviews, module reviews, architecture audits, security audits

**Basic usage:**
```bash
# Review a file
/code-review path/to/file.py

# Review architecture
/code-review --architecture

# Security audit with threat modeling
/code-review --security --threat-modeling

# Performance analysis
/code-review --performance --async
```

**Review types (ranked by scope):**
- Pull request review — Focused on changeset impact (5-10 min)
- Module review — Deep dive into component (20-30 min)
- Full architecture review — System-wide analysis (1-2 hours)
- Security audit — Threat modeling and vulns (1-2 hours)

**Output format:**
```
## 🎯 Review Scope
[What was reviewed]

## 📊 Executive Summary
[Key findings ranked by severity]

## ✅ Strengths
[Patterns worth replicating]

## ⚠️ Findings (95% Confidence)
[Verified issues with severity, file:line, verification method, impact, fix, prevention]
```

**Severity levels:**
- 🔴 Critical — System crashes, data loss, security breach, core feature broken
- 🟠 High — Performance degradation, scalability issue, auth flaw
- 🟡 Medium — Code quality, prevents bugs, minor perf issue
- 🟢 Low — Nice to have, style, edge case

**When to use:**
- Before submitting pull request (catch issues early)
- During code review (verify fixes before merge)
- Architecture planning (validate system design)
- Security audit (identify vulnerabilities)
- Performance optimization (find bottlenecks)

**Key principle:**
Only reports findings above 95% confidence. No plausible, exploratory, or hypothetical issues—only verified problems.

**Related:**
- `/run-ui-tests` — Verify tests pass for changes
- `/debug-ui-error` — Diagnose if code breaks something
- `PROBLEM_REPORT_TEMPLATE.md` — How to structure detailed reports

**File location:** `.claude/skills/code-review/SKILL.md`

---

## 📋 Templates & Guides

### `PROBLEM_REPORT_TEMPLATE.md`

**What it is:** A comprehensive template for reporting problems clearly and actionably.

**Sections:**
- One-liner (problem in one sentence)
- Quick stats (severity, status, impact)
- Plain English problem description
- Raw evidence (logs, errors, health checks)
- Root cause analysis
- Impact quantification
- Multiple fix options (ranked by time/durability)
- Verification checklist
- Prevention strategies
- File references and context

**When to use:**
- Reporting a bug or issue
- Documenting a problem for others to fix
- Creating post-mortem after incident
- Sharing debugging session results

**Pro tips:**
- Use emoji for quick scanning (🔴 = critical, ✅ = fixed)
- Show raw logs, not interpretations
- Give 2-3 fix options (quick, better, proper)
- End with prevention section
- Link to files, line numbers, endpoints

**File location:** `.claude/skills/PROBLEM_REPORT_TEMPLATE.md`

---

### `SAMPLE_PROBLEM_REPORT.md`

**What it is:** A complete, real-world example of a problem report.

**Scenario:** Frontend timeout on cluster list (intermittent, hard to debug)

**Shows:**
- How to fill out each section of the template
- Real error messages and logs
- Root cause analysis for async/blocking issue
- Three fix options with code
- Verification checklist (copy-paste ready)
- Prevention code examples
- Key architectural lessons

**When to use:**
- First time using the problem report template
- Need to understand what "good" looks like
- Want to copy structure for your own reports

**File location:** `.claude/skills/SAMPLE_PROBLEM_REPORT.md`

---

## 🗺️ Skill Map

```
┌─────────────────────────────────────────────────────────────┐
│                  test-automation-capa                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Lifecycle       Testing          Debugging         Review  │
│  ─────────       ───────          ────────          ──────  │
│  /run-ui         /run-ui-tests    /debug-ui-error   /code-  │
│  /stop-ui                        /export-ui-logs    review  │
│                                                             │
│  Templates                                                  │
│  ─────────                                                  │
│  PROBLEM_REPORT_TEMPLATE.md                                 │
│  SAMPLE_PROBLEM_REPORT.md                                   │
│  FINDINGS_TEMPLATE.md (for debug-ui-error)                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 Skill Usage Patterns

### Development Workflow
```bash
# Start your day
/run-ui

# Make code changes, then verify
/run-ui-tests

# If tests fail, debug
/debug-ui-error

# Export logs for analysis
/export-ui-logs

# End of day
/stop-ui
```

### Debugging Workflow
```bash
# Something's wrong
/debug-ui-error

# Need more details
/export-ui-logs

# Create structured report
# (Use PROBLEM_REPORT_TEMPLATE.md)

# Share with team
# (Attach exported logs + structured report)
```

### CI/CD Pipeline
```bash
/run-ui              # Build and start
/run-ui-tests        # Verify tests pass
# If fail:
/export-ui-logs      # Capture for debugging
/debug-ui-error      # Analyze
/stop-ui             # Clean up
```

---

## 🔧 Troubleshooting Skill Issues

### Skill not found error
**Problem:** `/run-ui` gives "Unknown skill" error

**Solution:** Skills are in `.claude/skills/` but may not be registered in this session.
Run the commands directly from the skill files instead.

```bash
# Check skills exist
ls -la .claude/skills/

# If the issue persists, the skill might need to be loaded in your Claude Code session
# Restart Claude Code or check the skill path
```

### Container not found
**Problem:** "Container 'test-automation-capa' not found"

**Solution:** Container may have exited or wasn't started
```bash
/run-ui              # Start it first
podman ps -a         # List all containers
```

### Port already in use
**Problem:** "Address already in use" when running `/run-ui`

**Solution:**
```bash
# Find what's using the port
lsof -i :3000        # Check port 3000
lsof -i :8000        # Check port 8000

# Kill it or stop the old container
/stop-ui
# Then try again
/run-ui
```

### Tests hanging
**Problem:** `/run-ui-tests` never completes

**Solution:** Some tests may be slow or stuck
```bash
# Run with timeout
timeout 120s podman run --rm --entrypoint bash test-automation-capa:latest -c "cd /app && pytest -v --tb=short"

# Or run specific fast test
podman run --rm --entrypoint bash test-automation-capa:latest -c "cd /app && pytest -v -k health"
```

---

## 📚 Related Documentation

- **Architecture:** `ARCHITECTURAL_REVIEW.md` — System design and patterns
- **Docker:** `Dockerfile` — Container image definition
- **Environment:** `.env.example` — Configuration template
- **Tests:** `ui/backend/test_app.py` — Test examples

---

## 💡 Pro Tips

1. **Always start with `/run-ui`** — Ensures clean state before work
2. **Always run `/run-ui-tests` before committing** — Catch regressions early
3. **Use `/export-ui-logs` before stopping** — Preserve evidence
4. **Follow PROBLEM_REPORT_TEMPLATE.md** — Make issues clear and actionable
5. **Check health endpoint often** — Quick way to verify app is working

---

## 🤝 Contributing New Skills

To create a new skill:

1. Create directory: `.claude/skills/my-skill/`
2. Create `SKILL.md` with:
   - What it does
   - Basic usage
   - Examples
   - Related skills
   - File location pointer
3. Add to this guide under appropriate section
4. Test it works from any directory
5. Document any new templates/guides

---

## 📞 Support

If a skill isn't working:

1. Check `.claude/skills/[skill-name]/SKILL.md` for requirements
2. Run `/debug-ui-error` to check container state
3. Run `/export-ui-logs` to save diagnostics
4. Create structured report using `PROBLEM_REPORT_TEMPLATE.md`
5. Share report + logs with the team

---

**Last updated:** 2026-09-28  
**Skills count:** 6 (lifecycle, testing, debugging, code review)  
**Templates:** 3 (problem reporting, findings, sample)  
**Test results:** 1763 tests, 98-99% pass rate
