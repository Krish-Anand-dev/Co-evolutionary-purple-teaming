"""T21 ground-truth labeler: key matching, label rules, bridge wiring, and a live episode where every event is labelled."""
from __future__ import annotations

import copy
import ipaddress
import pathlib
import sys
from types import SimpleNamespace

import pytest

from src.bridge import GroundTruthLabeler, TelemetryBridge
from src.bridge.labeler import (Label, _CTX, _TaggedList, conn_key, event_key, label_for, record_key)

ROOT = pathlib.Path(__file__).resolve().parents[1]
CAGE4 = ROOT / "external" / "cage-challenge-4"
if CAGE4.exists():
    sys.path.insert(0, str(CAGE4))


def net(la, lp=None, ra=None, rp=None, pid=None):
    """Stand-in for CybORG's NetworkConnection (attributes only)."""
    return SimpleNamespace(local_address=ipaddress.IPv4Address(la), local_port=lp,
                           remote_address=ipaddress.IPv4Address(ra) if ra else None, remote_port=rp, pid=pid)


# ---------- label rules ----------
@pytest.mark.parametrize("agent,expected", [("red_agent_3", (1, "red_agent_3")), ("green_agent_0", (0, "green")),
                                            ("blue_agent_1", (0, "blue")), (None, (0, "unknown"))])
def test_label_rules(agent, expected):
    lab = label_for((agent, "SomeAction"), 7)
    assert (lab.label_red, lab.source_agent) == expected and lab.source_action == "SomeAction" and lab.step == 7


def test_no_context_means_benign_unknown():
    lab = label_for(None, 3)
    assert (lab.label_red, lab.source_action, lab.source_agent) == (0, "unknown", "unknown")


# ---------- keys: event side and record side must agree ----------
def test_network_event_key_matches_its_record():
    ev = net("10.0.0.5", 22, "10.0.1.9", 40001)
    rec = {"Connections": [{"local_address": ipaddress.IPv4Address("10.0.0.5"), "local_port": 22,
                            "remote_address": ipaddress.IPv4Address("10.0.1.9"), "remote_port": 40001}]}
    assert event_key(ev) == record_key(rec) == (None, ("10.0.0.5", 22, "10.0.1.9", 40001))


def test_path_side_event_has_no_local_port():
    ev = net("10.0.0.5", None, "10.0.1.9", 22)
    rec = {"Connections": [{"local_address": "10.0.0.5", "remote_address": "10.0.1.9", "remote_port": 22}]}
    assert event_key(ev) == record_key(rec)


def test_session_event_key_is_pid_only_because_add_process_drops_connections():
    ev = {"pid": 4242, "Connections": [{"local_address": "10.0.0.5", "local_port": 22,
                                         "remote_address": "10.0.1.9", "remote_port": 4444}]}
    assert event_key(ev) == record_key({"PID": 4242}) == (4242, None)


def test_green_local_alert_key():
    ev = {"local_address": ipaddress.IPv4Address("10.0.0.7"), "local_port": 50123}
    rec = {"Connections": [{"local_address": "10.0.0.7", "local_port": 50123}]}
    assert event_key(ev) == record_key(rec)
    assert conn_key(None, None, None, None) is None


# ---------- tagged list ----------
def test_tagged_list_stamps_context_and_survives_deepcopy():
    labeler = GroundTruthLabeler()
    lst = _TaggedList()
    lst.labeler = labeler
    token = _CTX.set(("red_agent_0", "ExploitRemoteService"))
    try:
        item = {"pid": 1}
        lst.append(item)
    finally:
        _CTX.reset(token)
    lst.append({"pid": 2})  # appended with no context
    assert lst.tags[id(item)].label_red == 1 and lst.tags[id(lst[1])].source_agent == "unknown"
    clone = copy.deepcopy(lst)
    assert type(clone) is list and clone == lst  # plain list: no tags, no labeler dragged along
    lst.clear()
    assert not lst and not lst.tags


# ---------- claiming ----------
def put(labeler, agent, host, key, label):
    labeler._ledger[(agent, host, key)].append(label)


def test_claim_is_fifo_per_key_and_consumes_the_entry():
    lb = GroundTruthLabeler()
    key = (None, ("10.0.0.5", 22, "10.0.1.9", 40001))
    put(lb, "blue_agent_0", "h1", key, Label(1, "ExploitRemoteService", "red_agent_0", 5))
    put(lb, "blue_agent_0", "h1", key, Label(0, "GreenAccessService", "green", 5))
    rec = {"Connections": [{"local_address": "10.0.0.5", "local_port": 22, "remote_address": "10.0.1.9", "remote_port": 40001}]}
    assert lb.claim("blue_agent_0", "h1", rec).label_red == 1
    assert lb.claim("blue_agent_0", "h1", rec).label_red == 0
    assert lb.claim("blue_agent_0", "h1", rec) is None
    assert lb.claim("blue_agent_1", "h1", rec) is None  # other Blue agent's ledger is separate


