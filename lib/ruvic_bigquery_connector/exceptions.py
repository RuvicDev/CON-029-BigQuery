"""Excepciones propias del conector BigQuery.

Separan los tipos de fallo que el usuario debe distinguir: configuración
inválida, autenticación, red, seguridad (consulta de escritura bloqueada,
tope de costo excedido), y datos (SQL inválido, dataset/tabla inexistente).
"""


class BigQueryConnectorError(Exception):
    """Error base del conector."""


class BigQueryConfigError(BigQueryConnectorError):
    """Configuración inválida: falta un campo requerido, o el JSON de la
    cuenta de servicio no se pudo interpretar."""


class BigQueryAuthError(BigQueryConnectorError):
    """La cuenta de servicio fue rechazada — credenciales inválidas, o sin
    permisos suficientes en el proyecto de Google Cloud."""


class BigQueryNetworkError(BigQueryConnectorError):
    """No se pudo alcanzar la API de BigQuery (DNS, timeout, red)."""


class BigQuerySecurityError(BigQueryConnectorError):
    """La consulta fue bloqueada por una protección de seguridad: es una
    consulta de escritura (DML/DDL) no permitida, o supera el tope de
    bytes facturables configurado."""


class BigQueryDataError(BigQueryConnectorError):
    """La operación es válida pero el SQL es inválido, o el dataset/tabla
    no existe."""
