"""
OCM Role Linkage Validator
==========================

Validates *mandatory OCM-role linkage* for ROSA cluster operations.

Background
----------
Jira ROSA-637: OCM roles become mandatory for ROSA cluster operations by the
end of Sept 2026. Regression ROSAENG-60868: an HCP PROD FVT failed because the
`secondRegularConnection` org lacked a linked OCM Role for the prod FVT AWS
account, so the OCM API returned **404** where the test expected **403**.

This module implements the linkage probe the repo did not previously have:
a call that authoritatively distinguishes "authorized (role linked)" from
"rejected (role not linked)". It intentionally reuses the repo's battle-tested
building blocks:
  * `agents.ocm_client.OCMClient` for OCM token exchange + authed requests.
  * `agents.aws_client.AWSClient` / the "find any OCM-Role by substring"
    pattern for the IAM-side existence check.

Assertions produced (first cut, ROSA-637 scope)
-----------------------------------------------
1. POSITIVE: with a properly-linked OCM role, an OCM API cluster operation
   succeeds (authorized).
2. NEGATIVE: without OCM-role linkage, the operation is rejected with a clear
   authorization error. We assert the rejection is a **403**, but **TOLERATE
   404** during the enforcement-transition window (that tolerance is the whole
   point of ROSAENG-60868 — unlinked currently yields 404, and the fix is to
   treat 403-or-404 as "correctly rejected / enforcement applies"). A 200 on
   the negative probe means enforcement is NOT applied and is a meaningful test
   failure.

Lifecycle-persistence (create -> upgrade -> delete) is OUT of scope here.

LIVE-VERIFICATION RESIDUAL (documented, not yet confirmed against live OCM)
--------------------------------------------------------------------------
The exact OCM endpoint whose 403-vs-404 semantics mirror the FVT is a known
live-verification residual. The endpoints below are chosen defensively and are
exposed as instance attributes / function args so they can be corrected without
code surgery once the user runs the live verification step. See
`OCMRoleLinkageValidator.positive_probe_path` /
`.negative_probe_path_template` and the `verdict_from_status` docstring.
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
    """Validate OCM-role linkage using OCMClient + AWSClient.

    Parameters
    ----------
    ocm_client:
        An `agents.ocm_client.OCMClient` (already carries token exchange +
        Bearer/401-refresh). Injected so this class stays unit-testable.
    aws_client:
        An `agents.aws_client.AWSClient` (boto3 IAM access) for the IAM
        OCM-Role existence check.
    aws_account_id:
        The AWS account under test (for messaging / IAM scoping).
    positive_probe_path / negative_probe_path_template:
        The OCM API paths (relative to api_url) used for the authorized and
        unauthorized probes. Exposed as overridable attributes because the
        exact endpoint that mirrors the FVT 403-vs-404 semantic is a
        live-verification residual (see module docstring).
    """

    # PROTECTED_PREFIXES mirrors OcmRoleManager.check_iam_role_exists so we skip
    # the same non-OCM roles when scanning IAM.
    PROTECTED_PREFIXES = ("mv", "melserng")

    def __init__(
        self,
        ocm_client,
        aws_client=None,
        aws_account_id: str = "",
        positive_probe_path: Optional[str] = None,
        negative_probe_path_template: Optional[str] = None,
    ):
        self.ocm = ocm_client
        self.aws = aws_client
        self.aws_account_id = aws_account_id

        # --- Endpoint selection (LIVE-VERIFICATION RESIDUAL) ---------------
        # POSITIVE probe: read the current account's organization. This is the
        # same authenticated org read OcmRoleManager.get_ocm_organization uses.
        # With a linked OCM role the caller is authorized and this returns 200.
        # It is a safe, side-effect-free authorized operation and always
        # available (no pre-existing cluster required), which is why it is the
        # default positive probe. NOTE: the FVT specifically exercised a
        # clusters_mgmt op (kubelet_config / node_pool on an existing cluster);
        # if the user has a cluster id to test against, override
        # positive_probe_path to that clusters_mgmt path for a higher-fidelity
        # positive signal. VERIFIED-AGAINST-LIVE-OCM PENDING.
        self.positive_probe_path = (
            positive_probe_path
            or "/api/accounts_mgmt/v1/current_account"
        )

        # NEGATIVE probe: exercise an operation scoped to a resource that
        # requires OCM-role linkage for the AWS account. Without linkage the
        # OCM API rejects it — 403 once enforcement lands, 404 today
        # (ROSAENG-60868). We probe the org's AWS-infrastructure-access roles
        # view scoped to the account; an unlinked account has no such binding
        # and OCM returns 404 today / 403 after enforcement.
        #
        # `{account_id}` is substituted at call time. This template is the
        # single knob to correct once the live 403-vs-404 endpoint is
        # confirmed. VERIFIED-AGAINST-LIVE-OCM PENDING — the exact path/semantic
        # that reproduces the FVT's 403-expected/404-actual is the known
        # residual to nail down during the user's live run.
        self.negative_probe_path_template = (
            negative_probe_path_template
            or "/api/accounts_mgmt/v1/access_review"
            "?account_id={account_id}&action=create&resource_type=Cluster"
        )

    # ------------------------------------------------------------------
    # IAM side
    # ------------------------------------------------------------------
    def check_iam_ocm_role_exists(self) -> Optional[str]:
        """Return the ARN of an OCM-Role in IAM, or None.

        Mirrors OcmRoleManager.check_iam_role_exists: paginate list_roles,
        match ``"OCM-Role" in name``, skip PROTECTED_PREFIXES.
        """
        if self.aws is None or not getattr(self.aws, "available", False):
            logger.warning("AWSClient/boto3 unavailable — cannot check IAM OCM-Role")
            return None

        iam = self.aws._client("iam")
        if iam is None:
            return None

        paginator = iam.get_paginator("list_roles")
        for page in paginator.paginate():
            for role in page.get("Roles", []):
                name = role["RoleName"]
                if any(name.lower().startswith(p) for p in self.PROTECTED_PREFIXES):
                    continue
                if "OCM-Role" in name:
                    logger.info("Found IAM OCM-Role: %s (%s)", name, role["Arn"])
                    return role["Arn"]
        return None

    # ------------------------------------------------------------------
    # OCM side
    # ------------------------------------------------------------------
    def get_organization_id(self) -> Optional[str]:
        """Return the current account's OCM organization id (or None)."""
        try:
            account = self.ocm._authed_request(
                f"{self.ocm.api_url}/api/accounts_mgmt/v1/current_account"
            )
            return account.get("organization", {}).get("id") or None
        except Exception as e:  # noqa: BLE001 - surface as None for messaging
            logger.warning("Could not read OCM organization: %s", e)
            return None

    def _probe_status(self, path: str) -> int:
        """Issue an authed OCM request and return the HTTP status code.

        Returns 200 on success, or the HTTPError.code on failure. Follows the
        repo's HTTPError.code branching idiom (diagnostic_agent.py ~542-551).
        Re-raises non-HTTP (network) errors so callers can distinguish a probe
        that did not complete from a probe that returned a status.
        """
        url = f"{self.ocm.api_url}{path}"
        try:
            self.ocm._authed_request(url)
            return 200
        except urllib.error.HTTPError as e:
            return e.code

    def probe_positive(self) -> Dict:
        """Authorized probe: expect 200 with a linked OCM role."""
        status = self._probe_status(self.positive_probe_path)
        authorized = status == 200
        return {
            "status_code": status,
            "authorized": authorized,
            "path": self.positive_probe_path,
        }

    def probe_negative(self) -> Dict:
        """Unauthorized probe: expect 403 (tolerate 404) without linkage."""
        # Guard against a false pass: if the negative probe template is scoped
        # by account_id but none was supplied, the substituted query would be
        # malformed (?account_id=&...) and OCM could return 404 for a *bad
        # query* rather than for genuine non-linkage — which verdict_from_status
        # would (wrongly) treat as "rejected_404_transition_tolerated". Refuse
        # to run the negative probe on an empty account_id when the template
        # actually requires it. (suite 20 does not pass aws_account_id, so this
        # must be surfaced, not silently tolerated.)
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

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------
    def validate(self) -> Dict:
        """Run both probes + the IAM check and return a structured result.

        Result keys:
          iam_role_exists, linked, positive_op_authorized,
          negative_op_rejected, negative_status_code, verdict, messages.
        """
        messages = []

        iam_arn = self.check_iam_ocm_role_exists()
        iam_role_exists = iam_arn is not None
        if iam_role_exists:
            messages.append(f"IAM OCM-Role present: {iam_arn}")
        else:
            messages.append(
                "IAM OCM-Role NOT found for the AWS account — OCM-role linkage "
                "cannot succeed (ROSA-637 makes this mandatory)."
            )

        positive = self.probe_positive()
        messages.append(
            f"Positive probe {positive['path']} -> HTTP {positive['status_code']} "
            f"({'authorized' if positive['authorized'] else 'NOT authorized'})"
        )

        negative = self.probe_negative()
        messages.append(
            f"Negative probe {negative['path']} -> HTTP {negative['status_code']}: "
            f"{negative['message']}"
        )

        # "linked" is inferred: IAM role exists AND the authorized op succeeded.
        linked = iam_role_exists and positive["authorized"]

        return {
            "iam_role_exists": iam_role_exists,
            "iam_role_arn": iam_arn,
            "linked": linked,
            "positive_op_authorized": positive["authorized"],
            "positive_status_code": positive["status_code"],
            "negative_op_rejected": negative["negative_op_rejected"],
            "negative_status_code": negative["status_code"],
            "enforcement_applied": negative["enforcement_applied"],
            "verdict": negative["verdict"],
            "messages": messages,
        }


