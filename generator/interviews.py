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


def get_next_working_day(dt: datetime, start_hour: int = 9) -> datetime:
    """Advance to start_hour:00 of the next working day (Sunday to Thursday in Bangladesh)."""
    next_date = dt.date() + timedelta(days=1)
    # Weekday in Python: Monday=0, ..., Thursday=3, Friday=4, Saturday=5, Sunday=6
    # Working days: Sunday (6), Monday (0), Tuesday (1), Wednesday (2), Thursday (3)
    # Weekend: Friday (4), Saturday (5)
    while next_date.weekday() in (4, 5):
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
    """Compute interview duration in minutes according to log-linear model (dgp §3.5).

    log(duration_min) = mu + gamma * hh_size + s_e + epsilon
    where epsilon ~ Normal(0, sigma_eps^2)
    """
    eps = float(rng.normal(0.0, sigma_eps))
    log_dur = mu + (gamma * hh_size) + speed_effect + eps
    # Bound duration between 5.0 and 420.0 minutes
    dur_min = math.exp(log_dur)
    return max(5.0, min(420.0, dur_min))


def generate_submissions_for_round(
    config: Dict[str, Any],
    geography: Geography,
    enumerators: Dict[str, Enumerator],
    icc_level: str,
    round_num: int,
    rng: np.random.Generator,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Generate all interview submissions for a survey round without fraud injection."""
    # Config parameters
    v_eff_cfg = config["village_effects"]
    hh_cfg = config["household"]
    int_cfg = config["interview"]
    gps_cfg = config.get("gps", {})

    target_icc = float(v_eff_cfg["icc_levels"][icc_level])
    beta = float(v_eff_cfg.get("beta", 0.8))
    sigma_w = float(v_eff_cfg.get("sigma_w", 0.15))
    sigma_u = compute_sigma_u(target_icc, beta=beta)

    # Durations config
    dur_cfg = int_cfg.get("duration_lognormal", {})
    mu_dur = float(dur_cfg.get("mu", 3.355))
    sigma_dur = float(dur_cfg.get("sigma", 0.25))
    gamma_dur = float(int_cfg.get("per_member_minutes", 0.05))

    # Assets & target rates
    asset_targets = {a["name"]: float(a["base_prob"]) for a in hh_cfg["assets"]}
    alphas = get_calibrated_alphas(asset_targets=asset_targets, icc=target_icc, beta=beta)

    # GPS config
    device_error_sd = float(gps_cfg.get("device_error_sd_m", 10.0))
    acc_min, acc_max = gps_cfg.get("accuracy_range_m", [3.0, 25.0])

    # Timing config (Bangladesh Standard Time: UTC+6, no DST)
    tz = BANGLADESH_TZ
    start_date_str = str(int_cfg.get("start_date", "2026-11-01"))
    base_start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    work_start_hour, work_end_hour = int_cfg.get("work_hours", [9, 17])
    work_end_time = time(work_end_hour, 0, 0)
    gap_same_min = int_cfg.get("gap_same_village_min", [5, 20])
    gap_diff_min = int_cfg.get("gap_change_village_min", [30, 90])

    # Generate village effects u_v and w_v
    village_ids = list(geography.villages.keys())
    u_v_dict, w_v_dict = generate_village_effects(
        village_ids=village_ids,
        sigma_u=sigma_u,
        sigma_w=sigma_w,
        rng=rng,
    )

    # Step 1: Collect total household demand per village from all enumerators
    village_demands: Dict[str, int] = {vid: 0 for vid in village_ids}
    for enum in enumerators.values():
        for vid, count in enum.village_workloads.items():
            village_demands[vid] += count

    # Step 2: Ensure village sampling frame satisfies demand (enlarge if necessary and log)
    for vid, demand in village_demands.items():
        geography.enlarge_frame_if_needed(vid, demand, rng=rng)

    # Step 3: Sample distinct households without replacement per village
    village_hh_pool: Dict[str, List[str]] = {}
    for vid in village_ids:
        vil = geography.get_village(vid)
        shuffled_hh = [str(x) for x in rng.permutation(vil.household_ids)]
        village_hh_pool[vid] = shuffled_hh

    # Step 4: Schedule interviews for each enumerator village by village
    rows: List[Dict[str, Any]] = []
    submission_counter = 0

    # Sort enumerators for deterministic iteration
    sorted_enumerators = sorted(enumerators.values(), key=lambda e: e.enumerator_id)

    for enum in sorted_enumerators:
        # Enumerator starts on Day 1 at work_start_hour:00
        current_dt = datetime(
            base_start_date.year,
            base_start_date.month,
            base_start_date.day,
            work_start_hour,
            0,
            0,
            tzinfo=tz,
        )

        n_assigned_villages = len(enum.assigned_villages)
        for v_idx, vid in enumerate(enum.assigned_villages):
            n_interviews = enum.village_workloads[vid]
            vil = geography.get_village(vid)
            u_v = u_v_dict[vid]
            w_v = w_v_dict[vid]

            # Pop distinct households for this enumerator
            assigned_hhs = [village_hh_pool[vid].pop() for _ in range(n_interviews)]

            for i_idx, hh_id in enumerate(assigned_hhs):
                submission_counter += 1
                sub_id = f"sub_{round_num:02d}_{submission_counter:05d}"

                # Household size and assets
                hh_size = generate_household_size(w_v=w_v, sigma_w=sigma_w, rng=rng)
                assets_raw, _ = generate_household_assets(u_v=u_v, alphas=alphas, beta=beta, rng=rng)
                assets = apply_item_nonresponse(assets_raw, care_effect=enum.care_effect, rng=rng)

                # Demographics
                head_age, roster_ages = generate_age_roster(
                    hh_size=hh_size,
                    care_effect=enum.care_effect,
                    rng=rng,
                )

                # Duration
                dur_min = compute_duration_min(
                    hh_size=hh_size,
                    speed_effect=enum.speed_effect,
                    mu=mu_dur,
                    gamma=gamma_dur,
                    sigma_eps=sigma_dur,
                    rng=rng,
                )

                # Timing: check if interview fits into current working day
                dur_td = timedelta(minutes=dur_min)
                tentative_end = current_dt + dur_td
                if tentative_end.time() > work_end_time or tentative_end.date() != current_dt.date():
                    # Advance to next working day
                    current_dt = get_next_working_day(current_dt, start_hour=work_start_hour)
                    tentative_end = current_dt + dur_td

                start_dt = current_dt
                end_dt = tentative_end

                # GPS location: true location + device error
                true_lat, true_lon = vil.household_locations[hh_id]
                err_y, err_x = rng.normal(0.0, device_error_sd, size=2)
                dlat, dlon = _meters_to_deg(err_y, err_x, true_lat)
                gps_lat = true_lat + dlat
                gps_lon = true_lon + dlon
                gps_acc = float(rng.uniform(acc_min, acc_max))

                # Assemble record according to dgp §3.8
                row = {
                    "submission_id": sub_id,
                    "round": round_num,
                    "enumerator_id": enum.enumerator_id,
                    "upazila_code": vil.upazila_code,
                    "village_id": vid,
                    "start_time": start_dt.isoformat(),
                    "end_time": end_dt.isoformat(),
                    "duration_min": round(dur_min, 2),
                    "gps_lat": round(gps_lat, 7),
                    "gps_lon": round(gps_lon, 7),
                    "gps_accuracy": round(gps_acc, 2),
                    "hh_size": hh_size,
                    "head_age": head_age,
                    "roster_ages": roster_ages,
                }
                # Asset columns
                for asset_name in asset_targets:
                    row[asset_name] = assets[asset_name]

                rows.append(row)

                # Gap to next interview
                is_last_in_village = (i_idx == n_interviews - 1)
                is_last_overall = is_last_in_village and (v_idx == n_assigned_villages - 1)

                if not is_last_overall:
                    if is_last_in_village:
                        gap_min = float(rng.uniform(gap_diff_min[0], gap_diff_min[1]))
                    else:
                        gap_min = float(rng.uniform(gap_same_min[0], gap_same_min[1]))

                    current_dt = end_dt + timedelta(minutes=gap_min)
                    if current_dt.time() >= work_end_time or current_dt.date() != end_dt.date():
                        current_dt = get_next_working_day(current_dt, start_hour=work_start_hour)

    df = pd.DataFrame(rows)
    meta = {
        "round": round_num,
        "icc_level": icc_level,
        "target_icc": target_icc,
        "sigma_u": sigma_u,
        "calibrated_alphas": alphas,
        "u_v": u_v_dict,
        "w_v": w_v_dict,
        "frame_expansion_log": geography.frame_expansion_log,
    }
    return df, meta

