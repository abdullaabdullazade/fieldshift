"""Global ADM1 catalogue from geoBoundaries (gbOpen, CC BY 4.0 / ODbL depending on source).

Downloads simplified ADM1 GeoJSON for every country, writes:
  data/geo/<ISO3>.geojson   province polygons (id, name) for the country map
  data/geo/world.geojson    country outlines (dissolved from ADM1) with iso3/name/group
  data/world_units.json     one record per province: id, iso3, name, lat, lon, area_km2
  data/countries.json       iso3, name, continent, subregion, group (home / near / world), centroid
Azerbaijan keeps its own district-level data; its ADM1 file is used only for the world outline.
"""
import asyncio
import json
import re
import unicodedata
from pathlib import Path

import httpx
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "gb_adm1"
GEO = ROOT / "data" / "geo"
API = "https://www.geoboundaries.org/api/current/gbOpen/ALL/ADM1/"
# Phase 1 / "Near Azerbaijan": neighbours, Caucasus and Central Asia
NEAR = ["GEO", "ARM", "TUR", "IRN", "RUS", "KAZ", "UZB", "TKM", "KGZ", "TJK", "AFG", "IRQ", "UKR", "MNG"]


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "x"


async def fetch(client, sem, meta):
    iso = meta["boundaryISO"]
    f = RAW / f"{iso}.geojson"
    if f.exists() and f.stat().st_size > 200:
        return
    async with sem:
        for attempt in range(4):
            try:
                r = await client.get(meta["simplifiedGeometryGeoJSON"], timeout=180, follow_redirects=True)
                r.raise_for_status()
                f.write_bytes(r.content)
                return
            except Exception as e:  # noqa: BLE001
                print("retry", iso, attempt, repr(e)[:90], flush=True)
                await asyncio.sleep(5 * (attempt + 1))


async def main():
    RAW.mkdir(parents=True, exist_ok=True)
    GEO.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient() as client:
        metas = (await client.get(API, timeout=120)).json()
        json.dump(metas, open(RAW / "_meta.json", "w"))
        sem = asyncio.Semaphore(6)
        await asyncio.gather(*(fetch(client, sem, m) for m in metas))

    units, countries, world = [], [], []
    seen_iso = set()
    for m in sorted(metas, key=lambda m: m["boundaryISO"]):
        if m["boundaryISO"] in seen_iso:     # the API lists some countries twice (two sources)
            continue
        seen_iso.add(m["boundaryISO"])
        iso = m["boundaryISO"]
        f = RAW / f"{iso}.geojson"
        if not f.exists():
            print("missing", iso)
            continue
        feats, seen, shapes = [], set(), []
        for ft in json.load(open(f))["features"]:
            try:
                g = shape(ft["geometry"]).buffer(0)
            except Exception:  # noqa: BLE001
                continue
            if g.is_empty:
                continue
            name = (ft["properties"].get("shapeName") or "Unknown").strip()
            uid = f"{iso.lower()}-{slug(name)}"
            k = 2
            while uid in seen:
                uid = f"{iso.lower()}-{slug(name)}-{k}"
                k += 1
            seen.add(uid)
            shapes.append(g)
            tol = 0.01 if g.area > 1 else 0.004
            gs = g.simplify(tol, preserve_topology=True)
            p = g.representative_point()
            lat = p.y
            area = round(g.area * 111.32 * 111.32 * abs(__import__("math").cos(__import__("math").radians(lat))), 0)
            feats.append({"type": "Feature", "properties": {"id": uid, "name": name},
                          "geometry": mapping(gs)})
            if iso != "AZE":
                units.append({"id": uid, "iso3": iso, "name": name, "lat": round(p.y, 4), "lon": round(p.x, 4),
                              "area_km2": area})
        if not shapes:
            continue
        group = "home" if iso == "AZE" else "near" if iso in NEAR else "world"
        if iso != "AZE":
            json.dump({"type": "FeatureCollection", "features": feats}, open(GEO / f"{iso}.geojson", "w"),
                      separators=(",", ":"))
        outline = unary_union(shapes)
        c = outline.representative_point()
        countries.append({"iso3": iso, "name": m["boundaryName"], "continent": m.get("Continent", ""),
                          "subregion": m.get("UNSDG-subregion", ""), "group": group, "lat": round(c.y, 3),
                          "lon": round(c.x, 3), "units": len(feats)})
        world.append({"type": "Feature", "properties": {"iso3": iso, "name": m["boundaryName"], "group": group},
                      "geometry": mapping(outline.simplify(0.05 if outline.area > 5 else 0.01,
                                                           preserve_topology=True))})
    json.dump({"type": "FeatureCollection", "features": world}, open(GEO / "world.geojson", "w"),
              separators=(",", ":"))
    json.dump(units, open(ROOT / "data" / "world_units.json", "w"))
    json.dump(countries, open(ROOT / "data" / "countries.json", "w"), indent=0)
    print(len(countries), "countries,", len(units), "provinces,",
          sum(1 for u in units if u["iso3"] in NEAR), "in Near Azerbaijan")


if __name__ == "__main__":
    asyncio.run(main())
