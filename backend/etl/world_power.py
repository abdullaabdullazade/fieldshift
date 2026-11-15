"""NASA POWER daily (1981-today) for every world province point, aggregated on arrival.

Raw daily JSON would be ~6.5 GB for 3,270 points, so each response is reduced immediately to:
  annual rows (same columns as climate_year) + monthly climatologies 1981-2010, 2016-2025, 1995-2014.
Southern hemisphere: frost dates, growing season and GDD use a season calendar shifted by six months.
Temperatures are corrected from the ~50 km MERRA-2 cell elevation to the point elevation (6.5 °C/km), otherwise
foothill valleys next to mountains (e.g. Almaty: cell 2,478 m, city 768 m) come out ~10 °C too cold.
Output: data/raw/power_world/<unit id>.json   (Near Azerbaijan countries are fetched first).
"""
import asyncio
import json
from datetime import date, timedelta
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "power_world"
URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMS = "T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,GWETROOT,GWETTOP,RH2M,ALLSKY_SFC_SW_DWN"
PERIODS = {"1981-2010": (1981, 2010), "2016-2025": (2016, 2025), "1995-2014": (1995, 2014)}


def nz(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), 3)


LAPSE = 0.0065   # °C per metre (standard environmental lapse rate)


def aggregate(P, lat, last_full, dz=0.0):
    """dz = MERRA-2 cell elevation - point elevation; temperatures are lapse-rate corrected to the point."""
    df = pd.DataFrame({k: pd.Series(v) for k, v in P.items()})
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df = df.replace(-999.0, np.nan)
    for col in ("T2M", "T2M_MAX", "T2M_MIN"):
        df[col] = df[col] + LAPSE * dz
    south = lat < 0
    # season frame: in the southern hemisphere shift dates by +182 days so "Apr-Sep" means the local growing season
    sf = df.copy()
    if south:
        sf.index = sf.index + pd.Timedelta(days=182)
    years = []
    for y, d in df.groupby(df.index.year):
        if len(d) < 300 and y != last_full + 1:
            continue
        s = sf[sf.index.year == y]
        spring = s[(s.index.month < 7) & (s.T2M_MIN < 0)]
        autumn = s[(s.index.month >= 7) & (s.T2M_MIN < 0)]
        lf = spring.index.max().dayofyear if len(spring) else 1
        ff = autumn.index.min().dayofyear if len(autumn) else 366
        gs = s[(s.index.month >= 4) & (s.index.month <= 9)]
        gd = s[(s.index.month >= 4) & (s.index.month <= 10)]
        gdd = float(np.clip((gd.T2M_MAX + gd.T2M_MIN) / 2 - 10, 0, None).sum())
        years.append([int(y), nz(d.T2M.mean()), nz(d.T2M_MAX.mean()), nz(d.T2M_MIN.mean()), int((d.T2M_MAX > 35).sum()),
                      int((d.T2M_MIN < 0).sum()), nz(d.PRECTOTCORR.sum()), nz(d.GWETROOT.mean()), nz(d.GWETTOP.mean()),
                      nz(gdd), int(lf), int(ff), int(ff - lf), nz(gs.T2M.mean()), nz(gs.PRECTOTCORR.sum()),
                      nz(gs.GWETROOT.mean()), nz(d.RH2M.mean()), nz(d.ALLSKY_SFC_SW_DWN.mean()), int(len(d) < 360)])
    months = {}
    for name, (a, b) in PERIODS.items():
        d = df[(df.index.year >= a) & (df.index.year <= b)]
        g = d.groupby(d.index.month)
        months[name] = [[int(m), nz(g.T2M_MIN.mean()[m]), nz(g.T2M.mean()[m]), nz(g.T2M_MAX.mean()[m]),
                         nz(g.PRECTOTCORR.sum()[m] / (b - a + 1)), nz(g.GWETROOT.mean()[m])] for m in range(1, 13)]
    return {"years": years, "months": months}


async def one(client, sem, u, end, last_full):
    f = OUT / f"{u['id']}.json"
    if f.exists():
        return True
    async with sem:
        for attempt in range(5):
            try:
                r = await client.get(URL, params={"parameters": PARAMS, "community": "AG", "latitude": u["lat"],
                                                  "longitude": u["lon"], "start": "19810101", "end": end,
                                                  "format": "JSON"}, timeout=240)
                r.raise_for_status()
                js = r.json()
                P = js["properties"]["parameter"]
                cell = float(js["geometry"]["coordinates"][2])
                pt = u.get("farm_elev", u.get("elev"))
                # cap at ±1.5 km: big gaps mean the cell straddles a range and valleys sit under inversions
                dz = max(-1500.0, min(1500.0, cell - pt)) if pt is not None else 0.0
                agg = await asyncio.to_thread(aggregate, P, u["lat"], last_full, dz)
                agg["cell_elev"], agg["point_elev"], agg["lapse_dz"] = cell, pt, round(dz, 1)
                f.write_text(json.dumps(agg, separators=(",", ":")))
                return True
            except Exception as e:  # noqa: BLE001
                print("retry", u["id"], attempt, repr(e)[:100], flush=True)
                await asyncio.sleep(8 * (attempt + 1))
    return False


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    from etl.world_geo import NEAR
    units = json.load(open(ROOT / "data" / "world_units.json"))
    units.sort(key=lambda u: (u["iso3"] not in NEAR, u["iso3"]))
    end = (date.today() - timedelta(days=5)).strftime("%Y%m%d")
    last_full = date.today().year - 1
    sem = asyncio.Semaphore(6)
    done = 0
    async with httpx.AsyncClient() as client:
        tasks = [asyncio.create_task(one(client, sem, u, end, last_full)) for u in units]
        for t in asyncio.as_completed(tasks):
            await t
            done += 1
            if done % 50 == 0:
                print(f"{done}/{len(units)}", flush=True)
    print("done", sum(1 for u in units if (OUT / f"{u['id']}.json").exists()), "/", len(units), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
