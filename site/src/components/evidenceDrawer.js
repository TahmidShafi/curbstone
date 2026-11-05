import * as Plot from "npm:@observablehq/plot";
import * as htl from "npm:htl";
import { renderCardIntervalChart } from "./intervalBar.js";

export const FEATURE_NAMES = {
  F1: "Fast interviews",
  F2: "High daily volume",
  F3: "Near-duplicates",
  F4: "Straight-lining",
  F5: "Low asset dispersion",
  F6: "Low household-size dispersion",
  F7: "GPS clustering",
  F8: "Age heaping",
  F9: "Non-response",
  F10: "Duration–size coupling",
};

const FEATURE_EXPLANATIONS = {
  F1: "Interview durations are significantly shorter than village peers after adjusting for household size.",
  F2: "Enumerator completed an implausibly high volume of interviews on peak working days.",
  F3: "Interviews within the same village are near-duplicates of each other, differing in at most one question.",
  F4: "Asset module responses are straight-lined (all asset items recorded identically, e.g. all 0s or all 1s).",
  F5: "Asset ownership responses exhibit artificially suppressed dispersion compared to village peer distributions.",
  F6: "Household sizes exhibit unnaturally low variance across interviews compared to village peer distributions.",
  F7: "GPS interview locations are tightly clustered near an anchor point with suppressed spatial dispersion.",
  F8: "Roster member ages exhibit severe digit preference/heaping on multiples of 5 (ending in 0 or 5).",
  F9: "Unusual rate of missing responses / item nonresponse across the survey module.",
  F10: "Interview duration is decoupled from household size (lacks expected positive duration-size correlation).",
};

export function renderEvidenceDrawer({
  enumeratorId,
  enumEvidence,
  allSubmissions = [],
  villages = [],
  onClose,
}) {
  if (!enumeratorId || !enumEvidence) {
    const empty = document.createElement("div");
    empty.style.cssText = "padding: 16px; color: var(--muted); font-style: italic;";
    empty.textContent = "Select an enumerator row from the risk table above to inspect the audit evidence.";
    return empty;
  }

  const features = enumEvidence.features || {};
  const featureKeys = Object.keys(features);

  const container = document.createElement("div");
  container.style.cssText = "background: var(--page); border: 1px solid var(--line); border-radius: 8px; padding: 16px; margin: 4px 0;";

  const header = document.createElement("div");
  header.style.cssText = "display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--line); padding-bottom: 12px; margin-bottom: 16px;";

  const headerLeft = document.createElement("div");
  headerLeft.innerHTML = `
    <h3 style="margin: 0; font-size: 18px; color: var(--ink);">
      Audit Evidence: <span class="enum-id" style="color: var(--accent);">${enumeratorId}</span>
    </h3>
    <p style="margin: 4px 0 0 0; font-size: 13px; color: var(--muted);" class="tabular-nums">
      Risk score: <strong>${enumEvidence.risk_score.toFixed(1)}</strong> &bull;
      Interviews: <strong>${enumEvidence.n_interviews}</strong> &bull;
      Flagged features (p &lt; 0.05/m): <strong>${featureKeys.length > 0 ? featureKeys.map((k) => FEATURE_NAMES[k] || k).join(", ") : "None"}</strong>
    </p>
  `;
  header.appendChild(headerLeft);

  if (onClose) {
    const closeBtn = document.createElement("button");
    closeBtn.className = "btn-secondary";
    closeBtn.textContent = "Close";
    closeBtn.onclick = onClose;
    header.appendChild(closeBtn);
  }
  container.appendChild(header);

  if (featureKeys.length === 0) {
    const noFeat = document.createElement("p");
    noFeat.style.cssText = "color: var(--muted); font-style: italic; font-size: 13px; margin: 8px 0;";
    noFeat.textContent = "No features met the Bonferroni significance threshold (p < 0.05 / m) for this enumerator.";
    container.appendChild(noFeat);
  } else {
    const grid = document.createElement("div");
    grid.style.cssText = "display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 16px;";
    for (const fKey of featureKeys) {
      grid.appendChild(renderFeatureCard(fKey, features[fKey], enumeratorId, allSubmissions, villages));
    }
    container.appendChild(grid);
  }

  return container;
}

function formatPValue(p) {
  if (p == null) return "—";
  if (p < 1e-16) return "< 1e-16";
  return p.toExponential(2);
}

