# ACI Migration Runbook
## Moving a Legacy Nexus VLAN Domain into Cisco ACI Fabric

| | |
|---|---|
| **Document ref** | `docs/migration-runbook.md` |
| **Repo** | `dc-aci-migration` |
| **Version** | 1.0 |
| **Status** | DRAFT — pending CAB approval |
| **Site** | &lt;site_name&gt; |
| **Target VLAN domain** | &lt;vlan_range, e.g. VLANs 10–99 / VRF PROD&gt; |
| **Change window** | &lt;YYYY-MM-DD HH:MM – HH:MM WAT&gt; |
| **Prepared by** | &lt;DC Team Lead&gt; |
| **Last updated** | &lt;YYYY-MM-DD&gt; |

---

## Table of contents

1. [Purpose and scope](#1-purpose-and-scope)
2. [Engineer roles and responsibilities](#2-engineer-roles-and-responsibilities)
3. [Communication plan](#3-communication-plan)
4. [Pre-migration checklist](#4-pre-migration-checklist)
5. [ACI construct mapping reference](#5-aci-construct-mapping-reference)
6. [Cutover procedure](#6-cutover-procedure)
7. [Post-cutover validation](#7-post-cutover-validation)
8. [Rollback procedure](#8-rollback-procedure)
9. [Sign-off and closure](#9-sign-off-and-closure)
10. [Related documents](#10-related-documents)

---

## 1. Purpose and scope

This runbook is the step-by-step operational guide for migrating one VLAN domain from the legacy Cisco Nexus fabric into the Cisco ACI fabric at `<site_name>`. It is designed to be executed verbatim on change night — every command is written out in full so that any DC engineer on the team can carry out a step without referring to external documentation.

### In scope

- VLANs `<range>` in VRF `<name>` on switches `<list>`
- Associated SVI (gateway) interfaces on the Nexus core switches
- BGP sessions that carry prefixes from this VRF to upstream routers
- Endpoint connectivity for servers attached to the in-scope VLANs

### Out of scope

- VLANs outside the defined range
- Storage fabric (handled under separate CR)
- Firewall policy changes (coordinated separately — see Section 3)
- ACI fabric infrastructure (APIC, spine/leaf nodes) — assumed operational

### Success criteria

- All endpoints in the migrated VLANs have restored connectivity within **30 minutes** of cutover start
- BGP session to upstream re-established and prefix counts match pre-migration baseline
- Zero unresolved critical faults on APIC at sign-off
- Change window not exceeded (hard limit: T+4 hours from start)

---

## 2. Engineer roles and responsibilities

Every role must be staffed before the change window opens. No role is optional.

| Role | Name | Contact | Responsibility |
|------|------|---------|----------------|
| **DC Team Lead** | &lt;name&gt; | &lt;mobile&gt; | Overall change authority. Approves each phase gate. Makes go/rollback call at hard trigger. |
| **Lead Network Engineer** | &lt;name&gt; | &lt;mobile&gt; | Executes all Nexus and ACI commands. Single keyboard on change night. |
| **Rollback Engineer** | &lt;name&gt; | &lt;mobile&gt; | Dedicated to rollback readiness — does not execute cutover steps. Executes rollback immediately on trigger. |
| **Validation Engineer** | &lt;name&gt; | &lt;mobile&gt; | Runs all validation checks and reports pass/fail to Team Lead. Does not execute config changes. |
| **Application Owner(s)** | &lt;name&gt; | &lt;mobile&gt; | Validates application connectivity from the application side. Available on bridge for full window. |
| **Change Manager** | &lt;name&gt; | &lt;mobile&gt; | Monitors change record, records timestamps, escalates if window is breached. |

### Escalation path

1. Lead Network Engineer → DC Team Lead (immediate, any blocker)
2. DC Team Lead → Change Manager (window breach or rollback decision)
3. DC Team Lead → Cisco TAC if ACI fabric fault is suspected (SR pre-opened — see Section 3)

---

## 3. Communication plan

| Time | Action | Owner |
|------|--------|-------|
| T-5 days | Send maintenance notification to all application owners in scope | DC Team Lead |
| T-2 days | Confirm all application owners have acknowledged | DC Team Lead |
| T-1 day | Verify TAC SR is pre-opened and SR number is recorded below | Lead Network Engineer |
| T-1 day | Confirm all engineers are available and have reviewed this runbook | DC Team Lead |
| T-30 min | Open bridge call — all roles join | Change Manager |
| T-15 min | Final readiness poll — all roles confirm ready | DC Team Lead |
| T+0 | Post start notification in team channel | Change Manager |
| Rollback trigger | Notify application owners immediately | DC Team Lead |
| Change complete | Post completion notification; close bridge | Change Manager |

**Bridge call details:** &lt;dial-in / Teams / Zoom link&gt;  
**Team channel:** &lt;Slack / WhatsApp group name&gt;  
**Pre-opened TAC SR:** &lt;SR number&gt;  
**Cisco TAC number:** +1-800-553-2447

---

## 4. Pre-migration checklist

Complete this checklist in the 48 hours before the change window. All items must be checked before the window opens. Any unchecked item is a hard stop — escalate to the Change Manager.

The Validation Engineer signs off each section. The DC Team Lead signs off the overall checklist.

---

### 4.1 Readiness assessment gate

> **Prerequisite:** The readiness assessment (`docs/readiness-assessment.md`) must score **10/12 or higher** before this runbook is activated. If the score is below 10, do not proceed — return to remediation.

| # | Check | Owner | Status |
|---|-------|-------|--------|
| 1 | Readiness assessment score ≥ 10/12 | DC Team Lead | ☐ |
| 2 | Change record approved by CAB | Change Manager | ☐ |
| 3 | All application owner acknowledgements received | DC Team Lead | ☐ |
| 4 | TAC SR pre-opened | Lead Network Engineer | ☐ |
| 5 | All engineer roles confirmed and briefed | DC Team Lead | ☐ |

---

### 4.2 Current-state baseline

Run the inventory collector to capture the current-state snapshot. This is the baseline for the post-cutover diff.

```bash
# Run from the dc-aci-migration repo root
python scripts/inventory_collector.py \
  --inventory scripts/devices.yaml \
  --username admin \
  --site "<site_name>-pre-migration" \
  --output-dir output/pre-migration
```

Record the output file path: `output/pre-migration/inventory_<site>_<timestamp>.json`

| # | Check | Owner | Status |
|---|-------|-------|--------|
| 6 | Inventory collector run successfully on all in-scope devices | Lead Network Engineer | ☐ |
| 7 | Pre-migration JSON snapshot committed to Git | Lead Network Engineer | ☐ |
| 8 | BGP session count baseline recorded: `___` sessions, `___` established | Validation Engineer | ☐ |
| 9 | VLAN count baseline recorded: `___` VLANs in scope | Validation Engineer | ☐ |
| 10 | Ping baseline confirmed from application servers to their gateways | Application Owner | ☐ |

---

### 4.3 ACI fabric pre-checks

Log into APIC and verify the receiving fabric is healthy before the window opens.

```
# APIC login
https://<apic-ip> → admin → <password>
# Navigate: System → Dashboard
```

| # | Check | Command / location | Expected result | Owner | Status |
|---|-------|--------------------|-----------------|-------|--------|
| 11 | APIC cluster health | System → Controllers | All 3 nodes: In-Service | Validation Engineer | ☐ |
| 12 | Fabric health score | System → Dashboard | ≥ 90 | Validation Engineer | ☐ |
| 13 | No critical faults | System → Faults (filter: Critical) | 0 critical faults | Validation Engineer | ☐ |
| 14 | All leaf nodes registered | Fabric → Inventory → Topology | All nodes: Active | Validation Engineer | ☐ |
| 15 | Target Tenant exists | Tenants → &lt;tenant_name&gt; | Tenant visible | Lead Network Engineer | ☐ |
| 16 | Target VRF configured | Tenants → &lt;tenant&gt; → Networking → VRFs | VRF `<name>` present | Lead Network Engineer | ☐ |
| 17 | Bridge Domain pre-created for each in-scope VLAN | Tenants → &lt;tenant&gt; → Networking → BDs | One BD per VLAN in scope | Lead Network Engineer | ☐ |
| 18 | EPGs pre-created and mapped to BDs | Tenants → &lt;tenant&gt; → App Profiles → EPGs | All EPGs visible | Lead Network Engineer | ☐ |
| 19 | Contracts between EPGs configured | Tenants → &lt;tenant&gt; → Contracts | Subject/filter matches legacy ACL | Lead Network Engineer | ☐ |
| 20 | Physical domain and VLAN pool configured | Fabric → Access Policies → Domains | VLAN pool includes in-scope range | Lead Network Engineer | ☐ |
| 21 | Leaf interface profiles and port selectors configured | Fabric → Access Policies | Correct ports mapped to correct EPGs | Lead Network Engineer | ☐ |
| 22 | Border leaf BGP peer pre-configured (not yet active) | Tenants → &lt;tenant&gt; → Networking → L3Outs | L3Out peer in state: not established yet | Lead Network Engineer | ☐ |

---

### 4.4 Nexus pre-checks

Run these commands on each in-scope Nexus switch and confirm expected output.

```
# Check 1: NTP sync
show clock
show ntp status

# Check 2: VLAN database intact
show vlan brief

# Check 3: SVI state on core switches
show interface vlan <id> brief

# Check 4: BGP neighbour state
show bgp summary

# Check 5: Routing table — confirm prefixes present
show ip route vrf <vrf_name>

# Check 6: MAC address table for in-scope VLANs
show mac address-table vlan <id>
```

| # | Check | Expected result | Owner | Status |
|---|-------|-----------------|-------|--------|
| 23 | NTP synchronised on all switches | `Clock is synchronized` | Validation Engineer | ☐ |
| 24 | In-scope VLANs present in VLAN database | All VLANs: active | Validation Engineer | ☐ |
| 25 | SVI interfaces up/up on core switches | `up / up` | Validation Engineer | ☐ |
| 26 | BGP sessions established — count matches baseline | Established count = baseline | Validation Engineer | ☐ |
| 27 | Prefixes in routing table for in-scope subnets | All subnets visible | Validation Engineer | ☐ |
| 28 | MAC address table populated for in-scope VLANs | Endpoints visible | Validation Engineer | ☐ |

---

### 4.5 Final gate — approval to proceed

**The DC Team Lead must explicitly confirm GO before the change window opens.**

| Sign-off | Name | Time (WAT) | Signature |
|----------|------|-----------|-----------|
| DC Team Lead | | | |
| Change Manager | | | |

> **If any check in sections 4.1–4.4 is ☐ at T-15 minutes, this is a NO-GO. Do not open the change window. Raise with Change Manager immediately.**

---

## 5. ACI construct mapping reference

Use this table throughout the cutover procedure to translate legacy Nexus constructs into their ACI equivalents. Complete before the change window.

| Legacy Nexus | Value | ACI construct | Value |
|---|---|---|---|
| VRF name | `<name>` | ACI VRF | `<tenant>:<vrf_name>` |
| VLAN ID | `<id>` | Bridge Domain | `BD-VLAN<id>` |
| VLAN name | `<name>` | EPG | `EPG-<name>` |
| SVI gateway IP | `<ip/mask>` | BD gateway (L3) | `<ip/mask>` on BD |
| VLAN trunk port | `Eth1/X on N9K-CORE-01` | Leaf port selector | `<leaf-node>/<port>` |
| BGP peer IP | `<ip>` | L3Out BGP peer | `<ip>` in L3Out |
| BGP local AS | `<as>` | L3Out local AS | `<as>` |
| ACL name | `<name>` | Contract + Filter | `<contract_name>` |

---

## 6. Cutover procedure

**Read before starting:**

- The Lead Network Engineer executes all commands. No other engineer types configuration during the cutover.
- The Validation Engineer runs all verification commands and reports results verbally/on bridge.
- The DC Team Lead approves each phase gate before the next phase begins.
- Record the actual start time and end time of each phase in the table at the start of each section.
- If any step produces an unexpected result, **stop and report to the DC Team Lead immediately**. Do not attempt to fix forward without explicit approval.
- The **hard rollback trigger** is T+2 hours from cutover start (Phase 1 step 1). If cutover is not complete by this time, initiate rollback without further discussion.

---

### Phase 0 — Change window open (T+0)

| | |
|---|---|
| **Planned start** | &lt;HH:MM WAT&gt; |
| **Actual start** | |
| **Planned end** | T+10 min |
| **Actual end** | |
| **Phase lead** | DC Team Lead |

**Step 0.1** — Record change window start time on bridge call and in change record.

**Step 0.2** — All engineers confirm ready on bridge call:
- DC Team Lead: ✓
- Lead Network Engineer: ✓
- Rollback Engineer: ✓
- Validation Engineer: ✓
- Application Owner: ✓

**Step 0.3** — Post start notification to team channel:
```
[CHANGE IN PROGRESS] CR-<number> — ACI migration, VLANs <range>
Start: <HH:MM WAT>
Expected completion: <HH:MM WAT>
Hard rollback trigger: <HH:MM WAT> (T+2h)
Bridge: <link>
```

**Step 0.4** — Rollback Engineer: open rollback procedure (Section 8) in a separate terminal/window and keep it visible throughout.

> **Phase gate 0:** DC Team Lead confirms all engineers ready and rollback procedure is open.
>
> Approved by: _________________ Time: _______

---

### Phase 1 — Pre-cutover state capture (T+10)

| | |
|---|---|
| **Planned start** | T+10 min |
| **Actual start** | |
| **Planned end** | T+20 min |
| **Actual end** | |
| **Phase lead** | Validation Engineer |

**Step 1.1** — Capture final BGP state on all in-scope Nexus switches:

```
! Run on N9K-CORE-01 and N9K-CORE-02
show bgp summary
show bgp vrf <vrf_name> summary
```

Record BGP session count: _____ established

**Step 1.2** — Capture MAC address table for each in-scope VLAN:

```
! Run on each in-scope switch
show mac address-table vlan <id> | count
```

Record MAC count per VLAN:

| VLAN | MAC count |
|------|-----------|
| | |

**Step 1.3** — Application Owner: confirm application connectivity baseline from the application side. Record test result:

| Application | Test type | Result |
|------------|-----------|--------|
| &lt;app name&gt; | Ping to gateway | ✓ |
| &lt;app name&gt; | Application-level health check | ✓ |

**Step 1.4** — Capture APIC health score: _____ / 100

> **Phase gate 1:** Validation Engineer reports all baselines captured. DC Team Lead approves proceed to Phase 2.
>
> Approved by: _________________ Time: _______

---

### Phase 2 — ACI fabric preparation (T+20)

| | |
|---|---|
| **Planned start** | T+20 min |
| **Actual start** | |
| **Planned end** | T+50 min |
| **Actual end** | |
| **Phase lead** | Lead Network Engineer |

These steps configure the ACI fabric to receive traffic. No Nexus changes are made in this phase — existing connectivity is fully preserved.

**Step 2.1** — On APIC: deploy EPG to all target leaf ports using "pre-provision" deployment immediacy. This pushes the VLAN encap to the leaf hardware before any server ports are moved.

```
# Navigate: Tenants → <tenant> → App Profiles → <app_profile> → EPGs → <epg>
# → Domains → Physical Domain
# Set: Deployment Immediacy = Pre-Provision
# Set: Resolution Immediacy = Pre-Provision
# Click: Submit
```

Repeat for each in-scope EPG.

**Step 2.2** — Validate VLAN encap has been programmed on target leaf nodes:

```
# SSH to target leaf node
show vlan extended | include <vlan_id>
show endpoint | include <vlan_id>
```

Expected: VLAN appears in hardware table. Endpoint table empty (no traffic yet — correct).

**Step 2.3** — Enable the Bridge Domain gateway IP on each BD. This will become the new default gateway for endpoints once they move to ACI.

```
# Navigate: Tenants → <tenant> → Networking → Bridge Domains → BD-VLAN<id>
# → Subnets → <ip/mask>
# Scope: Private to VRF (not advertised externally yet)
# Click: Submit
```

Repeat for each in-scope BD.

**Step 2.4** — Verify BD gateway is programmed on leaf:

```
# On target leaf
show ip interface brief vrf <tenant>:<vrf>
```

Expected: BD gateway IP appears as a local interface.

**Step 2.5** — Configure L3Out BGP peer on border leaf. **Do not activate it yet** — set admin state to disabled.

```
# Navigate: Tenants → <tenant> → Networking → L3Outs → <l3out_name>
# → Logical Node Profiles → <node_profile> → BGP Peer Connectivity Profiles
# Peer IP: <upstream_bgp_peer_ip>
# Remote AS: <upstream_as>
# Local AS: <local_as>
# Admin State: Disabled
# Click: Submit
```

**Step 2.6** — Validation Engineer: confirm no faults introduced by Phase 2 steps:

```
# APIC: System → Faults → filter: Severity = Critical
```

Expected: 0 new critical faults.

> **Phase gate 2:** Validation Engineer confirms VLAN encap programmed on leaves, BD gateways up, 0 new critical faults. DC Team Lead approves proceed to Phase 3.
>
> Approved by: _________________ Time: _______

---

### Phase 3 — Server port migration (T+50)

| | |
|---|---|
| **Planned start** | T+50 min |
| **Actual start** | |
| **Planned end** | T+1h 30min |
| **Actual end** | |
| **Phase lead** | Lead Network Engineer |

> **Impact starts here.** Each server port migration causes a brief forwarding interruption for that server while the port is reconfigured. Total expected impact per server: **< 30 seconds**.

Migrate server ports VLAN by VLAN, starting with the lowest-criticality VLAN. Do not proceed to the next VLAN until the current one is validated.

**Step 3.1** — For each server port in VLAN `<id>`:

On the legacy Nexus switch, record the current port config before touching it:

```
! Record before removing
show running-config interface Ethernet1/<X>
```

Then administratively shut the Nexus port:

```
conf t
interface Ethernet1/<X>
  shutdown
end
```

**Step 3.2** — On the target ACI leaf, the server's physical port should already be mapped to the EPG via the interface profile configured in pre-checks. Bring the ACI leaf port up:

```
# If ACI port was pre-configured in interface profile, it activates automatically
# Verify on leaf:
show interface Ethernet1/<X>
show endpoint interface Ethernet1/<X>
```

Expected: Port up, endpoint IP/MAC learned in ACI.

**Step 3.3** — Validation Engineer: for each migrated server, confirm endpoint is learned in APIC:

```
# APIC: Tenants → <tenant> → Operational → Endpoints
# Filter by EPG or IP address
```

Expected: Server IP and MAC visible under the correct EPG.

**Step 3.4** — Application Owner: confirm application connectivity restored for the migrated server.

Record result per server:

| Server | IP | ACI leaf/port | Endpoint learned | App connectivity |
|--------|----|---------------|-----------------|-----------------|
| | | | ☐ | ☐ |

Repeat Steps 3.1–3.4 for each server in the VLAN, then for each VLAN in scope.

**Step 3.5** — After all servers in a VLAN are migrated, remove the SVI from the legacy Nexus switch:

```
conf t
no interface Vlan<id>
end
```

> Do not remove the VLAN from the VLAN database yet — keep it as an anchor until Phase 4 is confirmed stable.

> **Phase gate 3:** Validation Engineer confirms all endpoints learned in ACI and Application Owner confirms application connectivity for all migrated servers.
>
> Approved by: _________________ Time: _______

---

### Phase 4 — L3 handoff migration (T+1h 30min)

| | |
|---|---|
| **Planned start** | T+1h 30min |
| **Actual start** | |
| **Planned end** | T+2h 30min |
| **Actual end** | |
| **Phase lead** | Lead Network Engineer |

> **BGP impact window.** Steps in this phase will cause the BGP session to the upstream router to reset briefly while the handoff moves from the Nexus border switch to the ACI border leaf. Expected BGP convergence time: **< 60 seconds** if pre-configured correctly.

**Step 4.1** — Advertise in-scope subnets from ACI L3Out. Change BD subnet scope from "Private to VRF" to "Advertised Externally":

```
# APIC: Tenants → <tenant> → Networking → Bridge Domains → BD-VLAN<id>
# → Subnets → <ip/mask>
# Scope: Advertised Externally (check this box)
# Click: Submit
```

Repeat for each in-scope BD subnet.

**Step 4.2** — Enable the L3Out BGP peer configured in Phase 2, Step 2.5:

```
# APIC: Tenants → <tenant> → Networking → L3Outs → <l3out_name>
# → Logical Node Profiles → <node_profile> → BGP Peer Connectivity Profiles
# Peer IP: <upstream_bgp_peer_ip>
# Admin State: Enabled
# Click: Submit
```

**Step 4.3** — Monitor BGP session establishment on APIC:

```
# APIC: Tenants → <tenant> → Networking → L3Outs → <l3out_name> → Operational
# Wait for BGP peer state: Established
```

Also verify on the upstream router:

```
! On upstream router
show bgp summary | include <aci_border_leaf_ip>
```

Expected: Session established, prefix count matches pre-migration baseline.

**Step 4.4** — Once ACI BGP session is established and prefixes are received by the upstream router, remove the BGP session from the legacy Nexus border switch:

```
conf t
router bgp <local_as>
  vrf <vrf_name>
    no neighbor <upstream_bgp_peer_ip>
end
```

**Step 4.5** — Validation Engineer: confirm routing table on upstream router now shows in-scope prefixes via ACI next-hop:

```
! On upstream router
show ip route <subnet>
```

Expected: Next-hop IP is the ACI border leaf L3Out IP, not the legacy Nexus IP.

**Step 4.6** — Monitor for 10 minutes. Application Owner: confirm sustained application connectivity from external clients.

> **Phase gate 4:** Validation Engineer confirms BGP established on ACI, prefixes correct, upstream routing via ACI border leaf. Application Owner confirms external connectivity. DC Team Lead approves proceed to Phase 5.
>
> Approved by: _________________ Time: _______

---

### Phase 5 — Legacy cleanup and close (T+2h 30min)

| | |
|---|---|
| **Planned start** | T+2h 30min |
| **Actual start** | |
| **Planned end** | T+3h |
| **Actual end** | |
| **Phase lead** | Lead Network Engineer |

Only proceed to this phase after a **10-minute stability soak** following Phase 4 gate approval.

**Step 5.1** — Remove in-scope VLANs from all legacy Nexus trunk ports:

```
conf t
interface Ethernet1/<uplink_port>
  switchport trunk allowed vlan remove <vlan_range>
end
```

**Step 5.2** — Remove in-scope VLANs from the VLAN database on each Nexus switch:

```
conf t
no vlan <id>
end
```

**Step 5.3** — Save configuration on all modified Nexus switches:

```
copy running-config startup-config
```

**Step 5.4** — Run final validation (see Section 7 in full).

**Step 5.5** — Capture post-migration inventory snapshot:

```bash
python scripts/inventory_collector.py \
  --inventory scripts/devices.yaml \
  --username admin \
  --site "<site_name>-post-migration" \
  --output-dir output/post-migration
```

**Step 5.6** — Commit all configuration changes and output files to Git:

```bash
git add output/post-migration/ scripts/ docs/
git commit -m "ACI migration complete: VLANs <range> moved to ACI — CR-<number>"
git push
```

> **Phase gate 5 (final):** See Section 9 — Sign-off and closure.

---

## 7. Post-cutover validation

Run all checks in this section after Phase 5 Step 5.3. Validation Engineer owns all checks. DC Team Lead signs off.

### 7.1 ACI fabric validation

| # | Check | Command | Expected | Result |
|---|-------|---------|----------|--------|
| V1 | APIC health score | System → Dashboard | ≥ 90 | |
| V2 | No critical faults | System → Faults → Critical | 0 | |
| V3 | All endpoints learned in correct EPGs | Tenants → Operational → Endpoints | All server IPs visible | |
| V4 | BD gateway reachable from endpoints | Ping from server to gateway IP | Successful | |
| V5 | L3Out BGP session established | L3Out → Operational → BGP | Established | |
| V6 | Prefix count matches pre-migration | L3Out → BGP peer → Prefixes | Count = baseline | |
| V7 | Contracts passing traffic | Tenants → Operational → EP Connectivity | Traffic flows visible | |

### 7.2 Legacy Nexus validation

| # | Check | Command | Expected | Result |
|---|-------|---------|----------|--------|
| V8 | In-scope VLANs removed from VLAN database | `show vlan brief` | VLANs absent | |
| V9 | SVIs removed | `show interface vlan <id>` | Not found | |
| V10 | BGP session to upstream removed | `show bgp summary` | Session absent | |
| V11 | Running config saved | `show startup-config \| include vlan <id>` | VLAN absent | |

### 7.3 End-to-end validation

| # | Check | Owner | Expected | Result |
|---|-------|-------|----------|--------|
| V12 | Server-to-server connectivity within same EPG | Application Owner | Pass | |
| V13 | Server-to-server connectivity across EPGs (contract path) | Application Owner | Pass | |
| V14 | External client to server (via upstream router → ACI) | Application Owner | Pass | |
| V15 | Application-level health checks passing | Application Owner | All green | |
| V16 | Monitoring and alerting not showing anomalies | Validation Engineer | No new alerts | |

---

## 8. Rollback procedure

### When to initiate rollback

Rollback is initiated immediately — without further discussion — in any of these conditions:

| Trigger | Threshold |
|---------|-----------|
| Hard time trigger | T+2h from Phase 1 Step 1, if cutover is not at Phase 4 gate |
| Extended application outage | > 15 minutes with no confirmed path to resolution |
| ACI critical fault blocking traffic | Fault cannot be resolved within 10 minutes |
| BGP session not establishing | BGP peer not Established within 10 minutes of enablement |
| DC Team Lead call | Team Lead may call rollback at any point, for any reason |

The **Rollback Engineer** executes all rollback steps. The Lead Network Engineer does not type during rollback.

---

### Rollback procedure — steps

> **Note:** These steps are written to be executed in any order depending on how far the cutover progressed. The Rollback Engineer and DC Team Lead assess which phases were completed and execute only the relevant steps.

---

#### RB-1 — Restore Nexus SVI interfaces (if Phase 3 was started)

For each VLAN whose SVI was removed in Phase 3 Step 3.5:

```
conf t
interface Vlan<id>
  description <original_description>
  ip address <gateway_ip> <mask>
  vrf member <vrf_name>
  no shutdown
end
```

---

#### RB-2 — Restore server port configurations on Nexus (if Phase 3 was started)

For each server port that was moved to ACI:

Shut the ACI leaf port first to avoid duplicate endpoint:
```
# On ACI leaf
conf t
interface Ethernet1/<X>
  shutdown
end
```

Then restore the Nexus port:
```
conf t
interface Ethernet1/<X>
  description <original_description>
  switchport mode access
  switchport access vlan <id>
  no shutdown
end
```

---

#### RB-3 — Restore BGP session on Nexus border (if Phase 4 was started)

```
conf t
router bgp <local_as>
  vrf <vrf_name>
    neighbor <upstream_bgp_peer_ip> remote-as <upstream_as>
    neighbor <upstream_bgp_peer_ip> update-source loopback0
    address-family ipv4 unicast
      neighbor <upstream_bgp_peer_ip> activate
end
```

---

#### RB-4 — Disable ACI L3Out BGP peer (if Phase 4 was started)

```
# APIC: Tenants → <tenant> → Networking → L3Outs → <l3out_name>
# BGP Peer → Admin State: Disabled
# Submit
```

---

#### RB-5 — Remove ACI BD gateway advertisement (if Phase 4 Step 4.1 was done)

```
# APIC: Each BD → Subnets → <ip/mask>
# Scope: Remove "Advertised Externally"
# Submit
```

---

#### RB-6 — Validate legacy connectivity restored

Run these checks after rollback steps are complete:

```
! On N9K-CORE-01
show interface vlan <id>
show bgp summary
show ip route vrf <vrf_name>
show mac address-table vlan <id>
```

Expected: SVI up/up, BGP Established, subnets in routing table, MACs visible.

Then ask Application Owner to confirm application connectivity from their side.

---

#### RB-7 — Post-rollback comms

```
[ROLLBACK COMPLETE] CR-<number>
Rollback initiated: <HH:MM WAT>
Rollback completed: <HH:MM WAT>
Legacy connectivity restored: <confirmed by Application Owner at HH:MM>
Root cause investigation to follow.
Bridge remains open for 15 min — all engineers hold.
```

---

#### RB-8 — Save configuration on all Nexus switches after rollback

```
copy running-config startup-config
```

---

### Rollback timing estimates

| Phase reached at rollback | Estimated rollback duration |
|---------------------------|-----------------------------|
| Phase 2 only (no server changes) | < 15 minutes |
| Phase 3 partially complete | 20–40 minutes depending on server count |
| Phase 4 complete | 30–45 minutes |

---

### Post-rollback actions (within 24 hours)

1. Write a rollback incident report (RCA format) — DC Team Lead
2. Update the readiness assessment with lessons learned — DC Team Lead
3. Schedule a review meeting with all change engineers — Change Manager
4. Open a new change record for the retry — do not reuse this CR

---

## 9. Sign-off and closure

Complete after Phase 5 validation. All sign-offs required before the change record is closed.

### Timing record

| Event | Planned time | Actual time (WAT) |
|-------|-------------|-------------------|
| Change window open | | |
| Phase 1 complete | | |
| Phase 2 complete | | |
| Phase 3 complete | | |
| Phase 4 complete | | |
| Phase 5 complete | | |
| Change window close | | |

### Final validation sign-off

| Check | Pass / Fail | Notes |
|-------|-------------|-------|
| All V1–V16 validation checks passed | | |
| No unresolved critical APIC faults | | |
| Application Owner confirms connectivity | | |
| Post-migration inventory snapshot saved | | |
| Changes committed to Git | | |

### Approvals

| Role | Name | Signature | Time (WAT) |
|------|------|-----------|-----------|
| DC Team Lead | | | |
| Lead Network Engineer | | | |
| Validation Engineer | | | |
| Application Owner | | | |
| Change Manager | | | |

### Close actions (within 48 hours)

- [ ] Update change record to Closed — Change Manager
- [ ] Update readiness assessment score and notes — DC Team Lead
- [ ] Update VLAN/VRF mapping table in `templates/topology-audit.yaml` — Lead Network Engineer
- [ ] File post-migration snapshot in Google Drive stakeholder folder — DC Team Lead
- [ ] Send completion notification to all application owners — DC Team Lead
- [ ] Record lessons learned in team channel — DC Team Lead

---

## 10. Related documents

| Document | Location |
|----------|----------|
| Readiness assessment | `docs/readiness-assessment.md` |
| Topology audit data (YAML) | `templates/topology-audit.yaml` |
| Rollback procedure (standalone) | `docs/rollback-procedure.md` |
| Pre-migration inventory snapshot | `output/pre-migration/` |
| Post-migration inventory snapshot | `output/post-migration/` |
| Inventory collector script | `scripts/inventory_collector.py` |
| ACI tenant provisioning playbook | `ansible/provision_tenant.yml` |
| Team onboarding guide | `docs/team-onboarding-guide.md` |
| Google Drive stakeholder folder | &lt;link&gt; |
| CAB change record | &lt;link&gt; |
| TAC SR | &lt;SR number&gt; |

---

*This runbook is version-controlled in Git. The Google Drive copy is a read-only export — all edits must be made in the repo and re-exported.*
