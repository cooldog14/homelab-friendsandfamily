"""Settings (environment) and the YAML service catalogue.

Everything here is read-only at import time; no sockets are opened, so the unit
tests can import this module without a running homelab.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

HERE = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = HERE / "config.yml"


@dataclass(frozen=True)
class Integration:
    """One optional HTTP API. An empty key means "not configured"."""

    name: str
    url: str
    key: str

    @property
    def configured(self) -> bool:
        return bool(self.url and self.key)

    def state(self) -> dict:
        return {"configured": self.configured, "error": None}


@dataclass(frozen=True)
class Settings:
    prometheus_url: str = "http://prometheus:9090"
    docker_socket: str = "/var/run/docker.sock"
    tailscale_socket: str = "/var/run/tailscale/tailscaled.sock"
    stacks_root: str = "/opt/stacks"
    public_caddy_dir: str = "/usr/local/share/homelab-public-sites"
    private_edge: str = "caddy:443"
    bind: str = "0.0.0.0"
    port: int = 8080
    timezone: str = "Europe/Paris"
    integrations: tuple[Integration, ...] = field(default_factory=tuple)

    @property
    def secrets(self) -> list[str]:
        """Configured API keys, longest first, for log redaction."""
        keys = {i.key for i in self.integrations if i.key}
        return sorted(keys, key=len, reverse=True)

    def integration(self, name: str) -> Integration:
        for item in self.integrations:
            if item.name == name:
                return item
        return Integration(name, "", "")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env

        def get(key: str, default: str = "") -> str:
            value = env.get(key)
            return default if value is None else value.strip()

        return cls(
            prometheus_url=get("PROMETHEUS_URL", "http://prometheus:9090"),
            docker_socket=get("DOCKER_SOCKET", "/var/run/docker.sock"),
            tailscale_socket=get(
                "TAILSCALE_SOCKET", "/var/run/tailscale/tailscaled.sock"
            ),
            stacks_root=get("STACKS_ROOT", "/opt/stacks"),
            public_caddy_dir=get(
                "PUBLIC_CADDY_DIR", "/usr/local/share/homelab-public-sites"
            ),
            private_edge=get("PRIVATE_EDGE", "caddy:443"),
            bind=get("BIND", "0.0.0.0"),
            port=int(get("PORT", "8080") or 8080),
            timezone=get("TZ", "Europe/Paris"),
            integrations=(
                Integration(
                    "jellyfin",
                    get("JELLYFIN_URL", "http://jellyfin:8096"),
                    get("JELLYFIN_API_KEY"),
                ),
                Integration(
                    "jellyseerr",
                    get("JELLYSEERR_URL", "http://jellyseerr:5055"),
                    get("JELLYSEERR_API_KEY"),
                ),
                Integration(
                    "prowlarr",
                    get("PROWLARR_URL", "http://prowlarr:9696"),
                    get("PROWLARR_API_KEY"),
                ),
                Integration(
                    "sonarr",
                    get("SONARR_URL", "http://sonarr:8989"),
                    get("SONARR_API_KEY"),
                ),
                Integration(
                    "radarr",
                    get("RADARR_URL", "http://radarr:7878"),
                    get("RADARR_API_KEY"),
                ),
            ),
        )


def title_case(value: str) -> str:
    """`octo-fiesta` -> `Octo-Fiesta`, `slskd` -> `Slskd`."""
    return " ".join(part[:1].upper() + part[1:] for part in value.replace("_", " ").split())


@dataclass(frozen=True)
class DashboardConfig:
    public_domain: str = "malice.biz"
    private_domain: str = "h.malice.biz"
    categories: tuple[dict, ...] = ()
    stack_categories: Mapping[str, str] = field(default_factory=dict)
    services: Mapping[str, dict] = field(default_factory=dict)
    extra_services: tuple[dict, ...] = ()
    dnat: tuple[dict, ...] = ()

    def meta(self, service_id: str) -> dict:
        return dict(self.services.get(service_id) or {})

    def label(self, service_id: str) -> str:
        meta = self.meta(service_id)
        if meta.get("label"):
            return str(meta["label"])
        stack, _, service = service_id.partition("/")
        return title_case(service or stack)

    def category(self, stack: str) -> str:
        return str(self.stack_categories.get(stack, stack))

    def category_order(self) -> dict[str, dict]:
        return {str(row.get("id")): row for row in self.categories}

    def private_url(self, service_id: str) -> str | None:
        host = self.meta(service_id).get("private_host")
        return f"https://{host}.{self.private_domain}" if host else None

    def public_url(self, service_id: str) -> str | None:
        host = self.meta(service_id).get("public_host")
        return f"https://{host}.{self.public_domain}" if host else None

    def local_url(self, service_id: str) -> str | None:
        url = self.meta(service_id).get("local")
        return str(url) if url else None


def load_config(path: str | os.PathLike[str] | None = None) -> DashboardConfig:
    """Read the catalogue. A missing file yields an empty catalogue, not a crash."""
    target = Path(path) if path else DEFAULT_CONFIG_PATH
    try:
        raw: Any = yaml.safe_load(target.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        raw = None
    if not isinstance(raw, dict):
        raw = {}

    def as_dict(value: Any) -> dict:
        return dict(value) if isinstance(value, dict) else {}

    def as_tuple(value: Any) -> tuple:
        return tuple(value) if isinstance(value, list) else ()

    return DashboardConfig(
        public_domain=str(raw.get("public_domain") or "malice.biz"),
        private_domain=str(raw.get("private_domain") or "h.malice.biz"),
        categories=tuple(as_dict(row) for row in as_tuple(raw.get("categories"))),
        stack_categories=as_dict(raw.get("stack_categories")),
        services={str(k): as_dict(v) for k, v in as_dict(raw.get("services")).items()},
        extra_services=tuple(as_dict(row) for row in as_tuple(raw.get("extra_services"))),
        dnat=tuple(as_dict(row) for row in as_tuple(raw.get("dnat"))),
    )
