"""
OCM API Client
==============

Shared client for OpenShift Cluster Manager REST API. Replaces rosa CLI
subprocess calls with direct HTTP requests for cluster listing, version
queries, and account info.

Falls back to rosa CLI when OCM credentials are unavailable.
"""

import json
import logging
import os
import ssl
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("agent.ocm_client")

try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = None

SSO_TOKEN_URL = "https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token"


class OCMClient:
    """OCM REST API client with rosa CLI fallback."""

    def __init__(self, client_id: str = "", client_secret: str = "",
                 api_url: str = "", log_fn=None):
        self.client_id = client_id or os.environ.get("OCM_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("OCM_CLIENT_SECRET", "")
        self.api_url = (api_url or os.environ.get(
            "OCM_API_URL", "https://api.stage.openshift.com"
        )).rstrip("/")
        self._log_fn = log_fn
        self._token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._ocm_client_id: Optional[str] = None

        if not self.client_id or not self.client_secret:
            self._load_ocm_config()

    def _load_ocm_config(self):
        ocm_paths = [
            os.path.expanduser("~/Library/Application Support/ocm/ocm.json"),
            os.path.expanduser("~/.config/ocm/ocm.json"),
        ]
        for path in ocm_paths:
            try:
                with open(path) as f:
                    config = json.load(f)
                self._refresh_token = config.get("refresh_token", "")
                self._ocm_client_id = config.get("client_id", "ocm-cli")
                if config.get("url"):
                    self.api_url = config["url"].rstrip("/")
                if self._refresh_token:
                    self._log(f"Loaded OCM refresh token from {path}", "debug")
                    return
            except (FileNotFoundError, json.JSONDecodeError):
                continue

    @property
    def available(self) -> bool:
        return bool((self.client_id and self.client_secret) or self._refresh_token)

    def _log(self, message: str, level: str = "info"):
        if self._log_fn:
            self._log_fn(message, level)
        else:
            getattr(logger, level if level != "success" else "info")(message)

    def _api_request(self, url: str, method: str = "GET", data: dict = None,
                     headers: dict = None, timeout: int = 15) -> dict:
        hdrs = {"Accept": "application/json"}
        if headers:
            hdrs.update(headers)

        body = None
        if data is not None:
            content_type = hdrs.get("Content-Type", "application/json")
            if content_type == "application/json":
                body = json.dumps(data).encode()
            else:
                body = urllib.parse.urlencode(data).encode()

        req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CONTEXT) as resp:
            return json.loads(resp.read().decode())

    def _get_token(self) -> str:
        if self._token:
            return self._token

        if self.client_id and self.client_secret:
            result = self._api_request(
                SSO_TOKEN_URL,
                method="POST",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        elif self._refresh_token:
            result = self._api_request(
                SSO_TOKEN_URL,
                method="POST",
                data={
                    "grant_type": "refresh_token",
                    "client_id": self._ocm_client_id or "ocm-cli",
                    "refresh_token": self._refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if result.get("refresh_token"):
                self._refresh_token = result["refresh_token"]
        else:
            raise RuntimeError("No OCM credentials available")

        self._token = result.get("access_token", "")
        if not self._token:
            raise RuntimeError(f"Failed to get OCM token: {result.get('error', 'unknown error')}")
        return self._token

    def _authed_request(self, url: str, **kwargs) -> dict:
        token = self._get_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        try:
            return self._api_request(url, headers=headers, **kwargs)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                self.invalidate_token()
                token = self._get_token()
                headers["Authorization"] = f"Bearer {token}"
                return self._api_request(url, headers=headers, **kwargs)
            raise

    def invalidate_token(self):
        self._token = None

    # ================================================================
    # Account
    # ================================================================

    def whoami(self) -> Optional[Dict]:
        if not self.available:
            return self._whoami_cli()

        try:
            account = self._authed_request(
                f"{self.api_url}/api/accounts_mgmt/v1/current_account"
            )
            org = account.get("organization", {})
            return {
                "success": True,
                "authenticated": True,
                "user_info": {
                    "ocm_account_email": account.get("email", ""),
                    "ocm_account_name": f"{account.get('first_name', '')} {account.get('last_name', '')}".strip(),
                    "ocm_account_username": account.get("username", ""),
                    "ocm_account_id": account.get("id", ""),
                    "ocm_organization_id": org.get("id", ""),
                    "ocm_organization_name": org.get("name", ""),
                    "ocm_organization_external_id": org.get("external_id", ""),
                },
                "message": "OCM API authenticated",
                "source": "ocm_api",
            }
        except Exception as e:
            self._log(f"OCM whoami failed: {e}", "debug")
            return self._whoami_cli()

    def _whoami_cli(self) -> Optional[Dict]:
        try:
            result = subprocess.run(
                ["rosa", "whoami"], capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                return None

            user_info = {}
            for line in result.stdout.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    user_info[key.strip().lower().replace(" ", "_")] = value.strip()
            return {
                "success": True,
                "authenticated": True,
                "user_info": user_info,
                "raw_output": result.stdout,
                "message": "ROSA CLI authenticated",
                "source": "rosa_cli",
            }
        except Exception:
            return None

    # ================================================================
    # Clusters
    # ================================================================

    def list_clusters(self) -> Tuple[List[Dict], Optional[str]]:
        if not self.available:
            return self._list_clusters_cli()

        try:
            page = 1
            all_clusters = []
            while True:
                resp = self._authed_request(
                    f"{self.api_url}/api/clusters_mgmt/v1/clusters"
                    f"?page={page}&size=100"
                )
                items = resp.get("items", [])
                for c in items:
                    region = c.get("region", {})
                    api_obj = c.get("api", {})
                    console_obj = c.get("console", {})
                    all_clusters.append({
                        "name": c.get("name", "unknown"),
                        "status": c.get("state", "unknown"),
                        "region": region.get("id", "N/A") if isinstance(region, dict) else str(region),
                        "version": c.get("openshift_version", "N/A"),
                        "created": c.get("creation_timestamp"),
                        "api_url": api_obj.get("url") if isinstance(api_obj, dict) else None,
                        "console_url": console_obj.get("url") if isinstance(console_obj, dict) else None,
                    })
                total = resp.get("total", 0)
                if page * 100 >= total:
                    break
                page += 1

            return all_clusters, None
        except Exception as e:
            self._log(f"OCM list_clusters failed: {e}, falling back to CLI", "debug")
            return self._list_clusters_cli()

    def _list_clusters_cli(self) -> Tuple[List[Dict], Optional[str]]:
        try:
            result = subprocess.run(
                ["rosa", "list", "clusters", "-o", "json"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return [], result.stderr.strip() or "rosa list clusters failed"

            clusters = json.loads(result.stdout)
            cluster_list = []
            for c in clusters:
                region = c.get("region", {})
                cluster_list.append({
                    "name": c.get("name", "unknown"),
                    "status": c.get("state", "unknown"),
                    "region": region.get("id", "N/A") if isinstance(region, dict) else str(region),
                    "version": c.get("openshift_version", "N/A"),
                    "created": c.get("creation_timestamp"),
                })
            return cluster_list, None
        except Exception as e:
            return [], str(e)

    def describe_cluster(self, cluster_name: str) -> Tuple[Optional[Dict], Optional[str]]:
        if not self.available:
            return self._describe_cluster_cli(cluster_name)

        try:
            search = urllib.parse.quote(f"name='{cluster_name}'")
            resp = self._authed_request(
                f"{self.api_url}/api/clusters_mgmt/v1/clusters?search={search}"
            )
            items = resp.get("items", [])
            if not items:
                return None, f"Cluster '{cluster_name}' not found"

            exact = [c for c in items if c.get("name") == cluster_name]
            c = exact[0] if exact else items[0]

            region = c.get("region", {})
            api_obj = c.get("api", {})
            console_obj = c.get("console", {})
            return {
                "name": c.get("name"),
                "state": c.get("state"),
                "version": c.get("openshift_version"),
                "region": region.get("id") if isinstance(region, dict) else str(region),
                "api_url": api_obj.get("url") if isinstance(api_obj, dict) else None,
                "console_url": console_obj.get("url") if isinstance(console_obj, dict) else None,
                "created": c.get("creation_timestamp"),
                "id": c.get("id"),
            }, None
        except Exception as e:
            self._log(f"OCM describe_cluster failed: {e}, falling back to CLI", "debug")
            return self._describe_cluster_cli(cluster_name)

    def _describe_cluster_cli(self, cluster_name: str) -> Tuple[Optional[Dict], Optional[str]]:
        try:
            result = subprocess.run(
                ["rosa", "describe", "cluster", "--cluster", cluster_name, "-o", "json"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return None, result.stderr.strip() or "rosa describe cluster failed"

            c = json.loads(result.stdout)
            region = c.get("region", {})
            api_obj = c.get("api", {})
            console_obj = c.get("console", {})
            return {
                "name": c.get("name"),
                "state": c.get("state"),
                "version": c.get("openshift_version"),
                "region": region.get("id") if isinstance(region, dict) else str(region),
                "api_url": api_obj.get("url") if isinstance(api_obj, dict) else None,
                "console_url": console_obj.get("url") if isinstance(console_obj, dict) else None,
                "created": c.get("creation_timestamp"),
                "id": c.get("id"),
            }, None
        except Exception as e:
            return None, str(e)

    # ================================================================
    # Versions
    # ================================================================

    def list_versions(self, channel_group: str = "stable") -> Tuple[List[str], Optional[str]]:
        if not self.available:
            return self._list_versions_cli(channel_group)

        try:
            search = urllib.parse.quote(
                f"channel_group='{channel_group}' and rosa_enabled='true' and hosted_control_plane_enabled='true'"
            )
            resp = self._authed_request(
                f"{self.api_url}/api/clusters_mgmt/v1/versions"
                f"?search={search}&order=id+desc&size=100"
            )
            versions = []
            for v in resp.get("items", []):
                raw_id = v.get("raw_id") or v.get("id", "")
                if raw_id.startswith("openshift-"):
                    raw_id = raw_id.replace("openshift-v", "").replace("openshift-", "")
                parts = raw_id.split(".")
                if len(parts) == 3 and all(p.replace("-", "").replace("rc", "").isdigit() or p.isdigit() for p in parts):
                    versions.append(raw_id)
            return versions, None
        except Exception as e:
            self._log(f"OCM list_versions failed: {e}, falling back to CLI", "debug")
            return self._list_versions_cli(channel_group)

    def _list_versions_cli(self, channel_group: str = "stable") -> Tuple[List[str], Optional[str]]:
        try:
            result = subprocess.run(
                ["rosa", "list", "versions", "--channel-group", channel_group],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return [], result.stderr.strip() or "rosa list versions failed"

            versions = []
            for line in result.stdout.split("\n"):
                if line.strip() and not line.startswith("VERSION") and not line.startswith("WARN"):
                    parts = line.split()
                    if parts and parts[0]:
                        version = parts[0]
                        if len(version.split(".")) == 3:
                            versions.append(version)
            return versions, None
        except Exception as e:
            return [], str(e)


_default_client: Optional[OCMClient] = None


def get_ocm_client(**kwargs) -> OCMClient:
    global _default_client
    if _default_client is None:
        _default_client = OCMClient(**kwargs)
    return _default_client
