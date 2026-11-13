#!/usr/bin/env bash
# =============================================================================================
# Pruebas después del despliegue (sirven de evidencia para el informe: sacar captura de la salida).
#
#   1-8. API: /salud, 401 sin key y con key errónea, 201, 422 (APTO con sellos, sello inválido),
#        NO_APTO con sellos vacía, GET con kiosco_id y desde.
#   9-12. Red: PostgreSQL sin acceso público y no alcanzable desde Internet, firewall de Key Vault,
#        restricciones de IP del ingress y reglas de los NSG.
#
# La x-api-key se lee de Key Vault a una variable y a un archivo temporal (permiso 600) que se
# borra al terminar; nunca se imprime. Debe correrse desde la IP de administración (IP_ADMIN),
# porque la API y Key Vault rechazan cualquier otra.
# Uso:  bash verificar.sh
# =============================================================================================
set -euo pipefail

DIR_INFRA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=variables.sh
source "$DIR_INFRA/variables.sh"

KIOSCO_PRUEBA="verificacion-infra"
preparar_az

FQDN="$(azv containerapp show -g "$RG" -n "$CA_NOMBRE" --query properties.configuration.ingress.fqdn -o tsv)"
[[ -n "$FQDN" ]] || error "no se encontró la API $CA_NOMBRE en $RG"
URL="https://$FQDN"
info "API: $URL"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
chmod 700 "$TMP"
CUERPO="$TMP/cuerpo.json"
ok=0; fallos=0

# comprobar <descripción> <código esperado> <código obtenido>
comprobar() {
  if [[ "$3" == "$2" ]]; then
    printf '    \033[32mOK\033[0m   %-55s -> %s\n' "$1" "$3"; ok=$((ok + 1))
  else
    printf '    \033[31mFALLA\033[0m %-54s esperado %s, obtenido %s\n' "$1" "$2" "$3"; fallos=$((fallos + 1))
    if [[ -s "$CUERPO" ]]; then sed 's/^/           /' "$CUERPO" | head -c 600; echo; fi
  fi
}

# http <método> <ruta> [archivo-cabeceras|""] [json]  -> imprime el código HTTP; cuerpo en $CUERPO
http() {
  local metodo="$1" ruta="$2" cabeceras="${3:-}" datos="${4:-}"
  # curl de Windows no entiende las rutas /tmp/... de Git Bash: se le pasan rutas nativas
  local -a args=(-sS -o "$(ruta_nativa "$CUERPO")" -w '%{http_code}' --max-time 30 -X "$metodo")
  if [[ -n "$cabeceras" ]]; then args+=(-H "@$(ruta_nativa "$cabeceras")"); fi
  if [[ -n "$datos" ]]; then args+=(-H 'content-type: application/json' --data "$datos"); fi
  curl "${args[@]}" "$URL$ruta" || true   # si no conecta, -w ya imprime 000
}

# ---------------------------------------------------------------------------------------------
paso "1. /salud (sin autenticación; espera hasta 3 min por el arranque)"
# ---------------------------------------------------------------------------------------------
codigo="000"
for _ in $(seq 1 12); do
  codigo="$(http GET /salud)"
  [[ "$codigo" == "200" ]] && break
  sleep 15
done
comprobar "GET /salud responde y la BD está ok" 200 "$codigo"
if [[ -s "$CUERPO" ]]; then sed 's/^/           /' "$CUERPO"; echo; fi
if [[ "$codigo" == "403" ]]; then
  aviso "403: tu IP no está en la lista del ingress. ¿Cambió tu IP? Vuelve a correr desplegar_azure.sh"
fi

