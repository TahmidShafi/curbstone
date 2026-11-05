"""Mode-specific fraud injection implementations (dgp §5)."""

import math
from typing import Any, Dict, List, Set, Tuple
import numpy as np

from generator.geography import Geography, _meters_to_deg
from generator.households import generate_age_roster


def apply_rushed_pre_scheduling(
    raw_interviews: List[Dict[str, Any]],
    params: Dict[str, Any],
    fabricated_indices: Set[int],
) -> None:
    """R3: Apply duration compression before timestamp scheduling."""
    mult = params.get("duration_multiplier", 0.4)
    for idx in fabricated_indices:
        dur = raw_interviews[idx]["duration_min"] * mult
        raw_interviews[idx]["duration_min"] = max(2.0, dur)


def inject_straight_lining(
    raw_interviews: List[Dict[str, Any]],
    params: Dict[str, Any],
    fabricated_indices: Set[int],
    fraud_rng: np.random.Generator,
) -> None:
    p_straight = params["prob_straight"]
    p_zero = params["all_zero_prob"]
    for idx in fabricated_indices:
        row = raw_interviews[idx]
        if fraud_rng.uniform(0.0, 1.0) < p_straight:
            val = 0 if fraud_rng.uniform(0.0, 1.0) < p_zero else 1
            for k in list(row["assets"].keys()):
                row["assets"][k] = val


def inject_invented_gps(
    raw_interviews: List[Dict[str, Any]],
    params: Dict[str, Any],
    fabricated_indices: Set[int],
    geography: Geography,
    fraud_rng: np.random.Generator,
) -> None:
    n_anchor = params["n_anchor"]
    jitter_sd = params["jitter_sd_m"]
    radius = params["anchor_radius_m"]

    village_anchors: Dict[str, List[Tuple[float, float]]] = {}
    for idx in fabricated_indices:
        vid = raw_interviews[idx]["village_id"]
        if vid not in village_anchors:
            vil = geography.get_village(vid)
            anchors = []
            for _ in range(n_anchor):
                r = fraud_rng.uniform(0.0, radius)
                theta = fraud_rng.uniform(0.0, 2.0 * math.pi)
                dy, dx = r * math.sin(theta), r * math.cos(theta)
                dlat, dlon = _meters_to_deg(dy, dx, vil.centroid_lat)
                anchors.append((vil.centroid_lat + dlat, vil.centroid_lon + dlon))
            village_anchors[vid] = anchors

        chosen_anchor = village_anchors[vid][int(fraud_rng.integers(0, n_anchor))]
        jy, jx = fraud_rng.normal(0.0, jitter_sd, size=2)
        jdlat, jdlon = _meters_to_deg(jy, jx, chosen_anchor[0])
        raw_interviews[idx]["gps_lat"] = round(chosen_anchor[0] + jdlat, 7)
        raw_interviews[idx]["gps_lon"] = round(chosen_anchor[1] + jdlon, 7)


def inject_too_average(
    raw_interviews: List[Dict[str, Any]],
    params: Dict[str, Any],
    fabricated_indices: Set[int],
    village_models: Dict[str, Dict[str, Any]],
    fraud_rng: np.random.Generator,
) -> None:
    noise_rate = params["noise_rate"]
    hh_noise_sd = params["hh_size_noise_sd"]
    for idx in fabricated_indices:
        row = raw_interviews[idx]
        vid = row["village_id"]
        v_model = village_models[vid]

        for k in list(row["assets"].keys()):
            modal_val = v_model["modes"][k]
            if fraud_rng.uniform(0.0, 1.0) < noise_rate:
                modal_val = 1 - modal_val
            row["assets"][k] = modal_val

        v_mean_sz = round(v_model["mean_hh_size"])
        sz_noise = int(round(fraud_rng.normal(0.0, hh_noise_sd)))
        new_sz = max(1, v_mean_sz + sz_noise)
        row["hh_size"] = new_sz
        _, new_roster = generate_age_roster(
            hh_size=new_sz,
            care_effect=row.get("care_effect", 0.0),
            rng=fraud_rng,
            fixed_head_age=row["head_age"],
        )
        row["roster_ages"] = new_roster


