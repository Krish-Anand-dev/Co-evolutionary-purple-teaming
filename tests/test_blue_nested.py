import json

from src.agents.blue import BlueLLMAgent
from src.agents.blue.prompt import FEW_SHOT, build_prompt
from src.agents.blue.repair import extract_rule_objects, flatten_nested_rule
from src.agents.blue.schema import rule_json_schema
from src.rules.validator import validate_rule_dict

NESTED = {
    "title": "Decoy touched", "level": "high", "logsource": {"category": "network_connection"},
    "selections": {"decoy": {"is_decoy": True}, "ssh": {"dst_port": 22}},
    "condition": "decoy and not ssh", "confidence": 0.9, "rationale": "x",
}


class Recorder:
    def __init__(self, text):
        self.text, self.schemas, self.prompts = text, [], []

    def generate(self, prompt, schema=None):
        self.prompts.append(prompt)
        self.schemas.append(schema)
        return self.text, {"latency_s": 0.0}


def test_nested_schema_orders_selections_before_condition():
    props = list(rule_json_schema(nested=True)["properties"]["rules"]["items"]["properties"])
    assert props.index("selections") < props.index("condition")
    assert "detection" not in props


def test_flat_schema_unchanged_by_nested_option():
    assert rule_json_schema() == rule_json_schema(nested=False)
    assert "detection" in rule_json_schema()["properties"]["rules"]["items"]["properties"]


def test_nested_schema_required_keys_and_strict_selection_keys():
    item = rule_json_schema(nested=True, strict_fields=True)["properties"]["rules"]["items"]
    assert {"selections", "condition", "title", "level", "logsource"} <= set(item["required"])
    sel = item["properties"]["selections"]["additionalProperties"]
    assert sel["additionalProperties"] is False and "patternProperties" in sel


def test_flatten_builds_detection_with_same_content():
    flat = flatten_nested_rule(NESTED)
    assert flat["detection"] == {"decoy": {"is_decoy": True}, "ssh": {"dst_port": 22}, "condition": "decoy and not ssh"}
    assert "selections" not in flat and "condition" not in flat
    assert flat["title"] == NESTED["title"] and flat["confidence"] == 0.9
    flat.update(rule_id="r", round=1, agent_id="blue_0")
    assert validate_rule_dict(flat).valid


def test_flatten_leaves_flat_and_colliding_rules_alone():
    flat_rule = {"title": "t", "detection": {"s": {"dst_port": 1}, "condition": "s"}}
    assert flatten_nested_rule(flat_rule) is flat_rule
    collide = dict(NESTED, selections={"condition": {"dst_port": 1}})
    assert flatten_nested_rule(collide) is collide
    assert flatten_nested_rule({"title": "t", "selections": "oops"}) == {"title": "t", "selections": "oops"}


def test_extract_handles_nested_wrapper_and_bare():
    wrapped = extract_rule_objects(json.dumps({"rules": [NESTED, NESTED]}))
    assert len(wrapped) == 2 and all("detection" in r for r in wrapped)
    assert "detection" in extract_rule_objects("here: " + json.dumps(NESTED))[0]


def test_nested_prompt_shows_nested_layout_and_examples():
    p = build_prompt({"round": 1}, nested=True)
    assert '"selections"' in p and p.index('"selections"') < p.index('"condition"')
    # few-shot examples are converted: no example keeps a rule-level "detection" block
    examples_part = p.split("EXAMPLES OF VALID RULES:")[1].split("ALERTS YOUR CURRENT")[0]
    assert '"detection"' not in examples_part and '"selections"' in examples_part


def test_flat_prompt_is_unchanged_by_nested_option():
    base = build_prompt({"round": 1, "feedback": ["x"]})
    assert base == build_prompt({"round": 1, "feedback": ["x"]}, nested=False)
    assert '"detection"' in base
    assert FEW_SHOT[0]["detection"]          # the shared few-shot constant itself was not mutated


def test_agent_nested_end_to_end():
    rec = Recorder(json.dumps({"rules": [NESTED]}))
    agent = BlueLLMAgent("blue_2", rec, nested_schema=True, strict_schema=True)
    rules = agent.propose_rules({"round": 3})
    assert len(rules) == 1 and rules[0].detection["condition"] == "decoy and not ssh"
    assert rec.schemas[0] == rule_json_schema(5, strict_fields=True, nested=True)
    assert '"selections"' in rec.prompts[0]
    s = agent.history[-1]
    assert s.valid_raw == 1 and s.valid_final == 1 and not s.fallback


def test_agent_default_has_no_schema_and_flat_prompt():
    rec = Recorder(json.dumps({"rules": [{"title": "t", "level": "high", "logsource": {"category": "network_connection"},
                                           "detection": {"s": {"is_decoy": True}, "condition": "s"},
                                           "confidence": 0.5, "rationale": "x"}]}))
    agent = BlueLLMAgent("blue_0", rec)
    agent.propose_rules({"round": 1})
    assert rec.schemas == [None] and '"selections"' not in rec.prompts[0]
