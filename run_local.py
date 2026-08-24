"""Levanta la app localmente con waitress.

Uso:
    python run_local.py
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///local_dev.db')

from app import app, ensure_tables

with app.app_context():
    ensure_tables()

if __name__ == '__main__':
    from waitress import serve
    HOST = '127.0.0.1'
    PORT = 5000
    print(f"Mapa Gasoil/Naftas corriendo en http://{HOST}:{PORT}")
    print("Dejá esta ventana abierta. Para cerrarlo: Ctrl+C.")
    serve(app, host=HOST, port=PORT, threads=4)
