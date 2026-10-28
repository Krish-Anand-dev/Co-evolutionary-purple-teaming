import json

from src.agents.blue import BlueLLMAgent
from src.agents.blue.prompt import LIMITS_HINT, build_prompt

CTX = {"round": 2, "agent_id": "blue_1", "feedback": ["host server_2 needed Restore"], "last_alerts": []}
RULE = {"title": "t", "level": "high", "logsource": {"category": "network_connection"},
        "detection": {"s": {"is_decoy": True}, "condition": "s"}, "confidence": 0.5, "rationale": "x"}


class Recorder:
    def __init__(self):
        self.prompts = []

    def generate(self, prompt, schema=None):
        self.prompts.append(prompt)
        return json.dumps({"rules": [RULE]}), {"latency_s": 0.0}


def test_hint_text_only_present_when_requested():
    assert "LIMITS OF THE RULE LANGUAGE" not in build_prompt(CTX)
    hinted = build_prompt(CTX, hint=True)
    assert all(line in hinted for line in LIMITS_HINT)
    assert "not_in" in hinted and "NOT in the condition" in hinted


def test_default_prompt_is_unchanged_by_the_hint_option():
    base = build_prompt(CTX)
    assert base == build_prompt(CTX, hint=False)
    # the hint is a pure insertion: removing its lines gives back the base prompt
    assert build_prompt(CTX, hint=True).replace("\n".join(LIMITS_HINT) + "\n", "") == base


def test_hint_works_with_nested_layout_and_does_not_leak_ground_truth():
    p = build_prompt(CTX, nested=True, hint=True)
    assert '"selections"' in p and "LIMITS OF THE RULE LANGUAGE" in p
    for hidden in ("label_red", "source_action", "source_agent"):
        assert hidden not in p


def test_single_selection_without_condition_gets_that_selection_as_condition():
    from src.agents.blue.repair import normalise_rule
    rule = dict(RULE, detection={"decoy_hit": {"is_decoy": True}})
    assert normalise_rule(rule)["detection"] == {"decoy_hit": {"is_decoy": True}, "condition": "decoy_hit"}


def test_missing_condition_is_not_guessed_when_ambiguous():
    from src.agents.blue.repair import normalise_rule
    two = dict(RULE, detection={"a": {"dst_port": 1}, "b": {"dst_port": 2}})
    assert "condition" not in normalise_rule(two)["detection"]
    assert normalise_rule(dict(RULE, detection={}))["detection"] == {}
    keep = dict(RULE, detection={"a": {"dst_port": 1}, "condition": "a"})
    assert normalise_rule(keep)["detection"] == keep["detection"]


def test_agent_passes_the_hint_to_the_prompt():
    on, off = Recorder(), Recorder()
    BlueLLMAgent("blue_0", on, prompt_hint=True).propose_rules({"round": 1})
    BlueLLMAgent("blue_0", off).propose_rules({"round": 1})
    assert "LIMITS OF THE RULE LANGUAGE" in on.prompts[0]
    assert "LIMITS OF THE RULE LANGUAGE" not in off.prompts[0]
