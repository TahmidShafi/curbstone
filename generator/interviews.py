"""Interview generator: paradata, timing scheduler, GPS error, and full submission records."""

from datetime import datetime, time, timedelta, timezone
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

# Bangladesh Standard Time (BST) is fixed at UTC+6 (no Daylight Saving Time)
BANGLADESH_TZ = timezone(timedelta(hours=6))

from generator.geography import Geography, _meters_to_deg
from generator.enumerators import Enumerator
from generator.households import (
    apply_item_nonresponse,
    compute_sigma_u,
    generate_age_roster,
    generate_household_assets,
    generate_household_size,
    generate_village_effects,
    get_calibrated_alphas,
)
from generator.fraud import (
    apply_rushed_pre_scheduling,
    build_truth_label_dataframes,
    inject_fraud_into_submissions,
    select_fabricators,
)


def get_next_working_day(dt: datetime, start_hour: int = 9) -> datetime:
    """Advance to start_hour:00 of the next working day (Sunday to Thursday in Bangladesh)."""
    next_date = dt.date() + timedelta(days=1)
    while next_date.weekday() in (4, 5):  # Friday (4) or Saturday (5)
        next_date += timedelta(days=1)
    return datetime(
        next_date.year,
        next_date.month,
        next_date.day,
        start_hour,
        0,
        0,
        tzinfo=dt.tzinfo,
    )


def compute_duration_min(
    hh_size: int,
    speed_effect: float,
    mu: float,
    gamma: float,
    sigma_eps: float,
    rng: np.random.Generator,
) -> float:
    """Compute interview duration in minutes according to log-linear model (dgp §3.5)."""
    eps = float(rng.normal(0.0, sigma_eps))
    log_dur = mu + (gamma * hh_size) + speed_effect + eps
    dur_min = math.exp(log_dur)
    return max(5.0, min(420.0, dur_min))


