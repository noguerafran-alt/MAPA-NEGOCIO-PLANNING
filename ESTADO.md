# ESTADO.md — Mapa Negocio Planning

> **Mantenimiento**: este archivo se actualiza en el **mismo commit** que
> cualquier cambio de código — ver `CLAUDE.md`. No es un changelog
> retroactivo perfecto: empieza a llevarse desde acá en adelante.
>
> Última actualización: **2026-08-24**

## Qué hace la app hoy

### Mapa (`/`, `templates/index.html`)

- Círculos por provincia dimensionados y coloreados por volumen, sobre un
  basemap oscuro de CARTO.
- **Filtros**: años, meses, productos, petroleras y sectores, todos con el
  mismo desplegable multi-selección con "Seleccionar todo" / "Ninguno". El
  botón resume el estado sin abrir el panel ("Todos (12)", "3 de 12", el
  nombre cuando hay uno solo, "Ninguno" en rojo).
- **Hover**: tooltip con el total y el desglose GO2/GO3/N2/N3 con barra,
  volumen y porcentaje.
- **Rutas nacionales**: capa GeoJSON con las 101 rutas, en un pane propio con
  z-index 350 para quedar por debajo de los círculos (overlayPane = 400).
  Toggle en el sidebar.
- **Recuadro de provincia** (clic en un círculo): total, y cada producto con
  volumen **y porcentaje sobre el total de la provincia**. Trae un selector de
  **petrolera** propio que no es local al recuadro: escribe sobre el
  multi-select de petroleras del panel derecho y recarga el mapa, así el
  recuadro, el total filtrado y los círculos nunca muestran selecciones
  distintas. "Todas" vuelve a marcar todas las petroleras.
- **Resaltado del territorio**: al fijar una provincia se sombrea su polígono
  en gris (`fillOpacity` 0.18) con el límite marcado. Va en un pane propio con
  z-index 340, por debajo de las rutas (350) y de los círculos (400).
  **Buenos Aires y CABA se resaltan siempre juntas** — se leen como una sola
  región, aunque el recuadro siga mostrando los volúmenes de la que se tocó.
  Los polígonos salen de `static/provincias.geojson`.
- **Estimación de meses futuros** (opt-in, ver más abajo).
- **Panel de comparación** a la izquierda: se abre con "Comparar con otra
  selección", tiene los mismos filtros y muestra A / B / B−A. Con "También
  filtrar el mapa" el mapa pasa a mostrar la diferencia (radio = magnitud,
  verde si B es mayor, rojo si es menor).

### Modelo (`/modelo`, `templates/modelo.html`)

Pestaña de sólo lectura que explica los dos modelos y por qué son distintos: la
regresión del total país y el naive estacional del mapa. Define el **WAPE** y
por qué no se usa MAPE al grano del mapa. Incluye los backtests
que respaldan cada decisión y una sección con lo medido del gradient boosting,
que **no corre en la app** — no hay scikit-learn en `requirements.txt`.

Los números los pasa la ruta desde el backend (`ERROR_POR_HORIZONTE`,
`ANIOS_FUTUROS`, los coeficientes guardados, el período y el conteo de filas):
si cambian, la página los sigue. No hay valores escritos a mano en el HTML
salvo los resultados de backtest, que son históricos.

**Ojo con el MAPE**: `regression_config.mape` guarda una *fracción* cuando lo
calcula «Ajustar por mínimos cuadrados» (0,0526) y *puntos porcentuales* cuando
lo importa el Excel (2,803). Las dos pantallas lo muestran ×100, así que un
MAPE recién importado se ve 100 veces más grande. Está avisado en la página;
arreglarlo es normalizar en el importador.

### Proyecciones (`/proyecciones`)

- Serie real = **total país de los cuatro productos**, calculada sumando
  `volume_monthly` por mes. No sale del Excel.
