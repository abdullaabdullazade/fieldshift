"""Sample community data for presentations: farmers, buyers, reviews and feedback, all flagged users.is_demo=1.

Real datasets are never touched. Each demo farmer's crops are the real top crops (AzStat production) of their district,
and farm points fall inside the district polygon. Contacts are placeholders and are not clickable in the UI.

    python -m etl.seed_demo            # add (idempotent: replaces previous demo data)
    python -m etl.seed_demo --remove   # delete every demo account and everything they created
"""
import json
import random
import sys
from pathlib import Path

from shapely.geometry import Point, shape

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.auth import hash_password  # noqa: E402
from app.db import ROOT, init_schema, rows, tx  # noqa: E402

FIRST = ["Elvin", "Rauf", "Nigar", "Aynur", "Tural", "Kamran", "Leyla", "Orxan", "Sevinc", "Ramil", "Gunay", "Vugar",
         "Samir", "Lala", "Elnur", "Aysel", "Farid", "Narmin", "Ilkin", "Gulnar", "Rashad", "Konul", "Anar", "Ulviyya"]
LAST = ["Mammadov", "Aliyev", "Huseynov", "Hasanov", "Guliyev", "Ismayilov", "Abbasov", "Jafarov", "Rzayev", "Babayev",
        "Karimov", "Valiyev", "Najafov", "Qasimov", "Suleymanov", "Ahmadov"]
DISTRICTS = ["saatli", "imisli", "sabirabad", "berde", "agcabedi", "beyleqan", "seki", "zaqatala", "qax", "qebele",
             "quba", "qusar", "xacmaz", "lenkeran", "astara", "masalli", "celilabad", "goycay", "agdas", "semkir",
             "tovuz", "samaxi", "salyan", "haciqabul"]
COMMENTS = {
    5: ["Excellent quality, exactly as described. Will order again.", "Fresh produce and fair price, delivered on time.",
        "Very reliable supplier, the whole batch was consistent.", "Best {crop} we bought this season."],
    4: ["Good quality, delivery was a day late.", "Solid {crop}, a few pieces below grade but price was fair.",
        "Friendly and responsive, would buy again."],
    3: ["Average batch, sizes were mixed.", "OK overall, packaging could be better."],
    2: ["Quality lower than promised this time.", "Delivery was late and part of the {crop} was damaged."],
}
FEEDBACK = [
    ("idea", "Show wholesale market prices per crop", "Next to the yield ranking it would help to see Baku wholesale prices.", 5),
    ("idea", "Azerbaijani language version", "Most farmers in our district would use the app in Azerbaijani.", 4),
    ("data", "Add irrigation canal coverage per district", "Suitability changes a lot depending on canal access.", None),
    ("idea", "Weekly summary SMS", "One short SMS every Monday with the week's risks would be enough for older farmers.", 5),
    ("praise", "Frost alert saved our apricot bloom", "Got the warning two days early and covered the young trees.", 5),
    ("bug", "Map is slow on old Android phones", "Zooming the district map lags on a 2018 phone.", 3),
]


def remove(con):
    ids = [r["id"] for r in rows(con, "SELECT id FROM users WHERE is_demo=1")]
    for uid in ids:
        con.execute("DELETE FROM feedback_comments WHERE user_id=?", (uid,))
        con.execute("DELETE FROM feedback_votes WHERE user_id=?", (uid,))
        con.execute("DELETE FROM feedback_votes WHERE feedback_id IN (SELECT id FROM feedback WHERE user_id=?)", (uid,))
        con.execute("DELETE FROM feedback_comments WHERE feedback_id IN (SELECT id FROM feedback WHERE user_id=?)", (uid,))
        con.execute("DELETE FROM feedback WHERE user_id=?", (uid,))
        con.execute("DELETE FROM reviews WHERE farmer_id=? OR author_id=?", (uid, uid))
        con.execute("DELETE FROM alerts WHERE user_id=?", (uid,))
        con.execute("DELETE FROM sms_outbox WHERE user_id=?", (uid,))
        con.execute("DELETE FROM chat_messages WHERE user_id=?", (uid,))
        con.execute("DELETE FROM farm_crops WHERE farm_id IN (SELECT id FROM farms WHERE user_id=?)", (uid,))
        con.execute("DELETE FROM farms WHERE user_id=?", (uid,))
        con.execute("DELETE FROM users WHERE id=?", (uid,))
    return len(ids)


def point_in(geom, rnd):
    minx, miny, maxx, maxy = geom.bounds
    for _ in range(200):
        p = Point(rnd.uniform(minx, maxx), rnd.uniform(miny, maxy))
        if geom.contains(p):
            return round(p.y, 5), round(p.x, 5)
    c = geom.representative_point()
    return round(c.y, 5), round(c.x, 5)


