"""Live NASA satellite conditions per district / province, from NASA GIBS (no login needed).

GIBS serves colour-mapped images; every colour maps to an exact value range in the published colormap, so images are
decoded back to physical values and averaged over each unit with the label grids built by etl.sat_labels.

  ndvi   MODIS Aqua NDVI, monthly (1 km)          latest month vs the same month of the previous 5 years
  smap   SMAP L4 root-zone soil moisture, daily   latest day vs the same calendar day 2016 onward
  rain7  GPM IMERG precipitation, daily           total of the last 7 available days (mm)

Results go to sat_obs (one row per unit and product); refreshed every 12 h by loop().
"""
import asyncio
import calendar
import io
import json
import logging
import re
import time
from datetime import date, timedelta

import httpx
import numpy as np
from PIL import Image

from .db import ROOT, connect, rows, tx

log = logging.getLogger("satellite")
SAT = ROOT / "data" / "sat"
WMS = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
CAPS = "https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/1.0.0/WMTSCapabilities.xml"
PRODUCTS = {
    "ndvi": {"layer": "MODIS_Aqua_L3_NDVI_Monthly", "cmap": "MODIS_L3_NDVI", "unit": "NDVI",
             "label": "Vegetation (MODIS NDVI)"},
    "smap": {"layer": "SMAP_L4_Analyzed_Root_Zone_Soil_Moisture", "cmap": "SMAP_Analyzed_Soil_Moisture", "unit": "m³/m³",
             "label": "Root-zone soil moisture (SMAP L4)"},
    "rain7": {"layer": "IMERG_Precipitation_Rate", "cmap": "GPM_Precipitation_Rate", "unit": "mm",
              "label": "Rain, last 7 days (GPM IMERG)"},
}
# map overlays (rendered tiles, shown as-is); tms = EPSG:3857 tile matrix set by native resolution
OVERLAYS = {
    "truecolor": {"layer": "VIIRS_NOAA20_CorrectedReflectance_TrueColor", "tms": "GoogleMapsCompatible_Level9",
                  "ext": "jpg", "label": "True colour (VIIRS NOAA-20)", "legend": None},
    "ndvi8": {"layer": "MODIS_Terra_NDVI_8Day", "tms": "GoogleMapsCompatible_Level9", "ext": "png",
              "label": "Vegetation, 8-day (MODIS NDVI)", "legend": "MODIS_NDVI_H.svg"},
    "smap": {"layer": "SMAP_L4_Analyzed_Root_Zone_Soil_Moisture", "tms": "GoogleMapsCompatible_Level6", "ext": "png",
             "label": "Root-zone soil moisture (SMAP L4)", "legend": "SMAP_Analyzed_Soil_Moisture_H.svg"},
    "imerg": {"layer": "IMERG_Precipitation_Rate", "tms": "GoogleMapsCompatible_Level6", "ext": "png",
              "label": "Precipitation, daily (GPM IMERG)", "legend": "GPM_Precipitation_Rate_H.svg"},
    # near-real-time (NASA LANCE, a few hours after the satellite pass)
    "imerg30": {"layer": "IMERG_Precipitation_Rate_30min", "tms": "GoogleMapsCompatible_Level6", "ext": "png", "timed": True,
                "label": "Rain now, 30 min (GPM IMERG Early, NRT)", "legend": "GPM_Precipitation_Rate_H.svg"},
    "modis_today": {"layer": "MODIS_Terra_CorrectedReflectance_TrueColor", "tms": "GoogleMapsCompatible_Level9",
                    "ext": "jpg", "label": "True colour today (MODIS Terra, LANCE NRT)", "legend": None},
    "lst_day": {"layer": "MODIS_Aqua_Land_Surface_Temp_Day", "tms": "GoogleMapsCompatible_Level7", "ext": "png",
                "label": "Land surface temperature, day (MODIS Aqua, NRT)", "legend": "MODIS_Land_Surface_Temp_H.svg"},
    "lst_night": {"layer": "MODIS_Terra_Land_Surface_Temp_Night", "tms": "GoogleMapsCompatible_Level7", "ext": "png",
                  "label": "Land surface temperature, night: frost (MODIS Terra, NRT)",
                  "legend": "MODIS_Land_Surface_Temp_H.svg"},
    "snow": {"layer": "MODIS_Terra_L3_NDSI_Snow_Cover_Daily", "tms": "GoogleMapsCompatible_Level8", "ext": "png",
             "label": "Snow cover, daily (MODIS Terra)", "legend": "MODIS_NDSI_Snow_Cover_H.svg"},
}
TIMED = {o["layer"] for o in OVERLAYS.values() if o.get("timed")}   # sub-daily layers keep their full timestamp


