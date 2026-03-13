# AWS Usage Dashboard - Hybrid Configuration

## Overview

The AWS Usage Dashboard uses a **hybrid approach** for resource thresholds and costs:
- **YAML config** (`config/aws_resource_config.yml`) - Default values, costs, descriptions
- **AWS Service Quotas API** - Live quota data from your AWS account
- **Automatic fallback** - Uses defaults if AWS API unavailable
- **24-hour caching** - Prevents excessive AWS API calls

## Benefits

**Before (Hardcoded)**:
```javascript
const billedResources = [
  { threshold: 800, costPerMonth: 32.40 }  // Assumes same limits for all accounts
];
```

Problems: Inaccurate quotas, stale costs, requires code deployment to update.

**After (Hybrid)**:
```yaml
instance_profiles:
  default_threshold: 800
  use_aws_quota: true
  quota_service_code: "iam"
  quota_code: "L-C07B4B0D"
  warn_at_percent: 80  # Warn at 80% of actual quota
```

Benefits: Uses actual AWS quotas, easy cost updates, graceful fallback, tracks quota source.

## Configuration Structure

### config/aws_resource_config.yml

```yaml
metadata:
  version: "1.0"
  last_cost_update: "2024-01-15"
  region: "us-east-1"

billed_resources:
  nat_gateways:
    label: "NAT Gateways"
    icon: "🌉"
    description: "Network address translation gateways"
    default_threshold: 10
    use_aws_quota: false
    cost_per_month: 32.40
    cost_type: "fixed"

free_resources:
  instance_profiles:
    label: "Instance Profiles"
    icon: "🔖"
    description: "IAM instance profiles for EC2 instances"
    default_threshold: 800
    use_aws_quota: true
    quota_service_code: "iam"
    quota_code: "L-C07B4B0D"
    warn_at_percent: 80

quota_settings:
  enabled: true
  cache_duration_hours: 24
  fallback_to_defaults: true
```

## How It Works

1. Frontend fetches `/api/aws/usage-config` on mount
2. Backend loads YAML config
3. For resources with `use_aws_quota: true`, fetch from AWS API
4. Calculate threshold: `quota × warn_at_percent`
5. Cache result for 24 hours
6. Return config with quota source (aws_api, config, or default)

## Backend Implementation

**ui/backend/aws_config_service.py**:
```python
from aws_config_service import aws_config_service
config = aws_config_service.get_resource_config_with_quotas()
```

**ui/backend/app.py**:
```python
@app.get("/api/aws/usage-config")
async def get_aws_config():
    from aws_config_service import aws_config_service
    return aws_config_service.get_resource_config_with_quotas()
```

## Frontend Integration

**ui/frontend/src/pages/AWSUsageDashboard.jsx**:
```javascript
useEffect(() => {
  const fetchConfig = async () => {
    const response = await fetch('http://localhost:8000/api/aws/usage-config');
    const data = await response.json();
    setBilledResources(data.billedResources);
    setFreeResources(data.freeResources);
  };
  fetchConfig();
}, []);
```

## Common AWS Quota Codes

| Resource | Service Code | Quota Code | Default Limit |
|----------|--------------|------------|---------------|
| Instance Profiles | `iam` | `L-C07B4B0D` | 1000 |
| IAM Roles | `iam` | `L-FE177D64` | 5000 |
| VPCs | `vpc` | `L-F678F1CE` | 5 |
| Security Groups | `vpc` | `L-E79EC296` | 2500 |
| CloudFormation Stacks | `cloudformation` | `L-0485CB21` | 200 |
| EC2 Instances | `ec2` | `L-1216C47A` | Varies |
| Load Balancers | `elasticloadbalancing` | `L-53DA6B97` | 50 |

Find quota codes:
```bash
aws service-quotas list-service-quotas --service-code iam --output json | \
  jq '.Quotas[] | {Name: .QuotaName, Code: .QuotaCode}'
```

## Updating Configuration

### Update Costs (No Deployment Needed)
```yaml
nat_gateways:
  cost_per_month: 33.50  # Updated cost

metadata:
  last_cost_update: "2024-03-13"
```

### Change Warning Thresholds
```yaml
instance_profiles:
  warn_at_percent: 90  # Warn at 90% instead of 80%
```

### Add New Resource
```yaml
billed_resources:
  rds_instances:
    label: "RDS Instances"
    icon: "🗄️"
    default_threshold: 40
    use_aws_quota: true
    quota_service_code: "rds"
    quota_code: "L-78E853F4"
    cost_type: "variable"
```

Then add backend code to fetch RDS count in `/api/aws/usage`.

## Troubleshooting

### AWS Quota Fetch Fails

All resources show `quotaSource: "default"`

**Solutions**:
1. Check AWS CLI credentials: `aws sts get-caller-identity`
2. Add IAM permission: `servicequotas:GetServiceQuota`
3. Verify Service Quotas API available in region
4. Check network connectivity to AWS endpoints

### YAML Parse Error

Backend returns empty configuration.

**Solutions**:
1. Validate YAML: `python3 -c "import yaml; yaml.safe_load(open('config/aws_resource_config.yml'))"`
2. Check file exists at `config/aws_resource_config.yml` relative to project root

### Stale Quota Values

Quotas don't match current AWS account.

**Solutions**:
1. Restart backend to clear in-memory cache
2. Reduce `cache_duration_hours` in config

## Testing

```bash
# Test configuration loading
python3 -c "from aws_config_service import aws_config_service; \
  print(aws_config_service.get_resource_config_with_quotas())"

# Test AWS quota fetching
aws service-quotas get-service-quota \
  --service-code iam --quota-code L-C07B4B0D --region us-east-1

# Test API endpoint
curl http://localhost:8000/api/aws/usage-config | jq .
```
