# Syncthing Configuration Examples

This directory contains example inventory configurations for Syncthing automation.

## Example 1: Workstation Sync

Create `inventory/group_vars/workstations.yml`:

```yaml
---
syncthing_user: "josh"

# After running get_syncthing_device_ids.yml, fill in actual IDs
syncthing_devices:
  - name: "MainLaptop"
    id: "AAAAAAA-BBBBBBB-CCCCCCC-DDDDDDD-EEEEEEE-FFFFFFF-GGGGGGG-HHHHHHH"
    addresses: "dynamic"
  
  - name: "HomeDesktop"
    id: "XXXXXXX-YYYYYYY-ZZZZZZZ-1111111-2222222-3333333-4444444-5555555"
    addresses: "tcp://192.168.0.50:22000"

syncthing_folders:
  - id: "documents"
    label: "Documents"
    path: "/home/josh/Documents"
    devices:
      - "MainLaptop"
      - "HomeDesktop"
    type: "sendreceive"
    
  - id: "projects"
    label: "Projects"
    path: "/home/josh/Projects"
    devices:
      - "MainLaptop"
      - "HomeDesktop"
    type: "sendreceive"
```

## Example 2: Media Server with Backup

Create `inventory/group_vars/media_servers.yml`:

```yaml
---
syncthing_user: "josh"

syncthing_devices:
  - name: "MediaServer"
    id: "MEDIA01-DEVICE-ID-HERE"
    addresses: "tcp://192.168.0.102:22000"
  
  - name: "BackupNAS"
    id: "BACKUP-DEVICE-ID-HERE"
    addresses: "tcp://192.168.0.200:22000"

syncthing_folders:
  - id: "docker-configs"
    label: "Docker Configs"
    path: "/home/josh/docker-compose"
    devices:
      - "MediaServer"
      - "BackupNAS"
    type: "sendreceive"
    rescan_interval: 7200
  
  - id: "media-backups"
    label: "Media Backups"
    path: "/mnt/backups"
    devices:
      - "BackupNAS"
    type: "sendonly"
    rescan_interval: 86400

# Allow remote access to GUI
syncthing_gui_address: "0.0.0.0:8384"
syncthing_gui_user: "admin"
syncthing_gui_password: "{{ vault_syncthing_password }}"  # Store in vault
syncthing_firewall_enabled: true
```

## Example 3: LXC Containers Central Backup

Create `inventory/group_vars/lxc_containers.yml`:

```yaml
---
syncthing_user: "ansible"

syncthing_devices:
  - name: "ConfigCentralServer"
    id: "CENTRAL-SERVER-DEVICE-ID"
    addresses: "tcp://192.168.0.11:22000"

# Each container syncs its own config
syncthing_folders:
  - id: "lxc-{{ ansible_hostname }}-config"
    label: "{{ ansible_hostname }} Config"
    path: "/etc/app-config"
    devices:
      - "ConfigCentralServer"
    type: "sendreceive"
    ignore_perms: true

syncthing_gui_enabled: true
syncthing_gui_address: "127.0.0.1:8384"
```

## Example 4: Mixed Environment

Create `inventory/host_vars/192.168.0.102.yml` (media server):

```yaml
---
syncthing_user: "josh"

syncthing_devices:
  - name: "Laptop"
    id: "LAPTOP-DEVICE-ID"
    addresses: "dynamic"
  
  - name: "Desktop" 
    id: "DESKTOP-DEVICE-ID"
    addresses: "tcp://192.168.0.50:22000"
  
  - name: "BackupNAS"
    id: "NAS-DEVICE-ID"
    addresses: "tcp://192.168.0.200:22000"

syncthing_folders:
  # Share photos with workstations
  - id: "family-photos"
    label: "Family Photos"
    path: "/mnt/media/Photos"
    devices:
      - "Laptop"
      - "Desktop"
    type: "sendreceive"
  
  # Backup to NAS only
  - id: "critical-data"
    label: "Critical Data"
    path: "/home/josh/critical"
    devices:
      - "BackupNAS"
    type: "sendonly"
    rescan_interval: 3600
  
  # Receive backups from workstations
  - id: "workstation-backups"
    label: "Workstation Backups"
    path: "/mnt/backups/workstations"
    devices:
      - "Laptop"
      - "Desktop"
    type: "receiveonly"
```

## Step-by-Step Usage

### 1. Initial Setup

```bash
# Deploy Syncthing to all hosts
ansible-playbook -i inventory/hosts.ini playbooks/deploy_syncthing.yml

# Collect all device IDs
ansible-playbook -i inventory/hosts.ini playbooks/get_syncthing_device_ids.yml
```

### 2. Configure Variables

Copy the output from step 1 and create appropriate variable files in:
- `inventory/group_vars/<group>.yml`
- `inventory/host_vars/<host>.yml`

### 3. Deploy Configuration

```bash
# For workstations
ansible-playbook -i inventory/hosts.ini playbooks/setup_syncthing_workstations.yml

# For media servers
ansible-playbook -i inventory/hosts.ini playbooks/setup_syncthing_media.yml

# For LXC containers
ansible-playbook -i inventory/hosts.ini playbooks/setup_syncthing_lxc.yml
```

### 4. Verify

Access the web GUI on any host:
```
http://<host-ip>:8384
```

## Advanced: Using Ansible Vault

Store sensitive data securely:

```bash
# Create vault file
ansible-vault create inventory/group_vars/media_servers/vault.yml
```

Add to `vault.yml`:
```yaml
---
vault_syncthing_password: "your-secure-password"
vault_syncthing_api_key: "your-api-key"
```

Reference in `media_servers.yml`:
```yaml
---
syncthing_gui_password: "{{ vault_syncthing_password }}"
syncthing_gui_api_key: "{{ vault_syncthing_api_key }}"
```

Run playbooks with vault password:
```bash
ansible-playbook -i inventory/hosts.ini playbooks/setup_syncthing_media.yml --ask-vault-pass
```

## Common Patterns

### Pattern 1: Hub and Spoke
Central server receives from all devices:
```yaml
# On workstations - sendonly
type: "sendonly"

# On central server - receiveonly  
type: "receiveonly"
```

### Pattern 2: Peer-to-Peer
All devices sync equally:
```yaml
type: "sendreceive"
```

### Pattern 3: Backup Chain
Device A → Device B → Device C:
```yaml
# Device A
type: "sendonly"

# Device B  
type: "sendreceive"

# Device C
type: "receiveonly"
```

## Folder Sync Strategies

### Fast Sync (Frequent Changes)
```yaml
rescan_interval: 60  # 1 minute
```

### Normal Sync (Regular Files)
```yaml
rescan_interval: 3600  # 1 hour
```

### Slow Sync (Backups)
```yaml
rescan_interval: 86400  # 24 hours
```

## Tips

1. **Start Simple**: Begin with one or two folders between two devices
2. **Test First**: Use a test folder before syncing important data
3. **Monitor Initial Sync**: Large initial syncs can take time
4. **Use Labels**: Give folders descriptive labels for easy identification
5. **Plan Device Names**: Use consistent, descriptive device names across your infrastructure
