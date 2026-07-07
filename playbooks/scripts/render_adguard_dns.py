#!/usr/bin/env python3
"""Render local_adguard.json for AdGuardHome rewrite_domains from hosts.ini docker_services."""
import json, os, re, sys

inventory = os.path.join(os.path.dirname(__file__), "..", "inventory", "prod", "hosts.ini")
services = []
with open(inventory) as f:
    for line in f:
        m = re.match(r"^\s*docker_service_name=(\S+)\s+docker_service_port=(\d+)\s+docker_service_domain=(\S+)", line)
        if m:
            services.append({"service": m.group(1), "port": int(m.group(2)), "domain": m.group(3)})

result = {"rewrite_domains": []}
for s in services:
    fqdn = f"{s['service']}.lan"
    result["rewrite_domains"].append({"server": "0.0.0.0", "name": fqdn, "answer": "192.168.0.34"})
    result["rewrite_domains"].append({"server": "::", "name": fqdn, "answer": "192.168.0.34"})

print(json.dumps(result, indent=2))
