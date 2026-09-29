# stop-ui

Stop and clean up the test-automation-capa web application.

## What this skill does

Cleanly shuts down the test-automation-capa container:
- Stops the running container
- Removes the container
- Preserves data volumes for next startup
- Works from any directory

## Stops

- **Frontend**: React app (port 3000)
- **Backend**: FastAPI server (port 8000)
- **Redis**: Cache/queue backend (port 6379)

## Shutdown command

```bash
# Stop and remove container
podman stop test-automation-capa 2>/dev/null || true
podman rm test-automation-capa 2>/dev/null || true

# Verify stopped
podman ps | grep test-automation-capa || echo "Container stopped successfully"
```

Gracefully handles already-stopped containers (no errors).

## Data persistence

- Container removed but volumes preserved
- Data in `test-automation-data` volume retained
- Next `run-ui` will start fresh container with same data

## Logs before shutdown

If you want to capture logs before stopping:

```bash
podman logs test-automation-capa > /tmp/test-automation-capa-final.log
podman stop test-automation-capa
```

## Related skills

- `run-ui` — Start the application
- `run-tests` — Execute test suite

## Notes

- Safe to run multiple times (idempotent)
- Removes container but preserves volumes
- To fully clean (delete volumes too): `podman volume rm test-automation-data`
