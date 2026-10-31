# Real Red in the experiment runner (T28) - Krish

Code: `src/loop/real_episode.py` (`RealEpisodeRunner`, `round_extras`), a 6-line additive hook in `src/loop/runner.py`,
`src/agents/baselines/decoy_blue.py`, `scripts/run_red_experiment.py`, `configs/red_static_baseline.yaml`,
tests in `tests/test_real_episode.py`. Acceptance test from the plan: "Real Red plays full episodes inside the runner; labeler attached."

## What it does
`RealEpisodeRunner` is an `episode_fn` for Prateek's `run_experiment`. One call plays one full CAGE-4 episode:
1. **Red**: a scripted strategy (`cage4_default`, `aggressive`, `stealthy`, `deception_aware`, T19), the held-out `hit_and_run`
   (test seeds only), or `llm` (T20: an LLM plan once per round, cheap executor, memory per seed).
2. **Blue**: a stand-in (`passive` or `decoy`) until the real Blue (T27) is plugged in. It does not react to alerts.
3. **Detector**: optionally a rule set (`rules:` in the config, e.g. the 10 static rules) is run on the Blue-visible events,
   so tp / fp / fn / tn and the round metrics are real.
4. The telemetry bridge (T16) builds the events and the labeler (T21) marks each one red / benign; the run stops with an error
   if any event is unlabelled.
5. One contract-format **step record** per step and an `EpisodeResult` with the episode metrics; `round_extras` turns the
   episodes of a (seed, round) into the round record (precision, recall, fpr, time_to_detect, red_success, rule_validity, ...,
   pooled with `src/eval`, T25).

```
python scripts/run_red_experiment.py --config configs/red_static_baseline.yaml --output results/t28_static.jsonl
python scripts/run_red_experiment.py --red llm --llama-server http://127.0.0.1:8080 --seeds 0 1 2 --rounds 5 --output results/t28_llm.jsonl
python scripts/run_red_experiment.py --red llm --mock-llm --rounds 3 --seeds 0      # no GPU
python scripts/run_red_experiment.py --red hit_and_run --seed-set test --output results/t28_heldout.jsonl   # T44 only
```

## Rules the code enforces
- **The held-out Red strategy is refused on tuning seeds** (`ValueError`); it runs only with `--seed-set test`.
- Seeds come from the config's seed list of the chosen set; `--seeds` can only select a subset of it (tuning 0-9 / test 100-109).
- **LLM Red memory is per seed** (the 10 seeds are independent replicates, they must not learn from each other) and the rounds of a
  seed must arrive in order, otherwise `RuntimeError` (run with one worker).
- **Episodes are serialised** by a lock, whatever `max_workers` says: the labeler patches CybORG for the whole process and the T20
  executor keeps class-level state. So there is no parallel speed-up yet; for parallelism use one process per seed set.
- CybORG seed of an episode: round 1 / episode 0 uses the configured seed itself (so it matches every earlier measurement with that
  seed); other episodes get a hash-derived seed, which cannot collide with a configured seed (tests included).

