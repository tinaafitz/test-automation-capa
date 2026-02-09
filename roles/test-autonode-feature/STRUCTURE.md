# test-autonode-feature Role - Directory Structure

Created: 2025-10-21

## Complete Directory Structure

```
test-autonode-feature/
├── README.md                                    # Role documentation
├── defaults/
│   └── main.yml                                 # Default variables
├── vars/
│   └── main.yml                                 # Role-specific variables
├── handlers/
│   └── main.yml                                 # Event handlers
├── meta/
│   └── main.yml                                 # Role metadata and dependencies
├── tasks/
│   ├── main.yml                                 # Main task entry point
│   ├── 01-validate-prerequisites.yml            # Step 1: Validate environment
│   ├── 02-create-iam-policy.yml                 # Step 2: Create AWS IAM policy
│   ├── 03-get-cluster-info.yml                  # Step 3: Get cluster details
│   ├── 04-create-trust-policy.yml               # Step 4: Generate trust policy
│   ├── 05-create-iam-role.yml                   # Step 5: Create IAM role
│   ├── 06-update-rosacontrolplane.yml           # Step 6: Update K8s resource
│   ├── 07-tag-aws-resources.yml                 # Step 7: Tag SG and subnets
│   ├── 08-create-kubeconfig.yml                 # Step 8: Generate kubeconfig
│   ├── 09-create-ec2nodeclass.yml               # Step 9: Create EC2NodeClass
│   ├── 10-create-nodepool.yml                   # Step 10: Create NodePool
│   ├── 11-verify-autonode.yml                   # Step 11: Verify installation
│   ├── 12-test-scaling.yml                      # Step 12: Test scaling
│   └── cleanup.yml                              # Cleanup resources
├── templates/
│   ├── autonode-policy.json.j2                  # IAM policy template
│   ├── trust-policy.json.j2                     # Trust relationship template
│   ├── ec2nodeclass.yaml.j2                     # OpenshiftEC2NodeClass manifest
│   ├── nodepool.yaml.j2                         # NodePool manifest
│   └── test-deployment.yaml.j2                  # Test workload manifest
└── files/
    ├── autonode-validation-script.sh            # Validation helper script
    └── autonode-cleanup-script.sh               # Cleanup helper script
```

## File Count

- **Tasks**: 14 files (main.yml + 12 steps + cleanup)
- **Templates**: 5 Jinja2 templates
- **Scripts**: 2 bash helper scripts
- **Configuration**: 4 YAML config files
- **Documentation**: 2 markdown files (README + STRUCTURE)

**Total**: 27 files

## Purpose of Each Directory

### `/defaults`
Contains default variable values that can be overridden by users. These are the lowest priority variables in Ansible.

### `/vars`
Contains role-specific variables with higher priority than defaults. Used for variables that shouldn't typically be overridden.

### `/tasks`
Contains all Ansible tasks that implement the AutoNode testing workflow. Each numbered task file corresponds to a step in the QE AutoNode Test Guide.

### `/templates`
Contains Jinja2 templates for generating AWS IAM policies, trust relationships, and Kubernetes manifests with parameterized values.

### `/files`
Contains static files and scripts that are copied or executed during role execution. Includes validation and cleanup helper scripts.

### `/handlers`
Contains handlers that respond to task notifications. Used for restarting services or performing actions when specific events occur.

### `/meta`
Contains role metadata including dependencies, supported platforms, and Galaxy information.

## Next Steps

1. Populate `defaults/main.yml` with default variable definitions
2. Populate `meta/main.yml` with role metadata
3. Implement each task file (01-12, cleanup)
4. Create Jinja2 templates
5. Write helper scripts
6. Write comprehensive README.md
7. Test the role

## Task Implementation Order

The tasks should be implemented in numerical order:

1. **01-validate-prerequisites.yml** - Foundation for all other tasks
2. **02-create-iam-policy.yml** - Creates AWS IAM policy
3. **03-get-cluster-info.yml** - Retrieves cluster information
4. **04-create-trust-policy.yml** - Generates trust policy
5. **05-create-iam-role.yml** - Creates IAM role with trust policy
6. **06-update-rosacontrolplane.yml** - Updates K8s control plane
7. **07-tag-aws-resources.yml** - Tags AWS resources
8. **08-create-kubeconfig.yml** - Creates cluster credentials
9. **09-create-ec2nodeclass.yml** - Creates EC2NodeClass
10. **10-create-nodepool.yml** - Creates NodePool
11. **11-verify-autonode.yml** - Verifies all components
12. **12-test-scaling.yml** - Tests scaling functionality
13. **cleanup.yml** - Cleanup and teardown

## Status

- [x] Directory structure created
- [x] Task placeholder files created
- [x] Template placeholder files created
- [x] Script placeholder files created
- [x] Configuration files created
- [ ] Defaults populated
- [ ] Metadata populated
- [ ] Tasks implemented
- [ ] Templates created
- [ ] Scripts written
- [ ] README documentation
- [ ] Testing completed
