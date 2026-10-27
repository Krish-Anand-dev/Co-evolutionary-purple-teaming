import copy

import pytest

from src.rules import Rule, rule_validity, validate_rule, validate_rule_dict

VALID = {
    "rule_id": "r1",
    "round": 2,
    "agent_id": "blue_0",
    "title": "Service scan against server",
    "level": "medium",
    "logsource": {"category": "network_connection"},
    "detection": {
        "sel_scan": {"dst_port": [22, 80, 443], "protocol": "tcp"},
        "sel_known": {"src_ip|startswith": "10.0.1."},
        "condition": "sel_scan AND NOT sel_known",
    },
    "confidence": 0.7,
    "rationale": "Many connections to service ports from an unknown host.",
}


def variant(**changes):
    d = copy.deepcopy(VALID)
    d.update(changes)
    return d


def test_valid_rule_passes():
    res = validate_rule_dict(VALID)
    assert res.valid, res.errors


def test_dataclass_roundtrip():
    rule = Rule.from_dict(VALID)
    assert validate_rule(rule).valid
    assert rule.to_dict() == VALID


def test_missing_required_field():
    d = copy.deepcopy(VALID)
    del d["title"]
    res = validate_rule_dict(d)
    assert not res.valid and "title" in res.errors[0]


def test_not_a_dict():
    assert not validate_rule_dict("rule").valid
    assert not validate_rule_dict(None).valid


@pytest.mark.parametrize("changes", [
    {"level": "critical"},
    {"confidence": 1.5},
    {"confidence": -0.1},
    {"confidence": True},
    {"round": -1},
    {"round": "2"},
    {"agent_id": "red_0"},
    {"rule_id": ""},
    {"title": "  "},
    {"rationale": "x" * 301},
    {"logsource": {"category": "dns_query"}},
    {"logsource": {}},
])
def test_bad_scalar_fields(changes):
    assert not validate_rule_dict(variant(**changes)).valid


def test_unknown_field_rejected():
    d = variant()
    d["detection"]["sel_scan"]["registry_key"] = "x"
    res = validate_rule_dict(d)
    assert not res.valid and any("unknown field 'registry_key'" in e for e in res.errors)


def test_hidden_ground_truth_field_rejected():
    d = variant()
    d["detection"]["sel_scan"]["label_red"] = 1
    res = validate_rule_dict(d)
    assert not res.valid and any("hidden ground-truth field 'label_red'" in e for e in res.errors)


def test_bad_modifier_rejected():
    d = variant()
    d["detection"]["sel_scan"]["process_name|re"] = "evil.*"
    assert not validate_rule_dict(d).valid


def test_nested_value_rejected():
    d = variant()
    d["detection"]["sel_scan"]["dst_port"] = [{"a": 1}]
    assert not validate_rule_dict(d).valid


def test_empty_selection_and_list_rejected():
    d = variant()
    d["detection"]["sel_scan"] = {}
    assert not validate_rule_dict(d).valid
    d = variant()
    d["detection"]["sel_scan"] = {"dst_port": []}
    assert not validate_rule_dict(d).valid


@pytest.mark.parametrize("cond", [
    "sel_scan",
    "sel_scan and sel_known",
    "sel_scan OR sel_known",
    "NOT sel_known",
    "(sel_scan OR sel_known) AND NOT (sel_known)",
    "not not sel_scan",
])
def test_valid_conditions(cond):
    d = variant()
    d["detection"]["condition"] = cond
    res = validate_rule_dict(d)
    assert res.valid, (cond, res.errors)


@pytest.mark.parametrize("cond", [
    "",
    "sel_scan AND",
    "AND sel_scan",
    "sel_scan sel_known",
    "(sel_scan",
    "sel_scan)",
    "sel_missing",
    "sel_scan && sel_known",
    "1 of sel_*",
])
def test_invalid_conditions(cond):
    d = variant()
    d["detection"]["condition"] = cond
    assert not validate_rule_dict(d).valid, cond


def test_missing_condition_and_selections():
    d = variant()
    del d["detection"]["condition"]
    assert not validate_rule_dict(d).valid
    d = variant(detection={"condition": "sel"})
    assert not validate_rule_dict(d).valid


def test_selection_name_cannot_be_operator():
    d = variant(detection={"and": {"dst_port": 22}, "condition": "and"})
    assert not validate_rule_dict(d).valid


def test_rule_validity_fraction():
    bad = variant(level="critical")
    assert rule_validity([VALID, bad]) == 0.5
    assert rule_validity([VALID, VALID]) == 1.0
    assert rule_validity([bad]) == 0.0
    assert rule_validity([]) == 0.0
