# Ansible Infrastructure Automation

This repository automates the configuration and management of server infrastructure using Ansible. It currently focuses on a Proxmox VE cluster, a media server running Docker containers for media management, and setting up workstations.

---


## Repository Structure


```text
Ansible/
├── ansible.cfg
├── README.md
├── files/
│   ├── how_to_run_playbooks.txt
├── inventory/
│   ├── hosts.ini
│   └── group_vars/
│       └── all.yml         # Global/shared variables (e.g., users)
├── playbooks/
│   ├── onboard_all.yml
│   ├── onboard_lxc.yml
│   ├── update_docker_media.yml
│   ├── update_lxc_containers.yml
│   └── update_servers.yml
├── roles/
│   ├── base/
│   │   ├── defaults/
│   │   │   └── main.yml    # Role-specific defaults
│   │   └── tasks/
│   ├── dotfiles/
│   │   ├── defaults/
│   │   └── tasks/
│   ├── media_server/
│   │   ├── defaults/
│   │   ├── meta/
│   │   └── tasks/
│   └── workstations/
│       ├── defaults/
│       └── tasks/
```



## Variable Management

- **Global/shared variables** (such as the `users` list) are defined in `inventory/group_vars/all.yml` and are automatically available to all hosts and playbooks.
- **Role-specific defaults** should be placed in each role’s `defaults/main.yml` (e.g., `roles/base/defaults/main.yml`). These are only available to that role.

## Running Playbooks

To run a playbook, use:

```bash
ansible-playbook playbooks/onboard_all.yml -K
```
This will prompt for the sudo password (`-K`) and execute the onboarding playbook. Adjust the playbook name as needed for your use case.

## Playbooks Overview
**onboard_all.yml**: Complete onboarding for all hosts (users, SSH, media servers, workstations)
**onboard_lxc.yml**: Onboard LXC containers with users and SSH keys
**update_docker_media.yml**: Playbook to update Docker containers on the media server
**update_lxc_containers.yml**: Playbook to update LXC containers
**update_servers.yml**: Playbook to update server configurations and packages
## Roles Overview
**base**: Contains common tasks and configurations shared across all servers
**dotfiles**: Manages user-specific dotfiles and configurations
**media_server**: Configures the media server with Docker containers for media management
**workstations**: Configures workstations with necessary software and settings


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


