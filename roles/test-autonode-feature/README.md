# test-autonode-feature

Ansible role to automate testing of the AutoNode (Karpenter) feature on ROSA (Red Hat OpenShift Service on AWS) Hosted Control Plane (HCP) clusters.

## Overview

This role automates the complete workflow for testing AutoNode functionality on ROSA HCP clusters, including:

- Prerequisites validation
- IAM policy and role creation
- Cluster configuration
- Karpenter resource deployment
- Scaling tests
- Verification and cleanup

## Table of Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Role Variables](#role-variables)
- [Dependencies](#dependencies)
- [Example Playbooks](#example-playbooks)
- [Testing Workflow](#testing-workflow)
- [Tags](#tags)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## Requirements

### CLI Tools

The following CLI tools must be installed and available in your PATH:

- `kubectl` - Kubernetes CLI
- `oc` - OpenShift CLI
- `aws` - AWS CLI v2
- `rosa` - ROSA CLI
- `jq` - JSON processor

### Cluster Requirements

- ROSA HCP cluster in 'ready' state
- Cluster must support AutoNode feature
- OIDC provider configured for the cluster

### AWS Requirements

- AWS credentials with permissions to:
  - Create and manage IAM policies and roles
  - Tag EC2 resources (security groups, subnets)
  - Describe EC2 resources
- Access to the AWS account where the ROSA cluster is deployed

### Ansible Requirements

- Ansible >= 2.12
- Required collections:
  ```bash
  ansible-galaxy collection install kubernetes.core
  ansible-galaxy collection install community.general
  ansible-galaxy collection install amazon.aws
  ```

## Installation

### Clone the Repository

```bash
git clone <repository-url>
cd automation-capi
```

### Install Ansible Collections

```bash
ansible-galaxy collection install -r requirements.yml
```

## Role Variables

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `cluster_name` | Name of the ROSA HCP cluster | `my-rosa-cluster` |

### Common Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `cluster_namespace` | `clusters` | Namespace where RosaControlPlane exists |
| `aws_region` | `us-east-1` | AWS region for the cluster |
| `autonode_mode` | `enabled` | AutoNode mode (enabled/disabled) |

### IAM Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `autonode_policy_name` | `AutoNodePolicy-{{ cluster_name }}` | IAM policy name |
| `autonode_role_name` | `AutoNodeRole-{{ cluster_name }}` | IAM role name |

### NodePool Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `nodepool_name` | `default-nodepool` | Name of the Karpenter NodePool |
| `nodeclass_name` | `default-nodeclass` | Name of the EC2NodeClass |
| `autonode_instance_types` | `[m5.large, m5.xlarge, ...]` | EC2 instance types |
| `autonode_capacity_types` | `[on-demand, spot]` | Capacity types |
| `autonode_max_cpu` | `1000` | Maximum CPU cores |
| `autonode_max_memory` | `1000Gi` | Maximum memory |

### Scaling Test Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `autonode_test_replicas` | `10` | Number of test pods |
| `autonode_test_cpu` | `500m` | CPU request per pod |
| `autonode_test_memory` | `1Gi` | Memory request per pod |
| `autonode_scaling_timeout` | `600` | Scaling timeout in seconds |

### Cleanup Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `autonode_cleanup_test_deployment` | `true` | Delete test deployment after test |
| `autonode_cleanup_iam_resources` | `false` | Delete IAM resources during cleanup |

See [defaults/main.yml](defaults/main.yml) for a complete list of variables.

## Dependencies

This role has no dependencies on other Ansible roles.

Required Ansible collections:
- `kubernetes.core`
- `community.general`
- `amazon.aws`

## Example Playbooks

### Basic Usage

```yaml
---
- name: Test AutoNode on ROSA HCP cluster
  hosts: localhost
  gather_facts: yes
  roles:
    - role: test-autonode-feature
      vars:
        cluster_name: my-rosa-cluster
        aws_region: us-east-1
```

### Custom Instance Types

```yaml
---
- name: Test AutoNode with specific instance types
  hosts: localhost
  gather_facts: yes
  roles:
    - role: test-autonode-feature
      vars:
        cluster_name: my-rosa-cluster
        aws_region: us-west-2
        autonode_instance_types:
          - m6i.large
          - m6i.xlarge
          - c6i.large
        autonode_capacity_types:
          - spot
        autonode_test_replicas: 20
```

### Spot Instances Only

```yaml
---
- name: Test AutoNode with spot instances
  hosts: localhost
  gather_facts: yes
  roles:
    - role: test-autonode-feature
      vars:
        cluster_name: my-rosa-cluster
        autonode_capacity_types:
          - spot
        autonode_max_cpu: "500"
```

### Run Specific Steps

```yaml
---
- name: Run only IAM setup
  hosts: localhost
  gather_facts: yes
  tasks:
    - include_role:
        name: test-autonode-feature
        tasks_from: main
      vars:
        cluster_name: my-rosa-cluster
      tags:
        - iam
```

## Testing Workflow

The role executes the following workflow:

### Phase 1: Prerequisites & IAM Setup

1. **Validate Prerequisites** (Task 01)
   - Verify cluster exists and is ready
   - Check required CLI tools
   - Validate AWS credentials
   - Verify ROSA authentication

2. **Create IAM Policy** (Task 02)
   - Generate AutoNode IAM policy from template
   - Create policy in AWS
   - Store policy ARN

3. **Get Cluster Information** (Task 03)
   - Retrieve cluster ID
   - Extract OIDC provider URL
   - Validate AWS account

4. **Create Trust Policy** (Task 04)
   - Generate trust policy for OIDC federation
   - Configure Karpenter service account

5. **Create IAM Role** (Task 05)
   - Create IAM role with trust policy
   - Attach AutoNode policy

### Phase 2: Cluster Configuration

6. **Update RosaControlPlane** (Task 06)
   - Patch RosaControlPlane with AutoNode config
   - Set AutoNode mode and IAM role ARN

7. **Tag AWS Resources** (Task 07)
   - Tag security groups with `karpenter.sh/discovery`
   - Tag subnets for Karpenter resource discovery

8. **Create Kubeconfig** (Task 08)
   - Create cluster admin user
   - Generate kubeconfig file

### Phase 3: Karpenter Resources

9. **Create EC2NodeClass** (Task 09)
   - Generate OpenshiftEC2NodeClass manifest
   - Apply to cluster
   - Wait for ready status

10. **Create NodePool** (Task 10)
    - Generate NodePool manifest
    - Apply to cluster
    - Verify creation

### Phase 4: Testing & Verification

11. **Verify AutoNode** (Task 11)
    - Check Karpenter pods running
    - Verify NodePools and EC2NodeClass
    - Check for errors in events

12. **Test Scaling** (Task 12)
    - Deploy test workload
    - Monitor node provisioning
    - Measure scaling time
    - Validate success

### Cleanup

- **Cleanup** (cleanup.yml)
  - Remove test deployments
  - Delete NodePools and EC2NodeClass
  - Remove AutoNode from RosaControlPlane
  - Optionally delete IAM resources
  - Clean temporary files

## Tags

The role supports the following tags for selective execution:

| Tag | Description |
|-----|-------------|
| `validate` | Run validation tasks |
| `prerequisites` | Check prerequisites |
| `step1` | Validate prerequisites |
| `step2` | Create IAM policy |
| `step3` | Get cluster information |
| `step4` | Create trust policy |
| `step5` | Create IAM role |
| `step6` | Update RosaControlPlane |
| `step7` | Tag AWS resources |
| `step8` | Create kubeconfig |
| `step9` | Create EC2NodeClass |
| `step10` | Create NodePool |
| `step11` | Verify AutoNode |
| `step12` | Test scaling |
| `iam` | All IAM-related tasks (steps 2-5) |
| `karpenter` | Karpenter resource tasks (steps 9-10) |
| `test` | Testing tasks (steps 11-12) |

### Example: Run only validation

```bash
ansible-playbook playbooks/test-autonode.yml --tags validate
```

### Example: Run IAM setup only

```bash
ansible-playbook playbooks/test-autonode.yml --tags iam
```

### Example: Skip validation

```bash
ansible-playbook playbooks/test-autonode.yml --skip-tags validate
```

## Helper Scripts

The role includes two helper bash scripts in the `files/` directory:

### autonode-validation-script.sh

Standalone validation script that can be run outside of Ansible.

**Usage:**
```bash
./files/autonode-validation-script.sh <cluster_name> [kubeconfig_path]
```

**Features:**
- Validates all AutoNode components
- Checks Karpenter pods, NodePools, EC2NodeClass
- Verifies IAM resources
- Checks AWS resource tags
- Provides detailed pass/fail/warning status

### autonode-cleanup-script.sh

Standalone cleanup script for removing AutoNode resources.

**Usage:**
```bash
./files/autonode-cleanup-script.sh <cluster_name> [options]

Options:
  --delete-iam         Delete IAM resources
  --keep-iam           Keep IAM resources (default)
  --kubeconfig PATH    Custom kubeconfig path
  --dry-run            Show what would be deleted
  --force              Skip confirmation prompts
```

**Examples:**
```bash
# Dry run to see what would be deleted
./files/autonode-cleanup-script.sh my-cluster --dry-run

# Cleanup with IAM resource deletion
./files/autonode-cleanup-script.sh my-cluster --delete-iam --force

# Cleanup Kubernetes resources only
./files/autonode-cleanup-script.sh my-cluster --keep-iam
```

## Directory Structure

```
test-autonode-feature/
   README.md                    # This file
   STRUCTURE.md                 # Directory structure documentation
   defaults/
      main.yml                 # Default variables
   vars/
      main.yml                 # Role variables
   handlers/
      main.yml                 # Handlers
   meta/
      main.yml                 # Role metadata
   tasks/
      main.yml                 # Main task orchestration
      01-validate-prerequisites.yml
      02-create-iam-policy.yml
      03-get-cluster-info.yml
      04-create-trust-policy.yml
      05-create-iam-role.yml
      06-update-rosacontrolplane.yml
      07-tag-aws-resources.yml
      08-create-kubeconfig.yml
      09-create-ec2nodeclass.yml
      10-create-nodepool.yml
      11-verify-autonode.yml
      12-test-scaling.yml
      cleanup.yml
   templates/
      autonode-policy.json.j2  # IAM policy template
      trust-policy.json.j2     # Trust policy template
      ec2nodeclass.yaml.j2     # EC2NodeClass manifest
      nodepool.yaml.j2         # NodePool manifest
      test-deployment.yaml.j2  # Test deployment
   files/
       autonode-validation-script.sh
       autonode-cleanup-script.sh
```

## Troubleshooting

### Common Issues

#### 1. Cluster Not Ready

**Error:** "Cluster is not in 'ready' state"

**Solution:**
```bash
# Check cluster status
rosa describe cluster --cluster <cluster_name>

# Wait for cluster to be ready
rosa logs install --cluster <cluster_name> --watch
```

#### 2. AWS Credentials Not Found

**Error:** "AWS credentials are not configured or invalid"

**Solution:**
```bash
# Configure AWS credentials
aws configure

# Or export environment variables
export AWS_ACCESS_KEY_ID="your-key-id"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-1"
```

#### 3. ROSA Authentication Failed

**Error:** "ROSA authentication failed"

**Solution:**
```bash
# Login to ROSA
rosa login

# Verify authentication
rosa whoami
```

#### 4. Karpenter Pods Not Running

**Error:** "Karpenter pods are not in Running state"

**Solution:**
```bash
# Check Karpenter pods
kubectl get pods -n kube-system -l app.kubernetes.io/name=karpenter

# Check pod logs
kubectl logs -n kube-system -l app.kubernetes.io/name=karpenter

# Check events
kubectl get events -n kube-system --sort-by='.lastTimestamp'
```

#### 5. NodePool Not Provisioning Nodes

**Symptoms:** Test deployment pods remain pending, no new nodes created

**Diagnostics:**
```bash
# Check NodePool status
kubectl get nodepools
kubectl describe nodepool <nodepool_name>

# Check EC2NodeClass
kubectl get ec2nodeclass
kubectl describe ec2nodeclass <nodeclass_name>

# Check Karpenter logs
kubectl logs -n kube-system -l app.kubernetes.io/name=karpenter --tail=100
```

**Common Causes:**
- Security groups not tagged correctly
- Subnets not tagged correctly
- IAM role missing permissions
- Instance types not available in region

#### 6. IAM Permission Errors

**Error:** "User is not authorized to perform iam:CreatePolicy"

**Solution:** Ensure your AWS credentials have the following permissions:
- `iam:CreatePolicy`
- `iam:CreateRole`
- `iam:AttachRolePolicy`
- `iam:TagRole`
- `ec2:CreateTags`
- `ec2:DescribeSecurityGroups`
- `ec2:DescribeSubnets`

### Debug Mode

Enable debug mode for verbose output:

```yaml
- role: test-autonode-feature
  vars:
    cluster_name: my-cluster
    autonode_debug_mode: true
```

### Validation Script

Use the validation script to check AutoNode installation:

```bash
./files/autonode-validation-script.sh my-cluster
```

### Manual Verification

Verify AutoNode manually:

```bash
# Check RosaControlPlane
oc get rosacontrolplane <cluster_name> -o yaml | grep -A 5 autoNode

# Check Karpenter
kubectl get pods -n kube-system -l app.kubernetes.io/name=karpenter

# Check NodePools
kubectl get nodepools

# Check EC2NodeClass
kubectl get ec2nodeclass

# Check nodes
kubectl get nodes -l karpenter.sh/nodepool
```

## Results and Logs

### Results Directory

Test results are saved to `{{ autonode_results_dir }}` (default: `/tmp/autonode-results`):

- `verification-<cluster>-<timestamp>.txt` - Verification results
- `scaling-test-<cluster>-<timestamp>.txt` - Scaling test results
- `<nodeclass>-ec2nodeclass-<timestamp>.yaml` - EC2NodeClass manifest
- `<nodepool>-nodepool-<timestamp>.yaml` - NodePool manifest

### Temporary Files

Temporary files are created in `/tmp/`:

- `/tmp/AutoNodePolicy-*.json` - IAM policy
- `/tmp/*-trust-policy.json` - Trust policy
- `/tmp/*-ec2nodeclass.yaml` - EC2NodeClass manifest
- `/tmp/*-nodepool.yaml` - NodePool manifest
- `/tmp/autonode-scale-test-deployment.yaml` - Test deployment

These are cleaned up by the cleanup task.

## Cleanup

### Using Ansible

Run the cleanup playbook:

```bash
# Cleanup Kubernetes resources only
ansible-playbook playbooks/test-autonode-cleanup.yml

# Cleanup including IAM resources
ansible-playbook playbooks/test-autonode-cleanup.yml \
  -e "autonode_cleanup_iam_resources=true"
```

### Using Cleanup Script

```bash
# Cleanup without IAM resources
./files/autonode-cleanup-script.sh my-cluster

# Cleanup with IAM resources
./files/autonode-cleanup-script.sh my-cluster --delete-iam

# Dry run
./files/autonode-cleanup-script.sh my-cluster --dry-run
```

### Manual Cleanup

If automated cleanup fails, clean up manually:

```bash
# Delete test deployment
kubectl delete deployment autonode-scale-test

# Delete NodePools
kubectl delete nodepool <nodepool_name>

# Delete EC2NodeClass
kubectl delete ec2nodeclass <nodeclass_name>

# Remove autoNode from RosaControlPlane
oc patch rosacontrolplane <cluster_name> -n clusters --type json \
  -p '[{"op": "remove", "path": "/spec/autoNode"}]'

# Delete IAM role (detach policy first)
aws iam detach-role-policy --role-name <role_name> --policy-arn <policy_arn>
aws iam delete-role --role-name <role_name>

# Delete IAM policy
aws iam delete-policy --policy-arn <policy_arn>
```

## Contributing

Contributions are welcome! Please follow these guidelines:

1. Create a feature branch
2. Make your changes
3. Test thoroughly
4. Submit a pull request

## Support

For issues and questions:
- Open an issue in the repository
- Contact the CAPA team

## License

Apache License 2.0

## Authors

CAPA Team

## Version

1.0.0

## References

- [ROSA Documentation](https://docs.openshift.com/rosa/)
- [Karpenter Documentation](https://karpenter.sh/)
- [AutoNode Feature Guide](https://github.com/tinaafitz/automation-capi/blob/main/QE_AUTONODE_TEST_GUIDE.md)
- [AWS CLI Documentation](https://docs.aws.amazon.com/cli/)
- [Ansible Documentation](https://docs.ansible.com/)
