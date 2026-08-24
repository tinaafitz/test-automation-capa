# CAPA Test Automation Framework

Automated testing framework for **Cluster API Provider AWS (CAPA)** with focus on **ROSA HCP** (Red Hat OpenShift Service on AWS - Hosted Control Plane) cluster lifecycle management.

## Overview

This repository contains comprehensive test automation for CAPI/CAPA environments, including:

- ✅ MCE (Multicluster Engine) environment configuration and verification
- 🚀 ROSA HCP cluster provisioning with automated network and IAM role setup
- 🗑️ ROSA HCP cluster deletion and cleanup
- 🔄 CAPI/CAPA component management (enable/disable)
- 🧪 End-to-end lifecycle testing
- 📊 Test suite framework with JSON-based test definitions

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   MCE Hub Cluster                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Multicluster Engine (MCE)                           │   │
│  │  ├── CAPI Controller (cluster-api)                   │   │
│  │  └── CAPA Controller (cluster-api-provider-aws)      │   │
│  └──────────────────────────────────────────────────────┘   │
│                           │                                  │
│                           │ Manages                          │
│                           ▼                                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  ROSA HCP Cluster (AWS)                              │   │
│  │  ├── ROSAControlPlane (control plane in AWS)         │   │
│  │  ├── ROSANetwork (VPC, subnets via CloudFormation)   │   │
│  │  └── ROSARoleConfig (IAM roles, OIDC provider)       │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- **OpenShift Hub Cluster** with MCE/ACM installed
- **AWS Account** with appropriate permissions
- **OCM (OpenShift Cluster Manager)** credentials
- **Ansible** 2.9+ installed
- **Python** 3.8+ installed
- **oc CLI** installed and configured

### Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/YOUR_ORG/test-automation-capa.git
   cd test-automation-capa
   ```

2. **Configure credentials:**
   ```bash
   cp vars/user_vars.yml.example vars/user_vars.yml
   # Edit vars/user_vars.yml with your credentials
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt  # If Python deps exist
   ```

4. **Verify environment:**
   ```bash
   ./run-test-suite.py 05-verify-mce-environment
   ```

## Test Suites

List all available test suites:
```bash
./run-test-suite.py --list
```

### Core Test Suites

| ID | Name | Description |
|----|------|-------------|
| **05** | Verify MCE Environment | Validate MCE/CAPI/CAPA configuration |
| **10** | Configure MCE | Set up MCE for CAPI/CAPA provisioning |
| **20** | ROSA HCP Provision | Provision ROSA HCP cluster with automation |
| **30** | ROSA HCP Delete | Delete cluster and cleanup resources |
| **40** | Enable CAPI/Disable Hypershift | Switch MCE to CAPI mode |
| **41** | Disable CAPI/Enable Hypershift | Switch MCE to Hypershift mode |

### Usage Examples

#### 1. Configure MCE Environment
```bash
./run-test-suite.py 10-configure-mce-environment
```

#### 2. Provision ROSA HCP Cluster
```bash
# Using name_prefix (recommended)
./run-test-suite.py 20-rosa-hcp-provision -e name_prefix=test

# With custom configuration
./run-test-suite.py 20-rosa-hcp-provision \
  -e name_prefix=demo \
  -e openshift_version=4.20.10 \
  -e availability_zone_count=2
```

#### 3. Delete ROSA HCP Cluster
```bash
# Delete cluster and all resources
./run-test-suite.py 30-rosa-hcp-delete -e name_prefix=test

# Delete cluster but keep network
./run-test-suite.py 30-rosa-hcp-delete \
  -e name_prefix=test \
  -e delete_network=false
