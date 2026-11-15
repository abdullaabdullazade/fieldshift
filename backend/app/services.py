"""Read-side domain logic shared by the HTTP API and the AI chat tools."""
import json
import statistics as st

from .db import connect, row, rows

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def meta():
    con = connect()
    try:
        m = {r["key"]: json.loads(r["value"]) for r in rows(con, "SELECT * FROM meta")}
        m["counts"] = {
            "rayons": con.execute("SELECT count(*) FROM rayons WHERE iso3='AZE'").fetchone()[0],
            "provinces": con.execute("SELECT count(*) FROM rayons WHERE level='province'").fetchone()[0],
            "countries": con.execute("SELECT count(*) FROM countries").fetchone()[0],
            "crops": con.execute("SELECT count(*) FROM crops").fetchone()[0],
            "yield_rows": con.execute("SELECT count(*) FROM yields").fetchone()[0],
            "climate_years": con.execute("SELECT count(*) FROM climate_year").fetchone()[0],
            "country_yield_rows": con.execute("SELECT count(*) FROM country_yields").fetchone()[0],
            "farmers": con.execute("SELECT count(*) FROM users WHERE role='farmer'").fetchone()[0],
            "reviews": con.execute("SELECT count(*) FROM reviews").fetchone()[0],
            "demo_users": con.execute("SELECT count(*) FROM users WHERE is_demo=1").fetchone()[0],
        }
        return m
    finally:
        con.close()


def find_rayon(con, q: str):
    q = (q or "").strip().lower()
    r = row(con, "SELECT * FROM rayons WHERE id=?", q)
    if r:
        return r
    for cand in rows(con, "SELECT * FROM rayons"):
        if q and (q in cand["name"].lower() or q in cand["name_az"].lower() or q in cand["id"]):
            return cand
    return None


def find_crop(con, q: str):
    q = (q or "").strip().lower()
    r = row(con, "SELECT * FROM crops WHERE id=?", q)
    if r:
        return r
    for c in rows(con, "SELECT * FROM crops"):
        if q and (q in c["name"].lower() or q in c["name_az"].lower()):
            return c
    return None


def period_compare(con, rid):
    """1981-1990 vs 2016-2025 averages (the deck's 'past vs now' table) for one rayon."""
    keys = ["tmean", "hot35", "frost", "ffs", "last_frost", "gdd", "precip", "gwetroot"]
    a = row(con, "SELECT " + ",".join(f"avg({k}) {k}" for k in keys) +
            " FROM climate_year WHERE rayon_id=? AND year BETWEEN 1981 AND 1990", rid)
    b = row(con, "SELECT " + ",".join(f"avg({k}) {k}" for k in keys) +
            " FROM climate_year WHERE rayon_id=? AND year BETWEEN 2016 AND 2025", rid)
    return {k: {"past": a[k], "now": b[k], "delta": (b[k] - a[k]) if a[k] is not None else None} for k in keys}


def rayon_rating(con, rid):
    r = row(con, "SELECT avg(rv.rating) avg, count(*) n FROM reviews rv JOIN users u ON u.id=rv.farmer_id "
                 "WHERE u.id IN (SELECT user_id FROM farms WHERE rayon_id=?)", rid)
    return {"avg": round(r["avg"], 2) if r["avg"] else None, "count": r["n"]}


