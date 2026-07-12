# ACI Tenant Provisioning — Ansible Playbook

Provisions a complete Cisco ACI tenant from a single vars file.
Engineers edit `vars/tenant_vars.yaml` only — the playbook handles
the object hierarchy and ordering automatically.

## What gets provisioned

Tenant
└── VRF
└── Bridge Domains + Subnets
└── Application Profile
└── EPGs
└── Contract bindings
└── Filters + Entries
└── Contracts + Subjects

## Files

| File | Purpose |
|------|---------|
| `provision_tenant.yml` | Main playbook — do not edit for normal use |
| `vars/tenant_vars.yaml` | Edit this for each new tenant |

## Quickstart

```bash
# Install the ACI collection
ansible-galaxy collection install cisco.aci

# Dry run first — no changes applied
ansible-playbook provision_tenant.yml \
  -e @vars/tenant_vars.yaml \
  --check

# Apply
ansible-playbook provision_tenant.yml \
  -e @vars/tenant_vars.yaml \
  -e "apic_password=$APIC_PASSWORD"

# Tear down (lab use)
ansible-playbook provision_tenant.yml \
  -e @vars/tenant_vars.yaml \
  -e "desired_state=absent"
```

## Test without physical gear

Uses Cisco DevNet always-on ACI sandbox:
`sandboxapicdc.cisco.com` — credentials on devnetsandbox.cisco.com
