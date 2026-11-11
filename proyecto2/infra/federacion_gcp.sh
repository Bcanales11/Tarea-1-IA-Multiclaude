#!/usr/bin/env bash
# =============================================================================================
# Acceso de Cloud Run (Google) a Key Vault SIN claves fijas: federación de identidad.
#
# Crea en Entra ID:
#   - App registration "kiosco-agentes-gcp" + su service principal
#   - Credencial federada que confía en la service account de Google de Cloud Run:
#       issuer   = https://accounts.google.com
#       subject  = ID numérico (uniqueId) de kiosco-agentes-sa@kiosco-g19-agentes.iam.gserviceaccount.com
#       audience = api://AzureADTokenExchange
#   - Rol "Key Vault Secrets User" SOLO sobre los 4 secretos de los agentes (§4.5), no sobre todo
#     el vault: Cloud Run no puede leer la URL de la base de datos.
#
# Cómo funciona: Cloud Run pide al servidor de metadatos de Google un ID token con audience
# api://AzureADTokenExchange; Entra ID lo valida contra la credencial federada y entrega un token
# de Azure para Key Vault. No hay ningún secreto guardado en Google ni en el código.
#
# Uso:
#   GCP_SA_UNIQUE_ID=123456789012345678901 bash federacion_gcp.sh
# (el ID lo entrega Max: gcloud iam service-accounts describe <sa> --format='value(uniqueId)')
# Correr DESPUÉS de cargar_secretos.sh (el rol se asigna por secreto y el secreto debe existir).
# =============================================================================================
set -euo pipefail

DIR_INFRA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=variables.sh
source "$DIR_INFRA/variables.sh"

NOMBRE_CREDENCIAL="gcp-cloud-run-kiosco-agentes"

preparar_az
[[ "$GCP_SA_UNIQUE_ID" =~ ^[0-9]{15,25}$ ]] \
  || error "GCP_SA_UNIQUE_ID debe ser el ID numérico de la service account (no el correo). Pídeselo a Max."
KV_ID="$(azv keyvault show -n "$KV_NOMBRE" --query id -o tsv 2>/dev/null)" \
  || error "no existe el Key Vault $KV_NOMBRE (corre desplegar_azure.sh)"
TENANT_ID="$(azv account show --query tenantId -o tsv)"

# ---------------------------------------------------------------------------------------------
paso "1. App registration $APP_FEDERADA"
# ---------------------------------------------------------------------------------------------
APP_ID="$(azv ad app list --display-name "$APP_FEDERADA" --query '[0].appId' -o tsv)"
if [[ -z "$APP_ID" ]]; then
  APP_ID="$(azv ad app create --display-name "$APP_FEDERADA" --sign-in-audience AzureADMyOrg --query appId -o tsv)" \
    || error "no se pudo crear la app registration. Si tu cuenta no tiene permiso en Entra ID, ver README: plan B"
  info "creada (appId = AZURE_CLIENT_ID)"
else
  info "ya existe"
fi
if ! az ad sp show --id "$APP_ID" -o none 2>/dev/null; then
  reintentar 5 15 az ad sp create --id "$APP_ID" -o none
fi
SP_OBJ="$(azv ad sp show --id "$APP_ID" --query id -o tsv)"

# ---------------------------------------------------------------------------------------------
paso "2. Credencial federada (Google -> Entra ID)"
# ---------------------------------------------------------------------------------------------
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
cat > "$tmp" <<JSON
{
  "name": "$NOMBRE_CREDENCIAL",
  "issuer": "https://accounts.google.com",
  "subject": "$GCP_SA_UNIQUE_ID",
  "audiences": ["api://AzureADTokenExchange"],
  "description": "Cloud Run $GCP_PROYECTO ($GCP_SA_EMAIL) lee secretos de Key Vault sin claves fijas"
}
JSON
existe="$(azv ad app federated-credential list --id "$APP_ID" --query "length([?name=='$NOMBRE_CREDENCIAL'])" -o tsv)"
if [[ "$existe" == "0" ]]; then
  az ad app federated-credential create --id "$APP_ID" --parameters "@$(ruta_nativa "$tmp")" -o none
  info "creada"
else
  az ad app federated-credential update --id "$APP_ID" --federated-credential-id "$NOMBRE_CREDENCIAL" \
    --parameters "@$(ruta_nativa "$tmp")" -o none
  info "actualizada"
fi

# ---------------------------------------------------------------------------------------------
paso "3. Rol 'Key Vault Secrets User' solo sobre los secretos de los agentes"
# ---------------------------------------------------------------------------------------------
faltan=0
for secreto in "${SECRETOS_AGENTES[@]}"; do
  if secreto_existe "$secreto"; then
    asignar_rol "$SP_OBJ" ServicePrincipal "Key Vault Secrets User" "$KV_ID/secrets/$secreto"
  else
    aviso "$secreto todavía no existe en Key Vault: corre cargar_secretos.sh y luego este script otra vez"
    faltan=1
  fi
done

# ---------------------------------------------------------------------------------------------
paso "Listo"
# ---------------------------------------------------------------------------------------------
cat <<FIN

  Valores NO secretos para Max (variables del servicio de Cloud Run):
    AZURE_TENANT_ID = $TENANT_ID
    AZURE_CLIENT_ID = $APP_ID
    KEY_VAULT_URL   = https://$KV_NOMBRE.vault.azure.net

  Recordatorio: Key Vault solo acepta la IP de salida fija de Cloud Run (IP_SALIDA_CLOUD_RUN).
  Si Max todavía no la tenía al desplegar, vuelve a correr desplegar_azure.sh con ella.
FIN
if [[ "$faltan" != "0" ]]; then aviso "Faltan secretos: el rol no quedó asignado para todos."; fi
