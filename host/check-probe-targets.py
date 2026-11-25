#!/usr/bin/env python3
"""Fail `make check` when a probe target list drifts from its authority.

Public vhosts are declared once, in vps/sites/*.caddy. Three consumers used to
carry their own hardcoded copies: the WAN Worker, Prometheus blackbox-http,
and homelab-public-check (which is already derived at runtime). Private vhosts
are declared in stacks/edge/Caddyfile. This check compares all of them so a
new vhost cannot be probed by only one of the three alert paths.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SITES = ROOT / "vps" / "sites"
EDGE = ROOT / "stacks" / "edge" / "Caddyfile"
PROM = ROOT / "stacks" / "observability" / "prometheus" / "prometheus.yml"
WORKER = ROOT / "workers" / "wan-heartbeat" / "src" / "index.js"
PUBLIC_CHECK = ROOT / "host" / "public-check.sh"

# Same matcher as public-check.sh's list_public_hosts().
PUBLIC_HOST = re.compile(r"^\s*[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\s*\{", re.M)
EDGE_MATCHER = re.compile(r"^\s*@\S+\s+host\s+(\S+)", re.M)
URL = re.compile(r"https://([A-Za-z0-9.-]+)")


def public_authority() -> set[str]:
    hosts: set[str] = set()
    for path in sorted(SITES.glob("*.caddy")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("#"):
                continue
            m = PUBLIC_HOST.match(line)
            if m:
                hosts.add(line.strip().split()[0])
    return hosts


def private_authority() -> set[str]:
    return set(EDGE_MATCHER.findall(EDGE.read_text(encoding="utf-8")))


def prometheus_targets() -> dict[str, set[str]]:
    cfg = yaml.safe_load(PROM.read_text(encoding="utf-8"))
    jobs = cfg.get("scrape_configs") or []
    out: dict[str, set[str]] = {}
    for job in jobs:
        if job.get("job_name") not in ("blackbox-http", "blackbox-private", "blackbox-tcp"):
            continue
        targets: set[str] = set()
        for sc in job.get("static_configs") or []:
            for target in sc.get("targets") or []:
                if job["job_name"] == "blackbox-tcp":
                    targets.add(target.rsplit(":", 1)[-1])
                else:
                    m = URL.match(target)
                    if m:
                        targets.add(m.group(1))
        out[job["job_name"]] = targets
    return out


def worker_targets() -> set[str]:
    text = WORKER.read_text(encoding="utf-8")
    m = re.search(r"const\s+DEFAULT_TARGETS\s*=\s*\[(.*?)\];", text, re.S)
    if not m:
        raise RuntimeError("DEFAULT_TARGETS array not found in the Worker source")
    hosts = set()
    for url in re.findall(r'"(https://[^"]+)"', m.group(1)):
        hosts.add(URL.match(url).group(1))
    return hosts


def public_check_ports() -> set[str]:
    m = re.search(r"for\s+port\s+in\s+([^;]+);", PUBLIC_CHECK.read_text(encoding="utf-8"))
    if not m:
        raise RuntimeError("TCP port loop not found in public-check.sh")
    return set(re.findall(r"\d+", m.group(1)))


def compare(label: str, authority: set[str], found: set[str], errors: list[str]) -> None:
    if not authority:
        errors.append(f"{label}: authority list is empty (parser broke?)")
        return
    missing = sorted(authority - found)
    extra = sorted(found - authority)
    if missing:
        errors.append(f"{label}: missing from consumer: {', '.join(missing)}")
    if extra:
        errors.append(f"{label}: consumer probes undeclared targets: {', '.join(extra)}")


def main() -> int:
    errors: list[str] = []
    public = public_authority()
    private = private_authority()
    jobs = prometheus_targets()

    compare("public vhosts -> Worker DEFAULT_TARGETS", public, worker_targets(), errors)
    compare("public vhosts -> prometheus blackbox-http", public,
            jobs.get("blackbox-http", set()), errors)
    compare("private vhosts -> prometheus blackbox-private", private,
            jobs.get("blackbox-private", set()), errors)
    compare("TCP DNAT ports -> prometheus blackbox-tcp", public_check_ports(),
            jobs.get("blackbox-tcp", set()), errors)

    if errors:
        for err in errors:
            print(f"check-probe-targets: {err}", file=sys.stderr)
        return 1
    print(f"check-probe-targets: {len(public)} public, {len(private)} private, "
          f"{len(public_check_ports())} TCP targets agree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
