"""Tests for evidence layer, demo dataset generation, Stata export round-trip, and determinism."""

from datetime import datetime
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from engine.evidence import build_evidence
from engine.features import build_feature_table
from engine.scoring import score_enumerators
import pyarrow.parquet as pq
from generator.run import run_generation
from scripts.build_demo import build_demo


def test_evidence_generation_does_not_mutate_scores(tmp_path):
    """Verify that building evidence does not alter scores table (hash identical before/after)."""
    sub_path = run_generation(
        icc_level="medium",
        seed=5000,
        out_dir=tmp_path / "data",
        round_num=1,
        prevalence=0.125,
        include_holdout=False,
        workload_range=[5, 60],
        verbose=False,
    )
    vil_path = tmp_path / "data" / "reference" / "villages.parquet"

    df_sub = pd.read_parquet(sub_path)
    df_vil = pd.read_parquet(vil_path)
    df_feat = build_feature_table(sub_path, vil_path, seed=12345)
    scores = score_enumerators(df_feat, scoring_version="v3")

    hash_before = hashlib.sha256(scores.to_json().encode("utf-8")).hexdigest()
    evidence_dict = build_evidence(df_sub, df_vil, scores, df_feat)
    hash_after = hashlib.sha256(scores.to_json().encode("utf-8")).hexdigest()

    assert hash_before == hash_after, "scores DataFrame was mutated during evidence generation!"
    assert len(evidence_dict) == len(scores)


def test_evidence_structure(tmp_path):
    """Verify that evidence details include estimates, 90% CIs, p-values, and submission IDs."""
    sub_path = run_generation(
        icc_level="medium",
        seed=5000,
        out_dir=tmp_path / "data",
        round_num=1,
        prevalence=0.125,
        include_holdout=False,
        workload_range=[5, 60],
        verbose=False,
    )
    vil_path = tmp_path / "data" / "reference" / "villages.parquet"

    df_sub = pd.read_parquet(sub_path)
    df_vil = pd.read_parquet(vil_path)
    df_feat = build_feature_table(sub_path, vil_path, seed=12345)
    scores = score_enumerators(df_feat, scoring_version="v3")

    ev_dict = build_evidence(df_sub, df_vil, scores, df_feat)

    assert "enum_27" in ev_dict
    e27 = ev_dict["enum_27"]
    assert "F3" in e27["features"]
    assert "F7" in e27["features"]

    f3 = e27["features"]["F3"]
    assert "p_value" in f3 and f3["p_value"] < 0.05
    assert "feature_estimate" in f3
    assert "shrunk_estimate" in f3
    assert "ci_90" in f3 and len(f3["ci_90"]) == 2
    assert "honest_range_90" in f3 and len(f3["honest_range_90"]) == 2
    assert "observed_rate" in f3
    assert "pairs" in f3 and len(f3["pairs"]) > 0
    assert len(f3["submission_ids"]) > 0

    f7 = e27["features"]["F7"]
    assert "points" in f7 and len(f7["points"]) > 0
    assert "village_references" in f7 and len(f7["village_references"]) > 0
    assert "honest_range_90" in f7 and len(f7["honest_range_90"]) == 2
    assert "honest_halfwidth" in f7 and f7["honest_halfwidth"] > 0


@pytest.mark.parametrize("scenario", ["mixed", "low"])
def test_stata_and_csv_exports_match(scenario):
    """Verify that flags.dta reads back with pandas.read_stata and matches flags.csv for both scenarios."""
    root = Path(__file__).resolve().parent.parent
    data_dir = root / "site" / "src" / "data" / scenario

    csv_path = data_dir / "flags.csv"
    dta_path = data_dir / "flags.dta"

    assert csv_path.is_file(), f"flags.csv not found in site/src/data/{scenario}"
    assert dta_path.is_file(), f"flags.dta not found in site/src/data/{scenario}"

    df_csv = pd.read_csv(csv_path, keep_default_na=False)
    df_dta = pd.read_stata(dta_path)

    expected_cols = ["enumerator_id", "n", "risk_score", "rank", "evidence", "rule_hits"]
    assert list(df_csv.columns) == expected_cols
    assert list(df_dta.columns) == expected_cols

    assert len(df_csv) == len(df_dta) == 40
    assert (df_csv["enumerator_id"] == df_dta["enumerator_id"]).all()
    assert (df_csv["n"] == df_dta["n"]).all()
    assert np.allclose(df_csv["risk_score"], df_dta["risk_score"], atol=1e-4)
    assert (df_csv["rank"] == df_dta["rank"]).all()
    assert (df_csv["evidence"] == df_dta["evidence"]).all()
    assert (df_csv["rule_hits"] == df_dta["rule_hits"]).all()


def test_demo_build_deterministic(tmp_path):
    """Verify that build_demo produces bit-for-bit identical files across multiple executions."""
    dir1 = tmp_path / "run1"
    dir2 = tmp_path / "run2"
    res1 = tmp_path / "res1"
    res2 = tmp_path / "res2"

    build_demo(scenario="all", base_data_dir=dir1, results_dir=res1, verbose=False)
    build_demo(scenario="all", base_data_dir=dir2, results_dir=res2, verbose=False)

    for scenario in ["mixed", "low"]:
        sc_dir1 = dir1 / scenario
        sc_dir2 = dir2 / scenario
        files1 = sorted([f.name for f in sc_dir1.iterdir() if f.is_file()])
        files2 = sorted([f.name for f in sc_dir2.iterdir() if f.is_file()])
        assert files1 == files2, f"Files list mismatch in scenario {scenario}: {files1} != {files2}"

        for fname in files1:
            h1 = hashlib.sha256(open(sc_dir1 / fname, "rb").read()).hexdigest()
            h2 = hashlib.sha256(open(sc_dir2 / fname, "rb").read()).hexdigest()
            assert h1 == h2, f"Scenario {scenario} file {fname} hash mismatch between runs: {h1} != {h2}"


def test_all_parquet_files_valid_and_nonempty():
    """Verify that every parquet file under site/src/data can be opened by pyarrow and has rows."""
    root = Path(__file__).resolve().parent.parent
    data_dir = root / "site" / "src" / "data"
    parquet_files = sorted(list(data_dir.rglob("*.parquet")))
    assert len(parquet_files) > 0, "No parquet files found under site/src/data"

    for p in parquet_files:
        raw = p.read_bytes()
        assert len(raw) >= 8, f"{p} is too small ({len(raw)} bytes)"
        assert raw[:4] == b"PAR1", f"{p} does not start with PAR1 magic"
        assert raw[-4:] == b"PAR1", f"{p} does not end with PAR1 magic"
        tbl = pq.read_table(p)
        assert tbl.num_rows > 0, f"{p} has 0 rows"


@pytest.mark.parametrize("scenario", ["mixed", "low"])
def test_rule_hits_identical_between_variants(scenario):
    """Verify that rule hits are identical between shrinkage and no-shrinkage variants and match flags.csv."""
    root = Path(__file__).resolve().parent.parent
    data_dir = root / "site" / "src" / "data" / scenario

    rule_hits_path = data_dir / "rule_hits_by_enumerator.json"
    assert rule_hits_path.is_file(), f"rule_hits_by_enumerator.json not found in site/src/data/{scenario}"

    with open(rule_hits_path, "r", encoding="utf-8") as f:
        enum_hits = json.load(f)

    csv_path = data_dir / "flags.csv"
    df_csv = pd.read_csv(csv_path)
    for _, row in df_csv.iterrows():
        eid = str(row["enumerator_id"])
        assert eid in enum_hits
        assert int(row["rule_hits"]) == int(enum_hits[eid])
