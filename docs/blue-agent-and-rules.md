# Blue side: rules, executor, playbook, LLM agent (T15, T17, T18) - Bhavit

Status 27-Oct-2026. Code is local (not yet in the shared repo). Everything below is covered by pytest (`python -m pytest -q`, 84+ tests).

## Layout
| Path | What it does |
|---|---|
| `src/rules/schema.py` | `Rule` dataclass; event vocabulary: `VISIBLE_FIELDS` (Blue may use), `HIDDEN_FIELDS` (label_red, source_action, source_agent: rules may never reference them). DRAFT until Decision D2 / T12 closes. |
| `src/rules/validator.py` | `validate_rule_dict`, `rule_validity()` (paper Eq. 2 RuleValidity). Checks required fields, level/confidence/round/agent_id, `logsource.category`, field names, modifiers (`contains/startswith/endswith`), condition grammar (`AND/OR/NOT`, parentheses, only defined selection names), rationale <= 300 chars. Errors are collected, not raised. |
| `src/rules/sigma_export.py` | Converts a rule to a Sigma dict and cross-checks with pySigma 2.0.1. Notes: pySigma wants lowercase `and/or/not` (handled) and only checks conditions when each parsed condition is `.parse()`d (handled). |
| `src/rules/executor.py` | Applies valid rules to Blue-visible events -> `Alert`s. Fields in a selection ANDed, value lists ORed, case-insensitive, missing field never matches, rule only sees its `logsource.category`, invalid rules rejected at load. Deterministic. |
| `src/rules/playbook.py` | Alerts -> abstract actions: low = log only, medium = Analyse, high = Remove, persistent high (after `restore_after` removes) = Restore; per-host `cooldown`; `min_confidence`. Defaults (cooldown 3, restore_after 2) are untuned. Mapping to CybORG action objects/host slots is T27. |
| `src/rules/loader.py`, `configs/static_blue_rules.json` | `load_rules(path)`; the 10 hand-written baseline rules for T23(a) (validated, pySigma-clean; values are guesses against the DRAFT vocabulary, re-check after T16). |
| `src/rules/rating.py` | Human-rating tooling for T31: blinded shuffled sheets, score validation, quadratic-weighted kappa. Protocol in `docs/human-rating-protocol.md`. |
| `src/agents/blue/agent.py` | `BlueLLMAgent`: `reset/observe/act/update` per step (no LLM), `propose_rules(round_ctx)` once per round (1 LLM call + at most 1 repair call, dedupe, fallback to previous rules). Stamps `rule_id/round/agent_id` itself, never trusts the LLM for them. |
| `src/agents/blue/prompt.py` | Prompt: schema, field vocabulary, 3 valid few-shot rules, last alerts, observable feedback. Raises if any ground-truth field name appears in the prompt. |
| `src/agents/blue/repair.py` | Extracts rule objects from raw text (code fences, prose, trailing commas, **missing commas between keys**, truncated tails, wrapper `{"rules": [...]}`); `normalise_rule` = cosmetic fixes only (level case, confidence "85%", rationale length, **`condition` hoisted into `detection`**). |
| `src/agents/blue/llm_client.py` | `LlamaServerClient` (llama.cpp `llama-server`, sends `enable_thinking=false`), `OllamaClient` stand-in. Prateek owns the official `LLMClient`; same `generate(prompt, schema) -> (text, meta)` signature. |
| `src/agents/blue/mock_llm.py` | Fault-injecting fake LLM for tests. A pipeline test, NOT a model. |
| `scripts/measure_blue_validity.py`, `scripts/progress.py` | Valid-rule-rate measurement (T18 acceptance) and a live progress printer. |

## Rules of the road (constraints from the role prompt)
- Blue never sees ground truth. `label_red`, `source_action`, `source_agent` are rejected in rules and blocked from prompts. The "misses" fed to the prompt must be Blue-observable feedback only (hosts that needed Restore, reward penalties, decoy hits), built by the integration layer (T27).
- Rules must validate before they run; the executor refuses invalid ones.
- Telemetry noise is seeded via config (bridge, T16).

