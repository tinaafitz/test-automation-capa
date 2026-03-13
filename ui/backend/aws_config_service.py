"""
AWS Resource Configuration Service

Loads AWS resource configuration from YAML and fetches actual quotas from AWS.
Provides a hybrid approach: config file defaults + live AWS quota data.
"""

import os
import json
import yaml
import subprocess
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from pathlib import Path

class AWSConfigService:
    def __init__(self, config_path: str = "config/aws_resource_config.yml"):
        # Go up two levels from ui/backend/ to reach project root
        self.config_path = Path(__file__).parent.parent.parent / config_path
        self.quota_cache = {}
        self.quota_cache_time = {}

    def load_config(self) -> Dict[str, Any]:
        """Load AWS resource configuration from YAML file"""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading AWS config: {e}")
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """Fallback configuration if YAML fails to load"""
        return {
            "metadata": {"version": "1.0", "region": "us-east-1"},
            "billed_resources": {},
            "free_resources": {},
            "thresholds": {"safe": 70, "warning": 90, "critical": 90},
            "quota_settings": {
                "enabled": False,
                "cache_duration_hours": 24,
                "fallback_to_defaults": True
            }
        }

    def get_aws_quota(self, service_code: str, quota_code: str, region: str = "us-east-1") -> Optional[float]:
        """
        Fetch actual quota from AWS Service Quotas API

        Args:
            service_code: AWS service code (e.g., 'iam', 'ec2')
            quota_code: Quota code (e.g., 'L-C07B4B0D')
            region: AWS region

        Returns:
            Quota value or None if fetch fails
        """
        cache_key = f"{service_code}:{quota_code}:{region}"

        # Check cache
        if cache_key in self.quota_cache:
            cache_time = self.quota_cache_time.get(cache_key)
            if cache_time and (datetime.now() - cache_time).total_seconds() < 3600 * 24:
                print(f"Using cached quota for {cache_key}")
                return self.quota_cache[cache_key]

        try:
            print(f"Fetching AWS quota: {service_code}/{quota_code}")
            result = subprocess.run([
                "aws", "service-quotas", "get-service-quota",
                "--service-code", service_code,
                "--quota-code", quota_code,
                "--region", region,
                "--output", "json"
            ], capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                data = json.loads(result.stdout)
                quota_value = data.get("Quota", {}).get("Value")
                if quota_value is not None:
                    # Cache the result
                    self.quota_cache[cache_key] = float(quota_value)
                    self.quota_cache_time[cache_key] = datetime.now()
                    print(f"Quota fetched successfully: {quota_value}")
                    return float(quota_value)
            else:
                print(f"Failed to fetch quota: {result.stderr}")

        except Exception as e:
            print(f"Error fetching quota for {service_code}/{quota_code}: {e}")

        return None

    def get_resource_config_with_quotas(self) -> Dict[str, Any]:
        """
        Get resource configuration with actual AWS quotas where available

        Returns:
            Complete resource configuration with thresholds from AWS or defaults
        """
        config = self.load_config()
        quota_settings = config.get("quota_settings", {})

        if not quota_settings.get("enabled", True):
            print("AWS quota fetching disabled in config")
            return self._format_response(config)

        region = quota_settings.get("region", "us-east-1")

        # Process billed resources
        for key, resource in config.get("billed_resources", {}).items():
            if resource.get("use_aws_quota"):
                service_code = resource.get("quota_service_code")
                quota_code = resource.get("quota_code")

                if service_code and quota_code:
                    quota = self.get_aws_quota(service_code, quota_code, region)
                    if quota:
                        # Set threshold to warn_at_percent (default 80%) of actual quota
                        warn_percent = resource.get("warn_at_percent", 80) / 100
                        resource["threshold"] = int(quota * warn_percent)
                        resource["aws_quota_value"] = quota
                        resource["quota_source"] = "aws_api"
                    elif quota_settings.get("fallback_to_defaults", True):
                        resource["quota_source"] = "default"
                    else:
                        resource["threshold"] = None
                        resource["quota_source"] = "unavailable"
                else:
                    resource["quota_source"] = "default"
            else:
                resource["quota_source"] = "config"
                resource["threshold"] = resource.get("default_threshold")

        # Process free resources
        for key, resource in config.get("free_resources", {}).items():
            if resource.get("use_aws_quota"):
                service_code = resource.get("quota_service_code")
                quota_code = resource.get("quota_code")

                if service_code and quota_code:
                    quota = self.get_aws_quota(service_code, quota_code, region)
                    if quota:
                        # Set threshold to warn_at_percent (default 80%) of actual quota
                        warn_percent = resource.get("warn_at_percent", 80) / 100
                        resource["threshold"] = int(quota * warn_percent)
                        resource["aws_quota_value"] = quota
                        resource["quota_source"] = "aws_api"
                    elif quota_settings.get("fallback_to_defaults", True):
                        resource["quota_source"] = "default"
                    else:
                        resource["threshold"] = None
                        resource["quota_source"] = "unavailable"
                else:
                    resource["quota_source"] = "default"
            else:
                resource["quota_source"] = "config"
                resource["threshold"] = resource.get("default_threshold")

        return self._format_response(config)

    def _format_response(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Format configuration for API response"""
        billed = []
        free = []

        for key, resource in config.get("billed_resources", {}).items():
            billed.append({
                "key": key,
                "label": resource.get("label", key),
                "icon": resource.get("icon", "📊"),
                "description": resource.get("description", ""),
                "threshold": resource.get("threshold", resource.get("default_threshold", 10)),
                "costPerMonth": resource.get("cost_per_month"),
                "costType": resource.get("cost_type", "variable"),
                "costNotes": resource.get("cost_notes", ""),
                "quotaSource": resource.get("quota_source", "config"),
                "awsQuotaValue": resource.get("aws_quota_value")
            })

        for key, resource in config.get("free_resources", {}).items():
            free.append({
                "key": key,
                "label": resource.get("label", key),
                "icon": resource.get("icon", "📊"),
                "description": resource.get("description", ""),
                "threshold": resource.get("threshold", resource.get("default_threshold", 100)),
                "quotaSource": resource.get("quota_source", "config"),
                "awsQuotaValue": resource.get("aws_quota_value")
            })

        return {
            "success": True,
            "metadata": config.get("metadata", {}),
            "billedResources": billed,
            "freeResources": free,
            "thresholds": config.get("thresholds", {}),
            "timestamp": datetime.now().isoformat()
        }

# Create singleton instance
aws_config_service = AWSConfigService()
