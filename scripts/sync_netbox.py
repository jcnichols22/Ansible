#!/usr/bin/env python3
import argparse
import ipaddress
import json
import os
import sys
from typing import Any, Dict, List, Optional


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync hosts into NetBox")
    parser.add_argument("--url", default="", help="NetBox URL, e.g. https://netbox.local")
    parser.add_argument("--token", default="", help="NetBox API token")
    parser.add_argument(
        "--verify-ssl",
        default="",
        help="TLS verification setting (true/false), defaults from NETBOX_VERIFY_SSL",
    )
    parser.add_argument(
        "--hosts-json",
        default=None,
        help="JSON list of host objects (or use NETBOX_HOSTS_JSON env var)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show intended changes without writing")
    return parser.parse_args()


def parse_bool(value: str, default: bool = False) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def read_hosts(raw: str) -> List[Dict[str, Any]]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON for hosts: {exc}") from exc

    if not isinstance(parsed, list):
        raise ValueError("hosts JSON must be a list")

    for index, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise ValueError(f"hosts[{index}] must be an object")
        if not str(item.get("name", "")).strip():
            raise ValueError(f"hosts[{index}] must include non-empty 'name'")

    return parsed


def ensure_cidr(address: str) -> str:
    value = address.strip()
    if not value:
        return ""
    if "/" in value:
        return value

    try:
        parsed = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ValueError(f"Invalid management IP '{address}'") from exc

    if parsed.version == 4:
        return f"{value}/32"
    return f"{value}/128"


def get_by_name_or_slug(endpoint: Any, value: str) -> Optional[Any]:
    if not value:
        return None

    obj = endpoint.get(name=value)
    if obj is not None:
        return obj

    slug = value.strip().lower().replace(" ", "-")
    return endpoint.get(slug=slug)


def ensure_site(nb: Any, site_name: str, dry_run: bool) -> Any:
    existing = get_by_name_or_slug(nb.dcim.sites, site_name)
    if existing:
        return existing

    if dry_run:
        print(f"[DRY-RUN] create site: {site_name}")
        return {"id": -1, "name": site_name, "slug": site_name.strip().lower().replace(' ', '-')}

    created = nb.dcim.sites.create(
        {
            "name": site_name,
            "slug": site_name.strip().lower().replace(" ", "-"),
            "status": "active",
        }
    )
    print(f"Created site: {site_name}")
    return created


def ensure_role(nb: Any, role_name: str, dry_run: bool) -> Any:
    existing = get_by_name_or_slug(nb.dcim.device_roles, role_name)
    if existing:
        return existing

    if dry_run:
        print(f"[DRY-RUN] create device role: {role_name}")
        return {"id": -1, "name": role_name, "slug": role_name.strip().lower().replace(' ', '-')}

    created = nb.dcim.device_roles.create(
        {
            "name": role_name,
            "slug": role_name.strip().lower().replace(" ", "-"),
            "color": "9e9e9e",
        }
    )
    print(f"Created device role: {role_name}")
    return created


def ensure_manufacturer(nb: Any, manufacturer_name: str, dry_run: bool) -> Any:
    existing = get_by_name_or_slug(nb.dcim.manufacturers, manufacturer_name)
    if existing:
        return existing

    if dry_run:
        print(f"[DRY-RUN] create manufacturer: {manufacturer_name}")
        return {
            "id": -1,
            "name": manufacturer_name,
            "slug": manufacturer_name.strip().lower().replace(" ", "-"),
        }

    created = nb.dcim.manufacturers.create(
        {
            "name": manufacturer_name,
            "slug": manufacturer_name.strip().lower().replace(" ", "-"),
        }
    )
    print(f"Created manufacturer: {manufacturer_name}")
    return created


