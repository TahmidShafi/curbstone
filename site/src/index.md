---
title: Demo
---

# Curbstone

Which enumerators should field supervisors back-check first? A risk ranking for likely fabricated survey interviews, demonstrated on synthetic data with known ground truth.

<div class="text-meta" style="margin-bottom: 16px;">
  Synthetic data &bull; seeds fixed before results were viewed &bull; <a href="./method">Method</a> &bull; <a href="./results">Results</a>
</div>

```js
import { allocateBackChecks } from "./components/allocator.js";
import { renderRiskTable } from "./components/riskTable.js";
import { renderEvidenceDrawer } from "./components/evidenceDrawer.js";
import { toRows, formatPrecisionStat, downloadAllocationCsv } from "./components/demoHelpers.js";

const mixedData = {
  design: await FileAttachment("./data/mixed/design.json").json(),
  roundMetrics: await FileAttachment("./data/mixed/round_metrics.json").json(),
  ruleHitsByEnum: await FileAttachment("./data/mixed/rule_hits_by_enumerator.json").json(),
  scoresShrinkage: toRows(await FileAttachment("./data/mixed/mixed_scores_shrinkage.parquet").parquet()),
  scoresNoshrinkage: toRows(await FileAttachment("./data/mixed/mixed_scores_noshrinkage.parquet").parquet()),
  evidenceShrinkage: await FileAttachment("./data/mixed/evidence.json").json(),
  evidenceNoshrinkage: await FileAttachment("./data/mixed/evidence_noshrinkage.json").json(),
  submissions: toRows(await FileAttachment("./data/mixed/mixed_submissions.parquet").parquet()),
  villages: toRows(await FileAttachment("./data/mixed/mixed_villages.parquet").parquet()),
  flagsCsvHref: await FileAttachment("./data/mixed/flags.csv").href,
  flagsDtaHref: await FileAttachment("./data/mixed/flags.dta").href,
};

const lowData = {
  design: await FileAttachment("./data/low/design.json").json(),
  roundMetrics: await FileAttachment("./data/low/round_metrics.json").json(),
  ruleHitsByEnum: await FileAttachment("./data/low/rule_hits_by_enumerator.json").json(),
  scoresShrinkage: toRows(await FileAttachment("./data/low/low_scores_shrinkage.parquet").parquet()),
  scoresNoshrinkage: toRows(await FileAttachment("./data/low/low_scores_noshrinkage.parquet").parquet()),
  evidenceShrinkage: await FileAttachment("./data/low/evidence.json").json(),
  evidenceNoshrinkage: await FileAttachment("./data/low/evidence_noshrinkage.json").json(),
  submissions: toRows(await FileAttachment("./data/low/low_submissions.parquet").parquet()),
  villages: toRows(await FileAttachment("./data/low/low_villages.parquet").parquet()),
  flagsCsvHref: await FileAttachment("./data/low/flags.csv").href,
  flagsDtaHref: await FileAttachment("./data/low/flags.dta").href,
};
```

```js
const scenarioInput = Inputs.radio(["mixed", "low"], {
  value: "mixed",
  format: (x) => x === "mixed" ? "Mixed workload (5–60 interviews)" : "Low workload (5–15)"
});
const shrinkageInput = Inputs.toggle({ value: true, label: "Empirical-Bayes shrinkage" });
const budgetInput = Inputs.range([10, 200], { value: 60, step: 5 });
const floorShareInput = Inputs.range([0, 50], { value: 20, step: 5 });
const revealButton = Inputs.button("Reveal ground truth");
const allocSeedInput = Inputs.number({ value: 42, step: 1, label: "Allocator seed" });

const budgetValSpan = html`<span class="tabular-nums" style="font-weight: 600; color: var(--ink);">60 interviews</span>`;
budgetInput.addEventListener("input", () => { budgetValSpan.textContent = `${budgetInput.value} interviews`; });

const floorValSpan = html`<span class="tabular-nums" style="font-weight: 600; color: var(--ink);">20%</span>`;
floorShareInput.addEventListener("input", () => { floorValSpan.textContent = `${floorShareInput.value}%`; });

display(html`
<div class="control-panel">
  <div class="control-row control-row-1">
    <div class="control-item"><div class="control-label">Scenario</div><div class="segmented-control">${scenarioInput}</div></div>
    <div class="control-item"><div class="control-label">Shrinkage</div><div>${shrinkageInput}</div></div>
  </div>
  <div class="control-row control-row-2">
    <div class="control-item"><div class="control-label">Back-check budget: ${budgetValSpan}</div><div>${budgetInput}</div></div>
    <div class="control-item"><div class="control-label">Random floor: ${floorValSpan}</div><div>${floorShareInput}</div></div>
    <div class="control-item control-item-btn"><div class="reveal-btn">${revealButton}</div></div>
  </div>
