"""Load all real datasets into data/fieldshift.db and compute derived layers.

Steps: rayons + soil -> DSK yields/production -> NASA POWER annual/monthly climate ->
CMIP6 delta projections -> ECOCROP suitability (now / 2041-2050) -> yield models + forecasts.
App tables (users, reviews, feedback ...) are never touched.
"""
import json
import math
import statistics as st
import sys
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db import DATA_TABLES, DB_PATH, connect, init_schema  # noqa: E402
from etl.crops import CROPS, GROUP_EN, PERENNIAL, WINTER  # noqa: E402

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"



def num(v):
    if isinstance(v, str):
        v = v.replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- stat.gov.az
def read_stat(tbl):
    df = pd.read_excel(RAW / "stat" / f"{tbl}.xls", header=None)
    hdr = next(i for i in range(12) if (num(df.iloc[i, 2]) or 0) > 1990)
    years = [int(num(y)) if num(y) else None for y in df.iloc[hdr, 2:]]
    out = {}
    for i in range(hdr + 1, len(df)):
        name = " ".join(str(df.iloc[i, 1]).split())
        if name == "nan":
            continue
        out[name] = {y: num(df.iloc[i, 2 + k]) for k, y in enumerate(years) if y}
    return out


def load_stat(con, rayons):
    by_name = {r["name"]: r["id"] for r in rayons}
    for cid, *_rest in CROPS:
        ytbl, ptbl = _rest[3], _rest[4]
        yv, pv = read_stat(ytbl), read_stat(ptbl)
        for name, series in yv.items():
            key = name.replace(" rayonu", "")
            prod = pv.get(name, {})
            if name == "Azərbaycan Respublikası":
                for y, v in series.items():
                    if v is not None or prod.get(y) is not None:
                        con.execute("INSERT INTO national_yields VALUES(?,?,?,?)", (cid, y, v, prod.get(y)))
                continue
            rid = by_name.get(key)
            if not rid:
                continue
            for y, v in series.items():
                p = prod.get(y)
                if v is None and p is None:
                    continue
                con.execute("INSERT INTO yields VALUES(?,?,?,?,?)", (rid, cid, y, v, p))


# ---------------------------------------------------------------- NASA POWER
def load_power(rid, point_elev=None):
    """Daily NASA POWER; temperatures lapse-rate corrected from the MERRA-2 cell elevation to the point (6.5 °C/km)."""
    js = json.load(open(RAW / "power" / f"{rid}.json"))
    P = js["properties"]["parameter"]
    df = pd.DataFrame({k: pd.Series(v) for k, v in P.items()})
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df = df.replace(-999.0, np.nan)
    if point_elev is not None:
        dz = max(-1500.0, min(1500.0, float(js["geometry"]["coordinates"][2]) - point_elev))
        for col in ("T2M", "T2M_MAX", "T2M_MIN"):
            df[col] = df[col] + 0.0065 * dz
    return df


def annual(df, rid, con, last_full):
    for y, d in df.groupby(df.index.year):
        if len(d) < 300 and y != last_full + 1:
            continue
        spring = d[(d.index.month < 7) & (d.T2M_MIN < 0)]
        autumn = d[(d.index.month >= 7) & (d.T2M_MIN < 0)]
        lf = spring.index.max().dayofyear if len(spring) else 1
        ff = autumn.index.min().dayofyear if len(autumn) else 366
        gs = d[(d.index.month >= 4) & (d.index.month <= 9)]
        gdd_d = d[(d.index.month >= 4) & (d.index.month <= 10)]
        gdd = float(np.clip((gdd_d.T2M_MAX + gdd_d.T2M_MIN) / 2 - 10, 0, None).sum())
        con.execute(
            "INSERT INTO climate_year VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rid, int(y), d.T2M.mean(), d.T2M_MAX.mean(), d.T2M_MIN.mean(), int((d.T2M_MAX > 35).sum()),
             int((d.T2M_MIN < 0).sum()), d.PRECTOTCORR.sum(), d.GWETROOT.mean(), d.GWETTOP.mean(), gdd,
             int(lf), int(ff), int(ff - lf), gs.T2M.mean(), gs.PRECTOTCORR.sum(), gs.GWETROOT.mean(),
             d.RH2M.mean(), d.ALLSKY_SFC_SW_DWN.mean(), int(len(d) < 360)))


