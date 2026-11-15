import asyncio
import csv
import functools
import io
import json
import time
import os
import logging
import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import alerts, chat, fires, kur, plan, satellite, services, sms
from .auth import current_user, hash_password, make_token, optional_user, verify_password
from .db import ROOT, connect, init_schema, row, rows, tx
from .weather import WMO, forecast, snapshot


@asynccontextmanager
async def lifespan(_app):
    init_schema()
    task = asyncio.create_task(alerts.loop())
    sat_task = asyncio.create_task(satellite.loop())
    fire_task = asyncio.create_task(fires.loop())
    kur_task = asyncio.create_task(kur.loop())
    yield
    kur_task.cancel()
    task.cancel()
    sat_task.cancel()
    fire_task.cancel()


app = FastAPI(title="FieldShift API", lifespan=lifespan)
log = logging.getLogger("api")


def db():
    con = connect()
    try:
        yield con
    finally:
        con.close()


def need(v, msg="Not found"):
    if not v:
        raise HTTPException(404, msg)
    return v


# ------------------------------------------------------------------ catalogue & data
@app.get("/api/meta")
def get_meta():
    m = services.meta()
    m["sources"] = [
        {"name": "NASA SWOT (Hydrocron)", "nasa": True, "license": "NASA open data, no restrictions",
         "what": "Water-surface elevation of the lower Kür, reach by reach, from space (2023 onward); the slope km 13 → km 51 tells how strong the river is",
         "links": [["SWOT mission", "https://swot.jpl.nasa.gov/"], ["Hydrocron API", "https://podaac.github.io/hydrocron/"], ["PO.DAAC", "https://podaac.jpl.nasa.gov/SWOT"]],
         "how": "Hydrocron time-series API (no login) for 8 SWORD reaches between the Kür mouth and the Araz confluence, refreshed twice a day; only good-quality passes (reach_q 0–1) are used.",
         "url": "https://soto.podaac.earthdatacloud.nasa.gov/hydrocron/v1/timeseries"},
        {"name": "NASA GRACE / GRACE-FO (JPL mascons, via GIBS)", "nasa": True, "license": "NASA open data, no restrictions",
         "what": "Monthly total water storage of the Kür–Araz basin from the Earth's gravity field, 2002–2022",
         "links": [["GRACE-FO", "https://gracefo.jpl.nasa.gov/"], ["GRACE Tellus", "https://grace.jpl.nasa.gov/"]],
         "how": "GIBS images of the JPL mascon solution over the basin (land only) decoded to centimetres with the published colour map and averaged per month.",
         "url": "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"},
        {"name": "Landsat 8/9 Collection 2 Level-2 (NASA/USGS)", "nasa": True, "license": "Public domain (USGS)",
         "what": "Soil salt-crust indicator around every village, after harvest 2021–2025 (30 m)",
         "links": [["Landsat", "https://landsat.gsfc.nasa.gov/"], ["Planetary Computer catalogue", "https://planetarycomputer.microsoft.com/dataset/landsat-c2-l2"]],
         "how": "Clearest 15 Aug–31 Oct scenes; bare land only (NDVI < 0.2, no cloud or water); salinity index sqrt(blue·red) averaged within 2.5 km of each village; 5-year trend of the salt-crust share.",
         "url": "https://planetarycomputer.microsoft.com/api/stac/v1"},
        {"name": "SWORD v16 (SWOT River Database)", "nasa": True, "license": "CC BY 4.0",
         "what": "Kür and Araz centrelines, reach IDs and distance from the sea used for the river kilometres",
         "links": [["Dataset (Zenodo)", "https://doi.org/10.5281/zenodo.10013982"], ["SWORD Explorer", "https://www.swordexplorer.com/"]],
         "how": "Reach geometry read from the public SWORD Explorer vector tiles; kilometres interpolated along each reach.",
         "url": "https://www.swordexplorer.com/"},
        {"name": "GloFAS v4 river discharge (Copernicus)", "nasa": False, "license": "CC BY 4.0 (Copernicus Emergency Management Service)",
         "what": "Daily Kür discharge at the mouth, 2020–today, and a 16-day forecast",
         "links": [["GloFAS", "https://global-flood.emergency.copernicus.eu/"], ["Open-Meteo Flood API", "https://open-meteo.com/en/docs/flood-api"]],
         "how": "Open-Meteo Flood API at the GloFAS river cell of the Kür mouth (39.275 N, 49.275 E).",
         "url": "https://flood-api.open-meteo.com/v1/flood"},
        {"name": "OpenStreetMap villages", "nasa": False, "license": "ODbL",
         "what": "Settlements within 4 km of the Kür below the Araz confluence, with their river kilometre",
         "links": [["OpenStreetMap", "https://www.openstreetmap.org/"], ["Overpass API", "https://wiki.openstreetmap.org/wiki/Overpass_API"]],
         "how": "One Overpass query for place=village/town/city; each settlement is snapped to the nearest river kilometre.",
         "url": "https://overpass-api.de/"},
        {"name": "FAO crop salt tolerance (Ayers & Westcot 1985)", "nasa": False, "license": "FAO publication, free to use with citation",
         "what": "Soil salinity (ECe) at which each crop starts to lose yield; irrigation-water salinity classes",
         "links": [["FAO Irrigation and Drainage Paper 29", "https://www.fao.org/4/t0234e/t0234e00.htm"]],
         "how": "Thresholds typed in from the FAO tables for the crops grown on the lower Kür.",
         "url": "https://www.fao.org/4/t0234e/t0234e00.htm"},
        {"name": "NASA POWER (MERRA-2, AG community)", "nasa": True, "license": "NASA open data, no restrictions",
         "what": "Daily temperature, rainfall, soil wetness, 1981 to date, per district / province",
         "links": [["Project home", "https://power.larc.nasa.gov/"], ["Documentation", "https://power.larc.nasa.gov/docs/"], ["Data Access Viewer", "https://power.larc.nasa.gov/data-access-viewer/"]],
         "how": "Free REST API, no key. For every district / province point we request daily T2M, T2M_MAX, T2M_MIN, PRECTOTCORR, GWETROOT, GWETTOP from 1981 to yesterday as JSON, then aggregate to months and years.",
         "url": "https://power.larc.nasa.gov/api/temporal/daily/point"},
        {"name": "NASA NEX-GDDP-CMIP6", "nasa": True, "license": "NASA open data (CC BY-SA 4.0 per NCCS)",
         "what": "2026–2050 daily climate projections, SSP2-4.5, 5-model ensemble",
         "links": [["Dataset page", "https://www.nccs.nasa.gov/services/data-collections/land-based-products/nex-gddp-cmip6"], ["Paper (Thrasher et al. 2022)", "https://doi.org/10.1038/s41597-022-01393-4"]],
         "how": "NetCDF files on NASA NCCS THREDDS. We cut only our points with the NetCDF Subset Service (NCSS) for 5 models, SSP2-4.5, 2026–2050, and correct each month against NASA POWER 1995–2014 (delta method).",
         "url": "https://ds.nccs.nasa.gov/thredds/catalog/AMES/NEX/GDDP-CMIP6/catalog.html"},
        {"name": "NASA GIBS: MODIS NDVI", "nasa": True, "license": "NASA open data, no restrictions",
         "what": "Vegetation greenness now vs the same month of the last 5 years (layer MODIS_Aqua_L3_NDVI_Monthly)",
         "links": [["Product MYD13A3 (LP DAAC)", "https://lpdaac.usgs.gov/products/myd13a3v061/"], ["View in NASA Worldview", "https://worldview.earthdata.nasa.gov/?l=MODIS_Aqua_L3_NDVI_Monthly"]],
         "how": "NASA GIBS WMS (open, no key). We download the colour-coded image for the latest month, turn every pixel back into an NDVI value with the layer’s published colour map, and average it over each district / province.",
         "url": "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"},
        {"name": "NASA GIBS: SMAP L4 soil moisture", "nasa": True, "license": "NASA open data, no restrictions",
         "what": "Root-zone soil moisture, daily (layer SMAP_L4_Analyzed_Root_Zone_Soil_Moisture)",
         "links": [["Product SPL4SMGP (NSIDC)", "https://nsidc.org/data/spl4smgp"], ["View in NASA Worldview", "https://worldview.earthdata.nasa.gov/?l=SMAP_L4_Analyzed_Root_Zone_Soil_Moisture"]],
         "how": "Same GIBS WMS method, daily layer; the pixel colours are decoded to m³/m³ with the official colour map and compared with the same day of earlier years.",
         "url": "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"},
        {"name": "NASA GIBS: GPM IMERG", "nasa": True, "license": "NASA open data, no restrictions",
         "what": "Satellite precipitation, daily (layer IMERG_Precipitation_Rate)",
         "links": [["IMERG product page", "https://gpm.nasa.gov/data/imerg"], ["View in NASA Worldview", "https://worldview.earthdata.nasa.gov/?l=IMERG_Precipitation_Rate"]],
         "how": "Same GIBS WMS method, daily precipitation layer decoded to mm and summed over the last 7 days.",
         "url": "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"},
        {"name": "NASA GIBS: VIIRS, HLS (Landsat/Sentinel-2) imagery and base maps", "nasa": True,
         "license": "NASA open data; land/water base map derived from OpenStreetMap (ODbL)",
         "what": "Map imagery and base map", "links": [["GIBS documentation", "https://nasa-gibs.github.io/gibs-api-docs/"], ["HLS project", "https://hls.gsfc.nasa.gov/"], ["NASA Worldview", "https://worldview.earthdata.nasa.gov/"]],
         "how": "GIBS WMTS map tiles loaded straight into the map in your browser (true colour, NDVI, soil moisture, rain, 30 m HLS for farms).",
         "url": "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/"},
        {"name": "NASA FIRMS active fires", "nasa": True, "license": "NASA open data, no restrictions",
         "what": "Fire / hot-spot detections of the last 24 h from VIIRS (375 m, NOAA-20, NOAA-21, S-NPP) and MODIS (1 km)",
         "links": [["FIRMS", "https://firms.modaps.eosdis.nasa.gov/"], ["Active fire CSV files", "https://firms.modaps.eosdis.nasa.gov/active_fire/"], ["Fire map", "https://firms.modaps.eosdis.nasa.gov/map/"]],
         "how": "FIRMS publishes the last 24 hours of global detections as open CSV files. We reload them every 3 hours, drop low-confidence points, show them on the map, count fires in each district / province and alert farms with a fire within 10 km.",
         "url": "https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-20-viirs-c2/csv/J1_VIIRS_C2_Global_24h.csv"},
        {"name": "NASA LANCE near-real-time imagery (via GIBS)", "nasa": True, "license": "NASA open data, no restrictions",
         "what": "Today's MODIS true colour, MODIS land surface temperature day/night (frost and heat), MODIS snow cover, GPM IMERG Early 30-minute rain",
         "links": [["LANCE", "https://lance.modaps.eosdis.nasa.gov/"], ["Near-real-time data", "https://www.earthdata.nasa.gov/learn/find-data/near-real-time"], ["GIBS layers", "https://nasa-gibs.github.io/gibs-api-docs/available-visualizations/"], ["NASA Worldview", "https://worldview.earthdata.nasa.gov/"]],
         "how": "LANCE products appear in GIBS within about 3 hours of the satellite pass. The map loads them as tiles; the app reads each layer's newest date from the GIBS capabilities every 6 hours.",
         "url": "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml"},
        {"name": "EUMETSAT Meteosat IODC (EUMETView)", "nasa": False,
         "license": "EUMETSAT data policy: hourly Meteosat imagery free and unrestricted, attribution \"Contains EUMETSAT Meteosat data\"",
         "what": "Geostationary infrared cloud image over Azerbaijan, every hour (GOES and Himawari do not see the Caucasus)",
         "links": [["EUMETView", "https://view.eumetsat.int/"], ["EUMETSAT data policy", "https://www.eumetsat.int/eumetsat-data-licensing"]],
         "how": "Loaded straight from the EUMETView WMS into the map, only the frame of the last full hour (sub-hourly frames are licensed for the first 3 hours).",
         "url": "https://view.eumetsat.int/geoserver/ows?service=WMS&request=GetCapabilities"},
        {"name": "AzStat (State Statistical Committee of Azerbaijan)", "nasa": False,
         "license": "Official open statistics, free use with attribution",
         "what": "District crop yields (c/ha) and production (t), 2000–2025",
         "links": [["AzStat home", "https://www.stat.gov.az/"]],
         "how": "Official Excel tables (2.113–2.257) downloaded from stat.gov.az and parsed per district, crop and year.",
         "url": "https://www.stat.gov.az/source/agriculture/"},
        {"name": "FAOSTAT (FAO)", "nasa": False, "license": "CC BY 4.0",
         "what": "Country-level crop yields, production and area, 1990 onward",
         "links": [["FAOSTAT crops & livestock", "https://www.fao.org/faostat/en/#data/QCL"]],
         "how": "FAOSTAT bulk download (one ZIP/CSV), filtered to our crops: yield, production and harvested area per country and year.",
         "url": "https://bulks-faostat.fao.org/production/Production_Crops_Livestock_E_All_Data_(Normalized).zip"},
        {"name": "ISRIC SoilGrids 2.0", "nasa": False, "license": "CC BY 4.0",
         "what": "Soil pH, clay/sand/silt, organic carbon, nitrogen, CEC (0–30 cm)",
         "links": [["SoilGrids", "https://soilgrids.org/"], ["Paper (Poggio et al. 2021)", "https://doi.org/10.5194/soil-7-217-2021"]],
         "how": "SoilGrids WCS (open web coverage service): 250 m rasters of 0–30 cm soil properties cut to each polygon and averaged.",
         "url": "https://maps.isric.org/mapserv?map=/map/phh2o.map"},
        {"name": "FAO ECOCROP (via Recocrop)", "nasa": False, "license": "FAO ECOCROP database; Recocrop package GPL-3",
         "what": "Crop temperature, rainfall and pH requirements",
         "links": [["FAO ECOCROP", "https://gaez.fao.org/pages/ecocrop"], ["Recocrop package (CRAN)", "https://cran.r-project.org/package=Recocrop"]],
         "how": "The ECOCROP parameter table shipped in the Recocrop R package (one .rds file), read once.",
         "url": "https://raw.githubusercontent.com/cran/Recocrop/master/inst/parameters/ecocrop.rds"},
        {"name": "geoBoundaries (gbOpen)", "nasa": False, "license": "Open licences per country (CC BY 4.0 / CC BY-SA / ODbL)",
         "what": "Azerbaijan districts (ADM2) and provinces of 198 countries (ADM1)",
         "links": [["geoBoundaries", "https://www.geoboundaries.org/"], ["Paper (Runfola et al. 2020)", "https://doi.org/10.1371/journal.pone.0231866"]],
         "how": "geoBoundaries API: GeoJSON of Azerbaijan ADM2 and world ADM1, simplified for the web.",
         "url": "https://www.geoboundaries.org/api/current/gbOpen/ALL/ADM1/"},
        {"name": "NOAA ETOPO1", "nasa": False, "license": "U.S. Government work, public domain",
         "what": "Elevation, used to place climate points at farmland elevation",
         "links": [["ETOPO global relief (NOAA NCEI)", "https://www.ncei.noaa.gov/products/etopo-global-relief-model"]],
         "how": "NOAA ERDDAP griddap subset of 1-arc-minute elevation, used to find farmland elevation in each unit.",
         "url": "https://upwell.pfeg.noaa.gov/erddap/griddap/etopo180.html"},
        {"name": "Open-Meteo forecast", "nasa": False, "license": "CC BY 4.0 (free non-commercial API)",
         "what": "Live 16-day forecast (ECMWF / DWD ICON / NOAA GFS)", "links": [["API documentation", "https://open-meteo.com/en/docs"], ["Licence", "https://open-meteo.com/en/licence"]],
         "how": "Free forecast API called live (cached) per district point; the app also stores each forecast to measure later how wrong it was.",
         "url": "https://api.open-meteo.com/v1/forecast"},
    ]
    m["ai_chat"] = chat.enabled()
    m["exports"] = _export_counts()
    return m


