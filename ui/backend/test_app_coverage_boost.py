"""
Tests for app.py coverage boost.
Targets the largest uncovered ranges to maximize coverage per test.
"""

import importlib
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock, mock_open

import pytest

# ---------------------------------------------------------------------------
# Module-level mocking (must happen before app import)
# ---------------------------------------------------------------------------

if "app_extensions" in sys.modules:
    if isinstance(sys.modules["app_extensions"], MagicMock):
        del sys.modules["app_extensions"]

sys.modules.setdefault(
    "app_extensions",
    MagicMock(
        register_health_endpoints=MagicMock(),
        register_monitoring_endpoints=MagicMock(),
    ),
)
sys.modules.setdefault("anthropic", MagicMock())

from fastapi.testclient import TestClient

with patch("subprocess.run", return_value=MagicMock(returncode=1, stdout="", stderr="")):
    with patch("subprocess.Popen"):
        if "app" in sys.modules:
            importlib.reload(sys.modules["app"])
        import app as app_module

client = TestClient(app_module.app)
jobs = app_module.jobs
clusters = app_module.clusters
ai_agent_sessions = app_module.ai_agent_sessions


def _make_job(job_id=None, **overrides):
    """Helper to create a job entry in the jobs dict."""
    jid = job_id or str(uuid.uuid4())
    job = {
        "id": jid,
        "status": "running",
        "progress": 0,
        "message": "In progress",
        "started_at": datetime.now(),
        "logs": [],
        "stdout": "",
        "stderr": "",
    }
    job.update(overrides)
    jobs[jid] = job
    return jid


# -----------------------------------------------------------------------
# _wait_for_resource_deletion  (lines 563-622)
# -----------------------------------------------------------------------

class TestWaitForResourceDeletion:
    """Tests for _wait_for_resource_deletion helper."""

    @patch("app.time.sleep", return_value=None)
    @patch("app.subprocess.run")
    def test_resource_deleted_immediately(self, mock_run, mock_sleep):
        from app import _wait_for_resource_deletion  # noqa
        job_id = _make_job()
        # returncode != 0 with "not found" in output
        mock_run.return_value = MagicMock(returncode=1, stderr="Error from server (NotFound): not found", stdout="")
        result = _wait_for_resource_deletion("rosacontrolplane", "test-cluster", "ns-rosa-hcp", job_id, timeout_seconds=30, poll_interval=10)
        assert result is True

    @patch("app.time.sleep", return_value=None)
    @patch("app.subprocess.run")
    def test_resource_timeout(self, mock_run, mock_sleep):
        from app import _wait_for_resource_deletion  # noqa
        job_id = _make_job()
        # Resource always exists
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="NAME  STATUS")
        result = _wait_for_resource_deletion("rosacontrolplane", "test-cluster", "ns-rosa-hcp", job_id, timeout_seconds=20, poll_interval=10)
        assert result is False

    @patch("app.time.sleep", return_value=None)
    @patch("app.subprocess.run")
    def test_resource_oc_error_retries(self, mock_run, mock_sleep):
        from app import _wait_for_resource_deletion  # noqa
        job_id = _make_job()
        # First call: unexpected error; second: not found
        mock_run.side_effect = [
            MagicMock(returncode=1, stderr="connection refused", stdout=""),
            MagicMock(returncode=1, stderr="not found", stdout=""),
        ]
        result = _wait_for_resource_deletion("rosacontrolplane", "test-cluster", "ns-rosa-hcp", job_id, timeout_seconds=30, poll_interval=10)
        assert result is True

    @patch("app.time.sleep", return_value=None)
    @patch("app.subprocess.run")
    def test_resource_timeout_expired(self, mock_run, mock_sleep):
        from app import _wait_for_resource_deletion  # noqa
        job_id = _make_job()
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="oc", timeout=10)
        result = _wait_for_resource_deletion("rosacontrolplane", "test-cluster", "ns-rosa-hcp", job_id, timeout_seconds=10, poll_interval=10)
        assert result is False

    @patch("app.time.sleep", return_value=None)
    @patch("app.subprocess.run")
    def test_resource_generic_exception(self, mock_run, mock_sleep):
        from app import _wait_for_resource_deletion  # noqa
        job_id = _make_job()
        mock_run.side_effect = Exception("boom")
        result = _wait_for_resource_deletion("rosacontrolplane", "test-cluster", "ns-rosa-hcp", job_id, timeout_seconds=10, poll_interval=10)
        assert result is False

    @patch("app.time.sleep", return_value=None)
    @patch("app.subprocess.run")
    def test_agent_session_fed(self, mock_run, mock_sleep):
        from app import _wait_for_resource_deletion  # noqa
        job_id = _make_job()
        monitor = MagicMock()
        ai_agent_sessions[job_id] = {"monitor": monitor}
        mock_run.return_value = MagicMock(returncode=1, stderr="not found", stdout="")
        _wait_for_resource_deletion("rosacontrolplane", "test-cluster", "ns-rosa-hcp", job_id, timeout_seconds=30, poll_interval=10)
        assert monitor.process_line.called


