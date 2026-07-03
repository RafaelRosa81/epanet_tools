# Funcionalidades del repositorio

Este documento describe las funcionalidades implementadas en `epanet_tools` y `epanet_postprocess`, explicando los criterios técnicos utilizados en cada módulo. La intención es que funcione como documentación de referencia para entender qué hace actualmente el repositorio, qué supuestos adopta y cómo usar cada componente.

## 1. Visión general

El repositorio está orientado a construir, validar, editar y analizar modelos EPANET a partir de información GIS. El flujo general implementado es:

1. leer capas vectoriales de tuberías;
2. reproyectarlas a un sistema métrico de trabajo;
3. validar geometrías y CRS;
4. normalizar la topología;
5. construir nodos hidráulicos y conectividad de tuberías;
6. muestrear cotas desde un DEM/MDT;
7. completar atributos hidráulicos;
8. exportar capas GIS de revisión, reportes y un `.inp` básico;
9. generar patrones de demanda para riego por sectores;
10. leer y posprocesar reportes `.rpt` de EPANET.

La biblioteca separa dos paquetes principales:

```text
src/epanet_tools/          # preparación GIS, topología, atributos hidráulicos, INP y patterns
src/epanet_postprocess/    # lectura, diagnóstico, resumen, gráficos y exportación de resultados EPANET
```

## 2. Lectura de información GIS

Módulo principal: `epanet_tools.io.vector`

### Funciones principales

```python
from epanet_tools.io.vector import read_pipe_layer, read_pipe_layers
```

`read_pipe_layer(path, layer=None)` lee una capa individual de tuberías usando `geopandas.read_file`. Acepta Shapefile, GeoPackage u otros formatos soportados por GeoPandas/Fiona. El criterio de validación inicial es estricto: la capa debe existir, no puede estar vacía y debe tener CRS definido.

`read_pipe_layers(pipe_inputs, working_crs=None)` lee varias capas y las combina en una sola red interna. Los criterios usados son:

- si se define `working_crs`, todas las capas se reproyectan en memoria a ese CRS;
- el `working_crs` debe ser proyectado y métrico, porque longitudes, tolerancias y snapping se calculan en unidades del CRS;
- si no se define `working_crs`, todas las capas deben compartir el mismo CRS;
- las capas fuente no se modifican nunca;
- se agregan campos de trazabilidad para saber de dónde vino cada feature.

Campos de trazabilidad agregados:

| Campo | Descripción |
|---|---|
| `_source_order` | orden de la capa en el YAML |
| `_source_path` | ruta del archivo fuente |
| `_source_layer` | nombre de capa, si aplica |
| `_source_index` | índice original del feature |
| `_source_crs` | CRS original antes de reproyectar |

### Ejemplo

```python
from epanet_tools.io.vector import read_pipe_layers

pipes = read_pipe_layers(
    [
        {"path": "data/tuberias_sector_1.shp", "layer": None},
        {"path": "data/red_tuberias.gpkg", "layer": "tuberias"},
    ],
    working_crs="EPSG:32721",
)
```

## 3. Validación de capas de tuberías

Módulo principal: `epanet_tools.topology.validation`

### Funciones principales

```python
from epanet_tools.topology.validation import PipeValidationOptions, validate_pipe_layer
```

La validación revisa si una capa de tuberías es apta para construir una red hidráulica. Los criterios aplicados son:

- la capa debe tener CRS;
- el CRS debe ser proyectado si `require_projected_crs=True`;
- las geometrías deben ser `LineString` por defecto;
- las geometrías vacías o nulas son errores;
- las longitudes deben superar `min_length_m`;
- los `MultiLineString` son reportados como geometría no soportada, salvo que se permita explícitamente con `allow_multilines=True`, en cuyo caso se informan como advertencia.

### Ejemplo

```python
from epanet_tools.topology.validation import PipeValidationOptions, validate_pipe_layer

options = PipeValidationOptions(
    require_projected_crs=True,
    allow_multilines=False,
    min_length_m=0.05,
)
report = validate_pipe_layer(pipes, options)

print(report.has_errors)
print(report.count_by_severity())
```

## 4. Limpieza y normalización topológica

Módulo principal: `epanet_tools.topology.cleaning`

### Funciones principales

```python
from epanet_tools.topology.cleaning import normalize_pipe_topology, snap_pipe_endpoints
```

`normalize_pipe_topology(pipes, tolerance_m)` aplica reglas hidráulicas de conexión sobre las líneas. Los criterios implementados son importantes:

- primero se hace snapping de extremos de tuberías que están dentro de la tolerancia;
- los grupos de extremos cercanos se reemplazan por el centroide promedio del grupo;
- después se detectan extremos de tuberías que caen cerca del interior de otra tubería;
- cuando un extremo se conecta al interior de otra tubería, la tubería objetivo se parte en ese punto;
- los cruces interior-interior puros se ignoran durante la limpieza automática, porque pueden representar tuberías que se cruzan en planta sin conexión hidráulica;
- esos cruces se reportan después como posibles problemas para revisión manual.

Este criterio evita crear conexiones hidráulicas falsas en cruces visuales donde no hay tee, derivación, válvula o accesorio real.

### Ejemplo

```python
from epanet_tools.topology.cleaning import normalize_pipe_topology

pipes_clean, cleaning_report = normalize_pipe_topology(
    pipes,
    tolerance_m=0.20,
)

print(cleaning_report.snapped_endpoint_count)
print(cleaning_report.endpoint_to_segment_snap_count)
print(cleaning_report.split_pipe_count)
```

## 5. Construcción de junctions y conectividad

Módulo principal: `epanet_tools.topology.connectivity`

### Función principal

```python
from epanet_tools.topology.connectivity import build_junctions_and_connectivity
```

Esta función transforma una capa de tuberías limpia en una representación hidráulica básica:

- cada extremo de tubería se convierte en un posible nodo;
- los extremos coincidentes se agrupan redondeando coordenadas con `coordinate_precision`;
- se generan IDs determinísticos para nodos y tuberías;
- por defecto los nodos usan prefijo `J` y las tuberías prefijo `P`;
- se agregan campos `from_node`, `to_node` y `length_m` a cada tubería;
- la longitud hidráulica se calcula desde la geometría proyectada, no desde un atributo fuente;
- geometrías inválidas, vacías, de longitud cero o `MultiLineString` se omiten y se reportan.

### Ejemplo

```python
from epanet_tools.topology.connectivity import build_junctions_and_connectivity

pipes_links, junctions, connectivity_report = build_junctions_and_connectivity(
    pipes_clean,
    node_prefix="J",
    pipe_prefix="P",
    coordinate_precision=6,
)
```

## 6. Revisión topológica posterior

Módulo principal: `epanet_tools.topology.review`

### Función principal

```python
from epanet_tools.topology.review import review_normalized_topology
```

La revisión topológica genera capas GIS de control para QGIS. Los criterios revisados son:

- nodos libres o de grado 0/1 (`FREE_ENDPOINT`);
- tuberías más cortas que `min_pipe_length_m` (`SHORT_PIPE`);
- componentes desconectadas de la red;
- cruces interior-interior sin junction (`POSSIBLE_UNCONNECTED_CROSSING`).

Los cruces sin junction se marcan como `info`, no como error automático, porque pueden representar cruces en planta sin conexión hidráulica. El usuario debe revisar si ese cruce debe convertirse en una conexión real.

### Ejemplo

```python
from epanet_tools.topology.review import review_normalized_topology

topology_errors, topology_report, review_report = review_normalized_topology(
    pipes_links,
    junctions,
    min_pipe_length_m=0.05,
)
```

## 7. Muestreo de elevaciones desde DEM/MDT

Módulo principal: `epanet_tools.terrain.elevation`

### Función principal

```python
from epanet_tools.terrain.elevation import sample_junction_elevations
```

El muestreo toma la cota de cada junction desde un raster DEM/MDT. Los criterios son:

- si no se proporciona DEM, la función no falla; devuelve los nodos sin cota y reporta todas las cotas como faltantes;
- si el DEM no tiene CRS o tiene CRS ambiguo, se puede definir `dem_crs_override`;
- si el CRS de los nodos y el CRS del DEM son distintos, se transforma la coordenada del nodo al CRS del DEM antes de muestrear;
- se usa el valor de la banda 1 del raster;
- valores `nodata` o enmascarados se devuelven como `None`;
- el campo por defecto para cota es `elevation_m`.

### Ejemplo

```python
from epanet_tools.terrain.elevation import sample_junction_elevations

junctions, elevation_report = sample_junction_elevations(
    junctions,
    dem_path="data/mdt.tif",
    dem_crs_override=None,
)
```

## 8. Asignación de atributos hidráulicos

Módulo principal: `epanet_tools.hydraulic.attributes`

### Función principal

```python
from epanet_tools.hydraulic.attributes import apply_hydraulic_attributes
```

La función completa atributos necesarios para exportar tuberías EPANET. Los campos considerados son:

