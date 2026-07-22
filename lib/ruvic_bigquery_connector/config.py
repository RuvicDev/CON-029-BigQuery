"""Configuración del conector leída desde variables de entorno.

Convención de la plataforma: cada campo del formulario de configuración
llega como variable de entorno {ENV_PREFIX}{CAMPO} en mayúsculas.
Para este conector el prefijo es RUVIC_BIGQUERY_.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

ENV_PREFIX = "RUVIC_BIGQUERY_"

_DEFAULT_MAX_BYTES_BILLED = 10 * 1024 ** 3  # 10 GiB — tope de seguridad conservador por defecto


@dataclass(frozen=True)
class BigQueryConfig:
    """Parámetros de conexión a un proyecto de Google BigQuery."""

    project_id: str
    service_account_info: dict = field(default_factory=dict)
    location: str = "US"
    max_bytes_billed: int = _DEFAULT_MAX_BYTES_BILLED
    allow_write_queries: bool = False
    timeout: int = 60

    @classmethod
    def from_env(cls) -> "BigQueryConfig":
        """Construye la configuración desde las variables RUVIC_BIGQUERY_*.

        Raises:
            ValueError: si falta PROJECT_ID/SERVICE_ACCOUNT_JSON, o el
                JSON de la cuenta de servicio no es válido.
        """
        project_id = os.environ.get(f"{ENV_PREFIX}PROJECT_ID", "").strip()
        sa_json_raw = os.environ.get(f"{ENV_PREFIX}SERVICE_ACCOUNT_JSON", "").strip()

        missing = [
            name for name, val in (
                (f"{ENV_PREFIX}PROJECT_ID", project_id),
                (f"{ENV_PREFIX}SERVICE_ACCOUNT_JSON", sa_json_raw),
            ) if not val
        ]
        if missing:
            raise ValueError(
                "Faltan variables de entorno del conector bigquery: "
                + ", ".join(missing)
                + ". Configura el conector en Settings → Conectores."
            )

        try:
            service_account_info = json.loads(sa_json_raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{ENV_PREFIX}SERVICE_ACCOUNT_JSON no es un JSON válido: {exc}. "
                "Pega el contenido completo del archivo de clave de la cuenta de "
                "servicio, tal como lo descargaste de Google Cloud Console."
            ) from exc

        if not isinstance(service_account_info, dict) or "client_email" not in service_account_info:
            raise ValueError(
                f"{ENV_PREFIX}SERVICE_ACCOUNT_JSON no parece ser una clave de cuenta "
                "de servicio válida (falta 'client_email')."
            )

        allow_write_raw = os.environ.get(f"{ENV_PREFIX}ALLOW_WRITE_QUERIES", "false").strip().lower()

        return cls(
            project_id=project_id,
            service_account_info=service_account_info,
            location=os.environ.get(f"{ENV_PREFIX}LOCATION", "US").strip() or "US",
            max_bytes_billed=int(
                os.environ.get(f"{ENV_PREFIX}MAX_BYTES_BILLED", str(_DEFAULT_MAX_BYTES_BILLED))
            ),
            allow_write_queries=allow_write_raw in ("true", "1", "yes"),
            timeout=int(os.environ.get(f"{ENV_PREFIX}REQUEST_TIMEOUT", "60")),
        )