</div>
<details style="margin: 8px 0 16px 0; font-size: 13px;">
  <summary style="cursor: pointer; color: var(--muted); font-weight: 500;">Advanced</summary>
  <div style="padding-top: 8px; max-width: 200px;">${allocSeedInput}</div>
</details>`);

const scenario = Generators.input(scenarioInput);
const shrinkageOn = Generators.input(shrinkageInput);
const budget = Generators.input(budgetInput);
const floorShare = Generators.input(floorShareInput);
const allocSeed = Generators.input(allocSeedInput);
const revealCount = Generators.input(revealButton);
```

```js
const activeData = scenario === "mixed" ? mixedData : lowData;
const design = activeData.design;
const roundMetrics = activeData.roundMetrics;
const rawScores = shrinkageOn ? activeData.scoresShrinkage : activeData.scoresNoshrinkage;
const evidenceDict = shrinkageOn ? activeData.evidenceShrinkage : activeData.evidenceNoshrinkage;
const submissions = activeData.submissions;
const villages = activeData.villages;

const isRevealed = revealCount > 0;
const truthData = isRevealed
  ? await (scenario === "mixed" ? FileAttachment("./data/mixed/truth.json").json() : FileAttachment("./data/low/truth.json").json())
  : null;

const truthMap = new Map();
if (truthData) {
  for (const t of truthData) truthMap.set(t.enumerator_id, t);
}

const evidenceSubmissionIds = new Set();
for (const [eId, eInfo] of Object.entries(evidenceDict)) {
  for (const f of Object.values(eInfo.features || {})) {
    for (const sid of f.submission_ids || []) evidenceSubmissionIds.add(sid);
  }
}

const enumeratorList = rawScores.map(r => ({
  id: r.enumerator_id,
  n: Number(r.n_interviews),
  risk: Number(r.risk_score)
}));

const allocation = allocateBackChecks({
  enumerators: enumeratorList,
  submissions: submissions,
  evidenceIds: Array.from(evidenceSubmissionIds),
  budget: budget,
  floorShare: floorShare / 100.0,
  seed: allocSeed,
});
```

```js
display(html`
<div class="stat-strip">
  <div class="stat-tile">
    <div class="stat-value">${rawScores.length}</div>
    <div class="stat-label">Enumerators</div>
  </div>
  <div class="stat-tile">
    <div class="stat-value">${submissions.length.toLocaleString()}</div>
    <div class="stat-label">Interviews</div>
  </div>
  <div class="stat-tile">
    <div class="stat-value">${allocation.totalAllocated}</div>
    <div class="stat-label">Back-checks allocated (${allocation.floorAllocated} random + ${allocation.riskAllocated} risk-weighted)</div>
  </div>
  <div class="stat-tile">
    <div class="stat-value">
      ${!isRevealed ? "—" : (shrinkageOn ? roundMetrics.round_hits_v3 : roundMetrics.round_hits_noshrinkage) + " of 4"}
    </div>
    <div class="stat-label">
      ${!isRevealed ? "Precision@4 — shown after reveal" : formatPrecisionStat(roundMetrics, shrinkageOn)}
    </div>
  </div>
