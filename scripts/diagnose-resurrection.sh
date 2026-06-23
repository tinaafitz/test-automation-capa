#!/bin/bash

NAMESPACE=${1:-ns-rosa-hcp}
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUTPUT_FILE="/tmp/capa-cr-diagnosis-${TIMESTAMP}.json"

CR_TYPES=(
    "rosacontrolplane"
    "rosanetwork"
    "rosaroleconfig"
    "cluster"
    "rosamachinepool"
    "machinepool"
)

echo "Diagnosing CAPA CRs in namespace: $NAMESPACE"
echo "Output file: $OUTPUT_FILE"
echo ""

ALL_CRS=()
STUCK_DELETION=()
ACTIVE_CRS=()
HAS_FINALIZERS=()

for cr_type in "${CR_TYPES[@]}"; do
    crs=$(oc get $cr_type -n $NAMESPACE -o json 2>/dev/null)
    if [ $? -eq 0 ] && [ "$(echo "$crs" | jq '.items | length')" -gt 0 ]; then
        echo "$crs" | jq --arg type "$cr_type" '.items[] | {
            type: $type,
            name: .metadata.name,
            deletionTimestamp: .metadata.deletionTimestamp,
            finalizers: .metadata.finalizers,
            resourceVersion: .metadata.resourceVersion,
            conditions: .status.conditions
        }' >> "$OUTPUT_FILE"
        
        names=$(echo "$crs" | jq -r '.items[].metadata.name')
        for name in $names; do
            ALL_CRS+=("$cr_type/$name")
            
            deletion_ts=$(echo "$crs" | jq -r --arg name "$name" '.items[] | select(.metadata.name == $name) | .metadata.deletionTimestamp // empty')
            finalizers=$(echo "$crs" | jq -r --arg name "$name" '.items[] | select(.metadata.name == $name) | .metadata.finalizers // [] | length')
            
            if [ -n "$deletion_ts" ] && [ "$deletion_ts" != "null" ]; then
                STUCK_DELETION+=("$cr_type/$name")
            else
                ACTIVE_CRS+=("$cr_type/$name")
            fi
            
            if [ "$finalizers" -gt 0 ]; then
                HAS_FINALIZERS+=("$cr_type/$name")
            fi
        done
    fi
done

echo "=== DIAGNOSIS SUMMARY ==="
if [ ${#ALL_CRS[@]} -eq 0 ]; then
    echo "STATUS: CLEAN"
    echo "No CAPA CRs found in namespace $NAMESPACE"
elif [ ${#STUCK_DELETION[@]} -gt 0 ]; then
    echo "STATUS: STUCK DELETION"
    echo "CRs with deletionTimestamp:"
    printf '  %s\n' "${STUCK_DELETION[@]}"
else
    echo "STATUS: ACTIVE"
    echo "Active CRs (no deletionTimestamp):"
    printf '  %s\n' "${ACTIVE_CRS[@]}"
fi

if [ ${#HAS_FINALIZERS[@]} -gt 0 ]; then
    echo ""
    echo "CRs with finalizers:"
    printf '  %s\n' "${HAS_FINALIZERS[@]}"
fi

echo ""
echo "Full CR dump saved to: $OUTPUT_FILE"