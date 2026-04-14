#!/bin/bash
# Deploy CAPA Automation to an OpenShift cluster
#
# Prerequisites:
#   - oc logged in to the target cluster
#   - Image pushed to a registry (update deployment.yaml image field)
#   - Secret values filled in (deploy/secret.yaml)
#
# Usage:
#   ./deploy/deploy.sh           # deploy
#   ./deploy/deploy.sh teardown  # remove everything

set -e

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ "$1" = "teardown" ]; then
    echo "Removing CAPA Automation..."
    oc delete route capa-automation -n capa-automation 2>/dev/null || true
    oc delete service capa-automation -n capa-automation 2>/dev/null || true
    oc delete deployment capa-automation -n capa-automation 2>/dev/null || true
    oc delete pvc capa-automation-data -n capa-automation 2>/dev/null || true
    oc delete secret capa-automation-credentials -n capa-automation 2>/dev/null || true
    oc delete serviceaccount capa-automation -n capa-automation 2>/dev/null || true
    oc delete clusterrolebinding capa-automation 2>/dev/null || true
    oc delete clusterrole capa-automation 2>/dev/null || true
    oc delete namespace capa-automation 2>/dev/null || true
    echo "Done."
    exit 0
fi

echo "==========================================="
echo "  Deploying CAPA Automation"
echo "==========================================="
echo "  Cluster: $(oc whoami --show-server)"
echo "  User:    $(oc whoami)"
echo "==========================================="

# Check image is set
if grep -q "YOUR_ORG" "$DEPLOY_DIR/deployment.yaml"; then
    echo ""
    echo "ERROR: Update the image in deploy/deployment.yaml first."
    echo "  Replace 'quay.io/YOUR_ORG/capa-automation:latest' with your actual image."
    echo ""
    echo "  To push the image:"
    echo "    podman tag capa-automation quay.io/your-org/capa-automation:latest"
    echo "    podman push quay.io/your-org/capa-automation:latest"
    exit 1
fi

# Apply in order
oc apply -f "$DEPLOY_DIR/namespace.yaml"
oc apply -f "$DEPLOY_DIR/serviceaccount.yaml"
oc apply -f "$DEPLOY_DIR/rbac.yaml"
oc apply -f "$DEPLOY_DIR/secret.yaml"
oc apply -f "$DEPLOY_DIR/pvc.yaml"
oc apply -f "$DEPLOY_DIR/deployment.yaml"
oc apply -f "$DEPLOY_DIR/service.yaml"
oc apply -f "$DEPLOY_DIR/route.yaml"

echo ""
echo "Waiting for rollout..."
oc rollout status deployment/capa-automation -n capa-automation --timeout=120s

ROUTE=$(oc get route capa-automation -n capa-automation -o jsonpath='{.spec.host}')
echo ""
echo "==========================================="
echo "  CAPA Automation deployed!"
echo "  URL: https://$ROUTE"
echo "==========================================="
