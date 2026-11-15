"""NASA GRACE / GRACE-FO: total water storage of the Kür–Araz basin, monthly 2002 → 2022 (as published on GIBS).

GRACE measures tiny changes of the Earth's gravity; less water in a basin means a slightly weaker pull. GIBS serves
the JPL mascon solution (liquid water equivalent thickness, cm, anomaly vs 2004–2009) as a colour-mapped image; each
monthly image of the basin box is decoded back to centimetres with the published colour map and averaged.

Output data/kur/grace.json: [{date, cm}], the linear trend (cm/year) and the change over the record.
"""
import json
import re
import sys
from datetime import date
from io import BytesIO
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.satellite import CAPS, colormap  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LAYER = "GRACE_Tellus_Liquid_Water_Equivalent_Thickness_Mascon_CRI"
BOX = (38.4, 43.5, 42.3, 49.0)        # S, W, N, E: Kür–Araz basin on land (the Caspian is left out)
WMS = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"


def months(caps):
    i = caps.find(f"<ows:Identifier>{LAYER}</ows:Identifier>")
    seg = caps[caps.rfind("<Layer>", 0, i): caps.find("</Layer>", i)]
    out = set()
    for v in re.findall(r"<Value>([^<]+)</Value>", seg):
        a, b, step = v.split("/")
        d0, d1 = date.fromisoformat(a), date.fromisoformat(b)
        if step == "P1M":
            y, m = d0.year, d0.month
            while (y, m) <= (d1.year, d1.month):
                out.add(date(y, m, 1).isoformat())
                y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        else:
            out.add(d0.isoformat())
    return sorted(out)


def main():
    with httpx.Client(timeout=120, headers={"User-Agent": "FieldShift/1.0 (NASA Space Apps 2026)"}) as c:
        caps = c.get(CAPS).text
        lut = colormap(LAYER, c)
        keys = np.array(sorted(lut))
        vals = np.array([lut[k] for k in keys])
        series = []
        for d in months(caps):
            r = c.get(WMS, params={"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": LAYER, "CRS": "EPSG:4326",
                                   "BBOX": ",".join(map(str, BOX)), "WIDTH": 130, "HEIGHT": 78, "FORMAT": "image/png", "TIME": d})
            if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image"):
                continue
            a = np.asarray(Image.open(BytesIO(r.content)).convert("RGBA")).astype(np.int64)
            packed = a[..., 0] * 65536 + a[..., 1] * 256 + a[..., 2]
            ok = a[..., 3] > 0
            idx = np.searchsorted(keys, packed[ok])
            idx = np.clip(idx, 0, len(keys) - 1)
            hit = keys[idx] == packed[ok]
            if hit.sum() < 50:
                continue
            series.append({"date": d, "cm": round(float(vals[idx[hit]].mean()), 2)})
            print(d, series[-1]["cm"], end=" | ", flush=True)
    t = np.array([date.fromisoformat(s["date"]).toordinal() / 365.25 for s in series])
    y = np.array([s["cm"] for s in series])
    slope = float(np.polyfit(t, y, 1)[0])
    first = float(np.mean(y[:12])); last = float(np.mean(y[-12:]))
    out = {"series": series, "trend_cm_per_year": round(slope, 2), "first_year_mean": round(first, 1),
           "last_year_mean": round(last, 1), "change_cm": round(last - first, 1),
           "start": series[0]["date"], "end": series[-1]["date"], "box": BOX}
    (ROOT / "data" / "kur" / "grace.json").write_text(json.dumps(out, separators=(",", ":")))
    print("\nmonths", len(series), "trend", out["trend_cm_per_year"], "cm/yr, change", out["change_cm"], "cm")


if __name__ == "__main__":
    main()
