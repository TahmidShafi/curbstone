"""Tests for fraud injection, stream separation (R2), trace isolation (R1), and truth labels."""

from datetime import datetime, time
import math
from pathlib import Path
import numpy as np
import pytest

from generator.geography import METERS_PER_DEG_LAT, build_geography
from generator.enumerators import build_enumerators
from generator.fraud import inject_fraud_into_submissions
from generator.interviews import generate_submissions_for_round
from generator.run import run_generation


def test_r2_stream_separation(config):
    """R2: Same seed with fraud on vs off yields byte-identical records for honest enumerators."""
    seed = 42
    seq = np.random.SeedSequence(seed)
    h_seq, f_seq = seq.spawn(2)

    # Fraud OFF
    geo1 = build_geography(config, np.random.default_rng(h_seq))
    e1 = build_enumerators(config, list(geo1.villages.keys()), np.random.default_rng(h_seq))
    df_off, _ = generate_submissions_for_round(
        config, geo1, e1, "medium", 1, np.random.default_rng(h_seq), enable_fraud=False
    )

    # Fraud ON
    geo2 = build_geography(config, np.random.default_rng(h_seq))
    e2 = build_enumerators(config, list(geo2.villages.keys()), np.random.default_rng(h_seq))
    df_on, meta_on = generate_submissions_for_round(
        config, geo2, e2, "medium", 1, np.random.default_rng(h_seq),
        fraud_rng=np.random.default_rng(f_seq), enable_fraud=True
    )

    fab_enums = set(meta_on["fabricator_profiles"].keys())
    honest_enums = set(df_on["enumerator_id"]) - fab_enums

    df_on_h = df_on[df_on["enumerator_id"].isin(honest_enums)].reset_index(drop=True)
    df_off_h = df_off[df_off["enumerator_id"].isin(honest_enums)].reset_index(drop=True)

    assert df_on_h.equals(df_off_h), "Honest enumerator records must be byte-identical between fraud on and off"


def test_r1_trace_isolation(config):
    """R1: Each mode alters only its designated fields compared to honest counterpart."""
    asset_cols = {a["name"] for a in config["household"]["assets"]}
    allowed_diffs = {
        "copy_paste": {"hh_size", "head_age", "roster_ages", "gps_lat", "gps_lon"} | asset_cols,
        "straight_lining": asset_cols,
        "rushed": {"duration_min", "start_time", "end_time"},
        "invented_gps": {"gps_lat", "gps_lon"},
        "too_average": {"hh_size", "roster_ages"} | asset_cols,
    }

    modes_seen = set()
    for seed in range(10):
        seq = np.random.SeedSequence(seed)
        h_seq, f_seq = seq.spawn(2)
        geo = build_geography(config, np.random.default_rng(h_seq))
        enums = build_enumerators(config, list(geo.villages.keys()), np.random.default_rng(h_seq))

        df_h, _ = generate_submissions_for_round(
            config, geo, enums, "medium", 1, np.random.default_rng(h_seq), enable_fraud=False
        )
        df_f, meta_f = generate_submissions_for_round(
            config, geo, enums, "medium", 1, np.random.default_rng(h_seq),
            fraud_rng=np.random.default_rng(f_seq), enable_fraud=True
        )

        labels = meta_f["labels_submission"]
        fab_rows = df_f[labels["is_fabricated"]]

        for idx, row_f in fab_rows.iterrows():
            row_h = df_h.loc[idx]
            rec_mode = labels.loc[idx, "fraud_mode"]
            modes_seen.add(rec_mode)
            allowed = allowed_diffs[rec_mode]

            for col in df_f.columns:
                if col not in allowed:
                    assert row_f[col] == row_h[col], f"Mode {rec_mode} modified disallowed col {col}"

    assert len(modes_seen) >= 4, f"Observed modes {modes_seen} across seeds"


