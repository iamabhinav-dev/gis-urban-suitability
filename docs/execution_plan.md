# Execution plan

How we build the project from here: who does what, in which order, and how we avoid waiting on each other.

- **Requirements:** [PRD.md](PRD.md). The phase checklist and gate tests stay in [Tasks.md](Tasks.md).
- **What this plan adds:**
  - a split into **two parallel tracks**, one per person;
  - fixed **file contracts** between the tracks;
  - the method changes that came out of the study-area check and the prototype test (§2).

**Change 2026-10-01:** tracks swapped at Abhinav's request (raster experience). Abhinav now owns the raster and similarity track; Harsh owns the vector and learning track.

**Status on 2026-10-01:**
- Phase 0: environment, skeleton, config loader and pre-commit are done.
- P0.9: study-area comparison done, see [study_area.md](study_area.md).
- P0.10: Bengaluru South confirmed by Harsh. P0.12: deadline is Tue 2026-10-06 (report format still open).

---

## 1. How the split works

**Split by data type, then by model.** Each person owns one input pipeline end to end, and then one set of models.

| | **Abhinav: raster and similarity track** | **Harsh: vector and learning track** |
|---|---|---|
| Data | ESRI LULC (all years), WorldCover, DEM | OSM roads, water and buildings: 2018 snapshot + current |
| Preprocessing | Alignment to the 10 m reference grid, slope, class harmonisation | Road classes, building cleaning, reference building sets |
| Features | Grid, LULC fractions, context rings, terrain, distance to built-up and water | Distance to roads, road density, building density |
| Labels | Exclusion mask, persistent growth labels, growth type (LEI) | — |
| Models | **Building similarity**: per-building query + aggregate kNN | **Clustering** (3 classes), **change-based RF**, **MCDA/AHP baseline** |
| Evaluation | Validation harness (metrics, baselines, TOC, LEI breakdown) | Group ablation, spatial-CV tuning, sensitivity runs |
| Output | Interactive map, pipeline runner | Static maps and charts |
| Report | Study area, literature; similarity + validation methods and results | Introduction, data; clustering + RF + MCDA methods and results |
| Gate tests written | Phases 1, 3, 5, 7 | Phases 2, 4, 6, 8 |

**Why this is parallel:**
- The two tracks touch **different folders** and **different data**.
- They only meet through **files with a fixed format** (§4).
- Every contract has a **stub** (fake data with the right columns) from Week 1. So nobody waits for the other person's real output; you build against the stub and switch to real data when it lands.

**Estimated effort:** about 40 h each for the core pipeline and about 15 h each for the report and slides (§7).

---

## 2. Decisions (defaults adopted 2026-10-01)

These come from [study_area.md](study_area.md) and the prototype test.

**Status:**
- **All ten recommended defaults are adopted** (Abhinav, 2026-10-01). Re-checking them raised no new concern; the known caveats are already handled (Bannerghatta in the exclusion mask, A4.1b; the state RF kept as a comparison for D6; mirror fallbacks for D8).
- D1–D3, D5, D8–D10 are applied in `config/config.yaml`, and D1 in `config/aoi.geojson`.
- **Harsh can reopen any decision** when reviewing the PRD update (J4). Until then, work goes ahead on these defaults.

| # | Decision | Adopted (default) | Why |
|---|---|---|---|
| D1 | Study area | **Bengaluru South** (Hyderabad West as backup) | Strong persistent growth, a clear forest block (Bannerghatta), and good OSM coverage *in 2018*, which the temporal validation needs |
| D2 | LULC source for features | **ESRI IO LULC for everything**. WorldCover 2021 only as a cross-check | WorldCover has no 2018 map and can't be used for change. One source keeps the validated model = the final model |
| D3 | Years | Baseline **2018** (confirmed by 2019), end **2022 + 2023** | The ESRI 2017 map is noticeably noisier; requiring two years at each end removes classifier flicker |
| D4 | Leakage rule (updates FR-6.6) | Similarity and RF inputs use **no own-cell LULC fractions at all**, only context rings, distances and terrain | The prototype showed own-cell fractions alone separate built from non-built perfectly (AUC 1.0), because they sum to 1 − built |
| D5 | Similarity measure | **Euclidean** in standardised space; cosine only as a comparison | Prototype: cosine AUC 0.49 (random), Euclidean 0.74 |
| D6 | ML model | **Change-based RF**: learn from cells that grew between 2018 and 2020/21, using their 2018 features | Beat a built vs non-built RF: AUC 0.76 vs 0.66 on the same test |
| D7 | Headline metrics | Temporal ROC-AUC, top-N hit rate **with lift over random**, TOC plot. **Baselines always shown:** random, distance-to-built, MCDA | Distance-to-built alone scored 0.75 in the prototype, so it's the bar to beat. "RF spatial-CV AUC" is dropped as a success metric (it was 1.0 for a trivial task) |
| D8 | Roads for baseline-year features | **2018 OSM snapshot** (Overpass `[date:]`). Major roads may come from any snapshot | Today's roads leak future growth: "distance to any road" alone went from AUC 0.58 to 0.76 |
| D9 | Reference buildings | **OSM 2018 snapshot** for validation; current OSM for the final map | Buildings added after 2018 would leak into the validation |
| D10 | Open questions Q5 / Q6 | Cropland = usable but flagged; slope threshold 15° | Keeps the PRD defaults; revisit in the sensitivity analysis |

