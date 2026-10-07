# export-logs

Export container logs to file for analysis, debugging, or archival.

## What this skill does

Captures running container logs and saves them to a file:
- Exports all logs from container startup
- Saves to timestamped file (prevents overwrites)
- Supports filtering (errors only, last N lines, time range)
- Works from any directory (auto-detects repo)
- Container must be running

## Export all logs

```bash
# Export to timestamped file
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
podman logs test-automation-capa > /tmp/test-automation-capa_$TIMESTAMP.log

echo "✅ Logs exported to: /tmp/test-automation-capa_$TIMESTAMP.log"
ls -lh /tmp/test-automation-capa_*.log | tail -1
```

## Export with context

```bash
# Include timestamps in output
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
podman logs -t test-automation-capa > /tmp/test-automation-capa_with_ts_$TIMESTAMP.log

echo "Logs exported: /tmp/test-automation-capa_with_ts_$TIMESTAMP.log"
```

## Export errors only

```bash
# Filter for errors
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
podman logs test-automation-capa 2>&1 | grep -i "error\|exception\|traceback\|failed" > /tmp/test-automation-capa_errors_$TIMESTAMP.log

echo "Error logs exported: /tmp/test-automation-capa_errors_$TIMESTAMP.log"
```

## Export recent logs (last N minutes)

```bash
# Last 10 minutes
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
podman logs --since 10m test-automation-capa > /tmp/test-automation-capa_recent_$TIMESTAMP.log

echo "Recent logs exported: /tmp/test-automation-capa_recent_$TIMESTAMP.log"

# Or since specific time
podman logs --since 2026-09-28T12:00:00Z test-automation-capa > /tmp/capa_since_noon.log
```

## Export last N lines

```bash
# Last 500 lines
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
podman logs --tail 500 test-automation-capa > /tmp/test-automation-capa_tail_$TIMESTAMP.log

echo "Last 500 lines exported: /tmp/test-automation-capa_tail_$TIMESTAMP.log"
```

## Full diagnostic dump

```bash
# Export comprehensive diagnostic bundle
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="/tmp/capa_diagnostics_$TIMESTAMP"
mkdir -p "$OUTPUT_DIR"

echo "Collecting diagnostics to: $OUTPUT_DIR"

# Container logs
podman logs -t test-automation-capa > "$OUTPUT_DIR/container.log"

# Container status
podman ps --all > "$OUTPUT_DIR/container_status.txt"

# Health check
curl -s http://localhost:8000/api/health | jq . > "$OUTPUT_DIR/health_check.json"

# Container stats
podman stats --no-stream test-automation-capa > "$OUTPUT_DIR/resource_stats.txt"

# Errors only
podman logs test-automation-capa 2>&1 | grep -i "error\|exception" > "$OUTPUT_DIR/errors_only.log"

# Process list inside container
podman exec test-automation-capa ps aux > "$OUTPUT_DIR/processes.txt"

# Disk usage
podman exec test-automation-capa df -h > "$OUTPUT_DIR/disk_usage.txt"

echo "✅ Diagnostic bundle created:"
ls -lh "$OUTPUT_DIR"
```

## Save to specific location

```bash
# Export to project directory
REPO_PATH=$(git -C /Users/tinafitzgerald/acm_dev/ai_dev/test-automation-capa rev-parse --show-toplevel 2>/dev/null || echo /Users/tinafitzgerald/acm_dev/ai_dev/test-automation-capa)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

podman logs -t test-automation-capa > "$REPO_PATH/logs/capa_$TIMESTAMP.log"

echo "✅ Logs saved to: $REPO_PATH/logs/capa_$TIMESTAMP.log"
```

## Stream logs continuously

```bash
# Follow logs in real-time (Ctrl+C to stop)
podman logs -f test-automation-capa

# Or save while streaming
podman logs -f test-automation-capa | tee /tmp/capa_live_$(date +%s).log
```

## View exported logs

```bash
# List all exported logs
ls -lh /tmp/test-automation-capa_*.log

# View last exported log
cat /tmp/test-automation-capa_*.log | tail -100

# Search logs for pattern
grep "ERROR" /tmp/test-automation-capa_*.log

# Use less for pagination
less /tmp/test-automation-capa_*.log
```

## Common use cases

### After a failure, capture logs for analysis

```bash
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Full diagnostic bundle
OUTPUT_DIR="/tmp/capa_failed_$TIMESTAMP"
mkdir -p "$OUTPUT_DIR"
podman logs -t test-automation-capa > "$OUTPUT_DIR/full.log"
podman logs test-automation-capa 2>&1 | grep -i error > "$OUTPUT_DIR/errors.log"
curl -s http://localhost:8000/api/health | jq . > "$OUTPUT_DIR/health.json"
podman stats --no-stream test-automation-capa > "$OUTPUT_DIR/stats.txt"

echo "Exported to: $OUTPUT_DIR"
```

### Before restarting, save current state

```bash
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
podman logs -t test-automation-capa > "/tmp/before_restart_$TIMESTAMP.log"
echo "Saved pre-restart logs: /tmp/before_restart_$TIMESTAMP.log"

# Then restart
/stop-ui
/run-ui
```

### Send logs to colleague for debugging

```bash
# Export and compress
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
podman logs -t test-automation-capa | gzip > /tmp/capa_logs_$TIMESTAMP.log.gz

# Share the compressed file
echo "Share this file: /tmp/capa_logs_$TIMESTAMP.log.gz"
ls -lh /tmp/capa_logs_$TIMESTAMP.log.gz
```

## Options reference

- `-t` — Include timestamps
- `--tail N` — Show last N lines only
- `--since DURATION` — Show logs since duration (e.g., 5m, 10m, 1h)
- `--until TIME` — Show logs until timestamp
- `-f` — Follow (stream) logs
- `2>&1` — Include stderr in output

## Related skills

- `debug-ui-error` — Analyze logs to find issues
- `run-ui` — Start the application
- `stop-ui` — Stop the application

## Notes

- Logs are preserved even after container restarts
- Each export creates a new timestamped file (no overwrites)
- Default location: `/tmp/test-automation-capa_*.log`
- Timestamps in logs are UTC (matching container time)
- Export happens instantly (non-blocking)
- Container must be running (or recently stopped) to export logs
