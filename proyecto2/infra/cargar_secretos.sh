#!/usr/bin/env bash
# =============================================================================================
# Carga en Key Vault los secretos que leen los agentes (INSTRUCCIONES_GRUPO.md §4.5).
#
#   azure-openai-api-key    key del deployment gpt-5.4-mini en Foundry
#   foundry-search-api-key  key de consulta de Azure AI Search (knowledge bases)
#   gemini-api-key          key de Gemini (respaldo; la entrega Max por mensaje privado)
#   registro-api-key        la genera desplegar_azure.sh; aquí solo se rota (ROTAR_API_KEY=true)
#
# De dónde sale cada valor, en este orden:
#   1. Variable de entorno (AZURE_OPENAI_API_KEY, FOUNDRY_SEARCH_API_KEY, GEMINI_API_KEY).
#   2. Directo desde Azure, sin copiar ni pegar, si defines dónde está el recurso:
#        FOUNDRY_RECURSO=kiosco-g19-foundry FOUNDRY_RG=<su grupo>   -> azure-openai-api-key
#        SEARCH_SERVICIO=kiosco-g19-search  SEARCH_RG=<su grupo>    -> foundry-search-api-key
#   3. Si la terminal es interactiva, lo pide sin mostrarlo en pantalla (read -s).
#   Si no hay valor, ese secreto se salta (el script se puede correr de nuevo).
#
# Los valores nunca se imprimen ni quedan en el historial de la terminal.
# Uso:  bash cargar_secretos.sh
# =============================================================================================
set -euo pipefail

DIR_INFRA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=variables.sh
source "$DIR_INFRA/variables.sh"

FOUNDRY_RECURSO="${FOUNDRY_RECURSO:-kiosco-g19-foundry}"
FOUNDRY_RG="${FOUNDRY_RG:-$RG}"
SEARCH_SERVICIO="${SEARCH_SERVICIO:-kiosco-g19-search}"
SEARCH_RG="${SEARCH_RG:-$RG}"
ROTAR_API_KEY="${ROTAR_API_KEY:-false}"
SOBRESCRIBIR="${SOBRESCRIBIR:-false}"   # true = reemplaza secretos que ya existen

preparar_az
az keyvault show -n "$KV_NOMBRE" -o none 2>/dev/null || error "no existe el Key Vault $KV_NOMBRE (corre desplegar_azure.sh)"

# cargar <nombre-secreto> <variable-entorno> <comando-azure|""> <descripción>
cargar() {
  local nombre="$1" variable="$2" comando="$3" descripcion="$4" valor=""
  if secreto_existe "$nombre" && [[ "$SOBRESCRIBIR" != "true" ]]; then
    info "$nombre ya existe (SOBRESCRIBIR=true para reemplazarlo)"
    return 0
  fi
  if [[ -n "${!variable:-}" ]]; then
    valor="${!variable}"
  elif [[ -n "$comando" ]]; then
    valor="$(eval "$comando" | tr -d '\r\n' || true)"
  elif [[ -t 0 ]]; then
    read -r -s -p "    Pega $descripcion ($nombre) y Enter (vacío = saltar): " valor
    echo
  fi
  if [[ -z "$valor" ]]; then
    aviso "$nombre sin valor: se salta"
    return 0
  fi
  printf '%s' "$valor" | guardar_secreto "$nombre"
  valor=""
}

paso "Secretos de los agentes en $KV_NOMBRE"

cmd_openai=""
if [[ -n "$FOUNDRY_RECURSO" && -n "$FOUNDRY_RG" ]]; then
  cmd_openai="az cognitiveservices account keys list -n \"$FOUNDRY_RECURSO\" -g \"$FOUNDRY_RG\" --query key1 -o tsv"
fi
cargar azure-openai-api-key AZURE_OPENAI_API_KEY "$cmd_openai" "la key de Foundry (gpt-5.4-mini)"

cmd_search=""
if [[ -n "$SEARCH_RG" ]]; then
  # La query key alcanza para consultar las knowledge bases (probado por Max el 9 nov)
  cmd_search="az search query-key list --service-name \"$SEARCH_SERVICIO\" -g \"$SEARCH_RG\" --query '[0].key' -o tsv"
fi
cargar foundry-search-api-key FOUNDRY_SEARCH_API_KEY "$cmd_search" "la query key de Azure AI Search"

cargar gemini-api-key GEMINI_API_KEY "" "la key de Gemini que te pasó Max"

if [[ "$ROTAR_API_KEY" == "true" ]]; then
  paso "Rotación de $SECRETO_API_KEY"
  aleatorio_hex 32 | guardar_secreto "$SECRETO_API_KEY"
  # La API lee la key al arrancar: se reinicia la revisión activa para que tome la nueva
  revision="$(azv containerapp show -g "$RG" -n "$CA_NOMBRE" --query properties.latestRevisionName -o tsv 2>/dev/null || true)"
  if [[ -n "$revision" ]]; then
    az containerapp revision restart -g "$RG" -n "$CA_NOMBRE" --revision "$revision" -o none
    info "revisión $revision reiniciada"
  fi
  aviso "Avisa a Max: Cloud Run debe reiniciarse (nueva revisión) para leer la key nueva desde Key Vault."
fi

paso "Secretos presentes en $KV_NOMBRE (solo nombres)"
az keyvault secret list --vault-name "$KV_NOMBRE" --query "[].name" -o tsv | tr -d '\r' | sed 's/^/    /'
