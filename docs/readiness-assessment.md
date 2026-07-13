# DC ACI Migration — Readiness Assessment

**Site:** &lt;site_name&gt;  
**Prepared by:** &lt;lead_engineer&gt;  
**Audit date:** &lt;YYYY-MM-DD&gt;  
**Target migration window:** &lt;YYYY-MM-DD&gt;  
**Approved by:** &lt;approver&gt;

---

## Purpose

This document captures the current-state of the data centre fabric before any Nexus → Cisco ACI migration work begins. It is a team lead deliverable — not a study exercise. Every section must be completed and scored before the go/no-go decision is made. The completed YAML source file (`templates/topology-audit.yaml`) is the authoritative data record; this Markdown document is the stakeholder-facing summary.

---

## How to use this document

1. Complete `templates/topology-audit.yaml` first — it holds the detailed data.
2. Summarise each section here, noting gaps and owners.
3. Score each domain (0–2) and enter totals in the go/no-go table.
4. Review with your change manager and security team before submitting to the CAB.
5. Keep this document in Google Drive (shared with stakeholders) and link it from the GitHub repo README.

---

## Section 1 — Physical & logical inventory

**Score: __ / 2**

### What to capture

- All Nexus switches in scope: hostname, model, NX-OS version, role (core / distribution / access / border-leaf)
- All border devices: routers, firewalls, load balancers, their connected interfaces and routing protocols
- All devices explicitly out of scope (document the reason)

### Current status

> _Summarise what has been captured and what is still outstanding. Example: "9 of 11 Nexus switches audited. N9K-DC1-09 and N9K-DC1-10 pending access — ticket raised with ops team (INC0042311)."_

| Hostname | Model | Role | NX-OS | In-scope | Notes |
|----------|-------|------|-------|----------|-------|
|          |       |      |       |          |       |

**Outstanding items:**

- [ ] &lt;item&gt;

---

## Section 2 — VLAN & VRF mapping

**Score: __ / 2**

### What to capture

- All production VRFs and their RDs
- Every VLAN with subnet, gateway, traffic type, and the ACI construct it maps to: Tenant → VRF → Bridge Domain → EPG
- Unmapped VLANs with a named owner and deadline

### Current status

> _Summarise mapping progress. Example: "42 of 56 VLANs mapped to ACI constructs. 14 VLANs flagged as unmapped — majority owned by the storage team (contact: &lt;name&gt;). No cutover until all 14 are resolved."_

| VLAN ID | VLAN name | Subnet | ACI Tenant | ACI BD | ACI EPG | Mapped |
|---------|-----------|--------|------------|--------|---------|--------|
|         |           |        |            |        |         | ☐      |

**Unmapped VLANs requiring owner action:**

| VLAN ID | Owner team | Contact | Deadline |
|---------|------------|---------|----------|
|         |            |         |          |

---

## Section 3 — BGP neighbour state

**Score: __ / 2**

### What to capture

- All BGP sessions (iBGP and eBGP) on in-scope devices
- Current session state, prefix counts, address families
- Migration action for each session: retain / move-to-ACI / decommission / renegotiate

### Current status

> _Summarise BGP state. Example: "8 BGP sessions total. 6 iBGP (all Established). 2 eBGP with upstream provider — action: renegotiate handoff point to ACI border leaf. Lab test scheduled for &lt;date&gt;."_

| Neighbour IP | AS | Type | State | Prefixes | Migration action |
|--------------|----|------|-------|----------|-----------------|
|              |    |      |       |          |                 |

**BGP risk notes:**

> _Note any sessions where a flap would cause production impact. These drive the rollback plan._

---

## Section 4 — Dependency mapping

**Score: __ / 2**

### What to capture

- All upstream systems that inject routes or policies into this fabric
- All downstream systems (application servers, storage, monitoring) that depend on this fabric for connectivity
- Shared services: DNS, NTP, syslog, SNMP, NetFlow, TACACS/RADIUS — confirm each will remain reachable post-migration

### Current status

> _Summarise dependency status. Example: "Change communications sent to 4 of 6 upstream teams. Awaiting acknowledgement from Security Operations and Storage. Shared services DNS/NTP confirmed reachable via ACI OOB management VRF."_

#### Upstream systems

| System | Owner | Protocol | Criticality | Comms sent |
|--------|-------|----------|-------------|------------|
|        |       |          |             | ☐          |

#### Downstream systems

