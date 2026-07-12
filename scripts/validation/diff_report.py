"""
diff_report.py — Pre vs Post Migration Diff Report
===================================================
Compares two snapshots produced by pre_check.py and post_check.py.
Generates a structured JSON report and prints a human-readable
console summary.

Can also be run standalone against two saved snapshot files:
    python diff_report.py \
        --pre  snapshots/pre_migration_snapshot.json \
        --post snapshots/post_migration_snapshot.json \
        --report snapshots/diff_report.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── Thresholds ───────────────────────────────────────────────────────────────

# Endpoint count tolerance — a drop of more than this % flags as a failure
ENDPOINT_DROP_THRESHOLD_PCT = 10

# Health score — below this is a failure post-migration
HEALTH_FAILURE_THRESHOLD = 80


# ── Diff logic ───────────────────────────────────────────────────────────────

def diff_health(pre: Optional[int], post: Optional[int]) -> dict:
    """Compare health scores — return delta and status."""
    if pre is None or post is None:
        return {"pre": pre, "post": post, "delta": None, "status": "unknown"}

    delta = post - pre
    if post >= HEALTH_FAILURE_THRESHOLD:
        status = "ok"
    elif post >= 50:
        status = "degraded"
    else:
        status = "critical"

    return {
        "pre":    pre,
        "post":   post,
        "delta":  delta,
        "status": status,
    }


def diff_endpoints(pre_count: int, post_count: int, pre_eps: list, post_eps: list) -> dict:
    """
    Compare endpoint counts and lists.
    Identifies endpoints that appeared or disappeared between snapshots.
    """
    pre_macs  = {ep["mac"] for ep in pre_eps  if ep.get("mac")}
    post_macs = {ep["mac"] for ep in post_eps if ep.get("mac")}

    appeared  = post_macs - pre_macs
    disappeared = pre_macs - post_macs

    delta = post_count - pre_count
    drop_pct = abs(delta / pre_count * 100) if pre_count > 0 else 0

    if post_count == 0 and pre_count > 0:
        status = "critical"    # all endpoints lost
    elif drop_pct > ENDPOINT_DROP_THRESHOLD_PCT and delta < 0:
        status = "degraded"    # significant drop
    else:
        status = "ok"

    return {
        "pre_count":     pre_count,
        "post_count":    post_count,
        "delta":         delta,
        "drop_pct":      round(drop_pct, 1) if delta < 0 else 0,
        "status":        status,
        "appeared":      sorted(appeared),
        "disappeared":   sorted(disappeared),
    }


def diff_faults(pre: dict, post: dict) -> dict:
    """
    Compare fault counts before and after.
    New faults introduced by migration are flagged.
    """
    result   = {}
    statuses = []

    for sev in ["critical", "major", "minor", "warning", "total"]:
        pre_val  = pre.get(sev, 0)
        post_val = post.get(sev, 0)
        delta    = post_val - pre_val

        if sev == "critical" and delta > 0:
            status = "critical"
        elif sev == "major" and delta > 0:
            status = "degraded"
        elif delta > 0:
            status = "warning"
        else:
            status = "ok"

        result[sev] = {
            "pre":    pre_val,
            "post":   post_val,
            "delta":  delta,
            "status": status,
        }
        statuses.append(status)

    # Overall fault status — worst individual severity wins
    priority = {"critical": 3, "degraded": 2, "warning": 1, "ok": 0}
    overall  = max(statuses, key=lambda s: priority.get(s, 0))
    result["overall_status"] = overall

    return result


def diff_epg(pre_epg: dict, post_epg: dict) -> dict:
    """Diff a single EPG across all metrics."""
    health_diff = diff_health(
        pre_epg.get("health_score"),
        post_epg.get("health_score"),
    )
    ep_diff = diff_endpoints(
        pre_epg.get("endpoint_count", 0),
        post_epg.get("endpoint_count", 0),
        pre_epg.get("endpoints", []),
        post_epg.get("endpoints", []),
    )

    # Overall EPG status — worst metric wins
    statuses = [health_diff["status"], ep_diff["status"]]
    priority = {"critical": 3, "degraded": 2, "warning": 1, "unknown": 1, "ok": 0}
    overall  = max(statuses, key=lambda s: priority.get(s, 0))

    return {
        "name":          pre_epg["name"],
        "overall_status": overall,
        "health":        health_diff,
        "endpoints":     ep_diff,
    }


# ── Report assembly ──────────────────────────────────────────────────────────

def generate_report(pre: dict, post: dict) -> dict:
    """
    Build the full diff report from two snapshots.
    Returns a structured dict suitable for JSON output and console printing.
    """
    # Index EPGs by name for easy lookup
    pre_epgs  = {e["name"]: e for e in pre.get("epgs",  [])}
    post_epgs = {e["name"]: e for e in post.get("epgs", [])}

    all_epg_names = sorted(set(pre_epgs) | set(post_epgs))

    epg_diffs = []
    for name in all_epg_names:
        if name in pre_epgs and name in post_epgs:
            epg_diffs.append(diff_epg(pre_epgs[name], post_epgs[name]))
        elif name in post_epgs:
            # EPG appeared after migration — might be expected
            epg_diffs.append({
                "name":           name,
                "overall_status": "warning",
                "note":           "EPG not present in pre-migration snapshot",
                "health":         {"post": post_epgs[name].get("health_score"), "status": "unknown"},
                "endpoints":      {"post_count": post_epgs[name].get("endpoint_count", 0)},
            })
        else:
            # EPG disappeared — almost always a problem
            epg_diffs.append({
                "name":           name,
                "overall_status": "critical",
                "note":           "EPG present pre-migration but missing post-migration",
                "health":         {"pre": pre_epgs[name].get("health_score"), "status": "critical"},
                "endpoints":      {"pre_count": pre_epgs[name].get("endpoint_count", 0)},
            })

    fault_diff = diff_faults(
        pre.get("fault_counts",  {}),
        post.get("fault_counts", {}),
    )

    # Verdict — passed if no EPG is critical and no new critical/major faults
    issues = []
    for epg in epg_diffs:
        if epg["overall_status"] == "critical":
            issues.append(f"EPG {epg['name']}: critical status post-migration")
        elif epg["overall_status"] == "degraded":
            issues.append(f"EPG {epg['name']}: degraded post-migration — investigate")

    if fault_diff.get("critical", {}).get("delta", 0) > 0:
        issues.append(
            f"New critical faults: +{fault_diff['critical']['delta']} "
            f"(total {fault_diff['critical']['post']})"
        )
    if fault_diff.get("major", {}).get("delta", 0) > 0:
        issues.append(
            f"New major faults: +{fault_diff['major']['delta']} "
            f"(total {fault_diff['major']['post']})"
        )

    return {
        "report_meta": {
            "title":        "Migration Validation Diff Report",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "tenant":       pre.get("tenant"),
            "app_profile":  pre.get("app_profile"),
            "pre_captured": pre.get("captured_at"),
            "post_captured":post.get("captured_at"),
        },
        "verdict": {
            "passed": len(issues) == 0,
            "issues": issues,
        },
        "faults": fault_diff,
        "epgs":   epg_diffs,
    }


# ── Console output ───────────────────────────────────────────────────────────

# Console colours — degrade gracefully on terminals that don't support ANSI
try:
    import sys
    _use_colour = sys.stdout.isatty()
except Exception:
    _use_colour = False

def _c(text: str, code: str) -> str:
    if not _use_colour:
        return text
    return f"\033[{code}m{text}\033[0m"

def _ok(t):       return _c(t, "32")   # green
def _warn(t):     return _c(t, "33")   # yellow
def _err(t):      return _c(t, "31")   # red
def _bold(t):     return _c(t, "1")    # bold
def _dim(t):      return _c(t, "2")    # dim


STATUS_ICON = {
    "ok":       "✓",
    "degraded": "⚠",
    "critical": "✗",
    "warning":  "⚠",
    "unknown":  "?",
}

STATUS_COLOUR = {
    "ok":       _ok,
    "degraded": _warn,
    "critical": _err,
    "warning":  _warn,
    "unknown":  _dim,
}

def _status(s: str) -> str:
    icon   = STATUS_ICON.get(s, "?")
    colour = STATUS_COLOUR.get(s, _dim)
    return colour(f"{icon} {s.upper()}")


def print_report(report: dict) -> None:
    meta    = report["report_meta"]
    verdict = report["verdict"]
    faults  = report["faults"]
    epgs    = report["epgs"]

    line = "─" * 60

    print(f"\n{line}")
    print(_bold(f"  Migration Validation Report"))
    print(f"  Tenant      : {meta.get('tenant')}")
    print(f"  App Profile : {meta.get('app_profile')}")
    print(f"  Pre  capture: {meta.get('pre_captured', 'n/a')}")
    print(f"  Post capture: {meta.get('post_captured', 'n/a')}")
    print(line)

    # ── Fault summary ────────────────────────────────────────────────────────
    print(_bold("\n  FAULTS"))
    print(f"  {'Severity':<12} {'Pre':>6} {'Post':>6} {'Delta':>8}  Status")
    print(f"  {'─'*12} {'─'*6} {'─'*6} {'─'*8}  {'─'*10}")

    for sev in ["critical", "major", "minor", "warning"]:
        fd = faults.get(sev, {})
        pre  = fd.get("pre",   0)
        post = fd.get("post",  0)
        delta = fd.get("delta", 0)
        s    = fd.get("status", "ok")
        delta_str = f"+{delta}" if delta > 0 else str(delta)
        colour = STATUS_COLOUR.get(s, _dim)
        print(
            f"  {sev:<12} {pre:>6} {post:>6} {colour(f'{delta_str:>8}')}  {_status(s)}"
        )

    # ── EPG summary ──────────────────────────────────────────────────────────
    print(_bold("\n  EPGs"))
    print(
        f"  {'EPG':<22} {'Health':>8}  {'Hlth Δ':>7}  "
        f"{'EP pre':>7} {'EP post':>8} {'EP Δ':>7}  Status"
    )
    print(f"  {'─'*22} {'─'*8}  {'─'*7}  {'─'*7} {'─'*8} {'─'*7}  {'─'*12}")

    for epg in epgs:
        name    = epg["name"]
        overall = epg.get("overall_status", "unknown")
        h       = epg.get("health",    {})
        e       = epg.get("endpoints", {})

        h_post  = h.get("post",  h.get("pre",  "-"))
        h_delta = h.get("delta", "-")
        h_delta_str = (f"+{h_delta}" if isinstance(h_delta, int) and h_delta > 0
                       else str(h_delta) if h_delta is not None else "-")

        ep_pre  = e.get("pre_count",  e.get("pre",  "-"))
        ep_post = e.get("post_count", e.get("post", "-"))
        ep_d    = e.get("delta", "-")
        ep_d_str = (f"+{ep_d}" if isinstance(ep_d, int) and ep_d > 0
                    else str(ep_d) if ep_d is not None else "-")

        colour  = STATUS_COLOUR.get(overall, _dim)
        print(
            f"  {name:<22} {str(h_post):>8}  {colour(f'{h_delta_str:>7}')}  "
            f"{str(ep_pre):>7} {str(ep_post):>8} {colour(f'{ep_d_str:>7}')}  "
            f"{_status(overall)}"
        )

        # Show disappeared endpoints if any
        disappeared = e.get("disappeared", [])
        if disappeared:
            for mac in disappeared[:5]:   # cap at 5 to keep output readable
                print(f"    {_err('└─ endpoint lost:')} {mac}")
            if len(disappeared) > 5:
                print(f"    {_dim(f'   ... and {len(disappeared)-5} more')}")

    # ── Overall verdict ──────────────────────────────────────────────────────
    print(f"\n{line}")
    if verdict["passed"]:
        print(_ok(_bold("  ✓ MIGRATION PASSED")))
    else:
        print(_err(_bold("  ✗ MIGRATION FAILED")))
        for issue in verdict["issues"]:
            print(f"    {_err('•')} {issue}")
    print(line)


# ── File output ──────────────────────────────────────────────────────────────

def save_report(report: dict, path: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report saved: {path}")


# ── Standalone entry point ───────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate diff report from pre and post migration snapshots"
    )
    p.add_argument(
        "--pre",  default="snapshots/pre_migration_snapshot.json",
        help="Pre-migration snapshot JSON",
    )
    p.add_argument(
        "--post", default="snapshots/post_migration_snapshot.json",
        help="Post-migration snapshot JSON",
    )
    p.add_argument(
        "--report", default="snapshots/diff_report.json",
        help="Output report JSON path",
    )
    return p.parse_args()


def main():
    args = parse_args()

    for path, label in [(args.pre, "Pre"), (args.post, "Post")]:
        if not Path(path).exists():
            print(f"[ERROR] {label} snapshot not found: {path}")
            sys.exit(1)

    with open(args.pre)  as f: pre  = json.load(f)
    with open(args.post) as f: post = json.load(f)

    report = generate_report(pre, post)
    print_report(report)
    save_report(report, args.report)

    sys.exit(0 if report["verdict"]["passed"] else 1)


if __name__ == "__main__":
    main()
