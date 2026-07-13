# Team Automation Onboarding Guide

A practical guide for network engineers joining the automation
workflow for this DC ACI migration project. Written for engineers
who are confident with CLI but new to Python, Ansible, and Git.

---

## What this guide covers

1. Setting up your environment
2. Git basics — the workflow we use on this project
3. Your first Python script
4. Your first Ansible playbook
5. How to contribute to this repo

---

## 1. Environment setup

### Install Python
Download Python 3.10 or later from python.org.
Verify installation:
```bash
python3 --version
```

### Install required libraries
```bash
pip install requests urllib3 pyyaml ansible
```

### Install the Cisco ACI Ansible collection
```bash
ansible-galaxy collection install cisco.aci
```

### Install VS Code
Download from code.visualstudio.com.
Recommended extensions:
- Python (Microsoft)
- YAML (Red Hat)
- GitLens

---

## 2. Git basics

We use Git to track every change. No script or playbook gets run
in production unless it has been committed and reviewed.

### The four commands you will use every day

```bash
# Pull latest changes before starting any work
git pull

# Check what files you have changed
git status

# Stage your changes
git add filename.py

# Commit with a clear message
git commit -m "feat: add BGP state check to pre_check script"
```

### Commit message format

type: short description of what changed
Types:
feat     — new script or playbook
fix      — bug fix
docs     — README or documentation update
chore    — housekeeping (renaming, restructuring)

### Branch before you change anything

Never work directly on main. Create a branch first:
```bash
git checkout -b your-name/what-you-are-doing
```
Example:
```bash
git checkout -b hugo/add-vlan-validation
```

---

## 3. Your first Python script

Before touching any project scripts, run this exercise to confirm
your environment is working.

Create a file called `my_first_script.py` and paste this in:

```python
# A dictionary — like a record card for one device
device = {
    "hostname": "LEAF-01",
    "ip":       "10.0.0.1",
    "platform": "Nexus 9300",
}

# A list of BGP neighbours
bgp_neighbors = [
    {"peer": "10.1.0.1", "state": "Established"},
    {"peer": "10.1.0.2", "state": "Idle"},
]

# Print the device hostname
print(device["hostname"])

# Loop through neighbours and flag any that are down
for neighbor in bgp_neighbors:
    if neighbor["state"] != "Established":
        print(f"DOWN: {neighbor['peer']}")
```

Run it:
```bash
python3 my_first_script.py
```

Expected output:
LEAF-01
DOWN: 10.1.0.2

If you see that output, your environment is working correctly.

---

## 4. Your first Ansible playbook

This exercise runs a single task against a local inventory — no
device needed.

Create a file called `my_first_playbook.yml`:

```yaml
---
- name: My first playbook
  hosts: localhost
  gather_facts: false

  tasks:
    - name: Print a message
      ansible.builtin.debug:
        msg: "Ansible is working correctly"
```

Run it:
```bash
ansible-playbook my_first_playbook.yml
```

Expected output includes:
ok: [localhost] => {
"msg": "Ansible is working correctly"
}

Once that works, open `ansible/provision_tenant.yml` and read
through it. You will recognise the same structure — hosts, tasks,
modules — just applied to a real ACI fabric.

---

## 5. How to contribute to this repo

### Before you start
```bash
git pull
git checkout -b your-name/description
```

### Making changes
- Scripts go in `scripts/inventory/` or `scripts/validation/`
- Playbooks go in `ansible/`
- Documentation goes in `docs/`
- Never commit real credentials — use environment variables

### Submitting your work
```bash
git add your_file.py
git commit -m "feat: describe what you added"
git push origin your-name/description
```
Then open a Pull Request on GitHub for review.

---

## Ground rules

| Rule | Why |
|------|-----|
| Never commit passwords or credentials | Security — use env vars instead |
| Always pull before you start | Avoids merge conflicts |
| Every script needs a README | Recruiters and teammates read docs, not code |
| Test in the DevNet sandbox first | Never run untested automation against production |
| Commit after every working session | Builds history, makes rollback easy |

---

## Useful references

- DevNet NX-OS sandbox: `sbx-nxos-mgmt.cisco.com`
- DevNet ACI sandbox: `sandboxapicdc.cisco.com`
- Sandbox credentials: devnetsandbox.cisco.com
- Ansible cisco.aci docs: galaxy.ansible.com/cisco/aci
- Python requests library: docs.python-requests.org
