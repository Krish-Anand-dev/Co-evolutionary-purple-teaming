from pathlib import Path

from src.rules.executor import RuleExecutor
from src.rules.loader import load_rules
from src.rules.sigma_export import pysigma_errors

STATIC = Path(__file__).resolve().parents[1] / "configs" / "static_blue_rules.json"


def test_static_rules_all_valid_and_pysigma_clean():
    rules = load_rules(STATIC)
    assert len(rules) == 10
    assert len({r.rule_id for r in rules}) == 10
    for r in rules:
        assert pysigma_errors(r) == [], r.rule_id


def test_static_rules_levels_and_categories_are_mixed():
    rules = load_rules(STATIC)
    assert {r.level for r in rules} == {"low", "medium", "high"}
    assert {r.logsource["category"] for r in rules} == {"network_connection", "process_creation", "service_event"}


def test_static_rules_fire_on_expected_events_and_stay_quiet_on_benign():
    ex = RuleExecutor(load_rules(STATIC))
    assert not ex.rejected
    decoy = {"event_id": 1, "step": 1, "host_id": "h", "category": "network_connection", "is_decoy": True}
    callback = {"event_id": 2, "step": 1, "host_id": "h", "category": "network_connection", "dst_port": 22}
    escalate = {"event_id": 3, "step": 1, "host_id": "h", "category": "process_creation",
                "privilege": "elevated", "parent_process": "sshd"}
    benign = {"event_id": 4, "step": 1, "host_id": "h", "category": "network_connection", "dst_port": 5432,
              "is_decoy": False, "zone": "operational"}
    fired = {(a.rule_id, a.event_id) for a in ex.run([decoy, callback, escalate, benign])}
    assert ("static_01", 1) in fired and ("static_02", 2) in fired
    assert {("static_04", 3), ("static_10", 3)} <= fired
    assert not any(eid == 4 for _, eid in fired)
