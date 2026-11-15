"""Kür salt-water intrusion: how far Caspian sea water is pushed up the lower Kür today and in the next days.

When the Kür is weak, a north-east wind piles Caspian water (12–13 g/l) against the delta and the heavier salt
water creeps up the river bed, reported up to 30–40 km (June 2020, March 2022). Farmers pumping from the river then
irrigate with brackish water without knowing it.

Model (deliberately simple and transparent, calibrated on the March 2022 event):

    strength S = Q / 334 m³/s                    river discharge at the mouth vs its 2020–2026 median (GloFAS)
                 blended 50/50 with the SWOT water-surface slope (km 13 → km 51) vs its median (1.7 m),
                 when NASA SWOT passed in the last 12 days
    onshore wind U = max(0, wind · cos(direction − 45°))    north-east component, m/s
    salt front  L = 5.67 km · S⁻² · (1 + U / 6)             capped at 60 km; range 0.6 L … 1.6 L

A pump at river km x is red when x ≤ L, orange when x ≤ 1.6 L (or tomorrow will be red), green otherwise.
Water/soil measurements reported by users override the model for their stretch of river.
"""
import asyncio
import csv
import io
import json
import logging
import math
import time
from datetime import date, datetime, timedelta, timezone

import httpx

from .db import ROOT, connect, rows, tx

log = logging.getLogger("kur")
DIR = ROOT / "data" / "kur"
GLOFAS = (39.275, 49.275)          # GloFAS river cell at the Kür mouth (checked against the river network)
UPSTREAM = {"kur": (40.075, 48.575), "araz": (39.975, 48.375)}   # Kür above the Araz confluence, Araz before it
TRAVEL_DAYS = 2                    # ~150 km from the confluence to the sea at ~0.8 m/s
WIND = (39.35, 49.40)              # Kür delta
L0, QREF, HREF, WREF, LMAX = 5.67, 334.0, 1.7, 6.0, 60.0
HEAD = ("28461000013", "28461000051")   # SWORD reaches at km 13.4 and km 51.4
SWOT_REACHES = ["28461000013", "28461000021", "28461000031", "28461000041", "28461000051", "28461000081",
                "28461000121", "28463000011"]
HYDROCRON = "https://soto.podaac.earthdatacloud.nasa.gov/hydrocron/v1/timeseries"
SALTY_EC, CAUTION_EC = 3.0, 0.7    # FAO irrigation water EC (dS/m): >3 severe restriction, 0.7–3 slight to moderate

# FAO (Ayers & Westcot 1985) soil salinity ECe (dS/m) at which yield starts to fall
CROP_ECE = {"arpa": 8.0, "pambiq": 7.7, "seker-cugunduru": 7.0, "bugda": 6.0, "celtik": 3.0, "pomidor": 2.5,
            "xiyar": 2.5, "kelem": 1.8, "qargidali": 1.7, "kartof": 1.7, "bibar": 1.5, "uzum": 1.5, "sogan": 1.2,
            "lobya": 1.0, "noxud": 1.0, "yemis": 2.2, "qarpiz": 2.2, "badimcan": 1.1, "gunebaxan": 4.8,
            "nar": 4.0, "zeytun": 4.0, "alma": 1.0, "armud": 1.0, "saftali": 1.7, "erik": 1.6, "gavali": 1.5,
            "tutun": 2.0}

_state = {"data": None, "at": 0}
_swot = {"data": None, "at": 0}


def onshore(ws, wd):
    if ws is None or wd is None or ws < 0 or wd < 0:
        return None
    return max(0.0, ws * math.cos(math.radians(wd - 45)))


SYNODIC = 29.530588


def moon(day):
    """Days since new moon and whether it is a spring tide (new or full moon ± 2 days)."""
    ref = date(2000, 1, 6)                      # a new moon (18:14 UTC)
    age = ((date.fromisoformat(day) - ref).days - 0.76) % SYNODIC
    spring = age < 2 or abs(age - SYNODIC / 2) < 2 or age > SYNODIC - 2
    return round(age, 1), spring


def front(q, u, head=None, spring=False):
    """Salt-front distance up the river (km) and its plausible range.
    Caspian tides are only a few cm, so spring tides (new / full moon) add just 3 %."""
    if q is None or u is None:
        return None
    s = max(q, 50.0) / QREF
    if head is not None:
        s = 0.5 * s + 0.5 * max(head, 0.05) / HREF
    s = max(s, 0.15)
    L = min(LMAX, L0 * s ** -2 * (1 + u / WREF) * (1.03 if spring else 1.0))
    return {"km": round(L, 1), "lo": round(L * 0.6, 1), "hi": round(min(LMAX, L * 1.6), 1)}


