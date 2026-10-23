# Tasks

Task tracker for **GIS-Based Land Suitability Analysis for Urban Development**. Requirements and method details are in [PRD.md](PRD.md).

## How to use this file

- Each task has an **ID** (`P<phase>.<n>`), an **owner**, and the **PRD requirement** it covers.
- Tick the box (`- [x]`) in the **same PR** that completes the task.
- Owners: **Harsh**, **Abhinav**, or **Both** (both must contribute; split noted in the task).
- The reviewer of a task is the other teammate, unless the task is marked **Both**.
- Every phase ends with a **Phase Gate**:
  1. **Automated check:** `pytest tests/gates/test_phaseN.py` must pass.
  2. **Manual checklist:** every item must be ticked.
  3. **Sign-off:** both teammates tick their name.
- **Do not start the next phase's dependent tasks until the gate passes.** Independent tasks (e.g. report writing) may start early.

**Deadline: final submission Tue 2026-10-06.** Phase dates below follow the day plan in PRD §15.

**Status legend:** `- [ ]` not started · `- [~]` in progress (write `[~]` by hand) · `- [x]` done

---

## Progress overview

| Phase | Name | Harsh | Abhinav | Both | Gate test by | Gate passed |
|---|---|---|---|---|---|---|
| 0 | Setup and planning | 6 (6 done) | 4 (4 done) | 2 (1 done) | Harsh | ✅ 35/35, signed by both |
| 1 | Literature review and data discovery | 3 | 3 | 2 | Abhinav | ✅ 14/14, signed by both |
| 2 | Data acquisition | 4 | 4 | 1 | Harsh | ✅ 87/87 on Harsh's laptop (72/72 + area checks), signed by both |
| 3 | Preprocessing | 3 | 4 | 2 | Abhinav | ✅ 44/44, signed by both |
| 4 | Grid and feature engineering | 4 | 4 | 1 | Harsh | ✅ 19/19 (Harsh signed; Abhinav pending) |
| 5 | Land classification (clustering) | 3 | 5 | 1 | Abhinav | ✅ 9/9 (Harsh signed; Abhinav pending) |
| 6 | Building similarity | 4 | 4 | 1 | Harsh | ☐ |
| 7 | Suitability mapping and validation | 4 | 4 | 1 | Abhinav | ☐ |
| 8 | Visualisation, report and presentation | 5 | 5 | 3 | Harsh | ☐ |
| | **Total** | **36** | **37** | **14** | 5 / 4 | |

Ownership in short: **Harsh** leads the raster/LULC pipeline, building similarity, suitability scoring, temporal validation and the pipeline runner. **Abhinav** leads OSM/vector data, distance features, clustering, the Random Forest model, the MCDA baseline and static maps. Gate tests alternate between the two, so each person checks the other's phase work.

---

## Phase 0 — Setup and planning

**Goal:** a working shared repo and environment on both laptops, agreed conventions, and a chosen study area.
**Depends on:** nothing. **Target:** Thu 2026-10-01 (done).

### Todos

- [x] **P0.1** Create GitHub repo, first commit, push to `main`. — **Harsh**
- [x] **P0.2** Add `.gitignore` (Python, data, rasters, vectors). — **Harsh**
- [x] **P0.3** Add `docs/CLAUDE.md`, root `CLAUDE.md` pointer, `.claude/settings.json` (no AI attribution). — **Harsh**
- [x] **P0.4** Write PRD and Tasks. — **Harsh**
- [x] **P0.5** Add Abhinav as a collaborator on GitHub; Abhinav clones the repo. — **Harsh** · *Done: Abhinav is a collaborator and has merged PRs #1 and #2.*
- [x] **P0.6** Create `environment.yml` (conda-forge, Python 3.11, all libraries from PRD §12) and `scripts/check_env.py`. — **Harsh** · PRD NFR-1, NFR-3
- [x] **P0.7** Create the folder skeleton from PRD §11 (`src/` subpackages with `__init__.py`, `notebooks/`, `tests/unit/`, `tests/gates/`, `config/`, `outputs/`, `report/`) and `pyproject.toml` (black, ruff, pytest config). — **Abhinav** · NFR-4 · *Done by Harsh; `data/`, `outputs/`, `logs/` are git-ignored and created by `Config.ensure_dirs()`.*
- [x] **P0.8** Set up `pre-commit` with `black`, `ruff`, `nbstripout`. — **Abhinav** · NFR-6 · *Done by Harsh; hooks run the env's own tools (plus a 1 MB file-size guard), so run `pre-commit install` inside `gis-suit`.*
- [x] **P0.9** Propose 3 candidate study areas that meet PRD §5.1. For each, give: approx. area (km²), a screenshot of WorldCover, an OSM building coverage check, and visible growth 2017→2023. Write it up in `docs/study_area.md`. — **Abhinav** · PRD §5 · *14 areas checked with `scripts/study_area_candidates.py` (persistent 2018→2023 growth, OSM buildings in 2018 and 2026). Recommends Bengaluru South, then Hyderabad West; Pune West as fallback.*
- [x] **P0.10** Choose the study area together; draw `config/aoi.geojson`; set the UTM EPSG code. — **Both** · Q1 · *Bengaluru South adopted as the default (see `docs/execution_plan.md` §2). AOI = the study-area bbox (582 km², EPSG:32643 via `crs.epsg: auto`). Confirmed by Harsh 2026-10-01; the polygon can still be refined (PRD Q9).*
- [x] **P0.11** Write `config/config.yaml` and `src/config.py` (load + validate: AOI valid polygon, CRS projected, cell size > 0). — **Abhinav** · FR-1.1, FR-1.2 · *Done by Harsh, with 15 unit tests in `tests/unit/test_config.py`. `crs.epsg: auto` picks the UTM zone from the AOI, so P0.10 only needs the polygon + `aoi.name`.*
- [~] **P0.12** Find out the deadline, intermediate reviews and report format from the instructor; update PRD §15 and §20. — **Both** (Harsh: deadline/reviews, Abhinav: report format) · Q2, Q3 · *Deadline: **final submission Tue 2026-10-06** (Harsh, recorded in PRD §15). Report format: not yet specified by the instructor; a working default is recorded in PRD §20 Q3 (Abhinav, 2026-10-01). Replace it once the instructor answers.*

### Phase 0 Gate

**Automated — `tests/gates/test_phase0.py`** (written by **Harsh**):
- [x] Every library in `environment.yml` imports (`scripts/check_env.py` exits 0).
- [x] `config/config.yaml` loads through `src/config.py` without error.
- [x] `config/aoi.geojson` has exactly one valid polygon; area between 50 and 1,500 km² when projected.
- [x] The configured CRS is projected with units in metres.
- [x] `aoi.name` in the config is set (not `TBD`).
- [x] All tracked folders from PRD §11 and the key files exist; every `src/` subpackage has `__init__.py`.

Status on Harsh's laptop (2026-09-27): **30 passed, 5 failing**. All 5 need the AOI.
Status on Abhinav's laptop (2026-10-01, Linux, micromamba): **35 passed** (+ 15 unit tests), with the Bengaluru South AOI.
Status on Harsh's laptop (2026-10-01, Windows, micromamba): **35 passed**; full suite 82 passed, 1 skipped.

**Manual checklist:**
- [x] Both teammates created the conda env and ran `pytest tests/gates/test_phase0.py` successfully on **their own laptop**. *(Abhinav and Harsh: 35 passed, 2026-10-01)*
- [x] `pre-commit run --all-files` passes.
- [x] `docs/study_area.md` states the chosen AOI and the reason.
- [x] Deadline is recorded in PRD, and phase dates in this file are adjusted.

**Sign-off:** - [x] Harsh *(2026-10-05: gate passes on Harsh's laptop)*  - [x] Abhinav *(2026-10-01: gate passes on Abhinav's laptop)*

---

## Phase 1 — Literature review and data discovery

**Goal:** understand prior work and lock in the datasets.
**Depends on:** P0.10 (study area) for the coverage checks. **Target:** Fri 2026-10-02.

### Todos