## Local LLM setup used for T18 (this laptop)
- RTX 4050 Laptop, 6 GB VRAM, 15.7 GB RAM, i7-14650HX. llama.cpp `b11756` CUDA 13.4 in `C:\AI\Tools\llama-cpp-b11756-cuda134`.
- Models: SSD `C:\AI\Models\<name>\`, HDD `D:\AI\Models\<name>\`; move the one in use to the SSD and keep the empty folder behind. 27-Oct: Gemma4 on C:, Qwen3.8 and GLM-4.7-Flash on D:.
- Start (port 8080): `llama-server --model C:\AI\Models\Gemma4\gemma-4-26B-A4B-it-UD-Q3_K_M.gguf --alias gemma-local --host 127.0.0.1 --port 8080 --ctx-size 8192 --parallel 1 --device CUDA0 --fit on --fit-target 768 --flash-attn on --threads 16 --threads-batch 16 --jinja`
- Gemma 4 is a thinking model: without `chat_template_kwargs {"enable_thinking": false}` all tokens go to hidden reasoning and the answer is empty.
- Speed observed: about 19.6 tok/s generation, about 96 tok/s prompt processing, roughly 35-46 s per rule-writing call (about 700 output tokens). Feeds T09 / Decision D1.

## Measured: valid-rule rate on 50 prompts (T18 acceptance)
Setup for all runs: a fresh agent per prompt, `blue_{i%5}`, round `1 + i%10`, feedback = first `1 + i%5` lines of a fixed pool, no previous rules. Model: gemma-4-26B-A4B-it-UD-Q3_K_M, temperature 0.2. Result summaries are committed in [`results/summaries/`](../results/summaries/); the raw model answers (`*.raw.jsonl`, about 150 KB per run) are gitignored, so re-run the commands below to regenerate them.

**Run 1 (seed 0, parser BEFORE the two fixes) - baseline**
- 250 rules found, 200 valid (80%), 10 of 50 prompts ended with NO valid rule (fallback), 60 calls (1.2 per prompt), median 35 s/call.
- All 10 failures were exactly prompts 4, 9, 14 ... 49 (the prompts with the longest feedback list, agent blue_4). Cause: (a) first answer had a missing comma between `}` and `"condition"` so the whole JSON failed to parse; (b) the repair answer put `condition` next to `detection` instead of inside it, so the rule failed validation. Formatting slips, not content errors.

**Fixes (in `repair.py`, with tests):** missing-comma recovery (only tried after strict parsing fails, tested not to alter valid JSON) and hoisting a stray top-level `condition` into `detection`. Offline replay of run 1's recorded answers with the fixed parser: all 50 first answers yield a valid rule (in-sample: the fixes were designed by looking at this data, so not a fair estimate).

**Run 2 (seed 1, fixed parser) - out-of-sample check, run 27-Oct-2026**
- 250 rules found, 250 valid (100%), 0 of 50 prompts needed a repair or fell back, 50 calls (1.0 per prompt), median 34.8 s/call, about 714 output tokens and 22 tok/s per call.
- What the fixes did: 30 of the 50 answers were NOT strictly valid JSON (missing commas) and were rescued by the comma fix; without it most first attempts would have failed and gone to a repair call. The `condition` hoist was not needed in run 2 (0 rules), so run 2 does not test it; it is covered by unit tests and by run 1 (50 rules).
- Caveat on the comparison: run 1 and run 2 differ in seed AND parser, so the jump from 80% to 100% is the combined effect, not a controlled A/B of one change. Replaying run 1's recorded answers through the fixed parser (offline, in-sample) also gives 100% valid after cosmetic fixes (250 of 300 valid exactly as written).
- The model returned exactly 5 rules (the maximum) in every prompt, so this says nothing about rule diversity or usefulness.

**Schema A/B on Gemma 4, seed 3, 28-Oct-2026 (GPU back after reboot)**
- **Arm A, no schema, 50 prompts (complete):** 250 rules, 241 valid (96.4%), 0 prompts without a valid rule, 50 calls, median 36 s/call. All 9 invalid rules came from prompts 6, 11, 16 ... 46 (every 5th) and had the same error: a selection used the modifier `dst_port|not_in`, which is not in our grammar (allowed: contains/startswith/endswith). 9 of 50 answers were not strictly valid JSON (rescued by the comma fix). Repairs never fired because every prompt still had at least one valid rule (repair only runs when none is valid).
- **Arm B, basic flat schema, STOPPED after 10 answers (partial, not comparable):** 5 prompts' worth was already clearly worse: of 35 rules found only 7 were valid, 3 of 5 prompts had no valid rule. Two causes seen in the raw answers: (1) the schema writes `condition` BEFORE the selections (properties come before additionalProperties), so the model wrote a condition naming selections it had not defined yet and invented a fake `condition_logic` selection; (2) constrained answers are longer (mean 877 tokens vs about 714) and 3 of 10 hit the 1,000-token cap, leaving truncated JSON. So the flat schema as written HURTS here; this is a flaw of this schema design, not evidence against constrained decoding in general. Raw answers: `results/t18_ab_gemma_schemaflat_seed3_PARTIAL_stopped.raw.jsonl` (not committed).
- **Arm C, nested schema, 50 prompts, same seed 3 and prompts as arm A (complete):** `selections` and `condition` are rule-level keys with selections FIRST (`rule_json_schema(nested=True)`; `repair.extract_rule_objects` converts back to the Sigma-style `detection` block; prompt layout changed to match; token cap 1,500). Paired result from `scripts/compare_runs.py`:

  | | A: no schema | C: nested schema |
  |---|---|---|
  | rules valid | 241 / 250 (96.4%) | 250 / 250 (100%) |
  | answers that were not strictly valid JSON | 9 of 50 | 0 of 50 |
  | prompts with no valid rule / repair calls | 0 / 0 | 0 / 0 |
  | answers cut off at the token cap | 0 | 0 |
  | mean seconds per call / mean tokens out | 36.9 / 686 | 39.0 / 752 |

  Reading it honestly: one model, one seed, one run per arm. The 9 invalid rules in A were all the same slip (`dst_port|not_in`), which the nested schema does NOT prevent (it does not restrict modifiers), so C's 0 may come partly from the changed prompt layout rather than from the constraint itself; the two cannot be separated from this data. What the schema clearly does: removes the malformed-JSON answers (9 to 0) and guarantees `condition` sits with the rule. Cost: about 2 s more per call. Recommendation for now: use the nested schema for the Blue agent and keep the validator and the repair path (the repair path never fired in A or C because every prompt still had a valid rule).
- **`--schema-strict` (restricts selection keys with a `patternProperties` pattern) does not work with llama-server:** one test call on 28-Oct produced empty selections and whitespace until the 1,500-token cap, with zero rules. The server accepted the schema but the generated grammar degenerated. Not usable as written; do not combine it with the nested layout.
- **Model comparison, same 50 prompts, seed 3, nested schema, 1,500-token cap, thinking off (28-Oct-2026):**

  | | Gemma-4-26B-A4B Q3 | GLM-4.7-Flash Q3 | Qwen3.8-27B Q3 (dense) |
  |---|---|---|---|
  | rules valid | 250 / 250 | 250 / 250 | not run (too slow) |
  | prompts with no valid rule / non-strict JSON / cut off | 0 / 0 / 0 | 0 / 0 / 0 | - |
  | mean seconds per call | 39.0 | 26.5 | about 300 (estimated from one test call) |
  | mean tokens out | 752 | 573 | - |
  | generation speed | about 22 tok/s | about 22 tok/s | 2.55 tok/s |
  | distinct detections among 250 rules | 28 (11%), one repeated 40 times | 45 (18%), one repeated 18 times | - |
  | levels high / medium / low | 139 / 111 / 0 | 109 / 103 / 38 | - |

  Reading it: validity is saturated for both MoE models, so it does not separate them any more. GLM is about 1.5x faster per call. Both repeat the same few rules across independent prompts (low diversity; in the real loop the previous rules and alerts are shown, which may change this, not measured). My read of the field usage: 29 GLM rules key on `blue_agent`, which says which defender saw the event and is not a meaningful attack signal. Validity says nothing about whether any of these rules detect anything.
  Qwen: with 6 GB VRAM and 15.7 GB RAM the dense 27B model generates 2.55 tok/s (one 300-token test call took 125 s, free RAM fell to 1.1 GB), so one normal answer takes about 5 minutes; 50 prompts would need over 4 hours. The sheet's Mode B plan needs thousands of such calls, so it is not a candidate on this machine. Its answer quality was not measured.
- **Replacement Qwen (28-Oct-2026): Qwen3-30B-A3B-Instruct-2507, file `Qwen3-30B-A3B-Instruct-2507-UD-Q3_K_XL.gguf`** (Unsloth GGUF from huggingface.co/unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF; 13,833,048,480 bytes, sha256 `36c21449...e649121` verified; mixture-of-experts, 30.5B total / 3.3B active, non-thinking, Apache-2.0). Replaces the dense Qwen3.8-27B, which was removed. Same 50 prompts, seed 3, 1,500-token cap:

  | | Qwen3-30B-A3B, nested schema | Qwen3-30B-A3B, plain prompt (no schema) |
  |---|---|---|
  | rules valid | 239 / 249 (96.0%) | 241 / 250 (96.4%) |
  | prompts with no valid rule / non-strict JSON / cut off | 0 / 0 / 0 | 0 / 0 / 0 |
  | mean seconds per call / tokens out | 30.8 / 676 | 34.9 / 712 |
  | generation speed | about 23 tok/s | about 24 tok/s |

  It runs as smoothly as Gemma and GLM (about 23 tok/s). Unlike them it does not reach 100%, and the schema makes no difference for it (96.0% vs 96.4%; this model did not produce the malformed-JSON answers that Gemma did, so there was little for the schema to fix).
- **The remaining failures follow one pattern across ALL models:** they come from one specific prompt in each group of five (the one with the longest or most pointed feedback), where the model asks for something the single-event rule language cannot express. Seen: negated modifiers (`dst_port|not_in`, `parent_process|notcontains`), a field that does not exist (`duration`, 9 rules), and an aggregation (`event_id|count`, 9 rules). The nested schema fixes structure but cannot stop an invented field or modifier. Two ways to handle it, not tried: (a) say in the prompt that negation is done with `NOT <selection>` and that counts, durations and thresholds are not available; (b) accept it as a real limit of the rule language (no aggregation or time windows) and discuss it in the paper. Repair calls never fired in any run because every prompt still had at least one valid rule.
- **Where the models live:** convention is one model on the SSD (`C:\AI\Models\<name>\`) and the rest on the HDD (`D:\AI\Models\<name>\`) with the empty folders left in place. State at the end of the 28-Oct runs: Gemma on C:; GLM-4.7-Flash and Qwen3-30B-A3B-Instruct-2507 on D: (blank placeholders on C:). The old Qwen3.8-27B dense model is gone from both drives.
- **Gemma and GLM both need `chat_template_kwargs {"enable_thinking": false}`** or the whole token budget goes into hidden reasoning (verified for both).

**Earlier note (superseded by the section above):** the model's JSON is malformed in a large share of answers. Schema-constrained output is implemented: `src/agents/blue/schema.py` (`rule_json_schema`, structure only, field names stay the validator's job), `BlueLLMAgent(..., use_schema=True)`, and `--schema` in `scripts/measure_blue_validity.py`; 5 tests. The planned same-seed A/B (free vs constrained, 50 prompts, then GLM-4.7-Flash and Qwen on the same prompts) has not run: on 27-Oct after the laptop slept, Windows reported the NVIDIA GPU as status "Unknown" and llama-server found no CUDA device. Needs a driver reset or reboot first. Run: `llama-server ... ` as above, then `python scripts/measure_blue_validity.py --llama-server http://127.0.0.1:8080 --label <model> --seed 3 --out results/<name>.json` once without and once with `--schema`.

Honest limits: 50 prompts from one model, one temperature, and the same 5 feedback patterns repeated; validity says the rules are well-formed, NOT that they detect anything (that needs the bridge + labels, T16/T21). The mock-LLM figures (93.8% / 95.4%) test the parser only and must not be quoted.
