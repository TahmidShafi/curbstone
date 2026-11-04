# curbstone — Data-Generating Process (DGP) Specification

**Version:** 0.1 (draft) · **Status:** for review before implementation
**Scope:** how one synthetic survey round is produced, how fraud is injected, and how ground truth is recorded.

Every parameter is tagged with its basis:

- **[DATA]** taken from a published source (cited inline; verify against the primary report before release)
- **[ASSUMPTION]** a modelling choice with no public calibration source; varied in experiments where it matters
- **[DESIGN]** chosen to make the experiment informative or computationally feasible

All values live in `config/params.yaml`; this document is the authority on their meaning.

---

## 0. Plain-language summary

We simulate a household survey in rural Bangladesh. Villages differ from one another (some are richer, some have larger families), and households inside a village resemble each other to a controllable degree. Enumerators are assigned to villages, each with a personal working speed and carefulness. Most enumerators are honest. A chosen fraction fabricate some of their interviews using one of five known tricks. Because we generate the data, we know exactly who fabricated what, which lets us measure how well the detector works instead of guessing.

The design deliberately creates *honest* situations that look like fraud (uniform villages, fast but honest staff, small households), because a detector that cannot tell these apart from real fraud would accuse honest people.

---

## 1. Population hierarchy

| Level | Count | Basis |
|---|---|---|
| Upazilas | 3 (selected from HDX COD-AB Bangladesh admin-3 boundaries) | [DESIGN] |
| Villages per upazila | 12 → 36 villages total | [DESIGN] |
| Households per village (sampling frame) | Uniform integer in [100, 300] | [ASSUMPTION] |
| Households interviewed per round | Determined by enumerator workloads (§4), ≈ 1,000–1,400 | [DESIGN] |

**Village location.** Each village centroid is a random point inside its upazila polygon, with a minimum separation of 1.5 km between centroids [DESIGN]. Upazila names are recorded from the HDX dataset; the specific upazilas are to be chosen at implementation time and listed here.

**Rationale.** Thirty-six villages give enough peer groups for comparison while keeping a round small enough to run in the browser.

---

## 2. Between-village heterogeneity

This section controls the main confounder of the project: an honest enumerator in a uniform village produces low-variance data that resembles fabrication.

### 2.1 Village effects

Each village *v* draws two independent effects:

- **Wealth effect** u_v ~ Normal(0, σ_u²), shared by all asset variables in that village.
- **Household-size effect** w_v ~ Normal(0, σ_w²), with σ_w = 0.15 [ASSUMPTION].

### 2.2 Intra-class correlation (ICC)

For assets, the household-level latent model is (§3.2):

logit P(own asset *k*) = α_k + u_v + β · z_h, with z_h ~ Normal(0, 1)

The latent-scale ICC is:

ICC = σ_u² / (σ_u² + β² + π²/3)

With β = 0.8 [ASSUMPTION], the residual variance is β² + π²/3 ≈ 0.64 + 3.29 = 3.93, giving:

| ICC level | Target ICC | σ_u² | σ_u | Basis |
|---|---|---|---|---|
| low | 0.05 | 0.207 | 0.455 | [ASSUMPTION] |
| medium | 0.15 | 0.694 | 0.833 | [ASSUMPTION] |
| high | 0.30 | 1.684 | 1.298 | [ASSUMPTION] |

No public source gives village-level ICCs for these assets in Bangladesh. The three levels therefore span near-homogeneous to strongly clustered villages and are treated as an experimental factor (§7), not a fixed truth.

---

## 3. Variables

### 3.1 Household size

hh_size = 1 + Poisson(λ_v), where λ_v = 3.30 · exp(w_v − σ_w²/2), truncated at 15.

- Target mean ≈ 4.3. **[DATA]** HIES 2022 rural average household size 4.30 (Bangladesh Bureau of Statistics, as reported by CEIC; verify against the HIES 2022 final report).
- The −σ_w²/2 term keeps the mean unchanged when village effects are added.

### 3.2 Asset ownership (binary)

The model is in §2.2. Intercepts α_k are **calibrated numerically** so that the marginal ownership rate matches the target. A naive α_k = logit(target) does not work: adding random effects on the logit scale shifts the mean toward 0.5.

