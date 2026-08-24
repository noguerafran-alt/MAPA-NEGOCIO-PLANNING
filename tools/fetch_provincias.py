"""Regenera el GeoJSON de límites provinciales que usa el mapa.

    python tools/fetch_provincias.py

Salida: static/provincias.geojson — un Feature (Polygon o MultiPolygon) por
provincia, con la propiedad "name" ya normalizada al nombre canónico que usa
la app (`CANONICAL_PROVINCES`). Fuente: OpenStreetMap via Overpass (ODbL).

Sólo hace falta correrlo para actualizar los límites; el GeoJSON ya viene
versionado en el repo. La descarga cruda queda cacheada en
tools/overpass_provincias_raw.json (ignorada por git): borrala para forzar
una descarga nueva.

Los límites se simplifican con Douglas-Peucker: el archivo crudo ronda las
decenas de MB y el mapa sólo necesita la silueta, no la costa metro a metro.
"""
import json
import math
import os
import sys
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from parser_volumen import CANONICAL_PROVINCES  # noqa: E402

RAW = os.path.join(REPO, "tools", "overpass_provincias_raw.json")
OUT = os.path.join(REPO, "static", "provincias.geojson")

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Tolerancia del simplificado, en grados. 0.01 grados ~ 1 km: suficiente para
# una silueta provincial a escala pais y deja el archivo en pocos cientos de KB.
TOL = 0.01

# El nombre de OSM no siempre coincide con el canonico de la app.
ALIAS = {
    'Ciudad Autónoma de Buenos Aires': 'CABA',
    'Provincia de Buenos Aires': 'Buenos Aires',
    'Tierra del Fuego, Antártida e Islas del Atlántico Sur': 'Tierra del Fuego',
}


def fetch():
    """Baja las relaciones de admin_level=4 de Argentina."""
    if os.path.exists(RAW) and os.path.getsize(RAW) > 1000:
        print(f"usando cache {RAW} ({os.path.getsize(RAW)/1e6:.1f} MB)")
        return
    q = ('[out:json][timeout:600];'
         'area["ISO3166-1"="AR"][admin_level=2]->.ar;'
         'relation(area.ar)["admin_level"="4"]["boundary"="administrative"];'
         'out geom;')
    last = None
    for attempt in range(6):
        url = ENDPOINTS[attempt % len(ENDPOINTS)]
        try:
            print(f"  descargando de {url} (intento {attempt+1})")
            req = urllib.request.Request(
                url, data=q.encode(),
                headers={"User-Agent": "mapa-negocio-planning/1.0"})
            with urllib.request.urlopen(req, timeout=900) as r:
                data = r.read()
            with open(RAW, "wb") as f:
                f.write(data)
            print(f"  guardado {RAW} ({len(data)/1e6:.1f} MB)")
            return
        except Exception as ex:      # 429 / 504 / cortes de red
            last = ex
            wait = 10 * (attempt + 1)
            print(f"    reintento tras {type(ex).__name__} (espero {wait}s)")
            time.sleep(wait)
    raise RuntimeError(f"descarga fallida: {last}")


def perp_dist(p, a, b):
    if a == b:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def simplify(pts, tol):
    """Douglas-Peucker iterativo (recursivo desborda con anillos largos)."""
    if len(pts) < 3:
        return pts[:]
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    pila = [(0, len(pts) - 1)]
    while pila:
        i, j = pila.pop()
        peor, idx = 0.0, None
        for k in range(i + 1, j):
            d = perp_dist(pts[k], pts[i], pts[j])
            if d > peor:
                peor, idx = d, k
        if idx is not None and peor > tol:
            keep[idx] = True
            pila.append((i, idx))
            pila.append((idx, j))
    return [p for p, k in zip(pts, keep) if k]


def anillos(rel):
    """Cose los ways de una relacion en anillos cerrados.

    Overpass devuelve los tramos sueltos y en cualquier orden; hay que
    encadenarlos por extremos hasta cerrar cada anillo. Los que no cierran se
    descartan: son tramos incompletos y dibujarlos rompe el poligono.
    """
    exteriores, interiores = [], []
    for rol, destino in (('outer', exteriores), ('inner', interiores)):
        tramos = [
            [(p['lon'], p['lat']) for p in m['geometry']]
            for m in rel.get('members', [])
            if m.get('type') == 'way' and m.get('geometry')
            and (m.get('role') or 'outer') == rol
        ]
        while tramos:
            cadena = tramos.pop(0)
            movio = True
            while movio and cadena[0] != cadena[-1]:
                movio = False
                for i, t in enumerate(tramos):
                    if t[0] == cadena[-1]:
                        cadena = cadena + t[1:]
                    elif t[-1] == cadena[-1]:
                        cadena = cadena + t[-2::-1]
                    elif t[-1] == cadena[0]:
                        cadena = t[:-1] + cadena
                    elif t[0] == cadena[0]:
                        cadena = t[:0:-1] + cadena
                    else:
                        continue
                    tramos.pop(i)
                    movio = True
                    break
            if cadena[0] == cadena[-1] and len(cadena) >= 4:
                destino.append(cadena)
    return exteriores, interiores


def area_anillo(anillo):
    s = 0.0
    for (x1, y1), (x2, y2) in zip(anillo, anillo[1:]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def main():
    fetch()
    with open(RAW, encoding="utf-8") as f:
        data = json.load(f)

    canon = {n.lower(): n for n in CANONICAL_PROVINCES}
    features, vistos = [], set()

    for rel in data.get("elements", []):
        tags = rel.get("tags", {})
        crudo = tags.get("name", "")
        nombre = ALIAS.get(crudo) or canon.get(crudo.lower())
        if not nombre:
            # Sin nombre canonico no se puede casar con los datos: mejor
            # avisar que dibujar un poligono que nadie va a poder resaltar.
            print(f"  ignorada (nombre sin equivalente): {crudo!r}")
            continue
        if nombre in vistos:
            continue

        ext, inn = anillos(rel)
        if not ext:
            print(f"  ignorada (no cerro ningun anillo): {nombre}")
            continue
        vistos.add(nombre)

        poligonos = []
        for e in ext:
            e = simplify(e, TOL)
            if len(e) < 4:
                continue
            if e[0] != e[-1]:
                e.append(e[0])
            poligonos.append([[list(p) for p in e]])
        if not poligonos:
            vistos.discard(nombre)
            continue
        if inn:
            # Cada hueco va con el exterior que lo contiene; con anillos
            # provinciales alcanza con asignarlos al exterior mas grande.
            mayor = max(range(len(poligonos)),
                        key=lambda i: area_anillo([tuple(p) for p in poligonos[i][0]]))
            for h in inn:
                h = simplify(h, TOL)
                if len(h) < 4:
                    continue
                if h[0] != h[-1]:
                    h.append(h[0])
                poligonos[mayor].append([list(p) for p in h])

        geom = ({"type": "Polygon", "coordinates": poligonos[0]}
                if len(poligonos) == 1
                else {"type": "MultiPolygon", "coordinates": poligonos})
        features.append({"type": "Feature",
                         "properties": {"name": nombre},
                         "geometry": geom})

    faltan = [n for n in CANONICAL_PROVINCES if n not in vistos]
    if faltan:
        print(f"  OJO, sin poligono: {', '.join(faltan)}")

    gj = {"type": "FeatureCollection", "features": features}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(gj, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(features)} provincias -> {OUT} "
          f"({os.path.getsize(OUT)/1e6:.2f} MB)")


if __name__ == "__main__":
    main()
