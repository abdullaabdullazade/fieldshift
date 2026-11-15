import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.environ.get("FIELDSHIFT_DB", ROOT / "data" / "fieldshift.db"))

DATA_TABLES = ["rayons", "countries", "country_yields", "soil", "crops", "yields", "national_yields", "climate_year",
               "climate_month",
               "projection_year", "suitability", "yield_forecast", "model_metrics", "meta"]

DATA_SCHEMA = """
CREATE TABLE IF NOT EXISTS rayons(id TEXT PRIMARY KEY, name TEXT, name_az TEXT, econ TEXT, econ_az TEXT, econ_id TEXT, lat REAL, lon REAL,
  area_km2 REAL, has_shape INTEGER, iso3 TEXT DEFAULT 'AZE', level TEXT DEFAULT 'district');
CREATE INDEX IF NOT EXISTS rayons_iso3 ON rayons(iso3);
CREATE TABLE IF NOT EXISTS countries(iso3 TEXT PRIMARY KEY, name TEXT, continent TEXT, subregion TEXT, grp TEXT,
  lat REAL, lon REAL, units INTEGER);
CREATE TABLE IF NOT EXISTS country_yields(iso3 TEXT, crop_id TEXT, year INTEGER, yield REAL, production REAL, area REAL,
  PRIMARY KEY(iso3, crop_id, year));
CREATE INDEX IF NOT EXISTS country_yields_crop ON country_yields(crop_id, year);
CREATE TABLE IF NOT EXISTS soil(rayon_id TEXT PRIMARY KEY, ph REAL, clay REAL, sand REAL, silt REAL, soc REAL,
  nitrogen REAL, cec REAL, texture TEXT);
CREATE TABLE IF NOT EXISTS crops(id TEXT PRIMARY KEY, name TEXT, name_az TEXT, grp TEXT, perennial INTEGER,
  eco TEXT, ord INTEGER);
CREATE TABLE IF NOT EXISTS yields(rayon_id TEXT, crop_id TEXT, year INTEGER, yield REAL, production REAL,
  PRIMARY KEY(rayon_id, crop_id, year));
CREATE INDEX IF NOT EXISTS yields_crop_year ON yields(crop_id, year);
CREATE TABLE IF NOT EXISTS national_yields(crop_id TEXT, year INTEGER, yield REAL, production REAL,
  PRIMARY KEY(crop_id, year));
CREATE TABLE IF NOT EXISTS climate_year(rayon_id TEXT, year INTEGER, tmean REAL, tmax REAL, tmin REAL,
  hot35 INTEGER, frost INTEGER, precip REAL, gwetroot REAL, gwettop REAL, gdd REAL, last_frost INTEGER,
  first_frost INTEGER, ffs INTEGER, gs_tmean REAL, gs_precip REAL, gs_gwetroot REAL, rh REAL, rad REAL,
  partial INTEGER DEFAULT 0, PRIMARY KEY(rayon_id, year));
CREATE TABLE IF NOT EXISTS climate_month(rayon_id TEXT, period TEXT, month INTEGER, tmin REAL, tmean REAL,
  tmax REAL, precip REAL, gwetroot REAL, PRIMARY KEY(rayon_id, period, month));
CREATE TABLE IF NOT EXISTS projection_year(rayon_id TEXT, year INTEGER, tmean REAL, tmax REAL, tmin REAL,
  hot35 REAL, frost REAL, precip REAL, spread REAL, PRIMARY KEY(rayon_id, year));
CREATE TABLE IF NOT EXISTS suitability(rayon_id TEXT, crop_id TEXT, period TEXT, irrigated REAL, rainfed REAL,
  temp REAL, rain REAL, ph REAL, best_month INTEGER, PRIMARY KEY(rayon_id, crop_id, period));
CREATE TABLE IF NOT EXISTS yield_forecast(rayon_id TEXT, crop_id TEXT, year INTEGER, pred REAL, lo REAL, hi REAL,
  PRIMARY KEY(rayon_id, crop_id, year));
CREATE TABLE IF NOT EXISTS model_metrics(crop_id TEXT PRIMARY KEY, n_train INTEGER, n_test INTEGER, mae REAL,
  r2 REAL, baseline_mae REAL, importances TEXT);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""

APP_SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, phone TEXT,
  password_hash TEXT NOT NULL, name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('farmer','buyer')),
  bio TEXT DEFAULT '', whatsapp TEXT DEFAULT '', telegram TEXT DEFAULT '', show_phone INTEGER DEFAULT 1,
  sms_alerts INTEGER DEFAULT 1, created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS farms(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id)
  ON DELETE CASCADE, rayon_id TEXT NOT NULL REFERENCES rayons(id), name TEXT NOT NULL, lat REAL, lon REAL,
  area_ha REAL, irrigated INTEGER DEFAULT 1, created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS farm_crops(farm_id INTEGER REFERENCES farms(id) ON DELETE CASCADE, crop_id TEXT,
  PRIMARY KEY(farm_id, crop_id));
CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY AUTOINCREMENT, farmer_id INTEGER NOT NULL REFERENCES
  users(id) ON DELETE CASCADE, author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5), crop_id TEXT, comment TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now')), UNIQUE(farmer_id, author_id, crop_id));
CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id)
  ON DELETE SET NULL, kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT DEFAULT '', rating INTEGER,
  page TEXT DEFAULT '', status TEXT DEFAULT 'new', created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS feedback_votes(feedback_id INTEGER REFERENCES feedback(id) ON DELETE CASCADE,
  user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, PRIMARY KEY(feedback_id, user_id));
CREATE TABLE IF NOT EXISTS feedback_comments(id INTEGER PRIMARY KEY AUTOINCREMENT, feedback_id INTEGER
  REFERENCES feedback(id) ON DELETE CASCADE, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
  body TEXT NOT NULL, created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id)
  ON DELETE CASCADE, farm_id INTEGER REFERENCES farms(id) ON DELETE CASCADE, kind TEXT, severity TEXT,
  title TEXT, body TEXT, advice TEXT, event_date TEXT, dedup TEXT, read INTEGER DEFAULT 0,
  sms_status TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now')), UNIQUE(farm_id, dedup));
CREATE TABLE IF NOT EXISTS sms_outbox(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, phone TEXT,
  body TEXT, provider TEXT, status TEXT, error TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS forecast_snapshots(rayon_id TEXT, issued TEXT, target TEXT, tmin REAL, tmax REAL,
  precip REAL, PRIMARY KEY(rayon_id, issued, target));
CREATE TABLE IF NOT EXISTS sat_obs(rayon_id TEXT, product TEXT, date TEXT, value REAL, normal REAL, n_normal INTEGER,
  PRIMARY KEY(rayon_id, product));
CREATE TABLE IF NOT EXISTS sat_meta(product TEXT PRIMARY KEY, date TEXT, fetched_at TEXT, units INTEGER);
CREATE TABLE IF NOT EXISTS fires(lat REAL, lon REAL, acq TEXT, sat TEXT, conf TEXT, frp REAL, dn TEXT, days INTEGER DEFAULT 1);
CREATE INDEX IF NOT EXISTS fires_ll ON fires(lat, lon);
CREATE TABLE IF NOT EXISTS fire_cells(cell TEXT, day TEXT, PRIMARY KEY(cell, day));
CREATE TABLE IF NOT EXISTS kur_obs(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  kind TEXT NOT NULL CHECK(kind IN ('water','soil')), lat REAL, lon REAL, km REAL, ec REAL, ph REAL, salty INTEGER,
  observed_at TEXT NOT NULL, note TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now')));
CREATE INDEX IF NOT EXISTS kur_obs_t ON kur_obs(observed_at);
CREATE TABLE IF NOT EXISTS farm_salt_state(farm_id INTEGER PRIMARY KEY REFERENCES farms(id) ON DELETE CASCADE,
  state TEXT NOT NULL, at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS farm_irrigations(id INTEGER PRIMARY KEY AUTOINCREMENT, farm_id INTEGER NOT NULL REFERENCES farms(id)
  ON DELETE CASCADE, day TEXT NOT NULL, created_at TEXT DEFAULT (datetime('now')), UNIQUE(farm_id, day));
CREATE TABLE IF NOT EXISTS chat_messages(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id)
  ON DELETE CASCADE, role TEXT, content TEXT, created_at TEXT DEFAULT (datetime('now')));
"""


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    return con