# 30 m Harmonized Landsat-Sentinel-2 true colour: daily swaths are patchy, so the farm picker stacks the last 12 days
HLS = ["HLS_S30_Nadir_BRDF_Adjusted_Reflectance", "HLS_L30_Nadir_BRDF_Adjusted_Reflectance"]


def _client():
    return httpx.Client(timeout=180, headers={"User-Agent": "FieldShift/1.0 (NASA Space Apps 2026)"})


def colormap(name, client):
    """{packed rgb: value} for every non-transparent entry of a GIBS colormap (range midpoint)."""
    f = SAT / f"cm_{name}.xml"
    if not f.exists():
        r = client.get(f"https://gibs.earthdata.nasa.gov/colormaps/v1.3/{name}.xml")
        r.raise_for_status()
        f.write_text(r.text)
    lut = {}
    for m in re.finditer(r'<ColorMapEntry rgb="(\d+),(\d+),(\d+)"([^>]*)/>', f.read_text()):
        attrs = m.group(4)
        if 'transparent="true"' in attrs or "nodata" in attrs:
            continue
        v = re.search(r'value="\[([^,\]]+)(?:,([^)\]]+))?[)\]]"', attrs)
        if not v:
            continue
        a = float(v.group(1).replace("+INF", "inf").replace("-INF", "-inf"))
        b = float(v.group(2).replace("+INF", "inf").replace("-INF", "-inf")) if v.group(2) else a
        val = a if b == float("inf") else b if a == float("-inf") else (a + b) / 2
        lut[int(m.group(1)) * 65536 + int(m.group(2)) * 256 + int(m.group(3))] = val
    return lut


def latest_dates(client):
    """Default (latest) date of each product / overlay layer from the WMTS capabilities."""
    for attempt in range(3):
        try:
            s = client.get(CAPS).text
            break
        except httpx.HTTPError:
            if attempt == 2:
                raise
            time.sleep(10)
    out = {}
    for name in {p["layer"] for p in PRODUCTS.values()} | {o["layer"] for o in OVERLAYS.values()} | set(HLS):
        m = re.search(r"<ows:Identifier>" + name + r"</ows:Identifier>.*?<Default>([^<]+)</Default>", s, re.S)
        if m:
            out[name] = m.group(1) if name in TIMED else m.group(1)[:10]
    return out


class Grid:
    def __init__(self, name, meta):
        self.name, self.m = name, meta
        self.lab = np.load(SAT / f"labels_{name}.npy").astype(np.int32)
        self.n = len(meta["ids"]) + 1
        self.fallback = {meta["ids"].index(k): v for k, v in meta["fallback"].items()}

    def fetch(self, client, layer, day, lut):
        s, w, n, e = self.m["bbox"]
        params = {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": layer, "CRS": "EPSG:4326",
                  "BBOX": f"{s},{w},{n},{e}", "WIDTH": self.m["width"], "HEIGHT": self.m["height"],
                  "FORMAT": "image/png", "TIME": day}
        r = None
        for attempt in range(3):
            try:
                r = client.get(WMS, params=params)
                r.raise_for_status()
                break
            except httpx.HTTPError as e:
                log.warning("GIBS %s %s %s attempt %d: %s", layer, day, self.name, attempt, e)
                r = None
                time.sleep(5 * (attempt + 1))
        if r is None:
            return None
        if not r.headers.get("content-type", "").startswith("image"):
            return None
        a = np.asarray(Image.open(io.BytesIO(r.content)).convert("RGBA"))
        keys = a[..., 0].astype(np.int64) * 65536 + a[..., 1].astype(np.int64) * 256 + a[..., 2]
        vals = np.full(keys.shape, np.nan, dtype="float32")
        opaque = a[..., 3] > 0
        if not opaque.any():
            return None
        uk, inv = np.unique(keys[opaque], return_inverse=True)
        vals[opaque] = np.array([lut.get(int(k), np.nan) for k in uk], dtype="float32")[inv]
        return vals

    def zonal(self, vals):
        """Mean value per unit (index 1..n-1), NaN where the image has no data over the unit."""
        ok = ~np.isnan(vals) & (self.lab > 0)
        s = np.bincount(self.lab[ok], weights=vals[ok], minlength=self.n)
        c = np.bincount(self.lab[ok], minlength=self.n)
        out = np.where(c > 0, s / np.maximum(c, 1), np.nan)
        for i, (row, col) in self.fallback.items():
            out[i + 1] = vals[row, col]
        return out[1:]


def _ndvi_dates(latest):
    d = date.fromisoformat(latest)
    return latest, [f"{d.year - k}-{d.month:02d}-01" for k in range(1, 6)]


def _smap_dates(latest):
    d = date.fromisoformat(latest)
    out = []
    for y in range(2016, d.year):
        try:
            out.append(date(y, d.month, min(d.day, 28)).isoformat())
        except ValueError:
            continue
    return latest, out


