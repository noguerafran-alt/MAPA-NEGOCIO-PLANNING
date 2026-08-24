import os
import json
from datetime import datetime
from functools import wraps

from flask import (Flask, jsonify, request, render_template, session,
                   redirect, url_for, Response)
from flask_compress import Compress
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, and_
import click

from models import (db, VolumeMonthly, VolumeUploadLog, RegressionPoint,
                    RegressionConfig, Province, User)
from parser_volumen import parse_csv, CANONICAL_PROVINCES
from parser_regresion import parse_regresion_excel
from provinces_data import PROVINCE_CENTROIDS, REGION

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-me-planning')
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    MAX_CONTENT_LENGTH=40 * 1024 * 1024,
)

db_url = os.environ.get('DATABASE_URL', 'sqlite:///local_dev.db')
if db_url.startswith('postgres://'):
    db_url = db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)
Compress(app)

limiter = Limiter(get_remote_address, app=app, default_limits=["200 per minute"])


def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    return User.query.get(uid)


def login_required(min_nivel=1):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user or not user.is_active or user.nivel < min_nivel:
                if request.path.startswith('/api/'):
                    return jsonify({'error': 'No autorizado'}), 401
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return wrapped
    return decorator


def ensure_tables():
    db.create_all()
    if Province.query.count() == 0:
        for name, (lat, lon) in PROVINCE_CENTROIDS.items():
            db.session.add(Province(
                name=name,
                name_display=name,
                lat=lat,
                lon=lon,
                region=REGION.get(name, ''),
            ))
        db.session.commit()
        app.logger.info("Provincias sembradas: %d", len(PROVINCE_CENTROIDS))


@app.cli.command('autorizar-usuario')
@click.option('--email', required=True)
@click.option('--nombre', default='')
@click.option('--nivel', default=3, type=int)
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True)
def autorizar_usuario(email, nombre, nivel, password):
    user = User.query.filter_by(email=email.lower().strip()).first()
    if not user:
        user = User(email=email.lower().strip())
        db.session.add(user)
    user.nombre = nombre or email
    user.nivel = nivel
    user.is_active = True
    user.password_hash = generate_password_hash(password)
    db.session.commit()
    click.echo(f"Usuario {email} autorizado con nivel {nivel}.")


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').lower().strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email, is_active=True).first()
        if user and user.password_hash and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            user.last_login_at = datetime.utcnow()
            db.session.commit()
            return redirect(url_for('index'))
        return render_template('login.html', error='Credenciales incorrectas o cuenta no autorizada')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@login_required(1)
def index():
    return render_template('index.html', user=current_user())


@app.route('/proyecciones')
@login_required(1)
def proyecciones():
    return render_template('proyecciones.html', user=current_user())


@app.route('/admin')
@login_required(2)
def admin():
    return render_template('admin.html', user=current_user())


@app.route('/api/filtros')
@login_required(1)
def api_filtros():
    anios = db.session.query(VolumeMonthly.anio).distinct().order_by(VolumeMonthly.anio).all()
    petroleras = db.session.query(VolumeMonthly.petrolera).distinct().order_by(VolumeMonthly.petrolera).all()
    sectores = db.session.query(VolumeMonthly.sector).distinct().order_by(VolumeMonthly.sector).all()
    return jsonify({
        'anios': [a[0] for a in anios],
        'petroleras': [p[0] for p in petroleras],
        'sectores': [s[0] for s in sectores],
        'productos': ['GO2', 'GO3', 'N2', 'N3'],
        'provincias': CANONICAL_PROVINCES,
    })


