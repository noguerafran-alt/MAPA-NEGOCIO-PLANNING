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
from sqlalchemy import func, and_, inspect, text
import click

from models import (db, VolumeMonthly, VolumeUploadLog, RegressionPoint,
                    RegressionConfig, Province, User)
from parser_volumen import parse_archivo, CANONICAL_PROVINCES
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


def ensure_columns():
    """Agrega columnas nuevas a tablas que ya existen.

    db.create_all() crea tablas faltantes pero no altera las existentes, asi que
    una base ya desplegada se queda sin las columnas agregadas despues. Alcanza
    con un ALTER simple; sirve igual en SQLite y en Postgres.
    """
    insp = inspect(db.engine)
    if 'regression_config' not in insp.get_table_names():
        return
    columnas = {c['name'] for c in insp.get_columns('regression_config')}
    if 'b0' not in columnas:
        db.session.execute(text(
            'ALTER TABLE regression_config ADD COLUMN b0 FLOAT DEFAULT 0'))
        db.session.commit()
        app.logger.info('regression_config: columna b0 agregada')


def ensure_tables():
    db.create_all()
    ensure_columns()
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


def _lista(param):
    """Lee un parametro de lista separada por comas.

    Devuelve None si el parametro no vino (no se filtra por ese campo) y una
    lista vacia si vino vacio (el usuario destildo todo -> no debe pasar nada).
    Son casos distintos: sin esta diferencia, destildar todo mostraria todo.
    """
    raw = request.args.get(param)
    if raw is None:
        return None
    return [s.strip() for s in raw.split(',') if s.strip()]


def _enteros(valores):
    out = []
    for v in valores:
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            continue
    return out


def _anios_estimables(reales):
    """Anios futuros que se pueden estimar con un horizonte ya medido.

    El horizonte de cada mes es la distancia al ultimo anio que tiene ese mes,
    y no es igual para todos: si los datos llegan a junio, en el anio siguiente
    los meses de enero a junio estan a 1 anio y los de julio a diciembre a 2.
    Se ofrece un anio solo mientras su peor horizonte siga dentro de la tabla
    de errores medidos; mas alla no habria con que acompanar el numero.
    """
    if not reales:
        return []
    por_mes = {}
    for a, m in reales:
        por_mes.setdefault(m, []).append(a)
    tope = max(ERROR_POR_HORIZONTE)
    out = []
    anio = max(a for a, _ in reales)
    while len(out) < ANIOS_FUTUROS:
        anio += 1
        hs = [anio - max(por_mes[m]) for m in por_mes if any(y < anio for y in por_mes[m])]
        peor = max(hs) if hs else None
        if peor is None or peor > tope:
            break
        out.append({'anio': anio, 'error': ERROR_POR_HORIZONTE[peor], 'horizonte': peor})
    return out


@app.route('/api/filtros')
@login_required(1)
def api_filtros():
    anios = db.session.query(VolumeMonthly.anio).distinct().order_by(VolumeMonthly.anio).all()
    meses = db.session.query(VolumeMonthly.mes).distinct().order_by(VolumeMonthly.mes).all()
    petroleras = db.session.query(VolumeMonthly.petrolera).distinct().order_by(VolumeMonthly.petrolera).all()
    sectores = db.session.query(VolumeMonthly.sector).distinct().order_by(VolumeMonthly.sector).all()
    lista_anios = [a[0] for a in anios]
    reales_periodos = {(a, m) for a, m in
                       db.session.query(VolumeMonthly.anio, VolumeMonthly.mes).distinct()}
    futuros = _anios_estimables(reales_periodos)
    return jsonify({
        'anios': lista_anios,
        'anios_futuros': futuros,
        'meses': [m[0] for m in meses],
        'petroleras': [p[0] for p in petroleras],
        'sectores': [s[0] for s in sectores],
        'productos': ['GO2', 'GO3', 'N2', 'N3'],
        'provincias': CANONICAL_PROVINCES,
    })


# WAPE medido en backtest sobre 2023, 2024 y 2025 al grano del mapa, segun
# cuantos anios separan el mes estimado del ultimo anio con dato real.
# Se probaron factores de crecimiento (global, por producto y por serie, con
# CAGR de 3/5/8 anios, amortiguados y no) y todos dieron peor en los tres
# horizontes: el total pais no tiene tendencia medible (CAGR ~ 1.00), asi que
# aplicar un factor solo suma ruido.
ERROR_POR_HORIZONTE = {1: 17.8, 2: 23.1, 3: 28.9}

