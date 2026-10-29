"""Telemetry bridge, native layer (T16): CAGE-4 native Blue observations -> events a Sigma-style rule can match.

Scope of this file (see docs/telemetry-bridge-design.md v0.2):
  * Layer A: the real events CAGE-4's Monitor already gives Blue (connections with IPs and ports, bare PID records,
    Green false alerts), read from the unwrapped Blue observation, not from the boolean wrapper.
  * Layer B: deterministic, seeded enrichment of the fields CAGE-4 does not provide (process names, protocol, service
    names). Every enriched field is listed in Event.enriched_fields so the paper can report how much is invented.
NOT in this file, on purpose: synthetic events for actions that leave no native event (PrivilegeEscalate, Impact, ...),
which depends on Decision D2/D3, and the ground-truth labels (label_red / source_*), which are the labeler's job (T21).

Native record shapes (measured on 3 seeds, docs/telemetry-bridge-design.md section 2):
  target-side connection  Connections[0] has local_address, local_port (service), remote_address, remote_port (ephemeral)
  path-side connection    Connections[0] has local_address, remote_address, remote_port (service), NO local_port
  PID-only                {"PID": n}, the session of a successful exploit
  local-only              Connections[0] has only local_address, local_port (Green false alert)
  decoy confirmation      {"PID","PPID","service_name","username",...}: Blue's own DeployDecoy result
In both connection shapes local_address is the TARGET and remote_address the SOURCE of the connection.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from src.bridge.events import Event

log = logging.getLogger(__name__)

# Fixed by the CybORG decoy classes (Decoy*.py): service name -> port.
DECOY_PORTS = {"apache2": 80, "tomcat": 443, "haraka": 25, "vsftpd": 80}
# Well-known ports only; anything else gets no service_name rather than an invented one.
PORT_SERVICE = {21: "ftp", 22: "ssh", 25: "smtp", 80: "http", 443: "https", 445: "smb", 3389: "rdp"}
_SESSION_PROCESSES = ("sh", "bash")
_SESSION_PARENTS = ("sshd", "apache2", "haraka", "tomcat")
_BENIGN_PROCESSES = ("cron", "python3", "bash", "logrotate")


def _pick(options: tuple[str, ...], *key: object) -> str:
    """Deterministic choice from `options`, independent of PYTHONHASHSEED (uses sha256, not hash())."""
    digest = hashlib.sha256("|".join(str(k) for k in key).encode()).digest()
    return options[int.from_bytes(digest[:4], "big") % len(options)]


def split_hostname(host: str) -> tuple[str | None, str | None]:
    """'restricted_zone_a_subnet_user_host_6' -> ('restricted_zone_a_subnet', 'restricted_zone_a')."""
    marker = "_subnet"
    if marker not in host:
        return None, None
    subnet = host[: host.index(marker) + len(marker)]
    return subnet, subnet[: -len(marker)]


class TelemetryBridge:
    """One instance per episode (or call reset(seed) at the start of each). Deterministic given the seed and input."""

    def __init__(self, seed: int = 0):
        self.reset(seed)

    def reset(self, seed: int | None = None) -> None:
        if seed is not None:
            self.seed = seed
        self._counter = 0
        # Blue's own decoys, learned from its DeployDecoy confirmations (which carry the host name but NO IP address).
        self._decoy_ports: dict[str, set[int]] = {}
        # ip -> host name, learned from every record that has an Interface; used to resolve path-side events.
        self._host_by_ip: dict[str, str] = {}
        self.unknown_records = 0

    # ------------------------------------------------------------------ public
    def step_events(self, step: int, blue_obs: dict[str, dict[str, Any]]) -> list[Event]:
        """blue_obs: {blue_agent: native observation dict (hostname -> host record)}. Returns events in a fixed order
        (agents sorted, hosts sorted, records in observation order)."""
        # Pass 1: learn which IP belongs to which host (any record with an Interface), so pass 2 can use it.
        for agent in blue_obs:
            for host, rec in (blue_obs[agent] or {}).items():
                if isinstance(rec, dict):
                    for iface in rec.get("Interface", []) or []:
                        if iface.get("ip_address"):
                            self._host_by_ip[str(iface["ip_address"])] = host
        # Pass 2: convert.
        events: list[Event] = []
        for agent in sorted(blue_obs):
            obs = blue_obs[agent] or {}
            hosts = sorted(h for h, rec in obs.items() if isinstance(rec, dict) and "Processes" in rec)
            for host in hosts:
                for proc in obs[host].get("Processes", []):
                    ev = self._convert(step, agent, host, proc)
                    if ev is not None:
                        events.append(ev)
        return events

    @staticmethod
    def blue_view(events: list[Event]) -> list[dict[str, Any]]:
        """What Blue (and the rule executor) may see: visible fields only."""
        return [e.visible() for e in events]

    # ----------------------------------------------------------------- private
    def _next_id(self) -> str:
        self._counter += 1
        return f"e{self._counter:07d}"

    def _convert(self, step: int, agent: str, host: str, proc: dict[str, Any]) -> Event | None:
        subnet, zone = split_hostname(host)
        base = dict(step=step, blue_agent=agent, host_id=host, subnet=subnet, zone=zone)

        # Blue's own decoy deployment: remember where the decoy lives; it is not an attack event, so not emitted.
        if "PPID" in proc and proc.get("service_name") in DECOY_PORTS:
            self._decoy_ports.setdefault(host, set()).add(DECOY_PORTS[proc["service_name"]])
            return None

        conns = proc.get("Connections") or []
        conn = conns[0] if conns and isinstance(conns[0], dict) else None

        if conn is not None and "remote_port" in conn and "remote_address" in conn and "local_address" in conn:
            target_side = "local_port" in conn
            dst_port = conn["local_port"] if target_side else conn["remote_port"]
            # A live observation carries ipaddress.IPv4Address objects, recorded dumps carry strings: always emit strings.
            src_ip, dst_ip = str(conn["remote_address"]), str(conn["local_address"])
            # The target is this host for a target-side event; for a path-side event (seen on a router) look it up by IP.
            target_host = host if target_side else self._host_by_ip.get(dst_ip)
            return Event(
                event_id=self._next_id(), category="network_connection",
                src_ip=src_ip, dst_ip=dst_ip, dst_port=dst_port,
                protocol="tcp", service_name=PORT_SERVICE.get(dst_port),
                is_decoy=dst_port in self._decoy_ports.get(target_host, ()),
                provenance="native", enriched_fields=("protocol", "service_name"), **base,
            )

        if conn is None and "PID" in proc and "PPID" not in proc:
            pid = proc["PID"]
            return Event(
                event_id=self._next_id(), category="process_creation", privilege="user",
                process_name=_pick(_SESSION_PROCESSES, self.seed, host, pid, "name"),
                parent_process=_pick(_SESSION_PARENTS, self.seed, host, pid, "parent"),
                provenance="native", enriched_fields=("process_name", "parent_process", "privilege"), **base,
            )

        if conn is not None and "local_port" in conn and "remote_port" not in conn:
            return Event(
                event_id=self._next_id(), category="process_creation", privilege="user",
                process_name=_pick(_BENIGN_PROCESSES, self.seed, host, conn["local_port"], "name"),
                parent_process="systemd",
                provenance="native", enriched_fields=("process_name", "parent_process", "privilege"), **base,
            )

        self.unknown_records += 1
        log.debug("unrecognised native record on %s: %s", host, proc)
        return None