| Variable (ODK-style name) | Target rate | Basis |
|---|---|---|
| `asset_mobile` | 0.974 | [DATA] BBS ICT Use and Access Survey 2022, households with a mobile phone (secondary report; verify) |
| `asset_tv` | 0.568 | [DATA] same survey, rural households with a television (secondary report; verify) |
| `asset_internet` | 0.381 | [DATA] same survey, households with home internet access, national (rural value to be confirmed) |
| `asset_radio` | 0.128 | [DATA] same survey, households with a radio, national |
| `asset_computer` | 0.087 | [DATA] same survey, households with a computer, national |

**Deviation from the original spec.** The project brief named the DHS API as the calibration source. The household-asset table from BDHS 2022 was not retrieved for this draft. Either (a) replace these values with BDHS 2022 household-possession indicators from STATcompiler, or (b) keep the BBS values and update the README accordingly. **Decision required.**

`asset_mobile` is kept on purpose. Near-universal ownership produces almost no variance in *any* village, so a working detector must not flag it. It serves as a negative control.

### 3.3 Age roster

- Household head age ~ Uniform integer [25, 70] [ASSUMPTION].
- Other members: spouse = head age + Normal(−5, 3), with children and others drawn from Uniform [0, head age − 15] [ASSUMPTION].
- **Age heaping (honest):** with probability h_e, a reported age is rounded to the nearest multiple of 5. h_e = 0.10 · exp(c_e), where c_e is the enumerator care effect (§4) [ASSUMPTION].

Purpose: terminal-digit tests need a realistic honest baseline of heaping. Without one, any heaping looks fraudulent.

### 3.4 Item non-response

Each asset item is "don't know" (code −8) with probability 0.01 · exp(−c_e) [ASSUMPTION]. Careful enumerators produce fewer missing values.

### 3.5 Interview duration (paradata)

log(duration_min) = μ + γ · hh_size + s_e + ε, with ε ~ Normal(0, 0.25²)

- γ = 0.05 per member; μ = ln(35) − 4γ, giving a median of ≈ 35 minutes for a 4-person household [ASSUMPTION].
- s_e = enumerator speed effect (§4).

No public paradata source is available, so all duration parameters are assumptions. The structure, not the exact values, is what matters: duration depends on household size and on the enumerator.

### 3.6 Timestamps

- A round lasts 10 working days, Sunday–Thursday, with Friday–Saturday as the weekend [ASSUMPTION].
- Working window 09:00–17:00, Asia/Dhaka [ASSUMPTION].
- Gap between consecutive interviews in the same village ~ Uniform [5, 20] min. A village change adds Uniform [30, 90] min [ASSUMPTION].
- One enumerator's interviews never overlap. Work that does not fit in a day spills to the next working day.

### 3.7 GPS

- True household location = village centroid + bivariate Normal(0, σ = 300 m) [ASSUMPTION].
- Recorded GPS = true location + device error Normal(0, σ = 10 m). `gps_accuracy` is drawn from Uniform [3, 25] m [ASSUMPTION].

### 3.8 Output schema (one row per submission)

`submission_id, round, enumerator_id, upazila_code, village_id, start_time, end_time, duration_min, gps_lat, gps_lon, gps_accuracy, hh_size, head_age, roster_ages (list), asset_mobile, asset_tv, asset_internet, asset_radio, asset_computer`

Column names follow ODK/KoboToolbox export conventions so that a real export could later be mapped onto the schema.

---

## 4. Enumerator model

| Parameter | Value | Basis |
|---|---|---|
| Number of enumerators | 40 | [DESIGN] |
| Villages per enumerator | Uniform integer [1, 3] | [DESIGN] |
| Constraint | Every village has ≥ 2 enumerators | [DESIGN] — guarantees each enumerator has comparable peers |
| Workload | Set by the experiment grid (§7); default Uniform integer [5, 60] | [DESIGN] |
| Speed effect s_e | Normal(0, 0.20²) on the log-duration scale | [ASSUMPTION] |
| Care effect c_e | Normal(0, 0.30²) | [ASSUMPTION] |

Honest enumerators differ from one another by construction. An honest enumerator with s_e = −0.4 (two standard deviations fast) completes interviews about 33% faster than average. Speed alone must therefore not be enough for a flag.

---

## 5. Fraud mechanisms

A fabricator has one **primary mode** and a **fabrication share** s ∈ (0, 1]: the fraction of their interviews that are fabricated. Primary modes are assigned via stratified sampling: cycling through a shuffled list of the 5 active modes (from the fraud stream), so that each mode appears once before any repeats. The other interviews are generated honestly. Fabricated interviews still go through the honest timestamp scheduler, apart from any duration change the mode itself makes.

