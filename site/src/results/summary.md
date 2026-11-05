# Robustness Study Summary (Frozen Engine Scoring v3)

Full evaluation across 72 factorial configurations (1,440 rounds, seeds 1000..1019), held-out mode evaluation (seeds 2000..2019), and detection-time evaluation (seeds 3000..3019).

## 1. Precision@k by Workload Profile and Fraud Prevalence

| Workload   |   Prevalence |   Max Achievable |   Scoring v3 (Mean) |   v3 Rel. Prec. | v3 10th-90th     |   No-Shrink (Mean) |   No-Shrink Rel. Prec. |   Rules (Mean) |   Rules Rel. Prec. |
|:-----------|-------------:|-----------------:|--------------------:|----------------:|:-----------------|-------------------:|-----------------------:|---------------:|-------------------:|
| Low        |         0.02 |             0.25 |              0.0979 |          0.3917 | [0.0000, 0.2500] |             0.0979 |                 0.3917 |         0.0625 |             0.25   |
| Low        |         0.05 |             0.5  |              0.2854 |          0.5708 | [0.0000, 0.5000] |             0.2812 |                 0.5625 |         0.1417 |             0.2833 |
| Low        |         0.1  |             1    |              0.4938 |          0.4938 | [0.2500, 0.7500] |             0.3792 |                 0.3792 |         0.3563 |             0.3563 |
| Low        |         0.2  |             1    |              0.7042 |          0.7042 | [0.2500, 1.0000] |             0.5458 |                 0.5458 |         0.6125 |             0.6125 |
| Mixed      |         0.02 |             0.25 |              0.1375 |          0.55   | [0.0000, 0.2500] |             0.15   |                 0.6    |         0.0625 |             0.25   |
| Mixed      |         0.05 |             0.5  |              0.275  |          0.55   | [0.0000, 0.5000] |             0.2771 |                 0.5542 |         0.1479 |             0.2958 |
| Mixed      |         0.1  |             1    |              0.4688 |          0.4688 | [0.2500, 0.7500] |             0.5167 |                 0.5167 |         0.3375 |             0.3375 |
| Mixed      |         0.2  |             1    |              0.7729 |          0.7729 | [0.5000, 1.0000] |             0.7333 |                 0.7333 |         0.5875 |             0.5875 |
| High       |         0.02 |             0.25 |              0.1521 |          0.6083 | [0.0000, 0.2500] |             0.15   |                 0.6    |         0.0479 |             0.1917 |
| High       |         0.05 |             0.5  |              0.2792 |          0.5583 | [0.0000, 0.5000] |             0.2875 |                 0.575  |         0.1875 |             0.375  |
| High       |         0.1  |             1    |              0.5229 |          0.5229 | [0.2500, 0.7500] |             0.5729 |                 0.5729 |         0.2812 |             0.2812 |
| High       |         0.2  |             1    |              0.8021 |          0.8021 | [0.5000, 1.0000] |             0.775  |                 0.775  |         0.5979 |             0.5979 |

## 2. Per-Mode Recall@k with Wilson 95% CIs and Counts (including Held-Out `partial_section`)

| Mode            | Type                           |   Evaluated Rounds | Scoring v3 (x/n [95% CI])          | No-Shrinkage (x/n [95% CI])        | Rules Baseline (x/n [95% CI])     |
|:----------------|:-------------------------------|-------------------:|:-----------------------------------|:-----------------------------------|:----------------------------------|
| copy_paste      | Standard Active                |                756 | 950/990 (0.9596) [0.9454, 0.9702]  | 741/990 (0.7485) [0.7205, 0.7745]  | 817/990 (0.8253) [0.8004, 0.8476] |
| straight_lining | Standard Active                |                900 | 411/1116 (0.3683) [0.3405, 0.3970] | 630/1116 (0.5645) [0.5353, 0.5933] | 85/1116 (0.0762) [0.0620, 0.0932] |
| rushed          | Standard Active                |                846 | 343/990 (0.3465) [0.3175, 0.3766]  | 359/990 (0.3626) [0.3333, 0.3931]  | 621/990 (0.6273) [0.5967, 0.6568] |
| invented_gps    | Standard Active                |                846 | 561/1026 (0.5468) [0.5162, 0.5770] | 498/1026 (0.4854) [0.4549, 0.5160] | 72/1026 (0.0702) [0.0561, 0.0875] |
| too_average     | Standard Active                |                972 | 131/1278 (0.1025) [0.0870, 0.1203] | 60/1278 (0.0469) [0.0366, 0.0600]  | 48/1278 (0.0376) [0.0284, 0.0494] |
| partial_section | Held-Out (Out-of-Distribution) |                 15 | 11/15 (0.7333) [0.4805, 0.8910]    | 7/15 (0.4667) [0.2481, 0.6988]     | 1/15 (0.0667) [0.0119, 0.2982]    |

## 3. Detection Rate over Time by Working Day (Prevalence 0.10, k=4)

