"""NASA NEX-GDDP-CMIP6 (0.25°, bias-corrected, SSP2-4.5) daily projections for every rayon centroid.

One THREDDS NCSS request per model/variable/year returns the whole Azerbaijan box; we keep only the
grid cell nearest each rayon. Output: data/raw/nex/<model>/<var>_<year>.npy, shape (n_rayons, days).
"""
import asyncio
import io
import json
import re
from pathlib import Path

import httpx
import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "nex"
BASE = "https://ds.nccs.nasa.gov/thredds"
MODELS = {"MRI-ESM2-0": "r1i1p1f1", "MPI-ESM1-2-HR": "r1i1p1f1", "ACCESS-CM2": "r1i1p1f1", "EC-Earth3": "r1i1p1f1",
          "GFDL-ESM4": "r1i1p1f1"}
VARS = ["tasmax", "tasmin", "pr"]
HIST = range(1995, 2015)   # IPCC AR6 baseline
FUT = range(2026, 2051)
BOX = "north=42.0&south=38.3&west=44.7&east=50.7"


async def filenames(client, model, scen, var):
    url = f"{BASE}/catalog/AMES/NEX/GDDP-CMIP6/{model}/{scen}/{MODELS[model]}/{var}/catalog.xml"
    r = await client.get(url, timeout=120)
    r.raise_for_status()
    names = re.findall(r'name="([^"]+\.nc)"', r.text)
    by_year = {}
    for n in names:
        y = int(re.search(r"_(\d{4})(?:_v[\d.]+)?\.nc$", n).group(1))
        if y not in by_year or "v2.0" in n:   # prefer the corrected v2.0 files
            by_year[y] = n
    return by_year


async def one(client, sem, model, scen, var, year, fname, idx):
    f = OUT / model / f"{var}_{year}.npy"
    if f.exists():
        return
    url = (f"{BASE}/ncss/grid/AMES/NEX/GDDP-CMIP6/{model}/{scen}/{MODELS[model]}/{var}/{fname}"
           f"?var={var}&{BOX}&horizStride=1&temporal=all&accept=netcdf")
    async with sem:
        for attempt in range(5):
            try:
                r = await client.get(url, timeout=300)
                r.raise_for_status()
                ds = netCDF4.Dataset("mem", memory=r.content)
                a = np.asarray(ds.variables[var][:], dtype="float32")   # (time, lat, lon)
                lat, lon = ds.variables["lat"][:], ds.variables["lon"][:]
                ds.close()
                if idx[0] is None:
                    idx[0] = (np.abs(lat[None, :] - np.array([p[0] for p in idx[1]])[:, None]).argmin(1),
                              np.abs(lon[None, :] - np.array([p[1] for p in idx[1]])[:, None]).argmin(1))
                iy, ix = idx[0]
                ser = a[:, iy, ix].T                                   # (rayon, time)
                ser = ser - 273.15 if var.startswith("tas") else ser * 86400.0
                f.parent.mkdir(parents=True, exist_ok=True)
                np.save(f, ser.astype("float32"))
                return
            except Exception as e:  # noqa: BLE001
                print("retry", model, var, year, attempt, repr(e)[:100], flush=True)
                await asyncio.sleep(5 * (attempt + 1))


async def main():
    rayons = json.load(open(ROOT / "data" / "rayons.json"))
    pts = [(r["lat"], r["lon"]) for r in rayons]
    (OUT).mkdir(parents=True, exist_ok=True)
    json.dump([r["id"] for r in rayons], open(OUT / "rayons.json", "w"))
    sem = asyncio.Semaphore(16)
    async with httpx.AsyncClient() as client:
        jobs = []
        for model in MODELS:
            idx = [None, pts]
            for var in VARS:
                hist = await filenames(client, model, "historical", var)
                fut = await filenames(client, model, "ssp245", var)
                for y in HIST:
                    jobs.append(one(client, sem, model, "historical", var, y, hist[y], idx))
                for y in FUT:
                    jobs.append(one(client, sem, model, "ssp245", var, y, fut[y], idx))
        done = 0
        for fut_ in asyncio.as_completed(jobs):
            await fut_
            done += 1
            if done % 25 == 0:
                print(f"{done}/{len(jobs)}", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
