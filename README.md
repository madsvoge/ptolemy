# Ptolemy's Geographica, reconstructed from topostext

A topostext-native reconstruction of Claudius Ptolemy's world map: every
coordinate his catalogue gives, plotted; coastlines, rivers, mountain
ranges and islands rebuilt from the *order and wording* of his own
description. **topostext.org's English translation of work/209** (Brady
Kiesling, from Karl Nobbe's 1843 Greek text) is the sole source -- no
modern gazetteer, no other manuscript tradition, no cross-reference to any
other Ptolemy dataset.

This is a fresh, standalone project (see `topostextengineprompt.md`-derived
brief in the commit history for the original design mandate). It does not
share code or data with any project reconstructing the same map from a
different critical edition -- those are different manuscript traditions
with their own point counts and section boundaries, and mixing them would
introduce silent misalignment.

## Pipeline

```
data/raw/ptolemy_nobbe.txt
        |
        v
ptolemy/parser.py     Step 1  -- split into § book.map.section paragraphs,
                                  extract every (name_phrase, lon, lat)
                                  citation in document order
ptolemy/points.py     Step 1  -- dedup near-identical coordinates (~0.05°)
                                  into canonical Points, scoped per book.map
ptolemy/classify.py   Step 2  -- classify each section's own narrative type
                                  (coastal / inland / island / mountain /
                                  boundary), inheriting across a no-signal
                                  continuation within the same book.map
ptolemy/tag.py        Step 3  -- tag every point's own category from its
                                  name text + its section's resolved type
ptolemy/coords.py     Step 4  -- Ferro -> modern longitude conversion
ptolemy/export_json.py Step 5 -- declarative book -> chapter -> section ->
                                  point JSON export
ptolemy/lines.py      Step 6  -- the line-drawing engine: coastline trail
                                  decomposition, river/mountain grouping by
                                  name, island-walk detection
ptolemy/export_gpkg.py Step 7 -- GeoPackage export (one layer per feature
                                  kind + a full points layer)
ptolemy/visualize.py  Step 8  -- matplotlib smoke-test renders
ptolemy/pipeline.py            -- orchestrates all of the above
```

## Running it

```
pip install -r requirements.txt
python -m ptolemy.pipeline          # writes output/ptolemy.{json,gpkg} + PNGs
python -m scripts.verify            # prints the verification report below
python -m pytest tests/             # 39 unit tests covering the parsing/
                                     # classification/tagging gotchas found
                                     # while building this
```

`output/` is gitignored (generated); re-run the pipeline to reproduce it.
`output/ptolemy_map.png` renders the whole known world; `ptolemy_ireland.png`,
`ptolemy_britain.png`, `ptolemy_italy.png` are the brief's suggested
spot-check regions -- Britain in particular reproduces Ptolemy's famous
"bent-over Scotland" distortion, a good sign the reconstruction is reading
his actual catalogue order rather than an idealized shape.

## Key design decisions (and why)

- **Parsing gotchas** (all found empirically against this exact text, all
  covered by regression tests in `tests/test_parser.py`): the `§ i` and
  `§ 4.8[9].1`-style non-standard markers; bare-degree coordinates with no
  minutes; a stray footnote letter (`d`, `e`, `W`) standing in for the
  `.`/`,` separator between longitude and latitude; and the dominant
  failure mode found in the south-latitude marker -- of ~480 candidate `S`
  sightings, only 56 are real hemisphere markers, the other ~424 are the
  next citation's own name starting with a capital S ("...58°00'
  **S**outhern promontory"), which a naive `S\.?` regex swallows whole.

