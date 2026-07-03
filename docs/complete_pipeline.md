# Pipeline completo de trabajo

Este documento muestra un flujo completo posible con el repositorio `epanet_tools`, desde el trabajo inicial con shapes de tuberías hasta la generación de un `.inp`, la adaptación de patterns de riego y el posproceso de resultados EPANET.

El objetivo es que sirva como guía práctica para un proyecto real de red de riego o red hidráulica preparada desde información GIS.

## 1. Preparar el ambiente

Crear y activar el ambiente:

```bash
conda env create -f environment.yml
conda activate epanet_tools
pip install -e .
```

Si se van a exportar resultados a Excel:

```bash
pip install -e ".[excel]"
```

Verificaciones de desarrollo:

```bash
pytest
ruff check .
ruff format .
mypy src
```

## 2. Organizar datos de entrada

Estructura sugerida:

```text
project/
├── data/
│   ├── tuberias_sector_1.shp
│   ├── tuberias_sector_1.dbf
│   ├── tuberias_sector_1.shx
│   ├── tuberias_sector_1.prj
│   ├── tuberias_sector_2.shp
│   ├── red_tuberias.gpkg
│   └── mdt.tif
├── config/
│   └── validate_network_project.yml
└── outputs/
```

Criterios para los shapes o GeoPackages:

- las tuberías deben ser líneas;
- preferentemente geometría `LineString`;
- todas las capas deben tener CRS definido;
- trabajar siempre en CRS proyectado y métrico;
- si las capas están en CRS distintos, definir `spatial.working_crs`;
- los atributos hidráulicos pueden venir en la capa o asignarse por configuración;
- el DEM/MDT debe cubrir todos los nodos generados.

## 3. Crear configuración YAML del workflow GIS → INP

Archivo ejemplo: `config/validate_network_project.yml`

```yaml
pipeline: validate_network
name: red_riego_palo_alto
outdir: outputs/red_riego_palo_alto

inputs:
  pipes:
    - path: data/tuberias_sector_1.shp
      layer: null
    - path: data/tuberias_sector_2.shp
      layer: null
    - path: data/red_tuberias.gpkg
      layer: tuberias
  dem: data/mdt.tif
  # Usar solo si el DEM no trae CRS o el CRS no puede interpretarse correctamente.
  # dem_crs: EPSG:32719

spatial:
  # Usar un CRS proyectado local. Ejemplos:
  # Uruguay / UTM 21S: EPSG:32721
  # Chile zona 19S: EPSG:32719
  working_crs: EPSG:32721
  snap_tolerance_m: 0.20

# La implementación actual usa topology.snap_tolerance_m si existe;
# si no existe, usa spatial.snap_tolerance_m.
topology:
  snap_tolerance_m: 0.20
  explode_multilines: true
  min_length_m: 0.05

hydraulics:
  flow_units: LPS
  headloss: H-W

  # Si las tuberías ya tienen campos diameter_mm, roughness, minor_loss y status,
  # se conservan los valores válidos existentes.
  pipe_defaults:
    diameter_mm: 63.0
    roughness: 140.0
    minor_loss: 0.0
    status: OPEN
    material: PEAD

  # Opcional: reglas por categoría. El campo debe existir en la capa combinada.
  category_field: material
  categories:
    PEAD:
      roughness: 150.0
      status: OPEN
    PVC:
      roughness: 145.0
      status: OPEN
```

Notas importantes:

- `spatial.working_crs` debe ser métrico. No usar EPSG:4326 para snapping, longitudes o tolerancias.
- `topology.snap_tolerance_m` controla snapping de extremos y conexiones extremo-segmento.
- `topology.min_length_m` se usa tanto en validación inicial como en revisión posterior.
- `hydraulics.pipe_defaults` permite generar un `.inp` básico aunque los shapes no tengan todos los atributos.

## 4. Ejecutar workflow de validación y generación de INP

Desde la raíz del repositorio:

```bash
python -m epanet_tools.workflows.validate_network --config config/validate_network_project.yml
```

El comando imprime un diccionario resumen con:

- estado general;
- cantidad de features;
- conteo de errores, warnings e info;
- resumen de limpieza topológica;
- resumen de conectividad;
- resumen de elevaciones;
- resumen de atributos hidráulicos;
- resumen de revisión topológica;
- rutas de reportes, GIS e INP.

## 5. Revisar salidas generadas

La estructura esperada es:

