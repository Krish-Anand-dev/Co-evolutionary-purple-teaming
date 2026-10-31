"""Telemetry bridge, synthetic layer (T16, Decision D2 = synthetic events from day one, decided 31-Oct-2026).

CAGE-4 gives Blue no native event for PrivilegeEscalate, Impact or DegradeServices (measured, docs/telemetry-bridge-design.md
section 3). This module invents one for each SUCCESSFUL such action, from the Red action log the ground-truth labeler keeps
(src/bridge/labeler.py). Everything here is invented by us and is marked provenance="synthetic":
  PrivilegeEscalate -> process_creation, privilege=elevated, a shell whose parent is the daemon of the earlier exploit
  Impact            -> service_event, service_name="service_stopped"
  DegradeServices   -> service_event, service_name="service_degraded"
The same names are what static_09 / static_04 / static_10 in configs/static_blue_rules.json already expect.
DiscoverRemoteSystems, DiscoverDeception and Withdraw stay invisible on purpose (quiet reconnaissance / Red's own cleanup).

Rules of the layer:
  * only successful actions produce an event (a failed action changes nothing on the host);
  * the event goes to the one Blue agent that defends the target host's zone (CAGE-4: agents 0-3 one zone each, agent 4 the
    public, admin and office networks); hosts in an undefended zone (the contractor network) produce no event;
  * the event is Red-caused by construction: label_red=1 and source_action / source_agent come from the action log;
  * deterministic: the invented names depend only on (seed, host, step), never on Python's hash().
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from src.bridge.events import Event

SYNTHETIC_ACTIONS = ("PrivilegeEscalate", "Impact", "DegradeServices")

# Which Blue agent defends which zone (CAGE-4 EnterpriseScenarioGenerator._generate_blue_agents).
ZONE_OWNER = {
    "restricted_zone_a": "blue_agent_0",
    "operational_zone_a": "blue_agent_1",
    "restricted_zone_b": "blue_agent_2",
    "operational_zone_b": "blue_agent_3",
    "public_access_zone": "blue_agent_4",
    "admin_network": "blue_agent_4",
    "office_network": "blue_agent_4",
}

_ELEVATED_SHELLS = ("sh", "bash")
_DAEMON_PARENTS = ("sshd", "apache2", "haraka", "tomcat")


def _succeeded(record: Mapping[str, Any]) -> bool:
    return str(record.get("success", "")).upper() == "TRUE"


def synthetic_events(bridge: Any, step: int, red_actions: Iterable[Mapping[str, Any]],
                     actions: tuple[str, ...] = SYNTHETIC_ACTIONS) -> list[Event]:
    """Events for the Red actions in `red_actions` (labeler.action_log entries of this step). `bridge` supplies the id counter
    and the seed, so ids stay unique and sequential across native and synthetic events."""
    from src.bridge.native_tap import _pick, split_hostname  # local import: native_tap imports this module's package

    out: list[Event] = []
    for rec in red_actions:
        action = rec.get("action")
        host = rec.get("target")
        if action not in actions or not host or not _succeeded(rec):
            continue
        subnet, zone = split_hostname(host)
        agent = ZONE_OWNER.get(zone or "")
        if agent is None:
            continue
        common = dict(event_id=bridge._next_id(), step=step, blue_agent=agent, host_id=host, subnet=subnet, zone=zone,
                      label_red=1, source_action=action, source_agent=rec.get("agent"), provenance="synthetic")
        if action == "PrivilegeEscalate":
            out.append(Event(category="process_creation", privilege="elevated",
                             process_name=_pick(_ELEVATED_SHELLS, bridge.seed, host, step, "priv-name"),
                             parent_process=_pick(_DAEMON_PARENTS, bridge.seed, host, "priv-parent"),
                             enriched_fields=("process_name", "parent_process", "privilege"), **common))
        else:
            name = "service_stopped" if action == "Impact" else "service_degraded"
            out.append(Event(category="service_event", service_name=name, enriched_fields=("service_name",), **common))
    return out
