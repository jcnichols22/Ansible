# Syncthing Ansible Automation - Quick Reference

## Directory Structure
```
Ansible/
├── playbooks/
│   ├── deploy_syncthing.yml              # Initial installation
│   ├── get_syncthing_device_ids.yml      # Get device IDs
│   ├── setup_syncthing_workstations.yml  # Configure workstations
│   ├── setup_syncthing_media.yml         # Configure media servers
│   ├── setup_syncthing_lxc.yml           # Configure LXC containers
│   └── add_syncthing_device.yml          # Add new device
├── roles/
│   └── syncthing/
│       ├── defaults/main.yml             # Default variables
│       ├── tasks/main.yml                # Installation tasks
│       ├── handlers/main.yml             # Service handlers
│       ├── meta/main.yml                 # Role metadata
│       ├── templates/
│       │   ├── config.xml.j2             # Main config template
│       │   └── folder.xml.j2             # Folder config template
│       ├── README.md                     # Full documentation
│       └── EXAMPLES.md                   # Configuration examples
└── inventory/
    ├── hosts.ini                         # Your existing inventory
    └── group_vars/                       # Group-specific variables
```

## Quick Start Commands

### 1. Install Syncthing Everywhere
```bash
ansible-playbook -i inventory/hosts.ini playbooks/deploy_syncthing.yml
```

### 2. Get All Device IDs
```bash
ansible-playbook -i inventory/hosts.ini playbooks/get_syncthing_device_ids.yml
```

### 3. Configure Specific Groups
```bash
# Workstations
ansible-playbook -i inventory/hosts.ini playbooks/setup_syncthing_workstations.yml

# Media servers
ansible-playbook -i inventory/hosts.ini playbooks/setup_syncthing_media.yml

# LXC containers
ansible-playbook -i inventory/hosts.ini playbooks/setup_syncthing_lxc.yml
```

### 4. Install on Specific Host
```bash
ansible-playbook -i inventory/hosts.ini playbooks/deploy_syncthing.yml --limit 192.168.0.102
```

### 5. Add New Device (with variables)
```bash
ansible-playbook -i inventory/hosts.ini playbooks/add_syncthing_device.yml \
  --extra-vars "new_device_name=NewLaptop new_device_id=DEVICE-ID-HERE"
```

## Configuration Workflow

### Step 1: Initial Deployment
```bash
# Deploy to all hosts or specific group
ansible-playbook -i inventory/hosts.ini playbooks/deploy_syncthing.yml
# OR for specific group:
ansible-playbook -i inventory/hosts.ini playbooks/deploy_syncthing.yml --limit workstations
```

### Step 2: Collect Device IDs
```bash
ansible-playbook -i inventory/hosts.ini playbooks/get_syncthing_device_ids.yml
```

**Copy the output** - you'll need these IDs for configuration!

### Step 3: Update Inventory Variables

Create `inventory/group_vars/workstations.yml`:
```yaml
---
syncthing_user: "josh"

syncthing_devices:
  - name: "Laptop"
    id: "PASTE-DEVICE-ID-HERE"
    addresses: "dynamic"
  - name: "Desktop"
    id: "PASTE-DEVICE-ID-HERE"
    addresses: "tcp://192.168.0.50:22000"

syncthing_folders:
  - id: "documents"
    label: "Documents"
    path: "/home/josh/Documents"
    devices:
      - "Laptop"
      - "Desktop"
    type: "sendreceive"
```

### Step 4: Apply Configuration
```bash
ansible-playbook -i inventory/hosts.ini playbooks/setup_syncthing_workstations.yml
```

### Step 5: Verify
Access web GUI: `http://<host-ip>:8384`

## Common Commands

### Check Service Status
```bash
ansible all -i inventory/hosts.ini -m shell -a "systemctl status syncthing@josh" -b
```

### Restart Syncthing
```bash
ansible all -i inventory/hosts.ini -m systemd -a "name=syncthing@josh state=restarted" -b
```

