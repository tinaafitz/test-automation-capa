# run-ui

Launch the test-automation-capa web application (FastAPI backend + React frontend).

## What this skill does

Builds and runs the test-automation-capa application using podman:
- **Backend**: FastAPI server on port 8000
- **Frontend**: React app on port 3000
- **Redis**: Cache/queue backend (port 6379)

Provides access to:
- Frontend UI at http://localhost:3000
- API at http://localhost:8000
- MCE Environment at http://localhost:3000/mce
- Minikube Environment at http://localhost:3000/minikube

## Prerequisites

- `podman` installed and in PATH
- Podman machine running (`podman machine start` if needed)
- 4+ GB RAM available
- Network access to localhost ports 3000, 8000, 6379
- Ports 3000, 8000, 6379 not in use

## Launch

Auto-detects repo location and handles setup:

```bash
# Ensure podman machine is running
podman machine start 2>/dev/null || true

# Auto-detect repo path
REPO_PATH=$(git -C /Users/tinafitzgerald/acm_dev/ai_dev/test-automation-capa rev-parse --show-toplevel 2>/dev/null || echo /Users/tinafitzgerald/acm_dev/ai_dev/test-automation-capa)

# Clean up any existing container
podman stop test-automation-capa 2>/dev/null || true
podman rm test-automation-capa 2>/dev/null || true

# Build image if needed
podman image exists test-automation-capa:latest || (echo "Building image..." && podman build -t test-automation-capa "$REPO_PATH")

# Run container with optional volume mounts
podman run -d \
  --name test-automation-capa \
  -p 3000:3000 \
  -p 8000:8000 \
  -p 6379:6379 \
  $([ -f "$HOME/.kube/config" ] && echo "-v $HOME/.kube/config:/kube/config:ro") \
  $([ -f "$REPO_PATH/vars/user_vars.yml" ] && echo "-v $REPO_PATH/vars/user_vars.yml:/app/vars/user_vars.yml:ro") \
  -v test-automation-data:/data \
  $([ -d "$REPO_PATH/generated-yamls" ] && echo "-v $REPO_PATH/generated-yamls:/app/generated-yamls") \
  test-automation-capa:latest
```

Works from any directory — automatically locates the repo, starts podman if needed, and handles optional files.

## Health checks

- Frontend health: `curl http://localhost:3000`
- API health: `curl http://localhost:8000/api/health`
- Redis health: `redis-cli -p 6379 ping`

## Logs

```bash
podman logs -f test-automation-capa
```

## Stop

```bash
podman stop test-automation-capa
podman rm test-automation-capa
```

## Notes

- Built image: `test-automation-capa:latest`
- Runs in background with automatic restart
- Mounts kubeconfig for cluster access
- Mounts user_vars.yml for configuration
- Data persisted in `test-automation-data` volume

## Architecture

See [ARCHITECTURAL_REVIEW.md](../../ARCHITECTURAL_REVIEW.md) for full system architecture.
