"""Web-sized GeoJSON: rounded coordinates and lighter outlines for the browser.
data/geo/*.geojson -> data/geo_web/*.geojson (world: 2 decimals + extra simplification; provinces: 3 decimals)."""
import json
from pathlib import Path

from shapely.geometry import MultiPolygon, mapping, shape

ROOT = Path(__file__).resolve().parents[2]
SRC, OUT = ROOT / "data" / "geo", ROOT / "data" / "geo_web"


def rnd(o, d):
    if isinstance(o, float):
        return round(o, d)
    if isinstance(o, (list, tuple)):
        return [rnd(x, d) for x in o]
    return o


def slim(path, out, digits, tol_big, tol_small, min_part=0.0):
    fc = json.load(open(path))
    feats = []
    for f in fc["features"]:
        g = shape(f["geometry"])
        if min_part and g.geom_type == "MultiPolygon":
            # drop islets smaller than min_part deg² (keep the largest part so small island states stay)
            g = MultiPolygon([p for p in g.geoms if p.area >= min_part] or [max(g.geoms, key=lambda p: p.area)])
        g = g.simplify(tol_big if g.area > 2 else tol_small, preserve_topology=True)
        if g.is_empty:
            continue
        geom = mapping(g)
        feats.append({"type": "Feature", "properties": f["properties"],
                      "geometry": {"type": geom["type"], "coordinates": rnd(geom["coordinates"], digits)}})
    json.dump({"type": "FeatureCollection", "features": feats}, open(out, "w"), separators=(",", ":"))


def main():
    OUT.mkdir(exist_ok=True)
    slim(SRC / "world.geojson", OUT / "world.geojson", 2, 0.2, 0.04, 0.01)   # ~20k vertices: phones render it
    for p in SRC.glob("*.geojson"):
        if p.name != "world.geojson":
            slim(p, OUT / p.name, 3, 0.02, 0.006)
    tot = sum(f.stat().st_size for f in OUT.glob("*.geojson"))
    print("world", (OUT / "world.geojson").stat().st_size // 1024, "KB; all", tot // 1024 // 1024, "MB")


if __name__ == "__main__":
    main()
