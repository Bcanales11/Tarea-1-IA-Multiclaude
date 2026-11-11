#!/usr/bin/env bash
# =============================================================================================
# Despliegue Azure del Kiosco Escolar Saludable (Grupo 19, TICS867 Magíster)
#
# Crea, en este orden:
#   1. Grupo de recursos
#   2. NSG (uno por subred) con reglas inbound/outbound explícitas
#   3. VNet 10.19.0.0/16 con 3 subredes: snet-api, snet-db, snet-pe
#   4. Log Analytics (logs de la API)
#   5. Key Vault (RBAC, firewall: solo IP de Cloud Run + admin) + private endpoint + DNS privada
#   6. Secreto registro-api-key (aleatorio, no se imprime)
#   7. PostgreSQL Flexible Server B1ms con acceso privado (sin IP pública) + secreto con su URL
#   8. Azure Container Registry Basic + imagen de la API (az acr build)
#   9. Identidad administrada de la API con permisos mínimos (AcrPull + 2 secretos)
#  10. Entorno de Container Apps en la VNet (workload profiles) + la API con ingress restringido
#
# Uso (desde proyecto2/infra, con `az login` hecho):
#   export IP_SALIDA_CLOUD_RUN=34.x.x.x     # la entrega Max (Cloud NAT)
#   bash desplegar_azure.sh
#
# Es idempotente en lo posible: si un recurso ya existe, lo deja y sigue. Correrlo de nuevo
# reconstruye la imagen, publica una revisión nueva y actualiza las reglas de IP.
# Ningún secreto se imprime ni se escribe en disco fuera de un archivo temporal que se borra.
# =============================================================================================
set -euo pipefail

DIR_INFRA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIR_API="$(cd "$DIR_INFRA/../api_registro" && pwd)"
# shellcheck source=variables.sh
source "$DIR_INFRA/variables.sh"
read -r -a TAGS <<< "$ETIQUETAS"

# ---------------------------------------------------------------------------------------------
paso "0. Comprobaciones previas"
# ---------------------------------------------------------------------------------------------
preparar_az
validar_ip "$IP_SALIDA_CLOUD_RUN"
validar_ip "$IP_COLEGIO"
if [[ -z "$IP_ADMIN" ]]; then
  IP_ADMIN="$(detectar_ip_publica | tr -d '\r\n' || true)"
  [[ -n "$IP_ADMIN" ]] || error "no se pudo detectar tu IP pública; defínela con export IP_ADMIN=..."
fi
validar_ip "$IP_ADMIN"
info "IP de administración (tu IP): $IP_ADMIN"
if [[ -z "$IP_SALIDA_CLOUD_RUN" ]]; then
  aviso "IP_SALIDA_CLOUD_RUN vacía: la API y Key Vault solo aceptarán tu IP por ahora."
  aviso "Cuando Max entregue la IP de Cloud NAT, vuelve a correr este script con ella."
fi

# IPs que pueden llegar a la API y a Key Vault (sin vacíos)
IPS_PERMITIDAS=()
for ip in "$IP_SALIDA_CLOUD_RUN" "$IP_COLEGIO" "$IP_ADMIN"; do
  if [[ -n "$ip" ]]; then IPS_PERMITIDAS+=("$ip"); fi
done

info "Extensión containerapp de az"
az extension add --name containerapp --upgrade --only-show-errors -o none

info "Proveedores de recursos (la primera vez puede tardar unos minutos)"
for proveedor in Microsoft.App Microsoft.OperationalInsights Microsoft.ContainerRegistry \
                 Microsoft.DBforPostgreSQL Microsoft.KeyVault Microsoft.Network Microsoft.ManagedIdentity; do
  estado="$(azv provider show --namespace "$proveedor" --query registrationState -o tsv 2>/dev/null || echo NotRegistered)"
  if [[ "$estado" != "Registered" ]]; then
    info "registrando $proveedor"
    az provider register --namespace "$proveedor" --wait -o none
  fi
done

YO_ID="$(azv ad signed-in-user show --query id -o tsv 2>/dev/null || true)"
[[ -n "$YO_ID" ]] || error "no se pudo leer tu usuario de Entra ID (az ad signed-in-user show)"
SUB_ID="$(azv account show --query id -o tsv)"

