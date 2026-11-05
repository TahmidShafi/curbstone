"""Evidence explanation layer: per-enumerator explanations for flagged features."""

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import numpy as np
import pandas as pd
from scipy.stats import betabinom, binom

from engine.scoring_helpers import estimate_beta_binomial_rho

ASSET_COLS = ["asset_mobile", "asset_tv", "asset_internet", "asset_radio", "asset_computer"]
CANONICAL_FIELDS = ["hh_size", "head_age", "roster_ages"] + ASSET_COLS
FEATURE_NAMES = {
    "F1": "Short interview duration",
    "F2": "High daily interview volume",
    "F3": "Near-duplicate submissions",
    "F4": "Straight-lined asset responses",
    "F5": "Low asset dispersion",
    "F6": "Low household size dispersion",
    "F7": "GPS clustering / low spread",
    "F8": "Age heaping (multiples of 5)",
    "F9": "Item nonresponse anomaly",
    "F10": "Duration-size decoupling",
}


def _extract_f3_pairs(df_e: pd.DataFrame) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Identify near-duplicate pairs within enumerator-village cells differing in <= 1 field."""
    pairs: List[Dict[str, Any]] = []
    contributing_ids: Set[str] = set()

    for vid, v_rows in df_e.groupby("village_id"):
        recs = [
            (
                row["submission_id"],
                (
                    row["hh_size"],
                    row["head_age"],
                    tuple(row["roster_ages"].tolist() if hasattr(row["roster_ages"], "tolist") else row["roster_ages"]),
                    *[row[a] for a in ASSET_COLS],
                ),
            )
            for _, row in v_rows.iterrows()
        ]
        n_recs = len(recs)
        for i in range(n_recs):
            sub_i, r_i = recs[i]
            for j in range(i + 1, n_recs):
                sub_j, r_j = recs[j]
                diffs = [CANONICAL_FIELDS[k] for k in range(len(CANONICAL_FIELDS)) if r_i[k] != r_j[k]]
                if len(diffs) <= 1:
                    pairs.append({
                        "submission_id_1": str(sub_i),
                        "submission_id_2": str(sub_j),
                        "village_id": str(vid),
                        "differing_fields": diffs,
                    })
                    contributing_ids.add(str(sub_i))
                    contributing_ids.add(str(sub_j))

    return pairs, sorted(contributing_ids)


def _extract_f4_straight(df_e: pd.DataFrame) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Identify straight-lined asset submissions (all non-missing asset items equal)."""
    records, contributing_ids = [], []
    for _, row in df_e.iterrows():
        vals = [row[a] for a in ASSET_COLS]
        if all(v != -8 for v in vals) and len(set(vals)) == 1:
            sid = str(row["submission_id"])
            contributing_ids.append(sid)
            records.append({"submission_id": sid, "village_id": str(row["village_id"]), "straight_value": int(vals[0])})
    return records, contributing_ids


def _extract_f7_gps(df_e: pd.DataFrame, df_vil: pd.DataFrame) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    """Extract enumerator GPS coordinates and associated village reference locations."""
    points = [{"submission_id": str(r["submission_id"]), "village_id": str(r["village_id"]), "lat": round(float(r["gps_lat"]), 6), "lon": round(float(r["gps_lon"]), 6)} for _, r in df_e.iterrows()]
    vil_refs = [{"village_id": str(v), "ref_lat": round(float(m["ref_lat"].iloc[0]), 6), "ref_lon": round(float(m["ref_lon"].iloc[0]), 6)} for v in df_e["village_id"].unique() if not (m := df_vil[df_vil["village_id"] == v]).empty]
    return points, vil_refs, [str(r["submission_id"]) for _, r in df_e.iterrows()]