def monthly(df, a, b):
    d = df[(df.index.year >= a) & (df.index.year <= b)]
    g = d.groupby(d.index.month)
    nyears = b - a + 1
    return pd.DataFrame({"tmin": g.T2M_MIN.mean(), "tmean": g.T2M.mean(), "tmax": g.T2M_MAX.mean(),
                         "precip": g.PRECTOTCORR.sum() / nyears, "gwetroot": g.GWETROOT.mean()})


# ---------------------------------------------------------------- CMIP6 delta method
def cmip6_deltas(econ_id):
    f = RAW / "cmip6" / f"{econ_id}.json"
    if not f.exists():
        return None
    D = json.load(open(f))["daily"]
    t = pd.to_datetime(D["time"])
    models = sorted({k.split("temperature_2m_max_")[1] for k in D if k.startswith("temperature_2m_max_")})
    out = {}
    for m in models:
        df = pd.DataFrame({"tmax": D[f"temperature_2m_max_{m}"], "tmin": D[f"temperature_2m_min_{m}"],
                           "tmean": D.get(f"temperature_2m_mean_{m}"), "pr": D[f"precipitation_sum_{m}"]},
                          index=t).astype(float)
        if df.tmean.isna().all():
            df["tmean"] = (df.tmax + df.tmin) / 2
        df = df.dropna(how="all")
        if df.empty:
            continue
        out[m] = df
    return out


class Nex:
    """NASA NEX-GDDP-CMIP6 point series cached by etl.fetch_nex (per model: var -> {year: (n_rayons, days)})."""

    def __init__(self):
        d = RAW / "nex"
        self.ok = (d / "rayons.json").exists()
        if not self.ok:
            return
        self.ids = json.load(open(d / "rayons.json"))
        self.data = {}
        for mdir in sorted(p for p in d.iterdir() if p.is_dir()):
            v = {}
            for f in mdir.glob("*.npy"):
                var, yr = f.stem.split("_")
                v.setdefault(var, {})[int(yr)] = np.load(f)
            if all(k in v for k in ("tasmax", "tasmin", "pr")) and len(v["tasmax"]) >= 40:
                self.data[mdir.name] = v
        self.ok = bool(self.data)

    def models_for(self, rid):
        i = self.ids.index(rid)
        out = {}
        for m, v in self.data.items():
            frames = []
            for yr in sorted(set(v["tasmax"]) & set(v["tasmin"]) & set(v["pr"])):
                n = v["tasmax"][yr].shape[1]
                idx = pd.date_range(f"{yr}-01-01", f"{yr}-12-31", freq="D")
                if n == 365 and len(idx) == 366:
                    idx = idx[~((idx.month == 2) & (idx.day == 29))]
                if len(idx) != n:
                    continue
                tx, tn = v["tasmax"][yr][i], v["tasmin"][yr][i]
                frames.append(pd.DataFrame({"tmax": tx, "tmin": tn, "tmean": (tx + tn) / 2, "pr": v["pr"][yr][i]},
                                           index=idx))
            if frames:
                out[m] = pd.concat(frames).astype(float)
        return out


