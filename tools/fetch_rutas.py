"""Regenera el GeoJSON de rutas nacionales que usa el mapa.

    python tools/fetch_rutas.py

Salida: static/rutas_nacionales.geojson — un Feature MultiLineString por ruta,
con la propiedad "ref" (ej. "RN 3"). Fuente: OpenStreetMap via Overpass (ODbL).

Solo hace falta correrlo para actualizar el trazado; el GeoJSON ya viene
versionado en el repo. La descarga cruda queda cacheada en tools/overpass_raw.json
(ignorada por git): borrala para forzar una descarga nueva.
"""
import json
import math
import os
import re
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(REPO, "tools", "overpass_raw.json")
OUT = os.path.join(REPO, "static", "rutas_nacionales.geojson")

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def fetch_bbox(s, w, n, e):
    """Descarga una franja. Reintenta y rota de endpoint ante 429/504."""
    q = (f'[out:json][timeout:300];'
         f'way[highway][ref~"^RN"]({s},{w},{n},{e});'
         f'out geom;')
    last = None
    for attempt in range(6):
        url = ENDPOINTS[attempt % len(ENDPOINTS)]
        try:
            req = urllib.request.Request(
                url, data=q.encode(),
                headers={"User-Agent": "mapa-negocio-planning/1.0"})
            with urllib.request.urlopen(req, timeout=420) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as ex:  # 429 / 504 / cortes de red
            last = ex
            wait = 10 * (attempt + 1)
            print(f"    reintento {attempt+1}/6 tras {type(ex).__name__} "
                  f"(espero {wait}s)")
            time.sleep(wait)
    raise RuntimeError(f"franja {s}..{n} fallo: {last}")


def fetch():
    if os.path.exists(RAW) and os.path.getsize(RAW) > 1000:
        print(f"usando cache {RAW} ({os.path.getsize(RAW)/1e6:.1f} MB)")
        return
    # franjas de 5 grados de latitud: cada una es chica para el servidor
    bands = [(s, min(s + 5, -21)) for s in range(-56, -21, 5)]
    seen = set()
    elements = []
    for s, n in bands:
        print(f"  franja lat {s}..{n} ...")
        data = fetch_bbox(s, -74, n, -53)
        got = data.get("elements", [])
        # las franjas se solapan en los bordes: deduplicar por id de way
        new = [e for e in got if e.get("id") not in seen]
        seen.update(e.get("id") for e in got)
        elements.extend(new)
        print(f"    {len(got)} ways ({len(new)} nuevos, {len(elements)} total)")
        time.sleep(3)  # cortesia con el servidor publico
    with open(RAW, "w", encoding="utf-8") as f:
        json.dump({"elements": elements}, f)
    print(f"descargado: {os.path.getsize(RAW)/1e6:.1f} MB")


def norm_ref(ref):
    """'RN3;RN 9' -> ['RN 3', 'RN 9']"""
    out = []
    for part in re.split(r"[;,]", ref or ""):
        m = re.match(r"^\s*RN\s*0*(\d+)\s*$", part.strip(), re.I)
        if m:
            out.append("RN " + m.group(1))
    return out


def perp_dist(p, a, b):
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x - x1, y - y1)
    t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


def simplify(pts, tol):
    """Douglas-Peucker iterativo (evita recursion profunda en tramos largos)."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        dmax, idx = 0.0, i
        for k in range(i + 1, j):
            d = perp_dist(pts[k], pts[i], pts[j])
            if d > dmax:
                dmax, idx = d, k
        if dmax > tol:
            keep[idx] = True
            stack.append((i, idx))
            stack.append((idx, j))
    return [p for p, k in zip(pts, keep) if k]


def stitch(segments):
    """Une tramos que comparten extremo en cadenas continuas."""
    remaining = [list(s) for s in segments]
    by_start = {}
    for i, s in enumerate(remaining):
        by_start.setdefault(s[0], []).append(i)
        by_start.setdefault(s[-1], []).append(i)

    used = [False] * len(remaining)
    chains = []
    for i in range(len(remaining)):
        if used[i]:
            continue
        used[i] = True
        chain = remaining[i]
        # extender por ambos extremos mientras haya un tramo que enganche
        grew = True
        while grew:
            grew = False
            for end, at_front in ((chain[0], True), (chain[-1], False)):
                for j in by_start.get(end, ()):
                    if used[j]:
                        continue
                    seg = remaining[j]
                    if seg[0] == end:
                        add = seg[1:]
                    elif seg[-1] == end:
                        add = seg[-2::-1]
                    else:
                        continue
                    used[j] = True
                    chain = (add[::-1] + chain) if at_front else (chain + add)
                    grew = True
                    break
                if grew:
                    break
        chains.append(chain)
    return chains


def main():
    fetch()
    with open(RAW, "r", encoding="utf-8") as f:
        data = json.load(f)

    els = data.get("elements", [])
    print(f"ways recibidos: {len(els)}")

    TOL = 0.01   # grados (~1.1 km) — suficiente para vista pais/provincia
    MIN_PTS = 2

    feats = []
    n_pts_in = n_pts_out = 0
    by_ref = {}
    for el in els:
        geom = el.get("geometry")
        if not geom:
            continue
        refs = norm_ref(el.get("tags", {}).get("ref", ""))
        if not refs:
            continue
        pts = [(round(g["lon"], 4), round(g["lat"], 4)) for g in geom]
        n_pts_in += len(pts)
        pts = simplify(pts, TOL)
        dedup = [pts[0]]
        for p in pts[1:]:
            if p != dedup[-1]:
                dedup.append(p)
        if len(dedup) < MIN_PTS:
            continue
        n_pts_out += len(dedup)
        for ref in refs:
            by_ref.setdefault(ref, []).append(dedup)

    n_seg_raw = sum(len(v) for v in by_ref.values())
    for ref in sorted(by_ref, key=lambda r: int(r.split()[1])):
        chains = stitch(by_ref[ref])
        feats.append({
            "type": "Feature",
            "properties": {"ref": ref},
            "geometry": {"type": "MultiLineString",
                         "coordinates": [[[p[0], p[1]] for p in c] for c in chains]},
        })

    n_seg_out = sum(len(f["geometry"]["coordinates"]) for f in feats)
    print(f"segmentos: {n_seg_raw} -> {n_seg_out} tras coser")

    fc = {"type": "FeatureCollection",
          "attribution": "(c) OpenStreetMap contributors, ODbL",
          "features": feats}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(fc, f, separators=(",", ":"), ensure_ascii=False)

    size = os.path.getsize(OUT)
    print(f"puntos: {n_pts_in} -> {n_pts_out} ({100*n_pts_out/max(n_pts_in,1):.1f}%)")
    print(f"features: {len(feats)}  rutas distintas: {len(by_ref)}")
    print(f"salida: {size/1e6:.2f} MB -> {OUT}")
    print("rutas:", ", ".join(sorted(by_ref, key=lambda r: int(r.split()[1]))))


if __name__ == "__main__":
    main()
