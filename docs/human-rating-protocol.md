# Human rating protocol for rule quality (T31) - Bhavit

Status 27-Oct-2026: protocol + tooling ready (`src/rules/rating.py`, 10 tests). Raters, sample and results are NOT collected yet; no rating numbers exist.
Goal: a small, honest human check of the paper's "rule quality" claim (Section 7), to sit next to RuleValidity and FPR replay (T36).

## What is rated
Only conditions that actually output rules (the FSM/grammar baseline and the raw-action ablation output actions, not rules):
1. Static hand-written rules (`configs/static_blue_rules.json`)
2. LLM Blue, no self-play
3. LLM Blue co-evolved with LLM Red (ours)

Sample: 20 rules per condition = 60 items, drawn from the final round of each test run, seeded. Each rater: about 60 items x 4 scores, roughly 1 hour. (20 per condition is small, enough to see large differences and to compute agreement, not to prove small ones; report CIs, never p-values alone.)

## Rubric (1-5 integer, 5 = best, one score per dimension)
| Dimension | Question | 1 | 3 | 5 |
|---|---|---|---|---|
| clarity | Could a SOC analyst understand what this rule looks for from title + conditions + rationale? | unreadable or contradictory | understandable with effort | immediately clear |
| actionability | If this alert fired, would the analyst know what to check or do next? | no idea | some idea | clear next step |
| plausibility | Does the logic plausibly catch real malicious behaviour of the kind in scope (discovery, exploit, privilege escalation, impact)? | does not make sense | partly | sound |
| fp_risk | How likely is it to fire on normal green-user activity? (5 = very unlikely to false-alarm, 1 = fires constantly) | fires on routine traffic | moderate | rarely fires on normal work |

Raters judge the rule text only, not its measured performance. No peeking at precision/recall.

## Procedure
1. After the test runs, collect each condition's final-round rules as JSON dicts.
2. Prateek (per the T31 hand-off in the Task Board) generates the sheet, so the labels are stripped by someone other than the rater who wrote the static rules:
   `build_rating_items({"static": [...], "llm": [...], "ours": [...]}, 20, seed)` then `write_rating_files(sheet, key, "results/ratings", ["bhavit","krish","prateek"])`.
   This strips `rule_id`, `agent_id`, `round` and the condition name, shuffles all items together, and writes one blank CSV per rater plus `KEY_do_not_open_until_all_rated.csv`.
3. Each rater fills their own CSV alone, without discussing items, then commits it. Nobody opens the key until all three CSVs exist.
4. `read_ratings` rejects missing scores or values outside 1..5. `pairwise_agreement` reports quadratic-weighted Cohen's kappa per dimension for each rater pair plus the mean.
5. Join ratings to the key, report mean score per condition and dimension with bootstrap 95% CIs (across items), and the kappas.
6. Do not drop disagreements. If a dimension's mean kappa is low (suggested threshold: below 0.4), say so and treat that dimension as indicative only.

## Known limitations (use this text in the paper's threats to validity)
- Raters are the three authors: not independent of the hypothesis, and not blind to expected outcomes.
- Style leaks: hand-written, LLM and co-evolved rules may be recognisable by wording even with IDs removed. Bhavit wrote the static rules and will often recognise them; report results with and without his scores on that condition.
- Three raters, 60 items: low statistical power; the human rating complements, never replaces, the automatic metrics.
- Scores are subjective; kappa measures consistency between us, not correctness.
- Rule quality here is judged against the synthetic telemetry vocabulary (Decision D2), not real logs.

## Quick check that the tooling works
`python -m pytest tests/test_rating.py -q` covers blinding, determinism, balance across conditions, file output, kappa (including a hand-computed example), and input validation.
