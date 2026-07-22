# conector-bigquery

Conector Ruvic para Google BigQuery: ejecutar consultas SQL, listar datasets/tablas, y estimar el costo de una consulta antes de ejecutarla.

## Capacidades

`execute_query`, `list_datasets_and_tables`, `estimate_query_cost`.

## Protecciones de seguridad incorporadas

1. **Bloqueo de consultas de escritura por defecto**: `execute_query` rechaza cualquier consulta con `INSERT`/`UPDATE`/`DELETE`/`DROP`/`TRUNCATE`/`CREATE`/`ALTER`/`MERGE`/`GRANT`/`REVOKE`, salvo que se active `allow_write_queries` explícitamente.
2. **Tope de bytes facturables** (`max_bytes_billed`, default 10 GiB): si una consulta escanearía más datos que ese límite, BigQuery la rechaza **antes** de cobrar por ella — protección nativa contra consultas costosas por accidente (ej. sin filtro sobre una tabla enorme sin particionar).

## Instalación

Requiere **Python ≥ 3.10**.

```bash
pip install git+https://github.com/tu-org/conector-bigquery.git#subdirectory=lib
```

Para desarrollo local (editable, en un venv limpio):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ./lib
```

## Variables de entorno

| Variable | Obligatoria | Descripción |
|----------|-------------|-------------|
| `RUVIC_BIGQUERY_PROJECT_ID` | Sí | ID del proyecto de Google Cloud |
| `RUVIC_BIGQUERY_SERVICE_ACCOUNT_JSON` | Sí | Contenido completo del JSON de la cuenta de servicio |
| `RUVIC_BIGQUERY_LOCATION` | No | Default `"US"` |
| `RUVIC_BIGQUERY_MAX_BYTES_BILLED` | No | Default 10 GiB (`10737418240`) |
| `RUVIC_BIGQUERY_ALLOW_WRITE_QUERIES` | No | `true`/`false`, default `false` |
| `RUVIC_BIGQUERY_REQUEST_TIMEOUT` | No | Segundos, default `60` |

## Permisos / prerrequisitos en Google Cloud

1. En **Google Cloud Console** → IAM & Admin → Service Accounts, crea una cuenta de servicio dedicada a esta integración.
2. Otorga los roles:
   - **BigQuery Data Viewer** — para leer datos.
   - **BigQuery Job User** — para ejecutar consultas (correr jobs).
   - **BigQuery Data Editor** — solo si vas a activar `allow_write_queries`.
3. Genera una **clave JSON** para esa cuenta de servicio (Keys → Add Key → JSON) y descárgala.
4. Pega el contenido completo de ese archivo `.json` en el campo correspondiente al configurar el conector en Ruvic.

No otorgues el rol **BigQuery Admin** ni roles a nivel de organización — acótalo al proyecto o los datasets específicos que el agente necesita.

## Cómo correr las pruebas locales

BigQuery no tiene una versión local/Docker (a diferencia de SFTP/AD-LDAP) — hace falta un proyecto real de Google Cloud, aunque puede ser el **nivel gratuito** de GCP (BigQuery da 1 TB de consultas gratis al mes).

```bash
export RUVIC_BIGQUERY_PROJECT_ID=tu-proyecto-de-prueba
export RUVIC_BIGQUERY_SERVICE_ACCOUNT_JSON="$(cat ruta/a/tu-clave.json)"

python test_connection.py
python validate_local.py
```

`validate_local.py` usa el dataset público `bigquery-public-data.samples.shakespeare` (gratis, disponible para cualquier proyecto de GCP) para no depender de datos propios.

Prueba también el caso de error:

```bash
RUVIC_BIGQUERY_SERVICE_ACCOUNT_JSON='{"client_email":"x"}' python test_connection.py
# FALLO: ...
```

## Limitaciones conocidas

- No implementa paginación real más allá de `max_results` por consulta.
- La estimación de costo (`estimate_query_cost`) usa el precio de referencia on-demand ($6.25/TiB) — no refleja proyectos con precio por capacidad (flat-rate/editions) o descuentos negociados.
- No expone jobs asíncronos de larga duración (todo `execute_query` espera el resultado de forma síncrona, hasta el timeout configurado).

## Notas de integración

- El paquete pip es `ruvic-bigquery-connector`; el import name es `ruvic_bigquery_connector`.
- Dependencia externa: `google-cloud-bigquery` (librería oficial de Google).
- Ver `SKILL.md` para los ejemplos de uso que consume el agente.
