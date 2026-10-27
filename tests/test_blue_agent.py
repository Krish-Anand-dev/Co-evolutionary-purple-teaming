import json

import pytest

from src.agents.blue import BlueLLMAgent, MockLLMClient
from src.agents.blue.prompt import build_prompt
from src.agents.blue.repair import extract_rule_objects, normalise_rule

RULE = {
    "title": "Decoy touched", "level": "high", "logsource": {"category": "network_connection"},
    "detection": {"sel": {"is_decoy": True}, "condition": "sel"}, "confidence": 0.9, "rationale": "x",
}


class ScriptedClient:
    """Returns the given texts in order; records prompts."""
    def __init__(self, *texts):
        self.texts, self.prompts = list(texts), []

    def generate(self, prompt, schema=None):
        self.prompts.append(prompt)
        return self.texts.pop(0), {"latency_s": 0.5}


# ---- repair / extraction ----
@pytest.mark.parametrize("text", [
    json.dumps({"rules": [RULE]}),
    "```json\n" + json.dumps({"rules": [RULE]}) + "\n```",
    "Here you go:\n" + json.dumps([RULE]) + "\nthanks",
    json.dumps({"rules": [RULE]}).replace("}]}", "},]}"),
])
def test_extract_variants(text):
    assert len(extract_rule_objects(text)) == 1


def test_extract_truncated_keeps_complete_objects():
    second = dict(RULE, title="Second rule")
    two = json.dumps({"rules": [RULE, second]})
    cut = two.index("Second rule") + 5            # cut inside the second rule
    # the outer {"rules": ...} wrapper is also unterminated, so nothing complete remains at depth 0
    assert extract_rule_objects(two[:cut]) == []
    bare = json.dumps([RULE, second])             # bare array: first object is complete
    assert [r["title"] for r in extract_rule_objects(bare[: bare.index("Second rule") + 5])] == ["Decoy touched"]


def test_extract_ignores_braces_inside_strings():
    r = dict(RULE, rationale="uses } and { inside text")
    assert extract_rule_objects(json.dumps([r]))[0]["rationale"] == r["rationale"]


def test_extract_missing_comma_between_keys():
    # Real Gemma 4 output: no comma after the closing brace of the selection, before "condition".
    text = ('{"rules": [\n {\n  "title": "T",\n  "level": "high",\n  "logsource": {"category": "network_connection"},\n'
            '  "detection": {\n   "decoy_hit": {\n    "is_decoy": true\n   }\n   "condition": "decoy_hit"\n  },\n'
            '  "confidence": 0.9,\n  "rationale": "x"\n }\n]}')
    rules = extract_rule_objects(text)
    assert len(rules) == 1 and rules[0]["detection"]["condition"] == "decoy_hit"


def test_valid_json_is_never_modified_by_comma_fix():
    rule = dict(RULE, rationale='has a "quote",\n"and a newline-quote" inside')
    assert extract_rule_objects(json.dumps({"rules": [rule]}))[0]["rationale"] == rule["rationale"]


def test_normalise_hoists_condition_into_detection():
    broken = {k: v for k, v in RULE.items()}
    broken["detection"] = {"sel": {"is_decoy": True}}
    broken["condition"] = "sel"
    fixed = normalise_rule(broken)
    assert fixed["detection"]["condition"] == "sel" and "condition" not in fixed


def test_normalise_leaves_existing_detection_condition_alone():
    both = dict(RULE, condition="other")
    assert normalise_rule(both)["detection"]["condition"] == "sel"


def test_extract_no_json():
    assert extract_rule_objects("just prose") == []


def test_normalise_is_cosmetic():
    out = normalise_rule(dict(RULE, level="HIGH", confidence="85%", rationale="y" * 500))
    assert out["level"] == "high" and out["confidence"] == 0.85 and len(out["rationale"]) == 300
    assert normalise_rule(dict(RULE, confidence=7))["confidence"] == 1.0
    assert "extra" not in normalise_rule(RULE) and normalise_rule(RULE) == RULE


