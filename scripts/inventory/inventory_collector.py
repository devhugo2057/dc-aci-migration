#!/usr/bin/env python3
"""
inventory_collector.py
======================
DC ACI Migration — Project 2: Pre-Migration Inventory Collector

Connects to one or more Cisco Nexus switches via NX-API and collects:
  - Device facts (hostname, model, NX-OS version, serial number, uptime)
  - Interface status (name, admin/oper state, speed, description, connected peer)
  - VLAN table (ID, name, active ports)
  - BGP neighbours (peer IP, AS, state, prefix counts, address families)

Output: a single timestamped JSON report per run, plus a human-readable
        summary printed to stdout. The JSON file is the source of truth for
        the ACI migration readiness assessment and pre/post diff scripts.

Usage:
  # Single device
  python inventory_collector.py --host 10.0.0.1 --username admin

  # Multiple devices from a file
  python inventory_collector.py --inventory devices.yaml --username admin

  # Output to a specific directory
  python inventory_collector.py --inventory devices.yaml --username admin --output-dir ../output

  # Suppress SSL warnings (lab / self-signed certs)
  python inventory_collector.py --inventory devices.yaml --username admin --no-verify

Dependencies:
  pip install requests PyYAML

Author: DC Team Lead
Repo:   dc-aci-migration/scripts/inventory_collector.py
"""

import argparse
import getpass
import json
import logging
import os
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml
from requests.auth import HTTPBasicAuth

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# NX-API client
# ---------------------------------------------------------------------------
class NxApiClient:
    """
    Thin wrapper around the Cisco NX-API JSON-RPC endpoint.
    Sends one or more CLI commands and returns parsed JSON.

    NX-API must be enabled on the switch:
        switch# conf t
        switch(config)# feature nxapi
        switch(config)# nxapi http port 80       ! or https port 443
    """

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 443,
        use_ssl: bool = True,
        verify_ssl: bool = True,
        timeout: int = 30,
    ):
        scheme = "https" if use_ssl else "http"
        self.base_url = f"{scheme}://{host}:{port}/ins"
        self.auth = HTTPBasicAuth(username, password)
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.host = host

    def _send(self, commands: list[str], output_type: str = "json") -> list[dict]:
        """
        Send a list of CLI commands to NX-API in a single request.
        Returns a list of result dicts — one per command.

        output_type: "json" (structured) | "text" (raw CLI output)
        """
        payload = {
            "ins_api": {
                "version": "1.0",
                "type": "cli_show",
                "chunk": "0",
                "sid": "1",
                "input": " ;; ".join(commands),
                "output_format": output_type,
            }
        }
        headers = {"Content-Type": "application/json"}

        try:
            resp = requests.post(
                self.base_url,
                auth=self.auth,
                headers=headers,
                data=json.dumps(payload),
                verify=self.verify_ssl,
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                f"Cannot reach {self.host} — check IP, port, and that NX-API is enabled"
            )
        except requests.exceptions.Timeout:
            raise RuntimeError(f"Connection to {self.host} timed out after {self.timeout}s")
        except requests.exceptions.HTTPError as exc:
            raise RuntimeError(f"HTTP {resp.status_code} from {self.host}: {exc}")

        body = resp.json()

        # NX-API wraps multi-command responses differently to single-command
        outputs = body.get("ins_api", {}).get("outputs", {}).get("output", [])
        if isinstance(outputs, dict):
            outputs = [outputs]  # single command — normalise to list

        results = []
        for item in outputs:
            code = item.get("code", "")
            if code != "200":
                msg = item.get("msg", "unknown error")
                cmd = item.get("input", "")
                log.warning("NX-API error on '%s': %s %s", cmd, code, msg)
                results.append(None)
            else:
                body_inner = item.get("body", {})
                results.append(body_inner if body_inner else None)

        return results

    def show(self, *commands: str) -> list[dict]:
        """Public helper — run one or more 'show' commands, return results."""
        return self._send(list(commands), output_type="json")


