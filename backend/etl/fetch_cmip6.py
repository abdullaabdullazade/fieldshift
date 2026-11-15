"""CMIP6 HighResMIP daily projections (Open-Meteo Climate API) per economic-region centroid.

Used with the delta method: future change = model(2026-2050) - model(1991-2020), added to each
rayon's NASA POWER baseline. Cached as data/raw/cmip6/<econ_id>.json.
"""
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "raw" / "cmip6"
MODELS = "EC_Earth3P_HR,MRI_AGCM3_2_S,MPI_ESM1_2_XR"
URL = "https://climate-api.open-meteo.com/v1/climate"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rayons = json.load(open(ROOT / "data" / "rayons.json"))
    econ = {}
    for r in rayons:
        econ.setdefault(r["econ_id"], []).append((r["lat"], r["lon"]))
    for eid, pts in econ.items():
        f = OUT / f"{eid}.json"
        if f.exists():
            continue
        lat = sum(p[0] for p in pts) / len(pts)
        lon = sum(p[1] for p in pts) / len(pts)
        for attempt in range(40):
            try:
                r = httpx.get(URL, params={
                    "latitude": round(lat, 3), "longitude": round(lon, 3), "start_date": "1991-01-01",
                    "end_date": "2050-12-31", "models": MODELS,
                    "daily": "temperature_2m_max,temperature_2m_min,temperature_2m_mean,precipitation_sum"},
                    timeout=300)
            except httpx.HTTPError as e:
                print("neterr", eid, repr(e)[:100], flush=True)
                time.sleep(60)
                continue
            if r.status_code == 200:
                f.write_text(r.text)
                print("ok", eid, flush=True)
                break
            print("retry", eid, r.status_code, r.text[:150], flush=True)
            time.sleep(900 if "Hourly" in r.text else 70)
        time.sleep(65)


if __name__ == "__main__":
    main()
