import { renderIntervalBar } from "./intervalBar.js";
import { FEATURE_NAMES } from "./demoHelpers.js";

let preservedOpenEnumeratorId = "enum_27";

/**
 * Render the full-width accessible risk table with inline evidence drawer.
 */
export function renderRiskTable({
  rows = [],
  selectedId,
  onSelect = () => {},
  isRevealed = false,
  evidenceDict = {},
  submissions = [],
  villages = [],
  drawerRenderer = null,
}) {
  const colSpan = isRevealed ? 9 : 8;
  const drawerOptions = { colSpan, evidenceDict, submissions, villages, drawerRenderer, onSelect };

  const container = document.createElement("div");

  const legend = document.createElement("div");
  legend.style.cssText = "font-size: 13px; color: var(--muted); margin-bottom: 8px;";
  legend.textContent = "Observed vs honest range: grey band = honest 90% range, vertical tick = expected rate / 0, dot = observed (filled = outside range, hollow = within range).";
  container.appendChild(legend);

  const wrapper = document.createElement("div");
  wrapper.className = "table-wrapper";
  wrapper.style.cssText = "background: var(--surface); border: 1px solid var(--line); border-radius: 8px;";

  const table = document.createElement("table");
  table.style.cssText = "width: 100%; border-collapse: collapse; font-size: 13px; text-align: left;";

  const thead = document.createElement("thead");
  thead.innerHTML = `
    <tr style="background: var(--surface); border-bottom: 1px solid var(--line); color: var(--ink); font-weight: 600;">
      <th style="padding: 10px 8px; width: 48px; min-width: 48px; max-width: 48px; box-sizing: border-box; white-space: nowrap;">Rank</th>
      <th style="padding: 10px 8px; width: 96px; min-width: 96px; max-width: 96px; box-sizing: border-box; white-space: nowrap;">Enumerator</th>
      <th style="padding: 10px 8px; width: 88px; min-width: 88px; max-width: 88px; box-sizing: border-box; text-align: right; white-space: nowrap;">Interviews</th>
      <th style="padding: 10px 8px; width: 64px; min-width: 64px; max-width: 64px; box-sizing: border-box; text-align: right; white-space: nowrap;">Risk</th>
      <th style="padding: 10px 8px; width: auto; white-space: nowrap;">Evidence</th>
      <th style="padding: 10px 8px; width: 140px; min-width: 140px; max-width: 140px; box-sizing: border-box; text-align: center; white-space: nowrap;">vs honest range</th>
      <th style="padding: 10px 8px; width: 72px; min-width: 72px; max-width: 72px; box-sizing: border-box; text-align: right; white-space: nowrap;">Rule hits</th>
      <th style="padding: 10px 8px; width: 88px; min-width: 88px; max-width: 88px; box-sizing: border-box; text-align: right; white-space: nowrap;">Back-checks</th>
      ${isRevealed ? '<th style="padding: 10px 8px; width: 168px; min-width: 168px; max-width: 168px; box-sizing: border-box; white-space: nowrap;">Truth</th>' : ""}
    </tr>
  `;
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const row of rows) {
    const tr = renderRowNode(row, isRevealed, () => activateRow(container, row.enumerator_id, drawerOptions));
    tbody.appendChild(tr);

    if (row.rank === 4) {
      const dividerTr = document.createElement("tr");
      dividerTr.className = "rank-divider-row";
      dividerTr.style.cssText = "background: var(--page); border-top: 1px solid var(--line); border-bottom: 1px solid var(--line);";
      const td = document.createElement("td");
      td.colSpan = colSpan;
      td.style.cssText = "padding: 6px 12px; font-size: 12px; font-weight: 600; color: var(--muted); text-align: center;";
      td.textContent = "Top 4 — evaluation cut-off (k = 4)";
      dividerTr.appendChild(td);
      tbody.appendChild(dividerTr);
    }
  }

  table.appendChild(tbody);
  wrapper.appendChild(table);
  container.appendChild(wrapper);

  // Restore open enumerator drawer if present in current rows
  const targetId = selectedId !== undefined ? selectedId : preservedOpenEnumeratorId;
  if (targetId && rows.some((r) => r.enumerator_id === targetId)) {
    activateRow(container, targetId, drawerOptions, true);
  } else if (targetId) {
    preservedOpenEnumeratorId = null;
  }

  return container;
}

/**
 * Activate or toggle an inline evidence drawer row.
 */
