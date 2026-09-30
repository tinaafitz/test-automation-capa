#!/bin/bash
set -e

# Delete ROSA HCP Clusters Skill
# Properly deletes clusters in correct order with appropriate timeouts

REPO_PATH=$(git -C /Users/tinafitzgerald/acm_dev/ai_dev/test-automation-capa rev-parse --show-toplevel 2>/dev/null || echo /Users/tinafitzgerald/acm_dev/ai_dev/test-automation-capa)
cd "$REPO_PATH"

# Parse arguments
CLUSTER_PREFIXES="${1:-}"
NAMESPACE="${NAMESPACE:-ns-rosa-hcp}"
WAIT_FOR_DELETION="${WAIT_FOR_DELETION:-true}"
FORCE_CLEANUP="${FORCE_CLEANUP:-true}"
VERBOSE="${VERBOSE:-false}"

if [ -z "$CLUSTER_PREFIXES" ]; then
  echo "❌ Error: No cluster prefix provided"
  echo "Usage: delete-clusters we5 [we4] [we2] [we1]"
  exit 1
fi

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                                                            ║"
echo "║  🗑️  ROSA HCP Cluster Deletion                            ║"
echo "║                                                            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "Clusters to delete:"
for prefix in $CLUSTER_PREFIXES; do
  echo "  • $prefix-rosa-hcp"
done
echo ""
echo "Namespace: $NAMESPACE"
echo "Wait for completion: $WAIT_FOR_DELETION"
echo "Force cleanup enabled: $FORCE_CLEANUP"
echo ""

# Build Ansible options
ANSIBLE_OPTS="-e capi_namespace=$NAMESPACE"
ANSIBLE_OPTS="$ANSIBLE_OPTS -e wait_for_deletion=$WAIT_FOR_DELETION"
ANSIBLE_OPTS="$ANSIBLE_OPTS -e force_cleanup_enabled=$FORCE_CLEANUP"

if [ "$VERBOSE" = "true" ]; then
  ANSIBLE_OPTS="$ANSIBLE_OPTS -vv"
fi

# Delete each cluster in sequence
TOTAL=0
SUCCESS=0
FAILED=0

for prefix in $CLUSTER_PREFIXES; do
  TOTAL=$((TOTAL + 1))
  CLUSTER_NAME="$prefix-rosa-hcp"

  echo ""
  echo "═══════════════════════════════════════════════════════════"
  echo "[$TOTAL] Deleting $CLUSTER_NAME..."
  echo "═══════════════════════════════════════════════════════════"
  echo ""

  if ansible-playbook playbooks/delete_rosa_hcp_cluster.yml \
    -e "name_prefix=$prefix" $ANSIBLE_OPTS 2>&1 | tee /tmp/delete_${prefix}_rosa_hcp.log; then
    SUCCESS=$((SUCCESS + 1))
    echo "✅ Deletion initiated for $CLUSTER_NAME"
  else
    FAILED=$((FAILED + 1))
    echo "⚠️  Deletion failed or timed out for $CLUSTER_NAME"
    echo "Check logs: /tmp/delete_${prefix}_rosa_hcp.log"
  fi

  # Small delay between deletions
  if [ $TOTAL -lt $(echo $CLUSTER_PREFIXES | wc -w) ]; then
    echo ""
    echo "Waiting 30 seconds before next deletion..."
    sleep 30
  fi
done

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                                                            ║"
echo "║  🗑️  DELETION COMPLETE                                    ║"
echo "║                                                            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "Summary:"
echo "  ✅ Successful: $SUCCESS/$TOTAL"
if [ $FAILED -gt 0 ]; then
  echo "  ⚠️  Failed/Timed out: $FAILED/$TOTAL"
fi
echo ""
echo "Verify deletion status:"
for prefix in $CLUSTER_PREFIXES; do
  echo "  oc get rosacontrolplane,rosanetwork,rosaroleconfig -n $NAMESPACE | grep $prefix"
done
echo ""
echo "Check OCM status:"
echo "  ocm list clusters | grep '$(echo $CLUSTER_PREFIXES | awk '{print $1}')-rosa-hcp'"
echo ""

if [ $FAILED -eq 0 ]; then
  exit 0
else
  exit 1
fi