| Mode            | Day 2                | Day 4                | Day 6                | Day 8                | Day 10               |
|:----------------|:---------------------|:---------------------|:---------------------|:---------------------|:---------------------|
| copy_paste      | 18/18 [0.824, 1.000] | 18/18 [0.824, 1.000] | 18/18 [0.824, 1.000] | 18/18 [0.824, 1.000] | 18/18 [0.824, 1.000] |
| straight_lining | 12/16 [0.505, 0.898] | 11/16 [0.444, 0.858] | 11/16 [0.444, 0.858] | 11/16 [0.444, 0.858] | 11/16 [0.444, 0.858] |
| rushed          | 3/15 [0.070, 0.452]  | 5/15 [0.152, 0.583]  | 3/15 [0.070, 0.452]  | 3/15 [0.070, 0.452]  | 3/15 [0.070, 0.452]  |
| invented_gps    | 7/15 [0.248, 0.699]  | 11/15 [0.480, 0.891] | 12/15 [0.548, 0.930] | 12/15 [0.548, 0.930] | 12/15 [0.548, 0.930] |
| too_average     | 1/16 [0.011, 0.283]  | 1/16 [0.011, 0.283]  | 1/16 [0.011, 0.283]  | 1/16 [0.011, 0.283]  | 1/16 [0.011, 0.283]  |

## 4. Small-n Protection (Honest False Flags with n < 15 in Top-4)

| Workload Profile         |   Total Slots | Scoring v3 (x/Total [Share])   | No-Shrinkage (x/Total [Share])   | Rules Baseline (x/Total [Share])   | v3 - No-Shrinkage (Paired 95% CI)   |
|:-------------------------|--------------:|:-------------------------------|:---------------------------------|:-----------------------------------|:------------------------------------|
| Low Workload [5, 15]     |          1920 | 1037/1920 (0.5401)             | 1139/1920 (0.5932)               | 1198/1920 (0.6240)                 | -0.0531 [-0.0708, -0.0359]          |
| Mixed Workload [5, 60]   |          1920 | 196/1920 (0.1021)              | 66/1920 (0.0344)                 | 53/1920 (0.0276)                   | +0.0677 [+0.0552, +0.0807]          |
| High Workload [40, 60]   |          1920 | 0/1920 (0.0000)                | 0/1920 (0.0000)                  | 0/1920 (0.0000)                    | +0.0000 [+0.0000, +0.0000]          |
| Overall (All 72 Configs) |          5760 | 1233/5760 (0.2141)             | 1205/5760 (0.2092)               | 1251/5760 (0.2172)                 | +0.0049 [-0.0026, +0.0127]          |

## 5. Held-Out `partial_section` Evidence Feature Attribution

Across the 20 holdout evaluation rounds (seeds 2000..2019), 15 fabricators were assigned the out-of-distribution `partial_section` mode. Scoring v3 successfully detected 11 of the 15 fabricators (73.33% recall). Breakdown of features appearing in evidence:

| Feature | Description | Appearances in Evidence | Share of Detected (x/11) | Share of All (x/15) |
|:---|:---|:---:|:---:|:---:|
| **F8** | Age heaping (multiples of 5) | 10 | 90.9% | 66.7% |
| **F7** | GPS clustering / dispersion | 1 | 9.1% | 6.7% |

> In 10 of 11 detections, Feature F8 was the primary attribution feature, exactly aligning with the data generating process where only `roster_ages` was invented with age heaping.

## 6. Statistical Significance and Bootstrap Confidence Intervals

| Metric / Subset                           | v3 - Rules (Mean [95% CI])   | v3 - No-Shrinkage (Mean [95% CI])   |
|:------------------------------------------|:-----------------------------|:------------------------------------|
| Precision@4 (Low Workload [5, 15])        | +0.1021 [+0.0828, +0.1219]   | +0.0693 [+0.0521, +0.0865]          |
| Precision@4 (Mixed Workload [5, 60])      | +0.1297 [+0.1104, +0.1495]   | -0.0057 [-0.0214, +0.0099]          |
| Precision@4 (High Workload [40, 60])      | +0.1604 [+0.1385, +0.1823]   | -0.0073 [-0.0219, +0.0078]          |
| Precision@4 (Overall (All 72 Configs))    | +0.1307 [+0.1191, +0.1422]   | +0.0187 [+0.0094, +0.0281]          |
| Average Precision (Overall)               | +0.1946 [+0.1783, +0.2110]   | +0.0369 [+0.0257, +0.0480]          |
| Average Precision (Mode: copy_paste)      | +0.1725 [+0.1487, +0.1972]   | +0.2237 [+0.2035, +0.2440]          |
| Average Precision (Mode: straight_lining) | +0.3373 [+0.3145, +0.3603]   | -0.1152 [-0.1417, -0.0886]          |
| Average Precision (Mode: rushed)          | -0.2032 [-0.2326, -0.1734]   | -0.0498 [-0.0708, -0.0285]          |
| Average Precision (Mode: invented_gps)    | +0.4612 [+0.4312, +0.4916]   | +0.0572 [+0.0430, +0.0720]          |
| Average Precision (Mode: too_average)     | +0.1271 [+0.1097, +0.1450]   | +0.0939 [+0.0765, +0.1109]          |

## 7. Figures

- Figure 1: Small-workload honest false-flag counts: ![small_n_honest.png](small_n_honest.png)
- Figure 2: Fabricator detection rate over time with Wilson 95% CIs: ![detection_by_day.png](detection_by_day.png)
