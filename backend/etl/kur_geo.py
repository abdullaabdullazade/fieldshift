"""Lower Kür geometry for the salt-intrusion module.

  data/kur/river.json   SWORD v16 reaches of the Kür (and the Araz above the confluence): id, km from the sea,
                        centreline as [lon, lat] list, width
  data/kur/villages.json settlements within 4 km of the river below the Araz confluence, with their river km

SWORD (SWOT River Database, CC BY 4.0) is read from the public PMTiles of SWORD Explorer (swordexplorer.com);
settlements come from OpenStreetMap (ODbL) via the Overpass API.
"""
import gzip
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

import mapbox_vector_tile as mvt
from pmtiles.reader import Reader

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "kur"
PMT = "https://pub-ceb2c39205d5401cac3cf448cff9518d.r2.dev/tiles/eu_reaches_002.pmtiles"
BBOX = (48.0, 39.15, 49.55, 40.2)          # lon/lat box of the lower Kür, the Araz mouth and the Kür delta
Z = 11


class Http:
    def __init__(self, url):
        self.url = url

    def __call__(self, off, ln):
        req = urllib.request.Request(self.url, headers={"Range": f"bytes={off}-{off + ln - 1}", "User-Agent": "FieldShift/1.0"})
        return urllib.request.urlopen(req, timeout=120).read()


def tile_range(z):
    n = 2 ** z
    x = lambda lon: int((lon + 180) / 360 * n)                                                     # noqa: E731
    y = lambda lat: int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)          # noqa: E731
    return range(x(BBOX[0]), x(BBOX[2]) + 1), range(y(BBOX[3]), y(BBOX[1]) + 1)


def to_lonlat(z, tx, ty, px, py, extent):
    n = 2 ** z
    lon = (tx + px / extent) / n * 360 - 180
    yy = ty + 1 - py / extent                     # MVT y grows downwards inside the tile
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yy / n))))
    return [round(lon, 5), round(lat, 5)]


def reaches():
    rd = Reader(Http(PMT))
    feats = {}
    xs, ys = tile_range(Z)
    for tx in xs:
        for ty in ys:
            raw = rd.get(Z, tx, ty)
            if not raw:
                continue
            try:
                raw = gzip.decompress(raw)
            except OSError:
                pass
            for layer in mvt.decode(raw).values():
                ext = layer.get("extent", 4096)
                for f in layer["features"]:
                    p = f["properties"]
                    rid = str(p.get("reach_id"))
                    if not rid.startswith(("28450", "28461", "28463", "28464", "28465")):   # Kür delta, Kür, Araz
                        continue
                    g = f["geometry"]
                    lines = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
                    pts = [to_lonlat(Z, tx, ty, x, y, ext) for line in lines for x, y in line]
                    e = feats.setdefault(rid, {"id": rid, "km": round(p["dist_out"] / 1000, 1), "width": p["width"],
                                               "x": p["x"], "y": p["y"], "swot_obs": p.get("swot_obs"),
                                               "up": [str(p[k]) for k in ("rch_id_up_1", "rch_id_up_2") if p.get(k)],
                                               "pts": []})
                    e["pts"].extend(pts)
    out = []
    for e in feats.values():
        # tiles cut lines; order the collected vertices along the reach by distance from its downstream end
        pts = {tuple(p) for p in e["pts"]}
        if len(pts) < 2:
            continue
        start = min(pts, key=lambda p: (p[0] - BBOX[2]) ** 2 + (p[1] - BBOX[1]) ** 2)
        line, rest = [start], set(pts) - {start}
        while rest:
            nxt = min(rest, key=lambda p: (p[0] - line[-1][0]) ** 2 + (p[1] - line[-1][1]) ** 2)
            line.append(nxt)
            rest.discard(nxt)
        e["line"] = [list(p) for p in line]
        del e["pts"]
        out.append(e)
    out = sorted(out, key=lambda e: e["km"])
    # km of every vertex: reaches on one stem are chained, a reach starts where the previous one ended
    for stem in (("28450", "28461", "28463", "28465"), ("28464",)):
        prev = 0.0
        for e in [e for e in out if e["id"].startswith(stem)]:
            seg = [0.0]
            for a, b in zip(e["line"], e["line"][1:]):
                seg.append(seg[-1] + math.hypot((b[0] - a[0]) * 111.32 * math.cos(math.radians(a[1])), (b[1] - a[1]) * 110.57))
            start = prev if stem != ("28464",) else e["km"] - seg[-1]
            scale = (e["km"] - start) / seg[-1] if seg[-1] > 0 else 0
            e["kms"] = [round(start + d * scale, 2) for d in seg]
            e["stem"] = "araz" if stem == ("28464",) else "kur"
            prev = e["km"]
    return out


def villages(river):
    q = f"""[out:json][timeout:120];
    (node["place"~"village|town|city"](39.2,48.8,40.0,49.5););out;"""   # below the Araz confluence
    els = None
    for host in ("https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass-api.de/api/interpreter",
                 "https://overpass.kumi.systems/api/interpreter"):
        try:
            req = urllib.request.Request(host, data=urllib.parse.urlencode({"data": q}).encode(),
                                         headers={"User-Agent": "FieldShift/1.0 (NASA Space Apps 2026)"})
            els = json.load(urllib.request.urlopen(req, timeout=180))["elements"]
            break
        except Exception as e:  # noqa: BLE001 - public mirrors are often busy
            print("overpass", host, e)
    if els is None:
        raise RuntimeError("no Overpass mirror answered")
    verts = [(k, p) for r in river if r.get("stem") == "kur" and r["km"] <= 160 for k, p in zip(r["kms"], r["line"])]
    res = []
    for el in els:
        t = el.get("tags", {})
        name = t.get("name:az") or t.get("name")
        if not name:
            continue
        lon, lat = el["lon"], el["lat"]
        best = min(verts, key=lambda v: (v[1][0] - lon) ** 2 * math.cos(math.radians(lat)) ** 2 + (v[1][1] - lat) ** 2)
        d = math.hypot((best[1][0] - lon) * 111 * math.cos(math.radians(lat)), (best[1][1] - lat) * 111)
        if d <= 4:
            res.append({"name": name, "name_en": t.get("name:en") or name, "lat": lat, "lon": lon,
                        "km": round(best[0], 1), "dist_km": round(d, 1), "place": t["place"]})
    return sorted(res, key=lambda v: v["km"])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rv = reaches()
    json.dump(rv, open(OUT / "river.json", "w"), separators=(",", ":"))
    print("reaches", len(rv), "km", rv[0]["km"], "->", rv[-1]["km"])
    vs = villages(rv)
    json.dump(vs, open(OUT / "villages.json", "w"), ensure_ascii=False, indent=0)
    print("villages", len(vs), [(v["name"], v["km"]) for v in vs[:12]])


if __name__ == "__main__":
    main()
