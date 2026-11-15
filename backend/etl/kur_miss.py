"""Mississippi 2023 salt wedge: the same physics as the Kür, with public measurements.

Inputs: USGS 07374525 (Mississippi River at Belle Chasse) daily discharge, and the salt-wedge toe positions the
US Army Corps of Engineers published during the 2023 event (river miles above Head of Passes).
The wedge was also held back by an underwater sill at river mile 64, so this is shown as qualitative support for
"weak river → salt water far upstream", not as a calibration of the Kür model.
Output data/kur/mississippi.json.
"""
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOE = [   # date, river mile, source
    ("2023-09-20", 63.8, "USACE via Fox 8 New Orleans: the wedge overtopped the sill at river mile 63.8"),
    ("2023-10-09", 63.9, "USACE: toe measured at river mile 63.9"),
    ("2023-10-30", 68.3, "USACE: toe last measured at river mile 68.3"),
    ("2024-01-22", 11.0, "Plaquemines Parish: wedge moved back towards the Gulf, river mile 11"),
]


def main():
    u = ("https://waterservices.usgs.gov/nwis/dv/?format=json&sites=07374525&parameterCd=00060"
         "&startDT=2015-01-01&endDT=2024-03-31&siteStatus=all")
    d = json.load(urllib.request.urlopen(u, timeout=300))
    q = {v["dateTime"][:10]: float(v["value"]) for v in d["value"]["timeSeries"][0]["values"][0]["value"] if float(v["value"]) > 0}
    vals = sorted(q.values())
    med = vals[len(vals) // 2]
    series = [{"date": k, "q": round(v * 0.0283168)} for k, v in sorted(q.items()) if "2023-05-01" <= k <= "2024-02-29"]
    toe = [{"date": dt, "rm": rm, "km": round(rm * 1.609, 1), "q": round(q.get(dt, 0) * 0.0283168), "q_pct_of_median": round(q.get(dt, 0) / med * 100),
            "source": src} for dt, rm, src in TOE]
    out = {"station": "USGS 07374525 Mississippi River at Belle Chasse, LA", "median_q": round(med * 0.0283168),
           "series": series, "toe": toe, "sill_km": round(64 * 1.609, 1)}
    (ROOT / "data" / "kur" / "mississippi.json").write_text(json.dumps(out, separators=(",", ":")))
    print([(t["date"], t["km"], t["q_pct_of_median"]) for t in toe])


if __name__ == "__main__":
    main()
