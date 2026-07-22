"""Cliente para consultar Google BigQuery.

Capacidades:
- execute_query():             ejecutar una consulta SQL (solo lectura por defecto).
- list_datasets_and_tables():  listar datasets del proyecto, o tablas de un dataset.
- estimate_query_cost():       estimar cuántos bytes escanearía una consulta y su costo aproximado, sin ejecutarla (dry run).

Protecciones de seguridad incorporadas:
- Por defecto, este conector **bloquea consultas de escritura** (INSERT,
  UPDATE, DELETE, DROP, TRUNCATE, CREATE, ALTER, MERGE, GRANT, REVOKE) —
  es un conector de consulta, no de modificación de datos. Se puede
  habilitar explícitamente con `allow_write_queries` si hace falta.
- Toda consulta real (`execute_query`) lleva un tope de bytes facturables
  (`maximum_bytes_billed`) configurado — si una consulta escanearía más
  de ese límite, BigQuery la rechaza ANTES de cobrar por ella, evitando
  sorpresas de costo por una consulta mal escrita (ej. sin filtro sobre
  una tabla enorme sin particionar).

Autenticación: cuenta de servicio de Google Cloud (JSON). Las
credenciales SIEMPRE provienen de variables de entorno RUVIC_BIGQUERY_*
(ver config.BigQueryConfig.from_env). Prohibido hardcodearlas.
"""

from __future__ import annotations

import re
from typing import Any

from google.api_core import exceptions as gcp_exceptions
from google.auth import exceptions as auth_exceptions
from google.cloud import bigquery
from google.oauth2 import service_account

from .config import BigQueryConfig
from .exceptions import (
    BigQueryAuthError,
    BigQueryDataError,
    BigQueryNetworkError,
    BigQuerySecurityError,
)
from .logging_utils import get_logger

_WRITE_KEYWORDS = (
    "INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "CREATE",
    "ALTER", "MERGE", "GRANT", "REVOKE",
)
_WRITE_KEYWORD_RE = re.compile(
    r"\b(" + "|".join(_WRITE_KEYWORDS) + r")\b", re.IGNORECASE
)

_ON_DEMAND_PRICE_PER_TIB_USD = 6.25  # precio de referencia; puede variar por región/acuerdo


