# CAPA RosaRoleConfig Deletion Deadlock

## Summary

When a ROSA HCP cluster's OIDC provider is deleted from AWS before the Kubernetes resources are cleaned up, the CAPA controller enters an infinite reconcile loop. The ROSAControlPlane and RosaRoleConfig controllers block each other indefinitely with no self-recovery path.

## Observed Behavior

Three clusters (`que-mini-rosa-tst`, `inv-invalid-min-rosa`, `cha-mini-test`) stuck in `Provisioning` state for 8+ days on minikube. Each shows:

- **ROSAControlPlane condition**: `OIDC Provider not found: AssumeRoleWithWebIdentity ... InvalidIdentityToken: No OpenIDConnect provider found`
- **RosaRoleConfig condition**: `Failed to delete operator roles: operator Roles with Prefix 'xxx' are in use cannot be deleted`

The OIDC providers were deleted from AWS (likely during a previous cleanup) but the K8s resources and OCM clusters were left intact.

## Root Cause: Circular Dependency

```
ROSAControlPlane.reconcileNormal()
  -> reconcileRosaRoleConfig()                    [line 232, rosacontrolplane_controller.go]
    -> RosaRoleConfig not ready (DeletionFailed)  [line 392-399]
    -> return error -> controller-runtime requeues automatically

RosaRoleConfig.reconcileDelete()
  -> deleteOperatorRoles()                        [line 176, rosaroleconfig_controller.go]
    -> OCMClient.HasAClusterUsingOperatorRolesPrefix(prefix)  [line 388]
    -> returns true (OCM cluster still exists)
    -> return error "in use cannot be deleted"    [line 391]
    -> controller-runtime requeues automatically
```

Neither controller can make progress:
- ROSAControlPlane waits for RosaRoleConfig to be ready
- RosaRoleConfig can't delete operator roles because OCM cluster holds them
- OCM cluster won't be deleted until ROSAControlPlane is deleted
- ROSAControlPlane finalizer won't be removed until reconcile succeeds

## Affected Code

### `rosaroleconfig_controller.go` (exp/controllers/)

**`deleteOperatorRoles()` line 386-391** — Hard block with no override:
```go
if usedOperatorRoles, err := r.Runtime.OCMClient.HasAClusterUsingOperatorRolesPrefix(prefix); err != nil {
    return err
} else if usedOperatorRoles {
    return fmt.Errorf("operator Roles with Prefix '%s' are in use cannot be deleted", prefix)
}
```

**`deleteOIDC()` line 370-374** — Same pattern:
```go
if usedOidcProvider, err := r.Runtime.OCMClient.HasAClusterUsingOidcProvider(oidcEndpointURL, ...); err != nil {
    return err
} else if usedOidcProvider {
    return fmt.Errorf("clusters using OIDC provider '%s', cannot be deleted", oidcEndpointURL)
}
```

**`reconcileDelete()` line 175-191** — Sequential deletion with no fallthrough:
```go
func (r *ROSARoleConfigReconciler) reconcileDelete(scope *scope.RosaRoleConfigScope) error {
    if err := r.deleteOperatorRoles(scope); err != nil {  // fails here, never reaches OIDC or account roles
        return err
    }
    if err := r.deleteOIDC(scope); err != nil {
        return err
    }
    if err := r.deleteAccountRoles(scope); err != nil {
        return err
    }
    return nil
}
```

### `rosacontrolplane_controller.go` (controlplane/rosa/controllers/)

**`reconcileRosaRoleConfig()` line 392-399** — No bypass when RosaRoleConfig is stuck:
```go
if !v1beta1conditions.IsTrue(rosaRoleConfig, expinfrav1.RosaRoleConfigReadyCondition) {
    return nil, fmt.Errorf("RosaRoleConfig %s/%s is not ready", ...)
}
```

## Proposed Fixes

### Option A: Force-delete annotation on RosaRoleConfig (least invasive)

ROSAControlPlane already has `ROSAControlPlaneForceDeleteAnnotation` (line 452-455). Add the same pattern to RosaRoleConfig:

```go
// reconcileDelete
func (r *ROSARoleConfigReconciler) reconcileDelete(scope *scope.RosaRoleConfigScope) error {
    forceDelete := annotations.Has(scope.RosaRoleConfig,
        "rosa.infrastructure.cluster.x-k8s.io/force-delete")

    if err := r.deleteOperatorRoles(scope, forceDelete); err != nil { ... }
    if err := r.deleteOIDC(scope, forceDelete); err != nil { ... }
    if err := r.deleteAccountRoles(scope, forceDelete); err != nil { ... }
    return nil
}

// deleteOperatorRoles - skip "in use" check when force-deleting
func (r *ROSARoleConfigReconciler) deleteOperatorRoles(scope *scope.RosaRoleConfigScope, forceDelete bool) error {
    if !forceDelete {
        if usedOperatorRoles, err := r.Runtime.OCMClient.HasAClusterUsingOperatorRolesPrefix(prefix); ... {
            return fmt.Errorf(...)
        }
    }
    // proceed with deletion
}
```

