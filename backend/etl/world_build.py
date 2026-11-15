"""World layer for build_db: countries, ~3,300 provinces (ADM1) with NASA POWER climate, SoilGrids soil,
NASA NEX-GDDP-CMIP6 projections (vectorised delta method) and FAOSTAT country yields.

Provinces live in the same `rayons` table as Azerbaijan's districts (iso3 + level='province'), so every
district feature (profile, crop advice, climate, weather, farms, alerts, AI chat) works for them unchanged.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"

FAO_ITEMS = {
    "bugda": "Wheat", "arpa": "Barley", "qargidali": "Maize (corn)", "celtik": "Rice", "noxud": "Chick peas; dry",
    "lobya": "Beans; dry", "mercimek": "Lentils; dry", "pambiq": "Seed cotton; unginned",
    "tutun": "Unmanufactured tobacco", "seker-cugunduru": "Sugar beet", "gunebaxan": "Sunflower seed",
    "kartof": "Potatoes", "terevez": "Vegetables Primary", "kelem": "Cabbages", "xiyar": "Cucumbers and gherkins",
    "pomidor": "Tomatoes", "sogan": "Onions and shallots; dry (excluding dehydrated)", "sarimsaq": "Green garlic",
    "badimcan": "Eggplants (aubergines)", "bibar": "Chillies and peppers; green (Capsicum spp. and Pimenta spp.)",
    "qarpiz": "Watermelons", "yemis": "Cantaloupes and other melons", "alma": "Apples", "armud": "Pears",
    "saftali": "Peaches and nectarines", "erik": "Apricots", "gilas": "Cherries", "gavali": "Plums and sloes",
    "qoz": "Walnuts; in shell", "findiq": "Hazelnuts; in shell", "badam": "Almonds; in shell",
    "xurma": "Persimmons", "encir": "Figs", "zeytun": "Olives", "limon": "Lemons and limes", "portagal": "Oranges",
    "naringi": "Tangerines; mandarins; clementines", "kivi": "Kiwi fruit", "uzum": "Grapes", "cay": "Tea leaves",
}   # pomegranate (nar) has no FAOSTAT item


def load_countries_units(con):
    countries = json.load(open(ROOT / "data" / "countries.json"))
    for c in countries:
        con.execute("INSERT INTO countries VALUES(?,?,?,?,?,?,?,?)", (c["iso3"], c["name"], c["continent"],
                    c["subregion"], c["group"], c["lat"], c["lon"], c["units"]))
    names = {c["iso3"]: c["name"] for c in countries}
    units = json.load(open(ROOT / "data" / "world_units.json"))
    soil = json.load(open(ROOT / "data" / "world_soil.json")) if (ROOT / "data" / "world_soil.json").exists() else {}
    for u in units:
        con.execute("INSERT INTO rayons(id, name, name_az, econ, econ_az, econ_id, lat, lon, area_km2, has_shape, iso3, "
                    "level) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (u["id"], u["name"], u["name"], names.get(u["iso3"], u["iso3"]), names.get(u["iso3"], u["iso3"]),
                     u["iso3"].lower(), u["lat"], u["lon"], u["area_km2"], 1, u["iso3"], "province"))
        s = soil.get(u["id"])
        if s:
            con.execute("INSERT INTO soil VALUES(?,?,?,?,?,?,?,?,?)", (u["id"], s["phh2o"], s["clay"], s["sand"],
                        s["silt"], s["soc"], s["nitrogen"], s["cec"], s["texture"]))
    return units


def load_climate(con, units):
    """climate_year + climate_month (1981-2010, 2016-2025) from the aggregated POWER files.
    Returns {unit_id: 1995-2014 monthly baseline array (12, 4): tmin, tmean, tmax, precip}."""
    base, n = {}, 0
    for u in units:
        f = RAW / "power_world" / f"{u['id']}.json"
        if not f.exists():
            continue
        a = json.load(open(f))
        for y in a["years"]:
            con.execute("INSERT INTO climate_year VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (u["id"], *y))
        for period in ("1981-2010", "2016-2025"):
            for m in a["months"][period]:
                con.execute("INSERT INTO climate_month VALUES(?,?,?,?,?,?,?,?)", (u["id"], period, *m))
        base[u["id"]] = np.array([[m[1], m[2], m[3], m[4]] for m in a["months"]["1995-2014"]], dtype="float64")
        n += 1
    print(f"world climate: {n}/{len(units)} provinces", flush=True)
    return base


def _days(year, n):
    idx = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
    if n == 365 and len(idx) == 366:
        idx = idx[~((idx.month == 2) & (idx.day == 29))]
    return idx.month.values - 1 if len(idx) == n else None


def load_projections(con, base, b0=1995, b1=2014):
    """Vectorised delta method over all provinces at once, per model; ensemble mean (and spread of tmean)."""
    d = RAW / "nex_world"
    if not (d / "rayons.json").exists():
        print("world projections: no NEX data", flush=True)
        return 0
    ids = json.load(open(d / "rayons.json"))
    first = {}
    for i, u in enumerate(ids):
        first.setdefault(u, i)                                 # fetch list may repeat ids; keep first row
    keep = np.array([i for u, i in first.items() if u in base])
    uid = [ids[i] for i in keep]
    bm = np.stack([base[u] for u in uid])                      # (U, 12, 4) POWER baseline
    years_f = range(2026, 2051)
    acc_y = {y: [] for y in years_f}                           # per year: list of (U, 6) per model
    acc_m = []                                                 # per model: (U, 12, 4) for 2041-2050
    models = sorted(p.name for p in d.iterdir() if p.is_dir())
    for model in models:
        md = d / model

        def load(var, yr):
            f = md / f"{var}_{yr}.npy"
            return np.load(f)[keep].astype("float64") if f.exists() else None
        # model baseline monthly means
        s = np.zeros((len(uid), 12, 3)); c = np.zeros((len(uid), 12, 3)); nyrs = 0
        prsum = np.zeros((len(uid), 12))
        for yr in range(b0, b1 + 1):
            tx, tn, pr = load("tasmax", yr), load("tasmin", yr), load("pr", yr)
            if tx is None or tn is None or pr is None:
                continue
            mo = _days(yr, tx.shape[1])
            if mo is None:
                continue
            nyrs += 1
            for m in range(12):
                k = mo == m
                for j, arr in enumerate((tx[:, k], tn[:, k], (tx[:, k] + tn[:, k]) / 2)):
                    s[:, m, j] += np.nansum(arr, axis=1)
                    c[:, m, j] += np.sum(~np.isnan(arr), axis=1)
                prsum[:, m] += np.nansum(pr[:, k], axis=1)
        if nyrs < 15:
            print("skip model (baseline incomplete)", model, flush=True)
            continue
        mb = s / np.maximum(c, 1)                                  # tmax, tmin, tmean
        mb_pr = prsum / nyrs
        d_tx = bm[:, :, 2] - mb[:, :, 0]
        d_tn = bm[:, :, 0] - mb[:, :, 1]
        ratio = np.clip(np.where(mb_pr > 0, bm[:, :, 3] / np.where(mb_pr > 0, mb_pr, 1), 1), 0.2, 5)
        fm = np.zeros((len(uid), 12, 4)); fcount = 0
        for yr in years_f:
            tx, tn, pr = load("tasmax", yr), load("tasmin", yr), load("pr", yr)
            if tx is None or tn is None or pr is None:
                continue
            mo = _days(yr, tx.shape[1])
            if mo is None:
                continue
            tx = tx + d_tx[:, mo]; tn = tn + d_tn[:, mo]; pr = pr * ratio[:, mo]; tm = (tx + tn) / 2
            acc_y[yr].append(np.stack([np.nanmean(tm, 1), np.nanmean(tx, 1), np.nanmean(tn, 1),
                                       np.sum(tx > 35, 1), np.sum(tn < 0, 1), np.nansum(pr, 1)], axis=1))
            if 2041 <= yr <= 2050:
                fcount += 1
                for m in range(12):
                    k = mo == m
                    fm[:, m, 0] += np.nanmean(tn[:, k], 1); fm[:, m, 1] += np.nanmean(tm[:, k], 1)
                    fm[:, m, 2] += np.nanmean(tx[:, k], 1); fm[:, m, 3] += np.nansum(pr[:, k], 1)
        if fcount:
            acc_m.append(fm / fcount)
        print("world projections: model", model, flush=True)
    for yr, lst in acc_y.items():
        if not lst:
            continue
        a = np.stack(lst)                                          # (models, U, 6)
        mean, spread = np.nanmean(a, 0), np.nanstd(a[:, :, 0], 0)
        con.executemany("INSERT INTO projection_year VALUES(?,?,?,?,?,?,?,?,?)",
                        [(uid[i], yr, *[float(v) for v in mean[i]], float(spread[i])) for i in range(len(uid))
                         if not np.isnan(mean[i, 0])])
    if acc_m:
        fm = np.nanmean(np.stack(acc_m), 0)
        con.executemany("INSERT INTO climate_month VALUES(?,?,?,?,?,?,?,?)",
                        [(uid[i], "2041-2050", m + 1, *[float(v) for v in fm[i, m]], None)
                         for i in range(len(uid)) for m in range(12) if not np.isnan(fm[i, m, 1])])
    return len(models)


def load_faostat(con):
    import pycountry
    f = RAW / "faostat" / "Production_Crops_Livestock_E_All_Data_(Normalized).csv"
    if not f.exists():
        print("faostat: missing", flush=True)
        return
    # the item-code file uses ";" where the data file uses "," (e.g. "Hazelnuts; in shell" vs "Hazelnuts, in shell")
    item2crop = {}
    for k, v in FAO_ITEMS.items():
        item2crop[v] = k
        item2crop[v.replace(";", ",")] = k
    rows = {}
    for chunk in pd.read_csv(f, encoding="latin-1", chunksize=400_000,
                             usecols=["Area Code (M49)", "Item", "Element", "Year", "Unit", "Value"]):
        chunk = chunk[chunk.Item.isin(item2crop) & chunk.Element.isin(["Yield", "Production", "Area harvested"])
                      & (chunk.Year >= 1990)]
        for r in chunk.itertuples(index=False):
            m49 = str(r[0]).strip("'")
            c = pycountry.countries.get(numeric=m49)
            if not c or pd.isna(r.Value):
                continue
            key = (c.alpha_3, item2crop[r.Item], int(r.Year))
            d = rows.setdefault(key, {})
            if r.Element == "Yield":
                d["yield"] = r.Value / {"kg/ha": 100, "100 g/ha": 1000, "hg/ha": 1000, "g/ha": 100000}.get(r.Unit, 100)
            elif r.Element == "Production":
                d["production"] = r.Value
            else:
                d["area"] = r.Value
    con.executemany("INSERT INTO country_yields VALUES(?,?,?,?,?,?)",
                    [(k[0], k[1], k[2], v.get("yield"), v.get("production"), v.get("area")) for k, v in rows.items()])
    print(f"faostat: {len(rows)} country-crop-years", flush=True)
