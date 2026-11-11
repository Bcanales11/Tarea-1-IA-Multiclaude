#!/usr/bin/env bash
# =============================================================================================
# Acceso de la app del kiosco (on-premise, app_kiosco/) al servicio de agentes en Cloud Run.
#
# Hoy el servicio es privado (--no-allow-unauthenticated, nadie tiene roles/run.invoker) y la app
# solo manda x-api-key, así que Google la rechaza con 403 antes de llegar a servidor.py.
# Dos opciones (detalle y recomendación en ../../app_kiosco/README.md, "Acceso a Cloud Run"):
#
#   a) RECOMENDADA. Privado + cuenta de servicio invocadora kiosco-app-invoker (roles/run.invoker
#      solo sobre este servicio). La app manda un ID token de Google + x-api-key.
#      Limitación: el equipo del colegio guarda un archivo de clave de esa cuenta de servicio.
#   b) Público (cualquiera llega al servicio) + x-api-key. Más simple, pero ojo: servidor.py
#      también expone las rutas estándar de ADK (/run, /run_sse, /apps/...) que NO piden
#      x-api-key. Con (b) cualquiera en internet podría usar los agentes y gastar tokens.
#      No usar (b) sin antes quitar o proteger esas rutas.
#
# NO lo corre Claude. Lo corre Max (Git Bash):
#   export GCLOUD="/d/Google Cloud CLI/google-cloud-sdk/bin/gcloud.cmd"   # si no está en el PATH
#   bash abrir_acceso_app.sh a      # o b
# =============================================================================================
set -euo pipefail

GCLOUD="${GCLOUD:-gcloud}"
PROYECTO="${PROYECTO:-kiosco-g19-agentes}"
REGION="${REGION:-southamerica-west1}"
SERVICIO="${SERVICIO:-kiosco-agentes}"
g() { "$GCLOUD" "$@" --project "$PROYECTO"; }

SA_APP="kiosco-app-invoker"
SA_APP_EMAIL="${SA_APP}@${PROYECTO}.iam.gserviceaccount.com"
# La clave queda FUERA del repo (en el equipo del kiosco). Nunca copiarla a proyecto2/.
ARCHIVO_CLAVE="${ARCHIVO_CLAVE:-$HOME/.kiosco/kiosco-app-invoker.json}"

URL="$(g run services describe "$SERVICIO" --region "$REGION" --format='value(status.url)' | tr -d '\r')"

case "${1:-}" in
  a)
    echo "== Opción a: privado + cuenta de servicio invocadora $SA_APP"
    g iam service-accounts describe "$SA_APP_EMAIL" >/dev/null 2>&1 \
      || g iam service-accounts create "$SA_APP" \
           --display-name "App del kiosco (invoca kiosco-agentes en Cloud Run)"

    # Solo puede invocar ESTE servicio (no es un rol de proyecto).
    g run services add-iam-policy-binding "$SERVICIO" --region "$REGION" \
      --member "serviceAccount:${SA_APP_EMAIL}" --role roles/run.invoker

    # Archivo de clave para el equipo del colegio. Es la limitación de esta opción: quien lo copie
    # puede invocar el servicio (igual necesita x-api-key). Rotarlo: crear otro y borrar el viejo
    # con  gcloud iam service-accounts keys list/delete --iam-account $SA_APP_EMAIL
    mkdir -p "$(dirname "$ARCHIVO_CLAVE")"
    if [[ -f "$ARCHIVO_CLAVE" ]]; then
      echo "Ya existe $ARCHIVO_CLAVE: no se crea otra clave."
    else
      g iam service-accounts keys create "$ARCHIVO_CLAVE" --iam-account "$SA_APP_EMAIL"
      chmod 600 "$ARCHIVO_CLAVE" 2>/dev/null || true
    fi

    cat <<EOF

Listo. En app_kiosco/.env del equipo del kiosco:
  AGENTES_URL=$URL
  AGENTES_AUDIENCIA_IAM=$URL
  GOOGLE_APPLICATION_CREDENTIALS=$ARCHIVO_CLAVE
  AGENTES_API_KEY=<la misma del secreto agentes-api-key>
