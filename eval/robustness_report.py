"""Generate summary report, tables, and visualization figures for the robustness study."""

import argparse
from pathlib import Path
import sys
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from eval.robustness_common import ACTIVE_MODES, ALL_MODES


def paired_bootstrap_ci(
    diff: np.ndarray,
    n_resamples: int = 10000,
    seed: int = 42,
) -> Tuple[float, float, float]:
    """Compute mean and 95% percentile bootstrap CI for paired differences."""
    clean = diff[~np.isnan(diff)]
    if len(clean) == 0:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    n = len(clean)
    boot_means = np.mean(rng.choice(clean, size=(n_resamples, n), replace=True), axis=1)
    return float(np.mean(clean)), float(np.percentile(boot_means, 2.5)), float(np.percentile(boot_means, 97.5))


def generate_precision_table(df_grid: pd.DataFrame) -> Tuple[pd.DataFrame, str]:
    """Table 1: Precision@k by workload x prevalence."""
    rows = []
    wl_order = ["low", "mixed", "high"]
    prev_order = [0.02, 0.05, 0.10, 0.20]

    for wl in wl_order:
        for p in prev_order:
            sub = df_grid[(df_grid["workload_name"] == wl) & (df_grid["prevalence"] == p)]
            rows.append({
                "Workload": wl.capitalize(),
                "Prevalence": f"{p:.2f}",
                "Scoring v3 (Mean)": f"{sub['v3_precision_k'].mean():.4f}",
                "v3 10th-90th": f"[{sub['v3_precision_k'].quantile(0.10):.4f}, {sub['v3_precision_k'].quantile(0.90):.4f}]",
                "No-Shrinkage (Mean)": f"{sub['noshrink_precision_k'].mean():.4f}",
                "Rules Baseline (Mean)": f"{sub['rules_precision_k'].mean():.4f}",
            })
    df_res = pd.DataFrame(rows)
    return df_res, df_res.to_markdown(index=False)


def generate_recall_table(df_grid: pd.DataFrame, df_holdout: pd.DataFrame) -> Tuple[pd.DataFrame, str]:
    """Table 2: Per-mode Recall@k including held-out partial_section."""
    rows = []
    # Standard 5 modes on grid
    for mod in ACTIVE_MODES:
        col = f"v3_recall_{mod}"
        col_ns = f"noshrink_recall_{mod}"
        col_ru = f"rules_recall_{mod}"
        n_eval = int(df_grid[col].dropna().count())
        rows.append({
            "Mode": mod,
            "Type": "Standard Active",
            "Evaluated Rounds": n_eval,
            "Scoring v3 Recall@k": f"{df_grid[col].mean():.4f}",
            "No-Shrinkage Recall@k": f"{df_grid[col_ns].mean():.4f}",
            "Rules Baseline Recall@k": f"{df_grid[col_ru].mean():.4f}",
        })

    # Held-out partial_section on holdout study
    for mod in ["partial_section"]:
        col = f"v3_recall_{mod}"
        col_ns = f"noshrink_recall_{mod}"
        col_ru = f"rules_recall_{mod}"
        n_eval = int(df_holdout[col].dropna().count()) if col in df_holdout else 0
        rows.append({
            "Mode": mod,
            "Type": "Held-Out (Out-of-Distribution)",
            "Evaluated Rounds": n_eval,
            "Scoring v3 Recall@k": f"{df_holdout[col].mean():.4f}" if col in df_holdout else "N/A",
            "No-Shrinkage Recall@k": f"{df_holdout[col_ns].mean():.4f}" if col_ns in df_holdout else "N/A",
            "Rules Baseline Recall@k": f"{df_holdout[col_ru].mean():.4f}" if col_ru in df_holdout else "N/A",
        })

    df_res = pd.DataFrame(rows)
    return df_res, df_res.to_markdown(index=False)


