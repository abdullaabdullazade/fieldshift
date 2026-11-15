"""Back-test of the Kür salt-front model, 2020 → today (the years the problem appeared), for the proof section.

Inputs (downloaded once into data/raw/kur/, refreshed with --fetch):
  glofas_mouth.json   daily river discharge at the Kür mouth, GloFAS v4 reanalysis (Copernicus, via Open-Meteo)
  power_mouth.json    daily 10 m wind speed and direction over the Kür delta, NASA POWER
  swot/<reach>.json   NASA SWOT water-surface elevations of the lower Kür reaches (Hydrocron)

Output data/kur/history.json: yearly counts of days with the modelled salt front beyond 20 / 30 km, the strongest
episodes, the documented events with what the model says on those days, the SWOT slope series and the sorted
discharge record (for percentiles).
"""
import argparse
import csv
import io
import json
import statistics as st
import sys
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.kur import GLOFAS, HEAD, SWOT_REACHES, UPSTREAM, WIND, front, onshore  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "kur"
START = "2020-01-01"     # first documented intrusion was June 2020; earlier years are not used
OUT = ROOT / "data" / "kur"

# events documented in the press, with the distance they report
EVENTS = [
    {"id": "2022-03", "from": "2022-03-01", "to": "2022-03-20", "reported_km": 30,
     "source": "bayraqdar.info, 9 Mar 2022: a Kür branch dried up and Caspian water flows into the Kür"},
]


def fetch():
    RAW.mkdir(parents=True, exist_ok=True)
    end = date.today().isoformat()
    u = (f"https://flood-api.open-meteo.com/v1/flood?latitude={GLOFAS[0]}&longitude={GLOFAS[1]}"
         f"&daily=river_discharge&start_date={START}&end_date={end}")
    (RAW / "glofas_mouth.json").write_bytes(urllib.request.urlopen(u, timeout=300).read())
    u = ("https://power.larc.nasa.gov/api/temporal/daily/point?parameters=WS10M,WS10M_MAX,WD10M&community=AG"
         f"&latitude={WIND[0]}&longitude={WIND[1]}&start={START.replace('-', '')}&end={end.replace('-', '')}&format=JSON")
    (RAW / "power_mouth.json").write_bytes(urllib.request.urlopen(u, timeout=600).read())
    fetch_upstream()
    (RAW / "swot").mkdir(exist_ok=True)
    for rid in SWOT_REACHES:
        u = ("https://soto.podaac.earthdatacloud.nasa.gov/hydrocron/v1/timeseries?feature=Reach"
             f"&feature_id={rid}&start_time=2023-03-01T00:00:00Z&end_time={end}T23:59:59Z&output=csv"
             "&fields=reach_id,time_str,wse,wse_u,width,slope,reach_q,dark_frac,xovr_cal_q")
        try:
            (RAW / "swot" / f"{rid}.json").write_bytes(urllib.request.urlopen(u, timeout=600).read())
        except Exception as e:  # noqa: BLE001
            print("SWOT", rid, e)


def fetch_upstream():
    end = date.today().isoformat()
    for k, (la, lo) in UPSTREAM.items():
        u = (f"https://flood-api.open-meteo.com/v1/flood?latitude={la}&longitude={lo}"
             f"&daily=river_discharge&start_date={START}&end_date={end}")
        (RAW / f"glofas_{k}.json").write_bytes(urllib.request.urlopen(u, timeout=300).read())