**Next:**
- **Abhinav** updates the PRD (FR-6.6, FR-8.1, §9.5, §9.8, `years` in config).
- **Harsh** reviews it and updates Tasks.md to match this plan.

That's one PR each.

---

## 3. Timeline

**Deadline: final submission Tue 2026-10-06.** The full scope is kept: the W1–W10 sequence below is compressed into Thu 1 – Tue 6 October, in the same order. Day targets per phase and milestone are in PRD §15.

**M = milestone:** a point where both tracks must have something working together.

| Week | Abhinav | Harsh | Joint / milestone |
|---|---|---|---|
| **W1** | A0 contracts + stubs (with A) · A1 raster downloads | H0 contracts + stubs (with H) · H1 OSM downloads (2018 + current) | Day 1: decisions (§2) · Day 3: `schema.py` and stubs merged · draw the AOI → **Phase 0 gate** |
| **W2** | A1 finish, manifest · A2 raster preprocessing | H1 finish (retries, cache) · H2 vector preprocessing | Literature review split (Phase 1) runs alongside · **Phase 1 gate** (A writes the test) |
| **W3** | A3 grid + raster features | H3 vector features | **M1: thin slice.** Real grid + a few real features + labels → one baseline score → harness runs. **Phase 2 gate** (H) |
| **W4** | A4 labels, exclusion mask, LEI · A3 finish | H3 finish · H4 clustering starts | **M2: full feature table** · **Phase 3 gate** (A) · **Phase 4 gate** (H) |
| **W5** | A6 validation harness (full) | H4 clustering + labelling + evaluation | **Phase 5 gate** (A) |
| **W6** | A5 similarity: profiles + per-building query | H5 change RF + state RF comparison | |
| **W7** | A5 aggregate similarity score | H5 group ablation · H6 MCDA/AHP | **M3: every model writes a score file** · **Phase 6 gate** (H) |
| **W8** | A7 temporal validation run, LEI breakdown, `pipeline.py` | H6 finish · H7 sensitivity runs (cell size, slope, k) | **M4: validation complete** · **Phase 7 gate** (A) |
| **W9** | A8 interactive map · report sections | H8 static maps + charts · report sections | Report draft |
| **W10** | A9 fresh-clone fix-ups · slides | H9 fresh-clone test · slides | **Phase 8 gate** (H) · submit |

**The only hard waits (everything else runs on stubs):**
1. **M1 (end of W3):** needs A3's grid and H3's features on the *real* AOI.
2. **Clustering (H4)** needs the real feature table: M2.
3. **Validation (A7)** needs real score files from all models: M3.

---

## 4. Contracts between the tracks

These are the only places the two tracks touch.
- Column names and file paths are fixed in **`src/features/schema.py`**, written together on day 1–3.
- Changing a contract needs a PR **approved by both**.
- `tests/unit/test_contracts.py` checks every file against its schema, so drift fails CI.

| ID | File | Producer | Consumers | Content |
|---|---|---|---|---|
| **C1** | `data/features/grid.parquet` (+ `.gpkg`) | Abhinav (A3) | everyone | `cell_id, row, col, x, y`, one row per 100 m cell. Cells align exactly with 10 × 10 blocks of the 10 m reference raster (ESRI tile grid, project UTM) |
| **C2** | `data/features/raster_features_{year}.parquet` | Abhinav (A3) | H4, H5, H6, A5 | `cell_id` + LULC fractions (own cell, for **clustering only**), ring/context fractions, terrain, `log_dist_built`, `log_dist_water` |
| **C3** | `data/features/vector_features_{snapshot}.parquet` | Harsh (H3) | H5, H6, A5 | `cell_id, log_dist_major, log_dist_any, road_density, bldg_count, bldg_area_frac`. The last two are listed in `LEAKY_FEATURES` |
| **C4** | `data/features/grid_features_{year}.parquet` | Abhinav (`build.py`, merges C2 + C3) | H4, H5, H6, A5 | Join on `cell_id`; nodata drops logged |
| **C5** | `data/features/labels.parquet` | Abhinav (A4) | H5, H6, A6 | `cell_id, excluded, built_baseline, candidate, grew, chg_train_pos, lei_type`. Years come from `config.yaml`, not the column names |
| **C6** | `data/processed/buildings_{snapshot}.gpkg` | Harsh (H2) | A5 | Cleaned footprints: `bldg_id, geometry, area_m2, building_type, cell_id`, for snapshots `2018` and `current` |
| **C7** | `outputs/lulc_3class.parquet` (+ `.tif`) | Harsh (H4) | A5, A6, H6 | `cell_id, cluster_id, class_3` (1 built-up, 2 forest, 3 usable, 255 excluded) |
| **C8** | `outputs/scores/{model}.parquet` | anyone who builds a model | A6 | `cell_id, score` (higher = more suitable), plus `outputs/scores/{model}.json` metadata (features used, training years). **Every model plugs into validation the same way.** |

