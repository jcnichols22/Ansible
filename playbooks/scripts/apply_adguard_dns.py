#!/usr/bin/env python3
"""Mirror local_adguard.json into AdGuardHome via API /control/dns_config."""
import json, os, sys, urllib.request, urllib.error

BASE = "http://127.0.0.1:3000"
CONFIG = os.path.expanduser("~/adguard_local_adguard.json")


def load():
    if not os.path.exists(CONFIG):
        print(f"Missing {CONFIG}", file=sys.stderr)
        sys.exit(1)
    with open(CONFIG) as f:
        return json.load(f)


def ensure(adguard):
    """Append server:item_name=IP rewrites under local_dns.rewrite_domains."""
    try:
        data = json.dumps(adguard).encode()
        req = urllib.request.Request(f"{BASE}/control/dns_config", data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.load(r)
    except Exception as e:
        return getattr(e, "code", 0), str(e)


def main():
    adguard = load()
    status, out = ensure(adguard)
    print(f"status={status} body={json.dumps(out)[:200]}")
    sys.exit(0 if status == 200 else 1)


if __name__ == "__main__":
    main()