- [x] **P1.1** Create `docs/literature_review.md` with a template matrix: title, authors, year, venue, study area, data used, method, criteria/features, validation, key findings, relevance to us. — **Abhinav** · *File and matrix created by Harsh with the P1.1 fields; rows A1–A6 pre-filled as suggestions for Abhinav to review.*
- [x] **P1.2** Review ≥ 5 papers on **GIS/MCDA land suitability and urban growth using LULC** (AHP, weighted overlay, FAO framework, LULC change). — **Abhinav** · G2 · *A1–A6 reviewed and completed from abstracts / open full texts; all DOIs verified on Crossref (`scripts/verify_literature.py`). **Correction:** the suggested A5 studies Delhi, not Bengaluru, so it was replaced by Ramachandra, Aithal & Sanna (2012), a Bangalore paper (built-up +584 %, vegetation −66 %, water bodies −74 % over four decades). A6 covers Delhi, Mumbai, Pune, Chennai and Coimbatore. A few details are marked *(to verify)* against full texts.*
- [x] **P1.3** Review ≥ 5 papers on **ML / clustering / similarity for land classification and site selection** (K-Means/GMM on land features, RF urban growth models, spatial CV). — **Harsh** · G2 · *Papers H1–H10 in `docs/literature_review.md`; a few details marked "to verify" against full texts.*
- [x] **P1.4** Write a 1-page synthesis in the review: common criteria, typical weights, common validation methods, and the gap our similarity approach fills. — **Both** (Abhinav: MCDA part, Harsh: ML part) · *Both halves done. Abhinav's MCDA part covers common criteria, weights, validation and the gap. Combined conclusion drafted by Abhinav; **Harsh to review**. Paper ids and decision ids are now written apart ("paper D1" vs "decision D7"). Checked by `scripts/verify_literature.py`.*
- [x] **P1.5** Check coverage and access for WorldCover (2020, 2021), ESRI Annual LULC (2017–2023) and Copernicus DEM over the AOI via Planetary Computer STAC. Record item IDs, tiles and sizes. — **Harsh** · PRD §7 · *Done with `scripts/check_data_coverage.py` for the D2/D3 years (ESRI 2018–2023, WorldCover 2021, DEM): one tile each, all cover AOI + buffer. See `docs/data_sources.md` §2.*
- [x] **P1.6** Check OSM coverage in the AOI: count buildings, road length and water features with a quick `osmnx` query. Decide whether a fallback building dataset (Microsoft / Google Open Buildings) is needed. — **Abhinav** · PRD §7, Risk 1 · *Done by Harsh (OSM is his track) with the ohsome API, 2018 vs 2026: 151k → 187k buildings, roads 3,889 → 8,730 km. **Decision: OSM only, no fallback.** See `docs/data_sources.md` §3.*
- [x] **P1.7** Write `docs/data_sources.md`: final dataset list, versions, years, licences, access method, and known issues. — **Harsh** · *Raster sections drafted for Abhinav to review; class mapping (§6) follows with A2.3; shared-drive link with H1.5.*
- [x] **P1.8** Decide the baseline and latest year for temporal validation (e.g. 2017 → 2023), and confirm there is visible growth between them. — **Both** · FR-8.1 · *D3: 2018 + 2019 → 2022 + 2023 (change-RF positives 2020 + 2021), set in `config.yaml`; 8.4 % persistent growth of non-built land (`study_area.md`).*

### Phase 1 Gate

**Automated — `tests/gates/test_phase1.py`** (written by **Abhinav**):
- [x] `docs/literature_review.md` exists and contains ≥ 10 paper entries (count matrix rows). *(18; plus ≥ 5 per half, a detail entry per row, synthesis written)*
- [x] `docs/data_sources.md` exists and lists WorldCover, ESRI LULC, DEM and OSM, each with licence and access method.
- [x] A STAC search for each raster collection over the AOI bbox returns ≥ 1 item (network test, marked `@pytest.mark.network`).

Status on Abhinav's laptop (2026-10-01): **14 passed** (11 offline + 3 network). The gate was mutation-tested: 7 deliberate breakages of the docs (9 papers, 4 A-papers, synthesis unwritten, missing detail entry, missing licence / dataset / access method) were all caught.

**Manual checklist:**
- [x] Each teammate has read the other's paper summaries. *(Abhinav ☑ 2026-10-01: read and verified H1–H10, D1–D2; H2, H3, H5 and H8 checked against full texts, their "to verify" fields filled. Harsh ☑ 2026-10-05: A1–A6.)*
- [x] The synthesis section clearly states what our project adds. *(Combined conclusion, points 1–4; Harsh to confirm at sign-off.)*
- [x] Building data source decided (OSM only, or OSM + fallback). *(OSM only)*
- [x] Temporal validation years fixed in `config.yaml`.

**Sign-off:** - [x] Harsh *(2026-10-05: gate passes on Harsh's laptop)*  - [x] Abhinav *(2026-10-01: gate passes on Abhinav's laptop)*

---

## Phase 2 — Data acquisition

**Goal:** all raw data downloaded reproducibly and recorded in a manifest.
**Depends on:** Phase 1 gate. **Target:** Fri 2026-10-02.

### Todos

- [x] **P2.1** Write `src/io_utils.py`: manifest read/write (`data/manifest.json`), SHA-256 checksum, "skip if exists and checksum matches" helper, logging setup. — **Harsh** · FR-2.5, FR-2.6, NFR-9
- [x] **P2.2** Write `src/download/lulc.py`: download ESA WorldCover (AOI + 1 km buffer) via STAC, mosaic tiles if needed. — **Harsh** · FR-2.1
- [x] **P2.3** Extend `lulc.py`: download ESRI Annual LULC for the baseline and latest years. — **Harsh** · FR-2.2
- [x] **P2.4** Write `src/download/dem.py`: download Copernicus DEM GLO-30 (AOI + buffer). — **Abhinav** · FR-2.3
- [x] **P2.5** Write `src/download/osm.py`: download roads (keep the `highway` tag), water (`natural=water`, `waterway=*`) and buildings (`building=*`) with osmnx. Save as GeoPackage. — **Abhinav** · FR-2.4 · *Done by Harsh (OSM is his track, H1.1–H1.4): 2018 snapshot (`[date:]`) + current, plus protected areas; 9 unit tests. Details and Overpass workarounds in `docs/data_sources.md` §5.*
- [x] **P2.6** If needed (from P1.6): download fallback building footprints (Microsoft / Google Open Buildings) for the AOI. — **Abhinav** · Risk 1 · *Not needed: OSM only (P1.6), 179,740 buildings in the 2018 snapshot.*
- [x] **P2.7** Add retries and clear error messages to all downloaders. — **Abhinav** · FR-2.6 · *Rasters: `io_utils.retry` (Abhinav). OSM: retries per mirror, 3-mirror fallback, clear final error (Harsh).*
- [x] **P2.8** Create `notebooks/01_data_download.ipynb`: calls the download functions and shows quick-look plots of each layer over the AOI. — **Harsh** · FR-10.1
- [x] **P2.9** Unit tests: manifest round-trip, checksum, skip-if-exists logic (with temporary files). — **Both** (Harsh: io_utils tests, Abhinav: downloader error-handling tests with mocked network) · *`tests/unit/test_io_download.py` (Abhinav) + `tests/unit/test_osm_download.py` (Harsh).*

### Phase 2 Gate

**Automated — `tests/gates/test_phase2.py`** (written by **Harsh**):
- [x] Every expected raw file exists: WorldCover, ESRI LULC × 2 years, DEM, roads, water, buildings. *(ESRI 2018–2023; OSM 2018 + current; protected areas)*
- [x] Every raster opens with rasterio, has a CRS and nodata defined, and its bounds cover the AOI bbox.
- [x] Every vector opens with geopandas, has a CRS, and is non-empty. *(plus: 2018 snapshot smaller than current; building / lake counts ≥ 95 % of ohsome; Bannerghatta NP present)*
- [x] LULC rasters contain only valid class codes (WorldCover: {10,20,…,100} + nodata; ESRI: documented codes).
- [x] `data/manifest.json` has one entry per file, and the stored checksums match the files on disk.
- [x] Rerunning the downloads doesn't re-download (checks file modified times). *(checked via `needs_download`, which the downloaders use to skip)*