def test_no_data_leakage(tmp_path, config):
    """Data parquet must contain none of the truth label columns; truth files exist separately."""
    out_dir = tmp_path / "data"
    truth_dir = tmp_path / "truth"

    run_generation(
        icc_level="medium",
        seed=42,
        out_dir=out_dir,
        round_num=1,
        truth_dir=truth_dir,
    )

    data_file = out_dir / "round=1" / "interviews.parquet"
    truth_sub_file = truth_dir / "round=1" / "labels_submission.parquet"
    truth_enum_file = truth_dir / "round=1" / "labels_enumerator.parquet"

    assert data_file.exists()
    assert truth_sub_file.exists()
    assert truth_enum_file.exists()

    import pyarrow.parquet as pq
    data_cols = pq.read_table(data_file).column_names
    forbidden = ["is_fabricated", "fraud_mode", "fab_share", "primary_mode"]
    for col in forbidden:
        assert col not in data_cols, f"Forbidden label column {col} found in data parquet"

    truth_sub_cols = pq.read_table(truth_sub_file).column_names
    assert "submission_id" in truth_sub_cols
    assert "is_fabricated" in truth_sub_cols
    assert "fraud_mode" in truth_sub_cols


def test_n_fab_correct_including_prevalence_floor(config):
    """n_fab matches max(1, round(p * n_enum)) with forced minimum 1 at p=0.02."""
    for p, exp_n_fab in [(0.02, 1), (0.05, 2), (0.10, 4), (0.20, 8)]:
        seq = np.random.SeedSequence(42)
        h_seq, f_seq = seq.spawn(2)
        geo = build_geography(config, np.random.default_rng(h_seq))
        enums = build_enumerators(config, list(geo.villages.keys()), np.random.default_rng(h_seq))
        _, meta = generate_submissions_for_round(
            config, geo, enums, "medium", 1, np.random.default_rng(h_seq),
            fraud_rng=np.random.default_rng(f_seq), prevalence=p, enable_fraud=True
        )
        assert len(meta["fabricator_profiles"]) == exp_n_fab


def test_realized_share_within_tolerance(config):
    """Realized number of fabricated interviews is within +-1 of round(s * W_e)."""
    seq = np.random.SeedSequence(42)
    h_seq, f_seq = seq.spawn(2)
    geo = build_geography(config, np.random.default_rng(h_seq))
    enums = build_enumerators(config, list(geo.villages.keys()), np.random.default_rng(h_seq))
    _, meta = generate_submissions_for_round(
        config, geo, enums, "medium", 1, np.random.default_rng(h_seq),
        fraud_rng=np.random.default_rng(f_seq), prevalence=0.10, enable_fraud=True
    )

    df_enum = meta["labels_enumerator"]
    for _, row in df_enum.iterrows():
        if row["enumerator_id"] in meta["fabricator_profiles"]:
            prof = meta["fabricator_profiles"][row["enumerator_id"]]
            target_n = round(prof.target_share * row["n_interviews"])
            assert abs(row["n_fabricated"] - target_n) <= 1


def test_per_mode_trace_sanity(config):
    """Verify trace sanity: rushed ratio in [0.3, 0.5], invented_gps NN < 20m, straight_lining var = 0."""
    asset_cols = [a["name"] for a in config["household"]["assets"]]
    checked = {"rushed": False, "invented_gps": False, "straight_lining": False}

    for seed in range(25):
        seq = np.random.SeedSequence(seed)
        h_seq, f_seq = seq.spawn(2)
        geo = build_geography(config, np.random.default_rng(h_seq))
        enums = build_enumerators(config, list(geo.villages.keys()), np.random.default_rng(h_seq))

        df_h, _ = generate_submissions_for_round(
            config, geo, enums, "medium", 1, np.random.default_rng(h_seq), enable_fraud=False
        )
        df_f, meta_f = generate_submissions_for_round(
            config, geo, enums, "medium", 1, np.random.default_rng(h_seq),
            fraud_rng=np.random.default_rng(f_seq), enable_fraud=True
        )
        labels = meta_f["labels_submission"]

        # 1. Rushed ratio check
        rushed_idx = labels[labels["fraud_mode"] == "rushed"].index
        if len(rushed_idx) > 0:
            ratios = df_f.loc[rushed_idx, "duration_min"] / df_h.loc[rushed_idx, "duration_min"]
            assert 0.28 <= float(np.median(ratios)) <= 0.52
            checked["rushed"] = True

        # 2. Straight lining zero variance check
        sl_idx = labels[labels["fraud_mode"] == "straight_lining"].index
        if len(sl_idx) > 0:
            for _, r in df_f.loc[sl_idx].iterrows():
                vals = [r[c] for c in asset_cols if r[c] != -8]
                if vals and (all(v == 0 for v in vals) or all(v == 1 for v in vals)):
                    assert np.var(vals) == 0.0
            checked["straight_lining"] = True

        # 3. Invented GPS nearest neighbour distance < 20 m
        gps_idx = labels[labels["fraud_mode"] == "invented_gps"].index
        if len(gps_idx) >= 2:
            for (eid, vid), grp in df_f.loc[gps_idx].groupby(["enumerator_id", "village_id"]):
                if len(grp) >= 2:
                    lats, lons = grp["gps_lat"].values, grp["gps_lon"].values
                    nn_dists = []
                    for i in range(len(lats)):
                        dists = [
                            math.hypot(
                                (lats[i] - lats[j]) * METERS_PER_DEG_LAT,
                                (lons[i] - lons[j]) * (METERS_PER_DEG_LAT * math.cos(math.radians(24.5))),
                            )
                            for j in range(len(lats)) if i != j
                        ]
                        nn_dists.append(min(dists))
                    assert float(np.median(nn_dists)) < 20.0
                    checked["invented_gps"] = True

        if all(checked.values()):
            break

    assert all(checked.values()), f"Could not test all modes: {checked}"


