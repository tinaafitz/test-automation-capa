"""Tests for AWSConfigService."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

from aws_config_service import AWSConfigService


@pytest.fixture
def aws_svc(tmp_path):
    """AWSConfigService with a temporary config file."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config = {
        "metadata": {"version": "1.0", "region": "us-east-1"},
        "billed_resources": {
            "vpc": {
                "label": "VPCs",
                "icon": "vpc-icon",
                "description": "Virtual Private Clouds",
                "default_threshold": 5,
                "use_aws_quota": False,
            },
            "nat_gw": {
                "label": "NAT Gateways",
                "icon": "nat-icon",
                "description": "NAT Gateways",
                "default_threshold": 5,
                "use_aws_quota": True,
                "quota_service_code": "vpc",
                "quota_code": "L-FE5A380F",
                "warn_at_percent": 80,
                "cost_per_month": 32,
                "cost_type": "variable",
                "cost_notes": "$0.045/hr",
            },
        },
        "free_resources": {
            "iam_roles": {
                "label": "IAM Roles",
                "icon": "iam-icon",
                "description": "IAM Roles",
                "default_threshold": 100,
                "use_aws_quota": True,
                "quota_service_code": "iam",
                "quota_code": "L-C07B4B0D",
                "warn_at_percent": 80,
            },
        },
        "thresholds": {"safe": 70, "warning": 90, "critical": 90},
        "quota_settings": {
            "enabled": True,
            "region": "us-east-1",
            "cache_duration_hours": 24,
            "fallback_to_defaults": True,
        },
    }
    with open(config_dir / "aws_resource_config.yml", "w") as f:
        yaml.dump(config, f)

    svc = AWSConfigService.__new__(AWSConfigService)
    svc.config_path = config_dir / "aws_resource_config.yml"
    svc.quota_cache = {}
    svc.quota_cache_time = {}
    return svc


class TestLoadConfig:
    def test_load_valid(self, aws_svc):
        config = aws_svc.load_config()
        assert config["metadata"]["version"] == "1.0"
        assert "vpc" in config["billed_resources"]

    def test_load_missing_file(self, tmp_path):
        svc = AWSConfigService.__new__(AWSConfigService)
        svc.config_path = tmp_path / "nonexistent.yml"
        svc.quota_cache = {}
        svc.quota_cache_time = {}
        config = svc.load_config()
        assert "metadata" in config  # default config

    def test_load_invalid_yaml(self, tmp_path):
        bad_file = tmp_path / "bad.yml"
        bad_file.write_text("{{invalid yaml")
        svc = AWSConfigService.__new__(AWSConfigService)
        svc.config_path = bad_file
        svc.quota_cache = {}
        svc.quota_cache_time = {}
        config = svc.load_config()
        assert "metadata" in config  # default config


class TestDefaultConfig:
    def test_has_required_keys(self, aws_svc):
        config = aws_svc._get_default_config()
        assert "metadata" in config
        assert "thresholds" in config
        assert config["quota_settings"]["enabled"] is False


class TestGetAwsQuota:
    @patch("aws_config_service.subprocess.run")
    def test_quota_success(self, mock_run, aws_svc):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"Quota": {"Value": 10.0}}),
        )
        result = aws_svc.get_aws_quota("vpc", "L-FE5A380F")
        assert result == 10.0

    def test_quota_cache_hit(self, aws_svc):
        aws_svc.quota_cache["vpc:L-FE5A380F:us-east-1"] = 15.0
        aws_svc.quota_cache_time["vpc:L-FE5A380F:us-east-1"] = datetime.now()
        result = aws_svc.get_aws_quota("vpc", "L-FE5A380F")
        assert result == 15.0

    def test_quota_cache_expired(self, aws_svc):
        aws_svc.quota_cache["vpc:L-FE5A380F:us-east-1"] = 15.0
        aws_svc.quota_cache_time["vpc:L-FE5A380F:us-east-1"] = datetime.now() - timedelta(hours=25)
        with patch("aws_config_service.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps({"Quota": {"Value": 20.0}}),
            )
            result = aws_svc.get_aws_quota("vpc", "L-FE5A380F")
            assert result == 20.0

    @patch("aws_config_service.subprocess.run")
    def test_quota_failure(self, mock_run, aws_svc):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="access denied")
        result = aws_svc.get_aws_quota("vpc", "L-FE5A380F")
        assert result is None

    @patch("aws_config_service.subprocess.run")
    def test_quota_exception(self, mock_run, aws_svc):
        mock_run.side_effect = Exception("network error")
        result = aws_svc.get_aws_quota("vpc", "L-FE5A380F")
        assert result is None


class TestGetResourceConfigWithQuotas:
    @patch("aws_config_service.subprocess.run")
    def test_with_aws_quotas(self, mock_run, aws_svc):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"Quota": {"Value": 10.0}}),
        )
        result = aws_svc.get_resource_config_with_quotas()
        assert result["success"] is True
        assert len(result["billedResources"]) == 2

    def test_quotas_disabled(self, aws_svc):
        config = aws_svc.load_config()
        config["quota_settings"]["enabled"] = False
        with patch.object(aws_svc, "load_config", return_value=config):
            result = aws_svc.get_resource_config_with_quotas()
            assert result["success"] is True


class TestFormatResponse:
    def test_format_basic(self, aws_svc):
        config = aws_svc.load_config()
        result = aws_svc._format_response(config)
        assert result["success"] is True
        assert "billedResources" in result
        assert "freeResources" in result
        assert "timestamp" in result
