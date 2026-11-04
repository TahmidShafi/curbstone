"""Shared fixtures and evaluation helpers for curbstone tests."""

from pathlib import Path
import numpy as np
import pytest
import yaml


@pytest.fixture
def config():
    config_path = Path(__file__).resolve().parent.parent / "config" / "params.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def compute_anova_icc(y: np.ndarray, groups: np.ndarray) -> float:
    """One-way ANOVA ICC on binary/continuous indicators (excluding missing code -8)."""
    valid = (y != -8)
    y_v, g_v = y[valid].astype(float), groups[valid].astype(int)
    n_groups, n_total = len(np.unique(g_v)), len(y_v)
    if n_groups <= 1 or n_total <= n_groups:
        return 0.0
    grand_mean = np.mean(y_v)
    counts = np.bincount(g_v)[np.bincount(g_v) > 0]
    means = np.bincount(g_v, weights=y_v)[np.bincount(g_v) > 0] / counts
    ss_b = np.sum(counts * (means - grand_mean) ** 2)
    ss_w = np.sum((y_v - grand_mean) ** 2) - ss_b
    df_b, df_w = n_groups - 1, n_total - n_groups
    ms_b, ms_w = ss_b / df_b, ss_w / df_w
    n0 = (n_total - np.sum(counts ** 2) / n_total) / df_b
    denom = ms_b + (n0 - 1) * ms_w
    return float((ms_b - ms_w) / denom) if denom != 0.0 else 0.0