def test_no_overlaps_and_work_hours_with_fraud(config):
    """Timestamps remain strictly valid, non-overlapping, and within work hours when fraud is on."""
    work_start, work_end = time(9, 0, 0), time(17, 0, 0)
    for seed in [0, 42, 99]:
        seq = np.random.SeedSequence(seed)
        h_seq, f_seq = seq.spawn(2)
        geo = build_geography(config, np.random.default_rng(h_seq))
        enums = build_enumerators(config, list(geo.villages.keys()), np.random.default_rng(h_seq))
        df, _ = generate_submissions_for_round(
            config, geo, enums, "medium", 1, np.random.default_rng(h_seq),
            fraud_rng=np.random.default_rng(f_seq), enable_fraud=True
        )

        for _, grp in df.groupby("enumerator_id"):
            prev_end = None
            for _, row in grp.iterrows():
                start_dt = datetime.fromisoformat(row["start_time"])
                end_dt = datetime.fromisoformat(row["end_time"])
                assert start_dt < end_dt
                assert start_dt.time() >= work_start and end_dt.time() <= work_end
                assert start_dt.weekday() not in (4, 5) and end_dt.weekday() not in (4, 5)
                if prev_end is not None:
                    assert start_dt >= prev_end
                prev_end = end_dt


def test_held_out_mode_not_implemented():
    """Held-out mode partial_section raises NotImplementedError until detectors are frozen."""
    from generator.fraud import FabricatorProfile
    prof = FabricatorProfile(
        enumerator_id="enum_01",
        primary_mode="partial_section",
        target_share=0.5,
        intensity_name="heaping_prob",
        intensity_value=0.6,
    )
    with pytest.raises(NotImplementedError, match="held out until detectors are frozen"):
        inject_fraud_into_submissions([], prof, {0}, None, {}, np.random.default_rng(42))


def test_stratified_mode_assignment(config):
    """Primary modes are assigned by cycling through shuffled permutations of the 5 modes."""
    from generator.fraud import ACTIVE_FRAUD_MODES, select_fabricators

    rng = np.random.default_rng(42)
    fake_enums = {f"enum_{i:02d}": None for i in range(40)}

    # At n_fab = 5 (prevalence = 5/40 = 0.125), all 5 modes must appear exactly once
    profs_5 = select_fabricators(fake_enums, prevalence=0.125, share_range=[0.3, 0.9], fraud_cfg=config["fraud"], fraud_rng=rng)
    assert len(profs_5) == 5
    assigned_5 = [p.primary_mode for p in profs_5.values()]
    assert set(assigned_5) == set(ACTIVE_FRAUD_MODES)

    # At n_fab = 8 (prevalence = 0.20), the first 5 must be a permutation of all 5
    profs_8 = select_fabricators(fake_enums, prevalence=0.20, share_range=[0.3, 0.9], fraud_cfg=config["fraud"], fraud_rng=rng)
    assert len(profs_8) == 8
    assigned_8 = [p.primary_mode for p in profs_8.values()]
    assert set(assigned_8[:5]) == set(ACTIVE_FRAUD_MODES)