def swot_series():
    out = {}
    for rid in SWOT_REACHES:
        p = RAW / "swot" / f"{rid}.json"
        if not p.exists():
            continue
        d = json.load(open(p))
        if "results" not in d:
            continue
        obs = defaultdict(list)
        for x in csv.DictReader(io.StringIO(d["results"]["csv"])):
            try:
                w = float(x["wse"])
            except ValueError:
                continue
            if w > -1000 and x.get("reach_q") in ("0", "1"):
                obs[x["time_str"][:10]].append(w)
        out[rid] = {k: round(st.median(v), 3) for k, v in obs.items()}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="download inputs again")
    if ap.parse_args().fetch or not (RAW / "glofas_mouth.json").exists():
        fetch()
    g = json.load(open(RAW / "glofas_mouth.json"))["daily"]
    Q = {t: v for t, v in zip(g["time"], g["river_discharge"]) if v is not None and t >= START}
    p = json.load(open(RAW / "power_mouth.json"))["properties"]["parameter"]
    k = lambda s: f"{s[:4]}-{s[4:6]}-{s[6:]}"                                # noqa: E731
    WS = {k(a): b for a, b in p["WS10M"].items() if b is not None and b >= 0}
    WD = {k(a): b for a, b in p["WD10M"].items() if b is not None and b >= 0}
    sw = swot_series()
    a, b = sw.get(HEAD[0], {}), sw.get(HEAD[1], {})
    heads = {d: round(b[d] - a[d], 2) for d in sorted(set(a) & set(b))}

    daily = {}
    for d in sorted(Q):
        if d not in WS or d not in WD:
            continue
        u = onshore(WS[d], WD[d])
        hd = max((h for h in heads if h <= d), default=None)
        head = heads[hd] if hd and (date.fromisoformat(d) - date.fromisoformat(hd)).days <= 12 else None
        f = front(Q[d], u, head)
        daily[d] = {"q": round(Q[d]), "u": round(u, 2), "ws": WS[d], "wd": WD[d], "head": head, "km": f["km"]}

    years = defaultdict(lambda: {"d20": 0, "d30": 0, "max": 0.0, "n": 0})
    for d, v in daily.items():
        y = years[d[:4]]
        y["n"] += 1
        y["d20"] += v["km"] >= 20
        y["d30"] += v["km"] >= 30
        y["max"] = max(y["max"], v["km"])
    yearly = [{"year": int(y), **{kk: (round(vv, 1) if isinstance(vv, float) else vv) for kk, vv in v.items()}}
              for y, v in sorted(years.items()) if v["n"] >= 300 or y == str(date.today().year)]

    episodes, seen = [], set()
    for d, v in sorted(daily.items(), key=lambda kv: -kv[1]["km"]):
        if d[:7] in seen:
            continue
        seen.add(d[:7])
        episodes.append({"date": d, **v})
        if len(episodes) >= 12:
            break

    events = []
    for e in EVENTS:
        ds = [d for d in daily if e["from"] <= d <= e["to"]]
        peak = max(ds, key=lambda d: daily[d]["km"])
        events.append({**e, "peak_date": peak, "model_km": daily[peak]["km"], **{x: daily[peak][x] for x in ("q", "u", "ws", "wd")},
                       "q_min": min(daily[d]["q"] for d in ds)})

    weekly = defaultdict(float)
    for d, v in daily.items():
        if d >= START:
            wk = date.fromisoformat(d).isocalendar()
            key = f"{wk[0]}-W{wk[1]:02d}"
            weekly[key] = max(weekly[key], v["km"])
    swot_rows = [{"date": d, "head": h, "q": daily.get(d, {}).get("q"), "km": daily.get(d, {}).get("km")} for d, h in heads.items()]
    if not all((RAW / f"glofas_{k}.json").exists() for k in UPSTREAM):
        fetch_upstream()
    med = {}
    for k in UPSTREAM:
        gg = json.load(open(RAW / f"glofas_{k}.json"))["daily"]
        med[f"q_{k}_median"] = round(st.median(v for t, v in zip(gg["time"], gg["river_discharge"]) if v is not None and t >= START))
    daily_out = [{"d": d, "km": v["km"], "q": v["q"], "u": v["u"], "wd": v["wd"]} for d, v in sorted(daily.items())]
    out = {"built": date.today().isoformat(), **med, "daily": daily_out, "yearly": yearly, "episodes": episodes, "events": events,
           "weekly": [{"w": w, "km": round(v, 1)} for w, v in sorted(weekly.items())], "swot": swot_rows,
           "q_sorted": sorted(round(v) for v in Q.values()), "q_median": round(st.median(Q.values())),
           "first": min(daily), "last": max(daily)}
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(OUT / "history.json", "w"), separators=(",", ":"))
    print("days", len(daily), "| years with >=30 km days:", [(y["year"], y["d30"]) for y in yearly if y["d30"]])
    for e in events:
        print(e["id"], "model", e["model_km"], "km on", e["peak_date"], "| Q min", e["q_min"])
    print("SWOT passes", len(swot_rows))


if __name__ == "__main__":
    main()
