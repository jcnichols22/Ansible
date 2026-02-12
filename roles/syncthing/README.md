# Syncthing Ansible Role

Automate Syncthing installation and configuration across your infrastructure.

## Overview

This role installs and configures Syncthing for file synchronization across multiple devices. It supports Debian, Ubuntu, and Arch-based systems.

## Role Structure

```
roles/syncthing/
├── defaults/main.yml       # Default variables
├── handlers/main.yml       # Service restart handlers
├── meta/main.yml          # Role metadata
├── tasks/main.yml         # Main installation/configuration tasks
└── templates/
    ├── config.xml.j2      # Main Syncthing configuration
    └── folder.xml.j2      # Folder configuration template
```

## Features

- ✅ Automatic installation from official Syncthing repository
- ✅ Multi-distribution support (Debian, Ubuntu, Arch)
- ✅ Automatic device configuration
- ✅ Folder synchronization setup
- ✅ Systemd service management
- ✅ GUI configuration
- ✅ Firewall rules (optional)
- ✅ Backup of existing configurations

## Requirements

- Ansible 2.9+
- systemd-based system
- Root/sudo access

## Quick Start

### 1. Install Syncthing on all hosts

```bash
ansible-playbook -i inventory/hosts.ini playbooks/deploy_syncthing.yml
```

### 2. Get device IDs from all hosts

```bash
ansible-playbook -i inventory/hosts.ini playbooks/get_syncthing_device_ids.yml
```

### 3. Configure synchronization

Update your inventory with device IDs, then run specific playbooks:

```bash
# For workstations
ansible-playbook -i inventory/hosts.ini playbooks/setup_syncthing_workstations.yml

# For media servers
ansible-playbook -i inventory/hosts.ini playbooks/setup_syncthing_media.yml

# For LXC containers
ansible-playbook -i inventory/hosts.ini playbooks/setup_syncthing_lxc.yml
```

## Playbooks

### deploy_syncthing.yml
Basic Syncthing installation on all hosts.

### get_syncthing_device_ids.yml
Collects device IDs from all hosts for easy reference.

### setup_syncthing_workstations.yml
Configures folder sync between workstations (Documents, Pictures, etc.).

### setup_syncthing_media.yml
Configures media servers with backup synchronization.

### setup_syncthing_lxc.yml
Sets up LXC containers to sync configs to central location.

### add_syncthing_device.yml
Adds a new device to existing Syncthing installations.

## Configuration Examples

### Basic Installation

```yaml
# In your playbook
- hosts: all
  roles:
    - syncthing
```

### Configure Devices and Folders

```yaml
# In group_vars/workstations.yml
syncthing_user: "josh"

syncthing_devices:
  - name: "Laptop"
    id: "AAAAAAA-BBBBBBB-CCCCCCC-DDDDDDD-EEEEEEE-FFFFFFF-GGGGGGG-HHHHHHH"
    addresses: "dynamic"
  - name: "Desktop"
    id: "XXXXXXX-YYYYYYY-ZZZZZZZ-1111111-2222222-3333333-4444444-5555555"
    addresses: "tcp://192.168.0.50:22000"

syncthing_folders:
  - id: "documents"
    label: "Documents"
    path: "/home/josh/Documents"
    devices:
      - "Laptop"
      - "Desktop"
    type: "sendreceive"
    rescan_interval: 3600
  
  - id: "backup"
    label: "Backup"
    path: "/home/josh/Backup"
    devices:
      - "Desktop"
    type: "sendonly"
    rescan_interval: 86400
```

### Enable Web GUI with Authentication

```yaml
syncthing_gui_enabled: true
syncthing_gui_address: "0.0.0.0:8384"  # Listen on all interfaces
syncthing_gui_user: "admin"
syncthing_gui_password: "securepassword"  # Use ansible-vault in production
syncthing_firewall_enabled: true
```

## Variables

