# Live DQA SQL Rule Engine

Execute all 12 pre-registered Data Quality Assurance (DQA) rules in DuckDB-Wasm in real time directly within your browser.

```js
import yaml from "npm:js-yaml";

// Load scenario files
const mixedSubmissions = FileAttachment("./data/mixed/submissions.parquet");
const mixedVillages = FileAttachment("./data/mixed/villages.parquet");
const mixedViewSql = await FileAttachment("./data/mixed/submissions_view.sql").text();
const mixedRulesYaml = await FileAttachment("./data/mixed/rules.yaml").text();
const mixedExpectedHits = await FileAttachment("./data/mixed/rule_hits_expected.json").json();

const lowSubmissions = FileAttachment("./data/low/submissions.parquet");
const lowVillages = FileAttachment("./data/low/villages.parquet");
const lowViewSql = await FileAttachment("./data/low/submissions_view.sql").text();
const lowRulesYaml = await FileAttachment("./data/low/rules.yaml").text();
const lowExpectedHits = await FileAttachment("./data/low/rule_hits_expected.json").json();
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
const activeSubmissions = isMixed ? mixedSubmissions : lowSubmissions;
const activeVillages = isMixed ? mixedVillages : lowVillages;
const activeViewSql = isMixed ? mixedViewSql : lowViewSql;
const activeRulesYaml = isMixed ? mixedRulesYaml : lowRulesYaml;
const expectedHits = isMixed ? mixedExpectedHits : lowExpectedHits;
const parsedRules = yaml.load(activeRulesYaml);

// Initialize DuckDBClient with raw tables
const db = await DuckDBClient.of({
  _raw_submissions: activeSubmissions,
  villages: activeVillages,
});

// Create the standard submissions view with start_local / end_local derivations
await db.query(activeViewSql);
```

```js
// Execute each rule and measure latency
const ruleExecutionResults = [];
for (const rule of parsedRules) {
  const t0 = performance.now();
  const res = await db.query(rule.sql);
  const elapsedMs = performance.now() - t0;
  const actualHits = res.numRows;
  const expected = expectedHits[rule.id] ?? 0;
  const pass = actualHits === expected;

  ruleExecutionResults.push({
    id: rule.id,
    level: rule.level,
    severity: rule.severity,
    description: rule.description,
    hits: actualHits,
    expected: expected,
    pass: pass,
    ms: elapsedMs,
    sql: rule.sql,
  });
}

const allPassed = ruleExecutionResults.every(r => r.pass);
const totalHits = ruleExecutionResults.reduce((acc, r) => acc + r.hits, 0);
const totalExpected = Object.values(expectedHits).reduce((acc, v) => acc + v, 0);
const totalMs = ruleExecutionResults.reduce((acc, r) => acc + r.ms, 0);
```