# -----------------------------------------------------------------------
# _run_deletion_wait_loops  (lines 625-682)
# -----------------------------------------------------------------------

class TestRunDeletionWaitLoops:
    """Tests for _run_deletion_wait_loops helper."""

    @patch("app._wait_for_resource_deletion")
    def test_all_deleted_success(self, mock_wait):
        from app import _run_deletion_wait_loops  # noqa
        job_id = _make_job()
        mock_wait.return_value = True
        result = _run_deletion_wait_loops(job_id, "test-cluster", "ns-rosa-hcp")
        assert result is True
        assert mock_wait.call_count == 3  # rcp, network, roles

    @patch("app._wait_for_resource_deletion")
    def test_rcp_fails(self, mock_wait):
        from app import _run_deletion_wait_loops  # noqa
        job_id = _make_job()
        mock_wait.return_value = False
        result = _run_deletion_wait_loops(job_id, "test-cluster", "ns-rosa-hcp")
        assert result is False
        assert mock_wait.call_count == 1  # Only rcp attempted

    @patch("app._wait_for_resource_deletion")
    def test_network_fails(self, mock_wait):
        from app import _run_deletion_wait_loops  # noqa
        job_id = _make_job()
        # rcp succeeds, network fails
        mock_wait.side_effect = [True, False]
        result = _run_deletion_wait_loops(job_id, "test-cluster", "ns-rosa-hcp")
        assert result is False

    @patch("app._wait_for_resource_deletion")
    def test_skip_network_and_roles(self, mock_wait):
        from app import _run_deletion_wait_loops  # noqa
        job_id = _make_job()
        mock_wait.return_value = True
        result = _run_deletion_wait_loops(job_id, "test-cluster", "ns-rosa-hcp", delete_network=False, delete_roles=False)
        assert result is True
        assert mock_wait.call_count == 1  # Only rcp


# -----------------------------------------------------------------------
# delete_rosa_cluster endpoint  (lines 3715-3770)
# -----------------------------------------------------------------------

# -----------------------------------------------------------------------
# MCE resources endpoint  (lines 3773-3907)
# -----------------------------------------------------------------------

class TestMCEResources:

    @patch("app.subprocess.run")
    def test_get_mce_resources_success(self, mock_run):
        # All oc calls return empty lists
        mock_run.return_value = MagicMock(returncode=0, stdout='{"items": []}', stderr="")
        resp = client.get("/api/mce/resources")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "resources" in data

    @patch("app.subprocess.run")
    def test_get_mce_resources_with_items(self, mock_run):
        items_json = json.dumps({"items": [{"metadata": {"name": "test-res", "namespace": "ns-rosa-hcp"}}]})
        yaml_output = "kind: ROSACluster\nname: test-res"
        mock_run.side_effect = [
            # awsclustercontrolleridentity from capa-system
            MagicMock(returncode=0, stdout=items_json, stderr=""),
            MagicMock(returncode=0, stdout=yaml_output, stderr=""),  # yaml fetch
            # rosacluster all ns
            MagicMock(returncode=0, stdout='{"items": []}', stderr=""),
            # rosanetwork all ns
            MagicMock(returncode=0, stdout='{"items": []}', stderr=""),
            # rosacontrolplane all ns
            MagicMock(returncode=0, stdout='{"items": []}', stderr=""),
            # rosaroleconfig all ns
            MagicMock(returncode=0, stdout='{"items": []}', stderr=""),
        ]
        resp = client.get("/api/mce/resources")
        data = resp.json()
        assert data["success"] is True
        assert data["count"] >= 1

    @patch("app.subprocess.run")
    def test_get_mce_resources_exception(self, mock_run):
        mock_run.side_effect = Exception("oc not found")
        resp = client.get("/api/mce/resources")
        data = resp.json()
        # Endpoint catches exceptions and returns success with partial data
        assert resp.status_code == 200


