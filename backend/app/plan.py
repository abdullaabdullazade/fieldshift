"""Irrigation plan for one field on the lower Kür: when to irrigate, how much, and whether the river is fresh that day.

Water balance (FAO-56, single crop coefficient):
    crop use ETc = Kc(crop, month) · ET0          ET0 = FAO Penman-Monteith reference evapotranspiration (forecast)
    deficit(d) = max(0, deficit(d-1) + ETc(d) − 0.8 · rain(d))
    irrigate when the deficit reaches the readily available water of the root zone (RAW, mm); dose = deficit
The deficit starts at 0 on the day the farmer last irrigated ("I irrigated today"); without a record the last
14 days are assumed to start from a watered field and the plan is marked approximate.
If the river is salty at the farm's pump on the planned day (Kür model), the irrigation is moved to the last fresh day
before it (fill storage), otherwise to the next fresh day.
"""
import time
from datetime import date, timedelta

import httpx

# FAO-56 style monthly crop coefficients for the Kür–Araz lowland calendar (0 = no crop in the field)
KC = {
    "pambiq": {4: .35, 5: .5, 6: .9, 7: 1.15, 8: 1.15, 9: .8, 10: .6},
    "bugda": {10: .4, 11: .5, 12: .4, 1: .4, 2: .6, 3: .9, 4: 1.15, 5: 1.15, 6: .4},
    "arpa": {10: .4, 11: .5, 12: .4, 1: .4, 2: .6, 3: .9, 4: 1.15, 5: .8},
    "qargidali": {5: .4, 6: .8, 7: 1.2, 8: 1.2, 9: .7},
    "pomidor": {4: .6, 5: .8, 6: 1.15, 7: 1.15, 8: 1.0, 9: .8},
    "yemis": {5: .5, 6: .9, 7: 1.0, 8: .8},
    "uzum": {4: .3, 5: .5, 6: .7, 7: .8, 8: .8, 9: .6, 10: .45},
    "seker-cugunduru": {4: .4, 5: .7, 6: 1.1, 7: 1.2, 8: 1.2, 9: 1.0, 10: .7},
}
RAW = {"pambiq": 70, "bugda": 60, "arpa": 60, "qargidali": 55, "pomidor": 35, "yemis": 40, "uzum": 60, "seker-cugunduru": 55}
_cache = {}


def weather(lat, lon):
    """Daily ET0 and rain, 14 past + 10 coming days (Open-Meteo forecast), cached 3 h per field."""
    key = (round(lat, 2), round(lon, 2))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < 3 * 3600:
        return hit[1]
    r = httpx.get("https://api.open-meteo.com/v1/forecast", timeout=60, params={
        "latitude": lat, "longitude": lon, "daily": "et0_fao_evapotranspiration,precipitation_sum,temperature_2m_max",
        "past_days": 14, "forecast_days": 10, "timezone": "Asia/Baku"})
    r.raise_for_status()
    d = r.json()["daily"]
    out = [{"date": t, "et0": e or 0.0, "rain": p or 0.0, "tmax": tx} for t, e, p, tx in
           zip(d["time"], d["et0_fao_evapotranspiration"], d["precipitation_sum"], d["temperature_2m_max"])]
    _cache[key] = (time.time(), out)
    return out


def plan(farm, salt_days, last_irrigation=None, today=None):
    """salt_days: {date: 'green'|'orange'|'red'} at the farm's pump (empty when the farm does not use Kür water)."""
    today = today or date.today().isoformat()
    crop = next((c for c in farm.get("crops", []) if c in KC), None)
    if crop is None or farm.get("water_source") == "none":
        return None
    wx = weather(farm["lat"], farm["lon"])
    start = last_irrigation if last_irrigation and last_irrigation >= wx[0]["date"] else wx[0]["date"]
    raw = RAW[crop]
    deficit, days, nxt = 0.0, [], None
    for w in wx:
        if w["date"] < start:
            continue
        kc = KC[crop].get(int(w["date"][5:7]), 0)
        etc = kc * w["et0"]
        if w["date"] > start:
            deficit = max(0.0, deficit + etc - 0.8 * w["rain"])
        need = w["date"] >= today and deficit >= raw
        days.append({"date": w["date"], "etc": round(etc, 1), "rain": round(w["rain"], 1), "deficit": round(deficit, 1),
                     "salt": salt_days.get(w["date"], "green") if salt_days else None, "need": need, "kc": kc})
        if need and nxt is None:
            nxt = {"date": w["date"], "mm": round(deficit), "moved": None}
    in_season = any(d["kc"] > 0 for d in days if d["date"] >= today)
    if nxt and salt_days:
        fresh = [d["date"] for d in days if d["date"] >= today and d["salt"] == "green"]
        if salt_days.get(nxt["date"], "green") != "green":
            before = [d for d in fresh if d < nxt["date"]]
            after = [d for d in fresh if d > nxt["date"]]
            new = before[-1] if before else (after[0] if after else None)
            nxt["moved"] = {"from": nxt["date"], "why": "salt"} if new else {"from": nxt["date"], "why": "no_fresh_day"}
            if new:
                nxt["date"] = new
    for d in days:
        d["irrigate"] = bool(nxt and d["date"] == nxt["date"])
    if nxt:
        nxt["m3_ha"] = nxt["mm"] * 10
        nxt["salt"] = salt_days.get(nxt["date"], "green") if salt_days else None
    week = [d for d in days if d["date"] >= today][:7]
    return {"crop": crop, "raw_mm": raw, "next": nxt, "in_season": in_season, "approx": not last_irrigation,
            "last_irrigation": last_irrigation, "today_deficit": next((d["deficit"] for d in days if d["date"] == today), None),
            "week": week, "rain_7d": round(sum(d["rain"] for d in week), 1), "use_7d": round(sum(d["etc"] for d in week), 1)}