export function activateRow(container, enumeratorId, drawerOptions = {}, forceOpen = false) {
  const row = container.querySelector(`tr[data-enum-id="${enumeratorId}"]`);
  if (!row) return null;

  const isCurrentlyOpen = row.getAttribute("aria-expanded") === "true";
  const shouldOpen = forceOpen || !isCurrentlyOpen;

  // Close any currently open drawer rows in this container
  const existingDrawers = container.querySelectorAll("tr.evidence-drawer-row");
  for (const d of existingDrawers) d.remove();

  const allRows = container.querySelectorAll("tr[data-enum-id]");
  for (const r of allRows) {
    r.setAttribute("aria-expanded", "false");
    r.style.background = "var(--surface)";
  }

  if (shouldOpen) {
    row.setAttribute("aria-expanded", "true");
    row.style.background = "var(--accent-soft)";
    preservedOpenEnumeratorId = enumeratorId;

    const drawerTr = document.createElement("tr");
    drawerTr.className = "evidence-drawer-row";
    drawerTr.setAttribute("data-drawer-for", enumeratorId);
    drawerTr.style.cssText = "background: var(--page); border-bottom: 1px solid var(--line);";

    const td = document.createElement("td");
    td.colSpan = drawerOptions.colSpan || 8;
    td.style.cssText = "padding: 16px 20px;";

    if (drawerOptions.drawerRenderer) {
      td.appendChild(drawerOptions.drawerRenderer({
        enumeratorId,
        enumEvidence: drawerOptions.evidenceDict ? drawerOptions.evidenceDict[enumeratorId] : null,
        allSubmissions: drawerOptions.submissions || [],
        villages: drawerOptions.villages || [],
        onClose: () => activateRow(container, enumeratorId, drawerOptions, false),
      }));
    } else {
      const fb = document.createElement("div");
      fb.textContent = `Evidence for ${enumeratorId}`;
      td.appendChild(fb);
    }

    drawerTr.appendChild(td);
    row.after(drawerTr);

    if (drawerOptions.onSelect && !forceOpen) drawerOptions.onSelect(enumeratorId);
    return drawerTr;
  } else {
    preservedOpenEnumeratorId = null;
    if (drawerOptions.onSelect) drawerOptions.onSelect(null);
    return null;
  }
}

export function renderRowNode(row, isRevealed, onActivate) {
  const tr = document.createElement("tr");
  tr.setAttribute("data-enum-id", row.enumerator_id);
  tr.setAttribute("role", "button");
  tr.setAttribute("aria-expanded", "false");
  tr.setAttribute("aria-label", `Toggle evidence for ${row.enumerator_id}`);
  tr.tabIndex = 0;
  tr.style.cssText = "background: var(--surface); border-bottom: 1px solid var(--line); cursor: pointer; transition: background 0.1s;";

  tr.onclick = () => onActivate();
  tr.onkeydown = (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onActivate();
    }
  };

  const tdRank = document.createElement("td");
  tdRank.style.cssText = "padding: 8px 8px; width: 48px; color: var(--muted);";
  tdRank.className = "tabular-nums";
  tdRank.textContent = String(row.rank);
  tr.appendChild(tdRank);

  const tdEnum = document.createElement("td");
  tdEnum.style.cssText = "padding: 8px 8px; width: 96px;";
  tdEnum.className = "enum-id";
  tdEnum.textContent = row.enumerator_id;
  tr.appendChild(tdEnum);

  const tdN = document.createElement("td");
  tdN.style.cssText = "padding: 8px 8px; width: 88px; text-align: right; color: var(--muted);";
  tdN.className = "tabular-nums";
  tdN.textContent = String(row.n);
  tr.appendChild(tdN);

  // Risk: number only (1 decimal), no bar
  const tdRisk = document.createElement("td");
  tdRisk.style.cssText = "padding: 8px 8px; width: 64px; text-align: right;";
  tdRisk.className = "tabular-nums";
  tdRisk.textContent = row.risk_score.toFixed(1);
  tr.appendChild(tdRisk);

  // Evidence: inline chips, max 2 then +N
  const tdEv = document.createElement("td");
  tdEv.style.cssText = "padding: 8px 8px; width: auto;";
  tdEv.appendChild(renderEvidenceChips(row.evidence));
  tr.appendChild(tdEv);

  const tdRange = document.createElement("td");
  tdRange.style.cssText = "padding: 6px 8px; width: 140px; text-align: center;";
  tdRange.appendChild(renderIntervalBar(row.strongest_est, row.strongest_ci_low, row.strongest_ci_high, 110, 20, 0));
  tr.appendChild(tdRange);

  const tdRules = document.createElement("td");
  tdRules.style.cssText = "padding: 8px 8px; width: 72px; text-align: right; color: var(--muted);";
  tdRules.className = "tabular-nums";
  tdRules.textContent = String(row.rule_hits);
  tr.appendChild(tdRules);

  const tdAlloc = document.createElement("td");
  tdAlloc.style.cssText = "padding: 8px 8px; width: 88px; text-align: right; font-weight: 600; color: var(--ink);";
  tdAlloc.className = "tabular-nums";
  tdAlloc.textContent = String(row.allocated_backchecks);
  tr.appendChild(tdAlloc);

  if (isRevealed) {
    const tdTruth = document.createElement("td");
    tdTruth.style.cssText = "padding: 8px 8px; width: 168px;";
    tdTruth.appendChild(renderTruthCell(row.truth_label));
    tr.appendChild(tdTruth);
  }

  return tr;
}

function renderEvidenceChips(evidenceStr) {
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
  const maxVisible = 2;
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
