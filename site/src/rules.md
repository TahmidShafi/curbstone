---
title: Rule engine (live)
---

# Live DQA SQL Rule Engine

Execute all 12 pre-registered Data Quality Assurance (DQA) rules in DuckDB-Wasm in real time directly within your browser.

```js
import {load} from "npm:js-yaml";
import { verifyDuckDBTables, executeDqaRules, run1MBenchmark } from "./components/ruleEngineHelpers.js";

// Load static rules YAML & expected hits
const mixedRulesYaml = await FileAttachment("./data/mixed/rules.yaml").text();
const mixedExpectedHits = await FileAttachment("./data/mixed/rule_hits_expected.json").json();
const mixedMetrics = await FileAttachment("./data/mixed/round_metrics.json").json();
const lowRulesYaml = await FileAttachment("./data/low/rules.yaml").text();
const lowExpectedHits = await FileAttachment("./data/low/rule_hits_expected.json").json();
const lowMetrics = await FileAttachment("./data/low/round_metrics.json").json();

// Initialize ONE DuckDB instance per page load by passing in-memory Arrow tables
const db = await DuckDBClient.of({
  mixed_submissions: await FileAttachment("./data/mixed/mixed_submissions.parquet").parquet(),
  mixed_villages:    await FileAttachment("./data/mixed/mixed_villages.parquet").parquet(),
  low_submissions:   await FileAttachment("./data/low/low_submissions.parquet").parquet(),
  low_villages:      await FileAttachment("./data/low/low_villages.parquet").parquet()
});
const benchHistory = [];

// Self-check after registration: verify row counts match expected values from build_demo.py
const tableErrors = await verifyDuckDBTables(db, mixedMetrics, lowMetrics);
if (tableErrors.length > 0) {
  display(html`<div class="card" style="padding: 16px; margin: 16px 0; background: var(--surface); border: 2px solid var(--ink); border-radius: 6px; color: var(--ink);">
    <div style="font-weight: bold; font-size: 1rem; margin-bottom: 4px;">Table Registration Verification Error</div>
    <div>The following registered DuckDB table verification check(s) failed:</div>
    <ul style="margin: 4px 0 0 0; padding-left: 20px;">${tableErrors.map(e => html`<li>${e}</li>`)}</ul>
  </div>`);
}
```

```js
const scenarioInput = Inputs.radio(["mixed", "low"], {
  value: "mixed",
  label: "Active Scenario:",
  format: (x) => x === "mixed" ? "Mixed Workload (Seed 5000)" : "Low Workload (Seed 5001)"
});
display(html`<div style="margin-top: 16px;">${scenarioInput}</div>`);
const scenario = Generators.input(scenarioInput);
```

```js
const isMixed = scenario === "mixed";
const activeRawTable = isMixed ? "mixed_submissions" : "low_submissions";
const activeVilTable = isMixed ? "mixed_villages" : "low_villages";
const activeRulesYaml = isMixed ? mixedRulesYaml : lowRulesYaml;
const expectedHits = isMixed ? mixedExpectedHits : lowExpectedHits;
const parsedRules = load(activeRulesYaml);

// Scenario switching only runs CREATE OR REPLACE VIEW statements over the registered files
await db.query(`
  CREATE OR REPLACE VIEW submissions AS
  SELECT *,
      CAST(substr(start_time, 1, 19) AS TIMESTAMP) AS start_local,
      CAST(substr(end_time, 1, 19) AS TIMESTAMP) AS end_local
  FROM ${activeRawTable};

  CREATE OR REPLACE VIEW villages AS
  SELECT * FROM ${activeVilTable};
`);

// Execute all 12 rules against active submissions & villages views
const ruleExecutionResults = await executeDqaRules(db, parsedRules, expectedHits);
const allPassed = ruleExecutionResults.every(r => r.pass);
const matchingRulesCount = ruleExecutionResults.filter(r => r.pass).length;
const totalHits = ruleExecutionResults.reduce((acc, r) => acc + r.hits, 0);
const totalExpected = Object.values(expectedHits).reduce((acc, v) => acc + v, 0);
const totalMs = ruleExecutionResults.reduce((acc, r) => acc + r.ms, 0);
const paritySymbol = allPassed ? "✓" : "✗";
const parityColor = allPassed ? "var(--accent)" : "var(--fab)";
const parityText = allPassed
  ? `Browser matches Python rule engine — 12 of 12 rules (${totalHits} hits)`
  : `Browser does NOT match Python rule engine — ${matchingRulesCount} of 12 rules match (${totalHits} vs ${totalExpected} hits)`;
```