- Modelo lineal `Yt = b0 + b1·X1 + b2·X2 + b3·X3 + b4·X4`, con los cinco
  coeficientes **editables en pantalla**: al tocarlos se recalculan en vivo el
  gráfico, el MAPE y el R² sobre los meses con dato real.
- Botón "Ajustar por mínimos cuadrados" (resuelve las ecuaciones normales 5×5
  en el navegador), "Restaurar guardados" y "Guardar" (nivel ≥ 2).
- Si los coeficientes guardados dan más de 25% de MAPE se avisa en pantalla.

### Admin (`/admin`, nivel ≥ 2)

- Carga de la planilla de VOLUMEN en **.xlsx o CSV**, leída por posición de
  columna (A=Año … G=Volumen) desde la fila 2.
- Carga del Excel de regresión.
- El resultado muestra período leído, volumen total, máximo de una fila y
  sectores encontrados, para poder detectar de un vistazo un archivo mal
  escalado.

## Decisiones de modelado, con los números que las respaldan

**No repetir estos experimentos sin leer esto primero.** Todos son backtests
sobre los datos reales (2010-01 a 2026-06, 478.444 filas).

**La métrica es WAPE**, no MAPE: `Σ|real − estimado| / Σ|real|`. Se pondera por
volumen a propósito. Con 4.497 series de tamaños muy distintos, el MAPE
promedia porcentajes por serie y una que vendió 3 m³ y se estimó en 6 aporta un
error de 100%, pesando igual que Buenos Aires errándole por 2%. Si se compara
contra un número nuevo, asegurarse de que también sea WAPE — el 2,99% / 5,26%
de la regresión es MAPE y **no es comparable** con el 17,8% de acá.

### La proyección usa naive estacional, y no es por simplicidad

Cada mes sin dato se estima con el mismo mes del último año que sí lo tenga.
Se midió contra todo lo razonable y ganó siempre.

Horizonte 12 meses, al grano del mapa (4.497 series de provincia × producto ×
petrolera × sector), WAPE promedio sobre 2023/2024/2025:

| Método | WAPE |
|---|---|
| **Naive estacional** | **17,8%** |
| × factor por producto amortiguado | 18,6% |
| × factor global | 19,2% |
| × factor por serie amortiguado | 19,7% |
| × factor por serie | 23,9% |

A nivel provincia × producto (96 series) el naive da 8,6% y el gradient
boosting 9,8%–10,9%. Agregar las macro X1–X4 como features lo **empeora**.

Multi-horizonte (1, 2 y 3 años), incluyendo CAGR estables de 3/5/8 años,
globales y por producto, amortiguados y no: el naive gana en los tres
(17,8% / 23,1% / 28,9%; las alternativas llegan a 58%–66% porque el factor se
eleva a la potencia h y amplifica el ruido).

**Por qué**: el CAGR real del total país es ~1,00 (0,995 a 3 años, 1,007 a 8).
El total no crece; lo que se mueve es la mezcla (GO3 se cuadruplicó desde
2010, GO2 cayó a 0,81×) y se compensa. No hay tendencia agregada que
extrapolar, así que aplicar un factor sólo suma ruido. Corregir la mezcla con
CAGR por producto tampoco mejora el error de ningún producto.

**Consecuencia visible**: todos los años futuros dan el mismo número. No es un
bug — está dicho en el aviso de la pantalla.

### Gradient boosting: sirve a 1 mes, no a 12

| Horizonte | Naive estacional | Naive mes anterior | GBM |
|---|---|---|---|
| 12 meses | 8,6% | — | 9,8%–10,9% |
| 1 mes | 8,6% | 7,8% | **6,4%** |

Los árboles no extrapolan: subestiman justo los productos que crecen (GO3
−14,2%, N3 −19,4% en 2025). A 1 mes, con los últimos lags disponibles, sí
ganan claro. XGBoost/CatBoost son de la misma familia y no cambiarían el
fondo. Se probó con `HistGradientBoostingRegressor` e hiperparámetros casi por
defecto.