def refresh_dates(client=None):
    """Latest dates of the map overlays / HLS layers (cheap: one capabilities request)."""
    own = client is None
    client = client or _client()
    try:
        dates = latest_dates(client)
    finally:
        if own:
            client.close()
    with tx() as con:
        for o in list(OVERLAYS.values()) + [{"layer": h} for h in HLS]:
            if o["layer"] in dates:
                con.execute("INSERT OR REPLACE INTO sat_meta(product, date, fetched_at) VALUES(?,?,datetime('now'))",
                            (f"overlay:{o['layer']}", dates[o["layer"]]))
    return dates


def refresh():
    """Blocking: fetch, decode and store every product for both grids. Returns a short status dict."""
    meta = json.load(open(SAT / "grids.json"))
    grids = [Grid(k, v) for k, v in meta.items()]
    status = {}
    with _client() as client:
        dates = refresh_dates(client)
        for key, p in PRODUCTS.items():
            latest = dates.get(p["layer"])
            if not latest:
                continue
            lut = colormap(p["cmap"], client)
            results = {}
            for g in grids:
                if key == "rain7":
                    d0 = date.fromisoformat(latest)
                    days = [(d0 - timedelta(days=k)).isoformat() for k in range(7)]
                    acc, n = None, 0
                    for day in days:
                        v = g.fetch(client, p["layer"], day, lut)
                        if v is None:
                            continue
                        z = g.zonal(v) * 24.0                       # mean mm/hr over the day -> mm/day
                        acc = z if acc is None else np.nansum(np.stack([acc, z]), axis=0)
                        n += 1
                    if acc is None:
                        continue
                    for uid, val in zip(g.m["ids"], acc):
                        if g.name == "az" or uid not in results:
                            results[uid] = (None if np.isnan(val) else float(val), None, n)
                    continue
                cur_date, normal_dates = (_ndvi_dates if key == "ndvi" else _smap_dates)(latest)
                cur = g.fetch(client, p["layer"], cur_date, lut)
                if cur is None:
                    continue
                now = g.zonal(cur)
                past = []
                for day in normal_dates:
                    v = g.fetch(client, p["layer"], day, lut)
                    if v is not None:
                        past.append(g.zonal(v))
                normal = np.nanmean(np.stack(past), axis=0) if past else np.full_like(now, np.nan)
                for uid, a, b in zip(g.m["ids"], now, normal):
                    if g.name == "az" or uid not in results:   # Azerbaijan: the finer 1 km grid wins
                        results[uid] = (None if np.isnan(a) else float(a), None if np.isnan(b) else float(b), len(past))
            with tx() as con:
                con.execute("DELETE FROM sat_obs WHERE product=?", (key,))
                con.executemany("INSERT INTO sat_obs(rayon_id, product, date, value, normal, n_normal) "
                                "VALUES(?,?,?,?,?,?)", [(u, key, latest, v[0], v[1], v[2]) for u, v in results.items()
                                                       if v[0] is not None])
                con.execute("INSERT OR REPLACE INTO sat_meta(product, date, fetched_at, units) "
                            "VALUES(?,?,datetime('now'),?)", (key, latest, sum(1 for v in results.values() if v[0] is not None)))
            status[key] = {"date": latest, "units": sum(1 for v in results.values() if v[0] is not None)}
            log.info("satellite %s %s: %s units", key, latest, status[key]["units"])
    return status


def stale(hours=20):
    con = connect()
    try:
        r = con.execute("SELECT min(fetched_at) FROM sat_meta WHERE product IN ('ndvi','smap','rain7')").fetchone()[0]
        n = con.execute("SELECT count(*) FROM sat_meta WHERE product IN ('ndvi','smap','rain7')").fetchone()[0]
    finally:
        con.close()
    if not r or n < 3:
        return True
    return time.time() - calendar.timegm(time.strptime(r, "%Y-%m-%d %H:%M:%S")) > hours * 3600   # sqlite now = UTC


async def loop(interval=6 * 3600):
    await asyncio.sleep(20)
    while True:
        try:
            if stale():
                await asyncio.to_thread(refresh)
            else:
                await asyncio.to_thread(refresh_dates)
        except Exception as e:  # noqa: BLE001
            log.warning("satellite refresh failed: %s", e)
        await asyncio.sleep(interval)


def for_unit(con, rid):
    out = {}
    for r in rows(con, "SELECT * FROM sat_obs WHERE rayon_id=?", rid):
        p = PRODUCTS[r["product"]]
        out[r["product"]] = {"date": r["date"], "value": r["value"], "normal": r["normal"], "n_normal": r["n_normal"],
                             "unit": p["unit"], "label": p["label"]}
    return out