# ---- prompt ----
def test_prompt_contains_vocab_and_examples_and_no_ground_truth():
    p = build_prompt({"agent_id": "blue_1", "round": 3, "last_alerts": [{"rule_id": "a", "host_id": "h", "step": 1, "level": "low"}],
                      "feedback": ["host h2 needed Restore"]})
    assert "dst_port" in p and "EXAMPLES OF VALID RULES" in p and "host h2 needed Restore" in p
    for hidden in ("label_red", "source_action", "source_agent"):
        assert hidden not in p


def test_prompt_refuses_ground_truth_leak():
    with pytest.raises(ValueError):
        build_prompt({"round": 1, "feedback": ["label_red=1 on host h"]})


def test_prompt_includes_repair_errors():
    assert "unknown field" in build_prompt({"round": 1}, repair_errors=["unknown field 'x'"])


# ---- agent ----
def test_agent_accepts_valid_and_stamps_ids():
    agent = BlueLLMAgent("blue_2", ScriptedClient(json.dumps({"rules": [dict(RULE, rule_id="evil", agent_id="blue_9", round=99)]})))
    rules = agent.propose_rules({"round": 4})
    assert [r.rule_id for r in rules] == ["blue_2_r4_0"] and rules[0].agent_id == "blue_2" and rules[0].round == 4
    s = agent.history[-1]
    assert s.llm_calls == 1 and s.valid_raw == 1 and s.valid_final == 1 and not s.fallback


def test_agent_counts_raw_vs_final_validity():
    agent = BlueLLMAgent("blue_0", ScriptedClient(json.dumps({"rules": [dict(RULE, level="HIGH")]})))
    agent.propose_rules({"round": 1})
    s = agent.history[-1]
    assert s.valid_raw == 0 and s.valid_final == 1


def test_agent_repairs_once_with_error_feedback():
    bad = json.dumps({"rules": [dict(RULE, detection={"sel": {"nope": 1}, "condition": "sel"})]})
    good = json.dumps({"rules": [RULE]})
    client = ScriptedClient(bad, good)
    agent = BlueLLMAgent("blue_0", client)
    rules = agent.propose_rules({"round": 1})
    assert len(rules) == 1 and agent.history[-1].llm_calls == 2
    assert "unknown field 'nope'" in client.prompts[1]


def test_agent_falls_back_to_previous_rules():
    good = json.dumps({"rules": [RULE]})
    agent = BlueLLMAgent("blue_0", ScriptedClient(good, "garbage", "garbage again"))
    agent.propose_rules({"round": 1})
    assert len(agent.active_rules) == 1
    assert agent.propose_rules({"round": 2}) == []
    s = agent.history[-1]
    assert s.fallback and s.llm_calls == 2 and len(agent.active_rules) == 1


def test_agent_drops_duplicates():
    good = json.dumps({"rules": [RULE]})
    agent = BlueLLMAgent("blue_0", ScriptedClient(good, good, good))
    agent.propose_rules({"round": 1})
    assert agent.propose_rules({"round": 2}) == []
    assert agent.history[-1].duplicates >= 1 and len(agent.active_rules) == 1


def test_agent_step_loop_alerts_and_actions():
    agent = BlueLLMAgent("blue_0", ScriptedClient(json.dumps({"rules": [RULE]})))
    agent.propose_rules({"round": 1})
    agent.reset(0)
    ev = {"event_id": 1, "step": 3, "host_id": "h1", "category": "network_connection", "is_decoy": True, "label_red": 1}
    alerts = agent.observe([ev], 3)
    assert len(alerts) == 1
    assert agent.act(3) == [("Remove", "h1")]
    assert agent.observe([dict(ev, is_decoy=False)], 4) == [] and agent.act(4) == []


def test_agent_with_mock_is_deterministic():
    def run():
        agent = BlueLLMAgent("blue_0", MockLLMClient(seed=7))
        for rnd in range(1, 6):
            agent.propose_rules({"round": rnd})
        return [(s.valid_raw, s.valid_final, s.llm_calls, s.fallback) for s in agent.history]
    assert run() == run()
