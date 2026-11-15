"""Continuous monitoring: checks every farm against the live 16-day forecast and against how wrong
earlier forecasts turned out, stores alerts with practical advice and sends (simulated) SMS for high risk."""
import asyncio
import re
import json
import logging
from datetime import date, timedelta

from . import sms
from .db import connect, rows, tx
from .weather import forecast, snapshot

log = logging.getLogger("alerts")
HORIZON = 7


def _crops(con, farm_id):
    return rows(con, "SELECT c.id, c.name, c.eco, c.perennial FROM farm_crops fc JOIN crops c ON c.id=fc.crop_id "
                     "WHERE fc.farm_id=?", farm_id)


def _rules(farm, crops, fc, today):
    d = fc["daily"]
    out = []
    month = today.month
    names = ", ".join(c["name"] for c in crops) or "crops"
    ecos = [json.loads(c["eco"]) if c["eco"] and c["eco"] != "null" else None for c in crops]
    # autumn-sown cereals overwinter by design, so they are not frost-tender
    tender = [c["name"] for c, e in zip(crops, ecos)
              if e and e["KTMP"] is not None and e["KTMP"] >= -2 and c["id"] not in ("bugda", "arpa")]
    for i, t in enumerate(d["time"]):
        day = date.fromisoformat(t)
        if day < today or day > today + timedelta(days=HORIZON):
            continue
        tmin, tmax = d["temperature_2m_min"][i], d["temperature_2m_max"][i]
        pr, gust = d["precipitation_sum"][i] or 0, d["wind_gusts_10m_max"][i] or 0
        if tmin is not None and tmin <= 0 and not (month in (12, 1, 2) and tmin > -8 and not tender):
            sev = "high" if tmin <= -3 or (tender and month in (3, 4, 5, 10, 11)) else "medium"
            out.append(dict(kind="frost", severity=sev, event_date=t,
                            title=f"Frost risk: {t}, night {tmin:.0f}°C",
                            body=f"{farm['name']} ({farm['rayon']}): night temperature may drop to {tmin:.1f}°C. "
                                 f"Sensitive crops: {', '.join(tender) or names}.",
                            advice="Irrigate lightly in the evening (moist soil holds heat), cover seedlings with "
                                   "fleece, prepare smudge/heaters in orchards; postpone fertilizing."))
        if tmax is not None and tmax >= 35:
            sev = "high" if tmax >= 38 else "medium"
            out.append(dict(kind="heat", severity=sev, event_date=t, title=f"Heat stress: {t}, day {tmax:.0f}°C",
                            body=f"{farm['name']}: max {tmax:.1f}°C expected, a risk during flowering and grain fill.",
                            advice="Move irrigation to early morning or evening, mulch, avoid spraying at midday; "
                                   "use shade nets on vegetables."))
        if pr >= 20:
            out.append(dict(kind="heavy rain", severity="high" if pr >= 35 else "medium", event_date=t,
                            title=f"Heavy rain: {t}, {pr:.0f} mm",
                            body=f"{farm['name']}: {pr:.0f} mm of rain forecast in one day.",
                            advice="Clear drainage ditches, hold spraying and nitrogen until after the rain, "
                                   "harvest anything ready beforehand."))
        if gust >= 60:
            out.append(dict(kind="wind", severity="high" if gust >= 80 else "medium", event_date=t,
                            title=f"Strong wind: {t}, gusts {gust:.0f} km/h",
                            body=f"{farm['name']}: wind gusts may reach {gust:.0f} km/h.",
                            advice="Secure greenhouse covers, check stakes and trellises, postpone pesticide spraying."))
    # dry spell: little rain, dry topsoil and high evaporative demand in the next 7 days
    idx = [i for i, t in enumerate(d["time"]) if today <= date.fromisoformat(t) <= today + timedelta(days=6)]
    if idx and 4 <= month <= 9:
        rain = sum(d["precipitation_sum"][i] or 0 for i in idx)
        et0 = sum(d["et0_fao_evapotranspiration"][i] or 0 for i in idx)
        sm = [d["soil_moisture"][i] for i in idx if d["soil_moisture"][i] is not None]
        if rain < 3 and et0 > 30 and sm and min(sm) < 0.18:
            out.append(dict(kind="drought", severity="medium", event_date=d["time"][idx[0]],
                            title="Dry spell: no rain in the next 7 days",
                            body=f"7-day rain {rain:.1f} mm, evapotranspiration (ET₀) {et0:.0f} mm, "
                                 f"soil moisture {min(sm):.2f} m³/m³.",
                            advice=f"Plan about {et0 - rain:.0f} mm of irrigation (≈{(et0 - rain) * 10:.0f} m³/ha); "
                                   "drip irrigation cuts losses."))
    return out


