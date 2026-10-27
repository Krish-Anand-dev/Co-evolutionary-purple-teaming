# Documentation index

Docs for the Blue side (rules, executor, Blue LLM agent) and the CAGE-4 telemetry findings, written by Bhavit. Task IDs
(T06, T12 ...) refer to the Task Board in the execution plan. Setup of CAGE-4 itself is in [setup.md](setup.md).

| Document | What it covers | Tasks | State |
|---|---|---|---|
| [cage4-cheatsheet.md](cage4-cheatsheet.md) | What Blue observes, what it can do, how reward is computed, how a custom agent plugs in. Includes the measured note that the simulator's native events are richer than the Blue wrapper's booleans. | T06 | done |
| [telemetry-bridge-design.md](telemetry-bridge-design.md) | Measured evidence of which Red actions leave native events Blue can see (3 seeds, plus a decoy-deploying Blue), the hybrid bridge design, the proposed labeler hook, open decisions D2/D3. | T12 | **draft, needs a team decision** |
| [attack-mapping-check.md](attack-mapping-check.md) | CAGE-4 Red actions checked against attack.mitre.org, and which techniques the old paper table got wrong. | input to T13 | done, re-open the pages before final use |
| [blue-agent-and-rules.md](blue-agent-and-rules.md) | Module-by-module guide to `src/rules/` and `src/agents/blue/`, the local-LLM setup, and all measured results (valid-rule rates, schema A/B, model comparison). | T15, T17, T18 | done, see limits below |
| [human-rating-protocol.md](human-rating-protocol.md) | Rubric, sample, blinding procedure and limitation text for rating rule quality. | T31 | protocol and tooling done, **no ratings collected** |
| [references.md](references.md) | Papers, CAGE-4 and Sigma links used by the project. | | |

## What is and is not established

- **Established** (by tests and recorded runs): the rule validator, executor and playbook behave as specified (115 pytest tests); the Blue LLM agent turns a model answer into validated rules; on 50 fixed prompts the nested-schema setup gave 250/250 valid rules on Gemma-4-26B-A4B and GLM-4.7-Flash and 239/249 on Qwen3-30B-A3B; results are in [`results/summaries/`](../results/summaries/).
- **Not established:** that any generated rule actually detects an attack. That needs the telemetry bridge (T16) and the ground-truth labeler (T21). Validity only means a rule is well-formed.
- **Caveats on the numbers:** one seed per arm, one run per arm, and the nested-schema change also changed the prompt layout, so the schema's own effect is not isolated. See [blue-agent-and-rules.md](blue-agent-and-rules.md).
- **Mock-LLM figures** (93.8% / 95.4% in the scripts' mock mode) test the parser only and must not be quoted.

## Reproduce

Blue-side tests (no CAGE-4 needed):

```bash
pip install -r requirements-blue.txt
python -m pytest -q
```

Valid-rule measurement against a local `llama-server` (flags and model notes in [blue-agent-and-rules.md](blue-agent-and-rules.md)):

```bash
python scripts/measure_blue_validity.py --llama-server http://127.0.0.1:8080 --label <model> --n 50 --seed 3 --schema-nested --max-tokens 1500 --out results/<name>.json
python scripts/compare_runs.py 50 A=results/<a>.raw.jsonl B=results/<b>.raw.jsonl
```

Native-event evidence (needs CAGE-4 in `external/cage-challenge-4`, see [setup.md](setup.md)):

```bash
python scripts/dump_native_events.py --seed 0 --steps 500 --out results/native_events_seed0.jsonl
python scripts/dump_native_events.py --blue decoy --seed 0 --steps 500 --out results/native_events_decoy_seed0.jsonl
python scripts/analyze_native_events.py results/native_events_seed0.jsonl
```

Raw answer and event dumps are gitignored by design (`results/*`); only summaries are committed.

## Code map

| Path | Contents |
|---|---|
| `src/rules/` | `schema.py` (Rule, event vocabulary), `validator.py`, `sigma_export.py` (pySigma cross-check), `executor.py`, `playbook.py`, `loader.py`, `rating.py` |
| `src/agents/blue/` | `agent.py` (BlueLLMAgent), `prompt.py`, `repair.py`, `schema.py` (JSON schemas for constrained output), `llm_client.py` (llama-server and Ollama clients), `mock_llm.py` |
| `configs/static_blue_rules.json` | 10 hand-written baseline rules (T23 condition a) |
| `scripts/` | measurement, progress and comparison scripts; native-event dump and analysis |
| `tests/` | one test module per area |