# ---------------------------------------------------------------------------------------------
paso "1. Grupo de recursos $RG ($UBICACION)"
# ---------------------------------------------------------------------------------------------
# Si el grupo ya existe (rg-kiosco-g19, con Foundry y AI Search) no se toca: ni etiquetas ni región.
if az group show -n "$RG" -o none 2>/dev/null; then
  info "el grupo ya existe; se agregan los recursos nuevos sin modificar los que hay"
else
  az group create --name "$RG" --location "$UBICACION" --tags "${TAGS[@]}" -o none
fi
RG_ID="/subscriptions/$SUB_ID/resourceGroups/$RG"

# ---------------------------------------------------------------------------------------------
paso "2. NSG con reglas explícitas (requisito Magíster)"
# ---------------------------------------------------------------------------------------------
# regla <nsg> <nombre> <prioridad> <Inbound|Outbound> <Allow|Deny> <Tcp|Udp|*> "<origenes>" "<destinos>" "<puertos destino>" "<motivo>"
# Origen/destino pueden ser prefijos (varios separados por espacio) o UNA etiqueta de servicio.
regla() {
  local nsg="$1" nombre="$2" prioridad="$3" direccion="$4" acceso="$5" protocolo="$6"
  local -a origenes destinos puertos
  read -r -a origenes <<< "$7"
  read -r -a destinos <<< "$8"
  read -r -a puertos <<< "$9"
  local motivo="${10}" accion=create
  if az network nsg rule show -g "$RG" --nsg-name "$nsg" -n "$nombre" -o none 2>/dev/null; then accion=update; fi
  az network nsg rule "$accion" -g "$RG" --nsg-name "$nsg" -n "$nombre" --priority "$prioridad" \
    --direction "$direccion" --access "$acceso" --protocol "$protocolo" \
    --source-address-prefixes "${origenes[@]}" --source-port-ranges '*' \
    --destination-address-prefixes "${destinos[@]}" --destination-port-ranges "${puertos[@]}" \
    --description "$motivo" -o none
  info "$nsg: $prioridad $direccion $acceso $nombre"
}

for nsg in "$NSG_API" "$NSG_DB" "$NSG_PE"; do
  az network nsg create -g "$RG" -n "$nsg" -l "$UBICACION" --tags "${TAGS[@]}" -o none
done

# --- snet-api (Container Apps) ---
regla "$NSG_API" Permitir-HTTPS-clientes        100 Inbound  Allow Tcp "${IPS_PERMITIDAS[*]}" "$SNET_API_PREFIJO" 443 \
  "Solo Cloud Run (IP fija de Cloud NAT), el colegio y el admin llegan a la API por HTTPS"
regla "$NSG_API" Permitir-AzureLoadBalancer     110 Inbound  Allow '*' AzureLoadBalancer "$SNET_API_PREFIJO" '*' \
  "Sondas de salud del balanceador de Container Apps"
regla "$NSG_API" Permitir-intra-subred-entrada  120 Inbound  Allow '*' "$SNET_API_PREFIJO" "$SNET_API_PREFIJO" '*' \
  "Componentes del entorno de Container Apps entre sí"
regla "$NSG_API" Denegar-todo-entrada          4096 Inbound  Deny  '*' '*' '*' '*' \
  "Todo lo demás se rechaza"
regla "$NSG_API" Permitir-PostgreSQL            100 Outbound Allow Tcp "$SNET_API_PREFIJO" "$SNET_DB_PREFIJO" 5432 \
  "La API escribe y lee en la BD"
regla "$NSG_API" Permitir-KeyVault-PE           110 Outbound Allow Tcp "$SNET_API_PREFIJO" "$SNET_PE_PREFIJO" 443 \
  "Lectura de secretos por el private endpoint de Key Vault"
regla "$NSG_API" Permitir-intra-subred-salida   120 Outbound Allow '*' "$SNET_API_PREFIJO" "$SNET_API_PREFIJO" '*' \
  "Componentes del entorno de Container Apps entre sí"
regla "$NSG_API" Permitir-EntraID               130 Outbound Allow Tcp "$SNET_API_PREFIJO" AzureActiveDirectory 443 \
  "Token de la identidad administrada"
regla "$NSG_API" Permitir-MCR                   140 Outbound Allow Tcp "$SNET_API_PREFIJO" MicrosoftContainerRegistry 443 \
  "Imágenes del sistema de Container Apps"