function renderFeatureCard(fKey, fData, enumeratorId, allSubmissions, villages) {
  const plainName = FEATURE_NAMES[fKey] || fData.feature_name;
  const explanation = FEATURE_EXPLANATIONS[fKey] || fData.feature_name;
  const isCount = ["F3", "F4", "F8", "F9"].includes(fKey);
  const pValStr = formatPValue(fData.p_value);
  const shrunkStr = fData.shrunk_estimate != null ? fData.shrunk_estimate.toFixed(3) : "—";

  const d = fData.feature_estimate;
  const dStr = d != null ? d.toFixed(3) : "—";
  const h = fData.honest_halfwidth ?? (fData.ci_90 ? (fData.ci_90[1] - fData.ci_90[0]) / 2 : null);
  const contRangeStr = h != null ? `[${(-h).toFixed(3)}, +${h.toFixed(3)}]` : "—";

  const rate = fData.observed_rate ?? (fData.k != null && fData.n ? fData.k / fData.n : fData.feature_estimate);
  const rateStr = rate != null ? rate.toFixed(3) : "—";
  const countsStr = fData.k != null && fData.n != null ? ` (${fData.k}/${fData.n})` : "";
  const countRange = fData.honest_range_90 ?? fData.ci_90;
  const countRangeStr = countRange ? `[${countRange[0].toFixed(3)}, ${countRange[1].toFixed(3)}]` : "—";

  const estVal = isCount ? rate : d;
  const [ciLo, ciHi] = isCount ? (countRange || [0, 0]) : [-h, h];

  const card = document.createElement("div");
  card.style.cssText = "background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 16px; box-sizing: border-box;";

  const topRow = document.createElement("div");
  topRow.style.cssText = "display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px;";
  topRow.innerHTML = `
    <h4 style="margin: 0; font-size: 15px; color: var(--ink);">
      <span class="evidence-chip" title="${fKey}">${fKey}</span>
      ${plainName}
    </h4>
    <span style="font-size: 13px; color: var(--muted); font-variant-numeric: tabular-nums;">p = ${pValStr}</span>
  `;
  card.appendChild(topRow);

  const desc = document.createElement("p");
  desc.style.cssText = "margin: 0 0 10px 0; font-size: 13px; color: var(--ink); line-height: 18px;";
  desc.textContent = explanation;
  card.appendChild(desc);

  const chartWrap = document.createElement("div");
  chartWrap.style.cssText = "margin: 8px 0 12px 0;";
  chartWrap.appendChild(renderCardIntervalChart(estVal, ciLo, ciHi, 0, 320, 48));
  card.appendChild(chartWrap);

  const stats = document.createElement("div");
  stats.className = "tabular-nums";
  stats.style.cssText = "display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 6px; background: var(--page); padding: 8px 10px; border-radius: 4px; font-size: 12px; margin-bottom: 8px;";
  stats.innerHTML = isCount
    ? `<div><strong>Observed:</strong> ${rateStr}${countsStr}</div><div><strong>Honest 90%:</strong> ${countRangeStr}</div><div><strong>Records:</strong> ${fData.submission_ids ? fData.submission_ids.length : 0}</div>`
    : `<div><strong>Observed:</strong> ${dStr}</div><div><strong>Honest 90%:</strong> ${contRangeStr}</div><div><strong>Records:</strong> ${fData.submission_ids ? fData.submission_ids.length : 0}</div>`;
  card.appendChild(stats);

  const details = document.createElement("details");
  details.style.cssText = "margin-top: 6px; font-size: 12px; color: var(--muted);";
  details.innerHTML = `
    <summary style="cursor: pointer; font-weight: 500;">Model details</summary>
    <div style="margin-top: 4px; color: var(--ink);" class="tabular-nums">
      ${isCount ? `Posterior mean: <strong>${shrunkStr}</strong>` : `Posterior mean (complete pooling when tau^2 = 0): <strong>${shrunkStr}</strong>`}
    </div>
  `;
  card.appendChild(details);

  if (fKey === "F7") {
    const gpsNode = renderGpsScatter(fData, enumeratorId, allSubmissions, villages);
    if (gpsNode) card.appendChild(gpsNode);
  }
  if (fKey === "F1") {
    const durNode = renderDurationStrip(enumeratorId, allSubmissions);
    if (durNode) card.appendChild(durNode);
  }
  const contribNode = renderContributingDetails(fKey, fData);
  if (contribNode) card.appendChild(contribNode);
  return card;
}