def _forecast_error(con, rayon_id, fc, today, since=None):
    """Compare forecasts issued 2+ days ago with what the model now reports for the past days
    (only days after the farm was added: a new farm should not get news about the days before it existed)."""
    d = fc["daily"]
    out = []
    for i, t in enumerate(d["time"]):
        day = date.fromisoformat(t)
        if not (today - timedelta(days=2) <= day < today) or (since and day < since):
            continue
        snap = con.execute("SELECT * FROM forecast_snapshots WHERE rayon_id=? AND target=? AND issued<=? "
                           "ORDER BY issued LIMIT 1", (rayon_id, t, (day - timedelta(days=2)).isoformat())).fetchone()
        if not snap:
            continue
        dt = abs((d["temperature_2m_min"][i] or 0) - (snap["tmin"] or 0))
        dp = abs((d["precipitation_sum"][i] or 0) - (snap["precip"] or 0))
        if dt >= 4 or dp >= 15:
            out.append(dict(kind="forecast error", severity="medium", event_date=t,
                            title=f"Forecast missed: {t}",
                            body=f"Forecast issued {snap['issued']}: min {snap['tmin']:.0f}°C, {snap['precip']:.0f} mm. "
                                 f"Actual: min {d['temperature_2m_min'][i]:.0f}°C, {d['precipitation_sum'][i]:.0f} mm.",
                            advice="Re-check the next days against the updated forecast and adjust irrigation and "
                                   "spraying schedules."))
    return out


def _fires(con, farm):
    """NASA FIRMS hot spots of the last 24 h within 10 km of the farm (one alert per day, nearest fire)."""
    from .fires import near
    lat, lon = farm["lat"] or farm["r_lat"], farm["lon"] or farm["r_lon"]
    fs = [f for f in near(con, lat, lon, 10) if f["days"] < 3]   # skip persistent industrial hot spots
    if not fs:
        return []
    f = fs[0]
    where = "your farm point" if farm["lat"] else f"the {farm['rayon']} centre (set the farm location for precise alerts)"
    return [dict(kind="fire", severity="high" if f["km"] <= 3 else "medium", event_date=f["acq"][:10],
                 title=f"Fire detected {f['km']:.0f} km from {farm['name']}",
                 body=f"{len(fs)} satellite fire detection(s) within 10 km of {where} in the last 24 h; nearest "
                      f"{f['km']} km, {f['sat']} at {f['acq'][11:16]} UTC (NASA FIRMS).",
                 advice="Check the field and the wind direction; keep a ploughed firebreak around crops and stacks; "
                        "do not burn stubble; call 112 if the fire is moving towards you.")]


def _salt(con, farm):
    """Salt water at the farm's pump, told only when the situation changes:
       warn  - fresh today, salty within 2 days  -> irrigate and fill storage now
       salty - salty at the pump now             -> stop pumping
       fresh - fresh again after warn/salty      -> you can irrigate"""
    from . import kur
    if farm.get("water_source") not in ("kur", "canal") or farm.get("pump_km") is None:
        return []
    st = kur.cached()
    s = kur.for_km(farm["pump_km"], st) if st else None
    if not s:
        return []
    soon = [d for d in s["days"] if st["today"] < d["date"] <= (date.today() + timedelta(days=2)).isoformat()]
    # one farmer's report alone never triggers an SMS; the model or two reports do
    if s.get("reported", 0) < 2 and s.get("model_level") == "green":
        s = {**s, "level": "green"}
    new = "salty" if s["level"] == "red" else "warn" if any(d["level"] == "red" for d in soon) or s["level"] == "orange" else "fresh"
    row_ = con.execute("SELECT state FROM farm_salt_state WHERE farm_id=?", (farm["id"],)).fetchone()
    old = row_[0] if row_ else "fresh"
    if old == "salty" and new == "warn":
        new = "salty"                    # after "salty" the next message is only "fresh again"
    if new == "fresh" and old in ("warn", "salty") and any(d["level"] != "green" for d in soon):
        new = old                        # "fresh again" only when the next 2 days are clear too (no flip-flop SMS)
    if new == old:
        return []
    con.execute("INSERT OR REPLACE INTO farm_salt_state(farm_id, state, at) VALUES(?,?,datetime('now'))", (farm["id"], new))
    con.commit()
    if new == "fresh" and old == "fresh":
        return []
    km = farm["pump_km"]
    first = s.get("first_red") or st["today"]
    if new == "warn":
        return [dict(kind="salt warn", severity="medium", event_date=first, title=f"Salt water expected at km {km:.0f} on {first}",
                     body="Weak river flow and sea wind will push Caspian water up the Kür.",
                     advice="Irrigate now and fill your pond; stop pumping when salt arrives.", when=first, fresh=s.get("fresh_again"))]
    if new == "salty":
        return [dict(kind="salt water", severity="high", event_date=st["today"], title=f"Salt water at your pump (km {km:.0f})",
                     body="Caspian water has reached your intake.", advice="Do not pump from the Kür. Use stored water.",
                     fresh=s.get("fresh_again"))]
    return [dict(kind="salt clear", severity="medium", event_date=st["today"], title=f"The Kür is fresh again at km {km:.0f}",
                 body="Fresh water from upstream pushed the sea water back.", advice="You can irrigate again.")]


