import * as htl from "npm:htl";

/**
 * Render a mini inline SVG 90% interval bar for the risk table.
 * - grey band = honest 90% range
 * - vertical tick at 0 (or expected rate)
 * - dot = observed; filled --ink when outside band, hollow when inside.
 */
export function renderIntervalBar(est, ciLow, ciHigh, width = 110, height = 20, expectedVal = 0) {
  if (est == null || ciLow == null || ciHigh == null || isNaN(est) || isNaN(ciLow) || isNaN(ciHigh)) {
    return htl.html`<span style="color: var(--muted); font-size: 12px;">—</span>`;
  }

  const exp = expectedVal ?? 0;
  const minVal = Math.min(ciLow, est, exp);
  const maxVal = Math.max(ciHigh, est, exp);
  const span = Math.max(0.01, maxVal - minVal);
  const domMin = minVal - 0.15 * span;
  const domMax = maxVal + 0.15 * span;

  const toX = (val) => {
    const frac = Math.max(0, Math.min(1, (val - domMin) / (domMax - domMin)));
    return 6 + frac * (width - 12);
  };

  const xLow = toX(ciLow);
  const xHigh = toX(ciHigh);
  const xTick = toX(exp);
  const xEst = toX(est);
  const yMid = height / 2;

  const isOutside = est < ciLow || est > ciHigh;
  const dotFill = isOutside ? "var(--ink, #1f2937)" : "var(--surface, #ffffff)";
  const dotStroke = "var(--ink, #1f2937)";

  return htl.html`<svg width="${width}" height="${height}" style="display: inline-block; vertical-align: middle;">
    <!-- Honest 90% Range Band -->
    <rect x="${Math.min(xLow, xHigh)}" y="${yMid - 3}" width="${Math.max(2, Math.abs(xHigh - xLow))}" height="6" rx="3" fill="#e5e7eb" />
    <!-- Expected Rate Tick -->
    <line x1="${xTick}" y1="${yMid - 6}" x2="${xTick}" y2="${yMid + 6}" stroke="#9ca3af" stroke-width="1.5" stroke-linecap="round" />
    <!-- Observed Dot -->
    <circle cx="${xEst}" cy="${yMid}" r="3.5" fill="${dotFill}" stroke="${dotStroke}" stroke-width="1.5" />
    <title>Observed: ${est.toFixed(3)}, Honest 90% range: [${ciLow.toFixed(3)}, ${ciHigh.toFixed(3)}]</title>
  </svg>`;
}

/**
 * Render a larger SVG interval chart for feature cards in the evidence drawer.
 */
export function renderCardIntervalChart(est, ciLow, ciHigh, expectedVal = 0, width = 340, height = 48) {
  if (est == null || ciLow == null || ciHigh == null || isNaN(est) || isNaN(ciLow) || isNaN(ciHigh)) {
    return htl.html`<div style="color: var(--muted); font-size: 13px; font-style: italic;">No interval data</div>`;
  }

  const exp = expectedVal ?? 0;
  const minVal = Math.min(ciLow, est, exp);
  const maxVal = Math.max(ciHigh, est, exp);
  const span = Math.max(0.01, maxVal - minVal);
  const domMin = minVal - 0.15 * span;
  const domMax = maxVal + 0.15 * span;

  const toX = (val) => {
    const frac = Math.max(0, Math.min(1, (val - domMin) / (domMax - domMin)));
    return 16 + frac * (width - 32);
  };

  const xLow = toX(ciLow);
  const xHigh = toX(ciHigh);
  const xTick = toX(exp);
  const xEst = toX(est);
  const yMid = 20;

  const isOutside = est < ciLow || est > ciHigh;
  const dotFill = isOutside ? "var(--ink, #1f2937)" : "var(--surface, #ffffff)";
  const dotStroke = "var(--ink, #1f2937)";

  return htl.html`<svg width="100%" height="${height}" viewBox="0 0 ${width} ${height}" style="display: block; overflow: visible; font-variant-numeric: tabular-nums;">
    <!-- Base track line -->
    <line x1="16" y1="${yMid}" x2="${width - 16}" y2="${yMid}" stroke="#e5e7eb" stroke-width="1" />
    <!-- Honest 90% Range Band -->
    <rect x="${Math.min(xLow, xHigh)}" y="${yMid - 4}" width="${Math.max(3, Math.abs(xHigh - xLow))}" height="8" rx="4" fill="#e5e7eb" />
    <!-- Expected Rate Tick -->
    <line x1="${xTick}" y1="${yMid - 8}" x2="${xTick}" y2="${yMid + 8}" stroke="#9ca3af" stroke-width="2" stroke-linecap="round" />
    <!-- Observed Dot -->
    <circle cx="${xEst}" cy="${yMid}" r="5" fill="${dotFill}" stroke="${dotStroke}" stroke-width="2" />
    <!-- Axis Labels -->
    <text x="${xTick}" y="${yMid + 20}" font-size="11" fill="#6b7280" text-anchor="middle" font-family="sans-serif">${exp === 0 ? "0" : exp.toFixed(2)}</text>
    <text x="${xLow}" y="${yMid - 10}" font-size="11" fill="#6b7280" text-anchor="middle" font-family="sans-serif">${ciLow.toFixed(2)}</text>
    <text x="${xHigh}" y="${yMid - 10}" font-size="11" fill="#6b7280" text-anchor="middle" font-family="sans-serif">${ciHigh.toFixed(2)}</text>
    <text x="${xEst}" y="${yMid - 10}" font-size="11" font-weight="600" fill="#1f2937" text-anchor="middle" font-family="sans-serif">${est.toFixed(2)}</text>
  </svg>`;
}