Y en el venv de la app:  pip install google-auth
Prueba: sin token -> 403 (Google); con token y clave mala -> 401 (servidor.py); ambos bien -> 200.

Volver atrás:
  gcloud run services remove-iam-policy-binding $SERVICIO --region $REGION --project $PROYECTO \\
    --member serviceAccount:$SA_APP_EMAIL --role roles/run.invoker
EOF
    ;;

  b)
    echo "== Opción b: público + x-api-key"
    echo "AVISO: las rutas de ADK (/run, /run_sse, /apps/...) quedan abiertas sin x-api-key." >&2
    read -r -p "¿Ya se quitaron o protegieron en servidor.py? (escribir 'si' para seguir): " ok
    [[ "$ok" == "si" ]] || { echo "Cancelado."; exit 1; }

    # Equivale a --allow-unauthenticated en el deploy. Si una política de organización bloquea
    # allUsers, usar en su lugar:  gcloud run services update $SERVICIO --region $REGION --no-invoker-iam-check
    g run services add-iam-policy-binding "$SERVICIO" --region "$REGION" \
      --member allUsers --role roles/run.invoker

    # Restricción de entrada. Cloud Run no filtra por IP de origen: --ingress solo distingue
    # "all", "internal" e "internal-and-cloud-load-balancing". "internal" dejaría fuera al colegio
    # (llega por internet), así que queda "all". Para aceptar solo la IP pública del colegio hace
    # falta un balanceador HTTPS externo + Cloud Armor (necesita un dominio para el certificado y
    # cuesta ≈ US$18-25/mes). Comandos de referencia, comentados:
    #
    #   IP_COLEGIO=<ip pública del colegio>/32
    #   DOMINIO=agentes.<dominio>
    #   gcloud compute network-endpoint-groups create neg-kiosco --region $REGION \
    #     --network-endpoint-type serverless --cloud-run-service $SERVICIO
    #   gcloud compute backend-services create be-kiosco --global --load-balancing-scheme EXTERNAL_MANAGED
    #   gcloud compute backend-services add-backend be-kiosco --global \
    #     --network-endpoint-group neg-kiosco --network-endpoint-group-region $REGION
    #   gcloud compute security-policies create solo-colegio
    #   gcloud compute security-policies rules update 2147483647 --security-policy solo-colegio --action deny-403
    #   gcloud compute security-policies rules create 1000 --security-policy solo-colegio \
    #     --src-ip-ranges $IP_COLEGIO --action allow
    #   gcloud compute backend-services update be-kiosco --global --security-policy solo-colegio
    #   gcloud compute url-maps create um-kiosco --default-service be-kiosco
    #   gcloud compute ssl-certificates create cert-kiosco --domains $DOMINIO --global
    #   gcloud compute target-https-proxies create px-kiosco --url-map um-kiosco --ssl-certificates cert-kiosco
    #   gcloud compute addresses create ip-entrada-kiosco --global
    #   gcloud compute forwarding-rules create fr-kiosco --global --load-balancing-scheme EXTERNAL_MANAGED \
    #     --address ip-entrada-kiosco --target-https-proxy px-kiosco --ports 443
    #   # y por último cerrar la URL run.app directa:
    #   gcloud run services update $SERVICIO --region $REGION --ingress internal-and-cloud-load-balancing

    cat <<EOF

Listo. En app_kiosco/.env: AGENTES_URL=$URL, AGENTES_API_KEY=<la de agentes-api-key>,
AGENTES_AUDIENCIA_IAM vacío.
Prueba: sin clave -> 401 (servidor.py); con clave -> 200.

Volver atrás (privado otra vez):
  gcloud run services remove-iam-policy-binding $SERVICIO --region $REGION --project $PROYECTO \\
    --member allUsers --role roles/run.invoker
EOF
    ;;

  *)
    echo "Uso: bash abrir_acceso_app.sh a|b   (a = privado + kiosco-app-invoker, recomendada)" >&2
    exit 1 ;;
esac