**`schema.py` also defines:**
- `FEATURE_GROUPS` (lulc, near_built, roads, terrain, water)
- `CONTEXT_FEATURES`: the only features allowed as similarity/RF inputs (D4)
- `OWN_CELL_FEATURES`: clustering only
- `LEAKY_FEATURES`
- `MODEL_INPUTS = CONTEXT_FEATURES − LEAKY_FEATURES`

**Stubs (A0 + H0, week 1):**
- `tests/conftest.py` gets a `synthetic_project` fixture that writes C1–C8 for a 20 × 20-cell fake AOI with plausible values.
- Each track develops against it until the real file exists.
- Real code must pass the same contract test as the stub.

---

## 5. Task checklist

### How to use this checklist

- **Tick** a box (`- [x]`) in the same PR that finishes the task. Write `[~]` by hand while it's in progress.
- **Markers:**
  - 🔓 = no dependency on the other person. Start any time.
  - 🔓 *(stub)* = develop and test on the stub data from §4. No need to wait for real data.
  - 🔒 **X** = **blocked until task X, owned by the other person, is ticked.**
- **The rule:** before you start a 🔒 task, check that **every** task it names is `[x]`. If one isn't:
  1. **Don't start it.**
  2. Work on a 🔓 task instead, or on the 🔓 *(stub)* version of the same work.
  3. Tell the other person which blocker you're waiting on.
- **Unmarked tasks:** these depend only on your own earlier tasks. Do them in order.
- **Blockers first:** tasks in **bold** unblock the other person (see "Who waits on what" at the end of this section). Do those before your other tasks in the same week.

### Joint

- [x] **J1** §2 defaults adopted (Abhinav ☑ 2026-10-01) · Harsh confirms ☑ 2026-10-01 (study area confirmed; D11/D12 proposed as additions in PRD §9.9) · W1 · 🔓
- [x] **J2** AOI polygon in `config/aoi.geojson` ☑, `aoi.name` set ☑, Phase 0 gate green on Abhinav's laptop ☑ · Harsh's laptop ☑ (35 passed, 2026-10-01) · W1 · after J1
- [~] **J3** `src/features/schema.py` merged (full draft by Abhinav on `main`, 2026-10-01; **Harsh to review the vector/model half**) (contract names, `FEATURE_GROUPS`, `CONTEXT_FEATURES`, `OWN_CELL_FEATURES`, `LEAKY_FEATURES`, `MODEL_INPUTS`) · W1 day 3 · one joint PR (A0.1 + H0.1)
- [ ] **J4** PRD updated to the §2 decisions (Abhinav writes, Harsh reviews) · W1 · after J1
- [ ] **J5** Tasks.md updated to this plan (Harsh writes, Abhinav reviews) · W1 · after J1
- [ ] **J6** `docs/literature_review.md`: Abhinav's MCDA/LULC half ☐ · Harsh's ML/validation half ☑ (H1–H10 + data papers D1–D2 + synthesis draft; A1–A6 pre-filled as suggestions for Abhinav) · synthesis together ☐ · W1–2
- [x] **J7** `docs/data_sources.md`: Abhinav's rasters ☑ (reviewed Harsh's draft; added §2b download/preprocessing, §6 class mapping, known issues) · Harsh's OSM + snapshot method ☑ · W2
- [ ] **J8** Report: Discussion + Conclusion written together · W9
- [ ] **J9** Slides done and rehearsed once · W10

### Abhinav: raster and similarity track

**A0. Contracts and stubs** · W1
- [x] A0.1 Draft the raster half of `schema.py` (joint PR = J3) · 🔓 · *drafted both halves*
- [x] A0.2 Stubs for C1, C2, C4, C5, C8 in `tests/conftest.py` (20 × 20-cell fake AOI) · after J3 · *generator in `src/synthetic.py` writes **all** of C1–C8; fixture `synthetic_project`*
- [x] A0.3 `tests/unit/test_contracts.py` checks every contract file against `schema.py` · after J3 · *also validates real files under `data/` and `outputs/` when they exist*