```js
display(html`
<div style="margin: 16px 0; font-size: 15px; font-weight: 600; color: var(--ink); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
  <div>
    <span style="color: ${parityColor}; font-weight: bold; margin-right: 6px;">${paritySymbol}</span>
    <span>${parityText}</span>
  </div>
  <div class="tabular-nums" style="font-size: 13px; color: var(--muted); font-weight: normal;">
    12 rules evaluated in ${totalMs.toFixed(1)} ms
  </div>
</div>
`);
```

### Executed Rules

```js
display(html`
<div class="table-wrapper" style="overflow-x: auto; max-width: 100%; background: var(--surface); border: 1px solid var(--line); border-radius: 8px; margin-bottom: 24px; box-sizing: border-box;">
  <table style="width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; table-layout: fixed;">
    <thead>
      <tr style="background: var(--surface); border-bottom: 1px solid var(--line); color: var(--ink); font-weight: 600;">
        <th style="padding: 10px 8px; width: 56px; box-sizing: border-box; white-space: nowrap;">Rule</th>
        <th style="padding: 10px 8px; width: 112px; box-sizing: border-box; white-space: nowrap;">Level</th>
        <th style="padding: 10px 8px; width: 80px; box-sizing: border-box; white-space: nowrap;">Severity</th>
        <th style="padding: 10px 8px; width: auto; min-width: 280px; box-sizing: border-box;">Description</th>
        <th style="padding: 10px 8px; width: 72px; box-sizing: border-box; text-align: right; white-space: nowrap;">Browser</th>
        <th style="padding: 10px 8px; width: 72px; box-sizing: border-box; text-align: right; white-space: nowrap;">Python</th>
        <th style="padding: 10px 8px; width: 56px; box-sizing: border-box; text-align: center; white-space: nowrap;">Parity</th>
        <th style="padding: 10px 8px; width: 72px; box-sizing: border-box; text-align: right; white-space: nowrap;">Time</th>
      </tr>
    </thead>
    <tbody>
      ${ruleExecutionResults.map(r => html`
        <tr style="border-bottom: 1px solid var(--line); color: var(--ink);">
          <td style="padding: 8px 8px; width: 56px; box-sizing: border-box; font-weight: 600; color: var(--accent);" class="enum-id">${r.id}</td>
          <td style="padding: 8px 8px; width: 112px; box-sizing: border-box; color: var(--muted);">${r.level}</td>
          <td style="padding: 8px 8px; width: 80px; box-sizing: border-box; color: var(--muted);">${r.severity}</td>
          <td style="padding: 8px 8px; width: auto; min-width: 280px; box-sizing: border-box;">${r.description}</td>
          <td style="padding: 8px 8px; width: 72px; box-sizing: border-box; text-align: right; font-weight: 600;" class="tabular-nums">${r.hits}</td>
          <td style="padding: 8px 8px; width: 72px; box-sizing: border-box; text-align: right; color: var(--muted);" class="tabular-nums">${r.expected}</td>
          <td style="padding: 8px 8px; width: 56px; box-sizing: border-box; text-align: center; font-weight: 600; color: ${r.pass ? 'var(--accent)' : 'var(--fab)'};">${r.pass ? "✓" : "✗"}</td>
          <td style="padding: 8px 8px; width: 72px; box-sizing: border-box; text-align: right; color: var(--muted);" class="tabular-nums">${r.ms.toFixed(1)} ms</td>
        </tr>
      `)}
    </tbody>
  </table>
</div>
`);
```

---

### In-Browser High-Throughput Benchmark (1,000,000 Rows)

Replicate survey submissions to 1,000,000 rows in DuckDB-Wasm memory and execute all 12 SQL rules.

```js
const runBenchmark = view(Inputs.button("Benchmark 1M rows"));
```

