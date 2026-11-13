# shellcheck shell=bash
# Variables comunes de la infraestructura Azure del Grupo 19 (las cargan todos los scripts).
# Cada una se puede sobrescribir antes de correr un script, por ejemplo:
#   export KV_NOMBRE=kv-kiosco-g19-b   # si el nombre ya está tomado en Azure
# Aquí NO van secretos: este archivo se sube al repositorio (público).

# --- Suscripción y ubicación ----------------------------------------------------------
SUSCRIPCION="${SUSCRIPCION:-}"                # vacío = la suscripción activa de `az account show`
# El mismo grupo del proyecto, donde ya están Foundry (kiosco-g19-foundry) y AI Search
# (kiosco-g19-search, con las 2 KB). Los recursos nuevos se agregan al lado sin modificarlos, y
# destruir.sh borra solo los nuestros, uno por uno, nunca el grupo. La suscripción del curso es
# compartida por ~80 grupos: nada se crea ni se borra fuera de este grupo.
RG="${RG:-rg-kiosco-g19}"
# En Windows la CLI de Azure falla al mostrar el log de `az acr build` (UnicodeEncodeError cp1252)
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
# Centro EE. UU.: la suscripción del curso restringe PostgreSQL en East US ("location is restricted")
# y en East US 2 / West US 3 ("SkuNotAvailable"); Central US y West US 2 sí lo permiten (probado el 10 nov).
# Foundry y AI Search siguen en East US; la red de la API y la BD no necesitan estar en la misma región.
UBICACION="${UBICACION:-centralus}"
ETIQUETAS="${ETIQUETAS:-proyecto=kiosco-saludable grupo=g19 ramo=TICS867}"

# --- Red (requisito Magíster: subredes y NSG) -----------------------------------------
VNET="${VNET:-vnet-kiosco-g19}"
VNET_PREFIJO="${VNET_PREFIJO:-10.19.0.0/16}"
SNET_API="${SNET_API:-snet-api}"              # Container Apps (delegada a Microsoft.App/environments)
SNET_API_PREFIJO="${SNET_API_PREFIJO:-10.19.0.0/27}"
SNET_DB="${SNET_DB:-snet-db}"                 # PostgreSQL Flexible (delegada)
SNET_DB_PREFIJO="${SNET_DB_PREFIJO:-10.19.1.0/28}"
SNET_PE="${SNET_PE:-snet-pe}"                 # private endpoint de Key Vault
SNET_PE_PREFIJO="${SNET_PE_PREFIJO:-10.19.2.0/27}"
NSG_API="${NSG_API:-nsg-snet-api}"
NSG_DB="${NSG_DB:-nsg-snet-db}"
NSG_PE="${NSG_PE:-nsg-snet-pe}"
# true = cada subred termina con "denegar salida a Internet". Si el entorno de Container Apps
# no logra aprovisionarse o la app no arranca, probar con false y avisar (ver README, plan B).
NSG_SALIDA_ESTRICTA="${NSG_SALIDA_ESTRICTA:-true}"

# --- IPs públicas permitidas (no son secretos, pero se pasan por variable, no se versionan) ---
# IP fija de salida de Cloud Run (Cloud NAT). La entrega Max. Formato: 34.x.x.x (sin /32)
IP_SALIDA_CLOUD_RUN="${IP_SALIDA_CLOUD_RUN:-}"
# IP pública del colegio (opcional, para probar desde el kiosco)
IP_COLEGIO="${IP_COLEGIO:-}"
# IP de quien despliega (Benjamín), para cargar secretos y correr verificar.sh.
# Vacío = se detecta sola. Se quita al final con: bash cerrar_acceso_admin.sh
IP_ADMIN="${IP_ADMIN:-}"

# --- Key Vault -------------------------------------------------------------------------------
KV_NOMBRE="${KV_NOMBRE:-kv-kiosco-g19}"       # único en todo Azure, 3-24 caracteres
PE_KV="${PE_KV:-pe-kv-kiosco-g19}"
ZONA_DNS_KV="privatelink.vaultcore.azure.net"

