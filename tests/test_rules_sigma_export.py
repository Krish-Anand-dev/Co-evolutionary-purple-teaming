import copy

import pytest

from src.rules import Rule, validate_rule
from src.rules.sigma_export import pysigma_errors, to_sigma_dict
from tests.test_rules_validator import VALID


def test_valid_rule_is_accepted_by_pysigma():
    rule = Rule.from_dict(VALID)
    assert validate_rule(rule).valid
    assert pysigma_errors(rule) == []


@pytest.mark.parametrize("cond", ["sel_scan", "sel_scan or sel_known", "(sel_scan or sel_known) and not sel_known"])
def test_conditions_roundtrip_to_pysigma(cond):
    d = copy.deepcopy(VALID)
    d["detection"]["condition"] = cond
    assert pysigma_errors(Rule.from_dict(d)) == []


def test_bool_and_int_values_accepted():
    d = copy.deepcopy(VALID)
    d["detection"] = {"sel": {"is_decoy": True, "dst_port": 4444}, "condition": "sel"}
    assert validate_rule(Rule.from_dict(d)).valid
    assert pysigma_errors(Rule.from_dict(d)) == []


@pytest.mark.parametrize("cond", ["sel_missing", "sel_scan and", "(sel_scan"])
def test_pysigma_rejects_bad_conditions(cond):
    d = copy.deepcopy(VALID)
    d["detection"]["condition"] = cond
    assert pysigma_errors(Rule.from_dict(d)) != []


def test_export_has_required_sigma_keys():
    out = to_sigma_dict(Rule.from_dict(VALID))
    assert {"title", "logsource", "detection", "level", "id"} <= set(out)
    assert out["logsource"] == {"category": "network_connection"}


def test_export_id_is_deterministic():
    assert to_sigma_dict(Rule.from_dict(VALID))["id"] == to_sigma_dict(Rule.from_dict(VALID))["id"]
