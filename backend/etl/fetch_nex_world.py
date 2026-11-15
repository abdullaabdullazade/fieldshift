"""NASA NEX-GDDP-CMIP6 for every world province: one global request per model/variable/year (2° stride,
NetCDF4-compressed, ~5 MB), sampled at the nearest land cell to each province point.
Output: data/raw/nex_world/<model>/<var>_<year>.npy, shape (n_units, days), same layout as etl.fetch_nex.
"""
import asyncio
import json
from pathlib import Path

import httpx
import netCDF4
import numpy as np

from etl.fetch_nex import BASE, FUT, HIST, MODELS, VARS, filenames

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "nex_world"
STRIDE = 8          # 0.25° * 8 = 2°
BOX = "north=80&south=-60&west=-180&east=180"


def nearest_land(lat, lon, valid, plat, plon):
    """Index (iy, ix) of the nearest valid (land) cell for each point."""
    yy, xx = np.nonzero(valid)
    vl, vo = lat[yy], lon[xx]
    out = []
    for a, b in zip(plat, plon):
        dlon = np.abs(((vo - b) + 180) % 360 - 180) * np.cos(np.radians(a))
        k = np.argmin((vl - a) ** 2 + dlon ** 2)
        out.append((yy[k], xx[k]))
    return np.array([o[0] for o in out]), np.array([o[1] for o in out])


async def one(client, sem, model, scen, var, year, fname, state):
    f = OUT / model / f"{var}_{year}.npy"
    if f.exists():
        return
    url = (f"{BASE}/ncss/grid/AMES/NEX/GDDP-CMIP6/{model}/{scen}/{MODELS[model]}/{var}/{fname}"
           f"?var={var}&{BOX}&horizStride={STRIDE}&temporal=all&accept=netcdf4")
    async with sem:
        for attempt in range(6):
            try:
                r = await client.get(url, timeout=600)
                r.raise_for_status()
                ds = netCDF4.Dataset("mem", memory=r.content)
                a = np.ma.filled(ds.variables[var][:].astype("float32"), np.nan)   # (time, lat, lon)
                lat, lon = np.asarray(ds.variables["lat"][:]), np.asarray(ds.variables["lon"][:])
                ds.close()
                lon = np.where(lon > 180, lon - 360, lon)
                if state.get("idx") is None:
                    state["idx"] = nearest_land(lat, lon, ~np.isnan(a[0]), state["lat"], state["lon"])
                iy, ix = state["idx"]
                ser = a[:, iy, ix].T
                ser = ser - 273.15 if var.startswith("tas") else ser * 86400.0
                f.parent.mkdir(parents=True, exist_ok=True)
                np.save(f, ser.astype("float32"))
                return
            except Exception as e:  # noqa: BLE001
                print("retry", model, var, year, attempt, repr(e)[:100], flush=True)
                await asyncio.sleep(10 * (attempt + 1))


async def main():
    units = json.load(open(ROOT / "data" / "world_units.json"))
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump([u["id"] for u in units], open(OUT / "rayons.json", "w"))
    state = {"lat": np.array([u["lat"] for u in units]), "lon": np.array([u["lon"] for u in units]), "idx": None}
    sem = asyncio.Semaphore(12)
    async with httpx.AsyncClient() as client:
        jobs = []
        for model in MODELS:
            for var in VARS:
                hist = await filenames(client, model, "historical", var)
                fut = await filenames(client, model, "ssp245", var)
                jobs += [(model, "historical", var, y, hist[y]) for y in HIST]
                jobs += [(model, "ssp245", var, y, fut[y]) for y in FUT]
        # first file alone, so the land-cell index is computed once
        await one(client, sem, *jobs[0], state)
        if state["idx"] is None:
            f0 = OUT / jobs[0][0] / f"{jobs[0][2]}_{jobs[0][3]}.npy"
            r = await client.get(f"{BASE}/ncss/grid/AMES/NEX/GDDP-CMIP6/{jobs[0][0]}/{jobs[0][1]}/{MODELS[jobs[0][0]]}/"
                                 f"{jobs[0][2]}/{jobs[0][4]}?var={jobs[0][2]}&{BOX}&horizStride={STRIDE}"
                                 f"&temporal=all&accept=netcdf4", timeout=600)
            ds = netCDF4.Dataset("mem", memory=r.content)
            a = np.ma.filled(ds.variables[jobs[0][2]][0].astype("float32"), np.nan)
            lat, lon = np.asarray(ds.variables["lat"][:]), np.asarray(ds.variables["lon"][:])
            lon = np.where(lon > 180, lon - 360, lon)
            state["idx"] = nearest_land(lat, lon, ~np.isnan(a), state["lat"], state["lon"])
            print("index from", f0.name, flush=True)
        done = 0
        tasks = [asyncio.create_task(one(client, sem, *j, state)) for j in jobs[1:]]
        for t in asyncio.as_completed(tasks):
            await t
            done += 1
            if done % 25 == 0:
                print(f"{done}/{len(tasks)}", flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
