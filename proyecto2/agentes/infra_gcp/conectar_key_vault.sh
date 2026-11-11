#!/usr/bin/env bash
# =============================================================================================
# Conecta Cloud Run (kiosco-agentes) con Azure Key Vault por federación de identidad, sin claves
# de Azure guardadas en Google, y pasa el registro de chequeos a la API de Benjamín.
#
# Requisitos ANTES de correrlo (todo lo hace Benjamín, ver README.md de esta carpeta):
#   - ip_salida_fija.sh ya corrido y la IP agregada al firewall de Key Vault y de la API.
#   - Key Vault con los secretos de §4.5 (azure-openai-api-key, foundry-search-api-key,
#     registro-api-key, gemini-api-key).
#   - App registration de Entra ID con federated credential: issuer https://accounts.google.com,
#     subject = uniqueId de kiosco-agentes-sa (102559164316011874170),
#     audience api://AzureADTokenExchange; y rol "Key Vault Secrets User" sobre el Key Vault.
#   - API de registro desplegada (URL https).
#
# Los 4 valores de abajo NO son secretos (Benjamín los pasa por el grupo). Ninguna clave se
# escribe aquí: kiosco_agentes/secretos.py las lee de Key Vault al arrancar.
#
# Dos fases, para no quedar nunca sin claves:
#   FASE=1  agrega las variables y deja los secretos de Secret Manager como están. secretos.py no
#           sobrescribe variables existentes, así que solo carga lo que falta (registro-api-key).
#           Sirve para probar la federación y el firewall sin riesgo.
#   FASE=2  quita de --set-secrets las claves que ya están en Key Vault. Desde aquí salen de Azure.
#
# Uso (Git Bash; NO lo corre Claude):
#   export GCLOUD="/d/Google Cloud CLI/google-cloud-sdk/bin/gcloud.cmd"   # si no está en el PATH
#   export KEY_VAULT_URL="https://<nombre>.vault.azure.net/"
#   export AZURE_TENANT_ID="<guid del tenant>"
#   export AZURE_CLIENT_ID="<guid de la app registration>"
#   export REGISTRO_API_URL="https://<api-de-registro>"
#   FASE=1 bash conectar_key_vault.sh     # y revisar el log secretos_key_vault
#   FASE=2 bash conectar_key_vault.sh
# =============================================================================================
set -euo pipefail

GCLOUD="${GCLOUD:-gcloud}"
PROYECTO="${PROYECTO:-kiosco-g19-agentes}"
REGION="${REGION:-southamerica-west1}"
SERVICIO="${SERVICIO:-kiosco-agentes}"
FASE="${FASE:-1}"
g() { "$GCLOUD" "$@" --project "$PROYECTO"; }

: "${KEY_VAULT_URL:?Falta KEY_VAULT_URL (https://<nombre>.vault.azure.net/)}"
: "${AZURE_TENANT_ID:?Falta AZURE_TENANT_ID}"
: "${AZURE_CLIENT_ID:?Falta AZURE_CLIENT_ID (app registration con la federated credential)}"
: "${REGISTRO_API_URL:?Falta REGISTRO_API_URL}"

# Secretos de Secret Manager que pasan a Key Vault (variable de entorno del servicio).
# AGENTES_API_KEY se queda en Secret Manager: es la clave que valida /consulta y no está en §4.5.
# Si se prefiere que el respaldo Gemini no dependa de Azure (si Azure cae, también cae Key Vault),
# sacar GEMINI_API_KEY de esta lista: secretos.py no la pisa si ya viene de Secret Manager.
PASAN_A_KEY_VAULT="${PASAN_A_KEY_VAULT:-AZURE_API_KEY,FOUNDRY_SEARCH_API_KEY,GEMINI_API_KEY}"

# Revisión actual, para poder volver atrás
ANTERIOR="$(g run services describe "$SERVICIO" --region "$REGION" --format='value(status.latestReadyRevisionName)' | tr -d '\r')"
echo "Revisión actual (para volver atrás): $ANTERIOR"

# El servicio debe salir por la IP fija; si no, Key Vault y la API lo van a rechazar.
if ! g run services describe "$SERVICIO" --region "$REGION" \
     --format='json(spec.template.metadata.annotations)' | grep -q 'network-interfaces'; then
  echo "AVISO: $SERVICIO no tiene Direct VPC egress. Correr antes ip_salida_fija.sh." >&2
  exit 1
fi

VARIABLES="KEY_VAULT_URL=${KEY_VAULT_URL},AZURE_TENANT_ID=${AZURE_TENANT_ID},AZURE_CLIENT_ID=${AZURE_CLIENT_ID}"
VARIABLES+=",REGISTRO_BACKEND=api,REGISTRO_API_URL=${REGISTRO_API_URL}"

case "$FASE" in
  1)
    echo "== FASE 1: agregar variables (los secretos de Secret Manager siguen)"
    # AZURE_CLIENT_SECRET no debe existir: su ausencia es lo que activa la federación.
    g run services update "$SERVICIO" --region "$REGION" \
      --update-env-vars "$VARIABLES" \
      --remove-env-vars AZURE_CLIENT_SECRET
    ;;
  2)
    echo "== FASE 2: quitar de Secret Manager lo que ya está en Key Vault: $PASAN_A_KEY_VAULT"
    g run services update "$SERVICIO" --region "$REGION" \
      --update-env-vars "$VARIABLES" \
      --remove-secrets "$PASAN_A_KEY_VAULT"
    ;;
  *)
    echo "FASE debe ser 1 o 2" >&2; exit 1 ;;
esac

URL="$(g run services describe "$SERVICIO" --region "$REGION" --format='value(status.url)' | tr -d '\r')"
cat <<EOF

== Qué revisar
1. Log de arranque (después de la primera consulta o de /salud):
   gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="$SERVICIO" AND jsonPayload.evento="secretos_key_vault"' --project $PROYECTO --limit 1 --format json
   Esperado: "metodo": "federacion_gcp", "fallidos": [] y
     FASE 1 -> "cargados": ["registro-api-key"], el resto en "ya_definidos"
     FASE 2 -> "cargados": [los secretos que se quitaron + registro-api-key]
   Si "error": "ClientAuthenticationError": revisar la federated credential (subject/audience) o el rol.
   Si fallan con HttpResponseError (403 ForbiddenByFirewall): la IP fija no está en el firewall.
2. GET $URL/salud debe decir "registro": "api".
3. Una consulta de registro desde la app del kiosco debe devolver un id de la API (no de SQLite).

== Volver atrás
   # a) a la revisión anterior, sin tocar nada más (lo más rápido):
   #    gcloud run services update-traffic $SERVICIO --region $REGION --to-revisions $ANTERIOR=100 --project $PROYECTO
   # b) o deshacer la configuración:
   #    gcloud run services update $SERVICIO --region $REGION --project $PROYECTO \\
   #      --remove-env-vars KEY_VAULT_URL,AZURE_TENANT_ID,AZURE_CLIENT_ID,REGISTRO_API_URL \\
   #      --update-env-vars REGISTRO_BACKEND=local \\
   #      --update-secrets GEMINI_API_KEY=gemini-api-key:latest,AZURE_API_KEY=azure-openai-api-key:latest,FOUNDRY_SEARCH_API_KEY=foundry-search-api-key:latest
EOF
