# Skills Summary

Complete toolkit for test-automation-capa development, testing, debugging, and code review.

---

## 🛠️ All Skills (6 Total)

### Lifecycle Skills (2)
| Skill | Purpose | Time | Status |
|-------|---------|------|--------|
| `/run-ui` | Start the application | 30s | ✅ Tested |
| `/stop-ui` | Stop the application cleanly | 5s | ✅ Tested |

### Testing Skills (1)
| Skill | Purpose | Time | Status |
|-------|---------|------|--------|
| `/run-ui-tests` | Run 1763-test suite | 5-10 min | ✅ Tested, 98-99% pass rate |

### Debugging Skills (2)
| Skill | Purpose | Time | Status |
|-------|---------|------|--------|
| `/debug-ui-error` | Troubleshoot issues | 2-5 min | ✅ Created |
| `/export-ui-logs` | Save logs to file | 1 min | ✅ Tested |

### Code Review Skills (1)
| Skill | Purpose | Time | Status |
|-------|---------|------|--------|
| `/code-review` | Architectural analysis (95% confidence) | 5 min - 2 hrs | ✅ Created |

---

## 📊 Quick Reference

### Start Your Day
```bash
/run-ui              # Launch app
```

### During Development
```bash
/run-ui-tests        # Verify tests pass
/code-review .       # Review your changes
```

### When Something Breaks
```bash
/debug-ui-error      # See what's wrong
/export-ui-logs      # Save logs for analysis
```

### End of Day
```bash
/stop-ui             # Shut down cleanly
```

---

## 📋 Templates & Guides

### Documentation
- **SKILLS_GUIDE.md** — Complete skill reference (this guide, detailed)
- **SKILLS_SUMMARY.md** — Quick skill overview (you are here)
- **TEST_RESULTS.md** — Latest test run results (1763 tests, 98-99% pass)

### Problem Reporting
- **PROBLEM_REPORT_TEMPLATE.md** — How to report problems clearly
- **SAMPLE_PROBLEM_REPORT.md** — Real-world example (frontend timeout)
- **FINDINGS_TEMPLATE.md** — Structured findings format

---

## 🎯 Key Features

### ✅ Location-Independent
All skills work from any directory via auto-detection:
```bash
cd /anywhere/in/filesystem
/run-ui              # Works! Auto-detects repo path
```

### ✅ No Dependencies
Each skill is self-contained. No setup required:
```bash
/run-ui              # Starts podman machine, builds image, launches container
```

### ✅ Idempotent
Safe to run multiple times:
```bash
/stop-ui             # Safe even if already stopped
/run-ui              # Rebuilds only if code changed
```

### ✅ 95% Confidence Threshold
Code review only reports verified findings, not plausible issues:
- ✅ Can reproduce the bug
- ✅ Can show exact failure scenario
- ✅ Impact is clear and measurable
- ❌ No "might be a problem" findings

### ✅ Comprehensive Testing
- 1763 tests collected
- 98-99% pass rate
- Agent framework verified (monitoring, diagnostic, remediation)
- Backend API verified
- Integration patterns tested

---

## 🔄 Common Workflows

### Feature Development
```bash
# Start
/run-ui

# Make changes, test frequently
/run-ui-tests

# Before commit
/code-review path/to/file.py

# End
/stop-ui
```

### Bug Investigation
```bash
# See what's wrong
/debug-ui-error

# Get more details
/export-ui-logs

# Create structured report
# (Use PROBLEM_REPORT_TEMPLATE.md)
```

### Code Review (PR)
```bash
# Quick review of changes
/code-review --pr main...feature-branch

# Or deep dive
/code-review --architecture
```

### Security Audit
```bash
# Threat modeling + vulnerabilities
/code-review --security --threat-modeling
```

---

## 📈 Test Coverage

**Test Suite:** 1763 tests  
**Pass Rate:** 98-99%  
**Coverage:**
- Agent framework (monitoring, diagnostic, remediation)
- Backend API (health, config, provisioning, auth)
- Integration patterns (Kubernetes, AWS, OCM)
- Error handling (timeouts, retries, state management)

---

## 🚀 Next Skills to Consider

1. **`health-check`** — Full system health verification
2. **`shell`** — Interactive container shell
3. **`rebuild-image`** — Force clean rebuild
4. **`watch-logs`** — Stream logs with filtering
5. **`perf-stats`** — Container resource monitoring

---

## 📚 Documentation Map

```
.claude/
├── SKILLS_GUIDE.md              ← Complete reference (detailed)
├── SKILLS_SUMMARY.md            ← Quick overview (you are here)
├── TEST_RESULTS.md              ← Latest test run
├── skills/
│   ├── run-ui/
│   │   └── SKILL.md
│   ├── stop-ui/
│   │   └── SKILL.md
│   ├── run-ui-tests/
│   │   └── SKILL.md
│   ├── debug-ui-error/
│   │   ├── SKILL.md
│   │   └── FINDINGS_TEMPLATE.md
│   ├── export-ui-logs/
│   │   └── SKILL.md
│   ├── code-review/
│   │   └── SKILL.md
│   ├── PROBLEM_REPORT_TEMPLATE.md
│   └── SAMPLE_PROBLEM_REPORT.md
└── CLAUDE.md                    ← Project standards (95% confidence)
```

---

## 💡 Best Practices

1. **Always start with `/run-ui`** before work session
2. **Always end with `/stop-ui`** to clean up
3. **Run `/run-ui-tests` before commits** (catch regressions)
4. **Use `/code-review` for PRs** (verify architecture)
5. **Use `/debug-ui-error` first when something breaks** (quick diagnosis)
6. **Use `PROBLEM_REPORT_TEMPLATE.md` for structured issues** (clarity for team)

---

## 🤝 Support

**Skills not working?**
1. Check `.claude/skills/[skill-name]/SKILL.md` for requirements
2. Run `/debug-ui-error` to check container state
3. Run `/export-ui-logs` to save diagnostics
4. Use `PROBLEM_REPORT_TEMPLATE.md` to structure your issue
5. Share report + logs with team

**Want to add a skill?**
1. Create `.claude/skills/my-skill/SKILL.md`
2. Document usage, examples, related skills
3. Test from any directory (auto-detection)
4. Update `SKILLS_GUIDE.md`

---

## 📊 Stats

- **Skills:** 6 total
- **Templates:** 3 (problem reporting, findings, sample)
- **Documentation:** 5 guides (SKILLS_GUIDE, SKILLS_SUMMARY, TEST_RESULTS, CLAUDE, architectural reviews)
- **Tests:** 1763 collected, 98-99% pass rate
- **Code fixes:** FastAPI upgrade, imports cleaned, Dockerfile fixed
- **Container:** Podman-based, location-independent, idempotent

---

**Ready to use! Pick a skill and start:**

```bash
/run-ui              # ← Start here
```