# --- Base de datos ----------------------------------------------------------------------------
PG_NOMBRE="${PG_NOMBRE:-psql-kiosco-g19}"     # único en todo Azure
PG_ADMIN="${PG_ADMIN:-kioscoadmin}"
PG_BD="${PG_BD:-registro}"
PG_VERSION="${PG_VERSION:-16}"
PG_SKU="${PG_SKU:-Standard_B1ms}"             # Burstable B1ms: 1 vCore, 2 GiB
PG_ALMACENAMIENTO_GB="${PG_ALMACENAMIENTO_GB:-32}"
ZONA_DNS_PG="${ZONA_DNS_PG:-privatelink.postgres.database.azure.com}"   # nombre estándar; Azure rechaza <servidor>.private.postgres...

# --- Contenedores ------------------------------------------------------------------------------
ACR_NOMBRE="${ACR_NOMBRE:-acrkioscog19}"      # único en todo Azure, solo letras y números
IMAGEN="${IMAGEN:-registro-api}"
ETIQUETA_IMAGEN="${ETIQUETA_IMAGEN:-$(date +%Y%m%d-%H%M)}"
LOG_WS="${LOG_WS:-log-kiosco-g19}"
CAE_NOMBRE="${CAE_NOMBRE:-cae-kiosco-g19}"    # entorno de Container Apps
CA_NOMBRE="${CA_NOMBRE:-ca-registro-api}"     # la API
IDENTIDAD="${IDENTIDAD:-id-registro-api}"     # identidad administrada de la API
MIN_REPLICAS="${MIN_REPLICAS:-1}"             # 1 = sin arranque en frío (el cliente espera 10 s); 0 = más barato
MAX_REPLICAS="${MAX_REPLICAS:-3}"
# true = construir la imagen con Docker local en vez de `az acr build` (si ACR Tasks está bloqueado)
USAR_DOCKER_LOCAL="${USAR_DOCKER_LOCAL:-false}"

# --- Secretos en Key Vault (nombres de INSTRUCCIONES_GRUPO.md §4.5 + los de la BD) -------------
SECRETO_API_KEY="registro-api-key"
SECRETO_DB_URL="registro-database-url"        # agregado al §4.5: URL completa de PostgreSQL
SECRETOS_AGENTES=("azure-openai-api-key" "foundry-search-api-key" "registro-api-key" "gemini-api-key")

# --- Federación con Google Cloud (Cloud Run de Max) --------------------------------------------
APP_FEDERADA="${APP_FEDERADA:-kiosco-agentes-gcp}"
GCP_PROYECTO="${GCP_PROYECTO:-kiosco-g19-agentes}"
GCP_SA_EMAIL="${GCP_SA_EMAIL:-kiosco-agentes-sa@kiosco-g19-agentes.iam.gserviceaccount.com}"
# ID numérico de la service account (21 dígitos). Lo entrega Max:
#   gcloud iam service-accounts describe <GCP_SA_EMAIL> --format='value(uniqueId)'
GCP_SA_UNIQUE_ID="${GCP_SA_UNIQUE_ID:-}"

# --- Utilidades comunes --------------------------------------------------------------------------
# Git Bash (Windows) convierte los argumentos que empiezan con "/" en rutas de Windows y rompe los
# IDs de recursos (/subscriptions/...). Esto lo desactiva; en Linux y Cloud Shell no tiene efecto.
export MSYS_NO_PATHCONV=1

# az en Windows termina las líneas con \r\n: azv captura un valor sin el \r final.
azv() { az "$@" | tr -d '\r'; }

# Ruta que entiende az: en Git Bash (Windows) az es un programa de Windows y no lee /d/... ni /tmp/...
ruta_nativa() {
  if command -v cygpath >/dev/null; then cygpath -w "$1"; else printf '%s' "$1"; fi
}