# ---------------------------------------------------------------------------------------------
paso "2. Autenticación"
# ---------------------------------------------------------------------------------------------
VALIDO='{"kiosco_id":"'"$KIOSCO_PRUEBA"'","producto":"Galletas X 120 g","sku":"612696","sellos":["AZUCARES","GRASAS_SATURADAS"],"veredicto":"NO_APTO","motivo":"Art. 110 bis: basta un sello ALTO EN","origen":"vision"}'
comprobar "POST /chequeos sin x-api-key -> 401" 401 "$(http POST /chequeos "" "$VALIDO")"
printf 'x-api-key: %s' "clave-incorrecta-de-prueba" > "$TMP/mala.txt"
comprobar "POST /chequeos con x-api-key errónea -> 401" 401 "$(http POST /chequeos "$TMP/mala.txt" "$VALIDO")"
comprobar "GET /chequeos sin x-api-key -> 401" 401 "$(http GET "/chequeos?kiosco_id=$KIOSCO_PRUEBA" "")"

# La key se lee de Key Vault y va directo a un archivo de cabeceras (no se imprime)
CABECERAS="$TMP/cabeceras.txt"
CLAVE="$(azv keyvault secret show --vault-name "$KV_NOMBRE" -n "$SECRETO_API_KEY" --query value -o tsv 2>/dev/null || true)"
( umask 077; printf 'x-api-key: %s' "$CLAVE" > "$CABECERAS" )
unset CLAVE
[[ "$(wc -c < "$CABECERAS")" -gt 20 ]] || error "no se pudo leer $SECRETO_API_KEY (¿tu IP está en el firewall de Key Vault?)"
info "x-api-key leída de Key Vault (no se muestra)"

# ---------------------------------------------------------------------------------------------
paso "3. Registro y validaciones (contrato §4.3)"
# ---------------------------------------------------------------------------------------------
comprobar "POST chequeo NO_APTO con 2 sellos -> 201" 201 "$(http POST /chequeos "$CABECERAS" "$VALIDO")"
if [[ -s "$CUERPO" ]]; then sed 's/^/           respuesta: /' "$CUERPO"; echo; fi
ID_CREADO="$(sed -n 's/.*"id":\([0-9]*\).*/\1/p' "$CUERPO")"

SIN_SELLOS='{"kiosco_id":"'"$KIOSCO_PRUEBA"'","producto":"Barra de cereal 25 g","sku":"","sellos":[],"veredicto":"NO_APTO","motivo":"Sello visto pero ilegible","origen":"vision"}'
comprobar "POST NO_APTO con sellos vacía -> 201" 201 "$(http POST /chequeos "$CABECERAS" "$SIN_SELLOS")"

APTO_CON_SELLOS='{"kiosco_id":"'"$KIOSCO_PRUEBA"'","producto":"Prueba APTO con sello","sku":"","sellos":["SODIO"],"veredicto":"APTO","motivo":"prueba","origen":"chat"}'
comprobar "POST APTO con sellos -> 422 (warning en logs)" 422 "$(http POST /chequeos "$CABECERAS" "$APTO_CON_SELLOS")"

SELLO_INVALIDO='{"kiosco_id":"'"$KIOSCO_PRUEBA"'","producto":"Prueba","sku":"","sellos":["AZUCAR"],"veredicto":"NO_APTO","motivo":"prueba","origen":"chat"}'
comprobar "POST sello inválido -> 422" 422 "$(http POST /chequeos "$CABECERAS" "$SELLO_INVALIDO")"

VEREDICTO_INVALIDO='{"kiosco_id":"'"$KIOSCO_PRUEBA"'","producto":"Prueba","sku":"","sellos":[],"veredicto":"QUIZAS","motivo":"prueba","origen":"chat"}'
comprobar "POST veredicto inválido -> 422" 422 "$(http POST /chequeos "$CABECERAS" "$VEREDICTO_INVALIDO")"

HOY="$(date +%Y-%m-%d)"   # la hora local de Windows es la de Chile (en Git Bash TZ=America/Santiago da GMT); en Cloud Shell: TZ=America/Santiago date
comprobar "GET /chequeos?kiosco_id=...&desde=$HOY -> 200" 200 \
  "$(http GET "/chequeos?kiosco_id=$KIOSCO_PRUEBA&desde=$HOY" "$CABECERAS")"