def projections(con, rid, df_power, models, b0=1995, b1=2014):
    """Annual projections 2026-2050 + monthly 2041-2050 climatology; delta method vs NASA POWER b0-b1."""
    base = df_power[(df_power.index.year >= b0) & (df_power.index.year <= b1)]
    bm = monthly(df_power, b0, b1)
    per_year, per_month = {}, []
    for m, df in models.items():
        mb = df[(df.index.year >= b0) & (df.index.year <= b1)]
        g = mb.groupby(mb.index.month)
        mb_m = pd.DataFrame({"tmax": g.tmax.mean(), "tmin": g.tmin.mean(), "tmean": g.tmean.mean(),
                             "pr": g.pr.sum() / (b1 - b0 + 1)})
        # daily delta-adjust: shift temps by monthly bias, scale precip by monthly ratio
        adj = df.copy()
        mo = adj.index.month
        for c, bc in (("tmax", "tmax"), ("tmin", "tmin"), ("tmean", "tmean")):
            adj[c] = adj[c].values + (bm[bc].values[mo - 1] - mb_m[c].values[mo - 1])
        ratio = (bm["precip"] / mb_m["pr"].replace(0, np.nan)).clip(0.2, 5).fillna(1)
        adj["pr"] = adj["pr"].values * ratio.values[mo - 1]
        fut = adj[adj.index.year >= 2026]
        for y, d in fut.groupby(fut.index.year):
            per_year.setdefault(int(y), []).append(
                (d.tmean.mean(), d.tmax.mean(), d.tmin.mean(), (d.tmax > 35).sum(), (d.tmin < 0).sum(), d.pr.sum()))
        f2 = adj[(adj.index.year >= 2041) & (adj.index.year <= 2050)]
        g2 = f2.groupby(f2.index.month)
        per_month.append(pd.DataFrame({"tmin": g2.tmin.mean(), "tmean": g2.tmean.mean(), "tmax": g2.tmax.mean(),
                                       "precip": g2.pr.sum() / 10}))
    for y, vals in per_year.items():
        a = np.array(vals, dtype=float)
        mean = a.mean(axis=0)
        con.execute("INSERT INTO projection_year VALUES(?,?,?,?,?,?,?,?,?)",
                    (rid, y, *[float(v) for v in mean], float(a[:, 0].std())))
    if per_month:
        fm = sum(per_month) / len(per_month)
        for mo, r in fm.iterrows():
            con.execute("INSERT INTO climate_month VALUES(?,?,?,?,?,?,?,?)",
                        (rid, "2041-2050", int(mo), r.tmin, r.tmean, r.tmax, r.precip, None))
    _ = base


# ---------------------------------------------------------------- ECOCROP
def trap(x, a, b, c, d):
    if x is None or any(v is None for v in (a, b, c, d)):
        return 1.0
    if x <= a or x >= d:
        return 0.0
    if b <= x <= c:
        return 1.0
    return (x - a) / (b - a) if x < b else (d - x) / (d - c)


def ecocrop(eco, clim, ph, perennial, winter=False):
    """ECOCROP (Hijmans/dismo) on monthly climatology, adapted for Azerbaijani practice:
    - temperature score = mean of monthly trapezoid scores over the growing window (dismo uses min,
      which zeroes any crop whose first month is cool);
    - perennials and winter cereals: months colder than TMIN are dormancy, not failure;
    - frost kill when mean monthly Tmin over active months < KTMP, winter kill when coldest Tmin < KTMP - 8;
    - pH acts as a correction factor (0.5..1) because 1-km SoilGrids means blur local soil management."""
    gmin, gmax = eco["GMIN"], eco["GMAX"]
    dur = 12 if perennial else max(1, min(12, round((gmin + gmax) / 2 / 30)))
    tmean, tmin, pr = clim["tmean"].tolist(), clim["tmin"].tolist(), clim["precip"].tolist()
    dormant_ok = perennial or winter
    best = (0, -1.0, 0.0)
    for start in range(12):
        months = [(start + i) % 12 for i in range(dur)]
        active = [m for m in months if tmean[m] > eco["TMIN"]] if dormant_ok else months
        if not active or (dormant_ok and len(active) * 30 < gmin * 0.8):
            continue
        ts = sum(trap(tmean[m], eco["TMIN"], eco["TOPMN"], eco["TOPMX"], eco["TMAX"]) for m in active) / len(active)
        if min(tmin[m] for m in active) < eco["KTMP"]:
            ts *= 0.3
        if dormant_ok and min(tmin) < eco["KTMP"] - 8:
            ts *= 0.3
        rain = sum(pr[m] for m in months)
        rs = trap(rain, eco["RMIN"], eco["ROPMN"], eco["ROPMX"], eco["RMAX"])
        if ts > best[1] + 1e-9 or (abs(ts - best[1]) < 1e-9 and rs > best[2]):
            best = (start + 1, ts, rs)
    month, ts, rs = best
    ts = max(ts, 0.0)
    phs = trap(ph, eco["PHMIN"], eco["PHOPMN"], eco["PHOPMX"], eco["PHMAX"])
    phf = 0.5 + 0.5 * phs
    return {"temp": ts, "rain": rs, "ph": phs, "irrigated": ts * phf, "rainfed": min(ts, rs) * phf,
            "best_month": month}