# -----------------------------------------------------------------------
# run_ansible_role endpoint  (lines 3910-4085)
# -----------------------------------------------------------------------

class TestRunAnsibleRole:

    @patch("app.subprocess.run")
    @patch("app.os.path.exists", return_value=True)
    @patch("app.os.unlink")
    def test_run_role_success(self, mock_unlink, mock_exists, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        resp = client.post("/api/ansible/run-role", json={
            "role_name": "configure-capa-environment",
            "description": "test role",
            "extra_vars": {"key": "val"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    @patch("app.os.path.exists", return_value=False)
    def test_run_role_not_found(self, mock_exists):
        resp = client.post("/api/ansible/run-role", json={"role_name": "nonexistent"})
        assert resp.status_code == 500

    def test_run_role_missing_name(self):
        resp = client.post("/api/ansible/run-role", json={})
        assert resp.status_code == 500

    @patch("app.subprocess.run")
    @patch("app.os.path.exists", return_value=True)
    @patch("app.os.unlink")
    def test_run_role_timeout(self, mock_unlink, mock_exists, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ansible-playbook", timeout=600)
        resp = client.post("/api/ansible/run-role", json={
            "role_name": "configure-capa-environment",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False


# -----------------------------------------------------------------------
# run_ansible_playbook endpoint  (lines 4299-4351)
# -----------------------------------------------------------------------

# TestRunAnsiblePlaybookEndpoint removed - already covered in test_app_deep_coverage.py
# and requires complex async mocking that causes hangs


# -----------------------------------------------------------------------
# AI Assistant chat endpoint  (lines 7877-8553)
# -----------------------------------------------------------------------

class TestAIAssistantChat:

    def test_auto_2(self):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "What clusters are running?",
            "context": {"clusters": [
                {"name": "test-cluster", "status": "ready", "namespace": "ns-rosa-hcp",
                 "region": "us-west-2", "version": "4.14.0", "created": "2024-01-01"}
            ]},
            "history": [],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "response" in data
        assert "test-cluster" in data["response"]

    def test_auto_3(self):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "What clusters are running?",
            "context": {"clusters": []},
            "history": [],
        })
        data = resp.json()
        assert "no" in data["response"].lower() or "don't have" in data["response"].lower()

    def test_auto_4(self):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "How to provision a new cluster?",
            "context": {"clusters": []},
            "history": [],
        })
        data = resp.json()
        assert "provision" in data["response"].lower() or "Provision" in data["response"]

    def test_auto_5(self):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "troubleshoot failed cluster",
            "context": {"clusters": [
                {"name": "bad-cluster", "status": "failed", "namespace": "ns-test"}
            ]},
            "history": [],
        })
        data = resp.json()
        assert "bad-cluster" in data["response"]
        assert "failed" in data["response"].lower() or "Troubleshoot" in data["response"]

    def test_auto_6(self):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "troubleshoot issues",
            "context": {"clusters": [
                {"name": "prov-cluster", "status": "provisioning", "namespace": "ns-test", "progress": 50}
            ]},
            "history": [],
        })
        data = resp.json()
        assert "prov-cluster" in data["response"]

    def test_auto_7(self):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "troubleshoot errors",
            "context": {"clusters": [
                {"name": "ok-cluster", "status": "ready", "namespace": "ns-test"}
            ]},
            "history": [],
        })
        data = resp.json()
        assert "don't see any failed" in data["response"].lower() or "Common issues" in data["response"]

    def test_auto_8(self):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "What is ROSA?",
            "context": {"clusters": []},
            "history": [],
        })
        data = resp.json()
        assert "ROSA" in data["response"]

    def test_auto_9(self):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "What is cluster api?",
            "context": {"clusters": []},
            "history": [],
        })
        data = resp.json()
        assert "CAPI" in data["response"] or "Cluster API" in data["response"]

    def test_auto_10(self):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "What is network automation?",
            "context": {"clusters": []},
            "history": [],
        })
        data = resp.json()
        assert "Network" in data["response"] or "VPC" in data["response"]

    def test_auto_11(self):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "What is role automation?",
            "context": {"clusters": []},
            "history": [],
        })
        data = resp.json()
        assert "Role" in data["response"] or "IAM" in data["response"]

    def test_auto_12(self):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "check environment status",
            "context": {"clusters": []},
            "history": [],
        })
        data = resp.json()
        assert "Environment" in data["response"] or "CAPI" in data["response"]

    def test_auto_13(self):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "how is the status?",
            "context": {"clusters": [
                {"name": "my-cluster", "status": "provisioning", "progress": 75}
            ]},
            "history": [],
        })
        data = resp.json()
        assert "my-cluster" in data["response"]

    def test_auto_14(self):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "monitoring status",
            "context": {"clusters": []},
            "history": [],
        })
        data = resp.json()
        assert "don't have any" in data["response"].lower() or "provision" in data["response"].lower()

    def test_auto_15(self):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "Tell me about test-cluster",
            "context": {"clusters": [
                {"name": "test-cluster", "status": "uninstalling", "namespace": "ns-rosa-hcp",
                 "region": "us-west-2", "version": "4.14.0", "created": "2024-01-01",
                 "domain_prefix": "test", "progress": 50}
            ]},
            "history": [],
        })
        data = resp.json()
        assert "UNINSTALLING" in data["response"]

    def test_auto_16(self):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "Tell me about test-cluster",
            "context": {"clusters": [
                {"name": "test-cluster", "status": "provisioning", "namespace": "ns-rosa-hcp",
                 "region": "us-west-2", "version": "4.14.0", "created": "2024-01-01",
                 "domain_prefix": "test", "progress": 30}
            ]},
            "history": [],
        })
        data = resp.json()
        assert "PROVISIONING" in data["response"]

    def test_auto_17(self):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "Tell me about test-cluster",
            "context": {"clusters": [
                {"name": "test-cluster", "status": "ready", "namespace": "ns-rosa-hcp",
                 "region": "us-west-2", "version": "4.14.0", "created": "2024-01-01",
                 "domain_prefix": "test"}
            ]},
            "history": [],
        })
        data = resp.json()
        assert "READY" in data["response"]

    def test_auto_18(self):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "Tell me about test-cluster",
            "context": {"clusters": [
                {"name": "test-cluster", "status": "unknown", "namespace": "ns-rosa-hcp",
                 "region": "us-west-2", "version": "4.14.0", "created": "2024-01-01",
                 "domain_prefix": "test"}
            ]},
            "history": [],
        })
        data = resp.json()
        assert "UNKNOWN" in data["response"]

    def test_auto_19(self):
        # Create a job so logs can be found
        job_id = _make_job(logs=["line1", "line2"], yaml_file="test-cluster.yml",
                           description="test op", created_at=datetime.now().isoformat())
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "show me the logs",
            "context": {"clusters": [
                {"name": "test-cluster", "status": "ready", "namespace": "ns-rosa-hcp"}
            ]},
            "history": [],
        })
        data = resp.json()
        assert "response" in data

    def test_auto_20(self):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "show me the logs",
            "context": {"clusters": []},
            "history": [],
        })
        data = resp.json()
        assert "couldn't find" in data["response"].lower() or "Logs will appear" in data["response"]

    def test_auto_21(self):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "tell me about bad-cluster",
            "context": {"clusters": [
                {"name": "bad-cluster", "status": "failed", "namespace": "ns-test",
                 "region": "us-east-1", "version": "4.14.0", "created": "2024-01-01"}
            ]},
            "history": [],
        })
        data = resp.json()
        assert "bad-cluster" in data["response"]
        assert "failed" in data["response"].lower() or "Troubleshooting" in data["response"]

    def test_auto_22(self):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "how is my-cluster doing?",
            "context": {"clusters": [
                {"name": "my-cluster", "status": "provisioning", "namespace": "ns-test",
                 "region": "us-east-1", "version": "4.14.0", "created": "2024-01-01",
                 "progress": 60}
            ]},
            "history": [],
        })
        data = resp.json()
        assert "my-cluster" in data["response"]

    def test_auto_23(self):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "tell me about my-cluster",
            "context": {"clusters": [
                {"name": "my-cluster", "status": "ready", "namespace": "ns-test",
                 "region": "us-east-1", "version": "4.14.0", "created": "2024-01-01"}
            ]},
            "history": [],
        })
        data = resp.json()
        assert "my-cluster" in data["response"]

    def test_auto_24(self):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "hello there",
            "context": {"clusters": []},
            "history": [],
        })
        data = resp.json()
        assert "response" in data
        assert "suggestions" in data


