import * as Plot from "npm:@observablehq/plot";

/**
 * Chart (a): Precision@4 by prevalence, faceted by workload (Low / Mixed / High)
 * Dots for v3, no shrinkage, rules, plus dashed line for max achievable.
 */
export function renderPrecisionChart(containerWidth = 840) {
  const width = Math.max(320, containerWidth);

  const precisionData = [
    // Low Workload
    { workload: "Low [5, 15]", prev: 0.02, method: "Scoring v3", prec: 0.0979 },
    { workload: "Low [5, 15]", prev: 0.02, method: "No shrinkage", prec: 0.0979 },
    { workload: "Low [5, 15]", prev: 0.02, method: "Rules", prec: 0.0625 },
    { workload: "Low [5, 15]", prev: 0.05, method: "Scoring v3", prec: 0.2854 },
    { workload: "Low [5, 15]", prev: 0.05, method: "No shrinkage", prec: 0.2812 },
    { workload: "Low [5, 15]", prev: 0.05, method: "Rules", prec: 0.1417 },
    { workload: "Low [5, 15]", prev: 0.10, method: "Scoring v3", prec: 0.4938 },
    { workload: "Low [5, 15]", prev: 0.10, method: "No shrinkage", prec: 0.3792 },
    { workload: "Low [5, 15]", prev: 0.10, method: "Rules", prec: 0.3563 },
    { workload: "Low [5, 15]", prev: 0.20, method: "Scoring v3", prec: 0.7042 },
    { workload: "Low [5, 15]", prev: 0.20, method: "No shrinkage", prec: 0.5458 },
    { workload: "Low [5, 15]", prev: 0.20, method: "Rules", prec: 0.6125 },

    // Mixed Workload
    { workload: "Mixed [5, 60]", prev: 0.02, method: "Scoring v3", prec: 0.1375 },
    { workload: "Mixed [5, 60]", prev: 0.02, method: "No shrinkage", prec: 0.1500 },
    { workload: "Mixed [5, 60]", prev: 0.02, method: "Rules", prec: 0.0625 },
    { workload: "Mixed [5, 60]", prev: 0.05, method: "Scoring v3", prec: 0.2750 },
    { workload: "Mixed [5, 60]", prev: 0.05, method: "No shrinkage", prec: 0.2771 },
    { workload: "Mixed [5, 60]", prev: 0.05, method: "Rules", prec: 0.1479 },
    { workload: "Mixed [5, 60]", prev: 0.10, method: "Scoring v3", prec: 0.4688 },
    { workload: "Mixed [5, 60]", prev: 0.10, method: "No shrinkage", prec: 0.5167 },
    { workload: "Mixed [5, 60]", prev: 0.10, method: "Rules", prec: 0.3375 },
    { workload: "Mixed [5, 60]", prev: 0.20, method: "Scoring v3", prec: 0.7729 },
    { workload: "Mixed [5, 60]", prev: 0.20, method: "No shrinkage", prec: 0.7333 },
    { workload: "Mixed [5, 60]", prev: 0.20, method: "Rules", prec: 0.5875 },

    // High Workload
    { workload: "High [40, 60]", prev: 0.02, method: "Scoring v3", prec: 0.1521 },
    { workload: "High [40, 60]", prev: 0.02, method: "No shrinkage", prec: 0.1500 },
    { workload: "High [40, 60]", prev: 0.02, method: "Rules", prec: 0.0479 },
    { workload: "High [40, 60]", prev: 0.05, method: "Scoring v3", prec: 0.2792 },
    { workload: "High [40, 60]", prev: 0.05, method: "No shrinkage", prec: 0.2875 },
    { workload: "High [40, 60]", prev: 0.05, method: "Rules", prec: 0.1875 },
    { workload: "High [40, 60]", prev: 0.10, method: "Scoring v3", prec: 0.5229 },
    { workload: "High [40, 60]", prev: 0.10, method: "No shrinkage", prec: 0.5729 },
    { workload: "High [40, 60]", prev: 0.10, method: "Rules", prec: 0.2812 },
    { workload: "High [40, 60]", prev: 0.20, method: "Scoring v3", prec: 0.8021 },
    { workload: "High [40, 60]", prev: 0.20, method: "No shrinkage", prec: 0.7750 },
    { workload: "High [40, 60]", prev: 0.20, method: "Rules", prec: 0.5979 },
  ];

  const maxLineData = [];
  for (const wl of ["Low [5, 15]", "Mixed [5, 60]", "High [40, 60]"]) {
    maxLineData.push(
      { workload: wl, prev: 0.02, max: 0.25 },
      { workload: wl, prev: 0.05, max: 0.50 },
      { workload: wl, prev: 0.10, max: 1.00 },
      { workload: wl, prev: 0.20, max: 1.00 }
    );
  }

  return Plot.plot({
    width: width,
    height: 280,
    marginLeft: 50,
    marginBottom: 40,
    grid: true,
    color: {
      domain: ["Scoring v3", "No shrinkage", "Rules"],
      range: ["#2563eb", "#93c5fd", "#6b7280"],
      legend: true,
    },
    x: { label: "Fraud prevalence (rate)", tickFormat: ".2f", domain: [0, 0.22] },
    y: { label: "Precision@4", domain: [0, 1.05] },
    fx: { label: "Workload profile" },
    marks: [
      Plot.line(maxLineData, {
        fx: "workload",
        x: "prev",
        y: "max",
        stroke: "#9ca3af",
        strokeDasharray: "4,4",
        strokeWidth: 1.5,
        title: () => "Max achievable precision",
      }),
      Plot.line(precisionData, {
        fx: "workload",
        x: "prev",
        y: "prec",
        z: "method",
        stroke: "method",
        strokeWidth: 1.5,
      }),
      Plot.dot(precisionData, {
        fx: "workload",
        x: "prev",
        y: "prec",
        fill: "method",
        r: 4,
        title: (d) => `${d.workload}\nPrevalence: ${d.prev}\n${d.method}: ${d.prec.toFixed(4)}`,
      }),
    ],
  });
}

