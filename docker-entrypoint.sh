#!/bin/bash
set -e

echo "==========================================="
echo "  CAPA Test Automation - Starting"
echo "==========================================="

# If kubeconfig is mounted, use it
if [ -f /kube/config ]; then
    export KUBECONFIG=/kube/config
    echo "  Kubeconfig: /kube/config"
# If running as a pod, use in-cluster ServiceAccount token
elif [ -f /var/run/secrets/kubernetes.io/serviceaccount/token ]; then
    echo "  Kubeconfig: in-cluster (ServiceAccount)"
fi

# If ROSA token is set, log in
if [ -n "$ROSA_TOKEN" ]; then
    rosa login --token="$ROSA_TOKEN" 2>/dev/null && echo "  ROSA: logged in" || echo "  ROSA: login failed"
fi

# Show credential status
echo "  AWS: ${AWS_ACCESS_KEY_ID:+configured}${AWS_ACCESS_KEY_ID:-not set}"
echo "  oc:  $(oc whoami 2>/dev/null || echo 'not logged in')"
echo "==========================================="

# Start backend
cd /app/ui/backend
echo "Starting backend on :8000..."
uvicorn app:app --host 0.0.0.0 --port 8000 --log-level info &
BACKEND_PID=$!

# Wait for backend to be ready
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then
        echo "Backend ready."
        break
    fi
    sleep 1
done

# Start nginx (frontend)
echo "Starting frontend on :3000..."
nginx -g "daemon off;" &
NGINX_PID=$!

echo "==========================================="
echo "  CAPA Automation ready at http://localhost:3000"
echo "==========================================="

# Wait for either process to exit
wait -n $BACKEND_PID $NGINX_PID
exit $?
