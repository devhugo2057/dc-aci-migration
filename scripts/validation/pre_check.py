"""
pre_check.py — Pre-Migration State Capture
==========================================
Run this BEFORE the migration window opens.

Captures EPG health, endpoint counts, and fault counts for a tenant
and saves a JSON snapshot to disk. The post_check.py script reads
this snapshot to produce the diff report.

Usage:
    python pre_check.py --tenant TN-LAGOS-DC1 --ap AP-PROD-APPS
    python pre_check.py --tenant TN-LAGOS-DC1 --ap AP-PROD-APPS --output snapshots/pre.json

    # Pass APIC credentials as environment variables (recommended):
    export APIC_HOST=sandboxapicdc.cisco.com
    export APIC_USERNAME=admin
    export APIC_PASSWORD='!v3G@!4@Y'
    python pre_check.py --tenant TN-LAGOS-DC1 --ap AP-PROD-APPS

    # Or pass inline for lab use:
    python pre_check.py \
        --host sandboxapicdc.cisco.com \
        --username admin \
        --password '!v3G@!4@Y' \
        --tenant TN-LAGOS-DC1 \
        --ap AP-PROD-APPS
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from apic_client import ApicClient, ApicError, client_from_env


# ── Snapshot collection ──────────────────────────────────────────────────────

def capture_snapshot(
    client: ApicClient,
    tenant: str,
    ap:     str,
    label:  str = "pre",
) -> dict:
    """
    Collect EPG health, endpoint counts, and fault counts.
    Returns a structured dict ready for JSON serialisation.
    """
    print(f"\n  Discovering EPGs under {tenant}/{ap} ...")
    epg_names = client.list_epgs(tenant, ap)

    if not epg_names:
        print(f"  [WARN] No EPGs found under {ap}. Check tenant/AP names.")

    print(f"  Found {len(epg_names)} EPG(s): {', '.join(epg_names)}")

    epg_snapshots = []
    for epg_name in epg_names:
        print(f"\n  [{epg_name}]")

        # Health
        print(f"    health score    ...", end=" ", flush=True)
        try:
            health = client.get_epg_health(tenant, ap, epg_name)
            print(f"{health['health_score']} ({health['health_status']})")
        except ApicError as exc:
            print(f"ERROR — {exc}")
            health = {"health_score": None, "health_status": "error", "name": epg_name}

        # Endpoints
        print(f"    endpoint count  ...", end=" ", flush=True)
        try:
            ep_data = client.get_endpoint_count(tenant, ap, epg_name)
            print(f"{ep_data['count']}")
        except ApicError as exc:
            print(f"ERROR — {exc}")
            ep_data = {"count": 0, "endpoints": []}

        epg_snapshots.append({
            "name":          epg_name,
            "health_score":  health.get("health_score"),
            "health_status": health.get("health_status"),
            "dn":            health.get("dn", ""),
            "endpoint_count": ep_data["count"],
            "endpoints":     ep_data["endpoints"],
        })

    # Tenant-wide faults
    print(f"\n  Fault counts for tenant {tenant} ...", end=" ", flush=True)
    try:
        faults = client.get_fault_counts(tenant)
        print(
            f"total={faults['total']}  "
            f"critical={faults['critical']}  "
            f"major={faults['major']}  "
            f"minor={faults['minor']}  "
            f"warning={faults['warning']}"
        )
    except ApicError as exc:
        print(f"ERROR — {exc}")
        faults = {"total": 0, "critical": 0, "major": 0, "minor": 0, "warning": 0}

    return {
        "snapshot_label":  label,
        "captured_at":     datetime.now(timezone.utc).isoformat(),
        "tenant":          tenant,
        "app_profile":     ap,
        "fault_counts":    faults,
        "epgs":            epg_snapshots,
    }


# ── Go / No-go assessment ────────────────────────────────────────────────────

def assess_go_nogo(snapshot: dict) -> tuple[bool, list[str]]:
    """
    Evaluate whether the pre-migration state is safe to proceed.
    Returns (go: bool, reasons: list[str]).
    A 'no-go' recommendation does not block the script — it informs.
    """
    issues = []
    faults = snapshot["fault_counts"]

    if faults["critical"] > 0:
        issues.append(
            f"CRITICAL: {faults['critical']} critical fault(s) present — "
            f"must be resolved before migration"
        )
    if faults["major"] > 0:
        issues.append(
            f"MAJOR: {faults['major']} major fault(s) — investigate before proceeding"
        )

    for epg in snapshot["epgs"]:
        score = epg.get("health_score")
        if score is not None and score < 80:
            issues.append(
                f"EPG {epg['name']}: health score {score} — "
                f"below 80 threshold ({'critical' if score < 50 else 'degraded'})"
            )
        if epg["endpoint_count"] == 0:
            issues.append(
                f"EPG {epg['name']}: zero endpoints — "
                f"expected traffic? Verify before cutover"
            )

    return (len(issues) == 0), issues


# ── Entry point ──────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Pre-migration state capture — APIC REST API"
    )
    p.add_argument("--host",     default=os.environ.get("APIC_HOST"),     help="APIC hostname/IP")
    p.add_argument("--username", default=os.environ.get("APIC_USERNAME"), help="APIC username")
    p.add_argument("--password", default=os.environ.get("APIC_PASSWORD"), help="APIC password")
    p.add_argument("--port",     default=443, type=int)
    p.add_argument("--tenant",   required=True, help="Tenant name, e.g. TN-LAGOS-DC1")
    p.add_argument("--ap",       required=True, help="Application Profile name")
    p.add_argument(
        "--output",
        default="snapshots/pre_migration_snapshot.json",
        help="Output file path (default: snapshots/pre_migration_snapshot.json)",
    )
    return p.parse_args()


def main():
    args = parse_args()

    # Validate credentials
    if not all([args.host, args.username, args.password]):
        print(
            "[ERROR] APIC credentials required.\n"
            "  Pass --host, --username, --password\n"
            "  OR set APIC_HOST, APIC_USERNAME, APIC_PASSWORD env vars."
        )
        sys.exit(1)

    # Ensure output directory exists
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  Pre-Migration State Capture")
    print(f"  APIC     : {args.host}")
    print(f"  Tenant   : {args.tenant}")
    print(f"  AP       : {args.ap}")
    print(f"  Output   : {args.output}")
    print("=" * 60)

    client = ApicClient(
        host     = args.host,
        username = args.username,
        password = args.password,
        port     = args.port,
    )

    try:
        client.login()
        print("\n  Logged in to APIC successfully.")

        snapshot = capture_snapshot(client, args.tenant, args.ap)

    except ApicError as exc:
        print(f"\n[ERROR] {exc}")
        sys.exit(1)
    finally:
        client.logout()

    # Save snapshot
    with open(output_path, "w") as f:
        json.dump(snapshot, f, indent=2)

    # Go / no-go
    go, issues = assess_go_nogo(snapshot)

    print("\n" + "=" * 60)
    print("  Pre-Migration Assessment")
    print("=" * 60)

    if go:
        print("  ✓ GO — no blocking issues found")
    else:
        print("  ✗ NO-GO — issues found:")
        for issue in issues:
            print(f"    • {issue}")

    print(f"\n  Snapshot saved: {output_path}")
    print("  Run post_check.py after migration to generate the diff.")
    print("=" * 60)

    # Exit with non-zero code on no-go so CI/CD pipelines can catch it
    sys.exit(0 if go else 1)


if __name__ == "__main__":
    main()
