"""Rayon catalogue: stat.gov.az names <-> geoBoundaries ADM2 shapes, economic regions, centroids.

Writes data/regions.geojson (one feature per rayon, merged multi-parts) and data/rayons.json.
Source: geoBoundaries gbOpen AZE ADM2 (CC BY-SA 3.0), DSK (stat.gov.az) regional tables.
"""
import json
import re
import unicodedata
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"

# stat.gov.az name (without " rayonu"/" şəhəri") -> geoBoundaries shapeName
GEO = {
    "Naxçıvan şəhəri": "Nakhchivan City", "Babək": "Babek District", "Culfa": "Julfa District",
    "Kəngərli": "Kangarli District", "Ordubad": "Ordubad District", "Sədərək": "Sadarak District",
    "Şahbuz": "Shahbuz District", "Şərur": "Sharur District",
    "Abşeron": "Absheron District", "Xızı": "Khizi District",
    "Ağsu": "Agsu District", "İsmayıllı": "Ismailli District", "Qobustan": "Gobustan District",
    "Şamaxı": "Shamakhi District",
    "Gəncə şəhəri": "Ganja City", "Naftalan şəhəri": "Naftalan City", "Daşkəsən": "Dashkasan District",
    "Goranboy": "Goranboy District", "Göygöl": "Goygol District", "Samux": "Samukh District",
    "Xankəndi şəhəri": "Khankendi City", "Ağcabədi": "Aghjabadi District", "Ağdam": "Agdam District",
    "Ağdərə": None, "Bərdə": "Barda District", "Füzuli": "Fuzuli District", "Xocalı": "Khojaly District",
    "Xocavənd": "Khojavend District", "Şuşa": "Shusha District", "Tərtər": "Tartar District",
    "Ağstafa": "Agstafa District", "Gədəbəy": "Gadabay District", "Qazax": "Qazakh District",
    "Şəmkir": "Shamkir District", "Tovuz": "Tovuz District",
    "Xaçmaz": "Khachmaz District", "Quba": "Quba District", "Qusar": "Qusar District",
    "Siyəzən": "Siazan District", "Şabran": "Shabran District",
    "Astara": "Astara District", "Cəlilabad": "Jalilabad District", "Lerik": "Lerik District",
    "Lənkəran": "Lankaran District", "Masallı": "Masally District", "Yardımlı": "Yardymli District",
    "Mingəçevir şəhəri": "Mingachevir City", "Ağdaş": "Agdash District", "Göyçay": "Goychay District",
    "Kürdəmir": "Kurdamir District", "Ucar": "Ujar District", "Yevlax": "Yevlakh District",
    "Zərdab": "Zardab District",
    "Beyləqan": "Beylagan District", "İmişli": "Imishli District", "Saatlı": "Saatly District",
    "Sabirabad": "Sabirabad District",
    "Balakən": "Balakan District", "Qax": "Qakh District", "Qəbələ": "Qabala District",
    "Oğuz": "Oghuz District", "Şəki": "Shaki District", "Zaqatala": "Zaqatala District",
    "Cəbrayıl": "Jabrayil District", "Kəlbəcər": "Kalbajar District", "Qubadlı": "Qubadli District",
    "Laçın": "Lachin District", "Zəngilan": "Zangilan District",
    "Biləsuvar": "Bilasuvar District", "Hacıqabul": "Hajigabul District", "Neftçala": "Neftchala District",
    "Salyan": "Salyan District",
}
# city enclaves merged into the surrounding rayon (stats are reported for the rayon)
MERGE = {"Lankaran City": "Lankaran District", "Shaki City": "Shaki District",
         "Yevlakh City": "Yevlakh District", "Shusha City": "Shusha District",
         "Shirvan City": None}
# Ağdərə has no ADM2 shape in geoBoundaries (absorbed into Tərtər/Kəlbəcər); town coordinates
POINTS = {"Ağdərə": (40.2133, 46.8150)}


ECON_EN = {"Naxçıvan": "Nakhchivan", "Abşeron-Xızı": "Absheron-Khizi", "Dağlıq Şirvan": "Mountainous Shirvan",
           "Gəncə-Daşkəsən": "Ganja-Dashkasan", "Qarabağ": "Karabakh", "Qazax-Tovuz": "Gazakh-Tovuz",
           "Quba-Xaçmaz": "Guba-Khachmaz", "Lənkəran-Astara": "Lankaran-Astara", "Mərkəzi Aran": "Central Aran",
           "Mil-Muğan": "Mil-Mughan", "Şəki-Zaqatala": "Shaki-Zagatala", "Şərqi Zəngəzur": "East Zangezur",
           "Şirvan-Salyan": "Shirvan-Salyan"}


def slug(s: str) -> str:
    tr = str.maketrans("əıöüğşçƏİÖÜĞŞÇ", "eiougscEIOUGSC")
    s = unicodedata.normalize("NFC", s).translate(tr).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def stat_rows():
    """Ordered (economic_region, rayon_name) from a stat table."""
    import pandas as pd
    df = pd.read_excel(RAW / "stat" / "2.113.xls", header=None)
    econ, out = None, []
    for v in df[1][4:]:
        v = " ".join(str(v).split())
        if v.endswith("iqtisadi rayonu"):
            econ = v.replace(" iqtisadi rayonu", "")
        elif econ:
            out.append((econ, v.replace(" rayonu", "")))
    return out


def build():
    geo = json.load(open(RAW / "adm2.geojson"))
    shapes = {}
    for f in geo["features"]:
        n = f["properties"]["shapeName"]
        n = MERGE.get(n, n) if n in MERGE else n
        if n is None:
            continue
        shapes.setdefault(n, []).append(shape(f["geometry"]))
    rayons, feats = [], []
    for econ, name in stat_rows():
        gname = GEO[name]
        en = (gname or "Aghdara").replace(" District", "")
        r = {"id": slug(name.replace(" şəhəri", "-sheher")), "name": name, "name_en": en, "econ": econ,
             "econ_en": ECON_EN[econ],
             "econ_id": slug(econ), "geo_name": gname}
        if gname:
            g = unary_union(shapes[gname]).simplify(0.003, preserve_topology=True)
            c = g.representative_point()
            r["lat"], r["lon"] = round(c.y, 4), round(c.x, 4)
            r["area_km2"] = round(unary_union(shapes[gname]).area * 111.32 * 111.32 * 0.76, 0)
            feats.append({"type": "Feature", "properties": {"id": r["id"], "name": en, "econ": r["econ_en"]},
                          "geometry": mapping(g)})
        else:
            r["lat"], r["lon"] = POINTS[name]
        rayons.append(r)
    (ROOT / "data").mkdir(exist_ok=True)
    json.dump({"type": "FeatureCollection", "features": feats},
              open(ROOT / "data" / "regions.geojson", "w"), ensure_ascii=False, separators=(",", ":"))
    json.dump(rayons, open(ROOT / "data" / "rayons.json", "w"), ensure_ascii=False, indent=1)
    return rayons


if __name__ == "__main__":
    rs = build()
    print(len(rs), "rayons;", sum(1 for r in rs if r["geo_name"]), "with shapes")