def test_merged_record_claims_one_label_and_retires_its_partner():
    """add_process merges records with one PID: a session event (pid) and a connection event (pid + connection)."""
    lb = GroundTruthLabeler()
    conn = ("10.0.0.5", 22, "10.0.1.9", 40001)
    put(lb, "b", "h", (9, conn), Label(1, "ExploitRemoteService", "red_agent_0", 1))
    put(lb, "b", "h", (9, None), Label(1, "ExploitRemoteService", "red_agent_0", 1))
    rec = {"PID": 9, "Connections": [{"local_address": "10.0.0.5", "local_port": 22,
                                      "remote_address": "10.0.1.9", "remote_port": 40001}]}
    assert lb.claim("b", "h", rec).label_red == 1
    assert lb.unclaimed() == 0 and lb.stats["merged_partners_retired"] == 1


def test_label_event_fills_hidden_fields_and_counts_failures():
    lb = GroundTruthLabeler()
    ev = SimpleNamespace(label_red=None, source_action=None, source_agent=None)
    rec = {"PID": 5}
    assert lb.label_event(ev, "b", "h", rec) is False and ev.label_red is None
    assert lb.stats["events_unlabelled"] == 1
    put(lb, "b", "h", (5, None), Label(1, "ExploitRemoteService", "red_agent_2", 3))
    assert lb.label_event(ev, "b", "h", rec) is True
    assert (ev.label_red, ev.source_action, ev.source_agent) == (1, "ExploitRemoteService", "red_agent_2")


# ---------- bridge wiring ----------
def test_bridge_events_are_identical_with_and_without_labeler_except_hidden_fields():
    obs = {"blue_agent_0": {"h1_subnet_user_host_1": {"Processes": [
        {"Connections": [{"local_address": "10.0.0.5", "local_port": 22, "remote_address": "10.0.1.9", "remote_port": 40001}]},
        {"PID": 77}], "Interface": [{"ip_address": "10.0.0.5"}]}}}
    plain = TelemetryBridge(1).step_events(0, obs)
    lb = GroundTruthLabeler()
    put(lb, "blue_agent_0", "h1_subnet_user_host_1", (None, ("10.0.0.5", 22, "10.0.1.9", 40001)),
        Label(1, "AggressiveServiceDiscovery", "red_agent_1", 0))
    put(lb, "blue_agent_0", "h1_subnet_user_host_1", (77, None), Label(1, "ExploitRemoteService", "red_agent_1", 0))
    labelled = TelemetryBridge(1, labeler=lb).step_events(0, obs)
    assert [e.visible() for e in plain] == [e.visible() for e in labelled]  # Blue sees the same thing
    assert [e.label_red for e in labelled] == [1, 1] and all(e.label_red is None for e in plain)
    assert lb.unclaimed() == 0
    # the hidden labels never appear in the Blue-visible view
    assert not {"label_red", "source_action", "source_agent"} & set(labelled[0].visible())


# ---------- live episode ----------
def test_live_episode_labels_every_event_and_agrees_with_the_action_log():
    pytest.importorskip("CybORG")
    pytest.importorskip("ray")
    from CybORG import CybORG
    from CybORG.Agents import EnterpriseGreenAgent, FiniteStateRedAgent, SleepAgent
    from CybORG.Simulator.Scenarios import EnterpriseScenarioGenerator

    with GroundTruthLabeler() as lb:
        sg = EnterpriseScenarioGenerator(blue_agent_class=SleepAgent, green_agent_class=EnterpriseGreenAgent,
                                         red_agent_class=FiniteStateRedAgent, steps=120)
        env = CybORG(sg, "sim", seed=1)
        env.reset()
        lb.reset()
        bridge = TelemetryBridge(1, labeler=lb)
        blues = [a for a in env.agents if a.startswith("blue")]
        events = []
        for step in range(119):
            env.step()
            obs = {}
            for a in blues:
                body = {k: v for k, v in env.get_observation(a).items() if k not in ("success", "action")}
                if body:
                    obs[a] = body
            events.extend(bridge.step_events(step, obs))
        log = list(lb.action_log)
    assert events and all(e.label_red in (0, 1) for e in events)
    assert lb.stats["events_unlabelled"] == 0 and lb.unclaimed() == 0
    red_log = {(r["step"], r["agent"], r["action"]) for r in log}
    for e in events:
        if e.label_red == 1:
            assert (e.step, e.source_agent, e.source_action) in red_log
        else:
            assert not (e.source_agent or "").startswith("red")
    assert {e.source_action for e in events if e.label_red == 0} <= {"GreenAccessService", "GreenLocalWork"}
    # patches are undone on exit
    from CybORG.Simulator.HostEvents import HostEvents
    from CybORG.Simulator.SimulationController import SimulationController
    assert not lb._installed
    assert SimulationController.execute_action is lb._originals["exec"]
    assert HostEvents.__init__ is lb._originals["init"]
