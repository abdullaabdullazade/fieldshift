"""Download NASA POWER daily point data (community=AG, MERRA-2) for every rayon centroid.

Cached as data/raw/power/<rayon>.json; re-running skips files already present.
"""
import asyncio
import json
from datetime import date, timedelta
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "power"
PARAMS = "T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,GWETROOT,GWETTOP,RH2M,ALLSKY_SFC_SW_DWN"
URL = "https://power.larc.nasa.gov/api/temporal/daily/point"


async def one(client, sem, r, end):
    f = OUT / f"{r['id']}.json"
    if f.exists():
        return
    async with sem:
        for attempt in range(4):
            try:
                resp = await client.get(URL, params={
                    "parameters": PARAMS, "community": "AG", "latitude": r["lat"], "longitude": r["lon"],
                    "start": "19810101", "end": end, "format": "JSON"}, timeout=180)
                resp.raise_for_status()
                f.write_text(resp.text)
                print("ok", r["id"], flush=True)
                return
            except Exception as e:  # noqa: BLE001
                print("retry", r["id"], attempt, repr(e)[:120], flush=True)
                await asyncio.sleep(10 * (attempt + 1))


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rayons = json.load(open(ROOT / "data" / "rayons.json"))
    end = (date.today() - timedelta(days=5)).strftime("%Y%m%d")
    sem = asyncio.Semaphore(4)
    async with httpx.AsyncClient() as client:
        await asyncio.gather(*(one(client, sem, r, end) for r in rayons))


if __name__ == "__main__":
    asyncio.run(main())
