"""Fraud injection module implementing DGP §5, design rules R1-R4, and ground truth labels."""

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from generator.geography import Geography, _meters_to_deg
from generator.households import generate_age_roster


ACTIVE_FRAUD_MODES = [
    "copy_paste",
    "straight_lining",
    "rushed",
    "invented_gps",
    "too_average",
]


@dataclass
class FabricatorProfile:
    enumerator_id: str
    primary_mode: str
    target_share: float
    intensity_name: str
    intensity_value: float
    params: Dict[str, Any] = field(default_factory=dict)


def select_fabricators(
    enumerators: Dict[str, Any],
    prevalence: float,
    share_range: List[float],
    fraud_cfg: Dict[str, Any],
    fraud_rng: np.random.Generator,
) -> Dict[str, FabricatorProfile]:
    """Select fabricators uniformly at random independent of enumerator characteristics (R4)."""
    n_enum = len(enumerators)
    if prevalence <= 0.0:
        return {}

    n_fab = max(1, int(round(prevalence * n_enum)))
    enum_ids = sorted(list(enumerators.keys()))
    chosen_ids = [str(x) for x in fraud_rng.choice(enum_ids, size=n_fab, replace=False)]

    modes_cfg = fraud_cfg.get("modes", {})
    profiles: Dict[str, FabricatorProfile] = {}

    # Stratified mode assignment: cycle through shuffled permutations of the 5 active modes
    modes_cycle: List[str] = []
    while len(modes_cycle) < n_fab:
        modes_cycle.extend([str(m) for m in fraud_rng.permutation(ACTIVE_FRAUD_MODES)])
    assigned_modes = modes_cycle[:n_fab]

    for idx, e_id in enumerate(chosen_ids):
        mode = assigned_modes[idx]
        s = float(fraud_rng.uniform(share_range[0], share_range[1]))
        m_cfg = modes_cfg.get(mode, {})
        params: Dict[str, Any] = {}
        int_name = "intensity"
        int_val = float(m_cfg.get("intensity", 0.5))

        if mode == "copy_paste":
            r = m_cfg.get("edit_rate_range", [0.1, 0.3])
            params["edit_rate"] = float(fraud_rng.uniform(r[0], r[1]))
            params["gps_jitter_sd_m"] = float(m_cfg.get("gps_jitter_sd_m", 15.0))
            int_name = "edit_rate"
            int_val = params["edit_rate"]

        elif mode == "straight_lining":
            r = m_cfg.get("prob_straight_range", [0.7, 1.0])
            params["prob_straight"] = float(fraud_rng.uniform(r[0], r[1]))
            params["all_zero_prob"] = float(m_cfg.get("all_zero_prob", 0.8))
            params["all_one_prob"] = float(m_cfg.get("all_one_prob", 0.2))
            int_name = "prob_straight"
            int_val = params["prob_straight"]

        elif mode == "rushed":
            r = m_cfg.get("duration_multiplier_range", [0.3, 0.5])
            params["duration_multiplier"] = float(fraud_rng.uniform(r[0], r[1]))
            int_name = "duration_multiplier"
            int_val = params["duration_multiplier"]

        elif mode == "invented_gps":
            choices = m_cfg.get("n_anchor_choices", [1, 2, 3])
            params["n_anchor"] = int(fraud_rng.choice(choices))
            params["anchor_radius_m"] = float(m_cfg.get("anchor_radius_m", 200.0))
            params["jitter_sd_m"] = float(m_cfg.get("jitter_sd_m", 5.0))
            int_name = "n_anchor"
            int_val = float(params["n_anchor"])

        elif mode == "too_average":
            r = m_cfg.get("noise_range", [0.0, 0.2])
            params["noise_rate"] = float(fraud_rng.uniform(r[0], r[1]))
            params["hh_size_noise_sd"] = float(m_cfg.get("hh_size_noise_sd", 0.5))
            int_name = "noise_rate"
            int_val = params["noise_rate"]

        profiles[e_id] = FabricatorProfile(
            enumerator_id=e_id,
            primary_mode=mode,
            target_share=s,
            intensity_name=int_name,
            intensity_value=int_val,
            params=params,
        )

    return profiles


def apply_rushed_pre_scheduling(
    raw_interviews: List[Dict[str, Any]],
    fab_profile: FabricatorProfile,
    fabricated_indices: set,
) -> None:
    """R3: Apply duration compression before timestamp scheduling."""
    if fab_profile.primary_mode != "rushed":
        return
    mult = fab_profile.params["duration_multiplier"]
    for idx in fabricated_indices:
        dur = raw_interviews[idx]["duration_min"] * mult
        raw_interviews[idx]["duration_min"] = max(2.0, dur)


