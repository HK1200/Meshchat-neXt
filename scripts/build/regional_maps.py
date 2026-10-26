"""Build raster MBTiles from an official, locally extracted Protomaps archive.

Build-only dependencies: pillow==13.0.0 mapbox-vector-tile==2.2.0 pmtiles==3.8.1.
No tiles are downloaded by this renderer. Input is a bounded regional extract.
"""

import argparse
import gzip
import io
import os
import sqlite3
import time
from concurrent.futures import ProcessPoolExecutor
from contextlib import closing
from itertools import islice
from pathlib import Path

import mapbox_vector_tile
from PIL import Image, ImageDraw, ImageFont
from pmtiles.reader import MmapSource, all_tiles

WATER = "#0f172a"
LAND = "#1e293b"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_font = None


def text_name(p):
    value = p.get("name:en") or p.get("name") or ""
    return value if isinstance(value, str) else ""


def render(item):
    global _font
    (z, x, y), raw = item
    if raw.startswith(b"\x1f\x8b"):
        raw = gzip.decompress(raw)
    layers = mapbox_vector_tile.decode(raw, default_options={"y_coord_down": True})
    image = Image.new("RGB", (256, 256), WATER)
    draw = ImageDraw.Draw(image)
    if _font is None:
        _font = ImageFont.truetype(FONT, 12)
    labels = []

    def xy(p, extent):
        return (p[0] * 256 / extent, p[1] * 256 / extent)

    def polygon(coords, extent, color, hole):
        if not coords:
            return
        draw.polygon([xy(p, extent) for p in coords[0]], fill=color)
        for ring in coords[1:]:
            draw.polygon([xy(p, extent) for p in ring], fill=hole)

    def geom(g, extent, color, hole=LAND, width=1):
        typ, c = g.get("type"), g.get("coordinates", [])
        if typ == "Polygon":
            polygon(c, extent, color, hole)
        elif typ == "MultiPolygon":
            for poly in c:
                polygon(poly, extent, color, hole)
        elif typ == "LineString" and len(c) > 1:
            draw.line(
                [xy(p, extent) for p in c], fill=color, width=width, joint="curve"
            )
        elif typ == "MultiLineString":
            for line in c:
                if len(line) > 1:
                    draw.line(
                        [xy(p, extent) for p in line],
                        fill=color,
                        width=width,
                        joint="curve",
                    )

    for layername in [
        "earth",
        "landcover",
        "landuse",
        "water",
        "boundaries",
        "roads",
        "buildings",
        "places",
        "pois",
    ]:
        layer = layers.get(layername, {})
        extent = layer.get("extent", 4096)
        for f in layer.get("features", []):
            p, g = f.get("properties", {}), f.get("geometry") or {}
            kind = p.get("kind", "")
            typ = g.get("type")
            if p.get("min_zoom", 0) > z:
                continue
            if layername == "earth":
                geom(g, extent, LAND, WATER)
            elif layername in ("landcover", "landuse"):
                colors = {
                    "forest": "#233e37",
                    "wood": "#233e37",
                    "park": "#29443a",
                    "national_park": "#29443a",
                    "nature_reserve": "#29443a",
                    "grassland": "#344339",
                    "glacier": "#8da5b5",
                    "urban_area": "#394453",
                    "residential": "#303d4e",
                }
                if kind in colors:
                    geom(g, extent, colors[kind])
            elif layername == "water":
                geom(g, extent, "#17364e", LAND)
            elif layername == "boundaries" and kind in ("country", "region"):
                geom(
                    g,
                    extent,
                    "#c79bbd" if kind == "country" else "#68778c",
                    width=2 if kind == "country" else 1,
                )
            elif layername == "roads":
                color = {
                    "highway": "#dfb780",
                    "major_road": "#a8b4bd",
                    "minor_road": "#708496",
                    "path": "#657f73",
                    "ferry": "#41899a",
                    "rail": "#8c8993",
                }.get(kind)
                if color is None or (kind in ("minor_road", "path", "rail") and z < 10):
                    continue
                width = 2 if kind == "highway" and z >= 9 else 1
                geom(g, extent, color, width=width)
                if (
                    z >= 11
                    and typ == "LineString"
                    and kind in ("highway", "major_road")
                ):
                    coords = g.get("coordinates", [])
                    name = p.get("ref") or text_name(p)
                    if (
                        name
                        and isinstance(name, str)
                        and len(name) < 28
                        and len(coords) > 1
                    ):
                        length = sum(
                            abs(coords[i][0] - coords[i - 1][0])
                            + abs(coords[i][1] - coords[i - 1][1])
                            for i in range(1, len(coords))
                        )
                        if length * 256 / extent > 100:
                            labels.append(
                                (3, name, xy(coords[len(coords) // 2], extent))
                            )
            elif layername == "buildings" and z >= 12:
                geom(g, extent, "#4c5969")
            elif (
                layername == "places"
                and typ == "Point"
                and kind in ("country", "region", "locality")
            ):
                name = text_name(p)
                if name:
                    point = xy(g["coordinates"], extent)
                    pop = p.get("population") or 0
                    priority = 0 if kind != "locality" else 1 if pop > 50000 else 2
                    labels.append((priority, name, point))
    occupied = []
    for priority, name, (xpos, ypos) in sorted(labels, key=lambda item: item[0]):
        if not -30 < xpos < 286 or not -15 < ypos < 271:
            continue
        box = draw.textbbox(
            (xpos + 4, ypos), name, font=_font, anchor="lm", stroke_width=1
        )
        if any(
            not (box[2] + 3 < a or c + 3 < box[0] or box[3] + 2 < b or d + 2 < box[1])
            for a, b, c, d in occupied
        ):
            continue
        occupied.append(box)
        if priority < 3:
            draw.ellipse((xpos - 1, ypos - 1, xpos + 1, ypos + 1), fill="#f1f5f9")
        draw.text(
            (xpos + 4, ypos),
            name,
            font=_font,
            anchor="lm",
            fill="#e2e8f0" if priority < 3 else "#c7d2df",
            stroke_width=2,
            stroke_fill="#0f172a",
        )
    buffer = io.BytesIO()
    image.quantize(colors=128).save(buffer, format="PNG", compress_level=6)
    return z, x, (1 << z) - 1 - y, buffer.getvalue()


def open_output(path, name, maxzoom, world):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".building")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    db.execute("PRAGMA journal_mode=MEMORY")
    db.execute("PRAGMA temp_store=MEMORY")
    db.execute("CREATE TABLE metadata(name TEXT PRIMARY KEY,value TEXT)")
    db.execute(
        "CREATE TABLE tiles(zoom_level INTEGER,tile_column INTEGER,tile_row INTEGER,tile_data BLOB,PRIMARY KEY(zoom_level,tile_column,tile_row))"
    )
    with closing(sqlite3.connect(world)) as src:
        db.executemany(
            "INSERT INTO tiles VALUES (?,?,?,?)",
            src.execute("SELECT * FROM tiles WHERE zoom_level<=4"),
        )
    metadata = {
        "name": name,
        "format": "png",
        "type": "baselayer",
        "version": "2026.10.25.1",
        "bounds": "-180,-85.05112878,180,85.05112878",
        "center": "-122,47.5,6",
        "minzoom": "0",
        "maxzoom": str(maxzoom),
        "meshchatnext:world_maxzoom": "4",
        "meshchatnext:regional_bounds": "-128,42,-110,53",
        "meshchatnext:regional_maxzoom": str(maxzoom),
        "meshchatnext:source": "https://build.protomaps.com/20261025.pmtiles",
        "meshchatnext:source_date": "2026-10-25",
        "attribution": "© OpenStreetMap contributors · Natural Earth. Protomaps basemap, ODbL.",
        "description": f"PNW and southern BC: Washington, Oregon, Idaho and southern British Columbia, zooms 5-{maxzoom}. World overview zooms 0-4. Regional context, not turn-by-turn navigation.",
    }
    if maxzoom == 9:
        metadata["meshchatnext:starter_revision"] = "20261025-pnw-overview-1"
    db.executemany("INSERT INTO metadata VALUES (?,?)", metadata.items())
    db.commit()
    return db, tmp, path


def init_worker(font):
    global FONT, _font
    FONT = font
    _font = None


def main():
    global FONT
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("--world", required=True)
    parser.add_argument("--overview", required=True)
    parser.add_argument("--detail", required=True)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--font", default=FONT)
    args = parser.parse_args()
    FONT = args.font
    if not 1 <= args.workers <= 8:
        parser.error("workers must be between 1 and 8")
    if Path(args.source).stat().st_size > 2 * 1024**3:
        parser.error("use a bounded regional extract smaller than 2 GiB")
    overview = open_output(
        args.overview,
        "Meshchat neXt starter world + PNW / southern BC overview",
        9,
        args.world,
    )
    detail = open_output(
        args.detail, "Meshchat neXt PNW / southern BC road detail", 12, args.world
    )
    count = 0
    start = time.monotonic()
    try:
        with (
            open(args.source, "rb") as source,
            ProcessPoolExecutor(
                max_workers=args.workers, initializer=init_worker, initargs=(args.font,)
            ) as pool,
        ):
            items = (
                item for item in all_tiles(MmapSource(source)) if 5 <= item[0][0] <= 12
            )
            while True:
                batch = list(islice(items, 128))
                if not batch:
                    break
                rendered = list(pool.map(render, batch, chunksize=8))
                detail[0].executemany(
                    "INSERT OR REPLACE INTO tiles VALUES (?,?,?,?)", rendered
                )
                overview[0].executemany(
                    "INSERT OR REPLACE INTO tiles VALUES (?,?,?,?)",
                    [row for row in rendered if row[0] <= 9],
                )
                for target in [detail, overview]:
                    target[0].commit()
                count += len(batch)
                if count % 1024 == 0:
                    print(
                        f"Rendered {count} tiles in {time.monotonic() - start:.0f}s",
                        flush=True,
                    )
        for db, tmp, path in [overview, detail]:
            db.execute("PRAGMA optimize")
            db.close()
            os.replace(tmp, path)
            print(
                f"{path.name}: {path.stat().st_size / 1024 / 1024:.1f} MiB", flush=True
            )
    finally:
        for db, _, _ in [overview, detail]:
            try:
                db.close()
            except sqlite3.Error:
                pass


if __name__ == "__main__":
    main()