function renderGpsScatter(fData, enumeratorId, allSubmissions, villages) {
  const points = fData.points || [];
  if (points.length === 0) return null;
  const activeVids = new Set(points.map((p) => p.village_id));
  const peers = allSubmissions.filter((s) => activeVids.has(s.village_id) && s.enumerator_id !== enumeratorId);
  const vilRefs = (villages || []).filter((v) => activeVids.has(v.village_id));

  return htl.html`<div style="margin: 12px 0;">
    <div style="font-size: 13px; font-weight: 600; color: var(--ink); margin-bottom: 4px;">GPS interview locations:</div>
    ${Plot.plot({
      width: 320,
      height: 240,
      aspectRatio: 1,
      grid: true,
      marks: [
        Plot.dot(peers, { x: "gps_lon", y: "gps_lat", fill: "#9ca3af", r: 2.5, title: (d) => `Peer interview (${d.submission_id})` }),
        Plot.dot(vilRefs, { x: "ref_lon", y: "ref_lat", stroke: "#4b5563", strokeWidth: 2, fill: "none", r: 6, title: (d) => `Village reference point (${d.village_id})` }),
        Plot.dot(points, { x: "lon", y: "lat", fill: "#1f2937", r: 4, title: (d) => `${enumeratorId} interview (${d.submission_id})` }),
      ],
    })}
    <div style="display: flex; gap: 12px; font-size: 11px; color: var(--muted); margin-top: 6px;">
      <span><span style="display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: #9ca3af; margin-right: 3px;"></span>Village peers</span>
      <span><span style="display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: #1f2937; margin-right: 3px;"></span>${enumeratorId} (Flagged)</span>
      <span><span style="display: inline-block; width: 7px; height: 7px; border-radius: 50%; border: 1.5px solid #4b5563; margin-right: 3px; box-sizing: border-box;"></span>Village reference</span>
    </div>
  </div>`;
}

function renderDurationStrip(enumeratorId, allSubmissions) {
  const enumSubs = allSubmissions.filter((s) => s.enumerator_id === enumeratorId);
  if (enumSubs.length === 0) return null;
  const vids = new Set(enumSubs.map((s) => s.village_id));
  const peerSubs = allSubmissions.filter((s) => vids.has(s.village_id) && s.enumerator_id !== enumeratorId);

  const plotData = [
    ...peerSubs.map((s) => ({ group: "Peers", duration: s.duration_min })),
    ...enumSubs.map((s) => ({ group: "Flagged", duration: s.duration_min })),
  ];

  return htl.html`<div style="margin: 12px 0;">
    <div style="font-size: 13px; font-weight: 600; color: var(--ink); margin-bottom: 4px;">Duration vs peers (min):</div>
    ${Plot.plot({
      width: 320,
      height: 120,
      x: { label: null, domain: [0, 80], grid: true },
      y: { label: null },
      color: { domain: ["Peers", "Flagged"], range: ["#9ca3af", "#1f2937"] },
      marks: [Plot.tickX(plotData, { x: "duration", y: "group", stroke: "group", strokeWidth: 2 })],
    })}
  </div>`;
}

function renderContributingDetails(fKey, fData) {
  if (fKey === "F3" && fData.pairs && fData.pairs.length > 0) {
    return htl.html`<details style="font-size: 12px; margin-top: 8px;">
      <summary style="cursor: pointer; color: var(--accent); font-weight: 500;">Near-duplicate pairs (${fData.pairs.length})</summary>
      <table style="width: 100%; border-collapse: collapse; margin-top: 6px; font-size: 11px;">
        <thead><tr style="border-bottom: 1px solid var(--line); color: var(--muted); text-align: left;"><th style="padding: 2px 4px;">Sub 1</th><th style="padding: 2px 4px;">Sub 2</th><th style="padding: 2px 4px;">Village</th><th style="padding: 2px 4px;">Diffs</th></tr></thead>
        <tbody>
          ${fData.pairs.slice(0, 10).map((p) => htl.html`<tr style="border-bottom: 1px solid var(--line);">
            <td style="padding: 2px 4px;" class="enum-id">${p.submission_id_1}</td>
            <td style="padding: 2px 4px;" class="enum-id">${p.submission_id_2}</td>
            <td style="padding: 2px 4px;">${p.village_id}</td>
            <td style="padding: 2px 4px; color: var(--muted);">${p.differing_fields.length === 0 ? "Exact duplicate" : p.differing_fields.join(", ")}</td>
          </tr>`)}
        </tbody>
      </table>
    </details>`;
  }

  if (fKey === "F4" && fData.straight_records && fData.straight_records.length > 0) {
    return htl.html`<details style="font-size: 12px; margin-top: 8px;">
      <summary style="cursor: pointer; color: var(--accent); font-weight: 500;">Straight-lined records (${fData.straight_records.length})</summary>
      <div style="font-size: 11px; background: var(--page); padding: 6px; border-radius: 4px; margin-top: 4px;" class="enum-id">
        ${fData.straight_records.map((r) => `${r.submission_id} (val: ${r.straight_value})`).join(", ")}
      </div>
    </details>`;
  }

  if (fData.submission_ids && fData.submission_ids.length > 0) {
    return htl.html`<details style="font-size: 12px; margin-top: 8px;">
      <summary style="cursor: pointer; color: var(--accent); font-weight: 500;">Contributing submissions (${fData.submission_ids.length})</summary>
      <div style="font-size: 11px; background: var(--page); padding: 6px; border-radius: 4px; margin-top: 4px; word-break: break-all;" class="enum-id">
        ${fData.submission_ids.slice(0, 20).join(", ")}${fData.submission_ids.length > 20 ? ` ... (+${fData.submission_ids.length - 20} more)` : ""}
      </div>
    </details>`;
  }

  return null;
}