```js
// Benchmark cell depends ONLY on runBenchmark and scenario
if (runBenchmark > 0) {
  await run1MBenchmark(db, parsedRules, activeRawTable, activeVilTable, scenario, benchHistory);
}

const recentRuns = benchHistory.slice(-3);
const hasRuns = recentRuns.length > 0;
const logicalCores = typeof navigator !== "undefined" ? (navigator.hardwareConcurrency || "Unknown") : "N/A";

let medianMs = 0;
let medianRate = "0.00";
let medianRowsPerSec = 0;
if (hasRuns) {
  const sortedTimes = recentRuns.map(r => r.ruleTotalMs).sort((a, b) => a - b);
  const mid = Math.floor(sortedTimes.length / 2);
  medianMs = sortedTimes.length % 2 === 1
    ? sortedTimes[mid]
    : (sortedTimes[mid - 1] + sortedTimes[mid]) / 2;
  medianRowsPerSec = Math.round(1000000 / (medianMs / 1000));
  const sortedRates = recentRuns.map(r => Number(r.benchRate)).sort((a, b) => a - b);
  medianRate = sortedRates[Math.floor(sortedRates.length / 2)].toFixed(2);
}

display(html`
<div style="margin-top: 16px;">
  <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px;">
    <h4 style="margin: 0; color: var(--ink); font-size: 15px;">1,000,000-Row Benchmark Results</h4>
    <div style="font-size: 12px; color: var(--muted);" class="tabular-nums">
      single-threaded DuckDB-Wasm; ${logicalCores} logical CPUs
    </div>
  </div>

  <div class="stat-strip" style="grid-template-columns: repeat(3, 1fr); margin: 12px 0;">
    <div class="stat-tile">
      <div class="stat-value tabular-nums">${hasRuns ? medianMs.toFixed(1) + " ms" : "—"}</div>
      <div class="stat-label">Median Rule Time</div>
    </div>
    <div class="stat-tile">
      <div class="stat-value tabular-nums">${hasRuns ? medianRowsPerSec.toLocaleString() : "—"}</div>
      <div class="stat-label">Throughput (rows/s)</div>
    </div>
    <div class="stat-tile">
      <div class="stat-value tabular-nums">${hasRuns ? medianRate : "—"}</div>
      <div class="stat-label">Violations per 1,000</div>
    </div>
  </div>

  ${!hasRuns ? html`
    <p style="margin: 8px 0; font-size: 13px; color: var(--muted); font-style: italic;">
      Click "Benchmark 1M rows" above to execute the benchmark in DuckDB-Wasm.
    </p>
  ` : html`
    <div style="font-size: 13px; font-weight: 600; color: var(--ink); margin: 16px 0 8px 0;">
      Last ${recentRuns.length} Execution${recentRuns.length > 1 ? "s" : ""}:
    </div>
    <div class="table-wrapper" style="overflow-x: auto; max-width: 100%; background: var(--surface); border: 1px solid var(--line); border-radius: 8px; box-sizing: border-box;">
      <table style="width: 100%; border-collapse: collapse; font-size: 13px; text-align: left;">
        <thead>
          <tr style="background: var(--surface); border-bottom: 1px solid var(--line); color: var(--ink); font-weight: 600;">
            <th style="padding: 8px 12px;">Run</th>
            <th style="padding: 8px 12px;">Scenario</th>
            <th style="padding: 8px 12px; text-align: right;">12-Rule Time</th>
            <th style="padding: 8px 12px; text-align: right;">Violations</th>
            <th style="padding: 8px 12px; text-align: right;">Rate / 1k</th>
          </tr>
        </thead>
        <tbody>
          ${recentRuns.map(r => html`
            <tr style="border-bottom: 1px solid var(--line); color: var(--ink);">
              <td style="padding: 8px 12px; font-weight: 600;">Run ${r.runIndex}</td>
              <td style="padding: 8px 12px; color: var(--muted);">${r.scenario}</td>
              <td style="padding: 8px 12px; text-align: right; font-weight: 600; color: var(--accent);" class="tabular-nums">${r.ruleTotalMs.toFixed(1)} ms</td>
              <td style="padding: 8px 12px; text-align: right;" class="tabular-nums">${r.benchHits.toLocaleString()}</td>
              <td style="padding: 8px 12px; text-align: right;" class="tabular-nums">${r.benchRate}</td>
            </tr>
          `)}
        </tbody>
      </table>
    </div>
  `}
</div>
`);
```
