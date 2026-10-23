"""Phase 8 gate (final): deliverables, figures, map, code quality (see docs/Tasks.md).

Run: pytest tests/gates/test_phase8.py
Build first: python -m src.pipeline; the report and slides PDFs (build steps at the top of
report/final/report.tex and report/final_slides/slides.tex).
The full-suite check runs only with GIS_SUIT_RUN_SUITE=1 (it runs pytest on every other test).
Set GIS_SUIT_CONFIG to run the gate on another project.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from src.config import load_config

cfg = load_config(os.environ.get("GIS_SUIT_CONFIG"))
ROOT = Path(cfg.root)
OUT = Path(cfg.paths["outputs"])
FIG = Path(cfg.paths["figures"])

# PRD §6 deliverables -> files that must exist (relative to the repo root or outputs/)
DELIVERABLES = {
    "D1 source code": [ROOT / "src" / "pipeline.py", ROOT / "src" / "suitability" / "score.py"],
    "D2 notebooks": [
        ROOT / "notebooks" / f
        for f in (
            "01_data_download.ipynb",
            "02_preprocessing.ipynb",
            "03_feature_engineering.ipynb",
            "04_clustering.ipynb",
            "05_similarity.ipynb",
            "06_suitability_validation.ipynb",
        )
    ],
    "D3 tests": [ROOT / "tests" / "gates" / f"test_phase{i}.py" for i in range(9)],
    "D4 literature review": [ROOT / "docs" / "literature_review.md"],
    "D5 data sources": [ROOT / "docs" / "data_sources.md"],
    "D6 study area": [ROOT / "docs" / "study_area.md"],
    "D7 three-class map": [
        OUT / "lulc_3class.parquet",
        OUT / "lulc_3class.tif",
        FIG / "map_class3_final.png",
    ],
    "D8 similarity": [
        OUT / "scores" / "similarity_knn.parquet",
        FIG / "map_score_similarity_knn_final.png",
    ],
    "D9 score files": [
        OUT / "scores" / f"{m}.parquet"
        for m in ("similarity_knn", "rf_change", "rf_state", "mcda", "suitability")
    ],
    "D10 suitability map": [OUT / "suitability_class.tif", FIG / "map_suitability_classes.png"],
    "D11 candidate sites": [OUT / "candidates.gpkg", OUT / "candidates.csv"],
    "D12 interactive map": [OUT / "map.html"],
    "D13 validation": [ROOT / "docs" / "validation.md", OUT / "metrics" / "validation.json"],
    "D14 report": [
        ROOT / "report" / "final" / "report.tex",
        ROOT / "report" / "final" / "report.pdf",
    ],
    "D15 slides": [
        ROOT / "report" / "final_slides" / "slides.tex",
        ROOT / "report" / "final_slides" / "slides.pdf",
    ],
    "D16 README": [ROOT / "README.md"],
}

# FR-9.1 maps and FR-9.3 charts
FIGURES = [
    "map_lulc_2018",
    "map_lulc_2023",
    "map_class3_final",
    "map_labels_growth",
    "map_feature_log_dist_built_2023",
    "map_feature_road_density_2023",
    "map_score_rf_change_final",
    "map_score_similarity_knn_final",
    "map_score_mcda_final",
    "map_suitability_classes",
    "chart_k_scan",
    "chart_cluster_profiles",
    "chart_class_areas",
    "chart_rf_importance",
    "chart_roc",
    "chart_toc",
    "chart_growth_type",
    "chart_ablation",
    "chart_sensitivity",
]

MAP_LAYERS = [
    "Land cover",
    "Three-class map",
    "Suitability classes",
    "Change-RF score",
    "Building similarity",
    "Candidate sites",
    "Top",
    "Reference buildings",
    "Study area",
]


@pytest.mark.parametrize("name", sorted(DELIVERABLES))
def test_deliverable_exists(name):
    missing = [
        str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)
        for p in DELIVERABLES[name]
        if not p.exists()
    ]
    assert not missing, f"{name}: missing {missing}"


@pytest.mark.parametrize("name", FIGURES)
def test_figure_at_300_dpi(name):
    p = FIG / f"{name}.png"
    assert p.exists(), f"{p.name} missing (python -m src.viz.static_maps / src.viz.charts)"
    dpi = Image.open(p).info.get("dpi", (0, 0))[0]
    assert round(dpi) >= 300, f"{p.name}: {dpi:.0f} dpi"


def test_interactive_map_has_every_layer():
    html = (OUT / "map.html").read_text(encoding="utf-8")
    missing = [layer for layer in MAP_LAYERS if layer not in html]
    assert not missing, f"map.html lacks layers {missing}"


@pytest.mark.parametrize("cmd", [["ruff", "check", "."], ["black", "--check", "--quiet", "."]])
def test_code_quality(cmd):
    # conda's ruff ships only the executable (no python -m ruff): use the env's bin directory
    exe = Path(sys.executable).parent / cmd[0]
    tool = [str(exe)] if exe.exists() else [sys.executable, "-m", cmd[0]]
    r = subprocess.run([*tool, *cmd[1:]], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, f"{' '.join(cmd)} failed:\n{(r.stdout + r.stderr)[-2000:]}"


@pytest.mark.parametrize("nb", sorted((ROOT / "notebooks").glob("*.ipynb")), ids=lambda p: p.name)
def test_notebook_has_no_stored_outputs(nb):
    data = json.loads(nb.read_text(encoding="utf-8"))
    stored = [
        i for i, c in enumerate(data["cells"]) if c.get("outputs") or c.get("execution_count")
    ]
    assert not stored, f"{nb.name}: cells {stored[:5]} have stored outputs (nbstripout)"


@pytest.mark.skipif(
    os.environ.get("GIS_SUIT_RUN_SUITE") != "1",
    reason="set GIS_SUIT_RUN_SUITE=1 (runs every other test)",
)
def test_full_test_suite_passes():
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests",
            "-q",
            "-m",
            "not network",
            "-p",
            "no:cacheprovider",
            "--ignore=tests/gates/test_phase8.py",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, f"test suite failed:\n{r.stdout[-3000:]}"