@app.route('/api/volumenes')
@login_required(1)
def api_volumenes():
    anio_desde = request.args.get('anio_desde', type=int)
    anio_hasta = request.args.get('anio_hasta', type=int)
    productos = [p.strip() for p in request.args.get('productos', 'GO2,GO3,N2,N3').split(',') if p.strip()]
    sectores = [s.strip() for s in request.args.get('sectores', '').split(',') if s.strip()]
    petroleras = [p.strip() for p in request.args.get('petroleras', '').split(',') if p.strip()]

    q = db.session.query(
        VolumeMonthly.provincia,
        VolumeMonthly.producto,
        func.sum(VolumeMonthly.volumen).label('total')
    )
    if anio_desde:
        q = q.filter(VolumeMonthly.anio >= anio_desde)
    if anio_hasta:
        q = q.filter(VolumeMonthly.anio <= anio_hasta)
    if productos:
        q = q.filter(VolumeMonthly.producto.in_(productos))
    if sectores:
        q = q.filter(VolumeMonthly.sector.in_(sectores))
    if petroleras:
        q = q.filter(VolumeMonthly.petrolera.in_(petroleras))

    q = q.group_by(VolumeMonthly.provincia, VolumeMonthly.producto)
    rows = q.all()

    result = {}
    for prov, prod, total in rows:
        if prov not in result:
            result[prov] = {'GO2': 0.0, 'GO3': 0.0, 'N2': 0.0, 'N3': 0.0, 'total': 0.0}
        result[prov][prod] = float(total or 0)
        result[prov]['total'] += float(total or 0)

    for name, data in result.items():
        c = PROVINCE_CENTROIDS.get(name)
        if c:
            data['lat'], data['lon'] = c

    return jsonify(result)


@app.route('/api/serie')
@login_required(1)
def api_serie():
    provincia = request.args.get('provincia')
    productos = [p.strip() for p in request.args.get('productos', 'GO2,GO3,N2,N3').split(',') if p.strip()]

    q = db.session.query(
        VolumeMonthly.anio,
        VolumeMonthly.mes,
        func.sum(VolumeMonthly.volumen).label('total')
    )
    if provincia:
        q = q.filter(VolumeMonthly.provincia == provincia)
    if productos:
        q = q.filter(VolumeMonthly.producto.in_(productos))
    q = q.group_by(VolumeMonthly.anio, VolumeMonthly.mes).order_by(VolumeMonthly.anio, VolumeMonthly.mes)
    rows = q.all()
    return jsonify([
        {'anio': r.anio, 'mes': r.mes, 'total': float(r.total or 0)}
        for r in rows
    ])


@app.route('/api/proyeccion')
@login_required(1)
def api_proyeccion():
    cfg = RegressionConfig.query.order_by(RegressionConfig.id.desc()).first()
    if not cfg:
        return jsonify({'error': 'No hay modelo de regresión cargado. Subilo desde Admin.'}), 404

    points = RegressionPoint.query.order_by(RegressionPoint.anio, RegressionPoint.mes).all()
    serie = []
    for p in points:
        pred = cfg.b1 * p.x1 + cfg.b2 * p.x2 + cfg.b3 * p.x3 + cfg.b4 * p.x4
        serie.append({
            'anio': p.anio, 'mes': p.mes, 'yt': p.yt, 'predicho': pred,
            'x1': p.x1, 'x2': p.x2, 'x3': p.x3, 'x4': p.x4,
        })

    return jsonify({
        'coeficientes': {'b1': cfg.b1, 'b2': cfg.b2, 'b3': cfg.b3, 'b4': cfg.b4},
        'mape': cfg.mape, 'r2': cfg.r2, 'serie': serie,
    })