def level_at(km, f, f_next=None):
    if not f:
        return "unknown"
    if km <= f["km"]:
        return "red"
    if km <= f["hi"] or (f_next and km <= f_next["km"]):
        return "orange"
    return "green"


# ------------------------------------------------------------------ static geometry and history (from etl.kur_build)
def geometry():
    river = json.load(open(DIR / "river.json"))
    villages = json.load(open(DIR / "villages.json"))
    return river, villages


def history():
    p = DIR / "history.json"
    return json.load(open(p)) if p.exists() else None


def soil_for(lat, lon):
    """Landsat surface-salt trend of the village nearest to lat/lon (etl.kur_soil), or None."""
    p = DIR / "soil.json"
    if lat is None or lon is None or not p.exists():
        return None
    vs = [v for v in json.load(open(p))["villages"] if v.get("trend")]
    if not vs:
        return None
    k = math.cos(math.radians(lat))
    villages = {v["name"]: v for v in json.load(open(DIR / "villages.json"))}
    best = min(vs, key=lambda v: ((villages[v["name"]]["lon"] - lon) * k) ** 2 + (villages[v["name"]]["lat"] - lat) ** 2)
    vv = villages[best["name"]]
    if math.hypot((vv["lon"] - lon) * k, vv["lat"] - lat) * 111 > 6:
        return None
    return {"village": best["name"], "trend": best["trend"], "years": best["years"]}


def nearest_km(lat, lon):
    """River km of the closest point on the Kür (main stem) to lat/lon, and the distance to it."""
    river, _ = geometry()
    best = None
    k = math.cos(math.radians(lat))
    for r in river:
        if r.get("stem") != "kur":
            continue
        for km, (x, y) in zip(r["kms"], r["line"]):
            d = ((x - lon) * k) ** 2 + (y - lat) ** 2
            if best is None or d < best[0]:
                best = (d, km, x, y)
    return {"km": round(best[1], 1), "dist_km": round(math.sqrt(best[0]) * 111, 2), "lon": best[2], "lat": best[3]}


# ------------------------------------------------------------------ live inputs
def _client():
    return httpx.Client(timeout=90, headers={"User-Agent": "FieldShift/1.0 (NASA Space Apps 2026)"})


def fetch_discharge(c, point=GLOFAS):
    r = c.get("https://flood-api.open-meteo.com/v1/flood", params={
        "latitude": point[0], "longitude": point[1], "daily": "river_discharge", "past_days": 60, "forecast_days": 16})
    r.raise_for_status()
    d = r.json()["daily"]
    return dict(zip(d["time"], d["river_discharge"]))


def fetch_basin(c):
    """Rain and evaporation over the lower basin (one point near Salyan), past 60 + 16 days."""
    r = c.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": 39.6, "longitude": 48.98, "daily": "precipitation_sum,et0_fao_evapotranspiration", "past_days": 60,
        "forecast_days": 16, "timezone": "Asia/Baku"})
    r.raise_for_status()
    d = r.json()["daily"]
    return {t: {"rain": p or 0.0, "et0": e or 0.0} for t, p, e in zip(d["time"], d["precipitation_sum"], d["et0_fao_evapotranspiration"])}


def fetch_wind(c):
    r = c.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": WIND[0], "longitude": WIND[1], "hourly": "wind_speed_10m,wind_direction_10m", "past_days": 60,
        "forecast_days": 16, "wind_speed_unit": "ms", "timezone": "Asia/Baku"})
    r.raise_for_status()
    h = r.json()["hourly"]
    days = {}
    for t, ws, wd in zip(h["time"], h["wind_speed_10m"], h["wind_direction_10m"]):
        if ws is None or wd is None:
            continue
        e = days.setdefault(t[:10], {"u": [], "ws": [], "x": 0.0, "y": 0.0})
        e["u"].append(onshore(ws, wd))
        e["ws"].append(ws)
        e["x"] += ws * math.sin(math.radians(wd))
        e["y"] += ws * math.cos(math.radians(wd))
    out = {}
    for d, e in days.items():
        if len(e["u"]) < 12:
            continue
        out[d] = {"u": round(sum(e["u"]) / len(e["u"]), 2), "ws": round(sum(e["ws"]) / len(e["ws"]), 2),
                  "ws_max": round(max(e["ws"]), 1), "wd": round(math.degrees(math.atan2(e["x"], e["y"])) % 360)}
    return out


