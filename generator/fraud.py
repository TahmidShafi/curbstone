"""Fraud injection module implementing DGP §5, design rules R1-R4, and ground truth labels."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
import numpy as np
import pandas as pd

from generator.geography import Geography
from generator.fraud_modes import (
    apply_rushed_pre_scheduling as _apply_rushed,
    inject_copy_paste,
    inject_invented_gps,
    inject_partial_section,
    inject_straight_lining,
    inject_too_average,
)


ACTIVE_FRAUD_MODES = [
    "copy_paste",
    "straight_lining",
    "rushed",
    "invented_gps",
    "too_average",
]

ALL_FRAUD_MODES_WITH_HOLDOUT = ACTIVE_FRAUD_MODES + ["partial_section"]


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
    include_holdout: bool = False,
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

    available_modes = ALL_FRAUD_MODES_WITH_HOLDOUT if include_holdout else ACTIVE_FRAUD_MODES

    # Stratified mode assignment: cycle through shuffled permutations of the available modes
    modes_cycle: List[str] = []
    while len(modes_cycle) < n_fab:
        modes_cycle.extend([str(m) for m in fraud_rng.permutation(available_modes)])
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

        elif mode == "partial_section":
            r = m_cfg.get("heaping_prob_range", [0.5, 0.8])
            params["heaping_prob"] = float(fraud_rng.uniform(r[0], r[1]))
            int_name = "heaping_prob"
            int_val = params["heaping_prob"]

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
    fabricated_indices: Set[int],
) -> None:
    """R3: Apply duration compression before timestamp scheduling."""
    if fab_profile.primary_mode == "rushed":
        _apply_rushed(raw_interviews, fab_profile.params, fabricated_indices)


def inject_fraud_into_submissions(
    raw_interviews: List[Dict[str, Any]],
    fab_profile: FabricatorProfile,
    fabricated_indices: Set[int],
    geography: Geography,
    village_models: Dict[str, Dict[str, Any]],
    fraud_rng: np.random.Generator,
) -> None:
    """R1: Apply fraud mode alterations to only the allowed fields of fabricated records."""
    mode = fab_profile.primary_mode
    params = fab_profile.params

    if mode == "straight_lining":
        inject_straight_lining(raw_interviews, params, fabricated_indices, fraud_rng)
    elif mode == "invented_gps":
        inject_invented_gps(raw_interviews, params, fabricated_indices, geography, fraud_rng)
    elif mode == "too_average":
        inject_too_average(raw_interviews, params, fabricated_indices, village_models, fraud_rng)
    elif mode == "copy_paste":
        inject_copy_paste(raw_interviews, params, fabricated_indices, village_models, fraud_rng)
    elif mode == "partial_section":
        inject_partial_section(raw_interviews, params, fabricated_indices, fraud_rng)
    elif mode == "rushed":
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
