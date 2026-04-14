#!/usr/bin/env python3
"""Tests for the CAPA CLI tool."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import pytest
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path so we can import from the capa script
PROJECT_ROOT = Path(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(PROJECT_ROOT))

# Import from the capa module (it's a script without .py extension)
# We create a symlink with .py extension for importlib to work
import importlib.util
import shutil

_capa_py = PROJECT_ROOT / "capa.py"
_needs_cleanup = False
if not _capa_py.exists():
    os.symlink(PROJECT_ROOT / "capa", _capa_py)
    _needs_cleanup = True

_spec = importlib.util.spec_from_file_location("capa_cli", _capa_py)
capa_cli = importlib.util.module_from_spec(_spec)
capa_cli.__name__ = "capa_cli"  # Prevent main() from running
_spec.loader.exec_module(capa_cli)

if _needs_cleanup:
    os.unlink(_capa_py)

FeatureRegistry = capa_cli.FeatureRegistry
ClusterAutomationSpec = capa_cli.ClusterAutomationSpec
ExecutionEngine = capa_cli.ExecutionEngine
C = capa_cli.C
load_spec = capa_cli.load_spec
_validate_feature_value = capa_cli._validate_feature_value_exit
_validate_feature_value_check = capa_cli._validate_feature_value_check

# Also import the shared core validation for direct testing
from capa_core import validate_feature_value


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def registry():
    """Load the real feature registry."""
    return FeatureRegistry(PROJECT_ROOT)


@pytest.fixture
def minimal_registry(tmp_path):
    """Create a minimal feature registry for isolated tests."""
    registry_data = {
        "version": "1.0",
        "var_map": {
            "private_network": "private",
            "channel_group": "channel_group",
        },
        "dependencies": {
            "machine_pool_upgrade": ["control_plane_upgrade"],
        },
        "sequences": {
            "upgrade": {
                "description": "Full cluster upgrade",
                "steps": [
                    {"feature": "control_plane_upgrade", "wait": True},
                    {"feature": "machine_pool_upgrade", "wait": True},
                ],
            },
        },
        "suites": [
            {
                "id": "test-suite",
                "name": "Test Suite",
                "description": "Test features",
                "category": "Testing",
                "phase": "Day2",
                "icon": "test",
                "features": [
                    {
                        "id": "channel_group",
                        "name": "Channel Group",
                        "description": "Update channel",
                        "type": "select",
                        "options": ["stable", "fast", "candidate"],
                        "mutable": True,
                        "applies_to": ["create", "apply", "upgrade"],
                        "default": "stable",
                        "k8s_field": ".spec.channelGroup",
                        "resource": "ROSAControlPlane",
                    },
                    {
                        "id": "control_plane_upgrade",
                        "name": "Control Plane Upgrade",
                        "description": "Upgrade CP",
                        "type": "version",
                        "mutable": True,
                        "applies_to": ["apply", "upgrade"],
                        "default": "",
                        "k8s_field": ".spec.version",
                        "resource": "ROSAControlPlane",
                        "playbook": "playbooks/upgrade_rosa_control_plane.yml",
                        "wait_timeout": 3600,
                    },
                    {
                        "id": "machine_pool_upgrade",
                        "name": "Machine Pool Upgrade",
                        "description": "Upgrade MP",
                        "type": "version",
                        "mutable": True,
                        "applies_to": ["apply", "upgrade"],
                        "default": "",
                        "k8s_field": ".spec.version",
                        "resource": "ROSAMachinePool",
                        "playbook": "playbooks/upgrade_rosa_machine_pool.yml",
                        "wait_timeout": 3600,
                        "depends_on": "control_plane_upgrade",
                    },
                    {
                        "id": "immutable_feat",
                        "name": "Immutable Feature",
                        "description": "Cannot change",
                        "type": "boolean",
                        "mutable": False,
                        "applies_to": ["create"],
                        "default": False,
                        "k8s_field": ".spec.immutable",
                        "resource": "ROSAControlPlane",
                    },
                ],
            },
        ],
    }
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir()
    with open(schemas_dir / "feature-registry.yml", "w") as f:
        yaml.dump(registry_data, f)
    return FeatureRegistry(tmp_path)


def make_spec(action="apply", cluster="test-cluster", **kwargs):
    """Helper to build a ClusterAutomationSpec dict."""
    data = {
        "apiVersion": "capa-automation/v1",
        "kind": "ClusterAutomationSpec",
        "metadata": {"name": "test-spec"},
        "spec": {"action": action, "cluster": cluster, **kwargs},
    }
    return data


# ============================================================================
# FeatureRegistry Tests
# ============================================================================

class TestFeatureRegistry:
    def test_loads_all_suites(self, registry):
        assert len(registry.suites) == 9

    def test_loads_all_features(self, registry):
        assert len(registry.all_features()) == 26

    def test_get_feature_exists(self, registry):
        feat = registry.get_feature("channel_group")
        assert feat is not None
        assert feat["name"] == "Channel Group"
        assert feat["type"] == "select"

    def test_get_feature_not_found(self, registry):
        assert registry.get_feature("nonexistent") is None

    def test_var_map(self, registry):
        vm = registry.var_map
        assert vm["private_network"] == "private"
        assert vm["byon"] == "byon_vpc"
        assert vm["disk_size"] == "root_volume_size"

    def test_resolve_var_mapped(self, registry):
        assert registry.resolve_var("private_network") == "private"

    def test_resolve_var_unmapped(self, registry):
        # Features without a var_map entry return their ID
        assert registry.resolve_var("node_labels") == "node_labels"

    def test_dependencies(self, registry):
        deps = registry.dependencies
        assert "machine_pool_upgrade" in deps
        assert "control_plane_upgrade" in deps["machine_pool_upgrade"]

    def test_get_deps(self, registry):
        assert registry.get_deps("machine_pool_upgrade") == ["control_plane_upgrade"]
        assert registry.get_deps("channel_group") == []

    def test_sequences(self, registry):
        seqs = registry.sequences
        assert "upgrade" in seqs
        assert "provision" in seqs
        assert "delete" in seqs

    def test_suite_metadata(self, registry):
        for suite in registry.suites:
            assert "id" in suite
            assert "name" in suite
            assert "phase" in suite
            assert "features" in suite

    def test_feature_has_applies_to(self, registry):
        for feat_id, feat in registry.all_features().items():
            assert "applies_to" in feat, f"Feature {feat_id} missing applies_to"

    def test_no_duplicate_feature_ids(self, registry):
        ids = []
        for suite in registry.suites:
            for feat in suite["features"]:
                ids.append(feat["id"])
        assert len(ids) == len(set(ids)), f"Duplicate feature IDs: {[x for x in ids if ids.count(x) > 1]}"

    def test_disk_volume_size_removed(self, registry):
        """disk_volume_size was a duplicate of disk_size and should be removed."""
        assert registry.get_feature("disk_volume_size") is None
        assert registry.get_feature("disk_size") is not None

    def test_minimal_registry(self, minimal_registry):
        assert len(minimal_registry.all_features()) == 4
        assert minimal_registry.get_feature("channel_group") is not None
        assert minimal_registry.resolve_var("private_network") == "private"


# ============================================================================
# ClusterAutomationSpec Tests
# ============================================================================

class TestClusterAutomationSpec:
    def test_basic_creation(self):
        data = make_spec(action="create", cluster="my-cluster")
        spec = ClusterAutomationSpec(data)
        assert spec.action == "create"
        assert spec.cluster == "my-cluster"
        assert spec.name == "test-spec"

    def test_invalid_api_version(self):
        data = make_spec()
        data["apiVersion"] = "wrong/v1"
        with pytest.raises(ValueError, match="Unsupported apiVersion"):
            ClusterAutomationSpec(data)

    def test_invalid_kind(self):
        data = make_spec()
        data["kind"] = "WrongKind"
        with pytest.raises(ValueError, match="Unsupported kind"):
            ClusterAutomationSpec(data)

    def test_defaults(self):
        data = make_spec()
        spec = ClusterAutomationSpec(data)
        assert spec.namespace == "ns-rosa-hcp"
        assert spec.region == "us-west-2"
        assert spec.channel == "stable"
        assert spec.version == ""
        assert spec.name_prefix == ""
        assert spec.features == {}
        assert spec.actions == []

    def test_overrides_cluster(self):
        data = make_spec(cluster="original")
        spec = ClusterAutomationSpec(data, overrides={"cluster": "override"})
        assert spec.cluster == "override"

    def test_overrides_version(self):
        data = make_spec()
        spec = ClusterAutomationSpec(data, overrides={"version": "4.20.12"})
        assert spec.version == "4.20.12"

    def test_overrides_namespace(self):
        data = make_spec()
        spec = ClusterAutomationSpec(data, overrides={"namespace": "custom-ns"})
        assert spec.namespace == "custom-ns"

    def test_overrides_feature_prefix(self):
        data = make_spec()
        spec = ClusterAutomationSpec(data, overrides={"feature.channel_group": "fast"})
        assert spec.features["channel_group"] == "fast"

    def test_overrides_generic_key_goes_to_features(self):
        data = make_spec()
        spec = ClusterAutomationSpec(data, overrides={"channel_group": "fast"})
        assert spec.features["channel_group"] == "fast"

    def test_actions_list(self):
        data = make_spec(actions=[
            {"feature": "channel_group", "value": "fast"},
            {"feature": "control_plane_upgrade", "value": "4.20.12"},
        ])
        spec = ClusterAutomationSpec(data)
        assert len(spec.actions) == 2
        assert spec.actions[0]["feature"] == "channel_group"

    def test_profile_from_metadata(self):
        data = make_spec()
        data["metadata"]["profile"] = "ha-production"
        spec = ClusterAutomationSpec(data)
        assert spec.profile == "ha-production"

    def test_features_dict(self):
        data = make_spec(features={"private_network": True, "channel_group": "fast"})
        spec = ClusterAutomationSpec(data)
        assert spec.features["private_network"] is True
        assert spec.features["channel_group"] == "fast"


# ============================================================================
# ExecutionEngine Plan Tests
# ============================================================================

class TestExecutionEnginePlan:
    def test_plan_create(self, minimal_registry, tmp_path):
        data = make_spec(action="create", cluster="", name_prefix="test1",
                         features={"channel_group": "fast"})
        spec = ClusterAutomationSpec(data)
        engine = ExecutionEngine(minimal_registry, tmp_path, dry_run=True)
        plan = engine.plan(spec)

        assert len(plan) == 1
        assert plan[0]["type"] == "playbook"
        assert plan[0]["playbook"] == "playbooks/create_rosa_hcp_cluster.yml"
        assert plan[0]["extra_vars"]["name_prefix"] == "test1"
        assert plan[0]["extra_vars"]["channel_group"] == "fast"

    def test_plan_create_uses_var_map(self, minimal_registry, tmp_path):
        data = make_spec(action="create", cluster="", name_prefix="test1",
                         features={"private_network": True})
        spec = ClusterAutomationSpec(data)
        engine = ExecutionEngine(minimal_registry, tmp_path, dry_run=True)
        plan = engine.plan(spec)

        # private_network should be mapped to "private" via var_map
        assert plan[0]["extra_vars"]["private"] is True
        assert "private_network" not in plan[0]["extra_vars"]

    def test_plan_upgrade(self, minimal_registry, tmp_path):
        data = make_spec(action="upgrade", cluster="my-cluster", version="4.20.12")
        data["spec"]["version"] = "4.20.12"
        spec = ClusterAutomationSpec(data)
        engine = ExecutionEngine(minimal_registry, tmp_path, dry_run=True)
        plan = engine.plan(spec)

        assert len(plan) == 2
        assert plan[0]["name"] == "Upgrade control plane to 4.20.12"
        assert plan[0]["feature"] == "control_plane_upgrade"
        assert plan[1]["name"] == "Upgrade machine pool to 4.20.12"
        assert plan[1]["feature"] == "machine_pool_upgrade"
        assert plan[1]["depends_on"] == "control_plane_upgrade"

    def test_plan_upgrade_requires_cluster(self, minimal_registry, tmp_path):
        data = make_spec(action="upgrade", cluster="")
        data["spec"]["version"] = "4.20.12"
        spec = ClusterAutomationSpec(data)
        engine = ExecutionEngine(minimal_registry, tmp_path, dry_run=True)
        with pytest.raises(ValueError, match="upgrade requires --cluster"):
            engine.plan(spec)

    def test_plan_upgrade_requires_version(self, minimal_registry, tmp_path):
        data = make_spec(action="upgrade", cluster="my-cluster")
        spec = ClusterAutomationSpec(data)
        engine = ExecutionEngine(minimal_registry, tmp_path, dry_run=True)
        with pytest.raises(ValueError, match="upgrade requires --version"):
            engine.plan(spec)

    def test_plan_apply_with_patch(self, minimal_registry, tmp_path):
        data = make_spec(action="apply", cluster="my-cluster",
                         actions=[{"feature": "channel_group", "value": "fast"}])
        spec = ClusterAutomationSpec(data)
        engine = ExecutionEngine(minimal_registry, tmp_path, dry_run=True)
        plan = engine.plan(spec)

        assert len(plan) == 1
        assert plan[0]["type"] == "patch"
        assert plan[0]["resource"] == "ROSAControlPlane"
        assert plan[0]["k8s_field"] == ".spec.channelGroup"
        assert plan[0]["value"] == "fast"

    def test_plan_apply_with_playbook(self, minimal_registry, tmp_path):
        data = make_spec(action="apply", cluster="my-cluster",
                         actions=[{"feature": "control_plane_upgrade", "value": "4.20.12"}])
        spec = ClusterAutomationSpec(data)
        engine = ExecutionEngine(minimal_registry, tmp_path, dry_run=True)
        plan = engine.plan(spec)

        assert len(plan) == 1
        assert plan[0]["type"] == "playbook"
        assert "upgrade_rosa_control_plane" in plan[0]["playbook"]

    def test_plan_apply_requires_cluster(self, minimal_registry, tmp_path):
        data = make_spec(action="apply", cluster="",
                         actions=[{"feature": "channel_group", "value": "fast"}])
        spec = ClusterAutomationSpec(data)
        engine = ExecutionEngine(minimal_registry, tmp_path, dry_run=True)
        with pytest.raises(ValueError, match="apply requires --cluster"):
            engine.plan(spec)

    def test_plan_apply_requires_actions(self, minimal_registry, tmp_path):
        data = make_spec(action="apply", cluster="my-cluster")
        spec = ClusterAutomationSpec(data)
        engine = ExecutionEngine(minimal_registry, tmp_path, dry_run=True)
        with pytest.raises(ValueError, match="apply requires actions"):
            engine.plan(spec)

    def test_plan_apply_unknown_feature(self, minimal_registry, tmp_path):
        data = make_spec(action="apply", cluster="my-cluster",
                         actions=[{"feature": "nonexistent", "value": "x"}])
        spec = ClusterAutomationSpec(data)
        engine = ExecutionEngine(minimal_registry, tmp_path, dry_run=True)
        with pytest.raises(ValueError, match="Unknown feature"):
            engine.plan(spec)

    def test_plan_delete(self, minimal_registry, tmp_path):
        data = make_spec(action="delete", cluster="my-cluster")
        spec = ClusterAutomationSpec(data)
        engine = ExecutionEngine(minimal_registry, tmp_path, dry_run=True)
        plan = engine.plan(spec)

        assert len(plan) == 1
        assert plan[0]["type"] == "playbook"
        assert "delete_rosa_hcp_cluster" in plan[0]["playbook"]
        assert plan[0]["extra_vars"]["cluster_name"] == "my-cluster"

    def test_plan_delete_requires_cluster(self, minimal_registry, tmp_path):
        data = make_spec(action="delete", cluster="")
        spec = ClusterAutomationSpec(data)
        engine = ExecutionEngine(minimal_registry, tmp_path, dry_run=True)
        with pytest.raises(ValueError, match="delete requires --cluster"):
            engine.plan(spec)

    def test_plan_unknown_action(self, minimal_registry, tmp_path):
        data = make_spec(action="bogus", cluster="my-cluster")
        spec = ClusterAutomationSpec(data)
        engine = ExecutionEngine(minimal_registry, tmp_path, dry_run=True)
        with pytest.raises(ValueError, match="Unknown action"):
            engine.plan(spec)

    def test_plan_multi_step_apply(self, minimal_registry, tmp_path):
        data = make_spec(action="apply", cluster="my-cluster", actions=[
            {"feature": "channel_group", "value": "fast"},
            {"feature": "control_plane_upgrade", "value": "4.20.12"},
        ])
        spec = ClusterAutomationSpec(data)
        engine = ExecutionEngine(minimal_registry, tmp_path, dry_run=True)
        plan = engine.plan(spec)

        assert len(plan) == 2
        assert plan[0]["step"] == 1
        assert plan[1]["step"] == 2


# ============================================================================
# ExecutionEngine Execute Tests
# ============================================================================

class TestExecutionEngineExecute:
    def test_dry_run_returns_dry_run_status(self, minimal_registry, tmp_path):
        data = make_spec(action="delete", cluster="my-cluster")
        spec = ClusterAutomationSpec(data)
        engine = ExecutionEngine(minimal_registry, tmp_path, dry_run=True)
        plan = engine.plan(spec)
        results = engine.execute(plan)

        assert len(results) == 1
        assert results[0]["status"] == "dry_run"

    def test_execute_playbook_not_found(self, minimal_registry, tmp_path):
        data = make_spec(action="delete", cluster="my-cluster")
        spec = ClusterAutomationSpec(data)
        engine = ExecutionEngine(minimal_registry, tmp_path, dry_run=False)
        plan = engine.plan(spec)
        results = engine.execute(plan)

        assert results[0]["status"] == "failed"
        assert "not found" in results[0]["error"]

    def test_execute_patch_step(self, minimal_registry, tmp_path):
        data = make_spec(action="apply", cluster="my-cluster",
                         actions=[{"feature": "channel_group", "value": "fast"}])
        spec = ClusterAutomationSpec(data)
        engine = ExecutionEngine(minimal_registry, tmp_path, dry_run=False)
        plan = engine.plan(spec)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="patched")
            results = engine.execute(plan)

        assert results[0]["status"] == "completed"
        call_args = mock_run.call_args[0][0]
        assert "oc" in call_args
        assert "patch" in call_args

    def test_execute_patch_failure(self, minimal_registry, tmp_path):
        data = make_spec(action="apply", cluster="my-cluster",
                         actions=[{"feature": "channel_group", "value": "fast"}])
        spec = ClusterAutomationSpec(data)
        engine = ExecutionEngine(minimal_registry, tmp_path, dry_run=False)
        plan = engine.plan(spec)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="not found")
            results = engine.execute(plan)

        assert results[0]["status"] == "failed"

    def test_execute_stops_on_failure(self, minimal_registry, tmp_path):
        data = make_spec(action="apply", cluster="my-cluster", actions=[
            {"feature": "channel_group", "value": "fast"},
            {"feature": "channel_group", "value": "stable"},
        ])
        spec = ClusterAutomationSpec(data)
        engine = ExecutionEngine(minimal_registry, tmp_path, dry_run=False)
        plan = engine.plan(spec)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="error")
            results = engine.execute(plan)

        assert results[0]["status"] == "failed"
        assert results[1]["status"] == "skipped"

    def test_execute_playbook_success(self, minimal_registry, tmp_path):
        # Create a fake playbook file so the file-exists check passes
        pb_dir = tmp_path / "playbooks"
        pb_dir.mkdir()
        (pb_dir / "delete_rosa_hcp_cluster.yml").write_text("---\n- hosts: localhost\n")

        data = make_spec(action="delete", cluster="my-cluster")
        spec = ClusterAutomationSpec(data)
        engine = ExecutionEngine(minimal_registry, tmp_path, dry_run=False)
        plan = engine.plan(spec)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="ok")
            results = engine.execute(plan)

        assert results[0]["status"] == "completed"

    def test_execute_playbook_timeout(self, minimal_registry, tmp_path):
        pb_dir = tmp_path / "playbooks"
        pb_dir.mkdir()
        (pb_dir / "delete_rosa_hcp_cluster.yml").write_text("---\n- hosts: localhost\n")

        data = make_spec(action="delete", cluster="my-cluster")
        spec = ClusterAutomationSpec(data)
        engine = ExecutionEngine(minimal_registry, tmp_path, dry_run=False)
        plan = engine.plan(spec)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="ansible", timeout=30)
            results = engine.execute(plan)

        assert results[0]["status"] == "failed"
        assert "Timeout" in results[0]["error"]


# ============================================================================
# Validation Tests
# ============================================================================

class TestValidation:
    def test_validate_boolean_valid(self):
        feat = {"id": "test", "type": "boolean"}
        errors, warnings = [], []
        _validate_feature_value_check(feat, True, errors, warnings)
        assert len(errors) == 0

    def test_validate_boolean_invalid(self):
        feat = {"id": "test", "type": "boolean"}
        errors, warnings = [], []
        _validate_feature_value_check(feat, "yes", errors, warnings)
        assert len(errors) == 1
        assert "boolean" in errors[0]

    def test_validate_select_valid(self):
        feat = {"id": "test", "type": "select", "options": ["a", "b", "c"]}
        errors, warnings = [], []
        _validate_feature_value_check(feat, "b", errors, warnings)
        assert len(errors) == 0

    def test_validate_select_invalid(self):
        feat = {"id": "test", "type": "select", "options": ["a", "b", "c"]}
        errors, warnings = [], []
        _validate_feature_value_check(feat, "d", errors, warnings)
        assert len(errors) == 1
        assert "one of" in errors[0]

    def test_validate_number_valid(self):
        feat = {"id": "test", "type": "number"}
        errors, warnings = [], []
        _validate_feature_value_check(feat, 42, errors, warnings)
        assert len(errors) == 0

    def test_validate_number_invalid(self):
        feat = {"id": "test", "type": "number"}
        errors, warnings = [], []
        _validate_feature_value_check(feat, "not_a_number", errors, warnings)
        assert len(errors) == 1
        assert "number" in errors[0]

    def test_validate_string_max_length_ok(self):
        feat = {"id": "test", "type": "string", "max_length": 15}
        errors, warnings = [], []
        _validate_feature_value_check(feat, "short", errors, warnings)
        assert len(errors) == 0

    def test_validate_string_max_length_exceeded(self):
        feat = {"id": "test", "type": "string", "max_length": 5}
        errors, warnings = [], []
        _validate_feature_value_check(feat, "too_long_string", errors, warnings)
        assert len(errors) == 1
        assert "max length" in errors[0]

    def test_validate_key_value_valid(self):
        feat = {"id": "test", "type": "key_value"}
        errors, warnings = [], []
        _validate_feature_value_check(feat, {"key": "val"}, errors, warnings)
        assert len(errors) == 0

    def test_validate_key_value_invalid(self):
        feat = {"id": "test", "type": "key_value"}
        errors, warnings = [], []
        _validate_feature_value_check(feat, "not_a_dict", errors, warnings)
        assert len(errors) == 1
        assert "key-value" in errors[0]

    def test_validate_list_valid(self):
        feat = {"id": "test", "type": "list"}
        errors, warnings = [], []
        _validate_feature_value_check(feat, ["a", "b"], errors, warnings)
        assert len(errors) == 0

    def test_validate_list_invalid(self):
        feat = {"id": "test", "type": "list"}
        errors, warnings = [], []
        _validate_feature_value_check(feat, "not_a_list", errors, warnings)
        assert len(errors) == 1
        assert "list" in errors[0]

    def test_validate_range_valid(self):
        feat = {"id": "test", "type": "range"}
        errors, warnings = [], []
        _validate_feature_value_check(feat, {"min": 1, "max": 5}, errors, warnings)
        assert len(errors) == 0

    def test_validate_range_min_greater_than_max(self):
        feat = {"id": "test", "type": "range"}
        errors, warnings = [], []
        _validate_feature_value_check(feat, {"min": 10, "max": 2}, errors, warnings)
        assert len(errors) == 1
        assert "min" in errors[0] and "max" in errors[0]

    def test_validate_range_invalid_type(self):
        feat = {"id": "test", "type": "range"}
        errors, warnings = [], []
        _validate_feature_value_check(feat, 42, errors, warnings)
        assert len(errors) == 1
        assert "range" in errors[0]

    def test_validate_range_missing_keys(self):
        feat = {"id": "test", "type": "range"}
        errors, warnings = [], []
        _validate_feature_value_check(feat, {"min": 1}, errors, warnings)
        assert len(errors) == 1


# ============================================================================
# cmd_set Validation Tests (via _validate_feature_value)
# ============================================================================

class TestCmdSetValidation:
    def test_set_immutable_feature_passes_type_check(self):
        """_validate_feature_value only checks type, not mutability.
        Mutability is checked in cmd_set before calling this function."""
        feat = {"id": "private_network", "type": "boolean", "mutable": False,
                "applies_to": ["create"]}
        # Should not raise — type check passes (True is a valid boolean)
        _validate_feature_value(feat, True)

    def test_set_select_invalid_exits(self):
        feat = {"id": "channel_group", "type": "select",
                "options": ["stable", "fast", "candidate"],
                "mutable": True, "applies_to": ["apply"]}
        with pytest.raises(SystemExit):
            _validate_feature_value(feat, "invalid")

    def test_set_select_valid_passes(self):
        feat = {"id": "channel_group", "type": "select",
                "options": ["stable", "fast", "candidate"],
                "mutable": True, "applies_to": ["apply"]}
        # Should not raise
        _validate_feature_value(feat, "fast")

    def test_set_boolean_invalid_exits(self):
        feat = {"id": "proxy", "type": "boolean", "mutable": True,
                "applies_to": ["apply"]}
        with pytest.raises(SystemExit):
            _validate_feature_value(feat, "yes")

    def test_set_number_invalid_exits(self):
        feat = {"id": "parallel", "type": "number", "mutable": True,
                "applies_to": ["apply"]}
        with pytest.raises(SystemExit):
            _validate_feature_value(feat, "abc")

    def test_set_string_max_length_exits(self):
        feat = {"id": "domain", "type": "string", "mutable": True,
                "applies_to": ["apply"], "max_length": 5}
        with pytest.raises(SystemExit):
            _validate_feature_value(feat, "too_long_string")


# ============================================================================
# load_spec Tests
# ============================================================================

class TestLoadSpec:
    def test_load_from_file(self, tmp_path):
        spec_data = make_spec(action="apply", cluster="test-cluster",
                              actions=[{"feature": "channel_group", "value": "fast"}])
        spec_file = tmp_path / "test.yml"
        with open(spec_file, "w") as f:
            yaml.dump(spec_data, f)

        args = MagicMock()
        args.file = str(spec_file)
        args.profile = None
        args.extra_vars = None
        args.cluster = None
        args.version = None
        args.namespace = None
        args.name_prefix = None

        spec = load_spec(args, tmp_path)
        assert spec.action == "apply"
        assert spec.cluster == "test-cluster"

    def test_load_from_file_with_overrides(self, tmp_path):
        spec_data = make_spec(action="apply", cluster="original")
        spec_file = tmp_path / "test.yml"
        with open(spec_file, "w") as f:
            yaml.dump(spec_data, f)

        args = MagicMock()
        args.file = str(spec_file)
        args.profile = None
        args.extra_vars = ["channel_group=fast"]
        args.cluster = "override-cluster"
        args.version = "4.20.12"
        args.namespace = None
        args.name_prefix = None

        spec = load_spec(args, tmp_path)
        assert spec.cluster == "override-cluster"
        assert spec.version == "4.20.12"
        assert spec.features["channel_group"] == "fast"

    def test_load_from_profile(self, tmp_path):
        spec_data = make_spec(action="create",
                              features={"private_network": True})
        specs_dir = tmp_path / "specs" / "profiles"
        specs_dir.mkdir(parents=True)
        with open(specs_dir / "test-profile.yml", "w") as f:
            yaml.dump(spec_data, f)

        args = MagicMock()
        args.file = None
        args.profile = "test-profile"
        args.extra_vars = None
        args.cluster = None
        args.version = None
        args.namespace = None
        args.name_prefix = None

        spec = load_spec(args, tmp_path)
        assert spec.features["private_network"] is True

    def test_load_inline_spec(self):
        args = MagicMock()
        args.file = None
        args.profile = None
        args.extra_vars = None
        args.cluster = "my-cluster"
        args.version = None
        args.namespace = None
        args.name_prefix = None
        args.command = "delete"

        spec = load_spec(args, PROJECT_ROOT)
        assert spec.action == "delete"
        assert spec.cluster == "my-cluster"

    def test_extra_vars_boolean_parsing(self, tmp_path):
        spec_data = make_spec(action="create")
        spec_file = tmp_path / "test.yml"
        with open(spec_file, "w") as f:
            yaml.dump(spec_data, f)

        args = MagicMock()
        args.file = str(spec_file)
        args.profile = None
        args.extra_vars = ["private_network=true", "byon=false"]
        args.cluster = None
        args.version = None
        args.namespace = None
        args.name_prefix = None

        spec = load_spec(args, tmp_path)
        assert spec.features["private_network"] is True
        assert spec.features["byon"] is False

    def test_extra_vars_number_parsing(self, tmp_path):
        spec_data = make_spec(action="create")
        spec_file = tmp_path / "test.yml"
        with open(spec_file, "w") as f:
            yaml.dump(spec_data, f)

        args = MagicMock()
        args.file = str(spec_file)
        args.profile = None
        args.extra_vars = ["parallel_upgrade=3"]
        args.cluster = None
        args.version = None
        args.namespace = None
        args.name_prefix = None

        spec = load_spec(args, tmp_path)
        assert spec.features["parallel_upgrade"] == 3


# ============================================================================
# CLI Integration Tests (subprocess)
# ============================================================================

class TestCLIIntegration:
    def test_help(self):
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "capa"), "--help"],
            capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0
        assert "CAPA CLI" in result.stdout

    def test_features_command(self):
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "capa"), "features"],
            capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0
        assert "Feature Registry" in result.stdout
        assert "channel_group" in result.stdout

    def test_specs_command(self):
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "capa"), "specs"],
            capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0
        assert "Available Specs" in result.stdout

    def test_set_dry_run(self):
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "capa"), "set",
             "channel_group", "fast", "-c", "test-cluster", "--dry-run"],
            capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0
        assert "DRY RUN" in result.stdout

    def test_set_unknown_feature(self):
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "capa"), "set",
             "bogus_feature", "val", "-c", "test-cluster", "--dry-run"],
            capture_output=True, text=True, timeout=10
        )
        assert result.returncode != 0
        assert "Unknown feature" in result.stderr or "Unknown feature" in result.stdout

    def test_set_immutable_feature(self):
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "capa"), "set",
             "private_network", "true", "-c", "test-cluster", "--dry-run"],
            capture_output=True, text=True, timeout=10
        )
        assert result.returncode != 0
        assert "immutable" in (result.stderr + result.stdout).lower()

    def test_set_invalid_select_value(self):
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "capa"), "set",
             "channel_group", "invalid", "-c", "test-cluster", "--dry-run"],
            capture_output=True, text=True, timeout=10
        )
        assert result.returncode != 0

    def test_validate_valid_spec(self):
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "capa"), "validate",
             str(PROJECT_ROOT / "specs" / "features" / "channel-group.yml")],
            capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0
        assert "Valid spec" in result.stdout

    def test_validate_profile(self):
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "capa"), "validate",
             str(PROJECT_ROOT / "specs" / "profiles" / "default.yml")],
            capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0

    def test_validate_nonexistent_file(self):
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "capa"), "validate",
             "/nonexistent/file.yml"],
            capture_output=True, text=True, timeout=10
        )
        assert result.returncode != 0

    def test_plan_with_spec_file(self):
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "capa"), "plan",
             "-f", str(PROJECT_ROOT / "specs" / "features" / "channel-group.yml"),
             "--cluster", "test-cluster"],
            capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0
        assert "DRY RUN" in result.stdout

    def test_plan_with_profile(self):
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "capa"), "plan",
             "--profile", "default", "-e", "name_prefix=test1"],
            capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0
        assert "DRY RUN" in result.stdout

    def test_generate_specs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Copy registry to temp dir
            tmp_schemas = Path(tmpdir) / "schemas"
            tmp_schemas.mkdir()
            tmp_specs = Path(tmpdir) / "specs" / "features"
            tmp_specs.mkdir(parents=True)

            import shutil
            shutil.copy(PROJECT_ROOT / "schemas" / "feature-registry.yml",
                        tmp_schemas / "feature-registry.yml")
            # Copy the capa script and its shared core module
            shutil.copy(PROJECT_ROOT / "capa", Path(tmpdir) / "capa")
            shutil.copy(PROJECT_ROOT / "capa_core.py", Path(tmpdir) / "capa_core.py")

            result = subprocess.run(
                [sys.executable, str(Path(tmpdir) / "capa"), "generate-specs"],
                capture_output=True, text=True, timeout=10
            )
            assert result.returncode == 0
            assert "Generated" in result.stdout

            # Check files were created
            generated = list(tmp_specs.glob("*.yml"))
            assert len(generated) > 0

    def test_no_command_shows_help(self):
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "capa")],
            capture_output=True, text=True, timeout=10
        )
        assert result.returncode != 0


# ============================================================================
# Real Spec File Validation Tests
# ============================================================================

class TestProfileInheritance:
    """Tests for profile inheritance (metadata.inherits)."""

    def test_inheritance_merges_parent_features(self, registry):
        """Child inherits parent features, child features win on conflict."""
        data = {
            "apiVersion": "capa-automation/v1",
            "kind": "ClusterAutomationSpec",
            "metadata": {"name": "child", "inherits": "default"},
            "spec": {
                "action": "create",
                "features": {
                    "instance_type": "m5.4xlarge",  # override parent's m5.xlarge
                },
            },
        }
        spec = capa_cli.ClusterAutomationSpec(data, base_dir=PROJECT_ROOT)
        # Child override wins
        assert spec.features["instance_type"] == "m5.4xlarge"
        # Parent features inherited
        assert spec.features["availability_zones"] == "1"
        assert "automated" in spec.features["additional_tags"]

    def test_inheritance_child_features_win(self, registry):
        """When both parent and child define the same feature, child wins."""
        data = {
            "apiVersion": "capa-automation/v1",
            "kind": "ClusterAutomationSpec",
            "metadata": {"name": "override-test", "inherits": "default"},
            "spec": {
                "action": "create",
                "features": {
                    "additional_tags": {"custom": "value"},
                },
            },
        }
        spec = capa_cli.ClusterAutomationSpec(data, base_dir=PROJECT_ROOT)
        # Child's tags replace parent's tags entirely (dict override)
        assert spec.features["additional_tags"] == {"custom": "value"}

    def test_inheritance_inherits_top_level_fields(self, registry):
        """Child inherits parent's version, region, channel if not set."""
        data = {
            "apiVersion": "capa-automation/v1",
            "kind": "ClusterAutomationSpec",
            "metadata": {"name": "minimal", "inherits": "default"},
            "spec": {
                "action": "create",
                "features": {},
            },
        }
        spec = capa_cli.ClusterAutomationSpec(data, base_dir=PROJECT_ROOT)
        assert spec.version == "4.20.11"  # from default profile
        assert spec.region == "us-west-2"
        assert spec.channel == "stable"

    def test_inheritance_child_overrides_top_level(self, registry):
        """Child's explicit top-level fields override parent."""
        data = {
            "apiVersion": "capa-automation/v1",
            "kind": "ClusterAutomationSpec",
            "metadata": {"name": "override-region", "inherits": "default"},
            "spec": {
                "action": "create",
                "region": "eu-west-1",
                "features": {},
            },
        }
        spec = capa_cli.ClusterAutomationSpec(data, base_dir=PROJECT_ROOT)
        assert spec.region == "eu-west-1"

    def test_inheritance_missing_parent_raises(self):
        """Inheriting from nonexistent profile raises ValueError."""
        data = {
            "apiVersion": "capa-automation/v1",
            "kind": "ClusterAutomationSpec",
            "metadata": {"name": "bad-inherit", "inherits": "nonexistent-profile"},
            "spec": {"action": "create"},
        }
        with pytest.raises(ValueError, match="not found"):
            capa_cli.ClusterAutomationSpec(data, base_dir=PROJECT_ROOT)

    def test_inheritance_no_base_dir_skips(self):
        """Without base_dir, inheritance is silently skipped."""
        data = {
            "apiVersion": "capa-automation/v1",
            "kind": "ClusterAutomationSpec",
            "metadata": {"name": "no-basedir", "inherits": "default"},
            "spec": {"action": "create", "features": {}},
        }
        # Should not raise — inheritance is skipped when base_dir is None
        spec = capa_cli.ClusterAutomationSpec(data)
        assert spec.features == {}

    def test_real_inherited_profile(self, registry):
        """Test the real private-encrypted-custom profile that inherits from private-encrypted."""
        profile_path = PROJECT_ROOT / "specs" / "profiles" / "private-encrypted-custom.yml"
        if not profile_path.exists():
            pytest.skip("private-encrypted-custom.yml not found")
        with open(profile_path) as f:
            data = yaml.safe_load(f)
        spec = capa_cli.ClusterAutomationSpec(data, base_dir=PROJECT_ROOT)
        # From child
        assert spec.features["instance_type"] == "m5.4xlarge"
        assert spec.features["disk_size"] == 500
        # From parent (private-encrypted)
        assert spec.features["private_network"] is True
        assert spec.features["availability_zones"] == "3"

    def test_version_type_validation(self, registry):
        """Test that version type validates semver format."""
        feat = {"id": "test_version", "type": "version"}
        errors = []
        warnings = []
        capa_cli._validate_feature_value_check(feat, "4.20.11", errors, warnings)
        assert errors == []

        errors = []
        capa_cli._validate_feature_value_check(feat, "not-a-version", errors, warnings)
        assert len(errors) == 1
        assert "semver" in errors[0]

        errors = []
        capa_cli._validate_feature_value_check(feat, "4.20", errors, warnings)
        assert len(errors) == 1  # Missing patch version

    def test_multi_level_inheritance(self):
        """Multi-level: grandchild inherits parent inherits grandparent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            specs_dir = Path(tmpdir) / "specs" / "profiles"
            specs_dir.mkdir(parents=True)

            # Grandparent: base features
            grandparent = {
                "apiVersion": "capa-automation/v1",
                "kind": "ClusterAutomationSpec",
                "metadata": {"name": "grandparent"},
                "spec": {
                    "action": "create",
                    "region": "us-east-1",
                    "features": {"private_network": True, "sts": True},
                },
            }
            with open(specs_dir / "grandparent.yml", "w") as f:
                yaml.dump(grandparent, f)

            # Parent: inherits grandparent, adds/overrides
            parent = {
                "apiVersion": "capa-automation/v1",
                "kind": "ClusterAutomationSpec",
                "metadata": {"name": "parent", "inherits": "grandparent"},
                "spec": {
                    "action": "create",
                    "features": {"availability_zones": "3"},
                },
            }
            with open(specs_dir / "parent.yml", "w") as f:
                yaml.dump(parent, f)

            # Child: inherits parent
            child_data = {
                "apiVersion": "capa-automation/v1",
                "kind": "ClusterAutomationSpec",
                "metadata": {"name": "child", "inherits": "parent"},
                "spec": {
                    "action": "create",
                    "features": {"instance_type": "m5.4xlarge"},
                },
            }
            spec = ClusterAutomationSpec(child_data, base_dir=Path(tmpdir))

            # From grandparent
            assert spec.features["private_network"] is True
            assert spec.features["sts"] is True
            assert spec.region == "us-east-1"
            # From parent
            assert spec.features["availability_zones"] == "3"
            # From child
            assert spec.features["instance_type"] == "m5.4xlarge"

    def test_circular_inheritance_raises(self):
        """Circular inheritance (A -> B -> A) raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            specs_dir = Path(tmpdir) / "specs" / "profiles"
            specs_dir.mkdir(parents=True)

            a_data = {
                "apiVersion": "capa-automation/v1",
                "kind": "ClusterAutomationSpec",
                "metadata": {"name": "a", "inherits": "b"},
                "spec": {"action": "create", "features": {}},
            }
            b_data = {
                "apiVersion": "capa-automation/v1",
                "kind": "ClusterAutomationSpec",
                "metadata": {"name": "b", "inherits": "a"},
                "spec": {"action": "create", "features": {}},
            }
            with open(specs_dir / "a.yml", "w") as f:
                yaml.dump(a_data, f)
            with open(specs_dir / "b.yml", "w") as f:
                yaml.dump(b_data, f)

            with pytest.raises(ValueError, match="Circular inheritance"):
                ClusterAutomationSpec(a_data, base_dir=Path(tmpdir))