# ---------------------------------------------------------------------------
# Data collectors
# ---------------------------------------------------------------------------

def collect_device_facts(client: NxApiClient) -> dict:
    """
    Collect device identity: hostname, model, NX-OS version, serial, uptime.
    Source command: show version
    """
    results = client.show("show version")
    raw = results[0] or {}

    return {
        "hostname":    raw.get("host_name", "unknown"),
        "model":       raw.get("chassis_id", "unknown"),
        "nxos_version": raw.get("nxos_ver_str", "unknown"),
        "serial":      raw.get("proc_board_id", "unknown"),
        "uptime":      raw.get("kern_uptm_str", "unknown"),
        "bios_version": raw.get("bios_ver_str", "unknown"),
        "kickstart_image": raw.get("kickstart_image_file", "unknown"),
        "system_image":   raw.get("rr_sys_image", "unknown"),
    }


def collect_interfaces(client: NxApiClient) -> list[dict]:
    """
    Collect interface state for all interfaces.
    Source command: show interface
    Captures: name, admin state, oper state, speed, MTU, description, MAC,
              last_cleared counters, input/output errors.
    """
    results = client.show("show interface")
    raw = results[0] or {}

    # NX-API returns TABLE_interface → ROW_interface (list or single dict)
    rows = raw.get("TABLE_interface", {}).get("ROW_interface", [])
    if isinstance(rows, dict):
        rows = [rows]

    interfaces = []
    for row in rows:
        interfaces.append({
            "interface":      row.get("interface", ""),
            "admin_state":    row.get("admin_state", ""),
            "oper_state":     row.get("state", ""),
            "state_reason":   row.get("state_rsn_desc", ""),
            "description":    row.get("desc", ""),
            "speed":          row.get("eth_speed", row.get("speed", "")),
            "duplex":         row.get("eth_duplex", ""),
            "mtu":            row.get("eth_mtu", row.get("mtu", "")),
            "mac_address":    row.get("eth_hw_addr", ""),
            "ip_address":     row.get("eth_ip_addr", ""),
            "prefix_length":  row.get("eth_ip_mask", ""),
            "in_errors":      row.get("eth_inerr", "0"),
            "out_errors":     row.get("eth_outerr", "0"),
            "in_discards":    row.get("eth_indiscard", "0"),
            "out_discards":   row.get("eth_outdiscard", "0"),
        })

    return interfaces


def collect_vlans(client: NxApiClient) -> list[dict]:
    """
    Collect the VLAN table.
    Source command: show vlan
    Captures: VLAN ID, name, state, active ports.
    """
    results = client.show("show vlan")
    raw = results[0] or {}

    rows = raw.get("TABLE_vlanbrief", {}).get("ROW_vlanbrief", [])
    if isinstance(rows, dict):
        rows = [rows]

    vlans = []
    for row in rows:
        # Ports can be a space-separated string or absent
        ports_raw = row.get("vlanshowplist-ifidx", "")
        ports = [p.strip() for p in ports_raw.split(",") if p.strip()] if ports_raw else []

        vlans.append({
            "vlan_id":   str(row.get("vlanshowbr-vlanid", "")),
            "name":      row.get("vlanshowbr-vlanname", ""),
            "state":     row.get("vlanshowbr-vlanstate", ""),
            "admin":     row.get("vlanshowbr-shutstate", ""),
            "ports":     ports,
            "port_count": len(ports),
        })

    return vlans


