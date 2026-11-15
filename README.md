# Field Shift: Kür salt-water intrusion forecast

**NASA Space Apps Challenge 2026 · Team Earthly**

Field Shift forecasts, every day, how far salty Caspian Sea water has pushed up the lower Kür river (Azerbaijan),
and turns that distance into a status for every pump, field and village along the last 160 km of the river.
It runs on NASA satellite and reanalysis data (SWOT, POWER, GRACE/GRACE-FO, Landsat), with open river-discharge
forecasts from Copernicus GloFAS. It is live, refreshed every 3 hours, with a 16-day outlook.

Live: <https://fieldshift.olimpedia.site> · Monitor: <https://fieldshift.olimpedia.site/monitor> · Farmer app: <https://fieldshift.olimpedia.site/app>

---

## Contents

1. [The physical problem](#1-the-physical-problem)
2. [System overview](#2-system-overview)
3. [Data sources](#3-data-sources)
4. [The salt-front model](#4-the-salt-front-model)
5. [From distance to status](#5-from-distance-to-status)
6. [Ground observations and data fusion](#6-ground-observations-and-data-fusion)
7. [Alerts](#7-alerts)
8. [Irrigation plan (FAO-56 water balance)](#8-irrigation-plan-fao-56-water-balance)
9. [Soil salinity trend (Landsat)](#9-soil-salinity-trend-landsat)
10. [Basin water loss (GRACE)](#10-basin-water-loss-grace)
11. [Back-test 2020–2026](#11-back-test-20202026)
12. [Replay of past events](#12-replay-of-past-events)
13. [API reference](#13-api-reference)
14. [Data files and database](#14-data-files-and-database)
15. [Build, run, deploy](#15-build-run-deploy)
16. [Repository layout](#16-repository-layout)
17. [Limitations](#17-limitations)
18. [Credits and licences](#18-credits-and-licences)

---

## 1. The physical problem

At a river mouth, fresh river water flows out over denser sea water. Caspian water carries 12–13 g/l of salt
(about 20 dS/m), so it is roughly 1 % denser than the Kür. When the river is strong it holds the sea back at the mouth.
When river discharge drops, and a north-easterly wind piles Caspian water against the Kür delta, the heavier salt water
creeps upstream along the river bed as a **salt wedge**. The surface can stay fresh while an intake near the bed draws
brackish water.

The lower Kür has weakened over recent dry years. Azerbaijan reports a decline of more than 25 % in water resources
over the last four years, and NASA GRACE shows the Kür–Araz basin losing 22.5 cm of water-equivalent storage in
2002–2022 (section 10). Intrusion of 30 km and more has been reported in the press (March 2022).

Irrigation water above 3 dS/m causes severe yield restriction (FAO, Ayers & Westcot 1985). Caspian water is about
seven times that threshold.

## 2. System overview

```
                 ┌──────────────── every 3 h ────────────────┐
 NASA SWOT ──────┤  water-surface elevation, 8 reaches        │
 (Hydrocron)     │  → slope km 13 → km 51 ("head")            │
                 │                                            │
 GloFAS v4 ──────┤  discharge at the mouth + Kür and Araz     │      ┌─────────────────┐
 (Copernicus)    │  upstream, 60 days back + 16 days ahead    ├────► │  salt-front     │
                 │                                            │      │  model L(t), km │
 Wind ───────────┤  hourly 10 m wind → daily onshore (NE)     │      └────────┬────────┘
 NASA POWER      │  component; POWER for history,             │               │
 + forecast      │  forecast for the next 16 days             │               ▼
                 │                                            │      status per river km
 Ground reports ─┤  farmers' EC / salty-fresh reports         │      (red / orange / green)
                 └────────────────────────────────────────────┘               │
                                                                              ▼
 Static layers:  SWORD river centreline (km from sea) · OSM villages ·  web app · monitor ·
                 Landsat soil salt trend · GRACE basin storage ·        SMS state machine ·
                 FAO crop salt tolerance                                irrigation plan
```

- **Backend:** Python 3, FastAPI, SQLite (WAL). The model lives in `backend/app/kur.py`. A background loop recomputes
  the state every 3 hours, caches it in memory and in `data/kur/state.json`, and keeps serving the last good state if
  an upstream API fails.
- **ETL:** `backend/etl/kur_*.py` build the static layers and the 2020–2026 back-test once (or on demand).
- **Frontend:** React (Vite), Leaflet for the river map. Azerbaijani and English (`src/i18n.jsx`).

## 3. Data sources

| Source | Provider | What we take | Resolution / revisit | Access | Licence |
|---|---|---|---|---|---|
| **SWOT** L2 river single-pass (Hydrocron) | NASA / CNES | Water-surface elevation (`wse`) of 8 SWORD reaches of the lower Kür, with quality flag `reach_q` | Reach ≈ 10 km · 21-day repeat orbit | `soto.podaac.earthdatacloud.nasa.gov/hydrocron/v1/timeseries`, no login | NASA open data |
| **SWORD v16** | SWOT science team | River centreline, reach IDs, distance from the sea (km), width | Reach ≈ 10 km | Public PMTiles (SWORD Explorer) | CC BY 4.0 |
| **NASA POWER** (MERRA-2, AG community) | NASA LaRC | Daily 10 m wind speed and direction (`WS10M`, `WS10M_MAX`, `WD10M`) over the Kür delta, 2020 → today | 0.5° × 0.625° · daily | `power.larc.nasa.gov/api/temporal/daily/point` | NASA open data |
| **GRACE / GRACE-FO** JPL mascons | NASA JPL | Liquid-water-equivalent thickness anomaly over the Kür–Araz basin box | ~3° mascons · monthly · 2002–2022 on GIBS | NASA GIBS WMS, decoded through the published colour map | NASA open data |
| **Landsat 8/9** Collection 2 Level-2 | NASA / USGS | Surface reflectance (blue, red, NIR) for a salinity index, 2021–2025 | 30 m · 16 days (8 days with both) | Microsoft Planetary Computer STAC (mirror of USGS data) | Public domain |
| **NASA GIBS** basemap and imagery | NASA EOSDIS | VIIRS / MODIS true colour, labels for the map | 250 m–1 km | WMTS | NASA open data |
| **GloFAS v4** | Copernicus EMS (ECMWF) | Daily river discharge at the Kür mouth (39.275 N, 49.275 E), the Kür above the Araz confluence and the Araz, reanalysis 2020 → today and 16-day forecast | 0.05° · daily | Open-Meteo flood API | CC BY 4.0 |
| Weather forecast | Open-Meteo (ECMWF, DWD ICON, NOAA GFS) | Hourly 10 m wind for the next 16 days; daily rain and FAO-56 ET0 | 1–11 km · hourly | `api.open-meteo.com` | CC BY 4.0 |
| OpenStreetMap | OSM contributors | 45 settlements within 4 km of the river below the Araz confluence | Point | Overpass API | ODbL |
| Crop salt tolerance | FAO (Ayers & Westcot 1985) | Soil ECe at which yield starts to fall, 27 crops | Table | Publication | Free with citation |

Every source, its licence and a link are also listed in the app (`/data`) and served by `GET /api/meta`.

## 4. The salt-front model

The model is deliberately small and fully transparent. Every coefficient is shown in the API output (`state.model`).

### 4.1 River strength

```
S_Q    = max(Q, 50) / Q_ref                    Q     = GloFAS discharge at the mouth (m³/s)
                                               Q_ref = 334 m³/s, median 2020–2026
S_head = max(H, 0.05) / H_ref                  H     = SWOT water-surface slope, km 13.4 → km 51.4 (m)
                                               H_ref = 1.7 m, median of SWOT passes
S      = 0.5 · S_Q + 0.5 · S_head              when a SWOT pass exists within the last 12 days
S      = S_Q                                   otherwise
S      = max(S, 0.15)
```

GloFAS gives a daily, forecastable discharge but is a model. SWOT gives a direct physical measurement of the
river's push against the sea (the water-surface drop from km 51 to km 13), but only every ~21 days. Blending the two
anchors the modelled discharge to an observation whenever one exists.

### 4.2 Onshore wind

```
U = max(0, ws · cos(wd − 45°))                 ws, wd = hourly 10 m wind speed (m/s) and direction (°)
                                               daily U = mean of the hourly values (≥ 12 hours required)
```

Only the component blowing from the north-east (45°) counts. Winds from that sector drive Caspian water south along
the western coast and raise the water level at the Kür delta (wind set-up). In the documented episodes the daily
wind direction was between 20° and 52° (March 2022: 39.5°).

### 4.3 Salt-front distance

```
L = min(60, L0 · S⁻² · (1 + U / U_ref) · k_moon)     km from the sea

L0     = 5.67 km      front at median flow and calm wind
U_ref  = 6 m/s        wind that doubles the intrusion
k_moon = 1.03         new / full moon ± 2 days, else 1.0 (Caspian tides are a few cm)
range  = [0.6 · L, min(60, 1.6 · L)]
```

The inverse-square dependence on river strength follows the classic salt-wedge result: the wedge length shrinks
sharply as discharge rises. The cap of 60 km keeps the front inside the stretch the model is meant for.

### 4.4 Inputs per day

`compute()` (in `kur.py`) assembles 76 days: 60 past and 16 forecast. For each day it stores discharge (mouth, Kür
upstream, Araz), daily onshore wind, mean speed, max speed and vector-mean direction, SWOT head and its date, moon age,
basin rain and ET0, and the front `{km, lo, hi}`. Days after today are flagged `fc: true`.

Upstream discharge is used for explanation and early signal. Water from the Kür–Araz confluence takes about 2 days to
reach the sea (~150 km at ~0.8 m/s).

## 5. From distance to status

For a pump, field or village at river km `x`:

```
red     x ≤ L(today)
orange  x ≤ L_hi(today)  or  x ≤ L(tomorrow)
green   otherwise
```

`GET /api/kur/km/{km}` returns today's status, a 15-day strip (7 back, 7 ahead), the first forecast red day, the
day it turns fresh again, and the reasons in plain terms:

| Reason | Rule |
|---|---|
| Kür / Araz / mouth discharge | "bad" when ≥ 25 % below its 2020–2026 median |
| Sea wind | "bad" when daily onshore component U ≥ 5 m/s |
| Heat | ET0 ≥ 5 mm/day |
| Rain | 7-day forecast total; < 2 mm "bad", ≥ 10 mm "ok" |
| Moon | spring tide flag (effect +3 %) |

River km of any point is found by projecting it onto the SWORD centreline (`nearest_km`).

## 6. Ground observations and data fusion

Users report river water as salty / fresh, optionally with an EC reading (dS/m), and soil EC / pH
(`POST /api/kur/obs`). The model uses the last 3 days of water reports:

- A salty report moves today's front only if it is physically plausible: beyond the model's front but within
  15 km of the upper range (`front.hi + 15`). The front then becomes the furthest such report and is flagged
  `observed: true`.
- At a given km, reports within 5 km count. Two or more salty reports force **red**. A single report turns a green
  point **orange** (check the water). One report alone never triggers an SMS.

EC thresholds follow FAO irrigation-water classes: < 0.7 dS/m no restriction, 0.7–3 slight to moderate, > 3 severe.

## 7. Alerts

Every 3 hours, `alerts.py` evaluates each registered field with a river or canal intake. It keeps one state per field
in `farm_salt_state` and sends a message only when the state changes:

```
            salt within 2 days                 salt at the intake
  fresh ─────────────────────────► warn ─────────────────────────► salty
    ▲                                │                               │
    └───── today and the next 2 days all green (hysteresis) ─────────┘
```

- `warn`: "irrigate and fill storage now", with the expected date.
- `salty`: "do not pump", with the expected fresh-again date.
- `fresh`: sent only when today and the next two days are all green, so the message does not flip back and forth
  around the threshold.

Messages go to `alerts` and `sms_outbox`. SMS delivery is simulated: messages are generated as they would be sent,
but no real gateway is used.

## 8. Irrigation plan (FAO-56 water balance)

`backend/app/plan.py` schedules irrigation per field:

```
ETc(d)     = Kc(crop, month) · ET0(d)            ET0 = FAO Penman-Monteith reference evapotranspiration
deficit(d) = max(0, deficit(d−1) + ETc(d) − 0.8 · rain(d))
irrigate when deficit ≥ RAW(crop); dose = deficit
```

Kc values follow the Kür–Araz lowland crop calendar (e.g. cotton 0.35 in April → 1.15 in July–August). Readily
available water RAW ranges from 35 mm (tomato) to 70 mm (cotton). The deficit resets on the day the user records an
irrigation (`POST /api/me/farms/{id}/irrigated`). If the planned day is salty at the field's intake, irrigation moves
to the last fresh day before it (fill storage), otherwise to the next fresh day.

## 9. Soil salinity trend (Landsat)

`backend/etl/kur_soil.py`, run once per season:

1. Landsat 8/9 Collection 2 Level-2 scenes, 15 August – 31 October of 2021–2025, cloud cover < 10 %. Most fields are
   bare after harvest, and salt shows on the surface as a bright crust.
2. Bare-land pixels only: NDVI < 0.2, not water, clear sky.
3. Salinity index `SI = √(blue · red)` (Khan et al., 2005), averaged within 2.5 km of each of the 45 villages.
4. Per year: village mean divided by the zone median. Trend = slope of that ratio. A slope ≥ 0.03 per year is labelled
   "getting saltier".

Output: `data/kur/soil.json`, shown per field as a 5-year trend next to the FAO crop tolerance table.

## 10. Basin water loss (GRACE)

`backend/etl/kur_grace.py` decodes the monthly GRACE / GRACE-FO JPL mascon images from NASA GIBS (liquid water
equivalent, cm, anomaly vs 2004–2009) through their published colour map, and averages them over the Kür–Araz basin box
(38.4–43.5° N, 42.3–49.0° E).

| | Value |
|---|---|
| Record | April 2002 – July 2022 |
| Linear trend | **−1.48 cm / year** |
| Change, first year → last year | **−22.5 cm** water equivalent |

GRACE measures changes in Earth's gravity field from the distance between two satellites ~220 km apart. Less water
in a region means slightly weaker gravity there, and the inter-satellite range changes by micrometres. This is the
basin-scale background of the weakening river. It is not an input to the daily model.

## 11. Back-test 2020–2026

`backend/etl/kur_build.py` runs the same model over every day from 1 January 2020, with GloFAS v4 reanalysis
discharge, NASA POWER daily wind and every SWOT pass. Output: `data/kur/history.json`, 2,506 days.

### 11.1 Days with the modelled front beyond 20 km and 30 km

| Year | Days ≥ 20 km | Days ≥ 30 km | Max (km) |
|---|---|---|---|
| 2020 | 1 | 0 | 20.0 |
| 2021 | 32 | 1 | 30.2 |
| 2022 | 39 | 1 | 30.9 |
| 2023 | 34 | 8 | 34.3 |
| 2024 | 16 | 8 | 52.8 |
| 2025 | 2 | 0 | 23.0 |
| 2026 (to 10 Nov) | 0 | 0 | 15.3 |

### 11.2 Documented event

| Event | Reported | Model | Discharge | Onshore wind | Direction |
|---|---|---|---|---|---|
| March 2022 (peak 10 Mar) | ~30 km (bayraqdar.info, 9 Mar 2022) | **29.6 km** | 219 m³/s (min 215) | 7.5 m/s | 39.5° |

The March 2022 event is the calibration point of `L0`.

### 11.3 SWOT observations

17 usable SWOT passes over the lower Kür (10 March 2024 → 25 October 2026). The strongest signal:

| Date | SWOT head km 13 → 51 | Discharge | Model front |
|---|---|---|---|
| 10 March 2024 | **0.26 m** (median 1.7 m) | 247 m³/s | 50.8 km |
| 13 July 2024 | 1.47 m | 466 m³/s | 6.2 km |
| 3 August 2024 | 1.73 m | 593 m³/s | 4.2 km |

On 10 March 2024 the river surface between km 51 and km 13 was almost flat: the river had nearly lost its gradient
toward the sea, and the model places the front beyond 50 km. The strongest modelled episode of the record follows on
19 March 2024 (52.8 km, discharge 275 m³/s, NE wind 7.3 m/s).

### 11.4 Strongest modelled episodes

| Date | Front | Discharge | Onshore wind |
|---|---|---|---|
| 19 Mar 2024 | 52.8 km | 275 m³/s | 7.32 m/s |
| 9 Feb 2023 | 34.3 km | 219 m³/s | 9.64 m/s |
| 31 Mar 2023 | 33.2 km | 213 m³/s | 8.26 m/s |
| 8 Jan 2023 | 33.0 km | 216 m³/s | 8.64 m/s |

## 12. Replay of past events

`GET /api/kur/replay?day=YYYY-MM-DD&n=16` returns real past days from the back-test, re-run through the same model.
The app plays them day by day (`/?sim=2022-03-01`), with the field statuses and the SMS each field would have received
under the same state machine as section 7. Built-in episodes: 1 Feb 2023, 1 Mar 2022, 6 Mar 2024.

The monitor (`/monitor`) shows the live map, the 16-day forecast of the front, the causes, the 2020–2026 daily record
and a phone running the replay.

## 13. API reference

All endpoints are under `/api`. Responses are JSON.

| Method | Path | Description |
|---|---|---|
| GET | `/kur/state` | Full model state: 76 days of inputs and fronts, today, norms, SWOT levels, model coefficients |
| GET | `/kur/geo` | River centreline (SWORD reaches with km) and villages |
| GET | `/kur/history` | Back-test 2020 → today (yearly counts, episodes, events, SWOT series) |
| GET | `/kur/daily?start` | Back-tested front for every day since 2020 (monitor timeline) |
| GET | `/kur/stats` | Villages and registered fields by status, SMS and reports in the last 7 days |
| GET | `/kur/replay?day&n` | Past days re-run through the model |
| GET | `/kur/km/{km}` | Status of one river km: level, 15-day strip, first red day, fresh-again date, reasons |
| GET | `/kur/point?lat&lon` | Nearest river km to a point and the distance to the river |
| GET | `/kur/grace` | GRACE basin series and trend |
| GET | `/kur/crops` | FAO salt tolerance per crop |
| GET / POST | `/kur/obs` | Recent ground reports / add a report |
| POST | `/kur/ask` | Short plain-language answer grounded in today's model output (LLM, rate limited 20/hour/IP) |
| GET | `/me/kur` | The signed-in user's fields with status, plan, soil trend and messages |
| POST | `/me/farms/{id}/irrigated` | Record an irrigation (resets the water balance) |
| POST | `/auth/register`, `/auth/login`, `/auth/demo` | Phone sign-up, login, shared demo account |
| GET | `/meta` | Sources, licences, links |

Authentication: JWT in the `X-Auth-Token` header.

## 14. Data files and database

`data/kur/`:

| File | Built by | Content |
|---|---|---|
| `river.json` | `etl/kur_geo.py` | 40 SWORD reaches (Kür and Araz), centreline, km 0–312 |
| `villages.json` | `etl/kur_geo.py` | 45 settlements with river km |
| `history.json` | `etl/kur_build.py` | Back-test 2020 → today |
| `soil.json` | `etl/kur_soil.py` | Landsat salinity index and trend per village |
| `grace.json` | `etl/kur_grace.py` | GRACE basin storage series |
| `swot_live.json` | `app/kur.py` | Latest SWOT elevations (refreshed every 12 h) |
| `state.json` | `app/kur.py` | Last computed model state (fallback if APIs fail) |

Raw downloads go to `data/raw/kur/` (GloFAS, POWER, SWOT per reach).

SQLite tables used by this module: `users`, `farms` (with `water_source`, `pump_lat`, `pump_lon`, `pump_km`),
`farm_crops`, `kur_obs` (water / soil reports with EC, pH, salty flag), `farm_salt_state`, `alerts`, `sms_outbox`.

## 15. Build, run, deploy

```bash
# Python environment and database
./refresh_data.sh                                   # first time: builds data/fieldshift.db

# Kür layers (run from backend/)
.venv/bin/python -m etl.kur_geo                     # SWORD river + OSM villages
.venv/bin/python -m etl.kur_build --fetch           # download GloFAS, POWER, SWOT and run the back-test
.venv/bin/python -m etl.kur_soil                    # Landsat soil salinity trend
.venv/bin/python -m etl.kur_grace                   # GRACE basin storage

# Serve API + site on http://127.0.0.1:8077
./run.sh                                            # optional backend/.env: DEEPSEEK_API_KEY for /kur/ask

# Frontend dev server (proxies /api to :8077)
cd frontend && npx vite

# Production (systemd service + nginx, see deploy.sh)
./deploy.sh                                         # code and frontend; the live database is kept
```

## 16. Repository layout

```
backend/
  app/
    kur.py        salt-front model, live inputs, status per km, reasons, ask context
    plan.py       FAO-56 irrigation plan per field
    alerts.py     3-hourly alert loop and SMS state machine
    main.py       FastAPI routes
    db.py         SQLite schema and migrations
    sms.py        simulated SMS gateway
  etl/
    kur_geo.py    SWORD reaches and OSM villages
    kur_build.py  2020 → today back-test
    kur_soil.py   Landsat salinity index
    kur_grace.py  GRACE basin storage
frontend/src/
  pages/KurApp.jsx   phone-style app (fields, map, SMS, profile, replay player)
  pages/Kur.jsx      river map, sign-up, field and report forms
  pages/Monitor.jsx  big-screen monitor
  i18n.jsx           Azerbaijani / English
data/kur/            model inputs and outputs (section 14)
docs/LEGACY.md       earlier modules of the project (crop suitability, world layer), still in the code base
```

## 17. Limitations

- `L0` is calibrated on one documented event (March 2022). Independent validation needs more in-situ salinity
  measurements, which the ground-report feature is built to collect.
- GloFAS is a hydrological model, not a gauge. Discharge regulated by upstream reservoirs is represented
  approximately. Gauge records of the lower Kür are not openly published.
- SWOT revisits every ~21 days. Between passes the model runs on discharge and wind only.
- The uncertainty range (0.6 L to 1.6 L) is a fixed band, not a statistical interval.
- The Landsat index sees surface salt only, not the root zone, and has not been checked against field EC in this area.
- SMS delivery is simulated.

## 18. Credits and licences

NASA SWOT (NASA/CNES, PO.DAAC Hydrocron), SWORD v16 (CC BY 4.0), NASA POWER, NASA GRACE / GRACE-FO (JPL), NASA GIBS,
Landsat 8/9 (NASA/USGS, public domain), Copernicus GloFAS v4 (CC BY 4.0), Open-Meteo (CC BY 4.0), OpenStreetMap (ODbL),
FAO Irrigation and Drainage Paper 29 (Ayers & Westcot, 1985), FAO-56 (Allen et al., 1998),
Khan et al. (2005) salinity index.

Team Earthly · NASA Space Apps Challenge 2026.