**Lo que cambiaría el veredicto a 12 meses**: drivers exógenos por provincia
(precio, parque automotor, cosecha). Cuatro índices nacionales no alcanzan
para explicar 96 series provinciales.

### Sólo se ofrece 1 año de proyección

El horizonte de cada mes es la distancia al último año que tiene **ese mes**, y
no es uniforme: con datos hasta 2026-06, en 2027 los meses de enero a junio
están a 1 año y los de julio a diciembre a 2. Por eso 2027 se etiqueta ±23%
(su peor horizonte) y no ±18%.

`ANIOS_FUTUROS = 1` en `app.py` controla cuántos se ofrecen.
`ERROR_POR_HORIZONTE` tiene los errores medidos (1: 17,8 / 2: 23,1 / 3: 28,9);
no se ofrece un año cuyo peor horizonte quede fuera de esa tabla.

## Sobre el Excel de regresión — leer antes de tocar el modelo

El archivo `26_08_21_-_Regresion.xlsx` trae en la columna J cuatro coeficientes
(b1=−344.078, b2=0,3788, b3=831.402, b4=2.632) y declara MAPE 2,803% y
R² 0,8704. **Esos coeficientes no reproducen la serie.**

- `b1·X1 + b2·X2 + b3·X3 + b4·X4` con los X de la propia hoja (índices ~100)
  da 32–66 M, contra un Yt de 0,79–1,30 M. MAPE 4.313%.
- Se probaron 384 combinaciones (8 transformaciones × 24 permutaciones × con y
  sin intercepto). El mejor MAPE alcanzable es 52%.
- El **R² máximo posible** con un modelo lineal sobre esas cuatro columnas es
  **0,7642** (mínimos cuadrados lo maximiza por definición). El 0,8704 que
  declara la hoja es inalcanzable, lo que prueba que el modelo original se
  ajustó sobre **otras variables**, no sobre las columnas D–G.
- La hoja tiene valores pegados, sin fórmulas: no dice de dónde salieron.

**Qué es la columna Yt**: no es GO3 ni el total. Comparada contra los volúmenes
reales es **GO2+GO3, el gasoil total** (diferencia mediana 0,211%, correlación
0,966). La etiqueta original "Gasoil + Nafta total país" era incorrecta, y
"GO3" también.

Por eso los coeficientes son editables en pantalla en vez de estar fijos: no
hay forma de derivar el modelo correcto desde el archivo. **Si aparece la lista
de variables originales, implementarlo tal cual y anotarlo acá.**

Ajustando sobre las columnas disponibles: contra el gasoil da MAPE 2,99% /
R² 0,762; contra el total país (que es lo que muestra la app hoy) da 5,26% /
R² 0,528. Los X explican mejor el gasoil que el total, cosa esperable si se
eligieron para gasoil.

## Bugs que costaron encontrar

- **La carga de VOLUMEN parecía colgada**: hacía una consulta SQL por cada fila
  (`filter_by(...).first()` dentro del loop). Con 475.000 filas son 475.000
  round-trips: ~1.650 filas/s, unos 5 minutos contra SQLite local y mucho peor
  contra una base remota. Ahora trae las claves en una consulta y hace
  `bulk_insert_mappings` / `bulk_update_mappings`: **9,3 s** para el archivo
  real de 23,3 MB. Al pasar a bloque hubo que **deduplicar por clave** dentro
  del propio CSV (3.564 filas repetidas), porque el código viejo las resolvía
  sin querer vía autoflush y el bulk hubiera roto la constraint.
- **La coma decimal leída como separador de miles**: el CSV trae `10216,123`
  (= 10.216,123 m³). Si el archivo se abre en Excel con la configuración
  regional equivocada queda `10216123`, mil veces más grande. El máximo real de
  una fila en todo el histórico es **143.383**, sirve como referencia. Hay un
  detector que compara contra lo cargado y frena con 409.
