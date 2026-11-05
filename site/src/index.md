# Curbstone Quality Audit Demo

Detect likely fabricated survey interviews (curbstoning) at the enumerator level and allocate field back-checks using empirical Bayes shrinkage risk ranking.

```js
import { allocateBackChecks } from "./components/allocator.js";
import { renderRiskTable } from "./components/riskTable.js";
import { renderEvidenceDrawer } from "./components/evidenceDrawer.js";

// Helper to convert Apache Arrow tables to plain objects with number types and plain arrays
const toRows = (t) => Array.from(t, (r) => {
  const o = r.toJSON();
  for (const k in o) {
    if (typeof o[k] === "bigint") {
      o[k] = Number(o[k]);
    } else if (Array.isArray(o[k])) {
      o[k] = o[k].map(v => typeof v === "bigint" ? Number(v) : v);
    } else if (o[k] != null && typeof o[k] === "object" && typeof o[k][Symbol.iterator] === "function") {
      o[k] = Array.from(o[k], v => typeof v === "bigint" ? Number(v) : v);
    }
  }
  return o;
});

// Static file attachments across scenarios
const mixedData = {
  design: await FileAttachment("./data/mixed/design.json").json(),
  roundMetrics: await FileAttachment("./data/mixed/round_metrics.json").json(),
  scoresShrinkage: toRows(await FileAttachment("./data/mixed/scores_shrinkage.parquet").parquet()),
  scoresNoshrinkage: toRows(await FileAttachment("./data/mixed/scores_noshrinkage.parquet").parquet()),
  evidenceShrinkage: await FileAttachment("./data/mixed/evidence.json").json(),
  evidenceNoshrinkage: await FileAttachment("./data/mixed/evidence_noshrinkage.json").json(),
  submissions: toRows(await FileAttachment("./data/mixed/submissions.parquet").parquet()),
  villages: toRows(await FileAttachment("./data/mixed/villages.parquet").parquet()),
  flagsCsvHref: await FileAttachment("./data/mixed/flags.csv").href,
  flagsDtaHref: await FileAttachment("./data/mixed/flags.dta").href,
};

const lowData = {
  design: await FileAttachment("./data/low/design.json").json(),
  roundMetrics: await FileAttachment("./data/low/round_metrics.json").json(),
  scoresShrinkage: toRows(await FileAttachment("./data/low/scores_shrinkage.parquet").parquet()),
  scoresNoshrinkage: toRows(await FileAttachment("./data/low/scores_noshrinkage.parquet").parquet()),
  evidenceShrinkage: await FileAttachment("./data/low/evidence.json").json(),
  evidenceNoshrinkage: await FileAttachment("./data/low/evidence_noshrinkage.json").json(),
  submissions: toRows(await FileAttachment("./data/low/submissions.parquet").parquet()),
  villages: toRows(await FileAttachment("./data/low/villages.parquet").parquet()),
  flagsCsvHref: await FileAttachment("./data/low/flags.csv").href,
  flagsDtaHref: await FileAttachment("./data/low/flags.dta").href,
};
```

```js
const scenarioInput = Inputs.radio(["mixed", "low"], {
  value: "mixed",
  label: "Workload Scenario:",
  format: (x) => x === "mixed" ? "Mixed Workload [5, 60] (Seed 5000)" : "Low Workload [5, 15] (Seed 5001)"
});
const shrinkageInput = Inputs.toggle({
  value: true,
  label: "Empirical Bayes Shrinkage (Scoring v3):"
});

display(html`<div class="grid grid-cols-2" style="margin-top: 16px;">
  <div>${scenarioInput}</div>
  <div>${shrinkageInput}</div>
</div>`);

const scenario = Generators.input(scenarioInput);
const shrinkageOn = Generators.input(shrinkageInput);
```

```js
const activeData = scenario === "mixed" ? mixedData : lowData;
const design = activeData.design;
const roundMetrics = activeData.roundMetrics;
const rawScores = shrinkageOn ? activeData.scoresShrinkage : activeData.scoresNoshrinkage;
const evidenceDict = shrinkageOn ? activeData.evidenceShrinkage : activeData.evidenceNoshrinkage;
const submissions = activeData.submissions;
const villages = activeData.villages;
```

