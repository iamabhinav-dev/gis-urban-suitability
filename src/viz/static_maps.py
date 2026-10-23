"""Static maps in one style (PRD FR-9.1; Tasks P8.1).

Every map has a title, a legend or colour bar, a scale bar, a north arrow, the AOI outline
and a light basemap (Esri World Gray Canvas via contextily; CARTO now needs an API key;
tiles cached under ``data/raw/tiles``; if tiles can't be fetched the map is drawn without
one and a warning is logged). Saved as PNG at 300 dpi in ``outputs/figures/map_*.png``.

Maps: ESRI land cover (baseline and latest year), the 3-class map (both runs), key
features, the validation labels, every model score (validation and final run), and,
when Phase 7 has produced them, the suitability classes and the candidate patches.

Run: python -m src.viz.static_maps [--no-basemap]
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402
from matplotlib.axes import Axes  # noqa: E402
from matplotlib.colors import BoundaryNorm, ListedColormap  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib_scalebar.scalebar import ScaleBar  # noqa: E402

from src.classify.label import c7_path  # noqa: E402
from src.config import load_config  # noqa: E402
from src.features import schema  # noqa: E402
from src.features.grid import lattice  # noqa: E402
from src.io_utils import setup_logging  # noqa: E402
from src.preprocess.raster import load_reference_grid, processed_dir  # noqa: E402
from src.similarity.rf_model import scores_path  # noqa: E402
from src.viz import style  # noqa: E402

log = logging.getLogger(__name__)

BASEMAP = True


def figures_dir(cfg) -> Path:
    p = Path(cfg.paths["figures"])
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------- frame


def _basemap(cfg, ax) -> None:
    if not BASEMAP:
        return
    try:
        import contextily as cx

        cx.set_cache_dir(str(Path(cfg.paths["data_raw"]) / "tiles"))
        cx.add_basemap(
            ax, crs=cfg.crs, source=cx.providers.Esri.WorldGrayCanvas, attribution_size=5, zorder=0
        )
    except Exception as exc:  # network / tile server
        log.warning("basemap skipped: %s", exc)


def base_map(cfg, title: str, subtitle: str | None = None) -> tuple[Figure, Axes]:
    """Figure + axes framed on the AOI, with basemap, outline, scale bar and north arrow."""
    style.apply()
    fig, ax = plt.subplots(figsize=(6.4, 6.4))
    aoi = cfg.aoi_projected
    x0, y0, x1, y1 = aoi.total_bounds
    pad = 0.02 * max(x1 - x0, y1 - y0)
    ax.set_xlim(x0 - pad, x1 + pad)
    ax.set_ylim(y0 - pad, y1 + pad)
    ax.set_aspect("equal")
    _basemap(cfg, ax)
    ax.set_xlim(x0 - pad, x1 + pad)
    ax.set_ylim(y0 - pad, y1 + pad)
    ax.set_axis_off()
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold", color=style.INK, pad=14)
    if subtitle:
        ax.text(
            0, 1.005, subtitle, transform=ax.transAxes, fontsize=8, color=style.INK_2, va="bottom"
        )
    ax.add_artist(
        ScaleBar(
            1,
            "m",
            location="upper left",
            frameon=True,
            box_alpha=0.8,
            color=style.INK,
            font_properties={"size": 7},
        )
    )
    ax.annotate(
        "N",
        xy=(0.95, 0.96),
        xytext=(0.95, 0.86),
        xycoords="axes fraction",
        ha="center",
        va="center",
        fontsize=9,
        fontweight="bold",
        color=style.INK,
        arrowprops={"arrowstyle": "-|>", "color": style.INK, "lw": 1.2},
    )
    return fig, ax


def _outline(cfg, ax) -> None:
    cfg.aoi_projected.boundary.plot(ax=ax, color=style.INK, linewidth=0.8, zorder=5)


def lattice_extent(cfg) -> tuple[float, float, float, float]:
    """Map extent (left, right, bottom, top) of the cell lattice."""
    lat = lattice(cfg)
    return (
        lat.left,
        lat.left + lat.shape[1] * lat.cell_m,
        lat.top - lat.shape[0] * lat.cell_m,
        lat.top,
    )


def cell_image(cfg, cell_ids, values) -> np.ndarray:
    """Values of ``cell_ids`` on the cell lattice (NaN elsewhere)."""
    lat = lattice(cfg)
    grid = schema.read_contract(schema.contract_path(cfg, "C1"), "C1").set_index("cell_id")
    g = grid.loc[np.asarray(cell_ids)]
    img = np.full(lat.shape, np.nan)
    img[g["row"].to_numpy(), g["col"].to_numpy()] = np.asarray(values, dtype="float64")
    return img


def save(fig, cfg, name: str) -> Path:
    p = figures_dir(cfg) / f"{name}.png"
    fig.savefig(p, dpi=style.DPI)
    plt.close(fig)
    log.info("wrote %s", p.name)
    return p


def _categorical(ax, img, codes: dict[int, tuple[str, str]], extent, legend_title: str, alpha=1.0):
    keys = sorted(codes)
    lut = {k: i for i, k in enumerate(keys)}
    idx = np.full(img.shape, np.nan)
    for k in keys:
        idx[img == k] = lut[k]
    cmap = ListedColormap([codes[k][1] for k in keys])
    ax.imshow(
        idx,
        extent=extent,
        cmap=cmap,
        norm=BoundaryNorm(np.arange(len(keys) + 1) - 0.5, len(keys)),
        interpolation="nearest",
        zorder=2,
        alpha=alpha,
    )
    present = [k for k in keys if (img == k).any()]
    handles = [Patch(facecolor=codes[k][1], edgecolor="none", label=codes[k][0]) for k in present]
    ax.legend(
        handles=handles,
        title=legend_title,
        loc="upper left",
        bbox_to_anchor=(1.02, 1.0),
        fontsize=7,
        title_fontsize=7,
        alignment="left",
    )


def _sequential(cfg, fig, ax, img, label: str, vmin=None, vmax=None, cmap=None):
    im = ax.imshow(
        img,
        extent=lattice_extent(cfg),
        cmap=cmap or style.SEQUENTIAL,
        vmin=vmin,
        vmax=vmax,
        interpolation="nearest",
        zorder=2,
    )
    cb = fig.colorbar(im, ax=ax, shrink=0.6, pad=0.02)
    cb.set_label(label, color=style.INK_2)
    cb.outline.set_visible(False)


# ---------------------------------------------------------------- maps


def lulc_map(cfg, year: int) -> Path:
    ref = load_reference_grid(cfg)
    with rasterio.open(processed_dir(cfg) / f"lulc_esri_{year}.tif") as ds:
        arr = ds.read(1).astype("float64")
    arr[arr == 0] = np.nan
    b = ref.bounds
    fig, ax = base_map(cfg, f"Land cover {year}", "Esri 10 m Annual LULC (Impact Observatory)")
    _categorical(ax, arr, dict(style.ESRI_COLORS), (b[0], b[2], b[1], b[3]), "ESRI class")
    _outline(cfg, ax)
    return save(fig, cfg, f"map_lulc_{year}")


def class3_map(cfg, run: str) -> Path:
    c7 = schema.read_contract(c7_path(cfg, run), "C7")
    img = cell_image(cfg, c7["cell_id"], c7["class_3"])
    year = cfg["years"]["latest"] if run == "final" else cfg["years"]["baseline"]
    fig, ax = base_map(
        cfg,
        f"Three-class land map ({run} run, {year})",
        "K-Means clusters (k = 7) mapped by centroid rules; exclusion mask applied",
    )
    codes = {k: (style.CLASS_NAMES[k], style.CLASS_COLORS[k]) for k in style.CLASS_NAMES}
    _categorical(ax, img, codes, lattice_extent(cfg), "Class")
    _outline(cfg, ax)
    return save(fig, cfg, f"map_class3_{run}")


FEATURE_MAPS = {
    "log_dist_built": ("Distance to built-up", "metres", True),
    "log_dist_major": ("Distance to a major road", "metres", True),
    "road_density": ("Road density within 500 m", "km per km²", False),
    "ring500_built": ("Built-up share within 500 m", "share of the ring", False),
    "slope_mean": ("Mean slope", "degrees", False),
}


def feature_map(cfg, col: str, year: int) -> Path:
    c4 = schema.read_contract(schema.contract_path(cfg, "C4", year=year), "C4")
    title, unit, is_log = FEATURE_MAPS[col]
    v = np.expm1(c4[col]) if is_log else c4[col]
    img = cell_image(cfg, c4["cell_id"], v)
    snap = schema.vector_snapshot_for(cfg, year)
    sub = f"{year} features" + (
        f", OSM {snap} snapshot" if col in ("log_dist_major", "road_density") else ""
    )
    fig, ax = base_map(cfg, title, sub)
    _sequential(cfg, fig, ax, img, unit, vmin=0, vmax=float(np.nanpercentile(img, 99)))
    _outline(cfg, ax)
    return save(fig, cfg, f"map_feature_{col}_{year}")


def labels_map(cfg) -> Path:
    lab = schema.read_contract(schema.contract_path(cfg, "C5"), "C5")
    code = np.select(
        [lab["excluded"], lab["built_baseline"], lab["grew"], lab["candidate"] & ~lab["ambiguous"]],
        [255, 1, 4, 3],
        default=0,
    )
    img = cell_image(cfg, lab["cell_id"], np.where(code == 0, np.nan, code))
    codes = {
        1: ("Built in 2018", style.CLASS_COLORS[1]),
        4: ("Grew by 2022/23", style.SERIES[0]),
        3: ("Non-built, did not grow", "#cde2fb"),
        255: ("Excluded", style.NEUTRAL),
    }
    fig, ax = base_map(
        cfg,
        "Validation labels (2018 → 2022/23)",
        "Persistent growth: non-built in 2018 and 2019, built in 2022 and 2023",
    )
    _categorical(ax, img, codes, lattice_extent(cfg), "Cell")
    _outline(cfg, ax)
    return save(fig, cfg, "map_labels_growth")


SCORE_TITLES = {
    "rf_change": "Change random forest",
    "rf_state": "State random forest (comparison)",
    "mcda": "MCDA / AHP baseline",
    "mcda_no_lulc": "MCDA without land cover",
    "similarity_knn": "Building similarity (kNN)",
    "suitability": "Combined suitability score",
}


def score_map(cfg, model: str, run: str) -> Path | None:
    p = scores_path(cfg, model, run)
    if not p.exists():
        return None
    s = pd.read_parquet(p)
    img = cell_image(cfg, s["cell_id"], s["score"])
    scope = (
        "candidate cells, out-of-fold, 2018 features"
        if run == "validation"
        else "usable cells, latest features"
    )
    fig, ax = base_map(cfg, f"{SCORE_TITLES.get(model, model)}: {run} run", scope)
    _sequential(
        cfg,
        fig,
        ax,
        img,
        "score (higher = more suitable)",
        vmin=0,
        vmax=float(np.nanpercentile(img, 99.5)),
    )
    _outline(cfg, ax)
    return save(fig, cfg, f"map_score_{model}_{run}")


def suitability_map(cfg) -> Path | None:
    p = Path(cfg.paths["outputs"]) / "suitability_class.tif"
    if not p.exists():
        return None
    with rasterio.open(p) as ds:
        img = ds.read(1).astype("float64")
        img[img == ds.nodata] = np.nan
    codes = {
        1: ("S1 (top 10 %)", style.SEQ_BLUE[6]),
        2: ("S2", style.SEQ_BLUE[4]),
        3: ("S3", style.SEQ_BLUE[2]),
        4: ("N", style.NEUTRAL),
    }
    fig, ax = base_map(
        cfg,
        "Suitability for urban development",
        "Classes S1-S3 on usable land; forest, built-up and excluded are N",
    )
    _categorical(ax, img, codes, lattice_extent(cfg), "Class")
    cand = Path(cfg.paths["outputs"]) / "candidates.gpkg"
    if cand.exists():
        gpd.read_file(cand).boundary.plot(ax=ax, color=style.INK, linewidth=0.6, zorder=4)
    _outline(cfg, ax)
    return save(fig, cfg, "map_suitability_classes")


def make_all(cfg) -> list[Path]:
    y0, y1 = int(cfg["years"]["baseline"]), int(cfg["years"]["latest"])
    out = [
        lulc_map(cfg, y0),
        lulc_map(cfg, y1),
        class3_map(cfg, "validation"),
        class3_map(cfg, "final"),
    ]
    out += [feature_map(cfg, c, y1) for c in FEATURE_MAPS]
    out.append(labels_map(cfg))
    for model in SCORE_TITLES:
        for run in ("validation", "final"):
            out.append(score_map(cfg, model, run))
    out.append(suitability_map(cfg))
    return [p for p in out if p is not None]


def main(argv: list[str] | None = None) -> None:
    global BASEMAP
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-basemap", action="store_true")
    args = parser.parse_args(argv)
    BASEMAP = not args.no_basemap
    cfg = load_config()
    setup_logging(cfg, "viz")
    make_all(cfg)


if __name__ == "__main__":
    main()