# Processed open data (no user data): what the app computed from the sources above, as CSV.
EXPORTS = {
    "rayons": "Districts and provinces: id, name, country, centre point, area",
    "countries": "Countries: ISO3, name, region, centre point",
    "soil": "SoilGrids 0–30 cm means per district / province",
    "climate_year": "NASA POWER yearly climate per district / province (lapse-rate corrected)",
    "climate_month": "NASA POWER monthly climate normals per period",
    "projection_year": "NASA NEX-GDDP-CMIP6 SSP2-4.5 yearly projections (5-model mean, delta-corrected)",
    "suitability": "ECOCROP suitability per crop, period, irrigated / rainfed",
    "yields": "AzStat district yields and production",
    "country_yields": "FAOSTAT country yields, production and area",
    "yield_forecast": "Yield forecasts with 80% range",
    "sat_obs": "Latest NASA satellite values (NDVI, SMAP, IMERG) per unit vs normal",
}


@functools.lru_cache(maxsize=1)
def _export_counts():
    """Row counts of the exportable tables; counted once per process (data tables only change on redeploy)."""
    con = connect()
    try:
        return [{"table": t, "what": w, "rows": con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]} for t, w in EXPORTS.items()]
    finally:
        con.close()


@app.get("/api/export/{table}.csv")
def export_csv(table: str):
    if table not in EXPORTS:
        raise HTTPException(404, "Not found")

    def gen():
        con = connect()
        try:
            cur = con.execute(f"SELECT * FROM {table}")   # table name comes from the EXPORTS whitelist
            out = io.StringIO()
            w = csv.writer(out)
            w.writerow([c[0] for c in cur.description])
            while batch := cur.fetchmany(5000):
                w.writerows(tuple(r) for r in batch)
                yield out.getvalue()
                out.seek(0)
                out.truncate()
            if out.getvalue():
                yield out.getvalue()
        finally:
            con.close()
    return StreamingResponse(gen(), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="fieldshift_{table}.csv"'})


@app.get("/api/overview")
def overview(con: sqlite3.Connection = Depends(db)):
    """Country-level headline numbers computed from all rayons (NASA POWER) — the deck's 'past vs now'."""
    def avg(cols, a, b):
        return row(con, "SELECT " + ",".join(f"avg({c}) {c}" for c in cols) +
                   " FROM climate_year WHERE year BETWEEN ? AND ? AND rayon_id IN (SELECT id FROM rayons WHERE iso3='AZE')", a, b)
    cols = ["tmean", "hot35", "frost", "ffs", "last_frost", "gdd", "precip"]
    past, now = avg(cols, 1981, 1990), avg(cols, 2016, 2025)
    base = {r["rayon_id"]: r["t"] for r in rows(con, "SELECT rayon_id, avg(tmean) t FROM climate_year "
                                                      "WHERE year BETWEEN 1981 AND 2010 AND rayon_id IN (SELECT id FROM rayons WHERE iso3='AZE') GROUP BY rayon_id")}
    anom = {}
    for r in rows(con, "SELECT rayon_id, year, tmean, hot35 FROM climate_year WHERE partial=0 AND rayon_id IN (SELECT id FROM rayons WHERE iso3='AZE')"):
        a = anom.setdefault(r["year"], [[], []])
        a[0].append(r["tmean"] - base[r["rayon_id"]])
        a[1].append(r["hot35"])
    series = [{"year": y, "anomaly": sum(v[0]) / len(v[0]), "hot35": sum(v[1]) / len(v[1])}
              for y, v in sorted(anom.items())]
    proj = rows(con, "SELECT year, avg(tmean) tmean, avg(hot35) hot35, avg(frost) frost, avg(precip) precip, "
                     "avg(spread) spread FROM projection_year WHERE rayon_id IN (SELECT id FROM rayons WHERE iso3='AZE') GROUP BY year ORDER BY year")
    base_all = sum(base.values()) / len(base)
    for p in proj:
        p["anomaly"] = p["tmean"] - base_all
    last = con.execute("SELECT max(year) FROM national_yields WHERE yield>0").fetchone()[0]
    top = rows(con, """SELECT n.crop_id, c.name, n.production, n.yield,
                (SELECT yield FROM national_yields p WHERE p.crop_id=n.crop_id AND p.year=2005) y2005
                FROM national_yields n JOIN crops c ON c.id=n.crop_id WHERE n.year=? AND n.production>0
                AND n.crop_id!='terevez' ORDER BY n.production DESC LIMIT 10""", last)
    return {"past": past, "now": now, "anomaly_series": series, "projection": proj, "top_crops": top,
            "stat_year": last, "warm_years_since_2004": sum(1 for s in series if s["year"] >= 2004 and s["anomaly"] > 0),
            "years_since_2004": sum(1 for s in series if s["year"] >= 2004)}


# ------------------------------------------------------------------ Kür salt water
@app.get("/api/kur/state")
def kur_state():
    st = kur.state()
    if not st:
        raise HTTPException(503, "Kür data is not available yet, try again in a minute")
    return st


@app.get("/api/kur/geo")
def kur_geo():
    river, villages = kur.geometry()
    return {"river": [{k: r[k] for k in ("id", "km", "stem", "width", "line", "kms") if k in r} for r in river],
            "villages": villages}


@app.get("/api/kur/history")
def kur_history():
    h = kur.history()
    if not h:
        raise HTTPException(404, "Not built")
    return {k: v for k, v in h.items() if k not in ("q_sorted", "daily")}


@app.get("/api/kur/daily")
def kur_daily(start: date = date(2020, 1, 1)):
    """Back-tested salt front for every day since 2020 (the monitor's timeline)."""
    h = kur.history() or {}
    d0 = start.isoformat()
    return [r for r in h.get("daily", []) if r["d"] >= d0]


@app.get("/api/kur/stats")
def kur_stats(con: sqlite3.Connection = Depends(db)):
    """Aggregated, anonymous numbers for the monitor: villages and registered fields by status, SMS sent."""
    st = kur.state()
    river, villages = kur.geometry()
    lv = {"green": 0, "orange": 0, "red": 0}
    vout = []
    for v in villages:
        s = kur.for_km(v["km"], st)
        lv[s["level"]] = lv.get(s["level"], 0) + 1
        vout.append({"name": v["name"], "km": v["km"], "lat": v["lat"], "lon": v["lon"], "level": s["level"]})
    farms = rows(con, "SELECT pump_km FROM farms WHERE pump_km IS NOT NULL AND water_source IN ('kur','canal')")
    fl = {"green": 0, "orange": 0, "red": 0}
    for f in farms:
        s = kur.for_km(f["pump_km"], st)
        fl[s["level"]] = fl.get(s["level"], 0) + 1
    sms7 = con.execute("SELECT count(*) FROM sms_outbox WHERE created_at >= datetime('now','-7 day')").fetchone()[0]
    obs7 = con.execute("SELECT count(*) FROM kur_obs WHERE observed_at >= date('now','-7 day')").fetchone()[0]
    return {"villages": lv, "village_list": vout, "fields": fl, "fields_total": len(farms), "sms_7d": sms7, "obs_7d": obs7,
            "updated": st["updated"] if st else None}


@app.get("/api/kur/replay")
def kur_replay(day: date, n: int = Query(7, ge=1, le=30)):
    """Real past days re-run through the same model (for demonstrations): the salt front from `day` for `n` days."""
    h = kur.history()
    daily = {r["d"]: r for r in (h or {}).get("daily", [])}
    d0 = day.isoformat()
    if d0 not in daily:
        raise HTTPException(404, "No data for that day")
    days = []
    for i in range(n):
        r = daily.get((day + timedelta(days=i)).isoformat())
        if r:
            km = r["km"]
            days.append({"date": r["d"], "front": {"km": km, "lo": round(km * 0.6, 1), "hi": round(min(kur.LMAX, km * 1.6), 1)},
                         "q": r["q"], "u": r["u"], "wd": r["wd"]})
    return {"date": d0, "front": days[0]["front"], "q": days[0]["q"], "u": days[0]["u"], "wd": days[0]["wd"], "days": days,
            "q_median": kur.QREF}


class KurAsk(BaseModel):
    message: str = Field(min_length=2, max_length=600)
    km: float | None = Field(default=None, ge=0, le=400)


_ask_hits: dict[str, list[float]] = {}


@app.post("/api/kur/ask")
async def kur_ask(b: KurAsk, request: Request):
    """Short plain-language answer about the Kür salt water, grounded in today's model output."""
    if not chat.enabled():
        raise HTTPException(503, "The assistant is not configured")
    ip = request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for", "").split(",")[0] or request.client.host
    now_ = time.time()
    hits = [t for t in _ask_hits.get(ip, []) if now_ - t < 3600]
    if len(hits) >= 20:
        raise HTTPException(429, "Too many questions, try again in an hour")
    _ask_hits[ip] = hits + [now_]
    import httpx as _httpx
    ctx = kur.ask_context(b.km)
    body = {"model": chat.MODEL, "temperature": 0.3, "max_tokens": 400, "messages": [
        {"role": "system", "content": kur.ASK_SYSTEM + "\nToday's data (JSON): " + json.dumps(ctx, ensure_ascii=False)},
        {"role": "user", "content": b.message}]}
    async with _httpx.AsyncClient(timeout=60) as c:
        r = await c.post(chat.API_URL, json=body, headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"})
    if r.status_code != 200:
        raise HTTPException(502, "The assistant is busy, try again")
    return {"answer": r.json()["choices"][0]["message"]["content"].strip()}


@app.get("/api/kur/grace")
def kur_grace():
    p = kur.DIR / "grace.json"
    if not p.exists():
        raise HTTPException(404, "Not built")
    return json.loads(p.read_text())


@app.get("/api/kur/point")
def kur_point(lat: float = Query(..., ge=38.5, le=41.0), lon: float = Query(..., ge=47.5, le=50.0)):
    near = kur.nearest_km(lat, lon)
    return {**near, "status": kur.for_km(near["km"])}


@app.get("/api/kur/km/{km}")
def kur_km(km: float):
    if not 0 <= km <= 400:
        raise HTTPException(400, "km out of range")
    return kur.for_km(km)


@app.get("/api/kur/crops")
def kur_crops(con: sqlite3.Connection = Depends(db)):
    names = {r["id"]: (r["name"], r["name_az"]) for r in rows(con, "SELECT id, name, name_az FROM crops")}
    return sorted([{"id": k, "name": names.get(k, (k, k))[0], "name_az": names.get(k, (k, k))[1], "ece": v}
                   for k, v in kur.CROP_ECE.items()], key=lambda x: -x["ece"])


class KurObs(BaseModel):
    kind: Literal["water", "soil"]
    lat: float = Field(ge=38.5, le=41.0)
    lon: float = Field(ge=47.5, le=50.0)
    ec: float | None = Field(default=None, ge=0, le=100)      # dS/m (= mS/cm)
    tds: float | None = Field(default=None, ge=0, le=100000)   # ppm, converted with EC = TDS / 640
    ph: float | None = Field(default=None, ge=3, le=11)
    salty: bool | None = None                                  # "it tasted / looked salty" without a meter
    observed_at: date | None = None
    note: str = Field(default="", max_length=300)


@app.post("/api/kur/obs")
def kur_add_obs(b: KurObs, user=Depends(current_user)):
    ec = b.ec if b.ec is not None else (round(b.tds / 640, 2) if b.tds is not None else None)
    if ec is None and b.salty is None and b.ph is None:
        raise HTTPException(400, "Give a reading (EC, TDS or pH) or say whether the water was salty")
    salty = b.salty if ec is None else ec >= (kur.SALTY_EC if b.kind == "water" else 4.0)
    near = kur.nearest_km(b.lat, b.lon)
    km = near["km"] if b.kind == "water" and near["dist_km"] <= 3 else None
    when = (b.observed_at or date.today())
    if when > date.today() or when < date.today() - timedelta(days=60):
        raise HTTPException(400, "Date must be within the last 60 days")
    with tx() as con:
        oid = con.execute("INSERT INTO kur_obs(user_id, kind, lat, lon, km, ec, ph, salty, observed_at, note) "
                          "VALUES(?,?,?,?,?,?,?,?,?,?)", (user["id"], b.kind, b.lat, b.lon, km, ec, b.ph,
                                                          None if salty is None else int(salty), when.isoformat(), b.note)).lastrowid
    kur._state["at"] = 0          # next read re-evaluates with the new observation
    return {"id": oid, "km": km, "ec": ec, "salty": salty}


@app.get("/api/me/obs")
def my_obs(user=Depends(current_user), con: sqlite3.Connection = Depends(db)):
    return rows(con, "SELECT id, kind, km, ec, ph, salty, observed_at, note FROM kur_obs WHERE user_id=? ORDER BY observed_at DESC, id DESC LIMIT 100",
                user["id"])


@app.delete("/api/me/obs/{oid}")
def del_obs(oid: int, user=Depends(current_user)):
    with tx() as con:
        cur = con.execute("DELETE FROM kur_obs WHERE id=? AND user_id=?", (oid, user["id"]))
    if not cur.rowcount:
        raise HTTPException(404, "Not found")
    kur._state["at"] = 0
    return {"ok": True}


@app.get("/api/kur/obs")
def kur_obs(days: int = Query(30, ge=1, le=365), con: sqlite3.Connection = Depends(db)):
    since = (date.today() - timedelta(days=days)).isoformat()
    return rows(con, "SELECT id, kind, round(lat, 3) lat, round(lon, 3) lon, km, ec, ph, salty, observed_at, note "
                     "FROM kur_obs WHERE observed_at >= ? ORDER BY observed_at DESC LIMIT 500", since)


def last_irrigation(con, fid):
    r = con.execute("SELECT max(day) FROM farm_irrigations WHERE farm_id=?", (fid,)).fetchone()
    return r[0] if r else None


def farm_plan(con, f, status):
    salt = {d["date"]: d["level"] for d in status["days"]} if status else {}
    try:
        return plan.plan(f, salt, last_irrigation(con, f["id"]))
    except Exception as e:  # noqa: BLE001 - the forecast service can be down; the water status still shows
        log.warning("plan for farm %s failed: %s", f["id"], e)
        return None


class Irrigated(BaseModel):
    day: date | None = None


@app.post("/api/me/farms/{fid}/irrigated")
def farm_irrigated(fid: int, b: Irrigated, user=Depends(current_user)):
    day = b.day or date.today()
    if day > date.today() or day < date.today() - timedelta(days=30):
        raise HTTPException(400, "Date must be within the last 30 days")
    with tx() as con:
        need(row(con, "SELECT id FROM farms WHERE id=? AND user_id=?", fid, user["id"]))
        con.execute("INSERT OR IGNORE INTO farm_irrigations(farm_id, day) VALUES(?,?)", (fid, day.isoformat()))
    return {"ok": True, "day": day.isoformat()}


@app.get("/api/me/kur")
def my_kur(user=Depends(current_user), con: sqlite3.Connection = Depends(db)):
    """Personal screen: every farm with its water status, irrigation plan, soil and crop advice."""
    st = kur.state()
    out = []
    soil = {r["rayon_id"]: r for r in rows(con, "SELECT rayon_id, ph, soc, clay, sand FROM soil")}
    for f in _farms(con, user["id"]):
        km = f.get("pump_km")
        status = kur.for_km(km, st) if km is not None and f.get("water_source") in ("kur", "canal") else None
        last = row(con, "SELECT ec, ph, observed_at FROM kur_obs WHERE user_id=? AND kind='soil' ORDER BY observed_at DESC LIMIT 1",
                   user["id"])
        ece = (last or {}).get("ec") or f.get("soil_ec")
        crops = [{"id": c, "ece": kur.CROP_ECE.get(c), "ok": None if ece is None or c not in kur.CROP_ECE else ece < kur.CROP_ECE[c]}
                 for c in f["crops"]]
        tolerant = [k for k, v in sorted(kur.CROP_ECE.items(), key=lambda kv: -kv[1]) if ece is None or v > ece][:5]
        out.append({"farm": f, "status": status, "soil": {"ec": ece, "ph": (last or {}).get("ph") or f.get("soil_ph"),
                    "grids": soil.get(f["rayon_id"]), "measured": last, "satellite": kur.soil_for(f.get("lat"), f.get("lon"))},
                    "crops": crops, "tolerant": tolerant, "plan": farm_plan(con, f, status)})
    sms_rows = rows(con, "SELECT body, status, created_at FROM sms_outbox WHERE user_id=? ORDER BY id DESC LIMIT 5", user["id"])
    return {"farms": out, "updated": st["updated"] if st else None, "sms": sms_rows, "phone": user.get("phone"),
            "sms_on": bool(user.get("sms_alerts"))}


NRT = {"imerg30", "modis_today", "lst_day", "lst_night"}


@app.get("/api/fires")
def fires_in(s: float = Query(..., ge=-90, le=90), w: float = Query(..., ge=-540, le=540),
             n: float = Query(..., ge=-90, le=90), e: float = Query(..., ge=-540, le=540),
             con: sqlite3.Connection = Depends(db)):
    """FIRMS detections inside the visible map box (strongest first, capped so a world view stays light)."""
    w, e = max(w, -180), min(e, 180)
    pts = rows(con, "SELECT lat, lon, acq, sat, conf, frp, days FROM fires WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ? "
                    "ORDER BY frp DESC LIMIT 3000", s, n, w, e)
    total = con.execute("SELECT count(*) FROM fires WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?", (s, n, w, e)).fetchone()[0]
    return {"points": pts, "total": total}


@app.get("/api/satellite")
def satellite_info(con: sqlite3.Connection = Depends(db)):
    meta = {r["product"]: r for r in rows(con, "SELECT * FROM sat_meta")}
    products = {k: {**p, **{x: meta.get(k, {}).get(x) for x in ("date", "fetched_at", "units")}}
                for k, p in satellite.PRODUCTS.items()}
    overlays = []
    for key, o in satellite.OVERLAYS.items():
        d = meta.get(f"overlay:{o['layer']}", {}).get("date")
        if not d:
            continue
        if key == "truecolor":   # today's swaths are still being processed: show yesterday's full mosaic
            d = (date.fromisoformat(d) - timedelta(days=1)).isoformat()
        overlays.append({"id": key, "label": o["label"], "date": d, "nrt": key in NRT,
                         "url": f"https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{o['layer']}/default/{d}/{o['tms']}/{{z}}/{{y}}/{{x}}.{o['ext']}",
                         "maxNativeZoom": int(o["tms"].rsplit("Level", 1)[1]),
                         "legend": f"https://gibs.earthdata.nasa.gov/legends/{o['legend']}" if o["legend"] else None})
    # Meteosat IODC (EUMETSAT, over the Indian Ocean: covers the Caucasus and Central Asia), hourly frames only:
    # hourly imagery is free and unrestricted under the EUMETSAT data policy (15-min frames need a licence < 3 h)
    hour = (datetime.now(timezone.utc) - timedelta(minutes=75)).replace(minute=0, second=0, microsecond=0)
    overlays.append({"id": "meteosat", "label": "Clouds now, hourly (Meteosat IODC infrared, EUMETSAT)", "nrt": True,
                     "date": hour.strftime("%Y-%m-%d %H:00 UTC"), "wms": {
                         "url": "https://view.eumetsat.int/geoserver/ows", "layers": "msg_iodc:ir108",
                         "time": hour.strftime("%Y-%m-%dT%H:00:00Z")},
                     "attribution": f"Contains EUMETSAT Meteosat data {hour.year}", "legend": None})
    fm = meta.get("fires", {})
    if fm.get("date"):
        overlays.append({"id": "fires", "label": "Active fires, last 24 h (NASA FIRMS)", "nrt": True, "points": True,
                         "date": fm["date"].replace("T", " ").replace(":00Z", " UTC"), "legend": None})
    hls = []
    for layer in satellite.HLS:
        d = meta.get(f"overlay:{layer}", {}).get("date")
        if d:
            for k in range(12):
                day = (date.fromisoformat(d) - timedelta(days=k)).isoformat()
                hls.append(f"https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{layer}/default/{day}/"
                           "GoogleMapsCompatible_Level12/{z}/{y}/{x}.png")
    base = {"land": "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/OSM_Land_Water_Map/default/2026-01-01/"
                    "GoogleMapsCompatible_Level9/{z}/{y}/{x}.png",
            "labels": "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/Reference_Labels_15m/default/2026-01-01/"
                      "GoogleMapsCompatible_Level13/{z}/{y}/{x}.png",
            "features": "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/Reference_Features_15m/default/2026-01-01/"
                        "GoogleMapsCompatible_Level13/{z}/{y}/{x}.png"}
    tc = next((o for o in overlays if o["id"] == "truecolor"), None)
    return {"products": products, "overlays": overlays, "hls": hls[::-1], "base": base,
            "truecolor": tc["url"] if tc else None}


@app.get("/api/world/overview")
@functools.lru_cache(maxsize=1)
def world_overview():
    """Per-country climate summary (mean over provinces / districts) for the home page and Near-Azerbaijan panel."""
    con = connect()
    try:
        per = rows(con, """SELECT r.iso3, c.name, c.grp, c.continent,
                 avg(CASE WHEN y.year BETWEEN 1981 AND 1990 THEN y.tmean END) t_past,
                 avg(CASE WHEN y.year BETWEEN 2016 AND 2025 THEN y.tmean END) t_now,
                 avg(CASE WHEN y.year BETWEEN 1981 AND 1990 THEN y.hot35 END) h_past,
                 avg(CASE WHEN y.year BETWEEN 2016 AND 2025 THEN y.hot35 END) h_now
                 FROM climate_year y JOIN rayons r ON r.id=y.rayon_id JOIN countries c ON c.iso3=r.iso3
                 WHERE y.partial=0 GROUP BY r.iso3""")
        fut = {r["iso3"]: r for r in rows(con, """SELECT r.iso3, avg(p.tmean) t, avg(p.hot35) h FROM projection_year p
                 JOIN rayons r ON r.id=p.rayon_id WHERE p.year BETWEEN 2041 AND 2050 GROUP BY r.iso3""")}
        for p_ in per:
            f = fut.get(p_["iso3"], {})
            p_["warming"] = (p_["t_now"] - p_["t_past"]) if p_["t_past"] is not None and p_["t_now"] is not None else None
            p_["t_2045"], p_["h_2045"] = f.get("t"), f.get("h")
        counts = row(con, """SELECT (SELECT count(*) FROM countries) countries,
                 (SELECT count(*) FROM rayons WHERE level='province') provinces,
                 (SELECT count(DISTINCT rayon_id) FROM climate_year) units_with_climate,
                 (SELECT count(DISTINCT rayon_id) FROM projection_year) units_with_projection,
                 (SELECT count(DISTINCT iso3) FROM country_yields) faostat_countries""")
        ws = [p_["warming"] for p_ in per if p_["warming"] is not None]
        return {"counts": counts, "countries": per, "world_mean_warming": sum(ws) / len(ws) if ws else None,
                "near": sorted([p_ for p_ in per if p_["grp"] != "world"], key=lambda r: -(r["warming"] or 0))}
    finally:
        con.close()


@app.get("/api/geo/regions")
def geo():
    return FileResponse(ROOT / "data" / "regions.geojson", media_type="application/geo+json")


@app.get("/api/crops")
def crops(con: sqlite3.Connection = Depends(db)):
    out = rows(con, "SELECT id, name, name_az, grp, perennial, eco FROM crops ORDER BY ord")
    for c in out:
        c["eco"] = json.loads(c["eco"]) if c["eco"] else None
    return out


@app.get("/api/rayons")
def rayons(scope: str = "AZE", con: sqlite3.Connection = Depends(db)):
    """Districts of Azerbaijan by default; scope=<ISO3> lists that country's provinces."""
    out = rows(con, """SELECT r.*, s.ph, s.texture, s.soc,
        (SELECT count(DISTINCT user_id) FROM farms f WHERE f.rayon_id=r.id) farmers
        FROM rayons r LEFT JOIN soil s ON s.rayon_id=r.id WHERE r.iso3=? ORDER BY r.econ, r.name""", scope.upper())
    for r in out:
        r["rating"] = services.rayon_rating(con, r["id"])
    return out


@app.get("/api/countries")
def countries(con: sqlite3.Connection = Depends(db)):
    return rows(con, "SELECT * FROM countries ORDER BY grp='home' DESC, grp='near' DESC, name")


@app.get("/api/countries/{iso3}")
def country(iso3: str):
    return need(services.country_profile(iso3.upper()))


@app.get("/api/geo/world")
def geo_world():
    return FileResponse(ROOT / "data" / "geo_web" / "world.geojson", media_type="application/geo+json")


@app.get("/api/geo/country/{iso3}")
def geo_country(iso3: str):
    iso3 = iso3.upper()
    if iso3 == "AZE":
        return FileResponse(ROOT / "data" / "regions.geojson", media_type="application/geo+json")
    if not re.fullmatch(r"[A-Z]{3}", iso3):
        raise HTTPException(404, "Not found")
    f = ROOT / "data" / "geo_web" / f"{iso3}.geojson"
    if not f.exists():
        raise HTTPException(404, "Not found")
    return FileResponse(f, media_type="application/geo+json")


LAYERS = Literal["yield", "production", "suitability", "suit_change", "warming", "hot35", "frost", "precip",
                 "ph", "soc", "rating", "farmers", "ndvi", "ndvi_anom", "smap", "smap_anom", "rain7"]
STATIC_LAYERS = {"suitability", "suit_change", "warming", "hot35", "frost", "precip", "ph", "soc"}


@app.get("/api/map")
def map_layer(layer: LAYERS = "yield", crop: str = "bugda", year: int | None = None, irrigated: bool = True,
              scope: str = "AZE", con: sqlite3.Connection = Depends(db)):
    """One value per polygon: scope=AZE districts, scope=<ISO3> provinces, scope=world countries."""
    scope = scope.upper() if scope.lower() != "world" else "world"
    if scope == "world" and layer in ("yield", "production"):
        year = year or con.execute("SELECT max(year) FROM country_yields WHERE crop_id=? AND yield>0",
                                   (crop,)).fetchone()[0]
        vals = {r["iso3"]: r["v"] for r in rows(con, f"SELECT iso3, {layer} v FROM country_yields WHERE crop_id=? "
                                                     f"AND year=? AND {layer}>0", crop, year)}
        return {"layer": layer, "crop": crop, "year": year, "unit": "c/ha" if layer == "yield" else "t",
                "values": vals, "source": "FAOSTAT"}
    if scope != "AZE" and layer in ("yield", "production"):
        raise HTTPException(422, "Province-level yields exist only for Azerbaijan; use the world view for FAOSTAT")
    if layer in STATIC_LAYERS:
        vals, unit = _unit_layer(layer, crop, irrigated)
    else:
        vals, unit = _dynamic_layer(con, layer, crop, year)
        if layer in ("yield", "production"):
            year = year or con.execute("SELECT max(year) FROM yields WHERE crop_id=?", (crop,)).fetchone()[0]
    iso_of = _iso_of()
    if scope == "world":
        agg = {}
        for rid, v in vals.items():
            if v is not None:
                agg.setdefault(iso_of.get(rid), []).append(v)
        vals = {k: round(sum(v) / len(v), 2) for k, v in agg.items() if k}
    else:
        vals = {k: v for k, v in vals.items() if iso_of.get(k) == scope}
    return {"layer": layer, "crop": crop, "year": year, "unit": unit, "values": vals}


@functools.lru_cache(maxsize=1)
def _iso_of():
    con = connect()
    try:
        return {r["id"]: r["iso3"] for r in rows(con, "SELECT id, iso3 FROM rayons")}
    finally:
        con.close()


@functools.lru_cache(maxsize=256)
def _unit_layer(layer, crop, irrigated):
    """Static per-unit layers (all units worldwide), cached: the data only changes on rebuild."""
    con = connect()
    try:
        vals = {}
        if layer in ("suitability", "suit_change"):
            col = "irrigated" if irrigated else "rainfed"
            now = {r["rayon_id"]: r["v"] for r in rows(con, f"SELECT rayon_id, {col} v FROM suitability "
                                                            "WHERE crop_id=? AND period='2016-2025'", crop)}
            if layer == "suitability":
                return {k: round(v * 100) for k, v in now.items()}, "score"
            for r in rows(con, f"SELECT rayon_id, {col} v FROM suitability WHERE crop_id=? AND period='2041-2050'",
                          crop):
                if r["rayon_id"] in now:
                    vals[r["rayon_id"]] = round((r["v"] - now[r["rayon_id"]]) * 100)
            return vals, "pts (2041-50 vs now)"
        if layer in ("warming", "hot35", "frost", "precip"):
            col = "tmean" if layer == "warming" else layer
            for r in rows(con, f"""SELECT rayon_id, avg(CASE WHEN year>=2016 THEN {col} END) -
                           avg(CASE WHEN year<=1990 THEN {col} END) v FROM climate_year WHERE partial=0
                           GROUP BY rayon_id"""):
                if r["v"] is not None:
                    vals[r["rayon_id"]] = round(r["v"], 2)
            return vals, {"warming": "°C", "hot35": "days", "frost": "days", "precip": "mm"}[layer] + " (2016-25 vs 1981-90)"
        vals = {r["rayon_id"]: r["v"] for r in rows(con, f"SELECT rayon_id, {layer} v FROM soil WHERE {layer} IS NOT NULL")}
        return vals, "pH" if layer == "ph" else "g/kg"
    finally:
        con.close()


def _dynamic_layer(con, layer, crop, year):
    vals = {}
    if layer in ("ndvi", "ndvi_anom", "smap", "smap_anom", "rain7"):
        product = layer.split("_")[0]
        for r in rows(con, "SELECT rayon_id, value, normal FROM sat_obs WHERE product=?", product):
            if layer.endswith("_anom"):
                if r["normal"] is None or r["value"] is None:
                    continue
                vals[r["rayon_id"]] = round(r["value"] - r["normal"], 3)
            else:
                vals[r["rayon_id"]] = round(r["value"], 3)
        d = row(con, "SELECT date FROM sat_meta WHERE product=?", product)
        unit = {"ndvi": "NDVI", "ndvi_anom": "NDVI vs 5-yr normal", "smap": "m³/m³", "smap_anom": "m³/m³ vs normal",
                "rain7": "mm, last 7 days"}[layer]
        return vals, f"{unit} · {d['date'] if d else ''}"
    if layer in ("yield", "production"):
        year = year or con.execute("SELECT max(year) FROM yields WHERE crop_id=?", (crop,)).fetchone()[0]
        for r in rows(con, f"SELECT rayon_id, {layer} v FROM yields WHERE crop_id=? AND year=? AND {layer}>0",
                      crop, year):
            vals[r["rayon_id"]] = r["v"]
        return vals, "c/ha" if layer == "yield" else "t"
    if layer == "rating":
        for r in rows(con, "SELECT f.rayon_id, avg(rv.rating) v FROM reviews rv JOIN farms f ON f.user_id=rv.farmer_id "
                           "GROUP BY f.rayon_id"):
            vals[r["rayon_id"]] = round(r["v"], 2)
        return vals, "★"
    vals = {r["rayon_id"]: r["v"] for r in rows(con, "SELECT rayon_id, count(DISTINCT user_id) v FROM farms "
                                                     "GROUP BY rayon_id")}
    return vals, "farmers"


@app.get("/api/rayons/{rid}")
def rayon(rid: str):
    return need(services.rayon_profile(rid))


@app.get("/api/rayons/{rid}/climate")
def rayon_climate(rid: str, con: sqlite3.Connection = Depends(db)):
    need(row(con, "SELECT id FROM rayons WHERE id=?", rid))
    return {
        "annual": rows(con, "SELECT * FROM climate_year WHERE rayon_id=? ORDER BY year", rid),
        "monthly": rows(con, "SELECT * FROM climate_month WHERE rayon_id=? ORDER BY period, month", rid),
        "projection": rows(con, "SELECT * FROM projection_year WHERE rayon_id=? ORDER BY year", rid),
    }


@app.get("/api/rayons/{rid}/recommendations")
def rayon_recs(rid: str, irrigated: bool = True):
    return services.recommendations(rid, irrigated)


@app.get("/api/rayons/{rid}/yields")
def rayon_yields(rid: str, crop: str, con: sqlite3.Connection = Depends(db)):
    need(row(con, "SELECT id FROM rayons WHERE id=?", rid))
    out = services.yield_series(rid, crop)
    r = row(con, "SELECT iso3, level FROM rayons WHERE id=?", rid)
    if r["level"] == "province":
        out["crops"] = rows(con, """SELECT DISTINCT y.crop_id id, c.name FROM country_yields y JOIN crops c
                            ON c.id=y.crop_id WHERE y.iso3=? AND y.yield>0 ORDER BY c.ord""", r["iso3"])
    else:
        out["crops"] = rows(con, """SELECT DISTINCT y.crop_id id, c.name FROM yields y JOIN crops c ON c.id=y.crop_id
                            WHERE y.rayon_id=? AND y.yield>0 ORDER BY c.ord""", rid)
    return out


@app.get("/api/rayons/{rid}/forecast")
async def rayon_forecast(rid: str):
    con = connect()
    try:
        r = need(row(con, "SELECT * FROM rayons WHERE id=?", rid))
    finally:
        con.close()
    try:
        f = await forecast(r["lat"], r["lon"])
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Could not fetch weather forecast: {e}") from e
    snapshot(rid, f)
    f["daily"]["sky"] = [WMO.get(c, "") for c in f["daily"]["weather_code"]]
    return f


@app.get("/api/stats/ranking")
def stats_ranking(crop: str = "bugda", year: int | None = None, metric: Literal["yield", "production"] = "yield"):
    return services.ranking(crop, year, metric)


@app.get("/api/stats/crop/{cid}")
def stats_crop(cid: str, con: sqlite3.Connection = Depends(db)):
    c = need(row(con, "SELECT * FROM crops WHERE id=?", cid))
    c["eco"] = json.loads(c["eco"]) if c["eco"] else None
    nat = rows(con, "SELECT year, yield, production FROM national_yields WHERE crop_id=? ORDER BY year", cid)
    econ = rows(con, """SELECT r.econ, sum(y.production) production,
              sum(y.production)/NULLIF(sum(y.production/NULLIF(y.yield,0)),0) yield FROM yields y
              JOIN rayons r ON r.id=y.rayon_id WHERE y.crop_id=? AND y.year=(SELECT max(year) FROM yields
              WHERE crop_id=?) AND y.production>0 GROUP BY r.econ ORDER BY production DESC""", cid, cid)
    m = row(con, "SELECT * FROM model_metrics WHERE crop_id=?", cid)
    if m:
        m.update(json.loads(m.pop("importances")))
    suit = row(con, """SELECT avg(CASE WHEN period='1981-2010' THEN irrigated END) past,
             avg(CASE WHEN period='2016-2025' THEN irrigated END) now,
             avg(CASE WHEN period='2041-2050' THEN irrigated END) future FROM suitability WHERE crop_id=?""", cid)
    return {"crop": c, "national": nat, "econ": econ, "model": m, "suitability": suit}


@app.get("/api/stats/compare")
def stats_compare(rayons: str, crop: str = "bugda", con: sqlite3.Connection = Depends(db)):
    ids = [x for x in rayons.split(",") if x][:6]
    out = []
    for rid in ids:
        r = row(con, "SELECT id, name, econ FROM rayons WHERE id=?", rid)
        if not r:
            continue
        r["series"] = rows(con, "SELECT year, yield, production FROM yields WHERE rayon_id=? AND crop_id=? "
                                "ORDER BY year", rid, crop)
        r["compare"] = services.period_compare(con, rid)
        r["soil"] = row(con, "SELECT * FROM soil WHERE rayon_id=?", rid)
        r["suit"] = row(con, "SELECT irrigated, rainfed FROM suitability WHERE rayon_id=? AND crop_id=? "
                             "AND period='2016-2025'", rid, crop)
        r["rating"] = services.rayon_rating(con, rid)
        out.append(r)
    return {"crop": crop, "rayons": out,
            "national": rows(con, "SELECT year, yield FROM national_yields WHERE crop_id=? ORDER BY year", crop)}


@app.get("/api/stats/world")
def stats_world(crop: str = "bugda", year: int | None = None, metric: Literal["yield", "production"] = "yield"):
    return services.world_ranking(crop, year, metric)


@app.get("/api/stats/countries/compare")
def stats_countries_compare(iso3: str = "AZE,GEO,ARM,TUR,IRN", crop: str = "bugda",
                            con: sqlite3.Connection = Depends(db)):
    out = []
    for code in [x.strip().upper() for x in iso3.split(",") if x.strip()][:6]:
        c = row(con, "SELECT iso3, name, grp FROM countries WHERE iso3=?", code)
        if not c:
            continue
        c["series"] = rows(con, "SELECT year, yield, production FROM country_yields WHERE iso3=? AND crop_id=? "
                                "AND yield>0 ORDER BY year", code, crop)
        prof = services.country_profile(code)
        c["compare"], c["future"] = prof["compare"], prof["future"]
        c["suit"] = row(con, """SELECT avg(s.irrigated) irrigated, avg(s.rainfed) rainfed FROM suitability s
                        JOIN rayons r ON r.id=s.rayon_id WHERE r.iso3=? AND s.crop_id=? AND s.period='2016-2025'""",
                        code, crop)
        out.append(c)
    world = rows(con, "SELECT year, avg(yield) yield FROM country_yields WHERE crop_id=? AND yield>0 GROUP BY year "
                      "ORDER BY year", crop)
    return {"crop": crop, "countries": out, "world": world}


@app.get("/api/stats/regions")
def stats_regions(con: sqlite3.Connection = Depends(db)):
    """Region leaderboard: average yield index across crops vs the national level (last 3 stat years),
    plus buyer rating — powers 'most productive on top, least productive as a separate category'."""
    last = con.execute("SELECT max(year) FROM yields").fetchone()[0]
    data = rows(con, """SELECT y.rayon_id, r.name, r.econ, avg(y.yield / n.yield) idx, count(DISTINCT y.crop_id) ncrops,
              sum(y.production) prod FROM yields y JOIN national_yields n ON n.crop_id=y.crop_id AND n.year=y.year
              JOIN rayons r ON r.id=y.rayon_id WHERE y.year>? AND y.yield>0 AND n.yield>0 AND y.crop_id!='terevez'
              GROUP BY y.rayon_id HAVING ncrops>=5 ORDER BY idx DESC""", last - 3)
    n = len(data)
    for i, d in enumerate(data):
        d["rank"] = i + 1
        q = i / max(1, n)
        d["category"] = "Leader" if q < 0.25 else "Good" if q < 0.5 else "Average" if q < 0.75 else "Low"
        d["rating"] = services.rayon_rating(con, d["rayon_id"])
    return {"from_year": last - 2, "to_year": last, "rows": data}


# ------------------------------------------------------------------ auth & profile
PHONE_RE = re.compile(r"^\+?[0-9 ()-]{7,20}$")


class Register(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(default="", max_length=120, pattern=r"^$|^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: str = Field(default="", max_length=25)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["farmer", "buyer"]


def norm_phone(p):
    """Digits only, Azerbaijani local formats (050…, 50…) turned into 99450…"""
    d = re.sub(r"\D", "", p or "")
    if d.startswith("0") and len(d) == 10:
        d = "994" + d[1:]
    elif len(d) == 9:
        d = "994" + d
    return d


def user_by_phone(con, phone):
    n = norm_phone(phone)
    if len(n) < 9:
        return None
    for u in rows(con, "SELECT id, phone, password_hash FROM users WHERE phone != ''"):
        if norm_phone(u["phone"]) == n:
            return u
    return None


@app.post("/api/auth/register")
def register(b: Register):
    if b.phone and not PHONE_RE.match(b.phone):
        raise HTTPException(422, "Invalid phone number")
    if not b.email and not b.phone:
        raise HTTPException(422, "Give a phone number or an email")
    with tx() as con:
        if b.phone and user_by_phone(con, b.phone):
            raise HTTPException(409, "An account with this phone number already exists")
        try:
            cur = con.execute("INSERT INTO users(email, phone, password_hash, name, role) VALUES(?,?,?,?,?)",
                              (b.email.lower().strip() or None, b.phone.strip(), hash_password(b.password), b.name.strip(),
                               b.role))
        except sqlite3.IntegrityError as e:
            raise HTTPException(409, "An account with this email already exists") from e
        uid = cur.lastrowid
    return {"token": make_token(uid)}


DEMO_PHONE = "+994000000001"
DEMO_FARMS = [("Bankə", "neftcala", "qargidali"), ("Xıllı", "neftcala", "bugda"), ("Surra", "neftcala", "pambiq"), ("Salyan", "salyan", "pomidor")]


@app.post("/api/auth/demo")
def demo_login():
    """A shared, clearly marked demo farmer with fields along the Kür, so judges can open the app without signing up."""
    with tx() as con:
        u = row(con, "SELECT id FROM users WHERE phone=?", DEMO_PHONE)
        if not u:
            uid = con.execute("INSERT INTO users(email, phone, password_hash, name, role, is_demo, sms_alerts) VALUES(?,?,?,?,?,1,1)",
                              (None, DEMO_PHONE, hash_password(os.urandom(16).hex()), "Demo fermer", "farmer")).lastrowid
        else:
            uid = u["id"]
        if not con.execute("SELECT 1 FROM farms WHERE user_id=?", (uid,)).fetchone():
            _, villages = kur.geometry()
            vmap = {v["name"]: v for v in villages}
            for name, rayon, crop in DEMO_FARMS:
                v = vmap.get(name)
                if not v:
                    continue
                pt = kur.nearest_km(v["lat"], v["lon"])
                fid = con.execute("INSERT INTO farms(user_id, name, rayon_id, lat, lon, irrigated, water_source, pump_lat, pump_lon, pump_km) "
                                  "VALUES(?,?,?,?,?,1,'kur',?,?,?)", (uid, name, rayon, v["lat"], v["lon"], pt["lat"], pt["lon"], pt["km"])).lastrowid
                con.execute("INSERT OR IGNORE INTO farm_crops VALUES(?,?)", (fid, crop))
    return {"token": make_token(uid)}


class Login(BaseModel):
    email: str
    password: str


@app.post("/api/auth/login")
def login(b: Login, con: sqlite3.Connection = Depends(db)):
    who = b.email.strip()       # email or phone number
    u = row(con, "SELECT id, password_hash FROM users WHERE email=?", who.lower()) if "@" in who else user_by_phone(con, who)
    if not u or not verify_password(b.password, u["password_hash"]):
        raise HTTPException(401, "Wrong phone/email or password")
    return {"token": make_token(u["id"])}


@app.get("/api/me")
def me(user=Depends(current_user), con: sqlite3.Connection = Depends(db)):
    user["farms"] = _farms(con, user["id"])
    user["unread"] = con.execute("SELECT count(*) FROM alerts WHERE user_id=? AND read=0", (user["id"],)).fetchone()[0]
    return user


class Profile(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    phone: str = Field(default="", max_length=25)
    bio: str = Field(default="", max_length=1000)
    whatsapp: str = Field(default="", max_length=25)
    telegram: str = Field(default="", max_length=40, pattern=r"^@?[A-Za-z0-9_]{0,40}$")
    show_phone: bool = True
    sms_alerts: bool = True


@app.put("/api/me")
def update_me(b: Profile, user=Depends(current_user)):
    for p in (b.phone, b.whatsapp):
        if p and not PHONE_RE.match(p):
            raise HTTPException(422, "Invalid phone number")
    with tx() as con:
        con.execute("UPDATE users SET name=?, phone=?, bio=?, whatsapp=?, telegram=?, show_phone=?, sms_alerts=? "
                    "WHERE id=?", (b.name, b.phone, b.bio, b.whatsapp, b.telegram.lstrip("@"), int(b.show_phone),
                                   int(b.sms_alerts), user["id"]))
    return {"ok": True}


def _farms(con, uid):
    out = rows(con, "SELECT f.*, r.name rayon, r.iso3, r.econ country FROM farms f JOIN rayons r ON r.id=f.rayon_id WHERE f.user_id=? "
                    "ORDER BY f.id", uid)
    for f in out:
        f["crops"] = [r["crop_id"] for r in rows(con, "SELECT crop_id FROM farm_crops WHERE farm_id=?", f["id"])]
    return out


class Farm(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    rayon_id: str
    lat: float | None = Field(default=None, ge=-60.0, le=85.0)
    lon: float | None = Field(default=None, ge=-180.0, le=180.0)
    area_ha: float | None = Field(default=None, ge=0, le=100000)
    irrigated: bool = True
    crops: list[str] = Field(default_factory=list, max_length=20)
    # Kür salt-water module
    water_source: Literal["kur", "canal", "well", "pond", "none"] | None = None
    pump_lat: float | None = Field(default=None, ge=38.5, le=41.0)
    pump_lon: float | None = Field(default=None, ge=47.5, le=50.0)
    pond_m3: float | None = Field(default=None, ge=0, le=10_000_000)
    drainage: bool | None = None
    irr_method: Literal["furrow", "drip", "sprinkler", "flood"] | None = None
    soil_ec: float | None = Field(default=None, ge=0, le=100)
    soil_ph: float | None = Field(default=None, ge=3, le=11)
    salty_note: str | None = Field(default=None, max_length=300)


KUR_FIELDS = ["water_source", "pump_lat", "pump_lon", "pump_km", "pond_m3", "drainage", "irr_method", "soil_ec",
              "soil_ph", "salty_note"]


def _kur_values(b: Farm):
    km = None
    if b.water_source in ("kur", "canal") and b.pump_lat is not None and b.pump_lon is not None:
        near = kur.nearest_km(b.pump_lat, b.pump_lon)
        if near["dist_km"] > 3:
            raise HTTPException(400, "The pump / intake point must be on the Kür (within 3 km of the river)")
        km = near["km"]
    return [b.water_source, b.pump_lat, b.pump_lon, km, b.pond_m3,
            None if b.drainage is None else int(b.drainage), b.irr_method, b.soil_ec, b.soil_ph, b.salty_note]


def _save_farm(con, uid, b: Farm, fid=None):
    need(row(con, "SELECT id FROM rayons WHERE id=?", b.rayon_id), "District not found")
    valid = {r["id"] for r in rows(con, "SELECT id FROM crops")}
    if fid:
        con.execute("UPDATE farms SET name=?, rayon_id=?, lat=?, lon=?, area_ha=?, irrigated=? WHERE id=? AND user_id=?",
                    (b.name, b.rayon_id, b.lat, b.lon, b.area_ha, int(b.irrigated), fid, uid))
        con.execute("DELETE FROM farm_crops WHERE farm_id=?", (fid,))
    else:
        fid = con.execute("INSERT INTO farms(user_id, name, rayon_id, lat, lon, area_ha, irrigated) VALUES(?,?,?,?,?,?,?)",
                          (uid, b.name, b.rayon_id, b.lat, b.lon, b.area_ha, int(b.irrigated))).lastrowid
    con.execute("UPDATE farms SET " + ", ".join(f"{c}=?" for c in KUR_FIELDS) + " WHERE id=?", (*_kur_values(b), fid))
    for c in set(b.crops) & valid:
        con.execute("INSERT INTO farm_crops VALUES(?,?)", (fid, c))
    return fid


@app.post("/api/me/farms")
def add_farm(b: Farm, user=Depends(current_user)):
    if user["role"] != "farmer":
        raise HTTPException(403, "Only farmer accounts can add farms")
    with tx() as con:
        fid = _save_farm(con, user["id"], b)
        first = con.execute("SELECT count(*) FROM farms WHERE user_id=?", (user["id"],)).fetchone()[0] == 1
    if user.get("sms_alerts") and user.get("phone"):
        hello = (f"Field Shift - {b.name}: qeydiyyat tamamlandi. Kurun suyu duzlananda ve sulama vaxti gelende SMS alacaqsan."
                 if first else f"Field Shift - {b.name} sahesi elave olundu.")
        sms.send(user["id"], user["phone"], hello.translate(alerts._TR))
    return {"id": fid}


@app.put("/api/me/farms/{fid}")
def edit_farm(fid: int, b: Farm, user=Depends(current_user)):
    with tx() as con:
        need(row(con, "SELECT id FROM farms WHERE id=? AND user_id=?", fid, user["id"]))
        _save_farm(con, user["id"], b, fid)
    return {"ok": True}


@app.delete("/api/me/farms/{fid}")
def del_farm(fid: int, user=Depends(current_user)):
    with tx() as con:
        con.execute("DELETE FROM farms WHERE id=? AND user_id=?", (fid, user["id"]))
    return {"ok": True}


# ------------------------------------------------------------------ farmers directory & reviews
def _public_farmer(con, u, viewer=None):
    u["farms"] = _farms(con, u["id"])
    r = row(con, "SELECT avg(rating) avg, count(*) n FROM reviews WHERE farmer_id=?", u["id"])
    u["rating"] = {"avg": round(r["avg"], 2) if r["avg"] else None, "count": r["n"]}
    if not u.pop("show_phone", 1) and not (viewer and viewer["id"] == u["id"]):
        u["phone"] = ""
    u.pop("email", None)
    return u


@app.get("/api/farmers")
def farmers(rayon: str | None = None, crop: str | None = None, q: str | None = None, country: str | None = None,
            sort: Literal["rating", "new", "reviews"] = "rating", viewer=Depends(optional_user),
            con: sqlite3.Connection = Depends(db)):
    sql = ["SELECT DISTINCT u.id, u.name, u.phone, u.bio, u.whatsapp, u.telegram, u.show_phone, u.created_at, u.is_demo "
           "FROM users u LEFT JOIN farms f ON f.user_id=u.id LEFT JOIN farm_crops fc ON fc.farm_id=f.id "
           "LEFT JOIN rayons rr ON rr.id=f.rayon_id "
           "WHERE u.role='farmer'"]
    args = []
    if rayon:
        sql.append("AND f.rayon_id=?")
        args.append(rayon)
    if country:
        sql.append("AND rr.iso3=?")
        args.append(country.upper())
    if crop:
        sql.append("AND fc.crop_id=?")
        args.append(crop)
    if q:
        sql.append("AND (u.name LIKE ? OR u.bio LIKE ?)")
        args += [f"%{q}%", f"%{q}%"]
    out = [_public_farmer(con, u, viewer) for u in rows(con, " ".join(sql), *args)]
    key = {"rating": lambda u: (-(u["rating"]["avg"] or 0), -u["rating"]["count"]),
           "reviews": lambda u: -u["rating"]["count"], "new": lambda u: u["created_at"]}[sort]
    out.sort(key=key, reverse=sort == "new")
    return out


@app.get("/api/farmers/{uid}")
def farmer(uid: int, viewer=Depends(optional_user), con: sqlite3.Connection = Depends(db)):
    u = need(row(con, "SELECT id, name, phone, bio, whatsapp, telegram, show_phone, created_at, is_demo FROM users "
                      "WHERE id=? AND role='farmer'", uid))
    u = _public_farmer(con, u, viewer)
    u["reviews"] = rows(con, """SELECT rv.*, a.name author, a.role author_role, a.is_demo author_demo, c.name crop FROM reviews rv
                        JOIN users a ON a.id=rv.author_id LEFT JOIN crops c ON c.id=rv.crop_id
                        WHERE rv.farmer_id=? ORDER BY rv.id DESC""", uid)
    u["histogram"] = {i: 0 for i in range(1, 6)}
    for r in u["reviews"]:
        u["histogram"][r["rating"]] += 1
    return u


class Review(BaseModel):
    rating: int = Field(ge=1, le=5)
    crop_id: str | None = None
    comment: str = Field(default="", max_length=1500)


@app.post("/api/farmers/{uid}/reviews")
def add_review(uid: int, b: Review, user=Depends(current_user)):
    if uid == user["id"]:
        raise HTTPException(400, "You cannot review yourself")
    with tx() as con:
        need(row(con, "SELECT id FROM users WHERE id=? AND role='farmer'", uid))
        con.execute("INSERT INTO reviews(farmer_id, author_id, rating, crop_id, comment) VALUES(?,?,?,?,?) "
                    "ON CONFLICT(farmer_id, author_id, crop_id) DO UPDATE SET rating=excluded.rating, "
                    "comment=excluded.comment, created_at=datetime('now')",
                    (uid, user["id"], b.rating, b.crop_id or None, b.comment.strip()))
    return {"ok": True}


@app.delete("/api/reviews/{rid}")
def del_review(rid: int, user=Depends(current_user)):
    with tx() as con:
        con.execute("DELETE FROM reviews WHERE id=? AND author_id=?", (rid, user["id"]))
    return {"ok": True}


# ------------------------------------------------------------------ alerts & SMS (simulated)
@app.get("/api/me/alerts")
def my_alerts(user=Depends(current_user), con: sqlite3.Connection = Depends(db)):
    return rows(con, """SELECT a.*, f.name farm FROM alerts a LEFT JOIN farms f ON f.id=a.farm_id
                WHERE a.user_id=? ORDER BY a.event_date DESC, a.id DESC LIMIT 200""", user["id"])


@app.post("/api/me/alerts/read")
def read_alerts(user=Depends(current_user)):
    with tx() as con:
        con.execute("UPDATE alerts SET read=1 WHERE user_id=?", (user["id"],))
    return {"ok": True}


@app.post("/api/me/alerts/check")
async def check_now(user=Depends(current_user)):
    created, failed = await alerts.check_user(user["id"])
    return {"created": len(created), "failed": failed}


@app.get("/api/me/sms")
def my_sms(user=Depends(current_user), con: sqlite3.Connection = Depends(db)):
    return rows(con, "SELECT * FROM sms_outbox WHERE user_id=? ORDER BY id DESC LIMIT 100", user["id"])


# ------------------------------------------------------------------ AI chat (DeepSeek)
class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    rayon_id: str | None = None


_chat_hits: dict[int, list[float]] = {}


def _chat_limit(uid, n=30):
    """The site is public and the demo account is shared: cap LLM calls per account per hour."""
    now_ = time.time()
    hits = [t for t in _chat_hits.get(uid, []) if now_ - t < 3600]
    if len(hits) >= n:
        raise HTTPException(429, "Too many questions, try again in an hour")
    _chat_hits[uid] = hits + [now_]


@app.post("/api/chat")
async def chat_post(b: ChatIn, user=Depends(current_user)):
    _chat_limit(user["id"])
    if not chat.enabled():
        raise HTTPException(503, "AI chat is not enabled: DEEPSEEK_API_KEY is not set on the server")
    try:
        return await chat.answer(user, b.message, b.rayon_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"AI service did not respond: {str(e)[:200]}") from e


@app.post("/api/chat/stream")
async def chat_stream(b: ChatIn, user=Depends(current_user)):
    """NDJSON event stream: live tool steps, then answer tokens."""
    _chat_limit(user["id"])
    if not chat.enabled():
        raise HTTPException(503, "AI chat is not enabled: DEEPSEEK_API_KEY is not set on the server")

    async def gen():
        try:
            async for ev in chat.answer_stream(user, b.message, b.rayon_id):
                yield json.dumps(ev, ensure_ascii=False) + "\n"
        except Exception as e:  # noqa: BLE001
            yield json.dumps({"t": "error", "v": f"AI service did not respond: {str(e)[:200]}"}) + "\n"
    return StreamingResponse(gen(), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/chat/history")
def chat_history(user=Depends(current_user), con: sqlite3.Connection = Depends(db)):
    return rows(con, "SELECT role, content, created_at FROM chat_messages WHERE user_id=? ORDER BY id DESC LIMIT 50",
                user["id"])[::-1]


@app.delete("/api/chat/history")
def chat_clear(user=Depends(current_user)):
    with tx() as con:
        con.execute("DELETE FROM chat_messages WHERE user_id=?", (user["id"],))
    return {"ok": True}


# ------------------------------------------------------------------ Feedback+
KINDS = Literal["idea", "bug", "data", "praise"]


class FeedbackIn(BaseModel):
    kind: KINDS
    title: str = Field(min_length=3, max_length=140)
    body: str = Field(default="", max_length=4000)
    rating: int | None = Field(default=None, ge=1, le=5)
    page: str = Field(default="", max_length=200)


@app.get("/api/feedback")
def feedback_list(kind: str | None = None, status: str | None = None,
                  sort: Literal["top", "new"] = "top", viewer=Depends(optional_user),
                  con: sqlite3.Connection = Depends(db)):
    sql = """SELECT fb.*, u.name author, u.is_demo author_demo,
             (SELECT count(*) FROM feedback_votes v WHERE v.feedback_id=fb.id) votes,
             (SELECT count(*) FROM feedback_comments c WHERE c.feedback_id=fb.id) comments,
             (SELECT count(*) FROM feedback_votes v WHERE v.feedback_id=fb.id AND v.user_id=?) voted
             FROM feedback fb LEFT JOIN users u ON u.id=fb.user_id WHERE 1=1"""
    args = [viewer["id"] if viewer else -1]
    if kind:
        sql += " AND fb.kind=?"
        args.append(kind)
    if status:
        sql += " AND fb.status=?"
        args.append(status)
    sql += " ORDER BY votes DESC, fb.id DESC" if sort == "top" else " ORDER BY fb.id DESC"
    items = rows(con, sql, *args)
    st = row(con, "SELECT count(*) n, avg(rating) avg FROM feedback WHERE rating IS NOT NULL")
    dist = {r["rating"]: r["n"] for r in rows(con, "SELECT rating, count(*) n FROM feedback WHERE rating IS NOT NULL "
                                                   "GROUP BY rating")}
    by_kind = {r["kind"]: r["n"] for r in rows(con, "SELECT kind, count(*) n FROM feedback GROUP BY kind")}
    return {"items": items, "summary": {"count": st["n"], "avg": st["avg"], "dist": dist, "by_kind": by_kind}}


@app.post("/api/feedback")
def feedback_add(b: FeedbackIn, user=Depends(current_user)):
    with tx() as con:
        fid = con.execute("INSERT INTO feedback(user_id, kind, title, body, rating, page) VALUES(?,?,?,?,?,?)",
                          (user["id"], b.kind, b.title.strip(), b.body.strip(), b.rating, b.page)).lastrowid
        con.execute("INSERT INTO feedback_votes VALUES(?,?)", (fid, user["id"]))
    return {"id": fid}


@app.get("/api/feedback/{fid}")
def feedback_get(fid: int, con: sqlite3.Connection = Depends(db)):
    f = need(row(con, "SELECT fb.*, u.name author, u.is_demo author_demo FROM feedback fb LEFT JOIN users u ON u.id=fb.user_id "
                      "WHERE fb.id=?", fid))
    f["votes"] = con.execute("SELECT count(*) FROM feedback_votes WHERE feedback_id=?", (fid,)).fetchone()[0]
    f["comments"] = rows(con, "SELECT c.*, u.name author, u.is_demo author_demo FROM feedback_comments c JOIN users u ON u.id=c.user_id "
                              "WHERE c.feedback_id=? ORDER BY c.id", fid)
    return f


@app.post("/api/feedback/{fid}/vote")
def feedback_vote(fid: int, user=Depends(current_user)):
    with tx() as con:
        need(row(con, "SELECT id FROM feedback WHERE id=?", fid))
        cur = con.execute("DELETE FROM feedback_votes WHERE feedback_id=? AND user_id=?", (fid, user["id"]))
        if not cur.rowcount:
            con.execute("INSERT INTO feedback_votes VALUES(?,?)", (fid, user["id"]))
        voted = not cur.rowcount
        n = con.execute("SELECT count(*) FROM feedback_votes WHERE feedback_id=?", (fid,)).fetchone()[0]
    return {"voted": voted, "votes": n}


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


@app.post("/api/feedback/{fid}/comments")
def feedback_comment(fid: int, b: CommentIn, user=Depends(current_user)):
    with tx() as con:
        need(row(con, "SELECT id FROM feedback WHERE id=?", fid))
        con.execute("INSERT INTO feedback_comments(feedback_id, user_id, body) VALUES(?,?,?)",
                    (fid, user["id"], b.body.strip()))
    return {"ok": True}


# ------------------------------------------------------------------ SPA
DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        f = DIST / path
        if path and f.is_file() and DIST in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-cache"})   # new builds show at once