```

#### 4. Complete Lifecycle Test
```bash
# Configure → Verify → Provision → Delete
./run-test-suite.py 10-configure-mce-environment
./run-test-suite.py 05-verify-mce-environment
./run-test-suite.py 20-rosa-hcp-provision -e name_prefix=e2e
./run-test-suite.py 30-rosa-hcp-delete -e name_prefix=e2e
```

## Repository Structure

```
test-automation-capa/
├── test-suites/           # Test suite definitions (JSON)
│   ├── 05-verify-mce-environment.json
│   ├── 10-configure-mce-environment.json
│   ├── 20-rosa-hcp-provision.json
│   └── 30-rosa-hcp-delete.json
├── playbooks/             # Ansible playbooks
│   ├── create_rosa_hcp_cluster.yml
│   ├── delete_rosa_hcp_cluster.yml
│   ├── configure_mce_environment.yml
│   └── verify_capi_environment.yaml
├── tasks/                 # Ansible task files
│   ├── create_rosa_network.yml
│   ├── create_rosa_role_config.yml
│   ├── delete_rosa_hcp_resources.yml
│   └── login_ocp.yml
├── templates/             # Jinja2 templates
│   └── versions/          # Version-specific templates
├── roles/                 # Ansible roles
│   └── test-autonode-feature/
├── vars/                  # Variables
│   ├── vars.yml           # Default variables
│   └── user_vars.yml.example  # Credentials template
├── scripts/               # Helper scripts
│   ├── mce_env_manager.py
│   └── check-mce-health.sh
├── run-test-suite.py      # Main test runner
├── ansible.cfg            # Ansible configuration
├── .gitignore
└── README.md
```

## Configuration

### Required Credentials (`vars/user_vars.yml`)

```yaml
# OpenShift Hub Cluster
OCP_HUB_API_URL: "https://api.example.com:6443"
OCP_HUB_CLUSTER_USER: "kubeadmin"
OCP_HUB_CLUSTER_PASSWORD: "your-password"

# AWS
AWS_REGION: "us-west-2"
AWS_ACCESS_KEY_ID: "AKIAIOSFODNN7EXAMPLE"
AWS_SECRET_ACCESS_KEY: "your-secret-key"

# OCM (OpenShift Cluster Manager)
OCM_CLIENT_ID: "your-client-id"
OCM_CLIENT_SECRET: "your-client-secret"
```

### Common Variables

- `name_prefix`: Simple prefix for all resources (e.g., `test` → `test-rosa-hcp`)
- `cluster_name`: Explicit cluster name (auto-derived from `name_prefix`)
- `openshift_version`: OpenShift version (default: `4.20.10`)
- `aws_region`: AWS region (default: `us-west-2`)
- `availability_zone_count`: Number of AZs (1-3, default: `1`)
- `create_rosa_network`: Create VPC/subnets (default: `true`)
- `create_rosa_role_config`: Create IAM roles (default: `true`)

## Test Suite Framework

Test suites are defined in JSON files with this structure:

```json
{
  "name": "ROSA HCP Cluster Provisioning",
  "description": "Provision a ROSA HCP cluster",
  "version": "1.0.0",
  "tags": ["rosa", "hcp", "provisioning"],
  "environment": "mce",
  "playbooks": [
    {
      "name": "Create ROSA HCP Cluster",
      "file": "create_rosa_hcp_cluster.yml",
      "extra_vars": {
        "openshift_version": "4.20.10",
        "create_rosa_network": true
      }
    }
  ]
}
```

## Features

### Automated ROSANetwork Creation

Automatically creates AWS networking resources via CloudFormation:
- VPC with configurable CIDR block
- Public and private subnets across availability zones
- Internet Gateway and NAT Gateways
- Route tables and security groups

### Automated ROSARoleConfig Creation

Automatically creates AWS IAM resources:
- Installer, Support, and Worker IAM roles
- OIDC provider for cluster authentication
- Role trust policies and permissions
- Operator-specific IAM roles

### Verification and Health Checks

- OCP login validation
- CAPI/CAPA controller deployment checks
- Component status reporting
- Credential validation
- Resource inventory

## Monitoring

### Check Cluster Resources
```bash
# View all ROSA cluster resources
oc get rosacontrolplane,rosamachinepool,rosanetwork,rosaroleconfig -n ns-rosa-hcp

# View all ROSA clusters across all namespaces
oc get rosacontrolplane --all-namespaces -o wide