- **Encabezados y datos con la codificación rota**: `AÃ±o`, `Al PÃºblico`. Por
  eso el parser lee por posición y `reparar_texto()` arregla el mojibake — sin
  eso quedarían dos sectores distintos para el mismo nombre.
- **`parse_volumen` convertía en 0, sin avisar, cualquier valor > 50 M**. Un
  cero silencioso no se nota nunca. Ahora el tope se aplica contando los casos
  y el resumen de la carga informa cuántas filas quedaron fuera.
- **Destildar todos los sectores mostraba todos**: el backend no distinguía
  "parámetro ausente" de "parámetro vacío". Ahora `_lista()` devuelve `None` vs
  `[]` y son casos distintos.
- **"Unexpected token '<', \"<!doctype\"..."**: el endpoint devolvía la página
  HTML de error de Werkzeug y el navegador intentaba parsearla como JSON, con
  lo que el mensaje que veía el usuario no decía nada del problema real. Ahora
  hay `errorhandler` para 413 y para cualquier excepción que devuelve JSON en
  las rutas `/api/`, y el cliente tiene `leerJson()` que, si igual llega HTML,
  muestra el código de estado y el texto plano. **El límite de subida era de
  40 MB** y un .xlsx guardado desde Excel lo puede pasar: se subió a 250 MB.
- **La estimación se aplicaba sola**: como 2026 tiene datos sólo hasta junio,
  julio a diciembre se estimaban sin pedirlo y el total por defecto pasaba de
  365,7 M a 378,0 M. Ahora es opt-in con el checkbox.

## Rendimiento de la carga (medido)

Con el histórico completo (478.444 filas):

| Etapa | Tiempo |
|---|---|
| Parsear el **CSV** | 3,2 s (147.000 filas/s) |
| Parsear el **.xlsx** | 35,6 s (13.400 filas/s) |
| Carga entera por el endpoint (.xlsx) | **43,4 s** |
| Carga entera por el endpoint (.csv) | ~9,3 s |

**El Excel tarda 11 veces más que el CSV**: openpyxl es lento y no hay
alternativa sin sumar una dependencia. Para el histórico completo conviene el
CSV; el Excel es cómodo para la carga mensual, que son ~2.400 filas.

La inserción va **por lotes de 20.000**: SQLAlchemy arma la lista de
parámetros entera y con medio millón de filas duplicaba la memoria. El pico
del proceso bajó de ~430 MB a ~144 MB.

`run_local.py` levanta waitress con `channel_timeout=1800`. El default es 120 s
y una carga larga en una máquina lenta lo pasaba, cortando la conexión sin
explicación.

## Detalles que no son obvios

- Los años futuros del desplegable arrancan **desmarcados**.
- Hay dos "provincias" sin centroide, `Estado Nacional` y `No aplica`, ambas con
  volumen 0: no se dibujan y no se está ocultando nada real.
- El panel del multi-select se expande **en el flujo**, no flotando: el sidebar
  tiene `overflow-y: auto` y recortaría un panel absoluto.
- `static/provincias.geojson` se regenera con `tools/fetch_provincias.py`
  (Overpass, `admin_level=4`, ODbL). Los anillos vienen como tramos sueltos y
  hay que coserlos por extremos; los que no cierran se descartan. Simplificado
  con Douglas-Peucker a 0,01° (~1 km): 33 MB crudos quedan en **0,15 MB** con
  las 24 provincias. Se ignoran dos relaciones fronterizas de Chile y Paraguay
  que la consulta trae de más.
- `static/rutas_nacionales.geojson` se regenera con `tools/fetch_rutas.py`
  (Overpass, ODbL). Los 29.614 tramos crudos se simplifican con Douglas-Peucker
  y se cosen por ruta en 2.466 cadenas: 0,61 MB, 0,16 MB gzipped, y Leaflet
  dibuja 101 paths en vez de decenas de miles.
