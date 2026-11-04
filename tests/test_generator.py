"""Tests for honest synthetic data generator properties, determinism, and scheduler."""

from datetime import datetime, time
import numpy as np

from generator.geography import build_geography
from generator.enumerators import (
    allocate_workload_across_villages,
    build_enumerators,
)
from generator.households import (
    generate_age_roster,
    generate_household_size,
)
from generator.interviews import generate_submissions_for_round


def test_determinism(config):
    """Same seed produces identical output; different seed produces different output."""
    rng1 = np.random.default_rng(12345)
    geo1 = build_geography(config, rng1)
    e1 = build_enumerators(config, list(geo1.villages.keys()), rng1)
    df1, _ = generate_submissions_for_round(config, geo1, e1, "medium", 1, rng1)

    rng2 = np.random.default_rng(12345)
    geo2 = build_geography(config, rng2)
    e2 = build_enumerators(config, list(geo2.villages.keys()), rng2)
    df2, _ = generate_submissions_for_round(config, geo2, e2, "medium", 1, rng2)

    rng3 = np.random.default_rng(99999)
    geo3 = build_geography(config, rng3)
    e3 = build_enumerators(config, list(geo3.villages.keys()), rng3)
    df3, _ = generate_submissions_for_round(config, geo3, e3, "medium", 1, rng3)

    assert df1.equals(df2), "Identical seeds must produce identical DataFrames"
    assert not df1.equals(df3), "Different seeds must produce different DataFrames"


def test_peer_overlap_and_village_constraints(config):
    """Every village has >= 2 enumerators, and every enumerator shares >= 1 village with peers."""
    rng = np.random.default_rng(42)
    geo = build_geography(config, rng)
    village_ids = list(geo.villages.keys())
    enumerators = build_enumerators(config, village_ids, rng)

    village_to_enums = {vid: [] for vid in village_ids}
    for e_id, enum in enumerators.items():
        assert 1 <= len(enum.assigned_villages) <= 3
        for vid in enum.assigned_villages:
            village_to_enums[vid].append(e_id)

    for vid, enums in village_to_enums.items():
        assert len(enums) >= 2, f"Village {vid} has fewer than 2 enumerators"

    for e_id, enum in enumerators.items():
        peers = {p for vid in enum.assigned_villages for p in village_to_enums[vid] if p != e_id}
        assert len(peers) >= 1, f"Enumerator {e_id} has no overlapping peers"


def test_submission_timing_and_durations(config):
    """Durations > 0, timestamps within work hours, and no overlapping interviews per enumerator."""
    rng = np.random.default_rng(42)
    geo = build_geography(config, rng)
    enumerators = build_enumerators(config, list(geo.villages.keys()), rng)
    df, _ = generate_submissions_for_round(config, geo, enumerators, "medium", 1, rng)

    assert len(df) > 0
    assert (df["duration_min"] > 0).all()

    work_start, work_end = time(9, 0, 0), time(17, 0, 0)
    for enum_id, group in df.groupby("enumerator_id"):
        prev_end = None
        for _, row in group.iterrows():
            start_dt = datetime.fromisoformat(row["start_time"])
            end_dt = datetime.fromisoformat(row["end_time"])
            assert start_dt < end_dt
            assert start_dt.time() >= work_start and end_dt.time() <= work_end
            assert start_dt.weekday() not in (4, 5) and end_dt.weekday() not in (4, 5)
            if prev_end is not None:
                assert start_dt >= prev_end
            prev_end = end_dt


def test_workload_allocation_multinomial():
    """Workload allocation distributes W_e across villages with each getting >= 1."""
    rng = np.random.default_rng(42)
    villages = ["V1", "V2", "V3"]
    workload = 17
    counts = allocate_workload_across_villages(workload, villages, rng)
    assert sum(counts.values()) == workload
    for v in villages:
        assert counts[v] >= 1


def test_household_size_properties():
    """Household size generated adheres to dgp §3.1 bounds and expected mean ~4.3."""
    rng = np.random.default_rng(42)
    sizes = [
        generate_household_size(w_v=rng.normal(0.0, 0.15), sigma_w=0.15, rng=rng)
        for _ in range(5000)
    ]
    assert all(1 <= s <= 15 for s in sizes)
    mean_size = np.mean(sizes)
    assert 4.0 <= mean_size <= 4.6, f"Empirical mean size {mean_size:.3f} outside expected [4.0, 4.6]"


def test_age_roster_basic_properties():
    """Age roster produces correct head age and member counts."""
    rng = np.random.default_rng(42)
    hh_size = 4
    head_age, roster = generate_age_roster(hh_size, care_effect=0.0, rng=rng)
    assert 25 <= head_age <= 70
    assert len(roster) == hh_size
    assert roster[0] == head_age