def load_ecocrop():
    import rdata
    d = rdata.read_rds(RAW / "ecocrop" / "ecocrop.rds")
    d["SCIENTNAME"] = d["SCIENTNAME"].astype(str)
    out = {}
    for c in CROPS:
        if not c[6]:
            continue
        r = d[d.SCIENTNAME == c[6]].iloc[0]
        out[c[0]] = {k: (None if pd.isna(r[k]) else float(r[k])) for k in
                     ["GMIN", "GMAX", "KTMP", "TMIN", "TOPMN", "TOPMX", "TMAX", "RMIN", "ROPMN", "ROPMX", "RMAX",
                      "PHMIN", "PHOPMN", "PHOPMX", "PHMAX"]}
        out[c[0]]["name"] = str(r["NAME"])
        out[c[0]]["sci"] = c[6]
    return out


# ---------------------------------------------------------------- yield model
CLIM_F = ["gs_tmean", "gs_precip", "hot35", "frost", "gs_gwetroot", "gdd", "last_frost"]
FEATS = [f + "_a" for f in CLIM_F] + ["rel3", "trend_r"]


def _feat(hist, c, norm_r):
    """hist: list of past yields (oldest..newest); c: climate row of target year; norm_r: rayon 1981-2015 norms."""
    lag1 = hist[-1]
    d = {"lag1": lag1, "rel3": float(np.mean(hist[-3:])) / lag1 - 1, "trend_r": (hist[-1] - hist[-3]) / 2 / lag1}
    for f in CLIM_F:
        d[f + "_a"] = float(c[f] - norm_r[f])
    return d


def yield_models(con):
    """Per crop: choose persistence or a climate-anomaly GBM (predicting log change vs last year) on
    validation years 2016-2019, report honest test error on 2020-2025, then forecast unpublished seasons."""
    from sklearn.ensemble import GradientBoostingRegressor

    clim = pd.read_sql("SELECT * FROM climate_year", con).set_index(["rayon_id", "year"])
    norm = clim[clim.index.get_level_values(1) <= 2015].groupby(level=0).mean()
    max_clim_year = int(clim.index.get_level_values(1).max())

    def gbm():
        return GradientBoostingRegressor(n_estimators=200, max_depth=2, learning_rate=0.03, subsample=0.8,
                                         loss="huber", random_state=1)

    for cid, *_ in CROPS:
        y = pd.read_sql("SELECT rayon_id, year, yield FROM yields WHERE crop_id=? AND yield>0", con, params=(cid,))
        if y.empty:
            continue
        piv = y.pivot(index="year", columns="rayon_id", values="yield")
        rows = []
        for rid in piv.columns:
            s = piv[rid]
            for yr in range(2003, int(piv.index.max()) + 1):
                hist = s[s.index < yr].dropna()
                if len(hist) < 3 or pd.isna(s.get(yr)) or (rid, yr) not in clim.index:
                    continue
                rows.append({"rayon_id": rid, "year": yr, "t": s[yr],
                             **_feat(hist.tolist(), clim.loc[(rid, yr)], norm.loc[rid])})
        df = pd.DataFrame(rows)
        if len(df) < 150:
            continue
        df["tgt"] = np.log(df.t / df.lag1)
        tr, va, te = df[df.year <= 2015], df[(df.year > 2015) & (df.year <= 2019)], df[df.year >= 2020]
        if len(va) < 10 or len(te) < 10:
            continue
        m = gbm().fit(tr[FEATS], tr.tgt)
        use_model = np.mean(np.abs(va.t - va.lag1 * np.exp(m.predict(va[FEATS])))) < np.mean(np.abs(va.t - va.lag1))
        trva = pd.concat([tr, va])
        if use_model:
            m = gbm().fit(trva[FEATS], trva.tgt)
            pte = te.lag1 * np.exp(m.predict(te[FEATS]))
        else:
            pte = te.lag1
        mae = float(np.mean(np.abs(te.t - pte)))
        base_mae = float(np.mean(np.abs(te.t - te.lag1)))
        ss = float(np.sum((te.t - te.t.mean()) ** 2))
        r2 = 1 - float(np.sum((te.t - pte) ** 2)) / ss if ss else 0.0
        # relative error band (80th pct of |actual/pred - 1|) on test years
        rel_q = float(np.quantile(np.abs(te.t / pte - 1), 0.8))
        imp = {}
        if use_model:
            m = gbm().fit(df[FEATS], df.tgt)
            imp = dict(sorted(zip(FEATS, m.feature_importances_.round(3).tolist()), key=lambda kv: -kv[1]))
        con.execute("INSERT INTO model_metrics VALUES(?,?,?,?,?,?,?)",
                    (cid, len(trva), len(te), mae, r2, base_mae,
                     json.dumps({"method": "gbm_climate" if use_model else "persistence", "rel_band": rel_q,
                                 "importances": imp})))
        last_stat = int(piv.index.max())
        for rid in piv.columns:
            s = piv[rid].dropna()
            if len(s) < 3 or s.index.max() < last_stat:
                continue
            hist = s.tolist()
            for k, yr in enumerate((last_stat + 1, last_stat + 2)):
                if use_model:
                    c = clim.loc[(rid, yr)] if (rid, yr) in clim.index and yr <= max_clim_year else norm.loc[rid]
                    pr = hist[-1] * float(np.exp(m.predict(pd.DataFrame([_feat(hist, c, norm.loc[rid])])[FEATS])[0]))
                else:
                    pr = hist[-1]
                band = rel_q * (1 + 0.5 * k)
                con.execute("INSERT INTO yield_forecast VALUES(?,?,?,?,?,?)",
                            (rid, cid, yr, pr, pr * (1 - band), pr * (1 + band)))
                hist.append(pr)
        print(f"model {cid}: {'gbm' if use_model else 'persist'} test MAE {mae:.2f} (persistence {base_mae:.2f})",
              flush=True)


