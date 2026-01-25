# Ansible Infrastructure Automation

This repository automates the configuration and management of server infrastructure using Ansible. It currently focuses on a Proxmox VE cluster, a media server running Docker containers for media management, and setting up workstations.

---


## Repository Structure

```text
ANSIBLE/
├── Files/
│   ├── sudor_ansible 
│   └── users.yml
├── inventory/
│   └── hosts.ini
├── playbooks/
│   ├── onboard_all.yml
├── files/
│   ├── how_to_run_playbooks.txt
│   ├── sudoer_ansible
│   └── users.yml
│   ├── update_bash.yml
│   └── update_servers.yml
├── roles/
│   ├── base/
│   │   ├── defaults/
│   │   ├── meta/
│   ├── onboard.yml
│   ├── dotfiles/
│   │   ├── defaults/
│   │   └── tasks/
│   ├── media_server/
│   │   ├── defaults/
│   │   ├── meta/
│   │   └── tasks/
│   ├── proxmox_servers/
│   │   ├── defaults/
│   │   ├── meta/
│   │   └── tasks/
│   └── workstations/
│       ├── defaults/
│       ├── meta/
│       └── tasks/
├── ansible.cfg
└── README.md

```


## Running Playbooks

To run the Ansible playbooks, ensure you have Ansible installed and configured on your control machine. You can execute the playbooks using the following command:

```bash
ansible-playbook playbooks/onboard.yml -K
```
This command will prompt for the sudo password (`-K`) and execute the `onboard.yml` playbook, which includes tasks for setting up the Proxmox cluster, media server, and workstations.
To run a playbook, use:
## Playbooks Overview 
- **onboard.yml**: Main playbook that orchestrates the onboarding of all components.
- **onboard_all.yml**: Playbook to onboard all components including Proxmox, media server, and workstations.
- **onboard_media.yml**: Playbook specifically for setting up the media server.
- **onboard_workstations.yml**: Playbook for configuring workstations.
- **update_bash.yml**: Playbook to update bash configurations and install necessary packages.
- **update_servers.yml**: Playbook to update server configurations and packages.
- **onboard_all.yml**: Complete onboarding for all hosts (users, SSH, media servers, workstations)
## Roles Overview
- **base**: Contains common tasks and configurations shared across all servers.
- **dotfiles**: Manages user-specific dotfiles and configurations.
- **media_server**: Configures the media server with Docker containers for media management.
- **proxmox_servers**: Sets up the Proxmox VE cluster and manages virtual machines and containers.
- **workstations**: Configures workstations with necessary software and settings.


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