```js
display(html`
<div class="card" style="padding: 16px; margin: 16px 0; background: ${allPassed ? '#f0fdf4' : '#fef2f2'}; border: 1px solid ${allPassed ? '#86efac' : '#fca5a5'}; border-radius: 6px;">
  <div style="display: flex; justify-content: space-between; align-items: center;">
    <div>
      <span style="display: inline-block; padding: 4px 10px; border-radius: 4px; font-weight: bold; font-size: 0.9rem; background: ${allPassed ? '#16a34a' : '#dc2626'}; color: #fff;">
        ${allPassed ? "PARITY BADGE: 100% MATCH" : "PARITY MISMATCH"}
      </span>
      <span style="margin-left: 12px; font-size: 0.95rem; color: #1e293b; font-weight: 600;">
        DuckDB-Wasm in browser matches Python rule engine (${totalHits} / ${totalExpected} rule hits)
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
            ${r.pass 
              ? html`<span style="color: #16a34a; font-weight: bold;">PASS</span>`
              : html`<span style="color: #dc2626; font-weight: bold;">FAIL</span>`
            }
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
async function executeBenchmark() {
  const t0 = performance.now();
  const demoCountRes = await db.query("SELECT count(*)::INT AS cnt FROM submissions;");
  const demoSubmissionsCount = demoCountRes.toArray()[0].cnt;
  const demoRate = (totalHits / (demoSubmissionsCount / 1000)).toFixed(2);

  await db.query(`
    CREATE OR REPLACE TABLE _bench_submissions AS
    SELECT
      'bench_' || r.i AS submission_id,
      s.round,
      s.enumerator_id || '_r' || (r.i // ${demoSubmissionsCount}) AS enumerator_id,
      s.upazila_code,
      s.village_id,
      s.start_time,
      s.end_time,
      s.duration_min,
      s.gps_lat,
      s.gps_lon,
      s.gps_accuracy,
      s.hh_size,
      s.head_age,
      s.roster_ages,
      s.asset_mobile,
      s.asset_tv,
      s.asset_internet,
      s.asset_radio,
      s.asset_computer,
      s.start_local,
      s.end_local
    FROM range(0, 1000000) r(i)
    JOIN (SELECT *, row_number() OVER () - 1 AS rn FROM submissions) s
      ON s.rn = r.i % ${demoSubmissionsCount};
  `);

  await db.query("CREATE OR REPLACE VIEW submissions AS SELECT * FROM _bench_submissions;");

  let ruleTotalMs = 0;
  let benchHits = 0;
  for (const rule of parsedRules) {
    const tb0 = performance.now();
    const res = await db.query(rule.sql);
    ruleTotalMs += (performance.now() - tb0);
    benchHits += res.numRows;
  }

  await db.query(activeViewSql);
  const totalElapsed = performance.now() - t0;
  const benchRate = (benchHits / 1000).toFixed(2);

  return {
    rows: 1000000,
    ruleTotalMs: ruleTotalMs,
    totalElapsed: totalElapsed,
    benchHits: benchHits,
    benchRate: benchRate,
    demoRate: demoRate,
    cores: typeof navigator !== 'undefined' ? (navigator.hardwareConcurrency || "Unknown") : "N/A",
    userAgent: typeof navigator !== 'undefined' ? (navigator.userAgent || "Unknown") : "Node.js",
  };
}

const benchResult = runBenchmark > 0 ? await executeBenchmark() : null;

if (benchResult) {
  display(html`
    <div class="card" style="padding: 16px; margin-top: 16px; background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px;">
      <h4 style="margin: 0 0 10px 0; color: #1e293b;">1,000,000-Row Benchmark Results</h4>
      <div class="grid grid-cols-3" style="gap: 12px; margin-bottom: 12px;">
        <div style="background: #fff; padding: 10px; border-radius: 4px; border: 1px solid #e2e8f0;">
          <div style="font-size: 0.8rem; color: #64748b;">12-Rule Evaluation Time</div>
          <div style="font-size: 1.25rem; font-weight: bold; color: #0284c7;">${benchResult.ruleTotalMs.toFixed(1)} ms</div>
          <div style="font-size: 0.75rem; color: #64748b; margin-top: 4px;">measured in this browser (DuckDB-Wasm)</div>
        </div>
        <div style="background: #fff; padding: 10px; border-radius: 4px; border: 1px solid #e2e8f0;">
          <div style="font-size: 0.8rem; color: #64748b;">Processing Throughput</div>
          <div style="font-size: 1.25rem; font-weight: bold; color: #16a34a;">
            ${(1000000 / (benchResult.ruleTotalMs / 1000)).toLocaleString(undefined, {maximumFractionDigits: 0})} rows/sec
          </div>
          <div style="font-size: 0.75rem; color: #64748b; margin-top: 4px;">in-memory streaming SQL</div>
        </div>
        <div style="background: #fff; padding: 10px; border-radius: 4px; border: 1px solid #e2e8f0;">
          <div style="font-size: 0.8rem; color: #64748b;">Violations per 1,000 Submissions</div>
          <div style="font-size: 1.25rem; font-weight: bold; color: #c2410c;">
            ${benchResult.benchRate} <span style="font-size: 0.85rem; font-weight: normal; color: #64748b;">(demo: ${benchResult.demoRate})</span>
          </div>
          <div style="font-size: 0.75rem; color: #64748b; margin-top: 4px;">${benchResult.benchHits.toLocaleString()} total violations detected</div>
        </div>
      </div>
      <div style="font-size: 0.825rem; color: #64748b; font-family: monospace;">
        <strong>Stated Hardware:</strong> CPU Concurrency: ${benchResult.cores} threads &bull; User Agent: ${benchResult.userAgent}
      </div>
    </div>
  `);
}
```
