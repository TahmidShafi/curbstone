# Live DQA SQL Rule Engine

Execute all 12 pre-registered Data Quality Assurance (DQA) rules in DuckDB-Wasm in real time directly within your browser.

```js
import {load} from "npm:js-yaml";

// Load static rules YAML & expected hits
const mixedRulesYaml = await FileAttachment("./data/mixed/rules.yaml").text();
const mixedExpectedHits = await FileAttachment("./data/mixed/rule_hits_expected.json").json();
const lowRulesYaml = await FileAttachment("./data/low/rules.yaml").text();
const lowExpectedHits = await FileAttachment("./data/low/rule_hits_expected.json").json();

// Initialize ONE DuckDB instance per page load with unique file names
const db = await DuckDBClient.of({
  mixed_submissions: FileAttachment("./data/mixed_submissions.parquet"),
  mixed_villages: FileAttachment("./data/mixed_villages.parquet"),
  low_submissions: FileAttachment("./data/low_submissions.parquet"),
  low_villages: FileAttachment("./data/low_villages.parquet"),
});
const benchHistory = [];
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
async function executeRules() {
  const results = [];
  for (const rule of parsedRules) {
    const t0 = performance.now();
    const res = await db.query(rule.sql);
    const actualHits = res.numRows;
    const expected = expectedHits[rule.id] ?? 0;
    results.push({
      id: rule.id, level: rule.level, severity: rule.severity, description: rule.description,
      hits: actualHits, expected: expected, pass: actualHits === expected,
      ms: performance.now() - t0, sql: rule.sql,
    });
  }
  return results;
}

const ruleExecutionResults = await executeRules();
const allPassed = ruleExecutionResults.every(r => r.pass);
const matchingRulesCount = ruleExecutionResults.filter(r => r.pass).length;
const totalHits = ruleExecutionResults.reduce((acc, r) => acc + r.hits, 0);
const totalExpected = Object.values(expectedHits).reduce((acc, v) => acc + v, 0);
const totalMs = ruleExecutionResults.reduce((acc, r) => acc + r.ms, 0);
const badgeMessage = allPassed
  ? `DuckDB-Wasm matches the Python rule engine: 12 of 12 rules (${totalHits} hits)`
  : `DuckDB-Wasm does NOT match the Python rule engine: ${matchingRulesCount} of 12 rules match (browser total ${totalHits} vs expected ${totalExpected})`;
```

```js
display(html`
<div class="card" style="padding: 16px; margin: 16px 0; background: ${allPassed ? '#f0fdf4' : '#fef2f2'}; border: 1px solid ${allPassed ? '#86efac' : '#fca5a5'}; border-radius: 6px;">
  <div style="display: flex; justify-content: space-between; align-items: center;">
    <div>
      <span style="display: inline-block; padding: 4px 10px; border-radius: 4px; font-weight: bold; font-size: 0.9rem; background: ${allPassed ? '#16a34a' : '#dc2626'}; color: #fff;">
        ${allPassed ? "PARITY MATCH" : "PARITY MISMATCH"}
      </span>
      <span style="margin-left: 12px; font-size: 0.95rem; color: #1e293b; font-weight: 600;">
        ${badgeMessage}
      </span>
    </div>
    <div style="font-size: 0.85rem; color: #64748b; font-family: monospace;">
      12 rules evaluated in ${totalMs.toFixed(1)} ms
    </div>
  </div>
</div>
`);
```

### Executed Rules

