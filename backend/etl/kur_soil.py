"""Soil salinity trend around every village on the lower Kür, 2021–2025, from Landsat 8/9 (NASA/USGS, 30 m).

After harvest (15 Aug – 31 Oct) many fields lie bare and salt shows on the surface as a bright crust. For every year
the clearest scenes of the zone are read (Landsat Collection 2 Level-2 surface reflectance, via the Microsoft Planetary
Computer STAC, no login), and for bare land pixels (NDVI < 0.2, not water, clear sky) the salinity index
SI = sqrt(blue · red) (Khan et al. 2005) is averaged inside 2.5 km of each village, together with the share of
"crust" pixels (SI above the zone's 2021 90th percentile). This is an indicator of surface salt, not a measurement:
farmers' EC readings remain the ground truth.

Output data/kur/soil.json: per village yearly SI, crust share and the 5-year trend.
"""
import json
import math
import sys
from pathlib import Path

import httpx
import numpy as np
import rasterio
from rasterio.warp import transform, transform_bounds
from rasterio.windows import from_bounds

ROOT = Path(__file__).resolve().parents[2]
ZONE = (48.85, 39.2, 49.45, 40.0)            # lon/lat box of the Kür below the Araz confluence
YEARS = [2021, 2022, 2023, 2024, 2025]
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
TOKEN = "https://planetarycomputer.microsoft.com/api/sas/v1/token/landsat-c2-l2"
R_KM = 2.5
CACHE = ROOT / "data" / "raw" / "kur" / "landsat"
SCALE, OFFSET = 0.0000275, -0.2


def scenes(c, year):
    r = c.post(STAC, json={"collections": ["landsat-c2-l2"], "bbox": list(ZONE), "limit": 50,
                            "datetime": f"{year}-08-15/{year}-10-31",
                            "query": {"eo:cloud_cover": {"lt": 10}, "platform": {"in": ["landsat-8", "landsat-9"]},
                                      "landsat:collection_category": {"eq": "T1"}}})
    r.raise_for_status()
    feats = sorted(r.json()["features"], key=lambda f: f["properties"]["eo:cloud_cover"])
    picked, per_tile = [], {}
    for f in feats:                      # up to 3 scenes per WRS tile
        tile = f["properties"].get("landsat:wrs_path", "") + f["properties"].get("landsat:wrs_row", "")
        if per_tile.get(tile, 0) < 3:
            per_tile[tile] = per_tile.get(tile, 0) + 1
            picked.append(f)
    return picked


def read(href, token, bounds_utm, shape=None):
    with rasterio.open(f"{href}?{token}") as src:
        w = from_bounds(*bounds_utm, src.transform)
        a = src.read(1, window=w, out_shape=shape, boundless=True, fill_value=0)
        return a, src.window_transform(w), src.crs


