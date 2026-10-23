"""Single-building similarity query: building A -> similar locations B (PRD FR-6.3; Tasks P6.3).

Given a building (its ``bldg_id`` in the run's C6), a WGS84 point or a cell id, rank
the candidate cells of the run by how similar their surroundings are to A's:

- **Euclidean** distance between standardised profiles (decision D5, the default);
- cosine distance only as a comparison (it ignores magnitude: in the prototype it
  ranked no better than random).

Each result carries a per-feature explanation: the three profile features where B is
closest to A and the three where it differs most (in standard deviations), plus A's and
B's raw values. ``write_query`` exports ``outputs/similarity_query_<name>.gpkg`` (A and
the top-N cells with rank, distance, similarity and explanation) and a map PNG in
``outputs/figures/``.

Run: python -m src.similarity.query --building 12345 [--run final] [--n 20]
     python -m src.similarity.query --lonlat 77.66 12.84
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import load_config
from src.features import schema
from src.features.grid import grid_geodataframe
from src.io_utils import setup_logging
from src.similarity import profiles as pf

log = logging.getLogger(__name__)

METRICS = ("euclidean", "cosine")
FEATURE_LABELS = {
    "log_dist_built": "distance to built-up",
    "log_dist_water": "distance to water",
    "log_dist_major": "distance to a major road",
    "log_dist_any": "distance to any road",
    "road_density": "road density (500 m)",
    "elev_mean": "elevation",
    "slope_mean": "slope (mean)",
    "slope_max": "slope (max)",
}


def feature_label(col: str) -> str:
    if col in FEATURE_LABELS:
        return FEATURE_LABELS[col]
    if col.startswith("ring"):
        r, c = col[4:].split("_", 1)
        return f"{c} share within {r} m"
    return col


TRIVIAL_SHARE = 0.005  # a land-cover share below 0.5 % at both A and B


def trivial_match(cols, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Ring shares that are ~0 at both cells: a match that says nothing, ranked last."""
    is_share = np.array([c.startswith("ring") for c in cols])
    return is_share & (np.abs(a) < TRIVIAL_SHARE) & (np.abs(b) < TRIVIAL_SHARE)


@dataclass
class QueryResult:
    run: str
    query_cell: int
    metric: str
    results: pd.DataFrame  # rank, cell_id, distance, similarity, explanation columns
    query_profile: pd.Series  # raw values of A
    label: str = ""
    extra: dict = field(default_factory=dict)


def distances(z_cands: np.ndarray, z_a: np.ndarray, metric: str) -> np.ndarray:
    """Distance from A to every candidate (standardised profiles)."""
    if metric == "euclidean":
        return np.linalg.norm(z_cands - z_a, axis=1)
    if metric == "cosine":
        na, nc = np.linalg.norm(z_a), np.linalg.norm(z_cands, axis=1)
        cos = (z_cands @ z_a) / np.where(nc * na > 0, nc * na, 1.0)
        return 1.0 - cos
    raise ValueError(f"metric must be one of {METRICS}, got {metric!r}")


def resolve_cell(cfg, run: str, bldg_id=None, lonlat=None, cell_id=None) -> tuple[int, str]:
    """Query cell id and a short label, from a building id, a lon/lat or a cell id."""
    if bldg_id is not None:
        cell, row = pf.building_cell(cfg, run, int(bldg_id))
        kind = row.get("building_type") or "yes"
        return cell, f"building {bldg_id} ({kind})"
    if lonlat is not None:
        cell = pf.lonlat_to_cell(cfg, *lonlat)
        if cell < 0:
            raise ValueError(f"{lonlat} is outside the grid")
        return cell, f"point {lonlat[0]:.5f} E, {lonlat[1]:.5f} N"
    if cell_id is not None:
        return int(cell_id), f"cell {cell_id}"
    raise ValueError("give a building id, a lon/lat or a cell id")


def query(
    cfg,
    run: str = "final",
    bldg_id=None,
    lonlat=None,
    cell_id=None,
    n: int | None = None,
    metric: str = "euclidean",
    candidates: str = "usable",
    include_cells=(),
    profiles: pf.RunProfiles | None = None,
) -> QueryResult:
    """Top-N cells most similar to A. ``candidates``: "usable" (FR-6.7) or "all" grid cells."""
    rp = profiles or pf.run_profiles(cfg, run)
    cell, label = resolve_cell(cfg, run, bldg_id, lonlat, cell_id)
    if cell not in rp.z.index:
        raise ValueError(f"{label}: cell {cell} is not in the analysis grid")
    if candidates == "usable":
        cand = np.union1d(
            np.setdiff1d(rp.candidates, [cell]), np.asarray(include_cells, dtype="int64")
        )
    elif candidates == "all":
        cand = rp.z.index.to_numpy()
    else:
        raise ValueError("candidates must be 'usable' or 'all'")
    za = rp.z.loc[cell].to_numpy()
    zc = rp.z.loc[cand].to_numpy()
    d = distances(zc, za, metric)
    n = int(n or cfg["similarity"]["top_n"])
    order = np.argsort(d, kind="stable")[:n]
    top = pd.DataFrame(
        {"rank": np.arange(1, len(order) + 1), "cell_id": cand[order], "distance": d[order]}
    )
    dmax = float(np.percentile(d, 99)) or 1.0
    top["similarity"] = np.clip(1 - top["distance"] / dmax, 0, 1)
    gaps = np.abs(rp.z.loc[top["cell_id"]].to_numpy() - za)  # per-feature |z_B - z_A|
    cols = np.array(rp.z.columns)
    raw_all = pf.profile_table(cfg, run)
    raw_a = raw_all.loc[cell].to_numpy()
    closest, different = [], []
    for g, b_raw in zip(gaps, raw_all.loc[top["cell_id"]].to_numpy(), strict=True):
        trivial = trivial_match(cols, raw_a, b_raw)
        order = np.lexsort((g, trivial))
        closest.append("; ".join(feature_label(c) for c in cols[order[:3]]))
        worst = np.argsort(g)[::-1][:3]
        different.append("; ".join(f"{feature_label(cols[i])} ({g[i]:.1f} sd)" for i in worst))
    top["closest_features"], top["most_different"] = closest, different
    raw = raw_all.loc[[cell]].iloc[0]
    res = QueryResult(run, cell, metric, top, raw, label)
    res.extra["rank_percentile"] = (np.argsort(np.argsort(d)) + 1) / len(d)
    res.extra["candidate_ids"] = cand
    return res


