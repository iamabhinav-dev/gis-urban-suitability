# Validation

How well does each score predict where Bengaluru South actually grew? This document records the
metrics, figures and misses (PRD §9.8, deliverable D13). Numbers come from
`outputs/metrics/*.json` (mainly `validation.json`, written by `src/suitability/validate.py`);
figures are in `outputs/figures/`. Every number below is recomputed independently by
`scripts/verify_suitability.py`, `verify_similarity.py`, `verify_similarity_models.py`,
`verify_mcda.py` and `verify_sensitivity.py`.

## 1. Design

Every score is computed **as of 2018** (the validation run):
- 2018 land cover;
- the 2018-01-01 OSM snapshot;
- a 3-class map and exclusion mask built from data up to 2019 (time-travel rule, D12);
- 2018 reference buildings.

It is then compared with **persistent growth**: candidate cells (non-built in 2018 and 2019, not
excluded) that are built in **both 2022 and 2023** (`grew`, C5). Cells that are neither clearly
grown nor clearly non-built in 2022/23 (`ambiguous`) are left out. That leaves **12,777
candidate cells, of which 1,125 grew (8.8 %)**: 1,034 next to existing built-up land
(`adjacent`) and 91 away from it (`outlying`), by the landscape expansion index.

**Leakage guards:**
- No model sees a cell's own land cover or building count (D4, `schema.check_model_inputs`).
- Models trained on growth labels are scored **out of fold** with 2 km spatial blocks (D11).
- The combined score's weight is chosen on the 2020/21 training label, never on `grew`.
- Distance to built-up and random are always shown as baselines (D7).

**Time-travel exceptions** (static layers, FR-8.2): the Copernicus DEM (2011–2015 acquisition,
terrain treated as static) and the OSM protected-area boundary (Bannerghatta National Park,
current snapshot; a park boundary, not something that grows). Both are used in both runs.

## 2. Headline results

| Score | AUC | Precision, top 10 % | Lift, top 10 % | Lift, top 30 % | AUC adjacent | AUC outlying |
|---|---|---|---|---|---|---|
| **Combined suitability** | **0.797** | **30.4 %** | **3.45** | **2.40** | 0.822 | 0.512 |
| Change RF (out of fold) | 0.779 | 28.5 % | 3.23 | 2.27 | 0.803 | 0.512 |
| Building similarity (kNN) | 0.773 | 26.4 % | 2.99 | 2.22 | 0.796 | 0.511 |
| *Distance to built-up* | 0.763 | 26.8 % | 3.04 | 2.15 | 0.792 | 0.439 |
| State RF (out of fold) | 0.702 | 29.0 % | 3.29 | 1.92 | 0.722 | 0.484 |
| MCDA / AHP | 0.636 | 16.4 % | 1.86 | 1.64 | 0.655 | 0.420 |
| MCDA without land cover | 0.614 | 15.3 % | 1.73 | 1.46 | 0.630 | 0.430 |
| *Random* | 0.499 | 8.8 % | 1.00 | 1.02 | 0.501 | 0.477 |

*Italics: baselines.* Figures: `chart_roc.png`, `chart_toc.png`, `chart_growth_type.png`.

**Against the PRD targets (§9.8):**
- Best model ≥ distance to built-up: **met** (0.797 vs 0.763).
- Lift ≥ 2 in the top 10 %: **met** (3.45).
- **S1 + S2 hit rate:** the S1 and S2 classes of the validation run hold 25 % of the evaluated
  cells and **65.2 % of the growth** (precision 22.9 %, lift 2.60). They are 30 % of all
  candidates: the 2,881 ambiguous cells left out of the evaluation (partly built by 2022/23)
  fall in S1 + S2 twice as often (52 %), so the scores also rank partial growth high.

**Combining helps.** The combined score (0.3 × similarity + 0.7 × change RF, within-run
percentiles) beats both of its parts. They rank cells differently enough to complement each
other: the similarity never sees a growth label, while the RF learns from 2020/21 change.

