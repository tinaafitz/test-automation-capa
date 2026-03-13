# AWS Usage Dashboard - Hybrid Configuration Approach

## Overview

The AWS Usage Dashboard now uses a **hybrid approach** for resource thresholds and costs:
- **Configuration file** (`config/aws_resource_config.yml`) - Default values, costs, descriptions
- **AWS Service Quotas API** - Live quota data from your AWS account
- **Automatic fallback** - Uses defaults if AWS API unavailable

## Benefits

### Before (Hardcoded)
```javascript
// Frontend code
const billedResources = [
  {
    threshold: 800,  // Assumes 1000 instance profile limit for ALL accounts
    costPerMonth: 32.40  // Hardcoded cost, requires code changes to update
  }
];
```

**Problems**:
❌ Inaccurate for accounts with different quotas
❌ Costs go stale as AWS pricing changes
❌ Requires code deployment to update values
❌ No visibility into quota source

### After (Hybrid)
```yaml
# config/aws_resource_config.yml
instance_profiles:
  default_threshold: 800
  use_aws_quota: true           # Fetch actual quota from AWS
  quota_service_code: "iam"
  quota_code: "L-C07B4B0D"      # AWS quota identifier
  warn_at_percent: 80           # Warn at 80% of actual quota
```

**Benefits**:
✅ Uses your account's actual quotas
✅ Easy to update costs without deployment
✅ Graceful fallback to defaults
✅ Tracks quota source (config vs AWS API)
✅ Configurable warning thresholds

## Configuration File Structure

### Location
```
test-automation-capa/
  config/
    aws_resource_config.yml  # Main configuration
```

### Configuration Sections

#### 1. Metadata
```yaml
metadata:
  version: "1.0"
  last_cost_update: "2024-01-15"  # When costs were last verified
  region: "us-east-1"
  notes: "Costs based on AWS pricing as of January 2024"
```

#### 2. Billed Resources
Resources that incur AWS charges:

```yaml
billed_resources:
  nat_gateways:
    label: "NAT Gateways"
    icon: "🌉"
    description: "Network address translation gateways"
    default_threshold: 10              # Used if AWS quota unavailable
    use_aws_quota: false               # No quota API for NAT Gateways
    cost_per_month: 32.40              # Fixed monthly cost
    cost_type: "fixed"                 # or "variable"
    cost_notes: "Base charge + data processing"
```

#### 3. Free Resources
Resources with no direct cost (quota management only):

```yaml
free_resources:
  instance_profiles:
    label: "Instance Profiles"
    icon: "🔖"
    description: "IAM instance profiles for EC2 instances"
    default_threshold: 800             # Default if quota fetch fails
    use_aws_quota: true                # ⭐ Fetch from AWS API
    quota_service_code: "iam"          # AWS service code
    quota_code: "L-C07B4B0D"          # Specific quota code
    warn_at_percent: 80                # Warn at 80% of quota
```

#### 4. Quota Settings
```yaml
quota_settings:
  enabled: true                       # Enable AWS quota fetching
  cache_duration_hours: 24            # Cache quotas for 24 hours
  fallback_to_defaults: true          # Use defaults if fetch fails
  region: "us-east-1"                 # Region for quota queries
```

## How It Works

### Flow Diagram
```
User clicks "Refresh Data"
         ↓
Frontend: GET /api/aws/usage-config
         ↓
Backend loads YAML config
         ↓
For each resource with use_aws_quota: true
    ↓
    Try fetch from AWS Service Quotas API
    ├─ Success → threshold = quota × warn_at_percent
    └─ Failure → threshold = default_threshold
         ↓
Return config to frontend
         ↓
Frontend: GET /api/aws/usage (actual counts)
         ↓
Display with thresholds from config
```

### Example: Instance Profiles

**Configuration**:
```yaml
instance_profiles:
  default_threshold: 800
  use_aws_quota: true
  quota_code: "L-C07B4B0D"
  warn_at_percent: 80
```

**AWS API Response**:
```json
{
  "Quota": {
    "Value": 1000.0  // Your account limit
  }
}
```

**Calculated Threshold**:
```
threshold = 1000 × 0.80 = 800 (warn at 80% capacity)
```

**UI Display**:
```
Instance Profiles: 640 / 1000
Status: ⚠️ Warning (80% used - approaching limit)
Quota Source: AWS API
```

## Backend Implementation

### New Service: `aws_config_service.py`

Located at `ui/backend/aws_config_service.py`:

```python
from aws_config_service import aws_config_service

# Get configuration with AWS quotas
config = aws_config_service.get_resource_config_with_quotas()

# Response includes:
# - billedResources: Resources with costs
# - freeResources: Quota-only resources
# - thresholds: Warning levels
# - quotaSource: "aws_api", "config", or "default"
```

### Caching Strategy

- **Duration**: 24 hours (configurable)
- **Purpose**: Avoid excessive AWS API calls
- **Cache Key**: `service_code:quota_code:region`
- **Refresh**: Automatic after cache expires

### Error Handling

```python
try:
    quota = get_aws_quota("iam", "L-C07B4B0D")
except Exception:
    if fallback_to_defaults:
        quota = default_threshold  # Use config value
    else:
        quota = None  # Mark as unavailable
```

## Frontend Integration

### Update `AWSUsageDashboard.jsx`

**Before** (hardcoded):
```javascript
const billedResources = [
  { key: 'nat_gateways', threshold: 10, costPerMonth: 32.40 }
];
```

**After** (from API):
```javascript
const [resourceConfig, setResourceConfig] = useState(null);

useEffect(() => {
  // Fetch configuration from backend
  fetch('http://localhost:8000/api/aws/usage-config')
    .then(res => res.json())
    .then(data => {
      setResourceConfig(data);
      setBilledResources(data.billedResources);
      setFreeResources(data.freeResources);
    });
}, []);
```

