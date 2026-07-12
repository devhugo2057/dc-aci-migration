"""
apic_client.py — Shared APIC REST API client
=============================================
Used by pre_check.py and post_check.py.
Handles authentication, session management, and all API calls.

All APIC REST responses follow the same envelope:
  { "imdata": [ { "objectClass": { "attributes": {...} } }, ... ],
    "totalCount": "N" }

This module unwraps that envelope so callers only deal with clean dicts.
"""

import requests
import urllib3
import json
import os
import sys
from typing import Optional

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ── Constants ────────────────────────────────────────────────────────────────

# APIC REST API paths
PATHS = {
    "login":        "/api/aaaLogin.json",
    "epg":          "/api/mo/uni/tn-{tenant}/ap-{ap}/epg-{epg}.json",
    "epgs_in_ap":   "/api/mo/uni/tn-{tenant}/ap-{ap}.json",
    "endpoints":    "/api/mo/uni/tn-{tenant}/ap-{ap}/epg-{epg}.json",
    "faults":       "/api/mo/uni/tn-{tenant}.json",
    "tenant_faults":"/api/node/class/faultInst.json",
}

# EPG health score thresholds — used in diff report colouring
HEALTH_CRITICAL = 50
HEALTH_WARNING  = 80


class ApicError(Exception):
    """Raised when an APIC API call fails or returns unexpected data."""
    pass


# ── APIC client ──────────────────────────────────────────────────────────────

