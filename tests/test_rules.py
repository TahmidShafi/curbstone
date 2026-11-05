"""Tests for DQA rule engine, YAML validation, 24 rule unit fixtures, and leakage prevention."""

import ast
from pathlib import Path
import duckdb
import pandas as pd
import pytest

from engine.rules import load_rules, run_rules, validate_rules
from generator.run import run_generation


def test_leakage_in_engine():
    """Verify that engine/ never imports generator.fraud or contains the string 'truth'."""
    engine_dir = Path(__file__).resolve().parent.parent / "engine"
    py_files = list(engine_dir.glob("*.py"))
    assert len(py_files) > 0, "No python files found in engine/"

    for py_file in py_files:
        with open(py_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert "truth" not in content.lower(), f"Leakage: string 'truth' found in {py_file}"

        tree = ast.parse(content, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "generator.fraud", f"Leakage: 'import {alias.name}' in {py_file}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert node.module != "generator.fraud" and not node.module.startswith("generator.fraud"), (
                        f"Leakage: 'from {node.module} import ...' in {py_file}"
                    )


def test_yaml_validation_missing_key():
    with pytest.raises(ValueError, match="missing required fields"):
        validate_rules([{"id": "R01", "version": "1.0.0", "level": "submission"}])


def test_yaml_validation_duplicate_id():
    duplicate_rules = [
        {"id": "R01", "version": "1.0.0", "level": "submission", "description": "d", "rationale": "r", "threshold_basis": "b", "severity": "low", "sql": "SELECT 1"},
        {"id": "R01", "version": "1.0.0", "level": "submission", "description": "d2", "rationale": "r2", "threshold_basis": "b2", "severity": "high", "sql": "SELECT 1"},
    ]
    with pytest.raises(ValueError, match="Duplicate rule id detected"):
        validate_rules(duplicate_rules)


def test_honest_round_start_local_hours(tmp_path):
    """Test that in an honest round, all start_local hours fall within 09-17 BST."""
    p = run_generation("medium", 42, tmp_path / "data", round_num=1, no_fraud=True)
    df = pd.read_parquet(p)
    con = duckdb.connect(":memory:")
    con.register("_raw_submissions", df)
    view_sql_path = Path(__file__).resolve().parent.parent / "rules" / "submissions_view.sql"
    con.sql(view_sql_path.read_text(encoding="utf-8"))
    hours = con.sql("SELECT hour(start_local) AS hr FROM submissions").df()["hr"]
    assert hours.between(9, 17).all(), f"Found hours outside 9-17: min={hours.min()}, max={hours.max()}"


def test_guard_timestamps_end_with_dhaka_offset(tmp_path):
    """Guard rule: every start_time and end_time must end with '+06:00' (fails loudly otherwise)."""
    p = run_generation("medium", 42, tmp_path / "data", round_num=1, no_fraud=True)
    df = pd.read_parquet(p)
    assert df["start_time"].str.endswith("+06:00").all()
    assert df["end_time"].str.endswith("+06:00").all()

    # Fail loudly when offset differs
    df_bad_start = df.copy()
    df_bad_start.loc[0, "start_time"] = "2026-11-01T10:00:00Z"
    with pytest.raises(ValueError, match="Every start_time must end with '\\+06:00'"):
        run_rules(df_bad_start, _REF_VIL)

    df_bad_end = df.copy()
    df_bad_end.loc[0, "end_time"] = "2026-11-01T10:35:00+00:00"
    with pytest.raises(ValueError, match="Every end_time must end with '\\+06:00'"):
        run_rules(df_bad_end, _REF_VIL)


def _make_clean_row(**kwargs):
    row = {
        "submission_id": "sub_01",
        "round": 1,
        "enumerator_id": "enum_01",
        "upazila_code": "upz_01",
        "village_id": "vil_01",
        "start_time": "2026-11-01T10:00:00+06:00",
        "end_time": "2026-11-01T10:35:00+06:00",
        "duration_min": 35.0,
        "gps_lat": 24.5001,
        "gps_lon": 90.0001,
        "gps_accuracy": 12.0,
        "hh_size": 4,
        "head_age": 45,
        "roster_ages": [45, 40, 15, 12],
        "asset_mobile": 1,
        "asset_tv": 1,
        "asset_internet": 0,
        "asset_radio": 0,
        "asset_computer": 0,
    }
    row.update(kwargs)
    return row


_REF_VIL = pd.DataFrame([{"village_id": "vil_01", "upazila_code": "upz_01", "ref_lat": 24.5000, "ref_lon": 90.0000}])


@pytest.mark.parametrize(
    "rule_id,clean_overrides,violating_overrides,expected_val",
    [
        ("R01", {}, {"hh_size": 18}, 18.0),
        ("R02", {}, {"head_age": 12}, 12.0),
        ("R03", {}, {"roster_ages": [45, 40]}, -2.0),
        ("R04", {}, {"roster_ages": [45, 40, -3, 12]}, -3.0),
        ("R05", {}, {"duration_min": 6.5}, 6.5),
        ("R06", {}, {"duration_min": 195.0}, 195.0),
        ("R07", {}, {"start_time": "2026-11-01T05:00:00+06:00", "end_time": "2026-11-01T05:35:00+06:00"}, 5.0),
        ("R08", {}, {"gps_accuracy": 65.0}, 65.0),
        ("R09", {}, {"gps_lat": 24.5500, "gps_lon": 90.0000}, None),  # distance > 3000
        ("R10", {}, {"asset_mobile": -8, "asset_tv": -8, "asset_internet": -8}, 3.0),
    ],
)
def test_submission_rules_unit_fixtures(rule_id, clean_overrides, violating_overrides, expected_val):
    """Test 20 unit fixture cases for R01-R10 (1 clean and 1 violating row per rule)."""
    rules = [r for r in load_rules(Path(__file__).resolve().parent.parent / "rules" / "rules.yaml") if r["id"] == rule_id]

    # Clean row must produce zero hits
    df_clean = pd.DataFrame([_make_clean_row(**clean_overrides)])
    hits_clean = run_rules(df_clean, _REF_VIL, rules=rules)
    assert hits_clean.empty, f"Rule {rule_id} fired on clean fixture"

    # Violating row must produce exactly one hit
    df_viol = pd.DataFrame([_make_clean_row(**violating_overrides)])
    hits_viol = run_rules(df_viol, _REF_VIL, rules=rules)
    assert len(hits_viol) == 1, f"Rule {rule_id} did not fire on violating fixture"
    assert hits_viol.iloc[0]["rule_id"] == rule_id
    if expected_val is not None:
        assert hits_viol.iloc[0]["value"] == pytest.approx(expected_val)
    elif rule_id == "R09":
        assert hits_viol.iloc[0]["value"] > 3000.0


def test_r11_unit_fixtures():
    """Test 2 unit fixture cases for R11 (exact duplicate entry)."""
    rules = [r for r in load_rules(Path(__file__).resolve().parent.parent / "rules" / "rules.yaml") if r["id"] == "R11"]

    # Clean: distinct submissions
    df_clean = pd.DataFrame([
        _make_clean_row(submission_id="sub_01", hh_size=3, roster_ages=[45, 40, 15]),
        _make_clean_row(submission_id="sub_02", hh_size=4, roster_ages=[45, 40, 15, 12]),
    ])
    assert run_rules(df_clean, _REF_VIL, rules=rules).empty

    # Violating: duplicate submission by same enumerator
    df_viol = pd.DataFrame([
        _make_clean_row(submission_id="sub_01", enumerator_id="enum_01"),
        _make_clean_row(submission_id="sub_02", enumerator_id="enum_01"),
    ])
    hits_viol = run_rules(df_viol, _REF_VIL, rules=rules)
    assert len(hits_viol) == 2
    assert (hits_viol["rule_id"] == "R11").all()
    assert (hits_viol["value"] == 2.0).all()


def test_r12_unit_fixtures():
    """Test 2 unit fixture cases for R12 (infeasible daily volume > 12)."""
    rules = [r for r in load_rules(Path(__file__).resolve().parent.parent / "rules" / "rules.yaml") if r["id"] == "R12"]

    # Clean: 12 submissions on same date
    clean_rows = [_make_clean_row(submission_id=f"sub_{i:02d}") for i in range(12)]
    assert run_rules(pd.DataFrame(clean_rows), _REF_VIL, rules=rules).empty

    # Violating: 13 submissions on same date
    viol_rows = [_make_clean_row(submission_id=f"sub_{i:02d}") for i in range(13)]
    hits_viol = run_rules(pd.DataFrame(viol_rows), _REF_VIL, rules=rules)
    assert len(hits_viol) == 1
    assert hits_viol.iloc[0]["rule_id"] == "R12"
    assert hits_viol.iloc[0]["unit_id"] == "enum_01_2026-11-01"
    assert hits_viol.iloc[0]["value"] == 13.0


def test_honest_round_hit_counts(tmp_path):
    """Test hit counts on honest round (seed 42, no-fraud); expected ~0 for most rules."""
    p = run_generation("medium", 42, tmp_path / "data", round_num=1, no_fraud=True)
    vil_p = tmp_path / "data" / "reference" / "villages.parquet"
    rules = load_rules(Path(__file__).resolve().parent.parent / "rules" / "rules.yaml")
    hits = run_rules(p, vil_p, rules=rules)
    # Most rules must have 0 hits in honest round
    by_rule = hits["rule_id"].value_counts().to_dict() if not hits.empty else {}
    for r in ["R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09", "R10", "R11"]:
        assert by_rule.get(r, 0) == 0, f"Honest round unexpectedly flagged {r}: {by_rule.get(r)}"


def test_offset_free_timestamp_rule_hit_parity(tmp_path):
    """Verify Python rule hit counts for seeds 0..4 and demo scenarios match exact historical counts."""
    rules = load_rules(Path(__file__).resolve().parent.parent / "rules" / "rules.yaml")
    expected_seed_hits = {0: 23, 1: 25, 2: 3, 3: 1, 4: 60}
    for seed, exp_hits in expected_seed_hits.items():
        sub_p = run_generation("medium", seed, tmp_path / f"s{seed}", round_num=1, verbose=False)
        vil_p = tmp_path / f"s{seed}" / "reference" / "villages.parquet"
        hits = run_rules(sub_p, vil_p, rules=rules)
        assert len(hits) == exp_hits, f"Seed {seed} rule hits mismatch: {len(hits)} != {exp_hits}"

    data_dir = Path(__file__).resolve().parent.parent / "site" / "src" / "data"
    for sc, exp_hits in [("mixed", 22), ("low", 7)]:
        sub_p = data_dir / sc / f"{sc}_submissions.parquet"
        vil_p = data_dir / sc / f"{sc}_villages.parquet"
        if sub_p.is_file() and vil_p.is_file():
            hits = run_rules(sub_p, vil_p, rules=rules)
            assert len(hits) == exp_hits, f"Scenario {sc} rule hits mismatch: {len(hits)} != {exp_hits}"
