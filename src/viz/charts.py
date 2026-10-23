"""Report charts in one style (PRD FR-9.3; Tasks P8.2).

PNG, 300 dpi, ``outputs/figures/chart_*.png``:

- ``chart_k_scan``: inertia, silhouette and Davies-Bouldin for k = 3..10 (K-Means vs GMM);
- ``chart_cluster_profiles``: cluster means as z-scores (diverging), raw values printed,
  each row named with the class its rule gave;
- ``chart_class_areas``: area of each class, validation (2018) vs final (2023) run;
- ``chart_rf_importance``: rf_change permutation and impurity importance;
- ``chart_roc``: temporal ROC (validation run, ``grew``) of rf_change, rf_state, MCDA and
  distance-to-built, with the random diagonal;
- ``chart_sensitivity``: AUC by slope threshold and by cell size;
- ``chart_holdout``: held-out building check, AUC per scorer.

- ``chart_toc``, ``chart_growth_type``, ``chart_ablation``: from ``validation.json`` (P7.4).

Run: python -m src.viz.charts
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import roc_auc_score, roc_curve  # noqa: E402

from src.classify.label import c7_path  # noqa: E402
from src.config import load_config  # noqa: E402
from src.features import schema  # noqa: E402
from src.io_utils import setup_logging  # noqa: E402
from src.similarity.rf_model import scores_path  # noqa: E402
from src.viz import style  # noqa: E402

log = logging.getLogger(__name__)

# fixed series identity across every chart (colour follows the model, never its rank)
MODEL_STYLE = {
    "suitability": ("Combined score", style.SERIES[5]),
    "rf_change": ("Change RF", style.SERIES[0]),
    "similarity_knn": ("Building similarity", style.SERIES[4]),
    "dist_to_built": ("Distance to built-up", style.SERIES[1]),
    "rf_state": ("State RF", style.SERIES[3]),
    "mcda": ("MCDA / AHP", style.SERIES[2]),
}


def _metrics(cfg, name: str) -> dict:
    return json.loads((Path(cfg.paths["metrics"]) / name).read_text())


def save(fig, cfg, name: str) -> Path:
    p = Path(cfg.paths["figures"]) / f"{name}.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(p, dpi=style.DPI)
    plt.close(fig)
    log.info("wrote %s", p.name)
    return p


def _title(fig, title: str, subtitle: str) -> None:
    """Title + subtitle in a fixed band above the axes (inches, so it never collides)."""
    h = fig.get_figheight()
    fig.tight_layout(rect=(0, 0, 1, 1 - 0.62 / h))
    fig.text(
        0.01,
        1 - 0.12 / h,
        title,
        ha="left",
        va="top",
        fontsize=12,
        fontweight="bold",
        color=style.INK,
    )
    fig.text(0.01, 1 - 0.36 / h, subtitle, ha="left", va="top", fontsize=8.5, color=style.INK_2)


def k_scan(cfg) -> Path:
    scan = pd.DataFrame(_metrics(cfg, "clustering.json")["final"]["scan"])
    k = int(cfg["clustering"]["k"])
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.2))
    panels = [
        ("inertia", "Inertia (K-Means)", ["kmeans"]),
        ("silhouette", "Silhouette (higher is better)", ["kmeans", "gmm"]),
        ("davies_bouldin", "Davies-Bouldin (lower is better)", ["kmeans", "gmm"]),
    ]
    colors = {"kmeans": style.SERIES[0], "gmm": style.SERIES[1]}
    names = {"kmeans": "K-Means", "gmm": "GMM"}
    for ax, (col, title, methods) in zip(axes, panels, strict=True):
        for m in methods:
            d = scan.loc[scan["method"] == m].sort_values("k")
            ax.plot(d["k"], d[col], color=colors[m], marker="o", markersize=4, label=names[m])
        ax.axvline(k, color=style.INK_MUTED, lw=1, ls="--")
        ax.set_title(title, fontsize=9.5)
        ax.set_xlabel("k")
        ax.set_xticks(range(int(cfg["clustering"]["k_min"]), int(cfg["clustering"]["k_max"]) + 1))
    axes[1].legend(loc="lower left", fontsize=8)
    axes[0].text(
        k + 0.1, axes[0].get_ylim()[1], f"chosen k = {k}", color=style.INK_2, fontsize=7.5, va="top"
    )
    _title(
        fig,
        "Choosing the number of clusters",
        f"Final run ({cfg['years']['latest']} features); silhouette on a 10,000-cell sample",
    )
    return save(fig, cfg, "chart_k_scan")


def cluster_profiles(cfg) -> Path:
    rules = pd.read_csv(Path(cfg.paths["metrics"]) / "class_rules_final.csv", index_col=0)
    cols = list(cfg["clustering"]["inputs"])
    c4 = schema.read_contract(schema.contract_path(cfg, "C4", year=cfg["years"]["latest"]), "C4")
    z = (rules[cols] - c4[cols].mean()) / c4[cols].std()
    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    im = ax.imshow(z.to_numpy(), cmap=style.DIVERGING, vmin=-3, vmax=3, aspect="auto")
    ax.grid(False)
    labels = {
        "frac_water": "water",
        "frac_tree": "trees",
        "frac_crop": "crops",
        "frac_built": "built",
        "frac_range": "rangeland",
        "elev_mean": "elevation",
        "slope_mean": "slope",
    }
    ax.set_xticks(range(len(cols)), [labels.get(c, c) for c in cols])
    ax.set_yticks(
        range(len(rules)), [f"{i}: {r.class_name} ({r.share:.0%})" for i, r in rules.iterrows()]
    )
    for i in range(len(rules)):
        for j, c in enumerate(cols):
            v = rules.iloc[i][c]
            txt = (
                f"{v:.2f}"
                if c.startswith("frac")
                else f"{v:.0f}" if c == "elev_mean" else f"{v:.1f}°"
            )
            ax.text(
                j,
                i,
                txt,
                ha="center",
                va="center",
                fontsize=7.5,
                color=style.INK if abs(z.iloc[i, j]) < 2 else style.SURFACE,
            )
    cb = fig.colorbar(im, ax=ax, shrink=0.85, pad=0.02)
    cb.set_label("z-score vs all cells", color=style.INK_2)
    cb.outline.set_visible(False)
    ax.spines[:].set_visible(False)
    _title(
        fig,
        "What each cluster is",
        "Cluster means (printed) and their z-scores; rows name the class the centroid rule gave",
    )
    return save(fig, cfg, "chart_cluster_profiles")


def class_areas(cfg) -> Path:
    cell_km2 = (cfg.cell_size_m / 1000) ** 2
    rows = []
    for run in ("validation", "final"):
        c7 = pd.read_parquet(c7_path(cfg, run))
        for code, n in c7["class_3"].value_counts().items():
            rows.append({"run": run, "class": style.CLASS_NAMES[code], "km2": n * cell_km2})
    d = (
        pd.DataFrame(rows)
        .pivot(index="class", columns="run", values="km2")
        .reindex(list(style.CLASS_NAMES.values()))
    )
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    y = np.arange(len(d))
    h = 0.36
    for i, (run, color) in enumerate((("validation", style.SERIES[0]), ("final", style.SERIES[1]))):
        yr = cfg["years"]["baseline"] if run == "validation" else cfg["years"]["latest"]
        bars = ax.barh(
            y + (i - 0.5) * (h + 0.04),
            d[run],
            height=h,
            color=color,
            label=f"{yr} ({run} run)",
            edgecolor=style.SURFACE,
            linewidth=1,
        )
        ax.bar_label(bars, fmt="%.0f", padding=3, fontsize=7.5, color=style.INK_2)
    ax.set_yticks(y, d.index)
    ax.invert_yaxis()
    ax.set_xlabel("area (km²)")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", fontsize=8)
    _title(fig, "Class areas", f"Three-class map, {len(c7):,} cells of {cfg.cell_size_m:.0f} m")
    return save(fig, cfg, "chart_class_areas")


def rf_importance(cfg) -> Path:
    imp = pd.DataFrame(_metrics(cfg, "similarity.json")["rf_change"]["importance"]).set_index(
        "feature"
    )
    fig, axes = plt.subplots(1, 2, figsize=(9, 5), sharey=True)
    order = imp.sort_values("permutation_auc_drop").index
    for ax, col, title in (
        (axes[0], "permutation_auc_drop", "Permutation: AUC drop on held-out folds"),
        (axes[1], "impurity", "Impurity (mean decrease, final model)"),
    ):
        ax.barh(
            range(len(order)),
            imp.loc[order, col],
            color=style.SERIES[0],
            height=0.7,
            edgecolor=style.SURFACE,
        )
        ax.set_title(title, fontsize=9.5)
        ax.grid(axis="y", visible=False)
        ax.axvline(0, color=style.INK_MUTED, lw=0.8)
    axes[0].set_yticks(range(len(order)), order)
    _title(
        fig,
        "What the change RF relies on",
        "rf_change, trained on 2018 surroundings of cells built by 2020/21",
    )
    return save(fig, cfg, "chart_rf_importance")


def roc(cfg) -> Path:
    lab = schema.read_contract(schema.contract_path(cfg, "C5"), "C5").set_index("cell_id")
    cand = lab.index[lab["candidate"] & ~lab["ambiguous"]]
    y = lab.loc[cand, "grew"].to_numpy().astype(int)
    c4 = schema.read_contract(
        schema.contract_path(cfg, "C4", year=cfg["years"]["baseline"]), "C4"
    ).set_index("cell_id")
    scores = {"dist_to_built": -c4.loc[cand, "log_dist_built"].to_numpy()}
    for m in MODEL_STYLE:
        p = scores_path(cfg, m, "validation")
        if m != "dist_to_built" and p.exists():
            scores[m] = pd.read_parquet(p).set_index("cell_id").loc[cand, "score"].to_numpy()
    fig, ax = plt.subplots(figsize=(5.2, 5))
    ax.plot([0, 1], [0, 1], color=style.INK_MUTED, lw=1, ls="--")
    ax.text(0.62, 0.55, "random", color=style.INK_MUTED, fontsize=8, rotation=40)
    for m in (m for m in MODEL_STYLE if m in scores):
        fpr, tpr, _ = roc_curve(y, scores[m])
        name, color = MODEL_STYLE[m]
        ax.plot(fpr, tpr, color=color, label=f"{name} (AUC {roc_auc_score(y, scores[m]):.3f})")
    ax.set_xlabel("false positive rate")
    ax.set_ylabel("true positive rate")
    ax.set_aspect("equal")
    ax.legend(loc="lower right", fontsize=8)
    _title(
        fig,
        "Predicting growth from 2018",
        f"{len(y):,} candidate cells, {y.sum():,} grew by 2022/23; RF scores out of fold",
    )
    return save(fig, cfg, "chart_roc")


def sensitivity(cfg) -> Path:
    s = _metrics(cfg, "sensitivity.json")
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.4), sharey=True)
    for ax, (exp, key, xlabel) in zip(
        axes,
        (
            ("slope", "slope_max_deg", "slope threshold (°)"),
            ("cell", "cell_size_m", "cell size (m)"),
        ),
        strict=True,
    ):
        d = pd.DataFrame(s[exp]).sort_values(key)
        for m in ("rf_change", "dist_to_built", "mcda"):
            name, color = MODEL_STYLE[m]
            ax.plot(d[key], d[f"auc_{m}"], color=color, marker="o", markersize=5, label=name)
        ax.set_xticks(d[key])
        ax.set_xlabel(xlabel)
    axes[0].set_ylabel("temporal AUC")
    axes[1].legend(loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=8)
    _title(
        fig,
        "Sensitivity of the results",
        "AUC changes little with the slope threshold or the cell size; "
        "the ranking holds everywhere",
    )
    return save(fig, cfg, "chart_sensitivity")


def holdout(cfg) -> Path:
    h = _metrics(cfg, "similarity.json")["holdout"]["validation"]["scorers"]
    names = {
        "rf": "Random forest",
        "knn": "kNN, all inputs",
        "knn_ring500": "kNN, 500 m rings only",
        "dist_to_built": "Distance to built-up",
    }
    d = pd.Series({names[k]: v["auc"] for k, v in h.items()}).sort_values()
    fig, ax = plt.subplots(figsize=(6.5, 2.6))
    bars = ax.barh(
        d.index, d.to_numpy(), color=style.SERIES[0], height=0.6, edgecolor=style.SURFACE
    )
    ax.bar_label(bars, fmt="%.3f", padding=3, fontsize=8, color=style.INK_2)
    ax.set_xlim(0.5, 1.0)
    ax.set_xlabel("AUC, held-out reference cells vs other cells (0.5 = chance)")
    ax.grid(axis="y", visible=False)
    _title(
        fig,
        "Do surroundings find buildings in unseen areas?",
        "5 spatial folds of 2 km blocks, validation run (2018)",
    )
    return save(fig, cfg, "chart_holdout")


def _validation(cfg) -> dict:
    return _metrics(cfg, "validation.json")


def toc(cfg) -> Path:
    v = _validation(cfg)
    ev = v["eval_set"]
    fig, ax = plt.subplots(figsize=(5.4, 5))
    ax.plot([0, 1], [0, 1], color=style.INK_MUTED, lw=1, ls="--")
    ax.text(0.55, 0.47, "random", color=style.INK_MUTED, fontsize=8, rotation=40)
    p = ev["prevalence"]
    ax.plot([0, p, 1], [0, 1, 1], color=style.INK_MUTED, lw=1, ls=":")
    ax.text(p + 0.01, 0.9, "perfect", color=style.INK_MUTED, fontsize=8)
    for m, (name, color) in MODEL_STYLE.items():
        if m in v["toc"]:
            t = v["toc"][m]
            ax.plot(t["flagged"], t["hits"], color=color, label=f"{name}")
    ax.set_xlabel("share of candidate cells flagged")
    ax.set_ylabel("share of growth found")
    ax.set_aspect("equal")
    ax.legend(loc="lower right", fontsize=8)
    _title(
        fig,
        "Total operating characteristic",
        f"{ev['n_cells']:,} candidate cells, {ev['n_grew']:,} grew by 2022/23",
    )
    return save(fig, cfg, "chart_toc")


def growth_type(cfg) -> Path:
    v = _validation(cfg)["models"]
    names = [m for m in MODEL_STYLE if m in v] + ["random"]
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    y = np.arange(len(names))
    h = 0.36
    for i, (key, label, color) in enumerate(
        (
            ("auc_adjacent", "next to existing built-up (adjacent)", style.SERIES[0]),
            ("auc_outlying", "away from it (outlying)", style.SERIES[1]),
        )
    ):
        vals = [v[m][key] for m in names]
        bars = ax.barh(
            y + (i - 0.5) * (h + 0.04),
            vals,
            height=h,
            color=color,
            label=label,
            edgecolor=style.SURFACE,
        )
        ax.bar_label(bars, fmt="%.2f", padding=3, fontsize=7.5, color=style.INK_2)
    ax.set_yticks(y, [MODEL_STYLE[m][0] if m in MODEL_STYLE else "Random" for m in names])
    ax.invert_yaxis()
    ax.axvline(0.5, color=style.INK_MUTED, lw=1, ls="--")
    ax.set_xlim(0.3, 0.9)
    ax.set_xlabel("AUC on growth of that type (0.5 = chance)")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", fontsize=8)
    ev = _validation(cfg)["eval_set"]
    _title(
        fig,
        "Growth type matters",
        f"{ev['n_adjacent']:,} adjacent and {ev['n_outlying']:,} outlying grown cells"
        " (landscape expansion index)",
    )
    return save(fig, cfg, "chart_growth_type")


def ablation_chart(cfg) -> Path | None:
    a = _validation(cfg).get("ablation")
    if not a:
        return None
    groups = list(a["drop"])
    labels = {
        "lulc_context": "land cover nearby",
        "near_built": "built-up nearby",
        "roads": "roads",
        "terrain": "terrain",
        "water": "water",
    }
    fig, ax = plt.subplots(figsize=(7, 3.4))
    y = np.arange(len(groups))
    h = 0.36
    for i, m in enumerate(("rf_change", "similarity_knn")):
        vals = [a["drop"][g][m]["delta"] for g in groups]
        name, color = MODEL_STYLE[m]
        bars = ax.barh(
            y + (i - 0.5) * (h + 0.04),
            vals,
            height=h,
            color=color,
            label=name,
            edgecolor=style.SURFACE,
        )
        ax.bar_label(bars, fmt="%+.3f", padding=3, fontsize=7.5, color=style.INK_2)
    ax.set_yticks(y, [labels.get(g, g) for g in groups])
    ax.invert_yaxis()
    ax.axvline(0, color=style.INK_MUTED, lw=1)
    lo = min(
        0.0, *(a["drop"][g][m]["delta"] for g in groups for m in ("rf_change", "similarity_knn"))
    )
    hi = max(
        0.0, *(a["drop"][g][m]["delta"] for g in groups for m in ("rf_change", "similarity_knn"))
    )
    pad = 0.35 * (hi - lo)
    ax.set_xlim(lo - pad, hi + pad)  # room for the value labels
    ax.set_xlabel("change in AUC when the group is dropped")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower left", fontsize=8)
    _title(
        fig,
        "Which surroundings carry the signal",
        f"Full AUC: change RF {a['full']['rf_change']:.3f}, "
        f"similarity {a['full']['similarity_knn']:.3f}",
    )
    return save(fig, cfg, "chart_ablation")


def make_all(cfg) -> list[Path]:
    style.apply()
    figs = [k_scan, cluster_profiles, class_areas, rf_importance, roc, sensitivity, holdout]
    if (Path(cfg.paths["metrics"]) / "validation.json").exists():
        figs += [toc, growth_type, ablation_chart]
    out = []
    for f in figs:
        try:
            out.append(f(cfg))
        except FileNotFoundError as exc:  # an optional input (e.g. sensitivity.json) not built
            log.warning("%s skipped: %s", f.__name__, exc)
    return [p for p in out if p is not None]


def main() -> None:
    cfg = load_config()
    setup_logging(cfg, "viz")
    make_all(cfg)


if __name__ == "__main__":
    main()