| Campo interno | Uso |
|---|---|
| `diameter_mm` | diámetro de tubería |
| `roughness` | rugosidad, por ejemplo coeficiente Hazen-Williams |
| `minor_loss` | pérdida menor |
| `status` | estado de tubería: `OPEN`, `CLOSED` o `CV` |
| `material` | material descriptivo |

El criterio de prioridad por campo es:

1. conservar valor existente válido en la capa;
2. aplicar regla por categoría si existe `hydraulics.category_field`;
3. aplicar valor de `hydraulics.pipe_defaults`;
4. dejar faltante y reportarlo.

Validaciones aplicadas:

- `diameter_mm` y `roughness` deben ser positivos;
- `minor_loss` debe ser mayor o igual a cero;
- `status` debe ser `OPEN`, `CLOSED` o `CV`;
- `material` no puede ser texto vacío si se usa.

### Ejemplo

```python
from epanet_tools.hydraulic.attributes import apply_hydraulic_attributes

hydraulics_config = {
    "category_field": "material",
    "pipe_defaults": {
        "diameter_mm": 63.0,
        "roughness": 140.0,
        "minor_loss": 0.0,
        "status": "OPEN",
    },
    "categories": {
        "PEAD": {"roughness": 150.0},
        "PVC": {"roughness": 145.0},
    },
}

pipes_links, hydraulic_report = apply_hydraulic_attributes(
    pipes_links,
    hydraulics_config,
)
```

## 9. Exportación de INP básico

Módulo principal: `epanet_tools.io.inp`

### Funciones principales

```python
from epanet_tools.io.inp import build_basic_inp_text, write_basic_inp
```

El exportador genera un archivo EPANET `.inp` mínimo con:

- `[TITLE]`;
- `[OPTIONS]`;
- `[JUNCTIONS]`;
- `[PIPES]`;
- `[COORDINATES]`;
- `[VERTICES]`;
- `[END]`.

Criterios usados:

- las junctions deben tener `node_id` y `elevation_m`;
- las tuberías deben tener `pipe_id`, `from_node`, `to_node`, `length_m`, `diameter_mm`, `roughness`, `minor_loss` y `status`;
- la demanda base se exporta como `0` en `[JUNCTIONS]`;
- las coordenadas de nodos se exportan desde la geometría de las junctions;
- los vértices intermedios de tuberías se exportan en `[VERTICES]` para preservar forma geométrica en EPANET;
- el archivo todavía es básico: no incorpora automáticamente tanques, reservorios, bombas, válvulas ni demandas reales salvo que se agreguen luego.

### Ejemplo

```python
from epanet_tools.io.inp import write_basic_inp

inp_path = write_basic_inp(
    junctions=junctions,
    pipes=pipes_links,
    outdir="outputs/red_ejemplo",
    name="red_ejemplo",
    flow_units="LPS",
    headloss="H-W",
)
```

## 10. Workflow completo de validación y exportación

Módulo principal: `epanet_tools.workflows.validate_network`

### Comando

```bash
python -m epanet_tools.workflows.validate_network --config config/validate_network_example.yml
```

El workflow YAML-driven ejecuta en secuencia:

1. lectura de capas de tuberías;
2. validación inicial de CRS y geometrías;
3. snapping y normalización topológica;
4. construcción de junctions y conectividad;
5. asignación de atributos hidráulicos;
6. muestreo de cotas desde DEM;
7. revisión topológica posterior;
8. validación básica del modelo EPANET;
9. exportación de reportes;
10. exportación de GeoPackage de trabajo;
11. exportación de `.inp` básico.

Salidas esperadas:

```text
outputs/<run_name>/report/<run_name>_validation.json
outputs/<run_name>/report/<run_name>_validation.csv
outputs/<run_name>/report/<run_name>_cleaning.csv
outputs/<run_name>/report/<run_name>_connectivity.csv
outputs/<run_name>/report/<run_name>_elevation.csv
outputs/<run_name>/report/<run_name>_hydraulics.csv
outputs/<run_name>/report/<run_name>_topology_review.csv
outputs/<run_name>/report/<run_name>_basic_model_validation.csv
outputs/<run_name>/gis/<run_name>_network.gpkg
outputs/<run_name>/gis/<run_name>_working.gpkg
outputs/<run_name>/inp/<run_name>.inp
```

## 11. Generación de patterns de riego

Módulo principal: `epanet_tools.irrigation_scheduler`

### Funciones principales

