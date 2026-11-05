import { renderIntervalBar } from "./intervalBar.js";
import { renderEvidenceChips, renderTruthCell } from "./demoHelpers.js";

/**
 * Render a single mobile card for an enumerator in the risk list.
 */
export function renderMobileCard(row, isRevealed, onActivate) {
  const card = document.createElement("div");
  card.className = "risk-card";
  card.setAttribute("data-enum-id", row.enumerator_id);
  card.setAttribute("role", "button");
  card.setAttribute("aria-expanded", "false");
  card.setAttribute("aria-label", `Toggle evidence for ${row.enumerator_id}`);
  card.tabIndex = 0;
  card.style.cssText = "background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px; cursor: pointer; transition: background 0.1s; box-sizing: border-box; width: 100%;";

  card.onclick = () => onActivate();
  card.onkeydown = (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onActivate();
    }
  };

  // Line 1: "#rank enum_id" + risk
  const line1 = document.createElement("div");
  line1.style.cssText = "display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px;";

  const left1 = document.createElement("div");
  const rankSpan = document.createElement("span");
  rankSpan.className = "tabular-nums";
  rankSpan.style.cssText = "color: var(--muted); margin-right: 6px; font-weight: 500; font-size: 13px;";
  rankSpan.textContent = `#${row.rank}`;
  left1.appendChild(rankSpan);

  const idSpan = document.createElement("span");
  idSpan.className = "enum-id";
  idSpan.style.cssText = "font-weight: 600; font-size: 14px; color: var(--ink);";
  idSpan.textContent = row.enumerator_id;
  left1.appendChild(idSpan);
  line1.appendChild(left1);

  const right1 = document.createElement("div");
  right1.className = "tabular-nums";
  right1.style.cssText = "font-size: 14px; font-weight: 600; color: var(--ink);";
  right1.innerHTML = `${row.risk_score.toFixed(1)} <span style="font-size: 11px; font-weight: 400; color: var(--muted);">risk</span>`;
  line1.appendChild(right1);
  card.appendChild(line1);

  // Line 2: evidence chips
  const line2 = document.createElement("div");
  line2.style.cssText = "margin-bottom: 8px;";
  line2.appendChild(renderEvidenceChips(row.evidence));
  card.appendChild(line2);

  // Line 3: honest-range mini chart (full width)
  const line3 = document.createElement("div");
  line3.style.cssText = "margin-bottom: 8px; width: 100%; box-sizing: border-box;";
  line3.appendChild(renderIntervalBar(row.strongest_est, row.strongest_ci_low, row.strongest_ci_high, 280, 20, 0, true));
  card.appendChild(line3);

  // Line 4: "n · rules · checks" muted
  const line4 = document.createElement("div");
  line4.className = "tabular-nums";
  line4.style.cssText = "font-size: 12px; color: var(--muted); margin-top: 4px;";
  line4.textContent = `${row.n} n · ${row.rule_hits} rules · ${row.allocated_backchecks} checks`;
  card.appendChild(line4);

  // After reveal: truth label line
  if (isRevealed) {
    const lineTruth = document.createElement("div");
    lineTruth.style.cssText = "margin-top: 8px; font-size: 12px;";
    lineTruth.appendChild(renderTruthCell(row.truth_label));
    card.appendChild(lineTruth);
  }

  return card;
}

/**
 * Top-4 divider between card 4 and 5 on mobile
 */
export function renderMobileCardDivider() {
  const div = document.createElement("div");
  div.className = "rank-divider-card";
  div.style.cssText = "background: var(--page); border: 1px solid var(--line); border-radius: 6px; padding: 6px 12px; font-size: 12px; font-weight: 600; color: var(--muted); text-align: center; box-sizing: border-box; width: 100%;";
  div.textContent = "Top 4 — evaluation cut-off (k = 4)";
  return div;
}

/**
 * Mobile inline drawer wrapper
 */
export function renderMobileDrawer(enumeratorId, drawerOptions, onClose) {
  const wrap = document.createElement("div");
  wrap.className = "risk-card-drawer";
  wrap.setAttribute("data-drawer-for", enumeratorId);
  wrap.style.cssText = "width: 100%; box-sizing: border-box; margin: 4px 0 10px 0;";

  if (drawerOptions.drawerRenderer) {
    wrap.appendChild(drawerOptions.drawerRenderer({
      enumeratorId,
      enumEvidence: drawerOptions.evidenceDict ? drawerOptions.evidenceDict[enumeratorId] : null,
      allSubmissions: drawerOptions.submissions || [],
      villages: drawerOptions.villages || [],
      onClose: onClose,
    }));
  } else {
    const fb = document.createElement("div");
    fb.style.cssText = "padding: 12px; background: var(--page); border-radius: 6px;";
    fb.textContent = `Evidence for ${enumeratorId}`;
    wrap.appendChild(fb);
  }

  return wrap;
}