def inject_fraud_into_submissions(
    raw_interviews: List[Dict[str, Any]],
    fab_profile: FabricatorProfile,
    fabricated_indices: set,
    geography: Geography,
    village_models: Dict[str, Dict[str, Any]],
    fraud_rng: np.random.Generator,
) -> None:
    """R1: Apply fraud mode alterations to only the allowed fields of fabricated records."""
    mode = fab_profile.primary_mode
    params = fab_profile.params

    if mode == "partial_section":
        # held out until detectors are frozen
        raise NotImplementedError("held out until detectors are frozen")

    if mode == "straight_lining":
        p_straight = params["prob_straight"]
        p_zero = params["all_zero_prob"]
        for idx in fabricated_indices:
            row = raw_interviews[idx]
            if fraud_rng.uniform(0.0, 1.0) < p_straight:
                val = 0 if fraud_rng.uniform(0.0, 1.0) < p_zero else 1
                for k in list(row["assets"].keys()):
                    row["assets"][k] = val

    elif mode == "invented_gps":
        n_anchor = params["n_anchor"]
        jitter_sd = params["jitter_sd_m"]
        radius = params["anchor_radius_m"]

        # Generate anchor points once per village for this fabricator
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

    elif mode == "too_average":
        noise_rate = params["noise_rate"]
        hh_noise_sd = params["hh_size_noise_sd"]
        for idx in fabricated_indices:
            row = raw_interviews[idx]
            vid = row["village_id"]
            v_model = village_models[vid]

            # Set assets to village mode + noise flip
            for k in list(row["assets"].keys()):
                modal_val = v_model["modes"][k]
                if fraud_rng.uniform(0.0, 1.0) < noise_rate:
                    modal_val = 1 - modal_val
                row["assets"][k] = modal_val

            # Household size close to village mean with consistent age roster
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

    elif mode == "copy_paste":
        edit_rate = params["edit_rate"]
        gps_jitter_sd = params["gps_jitter_sd_m"]

        # Pool honest candidates by this enumerator
        honest_candidates = [
            i for i in range(len(raw_interviews))
            if i not in fabricated_indices
        ]
        if not honest_candidates:
            honest_candidates = list(range(len(raw_interviews)))

        for idx in fabricated_indices:
            row = raw_interviews[idx]
            vid = row["village_id"]

            # Prefer honest submission from same village
            same_vil_honest = [i for i in honest_candidates if raw_interviews[i]["village_id"] == vid and i != idx]
            source_idx = same_vil_honest[0] if same_vil_honest else honest_candidates[0]
            source_row = raw_interviews[source_idx]

            # Copy household fields
            row["hh_size"] = source_row["hh_size"]
            row["head_age"] = source_row["head_age"]
            row["roster_ages"] = list(source_row["roster_ages"])
            row["assets"] = dict(source_row["assets"])

            # Re-draw hh_size and roster together with prob edit_rate from honest village model
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

            # GPS = source GPS + N(0, 15 m)
            jy, jx = fraud_rng.normal(0.0, gps_jitter_sd, size=2)
            jdlat, jdlon = _meters_to_deg(jy, jx, source_row["gps_lat"])
            row["gps_lat"] = round(source_row["gps_lat"] + jdlat, 7)
            row["gps_lon"] = round(source_row["gps_lon"] + jdlon, 7)

    elif mode == "rushed":
        # Handled in pre-scheduling stage
        pass


def build_truth_label_dataframes(
    submission_records: List[Dict[str, Any]],
    enumerator_profiles: Dict[str, FabricatorProfile],
    enumerator_interview_counts: Dict[str, int],
    enumerator_fabricated_counts: Dict[str, int],
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Assemble separate ground-truth label tables (dgp §6)."""
    sub_rows = [
        {
            "submission_id": rec["submission_id"],
            "is_fabricated": bool(rec["is_fabricated"]),
            "fraud_mode": rec["fraud_mode"],
        }
        for rec in submission_records
    ]
    df_sub = pd.DataFrame(sub_rows)

    enum_rows = []
    for e_id, n_total in sorted(enumerator_interview_counts.items()):
        n_fab = enumerator_fabricated_counts.get(e_id, 0)
        prof = enumerator_profiles.get(e_id)
        primary_mode = prof.primary_mode if prof else None
        param_name = prof.intensity_name if prof else None
        param_val = prof.intensity_value if prof else None

        fab_share_realized = round(n_fab / max(1, n_total), 4)
        enum_rows.append({
            "enumerator_id": e_id,
            "fab_share_realized": fab_share_realized,
            "primary_mode": primary_mode,
            "n_interviews": n_total,
            "n_fabricated": n_fab,
            "intensity_name": param_name,
            "intensity_value": param_val,
        })
    df_enum = pd.DataFrame(enum_rows)

    return df_sub, df_enum