```text
outputs/red_riego_palo_alto/
├── report/
│   ├── red_riego_palo_alto_validation.json
│   ├── red_riego_palo_alto_validation.csv
│   ├── red_riego_palo_alto_cleaning.csv
│   ├── red_riego_palo_alto_connectivity.csv
│   ├── red_riego_palo_alto_elevation.csv
│   ├── red_riego_palo_alto_hydraulics.csv
│   ├── red_riego_palo_alto_topology_review.csv
│   └── red_riego_palo_alto_basic_model_validation.csv
├── gis/
│   ├── red_riego_palo_alto_network.gpkg
│   └── red_riego_palo_alto_working.gpkg
└── inp/
    └── red_riego_palo_alto.inp
```

Abrir en QGIS:

```text
outputs/red_riego_palo_alto/gis/red_riego_palo_alto_working.gpkg
```

Capas útiles de revisión:

| Capa | Uso |
|---|---|
| `pipes_raw` | red combinada antes de normalizar |
| `pipes_clean_auto` | red después de snapping inicial automático |
| `pipes_clean` | red final con conectividad hidráulica |
| `junctions` | nodos generados automáticamente |
| `topology_errors` | puntos a revisar: extremos libres, cruces posibles, tuberías cortas |
| `topology_report` | revisión por nodo |

Criterios de interpretación:

- `FREE_ENDPOINT` puede ser normal en extremos reales de red, emisores, tanques, reservorios o acometidas; no siempre es error.
- `POSSIBLE_UNCONNECTED_CROSSING` debe revisarse visualmente. Si hay tee o conexión real, corregir el shape para que exista un nodo/intersección hidráulica. Si es solo cruce en planta, se puede dejar sin conectar.
- `SHORT_PIPE` puede indicar geometría residual, digitalización accidental o una conexión muy corta real.

## 6. Revisar el INP básico

Archivo generado:

```text
outputs/red_riego_palo_alto/inp/red_riego_palo_alto.inp
```

El archivo contiene secciones mínimas:

```text
[TITLE]
[OPTIONS]
[JUNCTIONS]
[PIPES]
[COORDINATES]
[VERTICES]
[END]
```

Antes de correr EPANET, revisar:

- si las cotas de `[JUNCTIONS]` fueron correctamente tomadas del DEM;
- si las tuberías tienen diámetro, rugosidad, pérdida menor y estado;
- si se necesitan tanques, reservorios, bombas o válvulas;
- si se deben agregar demandas base;
- si se deben agregar patterns;
- si las unidades (`UNITS`, `HEADLOSS`) coinciden con el criterio de diseño.

## 7. Generar patterns de riego por sectores

Crear un script, por ejemplo `scripts/generate_patterns_project.py`:

```python
from pathlib import Path

from epanet_tools.irrigation_scheduler import (
    generate_irrigation_patterns,
    insert_patterns_into_inp,
    plot_patterns,
    plot_schedule,
    plot_tank_balance,
    write_patterns_section,
)

OUTDIR = Path("outputs/red_riego_palo_alto/patterns")
OUTDIR.mkdir(parents=True, exist_ok=True)

sectors = [
    {
        "sector_id": "1",
        "nodes": ["J000024", "J000023"],
        "required_volume_m3": 4.00,
        "nominal_flow_m3h": 14.20,
    },
    {
        "sector_id": "2",
        "nodes": ["J000021"],
        "required_volume_m3": 4.75,
        "nominal_flow_m3h": 16.88,
    },
    {
        "sector_id": "3",
        "nodes": ["J000026", "J000027"],
        "required_volume_m3": 1.85,
        "nominal_flow_m3h": 16.20,
    },
]

result = generate_irrigation_patterns(
    sectors,
    start_time="06:00",
    pattern_step_minutes=5,
    cycle_duration_hours=24,
    tank_usable_volume_m3=4.24,
    refill_flow_m3h=3.6,
    min_tank_volume_m3=1.0,
    safety_factor=1.0,
    round_up=True,
)

# Tablas de planificación y balance.
result["schedule"].to_csv(OUTDIR / "schedule.csv", index=False)
result["tank_balance"].to_csv(OUTDIR / "tank_balance.csv", index=False)

# Sección PATTERNS suelta.
write_patterns_section(result["patterns"], OUTDIR / "patterns_section.inp")

# INP con patterns insertados y asignados a nodos.
insert_patterns_into_inp(
    inp_path="outputs/red_riego_palo_alto/inp/red_riego_palo_alto.inp",
    patterns=result["patterns"],
    node_to_pattern=result["node_to_pattern"],
    output_path="outputs/red_riego_palo_alto/inp/red_riego_palo_alto_patterns.inp",
)

# Gráficos opcionales.
ax = plot_schedule(result["schedule"])
ax.figure.savefig(OUTDIR / "schedule.png", dpi=150, bbox_inches="tight")

ax = plot_tank_balance(result["tank_balance"])
ax.figure.savefig(OUTDIR / "tank_balance.png", dpi=150, bbox_inches="tight")

ax = plot_patterns(result["patterns"])
ax.figure.savefig(OUTDIR / "patterns.png", dpi=150, bbox_inches="tight")
```

