from pathlib import Path
import pytest
import yaml


@pytest.fixture
def params():
    config_path = Path(__file__).resolve().parent.parent / "config" / "params.yaml"
    assert config_path.exists(), f"Configuration file not found at {config_path}"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_required_top_level_keys(params):
    required_keys = {
        "seed",
        "geography",
        "village_effects",
        "household",
        "enumerators",
        "interview",
        "gps",
        "fraud",
    }
    assert required_keys.issubset(params.keys())


def test_geography_keys(params):
    geo = params["geography"]
    assert "n_upazilas" in geo
    assert "villages_per_upazila" in geo
    assert "households_per_village" in geo
    assert len(geo["households_per_village"]) == 2
    assert geo["households_per_village"][0] <= geo["households_per_village"][1]


def test_village_effects_keys(params):
    ve = params["village_effects"]
    assert "icc_levels" in ve
    icc = ve["icc_levels"]
    for level in ("low", "medium", "high"):
        assert level in icc


def test_household_keys(params):
    hh = params["household"]
    assert "hh_size" in hh
    assert "dist" in hh["hh_size"]
    assert "mean" in hh["hh_size"]
    assert "assets" in hh
    assert isinstance(hh["assets"], list)
    for asset in hh["assets"]:
        assert "name" in asset
        assert "base_prob" in asset


def test_enumerators_keys(params):
    enum = params["enumerators"]
    required_keys = {
        "n_enumerators",
        "villages_per_enumerator",
        "workload",
        "speed_sd",
        "care_sd",
    }
    assert required_keys.issubset(enum.keys())
    assert len(enum["villages_per_enumerator"]) == 2
    assert enum["villages_per_enumerator"][0] <= enum["villages_per_enumerator"][1]
    assert len(enum["workload"]) == 2
    assert enum["workload"][0] <= enum["workload"][1]


def test_interview_keys(params):
    interview = params["interview"]
    assert "duration_lognormal" in interview
    assert "mu" in interview["duration_lognormal"]
    assert "sigma" in interview["duration_lognormal"]
    assert "per_member_minutes" in interview
    assert "work_hours" in interview
    assert len(interview["work_hours"]) == 2
    assert interview["work_hours"][0] <= interview["work_hours"][1]


def test_gps_keys(params):
    gps = params["gps"]
    assert "scatter_m" in gps


def test_fraud_keys(params):
    fraud = params["fraud"]
    assert "prevalence" in fraud
    assert "share_range" in fraud
    assert len(fraud["share_range"]) == 2
    assert fraud["share_range"][0] <= fraud["share_range"][1]
    assert "modes" in fraud
    expected_modes = {
        "copy_paste",
        "straight_lining",
        "rushed",
        "invented_gps",
        "too_average",
    }
    assert expected_modes.issubset(fraud["modes"].keys())
    for mode_name in expected_modes:
        assert "intensity" in fraud["modes"][mode_name]
    assert "holdout_mode" in fraud


def test_probabilities_in_range(params):
    # Check asset probabilities
    for asset in params["household"]["assets"]:
        prob = asset["base_prob"]
        assert 0.0 <= prob <= 1.0, f"Asset base_prob {prob} out of [0, 1] for {asset.get('name')}"

    # Check ICC levels
    for level, icc in params["village_effects"]["icc_levels"].items():
        assert 0.0 <= icc <= 1.0, f"ICC level {level} ({icc}) out of [0, 1]"

    # Check fraud prevalence and share_range
    prevalence = params["fraud"]["prevalence"]
    assert 0.0 <= prevalence <= 1.0, f"Fraud prevalence {prevalence} out of [0, 1]"

    share_min, share_max = params["fraud"]["share_range"]
    assert 0.0 <= share_min <= 1.0, f"Fraud share_range min {share_min} out of [0, 1]"
    assert 0.0 <= share_max <= 1.0, f"Fraud share_range max {share_max} out of [0, 1]"

    # Check fraud mode intensities
    for mode, conf in params["fraud"]["modes"].items():
        intensity = conf["intensity"]
        assert 0.0 <= intensity <= 1.0, f"Fraud intensity {intensity} for {mode} out of [0, 1]"

