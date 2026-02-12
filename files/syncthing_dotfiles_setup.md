# Syncthing Dotfiles Sync - Real-World Setup

Based on your actual working implementation with NixOS laptop + Proxmox nodes.

## Architecture

- **Hub**: Syncthing LXC container on Proxmox
  - Path: `/syncthing/dotfiles-josh`
  - Always-on, receives sync from all devices
  
- **Clients**: 
  - NixOS laptop: `/home/josh/dotfiles` (declarative config)
  - Proxmox nodes: `/syncthing/dotfiles-josh` (Ansible managed)
  - Other Debian/Ubuntu servers (Ansible managed)

## Key Differences from Generic Setup

### 1. System Service (Not User Service)
Proxmox doesn't handle `systemd --user` and `loginctl enable-linger` well, so we use:

```bash
# /etc/systemd/system/syncthing-josh.service
systemctl enable --now syncthing-josh.service
```

Instead of the standard:
```bash
# Would fail on Proxmox
systemctl --user enable --now syncthing.service
```

### 2. Data Directory Structure
```
/syncthing/                    # Main data directory
└── dotfiles-josh/             # Synced dotfiles folder
    ├── .bash_aliases          # Synced
    ├── README.md              # Synced
    └── .git/                  # NOT synced (.stignore)
```

### 3. Git + Syncthing Together
- `.git` directory is ignored via `.stignore`
- Syncthing keeps working files in sync
- Git still works locally for commits/history
- Can `git pull` periodically to sync from remote

## Quick Start (Your Workflow)

### Step 1: Deploy to Hub (LXC)
```bash
ansible-playbook -i inventory/hosts.ini playbooks/deploy_syncthing.yml --limit lxc_containers

# Or specific container
ansible-playbook -i inventory/hosts.ini playbooks/deploy_syncthing.yml --limit 192.168.0.11
```

### Step 2: Deploy to Clients (Proxmox nodes)
```bash
ansible-playbook -i inventory/hosts.ini playbooks/deploy_syncthing.yml --limit proxmox_nodes
```

### Step 3: Get All Device IDs
```bash
ansible-playbook -i inventory/hosts.ini playbooks/get_syncthing_device_ids.yml
```

Output format:
```
pve (192.168.0.157): AAAAAAA-BBBBBBB-CCCCCCC-DDDDDDD-EEEEEEE-FFFFFFF-GGGGGGG-HHHHHHH
lxc-ansible (192.168.0.11): XXXXXXX-YYYYYYY-ZZZZZZZ-1111111-2222222-3333333-4444444-5555555
```

### Step 4: Configure GUI on Each Host

**On Hub (LXC):**
```bash
ssh -L 8385:127.0.0.1:8384 josh@192.168.0.11
# Browser: http://127.0.0.1:8385
```

1. Actions → Settings → GUI
   - Set username/password
   - Save

2. Add Remote Devices
   - Add each client device ID
   - Give friendly names (pve, pve2, pve3)

3. Configure Folder
   - Add Folder
   - ID: `dotfiles`
   - Path: `/syncthing/dotfiles-josh`
   - Share with: all client devices
   - Edit → Ignore Patterns: `.git`

**On Each Client:**
```bash
ssh -L 8386:127.0.0.1:8384 josh@192.168.0.157
# Browser: http://127.0.0.1:8386
```

1. Set GUI username/password
2. Add hub device ID
3. Accept dotfiles folder when prompted
   - Path: `/syncthing/dotfiles-josh`
   - Confirm sharing

### Step 5: NixOS Laptop (Declarative)

Add to `configuration.nix`:

```nix
{
  services.syncthing = {
    enable = true;
    user = "josh";
    group = "users";
    dataDir = "/home/josh";
    configDir = "/home/josh/.config/syncthing";
    openDefaultPorts = true;
    guiAddress = "127.0.0.1:8384";
  };
}
```

Then:
```bash
sudo nixos-rebuild switch
```

Access GUI and add:
- Hub device ID
- Accept dotfiles folder → path: `/home/josh/dotfiles`

