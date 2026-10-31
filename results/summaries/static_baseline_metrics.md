# Static ruleset as a detector (T25 end-to-end check)

10 hand-written rules, CAGE-4 FiniteStateRedAgent, tuning seeds [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], 500 steps. Mean over seeds with 95% bootstrap CI over seeds.

### precision

| condition | round | precision mean [95% CI] | n seeds | missing |
|---|---|---|---|---|
| static_rules_decoy_blue | 1 | 0.950 [0.944, 0.956] | 10 | 0 |
| static_rules_passive_blue | 1 | 0.947 [0.940, 0.954] | 10 | 0 |

### recall

| condition | round | recall mean [95% CI] | n seeds | missing |
|---|---|---|---|---|
| static_rules_decoy_blue | 1 | 0.943 [0.936, 0.951] | 10 | 0 |
| static_rules_passive_blue | 1 | 0.946 [0.940, 0.952] | 10 | 0 |

### fpr

| condition | round | fpr mean [95% CI] | n seeds | missing |
|---|---|---|---|---|
| static_rules_decoy_blue | 1 | 0.252 [0.225, 0.281] | 10 | 0 |
| static_rules_passive_blue | 1 | 0.253 [0.212, 0.293] | 10 | 0 |

### time_to_detect

| condition | round | time_to_detect mean [95% CI] | n seeds | missing |
|---|---|---|---|---|
| static_rules_decoy_blue | 1 | 0.000 [0.000, 0.000] | 10 | 0 |
| static_rules_passive_blue | 1 | 0.000 [0.000, 0.000] | 10 | 0 |

### red_success

| condition | round | red_success mean [95% CI] | n seeds | missing |
|---|---|---|---|---|
| static_rules_decoy_blue | 1 | 16.800 [15.398, 18.200] | 10 | 0 |
| static_rules_passive_blue | 1 | 17.500 [16.000, 19.100] | 10 | 0 |
