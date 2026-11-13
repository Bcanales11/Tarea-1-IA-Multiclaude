#!/usr/bin/env bash
# =============================================================================================
# IP de salida fija para Cloud Run (kiosco-agentes) con Direct VPC egress + Cloud NAT.
#
# Para qué: Key Vault y la API de registro de Azure solo aceptan una IP conocida. Cloud Run sale a
# internet con IPs variables de Google; con esto todo su tráfico de salida pasa por una IP
# estática reservada, que Benjamín agrega a los firewalls de Azure.
#
#   Cloud Run ──(Direct VPC egress, all-traffic)──▶ subred-kiosco-run (vpc-kiosco)
#             ──▶ Cloud Router + Cloud NAT (IP estática ip-salida-kiosco) ──▶ Azure
#
# Por qué Direct VPC egress y no un conector Serverless VPC Access: el conector son VMs e2-micro
# encendidas todo el mes (mínimo 2 instancias, ≈ US$12/mes) y además limita el rendimiento.
# Direct VPC egress no tiene costo propio: Cloud Run toma IPs de la subred directamente.
#
# NO lo corre Claude. Lo corre Max, con su cuenta, desde Git Bash:
#   cd proyecto2/agentes/infra_gcp
#   export GCLOUD="/d/Google Cloud CLI/google-cloud-sdk/bin/gcloud.cmd"   # si gcloud no está en el PATH
#   bash ip_salida_fija.sh
#
# Es idempotente: si un recurso ya existe, lo salta. Crea una revisión nueva del servicio (no cambia
# imagen, variables ni secretos). Costo estimado: ≈ US$5-6/mes (ver README.md de esta carpeta).
# Volver atrás (el servicio vuelve a salir con IP variable):
#   gcloud run services update kiosco-agentes --region southamerica-west1 --clear-network
# =============================================================================================
set -euo pipefail

GCLOUD="${GCLOUD:-gcloud}"
PROYECTO="${PROYECTO:-kiosco-g19-agentes}"
REGION="${REGION:-southamerica-west1}"
SERVICIO="${SERVICIO:-kiosco-agentes}"
g() { "$GCLOUD" "$@" --project "$PROYECTO"; }   # sin tocar el proyecto por defecto de gcloud
VPC="vpc-kiosco"
SUBRED="subred-kiosco-run"
# Direct VPC egress usa ~2 IPs por instancia de Cloud Run durante los cambios de revisión.
# Google pide al menos /26; /24 (256 IPs) da margen para ~100 instancias y no cuesta nada.
RANGO_SUBRED="10.10.0.0/24"
ROUTER="router-kiosco"
NAT="nat-kiosco"
IP_NOMBRE="ip-salida-kiosco"

existe() { "$@" >/dev/null 2>&1; }

echo "== 0. API de Compute Engine (hoy no está habilitada en $PROYECTO)"
g services enable compute.googleapis.com

echo "== 1. Red VPC $VPC (modo custom: solo las subredes que se creen a mano)"
existe g compute networks describe "$VPC" \
  || g compute networks create "$VPC" --subnet-mode=custom \
       --description="Salida de Cloud Run (kiosco-agentes) por Cloud NAT con IP fija"

echo "== 2. Subred $SUBRED en $REGION para Direct VPC egress"
# --enable-private-ip-google-access: las llamadas a APIs de Google (Gemini, logging) van por la red
# interna de Google y no consumen NAT.
existe g compute networks subnets describe "$SUBRED" --region "$REGION" \
  || g compute networks subnets create "$SUBRED" --network "$VPC" --region "$REGION" \
       --range "$RANGO_SUBRED" --enable-private-ip-google-access

echo "== 3. IP externa estática $IP_NOMBRE (regional, la que ve Azure)"
existe g compute addresses describe "$IP_NOMBRE" --region "$REGION" \
  || g compute addresses create "$IP_NOMBRE" --region "$REGION" \
       --description="IP de salida fija de Cloud Run hacia Azure (Key Vault, API de registro)"

echo "== 4. Cloud Router $ROUTER"
existe g compute routers describe "$ROUTER" --region "$REGION" \
  || g compute routers create "$ROUTER" --network "$VPC" --region "$REGION"

echo "== 5. Cloud NAT $NAT con la IP estática (solo para la subred de Cloud Run)"
existe g compute routers nats describe "$NAT" --router "$ROUTER" --region "$REGION" \
  || g compute routers nats create "$NAT" --router "$ROUTER" --region "$REGION" \
       --nat-custom-subnet-ip-ranges "$SUBRED" \
       --nat-external-ip-pool "$IP_NOMBRE" \
       --enable-logging --log-filter ERRORS_ONLY

echo "== 6. Cloud Run $SERVICIO: todo el tráfico de salida por la VPC (y por lo tanto por el NAT)"
g run services update "$SERVICIO" --region "$REGION" \
  --network "$VPC" --subnet "$SUBRED" --vpc-egress all-traffic

IP_SALIDA="$(g compute addresses describe "$IP_NOMBRE" --region "$REGION" --format='value(address)' | tr -d '\r')"

echo
echo "== Verificación sugerida (después de que el servicio responda):"
echo "   - Logs del NAT sin errores:   gcloud logging read 'resource.type=\"nat_gateway\"' --limit 5"
echo "   - IPs del NAT:                gcloud compute routers get-nat-ip-info $ROUTER --region $REGION"
echo
echo "============================================================================================="
echo " IP de salida fija de Cloud Run (pasársela a Benjamín para Key Vault, API y NSG): $IP_SALIDA"
echo "============================================================================================="
