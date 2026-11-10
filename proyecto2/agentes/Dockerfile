# Imagen de los agentes para Google Cloud Run.
# Se construye desde la carpeta proyecto2/ (necesita knowledge/ para el modo KB local):
#   cd proyecto2
#   docker build -f agentes/Dockerfile -t kiosco-agentes .
FROM python:3.12-slim

WORKDIR /app
COPY agentes/requirements.txt agentes/requirements.txt
RUN pip install --no-cache-dir -r agentes/requirements.txt uvicorn

COPY knowledge/kb-normativa knowledge/kb-normativa
COPY knowledge/kb-catalogo knowledge/kb-catalogo
COPY agentes/kiosco_agentes agentes/kiosco_agentes
COPY agentes/servidor.py agentes/servidor.py

WORKDIR /app/agentes
ENV PORT=8080 PYTHONUNBUFFERED=1
# Cloud Run define PORT; los secretos llegan por Key Vault o variables del servicio, nunca en la imagen.
CMD exec uvicorn servidor:app --host 0.0.0.0 --port ${PORT}
