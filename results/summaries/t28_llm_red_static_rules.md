# LLM Red (Qwen3-4B, plan once per round) vs the static ruleset (T28, 3 tuning seeds x 5 rounds, 500 steps, Blue passive)

Inputs: results/t28_llm.jsonl. Mean over seeds, 95% bootstrap CI over seeds.

### precision

| condition | round | precision mean [95% CI] | n seeds | missing |
|---|---|---|---|---|
| static_rules_vs_llm_red | 1 | 0.840 [0.823, 0.872] | 3 | 0 |
| static_rules_vs_llm_red | 2 | 0.877 [0.867, 0.897] | 3 | 0 |
| static_rules_vs_llm_red | 3 | 0.864 [0.852, 0.871] | 3 | 0 |
| static_rules_vs_llm_red | 4 | 0.852 [0.849, 0.855] | 3 | 0 |
| static_rules_vs_llm_red | 5 | 0.863 [0.843, 0.885] | 3 | 0 |

### recall

| condition | round | recall mean [95% CI] | n seeds | missing |
|---|---|---|---|---|
| static_rules_vs_llm_red | 1 | 0.919 [0.915, 0.926] | 3 | 0 |
| static_rules_vs_llm_red | 2 | 0.904 [0.897, 0.914] | 3 | 0 |
| static_rules_vs_llm_red | 3 | 0.882 [0.856, 0.896] | 3 | 0 |
| static_rules_vs_llm_red | 4 | 0.918 [0.902, 0.926] | 3 | 0 |
| static_rules_vs_llm_red | 5 | 0.910 [0.884, 0.933] | 3 | 0 |

### fpr

| condition | round | fpr mean [95% CI] | n seeds | missing |
|---|---|---|---|---|
| static_rules_vs_llm_red | 1 | 0.721 [0.682, 0.745] | 3 | 0 |
| static_rules_vs_llm_red | 2 | 0.718 [0.670, 0.744] | 3 | 0 |
| static_rules_vs_llm_red | 3 | 0.705 [0.626, 0.747] | 3 | 0 |
| static_rules_vs_llm_red | 4 | 0.696 [0.660, 0.734] | 3 | 0 |
| static_rules_vs_llm_red | 5 | 0.750 [0.709, 0.792] | 3 | 0 |

### red_success

| condition | round | red_success mean [95% CI] | n seeds | missing |
|---|---|---|---|---|
| static_rules_vs_llm_red | 1 | 0.000 [0.000, 0.000] | 3 | 0 |
| static_rules_vs_llm_red | 2 | 14.000 [12.000, 16.000] | 3 | 0 |
| static_rules_vs_llm_red | 3 | 19.000 [13.000, 25.000] | 3 | 0 |
| static_rules_vs_llm_red | 4 | 9.667 [0.000, 16.000] | 3 | 0 |
| static_rules_vs_llm_red | 5 | 13.000 [0.000, 25.000] | 3 | 0 |

