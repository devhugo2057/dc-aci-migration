"""
post_check.py — Post-Migration State Capture
============================================
Run this AFTER the migration window closes.

Captures the same data points as pre_check.py, saves a post-migration
snapshot, then calls diff_report.py to generate the comparison.

Usage:
    python post_check.py \
        --tenant TN-LAGOS-DC1 \
        --ap AP-PROD-APPS \
        --pre snapshots/pre_migration_snapshot.json

    # With credentials via env vars:
    export APIC_HOST=sandboxapicdc.cisco.com
    export APIC_USERNAME=admin
    export APIC_PASSWORD='!v3G@!4@Y'
    python post_check.py --tenant TN-LAGOS-DC1 --ap AP-PROD-APPS
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from apic_client import ApicClient, ApicError
from pre_check   import capture_snapshot, assess_go_nogo
from diff_report import generate_report, print_report, save_report


# ── Entry point ──────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Post-migration state capture and diff — APIC REST API"
    )
    p.add_argument("--host",     default=os.environ.get("APIC_HOST"))
    p.add_argument("--username", default=os.environ.get("APIC_USERNAME"))
    p.add_argument("--password", default=os.environ.get("APIC_PASSWORD"))
    p.add_argument("--port",     default=443, type=int)
    p.add_argument("--tenant",   required=True)
    p.add_argument("--ap",       required=True)
    p.add_argument(
        "--pre",
        default="snapshots/pre_migration_snapshot.json",
        help="Path to pre-migration snapshot (default: snapshots/pre_migration_snapshot.json)",
    )
    p.add_argument(
        "--post-output",
        default="snapshots/post_migration_snapshot.json",
        help="Where to save the post snapshot",
    )
    p.add_argument(
        "--report",
        default="snapshots/diff_report.json",
        help="Where to save the diff report JSON",
    )
    return p.parse_args()


def main():
    args = parse_args()

    if not all([args.host, args.username, args.password]):
        print(
            "[ERROR] APIC credentials required.\n"
            "  Pass --host, --username, --password\n"
            "  OR set APIC_HOST, APIC_USERNAME, APIC_PASSWORD env vars."
        )
        sys.exit(1)

    # Load pre-migration snapshot
    pre_path = Path(args.pre)
    if not pre_path.exists():
        print(
            f"[ERROR] Pre-migration snapshot not found: {args.pre}\n"
            f"  Run pre_check.py first."
        )
        sys.exit(1)

    with open(pre_path) as f:
        pre_snapshot = json.load(f)

    print("=" * 60)
    print("  Post-Migration State Capture")
    print(f"  APIC      : {args.host}")
    print(f"  Tenant    : {args.tenant}")
    print(f"  AP        : {args.ap}")
    print(f"  Pre snap  : {args.pre}")
    print(f"  Post snap : {args.post_output}")
    print("=" * 60)

    # Capture post state
    client = ApicClient(
        host     = args.host,
        username = args.username,
        password = args.password,
        port     = args.port,
    )

    try:
        client.login()
        print("\n  Logged in to APIC successfully.")
        post_snapshot = capture_snapshot(
            client, args.tenant, args.ap, label="post"
        )
    except ApicError as exc:
        print(f"\n[ERROR] {exc}")
        sys.exit(1)
    finally:
        client.logout()

    # Save post snapshot
    post_path = Path(args.post_output)
    post_path.parent.mkdir(parents=True, exist_ok=True)
    with open(post_path, "w") as f:
        json.dump(post_snapshot, f, indent=2)
    print(f"\n  Post snapshot saved: {post_path}")

    # Generate and display diff report
    report = generate_report(pre_snapshot, post_snapshot)
    print_report(report)
    save_report(report, args.report)

    # Overall pass/fail
    # Migration passes if: no new critical/major faults, all EPGs healthy,
    # endpoint count stable (within 10% tolerance)
    verdict = report["verdict"]
    print("\n" + "=" * 60)
    if verdict["passed"]:
        print("  ✓ MIGRATION PASSED — all checks within tolerance")
    else:
        print("  ✗ MIGRATION FAILED — review issues below:")
        for issue in verdict["issues"]:
            print(f"    • {issue}")
    print(f"\n  Full report: {args.report}")
    print("=" * 60)

    sys.exit(0 if verdict["passed"] else 1)


if __name__ == "__main__":
    main()