# Se proyecta un solo anio hacia adelante. Mas alla el error crece rapido y el
# metodo repite el mismo origen, con lo que los anios siguientes no aportan un
# numero distinto.
ANIOS_FUTUROS = 1


def _resolver_periodos(anios, meses, reales):
    """Separa lo pedido en meses con dato real y meses a estimar.

    Un mes sin dato se estima con el mismo mes del ultimo anio que si lo tenga
    (naive estacional). Es el metodo que mejor midio en el backtest al grano
    del mapa: 17.8% de WAPE a 12 meses, contra 19-24% de las variantes que le
    aplican un factor de crecimiento.
    """
    por_mes = {}
    for a, m in reales:
        por_mes.setdefault(m, []).append(a)
    estimados = []          # (origen, pedido)
    for a in anios:
        for m in meses:
            if (a, m) in reales:
                continue
            previos = [y for y in por_mes.get(m, []) if y < a]
            if previos:
                estimados.append(((max(previos), m), (a, m)))
    return estimados


@app.route('/api/volumenes')
@login_required(1)
def api_volumenes():
    anios = _lista('anios')
    meses = _lista('meses')
    productos = _lista('productos')
    sectores = _lista('sectores')
    petroleras = _lista('petroleras')
    anio_desde = request.args.get('anio_desde', type=int)
    anio_hasta = request.args.get('anio_hasta', type=int)

    def base():
        q = db.session.query(
            VolumeMonthly.provincia, VolumeMonthly.producto,
            func.sum(VolumeMonthly.volumen).label('total'))
        if productos is not None:
            q = q.filter(VolumeMonthly.producto.in_(productos))
        if sectores is not None:
            q = q.filter(VolumeMonthly.sector.in_(sectores))
        if petroleras is not None:
            q = q.filter(VolumeMonthly.petrolera.in_(petroleras))
        return q

    result = {}

    def acumular(prov, prod, valor, estimado):
        d = result.setdefault(prov, {'GO2': 0.0, 'GO3': 0.0, 'N2': 0.0, 'N3': 0.0,
                                     'total': 0.0, 'estimado': 0.0})
        if prod in d:
            d[prod] += valor
        d['total'] += valor
        if estimado:
            d['estimado'] += valor

    # --- meses con dato real -------------------------------------------------
    q = base()
    if anios is not None:
        q = q.filter(VolumeMonthly.anio.in_(_enteros(anios)))
    else:
        if anio_desde:
            q = q.filter(VolumeMonthly.anio >= anio_desde)
        if anio_hasta:
            q = q.filter(VolumeMonthly.anio <= anio_hasta)
    if meses is not None:
        q = q.filter(VolumeMonthly.mes.in_(_enteros(meses)))
    for prov, prod, total in q.group_by(VolumeMonthly.provincia, VolumeMonthly.producto):
        acumular(prov, prod, float(total or 0), False)

    # --- meses futuros: se estiman ------------------------------------------
    # Solo se estima si se pide explicitamente: si no, un anio en curso con
    # meses todavia sin cargar inflaria el total sin que nadie lo haya pedido.
    estimados = []
    if request.args.get('estimar') == '1' and anios is not None and meses is not None:
        reales = {(a, m) for a, m in
                  db.session.query(VolumeMonthly.anio, VolumeMonthly.mes).distinct()}
        estimados = _resolver_periodos(_enteros(anios), _enteros(meses), reales)

    if estimados:
        # varios meses pedidos pueden apoyarse en el mismo mes de origen
        veces = {}
        for origen, _pedido in estimados:
            veces[origen] = veces.get(origen, 0) + 1
        qe = base().add_columns(VolumeMonthly.anio, VolumeMonthly.mes).filter(
            VolumeMonthly.anio.in_(sorted({a for a, _ in veces})),
            VolumeMonthly.mes.in_(sorted({m for _, m in veces})),
        ).group_by(VolumeMonthly.provincia, VolumeMonthly.producto,
                   VolumeMonthly.anio, VolumeMonthly.mes)
        for prov, prod, total, anio, mes in qe:
            n = veces.get((anio, mes), 0)
            if n:
                acumular(prov, prod, float(total or 0) * n, True)

    for name, data in result.items():
        c = PROVINCE_CENTROIDS.get(name)
        if c:
            data['lat'], data['lon'] = c

    return jsonify({
        'provincias': result,
        'estimados': [{'pedido': list(ped), 'origen': list(ori)} for ori, ped in estimados],
        'error_horizonte': ERROR_POR_HORIZONTE,
        'horizonte_max': (max(ped[0] - ori[0] for ori, ped in estimados)
                          if estimados else None),
    })


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

    # La serie real es el total pais de todos los productos, calculado desde los
    # volumenes cargados: el modelo estima ese total. La columna Yt del Excel no
    # se usa como real (resulto ser gasoil solo, GO2+GO3, no el total).
    totales = {}
    for anio, mes, total in db.session.query(
            VolumeMonthly.anio, VolumeMonthly.mes,
            func.sum(VolumeMonthly.volumen)).group_by(
            VolumeMonthly.anio, VolumeMonthly.mes):
        totales[(anio, mes)] = float(total or 0)

    points = RegressionPoint.query.order_by(RegressionPoint.anio, RegressionPoint.mes).all()
    b0 = cfg.b0 or 0.0
    serie = []
    for p in points:
        pred = b0 + cfg.b1 * p.x1 + cfg.b2 * p.x2 + cfg.b3 * p.x3 + cfg.b4 * p.x4
        # Los meses sin volumen cargado (los futuros) van sin real: solo prediccion.
        serie.append({
            'anio': p.anio, 'mes': p.mes, 'yt': totales.get((p.anio, p.mes)),
            'predicho': pred,
            'x1': p.x1, 'x2': p.x2, 'x3': p.x3, 'x4': p.x4,
        })

    return jsonify({
        'coeficientes': {'b0': b0, 'b1': cfg.b1, 'b2': cfg.b2, 'b3': cfg.b3, 'b4': cfg.b4},
        'mape': cfg.mape, 'r2': cfg.r2, 'serie': serie,
        'hay_volumen': bool(totales),
    })


