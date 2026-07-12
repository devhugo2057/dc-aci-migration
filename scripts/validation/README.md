# Pre/Post Migration Validation Suite

Queries the Cisco APIC REST API to capture EPG health, endpoint
counts, and fault counts before and after a migration window.
Generates a structured diff report with a clear PASS/FAIL verdict.

## How it works

pre_check.py        →  captures baseline state before cutover
saves snapshot to snapshots/pre_migration_snapshot.json
outputs go/no-go assessment
[migration happens]
post_check.py       →  captures state after cutover
compares against pre snapshot
calls diff_report.py automatically
diff_report.py      →  generates PASS/FAIL verdict
itemises any EPG health drops
flags lost endpoints by MAC address
flags new critical/major faults

## Files

| File | Purpose |
|------|---------|
| `apic_client.py` | Shared APIC REST client — handles login, session, all API calls |
| `pre_check.py` | Run before migration — captures baseline, outputs go/no-go |
| `post_check.py` | Run after migration — captures post state, triggers diff |
| `diff_report.py` | Standalone diff generator — compare any two snapshots |

## Quickstart

```bash
pip install requests urllib3

# Set credentials as environment variables
export APIC_HOST=sandboxapicdc.cisco.com
export APIC_USERNAME=admin
export APIC_PASSWORD='!v3G@!4@Y'

# Step 1 — capture pre-migration state
python pre_check.py --tenant TN-LAGOS-DC1 --ap AP-PROD-APPS

# Step 2 — run your migration

# Step 3 — capture post-migration state and generate diff
python post_check.py --tenant TN-LAGOS-DC1 --ap AP-PROD-APPS
```

## What the diff report checks

| Check | Pass condition |
|-------|---------------|
| EPG health score | Post score ≥ 80 |
| Endpoint count | Drop of less than 10% |
| Critical faults | Zero new critical faults |
| Major faults | Zero new major faults |

## Sample output
────────────────────────────────────────────────────────────
Migration Validation Report
Tenant      : TN-LAGOS-DC1
App Profile : AP-PROD-APPS
────────────────────────────────────────────────────────────
FAULTS
Severity      Pre   Post    Delta  Status
──────────── ───── ──────  ──────  ──────────
critical          0      0       0  ✓ OK
major             1      1       0  ✓ OK
minor             2      3      +1  ⚠ WARNING
EPGs
EPG           Health  Hlth Δ  EP pre  EP post  EP Δ  Status
──────────── ─────── ─────── ─────── ──────── ───── ──────────
✓ EPG-WEB        97      +2       4        4      0  ✓ OK
✓ EPG-APP        92       0       6        6      0  ✓ OK
✓ EPG-DB        100       0       2        2      0  ✓ OK
✓ EPG-STORAGE    91      +3       2        2      0  ✓ OK
✓ MIGRATION PASSED
────────────────────────────────────────────────────────────

## CI/CD integration

Both `pre_check.py` and `post_check.py` exit with code `1` on
failure. Wire them into a pipeline to stop a migration automatically
if pre-checks are not met.

## Test without physical gear

Uses Cisco DevNet always-on ACI sandbox:
`sandboxapicdc.cisco.com` — credentials on devnetsandbox.cisco.com