| Mode | What the fabricator does | Trace in the data | Intensity parameter | Honest look-alike |
|---|---|---|---|---|
| **copy_paste** | Copies one of their own honest submissions and edits a few fields. Re-drawn binary fields often reproduce the original value, so the effective edit rate is below the nominal edit_rate. | Near-duplicate rows within an enumerator | edit_rate ∈ [0.1, 0.3]: probability each field is re-drawn | Similar households in a high-ICC village |
| **straight_lining** | Answers every asset item the same way (all yes or all no) | Zero within-record variance across assets | prob_straight ∈ [0.7, 1.0] per fabricated record | Very poor or very rich households, especially at high ICC |
| **rushed** | Real visit, but the interview is cut short | Short durations relative to household size | duration multiplier ∈ [0.3, 0.5] | Fast honest enumerators; small households |
| **invented_gps** | Fills forms from one location | GPS points clustered within ≈ 20 m, or identical coordinates | n_anchor_points ∈ {1, 2, 3} | Dense village cores; poor device accuracy |
| **too_average** | Enters the "typical" answer for each field | Low between-household variance; values close to the village mode | noise_sd ∈ [0, 0.2] around the modal value | Uniform villages (high ICC) |

### 5.1 Implementation rules

  R1 Trace isolation: each mode alters only the fields listed for it below; all
     other fields of a fabricated record are generated by the honest process.
     - copy_paste: hh_size, head_age, roster_ages, asset_*, gps_lat, gps_lon
     - straight_lining: asset_*
     - rushed: duration_min
     - invented_gps: gps_lat, gps_lon
     - too_average: asset_*, hh_size, roster_ages
  R2 Stream separation: fraud randomness uses its own child stream
     (numpy SeedSequence.spawn). With the same seed, every honest record is
     byte-identical whether fraud is on or off.
  R3 Pre-scheduling injection: modes that change duration are applied before
     timestamp scheduling, so no idle gaps are created.
  R4 Fabricator selection is independent of enumerator speed, care, workload and village.

**Held-out mode (not used during detector development):**

| Mode | What the fabricator does | Trace | Intensity |
|---|---|---|---|
| **partial_section** | Only the age roster is invented. Assets, GPS and duration are genuine. | Ages with heavy 0/5 heaping and low within-household age spread | heaping prob ∈ [0.5, 0.8] |

This mode is not implemented in the generator until all detectors are frozen. Its results are reported separately as the out-of-distribution test.

---

## 6. Ground-truth labels

Labels are written to a **separate file** (`truth/labels_round{r}.parquet`) that the detection engine never reads. Only the evaluation harness may read it. This prevents data leakage.

**Submission level:** `submission_id, is_fabricated (bool), fraud_mode (str or null)`

**Enumerator level:** `enumerator_id, fab_share, primary_mode, n_interviews`

**Positive class:** an enumerator is a fabricator if fab_share ≥ τ. Results are reported for τ ∈ {0.10, 0.25, 0.50} [DESIGN].

---

## 7. Experiment grid

| Factor | Levels | n |
|---|---|---|
| Fraud prevalence (share of enumerators who fabricate) | 0.02, 0.05, 0.10, 0.20 | 4 |
| Workload profile | low [5, 15], mixed [5, 60], high [40, 60] | 3 |
| ICC | low, medium, high | 3 |
| Fabrication share among fabricators | low U[0.2, 0.4], high U[0.6, 1.0] | 2 |

**72 configurations × 20 seeds = 1,440 simulated rounds.** At about 1,200 submissions each, the full grid is cheap in Python.

**Prevalence floor.** At 2% prevalence with 40 enumerators, the expected number of fabricators is 0.8. At least one fabricator is forced per round [DESIGN], and this is stated in the results.

**Separate scale test:** one round with 1,000,000 submissions (more enumerators and villages, same parameters), used only to measure rule-set latency in DuckDB-Wasm. The hardware is reported.

**Primary metrics (fixed before any detector exists):**

1. Precision@k and recall at a fixed back-check budget k (k = 10% of enumerators).
2. Precision–recall AUC per fraud mode.
3. False-flag rate among honest enumerators with fewer than 15 interviews.
4. Number of submissions before a fabricator crosses the flag threshold.

---

## 8. Known limitations