```js
display(html`
<div style="overflow-x: auto; margin-bottom: 24px;">
  <table style="width: 100%; border-collapse: collapse; font-size: 0.85rem;">
    <thead>
      <tr style="background: #f8fafc; border-bottom: 2px solid #cbd5e1; text-align: left;">
        <th style="padding: 8px 10px;">Rule ID</th>
        <th style="padding: 8px 10px;">Level</th>
        <th style="padding: 8px 10px;">Severity</th>
        <th style="padding: 8px 10px;">Description</th>
        <th style="padding: 8px 10px; text-align: right;">Browser Hits</th>
        <th style="padding: 8px 10px; text-align: right;">Python Expected</th>
        <th style="padding: 8px 10px; text-align: center;">Parity</th>
        <th style="padding: 8px 10px; text-align: right;">Latency</th>
      </tr>
    </thead>
    <tbody>
      ${ruleExecutionResults.map(r => html`
        <tr style="border-bottom: 1px solid #f1f5f9;">
          <td style="padding: 8px 10px; font-family: monospace; font-weight: bold; color: #1e40af;">${r.id}</td>
          <td style="padding: 8px 10px; color: #475569;">${r.level}</td>
          <td style="padding: 8px 10px;">
            <span style="font-size: 0.75rem; font-weight: 600; padding: 2px 6px; border-radius: 4px; background: ${r.severity === 'high' ? '#fee2e2' : r.severity === 'medium' ? '#fef3c7' : '#f1f5f9'}; color: ${r.severity === 'high' ? '#991b1b' : r.severity === 'medium' ? '#92400e' : '#334155'};">
              ${r.severity.toUpperCase()}
            </span>
          </td>
          <td style="padding: 8px 10px; color: #334155;">${r.description}</td>
          <td style="padding: 8px 10px; text-align: right; font-weight: bold;">${r.hits}</td>
          <td style="padding: 8px 10px; text-align: right; color: #64748b;">${r.expected}</td>
          <td style="padding: 8px 10px; text-align: center;">
            ${r.pass ? html`<span style="color: #16a34a; font-weight: bold;">PASS</span>` : html`<span style="color: #dc2626; font-weight: bold;">FAIL</span>`}
          </td>
          <td style="padding: 8px 10px; text-align: right; font-family: monospace; color: #64748b;">${r.ms.toFixed(1)} ms</td>
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
  const t0 = performance.now();
  const demoCountRes = await db.query("SELECT count(*)::INT AS cnt FROM submissions;");
  const demoSubmissionsCount = demoCountRes.toArray()[0].cnt;

  let ruleTotalMs = 0;
  let benchHits = 0;

  try {
    await db.query(`
      CREATE OR REPLACE TABLE bench_submissions AS
      SELECT 'bench_' || r.i AS submission_id, s.round,
        s.enumerator_id || '_r' || (r.i // ${demoSubmissionsCount}) AS enumerator_id,
        s.upazila_code, s.village_id, s.start_time, s.end_time, s.duration_min,
        s.gps_lat, s.gps_lon, s.gps_accuracy, s.hh_size, s.head_age, s.roster_ages,
        s.asset_mobile, s.asset_tv, s.asset_internet, s.asset_radio, s.asset_computer,
        s.start_local, s.end_local
      FROM range(0, 1000000) r(i)
      JOIN (SELECT *, row_number() OVER () - 1 AS rn FROM submissions) s
        ON s.rn = r.i % ${demoSubmissionsCount};
    `);

    await db.query("CREATE OR REPLACE TABLE bench_villages AS SELECT * FROM villages;");
    await db.query("CREATE OR REPLACE VIEW submissions AS SELECT * FROM bench_submissions;");
    await db.query("CREATE OR REPLACE VIEW villages AS SELECT * FROM bench_villages;");

    for (const rule of parsedRules) {
      const tb0 = performance.now();
      const res = await db.query(rule.sql);
      ruleTotalMs += (performance.now() - tb0);
      benchHits += res.numRows;
    }
  } finally {
    await db.query(`
      CREATE OR REPLACE VIEW submissions AS
      SELECT *,
          CAST(substr(start_time, 1, 19) AS TIMESTAMP) AS start_local,
          CAST(substr(end_time, 1, 19) AS TIMESTAMP) AS end_local
      FROM ${activeRawTable};

      CREATE OR REPLACE VIEW villages AS
      SELECT * FROM ${activeVilTable};

      DROP TABLE IF EXISTS bench_submissions;
      DROP TABLE IF EXISTS bench_villages;
    `);
  }

  benchHistory.push({
    runIndex: benchHistory.length + 1,
    scenario: scenario,
    ruleTotalMs: ruleTotalMs,
    totalElapsed: performance.now() - t0,
    benchHits: benchHits,
    benchRate: (benchHits / 1000).toFixed(2),
  });
}

const recentRuns = benchHistory.slice(-3);
const hasRuns = recentRuns.length > 0;
const logicalCores = typeof navigator !== "undefined" ? (navigator.hardwareConcurrency || "Unknown") : "N/A";

let medianMs = 0;
if (hasRuns) {
  const sortedTimes = recentRuns.map(r => r.ruleTotalMs).sort((a, b) => a - b);
  const mid = Math.floor(sortedTimes.length / 2);
  medianMs = sortedTimes.length % 2 === 1
    ? sortedTimes[mid]
    : (sortedTimes[mid - 1] + sortedTimes[mid]) / 2;
}

display(html`
<div class="card" style="padding: 16px; margin-top: 16px; background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px;">
  <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px;">
    <h4 style="margin: 0; color: #1e293b;">1,000,000-Row Benchmark Results</h4>
    <div style="font-size: 0.8rem; color: #64748b; font-family: monospace;">
      single-threaded DuckDB-Wasm build; hardware: ${logicalCores} logical CPUs
    </div>
  </div>

  ${!hasRuns ? html`<p style="margin: 0; font-size: 0.85rem; color: #64748b; font-style: italic;">Click "Benchmark 1M rows" above to execute the benchmark in DuckDB-Wasm.</p>` : html`
    <div class="grid grid-cols-2" style="gap: 12px; margin-bottom: 12px;">
      <div style="background: #fff; padding: 10px; border-radius: 4px; border: 1px solid #e2e8f0;">
        <div style="font-size: 0.8rem; color: #64748b;">Median Rule Evaluation Time (Last ${recentRuns.length} Run${recentRuns.length > 1 ? "s" : ""})</div>
        <div style="font-size: 1.35rem; font-weight: bold; color: #0284c7;">${medianMs.toFixed(1)} ms</div>
      </div>
      <div style="background: #fff; padding: 10px; border-radius: 4px; border: 1px solid #e2e8f0;">
        <div style="font-size: 0.8rem; color: #64748b;">Median Processing Throughput</div>
        <div style="font-size: 1.35rem; font-weight: bold; color: #16a34a;">
          ${(1000000 / (medianMs / 1000)).toLocaleString(undefined, {maximumFractionDigits: 0})} rows/sec
        </div>
      </div>
    </div>

    <div style="font-size: 0.825rem; font-weight: 600; color: #475569; margin-bottom: 4px;">Last ${recentRuns.length} Execution${recentRuns.length > 1 ? "s" : ""}:</div>
    <table style="width: 100%; border-collapse: collapse; font-size: 0.825rem; background: #fff; border: 1px solid #e2e8f0; border-radius: 4px;">
      <thead>
        <tr style="background: #f1f5f9; text-align: left; border-bottom: 1px solid #e2e8f0;">
          <th style="padding: 6px 10px;">Run #</th>
          <th style="padding: 6px 10px;">Scenario</th>
          <th style="padding: 6px 10px; text-align: right;">12-Rule Time</th>
          <th style="padding: 6px 10px; text-align: right;">Violations</th>
          <th style="padding: 6px 10px; text-align: right;">Rate / 1k</th>
        </tr>
      </thead>
      <tbody>
        ${recentRuns.map(r => html`
          <tr style="border-bottom: 1px solid #f8fafc;">
            <td style="padding: 6px 10px; font-weight: 600; color: #475569;">Run ${r.runIndex}</td>
            <td style="padding: 6px 10px; color: #64748b;">${r.scenario}</td>
            <td style="padding: 6px 10px; text-align: right; font-family: monospace; font-weight: bold; color: #0284c7;">${r.ruleTotalMs.toFixed(1)} ms</td>
            <td style="padding: 6px 10px; text-align: right; font-family: monospace;">${r.benchHits.toLocaleString()}</td>
            <td style="padding: 6px 10px; text-align: right; font-family: monospace;">${r.benchRate}</td>
          </tr>
        `)}
      </tbody>
    </table>
  `}
</div>
`);
```
