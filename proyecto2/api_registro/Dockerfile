# Imagen de la API de registro para Azure Container Apps.
# Se construye desde proyecto2/api_registro (ver ../infra/desplegar_azure.sh, que usa az acr build).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY esquema.sql .

# Usuario sin privilegios (uid fijo); datos_local solo se usa si DATABASE_URL apunta a SQLite
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin api \
    && mkdir -p /app/datos_local && chown api /app/datos_local
USER 10001

EXPOSE 8000
# Los secretos (REGISTRO_API_KEY, DATABASE_URL) llegan como variables desde Key Vault, nunca en la imagen.
# El log de acceso de uvicorn se apaga: la app escribe su propio log JSON por petición.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-server-header"]
