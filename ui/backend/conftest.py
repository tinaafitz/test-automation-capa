"""
Shared pytest fixtures for backend tests.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure backend modules are importable
sys.path.insert(0, str(Path(__file__).parent))
# Ensure project root is importable (for agents etc.)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def tmp_config_dir(tmp_path):
    """Create a temporary vars directory with notification_config.yml."""
    vars_dir = tmp_path / "vars"
    vars_dir.mkdir()
    config = {
        "slack_enabled": True,
        "slack_webhook_url": "https://hooks.slack.com/test/webhook",
        "email_enabled": True,
        "smtp_server": "smtp.test.com",
        "smtp_port": 587,
        "smtp_username": "user@test.com",
        "smtp_password": "secret",
        "from_email": "noreply@test.com",
        "to_emails": ["admin@test.com"],
        "use_tls": True,
        "app_url": "http://localhost:3000",
    }
    import yaml
    with open(vars_dir / "notification_config.yml", "w") as f:
        yaml.dump(config, f)
    return tmp_path


@pytest.fixture
def tmp_aws_config(tmp_path):
    """Create a temporary AWS resource config YAML."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config = {
        "metadata": {"version": "1.0", "region": "us-east-1"},
        "billed_resources": {
            "vpc": {
                "label": "VPCs",
                "icon": "icon",
                "description": "VPCs",
                "default_threshold": 5,
                "use_aws_quota": False,
            }
        },
        "free_resources": {},
        "thresholds": {"safe": 70, "warning": 90, "critical": 90},
        "quota_settings": {
            "enabled": False,
            "cache_duration_hours": 24,
            "fallback_to_defaults": True,
        },
    }
    import yaml
    with open(config_dir / "aws_resource_config.yml", "w") as f:
        yaml.dump(config, f)
    return tmp_path


@pytest.fixture
def mock_subprocess():
    """Patch subprocess.run globally."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        yield mock_run