**A1. Raster downloads** · W1–2 · P2.1–P2.3, P2.8
- [x] **A1.1** `src/io_utils.py`: manifest, SHA-256, skip-if-exists, logging · 🔓 · *also `retry()` with clear errors; Harsh: use `Manifest.for_config`, `needs_download`, `record_download`, `retry`*
- [x] A1.2 `src/download/lulc.py`: ESRI IO LULC 2018–2023 + WorldCover 2021, AOI + 1 km buffer · code 🔓, real run after J2 · *shared STAC logic in `src/download/stac.py`*
- [x] A1.3 `src/download/dem.py`: Copernicus DEM GLO-30 · code 🔓, real run after J2
- [x] A1.4 Rerun makes no downloads; manifest checksums match; quick-looks in notebook 01 · *rerun skips all 8 files in 1.4 s*

**A2. Raster preprocessing** · W2 · P3.1–P3.3
- [x] **A2.1** `src/preprocess/raster.py`: reference 10 m grid (ESRI tile grid, project UTM), reproject and align all rasters, nearest for classes, bilinear for DEM. **Saves the reference grid spec** to `data/processed/reference_grid.json`. · *Harsh: use `load_reference_grid(cfg)` (CRS, transform, shape) to rasterise roads in H3.3. Grid = 2,620 × 2,670 px, edges on whole 100 m cells.*
- [x] A2.2 `src/preprocess/terrain.py`: slope (Horn); unit test on a synthetic plane · *slope computed on the 30 m UTM DEM, then bilinear to 10 m*
- [x] A2.3 ESRI ↔ WorldCover class mapping table (code + `data_sources.md`)
- [x] A2.4 Unit tests: reprojection keeps class values; aligned rasters share transform and shape · *done check: `scripts/verify_preprocessed.py`*

