import * as Plot from "npm:@observablehq/plot";
import * as htl from "npm:htl";

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
    return htl.html`<div class="card" style="padding: 16px; color: #666; font-style: italic;">
      Select an enumerator row from the risk table above to inspect the audit evidence drawer.
    </div>`;
  }

  const features = enumEvidence.features || {};
  const featureKeys = Object.keys(features);

  return htl.html`<div class="card" style="padding: 20px; border: 1px solid #c7d2fe; background: #fafafa; border-radius: 8px; margin-top: 20px;">
    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e2e8f0; padding-bottom: 12px; margin-bottom: 16px;">
      <div>
        <h3 style="margin: 0; font-size: 1.25rem; color: #1e293b;">
          Audit Evidence: <span style="font-family: monospace; color: #2563eb;">${enumeratorId}</span>
        </h3>
        <p style="margin: 4px 0 0 0; font-size: 0.875rem; color: #64748b;">
          Risk score: <strong>${enumEvidence.risk_score.toFixed(4)}</strong> &bull;
          Interviews: <strong>${enumEvidence.n_interviews}</strong> &bull;
          Flagged features (p &lt; 0.05/m): <strong>${featureKeys.length > 0 ? featureKeys.join(", ") : "None"}</strong>
        </p>
      </div>
      ${onClose ? htl.html`<button class="btn" onclick=${onClose} style="padding: 6px 12px; font-size: 12px; cursor: pointer; border-radius: 4px; border: 1px solid #cbd5e1; background: #fff;">Close Drawer</button>` : ""}
    </div>

    ${featureKeys.length === 0
      ? htl.html`<p style="color: #64748b; font-style: italic;">No features met the Bonferroni significance threshold (p &lt; 0.05 / m) for this enumerator.</p>`
      : featureKeys.map((fKey) => renderFeatureCard(fKey, features[fKey], enumeratorId, allSubmissions, villages))
    }
  </div>`;
}

function renderFeatureCard(fKey, fData, enumeratorId, allSubmissions, villages) {
  const explanation = FEATURE_EXPLANATIONS[fKey] || fData.feature_name;
  const pValStr = fData.p_value != null ? fData.p_value.toExponential(3) : "—";
  const estStr = fData.feature_estimate != null ? fData.feature_estimate.toFixed(3) : "—";
  const shrunkStr = fData.shrunk_estimate != null ? fData.shrunk_estimate.toFixed(3) : "—";
  const ciStr = fData.ci_90 ? `[${fData.ci_90[0].toFixed(3)}, ${fData.ci_90[1].toFixed(3)}]` : "—";

  return htl.html`<div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 16px; margin-bottom: 16px;">
    <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px;">
      <h4 style="margin: 0; font-size: 1rem; color: #0f172a;">
        <span style="display: inline-block; background: #dbeafe; color: #1e40af; font-weight: bold; padding: 2px 8px; border-radius: 4px; font-size: 0.85rem; margin-right: 8px;">${fKey}</span>
        ${fData.feature_name}
      </h4>
      <span style="font-family: monospace; font-size: 0.85rem; color: #b91c1c; font-weight: 600;">p = ${pValStr}</span>
    </div>

    <p style="margin: 0 0 12px 0; font-size: 0.9rem; color: #334155;">${explanation}</p>

    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 8px; background: #f8fafc; padding: 10px; border-radius: 4px; font-size: 0.85rem; margin-bottom: 14px;">
      <div><strong>Raw Estimate:</strong> ${estStr}</div>
      <div><strong>Shrunk Estimate:</strong> ${shrunkStr}</div>
      <div><strong>90% Interval:</strong> ${ciStr}</div>
      <div><strong>Contributing Records:</strong> ${fData.submission_ids ? fData.submission_ids.length : 0}</div>
    </div>

    <!-- Feature-specific visualizations -->
    ${fKey === "F7" ? renderGpsScatter(fData, enumeratorId, allSubmissions, villages) : ""}
    ${fKey === "F1" ? renderDurationStrip(enumeratorId, allSubmissions) : ""}

    <!-- Contributing Submissions Detail -->
    ${renderContributingDetails(fKey, fData)}
  </div>`;
}

function renderGpsScatter(fData, enumeratorId, allSubmissions, villages) {
  const points = fData.points || [];
  if (points.length === 0) return "";

  const activeVids = new Set(points.map((p) => p.village_id));
  const peers = allSubmissions.filter((s) => activeVids.has(s.village_id) && s.enumerator_id !== enumeratorId);
  const vilRefs = (villages || []).filter((v) => activeVids.has(v.village_id));

  const plotData = [
    ...peers.map((p) => ({ lat: p.gps_lat, lon: p.gps_lon, type: "Village Peers", size: 4 })),
    ...points.map((p) => ({ lat: p.lat, lon: p.lon, type: `${enumeratorId} (Flagged)`, size: 7 })),
    ...vilRefs.map((v) => ({ lat: v.ref_lat, lon: v.ref_lon, type: "Village Reference Point", size: 9 })),
  ];

  return htl.html`<div style="margin: 12px 0;">
    <div style="font-size: 0.85rem; font-weight: 600; color: #475569; margin-bottom: 4px;">F7 GPS Spatial Dispersion vs Village Peers:</div>
    ${Plot.plot({
      width: 580,
      height: 280,
      grid: true,
      color: {
        domain: ["Village Peers", `${enumeratorId} (Flagged)`, "Village Reference Point"],
        range: ["#94a3b8", "#ea580c", "#dc2626"],
        legend: true,
      },
      marks: [
        Plot.dot(plotData, {
          x: "lon",
          y: "lat",
          stroke: "type",
          fill: (d) => (d.type === "Village Peers" ? "none" : d.type === "Village Reference Point" ? "#dc2626" : "#ea580c"),
          r: (d) => (d.type === "Village Reference Point" ? 6 : d.type === "Village Peers" ? 3 : 5),
          symbol: (d) => (d.type === "Village Reference Point" ? "diamond" : "circle"),
        }),
      ],
    })}
  </div>`;
}