def collect_bgp_neighbours(client: NxApiClient) -> dict:
    """
    Collect BGP neighbour state across all VRFs.
    Source commands: show bgp summary, show bgp sessions
    Captures: local AS, peer IP, peer AS, state, up/down time,
              prefixes received, address families.

    Note: if BGP is not configured on this device the command returns
    an error — this is caught and returns an empty structure.
    """
    results = client.show("show bgp all summary", "show bgp sessions")
    summary_raw = results[0] or {}
    sessions_raw = results[1] or {}

    # BGP may not be configured — handle gracefully
    if not summary_raw:
        return {"configured": False, "local_as": None, "neighbours": []}

    neighbours = []

    # show bgp all summary → TABLE_vrf → ROW_vrf (one per VRF)
    vrf_rows = summary_raw.get("TABLE_vrf", {}).get("ROW_vrf", [])
    if isinstance(vrf_rows, dict):
        vrf_rows = [vrf_rows]

    local_as = None

    for vrf_row in vrf_rows:
        vrf_name = vrf_row.get("vrf-namestr", "default")
        local_as = vrf_row.get("local-as", local_as)

        # Each VRF has TABLE_af (address families) → ROW_af → TABLE_neighbor
        af_rows = vrf_row.get("TABLE_af", {}).get("ROW_af", [])
        if isinstance(af_rows, dict):
            af_rows = [af_rows]

        for af_row in af_rows:
            af_name = af_row.get("af-name", "")
            safi = af_row.get("af-id", "")

            nbr_rows = af_row.get("TABLE_neighbor", {}).get("ROW_neighbor", [])
            if isinstance(nbr_rows, dict):
                nbr_rows = [nbr_rows]

            for nbr in nbr_rows:
                peer_ip = nbr.get("neighborid", "")

                # Avoid duplicates across address families for same peer
                existing = next((n for n in neighbours if n["peer_ip"] == peer_ip), None)
                if existing:
                    if af_name not in existing["address_families"]:
                        existing["address_families"].append(af_name)
                    continue

                neighbours.append({
                    "peer_ip":          peer_ip,
                    "peer_as":          nbr.get("neighboras", ""),
                    "vrf":              vrf_name,
                    "address_families": [af_name] if af_name else [],
                    "state":            nbr.get("state", ""),
                    "up_down_time":     nbr.get("up-down-time", ""),
                    "prefixes_received": nbr.get("prefixreceived", "0"),
                    "prefixes_sent":    nbr.get("prefixaccepted", "0"),
                    "msg_received":     nbr.get("msgrecvd", "0"),
                    "msg_sent":         nbr.get("msgsent", "0"),
                    "reset_reason":     nbr.get("reset-reason", ""),
                })

    return {
        "configured": True,
        "local_as": local_as,
        "neighbours": neighbours,
        "neighbour_count": len(neighbours),
        "established_count": sum(
            1 for n in neighbours if n.get("state", "").lower() == "established"
        ),
    }


# ---------------------------------------------------------------------------
# Device snapshot — orchestrates all collectors
# ---------------------------------------------------------------------------