regla "$NSG_API" Permitir-FrontDoor-MCR         150 Outbound Allow Tcp "$SNET_API_PREFIJO" AzureFrontDoor.FirstParty 443 \
  "Dependencia de MicrosoftContainerRegistry"
regla "$NSG_API" Permitir-ACR                   160 Outbound Allow Tcp "$SNET_API_PREFIJO" AzureContainerRegistry 443 \
  "Descarga de la imagen de la API desde el ACR"
regla "$NSG_API" Permitir-Storage-ACR           170 Outbound Allow Tcp "$SNET_API_PREFIJO" Storage 443 \
  "Capas de la imagen (el ACR las sirve desde Blob Storage)"
regla "$NSG_API" Permitir-AzureMonitor          180 Outbound Allow Tcp "$SNET_API_PREFIJO" AzureMonitor 443 \
  "Envío de logs a Log Analytics"
regla "$NSG_API" Permitir-DNS-Azure             190 Outbound Allow '*' "$SNET_API_PREFIJO" 168.63.129.16/32 53 \
  "Resolución DNS de Azure (zonas privadas de Key Vault y PostgreSQL)"

# --- snet-db (PostgreSQL) ---
regla "$NSG_DB" Permitir-PostgreSQL-desde-API   100 Inbound  Allow Tcp "$SNET_API_PREFIJO" "$SNET_DB_PREFIJO" 5432 \
  "La BD solo acepta 5432 desde la subred de la API"
regla "$NSG_DB" Permitir-intra-subred-entrada   110 Inbound  Allow '*' "$SNET_DB_PREFIJO" "$SNET_DB_PREFIJO" '*' \
  "Tráfico interno del servidor administrado"
regla "$NSG_DB" Denegar-todo-entrada           4096 Inbound  Deny  '*' '*' '*' '*' \
  "Todo lo demás se rechaza (incluido Internet)"
regla "$NSG_DB" Permitir-intra-subred-salida    100 Outbound Allow '*' "$SNET_DB_PREFIJO" "$SNET_DB_PREFIJO" '*' \
  "Tráfico interno del servidor administrado"
regla "$NSG_DB" Permitir-Storage-respaldos      110 Outbound Allow Tcp "$SNET_DB_PREFIJO" Storage 443 \
  "Respaldos y archivado de WAL del servicio administrado"

# --- snet-pe (private endpoint de Key Vault) ---
regla "$NSG_PE" Permitir-KeyVault-desde-API     100 Inbound  Allow Tcp "$SNET_API_PREFIJO" "$SNET_PE_PREFIJO" 443 \
  "Solo la API lee Key Vault por la red privada"
regla "$NSG_PE" Denegar-todo-entrada           4096 Inbound  Deny  '*' '*' '*' '*' \
  "Todo lo demás se rechaza"
regla "$NSG_PE" Denegar-todo-salida            4096 Outbound Deny  '*' '*' '*' '*' \
  "Un private endpoint no inicia conexiones (las respuestas pasan: el NSG tiene estado)"

if [[ "$NSG_SALIDA_ESTRICTA" == "true" ]]; then
  regla "$NSG_API" Denegar-salida-Internet     4000 Outbound Deny '*' '*' Internet '*' \
    "La API no navega a Internet: solo servicios de Azure listados arriba"
  regla "$NSG_DB"  Denegar-salida-Internet     4000 Outbound Deny '*' '*' Internet '*' \
    "La BD no sale a Internet"
else
  aviso "NSG_SALIDA_ESTRICTA=false: se quitan las reglas 'Denegar-salida-Internet' (plan B)"
  for nsg in "$NSG_API" "$NSG_DB"; do
    az network nsg rule delete -g "$RG" --nsg-name "$nsg" -n Denegar-salida-Internet -o none 2>/dev/null || true
  done
fi

# ---------------------------------------------------------------------------------------------
paso "3. VNet $VNET y subredes"
# ---------------------------------------------------------------------------------------------
if ! az network vnet show -g "$RG" -n "$VNET" -o none 2>/dev/null; then
  az network vnet create -g "$RG" -n "$VNET" -l "$UBICACION" --address-prefixes "$VNET_PREFIJO" \
    --tags "${TAGS[@]}" -o none
fi

