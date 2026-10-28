import copy
import json
from pathlib import Path

import pytest

from src.bridge import DECOY_PORTS, Event, TelemetryBridge, split_hostname
from src.rules.executor import RuleExecutor
from src.rules.loader import load_rules
from src.rules.schema import HIDDEN_FIELDS, VISIBLE_FIELDS
from tests.test_static_rules import STATIC

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "native_obs_sample.json").read_text(encoding="utf-8"))
PASSIVE, DECOY = FIXTURE["passive_seed0"], FIXTURE["decoy_seed0"]
RESULTS = Path(__file__).resolve().parents[1] / "results"


def run(steps, seed=0):
    bridge = TelemetryBridge(seed)
    out = []
    for s in steps:
        out.append(bridge.step_events(s["step"], s["blue_obs"]))
    return bridge, out


def test_split_hostname():
    assert split_hostname("restricted_zone_a_subnet_user_host_6") == ("restricted_zone_a_subnet", "restricted_zone_a")
    assert split_hostname("admin_network_subnet_server_host_0") == ("admin_network_subnet", "admin_network")
    assert split_hostname("odd_name") == (None, None)


def test_target_side_connections_become_network_events():
    _, out = run(PASSIVE)
    events = out[1]                                    # step 4: four scan/exploit connections to one host
    assert [e.dst_port for e in events] == [22, 1, 80, 3390]
    for e in events:
        assert e.category == "network_connection" and e.protocol == "tcp"
        assert e.src_ip == "10.0.68.195" and e.dst_ip == "10.0.68.172"      # remote = source, local = target
        assert e.host_id == "operational_zone_b_subnet_user_host_7" and e.blue_agent == "blue_agent_3"
        assert (e.subnet, e.zone) == ("operational_zone_b_subnet", "operational_zone_b")
        assert not e.is_decoy
    assert [e.service_name for e in events] == ["ssh", None, "http", None]    # unknown ports get no invented name


def test_path_side_event_sits_on_the_router_and_points_at_the_target():
    _, out = run(PASSIVE)
    path = [e for e in out[2] if e.host_id.endswith("_router")]
    assert len(path) == 1
    e = path[0]
    assert (e.category, e.dst_port, e.src_ip, e.dst_ip) == ("network_connection", 22, "10.0.68.195", "10.0.68.251")


def test_pid_only_record_becomes_process_creation_with_listed_enrichment():
    _, out = run(PASSIVE)
    proc = [e for e in out[2] if e.category == "process_creation"]
    assert len(proc) == 1
    e = proc[0]
    assert e.privilege == "user" and e.process_name in ("sh", "bash") and e.parent_process
    assert set(e.enriched_fields) == {"process_name", "parent_process", "privilege"}
    assert e.src_ip is None and e.dst_port is None


def test_green_false_alert_becomes_benign_process_event():
    _, out = run(PASSIVE)
    e = out[0][0]
    assert e.category == "process_creation" and e.process_name in ("cron", "python3", "bash", "logrotate")
    assert e.parent_process == "systemd" and e.privilege == "user"


def test_decoy_confirmation_is_not_an_event_but_marks_later_hits():
    bridge, out = run(DECOY)
    assert out[0] == []                                # Blue's own deployment is not an alert source
    hits = out[1]
    assert len(hits) == 1 and hits[0].dst_port == DECOY_PORTS["tomcat"] and hits[0].is_decoy


def test_other_port_on_a_decoy_host_is_not_flagged():
    steps = copy.deepcopy(DECOY)
    host = "operational_zone_b_subnet_server_host_0"
    steps[1]["blue_obs"]["blue_agent_3"][host]["Processes"][0]["Connections"][0]["local_port"] = 22
    _, out = run(steps)
    assert len(out[1]) == 1 and not out[1][0].is_decoy


def test_path_side_event_on_a_router_is_flagged_when_it_points_at_a_decoy():
    router_event = {"blue_agent_3": {"operational_zone_b_subnet_router": {"Processes": [
        {"Connections": [{"remote_port": 443, "local_address": "10.0.68.254", "remote_address": "10.0.68.195"}]}]}}}
    bridge = TelemetryBridge(0)
    bridge.step_events(DECOY[0]["step"], DECOY[0]["blue_obs"])        # deployment (host name only, no IP)
    assert not bridge.step_events(20, router_event)[0].is_decoy         # the IP is not known yet: not flagged
    bridge.step_events(DECOY[1]["step"], DECOY[1]["blue_obs"])        # a record with the host's Interface teaches the IP
    assert bridge.step_events(21, router_event)[0].is_decoy             # now the router event is recognised
    other = copy.deepcopy(router_event)
    other["blue_agent_3"]["operational_zone_b_subnet_router"]["Processes"][0]["Connections"][0]["remote_port"] = 22
    assert not bridge.step_events(22, other)[0].is_decoy                # same target, different port