## Verification

### Check Service Status
```bash
# On Proxmox/Debian
ansible proxmox_nodes -i inventory/hosts.ini -m shell -a "systemctl status syncthing-josh" -b

# On specific host
ssh josh@192.168.0.157
systemctl status syncthing-josh
journalctl -u syncthing-josh -f
```

### Check Sync Status
GUI → dotfiles folder → check "Out of Sync" items

### Test Sync
```bash
# On any machine
echo "alias testme='echo syncthing works'" >> /syncthing/dotfiles-josh/.bash_aliases

# Check on other machines - should appear within seconds
cat /syncthing/dotfiles-josh/.bash_aliases
```

## Common Issues & Solutions

### GUI Not Accessible
```bash
# Check service is running
systemctl status syncthing-josh

# Verify it's listening
ss -tlnp | grep 8384

# Use SSH tunnel
ssh -L 8385:127.0.0.1:8384 josh@<host>
```

### Devices Not Connecting
- Check firewall: ports 22000/tcp, 21027/udp
- Verify both devices added each other
- Check "Recent Changes" in GUI for errors

### Files Not Syncing
- Ensure folder is "Up to Date" on hub
- Check `.stignore` isn't blocking files
- Look for conflicts in folder
- Check "Failed Items" in folder detail

### .git Getting Synced (Bad!)
Create/verify `.stignore` in folder:
```bash
echo ".git" > /syncthing/dotfiles-josh/.stignore
```

## Production Inventory Example

`inventory/group_vars/all.yml`:
```yaml
syncthing_user: "josh"
syncthing_service_type: "system"  # For Proxmox compatibility
```

`inventory/group_vars/lxc_containers.yml`:
```yaml
syncthing_data_dir: "/syncthing"
syncthing_dotfiles_dir: "/syncthing/dotfiles-josh"

syncthing_folders:
  - id: "dotfiles"
    label: "Dotfiles"
    path: "/syncthing/dotfiles-josh"
    type: "sendreceive"
    ignore_patterns:
      - ".git"
      - ".gitignore"
```

`inventory/group_vars/proxmox_nodes.yml`:
```yaml
syncthing_data_dir: "/syncthing"
syncthing_dotfiles_dir: "/syncthing/dotfiles-josh"

syncthing_folders:
  - id: "dotfiles"
    label: "Dotfiles"
    path: "/syncthing/dotfiles-josh"
    type: "sendreceive"
    ignore_patterns:
      - ".git"
```

## Automation Limitations

**What Ansible handles:**
- ✅ Install Syncthing
- ✅ Create directories
- ✅ Setup systemd service
- ✅ Create `.stignore` files

**What's still manual (via GUI):**
- ⚠️ Adding device IDs
- ⚠️ Accepting folder shares
- ⚠️ Setting GUI passwords

**Future automation:** Could use Syncthing REST API or `syncthing cli` to automate device/folder configuration.

## NixOS Note

**Do NOT use Ansible for NixOS Syncthing setup.**

Use declarative configuration instead:

```nix
services.syncthing = {
  enable = true;
  user = "josh";
  # ... etc
};
```

Ansible is only for Debian/Ubuntu/Proxmox hosts.

## Maintenance

### Backup Config
```bash
tar -czf syncthing-backup-$(date +%Y%m%d).tar.gz /home/josh/.config/syncthing
```

### Update Syncthing
```bash
# Ansible managed hosts
ansible all -i inventory/hosts.ini -m apt -a "name=syncthing state=latest update_cache=yes" -b

# NixOS
sudo nixos-rebuild switch
```

### Add New Machine
1. Deploy Syncthing: `ansible-playbook deploy_syncthing.yml --limit newhost`
2. Get device ID: `ansible-playbook get_syncthing_device_ids.yml --limit newhost`
3. Add to hub GUI
4. Accept folder on new host GUI

## Resources

- Syncthing docs: https://docs.syncthing.net/
- Ignore patterns: https://docs.syncthing.net/users/ignoring.html
- REST API (future automation): https://docs.syncthing.net/dev/rest.html
