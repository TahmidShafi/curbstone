/**
 * Helper to convert Apache Arrow tables to plain objects with Number conversions
 */
export const toRows = (t) => Array.from(t, (r) => {
  const o = r.toJSON();
  for (const k in o) {
    if (typeof o[k] === "bigint") {
      o[k] = Number(o[k]);
    } else if (Array.isArray(o[k])) {
      o[k] = o[k].map((v) => typeof v === "bigint" ? Number(v) : v);
    } else if (o[k] != null && typeof o[k] === "object" && typeof o[k][Symbol.iterator] === "function") {
      o[k] = Array.from(o[k], (v) => typeof v === "bigint" ? Number(v) : v);
    }
  }
  return o;
});

/**
 * Format the Precision@4 stat string
 */
export function formatPrecisionStat(rm, isShrink) {
  const roundHits = isShrink ? rm.round_hits_v3 : rm.round_hits_noshrinkage;
  const comp = rm.study_average;
  if (!comp) return `${roundHits} of 4`;
  if (rm.scenario === "mixed") {
    const mean = isShrink ? comp.v3_mean : comp.noshrink_mean;
    const ci = isShrink ? comp.v3_ci_95 : comp.noshrink_ci_95;
    return `${roundHits} of 4 (study avg ${mean.toFixed(3)} [${ci[0].toFixed(3)}, ${ci[1].toFixed(3)}])`;
  } else {
    const p10 = comp.prev_0_10;
    const p20 = comp.prev_0_20;
    const m10 = isShrink ? p10.v3_mean : p10.noshrink_mean;
    const ci10 = isShrink ? p10.v3_ci_95 : p10.noshrink_ci_95;
    const m20 = isShrink ? p20.v3_mean : p20.noshrink_mean;
    const ci20 = isShrink ? p20.v3_ci_95 : p20.noshrink_ci_95;
    return `${roundHits} of 4 (study avg prev 0.10: ${m10.toFixed(3)} [${ci10[0].toFixed(3)}, ${ci10[1].toFixed(3)}], prev 0.20: ${m20.toFixed(3)} [${ci20[0].toFixed(3)}, ${ci20[1].toFixed(3)}])`;
  }
}

/**
 * Trigger browser download of current allocation CSV
 */
export function downloadAllocationCsv(selectedSubmissions, scenario, budget) {
  const headers = ["submission_id", "enumerator_id", "selection_reason", "is_evidence"];
  const csvContent = [headers.join(",")].concat(
    selectedSubmissions.map((s) => `${s.submission_id},${s.enumerator_id},${s.selection_reason},${s.is_evidence}`)
  ).join("\n");
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `backcheck_allocation_${scenario}_b${budget}.csv`;
  a.click();
}
