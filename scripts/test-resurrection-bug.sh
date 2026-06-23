#!/bin/bash

set -euo pipefail

CLUSTER_PREFIX="${1:-}"
NAMESPACE="${2:-ns-rosa-hcp}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
PRE_DELETE_SNAPSHOT="/tmp/pre-delete-snapshot.json"
DELETION_LOG="/tmp/deletion-tracking-${TIMESTAMP}.log"
RESURRECTION_LOG="/tmp/resurrection-detection-${TIMESTAMP}.log"

if [[ -z "$CLUSTER_PREFIX" ]]; then
    echo "Usage: $0 <cluster-prefix> [namespace]"
    echo "Example: $0 goo ns-rosa-hcp"
    exit 1
fi

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$DELETION_LOG"
}

resurrection_log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$RESURRECTION_LOG"
}

capture_cr_state() {
    local output_file="$1"
    local prefix_filter="${2:-}"
    
    echo "Capturing CR state to $output_file..."
    
    local crd_types="clusters.cluster.x-k8s.io rosacontrolplanes.infrastructure.cluster.x-k8s.io rosaclusters.infrastructure.cluster.x-k8s.io rosanetworks.infrastructure.cluster.x-k8s.io rosaroleconfigs.infrastructure.cluster.x-k8s.io rosamachinepools.infrastructure.cluster.x-k8s.io machinepools.cluster.x-k8s.io"
    
    local all_crs=()
    
    for crd in $crd_types; do
        local crs
        if [[ -n "$prefix_filter" ]]; then
            crs=$(oc get "$crd" -n "$NAMESPACE" -o name 2>/dev/null | grep -E "/${prefix_filter}-" || true)
        else
            crs=$(oc get "$crd" -n "$NAMESPACE" -o name 2>/dev/null || true)
        fi
        
        for cr in $crs; do
            all_crs+=("$cr")
        done
    done
    
    {
        echo "{"
        echo "  \"timestamp\": \"$(date -Iseconds)\","
        echo "  \"namespace\": \"$NAMESPACE\","
        echo "  \"prefix_filter\": \"$prefix_filter\","
        echo "  \"resources\": ["
        
        local first=true
        for cr in "${all_crs[@]}"; do
            if [[ "$first" == "true" ]]; then
                first=false
            else
                echo ","
            fi
            
            local cr_data
            cr_data=$(oc get "$cr" -n "$NAMESPACE" -o json 2>/dev/null || echo '{}')
            
            echo -n "    {"
            echo -n "\"name\": \"$(echo "$cr_data" | jq -r '.metadata.name // "unknown"')\","
            echo -n "\"kind\": \"$(echo "$cr_data" | jq -r '.kind // "unknown"')\","
            echo -n "\"resourceVersion\": \"$(echo "$cr_data" | jq -r '.metadata.resourceVersion // "unknown"')\","
            echo -n "\"finalizers\": $(echo "$cr_data" | jq -c '.metadata.finalizers // []'),"
            echo -n "\"deletionTimestamp\": \"$(echo "$cr_data" | jq -r '.metadata.deletionTimestamp // null')\","
            echo -n "\"phase\": \"$(echo "$cr_data" | jq -r '.status.phase // null')\""
            echo -n "    }"
        done
        
        echo ""
        echo "  ]"
        echo "}"
    } > "$output_file"
}

get_capa_controller_pod_start_time() {
    oc get pods -n openshift-cluster-api -l app=cluster-api-provider-aws-controller -o jsonpath='{.items[0].status.startTime}' 2>/dev/null || echo "unknown"
}

check_aws_resources_exist() {
    local prefix="$1"
    local found=false
    
    resurrection_log "Checking AWS resources for prefix: $prefix"
    
    local stacks
    stacks=$(aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE --query "StackSummaries[?contains(StackName, '$prefix')].StackName" --output text 2>/dev/null || true)
    if [[ -n "$stacks" ]]; then
        resurrection_log "ALERT: Found CloudFormation stacks with prefix $prefix: $stacks"
        found=true
    fi
    
    local roles
    roles=$(aws iam list-roles --query "Roles[?contains(RoleName, '$prefix')].RoleName" --output text 2>/dev/null || true)
    if [[ -n "$roles" ]]; then
        resurrection_log "ALERT: Found IAM roles with prefix $prefix: $roles"
        found=true
    fi
    
    if [[ "$found" == "true" ]]; then
        resurrection_log "RESURRECTION DETECTED: AWS resources with old prefix $prefix still exist!"
        return 0
    else
        resurrection_log "No AWS resources found with prefix $prefix"
        return 1
    fi
}

echo "========================================"
echo "CAPA Cluster Resurrection Bug Test"
echo "========================================"
echo "Cluster prefix: $CLUSTER_PREFIX"
echo "Namespace: $NAMESPACE"
echo "Logs will be written to:"
echo "  - Deletion tracking: $DELETION_LOG"
echo "  - Resurrection detection: $RESURRECTION_LOG"
echo ""

echo "========================================"
echo "PHASE 1: PRE-DELETE SNAPSHOT"
echo "========================================"

capture_cr_state "$PRE_DELETE_SNAPSHOT" "$CLUSTER_PREFIX"
log "Pre-delete snapshot captured to $PRE_DELETE_SNAPSHOT"

initial_controller_start_time=$(get_capa_controller_pod_start_time)
log "Initial CAPA controller start time: $initial_controller_start_time"

echo ""
echo "Now trigger the deletion of cluster with prefix '$CLUSTER_PREFIX'"
echo "Press ENTER when deletion has been triggered..."
read -r