Ejecutar:

```bash
python scripts/generate_patterns_project.py
```

Salidas esperadas:

```text
outputs/red_riego_palo_alto/patterns/schedule.csv
outputs/red_riego_palo_alto/patterns/tank_balance.csv
outputs/red_riego_palo_alto/patterns/patterns_section.inp
outputs/red_riego_palo_alto/patterns/schedule.png
outputs/red_riego_palo_alto/patterns/tank_balance.png
outputs/red_riego_palo_alto/patterns/patterns.png
outputs/red_riego_palo_alto/inp/red_riego_palo_alto_patterns.inp
```

## 8. Ajustar manualmente el modelo EPANET si corresponde

El `.inp` generado automáticamente es una base. En un proyecto real puede ser necesario agregar o revisar:

- `[RESERVOIRS]`;
- `[TANKS]`;
- `[PUMPS]`;
- `[VALVES]`;
- `[DEMANDS]`;
- `[CURVES]`;
- `[CONTROLS]` o `[RULES]`;
- patrones adicionales;
- opciones de simulación hidráulica y calidad.

Para un modelo de riego sectorizado por patterns, recordar:

- los patterns encienden y apagan demanda nodal;
- no modelan apertura física de válvulas;
- son adecuados para planificación hidráulica de sectores;
- si se necesita representar electroválvulas reales, se deben modelar links y controles.

## 9. Correr EPANET

El repositorio no ejecuta EPANET directamente en el workflow actual. Se puede correr el `.inp` desde EPANET, QEPANET o una herramienta externa que produzca `.rpt`.

Ejemplo conceptual:

```text
Input:  outputs/red_riego_palo_alto/inp/red_riego_palo_alto_patterns.inp
Output: outputs/red_riego_palo_alto/epanet/red_riego_palo_alto.rpt
```

Configurar EPANET para que el reporte incluya resultados temporales de nodos y links, porque el parser de posproceso lee los bloques:

```text
Node Results at <time> Hrs:
Link Results at <time> Hrs:
```

## 10. Posprocesar resultados `.rpt`

Crear un script, por ejemplo `scripts/postprocess_project.py`:

```python
from pathlib import Path

from epanet_postprocess.reader import read_rpt
from epanet_postprocess.summary import summarize_links, summarize_nodes
from epanet_postprocess.diagnostics import (
    check_closed_links,
    check_high_velocities,
    check_low_pressures,
    check_negative_flows,
    check_negative_pressures,
    check_single_active_sector,
    identify_active_sectors,
)
from epanet_postprocess.plots import (
    plot_link_flows,
    plot_link_velocities,
    plot_node_pressures,
)
from epanet_postprocess.export import (
    export_results_to_csv,
    export_results_to_excel,
    export_summary_to_excel,
)

RPT = "outputs/red_riego_palo_alto/epanet/red_riego_palo_alto.rpt"
OUTDIR = Path("outputs/red_riego_palo_alto/postprocess")
OUTDIR.mkdir(parents=True, exist_ok=True)

results = read_rpt(RPT)

# Resúmenes generales.
link_summary = summarize_links(results)
node_summary = summarize_nodes(results)

# Diagnósticos hidráulicos.
low_pressures = check_low_pressures(results, min_pressure=10.0)
negative_pressures = check_negative_pressures(results, threshold=0.0)
high_velocities = check_high_velocities(results, max_velocity=2.0)
negative_flows = check_negative_flows(results, threshold=0.0)
closed_links = check_closed_links(results, flow_tolerance=1e-9)

# Diagnóstico por sectores usando links representativos.
# No mapear todas las tuberías internas: usar entrada, medidor o tubería representativa del sector.
sector_map = {
    "1": ["P000008"],
    "2": ["P000014"],
    "3": ["P000021"],
}
active = identify_active_sectors(results, sector_map, flow_threshold=1e-6)
sector_conflicts = check_single_active_sector(active)

# Gráficos.
plot_link_flows(
    results,
    links=["P000008", "P000014", "P000021"],
    output=OUTDIR / "flows_representative_links.png",
)
plot_link_velocities(
    results,
    links=["P000008", "P000014", "P000021"],
    output=OUTDIR / "velocities_representative_links.png",
)
plot_node_pressures(
    results,
    nodes=["J000024", "J000021", "J000026"],
    output=OUTDIR / "pressures_relevant_nodes.png",
)

# Exportaciones.
export_results_to_csv(results, OUTDIR / "csv")
export_summary_to_excel(
    link_summary,
    node_summary,
    OUTDIR / "summary.xlsx",
)
export_results_to_excel(
    results,
    OUTDIR / "diagnostics.xlsx",
    diagnostics={
        "low_pressures": low_pressures,
        "negative_pressures": negative_pressures,
        "high_velocities": high_velocities,
        "negative_flows": negative_flows,
        "closed_links": closed_links,
        "active_sectors": active,
        "sector_conflicts": sector_conflicts,
    },
)
```