- **Dedup tolerance** (~0.05°, per the brief's suggested starting point)
  was re-derived empirically against this text (`points.py`): loosening it
  to catch a couple of remaining near-miss restatements starts merging
  hundreds of genuinely distinct points, so 0.05° stands.

- **Section classification** (`classify.py`) deliberately does *not* treat
  a bare "island"/"mountain" keyword as its own signal -- Ptolemy opens
  the coastal walk of every insular region ("Setting of Hivernia British
  island", "Kyrnos island...is surrounded on the west") with exactly that
  word, and a bare-keyword match would misclassify every one of them as an
  island-*list* section. The real signal is the word acting as the subject
  of a list-introducing clause ("islands lying off X", "the named mountains
  in Y are"), confirmed against the ~80 lead_texts containing "island" and
  ~140 containing "mountain" across books 2-7.

- **Point tagging** (`tag.py`) has one non-obvious override: a tribal
  aside folded into an otherwise coastal section ("The Caletes occupy the
  northern coast...their city is Iuliobona") cites a real *inland* capital,
  not a coastal waypoint -- left to the naive section-type default it
  breaks catalogue-order adjacency badly enough to self-intersect the
  drawn coastline. Recognized once, generalized as "city-idiom" and
  "reference-marker" (mid-point/extreme-point/already-mentioned) regexes,
  not per-name exceptions.

- **Coastline stitching** (`lines.py`) tries all four end/start
  orientations when joining two trails, not just forward -- confirmed
  necessary on the brief's own worked example (2.2, Ireland): the
  north-coast run and the west/south/east run join **end-to-end**
  (Rhobogdium promontory sits next to the east coast's last point), not
  end-to-start, because Ptolemy's prose revisits the Boreum corner
  explicitly to *open* the second run rather than close the first.

## Verification

`python -m scripts.verify` reports, against the full corpus:

- 1,347 sections parsed (281 carrying zero coordinates -- kept, since a
  zero-point section's lead_text can still signal what kind of section
  follows); 6,253 raw citations dedup to 6,163 canonical points.
- Section types: 638 coastal, 437 inland, 225 boundary, 29 island, 18
  mountain -- consistent with the brief's own structural prior (coastal
  walk -> inland tail -> island/mountain appendix), spot-checked with no
  book.map showing more than 3 coastal/inland alternations.
- **Self-intersection check** on all 95 drawn lines: 31 still
  self-intersect. Every case investigated during development traced to one
  of two things: (a) a real classification/tagging gap, which got fixed
  with a general rule and a regression test, not a one-off patch -- the
  Pannonia (2.14), Cisalpine Gaul (3.1), and Cycladic-islands (3.14) cases
  in particular; or (b) a genuine non-monotonic sequence in topostext's own
  citation order, confirmed against the raw text directly (5.10.2's
  Kolchis coast zigzags in the source itself: Neapolis then *back* north
  to the Kyaneos river mouth then south again). This pipeline does not
  second-guess (b) -- a plotted position is "what Ptolemy's text claims,"
  distortion included, per the brief's own Step 4 guidance.
- Known points land roughly where expected once Ferro-converted: Boreum
  promontory (Malin Head, Ireland) at modern (-6.67°, 61.0°) against a real
  (-7.4°, 55.4°) -- latitude is Ptolemy's own well-documented northward
  skew, longitude is close. Rome at modern (19.0°, 41.67°) against a real
  (12.5°, 41.9°) -- the ~6.5° eastward longitude error is the same
  Mediterranean-stretching distortion documented in Ptolemy scholarship.

## What's deliberately not attempted

- **Islands** (`lines.py: build_islands`): per the brief, there's usually
  nothing in the text that reliably distinguishes "one island's detailed
  shore" from "a list of different islands" beyond an individually
  confirmed case. Rather than guess, island points are only connected when
  the *same* base name is cited consecutively within an island-list
  section (reusing the exact same grouping machinery as rivers/mountains,
  not a bespoke mechanism) -- otherwise they stay standalone points on the
  points layer.
- Ptolemy's own circumference-driven distortion is not corrected for
  anywhere in this pipeline, per the brief's explicit instruction: a
  plotted point is "what Ptolemy's text claims," not ground truth.
