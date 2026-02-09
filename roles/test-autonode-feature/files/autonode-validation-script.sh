#!/bin/bash
#
# AutoNode Validation Script
# Validates AutoNode (Karpenter) installation and configuration
#
# Usage: ./autonode-validation-script.sh <cluster_name> [kubeconfig_path]
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
CHECKS_PASSED=0
CHECKS_FAILED=0
CHECKS_WARNING=0

# Parse arguments
CLUSTER_NAME="${1:-}"
KUBECONFIG_PATH="${2:-$HOME/.kube/config}"

if [ -z "$CLUSTER_NAME" ]; then
    echo -e "${RED}Error: Cluster name is required${NC}"
    echo "Usage: $0 <cluster_name> [kubeconfig_path]"
    exit 1
fi

# Export kubeconfig
export KUBECONFIG="$KUBECONFIG_PATH"

echo "========================================"
echo "AutoNode Validation"
echo "========================================"
echo "Cluster: $CLUSTER_NAME"
echo "Kubeconfig: $KUBECONFIG_PATH"
echo "========================================"
echo ""

# Helper functions
check_pass() {
    echo -e "${GREEN}${NC} $1"
    ((CHECKS_PASSED++))
}

check_fail() {
    echo -e "${RED}${NC} $1"
    ((CHECKS_FAILED++))
}

check_warn() {
    echo -e "${YELLOW} ${NC} $1"
    ((CHECKS_WARNING++))
}

# Check 1: Verify CLI tools
echo -e "${BLUE}[1/10] Checking CLI tools...${NC}"
for tool in kubectl oc aws rosa jq; do
    if command -v $tool &> /dev/null; then
        check_pass "$tool is installed"
    else
        check_fail "$tool is not installed"
    fi
done
echo ""

# Check 2: Verify cluster access
echo -e "${BLUE}[2/10] Checking cluster access...${NC}"
if kubectl cluster-info &> /dev/null; then
    check_pass "Cluster is accessible"
    CLUSTER_VERSION=$(kubectl version --short 2>/dev/null | grep Server || echo "Unknown")
    echo "  Cluster version: $CLUSTER_VERSION"
else
    check_fail "Cannot access cluster"
fi
echo ""

# Check 3: Verify RosaControlPlane
echo -e "${BLUE}[3/10] Checking RosaControlPlane...${NC}"
if oc get rosacontrolplane "$CLUSTER_NAME" &> /dev/null; then
    check_pass "RosaControlPlane exists"

    # Check if autoNode is configured
    if oc get rosacontrolplane "$CLUSTER_NAME" -o yaml | grep -q "autoNode:"; then
        check_pass "AutoNode is configured in RosaControlPlane"

        # Get autoNode mode
        AUTONODE_MODE=$(oc get rosacontrolplane "$CLUSTER_NAME" -o jsonpath='{.spec.autoNode.mode}')
        echo "  AutoNode mode: $AUTONODE_MODE"

        # Get IAM role ARN
        ROLE_ARN=$(oc get rosacontrolplane "$CLUSTER_NAME" -o jsonpath='{.spec.autoNode.roleARN}')
        echo "  IAM Role ARN: $ROLE_ARN"
    else
        check_fail "AutoNode is not configured in RosaControlPlane"
    fi
else
    check_fail "RosaControlPlane not found"
fi
echo ""

# Check 4: Verify Karpenter pods
echo -e "${BLUE}[4/10] Checking Karpenter pods...${NC}"
KARPENTER_PODS=$(kubectl get pods -n kube-system -l app.kubernetes.io/name=karpenter --no-headers 2>/dev/null | wc -l)
if [ "$KARPENTER_PODS" -gt 0 ]; then
    check_pass "Found $KARPENTER_PODS Karpenter pod(s)"

    # Check pod status
    RUNNING_PODS=$(kubectl get pods -n kube-system -l app.kubernetes.io/name=karpenter --no-headers 2>/dev/null | grep -c "Running" || echo "0")
    if [ "$RUNNING_PODS" -eq "$KARPENTER_PODS" ]; then
        check_pass "All Karpenter pods are running"
    else
        check_fail "Not all Karpenter pods are running ($RUNNING_PODS/$KARPENTER_PODS)"
    fi

    # Show pod details
    kubectl get pods -n kube-system -l app.kubernetes.io/name=karpenter
else
    check_fail "No Karpenter pods found"
fi
echo ""

# Check 5: Verify NodePools
echo -e "${BLUE}[5/10] Checking NodePools...${NC}"
NODEPOOLS=$(kubectl get nodepools --no-headers 2>/dev/null | wc -l)
if [ "$NODEPOOLS" -gt 0 ]; then
    check_pass "Found $NODEPOOLS NodePool(s)"
    kubectl get nodepools
else
    check_warn "No NodePools found"
fi
echo ""

