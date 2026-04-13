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
│   └── prod/
│       ├── hosts.ini
│       └── group_vars/
│           └── all.yml     # Global/shared variables (e.g., users)
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

- **Global/shared variables** (such as the `users` list) are defined in `inventory/prod/group_vars/all.yml` and are automatically available to all hosts and playbooks.
- **Role-specific defaults** should be placed in each role’s `defaults/main.yml` (e.g., `roles/base/defaults/main.yml`). These are only available to that role.

## Running Playbooks

To run a playbook, use:

```bash
ansible-playbook playbooks/onboard_all.yml -K
```

This will prompt for the sudo password (`-K`) and execute the onboarding playbook. Adjust the playbook name as needed for your use case.

For first-time LXC onboarding (includes SSH key bootstrap + stale APT repo remediation), run:

```bash
ansible-playbook playbooks/onboard_lxc.yml -K
```

To sync service monitors into Uptime Kuma from Ansible vars, run:

```bash
ansible-playbook playbooks/sync_uptime_kuma.yml -K
```

This is the secure default (sync task output remains hidden). For troubleshooting only:

```bash
ansible-playbook playbooks/sync_uptime_kuma.yml -K -e kuma_sync_no_log=false
```

To sync inventory hosts into NetBox devices and management IPs, run:

```bash
ansible-playbook playbooks/sync_netbox_inventory.yml -K
```

To discover Docker services on the media server and sync `service.lan` entries into
Nginx Proxy Manager and AdGuard Home, run:

```bash
ansible-playbook playbooks/sync_service_hosts_docker.yml -K
```

To ingest Omada-managed network devices into NetBox (separate pipeline), run:

```bash
ansible-playbook playbooks/sync_netbox_omada.yml -K
```

## Playbooks Overview

**onboard_all.yml**: Complete onboarding for all hosts (users, SSH, media servers, workstations)
**onboard_lxc.yml**: Onboard LXC containers with users and SSH keys
**update_docker_media.yml**: Playbook to update Docker containers on the media server
**update_lxc_containers.yml**: Playbook to update LXC containers
**update_servers.yml**: Playbook to update server configurations and packages
**sync_uptime_kuma.yml**: Creates/updates Uptime Kuma monitors from `kuma_services` in `inventory/prod/group_vars/all.yml`
**sync_netbox_inventory.yml**: Creates/updates NetBox devices from inventory and assigns primary management IPs
**sync_netbox_omada.yml**: Ingests Omada controller devices into NetBox (one-way Omada -> NetBox), including connected port cable sync when link data is available
**sync_service_hosts_docker.yml**: Discovers Docker Compose services with published ports on the media server, then creates/updates matching Nginx Proxy Manager proxy hosts and AdGuard Home DNS rewrites for `service.lan`

## Uptime Kuma Monitor Sync

Define these variables in `inventory/prod/group_vars/all.yml`:

- `kuma_url`
- `kuma_username`
- `kuma_password`
- `kuma_services` (list of monitor definitions)

By default, this playbook auto-generates `ping` monitors for all hosts from
`inventory/prod/hosts.ini` (`all:!localhost`) and merges them with `kuma_services`.

For authenticated Kuma instances, define local secrets in `inventory/prod/group_vars/kuma_secrets.local.yml`
(git-ignored). Use `kuma_username` and `kuma_password` for this automation flow.

Supported monitor types in this repo sync script are:

- `http` (requires `url`)
- `ping` (requires `hostname`)
- `port` (requires `hostname`, `port`)
- `dns` (requires `hostname`)

## NetBox Inventory Sync

Define these variables in `inventory/prod/group_vars/all.yml`:

- `netbox_auto_host_pattern` (default `all:!localhost`)
- `netbox_default_site`
- `netbox_default_device_role`
- `netbox_default_device_status`
- `netbox_default_manufacturer`
- `netbox_default_device_type`
- `netbox_mgmt_interface`

Define local secrets in `inventory/prod/group_vars/netbox_secrets.local.yml`
(git-ignored):

- `netbox_url`
- `netbox_token`
- `netbox_verify_ssl` (set `false` for self-signed certs)

Per-host overrides are supported directly in inventory host vars:

- `netbox_site`
- `netbox_device_role`
- `netbox_status`
- `netbox_manufacturer`
- `netbox_device_type`
- `netbox_mgmt_interface`
- `netbox_serial`
- `netbox_comments`
- `netbox_tags` (list)

## Omada to NetBox Sync

Define local secrets in `inventory/prod/group_vars/omada_secrets.local.yml`
(git-ignored):

- `omada_url`
- `omada_username`
- `omada_password`
- `omada_verify_ssl` (set `false` for self-signed certs)

Define behavior in `inventory/prod/group_vars/all.yml`:

- `omada_sync_report_only` (default `false`)
- `omada_sync_dry_run` (default `false`)
- `omada_site_filter` (list of Omada site names, empty means all)
- `omada_site_map` (Omada site name -> NetBox site name)
- `omada_role_map` (`ap`/`switch`/`gateway` -> NetBox role)
- `omada_default_manufacturer`
- `omada_default_device_status`
- `omada_mgmt_interface`
- `omada_port_interface_prefix` (default `port`; used when Omada provides numeric port values)
- `omada_include_site_in_name` (default `true`)
- `omada_link_report` (default `true`; prints a per-link audit table with actions and skip reasons)

Recommended first run:

- Set `omada_sync_report_only: true`
- Run `ansible-playbook playbooks/sync_netbox_omada.yml -K`
- Review output summary, then set `omada_sync_report_only: false` to apply changes

Connected port syncing notes:

- The Omada sync remains one-way: it only writes to NetBox and never writes to Omada.
- When Omada exposes upstream link metadata, the sync creates/updates NetBox cables between interfaces.
- If a device moves ports, the old cable is removed and a new cable is created to reflect the new connection.
- If port-link metadata is missing for a device, device/IP sync still runs and cable sync is skipped for that link.
- Enable `omada_link_report: true` to print a per-link audit table showing discovered links, applied changes, and skipped reasons.

## Docker Service Host Sync

Define behavior in `inventory/prod/group_vars/all.yml`:

- `docker_service_sync_media_server_host`
- `docker_service_sync_media_server_user`
- `docker_service_sync_compose_dir`
- `docker_service_sync_domain_suffix`
- `docker_service_sync_rewrite_target`
- `docker_service_sync_backend_scheme`
- `docker_service_sync_service_exclude` (list)
- `docker_service_sync_service_overrides` (mapping by compose service name)

Define local secrets in git-ignored files:

- `inventory/prod/group_vars/npm_secrets.local.yml`
- `inventory/prod/group_vars/adguard_secrets.local.yml`

This playbook uses `docker compose ps --format json` on the media server,
keeps the first published TCP port for each running service, creates missing
`service.lan` proxy hosts in Nginx Proxy Manager, and creates matching AdGuard
Home rewrites that point to the NPM IP.

If a matching proxy host or rewrite already exists, it is left alone unless the
configured backend or rewrite target no longer matches the desired state.

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


\n## [2026-04-13] Added openclaw_onboard Ansible role\n- Automated onboarding for the openclaw user, ops group, SSH key, and permissions.\n- Role location: roles/openclaw_onboard\n- To use: Add openclaw_onboard to your onboarding playbooks.\n

## [2026-04-13] Added openclaw_onboard_machine.yml playbook
- New playbook for onboarding single machines to openclaw automation, allowing gradual rollout and testing.
- Location: playbooks/openclaw_onboard_machine.yml
- Usage: ansible-playbook playbooks/openclaw_onboard_machine.yml -l <target_host> -K

