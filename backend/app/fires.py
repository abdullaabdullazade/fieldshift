"""Active fires from NASA FIRMS (VIIRS 375 m on NOAA-20 / NOAA-21 / Suomi NPP and MODIS 1 km), last 24 hours.

FIRMS publishes the global 24-hour detections as open CSV files (no key needed), a few hours after each pass.
They are reloaded every 3 hours into the `fires` table; low-confidence detections are dropped.
Used by the map (points), the district / province page (fires nearby) and farm alerts (fire within 10 km).

Gas flares, refineries and steel works show up as "fires" every day. Each ~1 km cell remembers the days it had a
detection (fire_cells, last 10 days); a point whose cell burned on 3 or more days is marked persistent (days >= 3),
shown as "likely industrial" and never alerted.
"""
import asyncio
import csv
import io
import logging
import math

import httpx

from .db import connect, rows, tx

log = logging.getLogger("fires")
BASE = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/"
FEEDS = {
    "VIIRS NOAA-20": "noaa-20-viirs-c2/csv/J1_VIIRS_C2_Global_24h.csv",
    "VIIRS NOAA-21": "noaa-21-viirs-c2/csv/J2_VIIRS_C2_Global_24h.csv",
    "VIIRS S-NPP": "suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_Global_24h.csv",
    "MODIS": "modis-c6.1/csv/MODIS_C6_1_Global_24h.csv",
}


def _keep(sat, conf):
    if sat == "MODIS":
        try:
            return int(conf) >= 50
        except ValueError:
            return False
    return conf not in ("l", "low")


SEED = "noaa-20-viirs-c2/csv/J1_VIIRS_C2_Global_7d.csv"


def _seed(c):
    """First run only: learn persistent hot spots from the 7-day NOAA-20 file (cells only, ~20 MB download)."""
    con = connect()
    try:
        if con.execute("SELECT 1 FROM fire_cells LIMIT 1").fetchone():
            return
    finally:
        con.close()
    r = c.get(BASE + SEED, timeout=600)
    r.raise_for_status()
    cells = {(f"{float(d['latitude']):.2f},{float(d['longitude']):.2f}", d["acq_date"])
             for d in csv.DictReader(io.StringIO(r.text)) if _keep("VIIRS", d.get("confidence", ""))}
    with tx() as con:
        con.executemany("INSERT OR IGNORE INTO fire_cells VALUES(?,?)", cells)
    log.info("FIRMS: seeded %d cell-days from the 7-day file", len(cells))


def refresh():
    """Blocking: download every feed and replace the table. Returns {feed: rows kept}."""
    out, status = [], {}
    with httpx.Client(timeout=120, headers={"User-Agent": "FieldShift/1.0 (NASA Space Apps 2026)"}) as c:
        try:
            _seed(c)
        except Exception as e:  # noqa: BLE001 - seeding only improves flare detection
            log.warning("FIRMS seed failed: %s", e)
        for sat, path in FEEDS.items():
            try:
                r = c.get(BASE + path)
                r.raise_for_status()
            except httpx.HTTPError as e:
                log.warning("FIRMS %s failed: %s", sat, e)
                status[sat] = None
                continue
            n = 0
            for d in csv.DictReader(io.StringIO(r.text)):
                conf = d.get("confidence", "")
                if not _keep(sat, conf):
                    continue
                t = d.get("acq_time", "0000").zfill(4)
                out.append((float(d["latitude"]), float(d["longitude"]), f"{d['acq_date']}T{t[:2]}:{t[2:]}:00Z", sat,
                            {"n": "nominal", "h": "high"}.get(conf, conf), float(d.get("frp") or 0), d.get("daynight")))
                n += 1
            status[sat] = n
    if not any(status.values()):
        raise RuntimeError("no FIRMS feed could be read")
    cell = lambda la, lo: f"{la:.2f},{lo:.2f}"   # noqa: E731
    with tx() as con:
        con.executemany("INSERT OR IGNORE INTO fire_cells VALUES(?,?)", {(cell(f[0], f[1]), f[2][:10]) for f in out})
        con.execute("DELETE FROM fire_cells WHERE day < date('now', '-10 day')")
        seen = {}
        for c, n in con.execute("SELECT cell, count(*) FROM fire_cells GROUP BY cell"):
            seen[c] = n
        con.execute("DROP TABLE IF EXISTS fires")
        con.execute("CREATE TABLE fires(lat REAL, lon REAL, acq TEXT, sat TEXT, conf TEXT, frp REAL, dn TEXT, days INTEGER)")
        con.execute("CREATE INDEX fires_ll ON fires(lat, lon)")
        con.executemany("INSERT INTO fires VALUES(?,?,?,?,?,?,?,?)", [f + (seen.get(cell(f[0], f[1]), 1),) for f in out])
        con.execute("INSERT OR REPLACE INTO sat_meta(product, date, fetched_at) VALUES('fires', ?, datetime('now'))",
                    (max((f[2] for f in out), default=None),))
    return status


def km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))


def near(con, lat, lon, radius_km):
    """Fires within radius_km of a point, nearest first (bounding-box prefilter on the lat/lon index)."""
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * max(math.cos(lat * math.pi / 180), 0.05))
    cand = rows(con, "SELECT * FROM fires WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?",
                lat - dlat, lat + dlat, lon - dlon, lon + dlon)
    for f in cand:
        f["km"] = round(km(lat, lon, f["lat"], f["lon"]), 1)
    return sorted((f for f in cand if f["km"] <= radius_km), key=lambda f: f["km"])


def for_unit(con, r):
    """Fires within the district / province (approximated by a circle of its area around the centre + 5 km)."""
    radius = math.sqrt((r.get("area_km2") or 1000) / math.pi) + 5
    fs = near(con, r["lat"], r["lon"], radius)
    meta = con.execute("SELECT date, fetched_at FROM sat_meta WHERE product='fires'").fetchone()
    ind = [f for f in fs if f["days"] >= 3]
    fs = [f for f in fs if f["days"] < 3]
    return {"count": len(fs), "industrial": len(ind), "radius_km": round(radius), "nearest_km": fs[0]["km"] if fs else None,
            "max_frp": max((f["frp"] for f in fs), default=None), "latest": meta["date"] if meta else None,
            "fetched_at": meta["fetched_at"] if meta else None, "points": [
                {k: f[k] for k in ("lat", "lon", "acq", "sat", "conf", "frp", "km", "days")} for f in fs[:50]]}


def stale(hours=2.5):
    con = connect()
    try:
        r = con.execute("SELECT (julianday('now') - julianday(fetched_at)) * 24 FROM sat_meta WHERE product='fires'").fetchone()
    finally:
        con.close()
    return not r or r[0] is None or r[0] > hours


async def loop(interval=3 * 3600):
    await asyncio.sleep(30)
    while True:
        try:
            if stale():
                log.info("FIRMS refresh: %s", await asyncio.to_thread(refresh))
        except Exception as e:  # noqa: BLE001
            log.warning("FIRMS refresh failed: %s", e)
        await asyncio.sleep(interval if not stale() else 600)