def inject_copy_paste(
    raw_interviews: List[Dict[str, Any]],
    params: Dict[str, Any],
    fabricated_indices: Set[int],
    village_models: Dict[str, Dict[str, Any]],
    fraud_rng: np.random.Generator,
) -> None:
    edit_rate = params["edit_rate"]
    gps_jitter_sd = params["gps_jitter_sd_m"]

    honest_candidates = [
        i for i in range(len(raw_interviews))
        if i not in fabricated_indices
    ]
    if not honest_candidates:
        honest_candidates = list(range(len(raw_interviews)))

    for idx in fabricated_indices:
        row = raw_interviews[idx]
        vid = row["village_id"]

        same_vil_honest = [i for i in honest_candidates if raw_interviews[i]["village_id"] == vid and i != idx]
        source_idx = same_vil_honest[0] if same_vil_honest else honest_candidates[0]
        source_row = raw_interviews[source_idx]

        row["hh_size"] = source_row["hh_size"]
        row["head_age"] = source_row["head_age"]
        row["roster_ages"] = list(source_row["roster_ages"])
        row["assets"] = dict(source_row["assets"])

        v_model = village_models[vid]
        if fraud_rng.uniform(0.0, 1.0) < edit_rate:
            new_sz = max(1, int(fraud_rng.poisson(v_model["mean_hh_size"] - 1.0) + 1))
            row["hh_size"] = new_sz
            new_head_age, new_roster = generate_age_roster(
                hh_size=new_sz,
                care_effect=row.get("care_effect", 0.0),
                rng=fraud_rng,
            )
            row["head_age"] = new_head_age
            row["roster_ages"] = new_roster
        for k in list(row["assets"].keys()):
            if fraud_rng.uniform(0.0, 1.0) < edit_rate:
                row["assets"][k] = 1 if fraud_rng.uniform(0.0, 1.0) < v_model["probs"][k] else 0

        jy, jx = fraud_rng.normal(0.0, gps_jitter_sd, size=2)
        jdlat, jdlon = _meters_to_deg(jy, jx, source_row["gps_lat"])
        row["gps_lat"] = round(source_row["gps_lat"] + jdlat, 7)
        row["gps_lon"] = round(source_row["gps_lon"] + jdlon, 7)


def inject_partial_section(
    raw_interviews: List[Dict[str, Any]],
    params: Dict[str, Any],
    fabricated_indices: Set[int],
    fraud_rng: np.random.Generator,
) -> None:
    """R1: Only roster_ages is invented; hh_size, head_age, assets, and GPS are honest."""
    heaping_prob = float(params.get("heaping_prob", 0.65))
    for idx in fabricated_indices:
        row = raw_interviews[idx]
        hh_sz = row["hh_size"]
        head_age = row["head_age"]
        raw_ages = [head_age]

        if hh_sz >= 2:
            spouse_age = int(round(head_age + fraud_rng.normal(-2.0, 1.5)))
            raw_ages.append(max(18, min(95, spouse_age)))

        remaining = hh_sz - len(raw_ages)
        if remaining > 0:
            max_child_age = max(5, head_age - 18)
            base_child_age = int(fraud_rng.integers(5, max_child_age + 1)) if max_child_age >= 5 else 5
            for _ in range(remaining):
                c_age = int(round(base_child_age + fraud_rng.normal(0.0, 1.5)))
                raw_ages.append(max(0, min(head_age - 15, c_age)))

        new_roster = []
        for age in raw_ages:
            if fraud_rng.uniform(0.0, 1.0) < heaping_prob:
                new_roster.append(int(round(age / 5.0) * 5))
            else:
                new_roster.append(int(age))
        row["roster_ages"] = new_roster