Ejecutar:

```bash
python scripts/postprocess_project.py
```

## 11. Interpretar diagnósticos principales

### Presiones bajas

```python
low_pressures = check_low_pressures(results, min_pressure=10.0)
```

Interpretación:

- si aparecen nodos con demanda activa y presión menor al mínimo de diseño, revisar diámetros, cotas, pérdidas, bomba/tanque o simultaneidad de sectores;
- si aparecen nodos sin demanda o en horarios sin riego, revisar si el umbral debe aplicarse solo a nodos relevantes.

### Velocidades altas

```python
high_velocities = check_high_velocities(results, max_velocity=2.0)
```

Interpretación:

- velocidades altas pueden indicar diámetro insuficiente, caudal sectorial alto o demasiados sectores activos;
- la función usa valor absoluto de velocidad.

### Flujos negativos

```python
negative_flows = check_negative_flows(results)
```

Interpretación:

- flujo negativo normalmente significa que el agua circula en sentido opuesto a la orientación `from_node → to_node`;
- no necesariamente es error;
- revisar solo si el sentido hidráulico esperado era fijo.

### Sectores activos

```python
active = identify_active_sectors(results, sector_map)
sector_conflicts = check_single_active_sector(active)
```

Interpretación:

- si `sector_conflicts` muestra `no_active_sector`, puede haber pausas de recuperación, horario apagado o patrón incorrecto;
- si muestra `multiple_active_sectors`, revisar solapamiento de patterns o demandas asignadas a nodos equivocados;
- el mapa de sectores debe usar links representativos, no todas las tuberías internas del sector.

## 12. Ciclo recomendado de trabajo

```text
1. Preparar shapes y DEM.
2. Crear YAML del proyecto.
3. Ejecutar validate_network.
4. Abrir GeoPackage de trabajo en QGIS.
5. Corregir geometrías fuente si hay errores topológicos relevantes.
6. Repetir validate_network hasta obtener red coherente.
7. Revisar y completar atributos hidráulicos.
8. Revisar INP básico.
9. Generar patterns de riego si el modelo es sectorizado.
10. Correr EPANET.
11. Leer RPT con epanet_postprocess.
12. Revisar presiones, velocidades, sectores activos y warnings.
13. Ajustar geometría, diámetros, demands, patterns o elementos hidráulicos.
14. Repetir hasta obtener un modelo estable.
```

## 13. Ejemplo mínimo de comandos de principio a fin

```bash
# 1. Instalar
conda env create -f environment.yml
conda activate epanet_tools
pip install -e ".[excel]"

# 2. Validar GIS, construir conectividad, muestrear cotas y exportar INP básico
python -m epanet_tools.workflows.validate_network --config config/validate_network_project.yml

# 3. Generar patterns e insertar en INP
python scripts/generate_patterns_project.py

# 4. Correr EPANET manualmente o con la herramienta elegida
# Input: outputs/red_riego_palo_alto/inp/red_riego_palo_alto_patterns.inp
# Output esperado: outputs/red_riego_palo_alto/epanet/red_riego_palo_alto.rpt

# 5. Posprocesar resultados
python scripts/postprocess_project.py
```

## 14. Buenas prácticas

- Mantener los shapes fuente versionados o respaldados antes de limpiar topología.
- No usar CRS geográfico para tolerancias de snapping.
- Documentar el origen vertical del DEM y sus unidades.
- Usar tolerancias de snapping pequeñas y justificadas.
- Revisar manualmente los cruces detectados antes de convertirlos en conexiones.
- Usar defaults hidráulicos solo como punto de partida; para proyecto ejecutivo, completar diámetros y rugosidades reales.
- No interpretar automáticamente caudal negativo como error.
- Elegir umbrales de presión y velocidad según el criterio del proyecto y unidades del modelo.
- Para sectores, mapear links representativos de entrada, no todas las tuberías internas.
- Guardar cada corrida en una carpeta `outputs/<run_name>` distinta para poder comparar alternativas.
