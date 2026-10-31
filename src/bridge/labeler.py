"""Ground-truth labeler (T21): marks every bridge event red-caused (1) or benign (0), at the moment CAGE-4 creates it.

Definition: label_red = 1 iff the event record was created while a RED agent's action was executing (an exploit, a scan,
...). Events created under a Green agent's action (false alerts, connection failures) or anything else are 0.
`source_action` is the outermost action class that was running (e.g. ExploitRemoteService) and `source_agent` is the Red
agent's name, or "green" / "blue" / "unknown".

Why not match host + step afterwards (as the T12 analysis did): a path-side event lands on a router, not on the target,
so the host does not tell you who caused it. Here the cause is recorded while it happens.

How it works, without editing any CybORG file (light monkey-patching, undone by `uninstall()`):
  1. `SimulationController.execute_action` is wrapped: a context variable holds (agent, action class) while an action runs.
     Every executed Red action is also written to `action_log`.
  2. `HostEvents.__init__` is wrapped so each host's two event lists remember the context an item was appended under.
  3. `Monitor.execute` is wrapped: when Blue's Monitor consumes (and clears) a host's events, their tags move to a ledger
     keyed by (blue agent, host, record key).
  4. `TelemetryBridge` calls `label_event(...)` for each event it builds; the labeler claims the matching ledger entry.
The labels live only in this object and in the hidden event fields. They never enter any observation CybORG hands to an agent.

Records are matched by content, not by position, because CybORG's `Observation.add_process` merges records with the same
PID and can reorder them. Key = (PID or None, (local_address, local_port, remote_address, remote_port) or None).
Call `install()` BEFORE the CybORG environment is built (hosts are created then), and `reset()` between episodes.
"""
from __future__ import annotations

import contextvars
import copy
import logging
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

_CTX: contextvars.ContextVar[tuple[str | None, str] | None] = contextvars.ContextVar("t21_ctx", default=None)


@dataclass(frozen=True)
class Label:
    label_red: int
    source_action: str
    source_agent: str
    step: int | None = None


def _s(x: Any) -> str | None:
    return None if x is None else str(x)


def conn_key(local_address=None, local_port=None, remote_address=None, remote_port=None) -> tuple | None:
    if local_address is None and remote_address is None:
        return None
    return (_s(local_address), local_port or None, _s(remote_address), remote_port or None)


def event_key(item: Any) -> tuple:
    """Key of a host event object as Monitor will turn it into a record. NetworkConnection -> its pid and connection;
    process_creation dict with a pid -> PID only (Observation.add_process drops its 'Connections' key); a dict without a
    pid (Green false alert) -> its connection."""
    if isinstance(item, dict):
        if item.get("pid") is not None:
            return (int(item["pid"]), None)
        return (None, conn_key(item.get("local_address"), item.get("local_port"),
                               item.get("remote_address"), item.get("remote_port")))
    pid = getattr(item, "pid", None)
    return (int(pid) if pid is not None else None,
            conn_key(getattr(item, "local_address", None), getattr(item, "local_port", None),
                     getattr(item, "remote_address", None), getattr(item, "remote_port", None)))


def record_key(proc: dict[str, Any]) -> tuple:
    """Key of a native Blue-observation process record (same space as event_key)."""
    pid = proc.get("PID")
    conns = proc.get("Connections") or []
    c = conns[0] if conns and isinstance(conns[0], dict) else {}
    return (int(pid) if pid is not None else None,
            conn_key(c.get("local_address"), c.get("local_port"), c.get("remote_address"), c.get("remote_port")))


def label_for(ctx: tuple[str | None, str] | None, step: int | None) -> Label:
    if ctx is None:
        return Label(0, "unknown", "unknown", step)
    agent, action = ctx
    name = agent or ""
    if name.startswith("red"):
        return Label(1, action, name, step)
    if name.startswith("green"):
        return Label(0, action, "green", step)
    if name.startswith("blue"):
        return Label(0, action, "blue", step)
    return Label(0, action, "unknown", step)


class _TaggedList(list):
    """A list of host events that remembers, per item, the context it was appended under (keyed by id(item))."""

    def __init__(self, *a):
        super().__init__(*a)
        self.tags: dict[int, Label] = {}
        self.labeler: "GroundTruthLabeler | None" = None

    def _stamp(self, item: Any) -> None:
        if self.labeler is not None:
            self.tags[id(item)] = self.labeler.current_label()

    def append(self, item):
        super().append(item)
        self._stamp(item)

    def extend(self, items):
        for i in items:
            self.append(i)

    def insert(self, index, item):
        super().insert(index, item)
        self._stamp(item)

    def clear(self):
        super().clear()
        self.tags.clear()

    def __deepcopy__(self, memo):
        """Monitor deep-copies these lists into old_* ; copy only the items, never the tags or the labeler."""
        return copy.deepcopy(list(self), memo)