**Out-of-fold scoring matters.** Scored on its own training cells, the change RF would claim
AUC 0.997 against its honest 0.779. Its 2020/21 training positives are mostly also 2022/23
growth cells (`scripts/verify_similarity_models.py`, check 3).

## 3. Growth type: where every model fails

All scores find growth next to existing built-up land well (AUC ~0.80–0.82). For **outlying**
growth they are at chance (~0.51), and distance to built-up and MCDA are *below* chance (0.44,
0.42), because outlying growth is by definition far from built-up land. This matches Wang et
al. (2021): diffusional growth is much harder to predict than aggregated growth. Outlying growth
is only 8 % of the grown cells (91 of 1,125) here, so it hardly moves the overall AUC.

## 4. Ablation: which surroundings carry the signal

Each feature group dropped in turn (FR-8.5; `chart_ablation.png`):

| Dropped group | Change RF ΔAUC | Similarity ΔAUC |
|---|---|---|
| Built-up nearby (250 / 500 m rings, distance to built-up) | **−0.034** | **−0.057** |
| Land cover nearby (tree, crop, rangeland, bare, water rings) | −0.016 | +0.007 |
| Terrain (elevation, slope) | −0.012 | −0.001 |
| Roads (distances, density) | +0.002 | −0.003 |
| Water (distance to water) | +0.005 | −0.002 |

Built-up land nearby is by far the most important group for both. Roads and water add nothing
once the built-up context is known: road access is already implied by nearby built-up land.
Nearby land cover helps the RF but not the similarity.

## 5. MCDA / AHP baseline (P7.3, P7.5)

Five criteria, each rescaled to 0–1 (`src/suitability/mcda.py`, `config.yaml → mcda`):

| Criterion | 1 (most suitable) → 0 | AHP weight | AUC alone |
|---|---|---|---|
| Distance to built-up | next to built-up → ≥ 2 km | 0.298 | **0.763** |
| Distance to a major road | on the road → ≥ 3 km | 0.298 | 0.548 |
| Slope | flat → ≥ 15° | 0.158 | 0.612 |
| Land cover | rangeland / bare 1, crops 0.6, trees 0.2 | 0.158 | 0.527 |
| Distance to water | ≥ 200 m → within 100 m | 0.089 | 0.518 |

Pairwise matrix on Saaty's 1–9 scale: λmax = 5.013, **consistency ratio 0.003** (< 0.1).

**Why the overlay does worse than one of its own criteria.** Only distance to built-up carries
real signal. The AHP weights give the near-random criteria 70 % of the weight, which dilutes
it: the overlay scores 0.636, below distance to built-up alone (0.763), with a lift of only 1.86
in the top 10 %.

We did **not** tune the weights on `grew`, which is the test set. A fixed, defensible expert
overlay is what this baseline stands for.

**Is the land-cover criterion a leak?** No. D4 bans own-cell land cover from *trained* models,
because the fractions sum to 1 − built. MCDA is not trained, and the validation scores only
cells that were non-built in 2018/19. The score metadata lists it as `own_cell_inputs`, apart
from `features`.

## 6. Held-out building check (P6.6)

Reference cells are held out by 2 km block. Each scorer learns from the other blocks and ranks
every non-excluded cell in the held-out blocks.

| Scorer | AUC (held-out reference vs other cells) | Median percentile (best possible 70.0) |
|---|---|---|
| Random forest | **0.984** | 70.0 |
| kNN similarity, all inputs | 0.895 | 68.5 |
| Distance to built-up | 0.887 | 65.5 |
| kNN similarity, 500 m rings only | 0.871 | 66.9 |

Keeping both ring scales beats 500 m only, despite their correlation (r 0.91–0.95, notebook 03).

**Self-query sanity:** for every sampled building, a cell within one cell of it is in the top
1 % of the query's ranking, even with its own cell left out (Phase 6 gate,
`scripts/verify_similarity.py`).

