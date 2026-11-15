"""Label grids that map satellite-image pixels to districts / provinces (built locally, shipped with the app).

az:    Azerbaijan districts on a 0.01° grid (lat 38.3-42.0, lon 44.7-50.7)  -> ~1 km pixels
world: every province (and Azerbaijan's districts) on a 0.1° grid (lat -60..80, lon -180..180)
Writes data/sat/labels_<grid>.npy (int16, 0 = none), data/sat/grids.json (bbox, size, unit ids, fallback pixels).
"""
import json
from pathlib import Path

import numpy as np
from rasterio.features import rasterize
from rasterio.transform import from_bounds
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "sat"
GRIDS = {"az": {"bbox": [38.3, 44.7, 42.0, 50.7], "res": 0.01},      # S, W, N, E
         "world": {"bbox": [-60.0, -180.0, 80.0, 180.0], "res": 0.1}}


def build(name, units):
    """units: list of (id, geometry or None, lat, lon)."""
    s, w, n, e = GRIDS[name]["bbox"]
    res = GRIDS[name]["res"]
    W, H = round((e - w) / res), round((n - s) / res)
    tr = from_bounds(w, s, e, n, W, H)
    ids = [u[0] for u in units]
    shapes = [(u[1], i + 1) for i, u in enumerate(units) if u[1] is not None]
    lab = rasterize(shapes, out_shape=(H, W), transform=tr, fill=0, dtype="int32", all_touched=False)
    counts = np.bincount(lab.ravel(), minlength=len(ids) + 1)
    fallback = {}
    for i, u in enumerate(units):       # units too small for a pixel: use the pixel under their point
        if counts[i + 1] == 0:
            col, row = (int(v) for v in ~tr * (u[3], u[2]))
            if 0 <= row < H and 0 <= col < W:
                fallback[u[0]] = [row, col]
    np.save(OUT / f"labels_{name}.npy", lab.astype("int16"))
    return {"bbox": [s, w, n, e], "width": W, "height": H, "ids": ids, "fallback": fallback}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rayons = json.load(open(ROOT / "data" / "rayons.json"))
    az_geom = {f["properties"]["id"]: shape(f["geometry"])
               for f in json.load(open(ROOT / "data" / "regions.geojson"))["features"]}
    az_units = [(r["id"], az_geom.get(r["id"]), r["lat"], r["lon"]) for r in rayons]
    world_units = list(az_units)
    for u in json.load(open(ROOT / "data" / "world_units.json")):
        world_units.append((u["id"], None, u["lat"], u["lon"]))
    geoms = {}
    for iso in sorted({u["iso3"] for u in json.load(open(ROOT / "data" / "world_units.json"))}):
        for ft in json.load(open(ROOT / "data" / "geo" / f"{iso}.geojson"))["features"]:
            geoms[ft["properties"]["id"]] = shape(ft["geometry"])
    world_units = [(i, g if g is not None else geoms.get(i), la, lo) for i, g, la, lo in world_units]
    meta = {"az": build("az", az_units), "world": build("world", world_units)}
    json.dump(meta, open(OUT / "grids.json", "w"))
    for k, v in meta.items():
        print(k, v["width"], "x", v["height"], len(v["ids"]), "units,", len(v["fallback"]), "point fallbacks")


if __name__ == "__main__":
    main()