/**
 * Chart (b): Recall@4 by fraud mode: dot + Wilson 95% CI whisker per method,
 * modes sorted by v3 descending; partial_section marked "held-out".
 */
export function renderRecallChart(containerWidth = 840) {
  const width = Math.max(320, containerWidth);

  const recallData = [
    { mode: "copy_paste", method: "Scoring v3", recall: 0.9596, ci_lo: 0.9454, ci_hi: 0.9702, count: "950/990" },
    { mode: "copy_paste", method: "No shrinkage", recall: 0.7485, ci_lo: 0.7205, ci_hi: 0.7745, count: "741/990" },
    { mode: "copy_paste", method: "Rules", recall: 0.8253, ci_lo: 0.8004, ci_hi: 0.8476, count: "817/990" },

    { mode: "partial_section (held-out)", method: "Scoring v3", recall: 0.7333, ci_lo: 0.4805, ci_hi: 0.8910, count: "11/15" },
    { mode: "partial_section (held-out)", method: "No shrinkage", recall: 0.4667, ci_lo: 0.2481, ci_hi: 0.6988, count: "7/15" },
    { mode: "partial_section (held-out)", method: "Rules", recall: 0.0667, ci_lo: 0.0119, ci_hi: 0.2982, count: "1/15" },

    { mode: "invented_gps", method: "Scoring v3", recall: 0.5468, ci_lo: 0.5162, ci_hi: 0.5770, count: "561/1026" },
    { mode: "invented_gps", method: "No shrinkage", recall: 0.4854, ci_lo: 0.4549, ci_hi: 0.5160, count: "498/1026" },
    { mode: "invented_gps", method: "Rules", recall: 0.0702, ci_lo: 0.0561, ci_hi: 0.0875, count: "72/1026" },

    { mode: "straight_lining", method: "Scoring v3", recall: 0.3683, ci_lo: 0.3405, ci_hi: 0.3970, count: "411/1116" },
    { mode: "straight_lining", method: "No shrinkage", recall: 0.5645, ci_lo: 0.5353, ci_hi: 0.5933, count: "630/1116" },
    { mode: "straight_lining", method: "Rules", recall: 0.0762, ci_lo: 0.0620, ci_hi: 0.0932, count: "85/1116" },

    { mode: "rushed", method: "Scoring v3", recall: 0.3465, ci_lo: 0.3175, ci_hi: 0.3766, count: "343/990" },
    { mode: "rushed", method: "No shrinkage", recall: 0.3626, ci_lo: 0.3333, ci_hi: 0.3931, count: "359/990" },
    { mode: "rushed", method: "Rules", recall: 0.6273, ci_lo: 0.5967, ci_hi: 0.6568, count: "621/990" },

    { mode: "too_average", method: "Scoring v3", recall: 0.1025, ci_lo: 0.0870, ci_hi: 0.1203, count: "131/1278" },
    { mode: "too_average", method: "No shrinkage", recall: 0.0469, ci_lo: 0.0366, ci_hi: 0.0600, count: "60/1278" },
    { mode: "too_average", method: "Rules", recall: 0.0376, ci_lo: 0.0284, ci_hi: 0.0494, count: "48/1278" },
  ];

  const dyMap = { "Scoring v3": -6, "No shrinkage": 0, "Rules": 6 };

  return Plot.plot({
    width: width,
    height: 320,
    marginLeft: 170,
    marginRight: 30,
    marginBottom: 40,
    grid: true,
    color: {
      domain: ["Scoring v3", "No shrinkage", "Rules"],
      range: ["#2563eb", "#93c5fd", "#6b7280"],
      legend: true,
    },
    x: { label: "Recall@4 (with Wilson 95% CI)", domain: [0, 1.02] },
    y: {
      label: "Fraud mode (sorted by v3 recall)",
      domain: [
        "copy_paste",
        "partial_section (held-out)",
        "invented_gps",
        "straight_lining",
        "rushed",
        "too_average",
      ],
    },
    marks: [
      Plot.ruleX([0, 1], { stroke: "#e5e7eb" }),
      Plot.link(recallData, {
        x1: "ci_lo",
        x2: "ci_hi",
        y: "mode",
        dy: (d) => dyMap[d.method] || 0,
        stroke: "method",
        strokeWidth: 2,
      }),
      Plot.dot(recallData, {
        x: "recall",
        y: "mode",
        dy: (d) => dyMap[d.method] || 0,
        fill: "method",
        r: 4,
        title: (d) => `${d.mode} (${d.method})\nRecall: ${d.recall.toFixed(4)} (${d.count})\n95% CI: [${d.ci_lo.toFixed(4)}, ${d.ci_hi.toFixed(4)}]`,
      }),
    ],
  });
}

