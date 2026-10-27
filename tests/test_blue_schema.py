import json

from src.agents.blue import BlueLLMAgent
from src.agents.blue.schema import rule_json_schema
from src.rules.schema import EVENT_CATEGORIES, LEVELS

RULE = {
    "title": "Decoy touched", "level": "high", "logsource": {"category": "network_connection"},
    "detection": {"sel": {"is_decoy": True}, "condition": "sel"}, "confidence": 0.9, "rationale": "x",
}


class Recorder:
    def __init__(self):
        self.schemas = []

    def generate(self, prompt, schema=None):
        self.schemas.append(schema)
        return json.dumps({"rules": [RULE]}), {"latency_s": 0.0}


def test_schema_shape():
    s = rule_json_schema(3)
    rule = s["properties"]["rules"]["items"]
    assert s["required"] == ["rules"] and s["properties"]["rules"]["maxItems"] == 3
    assert set(rule["required"]) == {"title", "level", "logsource", "detection", "confidence", "rationale"}
    assert set(rule["properties"]["level"]["enum"]) == LEVELS
    assert set(rule["properties"]["logsource"]["properties"]["category"]["enum"]) == EVENT_CATEGORIES


def test_schema_puts_condition_inside_detection():
    det = rule_json_schema()["properties"]["rules"]["items"]["properties"]["detection"]
    assert det["required"] == ["condition"] and "condition" in det["properties"]
    assert "additionalProperties" in det          # selections are free-named


def test_schema_is_json_serialisable():
    json.dumps(rule_json_schema())


def test_schema_does_not_restrict_field_names():
    # field names stay the validator's job, so schema output can still be rejected for unknown fields
    assert "enum" not in json.dumps(rule_json_schema()["properties"]["rules"]["items"]["properties"]["detection"])


def test_strict_schema_restricts_selection_keys_to_visible_fields():
    import re
    from src.rules.schema import HIDDEN_FIELDS, VISIBLE_FIELDS
    det = rule_json_schema(strict_fields=True)["properties"]["rules"]["items"]["properties"]["detection"]
    sel = det["additionalProperties"]
    assert sel["additionalProperties"] is False
    (pattern,) = sel["patternProperties"]
    for f in VISIBLE_FIELDS:
        assert re.match(pattern, f) and re.match(pattern, f + "|contains")
    for f in list(HIDDEN_FIELDS) + ["condition_logic", "registry_key"]:
        assert not re.match(pattern, f)
    assert not re.match(pattern, "dst_port|not_in")


def test_basic_and_strict_schemas_differ_only_in_selection_rules():
    basic, strict = rule_json_schema(), rule_json_schema(strict_fields=True)
    assert basic != strict
    assert basic["properties"]["rules"]["items"]["required"] == strict["properties"]["rules"]["items"]["required"]


def test_agent_strict_flag_sends_strict_schema():
    rec = Recorder()
    BlueLLMAgent("blue_0", rec, strict_schema=True).propose_rules({"round": 1})
    assert rec.schemas[0] == rule_json_schema(5, strict_fields=True)


def test_agent_sends_schema_only_when_enabled():
    off, on = Recorder(), Recorder()
    BlueLLMAgent("blue_0", off).propose_rules({"round": 1})
    BlueLLMAgent("blue_0", on, use_schema=True).propose_rules({"round": 1})
    assert off.schemas == [None]
    assert on.schemas[0] == rule_json_schema(5)