def explain(res: QueryResult, cfg, rank: int = 1) -> pd.DataFrame:
    """A's and B's raw values and the gap in standard deviations, for one result."""
    rp = pf.run_profiles(cfg, res.run)
    b = int(res.results.loc[res.results["rank"] == rank, "cell_id"].iloc[0])
    raw = pf.profile_table(cfg, res.run)
    gap = (rp.z.loc[b] - rp.z.loc[res.query_cell]).abs()
    shown = raw.loc[[res.query_cell, b]].copy()
    logs = [c for c in shown.columns if c.startswith("log_dist")]
    shown[logs] = np.expm1(shown[logs])  # distances in metres
    out = pd.DataFrame(
        {"feature": [feature_label(c) + (" (m)" if c in logs else "") for c in raw.columns],
         "A": shown.iloc[0].to_numpy(), "B": shown.iloc[1].to_numpy(), "gap_sd": gap.to_numpy(),
         "trivial": trivial_match(
             np.array(raw.columns), shown.iloc[0].to_numpy(), shown.iloc[1].to_numpy()
         )}
    )  # fmt: skip
    return out.sort_values(["trivial", "gap_sd"]).drop(columns="trivial").reset_index(drop=True)


def write_query(cfg, res: QueryResult, name: str) -> tuple[Path, Path]:
    """GeoPackage of A + top-N cells and a map PNG."""
    from src.viz import static_maps as sm
    from src.viz import style

    grid = schema.read_contract(schema.contract_path(cfg, "C1"), "C1").set_index("cell_id")
    top = res.results.merge(grid[["row", "col", "x", "y"]], left_on="cell_id", right_index=True)
    gdf = grid_geodataframe(top.reset_index(drop=True), cfg)
    a = grid_geodataframe(grid.loc[[res.query_cell]].reset_index(), cfg).assign(
        rank=0, distance=0.0
    )
    out = Path(cfg.paths["outputs"]) / f"similarity_query_{name}.gpkg"
    gdf.to_file(out, layer="similar_cells", driver="GPKG")
    a.to_file(out, layer="query", driver="GPKG")

    fig, ax = sm.base_map(
        cfg,
        f"Locations similar to {res.label}",
        f"{res.run} run, top {len(top)} usable cells by {res.metric} distance",
    )  # noqa: E501
    use = pf.candidate_cells(cfg, res.run)
    img = sm.cell_image(cfg, use, np.ones(len(use)))
    ax.imshow(
        img,
        extent=sm.lattice_extent(cfg),
        cmap=style.class_cmap([3]),
        alpha=0.18,
        zorder=2,
        interpolation="nearest",
    )  # noqa: E501
    sc = ax.scatter(
        top["x"],
        top["y"],
        c=top["rank"],
        cmap=style.SEQUENTIAL.reversed(),
        s=28,
        marker="s",
        edgecolors=style.INK,
        linewidths=0.3,
        zorder=4,
        label="similar cells (rank)",
    )
    ax.scatter(
        [grid.at[res.query_cell, "x"]],
        [grid.at[res.query_cell, "y"]],
        marker="*",
        s=220,
        color=style.CLASS_COLORS[1],
        edgecolors=style.INK,
        linewidths=0.8,
        zorder=5,
        label="A",
    )
    sm._outline(cfg, ax)
    cb = fig.colorbar(sc, ax=ax, shrink=0.6, pad=0.02)
    cb.set_label("rank (1 = most similar)", color=style.INK_2)
    cb.outline.set_visible(False)
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), fontsize=7)
    png = sm.save(fig, cfg, f"map_similarity_query_{name}")
    log.info("wrote %s and %s", out.name, png.name)
    return out, png


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--building", type=int)
    g.add_argument("--lonlat", type=float, nargs=2)
    g.add_argument("--cell", type=int)
    parser.add_argument("--run", default="final", choices=pf.RUNS)
    parser.add_argument("--n", type=int)
    parser.add_argument("--metric", default="euclidean", choices=METRICS)
    args = parser.parse_args(argv)
    cfg = load_config()
    setup_logging(cfg, "similarity")
    res = query(cfg, args.run, args.building, args.lonlat, args.cell, args.n, args.metric)
    name = f"b{args.building}" if args.building is not None else f"c{res.query_cell}"
    write_query(cfg, res, name)
    print(res.results.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