paso() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
aviso() { printf '\033[1;33m[aviso]\033[0m %s\n' "$*" >&2; }
error() { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

# Reintenta un comando (para esperar la propagación de roles RBAC, que tarda 1-5 min)
reintentar() {
  local intentos="$1"; shift
  local espera="$1"; shift
  local i
  for ((i = 1; i <= intentos; i++)); do
    if "$@"; then return 0; fi
    aviso "intento $i/$intentos falló; reintento en ${espera}s (puede ser la propagación de permisos)"
    sleep "$espera"
  done
  return 1
}

# Comprueba sesión de az y fija la suscripción
preparar_az() {
  command -v az >/dev/null || error "falta Azure CLI (az). Instálalo: https://aka.ms/azcli"
  az account show >/dev/null 2>&1 || error "no hay sesión: corre 'az login' primero"
  if [[ -n "$SUSCRIPCION" ]]; then az account set --subscription "$SUSCRIPCION"; fi
  info "Suscripción: $(azv account show --query name -o tsv) ($(azv account show --query id -o tsv))"
}

# Valida que una variable sea una IPv4 simple (sin máscara)
validar_ip() {
  [[ -z "$1" || "$1" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || error "IP inválida: '$1' (formato 34.1.2.3, sin /32)"
}

# Asigna un rol solo si no existe ya (idempotente). Uso: asignar_rol <objectId> <tipo> <rol> <scope>
# tipo = User | ServicePrincipal. Requiere ser Owner, User Access Administrator o
# Role Based Access Control Administrator en el grupo de recursos.
asignar_rol() {
  local objeto="$1" tipo="$2" rol="$3" alcance="$4" n
  n="$(azv role assignment list --assignee "$objeto" --role "$rol" --scope "$alcance" --query 'length(@)' -o tsv 2>/dev/null || echo 0)"
  if [[ "$n" != "0" && -n "$n" ]]; then
    info "rol '$rol' ya asignado en ${alcance##*/providers/}"
    return 0
  fi
  reintentar 6 20 az role assignment create --assignee-object-id "$objeto" --assignee-principal-type "$tipo" \
    --role "$rol" --scope "$alcance" -o none \
    || error "no se pudo asignar '$rol'. ¿Tienes rol Owner o User Access Administrator? (ver README, limitaciones)"
  info "rol '$rol' asignado en ${alcance##*/providers/}"
}

# Guarda un secreto en Key Vault leyendo el valor de stdin: nunca queda en la línea de comandos
# ni en el historial. Uso:  printf '%s' "$valor" | guardar_secreto nombre
guardar_secreto() {
  local nombre="$1" tmp
  tmp="$(mktemp)"
  chmod 600 "$tmp"
  cat > "$tmp"
  if [[ ! -s "$tmp" ]]; then rm -f "$tmp"; aviso "valor vacío para $nombre; no se guardó"; return 1; fi
  if reintentar 10 30 az keyvault secret set --vault-name "$KV_NOMBRE" --name "$nombre" \
      --file "$(ruta_nativa "$tmp")" --encoding utf-8 --content-type "text/plain" --query id -o none; then
    rm -f "$tmp"
    info "secreto guardado en Key Vault: $nombre (valor no mostrado)"
  else
    rm -f "$tmp"
    error "no se pudo guardar $nombre en Key Vault"
  fi
}

# 0 = existe, 1 = NO existe (SecretNotFound); cualquier otro error (firewall que tarda 1-2 min en aplicar
# la IP nueva, RBAC sin propagar) se reintenta y, si persiste, detiene el script. Antes un 403 se tomaba
# por "no existe" y se regeneraba la clave de la API y la contraseña de PostgreSQL (auditoría 11 nov, H2).
secreto_existe() {
  local i salida
  for ((i = 1; i <= 12; i++)); do
    if salida="$(az keyvault secret show --vault-name "$KV_NOMBRE" --name "$1" --query id -o tsv 2>&1)"; then return 0; fi
    if grep -qiE 'SecretNotFound|was not found' <<< "$salida"; then return 1; fi
    aviso "no pude leer $1 de Key Vault (intento $i/12; ¿firewall o rol sin propagar?); reintento en 20s"
    sleep 20
  done
  error "no se pudo comprobar si existe el secreto $1 (¿tu IP está en el firewall de Key Vault?)"
}

# Genera una cadena aleatoria hexadecimal de N bytes (sin openssl si no está)
aleatorio_hex() {
  local bytes="${1:-32}"
  if command -v openssl >/dev/null; then
    openssl rand -hex "$bytes"
  else
    head -c "$bytes" /dev/urandom | od -An -tx1 | tr -d ' \n'
  fi
}

# IP pública de quien corre el script
detectar_ip_publica() {
  curl -fsS --max-time 10 https://api.ipify.org || curl -fsS --max-time 10 https://ifconfig.me
}