**Manual checklist:**
- [x] Quick-look plots in notebook 01 visually match the real area (compare with Google Maps / OSM). *(Rasters, Abhinav 2026-10-01: notebook 01 maps, plus landmark checks against OSM Nominatim coordinates in `scripts/verify_raw_data.py`: Madiwala Lake = water, Electronic City and Koramangala = built; pixel values equal the source COGs. OSM: 2018 vs current quick-look checked by Harsh; layers line up with the AOI.)*
- [x] Both teammates have the full raw data locally (via download or shared drive link recorded in `docs/data_sources.md`). *(Harsh: all files, gate 72/72 on 2026-10-01, for the old 1 km buffer. Abhinav ☑ 2026-10-01: all rasters and both OSM snapshots for the 3 km buffer, on a USB drive linked as `data/`. OSM was downloaded on another network, because Overpass is blocked on the campus network. Phase 2 gate 72/72. Harsh ☑ 2026-10-05: OSM re-downloaded for the 3 km buffer (the downloader now redoes files whose recorded area differs, and the gate checks every file covers the configured area). Overpass timed out behind a VPN; it worked once the VPN was off.)*
- [x] Unit tests pass: `pytest tests/unit`. *(56 passed, 1 skipped, 2026-10-01)*

**Sign-off:** - [x] Harsh *(2026-10-05: gate 87/87 on Harsh's laptop after re-downloading OSM for the 3 km buffer)*  - [x] Abhinav *(2026-10-01: gate 72/72 on Abhinav's laptop; full suite 226 passed)*

---

## Phase 3 — Preprocessing

**Goal:** every layer is clipped, in the project CRS, aligned to one reference grid, and clean.
**Depends on:** Phase 2 gate. **Target:** Sat 2026-10-03.

### Todos