class TestRealSpecFiles:
    """Validate all spec files in the repo against the registry."""

    def test_all_feature_specs_valid(self, registry):
        specs_dir = PROJECT_ROOT / "specs" / "features"
        if not specs_dir.exists():
            pytest.skip("No feature specs directory")
        for spec_file in specs_dir.glob("*.yml"):
            with open(spec_file) as f:
                data = yaml.safe_load(f)
            assert data["apiVersion"] == "capa-automation/v1", f"{spec_file.name}: bad apiVersion"
            assert data["kind"] == "ClusterAutomationSpec", f"{spec_file.name}: bad kind"
            for act in data.get("spec", {}).get("actions", []):
                feat_id = act["feature"]
                assert registry.get_feature(feat_id) is not None, \
                    f"{spec_file.name}: unknown feature '{feat_id}'"

    def test_all_profile_specs_valid(self, registry):
        specs_dir = PROJECT_ROOT / "specs" / "profiles"
        if not specs_dir.exists():
            pytest.skip("No profiles directory")
        for spec_file in specs_dir.glob("*.yml"):
            with open(spec_file) as f:
                data = yaml.safe_load(f)
            assert data["apiVersion"] == "capa-automation/v1", f"{spec_file.name}: bad apiVersion"
            assert data["kind"] == "ClusterAutomationSpec", f"{spec_file.name}: bad kind"
            for feat_id in data.get("spec", {}).get("features", {}):
                assert registry.get_feature(feat_id) is not None, \
                    f"{spec_file.name}: unknown feature '{feat_id}'"

    def test_all_workflow_specs_valid(self, registry):
        specs_dir = PROJECT_ROOT / "specs" / "workflows"
        if not specs_dir.exists():
            pytest.skip("No workflows directory")
        for spec_file in specs_dir.glob("*.yml"):
            with open(spec_file) as f:
                data = yaml.safe_load(f)
            assert data["apiVersion"] == "capa-automation/v1", f"{spec_file.name}: bad apiVersion"
            assert data["kind"] == "ClusterAutomationSpec", f"{spec_file.name}: bad kind"


