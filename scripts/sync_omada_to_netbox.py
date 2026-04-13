#!/usr/bin/env python3
import argparse
import asyncio
import ipaddress
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Omada devices into NetBox")
    parser.add_argument("--report-only", action="store_true", help="Fetch from Omada and print summary only")
    parser.add_argument("--dry-run", action="store_true", help="Show intended NetBox changes without writing")
    return parser.parse_args()


def parse_bool(value: str, default: bool = False) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def read_json_dict(value: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if default is None:
        default = {}
    if not value.strip():
        return default
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("Expected JSON object")
    return parsed


def read_json_list(value: str, default: Optional[List[Any]] = None) -> List[Any]:
    if default is None:
        default = []
    if not value.strip():
        return default
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("Expected JSON list")
    return parsed


def ensure_cidr(address: str) -> str:
    value = address.strip()
    if not value:
        return ""
    if "/" in value:
        return value

    parsed = ipaddress.ip_address(value)
    if parsed.version == 4:
        return f"{value}/32"
    return f"{value}/128"


def slugify(value: str) -> str:
    out = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")
    return out.lower() or "unknown"


def get_by_name_or_slug(endpoint: Any, value: str) -> Optional[Any]:
    if not value:
        return None

    obj = endpoint.get(name=value)
    if obj is not None:
        return obj

    return endpoint.get(slug=slugify(value))


def read_field(obj: Any, field: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(field, default)

    if hasattr(obj, "serialize"):
        data = obj.serialize()
        if isinstance(data, dict):
            return data.get(field, default)

    value = getattr(obj, field, default)
    if value is None:
        return default
    return value


def ensure_site(nb: Any, site_name: str, dry_run: bool) -> Any:
    existing = get_by_name_or_slug(nb.dcim.sites, site_name)
    if existing:
        return existing

    if dry_run:
        print(f"[DRY-RUN] create site: {site_name}")
        return {"id": -1, "name": site_name, "slug": slugify(site_name)}

    created = nb.dcim.sites.create({"name": site_name, "slug": slugify(site_name), "status": "active"})
    print(f"Created site: {site_name}")
    return created


def ensure_role(nb: Any, role_name: str, dry_run: bool) -> Any:
    existing = get_by_name_or_slug(nb.dcim.device_roles, role_name)
    if existing:
        return existing

    if dry_run:
        print(f"[DRY-RUN] create device role: {role_name}")
        return {"id": -1, "name": role_name, "slug": slugify(role_name)}

    created = nb.dcim.device_roles.create({"name": role_name, "slug": slugify(role_name), "color": "03a9f4"})
    print(f"Created device role: {role_name}")
    return created


def ensure_manufacturer(nb: Any, manufacturer_name: str, dry_run: bool) -> Any:
    existing = get_by_name_or_slug(nb.dcim.manufacturers, manufacturer_name)
    if existing:
        return existing

    if dry_run:
        print(f"[DRY-RUN] create manufacturer: {manufacturer_name}")
        return {"id": -1, "name": manufacturer_name, "slug": slugify(manufacturer_name)}

    created = nb.dcim.manufacturers.create({"name": manufacturer_name, "slug": slugify(manufacturer_name)})
    print(f"Created manufacturer: {manufacturer_name}")
    return created


def ensure_device_type(nb: Any, manufacturer: Any, model_name: str, dry_run: bool) -> Any:
    existing = nb.dcim.device_types.get(model=model_name, manufacturer_id=manufacturer["id"])
    if existing:
        return existing

    if dry_run:
        print(f"[DRY-RUN] create device type: {model_name}")
        return {"id": -1, "model": model_name, "slug": slugify(model_name)}

    created = nb.dcim.device_types.create(
        {
            "manufacturer": manufacturer["id"],
            "model": model_name,
            "slug": slugify(model_name),
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

    created = nb.dcim.interfaces.create({"device": device["id"], "name": interface_name, "type": "other"})
    print(f"Created interface: {device['name']}:{interface_name}")
    return created


def ensure_ip_address(nb: Any, cidr: str, interface_id: int, dry_run: bool) -> Any:
    existing = nb.ipam.ip_addresses.get(address=cidr)
    if existing:
        assigned = read_field(existing, "assigned_object")
        if isinstance(assigned, dict):
            assigned_id = int(assigned.get("id", 0))
        else:
            assigned_id = int(read_field(assigned, "id", 0)) if assigned else 0

        if assigned_id != interface_id:
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


def normalize_device_name(site_name: str, device_name: str, mac: str, include_site: bool) -> str:
    raw_name = (device_name or "").strip()
    if not raw_name:
        raw_name = mac.replace(":", "").lower()

    if include_site:
        return f"{slugify(site_name)}-{slugify(raw_name)}"
    return slugify(raw_name)


def to_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value

    for method_name in ["serialize", "model_dump", "dict"]:
        method = getattr(value, method_name, None)
        if callable(method):
            try:
                data = method()
            except TypeError:
                continue
            if isinstance(data, dict):
                return data

    data = getattr(value, "__dict__", None)
    if isinstance(data, dict):
        nested_data = data.get("_data")
        if isinstance(nested_data, dict):
            return nested_data
        return data

    return {}


def get_first_populated(data: Dict[str, Any], keys: List[str]) -> str:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() not in {"none", "null", "-", "n/a"}:
            return text
    return ""


def normalize_mac(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Fa-f]", "", value)
    if len(cleaned) != 12:
        return ""
    cleaned = cleaned.lower()
    return ":".join(cleaned[i : i + 2] for i in range(0, 12, 2))


def normalize_port_to_interface_name(port_value: str, prefix: str) -> str:
    text = str(port_value).strip()
    if not text:
        return ""

    if text.isdigit():
        return f"{prefix}{text}"

    # Preserve common interface-like names while still handling noisy labels.
    compact = re.sub(r"\s+", "", text)
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_./:+-]*", compact):
        return compact

    digits = re.sub(r"[^0-9]", "", text)
    if digits:
        return f"{prefix}{digits}"

    return ""


def format_link_endpoint(device_name: str, port_name: str) -> str:
    if not device_name:
        return "<unknown-device>"
    if not port_name:
        return device_name
    return f"{device_name}:{port_name}"


def print_link_report(link_audit: List[Dict[str, str]]) -> None:
    if not link_audit:
        print("Omada link audit: no link records")
        return

    headers = ["Local", "Remote", "Action", "Reason"]
    rows: List[List[str]] = []
    for item in link_audit:
        rows.append(
            [
                format_link_endpoint(item.get("local_device", ""), item.get("local_port", "")),
                format_link_endpoint(item.get("remote_device", ""), item.get("remote_port", "")),
                item.get("action", "unknown"),
                item.get("reason", ""),
            ]
        )

    widths = [len(header) for header in headers]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    def format_row(values: List[str]) -> str:
        return " | ".join(value.ljust(widths[index]) for index, value in enumerate(values))

    print("Omada link audit:")
    print(format_row(headers))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(format_row(row))


def extract_link_details(device_obj: Any) -> Dict[str, str]:
    data = to_dict(device_obj)

    uplink_mac = normalize_mac(
        get_first_populated(
            data,
            [
                "uplink_device_mac",
                "uplinkDeviceMac",
                "upstream_device_mac",
                "upstreamDeviceMac",
                "gateway_mac",
                "gatewayMac",
                "connected_device_mac",
                "connectedDeviceMac",
            ],
        )
    )
    local_port = get_first_populated(
        data,
        [
            "uplink_port",
            "uplinkPort",
            "upstream_port",
            "upstreamPort",
            "port",
            "portName",
            "port_name",
        ],
    )
    remote_port = get_first_populated(
        data,
        [
            "uplink_remote_port",
            "uplinkRemotePort",
            "upstream_remote_port",
            "upstreamRemotePort",
            "connected_port",
            "connectedPort",
            "peer_port",
            "peerPort",
        ],
    )

    return {
        "uplink_mac": uplink_mac,
        "local_port": local_port,
        "remote_port": remote_port,
    }


def endpoint_id(value: Any) -> Optional[int]:
    if value is None:
        return None

    if isinstance(value, list):
        for item in value:
            found = endpoint_id(item)
            if found is not None:
                return found
        return None

    if isinstance(value, dict):
        raw = value.get("id")
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    raw = read_field(value, "id")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def get_connected_endpoint_id(interface: Any) -> Optional[int]:
    connected = read_field(interface, "connected_endpoint")
    if connected is None:
        connected = read_field(interface, "connected_endpoints")
    return endpoint_id(connected)


def get_interface_cable_id(interface: Any) -> Optional[int]:
    cable = read_field(interface, "cable")
    return endpoint_id(cable)


def remove_existing_cable(nb: Any, interface: Any, dry_run: bool) -> bool:
    cable_id = get_interface_cable_id(interface)
    if not cable_id:
        return False

    if dry_run:
        print(f"[DRY-RUN] delete cable id {cable_id} from interface id {interface['id']}")
        return True

    cable = nb.dcim.cables.get(cable_id)
    if cable is None:
        return False
    cable.delete()
    print(f"Deleted cable id {cable_id} from interface id {interface['id']}")
    return True


def ensure_interface_link(nb: Any, a_iface: Any, b_iface: Any, dry_run: bool) -> str:
    a_id = int(a_iface["id"])
    b_id = int(b_iface["id"])

    if a_id == b_id:
        return "unchanged"

    a_connected = get_connected_endpoint_id(a_iface)
    b_connected = get_connected_endpoint_id(b_iface)

    if (a_connected == b_id and b_connected == a_id) or a_connected == b_id or b_connected == a_id:
        return "unchanged"

    changed = False
    if a_connected and a_connected != b_id:
        changed = remove_existing_cable(nb, a_iface, dry_run) or changed
        if not dry_run:
            a_iface = nb.dcim.interfaces.get(a_id)

    if b_connected and b_connected != a_id:
        changed = remove_existing_cable(nb, b_iface, dry_run) or changed

    if dry_run:
        print(f"[DRY-RUN] create cable between interface ids {a_id} and {b_id}")
        return "would-update"

    try:
        nb.dcim.cables.create(
            {
                "termination_a_type": "dcim.interface",
                "termination_a_id": a_id,
                "termination_b_type": "dcim.interface",
                "termination_b_id": b_id,
            }
        )
    except Exception as exc:
        # NetBox 4.x uses multi-termination fields instead of termination_a/termination_b.
        try:
            nb.dcim.cables.create(
                {
                    "a_terminations": [{"object_type": "dcim.interface", "object_id": a_id}],
                    "b_terminations": [{"object_type": "dcim.interface", "object_id": b_id}],
                }
            )
        except Exception as second_exc:
            if "Duplicate termination found" in str(second_exc) or "Duplicate termination found" in str(exc):
                return "unchanged"
            raise
    print(f"Created/updated cable between interface ids {a_id} and {b_id}")
    return "updated" if changed else "created"


async def fetch_omada_devices(
    omada_url: str,
    username: str,
    password: str,
    verify_ssl: bool,
    site_filter: List[str],
) -> List[Dict[str, str]]:
    from tplink_omada_client import OmadaClient

    devices: List[Dict[str, str]] = []
    extra_link_hints: Dict[str, Dict[str, str]] = {}

    async with OmadaClient(omada_url, username, password, verify_ssl=verify_ssl) as client:
        await client.login()
        sites = await client.get_sites()

        selected_sites = [s for s in sites if not site_filter or s.name in site_filter]
        for site in selected_sites:
            site_client = await client.get_site_client(site)
            site_devices = await site_client.get_devices()
            for device in site_devices:
                status_category = getattr(device.status_category, "value", str(device.status_category))
                link_details = extract_link_details(device)
                try:
                    if str(device.type) == "switch":
                        switch_detail = await site_client.get_switch(device)
                        switch_uplink = getattr(switch_detail, "uplink", None)
                        if switch_uplink is not None:
                            link_details["uplink_mac"] = normalize_mac(str(getattr(switch_uplink, "mac", "")))
                            link_details["local_port"] = str(getattr(switch_uplink, "port", ""))

                        # Downlink entries provide the switch-side port for attached devices.
                        for downlink in getattr(switch_detail, "downlink", []):
                            downlink_mac = normalize_mac(str(getattr(downlink, "mac", "")))
                            if not downlink_mac:
                                continue
                            extra_link_hints[downlink_mac] = {
                                "uplink_mac": normalize_mac(str(getattr(device, "mac", ""))),
                                "remote_port": str(getattr(downlink, "port", "")),
                            }
                    elif str(device.type) == "ap":
                        ap_detail = await site_client.get_access_point(device)
                        ap_uplink = getattr(ap_detail, "wired_uplink", None)
                        if ap_uplink is not None:
                            ap_uplink_data = to_dict(ap_uplink)
                            link_details["uplink_mac"] = normalize_mac(str(getattr(ap_uplink, "mac", "")))
                            # Omada exposes switch-side uplink port for APs.
                            link_details["remote_port"] = str(
                                ap_uplink_data.get("port", "") or ap_uplink_data.get("uplinkPort", "")
                            )
                    elif str(device.type) == "gateway":
                        gateway_detail = await site_client.get_gateway(device)
                        connected_lan_ports: List[str] = []
                        for port_status in getattr(gateway_detail, "port_status", []):
                            port_data = to_dict(port_status)
                            try:
                                is_lan_mode = int(port_data.get("mode", -1)) == 1
                                is_connected = int(port_data.get("status", 0)) == 1
                            except (TypeError, ValueError):
                                is_lan_mode = False
                                is_connected = False

                            if is_lan_mode and is_connected:
                                connected_lan_ports.append(str(port_data.get("port", "")))

                        # If exactly one LAN-side port is up, use it as the gateway cable endpoint.
                        if len(connected_lan_ports) == 1:
                            link_details["local_port"] = connected_lan_ports[0]
                except Exception:
                    # Keep device/IP sync resilient if detailed link data fetch fails for a device.
                    pass

                device_mac = normalize_mac(str(device.mac))
                extra_hint = extra_link_hints.get(device_mac, {})
                if extra_hint.get("uplink_mac") and not link_details.get("uplink_mac"):
                    link_details["uplink_mac"] = extra_hint["uplink_mac"]
                if extra_hint.get("remote_port") and not link_details.get("remote_port"):
                    link_details["remote_port"] = extra_hint["remote_port"]

                devices.append(
                    {
                        "site": site.name,
                        "omada_type": str(device.type),
                        "name": str(device.name),
                        "model": str(device.model),
                        "mac": str(device.mac),
                        "ip": str(device.ip_address),
                        "status": str(status_category),
                        "uplink_mac": link_details["uplink_mac"],
                        "local_port": link_details["local_port"],
                        "remote_port": link_details["remote_port"],
                    }
                )

    for item in devices:
        device_mac = normalize_mac(str(item.get("mac", "")))
        if not device_mac:
            continue
        extra_hint = extra_link_hints.get(device_mac, {})
        if extra_hint.get("uplink_mac") and not str(item.get("uplink_mac", "")).strip():
            item["uplink_mac"] = extra_hint["uplink_mac"]
        if extra_hint.get("remote_port") and not str(item.get("remote_port", "")).strip():
            item["remote_port"] = extra_hint["remote_port"]

    return devices


def main() -> int:
    args = parse_args()

    omada_url = os.environ.get("OMADA_URL", "").strip()
    omada_username = os.environ.get("OMADA_USERNAME", "").strip()
    omada_password = os.environ.get("OMADA_PASSWORD", "").strip()
    omada_verify_ssl = parse_bool(os.environ.get("OMADA_VERIFY_SSL", ""), default=False)

    netbox_url = os.environ.get("NETBOX_URL", "").strip()
    netbox_token = os.environ.get("NETBOX_TOKEN", "").strip()
    netbox_verify_ssl = parse_bool(os.environ.get("NETBOX_VERIFY_SSL", ""), default=False)

    default_status = os.environ.get("OMADA_DEFAULT_STATUS", "active").strip() or "active"
    default_manufacturer = os.environ.get("OMADA_DEFAULT_MANUFACTURER", "TP-Link").strip() or "TP-Link"
    mgmt_interface = os.environ.get("OMADA_MGMT_INTERFACE", "mgmt0").strip() or "mgmt0"
    port_interface_prefix = os.environ.get("OMADA_PORT_INTERFACE_PREFIX", "port").strip() or "port"
    include_site_in_name = parse_bool(os.environ.get("OMADA_INCLUDE_SITE_IN_NAME", ""), default=True)
    link_report = parse_bool(os.environ.get("OMADA_LINK_REPORT", ""), default=False)

    try:
        site_filter = [str(s) for s in read_json_list(os.environ.get("OMADA_SITE_FILTER_JSON", "[]"), default=[])]
        site_map = read_json_dict(os.environ.get("OMADA_SITE_MAP_JSON", "{}"), default={})
        role_map = read_json_dict(
            os.environ.get("OMADA_ROLE_MAP_JSON", "{}"),
            default={"ap": "Wireless AP", "switch": "Switch", "gateway": "Router"},
        )
    except ValueError as exc:
        print(f"Invalid mapping/filter JSON: {exc}", file=sys.stderr)
        return 2

    if not omada_url or not omada_username or not omada_password:
        print("OMADA_URL/OMADA_USERNAME/OMADA_PASSWORD are required.", file=sys.stderr)
        return 2

    if not netbox_url or not netbox_token:
        print("NETBOX_URL/NETBOX_TOKEN are required.", file=sys.stderr)
        return 2

    try:
        omada_devices = asyncio.run(
            fetch_omada_devices(
                omada_url=omada_url,
                username=omada_username,
                password=omada_password,
                verify_ssl=omada_verify_ssl,
                site_filter=site_filter,
            )
        )
    except Exception as exc:
        print(f"Failed to fetch Omada data: {exc}", file=sys.stderr)
        return 2

    if args.report_only:
        print(
            json.dumps(
                {
                    "total_omada_devices": len(omada_devices),
                    "site_filter": site_filter,
                    "sample": omada_devices[:10],
                }
            )
        )
        return 0

    try:
        import pynetbox
    except ImportError:
        print("Missing dependency 'pynetbox'.", file=sys.stderr)
        return 2

    nb = pynetbox.api(netbox_url, token=netbox_token)
    nb.http_session.verify = netbox_verify_ssl

    created_devices = 0
    updated_devices = 0
    unchanged_devices = 0
    ip_changes = 0
    skipped_no_ip = 0
    link_changes = 0
    link_candidates = 0
    device_by_mac: Dict[str, Any] = {}
    link_hints: Dict[str, Dict[str, str]] = {}
    link_audit: List[Dict[str, str]] = []

    for item in omada_devices:
        omada_site = item.get("site", "")
        netbox_site_name = str(site_map.get(omada_site, omada_site)).strip() or omada_site
        omada_type = str(item.get("omada_type", "")).strip().lower()
        role_name = str(role_map.get(omada_type, "Network Device")).strip() or "Network Device"

        site = ensure_site(nb, netbox_site_name, args.dry_run)
        role = ensure_role(nb, role_name, args.dry_run)
        manufacturer = ensure_manufacturer(nb, default_manufacturer, args.dry_run)

        model = str(item.get("model", "")).strip() or "Unknown Model"
        device_type = ensure_device_type(nb, manufacturer, model, args.dry_run)

        mac = str(item.get("mac", "")).strip().lower()
        mac = normalize_mac(mac) or mac
        serial = mac.replace(":", "") if mac else ""
        device_name = normalize_device_name(
            site_name=omada_site,
            device_name=str(item.get("name", "")).strip(),
            mac=mac,
            include_site=include_site_in_name,
        )

        existing_device = nb.dcim.devices.get(serial=serial) if serial else None
        if existing_device is None:
            existing_device = nb.dcim.devices.get(name=device_name)

        desired_payload: Dict[str, Any] = {
            "name": device_name,
            "site": site["id"],
            "role": role["id"],
            "device_type": device_type["id"],
            "status": default_status,
        }
        if serial:
            desired_payload["serial"] = serial

        if existing_device is None:
            if args.dry_run:
                print(f"[DRY-RUN] create device: {device_name}")
                device = {"id": -1, "name": device_name}
            else:
                device = nb.dcim.devices.create(desired_payload)
                print(f"Created device: {device_name}")
            created_devices += 1
        else:
            update_payload: Dict[str, Any] = {}
            for field in ["name", "site", "role", "device_type", "status", "serial"]:
                desired = desired_payload.get(field, "")
                current = read_field(existing_device, field)
                if isinstance(current, dict):
                    current = current.get("id")
                if str(current or "") != str(desired or ""):
                    update_payload[field] = desired

            if update_payload:
                if args.dry_run:
                    print(f"[DRY-RUN] update device: {device_name}")
                else:
                    existing_device.update(update_payload)
                    print(f"Updated device: {device_name}")
                updated_devices += 1
            else:
                print(f"Unchanged device: {device_name}")
                unchanged_devices += 1
            device = existing_device

        ip_value = str(item.get("ip", "")).strip()
        if mac:
            device_by_mac[mac] = device

        link_hints[mac] = {
            "uplink_mac": normalize_mac(str(item.get("uplink_mac", "")).strip()),
            "local_port": str(item.get("local_port", "")).strip(),
            "remote_port": str(item.get("remote_port", "")).strip(),
        }
        if not link_hints[mac]["local_port"] and str(item.get("omada_type", "")).strip().lower() == "ap":
            # AP uplink endpoint is not always exposed; use configured management interface as AP-side cable endpoint.
            link_hints[mac]["local_port"] = mgmt_interface

        if not ip_value:
            skipped_no_ip += 1
            continue

        try:
            mgmt_cidr = ensure_cidr(ip_value)
        except ValueError:
            skipped_no_ip += 1
            continue

        if device["id"] == -1:
            print(f"[DRY-RUN] ensure primary IP for device: {device_name} -> {mgmt_cidr}")
            ip_changes += 1
            continue

        interface = ensure_interface(nb, device, mgmt_interface, args.dry_run)
        ip_record = ensure_ip_address(nb, mgmt_cidr, interface["id"], args.dry_run)

        ip_obj = ip_record if isinstance(ip_record, dict) else ip_record.serialize()
        family = ip_obj.get("family")
        family_value = family.get("value") if isinstance(family, dict) else family

        if family_value == 6:
            current_primary_obj = read_field(device, "primary_ip6") or {}
            current_primary = current_primary_obj.get("id") if isinstance(current_primary_obj, dict) else None
            if current_primary != ip_obj.get("id"):
                if args.dry_run:
                    print(f"[DRY-RUN] set primary_ip6 for {device_name} -> {mgmt_cidr}")
                else:
                    device.update({"primary_ip6": ip_obj.get("id")})
                    print(f"Updated primary IP: {device_name} -> {mgmt_cidr}")
                ip_changes += 1
        else:
            current_primary_obj = read_field(device, "primary_ip4") or {}
            current_primary = current_primary_obj.get("id") if isinstance(current_primary_obj, dict) else None
            if current_primary != ip_obj.get("id"):
                if args.dry_run:
                    print(f"[DRY-RUN] set primary_ip4 for {device_name} -> {mgmt_cidr}")
                else:
                    device.update({"primary_ip4": ip_obj.get("id")})
                    print(f"Updated primary IP: {device_name} -> {mgmt_cidr}")
                ip_changes += 1

    processed_pairs: Set[Tuple[str, str]] = set()
    for mac, hint in link_hints.items():
        uplink_mac = hint.get("uplink_mac", "")
        local_device = device_by_mac.get(mac)
        remote_device = device_by_mac.get(uplink_mac)
        local_device_name = str(read_field(local_device, "name", "") or "") if local_device is not None else ""
        remote_device_name = str(read_field(remote_device, "name", "") or "") if remote_device is not None else ""
        local_port_name = normalize_port_to_interface_name(hint.get("local_port", ""), port_interface_prefix)
        remote_hint = link_hints.get(uplink_mac, {})
        remote_port_value = hint.get("remote_port", "") or remote_hint.get("local_port", "")
        remote_port_name = normalize_port_to_interface_name(remote_port_value, port_interface_prefix)

        if not mac or not uplink_mac:
            if link_report and local_device_name:
                link_audit.append(
                    {
                        "local_device": local_device_name,
                        "local_port": local_port_name,
                        "remote_device": remote_device_name,
                        "remote_port": remote_port_name,
                        "action": "skipped",
                        "reason": "missing_uplink_metadata",
                    }
                )
            continue

        left = min(mac, uplink_mac)
        right = max(mac, uplink_mac)
        pair = (left, right)
        if pair in processed_pairs:
            continue
        processed_pairs.add(pair)

        if local_device is None or remote_device is None:
            if link_report:
                link_audit.append(
                    {
                        "local_device": local_device_name,
                        "local_port": local_port_name,
                        "remote_device": remote_device_name,
                        "remote_port": remote_port_name,
                        "action": "skipped",
                        "reason": "peer_device_missing_in_netbox_sync_scope",
                    }
                )
            continue

        if not local_port_name or not remote_port_name:
            if link_report:
                link_audit.append(
                    {
                        "local_device": local_device_name,
                        "local_port": local_port_name,
                        "remote_device": remote_device_name,
                        "remote_port": remote_port_name,
                        "action": "skipped",
                        "reason": "missing_port_metadata",
                    }
                )
            continue

        link_candidates += 1

        if int(read_field(local_device, "id", 0) or 0) == -1 or int(read_field(remote_device, "id", 0) or 0) == -1:
            print(
                f"[DRY-RUN] ensure cable: {local_device['name']}:{local_port_name} <-> "
                f"{remote_device['name']}:{remote_port_name}"
            )
            link_changes += 1
            if link_report:
                link_audit.append(
                    {
                        "local_device": local_device_name,
                        "local_port": local_port_name,
                        "remote_device": remote_device_name,
                        "remote_port": remote_port_name,
                        "action": "would-update",
                        "reason": "device_pending_creation",
                    }
                )
            continue

        local_iface = ensure_interface(nb, local_device, local_port_name, args.dry_run)
        remote_iface = ensure_interface(nb, remote_device, remote_port_name, args.dry_run)
        link_result = ensure_interface_link(nb, local_iface, remote_iface, args.dry_run)
        if link_result in {"created", "updated", "would-update"}:
            link_changes += 1
        if link_report:
            link_audit.append(
                {
                    "local_device": local_device_name,
                    "local_port": local_port_name,
                    "remote_device": remote_device_name,
                    "remote_port": remote_port_name,
                    "action": link_result,
                    "reason": "",
                }
            )

    if link_report:
        print_link_report(link_audit)

    print(
        json.dumps(
            {
                "total_omada_devices": len(omada_devices),
                "created_devices": created_devices,
                "updated_devices": updated_devices,
                "unchanged_devices": unchanged_devices,
                "ip_changes": ip_changes,
                "skipped_no_ip": skipped_no_ip,
                "link_candidates": link_candidates,
                "link_changes": link_changes,
            }
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
