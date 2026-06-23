#!/bin/bash

set -e

RESOURCE_TYPES=(
    "rosacontrolplane"
    "rosanetwork" 
    "rosaroleconfig"
    "cluster.cluster.x-k8s.io"
    "rosamachinepool"
)

STUCK_CRS=()
ACTIVE_CRS=()
TOTAL_CRS=0

echo "=== CAPA Finalizer Audit ==="
echo "Timestamp: $(date)"
echo

for resource_type in "${RESOURCE_TYPES[@]}"; do
    echo "Checking $resource_type..."
    
    crs=$(oc get $resource_type --all-namespaces -o json 2>/dev/null | jq -r '.items[] | @base64' 2>/dev/null || echo "")
    
    if [ -z "$crs" ]; then
        echo "  No $resource_type found"
        continue
    fi
    
    while read -r cr_data; do
        if [ -z "$cr_data" ]; then
            continue
        fi
        
        cr=$(echo "$cr_data" | base64 --decode)
        
        namespace=$(echo "$cr" | jq -r '.metadata.namespace // "default"')
        name=$(echo "$cr" | jq -r '.metadata.name')
        creation_timestamp=$(echo "$cr" | jq -r '.metadata.creationTimestamp')
        deletion_timestamp=$(echo "$cr" | jq -r '.metadata.deletionTimestamp // empty')
        finalizers=$(echo "$cr" | jq -r '.metadata.finalizers[]? // empty' | tr '\n' ',' | sed 's/,$//')
        
        if [ -z "$finalizers" ]; then
            finalizers="none"
        fi
        
        age=$(python3 -c "
from datetime import datetime, timezone
import sys
try:
    created = datetime.fromisoformat('$creation_timestamp'.replace('Z', '+00:00'))
    now = datetime.now(timezone.utc)
    delta = now - created
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    if days > 0:
        print(f'{days}d{hours}h{minutes}m')
    elif hours > 0:
        print(f'{hours}h{minutes}m')
    else:
        print(f'{minutes}m')
except:
    print('unknown')
")
        
        TOTAL_CRS=$((TOTAL_CRS + 1))
        
        if [ -n "$deletion_timestamp" ]; then
            minutes_since_deletion=$(python3 -c "
from datetime import datetime, timezone
import sys
try:
    deleted = datetime.fromisoformat('$deletion_timestamp'.replace('Z', '+00:00'))
    now = datetime.now(timezone.utc)
    delta = now - deleted
    print(int(delta.total_seconds() / 60))
except:
    print('0')
")
            
            if [ "$minutes_since_deletion" -gt 10 ]; then
                status="STUCK"
                STUCK_CRS+=("$resource_type/$namespace/$name")
            else
                status="DELETING"
            fi
            
            echo "  $status: $namespace/$name (age: $age, deleting for ${minutes_since_deletion}m)"
            echo "    Finalizers: $finalizers"
            
        elif [ "$finalizers" != "none" ]; then
            status="ACTIVE WITH FINALIZERS"
            ACTIVE_CRS+=("$resource_type/$namespace/$name")
            echo "  $status: $namespace/$name (age: $age)"
            echo "    Finalizers: $finalizers"
        fi
        
    done <<< "$crs"
    echo
done

echo "=== SUMMARY ==="
echo "Total CRs found: $TOTAL_CRS"
echo "Stuck CRs (deleting >10m): ${#STUCK_CRS[@]}"
echo "Active CRs with finalizers: ${#ACTIVE_CRS[@]}"
echo

if [ ${#STUCK_CRS[@]} -gt 0 ]; then
    echo "=== STUCK CRs DETECTED ==="
    echo "The following CRs appear to be stuck in deletion:"
    for stuck_cr in "${STUCK_CRS[@]}"; do
        IFS='/' read -r resource_type namespace name <<< "$stuck_cr"
        echo "  $namespace/$name ($resource_type)"
    done
    echo
    echo "To force removal of finalizers (USE WITH CAUTION):"
    for stuck_cr in "${STUCK_CRS[@]}"; do
        IFS='/' read -r resource_type namespace name <<< "$stuck_cr"
        echo "oc patch $resource_type $name -n $namespace --type=merge -p '{\"metadata\":{\"finalizers\":[]}}'"
    done
fi