function renderDurationStrip(enumeratorId, allSubmissions) {
  const enumSubs = allSubmissions.filter((s) => s.enumerator_id === enumeratorId);
  if (enumSubs.length === 0) return "";
  const vids = new Set(enumSubs.map((s) => s.village_id));
  const peerSubs = allSubmissions.filter((s) => vids.has(s.village_id) && s.enumerator_id !== enumeratorId);

  const plotData = [
    ...peerSubs.map((s) => ({ group: "Village Peers", duration: s.duration_min })),
    ...enumSubs.map((s) => ({ group: `${enumeratorId} (Flagged)`, duration: s.duration_min })),
  ];

  return htl.html`<div style="margin: 12px 0;">
    <div style="font-size: 0.85rem; font-weight: 600; color: #475569; margin-bottom: 4px;">F1 Interview Duration vs Village Peers (Minutes):</div>
    ${Plot.plot({
      width: 580,
      height: 180,
      x: { label: "Duration (min)", domain: [0, 80], grid: true },
      y: { label: null },
      color: {
        domain: ["Village Peers", `${enumeratorId} (Flagged)`],
        range: ["#94a3b8", "#ea580c"],
        legend: true,
      },
      marks: [
        Plot.tickX(plotData, {
          x: "duration",
          y: "group",
          stroke: "group",
          strokeWidth: 2,
        }),
      ],
    })}
  </div>`;
}

function renderContributingDetails(fKey, fData) {
  if (fKey === "F3" && fData.pairs && fData.pairs.length > 0) {
    return htl.html`<details style="font-size: 0.825rem; margin-top: 8px;">
      <summary style="cursor: pointer; color: #2563eb; font-weight: 600;">View ${fData.pairs.length} Near-Duplicate Pairs</summary>
      <table style="width: 100%; border-collapse: collapse; margin-top: 6px;">
        <thead><tr style="background: #f1f5f9; text-align: left;"><th style="padding: 4px 8px;">Submission 1</th><th style="padding: 4px 8px;">Submission 2</th><th style="padding: 4px 8px;">Village</th><th style="padding: 4px 8px;">Differing Fields</th></tr></thead>
        <tbody>
          ${fData.pairs.slice(0, 15).map((p) => htl.html`<tr>
            <td style="padding: 4px 8px; font-family: monospace;">${p.submission_id_1}</td>
            <td style="padding: 4px 8px; font-family: monospace;">${p.submission_id_2}</td>
            <td style="padding: 4px 8px;">${p.village_id}</td>
            <td style="padding: 4px 8px; color: #475569;">${p.differing_fields.length === 0 ? "Exact duplicate (0 diffs)" : p.differing_fields.join(", ")}</td>
          </tr>`)}
        </tbody>
      </table>
      ${fData.pairs.length > 15 ? htl.html`<p style="margin: 4px 0 0 0; color: #64748b;">(Showing 15 of ${fData.pairs.length} pairs)</p>` : ""}
    </details>`;
  }

  if (fKey === "F4" && fData.straight_records && fData.straight_records.length > 0) {
    return htl.html`<details style="font-size: 0.825rem; margin-top: 8px;">
      <summary style="cursor: pointer; color: #2563eb; font-weight: 600;">View ${fData.straight_records.length} Straight-Lined Records</summary>
      <div style="font-family: monospace; font-size: 0.8rem; background: #f8fafc; padding: 6px 10px; border-radius: 4px; margin-top: 4px;">
        ${fData.straight_records.map((r) => `${r.submission_id} (value: ${r.straight_value})`).join(", ")}
      </div>
    </details>`;
  }

  if (fData.submission_ids && fData.submission_ids.length > 0) {
    return htl.html`<details style="font-size: 0.825rem; margin-top: 8px;">
      <summary style="cursor: pointer; color: #2563eb; font-weight: 600;">Contributing Submission IDs (${fData.submission_ids.length})</summary>
      <div style="font-family: monospace; font-size: 0.8rem; background: #f8fafc; padding: 6px 10px; border-radius: 4px; margin-top: 4px; word-break: break-all;">
        ${fData.submission_ids.slice(0, 30).join(", ")}${fData.submission_ids.length > 30 ? ` ... (+${fData.submission_ids.length - 30} more)` : ""}
      </div>
    </details>`;
  }

  return "";
}
