"""SoilGrids 2.0 topsoil (0-30 cm) zonal means for every world province.

Global WCS coverages at ~6 km (SCALEFACTOR 0.04), provinces rasterised once into a label grid, means via bincount.
Provinces smaller than one pixel fall back to the pixel under their representative point.
Output: data/world_soil.json {unit_id: {phh2o, clay, sand, silt, soc, nitrogen, cec, texture}}
"""
import json
from pathlib import Path

import httpx
import numpy as np
import rasterio
from rasterio.features import rasterize
from shapely.geometry import shape

from etl.soil import DEPTHS, PROPS, texture

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "soil_world"


def fetch(prop, depth):
    f = OUT / f"{prop}_{depth}.tif"
    if f.exists() and f.stat().st_size > 100_000:
        return f
    url = (f"https://maps.isric.org/mapserv?map=/map/{prop}.map&SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage"
           f"&COVERAGEID={prop}_{depth}_mean&FORMAT=image/tiff&SUBSET=long(-180,180)&SUBSET=lat(-60,80)"
           "&SUBSETTINGCRS=http://www.opengis.net/def/crs/EPSG/0/4326"
           "&OUTPUTCRS=http://www.opengis.net/def/crs/EPSG/0/4326&SCALEFACTOR=0.04")
    for attempt in range(4):
        try:
            r = httpx.get(url, timeout=900)
            r.raise_for_status()
            f.write_bytes(r.content)
            print("got", f.name, len(r.content), flush=True)
            return f
        except Exception as e:  # noqa: BLE001
            print("retry", f.name, attempt, repr(e)[:90], flush=True)
    raise RuntimeError(f"failed {f.name}")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    units = json.load(open(ROOT / "data" / "world_units.json"))
    idx = {u["id"]: i + 1 for i, u in enumerate(units)}
    shapes = []
    for iso in sorted({u["iso3"] for u in units}):
        for ft in json.load(open(ROOT / "data" / "geo" / f"{iso}.geojson"))["features"]:
            if ft["properties"]["id"] in idx:
                shapes.append((ft["geometry"], idx[ft["properties"]["id"]]))
    grids, transform, shp = {}, None, None
    for prop, div in PROPS.items():
        acc = None
        for depth, w in DEPTHS.items():
            with rasterio.open(fetch(prop, depth)) as src:
                a = src.read(1).astype("float64")
                a[a <= 0] = np.nan
                transform, shp = src.transform, a.shape
            acc = a * w if acc is None else acc + a * w
        grids[prop] = acc / sum(DEPTHS.values()) / div
    labels = rasterize(shapes, out_shape=shp, transform=transform, fill=0, dtype="int32", all_touched=True)
    n = len(units) + 1
    out = {}
    means = {}
    for prop, g in grids.items():
        ok = ~np.isnan(g) & (labels > 0)
        s = np.bincount(labels[ok], weights=g[ok], minlength=n)
        c = np.bincount(labels[ok], minlength=n)
        means[prop] = (s, c)
    inv = ~transform
    for u in units:
        i = idx[u["id"]]
        vals = {}
        for prop in PROPS:
            s, c = means[prop]
            if c[i] > 0:
                vals[prop] = round(float(s[i] / c[i]), 2)
            else:  # tiny province: nearest pixel / small window around the point
                col, row = (int(v) for v in inv * (u["lon"], u["lat"]))
                win = grids[prop][max(0, row - 2):row + 3, max(0, col - 2):col + 3]
                v = np.nanmean(win) if win.size and not np.isnan(win).all() else np.nan
                vals[prop] = None if np.isnan(v) else round(float(v), 2)
        if vals["clay"] is not None and vals["sand"] is not None and vals["silt"] is not None:
            vals["texture"] = texture(vals["clay"], vals["sand"], vals["silt"])
        else:
            vals["texture"] = None
        out[u["id"]] = vals
    json.dump(out, open(ROOT / "data" / "world_soil.json", "w"))
    print(len(out), "provinces;", sum(1 for v in out.values() if v["phh2o"] is None), "without soil data")


if __name__ == "__main__":
    main()
