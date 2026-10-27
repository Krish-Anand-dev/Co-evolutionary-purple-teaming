import copy

from src.rules import Rule
from src.rules.executor import Alert, RuleExecutor, rule_matches
from src.rules.playbook import PlaybookParams, ResponsePlaybook
from tests.test_rules_validator import VALID


def make_rule(**overrides) -> Rule:
    d = copy.deepcopy(VALID)
    d.update(overrides)
    return Rule.from_dict(d)


def event(**kw):
    base = {"event_id": 1, "step": 5, "host_id": "h1", "category": "network_connection",
            "dst_port": 22, "protocol": "tcp", "src_ip": "10.9.9.9", "process_name": "SSHD"}
    base.update(kw)
    return base


def test_basic_match_and_nomatch():
    rule = make_rule()  # port in [22,80,443] AND tcp AND NOT src startswith 10.0.1.
    assert rule_matches(rule, event())
    assert not rule_matches(rule, event(src_ip="10.0.1.7"))
    assert not rule_matches(rule, event(dst_port=9999))


def test_category_must_match():
    assert not rule_matches(make_rule(), event(category="process_creation"))


def test_missing_field_does_not_match():
    e = event()
    del e["protocol"]
    assert not rule_matches(make_rule(), e)


def test_string_compare_case_insensitive_and_modifiers():
    rule = make_rule(
        logsource={"category": "network_connection"},
        detection={"s": {"process_name|contains": "sshd", "src_ip|endswith": ".9"}, "condition": "s"},
    )
    assert rule_matches(rule, event(process_name="OpenSSHD-server"))
    assert not rule_matches(rule, event(src_ip="10.9.9.10"))


def test_or_and_parentheses():
    rule = make_rule(detection={
        "a": {"dst_port": 22}, "b": {"dst_port": 3389}, "c": {"protocol": "udp"},
        "condition": "(a or b) and not c",
    })
    assert rule_matches(rule, event(dst_port=3389))
    assert not rule_matches(rule, event(dst_port=3389, protocol="udp"))
    assert not rule_matches(rule, event(dst_port=80))


def test_bool_and_int_values():
    rule = make_rule(detection={"s": {"is_decoy": True}, "condition": "s"})
    assert rule_matches(rule, event(is_decoy=True))
    assert not rule_matches(rule, event(is_decoy=False))


def test_hidden_label_never_used_even_if_present_in_event():
    rule = make_rule(detection={"s": {"dst_port": 22}, "condition": "s"})
    assert rule_matches(rule, event(label_red=0))  # label ignored, match decided by visible fields only


def test_invalid_rule_rejected_not_executed():
    bad = make_rule(detection={"s": {"label_red": 1}, "condition": "s"})
    ex = RuleExecutor([bad, make_rule()])
    assert len(ex.rules) == 1 and ex.rejected[0][0] == bad.rule_id


def test_run_is_deterministic_and_ordered():
    ex = RuleExecutor([make_rule(rule_id="r1"), make_rule(rule_id="r2")])
    events = [event(event_id=1), event(event_id=2, dst_port=9999), event(event_id=3)]
    first = ex.run(events)
    assert first == ex.run(events)
    assert [(a.rule_id, a.event_id) for a in first] == [("r1", 1), ("r2", 1), ("r1", 3), ("r2", 3)]


def alert(host, level, conf=0.9, step=1):
    return Alert("r", 1, host, step, level, conf)


def test_playbook_levels():
    pb = ResponsePlaybook()
    acts = pb.decide(1, [alert("h1", "medium"), alert("h2", "high"), alert("h3", "low")])
    assert acts == [("Analyse", "h1"), ("Remove", "h2")]


def test_playbook_uses_worst_level_per_host():
    pb = ResponsePlaybook()
    assert pb.decide(1, [alert("h1", "low"), alert("h1", "high")]) == [("Remove", "h1")]


def test_playbook_cooldown_and_restore_escalation():
    pb = ResponsePlaybook(PlaybookParams(restore_after=2, cooldown=3))
    assert pb.decide(1, [alert("h1", "high")]) == [("Remove", "h1")]
    assert pb.decide(2, [alert("h1", "high")]) == []                  # cooling down
    assert pb.decide(4, [alert("h1", "high")]) == [("Remove", "h1")]
    assert pb.decide(7, [alert("h1", "high")]) == [("Restore", "h1")]  # persistent -> escalate
    assert pb.decide(10, [alert("h1", "high")]) == [("Remove", "h1")]  # counter reset


def test_playbook_min_confidence_and_reset():
    pb = ResponsePlaybook(PlaybookParams(min_confidence=0.5))
    assert pb.decide(1, [alert("h1", "high", conf=0.2)]) == []
    pb.decide(2, [alert("h1", "high")])
    pb.reset()
    assert pb.decide(3, [alert("h1", "high")]) == [("Remove", "h1")]
