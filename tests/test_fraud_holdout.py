"""Tests for held-out fraud mode partial_section (R1, R2, and mode rotation)."""

import numpy as np
from generator.geography import build_geography
from generator.enumerators import build_enumerators
from generator.interviews import generate_submissions_for_round
from generator.fraud import select_fabricators


def test_partial_section_r1_and_r2(config):
    """R1 & R2 for held-out mode partial_section: only roster_ages altered, len equals hh_size, honest records byte-identical."""
    seed = 42
    seq = np.random.SeedSequence(seed)
    h_seq, f_seq = seq.spawn(2)
    geo = build_geography(config, np.random.default_rng(h_seq))
    enums = build_enumerators(config, list(geo.villages.keys()), np.random.default_rng(h_seq))

    df_h, _ = generate_submissions_for_round(
        config, geo, enums, "medium", 1, np.random.default_rng(h_seq), enable_fraud=False
    )
    df_f, meta_f = generate_submissions_for_round(
        config, geo, enums, "medium", 1, np.random.default_rng(h_seq),
        fraud_rng=np.random.default_rng(f_seq), enable_fraud=True, include_holdout=True, prevalence=0.20
    )

    # R2: Honest enumerators byte-identical
    fab_enums = set(meta_f["fabricator_profiles"].keys())
    honest_enums = set(df_f["enumerator_id"]) - fab_enums
    df_on_h = df_f[df_f["enumerator_id"].isin(honest_enums)].reset_index(drop=True)
    df_off_h = df_h[df_h["enumerator_id"].isin(honest_enums)].reset_index(drop=True)
    assert df_on_h.equals(df_off_h), "Honest records must be byte-identical when include_holdout=True"

    # R1: partial_section alters ONLY roster_ages
    labels = meta_f["labels_submission"]
    ps_idx = labels[labels["fraud_mode"] == "partial_section"].index
    assert len(ps_idx) > 0, "partial_section must be assigned in prevalence 0.20 with holdout enabled"

    for idx in ps_idx:
        row_f = df_f.loc[idx]
        row_h = df_h.loc[idx]
        for col in df_f.columns:
            if col == "roster_ages":
                assert len(row_f[col]) == row_f["hh_size"]
            else:
                assert row_f[col] == row_h[col], f"partial_section altered disallowed col {col}"


def test_partial_section_only_when_requested(config):
    """partial_section appears in rotation ONLY when include_holdout=True."""
    fake_enums = {f"enum_{i:02d}": None for i in range(40)}

    rng = np.random.default_rng(123)
    for _ in range(50):
        profs = select_fabricators(fake_enums, prevalence=0.20, share_range=[0.3, 0.9], fraud_cfg=config["fraud"], fraud_rng=rng, include_holdout=False)
        assert "partial_section" not in [p.primary_mode for p in profs.values()]

    profs_h = select_fabricators(fake_enums, prevalence=0.20, share_range=[0.3, 0.9], fraud_cfg=config["fraud"], fraud_rng=rng, include_holdout=True)
    assert "partial_section" in [p.primary_mode for p in profs_h.values()]

