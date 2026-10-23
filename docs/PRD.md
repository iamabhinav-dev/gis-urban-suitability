# Product Requirements Document (PRD)

## GIS-Based Land Suitability Analysis for Urban Development Using Land Use Land Cover

| Field | Value |
|---|---|
| Project type | Term project |
| Team | Harsh, Abhinav |
| Repository | https://github.com/code-Harsh247/gis-urban-suitability |
| Study area | **Bengaluru South**, India (582 km², EPSG:32643) |
| Deadline | **Final submission Tue 2026-10-06** |
| Document status | v1.1, aligned with the execution plan decisions D1–D10 |
| Created / updated | 2026-09-27 / 2026-10-01 |
| Related docs | [execution_plan.md](execution_plan.md) (who does what, when; file contracts) · [Tasks.md](Tasks.md) (phase checklist and gates) · [study_area.md](study_area.md) |

Decisions from the execution plan are cited as **[D1]…[D10]**. Rules added in this version are **[D11]** and **[D12]** (§9.9), agreed by both on 2026-10-01.

---

## Table of contents

1. [Summary](#1-summary)
2. [Background and problem statement](#2-background-and-problem-statement)
3. [Goals and non-goals](#3-goals-and-non-goals)
4. [Stakeholders and users](#4-stakeholders-and-users)
5. [Study area](#5-study-area)
6. [Deliverables](#6-deliverables)
7. [Data requirements](#7-data-requirements)
8. [Functional requirements](#8-functional-requirements)
9. [Methodology in detail](#9-methodology-in-detail)
10. [Non-functional requirements](#10-non-functional-requirements)
11. [System design and repository layout](#11-system-design-and-repository-layout)
12. [Technology stack and environment](#12-technology-stack-and-environment)
13. [Output specifications and data contracts](#13-output-specifications-and-data-contracts)
14. [Evaluation, validation and success criteria](#14-evaluation-validation-and-success-criteria)
15. [Development phases and timeline](#15-development-phases-and-timeline)
16. [Roles and responsibilities](#16-roles-and-responsibilities)
17. [Team workflow and conventions](#17-team-workflow-and-conventions)
18. [Risks and mitigations](#18-risks-and-mitigations)
19. [Assumptions and dependencies](#19-assumptions-and-dependencies)
20. [Open questions](#20-open-questions)
21. [Glossary](#21-glossary)
22. [References](#22-references)
23. [Change log](#23-change-log)

---

## 1. Summary

We will build a Python pipeline that takes freely available satellite-derived **Land Use Land Cover (LULC)** data, terrain data and infrastructure data (roads, water, buildings) for **Bengaluru South** and produces a **land suitability map for urban development**.

The pipeline does three things:

1. **Classifies land** into three groups (**built-up**, **forest**, **usable / potential land**) using unsupervised clustering.
2. **Learns from existing buildings** ("building similarity"):
   - Given a building at location **A**, it describes the *surroundings* of A: nearby land cover, distance to roads, water and existing development, and terrain.
   - It then finds locations **B** on usable land with similar surroundings.
3. **Produces a ranked suitability map** and a list of top candidate sites.

**How we know it works:** we rebuild the whole analysis as it would have looked in **2018** and check whether it ranks the land that actually became built by **2022–2023** highly. Every model is compared against simple baselines: random, distance to existing built-up, and a classic weighted-overlay (MCDA) map.

Everything is done in Python (no QGIS in the workflow). QGIS may be used only to visually spot-check outputs.

---

## 2. Background and problem statement

Cities grow into surrounding land, often without a systematic check of whether that land is appropriate. Planners need to know **where new development can reasonably happen**. That means land that:
- is not forest or water,
- is not too steep,
- can be reached by road,
- and is similar to places where development already works.

Traditional GIS suitability analysis uses **multi-criteria decision analysis (MCDA)**. A planner picks criteria (slope, distance to roads, etc.), assigns weights (for example with AHP), and overlays the layers in desktop GIS. This has two weaknesses:

- The weights are subjective.
- The workflow is manual and hard to reproduce.

This project addresses both:

- It is **data-driven**. Clustering finds natural land groupings, and similarity to existing buildings and a model trained on past growth replace hand-set weights.
- It is **fully scripted in Python**, so it is reproducible and can be rerun for a different city by changing a config file.
- It is **honestly validated** against real growth that happened after the baseline date, with simple baselines shown next to every result.

**Problem statement:** *Given a study area, identify and rank the land that is suitable for new urban development, using LULC and supporting spatial data, with a reproducible Python workflow whose ranking is validated against observed urban growth.*

---

## 3. Goals and non-goals

### 3.1 Goals

| ID | Goal |
|---|---|
| G1 | Acquire and document LULC and supporting datasets for the study area, for every year 2018–2023 and both OSM snapshots. |
| G2 | Review existing research on LULC-based land suitability and urban growth analysis. |
| G3 | Classify the study area into **built-up**, **forest** and **usable** land using clustering. |
| G4 | Implement **building similarity**: from a reference building / location A, find similar candidate locations B. Also produce an aggregate similarity score for every usable cell. |
| G5 | Train a **change-based Random Forest** on past growth as a learned alternative, and build an **MCDA/AHP** map as the classic baseline. |
| G6 | Produce a final **suitability map** (graded classes) and a ranked list of candidate sites. |
| G7 | **Validate** every model temporally (2018 → 2022/23) against random and distance-to-built baselines, and break the results down by growth type (LEI). |
| G8 | Implement everything in **Python**, reproducible from a clean clone with one config file. |
| G9 | Deliver a written report and presentation explaining the method and the results, including what did *not* work. |

### 3.2 Non-goals

- No web application or production service. Interactive HTML maps are enough.
- No training of an LULC classifier from raw imagery. We use existing LULC products.
- No modelling of land prices, ownership or zoning law. Protected areas are the exception: they are excluded as a hard constraint.
- No prediction of *when* land will be developed (no CA-Markov style forecasting). We rank *where*.
- No field surveys or new ground truth.

---

## 4. Stakeholders and users

| Stakeholder | Interest |
|---|---|
| Course instructor / evaluator | Sound method, clear results, reproducibility, report quality |
| Harsh, Abhinav (team) | Complete the project, share work fairly, learn geospatial Python |
| Hypothetical end user: urban planner | A map of where development fits, with an explanation of *why* (per-building queries, feature contributions) |

---

## 5. Study area

### 5.1 Decision [D1]

**Bengaluru South** (Karnataka, India) is the study area. **Hyderabad West** is the backup and **Pune West** the fallback.

- **Bbox:** 77.52–77.74 E, 12.72–12.94 N, about **582 km²**.
- **Processing CRS:** **EPSG:32643** (WGS 84 / UTM 43N), picked automatically by `crs.epsg: auto`.
- **What it covers:**
  - Electronic City, Bommasandra and the Hosur Road corridor
  - the Kanakapura Road fringe
  - **Bannerghatta National Park** in the south-west

Fourteen candidates were compared in [study_area.md](study_area.md). Bengaluru South was chosen for four reasons:

1. **Strong persistent growth:** 8.4 % of the land that was non-built in 2018 became built by 2022/23.
2. **A clear forest block** (Bannerghatta, about 19 % tree cover), next to open cropland and scrub.
3. **Mostly gentle terrain.**
4. **Good OSM coverage *in 2018*:** about 151k buildings. Temporal validation needs this, because the 2018 reference buildings must exist in OSM as of 2018.

**Known issues** (handled in the exclusion mask, FR-5.5):
- Bannerghatta NP and its eco-sensitive zone would otherwise look like "usable" scrub next to the city.
- Many small tanks (lakes) need to be masked as water.

### 5.2 Selection criteria (for reference / rerunning in another city)

The AOI must:

1. Have a growing urban area with surrounding non-built land.
2. Contain all three classes (built-up, forest, usable) in meaningful amounts.
3. Be covered by ESRI IO LULC v02 (global) and ESA WorldCover.
4. Have **good OSM building coverage at the baseline date**, not only today. Check this with the ohsome history API (`scripts/study_area_candidates.py`).
5. Be **200–1,000 km²**, which at 100 m cells is 20,000–100,000 cells.
6. Show **persistent** growth between the baseline and end years (§9.6), not just classifier flicker.

### 5.3 AOI definition

- Stored as one polygon in `config/aoi.geojson` (EPSG:4326). The current polygon is the study-area bbox; it may still be refined.
- All processing happens in the projected CRS from `config/config.yaml` (metres).

---

## 6. Deliverables

| ID | Deliverable | Format | Location |
|---|---|---|---|
| D1 | Source code (pipeline modules) | Python package | `src/` |
| D2 | Analysis notebooks (one per stage) | `.ipynb` | `notebooks/` |
| D3 | Unit, contract and phase gate tests | `pytest` | `tests/` |
| D4 | Literature review (≥ 10 papers + synthesis) | Markdown | `docs/literature_review.md` |
| D5 | Data sources, versions, licences, OSM snapshot method | Markdown | `docs/data_sources.md` |
| D6 | Study-area comparison | Markdown + figures | `docs/study_area.md` |
| D7 | Three-class land map | Parquet + GeoTIFF + PNG | `outputs/` (contract C7) |
| D8 | Building similarity results (per-query + aggregate) | GeoPackage, Parquet, PNG | `outputs/` |
| D9 | Model score files (similarity, change RF, state RF, MCDA, baselines) | Parquet + JSON | `outputs/scores/` (contract C8) |
| D10 | Final suitability map (graded classes) | GeoTIFF + PNG | `outputs/` |
| D11 | Top-N candidate sites | GeoPackage + CSV | `outputs/` |
| D12 | Interactive map | HTML (folium) | `outputs/map.html` |
| D13 | Validation report (metrics, ROC/TOC, LEI breakdown, ablation, sensitivity) | Markdown + JSON | `docs/validation.md`, `outputs/metrics/` |
| D14 | Final project report | PDF | `report/` |
| D15 | Presentation slides | PDF / PPTX | `report/` |
| D16 | README with setup and run instructions | Markdown | `README.md` |

---

## 7. Data requirements

### 7.1 Primary datasets

| Layer | Dataset | Resolution | Years / snapshot | Access (Python) | Purpose |
|---|---|---|---|---|---|
| LULC (main) **[D2]** | **ESRI IO LULC v02** (Impact Observatory) | 10 m | **2018–2023**, every year | Planetary Computer STAC `io-lulc-annual-v02` | All LULC features, the 3-class map, growth labels |
| LULC (cross-check) | ESA WorldCover | 10 m | 2021 | Planetary Computer STAC `esa-worldcover` | Cross-check of classes (forest in particular); not a model input |
| Elevation | Copernicus DEM GLO-30 | 30 m | static | Planetary Computer STAC `cop-dem-glo-30` | Elevation, slope |
| Roads **[D8]** | OpenStreetMap | vector | **2018-01-01 snapshot** + current | Overpass API `[date:]` query, with mirror fallback | Distance to roads, road density |
| Buildings **[D9]** | OpenStreetMap footprints | vector | **2018-01-01 snapshot** + current | Overpass API `[date:]` query | Reference buildings for similarity; building density (analysis only) |
| Water | ESRI water / flooded-vegetation classes (+ OSM water) | 10 m / vector | per year | as above | Distance to water; exclusion mask |
| Protected areas | OpenStreetMap `boundary=protected_area`, `leisure=nature_reserve` | vector | current | Overpass API | Exclusion mask (Bannerghatta NP) |

**Why ESRI for everything [D2]:**
- WorldCover has no 2018 map, so it can't supply baseline-year features or change labels.
- Using one source keeps the model we validate identical to the model we use for the final map.

**Why OSM snapshots [D8, D9]:** today's OSM contains roads and buildings added *after* 2018, which leaks future growth into baseline-year features. In the prototype, "distance to any road" alone went from AUC 0.58 to 0.76 when current roads were used. So:
- Every validation-run feature uses the **2018-01-01** snapshot. Major roads may come from any snapshot, because they barely leak: AUC 0.53 → 0.55.
- The **final map** uses current OSM.

### 7.2 Optional / stretch datasets

| Layer | Dataset | Purpose |
|---|---|---|
| Built-up surface | GHSL | Built-up density cross-check |
| Vegetation | Sentinel-2 L2A → NDVI | Extra profile feature (stretch) |
| Population | WorldPop | Population density feature |
| Building fallback | Microsoft / Google Open Buildings | Only if OSM proves too sparse (it is not, for Bengaluru South in 2018) |

### 7.3 Data handling rules

- Folders, all git-ignored:
  - raw downloads → `data/raw/` (`lulc/`, `dem/`, `osm/`)
  - processed layers → `data/processed/`
  - features and labels → `data/features/`
- Every downloaded file is recorded in `data/manifest.json` (`src/io_utils.Manifest`) with:
  - dataset, source and collection / query
  - date downloaded, data year or snapshot
  - CRS, resolution, bbox
  - size and SHA-256
- Downloads are **idempotent**: a rerun skips files whose checksum matches. They retry with clear errors (`io_utils.retry`), and Overpass falls back across the mirrors in `config.yaml → osm.overpass_mirrors`.
- The slow OSM 2018 snapshot is also put on the team's shared drive, with the link in `docs/data_sources.md`.

### 7.4 LULC classes (ESRI IO LULC v02)

| Code | Class | Project use |
|---|---|---|
| 1 | Water | **Excluded** |
| 2 | Trees | Forest |
| 4 | Flooded vegetation | **Excluded** |
| 5 | Crops | Usable, but flagged as agricultural **[D10]** |
| 7 | Built area | Built-up |
| 8 | Bare ground | Usable |
| 9 | Snow / ice | **Excluded** |
| 10 | Clouds | Treated as nodata |
| 11 | Rangeland | Usable (note: ESRI maps much of Bannerghatta as rangeland, so protected areas are masked separately) |
| 0 | No data | nodata |

**Notes:**
- An ESRI ↔ WorldCover mapping table lives in code and in `docs/data_sources.md`. It's used for the cross-check only.
- This mapping is a **reference** for labelling and checking clusters. The clustering itself does not just copy it (§9.4).
- **Known data issue:** ESRI tree cover jumps between years in the AOI (7.0 % → 2.3 % → 8.4 %). The forest class therefore needs care (§9.4).

---

## 8. Functional requirements

Each requirement has an ID that tasks in [Tasks.md](Tasks.md) and [execution_plan.md](execution_plan.md) refer to.

### FR-1 Configuration

- **FR-1.1** A single `config/config.yaml` holds every parameter:
  - AOI path / name and buffer; CRS
  - grid cell size
  - LULC source and the years (`baseline`, `baseline_confirm`, `change_train_end`, `latest`, `latest_confirm`)
  - feature radii, exclusion rules, clustering and labelling thresholds
  - growth-label thresholds, similarity settings, OSM snapshot date and mirrors
  - suitability classes, validation block size, random seed and paths
- **FR-1.2** `src/config.py` validates the config on load:
  - the AOI is one valid polygon;
  - the CRS is projected, in metres;
  - the cell size is > 0;
  - the required sections are present.
- **FR-1.3** Changing only the config (and the AOI file) is enough to rerun the pipeline for a different area.

### FR-2 Data acquisition

- **FR-2.1** Download ESRI IO LULC v02 for **every year from `years.baseline` to `years.latest`** (2018–2023), clipped to the AOI + `aoi.buffer_m`.
- **FR-2.2** Download ESA WorldCover for `lulc.worldcover_check` (2021), as a cross-check.
- **FR-2.3** Download the Copernicus DEM GLO-30 for the AOI + buffer.
- **FR-2.4** Download OSM roads (with `highway`), water and buildings (`building=*`) for **two snapshots**: `osm.snapshot_baseline` (2018-01-01, via Overpass `[date:]`) and current. Save as GeoPackage.
- **FR-2.5** Download OSM protected-area polygons for the AOI.
- **FR-2.6** Record every download in `data/manifest.json`.
- **FR-2.7** Downloads are idempotent, retry on failure, fall back across Overpass mirrors, and fail with a clear message if every source is unavailable.

### FR-3 Preprocessing

- **FR-3.1** Define a **10 m reference grid**: the ESRI tile grid, in the project UTM CRS. Save its spec to `data/processed/reference_grid.json`.
- **FR-3.2** Reproject and align every raster to the reference grid (same transform and shape). Use nearest-neighbour for classes and bilinear for the DEM. One nodata value per raster.
- **FR-3.3** Compute **slope** (degrees, Horn method) from the aligned DEM.
- **FR-3.4** Keep the ESRI ↔ WorldCover class mapping (code + docs).
- **FR-3.5** Vector cleaning for each snapshot:
  - reproject and clip;
  - `make_valid`, drop empty geometries;
  - classify roads as **major** (motorway, trunk, primary, secondary, including `_link`) or **minor** (all other drivable classes);
  - clean buildings: drop footprints < 10 m² and outliers.
- **FR-3.6** Join each building to its grid cell (`cell_id`). This produces contract **C6** for the `2018` and `current` snapshots.

### FR-4 Grid, features and labels

- **FR-4.1** A regular **100 m grid** whose cells line up exactly with 10 × 10 blocks of the reference raster, giving contract **C1** (`cell_id, row, col, x, y`).
- **FR-4.2** **Raster features per year** (contract **C2**):
  - own-cell LULC fractions (**clustering only** [D4]);
  - **ring fractions** at 250 m and 500 m, *excluding the centre cell*;
  - terrain (`elev_mean`, `slope_mean`, `slope_max`);
  - `log_dist_built`, `log_dist_water` (distance transform at 10 m, sampled at cell centres, capped at `distance_cap_m`, log-transformed);
  - `nodata_frac`.
- **FR-4.3** **Vector features per snapshot** (contract **C3**):
  - `log_dist_major`, `log_dist_any`
  - `road_density` (within 500 m)
  - `bldg_count`, `bldg_area_frac` (analysis only; listed in `LEAKY_FEATURES`)
- **FR-4.4** Merge C2 + C3 on `cell_id` into the **feature table** per year (contract **C4**). Cells with more than `max_nodata_fraction` nodata are dropped, and the drops are logged.
- **FR-4.5** **Labels** (contract **C5**, §9.6): `excluded`, `built_baseline`, `candidate`, `grew`, `chg_train_pos`, `lei_type`.
- **FR-4.6** Column names, groups and allowed model inputs are defined once in `src/features/schema.py`:
  - `FEATURE_GROUPS`, `OWN_CELL_FEATURES`, `CONTEXT_FEATURES`, `LEAKY_FEATURES`, `MODEL_INPUTS`
  - Code must import these names and must not type column names by hand.

### FR-5 Land classification (clustering)

- **FR-5.1** Clustering inputs: own-cell LULC fractions + terrain (`schema.CLUSTER_INPUTS`; the owner may extend it). Standardise them; PCA is optional (≥ 90 % variance).
- **FR-5.2** Run K-Means (baseline) and GMM. HDBSCAN is optional, via `sklearn.cluster.HDBSCAN`.
- **FR-5.3** Choose *k* in 3–10 with elbow, silhouette and Davies–Bouldin.
- **FR-5.4** Map clusters to built-up / forest / usable / excluded with documented centroid rules (§9.4). Thresholds come from `config.yaml → labeling`.
- **FR-5.5** Apply the **exclusion mask** after labelling. A cell is excluded if any of these hold:
  - ESRI water / flooded / snow > `exclusion.max_excluded_fraction` (50 %);
  - slope > `exclusion.slope_max_deg` (15°) [D10];
  - nodata > 50 %;
  - it lies inside a protected area (Bannerghatta NP).
- **FR-5.6** Evaluate against ESRI collapsed to 3 classes (primary) and WorldCover 2021 (cross-check), with confusion matrices and agreement.
- **FR-5.7** A fixed seed gives identical labels.
- **FR-5.8** Output: contract **C7** (`cell_id, cluster_id, class_3`) + GeoTIFF. One C7 is produced **per run** (§9.9): baseline year for validation, latest year for the final map.

### FR-6 Building similarity and learned models

- **FR-6.1** **Reference buildings:**
  - the **OSM 2018 snapshot** for the validation run;
  - **current OSM** for the final map [D9].
- **FR-6.2** **Profiles** use `schema.MODEL_INPUTS` only:
  - context ring fractions, distances and terrain;
  - **no own-cell LULC fractions at all** and no building counts [D4];
  - `schema.check_model_inputs` raises an error on anything else.
- **FR-6.3** **Single-query mode:**
  - input: a building ID or lat/lon;
  - output: the top-N usable cells by **Euclidean distance in standardised space** [D5];
  - cosine similarity is available as a comparison only;
  - each result comes with a per-feature explanation (which features match), a GeoPackage and a PNG.
- **FR-6.4** **Aggregate mode:**
  - for every candidate cell, take the mean distance to its *k* nearest reference profiles (`similarity.knn_k`);
  - rescale to 0–1 (higher = more similar);
  - save as contract **C8**, model `similarity_knn`.
- **FR-6.5** **Change-based Random Forest** [D6] (model `rf_change`):
  - positives: cells non-built in 2018 and 2019 that are built in **2020 and 2021** (`chg_train_pos`);
  - negatives: other candidate cells;
  - features: the 2018 values of `MODEL_INPUTS`;
  - class-balanced.
- **FR-6.6** **State Random Forest** (model `rf_state`): built vs non-built in 2018 on `MODEL_INPUTS`, kept as a comparison only.
- **FR-6.7** **Scoring scope:**
  - In the **validation run**, models score every cell with `candidate = True` (C5).
  - In the **final run**, they score usable cells (C7 `class_3 = 3`, not excluded).
  - Forest, built-up and excluded cells never receive a positive suitability class.
- **FR-6.8** **Out-of-fold scoring for trained models [D11]:**
  - Any model fitted on growth labels (`rf_change`) must produce validation scores **out of fold**.
  - Use spatial-block K-fold (`validation.spatial_block_m`, 2 km blocks). Each cell's score comes from a model that never saw its block.
  - This matters because the 2020/21 training positives are also positives of the 2022/23 test label.
  - The final-map model is fitted on all blocks.

### FR-7 Suitability mapping

- **FR-7.1** **MCDA/AHP baseline** (model `mcda`):
  - rescale criteria to 0–1: slope, distance to major road, distance to built-up, distance to water (with a buffer), LULC;
  - AHP pairwise weights, with consistency ratio < 0.1.
- **FR-7.2** **Final combined score:** a documented weighted mean of `similarity_knn` and `rf_change`. Weights are chosen on the validation run and frozen before the final run.
- **FR-7.3** **Classes:** S1 ≥ q90, S2 ≥ q70, S3 ≥ q40, else N (`suitability.class_quantiles`). Forest, built-up and excluded cells are always N.
- **FR-7.4** **Candidate patches:**
  - merge adjacent S1 cells;
  - drop patches smaller than `suitability.min_patch_area_m2` (1 ha);
  - export with attributes.

### FR-8 Validation

- **FR-8.1** **Persistent growth label** (`grew`): a candidate cell that is built (built fraction ≥ `growth.built_min`) in **both 2022 and 2023**. A cell counts as a **candidate** only if it is non-built (built fraction < `growth.nonbuilt_max`) in **both 2018 and 2019** and is not excluded [D3].
- **FR-8.2** **Time-travel rule [D12]:** everything that feeds a validation-run score must be dated **≤ `years.baseline_confirm`**: LULC, OSM snapshot, 3-class map, exclusion mask and reference buildings. The only exceptions are static layers (DEM, protected areas), and each must be noted in `validation.md`.
- **FR-8.3** **A single validation harness** (`src/suitability/validate.py`) scores **any** C8 file the same way:
  - temporal ROC-AUC;
  - top-N hit rate with **lift over random**;
  - **TOC** curve;
  - AUC split by **LEI growth type**.
- **FR-8.4** **Baselines added automatically:** random and **distance-to-built** (`−log_dist_built`). MCDA is shown next to every model [D7].
- **FR-8.5** **Group ablation:** drop one `ABLATION_GROUP` at a time and report the change in AUC.
- **FR-8.6** **Sanity checks:**
  - querying building A returns A's own cell (or a neighbour) in the top 1 %;
  - no excluded, forest or built cell appears in S1–S3 or in the candidate list.
- **FR-8.7** **Sensitivity:** cell size (50 / 100 / 200 m), slope threshold and *k*, with the metric change reported.
- **FR-8.8** Spatial-block CV is used for **RF hyperparameter tuning** and out-of-fold scoring only. "RF spatial-CV AUC on built vs non-built" is **not** a success metric [D7].

### FR-9 Visualisation

- **FR-9.1** Static maps (PNG, 300 dpi) in one shared style: title, legend, scale bar, north arrow, basemap. They cover LULC, the 3-class map, key features, labels, each model score, suitability classes and the top candidates.
- **FR-9.2** An interactive HTML map (folium) with toggleable layers and popups for the candidates.
- **FR-9.3** Charts:
  - elbow / silhouette / Davies–Bouldin
  - cluster centroid profiles
  - RF feature importance
  - ROC and TOC curves
  - ablation table
  - LEI breakdown
  - class-area statistics

### FR-10 Reproducibility and orchestration

- **FR-10.1** Notebooks run top to bottom without manual edits.
- **FR-10.2** `python -m src.pipeline` runs every stage from the config, with `--from-stage`. Every stage reads and writes files on disk (the contracts in §13).
- **FR-10.3** `tests/unit/test_contracts.py` validates every contract file (stub and real) against `schema.py`.

---

## 9. Methodology in detail

### 9.1 Pipeline overview

```
config.yaml + aoi.geojson
        │
        ▼
Download ── ESRI LULC 2018–2023, WorldCover 2021, DEM            (Abhinav)
        └── OSM roads / water / buildings: 2018 + current,
            protected areas                                      (Harsh)
        │
        ▼
Preprocess ── 10 m reference grid, aligned rasters, slope        (Abhinav)
           └── road classes, clean buildings → C6                (Harsh)
        │
        ▼
Features ── grid C1 → raster features C2 (per year)              (Abhinav)
         └── vector features C3 (per snapshot)                   (Harsh)
         → feature table C4 (per year)   → labels C5             (Abhinav)
        │
        ├──► Clustering → 3-class map C7                         (Harsh)
        ├──► Building similarity → C8 similarity_knn             (Abhinav)
        ├──► Change RF / state RF → C8 rf_change, rf_state       (Harsh)
        └──► MCDA / AHP → C8 mcda                                (Harsh)
                    │
                    ▼
        Validation harness (all C8 + baselines) → validation.json (Abhinav)
        Combined score → S1/S2/S3/N + candidate patches          (Abhinav)
                    │
                    ▼
        Static maps (Harsh) · interactive map (Abhinav) · report
```

The whole chain runs **twice** (§9.9):
- the **validation run**, as of 2018;
- the **final run**, as of the latest year.

### 9.2 Grid

- Square cells, default **100 m** (1 ha). Configurable for the sensitivity runs (50–200 m).
- The cells line up exactly with 10 × 10 blocks of the 10 m reference raster, so per-cell fractions are a simple block aggregation (no polygon zonal statistics).
- **Why a grid:** it turns mixed data (10 m rasters, 30 m DEM, vectors) into one table with one row per cell, which suits scikit-learn.

### 9.3 Features

| Group (`schema.FEATURE_GROUPS`) | Features | Used by |
|---|---|---|
| `lulc_own` | `frac_{water,tree,flooded,crop,built,bare,snow,range}` (own cell) | **Clustering only** [D4] |
| `lulc_context` | `ring{250,500}_{tree,crop,range,bare,water}` (window minus centre cell) | Clustering, similarity, RF |
| `near_built` | `ring250_built`, `ring500_built`, `log_dist_built` | Similarity, RF |
| `roads` | `log_dist_major`, `log_dist_any`, `road_density` | Similarity, RF |
| `terrain` | `elev_mean`, `slope_mean`, `slope_max` | All |
| `water` | `log_dist_water` | Similarity, RF |
| `buildings` | `bldg_count`, `bldg_area_frac` | Analysis only (**leaky**) |

- `MODEL_INPUTS = CONTEXT_FEATURES − LEAKY_FEATURES`.
- Ring fractions exclude the centre cell, so they describe the *surroundings* without encoding the cell's own status.
- **Why own-cell fractions are banned from models [D4]:** in the prototype they separated built from non-built perfectly (AUC 1.0), because they sum to 1 − built.

### 9.4 Land classification (clustering)

1. **Inputs:** `schema.CLUSTER_INPUTS` (own-cell fractions + terrain; ring fractions may be added), standardised.
2. **Algorithms:** K-Means (k-means++, `n_init=10`, fixed seed) and GMM (full covariance, components by BIC). HDBSCAN is optional.
3. **Choosing *k*:** inertia (elbow), silhouette and Davies–Bouldin for k = 3…10. *k* may be > 3, with several clusters mapped to one class (e.g. "usable, flat, near roads" vs "usable, hilly").
4. **Rules from centroids to classes:**
   - highest mean `frac_built` (≥ `labeling.built_threshold`, 0.3) → **built-up**;
   - highest mean `frac_tree` (≥ `labeling.forest_threshold`, 0.5) → **forest**;
   - water-dominated → **excluded**;
   - everything else → **usable**. Cropland stays usable but flagged [D10].
5. **Exclusion mask** applied last (FR-5.5).
6. **Forest stability:**
   - ESRI tree cover flickers between years, so check the forest class against WorldCover 2021 (about 20 % trees in the AOI).
   - If one ESRI year is clearly off, document the choice of year.
   - In the validation run, use only years ≤ 2019 (FR-8.2).
7. **Evaluation:**
   - silhouette and Davies–Bouldin;
   - confusion matrix vs ESRI (collapsed to 3 classes) and vs WorldCover 2021;
   - centroid profile plots, with a written description of each cluster.
8. **Report point:** agreement with LULC is expected to be high, because LULC fractions are inputs. The value of clustering lies in the sub-groups it finds inside "usable" land.

### 9.5 Building similarity

**Idea:** a building exists at A because the surroundings of A suit a building. Locations whose surroundings look like A's are good candidates for a similar building.

- **Profile** of a location: its `MODEL_INPUTS` vector, i.e.
  - context ring fractions at 250 m and 500 m
  - distances to built-up, roads and water
  - road density
  - terrain

  Standardise it with statistics fitted on reference + candidate cells. Reference buildings take the profile of the cell they sit in.
- **Single query (the meeting's A → B idea):**
  1. Pick building A, by ID or lat/lon.
  2. Compute A's profile.
  3. Measure the **Euclidean distance** to every candidate cell [D5].
  4. Return the top-N cells B₁…Bₙ, with a per-feature breakdown of what matches.
  - Cosine is kept only as a comparison. In the prototype it ranked no better than random (AUC 0.49, vs 0.74 for Euclidean), because it ignores magnitude.
- **Aggregate score:**
  1. Find the *k* = 10 nearest reference profiles (`sklearn.neighbors.NearestNeighbors`).
  2. Take the mean distance → similarity = 1 − rescaled distance.
  3. Save as C8 `similarity_knn`.
- **Expected result:** going by the prototype, similarity may only *match* the distance-to-built baseline (about 0.75). The report frames its value as **explainable per-building queries**.
  - Stretch: add NDVI or 2018 building density to the profile.
- **Stretch:** similarity per building type (residential / commercial / industrial) if OSM tags allow (Q7).

### 9.6 Labels (contract C5)

| Label | Definition (thresholds from `config.yaml → growth`) |
|---|---|
| `excluded` | Exclusion mask (FR-5.5) |
| `built_baseline` | Built fraction ≥ `built_min` (0.5) in `years.baseline` (2018) |
| `candidate` | Built fraction < `nonbuilt_max` (0.1) in **2018 and 2019**, and not excluded |
| `grew` | `candidate` and built fraction ≥ 0.5 in **2022 and 2023** (persistent growth) |
| `chg_train_pos` | `candidate` and built in **2020 and 2021** (change-RF positives) [D6] |
| `lei_type` | Landscape Expansion Index of the growth patch (≥ `lei_min_patch_m2`, 20 m buffer): `adjacent` (infilling / edge expansion) or `outlying`; `none` if no growth |

**Why two years at each end [D3]:**
- Only 35–49 % of raw "new built" pixels between single years are persistent; the rest is classifier flicker.
- The 2017 map is noticeably noisier, so 2018 is the baseline.

Cells between the thresholds (built fraction 0.1–0.5) are neither candidates nor growth. They are left out of validation and their counts are logged.

### 9.7 Learned models and MCDA baseline

- **Change RF [D6]:**
  - learns which 2018 surroundings preceded growth by 2020/21;
  - in the prototype it beat a built vs non-built RF (AUC 0.76 vs 0.66);
  - validation scores are **out of fold** (FR-6.8), so 2020/21 training positives are never scored by a model that saw them.
- **State RF:** built vs non-built in 2018. Kept for comparison.
- **Both:** class-balanced, `MODEL_INPUTS` only. Spatial-block CV (2 km) is used to tune hyperparameters. Feature importance is reported both impurity-based and by permutation.
- **MCDA/AHP:** criteria rescaled to 0–1; weights from the literature or a small AHP matrix with consistency ratio < 0.1; output is C8 `mcda`. It's the "classic method" bar.

### 9.8 Validation design and targets [D7]

| Check | How | Target |
|---|---|---|
| Temporal ROC-AUC | Score from the validation run (as of 2018); label `grew` among `candidate` cells | Best model **≥ the distance-to-built baseline** (about 0.75 in the prototype); every model reported next to random, distance-to-built and MCDA |
| Top-N hit rate + lift | Share of `grew` cells in the top 10 % / 30 % of scores ÷ the share expected at random | Lift ≥ 2 in the top 10 % |
| TOC curve | Total operating characteristic for each model | Plotted for all models |
| LEI breakdown | AUC on `adjacent` vs `outlying` growth | Reported; outlying growth is expected to be harder |
| Ablation | Drop one feature group at a time | Table: which groups carry the signal |
| Self-query sanity | Query building A → A's own cell in the top 1 % | Must pass |
| Exclusion sanity | No excluded / forest / built cell in S1–S3 or the candidate list | 0 violations |
| Clustering agreement | vs ESRI collapsed to 3 classes (primary) and WorldCover 2021 | ≥ 80 %, or explained |
| Leakage guards | `check_model_inputs` on every model; time-travel rule (FR-8.2); out-of-fold RF scores (FR-6.8) | Enforced by gate tests |

**The real success criterion is honesty, not a number.** The prototype suggests distance-to-built alone is a strong baseline. If no model beats it clearly, the report says so and explains what the models add: per-building explanation, the sub-groups of usable land, and the comparison with MCDA.

### 9.9 Two runs and leakage rules

| | **Validation run** (as of 2018) | **Final run** (as of the latest year) |
|---|---|---|
| Purpose | Measure how well each model predicts 2018 → 2022/23 growth | Produce the suitability map for planning today |
| LULC features | ESRI 2018 | ESRI `years.latest` (2023) |
| OSM roads / buildings | 2018-01-01 snapshot | Current |
| 3-class map / mask | Built from data ≤ 2019 | Built from the latest data |
| Cells scored | C5 `candidate` | C7 usable, not excluded |
| RF training | `chg_train_pos` (2018/19 → 2020/21), out-of-fold scores | Same definition, fitted on all blocks; optionally shifted forward when newer years exist |
| Outputs | `outputs/scores/*`, `validation.json` | Suitability classes, candidate patches, maps |

**[D11] Out-of-fold scoring** (FR-6.8): without it, the change RF is scored on its own training positives (every `chg_train_pos` cell is also a `grew` cell), which inflates its AUC.

**[D12] Time-travel rule** (FR-8.2): with a 2023 3-class map in the validation run, every cell that grew by 2023 would already be labelled built-up and would never be scored. That breaks the validation.

Both rules came out of the PRD review on 2026-10-01 and are **agreed by both** (Abhinav, 2026-10-01):
- D12 is implemented in `src/features/labels.py` and tested (the validation mask ignores every map after 2019).
- D11 is needed on the real labels: 85 % of the 355 change-RF training positives are also `grew` cells (27 % of all growth), so in-sample scores would inflate the RF's AUC.

---

## 10. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 Reproducibility | Fresh clone + environment + config gives the same outputs: fixed seeds, data manifest with checksums, versions pinned once both laptops work. |
| NFR-2 Performance | The full pipeline for the AOI runs in **< 30 min** on a normal laptop (8–16 GB RAM), excluding the first download. Peak memory **< 8 GB**. |
| NFR-3 Portability | Works on Windows (Harsh) and Linux (Abhinav). Uses conda-forge packages and `pathlib` paths. |
| NFR-4 Code quality | Docstrings + type hints in `src/`. Notebooks call `src/` functions. `black` + `ruff` clean. |
| NFR-5 Testing | Unit tests on synthetic data (`src/synthetic.py`); contract tests for C1–C8; phase gate tests. |
| NFR-6 Version control | No data or large outputs in git (pre-commit blocks files > 1 MB). Notebook outputs stripped (`nbstripout`). |
| NFR-7 Documentation | README, PRD, execution plan, Tasks, study area, data sources, literature review, validation, report. |
| NFR-8 CRS correctness | All distances and areas are computed in the projected CRS. Never in EPSG:4326. |
| NFR-9 Logging | Each stage logs inputs, outputs, counts, drops and timings to `logs/` and the console. |
| NFR-10 Leakage safety | Model inputs pass `schema.check_model_inputs`; validation runs obey the time-travel rule; trained models are scored out of fold. |

---

## 11. System design and repository layout

```
gis-urban-suitability/
├── CLAUDE.md                     # pointer to docs/CLAUDE.md
├── README.md
├── environment.yml               # conda-forge env "gis-suit"
├── pyproject.toml                # package + black/ruff/pytest config
├── .pre-commit-config.yaml
├── config/
│   ├── config.yaml               # all parameters
│   └── aoi.geojson               # Bengaluru South polygon
├── docs/
│   ├── CLAUDE.md
│   ├── PRD.md                    # this document
│   ├── execution_plan.md         # tracks, contracts, decisions, timeline
│   ├── Tasks.md                  # phase checklist + gates
│   ├── study_area.md  + img/     # candidate comparison
│   ├── literature_review.md
│   ├── data_sources.md
│   └── validation.md
├── src/
│   ├── config.py                 # load + validate config
│   ├── io_utils.py               # manifest, checksums, retry, logging
│   ├── synthetic.py              # stub generator for all contracts (C1–C8)
│   ├── download/
│   │   ├── stac.py               # shared STAC search / mosaic / clip
│   │   ├── lulc.py               # ESRI 2018–2023 + WorldCover 2021        (A)
│   │   ├── dem.py                # Copernicus DEM                          (A)
│   │   └── osm.py                # Overpass snapshots, mirrors, protected  (H)
│   ├── preprocess/
│   │   ├── raster.py             # reference grid, align                   (A)
│   │   ├── terrain.py            # slope                                   (A)
│   │   └── vector.py             # clean, road classes, buildings → C6     (H)
│   ├── features/
│   │   ├── schema.py             # contracts, feature groups (joint)
│   │   ├── grid.py               # C1                                      (A)
│   │   ├── lulc_features.py      # own + ring fractions                    (A)
│   │   ├── context.py            # rings                                   (A)
│   │   ├── distance.py           # road distances, density → C3            (H)
│   │   ├── labels.py             # mask, growth, LEI → C5                  (A)
│   │   └── build.py              # C2 + C3 → C4                            (A)
│   ├── classify/
│   │   ├── cluster.py            # K-Means, GMM, k selection               (H)
│   │   └── label.py              # clusters → classes → C7                 (H)
│   ├── similarity/
│   │   ├── profiles.py           #                                          (A)
│   │   ├── query.py              # single-building query                   (A)
│   │   ├── aggregate.py          # kNN score → C8                          (A)
│   │   └── rf_model.py           # change RF + state RF → C8               (H)
│   ├── suitability/
│   │   ├── mcda.py               # AHP baseline → C8                       (H)
│   │   ├── validate.py           # harness: AUC, lift, TOC, LEI            (A)
│   │   └── score.py              # combined score, classes, patches        (A)
│   ├── viz/
│   │   ├── static_maps.py        #                                          (H)
│   │   └── interactive.py        #                                          (A)
│   └── pipeline.py               # end-to-end runner                       (A)
├── notebooks/                    # 01 download (A), 02 preprocessing (H), 03 features (A),
│                                 # 04 clustering (H), 05 similarity (A), 05b models (H),
│                                 # 06 validation (A)
├── tests/
│   ├── conftest.py               # synthetic_project fixture
│   ├── unit/                     # incl. test_contracts.py
│   └── gates/                    # test_phase0.py … test_phase8.py
├── scripts/                      # check_env, check_large_files, study_area_candidates
├── report/
├── data/  outputs/  logs/        # git-ignored
```

(A) = Abhinav, (H) = Harsh. Ownership details are in [execution_plan.md §6](execution_plan.md#6-working-without-blocking-each-other).

---

## 12. Technology stack and environment

| Area | Libraries |
|---|---|
| Core | Python 3.11, numpy, pandas, pyyaml, pyarrow |
| Raster | rasterio, rioxarray, xarray |
| Vector | geopandas, shapely ≥ 2, pyproj, pyogrio |
| Data access | pystac-client, planetary-computer, osmnx, requests (Overpass) |
| Terrain | numpy-based slope (Horn method), no extra dependency |
| Analysis | scipy, scikit-learn ≥ 1.3 (includes `sklearn.cluster.HDBSCAN`), mapclassify |
| Visualisation | matplotlib, seaborn, contextily, matplotlib-scalebar, folium |
| Dev | jupyterlab, ipykernel, pytest, black, ruff, nbstripout, pre-commit |

**Environment:**
- `environment.yml` uses the **conda-forge** channel.
- Any conda-compatible tool works: conda / Miniforge, mamba or micromamba. Both laptops currently use micromamba (Harsh: Windows, at `C:\micromamba`; Abhinav: Linux).
- Environment name: `gis-suit`. The project is installed in editable mode (`pip install -e .`).
- Pin exact versions (`environment.lock.yml`) once both laptops pass the Phase 0 gate.
- `scripts/check_env.py` checks every library (part of the Phase 0 gate).

---

## 13. Output specifications and data contracts

The contracts are fixed in `src/features/schema.py` and checked by `tests/unit/test_contracts.py`. Changing one needs a PR approved by both. Full table: [execution_plan.md §4](execution_plan.md#4-contracts-between-the-tracks).

| ID | File | Producer | Content |
|---|---|---|---|
| C1 | `data/features/grid.parquet` (+ `.gpkg`) | Abhinav | `cell_id, row, col, x, y` |
| C2 | `data/features/raster_features_{year}.parquet` | Abhinav | own + ring fractions, terrain, `log_dist_built`, `log_dist_water`, `nodata_frac` |
| C3 | `data/features/vector_features_{snapshot}.parquet` | Harsh | road distances, road density, building metrics (leaky) |
| C4 | `data/features/grid_features_{year}.parquet` | Abhinav | C2 + C3 joined on `cell_id` |
| C5 | `data/features/labels.parquet` | Abhinav | `excluded, built_baseline, candidate, grew, chg_train_pos, lei_type` |
| C6 | `data/processed/buildings_{snapshot}.gpkg` | Harsh | `bldg_id, geometry, area_m2, building_type, cell_id` |
| C7 | `outputs/lulc_3class.parquet` (+ `.tif`) | Harsh | `cell_id, cluster_id, class_3` (1 built-up, 2 forest, 3 usable, 255 excluded) |
| C8 | `outputs/scores/{model}.parquet` + `.json` | each model owner | `cell_id, score` (higher = more suitable) + metadata (features used, years, run = validation / final, out-of-fold yes/no) |

**Final outputs:**

| Output | Format | Content |
|---|---|---|
| `outputs/suitability_score.tif` | GeoTIFF float32 | Final combined score 0–1 |
| `outputs/suitability_class.tif` | GeoTIFF uint8 | 1 S1, 2 S2, 3 S3, 4 N |
| `outputs/candidates.gpkg` / `.csv` | GeoPackage, CSV | Patch id, area, mean score, slope, distance to road, distance to built-up |
| `outputs/similarity_query_<id>.gpkg` / `.png` | GeoPackage, PNG | Top-N matches for query building `<id>`, with feature breakdown |
| `outputs/metrics/validation.json` | JSON | AUC, lift, hit rates and LEI split for every model + baseline |
| `outputs/metrics/clustering.json` | JSON | k, silhouette, Davies–Bouldin, agreement |
| `outputs/map.html` | HTML | Interactive map |
| `outputs/figures/*.png` | PNG 300 dpi | All report figures |

---

## 14. Evaluation, validation and success criteria

The project is **complete** when:

1. All deliverables D1–D16 exist.
2. `python -m src.pipeline` runs both runs end to end from a fresh clone (data downloaded) without errors.
3. `pytest` passes: unit, contract and all phase gate tests.
4. `validation.json` holds every model **and** every baseline. The targets in §9.8 are met, or misses are explained in the report.
5. The leakage guards (NFR-10) are enforced by tests.
6. The report explains the method, results, limitations and possible improvements.
7. Every PR has been reviewed by the other teammate.

### 14.1 Final status (2026-10-23)

**Functional requirements**

| Group | Status | Evidence |
|---|---|---|
| FR-1 Configuration | Met | all parameters in `config/config.yaml`; AOI in `config/aoi.geojson` |
| FR-2 Data acquisition | Met | `src/download/`; manifest with checksums and extents; OSM 2018 and current snapshots both pinned by date |
| FR-3 Preprocessing | Met | one 10 m reference grid; rasters copied exactly where possible (`verify_raw_data.py`, `verify_preprocessed.py`) |
| FR-4 Grid, features, labels | Met | C1–C5; persistent growth labels with LEI types |
| FR-5 Land classification | Met | K-Means k = 7, centroid rules, exclusion mask; 96.6 % agreement with ESRI, 64.0 % with WorldCover on land cells |
| FR-6 Similarity and learned models | Met, except per-type similarity (Q7) | single query with explanation, aggregate kNN (AUC 0.773), change RF (0.779), state RF (0.702), out-of-fold scores |
| FR-7 Suitability mapping | Met | MCDA/AHP (CR 0.003), combined score (w = 0.3 / 0.7, chosen on the training label), S1–S3 / N, 557 candidate patches, top 20 sites |
| FR-8 Validation | Met | `src/suitability/validate.py` → `validation.json`: AUC, lift, TOC, LEI split, ablation, S1+S2 hit rate; sensitivity to cell size, slope and k |
| FR-9 Visualisation | Met | 300 dpi maps and charts (`outputs/figures/`), `outputs/map.html` |
| FR-10 Reproducibility | Met | `python -m src.pipeline` with `--from-stage`; full run 12.4 min after the downloads |

**Targets (§9.8):** best model ≥ distance to built-up: **met** (combined score 0.797 vs 0.763). Lift ≥ 2 in the top 10 %: **met** (3.45). Self-query in the top 1 %: **met**. Outlying growth is not predicted by any model (AUC ~0.51), as expected; explained in `docs/validation.md` and the report.

**Deliverables:** D1–D16 all present. The report (D14) and slides (D15) are LaTeX sources in `report/`; their PDFs are built locally (not committed: over the 1 MB file limit).

**Success criteria (§14):**
1. Deliverables: met.
2. Fresh clone → pipeline end to end: met (`scripts/compare_projects.py`; the validation run reproduces exactly).
3. `pytest`: met (unit, contract and phase gates 0–8).
4. `validation.json` with every model and baseline, targets met: met.
5. Leakage guards enforced by tests: met (`check_model_inputs`, time-travel tests, out-of-fold and spatial-fold tests, gate 6).
6. Report: met.
7. PR review by the other teammate: not met for the Phase 6–8 packages, which were committed directly to `main`.

---

## 15. Development phases and timeline

**Deadline: final submission Tue 2026-10-06** (code, report and slides). The full scope is kept.

- Work runs as **two parallel tracks** (§16).
- The execution plan's W1–W10 sequence is compressed into **Thu 1 – Tue 6 October**. Its order, milestones and blocking tasks are unchanged, only the dates move.
- The **sequence, milestones (M1–M4) and blocking tasks** are in [execution_plan.md §3 and §5](execution_plan.md#3-timeline).
- The **phase checklist and gate tests** are in [Tasks.md](Tasks.md).

| Phase | Name | Plan weeks | Target date | Gate test by |
|---|---|---|---|---|
| 0 | Setup and planning | W1 | Thu 10-01 (done) | Harsh |
| 1 | Literature review and data discovery | W1–2 | Fri 10-02 | Abhinav |
| 2 | Data acquisition | W1–2 | Fri 10-02 | Harsh |
| 3 | Preprocessing | W2 | Sat 10-03 | Abhinav |
| 4 | Grid, features and labels | W3–4 | Sat 10-03 | Harsh |
| 5 | Land classification (clustering) | W4–5 | Sun 10-04 | Abhinav |
| 6 | Building similarity and learned models | W6–7 | Sun 10-04 | Harsh |
| 7 | Suitability, validation and sensitivity | W7–8 | Mon 10-05 | Abhinav |
| 8 | Visualisation, report and presentation | W9–10 | Tue 10-06 (submit) | Harsh |

**Milestones:**
- **M1** thin slice: Sat 10-03 morning
- **M2** full feature table: Sat 10-03 evening
- **M3** every model writes a score file: Sun 10-04 evening
- **M4** validation complete: Mon 10-05 evening

A phase is **done** only when its gate passes and both teammates sign off in Tasks.md. Each person writes the gate tests that check the *other* person's work.

---

## 16. Roles and responsibilities

The work is split **by data type, then by model** [execution_plan §1, swapped 2026-10-01 at Abhinav's request]:

| | **Abhinav: raster and similarity track** | **Harsh: vector and learning track** |
|---|---|---|
| Data | ESRI LULC (all years), WorldCover, DEM | OSM roads / water / buildings (2018 + current), protected areas |
| Preprocessing | 10 m reference grid, alignment, slope, class mapping | Road classes, building cleaning, reference buildings (C6) |
| Features | Grid (C1), LULC + ring fractions, terrain, distance to built-up and water (C2), merge (C4) | Road distances, road density, building metrics (C3) |
| Labels | Exclusion mask, growth labels, LEI (C5) | — |
| Models | **Building similarity**: query + aggregate kNN | **Clustering** (C7), **change RF + state RF**, **MCDA/AHP** |
| Evaluation | Validation harness, temporal run, LEI breakdown | Ablation, spatial-CV tuning, sensitivity runs |
| Output | Combined score, interactive map, pipeline runner | Static maps and charts |
| Report | Study area, literature; similarity + validation | Introduction, data; clustering + RF + MCDA |
| Gate tests | Phases 1, 3, 5, 7 | Phases 0, 2, 4, 6, 8 |

**Joint:**
- `schema.py`, `config.yaml`, PRD and Tasks (joint PRs only)
- the literature review synthesis
- the report's discussion and conclusion
- the slides

Both tracks meet only through the contract files (§13). Each develops against the synthetic stubs (`src/synthetic.py`) until the real file lands.

---

## 17. Team workflow and conventions

- **Branches:** `main` always works. Work on `feat/a-<pkg>` / `feat/h-<pkg>`.
- **PRs:** small PRs, reviewed by the other person within 24 h. Link the task ID (e.g. `H1.1`, `P2.5`).
- **Commits:** short and descriptive, present tense. **No Claude / AI co-author lines** (see `docs/CLAUDE.md`).
- **Folder ownership** as in §11 / execution_plan §6. This avoids merge conflicts. Shared files change only in joint PRs.
- **Notebooks:** outputs stripped (pre-commit). Only the owner edits a notebook.
- **Blocked tasks:** never start a 🔒 task before its blocker is ticked. Keep working on the stub instead.
- **Sync:** 15-minute check-in Mon and Thu, plus the milestone reviews.
- **Data:** each person runs the idempotent downloaders. The OSM 2018 snapshot is shared via the drive.

---

## 18. Risks and mitigations

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Overpass historical (`[date:]`) query fails or times out | No 2018 roads/buildings | Medium | Three mirrors, a cached download, a shared-drive copy. Last resort: major roads only (barely leak) |
| Future data leaks into the validation run | Inflated metrics | High if unchecked | Time-travel rule (FR-8.2), OSM snapshots, `check_model_inputs`, out-of-fold RF scores; gate tests assert them |
| Similarity doesn't beat distance-to-built | Weak headline result | Likely (prototype) | Baselines always shown; similarity framed as explainable per-building queries; stretch features |
| ESRI class flicker (tree cover, built-up) | Noisy labels and forest class | High | Persistent labels (two years at each end); WorldCover cross-check; forest year choice documented |
| Bannerghatta looks like "usable" rangeland | Wrong candidates | High without a mask | OSM protected areas in the exclusion mask |
| Contract drift between tracks | Integration breaks | Medium | `schema.py` + contract tests; joint PRs only |
| Spatial autocorrelation inflates CV scores | Over-optimistic tuning | High | Spatial-block CV (2 km); headline metric is temporal, not CV |
| GDAL / environment problems | Blocks setup | Low (both laptops working) | conda-forge env; `check_env.py` |
| One person falls behind | Delays on the critical path | Medium | Milestones M1–M4; stub-based work; rebalance at milestone reviews |
| Tight schedule (deadline 2026-10-06) | Incomplete deliverables | Medium | Full scope kept. Only if a milestone slips, drop in this order: sensitivity → LEI breakdown → state RF → cell-size runs. Always keep clustering, similarity, change RF, MCDA, temporal validation |

---

## 19. Assumptions and dependencies

- Free access to Microsoft Planetary Computer STAC (signing via `planetary-computer`).
- Overpass API (or a mirror) supports `[date:]` historical queries for the AOI.
- The ESRI IO LULC v02 "built area" class is consistent enough between years once persistence is required.
- Both laptops have ≥ 8 GB RAM and ~10 GB free disk.
- **Key assumption, stated in the report:** existing buildings and past growth are a reasonable signal of suitable land. Past development reflects past decisions (and regulation), which are not always good planning.

---

## 20. Open questions

| # | Question | Status |
|---|---|---|
| Q1 | Study area | **Closed:** Bengaluru South [D1], confirmed by Harsh 2026-10-01 |
| Q2 | Submission deadline and intermediate reviews | **Closed:** final submission Tue 2026-10-06 |
| Q3 | Report format / length required by the instructor | **Closed:** no format was given; the working default was delivered (20-page A4 PDF report, author–year references, 300 dpi figures; 17 slides) |
| Q4 | Grid cell size | **Closed:** 100 m; 50 / 200 m in the sensitivity runs |
| Q5 | Cropland usable or excluded? | **Closed:** usable but flagged [D10] |
| Q6 | Slope threshold | **Closed:** 15° [D10]; revisited in the sensitivity runs |
| Q7 | Similarity per building type? | **Closed: not feasible:** 99.5 % of the 2018 and 94 % of the current OSM buildings are untyped (`building=yes`) |
| Q8 | Accept rules D11 (out-of-fold RF scores) and D12 (time-travel rule)? | **Closed:** agreed by both, 2026-10-01 (§9.9) |
| Q9 | Refine the AOI from the bbox to a planning boundary? | **Closed:** kept the 582 km² rectangle (all results and the sensitivity runs use it) |

---

## 21. Glossary

| Term | Meaning |
|---|---|
| **LULC** | Land Use Land Cover: a map that labels each pixel with a land type (forest, water, built-up, etc.) |
| **AOI** | Area of Interest: the study area |
| **CRS** | Coordinate Reference System. A projected CRS (e.g. UTM) uses metres |
| **STAC** | SpatioTemporal Asset Catalog: a standard API for searching satellite data |
| **DEM** | Digital Elevation Model: a raster of ground height |
| **Grid cell** | A 100 m × 100 m square: one row in the feature table |
| **Ring fraction** | The share of a land class in the window around a cell, excluding the cell itself |
| **Contract (C1–C8)** | A file with a fixed format that one track produces and the other consumes |
| **Stub** | Fake data with the right columns, used to develop before the real file exists |
| **Persistent growth** | Non-built in 2018 and 2019, built in 2022 and 2023: ignores single-year classifier flicker |
| **LEI** | Landscape Expansion Index: classifies a new built-up patch by how much it touches existing built-up (adjacent vs outlying) |
| **Change RF** | A Random Forest trained on which 2018 surroundings preceded growth |
| **MCDA / AHP** | Multi-Criteria Decision Analysis / Analytic Hierarchy Process: expert-weighted overlay |
| **ROC-AUC** | How well a score separates positives from negatives. 0.5 = random, 1.0 = perfect |
| **TOC** | Total Operating Characteristic: like ROC, but also shows the number of cells flagged at each threshold |
| **Lift** | Hit rate in the top N ÷ hit rate expected at random |
| **Data leakage** | When a model input secretly contains the answer, which inflates accuracy |
| **Out-of-fold score** | A cell's score from a model trained without that cell's spatial block |
| **Time-travel rule** | Nothing dated after the baseline may feed a validation-run score |
| **S1 / S2 / S3 / N** | FAO-style suitability classes: highly, moderately, marginally, not suitable |

---

## 22. References

Starting points. The literature review (J6) extends these to ≥ 10 papers.

- Malczewski, J. (2004). *GIS-based land-use suitability analysis: a critical overview.* Progress in Planning, 62(1), 3–65.
- Saaty, T. L. (1980). *The Analytic Hierarchy Process.* McGraw-Hill.
- FAO (1976). *A Framework for Land Evaluation.* FAO Soils Bulletin 32.
- Karra, K. et al. (2021). *Global land use / land cover with Sentinel 2 and deep learning.* IGARSS 2021 (ESRI / Impact Observatory LULC).
- Zanaga, D. et al. (2022). *ESA WorldCover 10 m 2021 v200.* ESA WorldCover project.
- Liu, X. et al. (2010). *A new landscape index for quantifying urban expansion using multi-temporal remotely sensed data.* Landscape Ecology, 25, 671–682 (LEI).
- Pontius, R. G. Jr. & Si, K. (2014). *The total operating characteristic to measure diagnostic ability for multiple thresholds.* International Journal of Geographical Information Science, 28(3), 570–583 (TOC).
- Dataset docs:
  - Microsoft Planetary Computer catalog (`io-lulc-annual-v02`, `esa-worldcover`, `cop-dem-glo-30`)
  - Overpass API `[date:]` documentation
  - ohsome API (OSM history)

---

## 23. Change log

| Date | Version | Change | By |
|---|---|---|---|
| 2026-09-27 | 1.0 | Initial PRD | Harsh |
| 2026-10-01 | 1.1 | Aligned with execution_plan decisions D1–D10 and the swapped tracks. Main changes: study area; ESRI as the LULC source for everything; years 2018–2023 with persistent labels; OSM snapshots; leakage rule D4; Euclidean similarity; change RF; LEI; contracts C1–C8; baselines-first validation. Added rules D11 (out-of-fold RF scores) and D12 (time-travel rule), pending Abhinav's agreement | Harsh |
| 2026-10-01 | 1.1 | Phase 0 close-out: study area confirmed; deadline 2026-10-06 recorded; plan compressed into 1–6 October with full scope | Harsh |
| 2026-10-23 | 1.2 | Final status (§14.1): requirements, targets, deliverables and success criteria marked met / not met; Q3, Q7, Q9 closed; current OSM snapshot pinned to 2026-10-01 | Abhinav |
