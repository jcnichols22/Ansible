# Ansible Infrastructure Automation

This repository automates the configuration and management of server infrastructure using Ansible. It currently focuses on a Proxmox VE cluster and a media server running Docker containers for media management.

---

## Overview

### Proxmox VE Cluster
- **Nodes:** pve, pve1 (in cluster)
- **Cluster Management:** LXC container provisioning, resource allocation, and HA configuration

### Media Server
- **OS:** Ubuntu Server LTS
- **Services:**
  - **Dockerized Applications:**
    - Arr Stack (Radarr, Sonarr, Prowlarr)
    - Jellyfin Media Server
    - Plex Media Server
  - **Storage Management:** Media libraries
  - **Automation:** Media processing pipelines


## Repository Structure

```text
├── ansible.cfg               # Ansible configuration
├── inventory/                # Host inventory
│   └── hosts.ini             # Production hosts
├── roles/
│   ├── base/                 # Common tasks for all servers
│   ├── proxmox/              # Proxmox cluster management
│   └── media_server/         # Media stack deployment
│   ├── workstations/         # Workstation configuration
├── playbooks/                # Ansible playbooks
├── files/                    # Files to be used by playbooks
```


## Running Playbooks

### Run Proxmox setup playbook
- **ansible-playbook playbooks/proxmox-setup.yml -l proxmox_cluster**

### Deploy media stack
- **ansible-playbook playbooks/media-stack.yml -l media_servers**



## Future Automation Roadmap

### Proxmox Cluster Automation

- **Automated cluster initialization with corosync/pacemaker**
- **LXC template management for consistent container deployments**
- **Storage configuration automation (ZFS/Ceph)**
- **HA proxy setup for service failover**

### Media Server Enhancements

- **Docker Compose integration for container management**
- **Automated Let's Encrypt certificate rotation**
- **Media library synchronization tasks**
- **Backup/restore workflows for container configurations**
- **Monitoring stack (Prometheus/Grafana) integration**

### General Improvements

- **CI/CD pipeline for playbook testing**
- **Terraform integration for infrastructure provisioning**
- **Vault integration for secret management**
- **Multi-environment support (dev/staging/prod)**