class BigQueryClient:
    """Cliente de BigQuery autenticado con una cuenta de servicio.

    Args:
        config: configuración de conexión. Si se omite, se lee de las
            variables de entorno RUVIC_BIGQUERY_* (comportamiento estándar
            en el runtime de la plataforma).

    Ejemplo:
        >>> client = BigQueryClient()  # lee RUVIC_BIGQUERY_* del entorno
        >>> client.execute_query("SELECT 1 AS n")
        {'rows': [{'n': 1}], 'total_rows': 1, 'total_bytes_processed': 0}
    """

    def __init__(self, config: BigQueryConfig | None = None) -> None:
        self.config = config or BigQueryConfig.from_env()
        self._logger = get_logger()
        self._client: bigquery.Client | None = None

    # ------------------------------------------------------------------ #
    # Cliente subyacente (creado una sola vez, perezosamente)
    # ------------------------------------------------------------------ #

    def _get_client(self) -> bigquery.Client:
        if self._client is not None:
            return self._client
        try:
            credentials = service_account.Credentials.from_service_account_info(
                self.config.service_account_info,
                scopes=["https://www.googleapis.com/auth/bigquery"],
            )
        except (ValueError, KeyError) as exc:
            raise BigQueryAuthError(
                f"No se pudo interpretar la cuenta de servicio: {exc}"
            ) from exc

        self._client = bigquery.Client(
            project=self.config.project_id,
            credentials=credentials,
            location=self.config.location,
        )
        return self._client

    # ------------------------------------------------------------------ #
    # Protección de seguridad: bloqueo de consultas de escritura
    # ------------------------------------------------------------------ #

    def _validate_query_safety(self, sql: str) -> None:
        if self.config.allow_write_queries:
            return
        match = _WRITE_KEYWORD_RE.search(sql)
        if match:
            raise BigQuerySecurityError(
                f"Consulta bloqueada: contiene la palabra clave de escritura "
                f"{match.group(1).upper()!r}. Este conector solo permite consultas "
                "de lectura por defecto. Si necesitas ejecutar escrituras, activa "
                "'allow_write_queries' explícitamente en la configuración del conector."
            )

    # ------------------------------------------------------------------ #
    # Manejo de errores
    # ------------------------------------------------------------------ #

    def _translate_error(self, exc: Exception, context: str) -> Exception:
        if isinstance(exc, auth_exceptions.GoogleAuthError):
            return BigQueryAuthError(f"Autenticación fallida en {context}: {exc}")
        if isinstance(exc, (gcp_exceptions.Unauthorized, gcp_exceptions.Forbidden)):
            message = str(exc)
            if "bytesBilled" in message or "maximum bytes billed" in message.lower():
                return BigQuerySecurityError(
                    f"La consulta en {context} supera el tope de bytes facturables "
                    f"configurado ({self.config.max_bytes_billed} bytes). Ajusta la "
                    "consulta para escanear menos datos (ej. agrega filtros), o "
                    "aumenta 'max_bytes_billed' en la configuración si el costo es "
                    "esperado."
                )
            return BigQueryAuthError(
                f"Permisos insuficientes en {context}: {exc}. La cuenta de servicio "
                "necesita el rol 'BigQuery Data Viewer' y 'BigQuery Job User' como mínimo."
            )
        if isinstance(exc, gcp_exceptions.NotFound):
            return BigQueryDataError(f"No encontrado en {context}: {exc}")
        if isinstance(exc, gcp_exceptions.BadRequest):
            return BigQueryDataError(f"Solicitud inválida en {context} (SQL inválido?): {exc}")
        if isinstance(exc, (gcp_exceptions.ServiceUnavailable, gcp_exceptions.DeadlineExceeded,
                             gcp_exceptions.RetryError)):
            return BigQueryNetworkError(f"Error de red/timeout en {context}: {exc}")
        if isinstance(exc, gcp_exceptions.GoogleAPICallError):
            return BigQueryDataError(f"Error de BigQuery en {context}: {exc}")
        return BigQueryNetworkError(f"Error inesperado en {context}: {exc}")

    # ------------------------------------------------------------------ #
    # Ping / prueba de conexión
    # ------------------------------------------------------------------ #

    def ping(self) -> bool:
        """Verifica las credenciales listando datasets (barato, no ejecuta ninguna consulta)."""
        client = self._get_client()
        try:
            next(iter(client.list_datasets(max_results=1)), None)
        except Exception as exc:  # noqa: BLE001 - se traduce a una excepcion propia
            raise self._translate_error(exc, "ping") from exc
        self._logger.info("Ping exitoso a BigQuery (proyecto: %s)", self.config.project_id)
        return True

    # ------------------------------------------------------------------ #
    # Capacidad 1: ejecutar una consulta
    # ------------------------------------------------------------------ #

    def execute_query(self, sql: str, max_results: int = 1000) -> dict[str, Any]:
        """Ejecuta una consulta SQL (solo lectura por defecto).

        Args:
            sql: consulta en GoogleSQL (dialecto estándar de BigQuery).
            max_results: máximo de filas a traer (default 1000).

        Returns:
            Dict con "rows" (lista de dicts), "total_rows", y
            "total_bytes_processed".

        Raises:
            BigQuerySecurityError: si la consulta contiene una palabra
                clave de escritura y `allow_write_queries` no está activo,
                o si supera el tope de bytes facturables.

        Ejemplo:
            >>> client.execute_query("SELECT nombre, ventas FROM `proyecto.dataset.tabla` LIMIT 10")
            {'rows': [{'nombre': 'Acme', 'ventas': 1000}, ...], 'total_rows': 10, ...}
        """
        if not sql or not sql.strip():
            raise BigQueryDataError("La consulta SQL no puede estar vacía.")
        self._validate_query_safety(sql)

        client = self._get_client()
        job_config = bigquery.QueryJobConfig(maximum_bytes_billed=self.config.max_bytes_billed)

        try:
            query_job = client.query(sql, job_config=job_config)
            results = query_job.result(max_results=max_results, timeout=self.config.timeout)
            rows = [dict(row) for row in results]
        except Exception as exc:  # noqa: BLE001 - se traduce a una excepcion propia
            raise self._translate_error(exc, "execute_query") from exc

        self._logger.info(
            "execute_query: %d fila(s), %s bytes procesados",
            len(rows), query_job.total_bytes_processed,
        )
        return {
            "rows": rows,
            "total_rows": results.total_rows,
            "total_bytes_processed": query_job.total_bytes_processed,
        }

    # ------------------------------------------------------------------ #
    # Capacidad 2: listar datasets o tablas
    # ------------------------------------------------------------------ #

    def list_datasets_and_tables(self, dataset_id: str | None = None) -> list[dict[str, Any]]:
        """Lista los datasets del proyecto, o las tablas de un dataset específico.

        Args:
            dataset_id: si se omite, lista los datasets del proyecto. Si
                se indica, lista las tablas dentro de ese dataset.

        Returns:
            Si `dataset_id` es None: lista de dicts con "dataset_id".
            Si `dataset_id` se indica: lista de dicts con "table_id" y
            "table_type" ("TABLE" o "VIEW").

        Ejemplo:
            >>> client.list_datasets_and_tables()
            [{'dataset_id': 'ventas'}, {'dataset_id': 'marketing'}]
            >>> client.list_datasets_and_tables("ventas")
            [{'table_id': 'pedidos', 'table_type': 'TABLE'}, ...]
        """
        client = self._get_client()
        try:
            if dataset_id:
                items = [
                    {"table_id": t.table_id, "table_type": t.table_type}
                    for t in client.list_tables(dataset_id)
                ]
            else:
                items = [{"dataset_id": d.dataset_id} for d in client.list_datasets()]
        except Exception as exc:  # noqa: BLE001 - se traduce a una excepcion propia
            raise self._translate_error(exc, f"list_datasets_and_tables({dataset_id!r})") from exc

        self._logger.info(
            "list_datasets_and_tables(%s): %d resultado(s)", dataset_id, len(items)
        )
        return items

    # ------------------------------------------------------------------ #
    # Capacidad 3: estimar el costo de una consulta (dry run)
    # ------------------------------------------------------------------ #

    def estimate_query_cost(self, sql: str) -> dict[str, Any]:
        """Estima cuántos bytes escanearía una consulta y su costo
        aproximado, sin ejecutarla (usa el modo "dry run" de BigQuery).

        Args:
            sql: consulta en GoogleSQL a evaluar.

        Returns:
            Dict con "bytes_processed", "estimated_cost_usd" (estimación
            basada en el precio on-demand de referencia, $6.25/TiB — puede
            no reflejar tu tarifa real si usas precio por capacidad o
            tienes descuentos), y "note" con esa aclaración.

        Ejemplo:
            >>> client.estimate_query_cost("SELECT * FROM `proyecto.dataset.tabla_grande`")
            {'bytes_processed': 549755813888, 'estimated_cost_usd': 3.125, 'note': '...'}
        """
        if not sql or not sql.strip():
            raise BigQueryDataError("La consulta SQL no puede estar vacía.")

        client = self._get_client()
        job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)

        try:
            query_job = client.query(sql, job_config=job_config)
        except Exception as exc:  # noqa: BLE001 - se traduce a una excepcion propia
            raise self._translate_error(exc, "estimate_query_cost") from exc

        bytes_processed = query_job.total_bytes_processed or 0
        tib = bytes_processed / (1024 ** 4)
        estimated_cost = round(tib * _ON_DEMAND_PRICE_PER_TIB_USD, 6)

        self._logger.info(
            "estimate_query_cost: %d bytes, ~$%.6f USD (estimación)",
            bytes_processed, estimated_cost,
        )
        return {
            "bytes_processed": bytes_processed,
            "estimated_cost_usd": estimated_cost,
            "note": (
                f"Estimación basada en el precio on-demand de referencia "
                f"(${_ON_DEMAND_PRICE_PER_TIB_USD}/TiB). Puede no reflejar tu costo "
                "real si el proyecto usa precio por capacidad (flat-rate/editions) "
                "o tiene descuentos negociados."
            ),
        }