### View Syncthing Logs
```bash
ansible all -i inventory/hosts.ini -m shell -a "journalctl -u syncthing@josh -n 50" -b
```

### Check Syncthing Version
```bash
ansible all -i inventory/hosts.ini -m shell -a "syncthing --version"
```

## Useful Tags

Most playbooks support tags for selective execution:

```bash
# Only install packages
ansible-playbook playbooks/deploy_syncthing.yml --tags packages

# Only configure syncthing
ansible-playbook playbooks/deploy_syncthing.yml --tags syncthing

# Skip syncthing tasks
ansible-playbook playbooks/deploy_syncthing.yml --skip-tags syncthing
```

## Testing

### Test on Single Host First
```bash
ansible-playbook -i inventory/hosts.ini playbooks/deploy_syncthing.yml \
  --limit 192.168.0.11 \
  --check  # Dry run
```

### Verify Connectivity
```bash
ansible all -i inventory/hosts.ini -m ping
```

## Folder Sync Types

| Type | Description | Use Case |
|------|-------------|----------|
| `sendreceive` | Bidirectional sync | Shared folders between devices |
| `sendonly` | Only send changes | Backup source |
| `receiveonly` | Only receive changes | Backup destination |

## Important Variables

```yaml
# User running Syncthing
syncthing_user: "josh"

# GUI access
syncthing_gui_address: "127.0.0.1:8384"  # localhost only
# OR
syncthing_gui_address: "0.0.0.0:8384"    # all interfaces (with auth!)

# Service control
syncthing_service_enabled: true
syncthing_service_state: started

# Network settings
syncthing_max_send_kbps: 0  # unlimited
syncthing_max_recv_kbps: 0  # unlimited
```

## Troubleshooting

### Can't Connect to GUI
```bash
# Check if service is running
systemctl status syncthing@josh

# Check firewall
sudo ufw status
```

### Devices Not Discovering
- Ensure ports 22000/tcp and 21027/udp are open
- Check `syncthing_global_discovery_enabled: true`
- Use specific addresses instead of "dynamic"

### Configuration Not Applied
```bash
# Backup and recreate config
ansible-playbook -i inventory/hosts.ini playbooks/setup_syncthing_workstations.yml --tags syncthing
```

## Next Steps

1. ✅ Install Syncthing on target hosts
2. ✅ Collect device IDs
3. ✅ Create inventory variable files
4. ✅ Configure folder synchronization
5. ✅ Verify through web GUI
6. Monitor initial synchronization
7. Set up additional folders as needed

## Resources

- Full documentation: `roles/syncthing/README.md`
- Configuration examples: `roles/syncthing/EXAMPLES.md`
- Syncthing docs: https://docs.syncthing.net/

## Security Reminders

- 🔒 Use ansible-vault for passwords
- 🔒 Restrict GUI to localhost unless needed
- 🔒 Use specific device addresses when possible
- 🔒 Enable firewall rules appropriately
- 🔒 Regularly backup configurations

## Example Complete Workflow

```bash
# 1. Deploy to workstations
ansible-playbook -i inventory/hosts.ini playbooks/deploy_syncthing.yml --limit workstations

# 2. Get device IDs
ansible-playbook -i inventory/hosts.ini playbooks/get_syncthing_device_ids.yml --limit workstations

# 3. Edit inventory/group_vars/workstations.yml with device IDs

# 4. Configure sync
ansible-playbook -i inventory/hosts.ini playbooks/setup_syncthing_workstations.yml

# 5. Check status
ansible workstations -i inventory/hosts.ini -m shell -a "systemctl status syncthing@josh" -b

# 6. Access GUI at http://<workstation-ip>:8384
```

## Need Help?

- Check logs: `journalctl -u syncthing@josh -f`
- Web GUI: `http://localhost:8384`
- Test configuration: Add `--check` to ansible-playbook commands
- Verbose output: Add `-v`, `-vv`, or `-vvv` to commands