def validate_from_env() -> Dict:
    """Convenience entry point: build clients from env and validate.

    Reads OCM_CLIENT_ID/OCM_CLIENT_SECRET/OCM_API_URL via OCMClient, and
    aws_account_id/aws_region from the environment. Returns the structured
    result dict from `OCMRoleLinkageValidator.validate`.
    """
    import os

    from agents.aws_client import AWSClient
    from agents.ocm_client import OCMClient

    region = os.environ.get("aws_region") or os.environ.get(
        "AWS_DEFAULT_REGION", "us-west-2"
    )
    account_id = os.environ.get("aws_account_id") or os.environ.get(
        "AWS_ACCOUNT_ID", ""
    )

    ocm = OCMClient()
    if not ocm.available:
        raise RuntimeError(
            "OCM credentials unavailable — set OCM_CLIENT_ID/OCM_CLIENT_SECRET"
        )
    aws = AWSClient(region=region)

    validator = OCMRoleLinkageValidator(
        ocm_client=ocm,
        aws_client=aws,
        aws_account_id=account_id,
        positive_probe_path=os.environ.get("OCM_LINKAGE_POSITIVE_PATH") or None,
        negative_probe_path_template=os.environ.get(
            "OCM_LINKAGE_NEGATIVE_PATH"
        )
        or None,
    )
    return validator.validate()


if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    result = validate_from_env()
    print(json.dumps(result, indent=2))