class ApicClient:
    """
    Thin wrapper around the APIC REST API.
    Handles login, session cookie, and GET requests.

    Usage:
        client = ApicClient("sandboxapicdc.cisco.com", "admin", "password")
        client.login()
        epg_data = client.get_epg_health("MyTenant", "MyAP", "EPG-WEB")
        client.logout()

    Or use as a context manager:
        with ApicClient(...) as client:
            data = client.get_epg_health(...)
    """

    def __init__(
        self,
        host:           str,
        username:       str,
        password:       str,
        port:           int  = 443,
        use_ssl:        bool = True,
        validate_certs: bool = False,
    ):
        scheme       = "https" if use_ssl else "http"
        self.base    = f"{scheme}://{host}:{port}"
        self.username = username
        self.password = password
        self.validate = validate_certs
        self.session  = requests.Session()
        self.session.verify = validate_certs
        self._logged_in = False

    # ── Authentication ───────────────────────────────────────────────────────

    def login(self) -> None:
        """Authenticate and store the session cookie for subsequent calls."""
        url     = self.base + PATHS["login"]
        payload = {
            "aaaUser": {
                "attributes": {
                    "name": self.username,
                    "pwd":  self.password,
                }
            }
        }
        resp = self.session.post(url, json=payload, timeout=15)
        if resp.status_code != 200:
            raise ApicError(
                f"Login failed — HTTP {resp.status_code}. "
                f"Check credentials and APIC reachability."
            )
        data = resp.json()
        # APIC returns the token in imdata on successful login
        try:
            token = data["imdata"][0]["aaaLogin"]["attributes"]["token"]
            self.session.headers.update({"APIC-cookie": token})
            self._logged_in = True
        except (KeyError, IndexError) as exc:
            raise ApicError(f"Login response missing token: {exc}") from exc

    def logout(self) -> None:
        """Invalidate the APIC session."""
        if self._logged_in:
            try:
                self.session.post(
                    self.base + "/api/aaaLogout.json",
                    json={"aaaUser": {"attributes": {"name": self.username}}},
                    timeout=10,
                )
            except Exception:
                pass  # best-effort — don't fail on logout errors
            self._logged_in = False

    def __enter__(self):
        self.login()
        return self

    def __exit__(self, *_):
        self.logout()

    # ── Raw API call ─────────────────────────────────────────────────────────

    def _get(self, path: str, params: Optional[dict] = None) -> list:
        """
        Execute a GET against the APIC and return the imdata list.
        Raises ApicError on non-200 or unexpected structure.
        """
        if not self._logged_in:
            raise ApicError("Not logged in — call .login() first.")

        url  = self.base + path
        resp = self.session.get(url, params=params, timeout=15)

        if resp.status_code != 200:
            raise ApicError(
                f"GET {path} returned HTTP {resp.status_code}: {resp.text[:200]}"
            )
        data = resp.json()
        return data.get("imdata", [])

    # ── EPG health ───────────────────────────────────────────────────────────

    def get_epg_health(
        self, tenant: str, ap: str, epg: str
    ) -> dict:
        """
        Return health score and basic attributes for a single EPG.
        Health score: 0 (critical) – 100 (fully healthy).
        """
        path = (
            f"/api/mo/uni/tn-{tenant}/ap-{ap}/epg-{epg}.json"
            f"?rsp-subtree-include=health,required"
        )
        items = self._get(path)

        epg_attrs   = {}
        health_score = None

        for item in items:
            if "fvAEPg" in item:
                epg_attrs = item["fvAEPg"]["attributes"]
            if "healthInst" in item:
                try:
                    health_score = int(item["healthInst"]["attributes"]["cur"])
                except (KeyError, ValueError):
                    pass

        return {
            "name":         epg_attrs.get("name",      epg),
            "dn":           epg_attrs.get("dn",        ""),
            "pref_gr_memb": epg_attrs.get("prefGrMemb",""),
            "health_score": health_score,
            "health_status": _health_label(health_score),
        }

    # ── Endpoint count ───────────────────────────────────────────────────────

    def get_endpoint_count(
        self, tenant: str, ap: str, epg: str
    ) -> dict:
        """
        Return total endpoint count and a list of endpoints for an EPG.
        Each endpoint includes MAC, IP (if known), and encap VLAN.
        """
        path = (
            f"/api/mo/uni/tn-{tenant}/ap-{ap}/epg-{epg}.json"
            f"?rsp-subtree-include=count"
            f"&rsp-subtree-class=fvCEp"
        )
        # First get the count
        count_items = self._get(path)
        count = 0
        for item in count_items:
            if "moCount" in item:
                try:
                    count = int(item["moCount"]["attributes"]["count"])
                except (KeyError, ValueError):
                    pass

        # Then get the actual endpoints (capped at 100 — enough for a diff)
        ep_path = (
            f"/api/mo/uni/tn-{tenant}/ap-{ap}/epg-{epg}.json"
            f"?rsp-subtree=children&rsp-subtree-class=fvCEp"
            f"&rsp-subtree-include=required"
        )
        ep_items = self._get(ep_path)
        endpoints = []
        for item in ep_items:
            if "fvCEp" in item:
                attrs = item["fvCEp"]["attributes"]
                endpoints.append({
                    "mac":   attrs.get("mac",   ""),
                    "ip":    attrs.get("ip",    "0.0.0.0"),
                    "encap": attrs.get("encap", ""),
                })

        return {
            "count":     count,
            "endpoints": endpoints,
        }

    # ── Fault count ──────────────────────────────────────────────────────────

    def get_fault_counts(self, tenant: str) -> dict:
        """
        Return fault counts for a tenant, broken down by severity.
        Severities: critical, major, minor, warning.
        """
        path = (
            f"/api/node/class/faultInst.json"
            f"?query-target-filter=wcard(faultInst.dn,\"tn-{tenant}/\")"
            f"&rsp-subtree-include=count"
        )
        # Total count first
        count_items = self._get(path)
        total = 0
        for item in count_items:
            if "moCount" in item:
                try:
                    total = int(item["moCount"]["attributes"]["count"])
                except (KeyError, ValueError):
                    pass

        # Breakdown by severity
        severities = {}
        for sev in ["critical", "major", "minor", "warning"]:
            sev_path = (
                f"/api/node/class/faultInst.json"
                f"?query-target-filter=and("
                f"wcard(faultInst.dn,\"tn-{tenant}/\"),"
                f"eq(faultInst.severity,\"{sev}\"))"
                f"&rsp-subtree-include=count"
            )
            sev_items = self._get(sev_path)
            for item in sev_items:
                if "moCount" in item:
                    try:
                        severities[sev] = int(
                            item["moCount"]["attributes"]["count"]
                        )
                    except (KeyError, ValueError):
                        severities[sev] = 0
            if sev not in severities:
                severities[sev] = 0

        return {
            "total":    total,
            "critical": severities.get("critical", 0),
            "major":    severities.get("major",    0),
            "minor":    severities.get("minor",    0),
            "warning":  severities.get("warning",  0),
        }

    # ── All EPGs in an AP ────────────────────────────────────────────────────

    def list_epgs(self, tenant: str, ap: str) -> list[str]:
        """Return list of EPG names under an Application Profile."""
        path = (
            f"/api/mo/uni/tn-{tenant}/ap-{ap}.json"
            f"?rsp-subtree=children&rsp-subtree-class=fvAEPg"
        )
        items  = self._get(path)
        result = []
        for item in items:
            if "fvAEPg" in item:
                name = item["fvAEPg"]["attributes"].get("name", "")
                if name:
                    result.append(name)
        return sorted(result)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _health_label(score: Optional[int]) -> str:
    if score is None:
        return "unknown"
    if score >= HEALTH_WARNING:
        return "healthy"
    if score >= HEALTH_CRITICAL:
        return "degraded"
    return "critical"


def client_from_env() -> "ApicClient":
    """
    Build an ApicClient from environment variables.
    Useful for CI/CD pipelines — avoids credentials in files.

    Required env vars:
        APIC_HOST, APIC_USERNAME, APIC_PASSWORD
    Optional:
        APIC_PORT (default 443), APIC_VALIDATE_CERTS (default false)
    """
    host     = os.environ.get("APIC_HOST")
    username = os.environ.get("APIC_USERNAME")
    password = os.environ.get("APIC_PASSWORD")

    missing = [k for k, v in {
        "APIC_HOST": host,
        "APIC_USERNAME": username,
        "APIC_PASSWORD": password,
    }.items() if not v]

    if missing:
        print(f"[ERROR] Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    return ApicClient(
        host           = host,
        username       = username,
        password       = password,
        port           = int(os.environ.get("APIC_PORT", 443)),
        validate_certs = os.environ.get("APIC_VALIDATE_CERTS", "false").lower() == "true",
    )