def rayon_profile(rid):
    con = connect()
    try:
        r = row(con, "SELECT * FROM rayons WHERE id=?", rid)
        if not r:
            return None
        r["soil"] = row(con, "SELECT * FROM soil WHERE rayon_id=?", rid)
        r["compare"] = period_compare(con, rid)
        r["rating"] = rayon_rating(con, rid)
        r["farmers"] = con.execute("SELECT count(DISTINCT user_id) FROM farms WHERE rayon_id=?", (rid,)).fetchone()[0]
        r["country"] = row(con, "SELECT * FROM countries WHERE iso3=?", r["iso3"])
        from .satellite import for_unit
        r["satellite"] = for_unit(con, rid)
        from .fires import for_unit as fires_for_unit
        r["fires"] = fires_for_unit(con, r)
        if r["level"] == "province":
            last = con.execute("SELECT max(year) FROM country_yields WHERE iso3=? AND production>0",
                               (r["iso3"],)).fetchone()[0]
            r["top_crops"] = rows(con, """
                SELECT y.crop_id, c.name, y.production, y.yield, w.med nat_yield FROM country_yields y
                JOIN crops c ON c.id=y.crop_id LEFT JOIN (SELECT crop_id, year, avg(yield) med FROM country_yields
                WHERE yield>0 GROUP BY crop_id, year) w ON w.crop_id=y.crop_id AND w.year=y.year
                WHERE y.iso3=? AND y.year=? AND y.production>0 AND y.crop_id!='terevez'
                ORDER BY y.production DESC LIMIT 8""", r["iso3"], last)
            r["stat_year"], r["stat_scope"] = last, "country"
            return r
        r["stat_scope"] = "district"
        last = con.execute("SELECT max(year) FROM yields WHERE rayon_id=?", (rid,)).fetchone()[0]
        r["top_crops"] = rows(con, """
            SELECT y.crop_id, c.name, y.production, y.yield, n.yield nat_yield FROM yields y
            JOIN crops c ON c.id=y.crop_id LEFT JOIN national_yields n ON n.crop_id=y.crop_id AND n.year=y.year
            WHERE y.rayon_id=? AND y.year=? AND y.production>0 AND y.crop_id!='terevez'
            ORDER BY y.production DESC LIMIT 8""", rid, last)
        r["stat_year"] = last
        return r
    finally:
        con.close()


def recommendations(rid, irrigated=True, limit=None):
    """Blend of FAO ECOCROP suitability (NASA climate + SoilGrids pH), the rayon's real DSK yield record
    relative to the national level, and CMIP6 2041-2050 suitability."""
    con = connect()
    try:
        col = "irrigated" if irrigated else "rainfed"
        crops = rows(con, "SELECT * FROM crops WHERE eco != 'null' ORDER BY ord")
        meta_r = row(con, "SELECT iso3, level FROM rayons WHERE id=?", rid) or {"iso3": "AZE", "level": "district"}
        province, iso3 = meta_r["level"] == "province", meta_r["iso3"]
        fao_last = con.execute("SELECT max(year) FROM country_yields WHERE yield>0").fetchone()[0] or 0
        out = []
        for c in crops:
            now = row(con, f"SELECT {col} s, temp, rain, ph, best_month FROM suitability "
                           "WHERE rayon_id=? AND crop_id=? AND period='2016-2025'", rid, c["id"])
            past = row(con, f"SELECT {col} s FROM suitability WHERE rayon_id=? AND crop_id=? AND period='1981-2010'",
                       rid, c["id"])
            fut = row(con, f"SELECT {col} s FROM suitability WHERE rayon_id=? AND crop_id=? AND period='2041-2050'",
                      rid, c["id"])
            if not now:
                continue
            if province:
                y = row(con, """SELECT avg(y.yield) ry, avg(w.m) ny, count(*) n FROM country_yields y
                        JOIN (SELECT year, avg(yield) m FROM country_yields WHERE crop_id=? AND yield>0 GROUP BY year) w
                        ON w.year=y.year WHERE y.iso3=? AND y.crop_id=? AND y.year>=?-4 AND y.yield>0""",
                        c["id"], iso3, c["id"], fao_last)
            else:
                y = row(con, """SELECT avg(y.yield) ry, avg(n.yield) ny, count(*) n, sum(y.production) prod FROM yields y
                        JOIN national_yields n ON n.crop_id=y.crop_id AND n.year=y.year
                        WHERE y.rayon_id=? AND y.crop_id=? AND y.year>=2021 AND y.yield>0""", rid, c["id"])
            rel = (y["ry"] / y["ny"]) if y and y["ry"] and y["ny"] else None
            # no official record in this rayon = unproven locally: neutral-low evidence instead of skipping
            yscore = 0.35 if rel is None else max(0.0, min(1.0, (rel - 0.4) / 1.0))
            fs = fut["s"] if fut else None
            parts = [(now["s"], 0.45), (yscore, 0.35), (fs, 0.20)]
            wsum = sum(w for v, w in parts if v is not None)
            score = sum(v * w for v, w in parts if v is not None) / wsum
            out.append({
                "crop_id": c["id"], "name": c["name"], "group": c["grp"], "score": round(score * 100),
                "suit_now": round(now["s"] * 100), "suit_past": round(past["s"] * 100) if past else None,
                "suit_2045": round(fs * 100) if fs is not None else None,
                "temp": round(now["temp"] * 100), "rain": round(now["rain"] * 100), "ph": round(now["ph"] * 100),
                "best_month": now["best_month"], "yield_rel": round(rel, 2) if rel else None,
                "grown_here": bool(y and y["n"]), "yield_avg": round(y["ry"], 1) if y and y["ry"] else None,
                "perennial": bool(c["perennial"]), "evidence": "country" if province else "district",
            })
        out.sort(key=lambda r: -r["score"])
        return out[:limit] if limit else out
    finally:
        con.close()