def generate_bootstrap_table(df_grid: pd.DataFrame) -> Tuple[pd.DataFrame, str]:
    """Table 3: Paired bootstrap CIs for differences in Precision@k and Average Precision."""
    rows = []

    # 1. Precision@k differences pooled within workload profiles and overall
    subsets = [
        ("Low Workload [5, 15]", df_grid[df_grid["workload_name"] == "low"]),
        ("Mixed Workload [5, 60]", df_grid[df_grid["workload_name"] == "mixed"]),
        ("High Workload [40, 60]", df_grid[df_grid["workload_name"] == "high"]),
        ("Overall (All 72 Configs)", df_grid),
    ]

    for label, sub in subsets:
        diff_ru = sub["v3_precision_k"].values - sub["rules_precision_k"].values
        diff_ns = sub["v3_precision_k"].values - sub["noshrink_precision_k"].values

        m_ru, lo_ru, hi_ru = paired_bootstrap_ci(diff_ru)
        m_ns, lo_ns, hi_ns = paired_bootstrap_ci(diff_ns)

        rows.append({
            "Metric / Subset": f"Precision@4 ({label})",
            "v3 - Rules (Mean [95% CI])": f"{m_ru:+.4f} [{lo_ru:+.4f}, {hi_ru:+.4f}]",
            "v3 - No-Shrinkage (Mean [95% CI])": f"{m_ns:+.4f} [{lo_ns:+.4f}, {hi_ns:+.4f}]",
        })

    # 2. Average Precision (PR-AUC) differences: overall and per mode
    diff_ap_ru = df_grid["v3_ap"].values - df_grid["rules_ap"].values
    diff_ap_ns = df_grid["v3_ap"].values - df_grid["noshrink_ap"].values
    m_ru, lo_ru, hi_ru = paired_bootstrap_ci(diff_ap_ru)
    m_ns, lo_ns, hi_ns = paired_bootstrap_ci(diff_ap_ns)

    rows.append({
        "Metric / Subset": "Average Precision (Overall)",
        "v3 - Rules (Mean [95% CI])": f"{m_ru:+.4f} [{lo_ru:+.4f}, {hi_ru:+.4f}]",
        "v3 - No-Shrinkage (Mean [95% CI])": f"{m_ns:+.4f} [{lo_ns:+.4f}, {hi_ns:+.4f}]",
    })

    for mod in ACTIVE_MODES:
        col_v3, col_ns, col_ru = f"v3_ap_{mod}", f"noshrink_ap_{mod}", f"rules_ap_{mod}"
        d_ru = df_grid[col_v3].values - df_grid[col_ru].values
        d_ns = df_grid[col_v3].values - df_grid[col_ns].values
        m_ru, lo_ru, hi_ru = paired_bootstrap_ci(d_ru)
        m_ns, lo_ns, hi_ns = paired_bootstrap_ci(d_ns)
        rows.append({
            "Metric / Subset": f"Average Precision (Mode: {mod})",
            "v3 - Rules (Mean [95% CI])": f"{m_ru:+.4f} [{lo_ru:+.4f}, {hi_ru:+.4f}]",
            "v3 - No-Shrinkage (Mean [95% CI])": f"{m_ns:+.4f} [{lo_ns:+.4f}, {hi_ns:+.4f}]",
        })

    df_res = pd.DataFrame(rows)
    return df_res, df_res.to_markdown(index=False)


def plot_small_n_honest(df_grid: pd.DataFrame, out_path: Path) -> None:
    """Figure 1: Small-n honest top-k slots vs workload profile per method."""
    wl_order = ["low", "mixed", "high"]
    methods = [
        ("v3_small_honest", "Scoring v3", "#1f77b4"),
        ("noshrink_small_honest", "v3 (No Shrinkage)", "#ff7f0e"),
        ("rules_small_honest", "Rules Baseline", "#7f7f7f"),
    ]

    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(len(wl_order))
    width = 0.25

    for idx, (col, label, color) in enumerate(methods):
        totals = [int(df_grid[df_grid["workload_name"] == wl][col].sum()) for wl in wl_order]
        ax.bar(x + (idx - 1) * width, totals, width, label=label, color=color, alpha=0.9, edgecolor="black", linewidth=0.8)

    ax.set_xticks(x)
    ax.set_xticklabels(["Low [5, 15]", "Mixed [5, 60]", "High [40, 60]"], fontsize=11)
    ax.set_xlabel("Workload Profile", fontsize=12, fontweight="bold", labelpad=8)
    ax.set_ylabel("Total False-Flag Slots (n < 15 Honest)", fontsize=12, fontweight="bold", labelpad=8)
    ax.set_title("Small-Workload Honest Enumerators in Top-4 by Workload Profile", fontsize=13, fontweight="bold", pad=12)
    ax.legend(frameon=True, fontsize=10)
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    plt.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    print(f"Saved figure: {out_path}")