@app.route('/api/admin/upload-volumen', methods=['POST'])
@login_required(2)
def api_upload_volumen():
    if 'file' not in request.files:
        return jsonify({'error': 'No se envió archivo'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'error': 'Nombre de archivo vacío'}), 400
    try:
        rows, skipped = parse_csv(f)
    except Exception as e:
        return jsonify({'error': f'Error parseando CSV: {e}'}), 400

    key_cols = ('anio', 'mes', 'petrolera', 'provincia', 'sector', 'producto')

    existing_ids = {}
    for row in db.session.query(
        VolumeMonthly.id, VolumeMonthly.anio, VolumeMonthly.mes, VolumeMonthly.petrolera,
        VolumeMonthly.provincia, VolumeMonthly.sector, VolumeMonthly.producto
    ):
        existing_ids[tuple(row[1:])] = row[0]

    # Si el CSV repite una clave, gana la última aparición (igual que el upsert fila a fila).
    pending = {}
    for r in rows:
        pending[tuple(r[c] for c in key_cols)] = r

    to_insert = []
    to_update = []
    for key, r in pending.items():
        rid = existing_ids.get(key)
        if rid is not None:
            to_update.append({'id': rid, 'volumen': r['volumen']})
        else:
            to_insert.append(r)

    if to_insert:
        db.session.bulk_insert_mappings(VolumeMonthly, to_insert)
    if to_update:
        db.session.bulk_update_mappings(VolumeMonthly, to_update)
    db.session.commit()
    inserted, updated = len(to_insert), len(to_update)
    log = VolumeUploadLog(
        filename=f.filename, rows_inserted=inserted, rows_updated=updated,
        rows_skipped=skipped, note=f'Total filas procesadas: {len(rows)}'
    )
    db.session.add(log)
    db.session.commit()
    return jsonify({'ok': True, 'inserted': inserted, 'updated': updated, 'skipped': skipped, 'total': len(rows)})


@app.route('/api/admin/upload-regresion', methods=['POST'])
@login_required(2)
def api_upload_regresion():
    if 'file' not in request.files:
        return jsonify({'error': 'No se envió archivo'}), 400
    f = request.files['file']
    try:
        coefs, points = parse_regresion_excel(f)
    except Exception as e:
        return jsonify({'error': f'Error parseando Excel: {e}'}), 400

    cfg = RegressionConfig.query.first()
    if not cfg:
        cfg = RegressionConfig()
        db.session.add(cfg)
    cfg.b1, cfg.b2, cfg.b3, cfg.b4 = coefs['b1'], coefs['b2'], coefs['b3'], coefs['b4']
    cfg.mape, cfg.r2 = coefs.get('mape'), coefs.get('r2')
    cfg.nota = f'Cargado desde {f.filename}'
    RegressionPoint.query.delete()
    for p in points:
        db.session.add(RegressionPoint(**p))
    db.session.commit()
    return jsonify({'ok': True, 'coeficientes': coefs, 'puntos': len(points)})


@app.route('/api/admin/stats')
@login_required(2)
def api_admin_stats():
    total_vol = db.session.query(func.count(VolumeMonthly.id)).scalar() or 0
    total_reg = db.session.query(func.count(RegressionPoint.id)).scalar() or 0
    logs = VolumeUploadLog.query.order_by(VolumeUploadLog.uploaded_at.desc()).limit(10).all()
    cfg = RegressionConfig.query.first()
    return jsonify({
        'volumen_rows': total_vol, 'regresion_points': total_reg,
        'coeficientes': {
            'b1': cfg.b1 if cfg else None, 'b2': cfg.b2 if cfg else None,
            'b3': cfg.b3 if cfg else None, 'b4': cfg.b4 if cfg else None,
            'mape': cfg.mape if cfg else None, 'r2': cfg.r2 if cfg else None,
        } if cfg else None,
        'uploads': [{
            'filename': l.filename,
            'at': l.uploaded_at.isoformat() if l.uploaded_at else None,
            'inserted': l.rows_inserted, 'updated': l.rows_updated, 'skipped': l.rows_skipped,
        } for l in logs],
    })


@app.route('/api/admin/users', methods=['GET', 'POST'])
@login_required(3)
def api_users():
    if request.method == 'GET':
        users = User.query.order_by(User.email).all()
        return jsonify([{
            'id': u.id, 'email': u.email, 'nombre': u.nombre,
            'nivel': u.nivel, 'is_active': u.is_active
        } for u in users])
    data = request.get_json() or {}
    email = (data.get('email') or '').lower().strip()
    if not email:
        return jsonify({'error': 'email requerido'}), 400
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(email=email)
        db.session.add(user)
    user.nombre = data.get('nombre') or email
    user.nivel = int(data.get('nivel', 1))
    user.is_active = bool(data.get('is_active', True))
    if data.get('password'):
        user.password_hash = generate_password_hash(data['password'])
    db.session.commit()
    return jsonify({'ok': True, 'id': user.id})


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    with app.app_context():
        ensure_tables()
    app.run(debug=True, port=5000)
