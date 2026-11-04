"""Enumerator-level peer-relative feature extraction (dgp-aligned)."""

import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
import yaml

from engine.feature_helpers import count_near_dups, median_nn_distance

ASSET_COLS = ["asset_mobile", "asset_tv", "asset_internet", "asset_radio", "asset_computer"]


def compute_f1_duration_resid(df: pd.DataFrame, enum_ids: List[str]) -> Dict[str, Tuple[float, float, int]]:
    slope, intercept = np.polyfit(df["hh_size"], np.log(df["duration_min"].clip(lower=1.0)), 1)
    resids = np.log(df["duration_min"].clip(lower=1.0)) - (intercept + slope * df["hh_size"])
    df_temp = df[["enumerator_id", "village_id"]].copy()
    df_temp["resid"] = resids

    res: Dict[str, Tuple[float, float, int]] = {}
    for e_id in enum_ids:
        e_rows = df_temp[df_temp["enumerator_id"] == e_id]
        val = float(e_rows["resid"].median()) if len(e_rows) > 0 else 0.0
        weights, peer_meds = [], []
        for vid, ev_rows in e_rows.groupby("village_id"):
            n_ev = len(ev_rows)
            p_rows = df_temp[(df_temp["village_id"] == vid) & (df_temp["enumerator_id"] != e_id)]
            if len(p_rows) > 0:
                weights.append(n_ev)
                peer_meds.append(float(p_rows["resid"].median()))
        peer_val = float(np.average(peer_meds, weights=weights)) if weights else 0.0
        res[e_id] = (round(val, 4), round(peer_val, 4), len(e_rows))
    return res


def compute_f2_throughput(df: pd.DataFrame, enum_ids: List[str]) -> Dict[str, Tuple[float, float, int]]:
    dates = df["start_time"].astype(str).str[:10]
    df_temp = df[["enumerator_id"]].copy()
    df_temp["date"] = dates

    t_dict: Dict[str, float] = {}
    counts: Dict[str, int] = {}
    for e_id, grp in df_temp.groupby("enumerator_id"):
        t_dict[str(e_id)] = len(grp) / max(1, grp["date"].nunique())
        counts[str(e_id)] = len(grp)

    res: Dict[str, Tuple[float, float, int]] = {}
    for e_id in enum_ids:
        val = t_dict.get(e_id, 0.0)
        others = [t_dict[o] for o in t_dict if o != e_id]
        peer_val = float(np.median(others)) if others else val
        res[e_id] = (round(val, 4), round(peer_val, 4), counts.get(e_id, 0))
    return res


def compute_f3_near_dup(df: pd.DataFrame, enum_ids: List[str], rng: np.random.Generator, B: int = 50) -> Dict[str, Tuple[int, float, int, bool]]:
    recs = [
        (row["hh_size"], row["head_age"], tuple(row["roster_ages"].tolist() if hasattr(row["roster_ages"], "tolist") else row["roster_ages"]), *[row[a] for a in ASSET_COLS])
        for _, row in df.iterrows()
    ]
    df_temp = df[["enumerator_id", "village_id"]].copy()
    df_temp["rec"] = recs

    res: Dict[str, Tuple[int, float, int, bool]] = {}
    for e_id in enum_ids:
        e_rows = df_temp[df_temp["enumerator_id"] == e_id]
        k_sum = 0
        k_exp_sum = 0.0
        null_limited = False
        for vid, ev_rows in e_rows.groupby("village_id"):
            n_ev = len(ev_rows)
            k_sum += count_near_dups(ev_rows["rec"].tolist())
            p_rows = df_temp[(df_temp["village_id"] == vid) & (df_temp["enumerator_id"] != e_id)]
            n_peer = len(p_rows)
            p_recs = p_rows["rec"].tolist()
            if n_peer < n_ev:
                null_limited = True
                k_exp_sum += count_near_dups(p_recs)
            else:
                sims = [count_near_dups([p_recs[i] for i in rng.choice(n_peer, size=n_ev, replace=False)]) for _ in range(B)]
                k_exp_sum += float(np.mean(sims))
        res[e_id] = (k_sum, round(k_exp_sum, 4), len(e_rows), null_limited)
    return res