# Check 6: Verify EC2NodeClass
echo -e "${BLUE}[6/10] Checking EC2NodeClass...${NC}"
EC2NODECLASSES=$(kubectl get ec2nodeclass --no-headers 2>/dev/null | wc -l)
if [ "$EC2NODECLASSES" -gt 0 ]; then
    check_pass "Found $EC2NODECLASSES EC2NodeClass(es)"
    kubectl get ec2nodeclass

    # Check ready status
    for nodeclass in $(kubectl get ec2nodeclass -o name 2>/dev/null); do
        READY=$(kubectl get "$nodeclass" -o jsonpath='{.status.ready}' 2>/dev/null || echo "false")
        NODECLASS_NAME=$(echo "$nodeclass" | cut -d'/' -f2)
        if [ "$READY" == "true" ]; then
            check_pass "EC2NodeClass $NODECLASS_NAME is ready"
        else
            check_warn "EC2NodeClass $NODECLASS_NAME is not ready"
        fi
    done
else
    check_warn "No EC2NodeClass found"
fi
echo ""

# Check 7: Verify Karpenter-provisioned nodes
echo -e "${BLUE}[7/10] Checking Karpenter-provisioned nodes...${NC}"
KARPENTER_NODES=$(kubectl get nodes -l karpenter.sh/nodepool --no-headers 2>/dev/null | wc -l)
if [ "$KARPENTER_NODES" -gt 0 ]; then
    check_pass "Found $KARPENTER_NODES Karpenter-provisioned node(s)"
    kubectl get nodes -l karpenter.sh/nodepool -o wide
else
    check_warn "No Karpenter-provisioned nodes found (this is OK if no workloads require scaling)"
fi
echo ""

# Check 8: Check Karpenter logs for errors
echo -e "${BLUE}[8/10] Checking Karpenter logs for errors...${NC}"
ERROR_COUNT=$(kubectl logs -n kube-system -l app.kubernetes.io/name=karpenter --tail=100 2>/dev/null | grep -i "error" | wc -l || echo "0")
if [ "$ERROR_COUNT" -eq 0 ]; then
    check_pass "No recent errors in Karpenter logs"
else
    check_warn "Found $ERROR_COUNT error line(s) in Karpenter logs (last 100 lines)"
    echo "  Recent errors:"
    kubectl logs -n kube-system -l app.kubernetes.io/name=karpenter --tail=100 2>/dev/null | grep -i "error" | tail -5 | sed 's/^/    /'
fi
echo ""

# Check 9: Verify AWS IAM role
echo -e "${BLUE}[9/10] Checking AWS IAM role...${NC}"
if [ -n "${ROLE_ARN:-}" ]; then
    ROLE_NAME=$(echo "$ROLE_ARN" | awk -F'/' '{print $NF}')
    if aws iam get-role --role-name "$ROLE_NAME" &> /dev/null; then
        check_pass "IAM role exists: $ROLE_NAME"

        # Check attached policies
        POLICY_COUNT=$(aws iam list-attached-role-policies --role-name "$ROLE_NAME" --query 'AttachedPolicies | length(@)' --output text 2>/dev/null || echo "0")
        if [ "$POLICY_COUNT" -gt 0 ]; then
            check_pass "IAM role has $POLICY_COUNT attached policy/policies"
        else
            check_warn "IAM role has no attached policies"
        fi
    else
        check_fail "IAM role not found: $ROLE_NAME"
    fi
else
    check_warn "IAM role ARN not available for verification"
fi
echo ""

# Check 10: Verify AWS resource tags
echo -e "${BLUE}[10/10] Checking AWS resource tags...${NC}"
CLUSTER_ID=$(oc get rosacontrolplane "$CLUSTER_NAME" -o jsonpath='{.status.id}' 2>/dev/null || echo "")
if [ -n "$CLUSTER_ID" ]; then
    echo "  Cluster ID: $CLUSTER_ID"

    # Check security groups
    SG_COUNT=$(aws ec2 describe-security-groups --filters "Name=tag:karpenter.sh/discovery,Values=$CLUSTER_ID" --query 'SecurityGroups | length(@)' --output text 2>/dev/null || echo "0")
    if [ "$SG_COUNT" -gt 0 ]; then
        check_pass "Found $SG_COUNT security group(s) tagged for Karpenter discovery"
    else
        check_fail "No security groups tagged with karpenter.sh/discovery=$CLUSTER_ID"
    fi

    # Check subnets
    SUBNET_COUNT=$(aws ec2 describe-subnets --filters "Name=tag:karpenter.sh/discovery,Values=$CLUSTER_ID" --query 'Subnets | length(@)' --output text 2>/dev/null || echo "0")
    if [ "$SUBNET_COUNT" -gt 0 ]; then
        check_pass "Found $SUBNET_COUNT subnet(s) tagged for Karpenter discovery"
    else
        check_fail "No subnets tagged with karpenter.sh/discovery=$CLUSTER_ID"
    fi
else
    check_warn "Cluster ID not available for AWS resource verification"
fi
echo ""

# Summary
echo "========================================"
echo "Validation Summary"
echo "========================================"
echo -e "Passed:   ${GREEN}$CHECKS_PASSED${NC}"
echo -e "Failed:   ${RED}$CHECKS_FAILED${NC}"
echo -e "Warnings: ${YELLOW}$CHECKS_WARNING${NC}"
echo "========================================"

# Exit code
if [ "$CHECKS_FAILED" -gt 0 ]; then
    echo -e "${RED}Validation completed with failures${NC}"
    exit 1
elif [ "$CHECKS_WARNING" -gt 0 ]; then
    echo -e "${YELLOW}Validation completed with warnings${NC}"
    exit 0
else
    echo -e "${GREEN}All validation checks passed!${NC}"
    exit 0
fi
