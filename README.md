# Dawei District floods and landslides, 26–27 September 2026

Interactive situation dashboard built from one field report by **Dawei Watch**
(27 Sep 2026, <https://web.facebook.com/share/p/18PNp9p4T4/>), with every place it
names geocoded onto **MIMU** (Myanmar Information Management Unit) geography.

**Live dashboard:** <https://geonet-myanmar.github.io/dawei-flood-dashboard/>

Or open `index.html` locally. It is fully self-contained (data inline; Leaflet
from cdnjs), and the MIMU vectors are the basemap. Optional satellite and
topographic tiles work when the page is served normally.

## What is on the page

- Headline figures: bodies recovered, missing, houses buried, people sheltering,
  Thayetchaung's official affected count, the record 280 mm rainfall at Dawei.
- Map: 47 reported sites (colour = what happened, shape = flood/landslide),
  the Poe Zar Pin road block, flooded Thayetchaung wards, village tracts with a
  report, and MIMU reference layers: all villages, hospitals, schools, roads,
  railway, bridges, rivers, land below 5 m, mine sites, Dawei SEZ.
- Charts: September daily rain and the 25–28 Sep storm build-up (Open-Meteo model,
  with the DMH gauge record), casualty/damage ledger, facilities within 1 km of
  reported sites, township comparison, timeline, quotes (Myanmar + English).
- Spatial analysis: what lies on the Launglon peninsula beyond the landslide
  that stopped the rescue convoy (54 villages, 30 schools, 1 hospital).

## Rebuild

```
pip install -r requirements.txt
python scripts/01_download_mimu.py    # MIMU GeoServer WFS -> data/raw/ (gitignored)
python scripts/02_fetch_rainfall.py   # Open-Meteo -> data/source/rainfall_openmeteo.json
python scripts/03_build_reports.py    # report -> data/processed/flood.json (geocoded)
python scripts/04_process_gis.py      # clip/simplify + analysis -> data/processed/
python scripts/05_build_html.py       # src/template.html + data -> index.html, dist/
```

Script 02 caches its result: model hours are replaced by analysis values over
time, so re-running it later will change the rainfall numbers. Skip it to keep
the published figures.

Never hand-edit `index.html`; edit `src/template.html` and re-run script 05.

## Sources and limits

- Report text: `data/source/dawei_watch_2026-09-27.txt`. Figures are as reported
  on 27 Sep, unverified, while landslides were ongoing.
- MIMU: boundaries v9.4, village points v9.7, wards v9.4, health facilities 2020
  (hospitals only), formal schools 2019, roads 1:250k, bridges, mining areas
  (2004–16 imagery), land below 5 m, industrial zones 2024.
- Geocoding grades (in `flood.json`): 40 exact, 2 variant spelling/township,
  2 probable, 2 approximate, 1 not found.
- Rainfall curves are Open-Meteo model output, not gauges.

## Deployment

GitHub Pages serves `index.html` from the root of the `main` branch
(`.nojekyll` skips the Jekyll build). To publish a change: re-run
`scripts/05_build_html.py`, commit `index.html` together with the source change,
and push. `data/processed/` and `data/source/` are committed so step 5 runs without
re-downloading MIMU data.