def test_decoy_hit_before_deployment_is_not_flagged():
    _, out = run([DECOY[1]])                           # same hit event, but the bridge never saw the deployment
    assert len(out[0]) == 1 and not out[0][0].is_decoy


def test_visible_view_contains_exactly_the_visible_fields():
    _, out = run(PASSIVE + DECOY)
    events = [e for step in out for e in step]
    assert events
    for e in events:
        view = e.visible()
        assert set(view) == set(VISIBLE_FIELDS)
        assert not set(view) & HIDDEN_FIELDS and "provenance" not in view and "enriched_fields" not in view


def test_log_view_has_hidden_fields_unset_because_labels_belong_to_the_labeler():
    _, out = run(PASSIVE)
    log = out[1][0].to_log()
    assert {"label_red", "source_action", "source_agent", "provenance", "enriched_fields"} <= set(log)
    assert log["label_red"] is None and log["source_action"] is None and log["source_agent"] is None
    assert log["provenance"] == "native" and set(log["enriched_fields"]) == {"protocol", "service_name"}


def test_deterministic_for_the_same_seed_and_seed_changes_only_enriched_names():
    a = [e.to_log() for step in run(PASSIVE, seed=7)[1] for e in step]
    b = [e.to_log() for step in run(PASSIVE, seed=7)[1] for e in step]
    assert a == b
    names = {tuple(e.process_name for step in run(PASSIVE, seed=s)[1] for e in step) for s in range(12)}
    assert len(names) > 1                              # enrichment really depends on the seed
    ports = {tuple(e.dst_port for step in run(PASSIVE, seed=s)[1] for e in step) for s in range(12)}
    assert len(ports) == 1                             # native fields never depend on the seed


def test_event_ids_are_unique_sequential_and_reset_restarts_everything():
    bridge, out = run(DECOY)
    ids = [e.event_id for step in out for e in step]
    assert ids == sorted(set(ids)) and ids[0] == "e0000001"
    bridge.reset(0)
    again = bridge.step_events(DECOY[1]["step"], DECOY[1]["blue_obs"])
    assert again[0].event_id == "e0000001" and not again[0].is_decoy      # decoy registry was cleared too


def test_unknown_records_are_skipped_and_counted_not_fatal():
    bridge = TelemetryBridge(0)
    obs = {"blue_agent_0": {"h_subnet_user_host_0": {"Processes": [{"Weird": 1}, {"Connections": []}], "Interface": []}}}
    assert bridge.step_events(1, obs) == [] and bridge.unknown_records == 2


def test_hosts_without_processes_and_non_host_keys_are_ignored():
    bridge = TelemetryBridge(0)
    obs = {"blue_agent_0": {"success": "TRUE", "h_subnet_user_host_0": {"Interface": [{"ip_address": "10.0.0.1"}]}}}
    assert bridge.step_events(1, obs) == []


def test_static_baseline_rules_fire_on_bridge_output():
    ex = RuleExecutor(load_rules(STATIC))
    bridge = TelemetryBridge(0)
    deploy = bridge.blue_view(bridge.step_events(DECOY[0]["step"], DECOY[0]["blue_obs"]))
    hit = bridge.blue_view(bridge.step_events(DECOY[1]["step"], DECOY[1]["blue_obs"]))
    scan = bridge.blue_view(TelemetryBridge(0).step_events(PASSIVE[1]["step"], PASSIVE[1]["blue_obs"]))
    assert ex.run(deploy) == []                                                    # Blue's own decoy raises no alert
    assert {a.rule_id for a in ex.run(hit)} >= {"static_01"}                       # decoy touched
    ssh = [a for a in ex.run(scan) if a.rule_id == "static_02"]
    assert len(ssh) == 1                                                           # one of the four scan events is port 22
    assert not any(a.rule_id == "static_01" for a in ex.run(scan))


@pytest.mark.skipif(not (RESULTS / "native_events_seed0.jsonl").exists(), reason="local dump not present")
def test_full_recorded_episode_converts_cleanly():
    rows = [json.loads(line) for line in (RESULTS / "native_events_seed0.jsonl").read_text(encoding="utf-8").splitlines()]
    bridge = TelemetryBridge(0)
    n_events = n_records = 0
    for r in rows:
        events = bridge.step_events(r["step"], r["blue_obs"])
        n_events += len(events)
        n_records += sum(len(h.get("Processes", [])) for o in r["blue_obs"].values() for h in o.values())
        assert all(isinstance(e, Event) and e.label_red is None for e in events)
    assert bridge.unknown_records == 0
    assert n_events == n_records > 0                   # passive Blue: every native record yields exactly one event
