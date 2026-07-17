# dc-aci-migration-project
# DC ACI Migration — Team Lead Portfolio

A practical portfolio documenting the end-to-end migration of a data
center team from traditional Nexus CLI operations to Cisco ACI and
network automation.

Built by a network engineer with 11 years of telecoms operations
experience (Nokia SR OS, BGP) stepping into a Data Center Team Lead
role. This repo captures the planning, tooling, and execution work —
not exam prep.

---

## What this project covers

| Phase | Focus | Status |
|-------|-------|--------|
| 1 — Planning | Readiness assessment, risk register, topology audit | ✅ Complete |
| 2 — Inventory | Pre-migration state capture via NX-API (Python) | ✅ Complete |
| 3 — Provisioning | ACI tenant provisioning via Ansible + cisco.aci | ✅ Complete |
| 4 — Validation | Pre/post migration checks via APIC REST API | ✅ Complete |
| 5 — Documentation | Runbook, rollback procedure, team onboarding guide | ✅ Complete |

---

## Repo structure
dc-aci-migration/
├── scripts/
│   ├── inventory/        # NX-API inventory collector
│   └── validation/       # APIC pre/post validation suite
├── ansible/              # Tenant provisioning playbook + vars
├── docs/                 # Runbook, readiness assessment, onboarding guide
├── snapshots/            # Sample pre/post JSON for diff testing
└── README.md

---

## Background

The migration scenario:

- **From:** Traditional Nexus fabric — manual CLI, VLAN-based
  segmentation, no automation
- **To:** Cisco ACI — policy-driven, EPG/contract model,
  Python/Ansible automation
- **Team context:** CLI-first engineers being introduced to
  infrastructure-as-code practices

This is the exact transition many DC teams face. The projects here
are the deliverables a lead would actually produce — not tutorials.

---

## Projects

### 1. Pre-ACI Inventory Collector
`scripts/inventory/`

Python + NX-API. Queries multiple Nexus switches and outputs a
structured JSON snapshot covering interface state, VLAN table, and
BGP neighbour status. Used as the pre-migration baseline.

### 2. ACI Tenant Provisioning Playbook
`ansible/`

Ansible + cisco.aci collection. Provisions a complete tenant — VRF,
Bridge Domains, Application Profile, EPGs, Filters, and Contracts —
from a single YAML vars file. Engineers edit the vars file only.

### 3. Pre/Post Migration Validation Suite
`scripts/validation/`

Python + APIC REST API. Captures EPG health scores, endpoint counts,
and fault counts before and after a migration window. Generates a
structured diff report with a clear PASS/FAIL verdict.

---

## Testing without physical gear

All scripts are tested against Cisco's always-on DevNet sandboxes:

- **NX-OS sandbox:** `sbx-nxos-mgmt.cisco.com` — for inventory
  collector
- **ACI sandbox:** `sandboxapicdc.cisco.com` — for provisioning
  playbook and validation suite

No lab equipment required to run and verify everything in this repo.

---

## Author

**Ugochukwu Owete**
Network Engineer · Lagos, Nigeria
11 years telecoms operations · Nokia SR OS · BGP · Cisco ACI

[LinkedIn](https://www.linkedin.com/in/ugochukwu-owete/)
