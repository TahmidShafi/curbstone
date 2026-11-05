import * as htl from "npm:htl";

/**
 * Render a small inline SVG 90% interval bar for a feature.
 * @param {number} est - Point estimate
 * @param {number} ciLow - Lower bound
 * @param {number} ciHigh - Upper bound
 * @param {number} width - Total SVG width in pixels
 * @param {number} height - Total SVG height in pixels
 */
export function renderIntervalBar(est, ciLow, ciHigh, width = 120, height = 20) {
  if (est == null || ciLow == null || ciHigh == null || isNaN(est) || isNaN(ciLow) || isNaN(ciHigh)) {
    return htl.html`<span style="color: #888; font-size: 11px;">—</span>`;
  }

  // Determine coordinate domain with margin
  const minVal = Math.min(ciLow, est);
  const maxVal = Math.max(ciHigh, est);
  const span = Math.max(0.1, maxVal - minVal);
  const domMin = minVal - 0.15 * span;
  const domMax = maxVal + 0.15 * span;

  const toX = (val) => {
    const frac = Math.max(0, Math.min(1, (val - domMin) / (domMax - domMin)));
    return 6 + frac * (width - 12);
  };

  const xLow = toX(ciLow);
  const xHigh = toX(ciHigh);
  const xEst = toX(est);
  const yMid = height / 2;

  return htl.html`<svg width="${width}" height="${height}" style="display: inline-block; vertical-align: middle;">
    <!-- Range bar -->
    <line x1="${xLow}" y1="${yMid}" x2="${xHigh}" y2="${yMid}" stroke="#4682b4" stroke-width="3" stroke-linecap="round" />
    <line x1="${xLow}" y1="${yMid - 4}" x2="${xLow}" y2="${yMid + 4}" stroke="#4682b4" stroke-width="2" />
    <line x1="${xHigh}" y1="${yMid - 4}" x2="${xHigh}" y2="${yMid + 4}" stroke="#4682b4" stroke-width="2" />
    <!-- Point estimate -->
    <circle cx="${xEst}" cy="${yMid}" r="3.5" fill="#d95f02" stroke="#fff" stroke-width="1" />
    <title>Estimate: ${est.toFixed(3)} [${ciLow.toFixed(3)}, ${ciHigh.toFixed(3)}]</title>
  </svg>`;
}

