#!/bin/bash

CLUSTER_PREFIX="$1"
NAMESPACE="${2:-multicluster-engine}"
ROSA_NAMESPACE="ns-rosa-hcp"

if [ -z "$CLUSTER_PREFIX" ]; then
    echo "Usage: $0 <cluster-prefix> [controller-namespace]"
    echo "Example: $0 goo"
    echo "         $0 goo open-cluster-management"
    exit 1
fi

CAPA_POD=""
LOG_PID=""
WATCH_PID=""

cleanup() {
    echo
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Cleaning up background processes..."
    if [ -n "$LOG_PID" ]; then
        kill $LOG_PID 2>/dev/null
    fi
    if [ -n "$WATCH_PID" ]; then
        kill $WATCH_PID 2>/dev/null
    fi
    exit 0
}

trap cleanup SIGINT SIGTERM

find_capa_pod() {
    oc get pods -n "$NAMESPACE" -l control-plane=capa-controller-manager -o jsonpath='{.items[0].metadata.name}' 2>/dev/null
}

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting CAPA resurrection monitor for cluster prefix: $CLUSTER_PREFIX"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Controller namespace: $NAMESPACE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] ROSA namespace: $ROSA_NAMESPACE"

CAPA_POD=$(find_capa_pod)
if [ -z "$CAPA_POD" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: Could not find CAPA controller pod in namespace $NAMESPACE"
    exit 1
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Found CAPA controller pod: $CAPA_POD"

{
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting controller log monitoring..."
    oc logs -n "$NAMESPACE" -f "$CAPA_POD" -c manager 2>/dev/null | while IFS= read -r line; do
        timestamp=$(date '+%Y-%m-%d %H:%M:%S')
        if echo "$line" | grep -q "$CLUSTER_PREFIX"; then
            if echo "$line" | grep -qi "reconcil\|delete\|create\|update"; then
                echo "[$timestamp] CONTROLLER: $line"
            fi
        fi
    done
} &
LOG_PID=$!

{
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting CR watch monitoring..."
    oc get cluster,rosacontrolplane,rosacluster,rosanetwork,rosaroleconfig,rosamachinepool -n "$ROSA_NAMESPACE" --watch 2>/dev/null | while IFS= read -r line; do
        timestamp=$(date '+%Y-%m-%d %H:%M:%S')
        if echo "$line" | grep -q "$CLUSTER_PREFIX"; then
            if echo "$line" | grep -qE "ADDED|MODIFIED|DELETED"; then
                echo "[$timestamp] CR_EVENT: $line"
            fi
        fi
    done
} &
WATCH_PID=$!

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Monitoring started. Press Ctrl+C to stop."
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Watching for events related to cluster prefix: $CLUSTER_PREFIX"

wait