def seed(con):
    rnd = random.Random(2026)
    pw = hash_password("demo-not-a-login-" + str(rnd.random()))  # unusable password: demo accounts cannot sign in
    geo = {f["properties"]["id"]: shape(f["geometry"])
           for f in json.load(open(ROOT / "data" / "regions.geojson"))["features"]}
    female = {"Nigar", "Aynur", "Leyla", "Sevinc", "Gunay", "Lala", "Aysel", "Narmin", "Gulnar", "Konul", "Ulviyya"}
    names = rnd.sample([f"{a} {b}{'a' if a in female else ''}" for a in FIRST for b in LAST], 40)
    farmers = []
    for i, rid in enumerate(DISTRICTS):
        r = rows(con, "SELECT name FROM rayons WHERE id=?", rid)[0]
        top = rows(con, """SELECT y.crop_id, c.name FROM yields y JOIN crops c ON c.id=y.crop_id
                   WHERE y.rayon_id=? AND y.year=2025 AND y.production>0 AND y.crop_id!='terevez'
                   ORDER BY y.production DESC LIMIT 6""", rid)
        crops = rnd.sample(top, k=min(len(top), rnd.randint(2, 4)))
        area = rnd.choice([4, 6, 8, 12, 15, 20, 25, 40, 60])
        nm = names[i]
        bio = (f"Family farm in {r['name']} growing {', '.join(c['name'].lower() for c in crops)} on about {area} ha. "
               f"{rnd.choice(['Direct sales to shops and restaurants.', 'Wholesale orders welcome.', 'Delivery to Baku twice a week.', 'Open to long-term contracts.'])}")
        uid = con.execute("INSERT INTO users(email, phone, password_hash, name, role, bio, whatsapp, telegram, show_phone, "
                          "sms_alerts, is_demo) VALUES(?,?,?,?,?,?,?,?,1,1,1)",
                          (f"demo.farmer{i + 1}@fieldshift.demo", f"+994 50 000 {i + 1:02d} {i + 11:02d}", pw, nm,
                           "farmer", bio, f"+994 50 000 {i + 1:02d} {i + 11:02d}" if i % 2 == 0 else "",
                           f"demo_farmer_{i + 1}" if i % 3 == 0 else "")).lastrowid
        lat, lon = point_in(geo[rid], rnd)
        fid = con.execute("INSERT INTO farms(user_id, rayon_id, name, lat, lon, area_ha, irrigated) VALUES(?,?,?,?,?,?,?)",
                          (uid, rid, f"{nm.split()[1]} farm", lat, lon, area, int(rnd.random() < .8))).lastrowid
        for c in crops:
            con.execute("INSERT INTO farm_crops VALUES(?,?)", (fid, c["crop_id"]))
        farmers.append((uid, crops))
    buyers = []
    for j in range(12):
        nm = names[len(DISTRICTS) + j]
        buyers.append(con.execute("INSERT INTO users(email, password_hash, name, role, is_demo) VALUES(?,?,?,?,1)",
                                  (f"demo.buyer{j + 1}@fieldshift.demo", pw, nm, "buyer")).lastrowid)
    for uid, crops in farmers:
        quality = rnd.choice([4.6, 4.3, 4.0, 3.6, 3.2])
        for b in rnd.sample(buyers, rnd.randint(1, 6)):
            stars = max(2, min(5, round(rnd.gauss(quality, 0.7))))
            c = rnd.choice(crops)
            text = rnd.choice(COMMENTS[stars]).format(crop=c["name"].lower())
            con.execute("INSERT OR IGNORE INTO reviews(farmer_id, author_id, rating, crop_id, comment, created_at) "
                        "VALUES(?,?,?,?,?,datetime('now', ?))", (uid, b, stars, c["crop_id"], text,
                                                                  f"-{rnd.randint(1, 120)} days"))
    everyone = [u for u, _ in farmers] + buyers
    for k, (kind, title, body, rating) in enumerate(FEEDBACK):
        author = everyone[k * 5 % len(everyone)]
        fid = con.execute("INSERT INTO feedback(user_id, kind, title, body, rating, status, created_at) "
                          "VALUES(?,?,?,?,?,?,datetime('now', ?))",
                          (author, kind, title, body, rating, rnd.choice(["new", "planned", "new"]),
                           f"-{rnd.randint(1, 30)} days")).lastrowid
        for v in rnd.sample(everyone, rnd.randint(1, 14)):
            con.execute("INSERT OR IGNORE INTO feedback_votes VALUES(?,?)", (fid, v))
    return len(farmers), len(buyers)


if __name__ == "__main__":
    init_schema()
    with tx() as con:
        n = remove(con)
        if "--remove" in sys.argv:
            print(f"removed {n} demo accounts")
        else:
            f, b = seed(con)
            print(f"seeded {f} demo farmers, {b} demo buyers (replaced {n} old demo accounts)")
