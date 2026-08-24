# Mapa Gasoil & Naftas — Análisis de ventas por provincia

App Flask para visualizar y proyectar volúmenes de **gasoil (GO2/GO3)** y **naftas (N2/N3)** por provincia argentina.

Basada en la arquitectura de [MAPA-NEGOCIO-LOCAL](https://github.com/noguerafran-alt/MAPA-NEGOCIO-LOCAL), adaptada a datos de ventas de combustibles en lugar de rutas aéreas.

## Características

- **Mapa interactivo** de provincias (Leaflet, estilo dark) con volúmenes agregados
- Filtros por año, producto, petrolera y sector
- **Proyecciones** con el modelo de regresión múltiple (`Yt ≈ b1·X1 + b2·X2 + b3·X3 + b4·X4`)
  - Yt = gasoil + nafta total país
- **Admin**: carga de `VOLUMEN.csv` y del Excel de regresión
- Auth local (email + contraseña) con niveles 1 / 2 / 3

## Datos

| Archivo | Contenido |
|---------|-----------|
| `VOLUMEN.csv` | Año;Mes;Petrolera;provincia;Sector;producto;Volumen (2010–2026) |
| Excel de regresión | Serie Yt + X1..X4 + coeficientes b1..b4, MAPE, R² |

## Uso local

```bash
python -m venv .venv
source .venv/bin/activate   # o .venv\Scripts\activate en Windows
pip install -r requirements.txt
python run_local.py
```

Abrí http://127.0.0.1:5000

### Crear el primer usuario (nivel 3)

```bash
flask --app app autorizar-usuario --email vos@empresa.com --nombre "Tu Nombre" --nivel 3
```

(te pide la contraseña)

## Deploy (Render)

1. Subí este repo a GitHub
2. New → Blueprint (o Web Service) apuntando al repo
3. Agregá `SECRET_KEY` y `DATABASE_URL` (Postgres)
4. Creá el usuario admin desde el Shell de Render

## Niveles de acceso

| Nivel | Acceso |
|-------|--------|
| 1 | Mapa + Proyecciones |
| 2 | + Admin (carga de archivos) |
| 3 | + Gestión de usuarios |
