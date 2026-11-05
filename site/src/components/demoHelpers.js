export const FEATURE_NAMES = {
  F1: "Fast interviews",
  F2: "High daily volume",
  F3: "Near-duplicates",
  F4: "Straight-lining",
  F5: "Low asset dispersion",
  F6: "Low household-size dispersion",
  F7: "GPS clustering",
  F8: "Age heaping",
  F9: "Non-response",
  F10: "Duration–size coupling",
};

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
 * Format the Precision@4 stat label after reveal
 */
export function formatPrecisionStat(rm, isShrink) {
  const comp = rm.study_average;
  if (!comp) return "Precision@4";
  if (rm.scenario === "mixed") {
    const mean = isShrink ? comp.v3_mean : comp.noshrink_mean;
    const ci = isShrink ? comp.v3_ci_95 : comp.noshrink_ci_95;
    return `Precision@4 (study avg ${mean.toFixed(3)} [${ci[0].toFixed(3)}, ${ci[1].toFixed(3)}])`;
  } else {
    const p10 = comp.prev_0_10;
    const p20 = comp.prev_0_20;
    const m10 = isShrink ? p10.v3_mean : p10.noshrink_mean;
    const ci10 = isShrink ? p10.v3_ci_95 : p10.noshrink_ci_95;
    const m20 = isShrink ? p20.v3_mean : p20.noshrink_mean;
    const ci20 = isShrink ? p20.v3_ci_95 : p20.noshrink_ci_95;
    return `Precision@4 (study avg prev 0.10: ${m10.toFixed(3)} [${ci10[0].toFixed(3)}, ${ci10[1].toFixed(3)}], prev 0.20: ${m20.toFixed(3)} [${ci20[0].toFixed(3)}, ${ci20[1].toFixed(3)}])`;
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

/**
 * Render inline evidence chips with max 1 visible chip + "+N"
 */
export function renderEvidenceChips(evidenceStr) {
  const wrap = document.createElement("div");
  wrap.style.cssText = "display: flex; flex-wrap: wrap; gap: 4px; align-items: center;";

  const codes = (evidenceStr || "").split(",").map((s) => s.trim()).filter(Boolean);
  if (codes.length === 0) {
    const dash = document.createElement("span");
    dash.style.cssText = "color: var(--muted); font-size: 12px;";
    dash.textContent = "—";
    wrap.appendChild(dash);
    return wrap;
  }

  const fullList = codes.map((c) => `${c}: ${FEATURE_NAMES[c] || c}`).join(", ");
  const maxVisible = 1;
  const visible = codes.slice(0, maxVisible);
  const remaining = codes.length - maxVisible;

  for (const code of visible) {
    const chip = document.createElement("span");
    chip.className = "evidence-chip";
    chip.title = `${code}: ${FEATURE_NAMES[code] || code}`;
    chip.textContent = FEATURE_NAMES[code] || code;
    wrap.appendChild(chip);
  }

  if (remaining > 0) {
    const more = document.createElement("span");
    more.className = "evidence-chip";
    more.title = fullList;
    more.textContent = `+${remaining}`;
    wrap.appendChild(more);
  }

  return wrap;
}

/**
 * Render concise truth status cell with full wording in title attribute
 */
export function renderTruthCell(label) {
  const span = document.createElement("span");
  span.style.cssText = "padding-left: 6px; color: var(--ink); font-size: 12px; white-space: nowrap;";
  if (label === "TP") {
    span.style.borderLeft = "3px solid var(--fab, #c2410c)";
    span.textContent = "Fabricator ✓";
    span.title = "Fabricator — in top 4";
  } else if (label === "FN") {
    span.style.borderLeft = "3px solid var(--fab, #c2410c)";
    span.textContent = "Fabricator — missed";
    span.title = "Fabricator — missed";
  } else if (label === "FP") {
    span.style.borderLeft = "3px solid var(--honest, #2563eb)";
    span.textContent = "Honest — flagged";
    span.title = "Honest — flagged";
  } else {
    span.style.borderLeft = "3px solid var(--honest, #2563eb)";
    span.textContent = "Honest";
    span.title = "Honest";
  }
  return span;
}