def snapshot_device(
    host: str,
    username: str,
    password: str,
    port: int = 443,
    use_ssl: bool = True,
    verify_ssl: bool = True,
) -> dict:
    """
    Run all collectors against a single device and return a complete snapshot dict.
    """
    log.info("Connecting to %s ...", host)
    client = NxApiClient(
        host=host,
        username=username,
        password=password,
        port=port,
        use_ssl=use_ssl,
        verify_ssl=verify_ssl,
    )

    # Run collectors — failures on individual sections don't abort the whole run
    facts = {}
    interfaces = []
    vlans = []
    bgp = {}

    try:
        log.info("  [%s] collecting device facts ...", host)
        facts = collect_device_facts(client)
        log.info("  [%s] hostname: %s | model: %s | NX-OS: %s",
                 host, facts.get("hostname"), facts.get("model"), facts.get("nxos_version"))
    except Exception as exc:
        log.error("  [%s] device facts failed: %s", host, exc)
        facts = {"error": str(exc)}

    try:
        log.info("  [%s] collecting interfaces ...", host)
        interfaces = collect_interfaces(client)
        log.info("  [%s] %d interfaces found", host, len(interfaces))
    except Exception as exc:
        log.error("  [%s] interface collection failed: %s", host, exc)
        interfaces = [{"error": str(exc)}]

    try:
        log.info("  [%s] collecting VLAN table ...", host)
        vlans = collect_vlans(client)
        log.info("  [%s] %d VLANs found", host, len(vlans))
    except Exception as exc:
        log.error("  [%s] VLAN collection failed: %s", host, exc)
        vlans = [{"error": str(exc)}]

    try:
        log.info("  [%s] collecting BGP neighbours ...", host)
        bgp = collect_bgp_neighbours(client)
        if bgp.get("configured"):
            log.info("  [%s] BGP local-AS %s | %d neighbours | %d established",
                     host, bgp.get("local_as"),
                     bgp.get("neighbour_count", 0),
                     bgp.get("established_count", 0))
        else:
            log.info("  [%s] BGP not configured on this device", host)
    except Exception as exc:
        log.error("  [%s] BGP collection failed: %s", host, exc)
        bgp = {"error": str(exc)}

    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "management_ip": host,
        "device_facts": facts,
        "interfaces": interfaces,
        "interface_count": len(interfaces),
        "vlan_table": vlans,
        "vlan_count": len(vlans),
        "bgp": bgp,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def build_report(snapshots: list[dict], collection_meta: dict) -> dict:
    """
    Wrap all device snapshots into a top-level report structure.
    """
    return {
        "report_type": "pre-aci-migration-inventory",
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "meta": collection_meta,
        "summary": {
            "device_count": len(snapshots),
            "total_interfaces": sum(s.get("interface_count", 0) for s in snapshots),
            "total_vlans": sum(s.get("vlan_count", 0) for s in snapshots),
            "total_bgp_neighbours": sum(
                s.get("bgp", {}).get("neighbour_count", 0) for s in snapshots
            ),
            "total_bgp_established": sum(
                s.get("bgp", {}).get("established_count", 0) for s in snapshots
            ),
        },
        "devices": snapshots,
    }


def print_summary(report: dict) -> None:
    """Print a readable summary table to stdout."""
    s = report["summary"]
    print("\n" + "=" * 60)
    print("  PRE-MIGRATION INVENTORY — COLLECTION SUMMARY")
    print("=" * 60)
    print(f"  Generated : {report['generated_at']}")
    print(f"  Devices   : {s['device_count']}")
    print(f"  Interfaces: {s['total_interfaces']}")
    print(f"  VLANs     : {s['total_vlans']}")
    print(f"  BGP peers : {s['total_bgp_neighbours']} total  |  "
          f"{s['total_bgp_established']} established")
    print("=" * 60)

    for device in report["devices"]:
        facts = device.get("device_facts", {})
        bgp = device.get("bgp", {})
        hostname = facts.get("hostname", device["management_ip"])
        print(f"\n  {hostname}  ({device['management_ip']})")
        print(f"    Model   : {facts.get('model', '—')}")
        print(f"    NX-OS   : {facts.get('nxos_version', '—')}")
        print(f"    Serial  : {facts.get('serial', '—')}")
        print(f"    Uptime  : {facts.get('uptime', '—')}")
        print(f"    IFs     : {device.get('interface_count', 0)}  |  "
              f"VLANs: {device.get('vlan_count', 0)}")

        if bgp.get("configured"):
            print(f"    BGP AS  : {bgp.get('local_as', '—')}  |  "
                  f"Peers: {bgp.get('neighbour_count', 0)}  |  "
                  f"Up: {bgp.get('established_count', 0)}")
            for nbr in bgp.get("neighbours", []):
                state_flag = "✓" if nbr.get("state", "").lower() == "established" else "✗"
                print(f"      {state_flag} {nbr['peer_ip']}  AS{nbr['peer_as']}  "
                      f"{nbr.get('state', '?')}  "
                      f"pfx-rcvd:{nbr.get('prefixes_received', 0)}  "
                      f"VRF:{nbr.get('vrf', 'default')}")
        else:
            print("    BGP     : not configured")

    print("\n" + "=" * 60 + "\n")


