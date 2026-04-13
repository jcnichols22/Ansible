#!/usr/bin/env python3
import argparse
import json
import os
import sys
from typing import Any, Dict, List


SUPPORTED_TYPES = {"http", "ping", "port", "dns"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync monitors into Uptime Kuma")
    parser.add_argument("--server", default="", help="Uptime Kuma URL, e.g. http://kuma:3001")
    parser.add_argument("--username", default="", help="Uptime Kuma username")
    parser.add_argument("--password", default="", help="Uptime Kuma password")
    parser.add_argument("--api-key", default="", help="Uptime Kuma API key")
    parser.add_argument(
        "--services-json",
        default=None,
        help="JSON list of service monitor definitions (or use KUMA_SERVICES_JSON env var)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show intended changes without writing")
    return parser.parse_args()


def read_services(raw: str) -> List[Dict[str, Any]]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON for services: {exc}") from exc

    if not isinstance(parsed, list):
        raise ValueError("services JSON must be a list")

    for idx, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise ValueError(f"services[{idx}] must be an object")
        if "name" not in item:
            raise ValueError(f"services[{idx}] is missing required key 'name'")

    return parsed


def normalize_monitor(service: Dict[str, Any]) -> Dict[str, Any]:
    monitor_type = str(service.get("type", "http")).strip().lower()
    if monitor_type not in SUPPORTED_TYPES:
        raise ValueError(
            f"Unsupported monitor type '{monitor_type}' for '{service.get('name')}'. "
            f"Supported types: {', '.join(sorted(SUPPORTED_TYPES))}"
        )

    name = str(service["name"]).strip()
    if not name:
        raise ValueError("Monitor name cannot be empty")

    payload: Dict[str, Any] = {
        "type": monitor_type,
        "name": name,
        "interval": int(service.get("interval", 60)),
        "maxretries": int(service.get("maxretries", 3)),
        "retryInterval": int(service.get("retryInterval", 60)),
    }

    if monitor_type == "http":
        url = service.get("url")
        if not url:
            raise ValueError(f"HTTP monitor '{name}' requires 'url'")
        payload["url"] = str(url)

        if "method" in service:
            payload["method"] = str(service["method"])
        if "ignoreTls" in service:
            payload["ignoreTls"] = bool(service["ignoreTls"])

    elif monitor_type in {"ping", "port", "dns"}:
        hostname = service.get("hostname")
        if not hostname:
            raise ValueError(f"{monitor_type} monitor '{name}' requires 'hostname'")
        payload["hostname"] = str(hostname)

        if monitor_type == "port":
            port = service.get("port")
            if port is None:
                raise ValueError(f"Port monitor '{name}' requires 'port'")
            payload["port"] = int(port)

    if "description" in service:
        payload["description"] = str(service["description"])
    if "upsideDown" in service:
        payload["upsideDown"] = bool(service["upsideDown"])

    return payload


def add_monitor_with_fallback(api: Any, monitor: Dict[str, Any], kuma_exc_cls: Any) -> None:
    try:
        api.add_monitor(**monitor)
        return
    except kuma_exc_cls as exc:
        message = str(exc)
        if "NOT NULL constraint failed: monitor.conditions" not in message:
            raise

    payload = api._build_monitor_data(**monitor)
    if payload.get("conditions") is None:
        payload["conditions"] = []
    api._call("add", payload)


def main() -> int:
    args = parse_args()

    server = (args.server or os.environ.get("KUMA_SERVER", "")).strip()
    if not server:
        print("Uptime Kuma server URL is required via --server or KUMA_SERVER.", file=sys.stderr)
        return 2

    raw_services = args.services_json or os.environ.get("KUMA_SERVICES_JSON", "")
    if not raw_services.strip():
        print("No services provided. Set --services-json or KUMA_SERVICES_JSON.", file=sys.stderr)
        return 2

    try:
        services = read_services(raw_services)
        desired_monitors = [normalize_monitor(service) for service in services]
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        from uptime_kuma_api import UptimeKumaApi
        from uptime_kuma_api.exceptions import UptimeKumaException
    except ImportError:
        print("Missing dependency 'uptime-kuma-api'. Install it in the running Python environment.", file=sys.stderr)
        return 2

    api = UptimeKumaApi(server)

    api_key = (args.api_key or os.environ.get("KUMA_API_KEY", "")).strip()
    username = (args.username or os.environ.get("KUMA_USERNAME", "")).strip()
    password = (args.password or os.environ.get("KUMA_PASSWORD", "")).strip()

    logged_in = False

    if api_key and hasattr(api, "login_by_token"):
        try:
            api.login_by_token(api_key)
            logged_in = True
        except UptimeKumaException as exc:
            if "authInvalidToken" not in str(exc):
                raise

    if not logged_in and username and password:
        api.login(username, password)
        logged_in = True

    if not logged_in:
        try:
            api.login(None, None)
            logged_in = True
        except Exception:
            logged_in = False

    if not logged_in:
        print(
            "Authentication failed. Use kuma_username/kuma_password (or disable auth in Kuma). "
            "Note: a uk1_ API key is not accepted by this client's loginByToken flow.",
            file=sys.stderr,
        )
        return 2

    existing_monitors = api.get_monitors()
    existing_by_name = {}
    for monitor in existing_monitors:
        monitor_name = str(monitor.get("name", "")).strip()
        if monitor_name:
            existing_by_name[monitor_name] = monitor

    created = 0
    updated = 0
    unchanged = 0

    for monitor in desired_monitors:
        existing = existing_by_name.get(monitor["name"])

        if existing is None:
            if args.dry_run:
                print(f"[DRY-RUN] create monitor: {monitor['name']}")
            else:
                add_monitor_with_fallback(api, monitor, UptimeKumaException)
                print(f"Created monitor: {monitor['name']}")
            created += 1
            continue

        monitor_id = int(existing["id"])
        needs_update = False
        for key, desired_value in monitor.items():
            if key == "name":
                continue

            current_value = existing.get(key)
            if isinstance(desired_value, bool):
                current_norm = bool(current_value)
                if current_norm != desired_value:
                    needs_update = True
                    break
            else:
                if str(current_value) != str(desired_value):
                    needs_update = True
                    break

        if not needs_update:
            print(f"Unchanged monitor: {monitor['name']}")
            unchanged += 1
            continue

        if args.dry_run:
            print(f"[DRY-RUN] update monitor: {monitor['name']}")
        else:
            api.edit_monitor(monitor_id, **monitor)
            print(f"Updated monitor: {monitor['name']}")
        updated += 1

    print(
        json.dumps(
            {
                "created": created,
                "updated": updated,
                "unchanged": unchanged,
                "total_desired": len(desired_monitors),
            }
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
