"""Pick an agriculturally representative point for each world province.

A polygon's representative point often lands on a mountain range (e.g. the Taurus for Antalya), which says little
about where crops grow. For every province we sample up to 25 candidate points inside the polygon, look up their
elevation (NOAA ETOPO1, 4' grid) and choose the candidate closest to the 20th-percentile
elevation: farmland is concentrated in lowlands and valleys. Provinces whose point moves by more than 300 m of
elevation get their cached NASA POWER file deleted so etl.world_power fetches the new location.
Updates data/world_units.json in place (adds elev, elev_old, moved).
"""
import json
import time
from pathlib import Path

import httpx
import numpy as np
from shapely.geometry import Point, shape
from shapely.prepared import prep

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "raw" / "elev_cache.json"


def candidates(geom, rep, n=5):
    minx, miny, maxx, maxy = geom.bounds
    pg = prep(geom)
    pts = [(rep.y, rep.x)]
    for gy in np.linspace(miny, maxy, n + 2)[1:-1]:
        for gx in np.linspace(minx, maxx, n + 2)[1:-1]:
            if pg.contains(Point(gx, gy)):
                pts.append((round(gy, 4), round(gx, 4)))
    if len(pts) < 6:   # thin / small shapes: denser grid
        for gy in np.linspace(miny, maxy, 9)[1:-1]:
            for gx in np.linspace(minx, maxx, 9)[1:-1]:
                if pg.contains(Point(gx, gy)):
                    pts.append((round(gy, 4), round(gx, 4)))
    return pts[:25]


def elevations(coords, cache=None):
    """Sample NOAA ETOPO1 (4-arc-minute subset from ERDDAP, cached in data/raw/dem) at each point."""
    import netCDF4
    f = ROOT / "data" / "raw" / "dem" / "etopo_4m.nc"
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        r = httpx.get("https://upwell.pfeg.noaa.gov/erddap/griddap/etopo180.nc?"
                      "altitude%5B(-60):4:(84)%5D%5B(-180):4:(180)%5D", timeout=900)
        r.raise_for_status()
        f.write_bytes(r.content)
    d = netCDF4.Dataset(f)
    alt = np.asarray(d.variables["altitude"][:], dtype="float32")
    lat, lon = np.asarray(d.variables["latitude"][:]), np.asarray(d.variables["longitude"][:])
    d.close()
    ys = np.clip(np.searchsorted(lat, [c[0] for c in coords]), 0, len(lat) - 1)
    xs = np.clip(np.searchsorted(lon, [c[1] for c in coords]), 0, len(lon) - 1)
    return [float(v) for v in alt[ys, xs]]


def main():
    units = json.load(open(ROOT / "data" / "world_units.json"))
    geoms = {}
    for iso in sorted({u["iso3"] for u in units}):
        for ft in json.load(open(ROOT / "data" / "geo" / f"{iso}.geojson"))["features"]:
            geoms[ft["properties"]["id"]] = shape(ft["geometry"])
    cand = {u["id"]: candidates(geoms[u["id"]], Point(u["lon"], u["lat"])) for u in units if u["id"] in geoms}
    flat = [c for v in cand.values() for c in v]
    print(len(flat), "candidate points", flush=True)
    elev = dict(zip(map(tuple, flat), elevations(flat)))
    moved = 0
    for u in units:
        pts = cand.get(u["id"])
        if not pts:
            continue
        es = [(p, elev.get(tuple(p))) for p in pts]
        es = [(p, e) for p, e in es if e is not None and e > -50]   # drop sea / bathymetry cells
        if not es:
            continue
        rep_e = es[0][1] if tuple(es[0][0]) == tuple(pts[0]) else None
        target = float(np.percentile([e for _, e in es], 20))
        u["farm_elev"] = round(target)
        best = min(es, key=lambda pe: abs(pe[1] - target))
        u["elev_old"] = rep_e
        if rep_e is not None and abs(rep_e - best[1]) > 300:
            if (u["lat"], u["lon"]) != tuple(best[0]):
                f = ROOT / "data" / "raw" / "power_world" / f"{u['id']}.json"
                if f.exists():
                    f.unlink()
            u["lat"], u["lon"], u["elev"], u["moved"] = best[0][0], best[0][1], best[1], True
            moved += 1
        else:
            u["elev"], u["moved"] = rep_e, False
    json.dump(units, open(ROOT / "data" / "world_units.json", "w"))
    print(f"moved {moved}/{len(units)} province points to farmland elevation", flush=True)


if __name__ == "__main__":
    main()


def farm_elevation(geom, rep):
    """20th-percentile elevation of candidate points inside a polygon: the 'farmland elevation' temperatures are
    lapse-rate corrected to (used for Azerbaijan's districts, whose NASA POWER points stay where they are)."""
    pts = candidates(geom, rep)
    es = [e for e in elevations(pts) if e > -50]
    return round(float(np.percentile(es, 20))) if es else None