def ensure_device_type(nb: Any, manufacturer: Any, model_name: str, dry_run: bool) -> Any:
    existing = nb.dcim.device_types.get(model=model_name, manufacturer_id=manufacturer["id"])
    if existing:
        return existing

    slug = model_name.strip().lower().replace(" ", "-")

    if dry_run:
        print(f"[DRY-RUN] create device type: {model_name}")
        return {"id": -1, "model": model_name, "slug": slug}

    created = nb.dcim.device_types.create(
        {
            "manufacturer": manufacturer["id"],
            "model": model_name,
            "slug": slug,
            "u_height": 1,
            "is_full_depth": False,
        }
    )
    print(f"Created device type: {model_name}")
    return created


def ensure_interface(nb: Any, device: Any, interface_name: str, dry_run: bool) -> Any:
    existing = nb.dcim.interfaces.get(device_id=device["id"], name=interface_name)
    if existing:
        return existing

    if dry_run:
        print(f"[DRY-RUN] create interface: {device['name']}:{interface_name}")
        return {"id": -1, "name": interface_name}

    created = nb.dcim.interfaces.create(
        {
            "device": device["id"],
            "name": interface_name,
            "type": "other",
        }
    )
    print(f"Created interface: {device['name']}:{interface_name}")
    return created


def ensure_ip_address(nb: Any, cidr: str, interface_id: int, dry_run: bool) -> Any:
    existing = nb.ipam.ip_addresses.get(address=cidr)
    if existing:
        assigned = existing.assigned_object
        if not assigned or int(assigned.get("id", 0)) != interface_id:
            if dry_run:
                print(f"[DRY-RUN] assign IP {cidr} to interface id {interface_id}")
            else:
                existing.update({"assigned_object_type": "dcim.interface", "assigned_object_id": interface_id})
                print(f"Reassigned IP: {cidr}")
        return existing

    if dry_run:
        print(f"[DRY-RUN] create IP: {cidr}")
        return {"id": -1, "address": cidr}

    created = nb.ipam.ip_addresses.create(
        {
            "address": cidr,
            "assigned_object_type": "dcim.interface",
            "assigned_object_id": interface_id,
            "status": "active",
        }
    )
    print(f"Created IP: {cidr}")
    return created