</div>

<div class="stat-note">
  Single rounds vary. Toggle shrinkage and reveal ground truth to see this round's trade-off; study-level effects are on the Results page.
</div>

<details style="margin: 8px 0 16px 0;">
  <summary style="cursor: pointer; font-size: 13px; font-weight: 600; color: var(--ink);">Simulation settings</summary>
  <dl class="sim-settings">
    <dt>Seed</dt><dd><code>${design.seed}</code></dd>
    <dt>Workload</dt><dd>${design.workload_profile} [${design.workload_range.join("–")}]</dd>
    <dt>Enumerators</dt><dd>${design.n_enumerators}</dd>
    <dt>Prevalence</dt><dd>${design.prevalence} (12.5% fabricators)</dd>
    <dt>ICC</dt><dd>${design.icc_level} (0.15)</dd>
    <dt>Fraud modes</dt><dd>copy-paste, straight-lining, rushed, invented GPS, too-average</dd>
  </dl>
</details>
`);
```

```js
const sortedScores = [...rawScores].sort((a, b) => {
  if (b.risk_score !== a.risk_score) return b.risk_score - a.risk_score;
  return a.enumerator_id.localeCompare(b.enumerator_id);
});

const tableRows = sortedScores.map((r, idx) => {
  const eId = r.enumerator_id;
  const evInfo = evidenceDict[eId] || {};
  const evFeatures = Object.keys(evInfo.features || {});
  
  let strongestEst = null, ciLo = null, ciHi = null;
  if (evFeatures.length > 0) {
    const fData = evInfo.features[evFeatures[0]];
    const isCount = ["F3", "F4", "F8", "F9"].includes(evFeatures[0]);
    strongestEst = isCount ? (fData.observed_rate ?? fData.feature_estimate) : (fData.feature_estimate ?? fData.shrunk_estimate);
    const rng = fData.honest_range_90 ?? (fData.honest_halfwidth != null ? [-fData.honest_halfwidth, fData.honest_halfwidth] : fData.ci_90);
    if (rng) [ciLo, ciHi] = rng;
  }

  let truthLabel = "TN";
  if (isRevealed) {
    const isFab = Boolean(truthMap.get(eId)?.is_fabricator);
    truthLabel = idx < 4 ? (isFab ? "TP" : "FP") : (isFab ? "FN" : "TN");
  }

  return {
    rank: idx + 1,
    enumerator_id: eId,
    n: Number(r.n_interviews),
    risk_score: Number(r.risk_score),
    evidence: r.evidence || "",
    strongest_est: strongestEst,
    strongest_ci_low: ciLo,
    strongest_ci_high: ciHi,
    rule_hits: Number(activeData.ruleHitsByEnum[eId] ?? 0),
    allocated_backchecks: allocation.allocatedCounts[eId] || 0,
    truth_label: truthLabel,
  };
});

display(renderRiskTable({
  scenario: scenario,
  rows: tableRows,
  isRevealed: isRevealed,
  evidenceDict: evidenceDict,
  submissions: submissions,
  villages: villages,
  drawerRenderer: renderEvidenceDrawer,
}));
```

```js
const staticCsvHref = scenario === "mixed" ? mixedData.flagsCsvHref : lowData.flagsCsvHref;
const staticDtaHref = scenario === "mixed" ? mixedData.flagsDtaHref : lowData.flagsDtaHref;

display(html`
<div class="downloads-row">
  <span>Download:</span>
  <a href="#" onclick=${(e) => { e.preventDefault(); downloadAllocationCsv(allocation.selectedSubmissions, scenario, budget); }}>allocation (CSV)</a> &bull;
  <a href="${staticCsvHref}" download>flags (CSV)</a> &bull;
  <a href="${staticDtaHref}" download>flags (Stata .dta)</a>
</div>
`);
```