## 7. Sensitivity (P7.6)

`src/suitability/sensitivity.py` → `sensitivity.json`; figure `chart_sensitivity.png`.

**Slope threshold** (exclusion mask and the MCDA slope criterion):

| Slope | Slope-excluded cells | Candidates | Grew | Change RF | Dist. to built-up | MCDA |
|---|---|---|---|---|---|---|
| 10° | 1,685 | 15,288 | 1,101 | 0.774 | 0.759 | 0.646 |
| **15°** | 472 | 15,658 | 1,125 | **0.779** | **0.763** | **0.636** |
| 20° | 158 | 15,762 | 1,130 | 0.780 | 0.765 | 0.633 |

**Number of clusters k** (final run): class shares move by about 1 percentage point and agreement
with ESRI on land cells stays at 96.6–98.8 %. k = 5 agrees slightly better with ESRI but loses
the steep-rangeland cluster (the Bannerghatta hills): forest drops from 5.0 % to 3.9 %. k = 7
keeps the best silhouette (0.606).

**Cell size** (features and labels rebuilt at each size):

| Cell | Cells | Candidates | Grew | Change RF | Dist. to built-up | MCDA |
|---|---|---|---|---|---|---|
| 50 m | 232,785 | 68,888 | 6,235 | 0.797 | 0.769 | 0.631 |
| **100 m** | 58,218 | 15,658 | 1,125 | **0.779** | **0.763** | **0.636** |
| 200 m | 14,567 | 3,307 | 148 | 0.780 | 0.778 | 0.647 |

The results barely depend on the cell size: the change RF scores 0.78–0.80 and distance to
built-up 0.76–0.78 at every size. The labels do change with the cell (a 50 m cell is "built" at
a finer grain), and at 200 m only 148 cells grew, so differences of a few thousandths are noise.
**The ranking change RF > distance to built-up > MCDA holds at every size**, though only by
0.003 at 200 m.

## 8. Final map

The final run applies the same models to the latest data (2023 land cover, OSM pinned at
2026-10-01):
- **Classes** (usable cells only; forest, built-up and excluded are N): S1 1,382 cells, S2
  2,762, S3 4,144, N 5,526 (`map_suitability_classes.png`).
- **Candidate sites:** 557 S1 patches (1,382 ha). The 20 best patches of at least 5 ha are the
  top sites (`outputs/candidates.gpkg` / `.csv`, interactive map `outputs/map.html`).
- **Check against an independent source:** the top sites overlap OSM lakes by 0.06 ha and
  protected areas by 0 ha.

## 9. Misses and limitations

- **Mostly edge expansion.** The combined score beats distance to built-up by 0.034 AUC: a real
  but modest gain. Growth here is mostly next to existing built-up land, which a single
  distance already captures. Outlying growth is not predicted by any model.
- **OSM completeness.** Road mapping grew a lot between 2018 and today (median road density
  3.0 → 12.4 km/km²), mostly through mapping effort, not construction.
  - Each run uses its own OSM snapshot, and the RF uses within-year percentiles.
  - OSM buildings cover only about 1 % of built cells in the south in 2018, so ESRI built cells
    fill the reference set.
  - Almost no buildings are typed, so similarity per building type (P6.7) was not possible.
- **Land-cover errors.** ESRI and WorldCover disagree on built-up land (62 % vs 33 % of the
  AOI): ESRI generalises urban areas. Growth labels inherit ESRI's errors; the two-year rule
  (D3) removes flicker but not systematic bias.
- **Small candidate patches.** Half of the S1 patches are single 1-ha cells, often small
  pockets inside built-up areas. Top sites are therefore taken from patches of at least 5 ha.
- **Past growth ≠ good planning.** Every score learns or encodes where building *has* happened,
  not where it *should*. Protected areas, water and steep slopes are excluded, but other
  constraints (zoning, flood risk, infrastructure capacity, land ownership) are not in the data.
