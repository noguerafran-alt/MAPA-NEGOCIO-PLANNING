from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class VolumeMonthly(db.Model):
    """Volumen mensual de gasoil (GO2/GO3) y naftas (N2/N3) por petrolera, provincia y sector.
    Fuente: planilla VOLUMEN.csv (Año;Mes;Petrolera;provincia;Sector;producto;Volumen).
    """
    __tablename__ = 'volume_monthly'
    id = db.Column(db.Integer, primary_key=True)
    anio = db.Column(db.Integer, nullable=False)
    mes = db.Column(db.Integer, nullable=False)          # 1-12
    petrolera = db.Column(db.String(40), nullable=False) # 1-YPF, 2-SHELL, ...
    provincia = db.Column(db.String(60), nullable=False)
    sector = db.Column(db.String(60), nullable=False)
    producto = db.Column(db.String(10), nullable=False)  # GO2 | GO3 | N2 | N3
    volumen = db.Column(db.Float, nullable=False, default=0.0)
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    __table_args__ = (
        db.UniqueConstraint('anio', 'mes', 'petrolera', 'provincia', 'sector', 'producto',
                            name='uq_volume_monthly'),
        db.Index('ix_volume_anio_mes', 'anio', 'mes'),
        db.Index('ix_volume_provincia', 'provincia'),
        db.Index('ix_volume_producto', 'producto'),
    )


class VolumeUploadLog(db.Model):
    __tablename__ = 'volume_upload_log'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255))
    uploaded_at = db.Column(db.DateTime, server_default=db.func.now())
    rows_inserted = db.Column(db.Integer)
    rows_updated = db.Column(db.Integer)
    rows_skipped = db.Column(db.Integer)
    note = db.Column(db.Text)


class RegressionPoint(db.Model):
    """Puntos del modelo de regresión: Yt (gasoil + nafta total país) y los regressors X1..X4.
    Se cargan desde el Excel de regresión. Los coeficientes se guardan en RegressionConfig.
    """
    __tablename__ = 'regression_point'
    id = db.Column(db.Integer, primary_key=True)
    anio = db.Column(db.Integer, nullable=False)
    mes = db.Column(db.Integer, nullable=False)   # 1-12
    yt = db.Column(db.Float)                      # valor real (puede ser None/0 en proyección)
    x1 = db.Column(db.Float, nullable=False)
    x2 = db.Column(db.Float, nullable=False)
    x3 = db.Column(db.Float, nullable=False)
    x4 = db.Column(db.Float, nullable=False)
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    __table_args__ = (
        db.UniqueConstraint('anio', 'mes', name='uq_regression_point'),
    )


class RegressionConfig(db.Model):
    """Coeficientes del modelo de regresión múltiple y métricas.
    Yt ≈ b1*X1 + b2*X2 + b3*X3 + b4*X4
    (sin intercepto explícito en el Excel original).
    """
    __tablename__ = 'regression_config'
    id = db.Column(db.Integer, primary_key=True)
    b1 = db.Column(db.Float, nullable=False)   # coef X1
    b2 = db.Column(db.Float, nullable=False)   # coef X2
    b3 = db.Column(db.Float, nullable=False)   # coef X3
    b4 = db.Column(db.Float, nullable=False)   # coef X4
    mape = db.Column(db.Float)
    r2 = db.Column(db.Float)
    nota = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())


class Province(db.Model):
    """Catálogo de provincias / jurisdicciones con nombre canónico y centroide para el mapa."""
    __tablename__ = 'province'
    name = db.Column(db.String(60), primary_key=True)   # nombre canónico
    name_display = db.Column(db.String(80))
    lat = db.Column(db.Float)
    lon = db.Column(db.Float)
    region = db.Column(db.String(40))   # opcional: Norte, Cuyo, Patagonia, etc.


class User(db.Model):
    """Cuenta autorizada. Auth local (email + password_hash). Niveles acumulativos:
      1 = mapa + proyecciones
      2 = + admin (carga de datos)
      3 = + gestión de usuarios
    """
    __tablename__ = 'app_user'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    nombre = db.Column(db.String(255))
    nivel = db.Column(db.Integer, nullable=False, default=1)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    password_hash = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    last_login_at = db.Column(db.DateTime)