# subred <nombre> <prefijo> <nsg> <delegación|""> [args extra...]
subred() {
  local nombre="$1" prefijo="$2" nsg="$3" delegacion="$4"; shift 4
  local -a extra=("$@")
  if [[ -n "$delegacion" ]]; then extra+=(--delegations "$delegacion"); fi
  if az network vnet subnet show -g "$RG" --vnet-name "$VNET" -n "$nombre" -o none 2>/dev/null; then
    az network vnet subnet update -g "$RG" --vnet-name "$VNET" -n "$nombre" \
      --network-security-group "$nsg" "${extra[@]}" -o none
  else
    az network vnet subnet create -g "$RG" --vnet-name "$VNET" -n "$nombre" \
      --address-prefixes "$prefijo" --network-security-group "$nsg" "${extra[@]}" -o none
  fi
  info "$nombre $prefijo -> $nsg ${delegacion:+(delegada a $delegacion)}"
}
subred "$SNET_API" "$SNET_API_PREFIJO" "$NSG_API" Microsoft.App/environments
subred "$SNET_DB"  "$SNET_DB_PREFIJO"  "$NSG_DB"  Microsoft.DBforPostgreSQL/flexibleServers
# En la subred del private endpoint hay que activar las políticas de red para que el NSG aplique
subred "$SNET_PE"  "$SNET_PE_PREFIJO"  "$NSG_PE"  "" --private-endpoint-network-policies Enabled

SNET_API_ID="$(azv network vnet subnet show -g "$RG" --vnet-name "$VNET" -n "$SNET_API" --query id -o tsv)"
VNET_ID="$(azv network vnet show -g "$RG" -n "$VNET" --query id -o tsv)"

# ---------------------------------------------------------------------------------------------
paso "4. Log Analytics $LOG_WS"
# ---------------------------------------------------------------------------------------------
if ! az monitor log-analytics workspace show -g "$RG" -n "$LOG_WS" -o none 2>/dev/null; then
  az monitor log-analytics workspace create -g "$RG" -n "$LOG_WS" -l "$UBICACION" \
    --retention-time 30 --tags "${TAGS[@]}" -o none
fi
LOG_WS_CLIENTE="$(azv monitor log-analytics workspace show -g "$RG" -n "$LOG_WS" --query customerId -o tsv)"

# ---------------------------------------------------------------------------------------------
paso "5. Key Vault $KV_NOMBRE (RBAC, firewall y private endpoint)"
# ---------------------------------------------------------------------------------------------
if ! az keyvault show -g "$RG" -n "$KV_NOMBRE" -o none 2>/dev/null; then
  if az keyvault show-deleted -n "$KV_NOMBRE" -o none 2>/dev/null; then
    error "existe un Key Vault '$KV_NOMBRE' eliminado (soft delete). Recupéralo con 'az keyvault recover -n $KV_NOMBRE' o elimínalo con 'az keyvault purge -n $KV_NOMBRE'"
  fi
  # Acceso público "habilitado" pero con acción por defecto Deny: solo entran las IPs de la lista
  # (Cloud Run y admin) y la red privada. Retención mínima de borrado (7 días) para poder recrearlo.
  az keyvault create -g "$RG" -n "$KV_NOMBRE" -l "$UBICACION" --sku standard \
    --enable-rbac-authorization true --retention-days 7 \
    --public-network-access Enabled --default-action Deny --bypass AzureServices \
    --tags "${TAGS[@]}" -o none \
    || error "no se pudo crear el Key Vault (¿nombre ya usado en Azure? prueba export KV_NOMBRE=kv-kiosco-g19-<algo>)"
fi
KV_ID="$(azv keyvault show -g "$RG" -n "$KV_NOMBRE" --query id -o tsv)"
KV_URI="$(azv keyvault show -g "$RG" -n "$KV_NOMBRE" --query properties.vaultUri -o tsv)"   # termina en /
az keyvault update -g "$RG" -n "$KV_NOMBRE" --default-action Deny --bypass AzureServices \
  --public-network-access Enabled -o none