## AWS Service Quota Codes

### How to Find Quota Codes

```bash
# List all quotas for a service
aws service-quotas list-service-quotas \
  --service-code iam \
  --output json | jq '.Quotas[] | {Name: .QuotaName, Code: .QuotaCode}'

# Example output:
{
  "Name": "Instance profiles",
  "Code": "L-C07B4B0D"
}
```

### Common Quota Codes

| Resource | Service Code | Quota Code | Default Limit |
|----------|--------------|------------|---------------|
| Instance Profiles | `iam` | `L-C07B4B0D` | 1000 |
| IAM Roles | `iam` | `L-FE177D64` | 5000 |
| VPCs | `vpc` | `L-F678F1CE` | 5 |
| Security Groups | `vpc` | `L-E79EC296` | 2500 per VPC |
| CloudFormation Stacks | `cloudformation` | `L-0485CB21` | 200 |
| EC2 Instances | `ec2` | `L-1216C47A` | Varies |
| Load Balancers | `elasticloadbalancing` | `L-53DA6B97` | 50 |

## Updating Configuration

### Change Cost Values

```yaml
# Edit config/aws_resource_config.yml
nat_gateways:
  cost_per_month: 33.00  # Updated cost

metadata:
  last_cost_update: "2024-03-13"  # Track when updated
```

**No code deployment needed!** Backend will use new values on next request.

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
    description: "Relational database instances"
    default_threshold: 40
    use_aws_quota: true
    quota_service_code: "rds"
    quota_code: "L-78E853F4"
    cost_type: "variable"
```

Then add backend code to fetch RDS instance count in `/api/aws/usage`.

### Disable AWS Quota Fetching

```yaml
quota_settings:
  enabled: false  # Use defaults only
```

## Testing

### 1. Test Configuration Loading

```bash
# From backend directory
python3 -c "
from aws_config_service import aws_config_service
config = aws_config_service.get_resource_config_with_quotas()
print(config)
"
```

### 2. Test AWS Quota Fetching

```bash
# Check if AWS CLI can fetch quotas
aws service-quotas get-service-quota \
  --service-code iam \
  --quota-code L-C07B4B0D \
  --region us-east-1
```

### 3. Test API Endpoint

```bash
curl http://localhost:8000/api/aws/usage-config | jq .
```

### 4. Verify Frontend

1. Open AWS Usage Dashboard
2. Click "Refresh Data"
3. Check browser console for quota source:
   ```javascript
   quotaSource: "aws_api"  // ✅ Using live AWS quotas
   quotaSource: "config"   // Using config defaults
   quotaSource: "default"  // Fallback (AWS fetch failed)
   ```

## Troubleshooting

### Issue: AWS Quota Fetch Fails

**Symptoms**:
- All resources show `quotaSource: "default"`
- Backend logs show quota fetch errors

**Solutions**:
1. **Check AWS CLI credentials**:
   ```bash
   aws sts get-caller-identity
   ```

2. **Check IAM permissions**:
   Add `servicequotas:GetServiceQuota` permission

3. **Verify region**:
   Service Quotas API may not be available in all regions

4. **Check network**:
   Ensure backend can reach AWS API endpoints

### Issue: YAML Parse Error

**Symptoms**:
- Backend returns empty configuration
- Error in logs: "Error loading AWS config"

**Solutions**:
1. **Validate YAML syntax**:
   ```bash
   python3 -c "import yaml; yaml.safe_load(open('config/aws_resource_config.yml'))"
   ```

2. **Check file path**:
   Ensure `config/aws_resource_config.yml` exists relative to backend

### Issue: Stale Quota Values

**Symptoms**:
- Quota limits don't match current AWS account

**Solutions**:
1. **Clear cache** (restart backend):
   ```bash
   # Cache is in-memory, restarting clears it
   ```

2. **Reduce cache duration**:
   ```yaml
   quota_settings:
     cache_duration_hours: 1  # Cache for 1 hour instead of 24
   ```

## Migration from Hardcoded

### Steps

1. ✅ **Created** `config/aws_resource_config.yml`
2. ✅ **Created** `ui/backend/aws_config_service.py`
3. ⏳ **TODO**: Add API endpoint to `ui/backend/app.py`
4. ⏳ **TODO**: Update frontend to fetch config from API
5. ⏳ **TODO**: Remove hardcoded resource arrays from frontend

### Backward Compatibility

The frontend can work with either approach:
- **Old**: Hardcoded arrays (still functional)
- **New**: API-driven config (better)

Both can coexist during migration.

## Cost Updates

When AWS pricing changes:

1. Update `config/aws_resource_config.yml`:
   ```yaml
   nat_gateways:
     cost_per_month: 33.50  # New price

   metadata:
     last_cost_update: "2024-03-13"
   ```

2. No code deployment needed
3. Users see updated costs on next "Refresh Data"

## Future Enhancements

- [ ] Fetch costs from AWS Pricing API (complex but accurate)
- [ ] Regional cost variations
- [ ] Reserved instance pricing
- [ ] Cost optimization recommendations
- [ ] Historical usage tracking
- [ ] Budget alerts based on thresholds
- [ ] Multi-account support

## Summary

The hybrid approach provides:

✅ **Accuracy** - Uses your account's actual quotas
✅ **Flexibility** - Easy to update without code changes
✅ **Reliability** - Graceful fallback to defaults
✅ **Transparency** - Shows quota source in UI
✅ **Maintainability** - Single config file for all settings

Perfect for managing AWS resources at scale!
