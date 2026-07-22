"""Validación local del conector bigquery: ejercita las 3 capacidades.

Requiere las env vars RUVIC_BIGQUERY_* exportadas contra un proyecto de
Google Cloud real (BigQuery no tiene una versión local/Docker — a
diferencia de SFTP/AD-LDAP, hace falta un proyecto de GCP real, aunque
puede ser el nivel gratuito / sandbox de BigQuery).

Usa el dataset público "bigquery-public-data.samples" (siempre disponible
gratis para cualquier proyecto de GCP) para no depender de datos propios.
"""

from ruvic_bigquery_connector import BigQueryClient, setup_logging

setup_logging("INFO")
client = BigQueryClient()

print("== 1. Listar datasets del proyecto propio ==")
datasets = client.list_datasets_and_tables()
print(f"  {len(datasets)} dataset(s) en el proyecto {client.config.project_id}")
for d in datasets[:5]:
    print(f"    {d}")

print("== 2. Estimar el costo de una consulta contra datos públicos ==")
sql_publico = "SELECT word, word_count FROM `bigquery-public-data.samples.shakespeare` LIMIT 10"
estimacion = client.estimate_query_cost(sql_publico)
print(f"  {estimacion}")

print("== 3. Ejecutar esa misma consulta ==")
resultado = client.execute_query(sql_publico)
print(f"  {resultado['total_rows']} fila(s), {resultado['total_bytes_processed']} bytes procesados")
for fila in resultado["rows"][:3]:
    print(f"    {fila}")

print("== 4. Confirmar que una consulta de escritura se bloquea por defecto ==")
try:
    client.execute_query("DELETE FROM `proyecto.dataset.tabla` WHERE true")
    print("  ERROR: debio bloquearse")
except Exception as exc:
    print(f"  OK, bloqueado correctamente: {exc}")

print("\nValidación completa.")
