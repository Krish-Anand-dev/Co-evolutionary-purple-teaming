# Metrics and statistics module (T25) - Krish

Code: `src/eval/` (`metrics.py`, `stats.py`, `summary.py`, `plots.py`). Tests: `tests/test_eval_metrics.py` (22 tests, a
hand-computed toy example inside). End-to-end check on real episodes: `scripts/eval_static_baseline.py`.
Pure Python except the figures (matplotlib is optional), so it runs in every environment of the project.

## Definitions (use these exact words in the paper)
Ground truth comes from the labeler (T21): every event has `label_red` (1 = created by a Red action, 0 = benign).
An event is **alerted** if at least one active rule fired on it (several rules on one event count once).

| | alerted | not alerted |
|---|---|---|
| red event | TP | FN |
| benign event | FP | TN |

- precision = TP / (TP + FP), recall = TP / (TP + FN), false-positive rate = FP / (FP + TN)
- **A ratio with a zero denominator is `null`, never 0 or 1** (the JSONL logger rejects NaN, and 0 would mean "found nothing"
  rather than "nothing to find"). Tables count such seeds as *missing*.
- **Time to detect** (per episode) = step of the first alerted red event minus step of the first red event, in env steps.
  `null` if Red produced no events or none was alerted. A round with several episodes pools the counts (micro average) and
  reports `time_to_detect` = mean over the episodes where Red WAS detected, `detection_rate` = detected / episodes with red
  events, and `time_to_detect_censored` where an undetected episode counts as (last step - first red step).
  Always show `detection_rate` next to `time_to_detect`; the mean over detected episodes alone is optimistic.
- `rule_validity` = rules_valid / rules_emitted (from the Blue agent). `red_success` (proposal, not yet agreed) = number of
  successful `Impact` actions in the episode (`eval.red_success(action_log)`).

## Statistics
- Per seed first, then across seeds: each metric is reduced to ONE number per seed (mean of that seed's non-null values) and
  the **bootstrap resamples seeds** (percentile method, 10,000 resamples, 95%, seeded, deterministic). With 10 seeds the
  percentile interval tends to be slightly narrow; every table shows n next to the interval.
- Comparing conditions: `compare_conditions` / `paired_diff_ci` pair the two conditions **by seed** (same simulator seed for
  both), give the mean paired difference with a bootstrap CI, and an exact two-sided **sign-flip test** p-value (exact for up
  to 16 non-zero differences). For 10 seeds the smallest possible p is 2/1024, so "p < 0.05" is achievable but not extreme.
- Tuning seeds 0-9 vs test seeds 100-109: the code does not know which is which; the scripts that call it enforce this.

## Use
```python
from src.eval import evaluate_episode, round_metrics, summarise, format_table, read_jsonl, split_records
ep = evaluate_episode(events, alerts, last_step=498)        # events carry label_red; alerts from RuleExecutor.run(...)
round_metrics([ep, ...])                                      # -> precision, recall, fpr, time_to_detect, detection_rate ...
rows = summarise(split_records(read_jsonl("results/run.jsonl"))[1], group_by=("condition", "round"))
print(format_table(rows, "precision"))                        # markdown table, mean [95% CI] and n seeds
from src.eval.plots import plot_round_curves, plot_condition_bars   # needs matplotlib
plot_round_curves(rows, "precision", "figs/precision.png", conditions=["static", "fsm", "llm", "coevo"])
```
From the step records (contract) `episodes_from_step_records` rebuilds the same metrics using the per-step `tp / fp / fn`.

## Figures
One measure per figure, one axis. Colours are the first slots of a categorical palette checked for colour-blind separation on a
light background (all checks pass for 5 slots; aqua, yellow and magenta fall under 3:1 contrast on the surface, so each series
also has its own marker shape, a legend and an end-of-line label, and `format_table` is the table view of the same numbers).
At most 5 conditions per figure. Lines show the mean over seeds, bands the 95% bootstrap CI over seeds.

## Things the team should decide or know
1. **The step record has no true-negative count**, so FPR cannot be computed from step logs alone. Proposal for Prateek: add an
   optional `tn` (or `benign_events`) to the step record. `episodes_from_step_records` uses it when present.
2. **Event-level counts vs campaign level.** Red scans and exploits create many events per action, so recall over events can
   look good while whole attack stages (PrivilegeEscalate, Impact) leave no event at all unless synthetic events are enabled
   (D2). Report `time_to_detect` and `detection_rate` alongside, and state the label coverage in the paper.
3. **Base rate.** Benign events are rare next to red events in these episodes (about 150 benign vs about 650 red per episode), so
   precision can be high while the false-positive rate is high too (see the static-rules check below). Report both.
4. `red_success` needs a definition before the loop logs it (the Impact count here is a placeholder).
5. Plots here are light-surface PNGs; a dark-mode variant is not provided.

## End-to-end check on real episodes: the static ruleset as a detector
`scripts/eval_static_baseline.py` runs the 10 hand-written rules (`configs/static_blue_rules.json`) on real labelled CAGE-4 episodes:
Red = `FiniteStateRedAgent`, Blue passive or decoy-deploying (it does not act on the rules), 500 steps, **tuning seeds 0-9**, labels
from T21. Raw: `results/summaries/static_baseline_metrics.json`, tables `static_baseline_metrics.md`, bars `static_baseline_*.png`.

| Blue behaviour | precision | recall | false-positive rate | time to detect (steps) | red_success (Impacts) |
|---|---|---|---|---|---|
| passive | 0.859 [0.847, 0.871] | 0.896 [0.890, 0.902] | 0.688 [0.657, 0.724] | 0.0 | 17.5 [16.0, 19.1] |
| decoy-deploying | 0.868 [0.855, 0.882] | 0.895 [0.886, 0.904] | 0.682 [0.649, 0.715] | 0.0 | 16.8 [15.4, 18.2] |

Mean over 10 seeds, 95% bootstrap CI over seeds, n = 10 and no missing seeds in every cell. Checked by hand for seed 0 (passive):
739 events = 561 TP + 82 FP + 60 FN + 36 TN; precision 561/643 = 0.872, recall 561/621 = 0.903, FPR 82/118 = 0.695, as printed.

What to take from it (and what not to):
- **The pipeline works on real data**: labels -> alerts -> metrics -> tables and figures, with no unlabelled event and no missing value.
- **Time to detect is 0 in all 20 episodes**: the rules fire on the very first scan or exploit, so for this ruleset the metric says
  nothing yet. It will matter for tuned or learned rule sets.
- **The false-positive rate is high (about 0.69) while precision looks fine (about 0.86)**, a base-rate effect: benign events are few.
  On seed 0 passive, the alerts on benign events came from `static_03` ("process created by a service daemon", 50 alerts),
  `static_08` ("connection into a restricted zone", 32) and `static_05` (11); the port rules fired on 0 benign events.
  `static_03` matches a parent process ending in "d", and the bridge's INVENTED parent for Green process alerts is `systemd`.
  So part of this false-positive rate is the rule meeting synthetic enrichment, not CAGE-4 behaviour. Bhavit may want to re-check
  the rule and the enrichment (T16), and the paper should not present these numbers as how a real SOC ruleset performs.
- These rules were written against the draft event vocabulary (Bhavit's note on T23). Treat the numbers as a baseline for the
  pipeline and for later comparison, not as a result of the paper. One Red strategy only (CAGE-4 FSM), Blue not acting.