# ---------------------------------------------------------------------------
# Inventory file parser
# ---------------------------------------------------------------------------

def load_inventory(path: str) -> list[dict]:
    """
    Parse a YAML device inventory file.

    Expected format:
        devices:
          - host: 10.0.0.1
            port: 443        # optional, default 443
            use_ssl: true    # optional, default true
            label: n9k-dc1   # optional human label
          - host: 10.0.0.2
    """
    with open(path) as f:
        data = yaml.safe_load(f)

    devices = data.get("devices", [])
    if not devices:
        raise ValueError(f"No devices found in inventory file: {path}")

    return devices


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="NX-API pre-migration inventory collector for dc-aci-migration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--host", metavar="IP", help="Single switch management IP")
    source.add_argument("--inventory", metavar="FILE",
                        help="YAML file listing multiple devices")

    parser.add_argument("--username", "-u", required=True,
                        help="NX-API username")
    parser.add_argument("--password", "-p", default=None,
                        help="NX-API password (prompted if omitted)")
    parser.add_argument("--port", type=int, default=443,
                        help="NX-API port (default: 443)")
    parser.add_argument("--no-ssl", action="store_true",
                        help="Use HTTP instead of HTTPS")
    parser.add_argument("--no-verify", action="store_true",
                        help="Disable SSL certificate verification (lab use only)")
    parser.add_argument("--output-dir", metavar="DIR", default="output",
                        help="Directory for JSON output (default: ./output)")
    parser.add_argument("--output-file", metavar="FILE", default=None,
                        help="Override output filename (default: auto-timestamped)")
    parser.add_argument("--site", metavar="NAME", default="",
                        help="Site label added to report metadata")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug logging")

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.no_verify:
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")
        log.warning("SSL verification disabled — do not use in production")

    # Resolve password
    password = args.password or getpass.getpass(
        f"Password for {args.username}@NX-API: "
    )

    # Build device list
    if args.host:
        devices = [{"host": args.host, "port": args.port, "use_ssl": not args.no_ssl}]
    else:
        devices = load_inventory(args.inventory)
        log.info("Loaded %d devices from %s", len(devices), args.inventory)

    # Run collection
    snapshots = []
    for dev in devices:
        host = dev.get("host") or dev.get("ip") or dev.get("management_ip")
        if not host:
            log.error("Device entry has no 'host' field — skipping: %s", dev)
            continue

        try:
            snap = snapshot_device(
                host=host,
                username=args.username,
                password=password,
                port=dev.get("port", args.port),
                use_ssl=dev.get("use_ssl", not args.no_ssl),
                verify_ssl=not args.no_verify,
            )
            snap["label"] = dev.get("label", "")
            snapshots.append(snap)
        except Exception as exc:
            log.error("FAILED to collect from %s: %s", host, exc)
            snapshots.append({
                "management_ip": host,
                "label": dev.get("label", ""),
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "error": str(exc),
            })

    # Build report
    report = build_report(
        snapshots=snapshots,
        collection_meta={
            "site": args.site,
            "username": args.username,
            "device_source": args.inventory if args.inventory else "cli --host",
            "tool": "inventory_collector.py",
            "repo": "dc-aci-migration",
        },
    )

    # Print summary
    print_summary(report)

    # Write JSON
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.output_file:
        out_path = out_dir / args.output_file
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        site_slug = args.site.replace(" ", "_").lower() if args.site else "site"
        out_path = out_dir / f"inventory_{site_slug}_{ts}.json"

    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)

    log.info("Report written to: %s", out_path)
    print(f"  Output: {out_path}\n")


if __name__ == "__main__":
    main()
