#!/usr/bin/env python3
import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional


try:
    import requests
except ImportError:
    print("Missing dependency 'requests'. Install it in the running Python environment.", file=sys.stderr)
    raise SystemExit(2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Docker-discovered service hosts into NPM and AdGuard Home")
    parser.add_argument("--service-hosts-json", default=None, help="Desired service host definitions")
    parser.add_argument("--npm-url", default=None, help="Nginx Proxy Manager base URL")
    parser.add_argument("--npm-username", default=None, help="NPM username")
    parser.add_argument("--npm-password", default=None, help="NPM password")
    parser.add_argument("--adguard-url", default=None, help="AdGuard Home base URL")
    parser.add_argument("--adguard-username", default=None, help="AdGuard username")
    parser.add_argument("--adguard-password", default=None, help="AdGuard password")
    parser.add_argument("--dry-run", action="store_true", help="Show intended changes without writing")
    return parser.parse_args()


def require_value(value: str, label: str) -> str:
    if not value.strip():
        raise ValueError(f"{label} is required")
    return value.strip()


def load_json_list(raw: str, label: str) -> List[Dict[str, Any]]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON for {label}: {exc}") from exc

    if not isinstance(parsed, list):
        raise ValueError(f"{label} must be a JSON list")

    for index, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise ValueError(f"{label}[{index}] must be an object")

    return parsed


def normalize_service(service: Dict[str, Any]) -> Dict[str, Any]:
    name = require_value(str(service.get("name", "")), "service name")
    domain = require_value(str(service.get("domain", "")), f"domain for {name}")
    backend_host = require_value(str(service.get("backend_host", "")), f"backend_host for {name}")
    backend_scheme = require_value(str(service.get("backend_scheme", "http")), f"backend_scheme for {name}").lower()
    if backend_scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported backend_scheme '{backend_scheme}' for {name}")

    try:
        backend_port = int(service.get("backend_port"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"backend_port for {name} must be an integer") from exc

    rewrite_target = require_value(str(service.get("rewrite_target", "")), f"rewrite_target for {name}")

    return {
        "name": name,
        "domain": domain.lower(),
        "backend_host": backend_host,
        "backend_scheme": backend_scheme,
        "backend_port": backend_port,
        "rewrite_target": rewrite_target,
    }


class NpmClient:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        token = self._get_token(username, password)
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def _get_token(self, username: str, password: str) -> str:
        response = self.session.post(
            f"{self.base_url}/api/tokens",
            json={"identity": username, "secret": password},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if "token" not in payload:
            raise ValueError("NPM token response did not include a token")
        return str(payload["token"])

    def list_proxy_hosts(self) -> List[Dict[str, Any]]:
        response = self.session.get(f"{self.base_url}/api/nginx/proxy-hosts", timeout=30)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Unexpected proxy host response from NPM")
        return payload

    def create_proxy_host(self, domain: str, backend_scheme: str, backend_host: str, backend_port: int) -> None:
        payload = {
            "domain_names": [domain],
            "forward_scheme": backend_scheme,
            "forward_host": backend_host,
            "forward_port": backend_port,
            "access_list_id": 0,
            "certificate_id": 0,
            "ssl_forced": False,
            "hsts_enabled": False,
            "hsts_subdomains": False,
            "http2_support": False,
            "block_exploits": False,
            "caching_enabled": False,
            "allow_websocket_upgrade": True,
            "advanced_config": "",
            "enabled": True,
            "locations": [],
        }
        response = self.session.post(f"{self.base_url}/api/nginx/proxy-hosts", json=payload, timeout=30)
        response.raise_for_status()

    def update_proxy_host(self, host_id: int, payload: Dict[str, Any]) -> None:
        response = self.session.put(f"{self.base_url}/api/nginx/proxy-hosts/{host_id}", json=payload, timeout=30)
        response.raise_for_status()


class AdGuardClient:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.auth = (username, password)
        self.session.headers.update({"Accept": "application/json"})

    def list_rewrites(self) -> List[Dict[str, Any]]:
        response = self.session.get(f"{self.base_url}/control/rewrite/list", timeout=30)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Unexpected rewrite response from AdGuard Home")
        return payload

    def add_rewrite(self, domain: str, answer: str) -> None:
        response = self.session.post(
            f"{self.base_url}/control/rewrite/add",
            json={"domain": domain, "answer": answer},
            timeout=30,
        )
        response.raise_for_status()

    def update_rewrite(self, target: Dict[str, Any], update: Dict[str, Any]) -> None:
        response = self.session.put(
            f"{self.base_url}/control/rewrite/update",
            json={"target": target, "update": update},
            timeout=30,
        )
        response.raise_for_status()


def find_matching_proxy_host(existing_hosts: List[Dict[str, Any]], domain: str) -> Optional[Dict[str, Any]]:
    domain_lower = domain.lower()
    for host in existing_hosts:
        for current_domain in host.get("domain_names", []):
            if str(current_domain).lower() == domain_lower:
                return host
    return None


def find_matching_rewrite(existing_rewrites: List[Dict[str, Any]], domain: str) -> Optional[Dict[str, Any]]:
    domain_lower = domain.lower()
    for rewrite in existing_rewrites:
        if str(rewrite.get("domain", "")).lower() == domain_lower:
            return rewrite
    return None


def main() -> int:
    args = parse_args()

    raw_services = args.service_hosts_json or os.environ.get("SERVICE_HOSTS_JSON", "")
    npm_url = args.npm_url or os.environ.get("NPM_URL", "")
    npm_username = args.npm_username or os.environ.get("NPM_USERNAME", "")
    npm_password = args.npm_password or os.environ.get("NPM_PASSWORD", "")
    adguard_url = args.adguard_url or os.environ.get("ADGUARD_URL", "")
    adguard_username = args.adguard_username or os.environ.get("ADGUARD_USERNAME", "")
    adguard_password = args.adguard_password or os.environ.get("ADGUARD_PASSWORD", "")

    try:
        require_value(raw_services, "SERVICE_HOSTS_JSON")
        services = [normalize_service(item) for item in load_json_list(raw_services, "SERVICE_HOSTS_JSON")]
        npm_url = require_value(npm_url, "NPM_URL")
        npm_username = require_value(npm_username, "NPM_USERNAME")
        npm_password = require_value(npm_password, "NPM_PASSWORD")
        adguard_url = require_value(adguard_url, "ADGUARD_URL")
        adguard_username = require_value(adguard_username, "ADGUARD_USERNAME")
        adguard_password = require_value(adguard_password, "ADGUARD_PASSWORD")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    npm_client = NpmClient(npm_url, npm_username, npm_password)
    adguard_client = AdGuardClient(adguard_url, adguard_username, adguard_password)

    existing_proxy_hosts = npm_client.list_proxy_hosts()
    existing_rewrites = adguard_client.list_rewrites()

    created_proxy_hosts = 0
    updated_proxy_hosts = 0
    unchanged_proxy_hosts = 0
    created_rewrites = 0
    updated_rewrites = 0
    unchanged_rewrites = 0

    for service in services:
        existing_host = find_matching_proxy_host(existing_proxy_hosts, service["domain"])
        if existing_host is None:
            if args.dry_run:
                print(f"[DRY-RUN] create proxy host: {service['domain']}")
            else:
                npm_client.create_proxy_host(
                    domain=service["domain"],
                    backend_scheme=service["backend_scheme"],
                    backend_host=service["backend_host"],
                    backend_port=service["backend_port"],
                )
                print(f"Created proxy host: {service['domain']}")
            created_proxy_hosts += 1
        else:
            desired = {
                "forward_scheme": service["backend_scheme"],
                "forward_host": service["backend_host"],
                "forward_port": service["backend_port"],
                "enabled": True,
            }
            needs_update = any(str(existing_host.get(key)) != str(value) for key, value in desired.items())
            if needs_update:
                if args.dry_run:
                    print(f"[DRY-RUN] update proxy host: {service['domain']}")
                else:
                    npm_client.update_proxy_host(int(existing_host["id"]), desired)
                    print(f"Updated proxy host: {service['domain']}")
                updated_proxy_hosts += 1
            else:
                print(f"Unchanged proxy host: {service['domain']}")
                unchanged_proxy_hosts += 1

        existing_rewrite = find_matching_rewrite(existing_rewrites, service["domain"])
        desired_rewrite = {"domain": service["domain"], "answer": service["rewrite_target"], "enabled": True}
        if existing_rewrite is None:
            if args.dry_run:
                print(f"[DRY-RUN] create rewrite: {service['domain']} -> {service['rewrite_target']}")
            else:
                adguard_client.add_rewrite(service["domain"], service["rewrite_target"])
                print(f"Created rewrite: {service['domain']} -> {service['rewrite_target']}")
            created_rewrites += 1
        else:
            existing_answer = str(existing_rewrite.get("answer", ""))
            existing_enabled = bool(existing_rewrite.get("enabled", True))
            needs_update = existing_answer != service["rewrite_target"] or not existing_enabled
            if needs_update:
                if args.dry_run:
                    print(f"[DRY-RUN] update rewrite: {service['domain']} -> {service['rewrite_target']}")
                else:
                    adguard_client.update_rewrite(existing_rewrite, desired_rewrite)
                    print(f"Updated rewrite: {service['domain']} -> {service['rewrite_target']}")
                updated_rewrites += 1
            else:
                print(f"Unchanged rewrite: {service['domain']}")
                unchanged_rewrites += 1

    print(
        json.dumps(
            {
                "proxy_hosts": {
                    "created": created_proxy_hosts,
                    "updated": updated_proxy_hosts,
                    "unchanged": unchanged_proxy_hosts,
                },
                "rewrites": {
                    "created": created_rewrites,
                    "updated": updated_rewrites,
                    "unchanged": unchanged_rewrites,
                },
                "total_desired": len(services),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())