def main():
    villages = json.load(open(ROOT / "data" / "kur" / "villages.json"))
    CACHE.mkdir(parents=True, exist_ok=True)
    tok = httpx.get(TOKEN, timeout=60).json()["token"]
    env = rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MULTIRANGE="YES", GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES",
                       CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".TIF,.tif", VSI_CACHE="TRUE")
    per_year = {}
    with env, httpx.Client(timeout=120) as c:
        for y in YEARS:
            stack, grid = [], None
            for f in scenes(c, y):
                a = f["assets"]
                with rasterio.open(f"{a['red']['href']}?{tok}") as src:
                    crs = src.crs
                bu = transform_bounds("EPSG:4326", crs, *ZONE)
                if grid is None or grid["crs"] != crs:
                    if grid is not None:
                        continue                  # keep one UTM zone per year (all tiles here are UTM 39N)
                    grid = {"crs": crs, "bounds": bu}
                red, tr, _ = read(a["red"]["href"], tok, grid["bounds"])
                shape = red.shape
                blue = read(a["blue"]["href"], tok, grid["bounds"], shape)[0]
                nir = read(a["nir08"]["href"], tok, grid["bounds"], shape)[0]
                green = read(a["green"]["href"], tok, grid["bounds"], shape)[0]
                qa = read(a["qa_pixel"]["href"], tok, grid["bounds"], shape)[0]
                grid["transform"], grid["shape"] = tr, shape
                ref = lambda x: x.astype("float32") * SCALE + OFFSET                     # noqa: E731
                R, B, N, G = ref(red), ref(blue), ref(nir), ref(green)
                clear = (qa & 0b11111) == 0          # fill, dilated cloud, cirrus, cloud, shadow bits all off
                clear &= ((qa >> 7) & 1) == 0        # not water
                ndvi = (N - R) / (N + R + 1e-6)
                ndwi = (G - N) / (G + N + 1e-6)
                ok = clear & (red > 0) & (ndvi < 0.2) & (ndwi < 0) & (R > 0) & (B > 0)
                si = np.where(ok, np.sqrt(np.clip(B, 0, 1) * np.clip(R, 0, 1)), np.nan)
                stack.append(si)
                print(y, f["id"], f["properties"]["eo:cloud_cover"], "bare px", int(ok.sum()), flush=True)
            if not stack:
                continue
            comp = np.nanmedian(np.stack(stack), axis=0)
            np.save(CACHE / f"si_{y}.npy", comp)
            json.dump({"crs": str(grid["crs"]), "transform": list(grid["transform"])[:6], "shape": list(grid["shape"])},
                      open(CACHE / f"si_{y}.json", "w"))
            per_year[y] = {"si": comp, **grid}

    # every year is compared with the zone itself, so haze, sensor and illumination differences between years cancel out
    zone = {y: (float(np.nanmedian(g["si"])), float(np.nanpercentile(g["si"], 90))) for y, g in per_year.items()}
    crust_thr = None
    out = []
    for v in villages:
        rec = {"name": v["name"], "km": v["km"], "years": {}}
        for y, g in per_year.items():
            xs, ys = transform("EPSG:4326", g["crs"], [v["lon"]], [v["lat"]])
            inv = ~g["transform"]
            col, row = inv * (xs[0], ys[0])
            rpx = R_KM * 1000 / 30
            r0, r1 = int(max(0, row - rpx)), int(min(g["shape"][0], row + rpx))
            c0, c1 = int(max(0, col - rpx)), int(min(g["shape"][1], col + rpx))
            win = g["si"][r0:r1, c0:c1]
            if win.size == 0:
                continue
            yy, xx = np.mgrid[r0:r1, c0:c1]
            win = np.where((yy - row) ** 2 + (xx - col) ** 2 <= rpx ** 2, win, np.nan)
            n = int(np.isfinite(win).sum())
            if n < 200:
                continue
            med, p90 = zone[y]
            vals = win[np.isfinite(win)]
            rec["years"][str(y)] = {"ratio": round(float(np.mean(vals)) / med, 3), "crust": round(float(np.mean(vals > p90)) * 100, 1), "n": n}
        ys_ = sorted(rec["years"])
        if len(ys_) >= 3:
            t = np.array([int(k) for k in ys_]); s = np.array([rec["years"][k]["ratio"] for k in ys_])
            slope = float(np.polyfit(t, s, 1)[0])          # change of the village/zone salinity ratio per year
            rec["trend_per_year"] = round(slope, 3)
            rec["now_ratio"] = rec["years"][ys_[-1]]["ratio"]
            rec["trend"] = "up" if slope >= 0.03 else "down" if slope <= -0.03 else "flat"
        out.append(rec)
    res = {"years": YEARS, "zone": {str(k): {"median": round(a, 4), "p90": round(b, 4)} for k, (a, b) in zone.items()},
           "radius_km": R_KM, "villages": out,
           "method": "Landsat 8/9 C2 L2 T1, 15 Aug–31 Oct, cloud < 10 %, bare land (NDVI<0.2), SI = sqrt(blue*red); "
                     "village mean / zone median per year; trend = slope of that ratio (≥ 0.03 / yr = getting saltier)"}
    (ROOT / "data" / "kur" / "soil.json").write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")))
    ups = [(r["name"], r["trend_per_year"]) for r in out if r.get("trend") == "up"]
    print("villages", len(out), "| rising salt crust:", ups)


if __name__ == "__main__":
    sys.exit(main())
