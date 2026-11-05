/**
 * Render a mini inline SVG 90% interval bar for the risk table.
 * - grey band = honest 90% range (#cbd5e1, height 8px)
 * - vertical tick at 0 / expected rate (#64748b)
 * - dot = observed (radius 4; filled --ink when outside band, hollow when inside)
 */
export function renderIntervalBar(est, ciLow, ciHigh, width = 110, height = 20, expectedVal = 0, isResponsive = false) {
  if (est == null || ciLow == null || ciHigh == null || isNaN(est) || isNaN(ciLow) || isNaN(ciHigh)) {
    const span = document.createElement("span");
    span.style.cssText = "color: var(--muted); font-size: 12px;";
    span.textContent = "—";
    return span;
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

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  if (isResponsive) {
    svg.setAttribute("width", "100%");
    svg.setAttribute("height", String(height));
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.style.cssText = "display: block; width: 100%; max-width: 100%;";
  } else {
    svg.setAttribute("width", String(width));
    svg.setAttribute("height", String(height));
    svg.style.cssText = "display: inline-block; vertical-align: middle;";
  }

  // Honest 90% band: fill #cbd5e1, height 8px
  const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  rect.setAttribute("x", String(Math.min(xLow, xHigh)));
  rect.setAttribute("y", String(yMid - 4));
  rect.setAttribute("width", String(Math.max(2, Math.abs(xHigh - xLow))));
  rect.setAttribute("height", "8");
  rect.setAttribute("rx", "4");
  rect.setAttribute("fill", "#cbd5e1");
  svg.appendChild(rect);

  // Expected tick: #64748b
  const tick = document.createElementNS("http://www.w3.org/2000/svg", "line");
  tick.setAttribute("x1", String(xTick));
  tick.setAttribute("y1", String(yMid - 6));
  tick.setAttribute("x2", String(xTick));
  tick.setAttribute("y2", String(yMid + 6));
  tick.setAttribute("stroke", "#64748b");
  tick.setAttribute("stroke-width", "2");
  tick.setAttribute("stroke-linecap", "round");
  svg.appendChild(tick);

  // Dot: radius 4
  const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  circle.setAttribute("cx", String(xEst));
  circle.setAttribute("cy", String(yMid));
  circle.setAttribute("r", "4");
  circle.setAttribute("fill", dotFill);
  circle.setAttribute("stroke", dotStroke);
  circle.setAttribute("stroke-width", "1.5");
  svg.appendChild(circle);

  const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
  title.textContent = `Observed: ${est.toFixed(3)}, Honest 90% range: [${ciLow.toFixed(3)}, ${ciHigh.toFixed(3)}]`;
  svg.appendChild(title);

  return svg;
}

/**
 * Render a larger SVG interval chart for feature cards in the evidence drawer.
 * - grey band #cbd5e1, height 8px
 * - expected tick #64748b
 * - dot radius 4
 * - small axis labels (11px)
 */
export function renderCardIntervalChart(est, ciLow, ciHigh, expectedVal = 0, width = 340, height = 48) {
  if (est == null || ciLow == null || ciHigh == null || isNaN(est) || isNaN(ciLow) || isNaN(ciHigh)) {
    const fallback = document.createElement("div");
    fallback.style.cssText = "color: var(--muted); font-size: 13px; font-style: italic;";
    fallback.textContent = "No interval data";
    return fallback;
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

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", "100%");
  svg.setAttribute("height", String(height));
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.style.cssText = "display: block; width: 100%; max-width: 100%; height: auto; font-variant-numeric: tabular-nums;";

  const track = document.createElementNS("http://www.w3.org/2000/svg", "line");
  track.setAttribute("x1", "16");
  track.setAttribute("y1", String(yMid));
  track.setAttribute("x2", String(width - 16));
  track.setAttribute("y2", String(yMid));
  track.setAttribute("stroke", "#e5e7eb");
  track.setAttribute("stroke-width", "1");
  svg.appendChild(track);

  // Band: #cbd5e1, height 8px
  const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  rect.setAttribute("x", String(Math.min(xLow, xHigh)));
  rect.setAttribute("y", String(yMid - 4));
  rect.setAttribute("width", String(Math.max(3, Math.abs(xHigh - xLow))));
  rect.setAttribute("height", "8");
  rect.setAttribute("rx", "4");
  rect.setAttribute("fill", "#cbd5e1");
  svg.appendChild(rect);

  // Tick: #64748b
  const tick = document.createElementNS("http://www.w3.org/2000/svg", "line");
  tick.setAttribute("x1", String(xTick));
  tick.setAttribute("y1", String(yMid - 8));
  tick.setAttribute("x2", String(xTick));
  tick.setAttribute("y2", String(yMid + 8));
  tick.setAttribute("stroke", "#64748b");
  tick.setAttribute("stroke-width", "2");
  tick.setAttribute("stroke-linecap", "round");
  svg.appendChild(tick);

  // Dot: radius 4
  const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  circle.setAttribute("cx", String(xEst));
  circle.setAttribute("cy", String(yMid));
  circle.setAttribute("r", "4");
  circle.setAttribute("fill", dotFill);
  circle.setAttribute("stroke", dotStroke);
  circle.setAttribute("stroke-width", "2");
  svg.appendChild(circle);

  const addText = (text, x, y, anchor = "middle", color = "#64748b", weight = "normal") => {
    const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
    t.setAttribute("x", String(x));
    t.setAttribute("y", String(y));
    t.setAttribute("font-size", "11");
    t.setAttribute("fill", color);
    t.setAttribute("text-anchor", anchor);
    t.setAttribute("font-family", "sans-serif");
    if (weight !== "normal") t.setAttribute("font-weight", weight);
    t.textContent = text;
    svg.appendChild(t);
  };

  addText(exp === 0 ? "0" : exp.toFixed(2), xTick, yMid + 20);
  addText(ciLow.toFixed(2), xLow, yMid - 10);
  addText(ciHigh.toFixed(2), xHigh, yMid - 10);
  addText(est.toFixed(2), xEst, yMid - 10, "middle", "#1f2937", "600");

  return svg;
}
