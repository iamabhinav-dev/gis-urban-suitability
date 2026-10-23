# GIS-Based Land Suitability Analysis for Urban Development

Term project (CS60111 Geographical Information Systems): where in **Bengaluru South** can new
urban development reasonably go? The whole analysis is done in Python, from open land use / land
cover (LULC), terrain and OpenStreetMap data.

The pipeline:
1. **classifies the land** into built-up, forest and usable by clustering 100 m cells;
2. **finds locations similar to a given building**: query a building A, get the usable cells B
   whose surroundings look most like A's, with an explanation of what matches;
3. **scores every usable cell**: a building-similarity score and a random forest that learns from
   recent growth are combined, graded into classes S1–S3 and grouped into candidate sites;
4. **tests every method against real growth**: scores computed with 2018 data only are compared
   with land that became built in 2022 and 2023, next to a classic MCDA/AHP overlay and simple
   baselines.

## Results in brief

| Score (computed as of 2018) | AUC on growth by 2022/23 | Lift in the top 10 % |
|---|---|---|
| **Combined suitability score** | **0.797** | **3.45** |
| Change random forest | 0.779 | 3.23 |
| Building similarity | 0.773 | 2.99 |
| Distance to built-up (baseline) | 0.763 | 3.04 |
| MCDA / AHP overlay | 0.636 | 1.86 |
| Random | 0.50 | 1.00 |

The classes S1 + S2 of the validation run hold 65 % of the growth. Growth next to existing
built-up land is predicted well (AUC ~0.82); growth far from it is not (~0.51). Details, misses
and limitations: [docs/validation.md](docs/validation.md).

## Setup

The environment uses **conda-forge** packages (reliable GDAL/rasterio on Windows and Linux). Use
any conda-compatible tool: Miniforge/conda, mamba or micromamba.

```bash
git clone https://github.com/code-Harsh247/gis-urban-suitability.git
cd gis-urban-suitability

conda env create -f environment.yml        # or: micromamba create -f environment.yml
conda activate gis-suit                    # or: micromamba activate gis-suit

pre-commit install                         # black, ruff, nbstripout, large-file check
python scripts/check_env.py                # all libraries import
pytest tests/unit                          # unit tests on synthetic data (no data needed)
```

To update after `environment.yml` changes: `conda env update -f environment.yml --prune`.

## Running the analysis

Everything runs from [config/config.yaml](config/config.yaml) and the study-area polygon in
`config/aoi.geojson`. One command runs every stage:

```bash
python -m src.pipeline                     # download → … → maps; ~15 min after the downloads
python -m src.pipeline --from-stage classify --to-stage suitability   # part of it
python -m src.pipeline --skip-sensitivity  # without the sensitivity analysis (a few minutes faster)
python -m src.pipeline --dry-run           # list the steps
```

| Stage | What it does | Main modules |
|---|---|---|
| `download` | ESRI 10 m LULC 2018–2023 and WorldCover 2021 (Planetary Computer), Copernicus DEM, OSM roads / water / buildings / protected areas as of 2018-01-01 and 2026-10-01 (Overpass) | `src/download/` |
| `preprocess` | rasters onto one 10 m reference grid (EPSG:32643), slope, cleaned OSM layers | `src/preprocess/` |
| `features` | 100 m grid, land-cover shares, rings at 250 / 500 m, distances, road density, terrain | `src/features/` |
| `labels` | exclusion mask (water, steep, protected), growth labels 2018 → 2022/23 | `src/features/labels.py` |
| `classify` | K-Means (k = 7) → built-up / forest / usable, evaluation vs ESRI and WorldCover | `src/classify/` |
| `similarity` | reference buildings, building similarity, random forests, held-out check | `src/similarity/` |
| `suitability` | MCDA/AHP, combined score and classes, candidate sites, validation | `src/suitability/` |
| `viz` | static maps and charts (300 dpi), interactive map | `src/viz/` |

The first download takes about 15 minutes; reruns skip files that are already there (checksums
and extents in `data/manifest.json`). Some university networks block the Overpass API, the
Planetary Computer or GitHub SSH; a VPN helps.

**Single building query:**

```bash
python -m src.similarity.query --building 274244          # an OSM building id (current snapshot)
python -m src.similarity.query --lonlat 77.66 12.84 --n 20
```

writes `outputs/similarity_query_<id>.gpkg` and a map in `outputs/figures/`.

**Notebooks** (`notebooks/01` … `06`, one per stage) call the `src/` functions and show the
tables and figures: data download, preprocessing, features, clustering, similarity, suitability
and validation. Run them after the pipeline.

## Outputs

| File | Content |
|---|---|
| `outputs/lulc_3class.tif`, `clusters.gpkg` | three-class land map (1 built-up, 2 forest, 3 usable, 255 excluded) |
| `outputs/suitability_score.tif`, `suitability_class.tif` | combined score 0–1 and classes (1 S1, 2 S2, 3 S3, 4 N) |
| `outputs/candidates.gpkg`, `candidates.csv` | candidate sites with area, score, slope, distances, land cover; `top_site_rank` for the 20 best ≥ 5 ha |
| `outputs/map.html` | interactive map with every layer and the top sites |
| `outputs/scores/*.parquet` | every model's score as of 2018 (validation run) |
| `outputs/final/scores/*.parquet` | the same models on the latest data (final map) |
| `outputs/metrics/*.json` | clustering, evaluation, similarity, MCDA, validation, sensitivity, pipeline timings |
| `outputs/figures/` | maps and charts used in the report |

`data/` and `outputs/` are not in git. The final report is in `report/final/` (LaTeX; build
steps at the top of `report.tex`) and the slides in `report/final_slides/`.

## How results are checked

- **Tests:** `pytest tests` runs the unit tests (synthetic data) and the phase gates 0–8 on the
  real outputs.
- **Independent checks:** every stage has a `scripts/verify_*.py` that recomputes its outputs a
  different way (e.g. pixel values against the source data, brute-force distances, AUC from
  ranks, OSM landmarks).
- **Reproducibility:** `scripts/compare_projects.py <a> <b>` compares two project folders, such
  as a fresh clone against a working copy.
- **Leakage rules:** no model sees a cell's own land cover; nothing after 2019 feeds a 2018
  score; trained models are scored out of fold with 2 km spatial blocks.

## Layout

```
config/      config.yaml + aoi.geojson (all parameters)
docs/        PRD, tasks, literature review, data sources, study area, validation
src/         download, preprocess, features, classify, similarity, suitability, viz, pipeline.py
notebooks/   01_data_download … 06_suitability_validation
tests/       unit/ (synthetic data) and gates/ (test_phase0 … test_phase8)
scripts/     verify_* checks, environment and data-coverage helpers
report/      final report and slides (LaTeX)
data/        downloaded and derived data (git-ignored)
outputs/     maps, rasters, scores, metrics (git-ignored)
```

## Data and attribution

- ESRI 10 m Annual Land Use Land Cover v02, Impact Observatory, Microsoft and Esri, CC BY 4.0.
- ESA WorldCover 10 m 2021 v200, © ESA WorldCover project / Contains modified Copernicus
  Sentinel data (2021) processed by the ESA WorldCover consortium, CC BY 4.0.
- Copernicus DEM GLO-30, provided under COPERNICUS by the European Union and ESA.
- © OpenStreetMap contributors, ODbL 1.0.
- Basemap tiles: Esri.

Details and versions: [docs/data_sources.md](docs/data_sources.md).