1. **Non-adaptive fraud.** Simulated fabricators follow fixed rules. Real fabricators learn which checks exist and avoid them, so detection rates here are likely an upper bound.
2. **Self-designed evaluation.** The same author designs the fraud and the detectors. The held-out mode (§5) reduces this risk but does not remove it.
3. **Calibration covers marginals only.** Target rates are national or rural averages. Regional variation, and correlations beyond the shared wealth factor, are not calibrated.
4. **Assumed paradata.** Duration, timing and GPS-error parameters have no public calibration source. Real paradata includes device clock errors, offline syncing and GPS dropouts that are not modelled.
5. **Secondary data sources.** The asset rates in §3.2 come from secondary reports of the BBS ICT survey and must be checked against the primary publication before release.
6. **Single primary mode per fabricator.** Real fabricators may mix strategies. Mixed-mode fraud is a planned extension.
7. **Modal knowledge in too_average.** too_average fabricators use the exact village modal values from the full frame; real fabricators know local norms only approximately, so this mode may be easier to detect than its real-world counterpart.
8. F3 treats roster_ages as one field; honest households with common sizes and asset profiles can match as near-duplicates.
9. Calibrated FDR control was not achieved (Scoring v1–v3); the delivered method is risk ranking with a fixed back-check budget.

---

## 9. Open decisions for the author

- [ ] Choose the 3 upazilas, and record their HDX codes in §1.
- [ ] Calibration source: BDHS 2022 (as in the original brief) or BBS ICT 2022 (this draft). See §3.2.
- [ ] Confirm the rural values for internet, radio and computer ownership.
- [ ] Confirm that 40 enumerators and 36 villages are acceptable for the demo dataset.

---

## 10. Scoring plan (Pre-registered)

Pre-registered hypothesis test directions and FDR control parameters:

| Feature | Feature Name | Direction | Rationale |
|---|---|---|---|
| **F1** | `duration_resid` | **low** | Fabricated interviews (e.g. rushed) have systematically negative duration residuals |
| **F2** | `throughput` | **high** | Fabricators achieve higher daily interview counts |
| **F3** | `near_dup` | **high** | Fabricated records duplicate answers, producing excess near-duplicates |
| **F4** | `straight_line` | **high** | Fabricators produce all-0 or all-1 asset blocks |
| **F5** | `asset_dispersion` | **low** | Fabricated/copied interviews have abnormally suppressed variance across assets |
| **F6** | `hhsize_dispersion` | **low** | Fabricators repeat modal/average household sizes with suppressed variance |
| **F7** | `gps_spread` | **low** | Faked or sofa-interview coordinates cluster with suppressed NN distances |
| **F8** | `age_heaping` | **high** | Fabricators disproportionately round reported ages to multiples of 5 |
| **F9** | `nonresponse` | **two-sided** | Fabricators may avoid non-response entirely or overuse "Don't know" (-8) |
| **F10** | `dur_size_coupling` | **two-sided** | Decoupled or distorted correlation between interview duration and household size |

- **FDR Control:** Benjamini–Hochberg procedure across all enumerators at false discovery rate target $q = 0.10$.
- **Sensitivity:** Benjamini–Yekutieli computed alongside BH under arbitrary dependence.
- **Enumerator-level decision:** Family-wise Bonferroni correction across valid non-NaN feature tests within enumerator ($p_e = \min(1, m_e \cdot \min_j p_{e,j})$).

### 10.1 Amendments

#### Amendment 1 (2026-11-04)
Reason: honest-only calibration failure (20/20 null rounds flagged), caused by (a) continuous-feature SEs omitting between-enumerator variance, (b) overdispersion estimates inflated by outlying enumerators. Changes were evaluated on honest-only data only; fraud-round results were not used to choose them.

- **B1 Continuous features (F1, F2, F5, F6, F7, F10):** Random-effects SE. $d_e$ = feature estimate (value - peer_value, or value - null), $s_e$ = within-enumerator SE. Estimate $\tau^2$ per feature per round with DerSimonian–Laird after excluding enumerators with $|d_e / s_e|$ above the 90th percentile (one trim pass, no truth). $z_e = d_e / \sqrt{\tau^2 + s_e^2}$. Shrunk estimate $= d_e \cdot \tau^2 / (\tau^2 + s_e^2)$ stored with 90% interval.
- **B2 Count features (F3, F4, F8, F9):** Estimate $\rho$ by method of moments after a one-pass trim (exclude enumerators whose plain-binomial $p < 0.01$ in the pre-registered direction).
- **B3 Skipped cells:** Skipped cells for F5, F6, and F7 must evaluate to NaN, never 0; enumerators with NaN for a feature simply have fewer tests ($m_e$).
- **B4 Survey-wide baseline floor:** Count features floor local peer expectation at the survey-wide mean: $p_{\text{floor}} = \max(10^{-4}, \sum k_{\text{exp}} / \sum n)$, $p0_e = \max(k_{\text{exp}} / n, p_{\text{floor}})$.

