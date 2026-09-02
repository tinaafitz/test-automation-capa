"""
OCM Role Linkage Validator (negative-enforcement assertion)
===========================================================

Asserts the *mandatory OCM-role linkage* enforcement for ROSA cluster
operations.

Background
----------
Jira ROSA-637: OCM roles become mandatory for ROSA cluster operations by the
end of Sept 2026. Regression ROSAENG-60868: an HCP PROD FVT failed because the
`secondRegularConnection` org lacked a linked OCM Role for the prod FVT AWS
account, so the OCM API returned **404** where the test expected **403**.

Scope of THIS module
---------------------
The repo's `tasks/preflight_check_ocm_role.yml` already checks OCM-role
existence + linkage in IAM and OCM AND auto-fixes it so provisioning succeeds.
What it does NOT do — and the only genuinely-new capability here — is assert
that an *unlinked* OCM-role operation is **rejected**:

    NEGATIVE: without OCM-role linkage, the operation is rejected with a clear
    authorization error. We assert the rejection is a **403**, but **TOLERATE
    404** during the enforcement-transition window (that tolerance is the whole
    point of ROSAENG-60868 — unlinked currently yields 404, and the fix is to
    treat 403-or-404 as "correctly rejected / enforcement applies"). A **200**
    on the negative probe means enforcement is NOT applied and is a meaningful
    test failure.

This module deliberately does NOT re-scan IAM or run a "positive" probe — the
preflight already establishes existence + linkage, so those would duplicate it.
It reuses the repo's battle-tested `agents.ocm_client.OCMClient` for OCM token
exchange + authed requests.

LIVE-VERIFICATION RESIDUAL (documented, not yet confirmed against live OCM)
--------------------------------------------------------------------------
The exact OCM endpoint whose 403-vs-404 semantics mirror the FVT is a known
live-verification residual. The negative probe path is chosen defensively and
is overridable via the `OCM_LINKAGE_NEGATIVE_PATH` env var (and the
`negative_probe_path_template` arg) so it can be corrected without code surgery
once the user runs the live verification step. See `verdict_from_status` and
`negative_probe_path_template` below. VERIFIED-AGAINST-LIVE-OCM PENDING.
"""

import logging
import urllib.error
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# Decision constants (pure, unit-testable)
# ----------------------------------------------------------------------------
# A negative (unlinked) probe is "correctly rejected / enforcement applies" if
# the OCM API returns any of these. 403 is the target end-state; 404 is
# tolerated during the ROSAENG-60868 enforcement-transition window.
REJECTED_STATUS_CODES = (403, 404)
# The canonical "authorization enforced" end-state we ultimately want.
ENFORCED_STATUS_CODE = 403
# During transition, unlinked returns this instead of 403.
TRANSITION_TOLERATED_STATUS_CODE = 404


def verdict_from_status(status_code: Optional[int]) -> Dict:
    """Pure decision logic: classify a negative-probe HTTP status code.

    This is the unit-testable core of the 403/404-tolerant policy.

    Returns a dict with:
      * negative_op_rejected: bool — True if the unlinked op was correctly
        rejected (403 OR, tolerated, 404).
      * enforcement_applied: bool — True only for the canonical 403 end-state.
      * verdict: short machine string.
      * message: human-readable explanation.

    Policy (ROSAENG-60868):
      403      -> rejected, enforcement fully applied (target end-state).
      404      -> rejected, TOLERATED transition behavior (unlinked -> 404).
      200      -> NOT rejected: enforcement not applied -> meaningful failure.
      other    -> unexpected status; treat as failure (surface for triage).
      None     -> probe did not complete (network/other error) -> failure.
    """
    if status_code == ENFORCED_STATUS_CODE:
        return {
            "negative_op_rejected": True,
            "enforcement_applied": True,
            "verdict": "rejected_403_enforced",
            "message": (
                "Unlinked OCM role correctly rejected with 403 — OCM-role "
                "linkage enforcement is fully applied (ROSA-637 target state)."
            ),
        }
    if status_code == TRANSITION_TOLERATED_STATUS_CODE:
        return {
            "negative_op_rejected": True,
            "enforcement_applied": False,
            "verdict": "rejected_404_transition_tolerated",
            "message": (
                "Unlinked OCM role rejected with 404 (expected 403). TOLERATED "
                "during the enforcement-transition window per ROSAENG-60868: "
                "unlinked currently yields 404. Treated as correctly rejected."
            ),
        }
    if status_code == 200:
        return {
            "negative_op_rejected": False,
            "enforcement_applied": False,
            "verdict": "not_enforced_200",
            "message": (
                "Unlinked OCM role operation returned 200 — enforcement is NOT "
                "applied. This is a meaningful test failure for ROSA-637."
            ),
        }
    return {
        "negative_op_rejected": False,
        "enforcement_applied": False,
        "verdict": "unexpected_status",
        "message": (
            f"Unlinked OCM role probe returned unexpected status "
            f"{status_code!r}; expected 403 (or tolerated 404). Surface for "
            f"triage — this is neither a clean authorization rejection nor a "
            f"known transition behavior."
        ),
    }