- [x] **P3.1** Write `src/preprocess/raster.py`: reproject to the project CRS, clip to AOI + buffer, align to a reference grid (WorldCover at 10 m is the reference). Nearest-neighbour for categorical, bilinear for continuous. Set nodata consistently. — **Harsh** · FR-3.1–3.3
- [x] **P3.2** Write `src/preprocess/terrain.py`: slope (degrees, Horn method) and aspect from the aligned DEM. — **Harsh** · FR-3.6
- [x] **P3.3** Harmonise ESRI LULC classes with WorldCover (mapping table in `src/preprocess/raster.py` + `docs/data_sources.md`), so temporal validation uses the same "built-up" definition. — **Harsh** · FR-8.1
- [x] **P3.4** Write `src/preprocess/vector.py`: reproject, clip, fix invalid geometries (`make_valid`), drop empties, explode multi-parts where needed. — **Abhinav** · FR-3.4 · *`python -m src.preprocess.vector`: reproject, clip to the reference grid, `make_valid`, drop empties, explode lines → `data/processed/osm/<snapshot>/<layer>.gpkg`. Checked by `scripts/verify_vectors.py`: drivable road length is conserved exactly after clipping; layers line up with ESRI within one pixel. Fixes after review (P4 week): waterways are now exploded like roads (2 MultiLineStrings in the current snapshot); an empty selection no longer crashes `clean_geometries`; building centroid columns renamed `cx`/`cy` → `centroid_x`/`centroid_y` (they shadowed GeoDataFrame's `.cx` indexer); the Phase 3 gate now also checks the grid extent and single-part lines.*
- [x] **P3.5** Classify roads into `major` / `minor` by `highway` tag (PRD FR-3.5); drop footpaths / tracks if configured. — **Abhinav** · FR-3.5 · *Major = motorway–secondary + links, minor = tertiary, residential, unclassified, service, living_street, road; tracks dropped unless `vector.keep_tracks`. 2018: 760 km major / 5,401 km minor. **2018 major roads in the AOI: 448 km, matching ohsome's 448 km.***
- [x] **P3.6** Clean buildings: remove tiny (< 10 m²) and huge outlier footprints; compute centroid, area and `building` type; dedupe fallback + OSM footprints if both are used. — **Abhinav** · *Drop < 10 m² and > 100,000 m² (largest real footprint 70,584 m²); add area, centroid, type and `cell_id` → C6. **2018: 151,257 buildings in AOI cells vs ohsome 151,374 (−0.1 %)**; current 192,727. No fallback dataset, so no deduplication needed.*
- [x] **P3.7** Create `notebooks/02_preprocessing.ipynb`: before/after plots and a table of CRS, resolution, shape and nodata % per layer. — **Abhinav** · FR-10.1 · *`notebooks/02_preprocessing.ipynb`: runs the preprocessing (skips existing outputs), a table of every processed layer (all 9 rasters on the reference grid with 0 % nodata; 7 vector layers in EPSG:32643), before/after plots and vector counts. Runs end to end.*
- [x] **P3.8** Unit tests on synthetic data: reprojection keeps category values, slope of a known plane equals the expected angle, road classification mapping. — **Both** (Harsh: raster/terrain tests, Abhinav: vector tests) · *Vector tests done: `tests/unit/test_preprocess_vector.py` (19). Raster / terrain tests (category values kept, exact slope on planes) done in A2: `tests/unit/test_preprocess_raster.py`.*
- [x] **P3.9** Visual overlay check in the notebook: roads, water and buildings drawn over LULC line up correctly (no shifts). — **Both** · *Notebook 02 §4 + `outputs/figures/verify_vectors*.png`: roads, lakes, buildings and Bannerghatta line up with ESRI. At Madiwala Lake the OSM outline (and its island) matches the ESRI water / tree pixels. The ~5–10 m OSM vs Sentinel-2 offset is in the source data (under one pixel). Checked by Abhinav; Harsh to review.*

### Phase 3 Gate

**Automated — `tests/gates/test_phase3.py`** (written by **Abhinav**):
- [x] All processed rasters have **identical** CRS, transform, width and height.
- [x] All processed rasters and vectors use the project CRS from the config.
- [x] Processed LULC contains only valid codes (resampling didn't create new values).
- [x] Slope values are within [0, 90] and elevation is within a plausible range for the AOI (config min/max).
- [x] All vector geometries are valid and non-empty; roads have a `road_class` column with values in {major, minor}.
- [x] Nodata share within the AOI is < 5 % for every raster.
- [x] *(added)* C6 buildings exist for both snapshots, pass the contract and lie in grid cells (FR-3.6).

Status on Abhinav's laptop (2026-10-01): **40 passed** (`config.qa.elevation_range_m` = 600–1,200 m). The gate was mutation-tested: 9 deliberate breakages of a scratch copy (raster shifted 10 m, invented class code, slope 95°, elevation 1,500 m, 12.6 % nodata, vector in EPSG:4326, road_class 'path', invalid polygon, C6 building outside the grid) were all caught.

**Manual checklist:**
- [x] Overlay plot (P3.9) reviewed by both: no misalignment visible. *(Abhinav ☑; Harsh ☑ 2026-10-05: in `verify_vectors_zoom.png` (Electronic City) buildings sit on ESRI built-up pixels, roads run between them)*
- [x] Slope map looks sensible (hills steep, plains flat). *(Steep only in the Bannerghatta hills (south-west); lakes 0°, the dense city under 2°: `scripts/verify_preprocessed.py`)*
- [x] ESRI → WorldCover class mapping documented. *(`docs/data_sources.md` §6, `harmonise_worldcover`)*

**Sign-off:** - [x] Harsh *(2026-10-05: gate 44/44 on Harsh's laptop)*  - [x] Abhinav *(2026-10-01: gate 40/40 on Abhinav's laptop)*

---

## Phase 4 — Grid and feature engineering

**Goal:** one feature table with a row per grid cell and all PRD §9.3 features.
**Depends on:** Phase 3 gate. **Target:** Sat 2026-10-03.

### Todos

- [x] **P4.1** Write `src/features/grid.py`: square grid of `cell_size` over the AOI, with `cell_id`, row, col and centroid; keep cells whose centre is inside the AOI. — **Harsh** · FR-4.1
- [x] **P4.2** Write `src/features/lulc_features.py`: per-cell class fractions from the 10 m LULC (block aggregation on the aligned raster, not slow polygon zonal stats). For both the baseline and latest years. — **Harsh** · FR-4.2
- [x] **P4.3** Terrain features per cell: `elev_mean`, `slope_mean`, `slope_max`. — **Harsh** · FR-4.2
- [x] **P4.4** Write `src/features/distance.py`: distance transforms (`scipy.ndimage.distance_transform_edt` with correct pixel size) for major road, any road, water and built-up; sample at cell centroids; cap and log-transform. — **Abhinav** · FR-4.2 · *Done (C3). Road distances are exact point-to-line distances (shapely STRtree nearest) instead of an EDT on rasterised roads: no rasterisation error, and as fast. Water and built-up distances come from the rasters (`src/features/proximity.py`, C2). Verified by `scripts/verify_vector_features.py` (matches `shapely.distance` to 1e-12 m). Caveat: in 4.1 % of cells the 2018 network has a road > 50 m closer than today; 82 % of those are ways retagged `highway=track` since 2018 (tracks are dropped), 13 % deleted/merged in OSM. Consistent within each snapshot, so it doesn't break the time-travel rule.*
- [x] **P4.5** Road density within 500 m, and building count / area fraction per cell (for analysis only; flagged as leaky). — **Abhinav** · FR-4.2, FR-6.6 · *Done (C3). Density = road length in the disk of cells within 500 m (81 cells, 0.81 km²), normalised by the cells on the lattice at the edge; r = 1.000 and 2–3 % median error against an exact 500 m circle. Medians: 3.0 km/km² (2018) vs 12.4 (current).*
- [x] **P4.6** Write `src/features/context.py`: focal means at 250 m and 500 m for base features; the "surrounding ring" built-up fraction (excluding the centre cell). — **Harsh** · FR-4.3
- [ ] **P4.7** Optional: NDVI (Sentinel-2 median composite) and WorldPop density. — **Abhinav** · PRD §7.2 · *Skipped for now (optional; time goes to Phases 5–7). Revisit only if time is left.*
- [x] **P4.8** Write `src/features/build.py` to assemble everything into `data/features/grid_features.parquet` (+ `.gpkg` with geometry); log dropped cells (> 50 % nodata). Create `notebooks/03_feature_engineering.ipynb` with a map of each feature, histograms and a correlation matrix. — **Abhinav** · FR-4.4, FR-4.5 · *Done. `python -m src.features.build` writes `grid_features_{2018,2023}.parquet` + `.gpkg` (2018 features use the 2018 OSM snapshot). 58,218 cells, none dropped (> 50 % nodata). Full rebuild (C2 + C3 + C4) 0.4 min. Verified by `scripts/verify_feature_table.py`. Five pairs with |r| > 0.9 (250 m vs 500 m rings of the same class, slope mean vs max): all kept in C4, decision in notebook 03. Road density rises even in the old urban core between snapshots: OSM mapping completeness, not construction.*
- [x] **P4.9** Unit tests: grid cell count and area on a synthetic AOI; fractions on a synthetic raster; distance transform of a single-pixel target gives the correct metres. — **Both** (Harsh: grid/fractions/context, Abhinav: distance/density) · *Grid, fractions, rings and raster distances done (`tests/unit/test_features_raster.py`); road distance/density done (`tests/unit/test_features_vector.py`).*

### Phase 4 Gate

**Automated — `tests/gates/test_phase4.py`** (written by **Harsh**):
- [x] The feature table row count equals the number of grid cells minus logged drops; `cell_id` is unique.
- [x] All PRD §9.3 core columns are present *(list in `schema.RASTER_FEATURES + VECTOR_FEATURES`)*.
- [x] For each cell, the LULC fractions sum to 1 ± 0.01.
- [x] Distances ≥ 0; slope in [0, 90]; no infinite values; NaN share per column < 1 %. *(also: distances ≤ `distance_cap_m`, slope_mean ≤ slope_max)*
- [x] Leaky columns (`frac_built`, `bldg_count`, `bldg_area_frac`) are listed in a `LEAKY_FEATURES` constant. *(also: no own-cell or leaky column is in `MODEL_INPUTS`; `check_model_inputs` rejects them)*
- [x] Spot check: a cell containing a known major road has `dist_road_major` ≤ `cell_size`. *(every cell a major road crosses, both snapshots)*
- [x] *(added)* Road distances equal `shapely.distance` for 300 random cells; the grid tiles the AOI; the baseline table's road / building columns come from the 2018 OSM snapshot (time-travel rule); OSM building counts agree with ESRI built-up.

Status on Harsh's laptop (2026-10-05): **19 passed**. Mutation-tested: 10 deliberate breakages of in-memory copies (current OSM in the baseline table, a dropped row, fractions +0.05, infinite / over-cap distance, 2 % NaN, major-road distances +150 m (two checks), shuffled building counts, a grid cell outside the AOI) were all caught.

**Manual checklist:**
- [x] Feature maps in notebook 03 look spatially sensible (distance grows away from roads, etc.).
- [x] Highly correlated features (|r| > 0.9) noted, with a decision on whether to drop them.
- [x] Feature build runs in < 10 min. *(0.4 min)*

**Sign-off:** - [x] Harsh *(2026-10-05: gate 19/19 on Harsh's laptop)*  - [x] Abhinav *(2026-10-22: gate 19/19 on Abhinav's laptop; `verify_feature_table.py` passes)*

---

## Phase 5 — Land classification (clustering)

**Goal:** a three-class map (built-up / forest / usable) from clustering, evaluated and explained.
**Depends on:** Phase 4 gate. **Target:** Sun 2026-10-04.

### Todos

- [x] **P5.1** Write `src/classify/cluster.py`: feature selection, standardisation, optional PCA (≥ 90 % variance). — **Abhinav** · FR-5.1 · *Done: `src/classify/cluster.py`. Inputs in `config → clustering.inputs`: frac_water, frac_tree, frac_crop, frac_built, frac_range, elev_mean, slope_mean (frac_snow constant, frac_flooded/frac_bare ~0, slope_max r = 0.95 with slope_mean). Standardised; PCA reported (5 PCs for 90 %; the 7th explains 0.03 % because the fractions nearly sum to 1) but not used.*
- [x] **P5.2** K-Means for k = 3…10: elbow (inertia) and silhouette plots; pick k with justification. — **Abhinav** · FR-5.2, FR-5.3 · *Done: scan k = 3…10 in `outputs/metrics/clustering.json`. Silhouette plateaus at k = 5–8 (0.57–0.61) and drops at k = 9 (0.45). **k = 7** (2018: 0.585, DB 0.819; 2023: 0.606, DB 0.827): best or within 0.003 of best in both years, and the two clusters beyond k = 5 are interpretable and appear in both years: steep rangeland (slope ~13°, Bannerghatta hills, 3–4 %) and the low western valley (≈ 760 m, mixed crop/built, 3–4 %). Plots in notebook 04 (P5.7).*
- [x] **P5.3** Alternative: GMM (choose components by BIC) and/or HDBSCAN; compare with K-Means (silhouette, Davies–Bouldin, maps). — **Abhinav** · FR-5.2 · *Done: GMM (full covariance) scanned for k = 3…10; silhouette 0.26–0.36 and DB 1.6–2.9 at every k, BIC keeps falling up to k = 10 (no clear minimum), so K-Means is kept. HDBSCAN (optional) not run. Verified by `scripts/verify_clustering.py` (K-Means fixed point, Davies–Bouldin by hand, OSM landmarks: Bellandur Lake → water cluster, 96–98 % of Bannerghatta → tree/rangeland clusters).*
- [x] **P5.4** Write `src/classify/label.py`: rule table mapping clusters → built-up / forest / usable / excluded from centroids (PRD §9.4); thresholds in config. — **Harsh** · FR-5.4 · *Caveat (found in P4.8): inside Bannerghatta NP, ESRI has 47 % trees and 50 % rangeland (dry deciduous forest and scrub). A rule that maps rangeland → usable would mark half the park usable; the protected mask removes it from scoring, but the 3-class map should treat protected / steep rangeland as forest-like or excluded.* · *Handover from Abhinav (P5.1–P5.3 done): cluster assignments in `outputs/clusters_{validation,final}.parquet`, centroids in original units in `outputs/metrics/cluster_centroids_{run}.csv` (k = 7: built, western valley mixed crop/built, steep rangeland, water, crop, rangeland, trees; ids ordered by mean frac_built, so read the CSV, don't hard-code ids). Please write C7 at the contract path for the **final** run, keep `cluster_id` from `clusters_final` (-1 only where you don't cluster) and set excluded cells to 255; the gate checks both. C7 has one path but FR-5.8 wants one C7 per run: your call how to name the validation one. Then `python -m src.classify.export` and `python -m src.classify.evaluate` produce the GeoTIFF, `clusters.gpkg` and the agreement.* · *Done by Harsh (2026-10-05): `src/classify/label.py`. Rules on each cluster's mean fractions, in order: water + flooded ≥ 0.5 → excluded; built ≥ 0.3 **and** the largest land group → built-up (a threshold alone flips the mixed western valley: 13 % built in 2018, 31 % in 2023); trees ≥ 0.5 → forest; trees + rangeland ≥ 0.5 on slopes ≥ 8° → forest (the Bannerghatta hills, slope ≈ 13°); otherwise usable, flagged `agricultural` if crop dominates (D10). Thresholds in `config → labeling`. C7 (final) at the contract path, `lulc_3class_validation.parquet` for the validation run, rule tables in `metrics/class_rules_{run}.csv`. Final 2023: built-up 60 %, usable 24 %, excluded 11 %, forest 5 % (Bannerghatta's core is in the protected mask).*
- [x] **P5.5** Exclusion mask: water, wetland, snow, mangroves and slope > threshold; applied after labelling. Save `outputs/exclusion_mask.tif`. — **Harsh** · FR-5.5 · *Done (2026-10-05): `label.py` applies `features.labels.exclusion_table(cfg, run)` last (wet, slope > 15°, nodata, protected) and writes `outputs/exclusion_mask.tif` / `exclusion_mask_validation.tif` (1 excluded, 0 kept, 255 outside the AOI) on the 100 m lattice.*
- [x] **P5.6** Evaluation: confusion matrix vs WorldCover majority class (collapsed to 3), overall agreement, per-class precision/recall; centroid profile plots (radar or heatmap) to interpret clusters. — **Abhinav** · FR-5.6 · *Code done: `src/classify/evaluate.py` (ESRI of the run year, primary; WorldCover 2021, cross-check; PRD §6 collapse; confusion matrix, agreement, precision/recall; `all` = 4 classes, `land` = cells neither side excludes, 3 classes). References checked against raw pixels by `scripts/verify_evaluation.py`. **Finding:** the references disagree a lot: built-up 62 % (ESRI 2023) vs 33 % (WorldCover 2021), forest 7 % vs 17 %, usable 28 % vs 48 % (ESRI generalises urban areas). Expect high agreement with ESRI, much lower with WorldCover. Numbers and centroid plots once C7 exists (P5.4).* · *Numbers (2026-10-05): agreement on land cells (3 classes) **96.6 %** with ESRI in both runs; WorldCover 2021: 64.0 % (final), 71.0 % (validation). Confusion matrices and centroid heatmap in notebook 04.*
- [x] **P5.7** Export `outputs/lulc_3class.tif` and `outputs/clusters.gpkg`; create `notebooks/04_clustering.ipynb` with all plots and a written interpretation of each cluster. — **Abhinav** · PRD §13 · *Export code done: `src/classify/export.py` writes `lulc_3class.tif` (100 m cell lattice, same origin as the 10 m grid; 0 = outside AOI) and `clusters.gpkg` from C7. Notebook 04 waits for C7.* · *Done (2026-10-05): `lulc_3class.tif` + `clusters.gpkg` exported; `notebooks/04_clustering.ipynb` written by Harsh: k scan, centroid heatmaps, a description of each cluster, rules, maps for both runs, agreement, visual check. Figures `outputs/figures/p5_*.png`. All cells run (checked in-process; Jupyter kernels can't start inside the Claude app on Harsh's laptop, a ZeroMQ issue).*
- [x] **P5.8** Unit tests: labelling rules on synthetic centroids; mask removes all water/steep cells; same seed gives identical labels. — **Harsh** · FR-5.7 · *Done (2026-10-05): `tests/unit/test_classify_label.py` (15): rules on synthetic centroids (incl. the mixed valley and steep rangeland), cropland switch, exclusion applied last, unclustered cells → 255 / -1, same seed = same labels, mask raster.*
- [x] **P5.9** Decide on open questions Q5 (cropland) and Q6 (slope threshold); record in the PRD and config. — **Both** · *Decided in D10 (`execution_plan.md` §2): cropland usable but flagged (`labeling.cropland_usable: true`, `agricultural` flag in the rule table); slope threshold 15° (`exclusion.slope_max_deg`). Both in the config.*

### Phase 5 Gate

**Automated — `tests/gates/test_phase5.py`** (written by **Abhinav**): *Written: 9 tests; dry-run on a synthetic project passes, and an excluded cell labelled usable, a GeoTIFF shifted by one pixel and changed cluster labels each fail their test. On real data it fails until C7 exists (P5.4).*
- [x] `outputs/lulc_3class.tif` is aligned with the project grid and contains only {1, 2, 3, 255}.
- [x] Every class (built-up, forest, usable) covers ≥ 1 % of the AOI. *(final: 60 / 5 / 24 %)*
- [x] **Zero** cells inside the exclusion mask are labelled usable.
- [x] Two runs with the same seed give identical cluster labels.
- [x] Overall agreement with collapsed WorldCover ≥ 80 % (or the test logs the value and the manual checklist requires an explanation). *(gate checks ESRI: 96.6 %; WorldCover 64 %, explained in notebook 04 §5: the two products disagree, ESRI generalises urban areas)*
- [x] Silhouette score for the chosen k is computed and saved to `outputs/metrics/clustering.json`. *(0.606 final, 0.585 validation)*`n`nStatus on Harsh's laptop (2026-10-05): **9 passed**.

**Manual checklist:**
- [x] The 3-class map was visually compared with satellite imagery for 5 random locations. *(Harsh 2026-10-05, notebook 04 §6: 4 of 5 clearly right; 1 debatable, farmland with houses on the fringe mapped built-up, which is ESRI's broad built-up class)*
- [x] Each cluster has a written description in notebook 04.
- [x] The choice of k and algorithm is justified in writing. *(notebook 04 §1)*

**Sign-off:** - [x] Harsh *(2026-10-05: gate 9/9 on Harsh's laptop)*  - [x] Abhinav *(2026-10-22: gate 9/9 on Abhinav's laptop after rebuilding C7; ESRI land agreement 96.6 %, WorldCover 64.0 %, recomputed by `verify_evaluation.py`)*

---

## Phase 6 — Building similarity

**Goal:** given building A, find similar locations B, plus an aggregate similarity score and an RF alternative for every usable cell.
**Depends on:** Phase 5 gate. **Target:** Sun 2026-10-04.

### Todos

- [x] **P6.1** Write `src/similarity/profiles.py`: context profile per location (100 / 250 / 500 m buffers, PRD §9.5), excluding leaky own-cell features; standardisation fitted on reference + candidate locations. — **Harsh** · FR-6.2, FR-6.6 · *Done by Abhinav: `src/similarity/profiles.py`. Profile = the cell's `MODEL_INPUTS` (250 / 500 m ring shares, distances, road density, terrain; own cell never used, `check_model_inputs` refuses leaky columns), z-scored on reference + candidate cells of the run (time-travel rule: 2018 profiles for validation, latest for final).*
- [x] **P6.2** Build the reference building set (OSM / fallback centroids, cleaned in P3.6); optionally a stratified sample by building type and area. — **Abhinav** · FR-6.1 · *Done: `src/similarity/reference.py` → `data/features/reference_{run}.parquet` (one row per cell: source osm / esri / both, n_buildings, area, main_type). Validation: 2018 OSM snapshot + ESRI 2018; final: current OSM + ESRI 2023 (time-travel rule). **Why ESRI fills:** OSM buildings cover 62–75 % of built cells in the north but ~1 % in the south (2018; 7–9 % today), exactly where growth happens, so OSM alone would describe northern surroundings only (`similarity.reference_source: osm+esri`). Validation: 31,392 reference cells (10,509 with OSM buildings), final: 36,066. Per-type similarity (P6.7) is not feasible: 99.5 % of 2018 and 94 % of current buildings are `building=yes`.*
- [x] **P6.3** Write `src/similarity/query.py`: single-query mode (building ID or lat/lon → top-N usable cells by cosine similarity; Euclidean as an option). Export `outputs/similarity_query_<id>.gpkg` + a map PNG showing A and B₁…Bₙ. — **Harsh** · FR-6.3, FR-6.7 · *Done by Abhinav: `src/similarity/query.py` (`python -m src.similarity.query --building ID | --lonlat LON LAT`). Euclidean in standardised space (cosine as an option); top-N usable cells with a per-feature explanation (closest features, most different features in sd, raw A vs B; land-cover shares that are ~0 at both cells count as trivial matches and are ranked last). Exports `outputs/similarity_query_<name>.gpkg` + `map_similarity_query_<name>.png`. Checked against a brute-force ranking (`scripts/verify_similarity.py`).*
- [x] **P6.4** Write `src/similarity/aggregate.py`: kNN mean similarity of every usable cell to the reference set; rescale to [0, 1]; export `outputs/similarity_score.tif`. — **Harsh** · FR-6.4 · *Done by Abhinav: `src/similarity/aggregate.py`. Mean distance to the 10 nearest reference profiles (a reference cell is never matched with itself), rescaled between the 1st and 99th percentile; C8 `similarity_knn` (validation: candidates, final: usable), `similarity_score.tif`. **AUC on grew 0.773** (validation run), between the change RF (0.779) and distance to built-up (0.763).*
- [x] **P6.5** Write `src/similarity/rf_model.py`: RF built vs non-built on context features, class-balanced, **spatial block CV** (e.g. 2 km blocks); feature importance (impurity + permutation); export `outputs/rf_probability.tif`. — **Abhinav** · FR-6.5, FR-8.2 · *Done: `src/similarity/rf_model.py`. `rf_change`: spatial-CV AUC 0.760 on `chg_train_pos` (tuned on that label only; best `min_samples_leaf` 20, `max_features` sqrt); out-of-fold AUC on `grew` **0.779 vs distance-to-built 0.763** (preview of P7.4). `rf_state`: CV 0.998 on built vs non-built, but only 0.702 on `grew` (comparison only, as in the prototype). Top permutation importance: ring500_built, ring250_tree, log_dist_built, ring500_crop. Outputs: C8 `outputs/scores/rf_{change,state}.parquet` (OOF, candidates), `outputs/final/scores/*` (usable cells, 2023 features), `outputs/rf_probability.tif`, `outputs/metrics/similarity.json`. Features are within-year percentiles (OSM mapping shift 2018 → today), rounded to 1e-6 first: ring fractions carry ~250,000 float-noise pairs < 1e-7 apart that ranks would otherwise order (found by a test). Verified by `scripts/verify_similarity_models.py` (fold refit reproduces stored scores; in-sample AUC 0.997 vs OOF 0.760 shows why D11 matters).*
- [x] **P6.6** Held-out building check: spatial blocks of buildings held out; report the median percentile rank of held-out locations. — **Abhinav** · FR-8.2 · *Done: `src/similarity/holdout.py`, 5 spatial folds, validation run. AUC of held-out reference cells vs other cells: RF 0.984, kNN all inputs 0.895, kNN 500 m rings only 0.871, distance-to-built 0.887. Median percentile is capped at ~70 because reference cells are 60 % of the cells (RF reaches it). **Decision (from notebook 03):** keep both ring scales in the similarity profile (all inputs beat 500 m only). The kNN here is a check scorer; plug in the P6.4 aggregate when it exists.*
- [ ] **P6.7** Stretch: similarity per building type (residential / commercial / industrial), if tags allow. — **Harsh** · Q7 · *Not feasible on this data (see P6.2): almost all OSM buildings are untyped.*
- [~] **P6.8** Create `notebooks/05_similarity.ipynb`: 3–5 example queries (different building types/areas), aggregate map, RF map, feature importance, and a comparison of the three. — **Abhinav** · FR-10.1 · *`notebooks/05_similarity.ipynb` created with the reference set, the RF results (table, ROC, importance, maps) and the held-out check; runs end to end. The example queries and aggregate map are added with P6.3/P6.4 (Harsh).*
- [x] **P6.9** Unit tests on synthetic data: identical profiles → similarity 1; the query never returns excluded/non-usable cells; leaky features are rejected by the profile builder (raises an error). — **Both** (Harsh: profiles/query, Abhinav: RF/CV split) · *Abhinav's part done: `tests/unit/test_similarity_rf.py` (12: blocks, folds never split a block, CV never trains on the test blocks, percentile scaling keeps the forest's partition, training sets, end-to-end C8/GeoTIFF, reference set) and `tests/unit/test_similarity_holdout.py` (8).* Profiles / query / aggregate: `tests/unit/test_similarity_query.py` (16: leaky features refused, identical profiles → distance 0 / similarity 1, no self-match, only usable results, self-query, lon/lat round trip, metrics, export).

### Phase 6 Gate

**Automated — `tests/gates/test_phase6.py`** (written by **Harsh**): *Written by Abhinav: 8 tests, pass on real data; a dry run on a synthetic project passes and a NaN in the wrong place, a leaky input and out-of-range scores each fail their test.*
- [x] **Self-query sanity:** querying an existing building returns a cell within 1 cell of its own location in the top 1 % (run with the building's own cell temporarily allowed as a candidate).
- [x] Query results contain only usable, non-excluded cells.
- [x] `similarity_score.tif` and `rf_probability.tif` are aligned with the grid, values in [0, 1], and NaN only outside usable land.
- [x] No column from `LEAKY_FEATURES` appears in the profile or RF input feature list.
- [x] Spatial CV folds have no overlapping blocks between train and test.
- [x] RF spatial-CV ROC-AUC is saved to `outputs/metrics/similarity.json`.

**Manual checklist:**
- [ ] Example query maps make intuitive sense (matches near roads and similar terrain).
- [ ] Feature importance is discussed: which surroundings matter most?
- [ ] Aggregate vs RF maps compared and differences explained.

**Sign-off:** - [ ] Harsh  - [ ] Abhinav

---

## Phase 7 — Suitability mapping and validation

**Goal:** final suitability classes, candidate sites, MCDA baseline, and validation metrics.
**Depends on:** Phase 6 gate. **Target:** Mon 2026-10-05.

### Todos

- [x] **P7.1** Write `src/suitability/score.py`: combine the similarity and RF scores (documented weights); classify into S1/S2/S3/N (quantiles or Jenks); export `suitability_score.tif` and `suitability_class.tif`. — **Harsh** · FR-7.1, FR-7.2 · *Done by Abhinav: `src/suitability/score.py`. Combined = w × percentile(similarity_knn) + (1 − w) × percentile(rf_change); w chosen on the validation run's **training** label (2020/21, out-of-fold RF scores), never on `grew`, then frozen: **w = 0.3**. Classes S1 ≥ q90, S2 ≥ q70, S3 ≥ q40 of the scored cells, else N; forest / built-up / excluded always N. `suitability_score.tif`, `suitability_class.tif` (1–4, 0 outside the AOI), C8 `suitability`. Validation AUC **0.797** (best model), S1 + S2 hold 65 % of the growth.*
- [x] **P7.2** Candidate patches: merge adjacent S1 cells, drop patches below the minimum area, compute patch attributes; export `candidates.gpkg` + `.csv`. — **Harsh** · FR-7.4 · *Done by Abhinav: `src/suitability/candidates.py`. S1 cells merged into patches of edge-adjacent cells, ≥ 1 ha: 557 patches, 1,382 ha (253 mostly cropland, flagged). Attributes: area, mean / max score, slope, distances to major road / built-up / water, road density, land cover, lon / lat. Half the patches are single cells, so the **top sites** are the 20 best patches ≥ 5 ha (`top_site_rank`, `suitability.top_site_min_area_ha`). `candidates.gpkg` + `.csv`. None of the top sites overlaps an OSM lake (0.06 ha) or the national park.*
- [x] **P7.3** Write `src/suitability/mcda.py`: rescale criteria, AHP pairwise matrix with consistency ratio, weighted overlay; export `mcda_score.tif`. — **Abhinav** · FR-7.3 · *Done: `src/suitability/mcda.py`. Criteria (0–1): slope (0 at 15°), distance to major road (0 at 3 km), distance to built-up (0 at 2 km), water (0 within 100 m, 1 beyond 200 m), own-cell land cover (rangeland/bare 1, crop 0.6, tree 0.2). AHP weights: road 0.30, built 0.30, slope 0.16, land cover 0.16, water 0.09; **CR 0.003**. Land cover is an MCDA criterion (FR-7.1) and not the D4 leak (not trained; validation scores only cells non-built in 2018/19); listed as `own_cell_inputs` in the score metadata, and `mcda_no_lulc` is scored too. Outputs: C8 `mcda`, `mcda_no_lulc` (validation: candidates, 2018), `outputs/final/scores/*`, `outputs/mcda_score.tif`, `outputs/metrics/mcda.json`. **Result:** AUC on `grew` 0.636 (0.614 without land cover) vs distance-to-built 0.763 and rf_change 0.779. Each criterion alone: built 0.763, slope 0.612, road 0.548, land cover 0.527, water 0.518: fixed expert weights dilute the one strong criterion. Weights are **not** tuned on the test label. Verified by `scripts/verify_mcda.py`.*
- [x] **P7.4** Write `src/suitability/validate.py` **temporal validation**: rerun features + scores on baseline-year data only; label new-growth cells (baseline non-built → latest built); compute ROC-AUC, precision@top-10 %, and the S1+S2 hit rate. — **Harsh** · FR-8.1, FR-8.3 · *Done by Abhinav: `src/suitability/validate.py` → `metrics/validation.json`. Every C8 + random + distance-to-built: AUC, precision / recall / lift in the top 10 % and 30 %, TOC, AUC by growth type (adjacent / outlying), S1 + S2 hit rate, group ablation (rf_change refitted out of fold, similarity recomputed). Recomputed independently by `scripts/verify_suitability.py`.*
- [x] **P7.5** Apply the same validation to the MCDA baseline; create a comparison table + ROC curves (data-driven vs MCDA vs random). — **Abhinav** · FR-8.3 · *Preview done without the harness: MCDA 0.636 vs change RF 0.779, distance to built-up 0.763, random 0.5 (table and ROC in `docs/validation.md` §2–3, `chart_roc.png`, notebook 06). Lift, TOC and LEI for MCDA come from the P7.4 harness.* · *Done: MCDA AUC 0.636, lift 1.86 (top 10 %) vs combined 0.797 / 3.45, change RF 0.779 / 3.23, distance to built-up 0.763 / 3.04, random 0.499 / 1.00; TOC and growth-type split for every model (`chart_roc`, `chart_toc`, `chart_growth_type`).*
- [x] **P7.6** Sensitivity analysis: vary cell size (e.g. 50/100/200 m), k, and slope threshold; report how the metrics change. — **Abhinav** · *Done: `src/suitability/sensitivity.py` → `outputs/metrics/sensitivity.json`; checked by `scripts/verify_sensitivity.py` (default rows reproduce the main results exactly; AOI area constant across cell sizes). Temporal AUC on `grew` (rf_change / distance-to-built / MCDA): **slope** 10° 0.774/0.759/0.646, 15° 0.779/0.763/0.636, 20° 0.780/0.765/0.633 (slope-excluded cells 1,685 → 158); **k** 5–8: class shares within ~1 pp, ESRI land agreement 96.6–98.8 % (k = 5 slightly higher but loses the steep-rangeland forest group: forest 3.9 % vs 5.0 %); **cell size** 50 m 0.839/0.810/0.699, 100 m 0.779/0.763/0.636, 200 m 0.834/0.825/0.733 (AUCs not comparable across sizes: the growth label changes with the cell, and 200 m has only 148 grown cells / 42 training positives). Robust result: **rf_change > distance-to-built > MCDA in every setting**. The 50 / 200 m runs rebuild features and labels in `outputs/sensitivity/cell_{m}/` (200 m crops 10 px of buffer); rf_change uses the frozen tuned parameters.*
- [~] **P7.7** Write `docs/validation.md` with all metrics, figures and an honest discussion of misses. Create `notebooks/06_suitability_validation.ipynb`. — **Both** (Harsh: temporal validation, Abhinav: MCDA comparison + sensitivity) · *Abhinav's part done: `docs/validation.md` (design, headline AUC table, MCDA §3, held-out check §4, sensitivity §5, misses and limitations §7) and `notebooks/06_suitability_validation.ipynb` (MCDA + sensitivity). Harsh's sections are marked *to be added*.*
- [x] **P7.8** Write `src/pipeline.py`: runs stages 2→7 from the config, with a `--from-stage` option; logs timings. — **Harsh** · FR-10.2, FR-10.3 · *Done by Abhinav: `src/pipeline.py` (`python -m src.pipeline [--from-stage S] [--to-stage S] [--with-sensitivity] [--dry-run]`): download → preprocess → features → labels → classify → similarity → suitability → viz, each step as `python -m <module>`, timings in `metrics/pipeline.json`. **Full run 12.4 min** (downloads skipped when present).*
- [x] **P7.9** Unit tests: classification thresholds produce the expected class proportions; AHP consistency ratio on a textbook matrix; the new-growth labelling on a synthetic 2-year raster. — **Abhinav** · *AHP part done (`tests/unit/test_suitability_mcda.py`: Saaty's 3×3 textbook example w ≈ 0.637/0.258/0.105, CR ≈ 0.033; a consistent matrix recovers its weights with CR 0; cyclic preferences give CR > 0.1). Growth labelling on a synthetic multi-year raster is covered by `tests/unit/test_labels.py::test_growth_cases` (A4). Class-proportion test waits for P7.1 (Harsh).* · *Done: class proportions (10 / 20 / 30 / 40 % for S1 / S2 / S3 / N on uniform scores), weight chosen on the training label only, combined = weighted mean of percentiles, patches use edge neighbours, TOC / lift / growth-type AUC on hand-made cases, pipeline plan (`tests/unit/test_suitability_phase7.py`); AHP and growth labels as noted before.*

### Phase 7 Gate

**Automated — `tests/gates/test_phase7.py`** (written by **Abhinav**): *Written: 10 tests; dry-run on a synthetic project passes, and a forest cell in S1, a raster shifted by one pixel, a sliver candidate patch and a low AUC without `docs/validation.md` each fail their test. Passes on real data (10/10 with `GIS_SUIT_RUN_PIPELINE=1`; the pipeline ran end to end in 12.4 min).*
- [x] Suitability rasters are aligned with the grid; classes only in {1, 2, 3, 4}.
- [x] **Zero** excluded / forest / built-up cells in S1–S3 or in `candidates.gpkg`.
- [x] All candidate patches are ≥ the minimum area.
- [x] AHP consistency ratio < 0.1.
- [x] Temporal validation ROC-AUC ≥ 0.75 **or** the test is marked `xfail` with a reason referencing `docs/validation.md`.
- [x] `outputs/metrics/validation.json` contains AUC, precision@10 % and S1+S2 hit rate for both the data-driven model and MCDA.
- [x] `python -m src.pipeline` runs end to end (from processed data) in < 30 min.

**Manual checklist:**
- [ ] Top 10 candidate sites checked against satellite imagery: no obvious nonsense (e.g. a lake or a stadium).
- [ ] `docs/validation.md` reviewed by both teammates.
- [ ] Limitations listed (OSM completeness, LULC errors, "past ≠ good planning" assumption, etc.).

**Sign-off:** - [ ] Harsh  - [ ] Abhinav

---

## Phase 8 — Visualisation, report and presentation

**Goal:** polished outputs, report and slides; the repo is clean and reproducible.
**Depends on:** Phase 7 gate (report writing can start earlier). **Target:** Tue 2026-10-06 (submit).

### Todos

- [~] **P8.1** Write `src/viz/static_maps.py`: a consistent map style (title, legend, scale bar, north arrow, basemap) for all maps in FR-9.1; export to `outputs/figures/` at 300 dpi. — **Abhinav** · FR-9.1 · *`src/viz/static_maps.py` + `src/viz/style.py`: title, subtitle, legend / colour bar outside the map, scale bar, north arrow, AOI outline, Esri World Gray Canvas basemap (CARTO tiles now return 'API KEY REQUIRED'; tiles cached in `data/raw/tiles`), 300 dpi. 18 maps written: ESRI LULC 2018/2023, 3-class (both runs), 5 key features, validation labels, rf_change / rf_state / mcda / mcda_no_lulc scores (both runs). Class colours validated for colour-vision deficiency (built-up orange, forest green, usable blue; worst CVD ΔE 9.2). Suitability classes + candidates map is coded and appears once P7.1/P7.2 outputs exist. Checked by `scripts/verify_figures.py` (300 dpi, real basemap, 200/200 sampled cells drawn in their class colour).*
- [~] **P8.2** Charts: class-area bar charts, elbow/silhouette, centroid profiles, feature importance, ROC curves. Same style throughout. — **Abhinav** · FR-9.3 · *`src/viz/charts.py`: k scan, cluster profiles, class areas, RF importance, temporal ROC (rf_change 0.779, distance-to-built 0.763, rf_state 0.702, MCDA 0.636), sensitivity, held-out check. TOC, ablation and LEI split come from the P7.4 harness.*
- [x] **P8.3** Write `src/viz/interactive.py`: folium HTML with toggleable layers (LULC, 3-class, suitability, candidates, reference buildings) and popups for candidates. — **Harsh** · FR-9.2 · *Done by Abhinav: `src/viz/interactive.py` → `outputs/map.html` (4 MB): land cover, three-class map, suitability classes (N transparent), change-RF score, similarity, all candidate sites and the numbered top 20 with popups, a 3,000-building sample, legend, Esri gray canvas / imagery basemaps (OSM tiles refuse pages opened from a file). Checked in a headless browser.*
- [ ] **P8.4** README: project summary, setup (conda), data download, how to run the pipeline and notebooks, and outputs description. — **Harsh** · D14
- [x] **P8.5** Report sections: Introduction, Study area, Data, Literature review. — **Abhinav** · D12 · *Done: `report/final/` (LaTeX, one file per section so both can write in parallel; figures read from `outputs/figures/`; build steps in `report.tex`). Introduction, literature review (with summary table), study area and data written; every literature claim follows `docs/literature_review.md` (only verified details; author initials as verified). Builds to 13 pages with no undefined references. `siunitx` isn't installed here, so the report uses small unit macros instead.*
- [ ] **P8.6** Report sections: Methodology (features, clustering, similarity, suitability), Validation design. — **Harsh** · D12
- [~] **P8.7** Report sections: Results, Discussion, Limitations, Future work, Conclusion. — **Both** (Harsh: similarity + validation results; Abhinav: clustering + MCDA results) · *Abhinav's part drafted in `sections/07_results.tex`: land classification, MCDA, sensitivity, and the learned-model / held-out results (built by Abhinav; Harsh to merge with the validation results). Similarity, suitability, discussion and conclusion are marked for Harsh / both.*
- [~] **P8.8** Slides (10–15): each person presents the parts they built. — **Both** · *Deck drafted in `report/final_slides/slides.tex` (15 slides, same theme as the mid-term; figures from `outputs/figures`): Abhinav's slides done (study area and data, clustering, three-class map, learned models, RF importance, MCDA, sensitivity, limitations); Harsh's (validation design, similarity, suitability) and the conclusion are marked placeholders. Rehearsal pending.*
- [ ] **P8.9** Code clean-up: remove dead code, check docstrings/type hints, `ruff` + `black` clean. — **Harsh** (`src/download`, `preprocess`, `similarity`, `suitability/score+validate`, `pipeline`) · NFR-4
- [x] **P8.10** Code clean-up for the remaining modules (`features/distance`, `classify`, `suitability/mcda`, `viz/static_maps`). — **Abhinav** · NFR-4 · *Done for `features/distance`, `classify/{cluster,evaluate,export}`, `suitability/{mcda,sensitivity}`, `similarity/{reference,rf_model,holdout}`, `viz/*`: ruff with extra rules (unused arguments, simplifications, return types) clean; unused parameter removed; docstrings on every substantive public function (path helpers and `main()` follow the codebase convention of none); black + ruff clean; 408 tests pass.*
- [~] **P8.11** Fresh-clone reproducibility test: the teammate who did **not** set up the env last clones the repo into a new folder, creates the env, downloads data, runs the pipeline and all notebooks, and records issues. — **Abhinav** · NFR-1 · *Partial run by Abhinav, 2026-10-22, before `src/pipeline.py` exists: fresh clone of the fork into an empty folder, existing `gis-suit` env (rebuilt from `environment.yml` the same day, which worked), every download from scratch, then each stage module in order. Results (`scripts/compare_projects.py <fresh> <working copy>`): **(1)** 202 unit tests + gate 0 pass in the clone with no data; **(2)** all 8 raster downloads and all 10 processed rasters are byte-identical; **(3)** the OSM 2018 snapshot is identical (same ids: 27,982 roads, 450 water, 267,656 buildings); **(4)** the whole validation run reproduces exactly: features, labels, clusters, 2018 3-class map, C8 `rf_change` / `rf_state` / `mcda` / `mcda_no_lulc`, `clustering.json`, `mcda.json`, `similarity.json`; **(5)** the chain from downloaded data takes 9.7 min (clustering 3.5 min with the k scan, RFs 4.5 min). **Issues for P8.12:** (a) the **current OSM snapshot isn't pinned**, so final-run outputs depend on the download date: 3 weeks of OSM edits changed 0.2–0.4 % of current features, 25 cells of the final 3-class map, 3 usable cells, 473 cells of the final RF score; suggest an `osm.snapshot_current` date queried with `[date:]` like 2018; (b) an empty tag (`leisure=nature_reserve`) costs ~7 min per mirror because 'no matching features' is retried on every mirror, which made the full OSM download take > 40 min; (c) the protected area also comes from the current snapshot, so `protected_frac` in the validation mask moved by 0.01 in one cell (no label changed). Still to do once P7.8 exists: `python -m src.pipeline` and all notebooks from the fresh clone.*
- [x] **P8.12** Fix any issues found in P8.11. — **Harsh** · *Done by Abhinav: (a) the current OSM snapshot is pinned (`osm.snapshot_current: 2026-10-01`, queried with `[date:]` like 2018; a changed date triggers a re-download); (b) an empty tag is no longer retried: an empty answer counts as an answer and is confirmed on one more mirror (2 queries instead of 6 with waits). Regression tests in `tests/unit/test_osm_download.py`.*
- [ ] **P8.13** Final PRD update: mark requirements met / not met; close open questions. — **Both**

### Phase 8 Gate (final)

**Automated — `tests/gates/test_phase8.py`** (written by **Harsh**):
- [ ] All deliverable files D1–D14 from PRD §6 exist.
- [ ] All figures listed in FR-9.1 / FR-9.3 exist in `outputs/figures/` and are ≥ 300 dpi.
- [ ] `outputs/map.html` exists and contains all required layer names.
- [ ] `ruff check .` and `black --check .` exit 0.
- [ ] No notebook in the repo has stored outputs (nbstripout check).
- [ ] The **full test suite passes**: `pytest` (unit + all gates 0–7).

**Manual checklist:**
- [ ] Fresh-clone test (P8.11) passed with no manual fixes.
- [ ] Report proofread by both; every figure is referenced in the text; references are formatted.
- [ ] Slides rehearsed once with timing.
- [ ] No Claude / AI co-author lines in the git history (`git log --format=%B | grep -i co-authored` returns nothing).
- [ ] Final commit tagged `v1.0` and pushed.

**Sign-off:** - [ ] Harsh  - [ ] Abhinav

---

## Definition of Done (whole project)

- [ ] All phase gates 0–8 passed and signed off.
- [ ] All deliverables D1–D14 complete.
- [ ] Validation metrics reported, and misses explained.
- [ ] Report and slides submitted.

---

## Change log

| Date | Change | By |
|---|---|---|
| 2026-09-27 | Initial PRD and task breakdown | Harsh |