class TestCmdTest:
    """Tests for the 'capa test' command (passthrough to run-test-suite.py)."""

    def _make_args(self, **kwargs):
        """Build a namespace with defaults for cmd_test args."""
        defaults = {
            "suite_id": None,
            "all": False,
            "list": False,
            "tag": None,
            "format": None,
            "no_save": False,
            "extra_vars": None,
            "ai_agent": False,
            "ai_agent_dry_run": False,
            "test_verbosity": 0,
            "dry_run": False,
            "verbose": False,
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    @patch("subprocess.run")
    def test_basic_suite_run(self, mock_run, tmp_path):
        """Test running a single suite by ID."""
        (tmp_path / "run-test-suite.py").write_text("# fake")
        mock_run.return_value = MagicMock(returncode=0)

        args = self._make_args(suite_id="20-rosa-hcp-provision")
        with pytest.raises(SystemExit) as exc_info:
            capa_cli.cmd_test(args, tmp_path, None)
        assert exc_info.value.code == 0

        cmd = mock_run.call_args[0][0]
        assert "run-test-suite.py" in cmd[1]
        assert "20-rosa-hcp-provision" in cmd

    @patch("subprocess.run")
    def test_list_flag(self, mock_run, tmp_path):
        """Test --list flag passthrough."""
        (tmp_path / "run-test-suite.py").write_text("# fake")
        mock_run.return_value = MagicMock(returncode=0)

        args = self._make_args(list=True)
        with pytest.raises(SystemExit) as exc_info:
            capa_cli.cmd_test(args, tmp_path, None)
        assert exc_info.value.code == 0

        cmd = mock_run.call_args[0][0]
        assert "--list" in cmd

    @patch("subprocess.run")
    def test_all_flag(self, mock_run, tmp_path):
        """Test --all flag passthrough."""
        (tmp_path / "run-test-suite.py").write_text("# fake")
        mock_run.return_value = MagicMock(returncode=0)

        args = self._make_args(all=True)
        with pytest.raises(SystemExit) as exc_info:
            capa_cli.cmd_test(args, tmp_path, None)
        assert exc_info.value.code == 0

        cmd = mock_run.call_args[0][0]
        assert "--all" in cmd

    @patch("subprocess.run")
    def test_ai_agent_flags(self, mock_run, tmp_path):
        """Test --ai-agent and --ai-agent-dry-run passthrough."""
        (tmp_path / "run-test-suite.py").write_text("# fake")
        mock_run.return_value = MagicMock(returncode=0)

        args = self._make_args(suite_id="30-delete", ai_agent=True, ai_agent_dry_run=True)
        with pytest.raises(SystemExit) as exc_info:
            capa_cli.cmd_test(args, tmp_path, None)
        assert exc_info.value.code == 0

        cmd = mock_run.call_args[0][0]
        assert "--ai-agent" in cmd
        assert "--ai-agent-dry-run" in cmd

    @patch("subprocess.run")
    def test_extra_vars_passthrough(self, mock_run, tmp_path):
        """Test -e extra vars are forwarded."""
        (tmp_path / "run-test-suite.py").write_text("# fake")
        mock_run.return_value = MagicMock(returncode=0)

        args = self._make_args(
            suite_id="20-provision",
            extra_vars=["OCP_HUB_API_URL=https://api.hub:6443", "AWS_ACCESS_KEY_ID=AKIA123"]
        )
        with pytest.raises(SystemExit) as exc_info:
            capa_cli.cmd_test(args, tmp_path, None)
        assert exc_info.value.code == 0

        cmd = mock_run.call_args[0][0]
        assert "-e" in cmd
        assert "OCP_HUB_API_URL=https://api.hub:6443" in cmd
        assert "AWS_ACCESS_KEY_ID=AKIA123" in cmd

    @patch("subprocess.run")
    def test_verbosity_passthrough(self, mock_run, tmp_path):
        """Test -V/-VV/-VVV verbosity mapping."""
        (tmp_path / "run-test-suite.py").write_text("# fake")
        mock_run.return_value = MagicMock(returncode=0)

        args = self._make_args(suite_id="20-provision", test_verbosity=3)
        with pytest.raises(SystemExit) as exc_info:
            capa_cli.cmd_test(args, tmp_path, None)
        assert exc_info.value.code == 0

        cmd = mock_run.call_args[0][0]
        assert "-vvv" in cmd

    @patch("subprocess.run")
    def test_format_passthrough(self, mock_run, tmp_path):
        """Test --format flag passthrough."""
        (tmp_path / "run-test-suite.py").write_text("# fake")
        mock_run.return_value = MagicMock(returncode=0)

        args = self._make_args(suite_id="20-provision", format="junit")
        with pytest.raises(SystemExit) as exc_info:
            capa_cli.cmd_test(args, tmp_path, None)
        assert exc_info.value.code == 0

        cmd = mock_run.call_args[0][0]
        assert "--format" in cmd
        assert "junit" in cmd

    @patch("subprocess.run")
    def test_tag_passthrough(self, mock_run, tmp_path):
        """Test --tag flag passthrough."""
        (tmp_path / "run-test-suite.py").write_text("# fake")
        mock_run.return_value = MagicMock(returncode=0)

        args = self._make_args(all=True, tag="rosa-hcp")
        with pytest.raises(SystemExit) as exc_info:
            capa_cli.cmd_test(args, tmp_path, None)
        assert exc_info.value.code == 0

        cmd = mock_run.call_args[0][0]
        assert "--tag" in cmd
        assert "rosa-hcp" in cmd

    @patch("subprocess.run")
    def test_dry_run_passthrough(self, mock_run, tmp_path):
        """Test --dry-run flag passthrough."""
        (tmp_path / "run-test-suite.py").write_text("# fake")
        mock_run.return_value = MagicMock(returncode=0)

        args = self._make_args(suite_id="20-provision", dry_run=True)
        with pytest.raises(SystemExit) as exc_info:
            capa_cli.cmd_test(args, tmp_path, None)
        assert exc_info.value.code == 0

        cmd = mock_run.call_args[0][0]
        assert "--dry-run" in cmd

    @patch("subprocess.run")
    def test_no_save_passthrough(self, mock_run, tmp_path):
        """Test --no-save flag passthrough."""
        (tmp_path / "run-test-suite.py").write_text("# fake")
        mock_run.return_value = MagicMock(returncode=0)

        args = self._make_args(suite_id="20-provision", no_save=True)
        with pytest.raises(SystemExit) as exc_info:
            capa_cli.cmd_test(args, tmp_path, None)
        assert exc_info.value.code == 0

        cmd = mock_run.call_args[0][0]
        assert "--no-save" in cmd

    def test_missing_runner_exits(self, tmp_path):
        """Test error when run-test-suite.py doesn't exist."""
        args = self._make_args(suite_id="20-provision")
        with pytest.raises(SystemExit):
            capa_cli.cmd_test(args, tmp_path, None)

    @patch("subprocess.run")
    def test_full_jenkins_style_invocation(self, mock_run, tmp_path):
        """Test a full Jenkins-style invocation with all flags."""
        (tmp_path / "run-test-suite.py").write_text("# fake")
        mock_run.return_value = MagicMock(returncode=0)

        args = self._make_args(
            suite_id="20-rosa-hcp-provision",
            format="junit",
            test_verbosity=3,
            ai_agent=True,
            extra_vars=[
                "OCP_HUB_API_URL=https://api.hub:6443",
                "OCP_HUB_ADMIN_USER=kubeadmin",
                "OCP_HUB_ADMIN_PASS=secret",
                "AWS_ACCESS_KEY_ID=AKIA123",
                "AWS_SECRET_ACCESS_KEY=secret456",
            ]
        )
        with pytest.raises(SystemExit) as exc_info:
            capa_cli.cmd_test(args, tmp_path, None)
        assert exc_info.value.code == 0

        cmd = mock_run.call_args[0][0]
        assert "20-rosa-hcp-provision" in cmd
        assert "--format" in cmd
        assert "junit" in cmd
        assert "-vvv" in cmd
        assert "--ai-agent" in cmd
        e_indices = [i for i, x in enumerate(cmd) if x == "-e"]
        assert len(e_indices) == 5

    @patch("subprocess.run")
    def test_exit_code_passthrough(self, mock_run, tmp_path):
        """Test that non-zero exit code from runner is propagated."""
        (tmp_path / "run-test-suite.py").write_text("# fake")
        mock_run.return_value = MagicMock(returncode=1)

        args = self._make_args(suite_id="20-provision")
        with pytest.raises(SystemExit) as exc_info:
            capa_cli.cmd_test(args, tmp_path, None)
        assert exc_info.value.code == 1

    @patch("subprocess.run")
    def test_verbosity_capped_at_4(self, mock_run, tmp_path):
        """Test that verbosity is capped at -vvvv even if -VVVVV given."""
        (tmp_path / "run-test-suite.py").write_text("# fake")
        mock_run.return_value = MagicMock(returncode=0)

        args = self._make_args(suite_id="20-provision", test_verbosity=6)
        with pytest.raises(SystemExit) as exc_info:
            capa_cli.cmd_test(args, tmp_path, None)
        assert exc_info.value.code == 0

        cmd = mock_run.call_args[0][0]
        assert "-vvvv" in cmd
        assert "-vvvvvv" not in cmd
