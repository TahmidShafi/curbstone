/**
 * Helper utilities for DuckDB-Wasm DQA rule engine in rules.md
 */

export async function verifyDuckDBTables(db, mixedMetrics, lowMetrics) {
  const mixedSubCnt = (await db.query("SELECT count(*)::INT AS cnt FROM mixed_submissions")).toArray()[0].cnt;
  const lowSubCnt = (await db.query("SELECT count(*)::INT AS cnt FROM low_submissions")).toArray()[0].cnt;
  const mixedVilCnt = (await db.query("SELECT count(*)::INT AS cnt FROM mixed_villages")).toArray()[0].cnt;
  const lowVilCnt = (await db.query("SELECT count(*)::INT AS cnt FROM low_villages")).toArray()[0].cnt;

  const mixedRosterType = (await db.query("SELECT typeof(roster_ages) AS t FROM mixed_submissions LIMIT 1")).toArray()[0]?.t ?? "unknown";
  const lowRosterType = (await db.query("SELECT typeof(roster_ages) AS t FROM low_submissions LIMIT 1")).toArray()[0]?.t ?? "unknown";

  const tableErrors = [];
  if (mixedSubCnt !== mixedMetrics.submissions_count) tableErrors.push(`mixed_submissions row count (got ${mixedSubCnt}, expected ${mixedMetrics.submissions_count})`);
  if (lowSubCnt !== lowMetrics.submissions_count) tableErrors.push(`low_submissions row count (got ${lowSubCnt}, expected ${lowMetrics.submissions_count})`);
  if (mixedVilCnt !== mixedMetrics.villages_count) tableErrors.push(`mixed_villages row count (got ${mixedVilCnt}, expected ${mixedMetrics.villages_count})`);
  if (lowVilCnt !== lowMetrics.villages_count) tableErrors.push(`low_villages row count (got ${lowVilCnt}, expected ${lowMetrics.villages_count})`);
  if (!mixedRosterType.includes("[]") && !mixedRosterType.toUpperCase().includes("LIST")) tableErrors.push(`mixed_submissions.roster_ages arrived as '${mixedRosterType}' instead of DuckDB LIST`);
  if (!lowRosterType.includes("[]") && !lowRosterType.toUpperCase().includes("LIST")) tableErrors.push(`low_submissions.roster_ages arrived as '${lowRosterType}' instead of DuckDB LIST`);

  return tableErrors;
}

export async function executeDqaRules(db, parsedRules, expectedHits) {
  const results = [];
  for (const rule of parsedRules) {
    const t0 = performance.now();
    const res = await db.query(rule.sql);
    const actualHits = res.numRows;
    const expected = expectedHits[rule.id] ?? 0;
    results.push({
      id: rule.id,
      level: rule.level,
      severity: rule.severity,
      description: rule.description,
      hits: actualHits,
      expected: expected,
      pass: actualHits === expected,
      ms: performance.now() - t0,
      sql: rule.sql,
    });
  }
  return results;
}

export async function run1MBenchmark(db, parsedRules, activeRawTable, activeVilTable, scenario, benchHistory) {
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