| System | Owner | Protocol | Criticality | Comms sent |
|--------|-------|----------|-------------|------------|
|        |       |          |             | ☐          |

#### Shared services reachability

| Service | Server IP(s) | Reachable via ACI? | Verified by | Date |
|---------|--------------|--------------------|-------------|------|
| DNS     |              | ☐                  |             |      |
| NTP     |              | ☐                  |             |      |
| Syslog  |              | ☐                  |             |      |
| SNMP    |              | ☐                  |             |      |
| TACACS  |              | ☐                  |             |      |

---

## Section 5 — ACI fabric pre-checks

**Score: __ / 2**

### What to capture

- APIC cluster health (all 3 nodes active, no critical faults)
- All spine and leaf nodes registered, firmware consistent
- Base fabric policy: BGP route reflector pod policy, NTP, OOB management
- APIC reachable from jump host used on change night

### Current status

> _Summarise fabric readiness. Example: "APIC cluster healthy, 3/3 nodes active. Fabric health score: 98. All 4 leaf nodes registered. NTP synced. BGP pod policy configured. One minor fault on leaf-103 (FW-2 link flap) — under investigation."_

#### APIC cluster

| APIC | IP | Version | Role | Health |
|------|----|---------|------|--------|
| apic1 |   |         |      |        |
| apic2 |   |         |      |        |
| apic3 |   |         |      |        |

#### Fabric health checklist

| Check | Status | Notes |
|-------|--------|-------|
| All nodes registered and active | ☐ | |
| No critical faults | ☐ | |
| Firmware consistent across nodes | ☐ | |
| NTP synced on all nodes | ☐ | |
| BGP pod policy configured | ☐ | |
| OOB management reachable from jump host | ☐ | |
| APIC GUI accessible on change night jump host | ☐ | |

---

## Section 6 — Risk register

**Score: __ / 2**

> Full risk details are in `templates/topology-audit.yaml` (risk_register section). This table is the executive summary.

| Risk ID | Description | Probability | Impact | Rating | Owner | Status |
|---------|-------------|-------------|--------|--------|-------|--------|
| R001    |             | —           | —      | —      |       | Open   |
| R002    | BGP session flap during L3 handoff migration | Medium | High | **High** | | Open |
| R003    | Endpoint learning delay causing forwarding blackhole | Medium | Medium | **Medium** | | Open |
| R004    | Change window overrun | Medium | High | **High** | | Open |

**Risk rating key:** Low × Low = Low · Medium × Medium = Medium · High × anything = High · High × High = Critical

---

## Go / No-go decision

### Scoring summary

| Section | Domain | Score (0–2) |
|---------|--------|-------------|
| 1 | Physical & logical inventory | |
| 2 | VLAN & VRF mapping | |
| 3 | BGP neighbour state | |
| 4 | Dependency mapping | |
| 5 | ACI fabric pre-checks | |
| 6 | Risk register | |
| | **Total** | **__ / 12** |

### Decision thresholds

| Total score | Decision |
|-------------|----------|
| 10 – 12 | ✅ **GO** — proceed with scheduled window |
| 7 – 9 | ⚠️ **CONDITIONAL GO** — resolve flagged gaps first; escalate to change manager |
| 0 – 6 | ❌ **NO-GO** — re-audit required; do not schedule cutover |

### Final decision

| | |
|---|---|
| **Score** | __ / 12 |
| **Decision** | &lt;GO / CONDITIONAL GO / NO-GO&gt; |
| **Decision date** | &lt;YYYY-MM-DD&gt; |
| **Decision maker** | &lt;name, title&gt; |
| **Next review** | &lt;YYYY-MM-DD&gt; |
| **Comments** | |

---

## Approvals

| Role | Name | Signature | Date |
|------|------|-----------|------|
| DC Team Lead | | | |
| Change Manager | | | |
| Security / Compliance | | | |
| Application Owner(s) | | | |

---

## Related documents

| Document | Location |
|----------|----------|
| Topology audit data (YAML) | `templates/topology-audit.yaml` |
| Risk register (full) | `templates/topology-audit.yaml` → `risk_register` |
| Migration runbook | `docs/migration-runbook.md` |
| Rollback procedure | `docs/rollback-procedure.md` |
| Team onboarding guide | `docs/team-onboarding-guide.md` |
| Google Drive stakeholder folder | &lt;link&gt; |

---

*This document is version-controlled in Git. Do not edit the Google Drive copy directly — export from the repo as the single source of truth.*
