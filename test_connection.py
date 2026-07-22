"""Prueba de conexión estándar del conector bigquery.

Firma estándar Ruvic: def test_connection() -> tuple[bool, str]
- Lee la configuración EXCLUSIVAMENTE de las env vars RUVIC_BIGQUERY_*.
- Nunca lanza excepciones; retorna (ok, mensaje).

Ejecutable también como script para pruebas locales:
    python test_connection.py
"""

from __future__ import annotations


def test_connection() -> tuple[bool, str]:
    """Verifica las credenciales listando datasets del proyecto."""
    try:
        from ruvic_bigquery_connector import (
            BigQueryAuthError,
            BigQueryClient,
            BigQueryDataError,
            BigQueryNetworkError,
        )
    except ImportError:
        return (
            False,
            "La librería ruvic-bigquery-connector no está instalada. "
            "Instala con: pip install git+https://github.com/tu-org/"
            "conector-bigquery.git#subdirectory=lib",
        )

    try:
        client = BigQueryClient()  # valida config y JSON de la cuenta de servicio
    except ValueError as exc:
        return False, str(exc)

    try:
        client.ping()
    except BigQueryAuthError as exc:
        return False, f"Autenticación fallida: {exc}"
    except BigQueryNetworkError as exc:
        return False, f"Error de red: {exc}"
    except BigQueryDataError as exc:
        return False, f"Error de datos: {exc}"
    except Exception as exc:  # red de seguridad: jamás propagar
        return False, f"Error inesperado: {exc}"

    return True, f"Conexión exitosa al proyecto {client.config.project_id}"


if __name__ == "__main__":
    ok, message = test_connection()
    print(f"{'OK' if ok else 'FALLO'}: {message}")
    raise SystemExit(0 if ok else 1)
