# Field Shift

Crop choice, climate risk and early warnings for farmers in Azerbaijan, built on NASA data and AI.
NASA Space Apps Challenge 2026, Team Earthly. The design follows the `FieldShift_EN.pdf` deck.

## Run

```bash
./refresh_data.sh            # first time only: downloads every dataset and builds data/fieldshift.db
./run.sh                     # http://127.0.0.1:8077  (reads backend/.env: DEEPSEEK_API_KEY)
backend/.venv/bin/python -m etl.seed_demo           # optional: sample farmers/buyers/reviews, shown with a "Demo" badge
backend/.venv/bin/python -m etl.seed_demo --remove  # delete all demo accounts
```

Dev mode: `cd frontend && npx vite` (proxies `/api` to :8077).

## What's inside

| Feature | Where | Data |
|---|---|---|
| District map (GIS choropleth, 12 layers) | `/map` | geoBoundaries ADM2 + all sources below |
| Past vs now climate, 1981–2026 | home, district pages | NASA POWER daily (MERRA-2, AG) per district centre |
| Future climate 2026–2050 | home, district › Climate | NASA NEX-GDDP-CMIP6, SSP2-4.5, 5 models, per district, delta-corrected to NASA POWER |
| Soil | district › Overview | ISRIC SoilGrids 2.0, 0–30 cm, zonal mean per district |
| Crop recommendations | district › Crop recommendations | FAO ECOCROP + NASA climate + SoilGrids pH + AzStat yields + CMIP6 |
| Official yields & production, 2000–2025 | stats, district › Yields | AzStat (stat.gov.az) regional tables, 41 crops × 72 districts |
| Yield forecast, back-tested | district › Yields | climate ML vs persistence, chosen on 2016–19, scored on 2020–25 |
| District leaderboard (Leader / Good / Average / Low) | `/stats` | AzStat yield index vs national |
| NASA satellites now: MODIS NDVI, SMAP root-zone soil moisture, GPM IMERG 7-day rain | map layers + image overlays, district page, drought alert | NASA GIBS (no login): images decoded via published colormaps, zonal means per unit (`app/satellite.py`, label grids from `etl.sat_labels`), refreshed every 12 h |
| Live weather, 16 days | district › Live weather, `/alerts` | Open-Meteo (ECMWF/ICON/GFS) |
| Monitoring + alerts + advice | `/alerts` | frost, heat, heavy rain, wind, dry spell, forecast misses; checked every 3 h |
| SMS | `/alerts` phone view | **simulated**, stored in `sms_outbox` |
| Accounts, farms, contacts | `/account`, `/farmers` | farmers list districts, crops, phone/WhatsApp/Telegram |
| Buyer ratings (1–5 ★) & reviews | farmer profile; map layer; leaderboards | user-generated |
| AI chat | `/chat` | DeepSeek (`deepseek-chat`) with tools that query the database |
| Feedback+ | `/feedback` | ideas / bugs / data issues / praise, votes, comments, app rating |

## World layer

Outside Azerbaijan the unit is the province (geoBoundaries ADM1): 198 countries, 3,234 provinces, each in the same
`rayons` table (`iso3`, `level='province'`), so every district feature works for them. Map: `/map?view=near|world`,
click a country to drill into its provinces. Stats: *World ranking* and *Compare countries* (FAOSTAT).

| Layer | Source | Notes |
|---|---|---|
| Province climate 1981–today | NASA POWER | point at farmland elevation (20th pct, NOAA ETOPO1); temperatures lapse-rate corrected from the MERRA-2 cell (6.5 °C/km, cap 1.5 km) |
| 2026–2050 projections | NASA NEX-GDDP-CMIP6 SSP2-4.5, 5 models | global request per file at 2° stride, nearest land cell, delta method vs POWER 1995–2014 |
| Soil | SoilGrids 2.0 | global ~6 km coverages, zonal mean per province |
| Yields | FAOSTAT QCL | country level only; pomegranate has no FAOSTAT item |

## Honest notes

- For most crops, "next year ≈ this year" beat the climate ML model on validation, so the app shows that baseline with its
  measured error instead of a worse model. Maize is the only crop where climate ML won.
- Province yields are FAOSTAT country values: sub-national official statistics are not published consistently worldwide.
- A province's climate is one farmland-elevation point; very large or mountainous provinces vary more than one point shows.
- Ağdərə has no polygon in geoBoundaries (merged into its neighbours). Its data uses the town's coordinates.
- AI chat is switched off when `DEEPSEEK_API_KEY` is not set. The rest of the app does not need it.
- Demo accounts (`users.is_demo=1`) are sample people: their districts and crops come from real AzStat data, but names,
  contacts and reviews are invented. They carry a Demo badge, their contacts are not clickable, and they cannot sign in.

## Layout

```
backend/app      FastAPI: main.py (routes), services.py, alerts.py, chat.py, weather.py, sms.py, auth.py, db.py
backend/etl      regions, soil, fetch_power, fetch_nex, crops, build_db, seed_demo
frontend/src     React + Leaflet + Recharts (pages/*)
data/            raw downloads, regions.geojson, fieldshift.db
```
