#!/usr/bin/env bash
# =============================================================================================
# Borra SOLO lo que creó desplegar_azure.sh, recurso por recurso, para no seguir pagando después
# de la entrega. NUNCA borra el grupo de recursos: en rg-kiosco-g19 también están Foundry
# (kiosco-g19-foundry, con el modelo y el proyecto) y AI Search (kiosco-g19-search, con las 2 KB),
# que no se tocan. La suscripción del curso es compartida: nada fuera de este grupo se toca.
# Pide confirmación. Opcionalmente purga el Key Vault (si no, su nombre queda reservado 7 días por
# el soft delete) y borra la app registration de la federación.
# Uso:  bash destruir.sh
# =============================================================================================
set -euo pipefail

DIR_INFRA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=variables.sh
source "$DIR_INFRA/variables.sh"
preparar_az

az group show -n "$RG" -o none 2>/dev/null || error "no existe el grupo $RG"

# Lista cerrada de lo que se borra (en orden: primero lo que depende de otros).
# tipo|nombre — solo recursos con estos nombres exactos, creados por desplegar_azure.sh.
RECURSOS=(
  "containerapp|$CA_NOMBRE"
  "containerapp-env|$CAE_NOMBRE"
  "postgres|$PG_NOMBRE"
  "private-endpoint|$PE_KV"
  "keyvault|$KV_NOMBRE"
  "acr|$ACR_NOMBRE"
  "identity|$IDENTIDAD"
  "log-ws|$LOG_WS"
  "dns|$ZONA_DNS_KV"
  "dns|$ZONA_DNS_PG"
  "vnet|$VNET"
  "nsg|$NSG_API"
  "nsg|$NSG_DB"
  "nsg|$NSG_PE"
)

paso "Se van a borrar SOLO estos recursos de $RG (Foundry y AI Search quedan intactos):"
for r in "${RECURSOS[@]}"; do echo "    - ${r%%|*}: ${r#*|}"; done
echo
paso "Quedan en $RG y NO se tocan:"
az resource list -g "$RG" -o tsv --query "[?type=='Microsoft.CognitiveServices/accounts' || type=='Microsoft.CognitiveServices/accounts/projects' || type=='Microsoft.Search/searchServices'].name" \
  | tr -d '\r' | sed 's/^/    - /'
echo
aviso "Esto borra la base de datos con todos los chequeos y no se puede deshacer."
read -r -p "    Escribe BORRAR para confirmar: " confirmacion
[[ "$confirmacion" == "BORRAR" ]] || error "no se confirmó; no se borró nada"

borrar() {  # borrar <descripción> <comando az...>: si no existe, sigue
  local desc="$1"; shift
  if "$@" -o none 2>/dev/null; then info "borrado: $desc"; else aviso "no estaba o no se pudo borrar: $desc"; fi
}
for r in "${RECURSOS[@]}"; do
  tipo="${r%%|*}"; nombre="${r#*|}"
  case "$tipo" in
    containerapp)     borrar "$nombre" az containerapp delete -g "$RG" -n "$nombre" --yes ;;
    containerapp-env) borrar "$nombre" az containerapp env delete -g "$RG" -n "$nombre" --yes ;;
    postgres)         borrar "$nombre" az postgres flexible-server delete -g "$RG" -n "$nombre" --yes ;;
    private-endpoint) borrar "$nombre" az network private-endpoint delete -g "$RG" -n "$nombre" ;;
    keyvault)         borrar "$nombre" az keyvault delete -g "$RG" -n "$nombre" ;;
    acr)              borrar "$nombre" az acr delete -g "$RG" -n "$nombre" --yes ;;
    identity)         borrar "$nombre" az identity delete -g "$RG" -n "$nombre" ;;
    log-ws)           borrar "$nombre" az monitor log-analytics workspace delete -g "$RG" -n "$nombre" --yes --force true ;;
    dns)
      for enlace in $(azv network private-dns link vnet list -g "$RG" -z "$nombre" --query "[].name" -o tsv 2>/dev/null); do
        borrar "enlace $enlace" az network private-dns link vnet delete -g "$RG" -z "$nombre" -n "$enlace" --yes
      done
      borrar "$nombre" az network private-dns zone delete -g "$RG" -n "$nombre" --yes ;;
    vnet)             borrar "$nombre" az network vnet delete -g "$RG" -n "$nombre" ;;
    nsg)              borrar "$nombre" az network nsg delete -g "$RG" -n "$nombre" ;;
  esac
done

read -r -p "    ¿Purgar el Key Vault $KV_NOMBRE para liberar el nombre ya? (s/N): " purgar
if [[ "$purgar" =~ ^[sS]$ ]]; then
  az keyvault purge -n "$KV_NOMBRE" -o none && info "Key Vault purgado"
fi

APP_ID="$(azv ad app list --display-name "$APP_FEDERADA" --query '[0].appId' -o tsv 2>/dev/null || true)"
if [[ -n "$APP_ID" ]]; then
  read -r -p "    ¿Borrar también la app registration $APP_FEDERADA (federación con Cloud Run)? (s/N): " borrar_app
  if [[ "$borrar_app" =~ ^[sS]$ ]]; then
    az ad app delete --id "$APP_ID" && info "app registration borrada"
  fi
fi
paso "Listo. Comprueba que Foundry y AI Search siguen ahí: az resource list -g $RG -o table"
