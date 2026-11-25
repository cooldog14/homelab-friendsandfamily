#!/usr/bin/env python3
"""Fail `make check` if a Prometheus rule cannot be delivered by the bridge.

alertmanager-gotify-bridge:2.3.2 builds each Gotify message from the
`summary` (title) and `description` (body) annotations and reads the Gotify
priority from a numeric `priority` annotation (strconv.Atoi). It does NOT read
the `severity` label. A missing annotation makes the bridge reject the alert
without a Gotify message; promtool check rules validates syntax only, so this
contract needs its own check.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RULES = ROOT / "stacks" / "observability" / "prometheus" / "rules" / "homelab.yml"
ALERTMANAGER = ROOT / "stacks" / "observability" / "alertmanager" / "alertmanager.yml"
PRIORITY = {"critical": "8", "warning": "5"}


def main() -> int:
    errors: list[str] = []
    groups = (yaml.safe_load(RULES.read_text(encoding="utf-8")) or {}).get("groups") or []
    rules = [r for group in groups for r in (group.get("rules") or []) if "alert" in r]
    if not rules:
        errors.append("no alert rules found")

    names: set[str] = set()
    for rule in rules:
        name = rule["alert"]
        if name in names:
            errors.append(f"{name}: duplicate alert name")
        names.add(name)

        severity = (rule.get("labels") or {}).get("severity")
        if severity not in PRIORITY:
            errors.append(f"{name}: severity {severity!r} not in {sorted(PRIORITY)}")

        annotations = rule.get("annotations") or {}
        for key in ("summary", "description", "priority"):
            if not annotations.get(key):
                errors.append(f"{name}: missing/empty annotation {key!r}")

        priority = annotations.get("priority")
        if priority is not None:
            try:
                int(priority)
            except (TypeError, ValueError):
                errors.append(f"{name}: priority {priority!r} is not an integer (bridge uses strconv.Atoi)")
            if severity in PRIORITY and str(priority) != PRIORITY[severity]:
                errors.append(f"{name}: severity {severity} requires priority {PRIORITY[severity]}, got {priority!r}")

    am = yaml.safe_load(ALERTMANAGER.read_text(encoding="utf-8")) or {}
    receivers = {r.get("name") for r in am.get("receivers") or []}
    receiver = (am.get("route") or {}).get("receiver")
    if receiver not in receivers:
        errors.append(f"alertmanager route receiver {receiver!r} has no matching receiver")
    if not am.get("inhibit_rules"):
        errors.append("alertmanager has no inhibit_rules (cascade noise is unmanaged)")

    if errors:
        for err in errors:
            print(f"check-alert-rules: {err}", file=sys.stderr)
        return 1
    print(f"check-alert-rules: {len(rules)} rules satisfy the bridge delivery contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
