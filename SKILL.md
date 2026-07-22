---
name: bigquery
description: "Usa la librería ruvic_bigquery_connector para consultar datos en Google BigQuery - ejecutar una consulta SQL (execute_query), listar los datasets del proyecto o las tablas de un dataset (list_datasets_and_tables), y estimar cuánto costaría una consulta antes de ejecutarla (estimate_query_cost). Úsala cuando el usuario pida consultar datos en BigQuery, explorar qué datasets/tablas existen, o saber cuánto costaría una consulta antes de correrla. Por defecto, este conector NO permite consultas de escritura (INSERT/UPDATE/DELETE/DROP/etc.) — solo lectura."
triggers:
- bigquery
- big query
- google cloud sql
- consulta sql
- dataset
- data warehouse
---

# Conector BigQuery (ruvic_bigquery_connector)

Librería Python para consultar Google BigQuery, autenticada con una cuenta de servicio de Google Cloud. Está **preinstalada en el runtime** cuando el conector está configurado (si no, instálala con `pip install git+https://github.com/tu-org/conector-bigquery.git#subdirectory=lib`).

## Regla crítica de credenciales

El código generado **NUNCA hardcodea credenciales**. Siempre se leen de variables de entorno, disponibles cuando el conector `bigquery` está configurado:

| Variable | Contenido |
|----------|-----------|
| `RUVIC_BIGQUERY_PROJECT_ID` / `..._SERVICE_ACCOUNT_JSON` | Siempre requeridas |
| `RUVIC_BIGQUERY_LOCATION` | (opcional) default `"US"` |
| `RUVIC_BIGQUERY_MAX_BYTES_BILLED` | (opcional) default 10 GiB |
| `RUVIC_BIGQUERY_ALLOW_WRITE_QUERIES` | (opcional) `true`/`false`, default `false` |
| `RUVIC_BIGQUERY_REQUEST_TIMEOUT` | (opcional) segundos, default `60` |

Si estas variables NO existen, el conector no está configurado: no generes código que lo use; indica al usuario que lo configure en **Settings → Conectores**.

El código generado **NUNCA** usa nombres de variable con segmento de alias (`_DEFAULT_`, `_TEST_`, `_PRODUCCION_`, etc.) — siempre `{ENV_PREFIX}{CAMPO}` tal cual, sin importar cuántas instancias de este conector haya configuradas. Esto aplica salvo que dichos nombres aparezcan explícitamente en una sección autogenerada al final de este skill.

## Conexión (siempre igual)

```python
from ruvic_bigquery_connector import BigQueryClient

client = BigQueryClient()  # lee RUVIC_BIGQUERY_* del entorno automáticamente
```

## ⚠️ Antes de ejecutar una consulta pesada, estima su costo primero

Si el usuario pide algo sobre una tabla que puede ser grande (sin especificar filtros claros), es buena práctica estimar el costo antes de ejecutar:

```python
estimacion = client.estimate_query_cost("SELECT * FROM `proyecto.dataset.tabla_grande`")
print(f"Esta consulta escanearía {estimacion['bytes_processed']} bytes (~${estimacion['estimated_cost_usd']} USD estimado)")
```

Si el costo estimado es alto, avisa al usuario antes de ejecutar la consulta real — no la corras a ciegas.

## Capacidad 1 — Ejecutar una consulta SQL

```python
resultado = client.execute_query("""
    SELECT nombre, SUM(monto) AS total
    FROM `proyecto.dataset.ventas`
    WHERE fecha >= '2026-01-01'
    GROUP BY nombre
    ORDER BY total DESC
    LIMIT 10
""")
for fila in resultado["rows"]:
    print(fila)
print(f"Bytes procesados: {resultado['total_bytes_processed']}")
```

Usa GoogleSQL (el dialecto estándar de BigQuery) — nombres de tabla entre backticks: `` `proyecto.dataset.tabla` ``.

## Capacidad 2 — Listar datasets y tablas

```python
# Listar los datasets del proyecto
datasets = client.list_datasets_and_tables()
for d in datasets:
    print(d["dataset_id"])

# Listar las tablas de un dataset especifico
tablas = client.list_datasets_and_tables("ventas")
for t in tablas:
    print(f"{t['table_id']} ({t['table_type']})")
```

## Capacidad 3 — Estimar el costo de una consulta (sin ejecutarla)

```python
estimacion = client.estimate_query_cost("SELECT * FROM `proyecto.dataset.tabla`")
print(estimacion)
# {'bytes_processed': ..., 'estimated_cost_usd': ..., 'note': '...'}
```

La estimación de costo es aproximada (usa el precio de referencia on-demand) — comunícalo al usuario si te pregunta por el costo exacto, no lo presentes como una cifra exacta de facturación.

## Este conector es de solo lectura por defecto

`execute_query` **rechaza automáticamente** cualquier consulta que contenga palabras clave de escritura (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `TRUNCATE`, `CREATE`, `ALTER`, `MERGE`, `GRANT`, `REVOKE`) salvo que el admin haya activado `allow_write_queries` explícitamente. Si el usuario pide modificar datos y la operación falla con `BigQuerySecurityError`, informa que el conector está configurado en modo de solo lectura — no intentes rodear esta protección.

## Manejo de errores

```python
from ruvic_bigquery_connector import (
    BigQueryAuthError, BigQueryNetworkError, BigQuerySecurityError, BigQueryDataError,
)

try:
    client.execute_query("SELECT * FROM `proyecto.dataset.tabla` LIMIT 10")
except BigQueryAuthError:
    print("Credenciales inválidas o permisos insuficientes — revisa la configuración del conector")
except BigQueryNetworkError:
    print("No se pudo conectar a BigQuery — revisa la red")
except BigQuerySecurityError as e:
    print(f"Consulta bloqueada por seguridad: {e}")  # escritura no permitida, o supera el tope de costo
except BigQueryDataError as e:
    print(f"Error de datos: {e}")  # ej. SQL inválido, tabla no encontrada
```

## Buenas prácticas al generar código

1. Lee credenciales SOLO de las variables `RUVIC_BIGQUERY_*` (el constructor de `BigQueryClient` ya lo hace).
2. Nunca imprimas `RUVIC_BIGQUERY_SERVICE_ACCOUNT_JSON` en logs ni en la salida.
3. Para consultas sobre tablas potencialmente grandes, considera usar `estimate_query_cost` primero.
4. No intentes construir consultas de escritura salvo que el usuario lo pida explícitamente Y sepas que `allow_write_queries` está activo — de lo contrario, la operación fallará de todas formas.
5. Usa siempre `LIMIT` en consultas exploratorias para no traer más filas de las necesarias.