#### Amendment 2 (2026-11-04)
Reason: Amendment 1 failed honest-only acceptance.
Diagnosis: (a) trimming before DerSimonian–Laird truncates the honest distribution and underestimates tau^2; (b) pooled rho for F3 is inflated by fabricators and ignores pairing of near-duplicates; (c) the survey-wide floor replaced local rates with the survey mean, not only zero rates; (d) acceptance was checked at p<0.05 while flags occur near p<0.001, and its lower bound wrongly penalised discrete conservativeness. All changes evaluated on honest-only data only.
Stopping rule: this is the final design amendment. If acceptance fails, the pre-specified fallback (empirical-null recalibration) is applied and reported.

- **C1 Continuous features (F1, F2, F5, F6, F7, F10):** No trimming. $\tau^2 = \max(0, (1.4826 \cdot \text{MAD}(d))^2 - \text{median}(s_e^2))$ per feature per round. $z_e = d_e / \sqrt{\tau^2 + s_e^2}$. Shrunk estimate $= d_e \cdot \tau^2 / (\tau^2 + s_e^2)$ and 90% interval as in Amendment 1.
- **C2 F3 (`near_dup`):** Increase workload-matched null draws to $B = 200$. From the null draws take mean $\mu_e$ and variance $v_e$ of $k$. Fit a beta-binomial for $e$ by moments (mean $\mu_e / n$, variance $v_e$); if $v_e \le \text{binomial variance}$, use plain binomial. $p = P(K \ge k_{\text{obs}})$. No pooled $\rho$ for F3.
- **C3 F4, F8, F9:** Remove the floor. Smoothed $p0_e = (k_{\text{exp}} + p_s) / (n + 1)$, where $p_s = \sum k_{\text{exp}} / \sum n$ (one pseudo-observation). Retain the B2 trimmed $\rho$.
- **C4 Skipped cells:** Ensure skipped cells are NaN for F5, F6, and F7 (B3).

### 10.2 Results — Scoring v1

Under the pre-registered stopping rule, calibrated FDR flagging was not achieved. v1 is retained for reference; v2 is a post-hoc track.

#### Acceptance Check: Amendment 2 Baseline (`empirical_null=False`)
Evaluation across honest-only rounds (seeds 0..19, medium ICC):

| Feature | Non-NaN Tests | Share $p < 0.05$ (target $\le 0.08$) | Share $p < 0.01$ (target $\le 0.02$) | Share $p < 0.001$ (target $\le 0.004$) | Status |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **F1** | 800 | 0.0425 | 0.0112 | 0.0050 | FAIL |
| **F2** | 800 | 0.0325 | 0.0050 | 0.0000 | PASS |
| **F3** | 800 | 0.1787 | 0.1713 | 0.1650 | FAIL |
| **F4** | 800 | 0.2238 | 0.0887 | 0.0138 | FAIL |
| **F5** | 484 | 0.0455 | 0.0124 | 0.0021 | PASS |
| **F6** | 484 | 0.0372 | 0.0083 | 0.0000 | PASS |
| **F7** | 775 | 0.0594 | 0.0258 | 0.0103 | FAIL |
| **F8** | 800 | 0.0725 | 0.0288 | 0.0125 | FAIL |
| **F9** | 800 | 0.2188 | 0.1350 | 0.0725 | FAIL |
| **F10** | 800 | 0.0488 | 0.0225 | 0.0075 | FAIL |

- Rounds with $\ge 1$ BH flag: 20 / 20 (target $\le 4$). Decision: REJECT.

#### Acceptance Check: Amendment 2 + Empirical-Null Fallback (`empirical_null=True`)
Evaluation across honest-only rounds (seeds 0..19, medium ICC):