class GroundTruthLabeler:
    def __init__(self):
        self._installed = False
        self._originals: dict[str, Any] = {}
        self._controller = None
        self.reset()

    # ------------------------------------------------------------------ state
    def reset(self) -> None:
        """Forget everything about the previous episode."""
        self._ledger: dict[tuple, deque[Label]] = defaultdict(deque)
        self.action_log: list[dict[str, Any]] = []
        self.stats: Counter[str] = Counter()
        self._step = 0

    def current_label(self) -> Label:
        return label_for(_CTX.get(), self._step)

    # --------------------------------------------------------------- patching
    def install(self) -> "GroundTruthLabeler":
        """Patch CybORG (idempotent). Do this before building the environment."""
        if self._installed:
            return self
        from CybORG.Simulator.Actions.AbstractActions.Monitor import Monitor
        from CybORG.Simulator.HostEvents import HostEvents
        from CybORG.Simulator.SimulationController import SimulationController

        labeler = self
        orig_exec, orig_init, orig_monitor = SimulationController.execute_action, HostEvents.__init__, Monitor.execute
        self._originals = {"exec": orig_exec, "init": orig_init, "monitor": orig_monitor,
                           "classes": (SimulationController, HostEvents, Monitor)}

        def execute_action(controller, action):
            labeler._step = getattr(controller, "step_count", labeler._step)
            labeler._controller = controller
            agent = getattr(action, "agent", None)
            token = _CTX.set((agent, type(action).__name__))
            try:
                obs = orig_exec(controller, action)
            finally:
                _CTX.reset(token)
            if str(agent or "").startswith("red"):
                target = next((getattr(action, a) for a in ("ip_address", "hostname", "subnet") if hasattr(action, a)), None)
                labeler.action_log.append({"step": labeler._step, "agent": agent, "action": type(action).__name__,
                                           "target": _s(target), "success": str(getattr(obs, "success", None))})
            return obs

        def host_events_init(events, *a, **kw):
            orig_init(events, *a, **kw)
            for attr in ("network_connections", "process_creation"):
                tagged = _TaggedList(getattr(events, attr))
                tagged.labeler = labeler
                setattr(events, attr, tagged)

        def monitor_execute(monitor, state):
            before: dict[str, list[tuple[str, Any, Label | None]]] = {}
            for hostname, host in state.hosts.items():
                ev = host.events
                items = []
                for attr in ("network_connections", "process_creation"):
                    lst = getattr(ev, attr)
                    if len(lst):
                        items.append((attr, list(lst), dict(getattr(lst, "tags", {}))))
                if items:
                    before[hostname] = items
            obs = orig_monitor(monitor, state)
            for hostname, items in before.items():
                for attr, snapshot, tags in items:
                    if len(getattr(state.hosts[hostname].events, attr)) == 0:  # Monitor consumed this list
                        for item in snapshot:
                            lab = tags.get(id(item))
                            if lab is None:
                                lab = label_for(None, labeler._step)
                                labeler.stats["untagged_events"] += 1
                            labeler._ledger[(monitor.agent, hostname, event_key(item))].append(lab)
                            labeler.stats["events_consumed"] += 1
            return obs

        SimulationController.execute_action = execute_action
        HostEvents.__init__ = host_events_init
        Monitor.execute = monitor_execute
        self._installed = True
        return self

    def uninstall(self) -> None:
        if not self._installed:
            return
        sim, host_events, monitor = self._originals["classes"]
        sim.execute_action, host_events.__init__, monitor.execute = (
            self._originals["exec"], self._originals["init"], self._originals["monitor"])
        self._installed = False

    def __enter__(self):
        return self.install()

    def __exit__(self, *exc):
        self.uninstall()

    # ----------------------------------------------------------------- claims
    def claim(self, blue_agent: str, host: str, proc: dict[str, Any]) -> Label | None:
        """Take the ledger entry that belongs to this native record (or None if there is none)."""
        pid, conn = record_key(proc)
        # exact key first; a record that merged a session-creation event with a connection event carries both parts
        for key in ((pid, conn), (pid, None), (None, conn)):
            q = self._ledger.get((blue_agent, host, key))
            if q:
                lab = q.popleft()
                if pid is not None and conn is not None:  # also retire the partner event that was merged into this record
                    for partner in ((pid, None), (None, conn)):
                        pq = self._ledger.get((blue_agent, host, partner))
                        if pq and partner != key:
                            pq.popleft()
                            self.stats["merged_partners_retired"] += 1
                return lab
        return None

    def label_event(self, event, blue_agent: str, host: str, proc: dict[str, Any]) -> bool:
        """Fill label_red / source_action / source_agent on a bridge Event. False (and counted) when nothing matched."""
        lab = self.claim(blue_agent, host, proc)
        if lab is None:
            self.stats["events_unlabelled"] += 1
            log.warning("no label for record on %s: %s", host, proc)
            return False
        event.label_red, event.source_action, event.source_agent = lab.label_red, lab.source_action, lab.source_agent
        self.stats["events_labelled"] += 1
        self.stats["labelled_red" if lab.label_red else "labelled_benign"] += 1
        return True

    def unclaimed(self) -> int:
        """Consumed events no bridge record claimed (e.g. Blue's own decoy confirmation is never an event)."""
        return sum(len(q) for q in self._ledger.values())
