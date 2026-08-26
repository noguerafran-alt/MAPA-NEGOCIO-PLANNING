# -*- coding: utf-8 -*-
r"""Termina de armar el entorno, offline, adentro del interprete embebido.

Lo corre preparar_entorno.bat justo despues de desempaquetar
vendor/python-3.12.10-embed-amd64.zip, con el python.exe recien salido del zip:

    %RUNTIME%\python.exe vendor\preparar.py

Tres pasos, ninguno sale a la red:

  1. Reescribir python312._pth, que define el sys.path del interprete embebido.
     El zip viene con site-packages apagado; sin esto pip no funciona.
  2. Descomprimir el wheel de pip adentro de site-packages. Un wheel es un zip:
     extraerlo alcanza para que "python -m pip" ande.
  3. pip install --no-index de vendor/requirements-lock.txt.

Solo usa la biblioteca estandar, porque cuando arranca no hay nada instalado.
Es idempotente: correrlo dos veces no rompe nada.
"""
import os
import subprocess
import sys
import zipfile

VENDOR = os.path.dirname(os.path.abspath(__file__))
RUNTIME = sys.prefix
SITE = os.path.join(RUNTIME, 'Lib', 'site-packages')
LOCK = os.path.join(VENDOR, 'requirements-lock.txt')
WHEELS = os.path.join(VENDOR, 'wheels')

# Si algo de esto no importa al final, el entorno quedo mal.
IMPRESCINDIBLES = ['flask', 'flask_sqlalchemy', 'sqlalchemy', 'openpyxl',
                   'waitress', 'flask_compress', 'flask_limiter']


def escribir_pth():
    """Deja el sys.path del interprete apuntando a site-packages.

    OJO: la sola existencia de este archivo pone a Python en modo aislado, y en
    modo aislado NO se agrega el directorio del script al sys.path. Por eso
    run_local.py hace sys.path.insert() de su propia carpeta.
    """
    pth = os.path.join(RUNTIME, 'python312._pth')
    lineas = [
        'python312.zip',                    # la biblioteca estandar, comprimida
        '.',                                # aca viven _sqlite3.pyd y compania
        'Lib' + os.sep + 'site-packages',   # lo que instala pip
        'import site',                      # sin esta linea pip no arranca
    ]
    with open(pth, 'w', encoding='ascii', newline='\n') as fh:
        fh.write('\n'.join(lineas) + '\n')
    print('  python312._pth escrito')


def instalar_pip():
    # Se pregunta al disco y no con "import pip": este proceso arranco con el
    # _pth viejo del zip, asi que su sys.path ya quedo fijado sin site-packages
    # y un import daria siempre negativo.
    if os.path.isdir(os.path.join(SITE, 'pip')):
        print('  pip ya estaba')
        return
    candidatos = sorted(n for n in os.listdir(WHEELS)
                        if n.startswith('pip-') and n.endswith('.whl'))
    if not candidatos:
        raise SystemExit('FALTA el wheel de pip en %s' % WHEELS)
    os.makedirs(SITE, exist_ok=True)
    with zipfile.ZipFile(os.path.join(WHEELS, candidatos[-1])) as z:
        z.extractall(SITE)
    print('  pip instalado desde %s' % candidatos[-1])


def instalar_paquetes():
    if not os.path.exists(LOCK):
        raise SystemExit('FALTA %s' % LOCK)
    # --no-index es la garantia de que no sale a la red: si falta un wheel,
    # esto falla en vez de bajarlo de PyPI por atras.
    cmd = [sys.executable, '-m', 'pip', 'install', '--no-index', '--no-cache-dir',
           '--disable-pip-version-check', '--no-warn-script-location',
           '--find-links', WHEELS, '-r', LOCK]
    print('  pip install --no-index --find-links vendor/wheels -r vendor/requirements-lock.txt')
    if subprocess.run(cmd).returncode != 0:
        raise SystemExit('pip install fallo')


def chequear():
    """Prueba los imports en un proceso nuevo.

    Tiene que ser nuevo: el sys.path de ESTE proceso se fijo al arrancar, con el
    _pth original del zip. De paso es el chequeo honesto, porque prueba lo mismo
    que va a hacer run_local.py.
    """
    faltan = []
    for mod in IMPRESCINDIBLES:
        r = subprocess.run([sys.executable, '-c', 'import ' + mod],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if r.returncode != 0:
            faltan.append(mod)
    if faltan:
        raise SystemExit('quedaron paquetes sin instalar: ' + ', '.join(faltan))
    print('  todo importa')


def main():
    print('Configurando el interprete...')
    escribir_pth()
    instalar_pip()
    print('Instalando los paquetes (nada sale a internet)...')
    instalar_paquetes()
    print('Chequeando...')
    chequear()
    print('Entorno listo en %s' % RUNTIME)


if __name__ == '__main__':
    try:
        main()
    except OSError as e:
        # WinError 206 = ruta demasiado larga. Pasa de verdad: site-packages
        # suma ~140 caracteres sobre RUNTIME y Windows corta en 260. Sin este
        # mensaje el error que se ve manda a buscar al lugar equivocado.
        if getattr(e, 'winerror', None) == 206 or 'too long' in str(e) or 'demasiado largo' in str(e):
            raise SystemExit(
                'La ruta del entorno es demasiado larga para Windows:\n  %s\n'
                'Windows corta los nombres en 260 caracteres y site-packages\n'
                'suma ~140. Move la carpeta a una ruta mas corta.' % RUNTIME)
        raise
