"""
OCM Role Linkage Validator Tests
================================

Unit tests for the pure 403/404-tolerant decision logic
(`verdict_from_status`) and the validator orchestration with fake clients.
Covers ROSA-637 / ROSAENG-60868 semantics.

Runnable both under pytest and standalone (mirrors test_rosa_hcp.py).
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from agents.domains.rosa_hcp.ocm_role_linkage_validator import (  # noqa: E402
    OCMRoleLinkageValidator,
    verdict_from_status,
)


def test_403_is_enforced_and_rejected():
    """403 = enforcement fully applied (ROSA-637 target end-state)."""
    d = verdict_from_status(403)
    assert d["negative_op_rejected"] is True
    assert d["enforcement_applied"] is True
    assert d["verdict"] == "rejected_403_enforced"
    print("PASSED: 403 -> enforced + rejected")


def test_404_is_tolerated_transition():
    """404 = rejected but TOLERATED during transition (ROSAENG-60868)."""
    d = verdict_from_status(404)
    assert d["negative_op_rejected"] is True
    assert d["enforcement_applied"] is False
    assert d["verdict"] == "rejected_404_transition_tolerated"
    print("PASSED: 404 -> tolerated transition, still rejected")


def test_200_is_not_enforced_failure():
    """200 = enforcement not applied = meaningful failure."""
    d = verdict_from_status(200)
    assert d["negative_op_rejected"] is False
    assert d["enforcement_applied"] is False
    assert d["verdict"] == "not_enforced_200"
    print("PASSED: 200 -> not enforced (failure)")


def test_unexpected_status_is_failure():
    """Any other status (e.g. 500) is unexpected and not a clean rejection."""
    for code in (401, 500, None):
        d = verdict_from_status(code)
        assert d["negative_op_rejected"] is False, code
        assert d["verdict"] == "unexpected_status", code
    print("PASSED: unexpected/None -> failure")


class _FakeOCM:
    """Minimal OCMClient stand-in returning canned statuses per path."""

    def __init__(self, api_url, responses):
        self.api_url = api_url
        self._responses = responses  # {path_substring: status_or_exc}

    def _authed_request(self, url):
        import urllib.error

        for frag, val in self._responses.items():
            if frag in url:
                if val == 200:
                    return {"organization": {"id": "org-123"}}
                raise urllib.error.HTTPError(url, val, "err", {}, None)
        raise urllib.error.HTTPError(url, 404, "not found", {}, None)


class _FakeAWS:
    available = False

    def _client(self, service):
        return None


def test_validate_positive_authorized_negative_404():
    """End-to-end with fakes: positive 200, negative 404 -> both pass."""
    ocm = _FakeOCM(
        "https://api.stage.openshift.com",
        {"current_account": 200, "access_review": 404},
    )
    v = OCMRoleLinkageValidator(ocm_client=ocm, aws_client=_FakeAWS(), aws_account_id="111")
    result = v.validate()
    assert result["positive_op_authorized"] is True
    assert result["negative_op_rejected"] is True
    assert result["negative_status_code"] == 404
    assert result["verdict"] == "rejected_404_transition_tolerated"
    print("PASSED: validate() positive=200, negative=404")


def test_validate_negative_200_flags_not_enforced():
    """If unlinked op returns 200, negative_op_rejected must be False."""
    ocm = _FakeOCM(
        "https://api.stage.openshift.com",
        {"current_account": 200, "access_review": 200},
    )
    v = OCMRoleLinkageValidator(ocm_client=ocm, aws_client=_FakeAWS(), aws_account_id="111")
    result = v.validate()
    assert result["negative_op_rejected"] is False
    assert result["verdict"] == "not_enforced_200"
    print("PASSED: validate() negative=200 -> not enforced")


def test_negative_probe_empty_account_id_raises():
    """Empty aws_account_id must raise, not silently 404 (false-pass guard)."""
    import pytest

    ocm = _FakeOCM(
        "https://api.stage.openshift.com",
        {"current_account": 200, "access_review": 404},
    )
    v = OCMRoleLinkageValidator(ocm_client=ocm, aws_client=_FakeAWS(), aws_account_id="")
    with pytest.raises(ValueError, match="aws_account_id is required"):
        v.probe_negative()
    print("PASSED: empty account_id -> ValueError (no false 404 pass)")


def test_negative_probe_custom_template_without_account_id_ok():
    """A template that doesn't reference account_id needn't require one."""
    ocm = _FakeOCM(
        "https://api.stage.openshift.com",
        {"current_account": 200, "custom_probe": 403},
    )
    v = OCMRoleLinkageValidator(
        ocm_client=ocm,
        aws_client=_FakeAWS(),
        aws_account_id="",
        negative_probe_path_template="/api/custom_probe",
    )
    decision = v.probe_negative()
    assert decision["negative_op_rejected"] is True
    assert decision["status_code"] == 403
    print("PASSED: account-id-less template runs without account_id")


if __name__ == "__main__":
    tests = [
        test_403_is_enforced_and_rejected,
        test_404_is_tolerated_transition,
        test_200_is_not_enforced_failure,
        test_unexpected_status_is_failure,
        test_validate_positive_authorized_negative_404,
        test_validate_negative_200_flags_not_enforced,
        test_negative_probe_empty_account_id_raises,
        test_negative_probe_custom_template_without_account_id_ok,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAILED: {test.__name__}: {e}")
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"OCM Role Linkage Validator Tests: {passed} passed, {failed} failed")
    print(f"{'=' * 60}")
    sys.exit(1 if failed > 0 else 0)