def compute_f4_straight_line(df: pd.DataFrame, enum_ids: List[str]) -> Dict[str, Tuple[int, float, int]]:
    valid_mask = ~(df[ASSET_COLS] == -8).any(axis=1)
    df_v = df[valid_mask].copy()
    df_v["straight"] = (df_v[ASSET_COLS].nunique(axis=1) == 1).astype(int)

    res: Dict[str, Tuple[int, float, int]] = {}
    for e_id in enum_ids:
        e_rows = df_v[df_v["enumerator_id"] == e_id]
        k_sum = int(e_rows["straight"].sum()) if len(e_rows) > 0 else 0
        k_exp_sum = 0.0
        for vid, ev_rows in e_rows.groupby("village_id"):
            p_rows = df_v[(df_v["village_id"] == vid) & (df_v["enumerator_id"] != e_id)]
            rate = float(p_rows["straight"].mean()) if len(p_rows) > 0 else 0.0
            k_exp_sum += len(ev_rows) * rate
        res[e_id] = (k_sum, round(k_exp_sum, 4), len(e_rows))
    return res


def compute_f5_asset_dispersion(df: pd.DataFrame, enum_ids: List[str]) -> Dict[str, Tuple[float, float, int]]:
    res: Dict[str, Tuple[float, float, int]] = {}
    for e_id in enum_ids:
        e_rows = df[df["enumerator_id"] == e_id]
        weights, cell_scores = [], []
        for vid, ev_rows in e_rows.groupby("village_id"):
            n_ev = len(ev_rows)
            if n_ev < 3:
                continue
            p_rows = df[(df["village_id"] == vid) & (df["enumerator_id"] != e_id)]
            if len(p_rows) < 3:
                continue
            ratios = []
            for a in ASSET_COLS:
                ev_a = ev_rows[ev_rows[a] != -8][a]
                pv_a = p_rows[p_rows[a] != -8][a]
                ve = float(ev_a.var(ddof=1)) if len(ev_a) > 1 else 0.0
                vp = float(pv_a.var(ddof=1)) if len(pv_a) > 1 else 0.0
                ratios.append(math.log((ve + 0.01) / (vp + 0.01)))
            weights.append(n_ev)
            cell_scores.append(float(np.mean(ratios)))
        val = float(np.average(cell_scores, weights=weights)) if weights else 0.0
        res[e_id] = (round(val, 4), 0.0, len(e_rows))
    return res


def compute_f6_hhsize_dispersion(df: pd.DataFrame, enum_ids: List[str]) -> Dict[str, Tuple[float, float, int]]:
    res: Dict[str, Tuple[float, float, int]] = {}
    for e_id in enum_ids:
        e_rows = df[df["enumerator_id"] == e_id]
        weights, cell_scores = [], []
        for vid, ev_rows in e_rows.groupby("village_id"):
            n_ev = len(ev_rows)
            if n_ev < 3:
                continue
            p_rows = df[(df["village_id"] == vid) & (df["enumerator_id"] != e_id)]
            if len(p_rows) < 3:
                continue
            ve = float(ev_rows["hh_size"].var(ddof=1)) if len(ev_rows) > 1 else 0.0
            vp = float(p_rows["hh_size"].var(ddof=1)) if len(p_rows) > 1 else 0.0
            weights.append(n_ev)
            cell_scores.append(math.log((ve + 0.01) / (vp + 0.01)))
        val = float(np.average(cell_scores, weights=weights)) if weights else 0.0
        res[e_id] = (round(val, 4), 0.0, len(e_rows))
    return res


