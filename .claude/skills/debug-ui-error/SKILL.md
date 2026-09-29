# debug-ui-error

Diagnose and troubleshoot issues with the test-automation-capa application.

## What this skill does

Collects diagnostic information from a running container:
- Streams live container logs with filtering
- Captures backend error stack traces
- Shows frontend console errors (via API)
- Displays container resource usage (CPU, memory)
- Health check status
- Service startup status

Works from any directory (auto-detects repo path).

## Show all logs

```bash
podman logs -f test-automation-capa
```

## Show only errors

```bash
podman logs test-automation-capa 2>&1 | grep -i error
```

## Show last N lines

```bash
# Last 50 lines
podman logs --tail 50 test-automation-capa

# Last 100 lines with timestamps
podman logs --tail 100 -t test-automation-capa
```

## Show logs since specific time

```bash
# Last 5 minutes
podman logs --since 5m test-automation-capa

# Last 10 minutes
podman logs --since 10m test-automation-capa
```

## Full diagnostic report

```bash
echo "=== Container Status ==="
podman ps --all | grep test-automation-capa

echo -e "\n=== Recent Logs (last 50 lines) ==="
podman logs --tail 50 test-automation-capa

echo -e "\n=== Errors Only ==="
podman logs test-automation-capa 2>&1 | grep -iE "error|exception|traceback"

echo -e "\n=== Container Stats ==="
podman stats --no-stream test-automation-capa

echo -e "\n=== Health Check ==="
curl -s http://localhost:8000/api/health | jq .

echo -e "\n=== Frontend Availability ==="
curl -s -I http://localhost:3000 | head -5

echo -e "\n=== Network Ports ==="
netstat -tulpn 2>/dev/null | grep -E "3000|8000|6379" || ss -tulpn 2>/dev/null | grep -E "3000|8000|6379"
```

## Common issues and fixes

### Backend won't start

**Symptom:** Container running but API not responding

```bash
# Check logs for import errors
podman logs test-automation-capa 2>&1 | grep -i "error\|modulenotfound\|import"

# Restart backend
podman exec test-automation-capa pkill -f uvicorn
```

### Frontend blank/not loading

**Symptom:** Port 3000 open but blank page

```bash
# Check nginx status
podman exec test-automation-capa ps aux | grep nginx

# Check frontend build
podman exec test-automation-capa ls -la /app/ui/frontend/build

# View nginx error logs
podman exec test-automation-capa tail -50 /var/log/nginx/error.log
```

### High memory usage

**Symptom:** Container using excessive RAM

```bash
# Check memory
podman stats test-automation-capa

# Show processes by memory
podman exec test-automation-capa ps aux --sort=-%mem | head -10
```

### Port already in use

**Symptom:** "Address already in use" error

```bash
# Find what's using the port
lsof -i :3000
lsof -i :8000

# Or with ss
ss -tulpn | grep 3000
```

### Redis not available

**Symptom:** "Redis not available" warning (normal for local mode)

This is expected. The app falls back to local orchestrator mode. Not an error.

## Interactive shell in container

```bash
# Access container shell for manual debugging
podman exec -it test-automation-capa /bin/bash

# Then inside:
ps aux              # See running processes
curl localhost:8000/api/health  # Test API
cat /var/log/nginx/error.log  # View nginx errors
```

## Related skills

- `run-ui` — Start the application
- `stop-ui` — Stop the application
- `run-ui-tests` — Run test suite

## Notes

- Logs are realtime; use Ctrl+C to stop streaming
- Container must be running to view logs
- If container crashed, logs still available: `podman logs <container-id>`
- All timestamps in container logs are UTC
- Sentry monitoring disabled by default (set SENTRY_DSN to enable)