```js
function formatComparison(rm, isShrink) {
  const roundHits = isShrink ? rm.round_hits_v3 : rm.round_hits_noshrinkage;
  const comp = rm.study_average;
  if (!comp) return `This round: ${roundHits} of 4.`;

  if (rm.scenario === "mixed") {
    const mean = isShrink ? comp.v3_mean : comp.noshrink_mean;
    const ci = isShrink ? comp.v3_ci_95 : comp.noshrink_ci_95;
    return `This round: ${roundHits} of 4. Study average at comparable settings: ${mean.toFixed(3)} [${ci[0].toFixed(3)}, ${ci[1].toFixed(3)}]`;
  } else {
    const p10 = comp.prev_0_10;
    const p20 = comp.prev_0_20;
    const m10 = isShrink ? p10.v3_mean : p10.noshrink_mean;
    const ci10 = isShrink ? p10.v3_ci_95 : p10.noshrink_ci_95;
    const m20 = isShrink ? p20.v3_mean : p20.noshrink_mean;
    const ci20 = isShrink ? p20.v3_ci_95 : p20.noshrink_ci_95;
    return `This round: ${roundHits} of 4. Study average at comparable settings: prev 0.10 = ${m10.toFixed(3)} [${ci10[0].toFixed(3)}, ${ci10[1].toFixed(3)}], prev 0.20 = ${m20.toFixed(3)} [${ci20[0].toFixed(3)}, ${ci20[1].toFixed(3)}]`;
  }
}

display(html`
<div class="card" style="padding: 14px 18px; margin: 16px 0; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px;">
  <div style="font-size: 0.9rem; color: #334155;">
    <strong>Design Parameters:</strong> Seed: <code>${design.seed}</code> &bull; Workload: <code>${design.workload_profile} [${design.workload_range.join(", ")}]</code> &bull; Enumerators: <code>${design.n_enumerators}</code> &bull; Prevalence: <code>${design.prevalence}</code> (12.5% fabricators) &bull; ICC: <code>${design.icc_level}</code> (0.15) &bull; Active modes: <code>${design.active_fraud_modes.join(", ")}</code>
  </div>
  <div style="font-size: 0.85rem; color: #64748b; margin-top: 6px;">
    <em>Seeds were fixed before results were viewed.</em> &bull;
    <strong>Round Performance:</strong> ${formatComparison(roundMetrics, shrinkageOn)}.
  </div>
</div>
`);
```

```js
const budgetInput = Inputs.range([10, 200], {value: 60, step: 5, label: "Back-check Budget (interviews):"});
const floorShareInput = Inputs.range([0, 50], {value: 20, step: 5, label: "Random Floor Share (%):"});
const allocSeedInput = Inputs.number({value: 42, step: 1, label: "Allocator Seed:"});
const revealButton = Inputs.button("Reveal Ground Truth");

display(html`<div class="grid grid-cols-4" style="gap: 12px; margin-bottom: 12px;">
  <div>${budgetInput}</div>
  <div>${floorShareInput}</div>
  <div>${allocSeedInput}</div>
  <div>${revealButton}</div>
</div>`);

const budget = Generators.input(budgetInput);
const floorShare = Generators.input(floorShareInput);
const allocSeed = Generators.input(allocSeedInput);
const revealCount = Generators.input(revealButton);
```

```js
// Reveal state tracking (only fetch truth.json when clicked)
const isRevealed = revealCount > 0;
const truthData = isRevealed
  ? await (scenario === "mixed" ? FileAttachment("./data/mixed/truth.json").json() : FileAttachment("./data/low/truth.json").json())
  : null;

const truthMap = new Map();
if (truthData) {
  for (const t of truthData) {
    truthMap.set(t.enumerator_id, t);
  }
}
```