# ---------------------------------------------------------------- main
def main():
    init_schema()
    con = connect()
    con.execute("PRAGMA foreign_keys=OFF")  # farms reference rayons; ids are stable across rebuilds
    for t in DATA_TABLES:   # data tables are rebuilt from scratch (schema may have grown); app tables are untouched
        con.execute(f"DROP TABLE IF EXISTS {t}")
    con.commit()
    con.close()
    init_schema()
    con = connect()
    con.execute("PRAGMA foreign_keys=OFF")
    rayons = json.load(open(ROOT / "data" / "rayons.json"))
    soil = json.load(open(ROOT / "data" / "soil.json"))
    for r in rayons:
        con.execute("INSERT INTO rayons(id, name, name_az, econ, econ_az, econ_id, lat, lon, area_km2, has_shape) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?)", (r["id"], r["name_en"], r["name"], r["econ_en"],
                    r["econ"], r["econ_id"],
                    r["lat"], r["lon"], r.get("area_km2"), int(bool(r["geo_name"]))))
        s = soil[r["id"]]
        con.execute("INSERT INTO soil VALUES(?,?,?,?,?,?,?,?,?)", (r["id"], s["phh2o"], s["clay"], s["sand"],
                    s["silt"], s["soc"], s["nitrogen"], s["cec"], s["texture"]))
    eco = load_ecocrop()
    for i, c in enumerate(CROPS):
        con.execute("INSERT INTO crops VALUES(?,?,?,?,?,?,?)",
                    (c[0], c[2], c[1], GROUP_EN[c[3]], int(c[3] in PERENNIAL), json.dumps(eco.get(c[0])), i))
    load_stat(con, rayons)
    con.commit()
    print("stat loaded", con.execute("SELECT count(*) FROM yields").fetchone()[0], flush=True)

    last_full = date.today().year - 1
    nex = Nex()
    cm_cache = {}
    from shapely.geometry import Point, shape
    from etl.world_points import elevations, farm_elevation
    az_geom = {f["properties"]["id"]: shape(f["geometry"])
               for f in json.load(open(ROOT / "data" / "regions.geojson"))["features"]}
    az_elev = {}
    for r in rayons:   # lapse-correct to farmland elevation (20th pct of the district), not the polygon's centre point
        g = az_geom.get(r["id"])
        az_elev[r["id"]] = farm_elevation(g, Point(r["lon"], r["lat"])) if g else elevations([(r["lat"], r["lon"])])[0]
    for r in rayons:
        rid = r["id"]
        df = load_power(rid, az_elev[rid])
        annual(df, rid, con, last_full)
        clims = {"1981-2010": monthly(df, 1981, 2010), "2016-2025": monthly(df, 2016, 2025)}
        for period, m in clims.items():
            for mo, v in m.iterrows():
                con.execute("INSERT INTO climate_month VALUES(?,?,?,?,?,?,?,?)",
                            (rid, period, int(mo), v.tmin, v.tmean, v.tmax, v.precip, v.gwetroot))
        if nex.ok:
            projections(con, rid, df, nex.models_for(rid))
        else:  # fallback: Open-Meteo CMIP6 per economic region
            if r["econ_id"] not in cm_cache:
                cm_cache[r["econ_id"]] = cmip6_deltas(r["econ_id"])
            if cm_cache[r["econ_id"]]:
                projections(con, rid, df, cm_cache[r["econ_id"]], 1991, 2020)
    con.commit()
    print("climate loaded", flush=True)

    # world: provinces of every other country (same tables, iso3 + level='province')
    from etl import world_build
    if (ROOT / "data" / "world_units.json").exists():
        units = world_build.load_countries_units(con)
        base = world_build.load_climate(con, units)
        con.commit()
        world_build.load_projections(con, base)
        world_build.load_faostat(con)
        con.commit()

    # suitability
    soil_ph = {r["rayon_id"]: r["ph"] for r in map(dict, con.execute("SELECT rayon_id, ph FROM soil"))}
    cm = pd.read_sql("SELECT * FROM climate_month", con)
    for (rid, period), g in cm.groupby(["rayon_id", "period"]):
        g = g.sort_values("month")
        for c in CROPS:
            if c[0] not in eco:
                continue
            s = ecocrop(eco[c[0]], g, soil_ph.get(rid), c[3] in PERENNIAL, winter=c[0] in WINTER)
            con.execute("INSERT INTO suitability VALUES(?,?,?,?,?,?,?,?,?)",
                        (rid, c[0], period, s["irrigated"], s["rainfed"], s["temp"], s["rain"], s["ph"],
                         s["best_month"]))
    con.commit()
    print("suitability done", flush=True)

    yield_models(con)
    meta = {"built_at": date.today().isoformat(),
            "power_end": con.execute("SELECT max(year) FROM climate_year").fetchone()[0],
            "stat_last_year": con.execute("SELECT max(year) FROM yields").fetchone()[0],
            "projection_source": "NASA NEX-GDDP-CMIP6 SSP2-4.5" if nex.ok else "Open-Meteo CMIP6",
            "projection_models": sorted(nex.data) if nex.ok else [],
            "projection_rayons": con.execute("SELECT count(DISTINCT rayon_id) FROM projection_year").fetchone()[0],
            "cmip6_regions": 13 if nex.ok else sum(1 for v in cm_cache.values() if v),
            "world_countries": con.execute("SELECT count(*) FROM countries").fetchone()[0],
            "world_provinces": con.execute("SELECT count(*) FROM rayons WHERE level='province'").fetchone()[0],
            "world_provinces_climate": con.execute("SELECT count(DISTINCT c.rayon_id) FROM climate_year c JOIN rayons r "
                                                   "ON r.id=c.rayon_id WHERE r.level='province'").fetchone()[0],
            "faostat_last_year": con.execute("SELECT max(year) FROM country_yields WHERE yield>0").fetchone()[0]}
    for k, v in meta.items():
        con.execute("INSERT INTO meta VALUES(?,?)", (k, json.dumps(v)))
    con.commit()
    con.close()
    print("built", DB_PATH, meta)


if __name__ == "__main__":
    main()
