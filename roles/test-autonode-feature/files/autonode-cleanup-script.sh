#!/bin/bash
#
# AutoNode Cleanup Script
# Cleans up AutoNode (Karpenter) resources from a ROSA HCP cluster
#
# Usage: ./autonode-cleanup-script.sh <cluster_name> [options]
#
# Options:
#   --delete-iam         Delete IAM resources (role and policy)
#   --keep-iam           Keep IAM resources (default)
#   --kubeconfig PATH    Path to kubeconfig file
#   --dry-run            Show what would be deleted without deleting
#   --force              Skip confirmation prompts
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default options
CLUSTER_NAME=""
DELETE_IAM=false
DRY_RUN=false
FORCE=false
KUBECONFIG_PATH="${KUBECONFIG:-$HOME/.kube/config}"
CLUSTER_NAMESPACE="clusters"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --delete-iam)
            DELETE_IAM=true
            shift
            ;;
        --keep-iam)
            DELETE_IAM=false
            shift
            ;;
        --kubeconfig)
            KUBECONFIG_PATH="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 <cluster_name> [options]"
            echo ""
            echo "Options:"
            echo "  --delete-iam         Delete IAM resources (role and policy)"
            echo "  --keep-iam           Keep IAM resources (default)"
            echo "  --kubeconfig PATH    Path to kubeconfig file"
            echo "  --dry-run            Show what would be deleted without deleting"
            echo "  --force              Skip confirmation prompts"
            echo "  -h, --help           Show this help message"
            exit 0
            ;;
        *)
            if [ -z "$CLUSTER_NAME" ]; then
                CLUSTER_NAME="$1"
            else
                echo -e "${RED}Error: Unknown argument: $1${NC}"
                exit 1
            fi
            shift
            ;;
    esac
done

if [ -z "$CLUSTER_NAME" ]; then
    echo -e "${RED}Error: Cluster name is required${NC}"
    echo "Usage: $0 <cluster_name> [options]"
    exit 1
fi

# Export kubeconfig
export KUBECONFIG="$KUBECONFIG_PATH"

echo "========================================"
echo "AutoNode Cleanup"
echo "========================================"
echo "Cluster: $CLUSTER_NAME"
echo "Kubeconfig: $KUBECONFIG_PATH"
echo "Delete IAM: $DELETE_IAM"
echo "Dry Run: $DRY_RUN"
echo "========================================"
echo ""

# Confirmation prompt
if [ "$FORCE" != "true" ] && [ "$DRY_RUN" != "true" ]; then
    echo -e "${YELLOW}WARNING: This will delete AutoNode resources from cluster $CLUSTER_NAME${NC}"
    if [ "$DELETE_IAM" == "true" ]; then
        echo -e "${YELLOW}This includes IAM roles and policies!${NC}"
    fi
    echo ""
    read -p "Are you sure you want to continue? (yes/no): " -r
    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        echo "Cleanup cancelled"
        exit 0
    fi
    echo ""
fi

# Helper function to execute or simulate
execute() {
    if [ "$DRY_RUN" == "true" ]; then
        echo -e "${BLUE}[DRY-RUN]${NC} $*"
    else
        echo -e "${GREEN}[EXEC]${NC} $*"
        eval "$@" || echo -e "${YELLOW}  Command failed (continuing...)${NC}"
    fi
}

# Step 1: Delete test deployments
echo -e "${BLUE}[1/6] Cleaning up test deployments...${NC}"
if kubectl --kubeconfig="$KUBECONFIG_PATH" get deployment autonode-scale-test &> /dev/null; then
    execute "kubectl --kubeconfig='$KUBECONFIG_PATH' delete deployment autonode-scale-test --ignore-not-found=true"
else
    echo "  No test deployment found"
fi
echo ""

# Step 2: Delete NodePools
echo -e "${BLUE}[2/6] Deleting NodePools...${NC}"
NODEPOOLS=$(kubectl --kubeconfig="$KUBECONFIG_PATH" get nodepools --no-headers -o custom-columns=":metadata.name" 2>/dev/null || echo "")
if [ -n "$NODEPOOLS" ]; then
    for nodepool in $NODEPOOLS; do
        echo "  Deleting NodePool: $nodepool"
        execute "kubectl --kubeconfig='$KUBECONFIG_PATH' delete nodepool '$nodepool' --ignore-not-found=true"
    done

    # Wait for nodes to be drained (only if not dry-run)
    if [ "$DRY_RUN" != "true" ]; then
        echo "  Waiting for Karpenter nodes to be removed..."
        sleep 10
        KARPENTER_NODES=$(kubectl --kubeconfig="$KUBECONFIG_PATH" get nodes -l karpenter.sh/nodepool --no-headers 2>/dev/null | wc -l || echo "0")
        if [ "$KARPENTER_NODES" -gt 0 ]; then
            echo -e "${YELLOW}  Warning: $KARPENTER_NODES Karpenter node(s) still present${NC}"
        else
            echo -e "${GREEN}  All Karpenter nodes removed${NC}"
        fi
    fi
else
    echo "  No NodePools found"
fi
echo ""

# Step 3: Delete EC2NodeClass
echo -e "${BLUE}[3/6] Deleting EC2NodeClass...${NC}"
EC2NODECLASSES=$(kubectl --kubeconfig="$KUBECONFIG_PATH" get ec2nodeclass --no-headers -o custom-columns=":metadata.name" 2>/dev/null || echo "")
if [ -n "$EC2NODECLASSES" ]; then
    for nodeclass in $EC2NODECLASSES; do
        echo "  Deleting EC2NodeClass: $nodeclass"
        execute "kubectl --kubeconfig='$KUBECONFIG_PATH' delete ec2nodeclass '$nodeclass' --ignore-not-found=true"
    done
