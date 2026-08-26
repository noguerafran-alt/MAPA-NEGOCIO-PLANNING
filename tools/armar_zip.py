# -*- coding: utf-8 -*-
"""Arma el zip que se le pasa a alguien para que lo corra sin instalar nada.

    python tools/armar_zip.py        ->  dist/MAPA-NEGOCIO-PLANNING.zip

Adentro va todo lo necesario, incluido vendor/ con el interprete de Python y
los wheels: en la PC que lo recibe alcanza con descomprimir y hacer doble clic
en iniciar.bat. No van las bases de datos ni los entornos ya desempaquetados.
"""
import fnmatch
import os
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(REPO, 'dist', 'MAPA-NEGOCIO-PLANNING.zip')
RAIZ = 'MAPA-NEGOCIO-PLANNING'      # carpeta dentro del zip: no explota suelto

EXCLUIR_DIR = {'.git', '__pycache__', 'venv', '.venv', 'instance', 'dist',
               '.claude', 'tools'}
EXCLUIR_PAT = ['*.db', '*.db.bak', '*.pyc', '*.log', 'overpass_raw.json']


def main():
    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    n = total = 0
    with zipfile.ZipFile(SALIDA, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for base, dirs, files in os.walk(REPO):
            dirs[:] = [d for d in dirs if d not in EXCLUIR_DIR]
            for f in files:
                if any(fnmatch.fnmatch(f, p) for p in EXCLUIR_PAT):
                    continue
                ruta = os.path.join(base, f)
                rel = os.path.relpath(ruta, REPO)
                # los .whl y el zip del interprete ya vienen comprimidos
                comp = (zipfile.ZIP_STORED if f.endswith(('.whl', '.zip'))
                        else zipfile.ZIP_DEFLATED)
                z.write(ruta, os.path.join(RAIZ, rel), compress_type=comp)
                n += 1
                total += os.path.getsize(ruta)
    print('archivos: %d   crudo: %.1f MB   zip: %.1f MB'
          % (n, total / 1e6, os.path.getsize(SALIDA) / 1e6))
    print(SALIDA)


if __name__ == '__main__':
    main()
