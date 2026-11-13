#!/usr/bin/env bash
# =============================================================================================
# Quita la IP de administración (la de quien desplegó) de los 3 controles de acceso, para que
# solo queden Cloud Run (y el colegio, si se configuró):
#   - restricción de IP del ingress de la API
#   - firewall de Key Vault
#   - regla Permitir-HTTPS-clientes del NSG de snet-api
# Correr al terminar las pruebas y capturas. Para volver a entrar: bash desplegar_azure.sh
# Uso:  bash cerrar_acceso_admin.sh
# =============================================================================================
set -euo pipefail

DIR_INFRA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=variables.sh
source "$DIR_INFRA/variables.sh"
preparar_az

# IP de la regla "admin" del ingress (la que puso desplegar_azure.sh)
ip_regla() {
  azv containerapp ingress access-restriction list -g "$RG" -n "$CA_NOMBRE" \
    --query "[?name=='$1'].ipAddressRange | [0]" -o tsv 2>/dev/null | sed 's#/32$##'
}
IP_ADMIN_ACTUAL="$(ip_regla admin)"
IP_CR="$(ip_regla cloud-run)"
IP_COL="$(ip_regla colegio)"
[[ -n "$IP_ADMIN_ACTUAL" ]] || { info "no hay regla 'admin' en el ingress: nada que cerrar"; exit 0; }
[[ -n "$IP_CR" ]] || error "no hay IP de Cloud Run configurada: si cierras el admin, nadie podrá usar la API. Despliega primero con IP_SALIDA_CLOUD_RUN."

paso "Quitando $IP_ADMIN_ACTUAL"
az containerapp ingress access-restriction remove -g "$RG" -n "$CA_NOMBRE" --rule-name admin -o none
info "ingress: regla admin eliminada"

az keyvault network-rule remove -g "$RG" -n "$KV_NOMBRE" --ip-address "$IP_ADMIN_ACTUAL" -o none 2>/dev/null \
  || az keyvault network-rule remove -g "$RG" -n "$KV_NOMBRE" --ip-address "$IP_ADMIN_ACTUAL/32" -o none
info "Key Vault: IP eliminada del firewall"

origenes=("$IP_CR")
if [[ -n "$IP_COL" ]]; then origenes+=("$IP_COL"); fi
az network nsg rule update -g "$RG" --nsg-name "$NSG_API" -n Permitir-HTTPS-clientes \
  --source-address-prefixes "${origenes[@]}" -o none
info "NSG $NSG_API: Permitir-HTTPS-clientes queda con ${origenes[*]}"

paso "Listo: solo Cloud Run${IP_COL:+ y el colegio} llegan a la API y a Key Vault"
