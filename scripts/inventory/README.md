# Pre-ACI Inventory Collector

Queries multiple Cisco Nexus switches via NX-API and outputs a
structured JSON snapshot — used as the pre-migration baseline before
transitioning to Cisco ACI.

## What it collects

| Data | NX-OS command |
|------|--------------|
| Interface state, speed, MTU | `show interface` |
| VLAN table + member ports | `show vlan` |
| BGP neighbour state + prefixes | `show bgp ipv4 unicast summary` |

## Files

| File | Purpose |
|------|---------|
| `inventory_collector.py` | Main collection script |
| `devices.yaml` | Device list — edit this for your environment |

## Quickstart

```bash
pip install requests urllib3 pyyaml
python inventory_collector.py --devices devices.yaml
```

## Enable NX-API on each switch first

switch(config)# feature nxapi
switch(config)# nxapi https port 443

## Test without physical gear

Uses Cisco DevNet always-on NX-OS sandbox:
`sbx-nxos-mgmt.cisco.com` — credentials on devnetsandbox.cisco.com