```python
from epanet_tools.irrigation_scheduler import (
    generate_irrigation_patterns,
    write_patterns_section,
    insert_patterns_into_inp,
    plot_schedule,
    plot_tank_balance,
    plot_patterns,
)
```

`generate_irrigation_patterns()` genera patrones binarios de demanda para sectores de riego. Los criterios hidráulicos usados son:

- cada sector se riega una vez por ciclo;
- cada sector recibe un patrón propio;
- todos los nodos asociados a un sector comparten el mismo patrón;
- los patrones son binarios: `1` = demanda activa, `0` = demanda apagada;
- la duración de riego se calcula como `volumen_requerido / caudal_nominal`;
- se puede aplicar `safety_factor` al volumen;
- si `round_up=True`, la duración se redondea hacia arriba al paso completo del pattern;
- se simula un balance simple de tanque con volumen inicial útil, caudal de reposición y volumen mínimo admisible;
- si el siguiente sector haría bajar el tanque por debajo del mínimo, se insertan pausas de recuperación;
- si dentro de un sector el tanque llegaría al mínimo, se insertan pausas internas;
- la función advierte si un sector no entra en el ciclo configurado.

Nota conceptual: estos patterns modifican multiplicadores de demanda nodal. No abren ni cierran físicamente válvulas, bombas o tuberías. Para representar válvulas reales deben modelarse links de EPANET con reglas o controles.

### Ejemplo

```python
from epanet_tools.irrigation_scheduler import generate_irrigation_patterns, write_patterns_section

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

write_patterns_section(result["patterns"], "outputs/patterns_section.inp")
```

Para insertar los patterns en un `.inp` existente:

```python
from epanet_tools.irrigation_scheduler import insert_patterns_into_inp

insert_patterns_into_inp(
    inp_path="outputs/red_ejemplo/inp/red_ejemplo.inp",
    patterns=result["patterns"],
    node_to_pattern=result["node_to_pattern"],
    output_path="outputs/red_ejemplo/inp/red_ejemplo_patterns.inp",
)
```

La asignación de patterns se intenta primero en `[DEMANDS]`. Si un nodo no tiene fila explícita en `[DEMANDS]`, se intenta asignar en `[JUNCTIONS]` cuando la fila tiene columna de demanda base editable.

## 12. Lectura de resultados EPANET

Paquete principal: `epanet_postprocess`

Módulo: `epanet_postprocess.reader`

### Funciones principales

```python
from epanet_postprocess.reader import read_rpt, read_node_results_csv, read_link_results_csv
```

`read_rpt()` lee reportes estándar EPANET 2.x. Los criterios del parser son:

- reconoce bloques `Node Results at <time> Hrs:`;
- reconoce bloques `Link Results at <time> Hrs:`;
- acepta continuaciones de página marcadas como `(continued)`;
- ignora tablas estáticas, encabezados, páginas y líneas separadoras;
- conserva flujos negativos, porque normalmente significan dirección opuesta a la orientación del link, no necesariamente error;
- devuelve las unidades como “as reported by EPANET”, porque dependen del `.inp` y del `.rpt` original.

Estructura devuelta:

```python
{
    "nodes": nodes_dataframe,
    "links": links_dataframe,
    "metadata": metadata_dictionary,
}
```

Columnas normalizadas:

```text
nodes: time, node_id, demand, head, pressure, quality
links: time, link_id, flow, velocity, headloss, status
```

### Ejemplo

```python
from epanet_postprocess.reader import read_rpt

results = read_rpt("outputs/red_ejemplo/epanet/red_ejemplo.rpt")
print(results["metadata"])
```

## 13. Gráficos de resultados

Módulo: `epanet_postprocess.plots`

### Funciones principales

```python
from epanet_postprocess.plots import (
    plot_link_flows,
    plot_link_velocities,
    plot_node_pressures,
    plot_node_demands,
)
```

Criterios:

- las funciones trabajan sobre las tablas normalizadas de `read_rpt()`;
- se puede filtrar por links o nodos específicos;
- si se solicita un elemento que no existe, se lanza un `KeyError`;
- si no hay datos para graficar, se lanza un `ValueError`;
- si se define `output`, la figura se guarda automáticamente creando la carpeta si no existe.

### Ejemplo

```python
from epanet_postprocess.plots import plot_link_velocities, plot_node_pressures

plot_link_velocities(
    results,
    links=["P000008", "P000009"],
    output="outputs/postprocess/velocities_selected_links.png",
)

plot_node_pressures(
    results,
    nodes=["J000024", "J000035"],
    output="outputs/postprocess/pressures_selected_nodes.png",
)
```