def generate_submissions_for_round(
    config: Dict[str, Any],
    geography: Geography,
    enumerators: Dict[str, Enumerator],
    icc_level: str,
    round_num: int,
    rng: np.random.Generator,
    fraud_rng: Optional[np.random.Generator] = None,
    prevalence: Optional[float] = None,
    enable_fraud: bool = True,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Generate all interview submissions for a survey round, optionally injecting fraud."""
    v_eff_cfg = config["village_effects"]
    hh_cfg = config["household"]
    int_cfg = config["interview"]
    gps_cfg = config.get("gps", {})
    fraud_cfg = config.get("fraud", {})

    target_icc = float(v_eff_cfg["icc_levels"][icc_level])
    beta = float(v_eff_cfg.get("beta", 0.8))
    sigma_w = float(v_eff_cfg.get("sigma_w", 0.15))
    sigma_u = compute_sigma_u(target_icc, beta=beta)

    dur_cfg = int_cfg.get("duration_lognormal", {})
    mu_dur = float(dur_cfg.get("mu", 3.355))
    sigma_dur = float(dur_cfg.get("sigma", 0.25))
    gamma_dur = float(int_cfg.get("per_member_minutes", 0.05))

    asset_targets = {a["name"]: float(a["base_prob"]) for a in hh_cfg["assets"]}
    alphas = get_calibrated_alphas(asset_targets=asset_targets, icc=target_icc, beta=beta)

    device_error_sd = float(gps_cfg.get("device_error_sd_m", 10.0))
    acc_min, acc_max = gps_cfg.get("accuracy_range_m", [3.0, 25.0])

    tz = BANGLADESH_TZ
    start_date_str = str(int_cfg.get("start_date", "2026-11-01"))
    base_start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    work_start_hour, work_end_hour = int_cfg.get("work_hours", [9, 17])
    work_end_time = time(work_end_hour, 0, 0)
    gap_same_min = int_cfg.get("gap_same_village_min", [5, 20])
    gap_diff_min = int_cfg.get("gap_change_village_min", [30, 90])

    village_ids = list(geography.villages.keys())
    u_v_dict, w_v_dict = generate_village_effects(
        village_ids=village_ids,
        sigma_u=sigma_u,
        sigma_w=sigma_w,
        rng=rng,
    )

    # Precalculate honest village models for too_average and copy_paste
    village_models: Dict[str, Dict[str, Any]] = {}
    for vid in village_ids:
        u_v = u_v_dict[vid]
        w_v = w_v_dict[vid]
        lam_v = 3.30 * math.exp(w_v - (sigma_w ** 2) / 2.0)
        v_probs = {}
        v_modes = {}
        for a_name, alpha in alphas.items():
            p = 1.0 / (1.0 + math.exp(-(alpha + u_v)))
            v_probs[a_name] = p
            v_modes[a_name] = 1 if p >= 0.5 else 0
        village_models[vid] = {
            "mean_hh_size": 1.0 + lam_v,
            "probs": v_probs,
            "modes": v_modes,
        }

    # Demand check & sampling frame enlargement
    for vid in village_ids:
        demand = sum(enum.village_workloads.get(vid, 0) for enum in enumerators.values())
        geography.enlarge_frame_if_needed(vid, demand, rng=rng)

    village_hh_pool: Dict[str, List[str]] = {}
    for vid in village_ids:
        vil = geography.get_village(vid)
        village_hh_pool[vid] = [str(x) for x in rng.permutation(vil.household_ids)]

    # Select fabricators if enabled (R2 & R4)
    fab_profiles: Dict[str, Any] = {}
    if enable_fraud and fraud_rng is not None:
        p_val = prevalence if prevalence is not None else float(fraud_cfg.get("prevalence", 0.10))
        share_range = fraud_cfg.get("share_range", [0.30, 0.90])
        fab_profiles = select_fabricators(enumerators, p_val, share_range, fraud_cfg, fraud_rng)

    submission_counter = 0
    final_rows: List[Dict[str, Any]] = []
    truth_records: List[Dict[str, Any]] = []
    enum_n_interviews: Dict[str, int] = {}
    enum_n_fabricated: Dict[str, int] = {}

    sorted_enumerators = sorted(enumerators.values(), key=lambda e: e.enumerator_id)

    for enum in sorted_enumerators:
        e_id = enum.enumerator_id
        is_fabricator = e_id in fab_profiles
        fab_profile = fab_profiles.get(e_id)

        # Step 1: Generate candidate records honestly using rng (honest stream)
        raw_interviews: List[Dict[str, Any]] = []
        n_assigned_villages = len(enum.assigned_villages)

        for v_idx, vid in enumerate(enum.assigned_villages):
            n_interviews = enum.village_workloads[vid]
            vil = geography.get_village(vid)
            u_v, w_v = u_v_dict[vid], w_v_dict[vid]
            assigned_hhs = [village_hh_pool[vid].pop() for _ in range(n_interviews)]

            for i_idx, hh_id in enumerate(assigned_hhs):
                hh_size = generate_household_size(w_v=w_v, sigma_w=sigma_w, rng=rng)
                assets_raw, _ = generate_household_assets(u_v=u_v, alphas=alphas, beta=beta, rng=rng)
                assets = apply_item_nonresponse(assets_raw, care_effect=enum.care_effect, rng=rng)
                head_age, roster_ages = generate_age_roster(hh_size=hh_size, care_effect=enum.care_effect, rng=rng)

                dur_min = compute_duration_min(
                    hh_size=hh_size,
                    speed_effect=enum.speed_effect,
                    mu=mu_dur,
                    gamma=gamma_dur,
                    sigma_eps=sigma_dur,
                    rng=rng,
                )

                true_lat, true_lon = vil.household_locations[hh_id]
                err_y, err_x = rng.normal(0.0, device_error_sd, size=2)
                dlat, dlon = _meters_to_deg(err_y, err_x, true_lat)
                gps_lat = true_lat + dlat
                gps_lon = true_lon + dlon
                gps_acc = float(rng.uniform(acc_min, acc_max))

                is_last_in_village = (i_idx == n_interviews - 1)
                is_last_overall = is_last_in_village and (v_idx == n_assigned_villages - 1)
                if not is_last_overall:
                    gap_range = gap_diff_min if is_last_in_village else gap_same_min
                    gap_after = float(rng.uniform(gap_range[0], gap_range[1]))
                else:
                    gap_after = 0.0

                raw_interviews.append({
                    "enumerator_id": e_id,
                    "upazila_code": vil.upazila_code,
                    "village_id": vid,
                    "hh_size": hh_size,
                    "head_age": head_age,
                    "roster_ages": roster_ages,
                    "assets": assets,
                    "duration_min": dur_min,
                    "gps_lat": round(gps_lat, 7),
                    "gps_lon": round(gps_lon, 7),
                    "gps_accuracy": round(gps_acc, 2),
                    "gap_after": gap_after,
                })

        w_e = len(raw_interviews)
        enum_n_interviews[e_id] = w_e

        # Step 2: Pre-scheduling fraud injection (R1, R3 using fraud_rng)
        fab_indices = set()
        if is_fabricator and fraud_rng is not None:
            n_fab_interviews = min(w_e, max(1, int(round(fab_profile.target_share * w_e))))
            fab_indices = set(fraud_rng.choice(w_e, size=n_fab_interviews, replace=False))
            enum_n_fabricated[e_id] = len(fab_indices)
            # R3: pre-scheduling duration alteration for rushed
            apply_rushed_pre_scheduling(raw_interviews, fab_profile, fab_indices)
            # R1: mode field alteration
            inject_fraud_into_submissions(raw_interviews, fab_profile, fab_indices, geography, village_models, fraud_rng)
        else:
            enum_n_fabricated[e_id] = 0

        # Step 3: Timestamp scheduling
        current_dt = datetime(
            base_start_date.year,
            base_start_date.month,
            base_start_date.day,
            work_start_hour,
            0,
            0,
            tzinfo=tz,
        )

        for idx, item in enumerate(raw_interviews):
            submission_counter += 1
            sub_id = f"sub_{round_num:02d}_{submission_counter:05d}"
            dur_td = timedelta(minutes=item["duration_min"])
            tentative_end = current_dt + dur_td

            if tentative_end.time() > work_end_time or tentative_end.date() != current_dt.date():
                current_dt = get_next_working_day(current_dt, start_hour=work_start_hour)
                tentative_end = current_dt + dur_td

            start_dt, end_dt = current_dt, tentative_end
            is_fab = (idx in fab_indices)
            f_mode = fab_profile.primary_mode if is_fab else None

            row = {
                "submission_id": sub_id,
                "round": round_num,
                "enumerator_id": e_id,
                "upazila_code": item["upazila_code"],
                "village_id": item["village_id"],
                "start_time": start_dt.isoformat(),
                "end_time": end_dt.isoformat(),
                "duration_min": round(item["duration_min"], 2),
                "gps_lat": item["gps_lat"],
                "gps_lon": item["gps_lon"],
                "gps_accuracy": item["gps_accuracy"],
                "hh_size": item["hh_size"],
                "head_age": item["head_age"],
                "roster_ages": item["roster_ages"],
            }
            for a_name in asset_targets:
                row[a_name] = item["assets"][a_name]

            final_rows.append(row)
            truth_records.append({
                "submission_id": sub_id,
                "is_fabricated": is_fab,
                "fraud_mode": f_mode,
            })

            # Advance current time with honest gap
            if item["gap_after"] > 0:
                current_dt = end_dt + timedelta(minutes=item["gap_after"])
                if current_dt.time() >= work_end_time or current_dt.date() != end_dt.date():
                    current_dt = get_next_working_day(current_dt, start_hour=work_start_hour)
            else:
                current_dt = end_dt

    df = pd.DataFrame(final_rows)
    df_labels_sub, df_labels_enum = build_truth_label_dataframes(
        truth_records,
        fab_profiles,
        enum_n_interviews,
        enum_n_fabricated,
    )

    meta = {
        "round": round_num,
        "icc_level": icc_level,
        "target_icc": target_icc,
        "sigma_u": sigma_u,
        "calibrated_alphas": alphas,
        "u_v": u_v_dict,
        "w_v": w_v_dict,
        "frame_expansion_log": geography.frame_expansion_log,
        "labels_submission": df_labels_sub,
        "labels_enumerator": df_labels_enum,
        "fabricator_profiles": fab_profiles,
    }
    return df, meta
