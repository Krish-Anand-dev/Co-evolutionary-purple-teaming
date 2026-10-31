# Four Red strategies vs the static ruleset (T28, 10 tuning seeds, 500 steps, Blue passive)

Inputs: results/t28_cage4_default.jsonl, results/t28_aggressive.jsonl, results/t28_stealthy.jsonl, results/t28_deception_aware.jsonl. Mean over seeds, 95% bootstrap CI over seeds.

### precision

| condition | precision mean [95% CI] | n seeds | missing |
|---|---|---|---|
| static_rules_vs_aggressive | 0.861 [0.845, 0.876] | 10 | 0 |
| static_rules_vs_cage4_default | 0.859 [0.847, 0.871] | 10 | 0 |
| static_rules_vs_deception_aware | 0.842 [0.824, 0.860] | 10 | 0 |
| static_rules_vs_stealthy | 0.860 [0.847, 0.872] | 10 | 0 |

### recall

| condition | recall mean [95% CI] | n seeds | missing |
|---|---|---|---|
| static_rules_vs_aggressive | 0.883 [0.878, 0.889] | 10 | 0 |
| static_rules_vs_cage4_default | 0.896 [0.890, 0.902] | 10 | 0 |
| static_rules_vs_deception_aware | 0.902 [0.894, 0.910] | 10 | 0 |
| static_rules_vs_stealthy | 0.914 [0.908, 0.919] | 10 | 0 |

### fpr

| condition | fpr mean [95% CI] | n seeds | missing |
|---|---|---|---|
| static_rules_vs_aggressive | 0.715 [0.680, 0.748] | 10 | 0 |
| static_rules_vs_cage4_default | 0.688 [0.657, 0.724] | 10 | 0 |
| static_rules_vs_deception_aware | 0.687 [0.661, 0.715] | 10 | 0 |
| static_rules_vs_stealthy | 0.691 [0.663, 0.719] | 10 | 0 |

### Paired comparisons (A - B, same seeds; exploratory)

| A | B | metric | n seeds | mean difference [95% CI] | sign-flip p |
|---|---|---|---|---|---|
| static_rules_vs_aggressive | static_rules_vs_cage4_default | precision | 10 | +0.002 [-0.017, +0.019] | 0.873 |
| static_rules_vs_aggressive | static_rules_vs_cage4_default | recall | 10 | -0.013 [-0.019, -0.006] | 0.006 |
| static_rules_vs_aggressive | static_rules_vs_cage4_default | fpr | 10 | +0.027 [-0.006, +0.060] | 0.168 |
| static_rules_vs_stealthy | static_rules_vs_aggressive | precision | 10 | -0.001 [-0.016, +0.015] | 0.869 |
| static_rules_vs_stealthy | static_rules_vs_aggressive | recall | 10 | +0.031 [+0.022, +0.039] | 0.002 |
| static_rules_vs_stealthy | static_rules_vs_aggressive | fpr | 10 | -0.024 [-0.041, -0.005] | 0.041 |
| static_rules_vs_deception_aware | static_rules_vs_cage4_default | precision | 10 | -0.017 [-0.034, +0.001] | 0.109 |
| static_rules_vs_deception_aware | static_rules_vs_cage4_default | recall | 10 | +0.006 [-0.001, +0.013] | 0.121 |
| static_rules_vs_deception_aware | static_rules_vs_cage4_default | fpr | 10 | -0.001 [-0.026, +0.023] | 0.943 |