if [[ -n "$ID_CREADO" ]] && grep -q "\"id\":$ID_CREADO[,}]" "$CUERPO"; then
  comprobar "el chequeo id=$ID_CREADO aparece en la lista" ok ok
else
  comprobar "el chequeo creado aparece en la lista" ok no
fi
comprobar "GET /chequeos con desde inválido -> 422" 422 \
  "$(http GET "/chequeos?kiosco_id=$KIOSCO_PRUEBA&desde=ayer" "$CABECERAS")"

# ---------------------------------------------------------------------------------------------
paso "4. Red: PostgreSQL privado"
# ---------------------------------------------------------------------------------------------
PG_FQDN="$(azv postgres flexible-server show -g "$RG" -n "$PG_NOMBRE" --query fullyQualifiedDomainName -o tsv)"
acceso="$(azv postgres flexible-server show -g "$RG" -n "$PG_NOMBRE" --query network.publicNetworkAccess -o tsv)"
comprobar "PostgreSQL: acceso público" Disabled "$acceso"
if timeout 8 bash -c "exec 3<>/dev/tcp/$PG_FQDN/5432" 2>/dev/null; then
  comprobar "PostgreSQL NO alcanzable desde Internet (5432)" cerrado abierto
else
  comprobar "PostgreSQL NO alcanzable desde Internet (5432)" cerrado cerrado
fi

# ---------------------------------------------------------------------------------------------
paso "5. Red: Key Vault, ingress y NSG (captura para el informe)"
# ---------------------------------------------------------------------------------------------
comprobar "Key Vault: acción por defecto del firewall" Deny \
  "$(azv keyvault show -n "$KV_NOMBRE" --query properties.networkAcls.defaultAction -o tsv)"
info "IPs permitidas en Key Vault:"
az keyvault show -n "$KV_NOMBRE" --query "properties.networkAcls.ipRules[].value" -o tsv | tr -d '\r' | sed 's/^/      /'
info "Private endpoints de Key Vault:"
az keyvault show -n "$KV_NOMBRE" --query "properties.privateEndpointConnections[].{estado:privateLinkServiceConnectionState.status}" -o tsv | tr -d '\r' | sed 's/^/      /'
info "Restricciones de IP del ingress de la API:"
az containerapp ingress access-restriction list -g "$RG" -n "$CA_NOMBRE" -o table | tr -d '\r' | sed 's/^/      /'
for nsg in "$NSG_API" "$NSG_DB" "$NSG_PE"; do
  info "Reglas de $nsg:"
  az network nsg rule list -g "$RG" --nsg-name "$nsg" -o table \
    --query "sort_by(@, &priority)[].{Prioridad:priority, Direccion:direction, Accion:access, Nombre:name, Protocolo:protocol, Origen:sourceAddressPrefix || join(' ', sourceAddressPrefixes), Destino:destinationAddressPrefix || join(' ', destinationAddressPrefixes), Puertos:destinationPortRange || join(' ', destinationPortRanges)}" \
    | tr -d '\r' | sed 's/^/      /'
done

# ---------------------------------------------------------------------------------------------
paso "6. Logs (los rechazos 401/422 llegan a Log Analytics con 2-5 min de retraso)"
# ---------------------------------------------------------------------------------------------
LOG_WS_CLIENTE="$(azv monitor log-analytics workspace show -g "$RG" -n "$LOG_WS" --query customerId -o tsv)"
cat <<CONSULTA
    En el portal: $LOG_WS > Logs, o con:
    az monitor log-analytics query -w $LOG_WS_CLIENTE -o table --analytics-query \\
      "ContainerAppConsoleLogs_CL | where ContainerAppName_s == '$CA_NOMBRE' | where Log_s has 'rechazo_' | project TimeGenerated, Log_s | order by TimeGenerated desc | take 20"
CONSULTA

paso "Resultado: $ok OK, $fallos con falla"
[[ "$fallos" == "0" ]]