def fetch_swot(since_days=400):
    """Latest NASA SWOT water-surface elevations of the lower Kür reaches (Hydrocron, no login)."""
    start = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y-%m-%dT00:00:00Z")
    end = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = {}
    with httpx.Client(timeout=300, headers={"User-Agent": "FieldShift/1.0"}) as c:
        for rid in SWOT_REACHES:
            try:
                r = c.get(HYDROCRON, params={"feature": "Reach", "feature_id": rid, "start_time": start, "end_time": end,
                                             "output": "csv", "fields": "reach_id,time_str,wse,width,reach_q"})
                r.raise_for_status()
                obs = {}
                for x in csv.DictReader(io.StringIO(r.json()["results"]["csv"])):
                    try:
                        w = float(x["wse"])
                    except ValueError:
                        continue
                    if w < -1000 or x.get("reach_q") not in ("0", "1"):
                        continue
                    obs.setdefault(x["time_str"][:10], []).append(w)
                out[rid] = {d: round(sorted(v)[len(v) // 2], 3) for d, v in obs.items()}
            except Exception as e:  # noqa: BLE001 - one reach failing must not drop the others
                log.warning("SWOT %s failed: %s", rid, e)
    return out


def swot_cached(max_age=12 * 3600):
    p = DIR / "swot_live.json"
    if _swot["data"] is None and p.exists():
        _swot["data"] = json.load(open(p))
        _swot["at"] = p.stat().st_mtime
    if _swot["data"] is None or time.time() - _swot["at"] > max_age:
        data = fetch_swot()
        if any(data.values()):
            _swot["data"], _swot["at"] = data, time.time()
            json.dump(data, open(p, "w"))
    return _swot["data"] or {}


def swot_head(sw, day):
    """Latest SWOT slope km 13 → km 51 on or before `day`: (head m, date)."""
    a, b = sw.get(HEAD[0], {}), sw.get(HEAD[1], {})
    both = sorted(d for d in set(a) & set(b) if d <= day)
    if not both:
        return None, None
    d = both[-1]
    return round(b[d] - a[d], 2), d


def observed(con, days=3):
    """Farmers' river-water reports of the last days (km, salty)."""
    since = (date.today() - timedelta(days=days)).isoformat()
    obs = rows(con, "SELECT km, ec, salty, observed_at FROM kur_obs WHERE kind='water' AND km IS NOT NULL "
                    "AND salty IS NOT NULL AND observed_at >= ? ORDER BY observed_at DESC", since)
    salty = [o["km"] for o in obs if o["salty"]]
    fresh = [o["km"] for o in obs if o["salty"] == 0]
    return {"n": len(obs), "salty": salty, "fresh": fresh,
            "salty_km": max(salty) if salty else None, "fresh_km": min(fresh) if fresh else None}


# ------------------------------------------------------------------ state
def compute():
    """Blocking: fetch inputs, run the model for 60 past + 16 coming days."""
    with _client() as c:
        q = fetch_discharge(c)
        w = fetch_wind(c)
        up = {k: fetch_discharge(c, pt) for k, pt in UPSTREAM.items()}
        try:
            basin = fetch_basin(c)
        except Exception:  # noqa: BLE001
            basin = {}
    try:
        sw = swot_cached()
    except Exception as e:  # noqa: BLE001
        log.warning("SWOT refresh failed: %s", e)
        sw = _swot["data"] or {}
    today = date.today().isoformat()
    days = []
    for d in sorted(set(q) & set(w)):
        head, hd = swot_head(sw, d)
        use_head = head if hd and (date.fromisoformat(d) - date.fromisoformat(hd)).days <= 12 else None
        age, spring = moon(d)
        f = front(q[d], w[d]["u"], use_head, spring)
        days.append({"date": d, "q": round(q[d]) if q[d] is not None else None, **w[d], "head": use_head,
                     "head_date": hd if use_head is not None else None, "front": f, "fc": d > today,
                     "q_kur": _r(up["kur"].get(d)), "q_araz": _r(up["araz"].get(d)), "moon": age, "spring": spring,
                     "rain": round(basin.get(d, {}).get("rain", 0), 1), "et0": round(basin.get(d, {}).get("et0", 0), 1)})
    hist = history() or {}
    con = connect()
    try:
        obs = observed(con)
    finally:
        con.close()
    head, hd = swot_head(sw, today)
    t = next((x for x in days if x["date"] == today), days[-1] if days else None)
    norms = {k: hist.get(f"{k}_median") for k in ("q", "q_kur", "q_araz")}
    state = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "today": today, "days": days, "norms": norms,
             "now": t, "observed": obs, "q_median": QREF, "q_pct": pct(hist.get("q_sorted"), t["q"]) if t else None,
             "swot": {"head": head, "date": hd, "head_median": HREF,
                      "levels": {rid: (max(v.items()) if v else None) for rid, v in sw.items()}},
             "model": {"L0": L0, "QREF": QREF, "HREF": HREF, "WREF": WREF, "LMAX": LMAX}}
    # a salty report moves today's front only when it is physically plausible (within 15 km beyond the model's range)
    if t and t["front"]:
        near = [k for k in obs["salty"] if t["front"]["km"] < k <= t["front"]["hi"] + 15]
        if near:
            state["now"] = {**t, "front": {**t["front"], "km": max(near), "observed": True}}
    return state


def _r(v):
    return round(v) if v is not None else None


def pct(sorted_vals, v):
    if not sorted_vals or v is None:
        return None
    lo, hi = 0, len(sorted_vals)
    while lo < hi:
        m = (lo + hi) // 2
        if sorted_vals[m] <= v:
            lo = m + 1
        else:
            hi = m
    return round(lo / len(sorted_vals) * 100)


def state(max_age=3 * 3600):
    if _state["data"] is None or time.time() - _state["at"] > max_age:
        p = DIR / "state.json"
        try:
            _state["data"] = compute()
            _state["at"] = time.time()
            json.dump(_state["data"], open(p, "w"))
        except Exception as e:  # noqa: BLE001 - keep serving the last good state
            log.warning("Kür state refresh failed: %s", e)
            if _state["data"] is None and p.exists():
                _state["data"] = json.load(open(p))
                _state["at"] = time.time() - max_age + 600
    return _state["data"]


def cached():
    """Last computed state without touching the network (for the alert loop)."""
    if _state["data"] is None and (DIR / "state.json").exists():
        _state["data"] = json.load(open(DIR / "state.json"))
    return _state["data"]


def for_km(km, st=None):
    """Status of one pump / intake at river km: today, tomorrow and the next days."""
    st = st or state()
    if not st:
        return None
    days = st["days"]
    idx = next((i for i, d in enumerate(days) if d["date"] == st["today"]), len(days) - 1)
    out = []
    for i, d in enumerate(days[max(0, idx - 7): idx + 8], start=max(0, idx - 7)):
        nxt = days[i + 1]["front"] if i + 1 < len(days) else None
        out.append({"date": d["date"], "level": level_at(km, d["front"], nxt), "front": d["front"], "fc": d["fc"],
                    "u": d["u"], "wd": d["wd"], "ws": d["ws"], "q": d["q"]})
    now = st["now"]
    nxt = days[idx + 1]["front"] if idx + 1 < len(days) else None
    level = level_at(km, now["front"], nxt)
    obs = st["observed"]
    near = [k for k in obs.get("salty", []) if abs(k - km) <= 5]      # farmers within 5 km who found salty water
    reported = len(near)
    model_level = level
    if reported >= 2:
        level = "red"                                                  # confirmed by two or more farmers
    elif reported == 1 and level == "green":
        level = "orange"                                               # one report: check the water, do not panic
    for d in out:                                                      # keep the day strip consistent with today
        if d["date"] == st["today"]:
            d["level"] = level
    upcoming = next((d for d in out if d["date"] > st["today"] and d["level"] == "red"), None)
    fresh_again = None
    if level != "green" and model_level != "green":
        fresh_again = next((d["date"] for d in out if d["date"] > st["today"] and d["level"] == "green"), None)
    return {"km": km, "level": level, "front": now["front"], "days": out, "first_red": upcoming["date"] if upcoming else None,
            "reported": reported, "model_level": model_level, "fresh_again": fresh_again, "reasons": reasons(st, upcoming["date"] if upcoming else st["today"])}


def reasons(st, day):
    """Plain causes for the water at `day`: each {key, level: bad|ok, value} for the UI and SMS."""
    d = next((x for x in st["days"] if x["date"] == day), st["now"])
    norms = st.get("norms") or {}
    out = []

    def rel(v, n):
        return round((v / n - 1) * 100) if v is not None and n else None
    for key, v in (("kur", d.get("q_kur")), ("araz", d.get("q_araz")), ("mouth", d.get("q"))):
        r = rel(v, norms.get({"kur": "q_kur", "araz": "q_araz", "mouth": "q"}[key]))
        if r is not None:
            out.append({"key": key, "level": "bad" if r <= -25 else "ok", "pct": r})
    u = d.get("u") or 0
    out.append({"key": "wind", "level": "bad" if u >= 5 else "ok", "value": round(u, 1), "dir": d.get("wd")})
    if d.get("et0", 0) >= 5:
        out.append({"key": "heat", "level": "bad", "value": d["et0"]})
    wk = [x for x in st["days"] if st["today"] <= x["date"] <= day or x["date"] == day]
    rain = round(sum(x.get("rain", 0) for x in st["days"] if x["date"] > st["today"] and x["date"] <= (date.fromisoformat(st["today"]) + timedelta(days=7)).isoformat()), 1)
    out.append({"key": "rain", "level": "ok" if rain >= 10 else "bad" if rain < 2 else "ok", "value": rain})
    out.append({"key": "moon", "level": "bad" if d.get("spring") else "ok", "spring": bool(d.get("spring"))})
    return out


def advice(level, has_pond=False):
    return {
        "red": "Do not pump from the Kür today: salt water has reached your intake. Use stored water.",
        "orange": "Pump and fill storage today; salt water may reach your intake soon.",
        "green": "River water is fresh at your intake." + (" Good day to fill the pond." if has_pond else ""),
    }.get(level, "")


async def loop(interval=3 * 3600):
    await asyncio.sleep(15)
    while True:
        try:
            await asyncio.to_thread(state, 0)
        except Exception as e:  # noqa: BLE001
            log.warning("Kür loop failed: %s", e)
        await asyncio.sleep(interval)


# ------------------------------------------------------------------ "Ask": plain answers grounded in today's data
ASK_SYSTEM = """You are Field Shift, an assistant for farmers on the lower Kür river in Azerbaijan (Neftçala, Salyan).
The product warns when salty Caspian water enters the Kür. Answer in the user's language (Azerbaijani unless they write
English), in 1–2 very short sentences (at most 35 words), simple village words, no numbers unless needed, no jargon, no lists. Be calm: say what to do.
Use ONLY the facts below and the JSON with today's data; if something is not known, say so.

How it works (facts):
- Salt water enters when the Kür is weak and a north-east wind pushes Caspian water (12–13 g/l) into the river mouth;
  heavy salt water creeps up the river bed, reported 30–40 km in bad episodes (2020, 2022).
- River strength = water from the Kür upstream + the Araz (largest tributary, joins at Suqovuşan), minus what canals
  take; reservoirs (Mingəçevir, Araz) decide releases, so rain upstream matters less than the river's own flow.
  Water from the confluence reaches the sea in about 2 days.
- NASA SWOT satellite measures the river level from space (a few passes a month); GloFAS gives daily flow and a 16-day forecast.
- Wind: north-east wind piles sea water against the delta; the stronger, the further salt goes.
- Moon: Caspian tides are only a few centimetres; new/full moon adds about 3 % — a small effect.
- Earth's gravity: NASA GRACE satellites weigh the basin's water by gravity; the Kür–Araz basin lost about 22.5 cm of
  water 2002–2022 (−1.5 cm/year) — the long-term reason the Kür is weaker. It does not change day to day.
- Rain and evaporation: rain upstream adds flow later; hot dry days increase evaporation and water use, weakening the river.
- Salt water burns crops and salts the soil for years; irrigate with stored water when the river is salty, wash soil
  with extra fresh water when the river is fresh. Salt-tolerant crops: barley, cotton, sugar beet, wheat; sensitive:
  maize, onion, beans, vegetables.
- Levels: green = fresh, orange = salt expected soon (irrigate now, fill the pond), red = salty at that point (do not pump).
Never mention JSON field names or internal words such as ok, bad, level, km values with decimals; speak like a helpful agronomist.
"""


def ask_context(km=None):
    st = cached() or {}
    ctx = {"today": st.get("today"), "salt_front_km_today": (st.get("now") or {}).get("front"),
           "flow_today_m3s": (st.get("now") or {}).get("q"), "flow_normal_m3s": QREF}
    if km is not None and st:
        s = for_km(km, st)
        if s:
            ctx.update({"place_km": km, "level_today": s["level"], "first_salty_day": s["first_red"],
                        "fresh_again": s["fresh_again"], "reasons": s["reasons"],
                        "next_days": [{"date": d["date"], "level": d["level"]} for d in s["days"] if d["date"] >= st["today"]][:7]})
    g = DIR / "grace.json"
    if g.exists():
        gg = json.load(open(g))
        ctx["grace"] = {"trend_cm_per_year": gg["trend_cm_per_year"], "change_cm": gg["change_cm"], "period": [gg["start"], gg["end"]]}
    return ctx