# TestTestSuiteEndpoints removed - already covered in test_app_clusters_suites.py


# -----------------------------------------------------------------------
# AWS resource details endpoint  (lines 10448-10877)
# -----------------------------------------------------------------------

class TestAWSResourceDetails:

    @patch("app.subprocess.run")
    def test_vpcs(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"Vpcs": [
                {"VpcId": "vpc-123", "CidrBlock": "10.0.0.0/16", "State": "available",
                 "IsDefault": False, "Tags": [{"Key": "Name", "Value": "my-vpc"}]}
            ]}),
            stderr=""
        )
        resp = client.get("/api/aws/resource-details/vpcs")
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 1
        assert data["details"][0]["id"] == "vpc-123"

    @patch("app.subprocess.run")
    def test_ec2_instances(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"Reservations": [
                {"Instances": [
                    {"InstanceId": "i-123", "InstanceType": "m5.xlarge",
                     "State": {"Name": "running"}, "VpcId": "vpc-123",
                     "SubnetId": "subnet-123", "PrivateIpAddress": "10.0.0.1",
                     "PublicIpAddress": "54.0.0.1", "LaunchTime": "2024-01-01",
                     "Tags": [{"Key": "Name", "Value": "test-instance"}]}
                ]}
            ]}),
            stderr=""
        )
        resp = client.get("/api/aws/resource-details/ec2_instances")
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 1

    @patch("app.subprocess.run")
    def test_ebs_volumes(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"Volumes": [
                {"VolumeId": "vol-123", "Size": 100, "VolumeType": "gp3",
                 "State": "in-use", "CreateTime": "2024-01-01",
                 "AvailabilityZone": "us-west-2a", "Encrypted": True,
                 "Attachments": [{"InstanceId": "i-123"}],
                 "Tags": [{"Key": "Name", "Value": "test-vol"}]}
            ]}),
            stderr=""
        )
        resp = client.get("/api/aws/resource-details/ebs_volumes")
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 1

    @patch("app.subprocess.run")
    def test_iam_roles(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"Roles": [
                {"RoleId": "role-123", "RoleName": "test-role", "Arn": "arn:aws:iam::role/test",
                 "CreateDate": "2024-01-01", "Path": "/", "Description": "test",
                 "MaxSessionDuration": 3600}
            ]}),
            stderr=""
        )
        resp = client.get("/api/aws/resource-details/iam_roles")
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 1

    @patch("app.subprocess.run")
    def test_instance_profiles(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"InstanceProfiles": [
                {"InstanceProfileId": "ip-123", "InstanceProfileName": "test-profile",
                 "Arn": "arn:aws:iam::instance-profile/test", "CreateDate": "2024-01-01",
                 "Path": "/", "Roles": [{"RoleName": "test-role"}]}
            ]}),
            stderr=""
        )
        resp = client.get("/api/aws/resource-details/instance_profiles")
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 1
        assert data["details"][0]["roles"] == ["test-role"]

    @patch("app.subprocess.run")
    def test_cloudformation_stacks(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps({"StackSummaries": [
                {"StackId": "stack-123", "StackName": "my-stack", "StackStatus": "CREATE_COMPLETE",
                 "CreationTime": "2024-01-01"},
                {"StackId": "stack-del", "StackName": "deleted-stack", "StackStatus": "DELETE_COMPLETE",
                 "CreationTime": "2024-01-01"},
            ]}), stderr=""),
            # describe-stacks for the non-deleted stack
            MagicMock(returncode=0, stdout=json.dumps({"Stacks": [
                {"StackName": "my-stack", "Description": "test stack",
                 "Tags": [{"Key": "env", "Value": "test"}]}
            ]}), stderr=""),
        ]
        resp = client.get("/api/aws/resource-details/cloudformation_stacks")
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 1  # DELETE_COMPLETE excluded

    @patch("app.subprocess.run")
    def test_route53_zones(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps({"HostedZones": [
                {"Id": "/hostedzone/Z123", "Name": "example.com.",
                 "ResourceRecordSetCount": 5,
                 "Config": {"PrivateZone": False, "Comment": "test zone"}}
            ]}), stderr=""),
            # tags for zone
            MagicMock(returncode=0, stdout=json.dumps({"ResourceTagSet": {"Tags": [
                {"Key": "env", "Value": "test"}
            ]}}), stderr=""),
        ]
        resp = client.get("/api/aws/resource-details/route53_zones")
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 1

    @patch("app.subprocess.run")
    def test_s3_buckets(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps({"Buckets": [
                {"Name": "my-bucket", "CreationDate": "2024-01-01"}
            ]}), stderr=""),
            # tags for bucket
            MagicMock(returncode=0, stdout=json.dumps({"TagSet": [
                {"Key": "env", "Value": "test"}
            ]}), stderr=""),
        ]
        resp = client.get("/api/aws/resource-details/s3_buckets")
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 1

    @patch("app.subprocess.run")
    def test_security_groups(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps({"SecurityGroups": [
                {"GroupId": "sg-123", "GroupName": "test-sg", "Description": "test",
                 "VpcId": "vpc-123",
                 "IpPermissions": [{"IpProtocol": "tcp"}],
                 "IpPermissionsEgress": [{"IpProtocol": "-1"}],
                 "Tags": [{"Key": "Name", "Value": "test-sg"}]}
            ]}), stderr=""),
            # vpc name lookup
            MagicMock(returncode=0, stdout=json.dumps({"Vpcs": [
                {"Tags": [{"Key": "Name", "Value": "my-vpc"}]}
            ]}), stderr=""),
        ]
        resp = client.get("/api/aws/resource-details/security_groups")
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 1
        assert data["details"][0]["vpc_name"] == "my-vpc"

    @patch("app.subprocess.run")
    def test_load_balancers(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps({"LoadBalancers": [
                {"LoadBalancerArn": "arn:aws:elasticloadbalancing:us-west-2:123:loadbalancer/app/my-lb/abc",
                 "LoadBalancerName": "my-lb", "Type": "application",
                 "Scheme": "internet-facing", "State": {"Code": "active"},
                 "DNSName": "my-lb.elb.amazonaws.com", "VpcId": "vpc-123",
                 "CreatedTime": "2024-01-01"}
            ]}), stderr=""),
            # tags
            MagicMock(returncode=0, stdout=json.dumps({"TagDescriptions": [
                {"Tags": [{"Key": "env", "Value": "test"}]}
            ]}), stderr=""),
            # vpc name
            MagicMock(returncode=0, stdout=json.dumps({"Vpcs": [
                {"Tags": [{"Key": "Name", "Value": "my-vpc"}]}
            ]}), stderr=""),
        ]
        resp = client.get("/api/aws/resource-details/load_balancers")
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 1

    @patch("app.subprocess.run")
    def test_nat_gateways(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps({"NatGateways": [
                {"NatGatewayId": "nat-123", "VpcId": "vpc-123", "SubnetId": "subnet-123",
                 "State": "available", "CreateTime": "2024-01-01",
                 "NatGatewayAddresses": [{"PublicIp": "54.0.0.1"}],
                 "Tags": [{"Key": "Name", "Value": "my-nat"}]}
            ]}), stderr=""),
            # vpc name
            MagicMock(returncode=0, stdout=json.dumps({"Vpcs": [
                {"Tags": [{"Key": "Name", "Value": "my-vpc"}]}
            ]}), stderr=""),
        ]
        resp = client.get("/api/aws/resource-details/nat_gateways")
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 1

    @patch("app.subprocess.run")
    def test_resource_error(self, mock_run):
        mock_run.side_effect = Exception("AWS CLI not found")
        resp = client.get("/api/aws/resource-details/vpcs")
        data = resp.json()
        assert data["success"] is False