def compute_f7_gps_spread(df: pd.DataFrame, enum_ids: List[str], rng: np.random.Generator, B: int = 50) -> Dict[str, Tuple[float, float, int]]:
    res: Dict[str, Tuple[float, float, int]] = {}
    for e_id in enum_ids:
        e_rows = df[df["enumerator_id"] == e_id]
        weights, cell_scores = [], []
        for vid, ev_rows in e_rows.groupby("village_id"):
            n_ev = len(ev_rows)
            if n_ev < 3:
                continue
            p_rows = df[(df["village_id"] == vid) & (df["enumerator_id"] != e_id)]
            n_peer = len(p_rows)
            if n_peer < 3:
                continue
            obs_nn = median_nn_distance(ev_rows["gps_lat"].values, ev_rows["gps_lon"].values)
            p_lats, p_lons = p_rows["gps_lat"].values, p_rows["gps_lon"].values
            if n_peer >= n_ev:
                sims = [median_nn_distance(p_lats[idx], p_lons[idx]) for idx in [rng.choice(n_peer, size=n_ev, replace=False) for _ in range(B)]]
                null_nn = float(np.median(sims))
            else:
                null_nn = median_nn_distance(p_lats, p_lons) * math.sqrt(n_peer / n_ev)
            score = math.log((obs_nn + 1.0) / (null_nn + 1.0))
            weights.append(n_ev)
            cell_scores.append(score)
        val = float(np.average(cell_scores, weights=weights)) if weights else 0.0
        res[e_id] = (round(val, 4), 0.0, len(e_rows))
    return res


def compute_f8_age_heaping(df: pd.DataFrame, enum_ids: List[str]) -> Dict[str, Tuple[int, float, int]]:
    res: Dict[str, Tuple[int, float, int]] = {}
    for e_id in enum_ids:
        e_rows = df[df["enumerator_id"] == e_id]
        k_sum = 0
        n_sum = 0
        k_exp_sum = 0.0
        for vid, ev_rows in e_rows.groupby("village_id"):
            ev_ages = [age for roster in ev_rows["roster_ages"] for age in roster if age >= 20]
            k_sum += sum(1 for a in ev_ages if a % 5 == 0)
            n_sum += len(ev_ages)
            p_rows = df[(df["village_id"] == vid) & (df["enumerator_id"] != e_id)]
            p_ages = [age for roster in p_rows["roster_ages"] for age in roster if age >= 20]
            p_rate = (sum(1 for a in p_ages if a % 5 == 0) / len(p_ages)) if len(p_ages) > 0 else 0.20
            k_exp_sum += len(ev_ages) * p_rate
        res[e_id] = (k_sum, round(k_exp_sum, 4), n_sum)
    return res


def compute_f9_nonresponse(df: pd.DataFrame, enum_ids: List[str]) -> Dict[str, Tuple[int, float, int]]:
    res: Dict[str, Tuple[int, float, int]] = {}
    for e_id in enum_ids:
        e_rows = df[df["enumerator_id"] == e_id]
        k_sum = int((e_rows[ASSET_COLS] == -8).sum().sum())
        n_sum = len(e_rows) * len(ASSET_COLS)
        k_exp_sum = 0.0
        for vid, ev_rows in e_rows.groupby("village_id"):
            ev_items = len(ev_rows) * len(ASSET_COLS)
            p_rows = df[(df["village_id"] == vid) & (df["enumerator_id"] != e_id)]
            p_items = len(p_rows) * len(ASSET_COLS)
            p_nr = int((p_rows[ASSET_COLS] == -8).sum().sum())
            p_rate = (p_nr / p_items) if p_items > 0 else 0.01
            k_exp_sum += ev_items * p_rate
        res[e_id] = (k_sum, round(k_exp_sum, 4), n_sum)
    return res