info "Firewall de Key Vault: solo ${IPS_PERMITIDAS[*]} (Key Vault no admite /32: va la IP sola)"
for ip in "${IPS_PERMITIDAS[@]}"; do
  ya="$(azv keyvault show -n "$KV_NOMBRE" -o tsv \
        --query "length(properties.networkAcls.ipRules[?value=='$ip' || value=='$ip/32'] || \`[]\`)" 2>/dev/null || echo 0)"
  if [[ "$ya" == "0" || -z "$ya" ]]; then
    az keyvault network-rule add -g "$RG" -n "$KV_NOMBRE" --ip-address "$ip" -o none
  fi
done

info "Rol 'Key Vault Secrets Officer' para ti (cargar secretos)"
asignar_rol "$YO_ID" User "Key Vault Secrets Officer" "$KV_ID"

info "Private endpoint + zona DNS privada $ZONA_DNS_KV"
if ! az network private-endpoint show -g "$RG" -n "$PE_KV" -o none 2>/dev/null; then
  az network private-endpoint create -g "$RG" -n "$PE_KV" -l "$UBICACION" \
    --vnet-name "$VNET" --subnet "$SNET_PE" --private-connection-resource-id "$KV_ID" \
    --group-id vault --connection-name "${PE_KV}-conexion" --tags "${TAGS[@]}" -o none
fi
if ! az network private-dns zone show -g "$RG" -n "$ZONA_DNS_KV" -o none 2>/dev/null; then
  az network private-dns zone create -g "$RG" -n "$ZONA_DNS_KV" -o none
fi
if ! az network private-dns link vnet show -g "$RG" --zone-name "$ZONA_DNS_KV" -n "enlace-$VNET" -o none 2>/dev/null; then
  az network private-dns link vnet create -g "$RG" --zone-name "$ZONA_DNS_KV" -n "enlace-$VNET" \
    --virtual-network "$VNET_ID" --registration-enabled false -o none
fi
if ! az network private-endpoint dns-zone-group show -g "$RG" --endpoint-name "$PE_KV" -n kv-zona -o none 2>/dev/null; then
  az network private-endpoint dns-zone-group create -g "$RG" --endpoint-name "$PE_KV" -n kv-zona \
    --private-dns-zone "$ZONA_DNS_KV" --zone-name vault -o none
fi

# ---------------------------------------------------------------------------------------------
paso "6. Secreto $SECRETO_API_KEY (aleatorio, no se muestra)"
# ---------------------------------------------------------------------------------------------
# La primera vez el rol recién asignado puede tardar unos minutos: guardar_secreto reintenta.
if secreto_existe "$SECRETO_API_KEY"; then
  info "ya existe; no se cambia (para rotarla: ROTAR_API_KEY=true bash cargar_secretos.sh)"
else
  aleatorio_hex 32 | guardar_secreto "$SECRETO_API_KEY"
fi

# ---------------------------------------------------------------------------------------------
paso "7. PostgreSQL Flexible Server $PG_NOMBRE ($PG_SKU, acceso privado)"
# ---------------------------------------------------------------------------------------------
# La contraseña se genera aquí, va directo a Key Vault dentro de la URL de conexión y nunca se
# imprime (-o none: la salida normal de 'create' incluye la contraseña).
url_bd() {  # url_bd <clave> -> postgresql://...
  local fqdn
  fqdn="$(azv postgres flexible-server show -g "$RG" -n "$PG_NOMBRE" --query fullyQualifiedDomainName -o tsv)"
  printf 'postgresql://%s:%s@%s:5432/%s?sslmode=require' "$PG_ADMIN" "$1" "$fqdn" "$PG_BD"
}
nueva_clave_bd() { printf 'Kg19-%s-Zx' "$(aleatorio_hex 20)"; }   # mayúsculas, minúsculas, dígitos y '-'

if ! az postgres flexible-server show -g "$RG" -n "$PG_NOMBRE" -o none 2>/dev/null; then
  info "creando el servidor (tarda 5-15 minutos)"
  PG_CLAVE="$(nueva_clave_bd)"
  az postgres flexible-server create -g "$RG" -n "$PG_NOMBRE" -l "$UBICACION" \
    --tier Burstable --sku-name "$PG_SKU" --storage-size "$PG_ALMACENAMIENTO_GB" --version "$PG_VERSION" \
    --admin-user "$PG_ADMIN" --admin-password "$PG_CLAVE" \
    --vnet "$VNET" --subnet "$SNET_DB" --private-dns-zone "$ZONA_DNS_PG" \
    --backup-retention 7 \
    --tags "${TAGS[@]}" --yes -o none \
    || error "no se pudo crear PostgreSQL (si la región está restringida para tu suscripción, ver README: plan B de región)"
  url_bd "$PG_CLAVE" | guardar_secreto "$SECRETO_DB_URL"
  unset PG_CLAVE
elif ! secreto_existe "$SECRETO_DB_URL"; then
  aviso "el servidor existe pero falta el secreto $SECRETO_DB_URL: se cambia la contraseña y se guarda"
  PG_CLAVE="$(nueva_clave_bd)"
  az postgres flexible-server update -g "$RG" -n "$PG_NOMBRE" --admin-password "$PG_CLAVE" -o none
  url_bd "$PG_CLAVE" | guardar_secreto "$SECRETO_DB_URL"
  unset PG_CLAVE
else
  info "ya existe, y su URL ya está en Key Vault"
fi
if ! az postgres flexible-server db show -g "$RG" -s "$PG_NOMBRE" -d "$PG_BD" -o none 2>/dev/null; then
  az postgres flexible-server db create -g "$RG" -s "$PG_NOMBRE" -d "$PG_BD" -o none
fi

# ---------------------------------------------------------------------------------------------
paso "8. Container Registry $ACR_NOMBRE (Basic) e imagen $IMAGEN:$ETIQUETA_IMAGEN"
# ---------------------------------------------------------------------------------------------
if ! az acr show -g "$RG" -n "$ACR_NOMBRE" -o none 2>/dev/null; then
  az acr create -g "$RG" -n "$ACR_NOMBRE" -l "$UBICACION" --sku Basic --admin-enabled false \
    --tags "${TAGS[@]}" -o none \
    || error "no se pudo crear el ACR (¿nombre usado? prueba export ACR_NOMBRE=acrkioscog19<algo>)"
fi
ACR_ID="$(azv acr show -g "$RG" -n "$ACR_NOMBRE" --query id -o tsv)"
ACR_SERVIDOR="$(azv acr show -g "$RG" -n "$ACR_NOMBRE" --query loginServer -o tsv)"
IMAGEN_COMPLETA="$ACR_SERVIDOR/$IMAGEN:$ETIQUETA_IMAGEN"

if [[ "$USAR_DOCKER_LOCAL" == "true" ]]; then
  info "construyendo con Docker local (plan B)"
  az acr login -n "$ACR_NOMBRE"
  docker build -t "$IMAGEN_COMPLETA" "$(ruta_nativa "$DIR_API")"
  docker push "$IMAGEN_COMPLETA"
else
  info "construyendo en Azure con az acr build (sube solo lo que no excluye .dockerignore)"
  az acr build -r "$ACR_NOMBRE" -t "$IMAGEN:$ETIQUETA_IMAGEN" "$(ruta_nativa "$DIR_API")" \
    || error "az acr build falló. Si dice que ACR Tasks no está disponible en tu suscripción: USAR_DOCKER_LOCAL=true bash desplegar_azure.sh"
fi

# ---------------------------------------------------------------------------------------------
paso "9. Identidad administrada $IDENTIDAD (permisos mínimos)"
# ---------------------------------------------------------------------------------------------
if ! az identity show -g "$RG" -n "$IDENTIDAD" -o none 2>/dev/null; then
  az identity create -g "$RG" -n "$IDENTIDAD" -l "$UBICACION" --tags "${TAGS[@]}" -o none
fi
ID_RECURSO="$(azv identity show -g "$RG" -n "$IDENTIDAD" --query id -o tsv)"
ID_PRINCIPAL="$(azv identity show -g "$RG" -n "$IDENTIDAD" --query principalId -o tsv)"
asignar_rol "$ID_PRINCIPAL" ServicePrincipal AcrPull "$ACR_ID"
# Solo los 2 secretos que usa la API (no puede leer las claves de Foundry ni de Gemini)
asignar_rol "$ID_PRINCIPAL" ServicePrincipal "Key Vault Secrets User" "$KV_ID/secrets/$SECRETO_API_KEY"
asignar_rol "$ID_PRINCIPAL" ServicePrincipal "Key Vault Secrets User" "$KV_ID/secrets/$SECRETO_DB_URL"

# ---------------------------------------------------------------------------------------------
paso "10. Container Apps: entorno $CAE_NOMBRE en $SNET_API y API $CA_NOMBRE"
# ---------------------------------------------------------------------------------------------
if ! az containerapp env show -g "$RG" -n "$CAE_NOMBRE" -o none 2>/dev/null; then
  info "creando el entorno (tarda 5-10 minutos)"
  LOG_WS_CLAVE="$(azv monitor log-analytics workspace get-shared-keys -g "$RG" -n "$LOG_WS" --query primarySharedKey -o tsv)"
  az containerapp env create -g "$RG" -n "$CAE_NOMBRE" -l "$UBICACION" \
    --enable-workload-profiles --infrastructure-subnet-resource-id "$SNET_API_ID" --internal-only false \
    --logs-destination log-analytics --logs-workspace-id "$LOG_WS_CLIENTE" --logs-workspace-key "$LOG_WS_CLAVE" \
    --tags "${TAGS[@]}" -o none \
    || error "no se pudo crear el entorno. Si el error menciona red o NSG: NSG_SALIDA_ESTRICTA=false bash desplegar_azure.sh"
  unset LOG_WS_CLAVE
fi

desplegar_app() {
  if az containerapp show -g "$RG" -n "$CA_NOMBRE" -o none 2>/dev/null; then
    az containerapp update -g "$RG" -n "$CA_NOMBRE" --image "$IMAGEN_COMPLETA" \
      --min-replicas "$MIN_REPLICAS" --max-replicas "$MAX_REPLICAS" -o none
  else
    # Los secretos son referencias a Key Vault: el valor nunca pasa por este script.
    az containerapp create -g "$RG" -n "$CA_NOMBRE" --environment "$CAE_NOMBRE" \
      --workload-profile-name Consumption \
      --image "$IMAGEN_COMPLETA" --registry-server "$ACR_SERVIDOR" --registry-identity "$ID_RECURSO" \
      --user-assigned "$ID_RECURSO" \
      --secrets "api-key=keyvaultref:${KV_URI}secrets/$SECRETO_API_KEY,identityref:$ID_RECURSO" \
                "database-url=keyvaultref:${KV_URI}secrets/$SECRETO_DB_URL,identityref:$ID_RECURSO" \
      --env-vars "REGISTRO_API_KEY=secretref:api-key" "DATABASE_URL=secretref:database-url" \
                 "ZONA_HORARIA=America/Santiago" "NIVEL_LOG=INFO" \
      --ingress external --target-port 8000 --transport auto \
      --cpu 0.25 --memory 0.5Gi --min-replicas "$MIN_REPLICAS" --max-replicas "$MAX_REPLICAS" \
      --scale-rule-name http-concurrencia --scale-rule-type http --scale-rule-http-concurrency 20 \
      --tags "${TAGS[@]}" -o none
  fi
}
# Reintenta porque los permisos de la identidad sobre Key Vault y el ACR tardan en propagarse
reintentar 5 60 desplegar_app || error "no se pudo crear/actualizar la app (revisa: az containerapp logs show -g $RG -n $CA_NOMBRE --type system)"

info "Ingress: solo las IPs permitidas (con una regla Allow, todo lo demás queda denegado)"
nombres_regla=(cloud-run colegio admin)
ips_regla=("$IP_SALIDA_CLOUD_RUN" "$IP_COLEGIO" "$IP_ADMIN")
for i in 0 1 2; do
  [[ -n "${ips_regla[$i]}" ]] || continue
  az containerapp ingress access-restriction set -g "$RG" -n "$CA_NOMBRE" \
    --rule-name "${nombres_regla[$i]}" --ip-address "${ips_regla[$i]}/32" --action Allow \
    --description "Acceso ${nombres_regla[$i]}" -o none
  info "permitido ${nombres_regla[$i]}: ${ips_regla[$i]}"
done

API_FQDN="$(azv containerapp show -g "$RG" -n "$CA_NOMBRE" --query properties.configuration.ingress.fqdn -o tsv)"

# ---------------------------------------------------------------------------------------------
paso "Listo"
# ---------------------------------------------------------------------------------------------
cat <<FIN

  Valores NO secretos para Max (por el grupo):
    REGISTRO_API_URL = https://$API_FQDN
    KEY_VAULT_URL    = ${KV_URI%/}
    AZURE_TENANT_ID  = $(azv account show --query tenantId -o tsv)
    (AZURE_CLIENT_ID lo entrega federacion_gcp.sh)

  Siguientes pasos:
    1. bash verificar.sh            # pruebas de la API desplegada (sacar capturas)
    2. bash cargar_secretos.sh      # claves de Foundry, AI Search y Gemini
    3. GCP_SA_UNIQUE_ID=... bash federacion_gcp.sh
    4. Cuando todo funcione: bash cerrar_acceso_admin.sh   (quita tu IP de los firewalls)

  Secretos (registro-api-key, registro-database-url): solo en Key Vault. No los copies al chat.
FIN
