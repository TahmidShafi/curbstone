import { renderIntervalBar } from "./intervalBar.js";
import { FEATURE_NAMES } from "./demoHelpers.js";

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
  drawerRenderer = null,
}) {
  const colSpan = isRevealed ? 9 : 8;
  const maxRisk = Math.max(...rows.map((r) => r.risk_score || 0), 1);

  const container = document.createElement("div");

  const legend = document.createElement("div");
  legend.style.cssText = "font-size: 13px; color: var(--muted); margin-bottom: 8px;";
  legend.textContent = "Observed vs honest range: grey band = honest 90% range, vertical tick = expected rate / 0, dot = observed (filled = outside range, hollow = within range).";
  container.appendChild(legend);

  const wrapper = document.createElement("div");
  wrapper.style.cssText = "overflow-x: auto; background: var(--surface); border: 1px solid var(--line); border-radius: 8px;";

  const table = document.createElement("table");
  table.style.cssText = "width: 100%; border-collapse: collapse; font-size: 13px; text-align: left;";

  const thead = document.createElement("thead");
  thead.innerHTML = `
    <tr style="background: var(--surface); border-bottom: 1px solid var(--line); color: var(--ink); font-weight: 600;">
      <th style="padding: 10px 12px; width: 45px; white-space: nowrap;">Rank</th>
      <th style="padding: 10px 12px; white-space: nowrap;">Enumerator</th>
      <th style="padding: 10px 12px; text-align: right; white-space: nowrap;">Interviews</th>
      <th style="padding: 10px 12px; text-align: right; white-space: nowrap;">Risk</th>
      <th style="padding: 10px 12px; white-space: nowrap;">Evidence</th>
      <th style="padding: 10px 12px; text-align: center; min-width: 140px; white-space: nowrap;">vs honest range</th>
      <th style="padding: 10px 12px; text-align: right; white-space: nowrap;">Rule hits</th>
      <th style="padding: 10px 12px; text-align: right; white-space: nowrap;">Back-checks</th>
      ${isRevealed ? '<th style="padding: 10px 12px; white-space: nowrap;">Truth</th>' : ""}
    </tr>
  `;
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const row of rows) {
    const isSelected = row.enumerator_id === selectedId;
    const tr = renderRowNode(row, isSelected, maxRisk, isRevealed, onSelect);
    tbody.appendChild(tr);

    if (row.rank === 4) {
      const dividerTr = document.createElement("tr");
      dividerTr.style.cssText = "background: var(--page); border-top: 1px solid var(--line); border-bottom: 1px solid var(--line);";
      const td = document.createElement("td");
      td.colSpan = colSpan;
      td.style.cssText = "padding: 6px 12px; font-size: 12px; font-weight: 600; color: var(--muted); text-align: center;";
      td.textContent = "Top 4 — evaluation cut-off (k = 4)";
      dividerTr.appendChild(td);
      tbody.appendChild(dividerTr);
    }

    if (isSelected) {
      const drawerTr = document.createElement("tr");
      drawerTr.style.cssText = "background: var(--page); border-bottom: 1px solid var(--line);";
      const td = document.createElement("td");
      td.colSpan = colSpan;
      td.style.cssText = "padding: 16px 20px;";
      if (drawerRenderer) {
        td.appendChild(drawerRenderer({
          enumeratorId: row.enumerator_id,
          enumEvidence: evidenceDict[row.enumerator_id],
          allSubmissions: submissions,
          villages: villages,
          onClose: () => onSelect(null),
        }));
      } else {
        const fallback = document.createElement("div");
        fallback.textContent = `Evidence for ${row.enumerator_id}`;
        td.appendChild(fallback);
      }
      drawerTr.appendChild(td);
      tbody.appendChild(drawerTr);
    }
  }

  table.appendChild(tbody);
  wrapper.appendChild(table);
  container.appendChild(wrapper);
  return container;
}