**Pros**: Simple, consistent with existing pattern, opt-in
**Cons**: Requires manual annotation to escape the loop

### Option B: Self-referential cluster detection (smarter)

In `deleteOperatorRoles()`, check if the *only* cluster using the roles is the owning cluster (which is itself being deleted):

```go
func (r *ROSARoleConfigReconciler) deleteOperatorRoles(scope *scope.RosaRoleConfigScope) error {
    clusters, err := r.Runtime.OCMClient.GetClustersUsingOperatorRolesPrefix(prefix)
    if err != nil {
        return err
    }

    // Filter out the owning cluster (it's being deleted too)
    ownerClusterID := scope.RosaRoleConfig.Status.OwnerClusterID
    externalUsers := filterOut(clusters, ownerClusterID)

    if len(externalUsers) > 0 {
        return fmt.Errorf("operator Roles with Prefix '%s' are in use by other clusters", prefix)
    }
    // proceed — only our own dying cluster uses these
}
```

**Pros**: Automatic, no manual intervention needed
**Cons**: Requires new OCM client method, needs cluster ID tracking in RosaRoleConfig status, more complex change

### Option C: Tolerate missing OIDC in reconcileNormal (defensive)

When the OIDC provider is missing and the cluster is in a non-recoverable state, detect this and mark the ROSAControlPlane for deletion instead of looping:

```go
// In reconcileNormal, after checking cluster state
if cluster.Status().State() == cmv1.ClusterStateReady {
    // Verify OIDC is still valid before marking ready
    if err := validateOIDCProvider(rosaScope); err != nil {
        // OIDC gone — cluster is zombie, surface error clearly
        rosaScope.ControlPlane.Status.FailureMessage = ptr.To("OIDC provider missing from AWS")
        return ctrl.Result{}, nil  // don't requeue — needs manual intervention
    }
}
```

**Pros**: Stops the infinite loop, surfaces clear error
**Cons**: Doesn't fix the deletion deadlock, only stops the noise

### Recommended: Option A + C combined

- Option A gives operators an escape hatch for the deletion deadlock
- Option C stops the infinite requeue noise when OIDC is missing
- Both are low-risk, backward-compatible changes

## Orphaned AWS Resources

Each stuck cluster leaves behind ~11 IAM roles:
- 3 account roles: `{prefix}-HCP-ROSA-Installer-Role`, `-Support-Role`, `-Worker-Role`
- 8 operator roles: `{prefix}-kube-system-control-plane-operator`, `-kube-system-kube-controller-manager`, `-kube-system-capa-controller-manager`, `-kube-system-kms-provider`, `-openshift-ingress-operator-cloud-credentials`, `-openshift-image-registry-installer-cloud-credentials`, `-openshift-cloud-network-config-controller-cloud-credentials`, `-openshift-cluster-csi-drivers-ebs-cloud-credentials`

These roles may have associated instance profiles that also become orphaned.

## Manual Cleanup Procedure

When clusters are stuck in this deadlock, clean up in this order:

1. **Delete the ROSA cluster from OCM** (releases the operator role lock):
   ```
   rosa delete cluster --cluster=<cluster-name> --yes
   ```

2. **Wait for OCM deletion to complete**, then delete operator roles:
   ```
   rosa delete operator-roles --prefix <prefix> --yes
   ```

3. **Delete the OIDC provider and config** (if still present):
   ```
   rosa delete oidc-provider --oidc-config-id <id> --yes
   ```

4. **Delete account roles**:
   ```
   rosa delete account-roles --prefix <prefix> --yes
   ```

5. **Remove the K8s resources from minikube**:
   ```
   kubectl delete cluster <name> -n ns-rosa-hcp
   ```
   If finalizer blocks deletion:
   ```
   kubectl patch rosacontrolplane <name> -n ns-rosa-hcp --type merge -p '{"metadata":{"finalizers":[]}}'
   kubectl patch rosaroleconfig <name>-roles -n ns-rosa-hcp --type merge -p '{"metadata":{"finalizers":[]}}'
   ```

## References

- Controller source: `controlplane/rosa/controllers/rosacontrolplane_controller.go`
- RoleConfig controller: `exp/controllers/rosaroleconfig_controller.go`
- Upstream repo: `kubernetes-sigs/cluster-api-provider-aws`
