"""Levanta la app localmente con waitress.

Uso:
    python run_local.py

Normalmente lo llama iniciar.bat, con el interprete embebido de vendor/.
"""
import os
import sys

# El interprete embebido corre en modo aislado (por el python312._pth), y en
# modo aislado Python NO agrega la carpeta del script al sys.path. Sin esto,
# "from app import app" no encuentra nada.
AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

os.environ.setdefault('DATABASE_URL', 'sqlite:///local_dev.db')

from werkzeug.security import generate_password_hash

from app import app, ensure_tables
from models import db, User

# Credenciales del primer arranque. La app escucha solo en 127.0.0.1, asi que
# no queda expuesta; aun asi conviene cambiarlas desde el panel de usuarios.
ADMIN_EMAIL = 'admin@local'
ADMIN_PASS = 'admin'


def crear_admin_si_no_hay():
    """Deja un usuario listo la primera vez, para no depender de la consola.

    El paquete portable se abre con doble clic: si la unica forma de crear el
    primer usuario fuera un comando de Flask, nadie podria entrar.
    """
    if User.query.count():
        return None
    db.session.add(User(
        email=ADMIN_EMAIL, nombre='Administrador', nivel=3, is_active=True,
        password_hash=generate_password_hash(ADMIN_PASS),
    ))
    db.session.commit()
    return ADMIN_EMAIL


with app.app_context():
    ensure_tables()
    creado = crear_admin_si_no_hay()

if __name__ == '__main__':
    from waitress import serve
    HOST = '127.0.0.1'
    PORT = 5000
    if creado:
        print('')
        print('=' * 62)
        print(' PRIMER ARRANQUE: se creo un usuario para poder entrar')
        print('')
        print('   Usuario:     %s' % ADMIN_EMAIL)
        print('   Contrasena:  %s' % ADMIN_PASS)
        print('')
        print(' Cambiala desde Admin -> Usuarios cuando entres.')
        print('=' * 62)
        print('', flush=True)
    print('Mapa Gasoil/Naftas corriendo en http://%s:%d' % (HOST, PORT))
    print('Deja esta ventana abierta. Para cerrarlo: Ctrl+C.')
    # channel_timeout por defecto es 120s: la carga del historico completo
    # puede pasarlo y la conexion se corta sin explicacion.
    serve(app, host=HOST, port=PORT, threads=4, channel_timeout=1800)
