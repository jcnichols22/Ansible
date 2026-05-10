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
    parser = argparse.ArgumentParser(description="Sync SSH connections into Apache Guacamole")
    parser.add_argument("--connections-json", default=None, help="Desired Guacamole connection definitions")
    parser.add_argument("--guacamole-url", default=None, help="Apache Guacamole base URL")
    parser.add_argument("--guacamole-username", default=None, help="Guacamole username")
    parser.add_argument("--guacamole-password", default=None, help="Guacamole password")
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


def normalize_connection(connection: Dict[str, Any]) -> Dict[str, Any]:
    name = require_value(str(connection.get("name", "")), "connection name")
    hostname = require_value(str(connection.get("hostname", "")), f"hostname for {name}")
    username = require_value(str(connection.get("username", "")), f"username for {name}")

    try:
        port = int(connection.get("port", 22))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"port for {name} must be an integer") from exc

    parent_identifier = require_value(str(connection.get("parent_identifier", "ROOT")), f"parent_identifier for {name}")
    raw_attributes = connection.get("attributes", {})
    if not isinstance(raw_attributes, dict):
        raise ValueError(f"attributes for {name} must be an object")
    private_key = str(connection.get("private_key", "")).strip()
    private_key_passphrase = str(connection.get("private_key_passphrase", "")).strip()
    color_scheme = str(connection.get("color_scheme", "")).strip()

    parameters: Dict[str, str] = {
        "hostname": hostname,
        "port": str(port),
        "username": username,
    }

    if private_key:
        parameters["private-key"] = private_key
    if private_key_passphrase:
        parameters["private-key-passphrase"] = private_key_passphrase
    if color_scheme:
        parameters["color-scheme"] = color_scheme

    return {
        "name": name,
        "parentIdentifier": parent_identifier,
        "protocol": "ssh",
        "parameters": parameters,
        "attributes": raw_attributes,
    }


class GuacamoleClient:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        auth_response = self.session.post(
            f"{self.base_url}/api/tokens",
            data={"username": username, "password": password},
            timeout=30,
        )
        auth_response.raise_for_status()
        payload = auth_response.json()
        if not isinstance(payload, dict):
            raise ValueError("Unexpected authentication response from Guacamole")
        if "authToken" not in payload or "dataSource" not in payload:
            raise ValueError("Guacamole authentication response did not include authToken and dataSource")
        self.auth_token = str(payload["authToken"])
        self.data_source = str(payload["dataSource"])

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        params = dict(kwargs.pop("params", {}))
        params["token"] = self.auth_token
        response = self.session.request(
            method,
            f"{self.base_url}{path}",
            params=params,
            timeout=30,
            **kwargs,
        )
        response.raise_for_status()
        return response

    def list_connections(self) -> List[Dict[str, Any]]:
        response = self._request("GET", f"/api/session/data/{self.data_source}/connections")
        payload = response.json()
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            values = list(payload.values())
            if values and all(isinstance(item, dict) for item in values):
                return values
        raise ValueError("Unexpected connection list response from Guacamole")

    def create_connection(self, connection: Dict[str, Any]) -> None:
        self._request(
            "POST",
            f"/api/session/data/{self.data_source}/connections",
            json=connection,
        )

    def get_connection_parameters(self, identifier: str) -> Dict[str, str]:
        response = self._request("GET", f"/api/session/data/{self.data_source}/connections/{identifier}/parameters")
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def update_connection(self, identifier: str, connection: Dict[str, Any]) -> None:
        self._request(
            "PUT",
            f"/api/session/data/{self.data_source}/connections/{identifier}",
            json=connection,
        )


def find_matching_connection(existing_connections: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    name_lower = name.lower()
    for connection in existing_connections:
        if str(connection.get("name", "")).lower() == name_lower:
            return connection
    return None


def main() -> int:
    args = parse_args()

    raw_connections = args.connections_json or os.environ.get("GUACAMOLE_CONNECTIONS_JSON", "")
    guacamole_url = args.guacamole_url or os.environ.get("GUACAMOLE_URL", "")
    guacamole_username = args.guacamole_username or os.environ.get("GUACAMOLE_USERNAME", "")
    guacamole_password = args.guacamole_password or os.environ.get("GUACAMOLE_PASSWORD", "")
    desired_color_scheme = os.environ.get("GUACAMOLE_COLOR_SCHEME", "").strip()

    try:
        require_value(raw_connections, "GUACAMOLE_CONNECTIONS_JSON")
        connections = [normalize_connection(item) for item in load_json_list(raw_connections, "GUACAMOLE_CONNECTIONS_JSON")]
        guacamole_url = require_value(guacamole_url, "GUACAMOLE_URL")
        guacamole_username = require_value(guacamole_username, "GUACAMOLE_USERNAME")
        guacamole_password = require_value(guacamole_password, "GUACAMOLE_PASSWORD")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    client = GuacamoleClient(guacamole_url, guacamole_username, guacamole_password)
    existing_connections = client.list_connections()

    created_connections = 0
    skipped_connections = 0

    for connection in connections:
        existing_connection = find_matching_connection(existing_connections, connection["name"])
        if existing_connection is not None:
            print(f"Skipped connection (already exists): {connection['name']}")
            skipped_connections += 1
            continue

        if args.dry_run:
            print(f"[DRY-RUN] create connection: {connection['name']}")
        else:
            client.create_connection(connection)
            print(f"Created connection: {connection['name']}")
        created_connections += 1

    # Re-fetch connections so newly created ones are included in the color scheme pass
    color_scheme_updated = 0
    if desired_color_scheme:
        all_connections = client.list_connections()
        for conn in all_connections:
            identifier = str(conn.get("identifier", "")).strip()
            name = str(conn.get("name", "unknown"))
            if not identifier:
                continue
            current_params = client.get_connection_parameters(identifier)
            if current_params.get("color-scheme", "").strip() == desired_color_scheme:
                continue
            updated_params = dict(current_params)
            updated_params["color-scheme"] = desired_color_scheme
            update_payload = {
                "name": conn.get("name"),
                "parentIdentifier": conn.get("parentIdentifier", "ROOT"),
                "protocol": conn.get("protocol", "ssh"),
                "parameters": updated_params,
                "attributes": conn.get("attributes", {}),
            }
            if args.dry_run:
                print(f"[DRY-RUN] update color scheme: {name}")
            else:
                client.update_connection(identifier, update_payload)
                print(f"Updated color scheme: {name}")
            color_scheme_updated += 1

    print(
        json.dumps(
            {
                "connections": {
                    "created": created_connections,
                    "skipped": skipped_connections,
                    "color_scheme_updated": color_scheme_updated,
                },
                "total_desired": len(connections),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())