else
    echo "  No EC2NodeClass found"
fi
echo ""

# Step 4: Remove autoNode from RosaControlPlane
echo -e "${BLUE}[4/6] Removing autoNode from RosaControlPlane...${NC}"
if oc get rosacontrolplane "$CLUSTER_NAME" -n "$CLUSTER_NAMESPACE" &> /dev/null; then
    if oc get rosacontrolplane "$CLUSTER_NAME" -n "$CLUSTER_NAMESPACE" -o yaml | grep -q "autoNode:"; then
        execute "oc patch rosacontrolplane '$CLUSTER_NAME' -n '$CLUSTER_NAMESPACE' --type json -p '[{\"op\": \"remove\", \"path\": \"/spec/autoNode\"}]'"
    else
        echo "  AutoNode configuration not found in RosaControlPlane"
    fi
else
    echo -e "${YELLOW}  Warning: RosaControlPlane not found${NC}"
fi
echo ""

# Step 5: Delete IAM resources
if [ "$DELETE_IAM" == "true" ]; then
    echo -e "${BLUE}[5/6] Deleting IAM resources...${NC}"

    # Get role ARN from RosaControlPlane (if it exists)
    ROLE_ARN=$(oc get rosacontrolplane "$CLUSTER_NAME" -n "$CLUSTER_NAMESPACE" -o jsonpath='{.spec.autoNode.roleARN}' 2>/dev/null || echo "")

    if [ -n "$ROLE_ARN" ]; then
        ROLE_NAME=$(echo "$ROLE_ARN" | awk -F'/' '{print $NF}')
        echo "  IAM Role: $ROLE_NAME"

        # Get attached policies
        POLICIES=$(aws iam list-attached-role-policies --role-name "$ROLE_NAME" --query 'AttachedPolicies[*].PolicyArn' --output text 2>/dev/null || echo "")

        # Detach policies
        if [ -n "$POLICIES" ]; then
            for policy_arn in $POLICIES; do
                echo "  Detaching policy: $policy_arn"
                execute "aws iam detach-role-policy --role-name '$ROLE_NAME' --policy-arn '$policy_arn'"
            done
        fi

        # Delete role
        echo "  Deleting IAM role: $ROLE_NAME"
        execute "aws iam delete-role --role-name '$ROLE_NAME'"

        # Delete custom policies (AutoNode policy)
        if [ -n "$POLICIES" ]; then
            for policy_arn in $POLICIES; do
                # Only delete customer-managed policies (not AWS managed)
                if [[ $policy_arn == *":policy/"* ]] && [[ $policy_arn != *"arn:aws:iam::aws:policy/"* ]]; then
                    # Check if policy is attached to other roles
                    ATTACHMENT_COUNT=$(aws iam list-entities-for-policy --policy-arn "$policy_arn" --query 'PolicyRoles | length(@)' --output text 2>/dev/null || echo "0")
                    if [ "$ATTACHMENT_COUNT" -eq 0 ]; then
                        echo "  Deleting IAM policy: $policy_arn"
                        execute "aws iam delete-policy --policy-arn '$policy_arn'"
                    else
                        echo -e "${YELLOW}  Skipping policy deletion (attached to $ATTACHMENT_COUNT other role(s)): $policy_arn${NC}"
                    fi
                fi
            done
        fi
    else
        echo "  No IAM role ARN found in cluster configuration"
        echo "  You may need to manually specify the role name to delete"
    fi
else
    echo -e "${BLUE}[5/6] Skipping IAM resource deletion${NC}"
    echo "  Use --delete-iam flag to delete IAM resources"
fi
echo ""

# Step 6: Clean up temporary files
echo -e "${BLUE}[6/6] Cleaning up temporary files...${NC}"
TMP_FILES=(
    "/tmp/AutoNodePolicy-*.json"
    "/tmp/*-trust-policy.json"
    "/tmp/*-ec2nodeclass.yaml"
    "/tmp/*-nodepool.yaml"
    "/tmp/autonode-scale-test-deployment.yaml"
    "/tmp/autonode-cluster-info-*.env"
)

for pattern in "${TMP_FILES[@]}"; do
    FILES=$(ls $pattern 2>/dev/null || echo "")
    if [ -n "$FILES" ]; then
        for file in $FILES; do
            echo "  Removing: $file"
            execute "rm -f '$file'"
        done
    fi
done
echo ""

# Summary
echo "========================================"
echo "Cleanup Summary"
echo "========================================"
if [ "$DRY_RUN" == "true" ]; then
    echo -e "${BLUE}DRY RUN - No resources were actually deleted${NC}"
else
    echo -e "${GREEN}Cleanup completed${NC}"
fi
echo ""
echo "Cleaned:"
echo "   Test deployments"
echo "   NodePools"
echo "   EC2NodeClass"
echo "   RosaControlPlane autoNode configuration"
if [ "$DELETE_IAM" == "true" ]; then
    echo "   IAM resources (role and policies)"
else
    echo "  Ë IAM resources (kept - use --delete-iam to remove)"
fi
echo "   Temporary files"
echo ""
echo "Note: The cluster itself has not been deleted."
echo "To delete the cluster, run: rosa delete cluster $CLUSTER_NAME"
echo "========================================"

if [ "$DRY_RUN" == "true" ]; then
    echo ""
    echo "To perform the actual cleanup, run without --dry-run flag"
fi
