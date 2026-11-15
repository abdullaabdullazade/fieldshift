"""SoilGrids 2.0 (ISRIC, CC BY 4.0) topsoil properties, zonal mean per rayon polygon.

Downloads 0-5/5-15/15-30 cm mean coverages over Azerbaijan via WCS (~1 km), averages to 0-30 cm
weighted by layer thickness, then takes the mean over each rayon shape. Writes data/soil.json.
"""
import json
from pathlib import Path

import httpx
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from shapely.geometry import Point, shape

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "soil"
BBOX = (44.7, 38.3, 50.7, 42.0)
# property -> divisor to convert mapped units (SoilGrids conventions)
PROPS = {"phh2o": 10, "clay": 10, "sand": 10, "silt": 10, "soc": 10, "nitrogen": 100, "cec": 10}
DEPTHS = {"0-5cm": 5, "5-15cm": 10, "15-30cm": 15}


def fetch(prop, depth):
    f = OUT / f"{prop}_{depth}.tif"
    if f.exists() and f.stat().st_size > 1000:
        return f
    url = (f"https://maps.isric.org/mapserv?map=/map/{prop}.map&SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage"
           f"&COVERAGEID={prop}_{depth}_mean&FORMAT=image/tiff"
           f"&SUBSET=long({BBOX[0]},{BBOX[2]})&SUBSET=lat({BBOX[1]},{BBOX[3]})"
           "&SUBSETTINGCRS=http://www.opengis.net/def/crs/EPSG/0/4326"
           "&OUTPUTCRS=http://www.opengis.net/def/crs/EPSG/0/4326&SCALEFACTOR=0.25")
    r = httpx.get(url, timeout=300)
    r.raise_for_status()
    f.write_bytes(r.content)
    print("got", f.name, len(r.content), flush=True)
    return f


def texture(clay, sand, silt):
    """USDA texture class (simplified triangle)."""
    if clay >= 40:
        return "Clay" if silt < 40 else "Silty clay"
    if clay >= 27:
        return "Clay loam" if sand < 45 else "Sandy clay loam"
    if silt >= 50:
        return "Silt loam"
    if sand >= 70:
        return "Sandy"
    return "Loam"


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    feats = {f["properties"]["id"]: shape(f["geometry"])
             for f in json.load(open(ROOT / "data" / "regions.geojson"))["features"]}
    rayons = json.load(open(ROOT / "data" / "rayons.json"))
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
    out = {}
    for r in rayons:
        g = feats.get(r["id"]) or Point(r["lon"], r["lat"]).buffer(0.05)
        mask = ~geometry_mask([g.__geo_interface__], out_shape=shp, transform=transform, all_touched=True)
        vals = {p: float(np.nanmean(grids[p][mask])) for p in PROPS}
        vals = {k: round(v, 2) for k, v in vals.items()}
        vals["texture"] = texture(vals["clay"], vals["sand"], vals["silt"])
        out[r["id"]] = vals
    json.dump(out, open(ROOT / "data" / "soil.json", "w"), ensure_ascii=False, indent=1)
    return out


if __name__ == "__main__":
    o = build()
    print(len(o), o.get("berde"), o.get("lenkeran"))