def compute_f10_dur_size_coupling(df: pd.DataFrame, enum_ids: List[str]) -> Dict[str, Tuple[float, float, int]]:
    corrs: Dict[str, float] = {}
    counts: Dict[str, int] = {}
    for e_id, grp in df.groupby("enumerator_id"):
        counts[str(e_id)] = len(grp)
        if len(grp) >= 5 and grp["hh_size"].nunique() > 1 and grp["duration_min"].nunique() > 1:
            r, _ = spearmanr(grp["hh_size"], grp["duration_min"])
            corrs[str(e_id)] = float(r) if not np.isnan(r) else 0.0
        else:
            corrs[str(e_id)] = float("nan")

    res: Dict[str, Tuple[float, float, int]] = {}
    for e_id in enum_ids:
        val = corrs.get(e_id, float("nan"))
        e_rows = df[df["enumerator_id"] == e_id]
        weights, peer_corrs = [], []
        for vid, ev_rows in e_rows.groupby("village_id"):
            n_ev = len(ev_rows)
            p_rows = df[(df["village_id"] == vid) & (df["enumerator_id"] != e_id)]
            p_ids = [str(x) for x in p_rows["enumerator_id"].unique()]
            valid_p_corrs = [corrs[p] for p in p_ids if not math.isnan(corrs.get(p, float("nan")))]
            if valid_p_corrs:
                weights.append(n_ev)
                peer_corrs.append(float(np.median(valid_p_corrs)))
        peer_val = float(np.average(peer_corrs, weights=weights)) if weights else float("nan")
        val_rounded = round(val, 4) if not math.isnan(val) else float("nan")
        peer_rounded = round(peer_val, 4) if not math.isnan(peer_val) else float("nan")
        res[e_id] = (val_rounded, peer_rounded, counts.get(e_id, 0))
    return res


def build_feature_table(
    submissions: Union[pd.DataFrame, str, Path],
    villages: Optional[Union[pd.DataFrame, str, Path]] = None,
    seed: Optional[int] = None,
    config_path: Optional[Union[str, Path]] = None,
) -> pd.DataFrame:
    """Build peer-relative feature table with one row per enumerator."""
    if isinstance(submissions, (str, Path)):
        df = pd.read_parquet(submissions)
    else:
        df = submissions.copy()

    if seed is None:
        if config_path is None:
            config_path = Path(__file__).resolve().parent.parent / "config" / "params.yaml"
        if Path(config_path).is_file():
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            seed = int(cfg.get("engine", {}).get("seed", 12345))
        else:
            seed = 12345

    rng = np.random.default_rng(seed)
    enum_ids = sorted([str(x) for x in df["enumerator_id"].unique()])
    f1 = compute_f1_duration_resid(df, enum_ids)
    f2 = compute_f2_throughput(df, enum_ids)
    f3 = compute_f3_near_dup(df, enum_ids, rng=rng)
    f4 = compute_f4_straight_line(df, enum_ids)
    f5 = compute_f5_asset_dispersion(df, enum_ids)
    f6 = compute_f6_hhsize_dispersion(df, enum_ids)
    f7 = compute_f7_gps_spread(df, enum_ids, rng=rng)
    f8 = compute_f8_age_heaping(df, enum_ids)
    f9 = compute_f9_nonresponse(df, enum_ids)
    f10 = compute_f10_dur_size_coupling(df, enum_ids)

    rows = []
    for e in enum_ids:
        rows.append({
            "enumerator_id": e, "n_e": f1[e][2],
            "f1_value": f1[e][0], "f1_peer_value": f1[e][1], "f1_n": f1[e][2],
            "f2_value": f2[e][0], "f2_peer_value": f2[e][1], "f2_n": f2[e][2],
            "f3_k": f3[e][0], "f3_k_exp": f3[e][1], "f3_n": f3[e][2], "f3_null_limited": f3[e][3],
            "f4_k": f4[e][0], "f4_k_exp": f4[e][1], "f4_n": f4[e][2],
            "f5_value": f5[e][0], "f5_peer_value": f5[e][1], "f5_n": f5[e][2],
            "f6_value": f6[e][0], "f6_peer_value": f6[e][1], "f6_n": f6[e][2],
            "f7_value": f7[e][0], "f7_peer_value": f7[e][1], "f7_n": f7[e][2],
            "f8_k": f8[e][0], "f8_k_exp": f8[e][1], "f8_n": f8[e][2],
            "f9_k": f9[e][0], "f9_k_exp": f9[e][1], "f9_n": f9[e][2],
            "f10_value": f10[e][0], "f10_peer_value": f10[e][1], "f10_n": f10[e][2],
        })
    return pd.DataFrame(rows)
