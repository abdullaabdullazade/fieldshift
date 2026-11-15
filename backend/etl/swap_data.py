"""Replace the data tables of the live database with those of a freshly built one, keeping app tables
(users, farms, reviews, feedback, alerts, chat, SMS) untouched.

    python -m etl.swap_data /path/to/new_fieldshift.db
"""
import sqlite3
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from app.db import DATA_TABLES, DB_PATH, init_schema  # noqa: E402


def main(src):
    init_schema()                                   # migrates older live schemas (adds rayons.iso3/level, ...)
    con = sqlite3.connect(DB_PATH, timeout=60)
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute("ATTACH DATABASE ? AS src", (src,))
    with con:
        for t in DATA_TABLES:
            con.execute(f"DROP TABLE IF EXISTS main.{t}")
    con.execute("DETACH DATABASE src")
    con.close()
    init_schema()                                   # recreate empty data tables with the current schema
    con = sqlite3.connect(DB_PATH, timeout=60)
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute("ATTACH DATABASE ? AS src", (src,))
    with con:
        for t in DATA_TABLES:
            cols = [r[1] for r in con.execute(f"PRAGMA src.table_info({t})")]
            if not cols:
                continue
            c = ",".join(cols)
            con.execute(f"INSERT INTO main.{t}({c}) SELECT {c} FROM src.{t}")
            print(t, con.execute(f"SELECT count(*) FROM main.{t}").fetchone()[0], flush=True)
    orphans = con.execute("SELECT count(*) FROM farms WHERE rayon_id NOT IN (SELECT id FROM rayons)").fetchone()[0]
    con.execute("DETACH DATABASE src")
    con.close()
    print("farms pointing to unknown units:", orphans)


if __name__ == "__main__":
    main(sys.argv[1])