def _irrigate(con, farm, crops):
    """Reminder the day before (and on the day of) a planned irrigation from the field's water balance."""
    from . import kur, plan
    st = kur.cached()
    salt = {}
    if farm.get("water_source") in ("kur", "canal") and farm.get("pump_km") is not None and st:
        s = kur.for_km(farm["pump_km"], st)
        salt = {d["date"]: d["level"] for d in s["days"]} if s else {}
    last = con.execute("SELECT max(day) FROM farm_irrigations WHERE farm_id=?", (farm["id"],)).fetchone()[0]
    f = {**farm, "crops": [c["id"] for c in crops]}
    try:
        p = plan.plan(f, salt, last)
    except Exception:  # noqa: BLE001 - forecast unavailable
        return []
    n = p and p["next"]
    if not n or n["date"] > (date.today() + timedelta(days=1)).isoformat():
        return []
    return [dict(kind="irrigate", severity="medium", event_date=n["date"], title=f"Irrigate on {n['date']}: about {n['mm']} mm",
                 body=f"The field has used about {n['mm']} mm since the last irrigation; {n['m3_ha']} m3 per hectare brings it back.",
                 advice="Irrigate early in the morning." + (" The Kür is fresh at your pump that day." if n.get("salt") == "green" else ""),
                 mm=n["mm"], m3=n["m3_ha"], salt=n.get("salt"))]


def _satellite_drought(con, farm):
    """NASA satellites agree the area is drier than normal: SMAP root-zone moisture below its same-day normal and
    MODIS NDVI below its same-month normal."""
    s = {r["product"]: r for r in rows(con, "SELECT * FROM sat_obs WHERE rayon_id=?", farm["rayon_id"])}
    sm, nd = s.get("smap"), s.get("ndvi")
    if not sm or not nd or sm["normal"] is None or nd["normal"] in (None, 0):
        return []
    dm, dn = sm["value"] - sm["normal"], nd["value"] / nd["normal"] - 1
    if dm > -0.03 or dn > -0.08:
        return []
    return [dict(kind="satellite drought", severity="high" if dm < -0.06 and dn < -0.15 else "medium",
                 event_date=sm["date"], title=f"Satellites see a dry spell in {farm['rayon']}",
                 body=f"SMAP root-zone soil moisture {sm['value']:.2f} m³/m³ ({dm:+.2f} vs normal for the date); "
                      f"MODIS vegetation index {dn * 100:+.0f}% vs the same month of the last 5 years.",
                 advice="Check soil moisture in the field before the next irrigation turn; prioritise young orchards "
                        "and vegetables; mulch to cut evaporation.")]


async def check_farm(farm: dict, send_sms=True) -> list[dict]:
    lat, lon = farm["lat"] or farm["r_lat"], farm["lon"] or farm["r_lon"]
    fc = await forecast(lat, lon)
    snapshot(farm["rayon_id"], fc)
    today = date.today()
    con = connect()
    try:
        crops = _crops(con, farm["id"])
        found = _rules(farm, crops, fc, today) + _forecast_error(con, farm["rayon_id"], fc, today,
                                                                     date.fromisoformat(str(farm["created_at"])[:10]))
        found += _satellite_drought(con, farm) + _fires(con, farm) + _salt(con, farm) + _irrigate(con, farm, crops)
    finally:
        con.close()
    created = []
    with tx() as con:
        for a in found:
            dedup = f"{a['kind']}:{a['event_date']}"
            cur = con.execute("INSERT OR IGNORE INTO alerts(user_id, farm_id, kind, severity, title, body, advice, "
                              "event_date, dedup) VALUES(?,?,?,?,?,?,?,?,?)",
                              (farm["user_id"], farm["id"], a["kind"], a["severity"], a["title"], a["body"],
                               a["advice"], a["event_date"], dedup))
            if cur.rowcount:
                a["id"] = cur.lastrowid
                created.append(a)
    for a in created:
        salt = a["kind"] in ("salt water", "salt warn", "salt clear", "irrigate")
        if send_sms and (a["severity"] == "high" or salt) and farm["sms_alerts"]:
            st = sms.send(farm["user_id"], farm["phone"], sms_az(a, farm))
            with tx() as con:
                con.execute("UPDATE alerts SET sms_status=? WHERE id=?", (st, a["id"]))
    return created