## Step record (contract section 5) as written here
`run_id, condition, seed, round, phase, episode, step, agent, action, reward_components, alerts, active_rules, tp, fp, fn,
llm_calls, llm_latency_s` plus the extras `tn` and `events`.
- `phase` = `eval` for every step (no learning happens inside an episode yet); `agent` = `env` (one record per step, not per agent);
  `action` = `{red agent: action class}` for the Red decisions taken that step (CybORG's own `Sleep` and `RedSessionCheck` left out).
- `reward_components` = `{blue_penalty, blue_action_cost}`, the Blue team reward of CAGE-4 (negative = worse for Blue).
- `alerts` = `[{rule_id, event_id}]`; `tp / fp / fn / tn` count EVENTS at this step by label and alerted-or-not (definitions in
  `docs/metrics-and-stats.md`). **`tn` is new**: the contract's step record had no true-negative count, which made FPR
  impossible to compute from the step logs. `llm_calls` and `llm_latency_s` are put on step 0 of the first episode of a round.
- A CAGE-4 episode of N steps has N-1 step records (CybORG ends it one step early, same as its own evaluation script).
- The round record gets extra keys (`tp fp fn tn events detection_rate red_plan red_plan_source mean_reward`); the logger accepts them.

## Things for Prateek (T24 / T29) and Bhavit (T27)
1. **The runner hook.** `run_experiment(..., round_extras_fn=None)` merges the dict the function returns into each round record.
   Default is unchanged (Prateek's T22 tests and one of mine check that the nulls are still written without it).
   The record key `mock_mean_reward` keeps its old name; the real mean is in `mean_reward`.
2. **Plugging Blue in (T27).** `RealEpisodeRunner._play` is where Blue's agents are chosen (`BLUES`) and where the rules come from.
   The real Blue needs: a `propose_rules` call at the round boundary (feed the rules to `self.executor`), and its actions applied
   through CybORG (the EnterpriseMAE wrapper or a custom Blue class). Not done here.
3. **Two-sided rounds (T24 / T29).** Today a round = N episodes against a fixed Red (or one LLM plan per round). In the co-evolution loop
   the Red plan and the Blue rules should both change between rounds; `_prepare_red` already does the Red half (plan per
   (seed, round), memory fed back after each round).
4. The labeler's `reset()` is called per episode; `RealEpisodeRunner.close()` removes the CybORG patches (call it in `finally`).
5. Held-out strategy and test seeds: only the final T44 evaluation should use `--seed-set test`.

## Limits
- Blue does not act, so "red_success" is how much Red achieves against a Blue that does nothing, and time to detect is how fast
  the RULES would have flagged Red, not a defence. Do not read these as co-evolution results.
- Only Red strategies already in T19 / T20; no Red learning inside the runner yet beyond the LLM's per-round plan.
- The LLM Red path was exercised with the mock LLM in tests and with a real model (Qwen3-4B) in the run below.

## Results

### 1. Four scripted Red strategies, static rules as detector (40 episodes)
`cage4_default`, `aggressive`, `stealthy`, `deception_aware`; Blue passive; the 10 static rules; tuning seeds 0-9; 500 steps.
Mean over 10 seeds, 95% bootstrap CI over seeds. Raw tables: `results/summaries/t28_red_strategies_vs_static_rules.md/.json`.

| Red strategy | precision | recall | false-positive rate | time to detect | red_success (Impacts) |
|---|---|---|---|---|---|
| cage4_default | 0.859 [0.848, 0.871] | 0.896 [0.890, 0.902] | 0.688 [0.657, 0.724] | 0 | 17.5 [16.0, 19.1] |
| aggressive | 0.861 [0.845, 0.876] | 0.883 [0.878, 0.889] | 0.715 [0.679, 0.748] | 0 | 18.5 [16.6, 20.3] |
| stealthy | 0.860 [0.847, 0.872] | 0.914 [0.908, 0.919] | 0.691 [0.663, 0.719] | 0 | 17.6 [15.6, 19.4] |
| deception_aware | 0.842 [0.825, 0.861] | 0.902 [0.894, 0.910] | 0.687 [0.660, 0.715] | 0 | 17.2 [15.4, 19.0] |

Paired by seed (exploratory, 10 seeds so the smallest possible p is 0.002): recall is 3.1 points higher against `stealthy` than
against `aggressive` (difference +0.031 [+0.022, +0.039], p = 0.002) and 1.3 points lower against `aggressive` than against the
default (-0.013 [-0.019, -0.006], p = 0.006); precision does not differ detectably. So the sparring partners do differ in how
detectable they are for this ruleset, but the effects are small (a few points of recall). Time to detect is 0 for every strategy:
the rules fire on the first scan or exploit. Do not read "stealthy is easier to catch" as a finding about stealth: these rules
were written against the draft event vocabulary and the numbers describe this ruleset only.

**Check that the new path is right:** for `cage4_default`, all 5 metrics of all 10 seeds equal the numbers T25's separately written
script (`scripts/eval_static_baseline.py`) produced for the same Red, rules and seeds, with no mismatch.

### 2. LLM Red through the runner (15 episodes)
Qwen3-4B-Instruct-2507 Q4_K_M on llama-server (RTX 3060), temperature 0.7, one plan per round, 3 tuning seeds x 5 rounds x 500 steps,
Blue passive, static rules. `results/summaries/t28_llm_red_static_rules.md/.json`.
- 15 of 15 plans valid on the first try, 0 fallbacks, 15 LLM calls, 23 s of LLM time in total (about 1.5 s per round).
- Precision 0.84-0.88 and recall 0.88-0.92 per round (mean over the 3 seeds), in the same range as the scripted strategies. Three seeds per round
  are too few for a real comparison; this shows the path works, not how good the LLM's plans are.
- **The 4B model's plans are almost deterministic.** The first run of this experiment used one shared LLM sampling seed and every seed
  drew the identical plan in every round. That is fixed (each (seed, round) now samples with its own seed, test added), and the sampling
  seed is effective, but the model is still strongly peaked: on the round-1 prompt, 10 different sampling seeds gave 2 distinct plans
  (8 of 10 identical at temperature 0.7, 7 of 10 at 1.2). In the corrected run rounds 1-3 are still the same for all seeds
  (the prompt is nearly the same), and rounds 4 and 5 differ (3 distinct plans each, driven by the per-seed memory). So the LLM
  adds little between-seed variation here; the seed-to-seed spread in these tables is mostly the simulator's. A more diverse plan
  distribution would need a larger model, a higher temperature with more fields, or planning from several samples.
