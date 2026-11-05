import * as htl from "npm:htl";
import { renderIntervalBar } from "./intervalBar.js";
import { renderEvidenceDrawer, FEATURE_NAMES } from "./evidenceDrawer.js";

/**
 * Render the full-width accessible risk table with inline evidence drawer.
 */
export function renderRiskTable({
  rows = [],
  selectedId = null,
  onSelect = () => {},
  isRevealed = false,
  evidenceDict = {},
  submissions = [],
  villages = [],
}) {
  const colSpan = isRevealed ? 9 : 8;
  const maxRisk = Math.max(...rows.map((r) => r.risk_score || 0), 1);

  return htl.html`<div>
    <!-- Legend line above the table -->
    <div style="font-size: 13px; color: var(--muted); margin-bottom: 8px;">
      Observed vs honest range: grey band = honest 90% range, vertical tick = expected rate / 0, dot = observed (filled = outside range, hollow = within range).
    </div>

    <div style="overflow-x: auto; background: var(--surface); border: 1px solid var(--line); border-radius: 8px;">
      <table style="width: 100%; border-collapse: collapse; font-size: 13px; text-align: left;">
        <thead>
          <tr style="background: var(--surface); border-bottom: 1px solid var(--line); color: var(--ink); font-weight: 600;">
            <th style="padding: 10px 12px; width: 45px;">Rank</th>
            <th style="padding: 10px 12px;">Enumerator</th>
            <th style="padding: 10px 12px; text-align: right;">Interviews</th>
            <th style="padding: 10px 12px; text-align: right;">Risk</th>
            <th style="padding: 10px 12px;">Evidence</th>
            <th style="padding: 10px 12px; text-align: center;">Observed vs honest range</th>
            <th style="padding: 10px 12px; text-align: right;">Rule hits</th>
            <th style="padding: 10px 12px; text-align: right;">Back-checks</th>
            ${isRevealed ? htl.html`<th style="padding: 10px 12px;">Truth</th>` : ""}
          </tr>
        </thead>
        <tbody>
          ${rows.map((row) => {
            const isSelected = row.enumerator_id === selectedId;
            const bg = isSelected ? "var(--accent-soft)" : "var(--surface)";
            const evCodes = (row.evidence || "").split(",").map((s) => s.trim()).filter(Boolean);

            return [
              htl.html`<tr
                style="background: ${bg}; border-bottom: 1px solid var(--line); cursor: pointer; transition: background 0.1s;"
                tabindex="0"
                role="button"
                aria-expanded="${isSelected}"
                aria-label="Toggle evidence for ${row.enumerator_id}"
                onclick=${() => onSelect(isSelected ? null : row.enumerator_id)}
                onkeydown=${(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onSelect(isSelected ? null : row.enumerator_id);
                  }
                }}
              >
                <td style="padding: 8px 12px; color: var(--muted);" class="tabular-nums">${row.rank}</td>
                <td style="padding: 8px 12px;" class="enum-id">${row.enumerator_id}</td>
                <td style="padding: 8px 12px; text-align: right; color: var(--muted);" class="tabular-nums">${row.n}</td>
                <td style="padding: 8px 12px; text-align: right;" class="tabular-nums">
                  <div style="display: inline-flex; align-items: center; justify-content: flex-end; gap: 8px;">
                    <span>${row.risk_score.toFixed(1)}</span>
                    <div style="width: 36px; height: 3px; background: #e5e7eb; border-radius: 2px; overflow: hidden; display: inline-block;">
                      <div style="width: ${Math.min(36, Math.round((row.risk_score / maxRisk) * 36))}px; height: 100%; background: #9ca3af;"></div>
                    </div>
                  </div>
                </td>
                <td style="padding: 8px 12px;">
                  ${evCodes.length > 0
                    ? evCodes.map((code) => htl.html`<span class="evidence-chip" title="${code}">${FEATURE_NAMES[code] || code}</span>`)
                    : htl.html`<span style="color: var(--muted); font-size: 12px;">—</span>`}
                </td>
                <td style="padding: 6px 12px; text-align: center;">
                  ${renderIntervalBar(row.strongest_est, row.strongest_ci_low, row.strongest_ci_high, 110, 18, 0)}
                </td>
                <td style="padding: 8px 12px; text-align: right; color: var(--muted);" class="tabular-nums">
                  ${row.rule_hits}
                </td>
                <td style="padding: 8px 12px; text-align: right; font-weight: 600; color: var(--ink);" class="tabular-nums">
                  ${row.allocated_backchecks}
                </td>
                ${isRevealed ? htl.html`<td style="padding: 8px 12px;">${renderTruthCell(row.truth_label)}</td>` : ""}
              </tr>`,

              /* Labelled divider after rank 4 */
              row.rank === 4
                ? htl.html`<tr style="background: var(--page); border-top: 1px solid var(--line); border-bottom: 1px solid var(--line);">
                    <td colspan="${colSpan}" style="padding: 6px 12px; font-size: 12px; font-weight: 600; color: var(--muted); text-align: center;">
                      Top 4 — evaluation cut-off (k = 4)
                    </td>
                  </tr>`
                : null,

              /* Inline drawer expansion under the clicked row */
              isSelected
                ? htl.html`<tr style="background: var(--page); border-bottom: 1px solid var(--line);">
                    <td colspan="${colSpan}" style="padding: 16px 20px;">
                      ${renderEvidenceDrawer({
                        enumeratorId: row.enumerator_id,
                        enumEvidence: evidenceDict[row.enumerator_id],
                        allSubmissions: submissions,
                        villages: villages,
                        onClose: () => onSelect(null),
                      })}
                    </td>
                  </tr>`
                : null,
            ];
          })}
        </tbody>
      </table>
    </div>
  </div>`;
}

function renderTruthCell(label) {
  if (label === "TP") {
    return htl.html`<span style="border-left: 3px solid var(--fab, #c2410c); padding-left: 6px; color: var(--ink); font-size: 12px;">Fabricator — in top 4</span>`;
  }
  if (label === "FN") {
    return htl.html`<span style="border-left: 3px solid var(--fab, #c2410c); padding-left: 6px; color: var(--ink); font-size: 12px;">Fabricator — missed</span>`;
  }
  if (label === "FP") {
    return htl.html`<span style="border-left: 3px solid var(--honest, #2563eb); padding-left: 6px; color: var(--ink); font-size: 12px;">Honest — flagged</span>`;
  }
  return htl.html`<span style="border-left: 3px solid var(--honest, #2563eb); padding-left: 6px; color: var(--ink); font-size: 12px;">Honest</span>`;
}
