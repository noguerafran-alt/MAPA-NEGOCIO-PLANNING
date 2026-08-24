# Mapa Negocio Planning — contexto para Claude Code

App interna de análisis de volúmenes de combustible en Argentina: gasoil
(GO2/GO3) y naftas (N2/N3) por año, mes, petrolera, provincia y sector.
Tiene un mapa provincial, una página de proyecciones con un modelo de
regresión y un panel de admin para cargar datos. Flask + SQLAlchemy,
SQLite en local y Postgres en producción.

## Regla de oro: actualizar ESTADO.md

**Cada cambio de este repo se acompaña de una actualización de
`ESTADO.md`, en el mismo commit.** El proyecto se trabaja desde distintas
sesiones de Claude (que no comparten memoria entre sí) y potencialmente
desde distintos usuarios de la máquina. Un cambio que no quede anotado en
`ESTADO.md` es un cambio que la próxima sesión va a redescubrir a los
ponchazos, o va a deshacer sin saberlo.

Qué corresponde anotar ahí: endpoint o panel nuevo, columna nueva en la
base, una decisión de diseño no obvia (y el motivo), **algo que se probó y
se descartó, con los números que lo respaldan** (evita reintentarlo), un
bug que costó encontrar, y lo que quedó a medias.

Lo de "con los números" no es decorativo: buena parte de este proyecto son
decisiones de modelado que sólo se sostienen por un backtest. Sin el número
al lado, la próxima sesión no tiene cómo saber si una idea ya se midió y
perdió.

## Arquitectura

- **Backend**: Flask en `app.py` (un solo archivo con todos los endpoints).
  `models.py` tiene las tablas, `parser_volumen.py` y `parser_regresion.py`
  leen las planillas que se suben desde admin, `provinces_data.py` tiene los
  centroides para el mapa.
- **Frontend**: Jinja + HTML/JS vanilla sin build step, todo en
  `templates/`. Cada página tiene un único `<script>` con sus funciones; no
  hay módulos ES ni bundler. Leaflet para el mapa, Chart.js para las series.
- **Datos**: `volume_monthly` es la tabla grande (~475.000 filas, 2010-2026),
  con constraint única sobre
  `(anio, mes, petrolera, provincia, sector, producto)`. `regression_point` y
  `regression_config` guardan el modelo de proyección.
- **Migraciones**: no hay Alembic. `db.create_all()` crea tablas nuevas pero
  **no altera las existentes**, así que agregar una columna requiere sumarla
  a `ensure_columns()` en `app.py`, que hace un `ALTER TABLE` idempotente que
  sirve igual en SQLite y en Postgres.

## Convenciones del proyecto

- **Todo en español**: nombres de funciones, variables, comentarios, mensajes
  de error al usuario. Mezclar inglés desentona con el resto.
- **Comentarios solo para el WHY, no el WHAT**: se explica una decisión no
  obvia o una restricción escondida, no lo que ya dice el nombre de la
  función.
- **Nada de fallar en silencio.** Si un filtro deja el mapa vacío, si una
  estimación no es un dato real, si una fila se descartó por estar fuera de
  rango: se dice en pantalla. Este proyecto ya tuvo dos bugs de datos que
  pasaron desapercibidos justamente por callarse (ver ESTADO.md).
- **Lo estimado se marca como estimado**, siempre, y con el error medido al
  lado. Un número proyectado nunca se muestra igual que uno real.
- **Antes de elegir un método de proyección, se lo mide contra los datos
  reales** con un backtest, y el resultado se anota en ESTADO.md. Ya pasó
  varias veces que la opción intuitivamente mejor perdió.

## Cuidados al tocar la carga de datos

- La planilla de VOLUMEN se lee **por posición de columna** (A a G), nunca
  por nombre de encabezado: los encabezados llegan con la codificación rota
  cuando el archivo pasó por Excel.
- El volumen viene con **coma decimal**. Si un archivo llega con los valores
  mil veces más grandes es que Excel la leyó como separador de miles — hay un
  detector que frena la carga, no lo saques.
- La carga hace upsert en bloque. **No volver al patrón de una consulta por
  fila**: con 475.000 filas eso tardaba minutos y parecía colgado.

## Correr local

```
python run_local.py          # http://127.0.0.1:5000
```

Usuario: `flask autorizar-usuario --email a@b.com --nivel 3`. Los niveles son
acumulativos: 1 mapa y proyecciones, 2 suma admin, 3 suma gestión de usuarios.
