import * as htl from "npm:htl";
import { renderIntervalBar } from "./intervalBar.js";

/**
 * Render the interactive accessible risk table.
 */
export function renderRiskTable({
  rows = [],
  selectedId = null,
  onSelect = () => {},
  isRevealed = false,
}) {
  return htl.html`<div style="overflow-x: auto; margin: 16px 0; border: 1px solid #e2e8f0; border-radius: 6px;">
    <table style="width: 100%; border-collapse: collapse; font-size: 0.875rem; text-align: left;">
      <thead>
        <tr style="background: #f8fafc; border-bottom: 2px solid #cbd5e1; color: #334155;">
          <th style="padding: 10px 12px; width: 50px;">Rank</th>
          <th style="padding: 10px 12px;">Enumerator</th>
          <th style="padding: 10px 12px; text-align: right;">N</th>
          <th style="padding: 10px 12px; text-align: right;">Risk Score</th>
          <th style="padding: 10px 12px;">Top Evidence</th>
          <th style="padding: 10px 12px; text-align: center;">90% CI (Primary)</th>
          <th style="padding: 10px 12px; text-align: right;">Rule Hits</th>
          <th style="padding: 10px 12px; text-align: right; background: #eff6ff;">Back-checks</th>
          ${isRevealed ? htl.html`<th style="padding: 10px 12px; background: #fdf2f8;">Ground Truth</th>` : ""}
        </tr>
      </thead>
      <tbody>
        ${rows.map((row) => {
          const isSelected = row.enumerator_id === selectedId;
          const bg = isSelected ? "#e0f2fe" : row.rank % 2 === 0 ? "#ffffff" : "#fbfcfe";

          return htl.html`<tr
            style="background: ${bg}; border-bottom: 1px solid #f1f5f9; cursor: pointer; transition: background 0.1s;"
            tabindex="0"
            role="button"
            aria-label="Inspect evidence for ${row.enumerator_id}"
            onclick=${() => onSelect(row.enumerator_id)}
            onkeydown=${(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect(row.enumerator_id);
              }
            }}
          >
            <td style="padding: 8px 12px; font-weight: 600; color: #475569;">${row.rank}</td>
            <td style="padding: 8px 12px; font-family: monospace; font-weight: bold; color: ${isSelected ? "#0369a1" : "#1e293b"};">
              ${row.enumerator_id}
            </td>
            <td style="padding: 8px 12px; text-align: right; color: #64748b;">${row.n}</td>
            <td style="padding: 8px 12px; text-align: right; font-weight: 600; color: ${row.risk_score >= 1.3 ? "#b91c1c" : "#334155"};">
              ${row.risk_score.toFixed(4)}
            </td>
            <td style="padding: 8px 12px;">
              ${row.evidence
                ? htl.html`<span style="background: #fee2e2; color: #991b1b; padding: 2px 6px; border-radius: 4px; font-weight: 600; font-size: 0.775rem;">${row.evidence}</span>`
                : htl.html`<span style="color: #94a3b8; font-size: 0.8rem;">—</span>`}
            </td>
            <td style="padding: 6px 12px; text-align: center;">
              ${renderIntervalBar(row.strongest_est, row.strongest_ci_low, row.strongest_ci_high, 110, 18)}
            </td>
            <td style="padding: 8px 12px; text-align: right; font-weight: 600; color: ${row.rule_hits > 0 ? "#c2410c" : "#64748b"};">
              ${row.rule_hits}
            </td>
            <td style="padding: 8px 12px; text-align: right; font-weight: bold; color: #1d4ed8; background: ${isSelected ? "#bae6fd" : "#f8fafc"};">
              ${row.allocated_backchecks}
            </td>
            ${isRevealed
              ? htl.html`<td style="padding: 8px 12px; background: ${isSelected ? "#fce7f3" : "#fdf4f8"}; font-size: 0.8rem;">
                  ${renderTruthBadge(row.truth_label)}
                </td>`
              : ""}
          </tr>`;
        })}
      </tbody>
    </table>
  </div>`;
}

function renderTruthBadge(label) {
  if (label === "TP") {
    return htl.html`<span style="background: #fee2e2; color: #991b1b; border: 1px solid #f87171; padding: 2px 6px; border-radius: 4px; font-weight: bold;">[TP] Fabricator</span>`;
  }
  if (label === "FP") {
    return htl.html`<span style="background: #ffedd5; color: #9a3412; border: 1px solid #fb923c; padding: 2px 6px; border-radius: 4px; font-weight: bold;">[FP] Honest (False Flag)</span>`;
  }
  if (label === "FN") {
    return htl.html`<span style="background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; padding: 2px 6px; border-radius: 4px; font-weight: bold;">[FN] Fabricator (Missed)</span>`;
  }
  return htl.html`<span style="color: #64748b;">[TN] Honest</span>`;
}
