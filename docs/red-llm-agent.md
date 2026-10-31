# LLM Red agent v1 (T20) - Krish

Code: `src/agents/red/plan.py` (plan schema, strict validator, compiler), `src/agents/red/llm_red.py` (planner, memory,
executor), `src/agents/red/mock_llm.py` (fault-injecting mock), `scripts/run_llm_red.py` (round runner),
tests in `tests/test_red_llm.py`. Results: `results/summaries/red_llm_qwen3-4b_10rounds.json`, `red_llm_mock_20rounds.json`.

## Design (Decision D1: the LLM acts once per round)
1. **Planner (LLM, once per round).** `RedPlanner.plan(round_ctx)` shows the LLM what Red can do and the last 5 rounds from
   the memory file (plan + what Red observed: exploits ok/tried, root gained, Impact ok, Degrade ok, progress). The LLM answers
   one JSON object: `goal`, `scan` (aggressive / stealthy / mixed), `probe_decoys` 0-1, `prioritise_servers`, `impact_bias` 0-1,
   `degrade_share` 0-1, `rationale`. Output is constrained with a JSON schema on llama-server.
2. **Validator.** Strict: every field present, right type and range, no extra keys, `rationale` <= 300 chars. One retry that
   quotes the errors back to the model. If the second answer is also unusable (or the server is down) the round falls back to
   CAGE-4's default scripted Red. Counted in the run summary.
3. **Executor (cheap, no LLM).** `PlannedRed` is a CAGE-4 `FiniteStateRedAgent` whose probability table is compiled from the plan
   (`compile_plan`; every row sums to 1, Withdraw is never offered). Every action is checked against the action space with
   `src/agents/red/legality.py`; an illegal one is replaced by Sleep and counted. CybORG builds one executor per Red agent,
   all sharing the round's plan (class-level state), so the plan must be set before the environment is created.
4. **Memory.** `RedMemory` appends one JSONL line per round (`--memory`). Only Red-observable information goes into the prompt:
   no Blue rules, nothing from the hidden label fields. A round that fell back is not stored (there is no plan to learn about).

The LLM never picks single actions, so there are no per-step LLM calls and no way for it to produce an illegal action.

## Measured (Qwen3-4B-Instruct-2507 Q4_K_M on llama-server, RTX 3060, temperature 0.7)
10 rounds, 500-step episodes, tuning seeds 0-4 cycled, Blue passive:

| Measure | Value |
|---|---|
| Plans requested / valid / invalid | 10 / 10 / 0 (invalid-plan rate 0%) |
| Valid on first try / after retry / fell back to scripted | 10 / 0 / 0 |
| LLM seconds per round (median) | 1.7 s (about 105 output tokens) |
| Illegal actions forced to Sleep | 0 of 28,578 executor steps |
| Distinct plans | 10 of 10 |

Fallback path, shown with the fault-injecting mock (NOT a real LLM; it tests parsing, retry and fallback only), 20 rounds:
26 LLM calls, 7 invalid answers (26.9%), 5 fixed by the retry, 1 round fell back to the scripted default, 0 illegal actions.

## How to read the real-LLM run honestly
- The plans are valid and varied, and the rationales refer to earlier rounds, so the memory is being read. The model moved
  between three of the four goals (decoy_evasion, balanced, fast_impact; it never chose stealth_recon in these 10 rounds).
- It does NOT clearly chase the progress number. It stayed mostly in a stealth-leaning style, and rounds with `impact_bias`
  at 0 produced 0 Impacts (rounds 1 and 4). Against a passive Blue there is no pressure to be stealthy or to adapt, so this run
  cannot say whether the LLM plans well. That needs an acting Blue (T28 / T29).
- "progress" here is the count of successful Impact actions in one episode. It is a placeholder, not the paper's Red reward
  (Eq. 1: kill-chain progress minus time to detect, T24).
- One model, one run, 10 rounds, one temperature. Do not rank models from it. Per-round impact numbers vary with the seed.
- The 4B model, `LlamaServerClient` and `RedPlanner` use the Blue stand-in client (`src/agents/blue/llm_client.py`). Prateek owns
  the official `LLMClient`; same `generate(prompt, schema) -> (text, meta)` signature, so it can be swapped in.

## A bug found and fixed while testing
After a discovery action CAGE-4 moves a host from R to RD (the trailing D means "subnet discovered"; I first misread it as
"decoy seen"). My first compiled table always offered Impact in RD, so `impact_bias = 0` still produced about 17 Impacts.
RD now offers DiscoverRemoteSystems with the same weights as R, and `test_impact_bias_zero_really_means_no_impact` guards it.
The first 10-round run was discarded and repeated; the numbers above are from the corrected code. The wrong "decoy seen"
wording in `scripted.py` and `red-strategies.md` was corrected too (the behaviour measured for the T19 variants is unaffected).

## Run it
```
llama-server --model <gguf> --alias qwen3-4b --host 127.0.0.1 --port 8080 --ctx-size 8192 --parallel 1 --device CUDA0 --fit on --flash-attn on --jinja
python scripts/run_llm_red.py --llama-server http://127.0.0.1:8080 --model qwen3-4b --rounds 10 --out results/summaries/red_llm_qwen3-4b.json
python scripts/run_llm_red.py --mock --rounds 20 --steps 150      # no GPU
```

## Not done yet (T28)
- Play against an acting Blue and the loop's reward; add the ground-truth labeler (T21) and the contract log format.
- Contract wording: `RedAgent.plan(round_ctx)` returns a dict (done); `act` needs the action space (see T07 note).
- Held-out strategy `hit_and_run` is not used by the LLM agent and must stay out of Blue training.
