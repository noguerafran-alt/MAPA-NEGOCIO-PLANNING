"""Parser de VOLUMEN.csv (separador ;).

Formato esperado:
    Año;Mes;Petrolera;provincia;Sector;producto;Volumen

Volumen puede venir con puntos como separador de miles (ej. 10.216.123)
o con notación científica errónea / valores gigantes → se normalizan.
"""

import csv
import re
from collections import defaultdict


# Normalización de nombres de provincia
PROVINCE_ALIASES = {
    'capital federal': 'CABA',
    'caba': 'CABA',
    'ciudad autonoma de buenos aires': 'CABA',
    'entre rios': 'Entre Ríos',
    'entre ríos': 'Entre Ríos',
    'rio negro': 'Río Negro',
    'río negro': 'Río Negro',
    'tucuman': 'Tucumán',
    'tucumán': 'Tucumán',
    'neuquen': 'Neuquén',
    'córdoba': 'Córdoba',
    'cordoba': 'Córdoba',
    'santa fe': 'Santa Fe',
    'tierra del fuego': 'Tierra del Fuego',
    'santiago del estero': 'Santiago del Estero',
    'la pampa': 'La Pampa',
    'la rioja': 'La Rioja',
    'san juan': 'San Juan',
    'san luis': 'San Luis',
    'santa cruz': 'Santa Cruz',
    'buenos aires': 'Buenos Aires',
    'estado nacional': 'Estado Nacional',
    'no aplica': 'No aplica',
    'provincia': 'No aplica',
}

CANONICAL_PROVINCES = [
    'Buenos Aires', 'CABA', 'Catamarca', 'Chaco', 'Chubut', 'Córdoba',
    'Corrientes', 'Entre Ríos', 'Formosa', 'Jujuy', 'La Pampa', 'La Rioja',
    'Mendoza', 'Misiones', 'Neuquén', 'Río Negro', 'Salta', 'San Juan',
    'San Luis', 'Santa Cruz', 'Santa Fe', 'Santiago del Estero',
    'Tierra del Fuego', 'Tucumán',
]


def normalize_province(name: str) -> str:
    if not name:
        return 'No aplica'
    key = name.strip().lower()
    key_ascii = (key
                 .replace('á', 'a').replace('é', 'e').replace('í', 'i')
                 .replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n'))
    for alias, canon in PROVINCE_ALIASES.items():
        alias_ascii = (alias
                       .replace('á', 'a').replace('é', 'e').replace('í', 'i')
                       .replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n'))
        if key == alias or key_ascii == alias_ascii:
            return canon
    return name.strip().title()


def parse_volumen(raw: str) -> float:
    if raw is None:
        return 0.0
    s = str(raw).strip()
    if not s or s in ('-', 'S/N', 'null', 'None'):
        return 0.0
    s = s.replace(' ', '')
    if s.count('.') > 1:
        parts = s.split('.')
        if len(parts[-1]) <= 2:
            s = ''.join(parts[:-1]) + '.' + parts[-1]
        else:
            s = ''.join(parts)
    s = s.replace(',', '.')
    try:
        val = float(s)
    except ValueError:
        return 0.0
    if abs(val) > 50_000_000:
        return 0.0
    return val


def parse_csv(file_obj, encoding='utf-8'):
    content = file_obj.read()
    if isinstance(content, bytes):
        for enc in (encoding, 'utf-8-sig', 'latin-1', 'cp1252'):
            try:
                text = content.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = content.decode('utf-8', errors='replace')
    else:
        text = content
    if text.startswith('\ufeff'):
        text = text[1:]
    reader = csv.DictReader(text.splitlines(), delimiter=';')
    field_map = {}
    for f in (reader.fieldnames or []):
        fl = f.strip().lower()
        if fl in ('año', 'anio', 'year'):
            field_map['anio'] = f
        elif fl in ('mes', 'month'):
            field_map['mes'] = f
        elif fl in ('petrolera',):
            field_map['petrolera'] = f
        elif fl in ('provincia',):
            field_map['provincia'] = f
        elif fl in ('sector',):
            field_map['sector'] = f
        elif fl in ('producto',):
            field_map['producto'] = f
        elif fl in ('volumen', 'volume'):
            field_map['volumen'] = f
    required = {'anio', 'mes', 'petrolera', 'provincia', 'sector', 'producto', 'volumen'}
    if not required.issubset(field_map.keys()):
        missing = required - set(field_map.keys())
        raise ValueError(f"Columnas faltantes en el CSV: {missing}. Columnas encontradas: {reader.fieldnames}")
    rows = []
    skipped = 0
    for row in reader:
        try:
            anio = int(float(str(row[field_map['anio']]).strip()))
            mes = int(float(str(row[field_map['mes']]).strip()))
            if not (1 <= mes <= 12):
                skipped += 1
                continue
            petrolera = str(row[field_map['petrolera']]).strip()
            provincia = normalize_province(str(row[field_map['provincia']]))
            sector = str(row[field_map['sector']]).strip() or 'S/N'
            producto = str(row[field_map['producto']]).strip().upper()
            if producto not in ('GO2', 'GO3', 'N2', 'N3'):
                skipped += 1
                continue
            volumen = parse_volumen(row[field_map['volumen']])
            rows.append({
                'anio': anio, 'mes': mes, 'petrolera': petrolera,
                'provincia': provincia, 'sector': sector,
                'producto': producto, 'volumen': volumen,
            })
        except (ValueError, TypeError, KeyError):
            skipped += 1
            continue
    return rows, skipped