/**
 * Chart (c): Shrinkage effect (v3 − no shrinkage) on precision@4 by workload:
 * dot + 95% CI, vertical zero line.
 */
export function renderShrinkageChart(containerWidth = 840) {
  const width = Math.max(320, containerWidth);

  const shrinkageData = [
    { workload: "Low [5, 15]", diff: 0.0693, ci_lo: 0.0521, ci_hi: 0.0865 },
    { workload: "Mixed [5, 60]", diff: -0.0057, ci_lo: -0.0214, ci_hi: 0.0099 },
    { workload: "High [40, 60]", diff: -0.0073, ci_lo: -0.0219, ci_hi: 0.0078 },
    { workload: "Overall (72 Configs)", diff: 0.0187, ci_lo: 0.0094, ci_hi: 0.0281 },
  ];

  return Plot.plot({
    width: width,
    height: 220,
    marginLeft: 150,
    marginRight: 40,
    marginBottom: 40,
    grid: true,
    x: {
      label: "Shrinkage effect on Precision@4 (v3 − no shrinkage)",
      domain: [-0.04, 0.10],
    },
    y: {
      label: "Workload profile",
      domain: [
        "Low [5, 15]",
        "Mixed [5, 60]",
        "High [40, 60]",
        "Overall (72 Configs)",
      ],
    },
    marks: [
      Plot.ruleX([0], { stroke: "#6b7280", strokeDasharray: "4,4", strokeWidth: 1.5 }),
      Plot.link(shrinkageData, {
        x1: "ci_lo",
        x2: "ci_hi",
        y: "workload",
        stroke: "#2563eb",
        strokeWidth: 2.5,
      }),
      Plot.dot(shrinkageData, {
        x: "diff",
        y: "workload",
        fill: "#2563eb",
        r: 5,
        title: (d) => `${d.workload}\nDifference: ${d.diff > 0 ? "+" : ""}${d.diff.toFixed(4)}\n95% CI: [${d.ci_lo.toFixed(4)}, ${d.ci_hi.toFixed(4)}]`,
      }),
    ],
  });
}