```js
// Extract evidence submission IDs across all enumerators
const evidenceSubmissionIds = new Set();
for (const [eId, eInfo] of Object.entries(evidenceDict)) {
  for (const f of Object.values(eInfo.features || {})) {
    for (const sid of f.submission_ids || []) {
      evidenceSubmissionIds.add(sid);
    }
  }
}

// Run back-check allocation pure function
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
// Assemble sorted table rows
const sortedScores = [...rawScores].sort((a, b) => {
  if (b.risk_score !== a.risk_score) return b.risk_score - a.risk_score;
  return a.enumerator_id.localeCompare(b.enumerator_id);
});

const tableRows = sortedScores.map((r, idx) => {
  const eId = r.enumerator_id;
  const evInfo = evidenceDict[eId] || {};
  const evFeatures = Object.keys(evInfo.features || {});
  
  // Find strongest feature interval
  let strongestEst = null, ciLo = null, ciHi = null;
  if (evFeatures.length > 0) {
    const fData = evInfo.features[evFeatures[0]];
    strongestEst = fData.shrunk_estimate ?? fData.feature_estimate;
    if (fData.ci_90) {
      ciLo = fData.ci_90[0];
      ciHi = fData.ci_90[1];
    }
  }

  // Determine ground truth status if revealed
  let truthLabel = "TN";
  if (isRevealed) {
    const isFab = Boolean(truthMap.get(eId)?.is_fabricator);
    const inTop4 = idx < 4;
    if (inTop4 && isFab) truthLabel = "TP";
    else if (inTop4 && !isFab) truthLabel = "FP";
    else if (!inTop4 && isFab) truthLabel = "FN";
    else truthLabel = "TN";
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
    rule_hits: Number(r.by_flag ? 1 : 0),
    allocated_backchecks: allocation.allocatedCounts[eId] || 0,
    truth_label: truthLabel,
  };
});
```

```js
// Selection state for evidence drawer
const selectedEnumInput = Inputs.input("enum_27");
const selectedEnumId = Generators.input(selectedEnumInput);
function setSelected(id) {
  selectedEnumInput.value = id;
  selectedEnumInput.dispatchEvent(new Event("input", { bubbles: true }));
}
```

```js
display(renderRiskTable({
  rows: tableRows,
  selectedId: selectedEnumId,
  onSelect: setSelected,
  isRevealed: isRevealed,
}));
```

```js
function downloadCsv() {
  const headers = ["submission_id", "enumerator_id", "selection_reason", "is_evidence"];
  const csvContent = [headers.join(",")].concat(
    allocation.selectedSubmissions.map(s => `${s.submission_id},${s.enumerator_id},${s.selection_reason},${s.is_evidence}`)
  ).join("\n");
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `backcheck_allocation_${scenario}_b${budget}.csv`;
  a.click();
}

const staticCsvHref = scenario === "mixed" ? mixedData.flagsCsvHref : lowData.flagsCsvHref;
const staticDtaHref = scenario === "mixed" ? mixedData.flagsDtaHref : lowData.flagsDtaHref;

display(html`
<div class="grid grid-cols-2" style="align-items: center; margin: 12px 0;">
  <div>
    <strong>Total Allocated Interviews:</strong> ${allocation.totalAllocated} / ${submissions.length} (${allocation.floorAllocated} random floor, ${allocation.riskAllocated} risk-weighted)
  </div>
  <div style="text-align: right;">
    <button class="btn" onclick=${() => downloadCsv()} style="padding: 6px 12px; font-weight: 600; cursor: pointer; border-radius: 4px; background: #2563eb; color: #fff; border: none;">
      Download Current Allocation (CSV)
    </button>
    <a href="${staticCsvHref}" download style="margin-left: 8px; font-size: 0.85rem; color: #2563eb;">Static flags.csv</a>
    <a href="${staticDtaHref}" download style="margin-left: 8px; font-size: 0.85rem; color: #2563eb;">Static flags.dta</a>
  </div>
</div>
`);
```

```js
display(renderEvidenceDrawer({
  enumeratorId: selectedEnumId,
  enumEvidence: evidenceDict[selectedEnumId],
  allSubmissions: submissions,
  villages: villages,
  onClose: () => setSelected(null),
}));
```