# -----------------------------------------------------------------------
# AWS single resource usage  (lines 10386-10445)
# -----------------------------------------------------------------------

class TestSingleResourceUsage:

    @patch("app.subprocess.run")
    def test_nat_gateways_count(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"NatGateways": [
                {"State": "available"}, {"State": "deleted"}
            ]})
        )
        resp = client.get("/api/aws/usage/nat_gateways")
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 1

    @patch("app.subprocess.run")
    def test_route53_zones_count(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"HostedZones": [{"Id": "z1"}, {"Id": "z2"}]})
        )
        resp = client.get("/api/aws/usage/route53_zones")
        data = resp.json()
        assert data["count"] == 2

    @patch("app.subprocess.run")
    def test_vpcs_count(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"Vpcs": [{"VpcId": "v1"}]})
        )
        resp = client.get("/api/aws/usage/vpcs")
        data = resp.json()
        assert data["count"] == 1

    @patch("app.subprocess.run")
    def test_ec2_instances_count(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"Reservations": [
                {"Instances": [{"InstanceId": "i-1"}, {"InstanceId": "i-2"}]}
            ]})
        )
        resp = client.get("/api/aws/usage/ec2_instances")
        data = resp.json()
        assert data["count"] == 2

    @patch("app.subprocess.run")
    def test_ebs_volumes_count(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"Volumes": [{"VolumeId": "v1"}]})
        )
        resp = client.get("/api/aws/usage/ebs_volumes")
        data = resp.json()
        assert data["count"] == 1

    @patch("app.subprocess.run")
    def test_iam_roles_count(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"Roles": [{"RoleName": "r1"}]})
        )
        resp = client.get("/api/aws/usage/iam_roles")
        data = resp.json()
        assert data["count"] == 1

    @patch("app.subprocess.run")
    def test_security_groups_count(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"SecurityGroups": [{"GroupId": "sg-1"}]})
        )
        resp = client.get("/api/aws/usage/security_groups")
        data = resp.json()
        assert data["count"] == 1

    @patch("app.subprocess.run")
    def test_load_balancers_count(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"LoadBalancers": [{"Arn": "a1"}, {"Arn": "a2"}]})
        )
        resp = client.get("/api/aws/usage/load_balancers")
        data = resp.json()
        assert data["count"] == 2

    @patch("app.subprocess.run")
    def test_s3_buckets_count(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"Buckets": [{"Name": "b1"}]})
        )
        resp = client.get("/api/aws/usage/s3_buckets")
        data = resp.json()
        assert data["count"] == 1

    @patch("app.subprocess.run")
    def test_cloudformation_count(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"StackSummaries": [
                {"StackStatus": "CREATE_COMPLETE"},
                {"StackStatus": "DELETE_COMPLETE"},
            ]})
        )
        resp = client.get("/api/aws/usage/cloudformation_stacks")
        data = resp.json()
        assert data["count"] == 1

    @patch("app.subprocess.run")
    def test_instance_profiles_count(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"InstanceProfiles": [{"Name": "p1"}]})
        )
        resp = client.get("/api/aws/usage/instance_profiles")
        data = resp.json()
        assert data["count"] == 1

    def test_auto_25(self):
        resp = client.get("/api/aws/usage/unknown_type")
        data = resp.json()
        assert data["success"] is False

    @patch("app.subprocess.run")
    def test_exception_handling(self, mock_run):
        mock_run.side_effect = Exception("AWS CLI error")
        resp = client.get("/api/aws/usage/vpcs")
        data = resp.json()
        assert data["success"] is False