def yield_series(rid, cid):
    con = connect()
    try:
        r = row(con, "SELECT iso3, level FROM rayons WHERE id=?", rid)
        if r and r["level"] == "province":
            series = rows(con, """SELECT y.year, y.yield, y.production, w.m nat_yield FROM country_yields y
                    LEFT JOIN (SELECT year, avg(yield) m FROM country_yields WHERE crop_id=? AND yield>0 GROUP BY year) w
                    ON w.year=y.year WHERE y.iso3=? AND y.crop_id=? AND y.yield>0 ORDER BY y.year""", cid, r["iso3"], cid)
            return {"series": series, "forecast": [], "model": None, "scope": "country"}
        series = rows(con, """SELECT y.year, y.yield, y.production, n.yield nat_yield FROM yields y
                LEFT JOIN national_yields n ON n.crop_id=y.crop_id AND n.year=y.year
                WHERE y.rayon_id=? AND y.crop_id=? ORDER BY y.year""", rid, cid)
        fc = rows(con, "SELECT year, pred, lo, hi FROM yield_forecast WHERE rayon_id=? AND crop_id=? ORDER BY year",
                  rid, cid)
        m = row(con, "SELECT * FROM model_metrics WHERE crop_id=?", cid)
        if m:
            m.update(json.loads(m.pop("importances")))
        return {"series": series, "forecast": fc, "model": m}
    finally:
        con.close()


def ranking(cid, year=None, metric="yield"):
    """Rayons ranked for a crop; quartile categories (Leader / Good / Average / Low)."""
    con = connect()
    try:
        if not year:
            year = con.execute("SELECT max(year) FROM yields WHERE crop_id=? AND yield>0", (cid,)).fetchone()[0]
        col = "production" if metric == "production" else "yield"
        data = rows(con, f"""SELECT y.rayon_id, r.name, r.econ, y.yield, y.production,
                (SELECT yield FROM yields p WHERE p.rayon_id=y.rayon_id AND p.crop_id=y.crop_id AND p.year=y.year-1)
                prev_yield FROM yields y JOIN rayons r ON r.id=y.rayon_id
                WHERE y.crop_id=? AND y.year=? AND y.{col}>0 ORDER BY y.{col} DESC""", cid, year)
        n = len(data)
        for i, d in enumerate(data):
            q = i / max(1, n)
            d["rank"] = i + 1
            d["category"] = "Leader" if q < 0.25 else "Good" if q < 0.5 else "Average" if q < 0.75 else "Low"
            d["change"] = (d["yield"] / d["prev_yield"] - 1) if d["yield"] and d["prev_yield"] else None
            d["rating"] = rayon_rating(con, d["rayon_id"])
        nat = row(con, "SELECT * FROM national_yields WHERE crop_id=? AND year=?", cid, year)
        vals = [d[col] for d in data if d[col]]
        return {"year": year, "metric": metric, "national": nat, "rows": data,
                "median": st.median(vals) if vals else None}
    finally:
        con.close()


