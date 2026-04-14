#!/bin/bash
# Run CAPA Test Automation as a container
#
# Usage:
#   ./container-run.sh                    # basic run
#   ./container-run.sh --build            # rebuild and run
#   ROSA_TOKEN=eyJ... ./container-run.sh  # with ROSA token
#
# Prerequisites:
#   - podman (or docker)
#   - oc login done on host (kubeconfig mounted)
#   - ROSA_TOKEN env var (or rosa login done on host)
#   - AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY env vars

set -e

IMAGE_NAME="capa-automation"
CONTAINER_NAME="capa-automation"
PORT="${PORT:-3000}"
RUNTIME="${CONTAINER_RUNTIME:-podman}"

# Check for podman/docker
if ! command -v "$RUNTIME" &>/dev/null; then
    if command -v docker &>/dev/null; then
        RUNTIME="docker"
    elif command -v podman &>/dev/null; then
        RUNTIME="podman"
    else
        echo "Error: podman or docker required"
        exit 1
    fi
fi

# Build if requested or image doesn't exist
if [ "$1" = "--build" ] || ! $RUNTIME image exists "$IMAGE_NAME" 2>/dev/null; then
    echo "Building $IMAGE_NAME..."
    $RUNTIME build -t "$IMAGE_NAME" .
fi

# Stop existing container if running
$RUNTIME rm -f "$CONTAINER_NAME" 2>/dev/null || true

# Build run args
RUN_ARGS=(
    --name "$CONTAINER_NAME"
    -p "${PORT}:3000"
)

# Mount kubeconfig if it exists
KUBECONFIG_PATH="${KUBECONFIG:-$HOME/.kube/config}"
if [ -f "$KUBECONFIG_PATH" ]; then
    RUN_ARGS+=(-v "${KUBECONFIG_PATH}:/kube/config:ro,Z")
    echo "Mounting kubeconfig: $KUBECONFIG_PATH"
fi

# Mount ROSA config if it exists
if [ -d "$HOME/.config/ocm" ]; then
    RUN_ARGS+=(-v "$HOME/.config/ocm:/root/.config/ocm:ro,Z")
    echo "Mounting ROSA/OCM config"
fi

# Mount AWS config if it exists
if [ -d "$HOME/.aws" ]; then
    RUN_ARGS+=(-v "$HOME/.aws:/root/.aws:ro,Z")
    echo "Mounting AWS config"
fi

# Pass credential env vars if set
[ -n "$ROSA_TOKEN" ]            && RUN_ARGS+=(-e "ROSA_TOKEN=$ROSA_TOKEN")
[ -n "$AWS_ACCESS_KEY_ID" ]     && RUN_ARGS+=(-e "AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID")
[ -n "$AWS_SECRET_ACCESS_KEY" ] && RUN_ARGS+=(-e "AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY")
[ -n "$AWS_DEFAULT_REGION" ]    && RUN_ARGS+=(-e "AWS_DEFAULT_REGION=$AWS_DEFAULT_REGION")
[ -n "$OCM_TOKEN" ]             && RUN_ARGS+=(-e "OCM_TOKEN=$OCM_TOKEN")

# Persistent data volume for action history, agent knowledge base, etc.
RUN_ARGS+=(-v "capa-data:/app/vars:Z")

echo ""
echo "Starting $IMAGE_NAME on http://localhost:${PORT}"
echo ""

$RUNTIME run --rm -it "${RUN_ARGS[@]}" "$IMAGE_NAME"