@contextmanager
def tx():
    con = connect()
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_schema():
    with tx() as con:
        # migrate pre-world databases: rayons gained iso3/level (needed before the index in DATA_SCHEMA)
        cols = {r[1] for r in con.execute("PRAGMA table_info(rayons)")}
        if cols and "iso3" not in cols:
            con.execute("ALTER TABLE rayons ADD COLUMN iso3 TEXT DEFAULT 'AZE'")
            con.execute("ALTER TABLE rayons ADD COLUMN level TEXT DEFAULT 'district'")
        con.executescript(DATA_SCHEMA + APP_SCHEMA)
        cols = {r[1] for r in con.execute("PRAGMA table_info(users)")}
        if "is_demo" not in cols:  # sample accounts for presentations; removable with etl.seed_demo --remove
            con.execute("ALTER TABLE users ADD COLUMN is_demo INTEGER DEFAULT 0")
        # Kür salt-water module: where the farm takes its water from and what the farmer told us about it
        fcols = {r[1] for r in con.execute("PRAGMA table_info(farms)")}
        for col, typ in [("water_source", "TEXT"), ("pump_lat", "REAL"), ("pump_lon", "REAL"), ("pump_km", "REAL"),
                         ("pond_m3", "REAL"), ("drainage", "INTEGER"), ("irr_method", "TEXT"), ("soil_ec", "REAL"),
                         ("soil_ph", "REAL"), ("salty_note", "TEXT")]:
            if col not in fcols:
                con.execute(f"ALTER TABLE farms ADD COLUMN {col} {typ}")


def rows(con, sql, *args):
    return [dict(r) for r in con.execute(sql, args).fetchall()]


def row(con, sql, *args):
    r = con.execute(sql, args).fetchone()
    return dict(r) if r else None