_TR = str.maketrans("əƏşŞçÇğĞıİöÖüÜ", "eEsScCgGiIoOuU")


def sms_az(a, farm):
    """Short Azerbaijani SMS, written in plain Latin letters so it fits one GSM message on any phone."""
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*(°C|mm|km/h|km)", a["title"])
    v = m.group(1) if m else ""
    d = a["event_date"]
    name = farm["name"]
    km = farm.get("pump_km")
    t = {
        "salt warn": f"{name}: {a.get('when', d)} Kürün suyu azalır, Xəzərin duzlu suyu bölgənə gələ bilər. İNDİ sula və hovuzu doldur.",
        "salt water": f"{name}: bölgəndə Kürün suyu artıq DUZLUDUR. Sulamaq torpağa ziyandır — nasosu işlətmə."
                      + (f" Təxminən {a['fresh']} şirinləşəcək, xəbər verəcəyik." if a.get("fresh") else " Şirinləşəndə xəbər verəcəyik."),
        "salt clear": f"{name}: Kürün suyu yenidən ŞİRİNDİR. Sulaya bilərsən.",
        "irrigate": f"{name}: {d} səhər tezdən sula, təxminən {a.get('mm')} mm ({a.get('m3')} m³/ha)."
                    + (" Kürün suyu o gün şirindir." if a.get("salt") == "green" else ""),
        "frost": f"{name}: {d} gecə şaxta ({v}°C). Axşam yüngül suvar, şitilləri ört, gübrələməni təxirə sal.",
        "heat": f"{name}: {d} isti ({v}°C). Səhər tezdən suvar, günorta çiləmə etmə.",
        "heavy rain": f"{name}: {d} güclü yağış ({v} mm). Arxları təmizlə, gübrə və çiləməni təxirə sal.",
        "wind": f"{name}: {d} güclü külək ({v} km/saat). Örtükləri bərkit, çiləməni təxirə sal.",
        "drought": f"{name}: 7 gün yağış gözlənilmir. Suvarmanı planla, torpağı örtüklə.",
        "fire": f"{name}: yaxınlıqda yanğın aşkarlandı ({v} km). Küləyin istiqamətinə bax, lazım olsa 112.",
        "satellite drought": f"{name}: peyk torpağın quruduğunu göstərir. Suvarmadan əvvəl torpağı yoxla.",
        "forecast error": f"{name}: hava proqnozu dəyişib. Növbəti günlərin proqnozuna yenidən bax.",
    }.get(a["kind"], f"{name}: {a['title']}")
    return ("Field Shift - " + t).translate(_TR)


FARM_SQL = """SELECT f.*, r.name rayon, r.lat r_lat, r.lon r_lon, u.phone, u.sms_alerts FROM farms f
              JOIN rayons r ON r.id=f.rayon_id JOIN users u ON u.id=f.user_id"""


async def check_user(uid: int):
    con = connect()
    try:
        farms = rows(con, FARM_SQL + " WHERE f.user_id=?", uid)
    finally:
        con.close()
    out, failed = [], []
    for f in farms:
        try:
            out += await check_farm(f)
        except Exception as e:  # noqa: BLE001 - one unreachable forecast must not fail the whole check
            log.warning("farm %s check failed: %s", f["id"], e)
            failed.append(f["name"])
    return out, failed


async def loop(interval=3 * 3600):
    while True:
        try:
            con = connect()
            farms = rows(con, FARM_SQL)
            con.close()
            for f in farms:
                try:
                    await check_farm(f)
                except Exception as e:  # noqa: BLE001
                    log.warning("farm %s check failed: %s", f["id"], e)
        except Exception as e:  # noqa: BLE001
            log.warning("alert loop failed: %s", e)
        await asyncio.sleep(interval)
