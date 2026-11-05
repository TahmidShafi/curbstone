import { renderIntervalBar } from "./intervalBar.js";
import { renderEvidenceChips, renderTruthCell } from "./demoHelpers.js";
import { renderMobileCard, renderMobileCardDivider, renderMobileDrawer } from "./mobileRiskCard.js";

let currentScenario = null;
let preservedOpenEnumeratorId = null;

/**
 * Render the full-width accessible risk table (desktop) and card list (mobile)
 * with inline evidence drawer.
 */
export function renderRiskTable({
  scenario,
  rows = [],
  selectedId,
  onSelect = () => {},
  isRevealed = false,
  evidenceDict = {},
  submissions = [],
  villages = [],
  drawerRenderer = null,
}) {
  // Drawer starts closed on page load and on scenario change
  if (scenario !== undefined && scenario !== currentScenario) {
    currentScenario = scenario;
    preservedOpenEnumeratorId = null;
  }

  const colSpan = isRevealed ? 9 : 8;
  const drawerOptions = { colSpan, evidenceDict, submissions, villages, drawerRenderer, onSelect };

  const container = document.createElement("div");

  const legend = document.createElement("div");
  legend.className = "risk-table-legend";
  legend.style.cssText = "font-size: 13px; color: var(--muted); margin-bottom: 8px;";
  legend.textContent = "Observed vs honest range: grey band = honest 90% range, vertical tick = expected rate / 0, dot = observed (filled = outside range, hollow = within range).";
  container.appendChild(legend);

  // 1. Desktop table wrapper
  const wrapper = document.createElement("div");
  wrapper.className = "table-wrapper";
  wrapper.style.cssText = "background: var(--surface); border: 1px solid var(--line); border-radius: 8px; width: 100%; box-sizing: border-box;";

  const table = document.createElement("table");
  table.className = "risk-table";
  table.style.cssText = "width: 100%; border-collapse: collapse; font-size: 13px; text-align: left;";

  const thead = document.createElement("thead");
  thead.innerHTML = `
    <tr style="background: var(--surface); border-bottom: 1px solid var(--line); color: var(--ink); font-weight: 600;">
      <th style="padding: 10px 6px; width: 44px; min-width: 44px; max-width: 44px; box-sizing: border-box; white-space: nowrap;">Rank</th>
      <th style="padding: 10px 6px; width: 92px; min-width: 92px; max-width: 92px; box-sizing: border-box; white-space: nowrap;">Enumerator</th>
      <th style="padding: 10px 6px; width: 52px; min-width: 52px; max-width: 52px; box-sizing: border-box; text-align: right; white-space: nowrap;">n</th>
      <th style="padding: 10px 6px; width: 56px; min-width: 56px; max-width: 56px; box-sizing: border-box; text-align: right; white-space: nowrap;">Risk</th>
      <th style="padding: 10px 6px; width: auto; white-space: nowrap;">Evidence</th>
      <th style="padding: 10px 6px; width: 130px; min-width: 130px; max-width: 130px; box-sizing: border-box; text-align: center; white-space: nowrap;">vs honest range</th>
      <th style="padding: 10px 6px; width: 56px; min-width: 56px; max-width: 56px; box-sizing: border-box; text-align: right; white-space: nowrap;">Rules</th>
      <th style="padding: 10px 6px; width: 64px; min-width: 64px; max-width: 64px; box-sizing: border-box; text-align: right; white-space: nowrap;">Checks</th>
      ${isRevealed ? '<th style="padding: 10px 6px; width: 136px; min-width: 136px; max-width: 136px; box-sizing: border-box; white-space: nowrap;">Truth</th>' : ""}
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

  // 2. Mobile cards list
  const mobileList = document.createElement("div");
  mobileList.className = "risk-cards-mobile";
  for (const row of rows) {
    const card = renderMobileCard(row, isRevealed, () => activateRow(container, row.enumerator_id, drawerOptions));
    mobileList.appendChild(card);

    if (row.rank === 4) {
      mobileList.appendChild(renderMobileCardDivider());
    }
  }
  container.appendChild(mobileList);

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
 * Activate or toggle an inline evidence drawer row and/or mobile card drawer.
 */
export function activateRow(container, enumeratorId, drawerOptions = {}, forceOpen = false) {
  const row = container.querySelector(`tr[data-enum-id="${enumeratorId}"]`);
  const card = container.querySelector(`.risk-card[data-enum-id="${enumeratorId}"]`);
  if (!row && !card) return null;

  const isRowOpen = row && row.getAttribute("aria-expanded") === "true";
  const isCardOpen = card && card.getAttribute("aria-expanded") === "true";
  const shouldOpen = forceOpen || (!isRowOpen && !isCardOpen);

  // Close any existing open drawers
  container.querySelectorAll("tr.evidence-drawer-row").forEach((d) => d.remove());
  container.querySelectorAll(".risk-card-drawer").forEach((d) => d.remove());

  container.querySelectorAll("tr[data-enum-id]").forEach((r) => {
    r.setAttribute("aria-expanded", "false");
    r.style.background = "var(--surface)";
  });
  container.querySelectorAll(".risk-card[data-enum-id]").forEach((c) => {
    c.setAttribute("aria-expanded", "false");
    c.style.background = "var(--surface)";
  });

  if (shouldOpen) {
    preservedOpenEnumeratorId = enumeratorId;
    let drawerTr = null;

    if (row) {
      row.setAttribute("aria-expanded", "true");
      row.style.background = "var(--accent-soft)";
      drawerTr = createDrawerTr(enumeratorId, drawerOptions, container);
      row.after(drawerTr);
    }

    if (card) {
      card.setAttribute("aria-expanded", "true");
      card.style.background = "var(--accent-soft)";
      const drawerDiv = renderMobileDrawer(enumeratorId, drawerOptions, () => activateRow(container, enumeratorId, drawerOptions, false));
      card.after(drawerDiv);
    }

    if (drawerOptions.onSelect && !forceOpen) drawerOptions.onSelect(enumeratorId);
    return drawerTr;
  } else {
    preservedOpenEnumeratorId = null;
    if (drawerOptions.onSelect) drawerOptions.onSelect(null);
    return null;
  }
}

function createDrawerTr(enumeratorId, drawerOptions, container) {
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
  return drawerTr;
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

  // Rank: 44px
  const tdRank = document.createElement("td");
  tdRank.style.cssText = "padding: 8px 6px; width: 44px; min-width: 44px; max-width: 44px; box-sizing: border-box; color: var(--muted);";
  tdRank.className = "tabular-nums";
  tdRank.textContent = String(row.rank);
  tr.appendChild(tdRank);

  // Enumerator: 92px
  const tdEnum = document.createElement("td");
  tdEnum.style.cssText = "padding: 8px 6px; width: 92px; min-width: 92px; max-width: 92px; box-sizing: border-box;";
  tdEnum.className = "enum-id";
  tdEnum.textContent = row.enumerator_id;
  tr.appendChild(tdEnum);

  // n (Interviews): 52px
  const tdN = document.createElement("td");
  tdN.style.cssText = "padding: 8px 6px; width: 52px; min-width: 52px; max-width: 52px; box-sizing: border-box; text-align: right; color: var(--muted);";
  tdN.className = "tabular-nums";
  tdN.textContent = String(row.n);
  tr.appendChild(tdN);

  // Risk: 56px (number only, 1 decimal)
  const tdRisk = document.createElement("td");
  tdRisk.style.cssText = "padding: 8px 6px; width: 56px; min-width: 56px; max-width: 56px; box-sizing: border-box; text-align: right;";
  tdRisk.className = "tabular-nums";
  tdRisk.textContent = row.risk_score.toFixed(1);
  tr.appendChild(tdRisk);

  // Evidence: auto (max 1 chip + "+N")
  const tdEv = document.createElement("td");
  tdEv.style.cssText = "padding: 8px 6px; width: auto;";
  tdEv.appendChild(renderEvidenceChips(row.evidence));
  tr.appendChild(tdEv);

  // vs honest range: 130px
  const tdRange = document.createElement("td");
  tdRange.style.cssText = "padding: 6px 6px; width: 130px; min-width: 130px; max-width: 130px; box-sizing: border-box; text-align: center;";
  tdRange.appendChild(renderIntervalBar(row.strongest_est, row.strongest_ci_low, row.strongest_ci_high, 110, 20, 0));
  tr.appendChild(tdRange);

  // Rules: 56px
  const tdRules = document.createElement("td");
  tdRules.style.cssText = "padding: 8px 6px; width: 56px; min-width: 56px; max-width: 56px; box-sizing: border-box; text-align: right; color: var(--muted);";
  tdRules.className = "tabular-nums";
  tdRules.textContent = String(row.rule_hits);
  tr.appendChild(tdRules);

  // Checks (Back-checks): 64px
  const tdAlloc = document.createElement("td");
  tdAlloc.style.cssText = "padding: 8px 6px; width: 64px; min-width: 64px; max-width: 64px; box-sizing: border-box; text-align: right; font-weight: 600; color: var(--ink);";
  tdAlloc.className = "tabular-nums";
  tdAlloc.textContent = String(row.allocated_backchecks);
  tr.appendChild(tdAlloc);

  // Truth: 136px
  if (isRevealed) {
    const tdTruth = document.createElement("td");
    tdTruth.style.cssText = "padding: 8px 6px; width: 136px; min-width: 136px; max-width: 136px; box-sizing: border-box;";
    tdTruth.appendChild(renderTruthCell(row.truth_label));
    tr.appendChild(tdTruth);
  }

  return tr;
}