- `dev_seed.db` es una base local de prueba, ignorada por git.

## Paquete portable (para pasarle el zip a alguien)

`python tools/armar_zip.py` genera `dist/MAPA-NEGOCIO-PLANNING.zip`, **18,6 MB**.
Quien lo recibe descomprime y hace doble clic en `iniciar.bat`: no necesita
Python, ni VS Code, ni internet.

Sigue el mismo patron que MAPA-NEGOCIO-LOCAL:

- `vendor/python-3.12.10-embed-amd64.zip` — el paquete *embeddable* oficial de
  python.org, 11 MB. No se instala ni toca el registro: se desempaqueta.
- `vendor/wheels/` — 26 wheels, 7 MB (cp312/win_amd64). Sin pandas ni numpy,
  por eso pesa mucho menos que los 83 MB del otro proyecto.
- `vendor/preparar.py` — reescribe `python312._pth`, extrae el wheel de pip a
  mano y corre `pip install --no-index`. `--no-index` es la garantia de que no
  sale a la red: si falta un wheel, falla en vez de bajarlo por atras.
- `preparar_entorno.bat` / `iniciar.bat` — idempotentes; si el entorno ya esta,
  arrancan directo.

El runtime se desempaqueta en `%USERPROFILE%envs\mapa-negocio-planning-runtime`,
**fuera** de la carpeta: son ~60 MB y si la carpeta esta en OneDrive se
sincronizarian enteros.

**Verificado de punta a punta**: se aparto el runtime, se extrajo el zip en una
carpeta limpia y se corrio `iniciar.bat`. Desempaqueto el interprete, instalo
los 24 paquetes offline, chequeo los imports, creo el usuario del primer
arranque y sirvio todo: `/` 200, `/proyecciones` 200, `/admin` 200, `/modelo`
200 y el GeoJSON de rutas 200 (599 KB). Login con `admin@local` correcto.

Dos cosas que hay que saber si se toca esto:

- El interprete embebido corre en **modo aislado**, y ahi Python no agrega la
  carpeta del script al `sys.path`. `run_local.py` hace `sys.path.insert()` de
  su propia carpeta; sin eso `from app import app` no encuentra nada.
- Los `.bat` tienen que quedar con **CRLF**. Con LF, `cmd.exe` parte mal las
  lineas de las etiquetas (`:label`) y falla de formas raras. Esta forzado en
  `.gitattributes`.

## Pendiente

- **Normalizar la unidad del MAPE**: `regression_config.mape` guarda una
  fracción cuando lo calcula el ajuste por mínimos cuadrados (0,0526) y puntos
  porcentuales cuando lo importa el Excel (2,803). Proyecciones y Modelo lo
  muestran ×100, así que un MAPE recién importado se ve 100 veces más grande.
  El arreglo es dividir por 100 en el importador y migrar los valores ya
  guardados. Está avisado en pantalla mientras tanto.
- **La pestaña Modelo se actualiza junto con el modelo.** Si cambia un método,
  un backtest o una constante, `templates/modelo.html` es parte del cambio: es
  la única explicación que ve quien usa la app.
- **Recuperar el modelo de regresión original**: falta saber qué variables usó
  (ver arriba). Mientras tanto los coeficientes se ajustan a mano.
- **Mejorar la proyección a 12 meses**: con los datos actuales el naive es lo
  mejor medido. El camino no es otro algoritmo sino traer drivers exógenos por
  provincia.
- **Modelo estructural (tendencia amortiguada + estacionalidad) por
  provincia-producto**: propuesto y no implementado; habría que backtestearlo
  contra el 17,8% del naive antes de adoptarlo.
- El error al grano fino del mapa (17,8%) es más del doble que a nivel
  provincia-producto (8,6%). Los números por provincia son bastante más
  confiables que los de una petrolera puntual en un sector puntual.