export function renderRowNode(row, isSelected, maxRisk, isRevealed, onSelect) {
  const bg = isSelected ? "var(--accent-soft)" : "var(--surface)";
  const evCodes = (row.evidence || "").split(",").map((s) => s.trim()).filter(Boolean);

  const tr = document.createElement("tr");
  tr.style.cssText = `background: ${bg}; border-bottom: 1px solid var(--line); cursor: pointer; transition: background 0.1s;`;
  tr.tabIndex = 0;
  tr.setAttribute("role", "button");
  tr.setAttribute("aria-expanded", String(isSelected));
  tr.setAttribute("aria-label", `Toggle evidence for ${row.enumerator_id}`);
  tr.onclick = () => onSelect(isSelected ? null : row.enumerator_id);
  tr.onkeydown = (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onSelect(isSelected ? null : row.enumerator_id);
    }
  };

  const tdRank = document.createElement("td");
  tdRank.style.cssText = "padding: 8px 12px; color: var(--muted);";
  tdRank.className = "tabular-nums";
  tdRank.textContent = String(row.rank);
  tr.appendChild(tdRank);

  const tdEnum = document.createElement("td");
  tdEnum.style.cssText = "padding: 8px 12px;";
  tdEnum.className = "enum-id";
  tdEnum.textContent = row.enumerator_id;
  tr.appendChild(tdEnum);

  const tdN = document.createElement("td");
  tdN.style.cssText = "padding: 8px 12px; text-align: right; color: var(--muted);";
  tdN.className = "tabular-nums";
  tdN.textContent = String(row.n);
  tr.appendChild(tdN);

  const tdRisk = document.createElement("td");
  tdRisk.style.cssText = "padding: 8px 12px; text-align: right;";
  tdRisk.className = "tabular-nums";
  const riskBox = document.createElement("div");
  riskBox.style.cssText = "display: inline-flex; align-items: center; justify-content: flex-end; gap: 8px;";
  const riskSpan = document.createElement("span");
  riskSpan.textContent = row.risk_score.toFixed(1);
  riskBox.appendChild(riskSpan);
  const barTrack = document.createElement("div");
  barTrack.style.cssText = "width: 36px; height: 3px; background: #e5e7eb; border-radius: 2px; overflow: hidden; display: inline-block;";
  const barFill = document.createElement("div");
  const barW = Math.min(36, Math.round((row.risk_score / maxRisk) * 36));
  barFill.style.cssText = `width: ${barW}px; height: 100%; background: #9ca3af;`;
  barTrack.appendChild(barFill);
  riskBox.appendChild(barTrack);
  tdRisk.appendChild(riskBox);
  tr.appendChild(tdRisk);

  const tdEv = document.createElement("td");
  tdEv.style.cssText = "padding: 8px 12px;";
  if (evCodes.length > 0) {
    for (const code of evCodes) {
      const chip = document.createElement("span");
      chip.className = "evidence-chip";
      chip.title = code;
      chip.textContent = FEATURE_NAMES[code] || code;
      tdEv.appendChild(chip);
    }
  } else {
    const dash = document.createElement("span");
    dash.style.cssText = "color: var(--muted); font-size: 12px;";
    dash.textContent = "—";
    tdEv.appendChild(dash);
  }
  tr.appendChild(tdEv);

  const tdRange = document.createElement("td");
  tdRange.style.cssText = "padding: 6px 12px; text-align: center;";
  tdRange.appendChild(renderIntervalBar(row.strongest_est, row.strongest_ci_low, row.strongest_ci_high, 110, 18, 0));
  tr.appendChild(tdRange);

  const tdRules = document.createElement("td");
  tdRules.style.cssText = "padding: 8px 12px; text-align: right; color: var(--muted);";
  tdRules.className = "tabular-nums";
  tdRules.textContent = String(row.rule_hits);
  tr.appendChild(tdRules);

  const tdAlloc = document.createElement("td");
  tdAlloc.style.cssText = "padding: 8px 12px; text-align: right; font-weight: 600; color: var(--ink);";
  tdAlloc.className = "tabular-nums";
  tdAlloc.textContent = String(row.allocated_backchecks);
  tr.appendChild(tdAlloc);

  if (isRevealed) {
    const tdTruth = document.createElement("td");
    tdTruth.style.cssText = "padding: 8px 12px;";
    tdTruth.appendChild(renderTruthCell(row.truth_label));
    tr.appendChild(tdTruth);
  }

  return tr;
}

function renderTruthCell(label) {
  const span = document.createElement("span");
  span.style.cssText = "padding-left: 6px; color: var(--ink); font-size: 12px;";
  if (label === "TP") {
    span.style.borderLeft = "3px solid var(--fab, #c2410c)";
    span.textContent = "Fabricator — in top 4";
  } else if (label === "FN") {
    span.style.borderLeft = "3px solid var(--fab, #c2410c)";
    span.textContent = "Fabricator — missed";
  } else if (label === "FP") {
    span.style.borderLeft = "3px solid var(--honest, #2563eb)";
    span.textContent = "Honest — flagged";
  } else {
    span.style.borderLeft = "3px solid var(--honest, #2563eb)";
    span.textContent = "Honest";
  }
  return span;
}