def plot_detection_by_day(df_det: pd.DataFrame, out_path: Path) -> None:
    """Figure 2: Detection share in top-k by working day per fraud mode."""
    days = [2, 4, 6, 8, 10]
    markers = ["o", "s", "^", "D", "v"]
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]

    fig, ax = plt.subplots(figsize=(8, 5))

    for idx, mod in enumerate(ACTIVE_MODES):
        col = f"v3_recall_{mod}"
        shares = []
        for d in days:
            sub = df_det[df_det["day"] == d]
            shares.append(float(sub[col].mean()) if col in sub and not sub[col].isna().all() else 0.0)

        ax.plot(days, shares, marker=markers[idx], color=colors[idx], linewidth=2.2, markersize=7, label=mod)

    ax.set_xticks(days)
    ax.set_xlabel("Working Day (Cumulative Fieldwork Progress)", fontsize=12, fontweight="bold", labelpad=8)
    ax.set_ylabel("Share of Fabricators in Top-4 (Recall@4)", fontsize=12, fontweight="bold", labelpad=8)
    ax.set_title("Fabricator Detection Rate over Time by Mode (Prevalence 0.10, k=4)", fontsize=13, fontweight="bold", pad=12)
    ax.set_ylim(-0.05, 1.05)
    ax.legend(frameon=True, fontsize=10, loc="lower right")
    ax.grid(True, linestyle="--", alpha=0.5)

    plt.tight_layout()
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    print(f"Saved figure: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate robustness report and figures from results.parquet.")
    parser.add_argument("--results", type=str, default="outputs/robustness/results.parquet", help="Path to results.parquet")
    parser.add_argument("--out-dir", type=str, default="outputs/robustness", help="Output directory for reports and figures")
    args = parser.parse_args()

    res_path = Path(args.results)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not res_path.exists():
        raise FileNotFoundError(f"Results file not found: {res_path}. Run eval/robustness.py first.")

    df = pd.read_parquet(res_path)
    df_grid = df[df["study"] == "grid"].copy()
    df_holdout = df[df["study"] == "holdout"].copy()
    df_det = df[df["study"] == "detection_time"].copy()

    # Generate tables
    _, tbl1 = generate_precision_table(df_grid)
    _, tbl2 = generate_recall_table(df_grid, df_holdout)
    _, tbl3 = generate_bootstrap_table(df_grid)

    # Generate figures
    fig1_path = out_dir / "small_n_honest.png"
    fig2_path = out_dir / "detection_by_day.png"
    plot_small_n_honest(df_grid, fig1_path)
    plot_detection_by_day(df_det, fig2_path)

    # Write summary.md
    summary_path = out_dir / "summary.md"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("# Robustness Study Summary (Frozen Engine Scoring v3)\n\n")
        f.write("Full evaluation across 72 factorial configurations (1,440 rounds, seeds 1000..1019), ")
        f.write("held-out mode evaluation (seeds 2000..2019), and detection-time evaluation (seeds 3000..3019).\n\n")
        f.write("## 1. Precision@k by Workload Profile and Fraud Prevalence\n\n")
        f.write(tbl1 + "\n\n")
        f.write("## 2. Per-Mode Recall@k (including Held-Out `partial_section`)\n\n")
        f.write(tbl2 + "\n\n")
        f.write("## 3. Statistical Significance and Bootstrap Confidence Intervals\n\n")
        f.write(tbl3 + "\n\n")
        f.write("## 4. Figures\n\n")
        f.write(f"- Figure 1: Small-workload honest false-flag counts: ![{fig1_path.name}]({fig1_path.name})\n")
        f.write(f"- Figure 2: Fabricator detection rate over time: ![{fig2_path.name}]({fig2_path.name})\n")

    print(f"Summary written to {summary_path}")


if __name__ == "__main__":
    main()