def country_profile(iso3):
    con = connect()
    try:
        c = row(con, "SELECT * FROM countries WHERE iso3=?", iso3)
        if not c:
            return None
        c["units"] = rows(con, "SELECT id, name, lat, lon, area_km2 FROM rayons WHERE iso3=? ORDER BY name", iso3)
        keys = ["tmean", "hot35", "frost", "ffs", "precip"]
        a = row(con, "SELECT " + ",".join(f"avg({k}) {k}" for k in keys) + """ FROM climate_year y JOIN rayons r
                ON r.id=y.rayon_id WHERE r.iso3=? AND y.year BETWEEN 1981 AND 1990""", iso3)
        b = row(con, "SELECT " + ",".join(f"avg({k}) {k}" for k in keys) + """ FROM climate_year y JOIN rayons r
                ON r.id=y.rayon_id WHERE r.iso3=? AND y.year BETWEEN 2016 AND 2025""", iso3)
        c["compare"] = {k: {"past": a[k], "now": b[k], "delta": (b[k] - a[k]) if a[k] is not None and b[k] is not None
                            else None} for k in keys}
        p = row(con, """SELECT avg(p.tmean) t, avg(p.hot35) hot FROM projection_year p JOIN rayons r ON r.id=p.rayon_id
                     WHERE r.iso3=? AND p.year BETWEEN 2041 AND 2050""", iso3)
        c["future"] = p
        last = con.execute("SELECT max(year) FROM country_yields WHERE iso3=? AND production>0", (iso3,)).fetchone()[0]
        c["top_crops"] = rows(con, """SELECT y.crop_id, c.name, y.production, y.yield FROM country_yields y
                JOIN crops c ON c.id=y.crop_id WHERE y.iso3=? AND y.year=? AND y.production>0 AND y.crop_id!='terevez'
                ORDER BY y.production DESC LIMIT 10""", iso3, last)
        c["stat_year"] = last
        return c
    finally:
        con.close()


def world_ranking(cid, year=None, metric="yield"):
    """Countries ranked for a crop from FAOSTAT, quartile categories, Near-Azerbaijan countries flagged."""
    con = connect()
    try:
        col = "production" if metric == "production" else "yield"
        if not year:
            year = con.execute("SELECT max(year) FROM country_yields WHERE crop_id=? AND yield>0", (cid,)).fetchone()[0]
        data = rows(con, f"""SELECT y.iso3, c.name, c.grp, c.continent, y.yield, y.production, y.area,
                (SELECT yield FROM country_yields p WHERE p.iso3=y.iso3 AND p.crop_id=y.crop_id AND p.year=y.year-1)
                prev_yield FROM country_yields y JOIN countries c ON c.iso3=y.iso3
                WHERE y.crop_id=? AND y.year=? AND y.{col}>0 ORDER BY y.{col} DESC""", cid, year)
        n = len(data)
        for i, d in enumerate(data):
            q = i / max(1, n)
            d["rank"] = i + 1
            d["category"] = "Leader" if q < 0.25 else "Good" if q < 0.5 else "Average" if q < 0.75 else "Low"
            d["change"] = (d["yield"] / d["prev_yield"] - 1) if d["yield"] and d["prev_yield"] else None
        vals = sorted(d[col] for d in data if d[col])
        return {"year": year, "metric": metric, "rows": data, "median": vals[len(vals) // 2] if vals else None,
                "source": "FAOSTAT"}
    finally:
        con.close()