def _detectar_escala(rows, key_cols, existing_vol):
    """Avisa si los volumenes que llegan estan fuera de escala.

    El caso conocido: la planilla trae el volumen con coma decimal
    (10216,123 = diez mil doscientos dieciseis) y Excel la interpreta como
    separador de miles, con lo que el valor entra mil veces mas grande. Nada
    en el archivo permite distinguirlo, asi que se compara contra lo cargado.

    Devuelve None si no hay nada raro, o un dict con el detalle.
    """
    if not rows or not existing_vol:
        return None

    # 1) filas cuya clave ya existe: se compara el valor nuevo con el viejo
    ratios = []
    for r in rows:
        if r['volumen'] <= 0:
            continue
        viejo = existing_vol.get(tuple(r[c] for c in key_cols))
        if viejo and viejo > 0:
            ratios.append(r['volumen'] / viejo)
    if len(ratios) >= 20:
        ratios.sort()
        mediana = ratios[len(ratios) // 2]
        if mediana >= 100:
            return {
                'motivo': 'ratio', 'mediana': mediana, 'comparadas': len(ratios),
                'mensaje': (
                    'Los volumenes vienen %.0f veces mas grandes que los ya cargados '
                    '(mediana sobre %d filas que coinciden). Suele pasar cuando la '
                    'planilla se abrio en Excel y la coma decimal se leyo como '
                    'separador de miles: 10216,123 queda como 10216123. Revisa el '
                    'archivo, o subilo igual si el cambio de escala es real.'
                    % (mediana, len(ratios))),
            }
        if mediana <= 0.01:
            return {
                'motivo': 'ratio', 'mediana': mediana, 'comparadas': len(ratios),
                'mensaje': (
                    'Los volumenes vienen %.0f veces mas chicos que los ya cargados '
                    '(mediana sobre %d filas que coinciden). Revisa el archivo, o '
                    'subilo igual si el cambio es real.'
                    % (1 / mediana, len(ratios))),
            }
        return None

    # 2) sin filas en comun (un mes nuevo): se compara contra el maximo historico
    max_nuevo = max(r['volumen'] for r in rows)
    max_viejo = max(existing_vol.values())
    if max_viejo > 0 and max_nuevo > 50 * max_viejo:
        return {
            'motivo': 'maximo', 'max_nuevo': max_nuevo, 'max_viejo': max_viejo,
            'mensaje': (
                'La fila mas grande de la planilla es %.0f, contra un maximo '
                'historico de %.0f. Suele pasar cuando la coma decimal se leyo '
                'como separador de miles. Revisa el archivo, o subilo igual si '
                'el salto es real.' % (max_nuevo, max_viejo)),
        }
    return None


@app.route('/api/admin/upload-volumen', methods=['POST'])
@login_required(2)
def api_upload_volumen():
    if 'file' not in request.files:
        return jsonify({'error': 'No se envió archivo'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'error': 'Nombre de archivo vacío'}), 400
    try:
        rows, skipped, info = parse_archivo(f, f.filename)
    except Exception as e:
        return jsonify({'error': f'Error leyendo la planilla: {e}'}), 400
    if not rows:
        return jsonify({'error': 'La planilla no tiene filas validas. Se esperan las '
                                 'columnas A a G (Anio, Mes, Petrolera, provincia, '
                                 'Sector, producto, Volumen) desde la fila 2.'}), 400

    key_cols = ('anio', 'mes', 'petrolera', 'provincia', 'sector', 'producto')

    # Se trae tambien el volumen: sirve para el upsert y para comparar escalas
    # sin pagar una segunda pasada por la tabla.
    existing_ids, existing_vol = {}, {}
    for row in db.session.query(
        VolumeMonthly.id, VolumeMonthly.anio, VolumeMonthly.mes, VolumeMonthly.petrolera,
        VolumeMonthly.provincia, VolumeMonthly.sector, VolumeMonthly.producto,
        VolumeMonthly.volumen
    ):
        clave = tuple(row[1:7])
        existing_ids[clave] = row[0]
        existing_vol[clave] = row[7]

    escala = _detectar_escala(rows, key_cols, existing_vol)
    if escala and request.args.get('forzar') != '1':
        return jsonify({'error': escala['mensaje'], 'escala': escala}), 409

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
    return jsonify({'ok': True, 'inserted': inserted, 'updated': updated,
                    'skipped': skipped, 'total': len(rows), 'resumen': info})


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
    cfg.b0 = 0.0   # el Excel no trae termino independiente
    cfg.mape, cfg.r2 = coefs.get('mape'), coefs.get('r2')
    cfg.nota = f'Cargado desde {f.filename}'
    RegressionPoint.query.delete()
    for p in points:
        db.session.add(RegressionPoint(**p))
    db.session.commit()
    return jsonify({'ok': True, 'coeficientes': coefs, 'puntos': len(points)})


@app.route('/api/admin/coeficientes', methods=['POST'])
@login_required(2)
def api_guardar_coeficientes():
    """Persiste los coeficientes ajustados a mano desde la pagina de proyecciones."""
    data = request.get_json() or {}
    cfg = RegressionConfig.query.order_by(RegressionConfig.id.desc()).first()
    if not cfg:
        return jsonify({'error': 'No hay modelo cargado. Subi el Excel desde Admin.'}), 404

    valores = {}
    for k in ('b0', 'b1', 'b2', 'b3', 'b4'):
        if k not in data:
            if k == 'b0':          # un cliente viejo no lo manda: sin constante
                valores[k] = 0.0
                continue
            return jsonify({'error': f'Falta {k}'}), 400
        try:
            valores[k] = float(data[k])
        except (TypeError, ValueError):
            return jsonify({'error': f'{k} no es un numero'}), 400

    for k, v in valores.items():
        setattr(cfg, k, v)
    # MAPE y R2 los recalcula el cliente sobre la serie, con estos coeficientes.
    for k in ('mape', 'r2'):
        if data.get(k) is not None:
            try:
                setattr(cfg, k, float(data[k]))
            except (TypeError, ValueError):
                pass
    cfg.nota = f'Coeficientes ajustados a mano por {current_user().email}'
    db.session.commit()
    return jsonify({'ok': True, 'coeficientes': valores})


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