### Installation Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `syncthing_install_method` | `official` | Installation method (`package` or `official`) |
| `syncthing_user` | `{{ ansible_user }}` | User to run Syncthing service |
| `syncthing_config_dir` | `~/.config/syncthing` | Configuration directory |
| `syncthing_service_enabled` | `true` | Enable service on boot |

### GUI Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `syncthing_gui_enabled` | `true` | Enable web GUI |
| `syncthing_gui_address` | `127.0.0.1:8384` | GUI listen address |
| `syncthing_gui_user` | `""` | GUI username (optional) |
| `syncthing_gui_password` | `""` | GUI password (optional) |

### Network Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `syncthing_listen_address` | `default` | Sync protocol listen address |
| `syncthing_max_send_kbps` | `0` | Max upload speed (0=unlimited) |
| `syncthing_max_recv_kbps` | `0` | Max download speed (0=unlimited) |
| `syncthing_global_discovery_enabled` | `true` | Enable global discovery |
| `syncthing_local_discovery_enabled` | `true` | Enable local discovery |
| `syncthing_relays_enabled` | `true` | Enable relay servers |

### Devices Configuration

```yaml
syncthing_devices:
  - name: "DeviceName"           # Friendly name
    id: "DEVICE-ID-HERE"         # 56-character device ID
    addresses: "dynamic"          # "dynamic" or "tcp://ip:port"
```

### Folders Configuration

```yaml
syncthing_folders:
  - id: "folder-id"              # Unique folder ID
    label: "Folder Label"        # Display name
    path: "/path/to/folder"      # Absolute path
    devices:                      # List of device names
      - "Device1"
      - "Device2"
    type: "sendreceive"          # sendreceive, sendonly, receiveonly
    rescan_interval: 3600        # Seconds between rescans
    ignore_delete: false         # Ignore deletions
    ignore_perms: false          # Ignore permissions
```

## Common Workflows

### Adding a New Device

1. Install Syncthing on the new device:
   ```bash
   ansible-playbook -i inventory/hosts.ini playbooks/deploy_syncthing.yml --limit new-device
   ```

2. Get the device ID:
   ```bash
   ansible-playbook -i inventory/hosts.ini playbooks/get_syncthing_device_ids.yml --limit new-device
   ```

3. Update your inventory with the new device ID in `group_vars/` or `host_vars/`

4. Re-run the appropriate setup playbook:
   ```bash
   ansible-playbook -i inventory/hosts.ini playbooks/setup_syncthing_workstations.yml
   ```

### Creating a New Sync Folder

1. Update your inventory to add the folder to `syncthing_folders`

2. Re-run the playbook:
   ```bash
   ansible-playbook -i inventory/hosts.ini playbooks/setup_syncthing_workstations.yml
   ```

### Backup Configuration

All configuration changes create automatic backups in the config directory with timestamps.

## Folder Types

- **sendreceive**: Bidirectional sync (both send and receive changes)
- **sendonly**: Only send changes to other devices
- **receiveonly**: Only receive changes from other devices

## Ports

- **22000/tcp**: Sync protocol (default)
- **21027/udp**: Local discovery
- **8384/tcp**: Web GUI (default, localhost only)

## Security Considerations

1. **Use ansible-vault** for GUI passwords:
   ```bash
   ansible-vault encrypt_string 'mypassword' --name 'syncthing_gui_password'
   ```

2. **Restrict GUI access** to localhost unless needed:
   ```yaml
   syncthing_gui_address: "127.0.0.1:8384"
   ```

3. **Use specific device addresses** instead of discovery when possible:
   ```yaml
   addresses: "tcp://192.168.0.100:22000"
   ```

## Troubleshooting

### Check service status
```bash
systemctl status syncthing@josh
```

### View logs
```bash
journalctl -u syncthing@josh -f
```

### Manual device ID retrieval
```bash
syncthing --device-id
```

### Access web GUI
```
http://<host-ip>:8384
```

## Examples

See the `playbooks/` directory for complete examples:
- Basic deployment
- Workstation sync
- Media server backup
- LXC container configuration
- Device management

## License

MIT

## Author

jcnichols22