def main() -> int:
    args = parse_args()

    netbox_url = (args.url or os.environ.get("NETBOX_URL", "")).strip()
    netbox_token = (args.token or os.environ.get("NETBOX_TOKEN", "")).strip()
    verify_ssl = parse_bool(args.verify_ssl or os.environ.get("NETBOX_VERIFY_SSL", ""), default=False)

    if not netbox_url:
        print("NetBox URL is required via --url or NETBOX_URL", file=sys.stderr)
        return 2
    if not netbox_token:
        print("NetBox token is required via --token or NETBOX_TOKEN", file=sys.stderr)
        return 2

    raw_hosts = args.hosts_json or os.environ.get("NETBOX_HOSTS_JSON", "")
    if not raw_hosts.strip():
        print("No hosts provided. Set --hosts-json or NETBOX_HOSTS_JSON", file=sys.stderr)
        return 2

    try:
        hosts = read_hosts(raw_hosts)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        import pynetbox
    except ImportError:
        print("Missing dependency 'pynetbox'. Install it in the running Python environment.", file=sys.stderr)
        return 2

    nb = pynetbox.api(netbox_url, token=netbox_token)
    nb.http_session.verify = verify_ssl

    created_devices = 0
    updated_devices = 0
    unchanged_devices = 0
    ip_changes = 0

    for host in hosts:
        host_name = str(host.get("name", "")).strip()
        if not host_name:
            continue

        site_name = str(host.get("site", "")).strip() or "Homelab"
        role_name = str(host.get("role", "")).strip() or "Server"
        status = str(host.get("status", "active")).strip() or "active"
        manufacturer_name = str(host.get("manufacturer", "Generic")).strip() or "Generic"
        device_type_name = str(host.get("device_type", "Generic Server")).strip() or "Generic Server"
        mgmt_interface_name = str(host.get("mgmt_interface", "mgmt0")).strip() or "mgmt0"
        serial = str(host.get("serial", "")).strip()
        comments = str(host.get("comments", "")).strip()
        tags = host.get("tags", [])
        if not isinstance(tags, list):
            tags = []

        site = ensure_site(nb, site_name, args.dry_run)
        role = ensure_role(nb, role_name, args.dry_run)
        manufacturer = ensure_manufacturer(nb, manufacturer_name, args.dry_run)
        device_type = ensure_device_type(nb, manufacturer, device_type_name, args.dry_run)

        existing_device = nb.dcim.devices.get(name=host_name)
        desired_payload: Dict[str, Any] = {
            "name": host_name,
            "site": site["id"],
            "role": role["id"],
            "device_type": device_type["id"],
            "status": status,
        }

        if serial:
            desired_payload["serial"] = serial
        if comments:
            desired_payload["comments"] = comments
        if tags:
            desired_payload["tags"] = tags

        if existing_device is None:
            if args.dry_run:
                print(f"[DRY-RUN] create device: {host_name}")
                device = {"id": -1, "name": host_name}
            else:
                device = nb.dcim.devices.create(desired_payload)
                print(f"Created device: {host_name}")
            created_devices += 1
        else:
            update_payload: Dict[str, Any] = {}
            comparable_fields = ["site", "role", "device_type", "status", "serial", "comments"]
            for field in comparable_fields:
                desired = desired_payload.get(field, "")
                current = existing_device.get(field)
                if isinstance(current, dict):
                    current = current.get("id")
                if str(current or "") != str(desired or ""):
                    update_payload[field] = desired

            existing_tags = sorted([t.get("name", "") for t in (existing_device.get("tags") or [])])
            desired_tags = sorted([str(t) for t in tags])
            if desired_tags != existing_tags:
                update_payload["tags"] = desired_tags

            if update_payload:
                if args.dry_run:
                    print(f"[DRY-RUN] update device: {host_name}")
                else:
                    existing_device.update(update_payload)
                    print(f"Updated device: {host_name}")
                updated_devices += 1
            else:
                print(f"Unchanged device: {host_name}")
                unchanged_devices += 1
            device = existing_device

        mgmt_ip = str(host.get("mgmt_ip", "")).strip()
        if not mgmt_ip:
            continue

        try:
            mgmt_cidr = ensure_cidr(mgmt_ip)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

        if device["id"] == -1:
            print(f"[DRY-RUN] ensure primary IP for device: {host_name} -> {mgmt_cidr}")
            ip_changes += 1
            continue

        interface = ensure_interface(nb, device, mgmt_interface_name, args.dry_run)
        ip_record = ensure_ip_address(nb, mgmt_cidr, interface["id"], args.dry_run)

        ip_obj = ip_record if isinstance(ip_record, dict) else ip_record.serialize()
        family = ip_obj.get("family")
        if isinstance(family, dict):
            family_value = family.get("value")
        else:
            family_value = family

        if family_value == 6:
            current_primary = (device.get("primary_ip6") or {}).get("id")
            if current_primary != ip_obj.get("id"):
                if args.dry_run:
                    print(f"[DRY-RUN] set primary_ip6 for {host_name} -> {mgmt_cidr}")
                else:
                    device.update({"primary_ip6": ip_obj.get("id")})
                    print(f"Updated primary IP: {host_name} -> {mgmt_cidr}")
                ip_changes += 1
        else:
            current_primary = (device.get("primary_ip4") or {}).get("id")
            if current_primary != ip_obj.get("id"):
                if args.dry_run:
                    print(f"[DRY-RUN] set primary_ip4 for {host_name} -> {mgmt_cidr}")
                else:
                    device.update({"primary_ip4": ip_obj.get("id")})
                    print(f"Updated primary IP: {host_name} -> {mgmt_cidr}")
                ip_changes += 1

    print(
        json.dumps(
            {
                "created_devices": created_devices,
                "updated_devices": updated_devices,
                "unchanged_devices": unchanged_devices,
                "ip_changes": ip_changes,
                "total_hosts": len(hosts),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
