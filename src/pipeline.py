"""Run the whole analysis from the config (PRD FR-10.2, FR-10.3; Tasks P7.8).

Stages, in order (each one reads and writes the contract files on disk, so a run can
start at any stage):

1. ``download``    ESRI LULC + WorldCover, Copernicus DEM, OSM (2018 and pinned current);
                   every download is skipped when the file is already there
2. ``preprocess``  rasters on the reference grid, cleaned OSM layers and buildings (C6)
3. ``features``    grid (C1), raster (C2) and vector (C3) features, feature table (C4)
4. ``labels``      exclusion masks and growth labels (C5)
5. ``classify``    clustering, three-class map (C7) for both runs, exports, evaluation
6. ``similarity``  reference set, random forests, aggregate similarity, held-out check
7. ``suitability`` MCDA, combined score and classes, candidate sites, validation harness
8. ``viz``         static maps, charts, interactive map

The sensitivity analysis (cell size, slope threshold, k; PRD FR-8.7) runs after
``suitability`` by default (it rebuilds the features at 50 and 200 m, a few extra minutes);
``--skip-sensitivity`` leaves it out.

Each step runs as ``python -m <module>`` in a subprocess with this interpreter; stage and
step timings go to the log and to ``outputs/metrics/pipeline.json``.

Run: python -m src.pipeline [--from-stage features] [--to-stage suitability]
                          [--skip-sensitivity] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

from src.config import load_config
from src.io_utils import setup_logging

log = logging.getLogger(__name__)

STAGES: dict[str, list[list[str]]] = {
    "download": [["src.download.lulc"], ["src.download.dem"], ["src.download.osm"]],
    "preprocess": [["src.preprocess.raster"], ["src.preprocess.vector"]],
    "features": [
        ["src.features.raster_features"],
        ["src.features.distance"],
        ["src.features.build"],
    ],
    "labels": [["src.features.labels"]],
    "classify": [
        ["src.classify.cluster"],
        ["src.classify.label"],
        ["src.classify.export"],
        ["src.classify.evaluate", "--run", "final"],
    ],
    "similarity": [
        ["src.similarity.reference"],
        ["src.similarity.rf_model"],
        ["src.similarity.aggregate"],
        ["src.similarity.holdout"],
    ],
    "suitability": [
        ["src.suitability.mcda"],
        ["src.suitability.score"],
        ["src.suitability.candidates"],
        ["src.suitability.validate"],
    ],
    "viz": [["src.viz.static_maps"], ["src.viz.charts"], ["src.viz.interactive"]],
}
SENSITIVITY = ["src.suitability.sensitivity"]


def plan(
    start: str | None = None, stop: str | None = None, sensitivity: bool = True
) -> list[tuple[str, list[str]]]:  # noqa: E501
    """(stage, command) steps from ``start`` to ``stop`` inclusive."""
    names = list(STAGES)
    for s in (start, stop):
        if s is not None and s not in STAGES:
            raise ValueError(f"unknown stage {s!r}; stages: {names}")
    i = names.index(start) if start else 0
    j = names.index(stop) if stop else len(names) - 1
    if i > j:
        raise ValueError(f"--from-stage {start} comes after --to-stage {stop}")
    steps = []
    for name in names[i : j + 1]:
        steps += [(name, cmd) for cmd in STAGES[name]]
        if name == "suitability" and sensitivity:
            steps.append((name, SENSITIVITY))
    return steps


def run(steps: list[tuple[str, list[str]]], root: Path, dry_run: bool = False) -> dict:
    """Run the steps in order; stop at the first failure."""
    timings: dict = {"steps": [], "stages": {}}
    t_all = time.perf_counter()
    for stage, cmd in steps:
        line = " ".join(cmd)
        if dry_run:
            log.info("[dry run] %s: python -m %s", stage, line)
            continue
        log.info("%s: python -m %s", stage, line)
        t = time.perf_counter()
        r = subprocess.run([sys.executable, "-m", *cmd], cwd=root)
        dt = time.perf_counter() - t
        timings["steps"].append(
            {"stage": stage, "step": line, "seconds": round(dt, 1), "returncode": r.returncode}
        )
        timings["stages"][stage] = round(timings["stages"].get(stage, 0.0) + dt, 1)
        if r.returncode != 0:
            raise RuntimeError(f"{stage}: python -m {line} failed with exit code {r.returncode}")
        log.info("%s: %s done in %.0f s", stage, line, dt)
    timings["total_seconds"] = round(time.perf_counter() - t_all, 1)
    return timings


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--from-stage", choices=list(STAGES))
    parser.add_argument("--to-stage", choices=list(STAGES))
    parser.add_argument(
        "--skip-sensitivity", action="store_true", help="leave out the sensitivity analysis"
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    cfg = load_config()
    setup_logging(cfg, "pipeline")
    steps = plan(args.from_stage, args.to_stage, not args.skip_sensitivity)
    timings = run(steps, Path(cfg.root), args.dry_run)
    if not args.dry_run:
        timings.update(from_stage=args.from_stage or "download", to_stage=args.to_stage or "viz")
        p = Path(cfg.paths["metrics"]) / "pipeline.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(timings, indent=1))
        log.info("pipeline done in %.1f min", timings["total_seconds"] / 60)


if __name__ == "__main__":
    main()