| Feature | Non-NaN Tests | Share $p < 0.05$ (target $\le 0.08$) | Share $p < 0.01$ (target $\le 0.02$) | Share $p < 0.001$ (target $\le 0.004$) | Status |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **F1** | 800 | 0.0462 | 0.0125 | 0.0050 | FAIL |
| **F2** | 800 | 0.0425 | 0.0088 | 0.0013 | PASS |
| **F3** | 800 | 0.1787 | 0.1713 | 0.1650 | FAIL |
| **F4** | 800 | 0.2238 | 0.0887 | 0.0138 | FAIL |
| **F5** | 484 | 0.0413 | 0.0103 | 0.0083 | FAIL |
| **F6** | 484 | 0.0847 | 0.0372 | 0.0165 | FAIL |
| **F7** | 775 | 0.0581 | 0.0258 | 0.0090 | FAIL |
| **F8** | 800 | 0.0725 | 0.0288 | 0.0125 | FAIL |
| **F9** | 800 | 0.2188 | 0.1350 | 0.0725 | FAIL |
| **F10** | 800 | 0.0612 | 0.0275 | 0.0125 | FAIL |

- Rounds with $\ge 1$ BH flag: 20 / 20 (target $\le 4$). Decision: REJECT.





## 11. Scoring v2 (post-hoc)

- **Primary output:** Enumerator ranking by risk score (risk_score = -log10 p_e); primary metric is precision@k (k = 10% of enumerators, k = 4 for 40 enumerators) and recall@k, as pre-specified in §7.
- **Data split:** Development seeds 0..19 and 42 are burned. Scoring v2 evaluation uses strictly held-out seeds:
  - Seeds 100..119: held-out honest-only null calibration.
  - Seeds 200..219: held-out fraud evaluation (prevalence 0.125).

### 11.1 Methodological Changes in v2

- **V1 F3 defect fix (near_dup):**
  - Count observed near-duplicates strictly *within* cells (e, v) (same footing as the null resampling distribution).
  - Smooth the expected rate identically to other count features: p_s = sum(mu_e) / sum(n), p0_e = (mu_e + p_s) / (n + 1).
  - Beta-Binomial variance estimate: v_eff = max(v_e, binomial var at p0_e) where binomial var = n * p0_e * (1 - p0_e). Overdispersion rho_e estimated from moments with variance floor.
- **V2 F4, F8, F9 (count features):**
  - Estimate overdispersion rho by method of moments across all enumerators *without trimming* (retaining the full empirical spread, analogous to C1 for continuous features).
- **V3 Continuous features (F1, F2, F5, F6, F7, F10):**
  - Compute p-values from the Student-t distribution with degrees of freedom df = (number of enumerators with non-NaN d) - 1 instead of standard normal (Z), accounting for finite-sample reference dispersion uncertainty.
- **FDR flags:**
  - FDR flags are secondary; claim FDR control only if honest-only acceptance (same criteria as Amendment 2: share p < 0.05 <= 0.08, share p < 0.01 <= 0.02, share p < 0.001 <= 0.004, and <= 4 / 20 rounds with flags) passes on held-out seeds 100..119.


## 12. Scoring v3 (post-hoc, final)

Scoring v3 (post-hoc, final). Reason: v2 count features failed honest calibration because peer expected counts for rare events were zero and the one-pseudo-observation smoothing was too weak. M = 50 is fixed before seeing any v3 results. After v3, scoring is frozen permanently regardless of outcome. Evaluation uses fresh seeds only: 300..319 (honest), 400..419 (fraud, prevalence 0.125).

### 12.1 Methodological Changes in v3

- **Shrink cell-level peer rate toward survey rate (F3, F4, F8, F9):**
  - Peer rate in each cell (e, v) shrunk with M = 50 pseudo-trials toward survey rate p_s:
    p_peer = (k_peer + M * p_s) / (n_peer + M)
  - Expected count for enumerator e: mu_e = sum_{v in V_e} n_ev * p_peer.
- **F3 near-dup adjustments:**
  - Retain the workload-matched null draws, but floor mu_e at the expected count from the shrunk peer rate: mu_e = max(mu_e_null, sum_v n_ev * p_peer).
  - Variance: v_e = max(v_e, beta-binomial variance at that mean).
- **Count model smoothing removal:**
  - Remove the (k_exp + p_s)/(n + 1) smoothing at the enumerator level since expectation is already shrunk at the cell level: p0_e = k_exp / n_e.
- **Overdispersion and continuous features:**
  - Estimate rho by method of moments across all enumerators untrimmed (as in v2).
  - Continuous features remain unchanged from v2 (robust tau^2 without trimming, Student-t distribution with df = N_d - 1).