def _extract_f8_heaping(df_e: pd.DataFrame) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Identify submissions containing ages >= 20 ending in 0 or 5."""
    records, contributing_ids = [], []
    for _, row in df_e.iterrows():
        roster = row["roster_ages"].tolist() if hasattr(row["roster_ages"], "tolist") else row["roster_ages"]
        if heaped := [int(a) for a in roster if a >= 20 and a % 5 == 0]:
            sid = str(row["submission_id"])
            contributing_ids.append(sid)
            records.append({"submission_id": sid, "village_id": str(row["village_id"]), "heaped_ages": heaped})
    return records, contributing_ids


def _extract_f1_durations(df_e: pd.DataFrame) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Extract submission durations and household sizes."""
    records = [{"submission_id": str(r["submission_id"]), "duration_min": round(float(r["duration_min"]), 2), "hh_size": int(r["hh_size"])} for _, r in df_e.iterrows()]
    return records, [r["submission_id"] for r in records]


def _extract_f2_throughput(df_e: pd.DataFrame) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Extract daily interview volume and submission counts."""
    by_date: Dict[str, List[str]] = {}
    for _, row in df_e.iterrows():
        by_date.setdefault(str(row["start_time"])[:10], []).append(str(row["submission_id"]))
    return [{"date": d, "count": len(subs), "submission_ids": subs} for d, subs in sorted(by_date.items())], [str(r["submission_id"]) for _, r in df_e.iterrows()]


def build_evidence(
    submissions: Union[pd.DataFrame, str, Path],
    villages: Union[pd.DataFrame, str, Path],
    scores: pd.DataFrame,
    features: Optional[pd.DataFrame] = None,
    no_shrinkage: Optional[bool] = None,
) -> Dict[str, Any]:
    """Assemble per-enumerator evidence for features satisfying p < 0.05 / m_e without mutating scores."""
    df_sub = pd.read_parquet(submissions) if isinstance(submissions, (str, Path)) else submissions
    df_vil = pd.read_parquet(villages) if isinstance(villages, (str, Path)) else villages

    if no_shrinkage is None:
        if features is not None and "f1_value" in features and "f1_peer_value" in features and "f1_est" in scores:
            d1 = features["f1_value"] - features["f1_peer_value"]
            diff = np.abs(scores["f1_est"].values - d1.values)
            no_shrinkage = bool(np.all(diff[~np.isnan(diff)] < 1e-4))
        else:
            no_shrinkage = False

    rho_dict: Dict[str, float] = {}
    if features is not None and not no_shrinkage:
        for f_id in ["f4", "f8", "f9"]:
            k_col, n_col = f"{f_id}_k", f"{f_id}_n"
            exp_col = f"{f_id}_k_exp_v3" if f"{f_id}_k_exp_v3" in features else f"{f_id}_k_exp"
            if k_col in features and n_col in features and exp_col in features:
                k_arr = features[k_col].values.astype(int)
                n_arr = np.maximum(1, features[n_col].values.astype(int))
                k_exp_arr = features[exp_col].values.astype(float)
                p0_arr = np.clip(k_exp_arr / n_arr, 1e-6, 1.0 - 1e-6)
                rho_dict[f_id] = estimate_beta_binomial_rho(k_arr, n_arr, k_exp_arr, p0_arr)

    evidence_dict: Dict[str, Any] = {}

    for idx, sc_row in scores.iterrows():
        e_id = str(sc_row["enumerator_id"])
        m_e = int(sc_row.get("m_e", 10))
        cutoff = (0.05 / m_e) if m_e > 0 else 0.0
        ev_str = str(sc_row.get("evidence", ""))
        flagged_fids = [f.strip().upper() for f in ev_str.split(",") if f.strip()]

        e_rows = df_sub[df_sub["enumerator_id"] == e_id]
        f_row = features[features["enumerator_id"] == e_id].iloc[0] if features is not None and not features[features["enumerator_id"] == e_id].empty else None

        enum_evidence: Dict[str, Any] = {
            "enumerator_id": e_id,
            "risk_score": float(sc_row["risk_score"]),
            "p_e": float(sc_row["p_e"]),
            "m_e": m_e,
            "n_interviews": len(e_rows),
            "evidence_features": flagged_fids,
            "features": {},
        }

        for fid in flagged_fids:
            fid_lower = fid.lower()
            p_val = float(sc_row[f"{fid_lower}_p"]) if f"{fid_lower}_p" in sc_row else None
            shrunk_est = float(sc_row[f"{fid_lower}_est"]) if f"{fid_lower}_est" in sc_row else None
            ci_low = float(sc_row[f"{fid_lower}_ci_low"]) if f"{fid_lower}_ci_low" in sc_row else None
            ci_high = float(sc_row[f"{fid_lower}_ci_high"]) if f"{fid_lower}_ci_high" in sc_row else None

            feat_est = None
            h_halfwidth = None
            h_range = None

            if f_row is not None:
                if fid == "F1" and "f1_value" in f_row and "f1_peer_value" in f_row:
                    feat_est = round(float(f_row["f1_value"] - f_row["f1_peer_value"]), 4)
                elif fid == "F2" and "f2_value" in f_row and "f2_peer_value" in f_row:
                    feat_est = round(float(f_row["f2_value"] - f_row["f2_peer_value"]), 4)
                elif fid in ["F3", "F4", "F8", "F9"] and f"{fid_lower}_k" in f_row and f"{fid_lower}_n" in f_row:
                    k_val = float(f_row[f"{fid_lower}_k"])
                    n_val = max(1, int(f_row[f"{fid_lower}_n"]))
                    feat_est = round(k_val / n_val, 4)
                elif f"{fid_lower}_value" in f_row:
                    v = f_row[f"{fid_lower}_value"]
                    feat_est = round(float(v), 4) if not math.isnan(v) else None

            f_data: Dict[str, Any] = {
                "feature_id": fid,
                "feature_name": FEATURE_NAMES.get(fid, fid),
                "p_value": p_val,
                "feature_estimate": feat_est,
                "shrunk_estimate": shrunk_est,
                "ci_90": [ci_low, ci_high] if ci_low is not None and ci_high is not None else None,
                "submission_ids": [],
            }

            if fid in ["F3", "F4", "F8", "F9"] and f_row is not None:
                k_val = float(f_row[f"{fid_lower}_k"])
                n_val = max(1, int(f_row[f"{fid_lower}_n"]))
                f_data["k"] = int(k_val)
                f_data["n"] = n_val
                f_data["observed_rate"] = round(k_val / n_val, 4)
                if fid == "F3":
                    exp_col = "f3_k_exp_v3" if "f3_k_exp_v3" in f_row else "f3_k_exp"
                    var_col = "f3_var_v3" if "f3_var_v3" in f_row else "f3_var"
                    mu3 = float(f_row[exp_col]) if exp_col in f_row else 0.0
                    v3 = float(f_row[var_col]) if var_col in f_row else mu3
                    p0_3 = min(max(mu3 / n_val, 1e-6), 1.0 - 1e-6)
                    vb_3 = n_val * p0_3 * (1.0 - p0_3)
                    veff_3 = max(v3, vb_3)
                    if no_shrinkage or veff_3 <= vb_3 + 1e-9:
                        k_lo, k_hi = float(binom.ppf(0.05, n_val, p0_3)), float(binom.ppf(0.95, n_val, p0_3))
                    else:
                        rho_i = min(0.999, max(1e-4, (veff_3 - vb_3) / ((n_val - 1) * vb_3)))
                        M_i = (1.0 - rho_i) / rho_i
                        a_i, b_i = max(1e-6, p0_3 * M_i), max(1e-6, (1.0 - p0_3) * M_i)
                        k_lo, k_hi = float(betabinom.ppf(0.05, n_val, a_i, b_i)), float(betabinom.ppf(0.95, n_val, a_i, b_i))
                    h_range = [round(k_lo / n_val, 4), round(k_hi / n_val, 4)]
                else:
                    exp_col = f"{fid_lower}_k_exp_v3" if f"{fid_lower}_k_exp_v3" in f_row else f"{fid_lower}_k_exp"
                    k_exp = float(f_row[exp_col]) if exp_col in f_row else 0.0
                    p0 = min(max(k_exp / n_val, 1e-6), 1.0 - 1e-6)
                    rho = rho_dict.get(fid_lower, 0.0)
                    if no_shrinkage or rho <= 1e-6:
                        k_lo, k_hi = float(binom.ppf(0.05, n_val, p0)), float(binom.ppf(0.95, n_val, p0))
                    else:
                        M = (1.0 - rho) / rho
                        a_p, b_p = max(1e-6, p0 * M), max(1e-6, (1.0 - p0) * M)
                        k_lo, k_hi = float(betabinom.ppf(0.05, n_val, a_p, b_p)), float(betabinom.ppf(0.95, n_val, a_p, b_p))
                    h_range = [round(k_lo / n_val, 4), round(k_hi / n_val, 4)]
            else:
                if ci_low is not None and ci_high is not None:
                    h_halfwidth = round((ci_high - ci_low) / 2.0, 4)
                    h_range = [-h_halfwidth, h_halfwidth]

            f_data["honest_halfwidth"] = h_halfwidth
            f_data["honest_range_90"] = h_range

            if fid == "F1":
                durations, sids = _extract_f1_durations(e_rows)
                f_data["durations"] = durations
                f_data["submission_ids"] = sids
                f_data["mean_duration"] = round(float(e_rows["duration_min"].mean()), 2) if not e_rows.empty else 0.0
            elif fid == "F2":
                daily, sids = _extract_f2_throughput(e_rows)
                f_data["daily_counts"] = daily
                f_data["submission_ids"] = sids
                f_data["max_daily_count"] = max((d["count"] for d in daily), default=0)
            elif fid == "F3":
                pairs, sids = _extract_f3_pairs(e_rows)
                f_data["pairs"] = pairs
                f_data["pair_count"] = len(pairs)
                f_data["submission_ids"] = sids
            elif fid == "F4":
                records, sids = _extract_f4_straight(e_rows)
                f_data["straight_records"] = records
                f_data["straight_count"] = len(records)
                f_data["submission_ids"] = sids
            elif fid == "F5":
                f_data["submission_ids"] = [str(s) for s in e_rows["submission_id"]]
                f_data["asset_variances"] = {a: round(float(e_rows[e_rows[a] != -8][a].var(ddof=1)), 4) if len(e_rows[e_rows[a] != -8]) > 1 else 0.0 for a in ASSET_COLS}
            elif fid == "F6":
                f_data["submission_ids"] = [str(s) for s in e_rows["submission_id"]]
                f_data["hh_size_variance"] = round(float(e_rows["hh_size"].var(ddof=1)), 4) if len(e_rows) > 1 else 0.0
            elif fid == "F7":
                points, vil_refs, sids = _extract_f7_gps(e_rows, df_vil)
                f_data["points"], f_data["village_references"], f_data["submission_ids"] = points, vil_refs, sids
            elif fid == "F8":
                records, sids = _extract_f8_heaping(e_rows)
                f_data["heaped_records"], f_data["heaped_count"], f_data["submission_ids"] = records, len(records), sids
            elif fid == "F9":
                missing_sids = [str(r["submission_id"]) for _, r in e_rows.iterrows() if any(r[a] == -8 for a in ASSET_COLS)]
                f_data["submission_ids"], f_data["missing_count"] = missing_sids, len(missing_sids)
            elif fid == "F10":
                f_data["submission_ids"] = [str(s) for s in e_rows["submission_id"]]
                f_data["records"] = [{"submission_id": str(r["submission_id"]), "duration_min": round(float(r["duration_min"]), 2), "hh_size": int(r["hh_size"])} for _, r in e_rows.iterrows()]

            enum_evidence["features"][fid] = f_data

        evidence_dict[e_id] = enum_evidence

    return evidence_dict


def export_evidence_json(evidence_dict: Dict[str, Any], out_path: Union[str, Path]) -> Path:
    """Serialize evidence dictionary to a formatted JSON file."""
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(evidence_dict, f, indent=2)
    return p