echo ""
echo "========================================"
echo "PHASE 2: POST-DELETE MONITORING"
echo "========================================"

log "Starting deletion monitoring for prefix: $CLUSTER_PREFIX"

deletion_complete=false
while [[ "$deletion_complete" == "false" ]]; do
    current_crs=$(oc get clusters.cluster.x-k8s.io,rosacontrolplanes.infrastructure.cluster.x-k8s.io,rosaclusters.infrastructure.cluster.x-k8s.io,rosanetworks.infrastructure.cluster.x-k8s.io,rosaroleconfigs.infrastructure.cluster.x-k8s.io,rosamachinepools.infrastructure.cluster.x-k8s.io,machinepools.cluster.x-k8s.io -n "$NAMESPACE" -o name 2>/dev/null | grep -E "/${CLUSTER_PREFIX}-" || true)
    
    if [[ -z "$current_crs" ]]; then
        log "All CRs with prefix $CLUSTER_PREFIX have been deleted"
        deletion_complete=true
    else
        log "Remaining CRs with prefix $CLUSTER_PREFIX:"
        for cr in $current_crs; do
            cr_info=$(oc get "$cr" -n "$NAMESPACE" -o jsonpath='{.metadata.name} finalizers={.metadata.finalizers} deletionTimestamp={.metadata.deletionTimestamp}' 2>/dev/null || echo "CR not found")
            log "  $cr: $cr_info"
        done
    fi
    
    if [[ "$deletion_complete" == "false" ]]; then
        sleep 10
    fi
done

echo ""
echo "========================================"
echo "PHASE 3: CONTROLLER RESTART DETECTION"
echo "========================================"

log "Monitoring for CAPA controller restart..."

controller_restarted=false
while [[ "$controller_restarted" == "false" ]]; do
    current_controller_start_time=$(get_capa_controller_pod_start_time)
    
    if [[ "$current_controller_start_time" != "$initial_controller_start_time" ]]; then
        log "CAPA controller restart detected!"
        log "  Initial start time: $initial_controller_start_time"
        log "  Current start time: $current_controller_start_time"
        controller_restarted=true
        
        sleep 5
        
        log "Post-restart CR dump:"
        capture_cr_state "/tmp/post-restart-snapshot-${TIMESTAMP}.json"
        
        post_restart_crs=$(oc get clusters.cluster.x-k8s.io,rosacontrolplanes.infrastructure.cluster.x-k8s.io,rosaclusters.infrastructure.cluster.x-k8s.io,rosanetworks.infrastructure.cluster.x-k8s.io,rosaroleconfigs.infrastructure.cluster.x-k8s.io,rosamachinepools.infrastructure.cluster.x-k8s.io,machinepools.cluster.x-k8s.io -n "$NAMESPACE" -o name 2>/dev/null | grep -E "/${CLUSTER_PREFIX}-" || true)
        
        if [[ -n "$post_restart_crs" ]]; then
            resurrection_log "RESURRECTION ALERT: CRs with old prefix $CLUSTER_PREFIX reappeared after controller restart!"
            for cr in $post_restart_crs; do
                resurrection_log "  Resurrected CR: $cr"
            done
        else
            log "No resurrection detected in Kubernetes CRs after controller restart"
        fi
    else
        echo -n "."
        sleep 30
    fi
done

echo ""
echo "Controller restart phase complete. You can now provision a new cluster."
echo "Press ENTER when new cluster provisioning has started..."
read -r

echo ""
echo "========================================"
echo "PHASE 4: RESURRECTION DETECTION"
echo "========================================"

resurrection_log "Starting resurrection detection phase"

echo "Monitoring for 5 minutes for any signs of resurrection..."

end_time=$(($(date +%s) + 300))
while [[ $(date +%s) -lt $end_time ]]; do
    k8s_resurrection_crs=$(oc get clusters.cluster.x-k8s.io,rosacontrolplanes.infrastructure.cluster.x-k8s.io,rosaclusters.infrastructure.cluster.x-k8s.io,rosanetworks.infrastructure.cluster.x-k8s.io,rosaroleconfigs.infrastructure.cluster.x-k8s.io,rosamachinepools.infrastructure.cluster.x-k8s.io,machinepools.cluster.x-k8s.io -n "$NAMESPACE" -o name 2>/dev/null | grep -E "/${CLUSTER_PREFIX}-" || true)
    
    if [[ -n "$k8s_resurrection_crs" ]]; then
        resurrection_log "RESURRECTION DETECTED: CRs with old prefix $CLUSTER_PREFIX found during new cluster provisioning!"
        for cr in $k8s_resurrection_crs; do
            resurrection_log "  Resurrected CR: $cr"
        done
    fi
    
    if check_aws_resources_exist "$CLUSTER_PREFIX"; then
        resurrection_log "AWS-level resurrection detected!"
    fi
    
    sleep 30
done

echo ""
echo "========================================"
echo "MONITORING COMPLETE"
echo "========================================"
echo "Deletion tracking log: $DELETION_LOG"
echo "Resurrection detection log: $RESURRECTION_LOG"
echo "Pre-delete snapshot: $PRE_DELETE_SNAPSHOT"
echo "Post-restart snapshot: /tmp/post-restart-snapshot-${TIMESTAMP}.json"
echo ""

if [[ -f "$RESURRECTION_LOG" && -s "$RESURRECTION_LOG" ]]; then
    echo "RESURRECTION ALERTS DETECTED - Check $RESURRECTION_LOG for details"
    echo "Last few resurrection log entries:"
    tail -10 "$RESURRECTION_LOG"
else
    echo "No resurrection detected during monitoring period"
fi