# Get detailed cluster information
oc get rosacontrolplane -n ns-rosa-hcp -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.ready}{"\t"}{.spec.region}{"\n"}{end}'
```

### Check MCE Components
```bash
# View MCE configuration
oc get mce $(oc get mce -ojsonpath='{.items[0].metadata.name}') -n multicluster-engine -o yaml

# Check CAPA controller logs
oc logs -n multicluster-engine deployment/capa-controller-manager
```

### View Test Results
Test results are saved in `test-results/` directory with timestamped subdirectories.

## Troubleshooting

### Common Issues

#### 1. OCP Login Failed
```bash
# Verify credentials
oc login $OCP_HUB_API_URL -u $OCP_HUB_CLUSTER_USER -p $OCP_HUB_CLUSTER_PASSWORD
```

#### 2. CAPI/CAPA Not Enabled
```bash
# Run configuration playbook
./run-test-suite.py 10-configure-mce-environment
```

#### 3. Cluster Provisioning Stuck
```bash
# Check ROSAControlPlane status
oc describe rosacontrolplane CLUSTER_NAME -n ns-rosa-hcp

# Check CAPA controller logs
oc logs -n multicluster-engine deployment/capa-controller-manager
```

#### 4. Deletion Timeout
```bash
# Check deletion status of network resources
oc get rosanetwork -n ns-rosa-hcp -o wide

# Check deletion status of role resources
oc get rosaroleconfig -n ns-rosa-hcp -o wide

# View deletion events
oc get events -n ns-rosa-hcp --sort-by='.lastTimestamp'
```

## Development

### Running Individual Playbooks

```bash
# Provision cluster
ansible-playbook playbooks/create_rosa_hcp_cluster.yml \
  -e name_prefix=dev

# Delete cluster
ansible-playbook playbooks/delete_rosa_hcp_cluster.yml \
  -e name_prefix=dev
```

### Creating New Test Suites

1. Create JSON definition in `test-suites/`
2. Reference existing playbooks or create new ones
3. Add documentation section with examples
4. Test with `./run-test-suite.py YOUR_SUITE_ID`

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## Security

**⚠️ IMPORTANT:**
- Never commit `vars/user_vars.yml` to git (it contains credentials)
- Use `vars/user_vars.yml.example` as a template
- Rotate credentials regularly
- Use least-privilege AWS IAM policies

## License

[Your License Here]

## Support

- **Issues**: https://github.com/YOUR_ORG/test-automation-capa/issues
- **Documentation**: See `test-suites/*.json` for detailed examples
- **Community**: [Your communication channel]

## Acknowledgments

Built with:
- [Ansible](https://www.ansible.com/)
- [Cluster API](https://cluster-api.sigs.k8s.io/)
- [Cluster API Provider AWS (CAPA)](https://cluster-api-aws.sigs.k8s.io/)
- [Red Hat MCE](https://access.redhat.com/products/red-hat-advanced-cluster-management-for-kubernetes)
- [ROSA](https://www.redhat.com/en/technologies/cloud-computing/openshift/aws)

## Web UI

The test automation suite includes a modern web interface for managing CAPI/ROSA test environments.

### Quick Start

**Using Docker (Recommended):**
```bash
cd ui
docker-compose up
```

**Manual Setup:**

1. **Frontend:**
```bash
cd ui/frontend
npm install
npm start  # Runs on http://localhost:3000
```

2. **Backend:**
```bash
cd ui/backend
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

### Features

- **MCE Environment** (`/mce`): Manage OpenShift hub clusters with Multicluster Engine
  - Configure MCE environments
  - Enable/disable CAPI components
  - Run test suites
  - View environment health

- **Minikube Environment** (`/minikube`): Local development clusters
  - Create/delete Minikube clusters
  - Install CAPI/CAPA controllers
  - Test cluster operations
  - Monitor component status

### Configuration

Edit `ui/backend/.env`:
```bash
AUTOMATION_PATH=/Users/tinafitzgerald/acm_dev/test-automation-capa
FRONTEND_URL=http://localhost:3000
BACKEND_PORT=8000
```

### Technology Stack

- **Frontend**: React 18, Tailwind CSS, Heroicons
- **Backend**: FastAPI, Python 3.11+
- **Communication**: REST API + WebSockets for real-time updates