## 14. Resúmenes estadísticos

Módulo: `epanet_postprocess.summary`

### Funciones principales

```python
from epanet_postprocess.summary import summarize_links, summarize_nodes, summarize_variable
```

Criterios:

- los resultados se agrupan por elemento (`link_id` o `node_id`);
- se calculan mínimo, máximo, media, desviación estándar, primer valor y último valor;
- para links se resumen `flow`, `velocity` y `headloss`;
- para nodos se resumen `demand`, `head` y `pressure`;
- si una variable no existe, se devuelve una tabla vacía para esa variable.

### Ejemplo

```python
from epanet_postprocess.summary import summarize_links, summarize_nodes

link_summary = summarize_links(results)
node_summary = summarize_nodes(results)
```

## 15. Diagnósticos hidráulicos

Módulo: `epanet_postprocess.diagnostics`

### Funciones principales

```python
from epanet_postprocess.diagnostics import (
    check_low_pressures,
    check_negative_pressures,
    check_extreme_negative_pressures,
    check_high_velocities,
    check_negative_flows,
    check_closed_links,
    identify_active_sectors,
    check_single_active_sector,
    check_sector_flow_balance,
)
```

Criterios:

- `check_low_pressures()` devuelve nodos con presión menor al umbral de servicio;
- `check_negative_pressures()` devuelve presiones menores a un umbral, por defecto 0;
- `check_extreme_negative_pressures()` usa por defecto -10 como umbral de presión fuertemente negativa;
- `check_high_velocities()` usa valor absoluto de velocidad, porque una velocidad negativa puede representar dirección opuesta;
- `check_negative_flows()` reporta caudales firmados negativos, pero no los interpreta automáticamente como error;
- `check_closed_links()` busca links con estado `CLOSED` y marca si tienen flujo no despreciable;
- `identify_active_sectors()` identifica sectores activos a partir de links representativos, no de todas las tuberías internas;
- `check_single_active_sector()` reporta pasos de tiempo con cero sectores activos o más de un sector activo;
- `check_sector_flow_balance()` compara caudales esperados con caudales simulados en links representativos.

### Ejemplo

```python
from epanet_postprocess.diagnostics import (
    check_high_velocities,
    check_low_pressures,
    identify_active_sectors,
    check_single_active_sector,
)

low_pressures = check_low_pressures(results, min_pressure=10.0)
high_velocities = check_high_velocities(results, max_velocity=2.0)

sector_map = {
    "1": ["P000008"],
    "2": ["P000014"],
    "3": ["P000021"],
}

active = identify_active_sectors(results, sector_map, flow_threshold=1e-6)
sector_conflicts = check_single_active_sector(active)
```

## 16. Exportación de resultados

Módulo: `epanet_postprocess.export`

### Funciones principales

```python
from epanet_postprocess.export import (
    export_results_to_csv,
    export_results_to_excel,
    export_summary_to_excel,
)
```

Criterios:

- `export_results_to_csv()` genera `nodes_results.csv` y `links_results.csv`;
- `export_results_to_excel()` exporta hojas `nodes`, `links`, `metadata` y diagnósticos opcionales;
- los nombres de hojas de diagnósticos se recortan a 31 caracteres por compatibilidad con Excel;
- `export_summary_to_excel()` exporta resúmenes de links y nodos.

### Ejemplo

```python
from epanet_postprocess.export import export_results_to_csv, export_results_to_excel

export_results_to_csv(results, "outputs/postprocess/csv")
export_results_to_excel(
    results,
    "outputs/postprocess/diagnostics.xlsx",
    diagnostics={
        "low_pressures": low_pressures,
        "high_velocities": high_velocities,
        "sector_conflicts": sector_conflicts,
    },
)
```

## 17. Limitaciones actuales

El repositorio ya implementa un flujo funcional desde GIS hasta un `.inp` básico y herramientas de posproceso, pero algunas partes todavía son deliberadamente simples:

- el `.inp` básico no incorpora automáticamente tanques, reservorios, bombas, válvulas ni demandas espaciales complejas;
- los patterns modifican demandas, no estados físicos de links;
- los cruces interior-interior no se conectan automáticamente;
- el muestreo de elevación usa la banda 1 del DEM y no aplica suavizado ni interpolación avanzada;
- la validación hidráulica básica verifica campos requeridos y conectividad, pero no reemplaza una corrida hidráulica en EPANET;
- los umbrales de presión, velocidad y caudal deben ajustarse al criterio de diseño y a las unidades del modelo.
