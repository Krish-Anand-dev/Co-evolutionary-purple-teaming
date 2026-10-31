import json

from src.bridge import SYNTHETIC_ACTIONS, TelemetryBridge, ZONE_OWNER
from src.rules.executor import RuleExecutor
from src.rules.loader import load_rules
from src.rules.schema import VISIBLE_FIELDS
from tests.test_static_rules import STATIC

HOST = "operational_zone_b_subnet_server_host_0"


def act(action, target=HOST, success="TRUE", agent="red_agent_4"):
    return {"step": 7, "agent": agent, "action": action, "target": target, "success": success}


def bridge(**kw):
    return TelemetryBridge(0, synthetic=SYNTHETIC_ACTIONS, **kw)


def test_off_by_default_and_without_red_actions():
    assert TelemetryBridge(0).step_events(7, {}, red_actions=[act("Impact")]) == []
    assert bridge().step_events(7, {}) == []


def test_privilege_escalate_becomes_an_elevated_process_event_owned_by_the_zone_defender():
    (e,) = bridge().step_events(7, {}, red_actions=[act("PrivilegeEscalate")])
    assert (e.category, e.privilege, e.blue_agent, e.host_id) == ("process_creation", "elevated", "blue_agent_3", HOST)
    assert e.process_name in ("sh", "bash") and e.parent_process in ("sshd", "apache2", "haraka", "tomcat")
    assert (e.provenance, e.label_red, e.source_action, e.source_agent) == ("synthetic", 1, "PrivilegeEscalate", "red_agent_4")
    assert (e.step, e.zone, e.subnet) == (7, "operational_zone_b", "operational_zone_b_subnet")


def test_impact_and_degrade_become_service_events():
    ev = bridge().step_events(7, {}, red_actions=[act("Impact"), act("DegradeServices")])
    assert [(e.category, e.service_name) for e in ev] == [("service_event", "service_stopped"), ("service_event", "service_degraded")]
    assert all(e.privilege is None and e.process_name is None for e in ev)


def test_failed_other_and_undefended_actions_give_no_event():
    ev = bridge().step_events(7, {}, red_actions=[
        act("Impact", success="FALSE"), act("Impact", success="IN_PROGRESS"),
        act("DiscoverRemoteSystems"), act("DiscoverDeception"), act("Withdraw"), act("ExploitRemoteService"),
        act("Impact", target="contractor_network_subnet_user_host_0"), act("Impact", target=None), act("Impact", target="odd_name")])
    assert ev == []


def test_every_defended_zone_has_one_owner_and_agent_4_has_three():
    assert sorted(set(ZONE_OWNER.values())) == [f"blue_agent_{i}" for i in range(5)]
    assert sum(v == "blue_agent_4" for v in ZONE_OWNER.values()) == 3


def test_ids_unique_visible_view_clean_deterministic_and_json():
    acts = [act("PrivilegeEscalate"), act("Impact")]
    a, b = bridge().step_events(7, {}, red_actions=acts), bridge().step_events(7, {}, red_actions=acts)
    assert [e.to_log() for e in a] == [e.to_log() for e in b]
    assert [e.event_id for e in a] == ["e0000001", "e0000002"]
    for e in a:
        assert set(e.visible()) == set(VISIBLE_FIELDS)
        json.dumps(e.to_log())


def test_event_ids_continue_after_native_events():
    br = bridge()
    br.step_events(1, {"blue_agent_0": {"h_subnet_user_host_0": {"Interface": [], "Processes": [{"PID": 5}]}}})
    (e,) = br.step_events(2, {}, red_actions=[act("Impact")])
    assert e.event_id == "e0000002"


def test_static_rules_catch_the_synthetic_events():
    ex = RuleExecutor(load_rules(STATIC))
    br = bridge()
    priv = br.blue_view(br.step_events(7, {}, red_actions=[act("PrivilegeEscalate")]))
    imp = br.blue_view(br.step_events(8, {}, red_actions=[act("Impact"), act("DegradeServices")]))
    assert {a.rule_id for a in ex.run(priv)} >= {"static_04", "static_10"}
    assert [a.rule_id for a in ex.run(imp)].count("static_09") == 2