**A3. Grid and raster features** · W3–4 · P4.1–P4.3, P4.6, P4.8
- [x] **A3.1** `src/features/grid.py`: real C1 for the AOI · *58,218 cells (centre inside AOI), `cell_id = row × n_cols + col` on the reference lattice. **Harsh:** use `xy_to_cell_id(cfg, x, y)` for building centroids (H2.3b); `data/features/grid.gpkg` has the cell polygons.*
- [x] A3.2 `src/features/lulc_features.py`: own-cell fractions (clustering only) per year · *fractions of valid pixels (clouds count as nodata)*
- [x] A3.3 `src/features/context.py`: 250 / 500 m ring fractions excluding the centre cell
- [x] A3.4 `log_dist_built`, `log_dist_water` (EDT at 10 m, sampled at cell centres) → real C2 per year · *built-up distance is to the nearest built pixel **outside** the cell (KD-tree, exact), so it never leaks the cell's own status. **Config change (done check):** `aoi.buffer_m` 1000 → 3000 and `features.distance_cap_m` 5000 → 3000, because distances are only exact up to the buffer (a cell at the AOI edge can't see beyond it). The code now refuses cap > buffer. **Harsh:** your OSM download area grows accordingly; cap road distances at 3 km too.*
- [x] A3.5a `src/features/build.py` merges C2 + C3 → C4 · 🔓 *(stub)* · *`python -m src.features.build`; drops and logs cells with `nodata_frac` > 0.5*
- [x] **A3.5b** Real C4 on the AOI · 🔒 **H3.3** · *`grid_features_{2018,2023}.parquet` + `.gpkg`; checked by `scripts/verify_feature_table.py`.*
- [ ] A3.6 Phase 4 gate passes on real data · 🔒 **H3.3**, 🔒 **G4** (Harsh's gate test)

**A4. Labels and masks** · W4 · P5.5, FR-8.1
- [x] **A4.1** Exclusion mask: water/flooded > 50 %, slope > 15°, nodata > 50 % · *also OSM water polygons from H1.3 if ready: vegetated lakes (e.g. Hulimavu) show as rangeland/wetland in ESRI 2023* · *`src/features/labels.py → exclusion_table(cfg, run)` for **two runs**: `validation` (ESRI 2018+2019 and OSM 2018 water only, time-travel rule) and `final` (2022+2023 and current OSM). Written to `data/features/exclusion_{run}.parquet` with one column per rule. **Harsh (H4.4): use `exclusion_table(cfg, run)` for C7.** Real data: 1,921 excluded in validation (1,450 wet, 472 steep), 2,138 in final. Hulimavu is caught by the 2018/19 water rule.*
- [x] A4.1b Add protected areas (e.g. Bannerghatta NP) to the mask · 🔒 **H1.4** · *optional: skip if not ready by the end of W4 and note it* · *Code done, together with OSM water: both are used when `data/raw/osm/...` exists, and skipped with a warning when it doesn't. **Applied 2026-10-01** after downloading OSM on another network: Bannerghatta NP (relation 8124064) excludes 4,127 cells = 41.3 km², exactly the park's area inside the AOI. OSM 2018 water adds 488 wet cells. Validation exclusions 1,921 → **6,253**; candidates 19,656 → **15,658**; grew 1,129 → **1,125**; evaluated 12,777 (prevalence **8.8 %**). Checked independently in `scripts/verify_labels.py` (point-in-polygon on pixel centres).*
- [x] **A4.2** Candidates, growth labels (2018/19 → 2022/23), change-training positives (2018/19 → 2020/21) → real C5 · *19,656 candidates → 1,129 grew, 15,599 stayed non-built, **2,928 ambiguous** (partly grown; left out of validation, PRD §9.6), 355 change positives. Prevalence 6.7 %. **Contract change:** C5 gained a boolean `ambiguous` column (schema + stubs updated).*
- [x] A4.3 LEI growth type (patches ≥ 0.5 ha, 20 m buffer) → `lei_type` in C5 · *1,038 adjacent, **91 outlying** (few, as the prototype predicted: report descriptively). Agrees with an exact per-patch ring for 239/241 checked cells; the fast version shares rings where two patches touch.*
- [x] A4.4 Unit tests on a synthetic 6-year stack; label counts logged · *done check: `scripts/verify_labels.py`*

**A5. Building similarity** · W6–7 · P6.1, P6.3, P6.4, P6.7
- [x] A5.1 `src/similarity/profiles.py` from `MODEL_INPUTS` only; raises on own-cell or leaky features · 🔓 *(stub)*
- [x] A5.2 `src/similarity/query.py`: building ID or lat/lon → top-N usable cells (Euclidean; cosine optional) + feature explanation + GeoPackage/PNG · 🔓 *(stub)*
- [x] A5.3 `src/similarity/aggregate.py`: kNN mean distance → 0–1 → C8 `similarity_knn` · 🔓 *(stub)*
- [x] **A5.4** Real run: 2018 reference buildings, usable cells only → real C8 `similarity_knn` · 🔒 **H2.3** (real C6), 🔒 **H4.4** (real C7)
- [x] A5.5 Self-query in the top 1 %; results only usable and non-excluded (on real data) · 🔒 **H2.3**, 🔒 **H4.4**
- [ ] A5.6 3–5 example queries in notebook 05

**A6. Validation harness** · W5 · P7.4
- [ ] **A6.1** `src/suitability/validate.py`: ROC-AUC, top-N hit + lift, TOC for any C8 file · 🔓 *(stub)*
- [ ] A6.2 Random + distance-to-built baselines added automatically · 🔓 *(stub)*
- [ ] A6.3 AUC split by LEI type
- [ ] A6.4 `outputs/metrics/validation.json` + ROC/TOC figures; unit tests on known score/label pairs

**A7. Scoring, pipeline and temporal validation** · W8 · P7.1, P7.2, P7.8
- [ ] A7.1a `src/suitability/score.py`: S1–S3/N classes + candidate patches · 🔓 *(stub)*
- [ ] **A7.2a** `src/pipeline.py` skeleton with `--from-stage`; stages call each module's entry function · 🔓 *(stub)*
- [ ] A7.1b Final combined score (similarity + RF weights) · 🔒 **H5.2**
- [ ] **A7.2b** Pipeline runs end to end on real data · 🔒 **H5.2**, 🔒 **H6.2**
- [ ] **A7.3** Validation run over all real C8 files → `validation.json` · 🔒 **H5.2**, 🔒 **H5.3**, 🔒 **H6.2**
- [ ] A7.4 `docs/validation.md`: similarity + temporal sections

**A8. Interactive map** · W9 · P8.3
- [ ] A8.1 `src/viz/interactive.py`: folium layers + popups · 🔓 *(stub)*
- [ ] A8.2 Final `outputs/map.html` with real layers · 🔒 **H4.4**

**A9. Clean-up** · W10 · P8.9, P8.12
- [ ] A9.1 Own modules: docstrings, type hints, ruff + black clean · 🔓
- [ ] A9.2 Fix issues from Harsh's fresh-clone test · 🔒 **H9.1**

**Gate tests Abhinav writes** (checks Harsh's side of each phase)
- [ ] **G1** `tests/gates/test_phase1.py` · W1–2 · 🔓
- [ ] **G3** `tests/gates/test_phase3.py` · W3 · 🔓
- [ ] **G5** `tests/gates/test_phase5.py` · W4 · 🔓
- [ ] **G7** `tests/gates/test_phase7.py` · W7 · 🔓

**Report (Abhinav):** study area ☐ · literature review ☐ · similarity + validation methods ☐ · similarity + validation results ☐

### Harsh: vector and learning track

**H0. Contracts and stubs** · W1
- [ ] H0.1 Draft the vector/model half of `schema.py` (joint PR = J3) · 🔓
- [~] H0.2 Stubs for C3, C6, C7 in `tests/conftest.py` · after J3 · *already generated by `src/synthetic.py` (A0.2); Harsh checks they fit his code and ticks*

**H1. OSM downloads** · W1–2 · P2.4–P2.7
- [x] H1.1 `src/download/osm.py`: Overpass `[date:"2018-01-01T00:00:00Z"]` snapshot + current; mirror fallback (overpass-api.de → kumi.systems → private.coffee); retries; cache to `data/raw/osm/` · 🔓 (any test bbox)
- [x] H1.2 Manifest entries for OSM files · 🔒 **A1.1**
- [x] H1.3 Real download for the AOI: roads, water, buildings × 2 snapshots · after J2 · *2018: 179,740 bldgs / 18,412 roads / 322 water; current: 226,947 / 73,475 / 1,460*
- [x] **H1.4** Protected-area polygons (`boundary=protected_area`, `leisure=nature_reserve`) for the AOI · after J2 · *Bannerghatta NP is `boundary=national_park` (relation 8124064), now included; `data/raw/osm/current/protected.gpkg`*
- [ ] H1.5 `data/raw/osm/` copied to the shared drive; link in `data_sources.md`

**H2. Vector preprocessing and reference buildings** · W2 · P3.4–P3.6, P6.2
- [x] H2.1 `src/preprocess/vector.py`: reproject, `make_valid`, drop empties · 🔓 *(stub)*
- [x] H2.2 Road classes major/minor; unit test on the mapping · 🔓
- [x] H2.3a Building cleaning (< 10 m², outliers), both snapshots · 🔓
- [x] **H2.3b** `cell_id` joined → real C6 for 2018 and current · 🔒 **A3.1** (real grid) · *H2.1–H2.3 done by Abhinav (Tasks.md assigns P3.4–P3.6 to Abhinav), 2026-10-01: `src/preprocess/vector.py`, C6 for both snapshots. This unblocks A5.4/A5.5 (needs C6).*

**H3. Vector features** · W3–4 · P4.4, P4.5
- [x] H3.1 `src/features/distance.py`: rasterise roads, EDT at 10 m, sample at cell centres · 🔓 *(stub)*; unit test: single road → correct metres
- [x] H3.2 Road density (500 m), building count + area fraction (marked leaky) · 🔓 *(stub)*
- [x] **H3.3** Real C3 for both snapshots · 🔒 **A2.1** (reference grid), 🔒 **A3.1** (real grid) · *H3.1–H3.3 done by Abhinav (`src/features/distance.py`; exact vector distances instead of EDT). `data/features/vector_features_{2018,current}.parquet`.*

**H4. Clustering (3 classes)** · W4–5 · P5.1–P5.4, P5.6–P5.8
- ⚠️ *Note for H4 (from A1.4):* ESRI tree cover jumps between years (7.0 % → 2.3 % → 8.4 %), and ESRI shows much of Bannerghatta as rangeland. Take the forest class from one year (`years.latest`) and cross-check with WorldCover 2021 (20 % trees). See notebook 01.
- [x] H4.1 `src/classify/cluster.py`: standardise, optional PCA, K-Means k = 3…10, GMM · 🔓 *(stub or prototype Pune table)*
- [ ] H4.2 Elbow + silhouette + Davies–Bouldin plots · 🔓 *(stub)*
- [x] H4.3 Real clustering on the AOI; choose k and justify · 🔒 **A3.5b** (real C4) · *H4.1/H4.3 done by Abhinav (Tasks.md assigns P5.1–P5.3 to Abhinav): K-Means k = 7 for both runs, `outputs/clusters_{validation,final}.parquet`. H4.2 metrics computed; plots go in notebook 04.*
- [x] **H4.4** `src/classify/label.py`: cluster → class rules + exclusion mask → real C7 · 🔒 **A4.1** · *2026-10-05: rules in `config → labeling` (built must be the largest land group; steep natural vegetation → forest); C7 final + `lulc_3class_validation.parquet`; `exclusion_mask[_validation].tif`; 15 unit tests; Phase 5 gate 9/9*
- [x] H4.5 Evaluation vs ESRI (primary) and WorldCover 2021, collapsed to 3 classes; cluster descriptions in notebook 04 · *Abhinav: `src/classify/evaluate.py` + `export.py` + gate `tests/gates/test_phase5.py` written; waiting for C7 (H4.4).* · *Harsh 2026-10-05: ran `evaluate` (ESRI 96.6 %, WorldCover 64–71 % on land cells); notebook 04 with cluster descriptions, rules, maps and the satellite check*
- [ ] H4.6 Unit tests: labelling rules, mask removes water/steep, same seed = same labels · 🔓

**H5. Learning models and ablation** · W6–7 · P6.5, P6.6
- [x] H5.1 `src/similarity/rf_model.py`: change RF + state RF, class-balanced, `MODEL_INPUTS` only · 🔓 *(stub)*
- [x] **H5.2** Real change RF (2018 features, `chg_train_pos`) → C8 `rf_change` · 🔒 **A3.5b**, 🔒 **A4.2**
- [x] **H5.3** Real state RF → C8 `rf_state` · 🔒 **A3.5b**, 🔒 **A4.2**
- [x] H5.4 Spatial-block CV (2 km) for hyperparameters only · *H5.1–H5.4 done by Abhinav (Tasks.md assigns P6.5 to Abhinav): out-of-fold validation scores, final scores, `rf_probability.tif`; see Tasks P6.5.*
- [ ] H5.5 Group drop-one ablation through the harness → ablation table · 🔒 **A6.1**

**H6. MCDA / AHP baseline** · W7–8 · P7.3, P7.5
- [x] H6.1 `src/suitability/mcda.py`: criteria rescaling, AHP matrix, consistency ratio < 0.1 · 🔓 *(stub)*
- [x] **H6.2** Real MCDA score → C8 `mcda` · 🔒 **A3.5b** · *H6.1/H6.2 done by Abhinav (Tasks.md assigns P7.3 to Abhinav): AUC on grew 0.636, CR 0.003; see Tasks P7.3.*
- [ ] H6.3 MCDA section of `docs/validation.md` · 🔒 **A7.3**

**H7. Sensitivity analysis** · W8 · P7.6
- [ ] H7.1 Cell size 50 / 100 / 200 m, slope threshold, k; results table · 🔒 **A7.2b**

**H8. Static maps and charts** · W9 · P8.1, P8.2
- [ ] H8.1 `src/viz/static_maps.py`: shared style (title, legend, scale bar, north arrow, basemap), 300 dpi · 🔓 *(stub)*
- [ ] H8.2 Clustering charts, feature importance + ablation · after H4.5, H5.5
- [ ] H8.3 Final maps and ROC/TOC figures · 🔒 **A7.3**

**H9. Fresh-clone test** · W10 · P8.11
- [ ] **H9.1** Clone to a new folder, create env, download, run pipeline + notebooks; list issues · 🔒 **A7.2b**
- [ ] H9.2 Own modules: docstrings, type hints, ruff + black clean · 🔓

**Gate tests Harsh writes** (checks Abhinav's side of each phase)
- [x] **G2** `tests/gates/test_phase2.py` · W2 · 🔓 · *72/72 on Harsh's laptop*
- [x] **G4** `tests/gates/test_phase4.py` · W3 · 🔓 · *2026-10-05: 19 checks incl. shapely distance spot checks and the time-travel rule; mutation-tested (10/10 caught)*
- [ ] **G6** `tests/gates/test_phase6.py` · W6 · 🔓
- [ ] **G8** `tests/gates/test_phase8.py` · W9 · 🔓

**Report (Harsh):** introduction ☐ · data ☐ · clustering + RF + MCDA methods ☐ · clustering + RF + MCDA results ☐

### Milestones (both tick to sign off)

- [ ] **M1 Thin slice** (end W3): real grid (A3.1) + real C2 (A3.4) + real C3 (H3.3) + labels (A4.2) → distance-to-built baseline scored by the harness (A6.1) · Abhinav ☐ Harsh ☐
- [~] **M2 Full feature table** (end W4): A3.5b and A4.1 done; Phase 4 gate green · Abhinav ☐ Harsh ☑ (gate 19/19 on Harsh's laptop, 2026-10-05)
- [ ] **M3 All scores** (end W7): A5.4, H5.2, H5.3, H6.2 written and passing the contract test · Abhinav ☐ Harsh ☐
- [ ] **M4 Validation complete** (end W8): A7.3 done; `validation.json` has every model + baselines · Abhinav ☐ Harsh ☐

### Who waits on what

Do these first: each one unblocks the other person.

| Blocking task | Owner | Unblocks |
|---|---|---|
| A1.1 io_utils | Abhinav | H1.2 |
| A2.1 reference grid | Abhinav | H3.3 |
| A3.1 real grid | Abhinav | H2.3b, H3.3 |
| A3.5b real feature table | Abhinav | H4.3, H5.2, H5.3, H6.2 |
| A4.1 exclusion mask | Abhinav | H4.4 |
| A4.2 labels | Abhinav | H5.2, H5.3 |
| A6.1 harness | Abhinav | H5.5 |
| A7.2b pipeline end to end | Abhinav | H7.1, H9.1 |
| A7.3 validation run | Abhinav | H6.3, H8.3 |
| H1.4 protected areas | Harsh | A4.1b (optional) |
| H2.3b real buildings (C6) | Harsh | A5.4, A5.5 |
| H3.3 real vector features (C3) | Harsh | A3.5b, A3.6 |
| H4.4 real 3-class map (C7) | Harsh | A5.4, A5.5, A8.2 |
| H5.2 / H5.3 RF scores | Harsh | A7.1b, A7.2b, A7.3 |
| H6.2 MCDA score | Harsh | A7.2b, A7.3 |
| H9.1 fresh-clone report | Harsh | A9.2 |
| G4 gate test | Harsh | A3.6 |

**Critical path:** A2.1 → A3.1 → H3.3 → A3.5b → H5.2 → A7.3.
- The raster track feeds most of Harsh's real-data work, so **Abhinav's blockers (A1–A4) have priority in W1–W4**.
- Harsh fills that time with stub development (H1–H4), gate tests and the literature review.

---

## 6. Working without blocking each other

- **Branches:** everything goes straight to `main`, with **one commit per finished work package** (message starts with its ID, e.g. `A2: ...`). The other person reviews the commit within 24 h.
- **Done check:** after every package, and before ticking it or committing, run the done check in [CLAUDE.md](CLAUDE.md#done-check-after-every-work-package--phase): tests, lint, contracts, an **independent correctness check of the outputs** (a `scripts/verify_*.py` script), reproducibility, then record and commit. Example: `scripts/verify_raw_data.py` for A1 found a sub-pixel shift that all unit tests missed.
- **Folder ownership avoids merge conflicts:**
  - **Abhinav:** `download/lulc.py`, `download/dem.py`, `preprocess/raster.py`, `preprocess/terrain.py`, `features/{grid,lulc_features,context,labels,build}.py`, `similarity/{profiles,query,aggregate}.py`, `suitability/{validate,score}.py`, `viz/interactive.py`, `pipeline.py`
  - **Harsh:** `download/osm.py`, `preprocess/vector.py`, `features/distance.py`, `classify/*`, `similarity/rf_model.py`, `suitability/mcda.py`, `viz/static_maps.py`
  - **Shared, edited only in joint PRs:** `features/schema.py`, `config/config.yaml`, `docs/PRD.md`, `docs/Tasks.md`
- **Notebooks:**
  - Abhinav owns 01 (download), 03 (features), 05 (similarity) and 06 (validation).
  - Harsh owns 02 (preprocessing) and 04 (clustering), and adds the RF + MCDA sections as a separate `05b_models.ipynb`.
- **Data sharing:** each person runs both downloaders once. They're idempotent and cached, so nobody waits for the other to upload files. The OSM 2018 snapshot is the slow one, so Harsh also puts `data/raw/osm/` on the shared drive.
- **Sync:** 15-minute check-in twice a week (Mon, Thu), plus the milestone reviews M1–M4.
- **When blocked:** never start a 🔒 task early (§5). Keep working on the stub. If a contract has to change, open the `schema.py` PR the same day.

---

## 7. Balance check

| | Abhinav | Harsh |
|---|---|---|
| Downloads | LULC ×2 sources + DEM | OSM ×2 snapshots, mirrors, cache |
| Preprocess | raster alignment, slope, class mapping | vector cleaning, road classes, reference buildings |
| Features | grid, fractions, rings, 2 distances, merge | 2 road distances, density, building metrics |
| Labels | mask, growth, change positives, LEI | — |
| Models | similarity (query + aggregate) | clustering, change RF + state RF, MCDA |
| Evaluation | harness + temporal run | ablation, sensitivity |
| Viz | interactive map | static maps + charts |
| Gate tests | 1, 3, 5, 7 | 2, 4, 6, 8 |
| **Core hours** | **~41** | **~40** |

Harsh has more models; Abhinav has the labels, the harness and the pipeline. Both have one data pipeline, one visual output and four gate tests.

---

## 8. Risks for this plan

| Risk | Mitigation |
|---|---|
| Contracts change halfway | `schema.py` + contract tests from Week 1; changes only through joint PRs |
| Overpass historical query fails | Three mirrors, a cached download, and a shared-drive copy. **Last resort:** major roads only, which barely leak (prototype AUC 0.53 → 0.55) |
| Similarity doesn't beat distance-to-built (likely, going by the prototype) | Planned for: the report frames similarity's value as **explainable per-building queries**, and the baselines are always shown. Stretch: add NDVI or 2018 building density to the profiles |
| AOI decision slips | Default D1 applies at the end of W1. All code is AOI-agnostic through the config |
| Deadline shorter than 10 weeks | Drop in this order: H7 sensitivity → LEI breakdown → state RF → cell-size experiments. Keep: clustering, similarity, change RF, MCDA, temporal validation |
| One person falls behind | Milestones M1–M4 surface it early. Stub-based work means the other person isn't blocked; rebalance packages at the milestone review |