class OCMRoleLinkageValidator:
    """Assert unlinked OCM-role operations are rejected, using OCMClient.

    The preflight (`tasks/preflight_check_ocm_role.yml`) already establishes
    OCM-role existence + linkage and auto-fixes it. This validator adds the one
    thing the preflight never did: the *negative* assertion that an unlinked
    operation is rejected (403; 404 tolerated in transition).

    Parameters
    ----------
    ocm_client:
        An `agents.ocm_client.OCMClient` (already carries token exchange +
        Bearer/401-refresh). Injected so this class stays unit-testable.
    aws_account_id:
        The AWS account under test — used to scope the negative probe and for
        messaging.
    negative_probe_path_template:
        The OCM API path (relative to api_url) used for the unauthorized probe.
        Exposed as an overridable attribute because the exact endpoint that
        mirrors the FVT 403-vs-404 semantic is a live-verification residual
        (see module docstring / `OCM_LINKAGE_NEGATIVE_PATH`).
    """

    def __init__(
        self,
        ocm_client,
        aws_account_id: str = "",
        negative_probe_path_template: Optional[str] = None,
    ):
        self.ocm = ocm_client
        self.aws_account_id = aws_account_id

        # NEGATIVE probe: exercise an operation scoped to a resource that
        # requires OCM-role linkage for the AWS account. Without linkage the
        # OCM API rejects it — 403 once enforcement lands, 404 today
        # (ROSAENG-60868). We probe the org's AWS-account-scoped access review;
        # an unlinked account has no such binding and OCM returns 404 today /
        # 403 after enforcement.
        #
        # `{account_id}` is substituted at call time. This template is the
        # single knob to correct once the live 403-vs-404 endpoint is confirmed.
        # VERIFIED-AGAINST-LIVE-OCM PENDING — the exact path/semantic that
        # reproduces the FVT's 403-expected/404-actual is the known residual to
        # nail down during the user's live run (override via
        # OCM_LINKAGE_NEGATIVE_PATH without touching code).
        self.negative_probe_path_template = (
            negative_probe_path_template
            or "/api/accounts_mgmt/v1/access_review"
            "?account_id={account_id}&action=create&resource_type=Cluster"
        )

    def _probe_status(self, path: str) -> int:
        """Issue an authed OCM request and return the HTTP status code.

        Returns 200 on success, or the HTTPError.code on failure. Re-raises
        non-HTTP (network) errors so callers can distinguish a probe that did
        not complete from a probe that returned a status.
        """
        url = f"{self.ocm.api_url}{path}"
        try:
            self.ocm._authed_request(url)
            return 200
        except urllib.error.HTTPError as e:
            return e.code

    def probe_negative(self) -> Dict:
        """Unauthorized probe: expect 403 (tolerate 404) without linkage."""
        # Guard against a false pass: if the negative probe template is scoped
        # by account_id but none was supplied, the substituted query would be
        # malformed (?account_id=&...) and OCM could return 404 for a *bad
        # query* rather than for genuine non-linkage — which verdict_from_status
        # would (wrongly) treat as "rejected_404_transition_tolerated". Refuse
        # to run the negative probe on an empty account_id when the template
        # actually requires it.
        if "{account_id}" in self.negative_probe_path_template and not (
            self.aws_account_id or ""
        ).strip():
            raise ValueError(
                "aws_account_id is required for the negative OCM-role linkage "
                "probe but was empty. Pass -e aws_account_id=<12-digit id> (or "
                "set AWS_ACCOUNT_ID). Running the negative probe without it would "
                "produce a malformed query whose 404 could be mistaken for a "
                "genuine linkage rejection (false pass)."
            )
        path = self.negative_probe_path_template.format(
            account_id=self.aws_account_id or ""
        )
        status = self._probe_status(path)
        decision = verdict_from_status(status)
        decision["status_code"] = status
        decision["path"] = path
        return decision


def validate_from_env() -> Dict:
    """Convenience entry point: build the OCM client from env and run ONLY the
    negative-enforcement probe.

    Reads OCM_CLIENT_ID/OCM_CLIENT_SECRET/OCM_API_URL via OCMClient, and
    aws_account_id from the environment. Returns a structured result dict:
      {negative_op_rejected, negative_status_code, enforcement_applied,
       verdict, messages, [error]}.
    """
    import os

    from agents.ocm_client import OCMClient

    account_id = os.environ.get("aws_account_id") or os.environ.get(
        "AWS_ACCOUNT_ID", ""
    )

    ocm = OCMClient()
    if not ocm.available:
        raise RuntimeError(
            "OCM credentials unavailable — set OCM_CLIENT_ID/OCM_CLIENT_SECRET"
        )

    validator = OCMRoleLinkageValidator(
        ocm_client=ocm,
        aws_account_id=account_id,
        negative_probe_path_template=os.environ.get(
            "OCM_LINKAGE_NEGATIVE_PATH"
        )
        or None,
    )

    negative = validator.probe_negative()
    messages = [
        f"Negative probe {negative['path']} -> HTTP {negative['status_code']}: "
        f"{negative['message']}"
    ]
    return {
        "negative_op_rejected": negative["negative_op_rejected"],
        "negative_status_code": negative["status_code"],
        "enforcement_applied": negative["enforcement_applied"],
        "verdict": negative["verdict"],
        "messages": messages,
    }


if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    result = validate_from_env()
    print(json.dumps(result, indent=2))
