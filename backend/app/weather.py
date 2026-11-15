"""Live forecasts from Open-Meteo (ECMWF/ICON/GFS best-match), cached in memory for 30 minutes."""
import time
from datetime import date

import httpx

from .db import tx

_cache: dict[tuple, tuple[float, dict]] = {}
TTL = 1800
DAILY = ("temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,"
         "wind_speed_10m_max,wind_gusts_10m_max,et0_fao_evapotranspiration,weather_code,"
         "soil_moisture_0_to_7cm_mean")
HOURLY_SOIL = "soil_temperature_6cm,soil_moisture_3_to_9cm"


async def forecast(lat: float, lon: float, days: int = 16) -> dict:
    key = (round(lat, 2), round(lon, 2), days)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    params = {"latitude": lat, "longitude": lon, "daily": DAILY.replace(",soil_moisture_0_to_7cm_mean", ""),
              "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,weather_code",
              "hourly": HOURLY_SOIL, "timezone": "Asia/Baku", "forecast_days": days, "past_days": 2}
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get("https://api.open-meteo.com/v1/forecast", params=params)
        r.raise_for_status()
        data = r.json()
    # daily soil moisture/temperature means from hourly
    h = data.get("hourly", {})
    soil = {}
    for i, t in enumerate(h.get("time", [])):
        d = t[:10]
        s = soil.setdefault(d, {"m": [], "t": []})
        if h["soil_moisture_3_to_9cm"][i] is not None:
            s["m"].append(h["soil_moisture_3_to_9cm"][i])
        if h["soil_temperature_6cm"][i] is not None:
            s["t"].append(h["soil_temperature_6cm"][i])
    d = data["daily"]
    d["soil_moisture"] = [round(sum(soil[x]["m"]) / len(soil[x]["m"]), 3) if soil.get(x, {}).get("m") else None
                          for x in d["time"]]
    d["soil_temp"] = [round(sum(soil[x]["t"]) / len(soil[x]["t"]), 1) if soil.get(x, {}).get("t") else None
                      for x in d["time"]]
    data.pop("hourly", None)
    data["fetched_at"] = int(time.time())
    _cache[key] = (time.time(), data)
    return data


def snapshot(rayon_id: str, data: dict):
    """Store today's issued forecast so later we can measure forecast error against what happened."""
    issued = date.today().isoformat()
    d = data["daily"]
    with tx() as con:
        for i, t in enumerate(d["time"]):
            if t <= issued:
                continue
            con.execute("INSERT OR IGNORE INTO forecast_snapshots VALUES(?,?,?,?,?,?)",
                        (rayon_id, issued, t, d["temperature_2m_min"][i], d["temperature_2m_max"][i],
                         d["precipitation_sum"][i]))


WMO = {0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Rime fog",
       51: "Drizzle", 53: "Drizzle", 55: "Heavy drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
       66: "Freezing rain", 67: "Freezing rain", 71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
       80: "Showers", 81: "Showers", 82: "Heavy showers", 85: "Snow showers", 86: "Snow showers",
       95: "Thunderstorm", 96: "Thunderstorm, hail", 99: "Severe hail"}
